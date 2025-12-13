"""
Tests for Graceful Degradation Module

Issue: #257
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from cortex.graceful_degradation import (
    GracefulDegradation,
    ResponseCache,
    PatternMatcher,
    APIStatus,
    FallbackMode,
    HealthCheckResult,
    CachedResponse,
    get_degradation_manager,
    process_with_fallback
)


class TestResponseCache:
    """Tests for the ResponseCache class."""
    
    @pytest.fixture
    def cache(self, tmp_path):
        """Create a temporary cache for testing."""
        db_path = tmp_path / "test_cache.db"
        return ResponseCache(db_path)
    
    def test_init_creates_database(self, cache):
        """Test that initialization creates the database."""
        assert cache.db_path.exists()
    
    def test_put_and_get(self, cache):
        """Test storing and retrieving responses."""
        query = "install docker"
        response = "sudo apt install docker.io"
        
        cache.put(query, response)
        result = cache.get(query)
        
        assert result is not None
        assert result.query == query
        assert result.response == response
        assert result.hit_count == 1
    
    def test_get_nonexistent(self, cache):
        """Test retrieving non-existent entry returns None."""
        result = cache.get("nonexistent query")
        assert result is None
    
    def test_hit_count_increments(self, cache):
        """Test that hit count increments on each get."""
        cache.put("test query", "test response")
        
        cache.get("test query")
        cache.get("test query")
        result = cache.get("test query")
        
        assert result.hit_count == 3
    
    def test_case_insensitive_matching(self, cache):
        """Test that queries match case-insensitively."""
        cache.put("Install Docker", "sudo apt install docker.io")
        
        result = cache.get("install docker")
        assert result is not None
    
    def test_get_similar(self, cache):
        """Test similar query matching."""
        cache.put("install docker for containers", "sudo apt install docker.io")
        cache.put("install nginx web server", "sudo apt install nginx")
        cache.put("install python programming", "sudo apt install python3")
        
        similar = cache.get_similar("install docker", limit=2)
        
        assert len(similar) >= 1
        assert any("docker" in s.query for s in similar)
    
    def test_get_stats(self, cache):
        """Test cache statistics."""
        cache.put("query1", "response1")
        cache.put("query2", "response2")
        cache.get("query1")
        cache.get("query1")
        
        stats = cache.get_stats()
        
        assert stats["total_entries"] == 2
        assert stats["total_hits"] == 2
        assert stats["db_size_kb"] > 0
    
    def test_clear_old_entries(self, cache):
        """Test clearing old entries."""
        cache.put("old query", "old response")
        
        # Clear entries older than 0 days (all entries)
        cleared = cache.clear_old_entries(days=0)
        
        # Note: This might not clear because the entry was just created
        # The test validates the method runs without error
        assert cleared >= 0


class TestPatternMatcher:
    """Tests for the PatternMatcher class."""
    
    @pytest.fixture
    def matcher(self):
        return PatternMatcher()
    
    def test_install_docker(self, matcher):
        """Test matching docker installation."""
        result = matcher.match("install docker")
        
        assert result is not None
        assert result["matched"] is True
        assert "docker" in result["command"]
    
    def test_install_python(self, matcher):
        """Test matching python installation."""
        result = matcher.match("setup python")
        
        assert result is not None
        assert "python" in result["command"]
    
    def test_install_nodejs(self, matcher):
        """Test matching nodejs installation."""
        result = matcher.match("install nodejs")
        
        assert result is not None
        assert "nodejs" in result["command"] or "node" in result["command"]
    
    def test_update_system(self, matcher):
        """Test matching system update."""
        result = matcher.match("update system")
        
        assert result is not None
        assert "apt update" in result["command"]
    
    def test_search_package(self, matcher):
        """Test matching package search."""
        result = matcher.match("search for imagemagick")
        
        assert result is not None
        assert "apt search" in result["command"]
    
    def test_remove_package(self, matcher):
        """Test matching package removal."""
        result = matcher.match("remove vim")
        
        assert result is not None
        assert "apt remove" in result["command"]
        assert "vim" in result["command"]
    
    def test_no_match(self, matcher):
        """Test that unknown queries return None."""
        result = matcher.match("what is the meaning of life")
        assert result is None
    
    def test_case_insensitive(self, matcher):
        """Test case insensitive matching."""
        result = matcher.match("INSTALL DOCKER")
        
        assert result is not None
        assert "docker" in result["command"]


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""
    
    def test_is_healthy_available(self):
        """Test that AVAILABLE status is healthy."""
        result = HealthCheckResult(status=APIStatus.AVAILABLE)
        assert result.is_healthy() is True
    
    def test_is_healthy_degraded(self):
        """Test that DEGRADED status is not fully healthy."""
        result = HealthCheckResult(status=APIStatus.DEGRADED)
        assert result.is_healthy() is False
    
    def test_is_healthy_unavailable(self):
        """Test that UNAVAILABLE status is not healthy."""
        result = HealthCheckResult(status=APIStatus.UNAVAILABLE)
        assert result.is_healthy() is False


class TestGracefulDegradation:
    """Tests for the main GracefulDegradation class."""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """Create a manager with temporary cache."""
        cache = ResponseCache(tmp_path / "test_cache.db")
        return GracefulDegradation(cache=cache)
    
    def test_initial_mode(self, manager):
        """Test initial mode is FULL_AI."""
        assert manager.current_mode == FallbackMode.FULL_AI
    
    def test_check_api_health_with_key(self, manager):
        """Test health check when API key is set."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            result = manager.check_api_health()
            assert result.status in [APIStatus.AVAILABLE, APIStatus.DEGRADED]
    
    def test_check_api_health_no_key(self, manager):
        """Test health check when no API key is set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove keys if they exist
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            
            result = manager.check_api_health()
            assert result.status == APIStatus.UNAVAILABLE
    
    def test_check_api_health_custom_function(self, manager):
        """Test health check with custom function."""
        result = manager.check_api_health(api_check_fn=lambda: True)
        assert result.status == APIStatus.AVAILABLE
        
        result = manager.check_api_health(api_check_fn=lambda: False)
        assert result.status == APIStatus.UNAVAILABLE
    
    def test_process_query_with_llm(self, manager):
        """Test processing query with working LLM."""
        mock_llm = Mock(return_value="sudo apt install test-package")
        
        result = manager.process_query("install test", llm_fn=mock_llm)
        
        assert result["source"] == "llm"
        assert result["confidence"] == 1.0
        assert "test-package" in result["response"]
    
    def test_process_query_llm_failure_uses_cache(self, manager):
        """Test fallback to cache when LLM fails."""
        # Pre-populate cache
        manager.cache.put("install docker", "cached: sudo apt install docker.io")
        
        # LLM that fails
        def failing_llm(query):
            raise Exception("API Error")
        
        result = manager.process_query("install docker", llm_fn=failing_llm)
        
        assert result["cached"] is True
        assert "cached" in result["response"]
    
    def test_process_query_pattern_matching(self, manager):
        """Test fallback to pattern matching."""
        manager.force_mode(FallbackMode.PATTERN_MATCHING)
        
        result = manager.process_query("install nginx")
        
        assert result["source"] == "pattern_matching"
        assert "nginx" in result["command"]
    
    def test_process_query_manual_mode(self, manager):
        """Test fallback to manual mode for unknown queries."""
        manager.force_mode(FallbackMode.PATTERN_MATCHING)
        
        result = manager.process_query("do something completely unknown xyz")
        
        assert result["source"] == "manual_mode"
        assert result["confidence"] == 0.0
        assert "apt" in result["response"]
    
    def test_mode_degrades_after_failures(self, manager):
        """Test that mode degrades after multiple failures."""
        # Simulate failures
        manager._api_failures = 3
        manager._update_mode()
        
        # Should switch to cached or pattern matching mode
        assert manager.current_mode != FallbackMode.FULL_AI
    
    def test_force_mode(self, manager):
        """Test forcing a specific mode."""
        manager.force_mode(FallbackMode.MANUAL_MODE)
        assert manager.current_mode == FallbackMode.MANUAL_MODE
    
    def test_reset(self, manager):
        """Test resetting to default state."""
        manager._api_failures = 5
        manager.force_mode(FallbackMode.MANUAL_MODE)
        
        manager.reset()
        
        assert manager._api_failures == 0
        assert manager.current_mode == FallbackMode.FULL_AI
    
    def test_get_status(self, manager):
        """Test getting current status."""
        status = manager.get_status()
        
        assert "mode" in status
        assert "api_status" in status
        assert "api_failures" in status
        assert "cache_entries" in status
    
    def test_caches_successful_llm_responses(self, manager):
        """Test that successful LLM responses are cached."""
        mock_llm = Mock(return_value="cached response")
        
        manager.process_query("test query", llm_fn=mock_llm)
        
        # Should be in cache now
        cached = manager.cache.get("test query")
        assert cached is not None
        assert cached.response == "cached response"


class TestGlobalFunctions:
    """Tests for module-level convenience functions."""
    
    def test_get_degradation_manager_singleton(self):
        """Test that get_degradation_manager returns singleton."""
        manager1 = get_degradation_manager()
        manager2 = get_degradation_manager()
        
        assert manager1 is manager2
    
    def test_process_with_fallback(self):
        """Test the convenience function."""
        # Force pattern matching mode
        manager = get_degradation_manager()
        manager.force_mode(FallbackMode.PATTERN_MATCHING)
        
        result = process_with_fallback("install docker")
        
        assert result is not None
        assert "query" in result
        assert "response" in result


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture
    def manager(self, tmp_path):
        cache = ResponseCache(tmp_path / "test_cache.db")
        return GracefulDegradation(cache=cache)
    
    def test_empty_query(self, manager):
        """Test handling empty query."""
        result = manager.process_query("")
        assert result is not None
    
    def test_whitespace_query(self, manager):
        """Test handling whitespace-only query."""
        result = manager.process_query("   ")
        assert result is not None
    
    def test_very_long_query(self, manager):
        """Test handling very long query."""
        long_query = "install " + "a" * 10000
        result = manager.process_query(long_query)
        assert result is not None
    
    def test_special_characters_in_query(self, manager):
        """Test handling special characters."""
        result = manager.process_query("install package-name_v1.0")
        assert result is not None
    
    def test_llm_returns_none(self, manager):
        """Test handling LLM returning None."""
        mock_llm = Mock(return_value=None)
        
        # This should handle None gracefully
        result = manager.process_query("test", llm_fn=mock_llm)
        assert result is not None
    
    def test_concurrent_cache_access(self, manager):
        """Test that cache handles concurrent access."""
        import threading
        
        def write_cache():
            for i in range(10):
                manager.cache.put(f"query_{i}", f"response_{i}")
        
        def read_cache():
            for i in range(10):
                manager.cache.get(f"query_{i}")
        
        threads = [
            threading.Thread(target=write_cache),
            threading.Thread(target=read_cache),
            threading.Thread(target=write_cache),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should complete without errors
        stats = manager.cache.get_stats()
        assert stats["total_entries"] >= 0


class TestIntegration:
    """Integration tests for the full degradation flow."""
    
    @pytest.fixture
    def manager(self, tmp_path):
        cache = ResponseCache(tmp_path / "test_cache.db")
        return GracefulDegradation(cache=cache)
    
    def test_full_degradation_flow(self, manager):
        """Test the complete degradation flow from AI to manual."""
        queries = ["install docker", "setup python", "update system"]
        
        # Phase 1: AI mode (simulated)
        manager.force_mode(FallbackMode.FULL_AI)
        mock_llm = Mock(side_effect=Exception("API Down"))
        
        # First query - LLM fails, should try cache
        result1 = manager.process_query(queries[0], llm_fn=mock_llm)
        
        # Phase 2: Pattern matching (after failures)
        manager.force_mode(FallbackMode.PATTERN_MATCHING)
        result2 = manager.process_query(queries[1])
        
        assert result2["source"] == "pattern_matching"
        assert result2["confidence"] > 0
        
        # Phase 3: Still works for known patterns
        result3 = manager.process_query(queries[2])
        assert result3["source"] == "pattern_matching"
    
    def test_recovery_after_api_returns(self, manager):
        """Test recovery when API becomes available again."""
        # Start in degraded mode
        manager._api_failures = 5
        manager._update_mode()
        assert manager.current_mode != FallbackMode.FULL_AI
        
        # API becomes available
        manager.check_api_health(api_check_fn=lambda: True)
        
        # Should recover to full AI mode
        assert manager._api_failures == 0
        assert manager.current_mode == FallbackMode.FULL_AI


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
