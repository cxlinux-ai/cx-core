#!/usr/bin/env python3
"""
Cortex KV-Cache Manager

User-space KV-cache management for LLM inference optimization.
"""

import builtins
import contextlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from enum import Enum
from multiprocessing import shared_memory
from pathlib import Path

from cortex.utils.db_pool import get_connection_pool

CORTEX_DB = Path.home() / ".cortex/kv_cache.db"
SHM_PREFIX = "cortex_kv_"


class CachePolicy(Enum):
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"


@dataclass
class CacheConfig:
    name: str
    size_bytes: int
    policy: str = "lru"
    max_sequences: int = 1000


@dataclass
class CacheEntry:
    sequence_id: int
    created_at: float
    last_accessed: float
    access_count: int
    token_count: int
    size_bytes: int
    offset: int


class CacheDatabase:
    def __init__(self):
        CORTEX_DB.parent.mkdir(parents=True, exist_ok=True)
        self._pool = get_connection_pool(str(CORTEX_DB), pool_size=5)
        with self._pool.get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pools (name TEXT PRIMARY KEY, config TEXT, shm_name TEXT);
                CREATE TABLE IF NOT EXISTS entries (seq_id INTEGER, pool TEXT, created REAL, accessed REAL,
                    count INTEGER, tokens INTEGER, size INTEGER, offset INTEGER, PRIMARY KEY(seq_id, pool));
                CREATE TABLE IF NOT EXISTS stats (pool TEXT PRIMARY KEY, hits INTEGER DEFAULT 0, misses INTEGER DEFAULT 0);
            """)

    def save_pool(self, cfg: CacheConfig, shm: str):
        with self._pool.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pools VALUES (?,?,?)",
                (cfg.name, json.dumps(asdict(cfg)), shm),
            )
            conn.execute("INSERT OR IGNORE INTO stats (pool) VALUES (?)", (cfg.name,))

    def get_pool(self, name: str):
        with self._pool.get_connection() as conn:
            row = conn.execute(
                "SELECT config, shm_name FROM pools WHERE name=?", (name,)
            ).fetchone()
            return (CacheConfig(**json.loads(row[0])), row[1]) if row else None

    def list_pools(self):
        with self._pool.get_connection() as conn:
            return [
                CacheConfig(**json.loads(r[0]))
                for r in conn.execute("SELECT config FROM pools").fetchall()
            ]


class SharedMemoryPool:
    def __init__(self, name: str, size: int, create: bool = True):
        self.name = f"{SHM_PREFIX}{name}"
        self.size = size
        if create:
            try:
                old = shared_memory.SharedMemory(name=self.name)
                old.close()
                old.unlink()
            except:
                pass
            self.shm = shared_memory.SharedMemory(name=self.name, create=True, size=size + 8192)
        else:
            self.shm = shared_memory.SharedMemory(name=self.name)

    def get_usage(self):
        return self.size, 0, 0  # Simplified

    def destroy(self):
        self.shm.close()
        with contextlib.suppress(builtins.BaseException):
            self.shm.unlink()


class KVCacheManager:
    def __init__(self):
        self.db = CacheDatabase()
        self.pools: dict[str, SharedMemoryPool] = {}

    def create_pool(self, cfg: CacheConfig) -> bool:
        pool = SharedMemoryPool(cfg.name, cfg.size_bytes)
        self.pools[cfg.name] = pool
        self.db.save_pool(cfg, pool.name)
        print(f"✅ Created cache pool '{cfg.name}' ({cfg.size_bytes / 1e9:.1f} GB)")
        return True

    def destroy_pool(self, name: str) -> bool:
        if name in self.pools:
            self.pools[name].destroy()
            del self.pools[name]
        with self.db._pool.get_connection() as conn:
            conn.execute("DELETE FROM pools WHERE name=?", (name,))
        print(f"✅ Destroyed pool '{name}'")
        return True

    def status(self, name: str = None):
        pools = [self.db.get_pool(name)] if name else [(p, "") for p in self.db.list_pools()]
        print(f"\n{'POOL':<20} {'SIZE':<12} {'POLICY':<10}")
        print("-" * 50)
        for item in pools:
            if item:
                cfg = item[0] if isinstance(item, tuple) else item
                print(f"{cfg.name:<20} {cfg.size_bytes / 1e9:.1f}G{'':<6} {cfg.policy:<10}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Cortex KV-Cache Manager")
    sub = parser.add_subparsers(dest="cmd")

    c = sub.add_parser("create")
    c.add_argument("name")
    c.add_argument("--size", required=True)
    c.add_argument("--policy", default="lru")

    sub.add_parser("destroy").add_argument("name")
    sub.add_parser("status").add_argument("name", nargs="?")
    sub.add_parser("list")

    args = parser.parse_args()
    mgr = KVCacheManager()

    if args.cmd == "create":
        size_str = args.size.upper()
        mult = {"K": 1e3, "M": 1e6, "G": 1e9}.get(size_str[-1], 1)
        size = int(float(size_str.rstrip("KMG")) * mult)
        mgr.create_pool(CacheConfig(args.name, size, args.policy))
    elif args.cmd == "destroy":
        mgr.destroy_pool(args.name)
    elif args.cmd in ("status", "list"):
        mgr.status(getattr(args, "name", None))


if __name__ == "__main__":
    main()
