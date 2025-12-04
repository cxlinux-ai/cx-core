#!/usr/bin/env python3
"""
KV-Cache Manager - User-Space Cache Management for LLM Inference

Manages transformer key-value caches as first-class system resources.
POSIX shared memory pools with multiple eviction policies.

Usage:
    cortex cache create llama-cache --size 16G --tier cpu
    cortex cache status llama-cache
    cortex cache persist llama-cache
    cortex cache restore llama-cache
    cortex cache evict llama-cache --percent 25

Author: Yair Siegel
Bounty: cortexlinux/cortex#221
"""

import os
import sys
import json
import mmap
import struct
import hashlib
import argparse
import threading
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from enum import Enum
from collections import OrderedDict
import time


# =============================================================================
# CONSTANTS
# =============================================================================

CACHE_MAGIC = b'KVCH'  # Magic bytes for cache header
CACHE_VERSION = 1
BLOCK_SIZE = 4096  # 4KB blocks
HEADER_SIZE = 4096  # Header block
BITMAP_SIZE = 4096  # Free list bitmap


# =============================================================================
# EVICTION POLICIES
# =============================================================================

class EvictionPolicy(Enum):
    LRU = "lru"      # Least Recently Used
    LFU = "lfu"      # Least Frequently Used
    FIFO = "fifo"    # First In First Out
    PRIORITY = "priority"  # Priority-based (user-defined)


# =============================================================================
# CACHE ENTRY
# =============================================================================

@dataclass
class CacheEntry:
    """Metadata for a cached KV tensor."""
    key: str
    prefix_hash: str  # Hash of prompt prefix for sharing
    offset: int       # Byte offset in pool
    size: int         # Size in bytes
    created_at: float
    last_accessed: float
    access_count: int = 0
    priority: int = 0  # Higher = more important
    sequence_length: int = 0
    layer_index: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'CacheEntry':
        return cls(**data)


# =============================================================================
# CACHE POOL CONFIGURATION
# =============================================================================

@dataclass
class CachePoolConfig:
    """Configuration for a KV-cache pool."""
    name: str
    size_bytes: int
    tier: str = "cpu"  # cpu, gpu, nvme
    eviction_policy: str = "lru"
    max_entries: int = 10000
    persist_path: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'CachePoolConfig':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =============================================================================
# BITMAP ALLOCATOR
# =============================================================================

class BitmapAllocator:
    """
    Thread-safe bitmap-based block allocator.

    Each bit represents one block. 1 = allocated, 0 = free.
    """

    def __init__(self, num_blocks: int):
        self.num_blocks = num_blocks
        self.bitmap_size = (num_blocks + 7) // 8
        self.bitmap = bytearray(self.bitmap_size)
        self.lock = threading.Lock()
        self.allocated_count = 0

    def allocate(self, num_blocks: int) -> Optional[int]:
        """
        Allocate contiguous blocks. Returns starting block index or None.
        """
        with self.lock:
            # Simple first-fit algorithm
            consecutive = 0
            start_block = 0

            for i in range(self.num_blocks):
                if self._is_free(i):
                    if consecutive == 0:
                        start_block = i
                    consecutive += 1
                    if consecutive == num_blocks:
                        # Found enough space, mark as allocated
                        for j in range(start_block, start_block + num_blocks):
                            self._set_allocated(j)
                        self.allocated_count += num_blocks
                        return start_block
                else:
                    consecutive = 0

            return None

    def free(self, start_block: int, num_blocks: int):
        """Free allocated blocks."""
        with self.lock:
            for i in range(start_block, start_block + num_blocks):
                self._set_free(i)
            self.allocated_count -= num_blocks

    def _is_free(self, block: int) -> bool:
        byte_idx = block // 8
        bit_idx = block % 8
        return (self.bitmap[byte_idx] & (1 << bit_idx)) == 0

    def _set_allocated(self, block: int):
        byte_idx = block // 8
        bit_idx = block % 8
        self.bitmap[byte_idx] |= (1 << bit_idx)

    def _set_free(self, block: int):
        byte_idx = block // 8
        bit_idx = block % 8
        self.bitmap[byte_idx] &= ~(1 << bit_idx)

    def get_usage(self) -> Tuple[int, int]:
        """Returns (allocated_blocks, total_blocks)."""
        return (self.allocated_count, self.num_blocks)

    def to_bytes(self) -> bytes:
        """Serialize bitmap for persistence."""
        return bytes(self.bitmap)

    def from_bytes(self, data: bytes):
        """Restore bitmap from persistence."""
        self.bitmap = bytearray(data[:self.bitmap_size])
        # Recount allocated
        self.allocated_count = sum(
            bin(b).count('1') for b in self.bitmap
        )


# =============================================================================
# EVICTION MANAGER
# =============================================================================

class EvictionManager:
    """Manages cache eviction based on configured policy."""

    def __init__(self, policy: EvictionPolicy):
        self.policy = policy
        self.entries: Dict[str, CacheEntry] = {}
        self.access_order: OrderedDict = OrderedDict()  # For LRU
        self.lock = threading.Lock()

    def add(self, entry: CacheEntry):
        """Add entry to eviction tracking."""
        with self.lock:
            self.entries[entry.key] = entry
            if self.policy == EvictionPolicy.LRU:
                self.access_order[entry.key] = entry.last_accessed
            elif self.policy == EvictionPolicy.FIFO:
                self.access_order[entry.key] = entry.created_at

    def access(self, key: str):
        """Record access (for LRU/LFU)."""
        with self.lock:
            if key in self.entries:
                entry = self.entries[key]
                entry.last_accessed = time.time()
                entry.access_count += 1

                if self.policy == EvictionPolicy.LRU:
                    # Move to end of order
                    self.access_order.move_to_end(key)

    def remove(self, key: str):
        """Remove entry from tracking."""
        with self.lock:
            if key in self.entries:
                del self.entries[key]
            if key in self.access_order:
                del self.access_order[key]

    def get_eviction_candidates(self, count: int) -> List[str]:
        """Get keys to evict based on policy."""
        with self.lock:
            if self.policy == EvictionPolicy.LRU:
                # Oldest accessed first
                return list(self.access_order.keys())[:count]

            elif self.policy == EvictionPolicy.LFU:
                # Least accessed first
                sorted_entries = sorted(
                    self.entries.items(),
                    key=lambda x: x[1].access_count
                )
                return [k for k, v in sorted_entries[:count]]

            elif self.policy == EvictionPolicy.FIFO:
                # First created first
                return list(self.access_order.keys())[:count]

            elif self.policy == EvictionPolicy.PRIORITY:
                # Lowest priority first
                sorted_entries = sorted(
                    self.entries.items(),
                    key=lambda x: x[1].priority
                )
                return [k for k, v in sorted_entries[:count]]

            return []

    def get_all_entries(self) -> List[CacheEntry]:
        """Get all tracked entries."""
        with self.lock:
            return list(self.entries.values())


# =============================================================================
# KV CACHE POOL
# =============================================================================

class KVCachePool:
    """
    POSIX shared memory pool for KV-cache tensors.

    Memory Layout:
    ┌──────────────────┐
    │ Header (4KB)     │ Magic, version, config
    ├──────────────────┤
    │ Bitmap (4KB)     │ Free list
    ├──────────────────┤
    │ Data Region      │ KV tensors
    └──────────────────┘
    """

    def __init__(self, config: CachePoolConfig, create: bool = True):
        self.config = config
        self.name = config.name
        self.size = config.size_bytes

        # Calculate blocks
        self.data_offset = HEADER_SIZE + BITMAP_SIZE
        self.data_size = self.size - self.data_offset
        self.num_blocks = self.data_size // BLOCK_SIZE

        # Initialize allocator and eviction manager
        self.allocator = BitmapAllocator(self.num_blocks)
        self.eviction = EvictionManager(EvictionPolicy(config.eviction_policy))

        # Entry index
        self.entries: Dict[str, CacheEntry] = {}
        self.prefix_index: Dict[str, List[str]] = {}  # prefix_hash -> keys
        self.lock = threading.Lock()

        # Memory mapping (simulated for portability)
        self._data = bytearray(self.data_size)

        if create:
            self._init_header()

    def _init_header(self):
        """Initialize pool header."""
        # In real implementation, this would write to shared memory
        pass

    def allocate(self, key: str, size: int, prefix_hash: str = "",
                 priority: int = 0, sequence_length: int = 0,
                 layer_index: int = 0) -> Optional[CacheEntry]:
        """Allocate space for a KV cache entry."""
        num_blocks = (size + BLOCK_SIZE - 1) // BLOCK_SIZE

        with self.lock:
            # Try to allocate
            start_block = self.allocator.allocate(num_blocks)

            if start_block is None:
                # Need to evict
                freed = self._evict_for_space(num_blocks)
                if freed:
                    start_block = self.allocator.allocate(num_blocks)

            if start_block is None:
                return None

            # Create entry
            now = time.time()
            entry = CacheEntry(
                key=key,
                prefix_hash=prefix_hash or self._compute_prefix_hash(key),
                offset=self.data_offset + (start_block * BLOCK_SIZE),
                size=size,
                created_at=now,
                last_accessed=now,
                priority=priority,
                sequence_length=sequence_length,
                layer_index=layer_index,
            )

            # Track entry
            self.entries[key] = entry
            self.eviction.add(entry)

            # Update prefix index
            if entry.prefix_hash not in self.prefix_index:
                self.prefix_index[entry.prefix_hash] = []
            self.prefix_index[entry.prefix_hash].append(key)

            return entry

    def get(self, key: str) -> Optional[bytes]:
        """Get cached data by key."""
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None

            self.eviction.access(key)

            # Read from data region
            start = entry.offset - self.data_offset
            return bytes(self._data[start:start + entry.size])

    def put(self, key: str, data: bytes, **kwargs) -> bool:
        """Store data in cache."""
        entry = self.allocate(key, len(data), **kwargs)
        if entry is None:
            return False

        # Write to data region
        start = entry.offset - self.data_offset
        self._data[start:start + len(data)] = data
        return True

    def delete(self, key: str) -> bool:
        """Delete entry from cache."""
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return False

            # Free blocks
            start_block = (entry.offset - self.data_offset) // BLOCK_SIZE
            num_blocks = (entry.size + BLOCK_SIZE - 1) // BLOCK_SIZE
            self.allocator.free(start_block, num_blocks)

            # Remove from tracking
            del self.entries[key]
            self.eviction.remove(key)

            # Update prefix index
            if entry.prefix_hash in self.prefix_index:
                self.prefix_index[entry.prefix_hash].remove(key)
                if not self.prefix_index[entry.prefix_hash]:
                    del self.prefix_index[entry.prefix_hash]

            return True

    def find_by_prefix(self, prefix_hash: str) -> List[CacheEntry]:
        """Find cache entries by prefix hash (for sharing)."""
        with self.lock:
            keys = self.prefix_index.get(prefix_hash, [])
            return [self.entries[k] for k in keys if k in self.entries]

    def evict(self, percent: float) -> int:
        """Evict a percentage of entries."""
        count = int(len(self.entries) * (percent / 100))
        return self._evict_entries(count)

    def _evict_for_space(self, blocks_needed: int) -> bool:
        """Evict entries to free space."""
        allocated, total = self.allocator.get_usage()
        free = total - allocated

        if free >= blocks_needed:
            return True

        # Evict until we have space
        candidates = self.eviction.get_eviction_candidates(len(self.entries))
        freed = 0

        for key in candidates:
            entry = self.entries.get(key)
            if entry:
                entry_blocks = (entry.size + BLOCK_SIZE - 1) // BLOCK_SIZE
                self.delete(key)
                freed += entry_blocks

                if freed >= blocks_needed:
                    return True

        return freed >= blocks_needed

    def _evict_entries(self, count: int) -> int:
        """Evict specified number of entries."""
        candidates = self.eviction.get_eviction_candidates(count)
        evicted = 0

        for key in candidates:
            if self.delete(key):
                evicted += 1

        return evicted

    def _compute_prefix_hash(self, key: str) -> str:
        """Compute prefix hash for cache sharing."""
        # Simple hash - in practice would hash actual prompt prefix
        return hashlib.sha256(key.encode()[:64]).hexdigest()[:16]

    def get_stats(self) -> Dict:
        """Get pool statistics."""
        allocated, total = self.allocator.get_usage()
        return {
            "name": self.name,
            "size_bytes": self.size,
            "data_size_bytes": self.data_size,
            "block_size": BLOCK_SIZE,
            "total_blocks": total,
            "allocated_blocks": allocated,
            "free_blocks": total - allocated,
            "utilization_percent": (allocated / total * 100) if total > 0 else 0,
            "entry_count": len(self.entries),
            "policy": self.config.eviction_policy,
        }

    def persist(self, path: str) -> bool:
        """Persist pool to disk."""
        persist_path = Path(path)
        persist_path.parent.mkdir(parents=True, exist_ok=True)

        with self.lock:
            try:
                data = {
                    "config": self.config.to_dict(),
                    "entries": {k: v.to_dict() for k, v in self.entries.items()},
                    "bitmap": self.allocator.to_bytes().hex(),
                    "data": self._data.hex(),
                }
                persist_path.write_text(json.dumps(data))
                return True
            except Exception as e:
                print(f"[ERROR] Failed to persist: {e}")
                return False

    @classmethod
    def restore(cls, path: str) -> Optional['KVCachePool']:
        """Restore pool from disk."""
        persist_path = Path(path)
        if not persist_path.exists():
            return None

        try:
            data = json.loads(persist_path.read_text())
            config = CachePoolConfig.from_dict(data["config"])
            pool = cls(config, create=False)

            # Restore bitmap
            pool.allocator.from_bytes(bytes.fromhex(data["bitmap"]))

            # Restore data
            pool._data = bytearray(bytes.fromhex(data["data"]))

            # Restore entries
            for key, entry_data in data["entries"].items():
                entry = CacheEntry.from_dict(entry_data)
                pool.entries[key] = entry
                pool.eviction.add(entry)

                if entry.prefix_hash not in pool.prefix_index:
                    pool.prefix_index[entry.prefix_hash] = []
                pool.prefix_index[entry.prefix_hash].append(key)

            return pool
        except Exception as e:
            print(f"[ERROR] Failed to restore: {e}")
            return None


# =============================================================================
# CACHE STORE
# =============================================================================

class CacheStore:
    """Manages multiple KV-cache pools."""

    def __init__(self, store_path: str = None):
        if store_path is None:
            store_path = os.path.expanduser("~/.config/cortex/kv_cache")
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)
        self.pools: Dict[str, KVCachePool] = {}

    def create(self, config: CachePoolConfig) -> KVCachePool:
        """Create a new cache pool."""
        pool = KVCachePool(config)
        self.pools[config.name] = pool
        self._save_config(config)
        return pool

    def get(self, name: str) -> Optional[KVCachePool]:
        """Get pool by name."""
        if name in self.pools:
            return self.pools[name]

        # Try to load from disk
        config = self._load_config(name)
        if config:
            pool = KVCachePool(config)
            self.pools[name] = pool
            return pool

        return None

    def delete(self, name: str) -> bool:
        """Delete a pool."""
        if name in self.pools:
            del self.pools[name]

        config_path = self.store_path / f"{name}.json"
        if config_path.exists():
            config_path.unlink()
            return True
        return False

    def list(self) -> List[str]:
        """List all pools."""
        return [p.stem for p in self.store_path.glob("*.json")]

    def _save_config(self, config: CachePoolConfig):
        """Save pool configuration."""
        config_path = self.store_path / f"{config.name}.json"
        config_path.write_text(json.dumps(config.to_dict(), indent=2))

    def _load_config(self, name: str) -> Optional[CachePoolConfig]:
        """Load pool configuration."""
        config_path = self.store_path / f"{name}.json"
        if config_path.exists():
            return CachePoolConfig.from_dict(json.loads(config_path.read_text()))
        return None


# =============================================================================
# CLI
# =============================================================================

def parse_size(size_str: str) -> int:
    """Parse size string like '16G' to bytes."""
    size_str = size_str.upper().strip()
    multipliers = {
        'K': 1024,
        'M': 1024 ** 2,
        'G': 1024 ** 3,
        'T': 1024 ** 4,
    }

    if size_str[-1] in multipliers:
        return int(float(size_str[:-1]) * multipliers[size_str[-1]])
    return int(size_str)


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


class KVCacheCLI:
    """CLI for cortex cache command."""

    def __init__(self):
        self.store = CacheStore()

    def create(self, args):
        """Create a new cache pool."""
        size = parse_size(args.size)

        config = CachePoolConfig(
            name=args.name,
            size_bytes=size,
            tier=args.tier,
            eviction_policy=args.policy,
        )

        pool = self.store.create(config)
        stats = pool.get_stats()

        print(f"Created cache pool '{args.name}'")
        print(f"  Size: {format_size(size)}")
        print(f"  Tier: {args.tier}")
        print(f"  Policy: {args.policy}")
        print(f"  Blocks: {stats['total_blocks']}")
        return 0

    def status(self, args):
        """Show cache status."""
        if args.name:
            pool = self.store.get(args.name)
            if not pool:
                print(f"Cache '{args.name}' not found")
                return 1

            stats = pool.get_stats()
            print(f"Cache: {stats['name']}")
            print(f"  Size: {format_size(stats['size_bytes'])}")
            print(f"  Used: {format_size(stats['allocated_blocks'] * BLOCK_SIZE)}")
            print(f"  Free: {format_size(stats['free_blocks'] * BLOCK_SIZE)}")
            print(f"  Utilization: {stats['utilization_percent']:.1f}%")
            print(f"  Entries: {stats['entry_count']}")
            print(f"  Policy: {stats['policy']}")
        else:
            pools = self.store.list()
            if not pools:
                print("No cache pools")
                return 0

            print("Cache pools:")
            for name in pools:
                pool = self.store.get(name)
                if pool:
                    stats = pool.get_stats()
                    print(f"  {name}: {format_size(stats['size_bytes'])} ({stats['utilization_percent']:.1f}% used)")

        return 0

    def persist(self, args):
        """Persist cache to disk."""
        pool = self.store.get(args.name)
        if not pool:
            print(f"Cache '{args.name}' not found")
            return 1

        persist_path = args.path or f"/tmp/cortex_cache_{args.name}.dat"
        if pool.persist(persist_path):
            print(f"Persisted cache '{args.name}' to {persist_path}")
            return 0
        return 1

    def restore(self, args):
        """Restore cache from disk."""
        persist_path = args.path
        if not Path(persist_path).exists():
            print(f"File not found: {persist_path}")
            return 1

        pool = KVCachePool.restore(persist_path)
        if pool:
            self.store.pools[pool.name] = pool
            print(f"Restored cache '{pool.name}' from {persist_path}")
            return 0
        return 1

    def evict(self, args):
        """Evict entries from cache."""
        pool = self.store.get(args.name)
        if not pool:
            print(f"Cache '{args.name}' not found")
            return 1

        evicted = pool.evict(args.percent)
        print(f"Evicted {evicted} entries from '{args.name}'")
        return 0

    def delete(self, args):
        """Delete a cache pool."""
        if self.store.delete(args.name):
            print(f"Deleted cache '{args.name}'")
            return 0
        print(f"Cache '{args.name}' not found")
        return 1

    def policies(self, args):
        """List available eviction policies."""
        print("Available eviction policies:")
        for policy in EvictionPolicy:
            desc = {
                "lru": "Least Recently Used - evict oldest accessed",
                "lfu": "Least Frequently Used - evict least accessed",
                "fifo": "First In First Out - evict oldest created",
                "priority": "Priority-based - evict lowest priority",
            }
            print(f"  {policy.value}: {desc[policy.value]}")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="KV-Cache Manager",
        prog="cortex cache"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    create_parser = subparsers.add_parser("create", help="Create cache pool")
    create_parser.add_argument("name", help="Pool name")
    create_parser.add_argument("--size", "-s", required=True, help="Pool size (e.g., 16G)")
    create_parser.add_argument("--tier", "-t", default="cpu",
                              choices=["cpu", "gpu", "nvme"], help="Memory tier")
    create_parser.add_argument("--policy", "-p", default="lru",
                              choices=[p.value for p in EvictionPolicy],
                              help="Eviction policy")

    # status
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.add_argument("name", nargs="?", help="Pool name")

    # persist
    persist_parser = subparsers.add_parser("persist", help="Persist to disk")
    persist_parser.add_argument("name", help="Pool name")
    persist_parser.add_argument("--path", help="Persistence path")

    # restore
    restore_parser = subparsers.add_parser("restore", help="Restore from disk")
    restore_parser.add_argument("path", help="Persistence path")

    # evict
    evict_parser = subparsers.add_parser("evict", help="Evict entries")
    evict_parser.add_argument("name", help="Pool name")
    evict_parser.add_argument("--percent", "-p", type=float, default=25,
                             help="Percent to evict")

    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete pool")
    delete_parser.add_argument("name", help="Pool name")

    # policies
    subparsers.add_parser("policies", help="List eviction policies")

    args = parser.parse_args()
    cli = KVCacheCLI()

    commands = {
        "create": cli.create,
        "status": cli.status,
        "persist": cli.persist,
        "restore": cli.restore,
        "evict": cli.evict,
        "delete": cli.delete,
        "policies": cli.policies,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
