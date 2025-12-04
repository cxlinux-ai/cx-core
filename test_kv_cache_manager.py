#!/usr/bin/env python3
"""
Tests for KV-Cache Manager

Run: python -m pytest test_kv_cache_manager.py -v
"""

import unittest
import tempfile
import shutil
import os
import time
from pathlib import Path

from kv_cache_manager import (
    BLOCK_SIZE,
    EvictionPolicy,
    CacheEntry,
    CachePoolConfig,
    BitmapAllocator,
    EvictionManager,
    KVCachePool,
    CacheStore,
    parse_size,
    format_size,
    KVCacheCLI,
)


class TestParseSize(unittest.TestCase):
    """Test size parsing utilities."""

    def test_parse_bytes(self):
        self.assertEqual(parse_size("1024"), 1024)

    def test_parse_kilobytes(self):
        self.assertEqual(parse_size("1K"), 1024)
        self.assertEqual(parse_size("1k"), 1024)

    def test_parse_megabytes(self):
        self.assertEqual(parse_size("1M"), 1024 ** 2)

    def test_parse_gigabytes(self):
        self.assertEqual(parse_size("16G"), 16 * 1024 ** 3)

    def test_parse_terabytes(self):
        self.assertEqual(parse_size("1T"), 1024 ** 4)

    def test_parse_decimal(self):
        self.assertEqual(parse_size("1.5G"), int(1.5 * 1024 ** 3))


class TestFormatSize(unittest.TestCase):
    """Test size formatting."""

    def test_format_bytes(self):
        self.assertIn("B", format_size(500))

    def test_format_kilobytes(self):
        self.assertIn("KB", format_size(2048))

    def test_format_megabytes(self):
        self.assertIn("MB", format_size(2 * 1024 ** 2))

    def test_format_gigabytes(self):
        self.assertIn("GB", format_size(16 * 1024 ** 3))


class TestCacheEntry(unittest.TestCase):
    """Test cache entry dataclass."""

    def test_create_entry(self):
        entry = CacheEntry(
            key="test-key",
            prefix_hash="abc123",
            offset=8192,
            size=4096,
            created_at=time.time(),
            last_accessed=time.time(),
        )
        self.assertEqual(entry.key, "test-key")
        self.assertEqual(entry.size, 4096)

    def test_to_dict(self):
        entry = CacheEntry(
            key="test",
            prefix_hash="hash",
            offset=0,
            size=100,
            created_at=1.0,
            last_accessed=1.0,
        )
        data = entry.to_dict()
        self.assertEqual(data["key"], "test")
        self.assertEqual(data["size"], 100)

    def test_from_dict(self):
        data = {
            "key": "test",
            "prefix_hash": "hash",
            "offset": 0,
            "size": 100,
            "created_at": 1.0,
            "last_accessed": 1.0,
            "access_count": 5,
            "priority": 10,
            "sequence_length": 128,
            "layer_index": 0,
        }
        entry = CacheEntry.from_dict(data)
        self.assertEqual(entry.key, "test")
        self.assertEqual(entry.access_count, 5)


class TestCachePoolConfig(unittest.TestCase):
    """Test pool configuration."""

    def test_create_config(self):
        config = CachePoolConfig(
            name="test-pool",
            size_bytes=16 * 1024 ** 3,
            tier="gpu",
            eviction_policy="lfu",
        )
        self.assertEqual(config.name, "test-pool")
        self.assertEqual(config.tier, "gpu")

    def test_default_values(self):
        config = CachePoolConfig(name="test", size_bytes=1024)
        self.assertEqual(config.tier, "cpu")
        self.assertEqual(config.eviction_policy, "lru")

    def test_to_dict(self):
        config = CachePoolConfig(name="test", size_bytes=1024)
        data = config.to_dict()
        self.assertEqual(data["name"], "test")

    def test_from_dict(self):
        data = {
            "name": "test",
            "size_bytes": 1024,
            "tier": "nvme",
            "eviction_policy": "fifo",
            "max_entries": 5000,
        }
        config = CachePoolConfig.from_dict(data)
        self.assertEqual(config.tier, "nvme")


class TestBitmapAllocator(unittest.TestCase):
    """Test bitmap-based block allocator."""

    def setUp(self):
        self.allocator = BitmapAllocator(1000)

    def test_allocate_single(self):
        block = self.allocator.allocate(1)
        self.assertEqual(block, 0)

    def test_allocate_multiple(self):
        block = self.allocator.allocate(10)
        self.assertEqual(block, 0)
        allocated, total = self.allocator.get_usage()
        self.assertEqual(allocated, 10)

    def test_allocate_consecutive(self):
        b1 = self.allocator.allocate(5)
        b2 = self.allocator.allocate(5)
        self.assertEqual(b1, 0)
        self.assertEqual(b2, 5)

    def test_free(self):
        self.allocator.allocate(10)
        self.allocator.free(0, 5)
        allocated, total = self.allocator.get_usage()
        self.assertEqual(allocated, 5)

    def test_reuse_freed(self):
        self.allocator.allocate(10)
        self.allocator.free(0, 5)
        block = self.allocator.allocate(3)
        self.assertEqual(block, 0)

    def test_full_allocation(self):
        self.allocator.allocate(1000)
        block = self.allocator.allocate(1)
        self.assertIsNone(block)

    def test_get_usage(self):
        self.allocator.allocate(100)
        allocated, total = self.allocator.get_usage()
        self.assertEqual(allocated, 100)
        self.assertEqual(total, 1000)

    def test_serialize_restore(self):
        self.allocator.allocate(50)
        data = self.allocator.to_bytes()

        new_allocator = BitmapAllocator(1000)
        new_allocator.from_bytes(data)

        allocated, total = new_allocator.get_usage()
        self.assertEqual(allocated, 50)


class TestEvictionManager(unittest.TestCase):
    """Test eviction policy management."""

    def _make_entry(self, key: str, created: float = None,
                    accessed: float = None, count: int = 0,
                    priority: int = 0) -> CacheEntry:
        now = time.time()
        return CacheEntry(
            key=key,
            prefix_hash="hash",
            offset=0,
            size=100,
            created_at=created or now,
            last_accessed=accessed or now,
            access_count=count,
            priority=priority,
        )

    def test_lru_eviction(self):
        manager = EvictionManager(EvictionPolicy.LRU)

        # Add entries with different access times
        e1 = self._make_entry("e1", accessed=1.0)
        e2 = self._make_entry("e2", accessed=2.0)
        e3 = self._make_entry("e3", accessed=3.0)

        manager.add(e1)
        manager.add(e2)
        manager.add(e3)

        candidates = manager.get_eviction_candidates(2)
        self.assertEqual(candidates, ["e1", "e2"])

    def test_lfu_eviction(self):
        manager = EvictionManager(EvictionPolicy.LFU)

        e1 = self._make_entry("e1", count=10)
        e2 = self._make_entry("e2", count=5)
        e3 = self._make_entry("e3", count=1)

        manager.add(e1)
        manager.add(e2)
        manager.add(e3)

        candidates = manager.get_eviction_candidates(2)
        self.assertIn("e3", candidates)  # Lowest count

    def test_fifo_eviction(self):
        manager = EvictionManager(EvictionPolicy.FIFO)

        e1 = self._make_entry("e1", created=1.0)
        e2 = self._make_entry("e2", created=2.0)
        e3 = self._make_entry("e3", created=3.0)

        manager.add(e1)
        manager.add(e2)
        manager.add(e3)

        candidates = manager.get_eviction_candidates(2)
        self.assertEqual(candidates, ["e1", "e2"])

    def test_priority_eviction(self):
        manager = EvictionManager(EvictionPolicy.PRIORITY)

        e1 = self._make_entry("e1", priority=100)
        e2 = self._make_entry("e2", priority=50)
        e3 = self._make_entry("e3", priority=10)

        manager.add(e1)
        manager.add(e2)
        manager.add(e3)

        candidates = manager.get_eviction_candidates(2)
        self.assertIn("e3", candidates)  # Lowest priority

    def test_access_updates_lru(self):
        manager = EvictionManager(EvictionPolicy.LRU)

        e1 = self._make_entry("e1")
        e2 = self._make_entry("e2")

        manager.add(e1)
        manager.add(e2)

        # Access e1, making it more recent
        time.sleep(0.01)
        manager.access("e1")

        candidates = manager.get_eviction_candidates(1)
        self.assertEqual(candidates, ["e2"])


class TestKVCachePool(unittest.TestCase):
    """Test KV-cache pool operations."""

    def setUp(self):
        self.config = CachePoolConfig(
            name="test-pool",
            size_bytes=1024 * 1024,  # 1MB
            eviction_policy="lru",
        )
        self.pool = KVCachePool(self.config)

    def test_allocate(self):
        entry = self.pool.allocate("key1", 1000)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.key, "key1")
        self.assertEqual(entry.size, 1000)

    def test_put_get(self):
        data = b"Hello, KV Cache!"
        self.pool.put("greeting", data)

        retrieved = self.pool.get("greeting")
        self.assertEqual(retrieved, data)

    def test_get_nonexistent(self):
        result = self.pool.get("nonexistent")
        self.assertIsNone(result)

    def test_delete(self):
        self.pool.put("to-delete", b"data")
        self.assertTrue(self.pool.delete("to-delete"))
        self.assertIsNone(self.pool.get("to-delete"))

    def test_multiple_entries(self):
        for i in range(10):
            self.pool.put(f"key{i}", f"value{i}".encode())

        for i in range(10):
            data = self.pool.get(f"key{i}")
            self.assertEqual(data, f"value{i}".encode())

    def test_eviction(self):
        # Fill pool with entries
        for i in range(100):
            self.pool.put(f"key{i}", b"x" * 1000)

        initial_count = len(self.pool.entries)
        evicted = self.pool.evict(25)

        self.assertGreater(evicted, 0)
        self.assertLess(len(self.pool.entries), initial_count)

    def test_find_by_prefix(self):
        # Create entries with same prefix
        for i in range(3):
            entry = self.pool.allocate(f"prompt-{i}", 100, prefix_hash="shared-prefix")

        matches = self.pool.find_by_prefix("shared-prefix")
        self.assertEqual(len(matches), 3)

    def test_get_stats(self):
        self.pool.put("key1", b"data1")
        self.pool.put("key2", b"data2")

        stats = self.pool.get_stats()
        self.assertEqual(stats["name"], "test-pool")
        self.assertEqual(stats["entry_count"], 2)
        self.assertIn("utilization_percent", stats)

    def test_auto_eviction_on_full(self):
        # Fill pool
        large_data = b"x" * (BLOCK_SIZE * 2)
        entries_created = 0

        for i in range(50):
            if self.pool.put(f"key{i}", large_data):
                entries_created += 1
            else:
                break

        # Pool should have evicted some to make room
        self.assertGreater(entries_created, 0)


class TestCachePoolPersistence(unittest.TestCase):
    """Test pool persistence."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = CachePoolConfig(
            name="persist-test",
            size_bytes=64 * 1024,
        )
        self.pool = KVCachePool(self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_persist_and_restore(self):
        # Add data
        self.pool.put("key1", b"data1")
        self.pool.put("key2", b"data2")

        # Persist
        persist_path = os.path.join(self.temp_dir, "cache.dat")
        self.assertTrue(self.pool.persist(persist_path))

        # Restore
        restored = KVCachePool.restore(persist_path)
        self.assertIsNotNone(restored)

        # Verify data
        self.assertEqual(restored.get("key1"), b"data1")
        self.assertEqual(restored.get("key2"), b"data2")

    def test_restore_nonexistent(self):
        result = KVCachePool.restore("/nonexistent/path")
        self.assertIsNone(result)


class TestCacheStore(unittest.TestCase):
    """Test cache store management."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = CacheStore(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_create_pool(self):
        config = CachePoolConfig(name="pool1", size_bytes=16384)  # 16KB minimum for header+bitmap
        pool = self.store.create(config)
        self.assertIsNotNone(pool)

    def test_get_pool(self):
        config = CachePoolConfig(name="pool1", size_bytes=16384)  # 16KB minimum for header+bitmap
        self.store.create(config)

        pool = self.store.get("pool1")
        self.assertIsNotNone(pool)

    def test_get_nonexistent(self):
        pool = self.store.get("nonexistent")
        self.assertIsNone(pool)

    def test_delete_pool(self):
        config = CachePoolConfig(name="to-delete", size_bytes=16384)  # 16KB minimum for header+bitmap
        self.store.create(config)

        self.assertTrue(self.store.delete("to-delete"))
        self.assertIsNone(self.store.get("to-delete"))

    def test_list_pools(self):
        self.store.create(CachePoolConfig(name="p1", size_bytes=16384))  # 16KB minimum
        self.store.create(CachePoolConfig(name="p2", size_bytes=16384))  # 16KB minimum

        pools = self.store.list()
        self.assertIn("p1", pools)
        self.assertIn("p2", pools)


class TestCLI(unittest.TestCase):
    """Test CLI commands."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cli = KVCacheCLI()
        self.cli.store = CacheStore(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_cli_initialization(self):
        cli = KVCacheCLI()
        self.assertIsNotNone(cli.store)


class TestEndToEnd(unittest.TestCase):
    """End-to-end integration tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = CacheStore(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_llm_cache_workflow(self):
        # Create cache for LLM inference
        config = CachePoolConfig(
            name="llama-cache",
            size_bytes=16 * 1024 * 1024,  # 16MB for test
            tier="cpu",
            eviction_policy="lru",
        )
        pool = self.store.create(config)

        # Simulate KV cache entries for different layers
        for layer in range(32):
            key = f"batch0_layer{layer}_kv"
            # Simulated KV cache tensor (in practice would be numpy/torch)
            kv_data = b"x" * 4096
            pool.put(key, kv_data, layer_index=layer, sequence_length=128)

        # Verify all entries
        self.assertEqual(len(pool.entries), 32)

        # Simulate access pattern
        for i in range(10):
            pool.get("batch0_layer0_kv")  # Hot layer

        # Evict cold entries
        evicted = pool.evict(25)
        self.assertGreater(evicted, 0)

        # Hot layer should still be there
        self.assertIsNotNone(pool.get("batch0_layer0_kv"))

    def test_prefix_sharing_workflow(self):
        config = CachePoolConfig(name="shared-cache", size_bytes=1024 * 1024)
        pool = self.store.create(config)

        # Same prompt prefix = same prefix hash
        prefix_hash = "system_prompt_hash"

        # Multiple requests with same prefix
        for i in range(5):
            pool.put(f"req{i}_kv", b"cached_kv" * 100, prefix_hash=prefix_hash)

        # Find all caches that share the prefix
        shared = pool.find_by_prefix(prefix_hash)
        self.assertEqual(len(shared), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
