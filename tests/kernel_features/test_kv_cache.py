import pytest
from cortex.kernel_features.kv_cache_manager import CacheConfig, KVCacheManager

def test_cache_config():
    cfg = CacheConfig("test", 1024*1024*16)
    assert cfg.policy == "lru"
    assert cfg.max_sequences == 1000
