"""
Tests for deterministic tools.

Tests lesson loader and fallback functionality.
"""

import tempfile
from pathlib import Path

import pytest

from cortex.tutor.tools.deterministic.lesson_loader import (
    LessonLoaderTool,
    get_fallback_lesson,
    load_lesson_with_fallback,
)


@pytest.fixture
def temp_db():
    """Create a temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


class TestLessonLoaderTool:
    """Tests for LessonLoaderTool."""

    def test_cache_miss(self, temp_db):
        """Test cache miss returns appropriate response."""
        loader = LessonLoaderTool(temp_db)
        result = loader._run("unknown_package")

        assert result["success"]
        assert not result["cache_hit"]
        assert result["lesson"] is None

    def test_force_fresh(self, temp_db):
        """Test force_fresh skips cache."""
        loader = LessonLoaderTool(temp_db)

        loader.cache_lesson("docker", {"summary": "cached"})

        result = loader._run("docker", force_fresh=True)
        assert not result["cache_hit"]

    def test_cache_lesson_and_retrieve(self, temp_db):
        """Test caching and retrieving a lesson."""
        loader = LessonLoaderTool(temp_db)

        lesson = {"summary": "Docker is...", "explanation": "A container platform"}
        loader.cache_lesson("docker", lesson, ttl_hours=24)

        result = loader._run("docker")
        assert result["success"]
        assert result["cache_hit"]
        assert result["lesson"]["summary"] == "Docker is..."


class TestFallbackLessons:
    """Tests for fallback lesson templates."""

    def test_docker_fallback(self):
        """Test Docker fallback exists."""
        fallback = get_fallback_lesson("docker")
        assert fallback is not None
        assert fallback["package_name"] == "docker"
        assert "summary" in fallback

    def test_git_fallback(self):
        """Test Git fallback exists."""
        fallback = get_fallback_lesson("git")
        assert fallback is not None

    def test_nginx_fallback(self):
        """Test Nginx fallback exists."""
        fallback = get_fallback_lesson("nginx")
        assert fallback is not None

    def test_unknown_fallback(self):
        """Test unknown package returns None."""
        fallback = get_fallback_lesson("unknown_package")
        assert fallback is None

    def test_case_insensitive(self):
        """Test fallback lookup is case insensitive."""
        fallback = get_fallback_lesson("DOCKER")
        assert fallback is not None


class TestLoadLessonWithFallback:
    """Tests for load_lesson_with_fallback function."""

    def test_returns_cache_if_available(self, temp_db):
        """Test returns cached lesson if available."""
        from cortex.tutor.memory.sqlite_store import SQLiteStore

        store = SQLiteStore(temp_db)
        store.cache_lesson("docker", {"summary": "cached"}, ttl_hours=24)

        result = load_lesson_with_fallback("docker", temp_db)
        assert result["source"] == "cache"

    def test_returns_fallback_if_no_cache(self, temp_db):
        """Test returns fallback if no cache."""
        result = load_lesson_with_fallback("docker", temp_db)
        assert result["source"] == "fallback_template"

    def test_returns_none_for_unknown(self, temp_db):
        """Test returns none for unknown package."""
        result = load_lesson_with_fallback("totally_unknown", temp_db)
        assert result["source"] == "none"
        assert result["needs_generation"]
