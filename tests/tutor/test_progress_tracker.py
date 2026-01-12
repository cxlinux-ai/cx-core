"""
Tests for progress tracker and SQLite store.

Tests learning progress persistence and retrieval.
"""

import os
import tempfile
from pathlib import Path

import pytest

from cortex.tutor.memory.sqlite_store import (
    LearningProgress,
    QuizResult,
    SQLiteStore,
    StudentProfile,
)
from cortex.tutor.tools.deterministic.progress_tracker import (
    ProgressTrackerTool,
    get_learning_progress,
    get_package_stats,
    mark_topic_completed,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_progress.db"
        yield db_path


@pytest.fixture
def store(temp_db):
    """Create a SQLite store with temp database."""
    return SQLiteStore(temp_db)


@pytest.fixture
def tracker(temp_db):
    """Create a progress tracker with temp database."""
    return ProgressTrackerTool(temp_db)


class TestSQLiteStore:
    """Tests for SQLiteStore class."""

    def test_init_creates_database(self, temp_db):
        """Test database is created on init."""
        _store = SQLiteStore(temp_db)
        assert temp_db.exists()

    def test_upsert_and_get_progress(self, store):
        """Test inserting and retrieving progress."""
        progress = LearningProgress(
            package_name="docker",
            topic="basics",
            completed=True,
            score=0.9,
        )
        store.upsert_progress(progress)

        result = store.get_progress("docker", "basics")
        assert result is not None
        assert result.package_name == "docker"
        assert result.completed is True
        assert result.score == pytest.approx(0.9)

    def test_upsert_updates_existing(self, store):
        """Test upsert updates existing record."""
        # Insert first
        progress1 = LearningProgress(
            package_name="docker",
            topic="basics",
            completed=False,
            score=0.5,
        )
        store.upsert_progress(progress1)

        # Update
        progress2 = LearningProgress(
            package_name="docker",
            topic="basics",
            completed=True,
            score=0.9,
        )
        store.upsert_progress(progress2)

        result = store.get_progress("docker", "basics")
        assert result.completed is True
        assert result.score == pytest.approx(0.9)

    def test_get_all_progress(self, store):
        """Test getting all progress records."""
        store.upsert_progress(
            LearningProgress(package_name="docker", topic="basics", completed=True)
        )
        store.upsert_progress(
            LearningProgress(package_name="docker", topic="advanced", completed=False)
        )
        store.upsert_progress(LearningProgress(package_name="git", topic="basics", completed=True))

        all_progress = store.get_all_progress()
        assert len(all_progress) == 3

        docker_progress = store.get_all_progress("docker")
        assert len(docker_progress) == 2

    def test_mark_topic_completed(self, store):
        """Test marking topic as completed."""
        store.mark_topic_completed("docker", "tutorial", 0.85)

        result = store.get_progress("docker", "tutorial")
        assert result.completed is True
        assert result.score == pytest.approx(0.85)

    def test_get_completion_stats(self, store):
        """Test getting completion statistics."""
        store.upsert_progress(
            LearningProgress(package_name="docker", topic="basics", completed=True, score=0.9)
        )
        store.upsert_progress(
            LearningProgress(package_name="docker", topic="advanced", completed=False, score=0.5)
        )

        stats = store.get_completion_stats("docker")
        assert stats["total"] == 2
        assert stats["completed"] == 1
        assert stats["avg_score"] == pytest.approx(0.7)

    def test_quiz_results(self, store):
        """Test adding and retrieving quiz results."""
        result = QuizResult(
            package_name="docker",
            question="What is Docker?",
            user_answer="A container platform",
            correct=True,
        )
        store.add_quiz_result(result)

        results = store.get_quiz_results("docker")
        assert len(results) == 1
        assert results[0].question == "What is Docker?"
        assert results[0].correct is True

    def test_student_profile(self, store):
        """Test student profile operations."""
        profile = store.get_student_profile()
        assert profile.learning_style == "reading"

        profile.learning_style = "hands-on"
        profile.mastered_concepts = ["docker basics"]
        store.update_student_profile(profile)

        updated = store.get_student_profile()
        assert updated.learning_style == "hands-on"
        assert "docker basics" in updated.mastered_concepts

    def test_add_mastered_concept(self, store):
        """Test adding mastered concept."""
        store.add_mastered_concept("containerization")

        profile = store.get_student_profile()
        assert "containerization" in profile.mastered_concepts

    def test_add_weak_concept(self, store):
        """Test adding weak concept."""
        store.add_weak_concept("networking")

        profile = store.get_student_profile()
        assert "networking" in profile.weak_concepts

    def test_lesson_cache(self, store):
        """Test lesson caching."""
        lesson = {"summary": "Docker is...", "explanation": "..."}
        store.cache_lesson("docker", lesson, ttl_hours=24)

        cached = store.get_cached_lesson("docker")
        assert cached is not None
        assert cached["summary"] == "Docker is..."

    def test_expired_cache_not_returned(self, store):
        """Test expired cache is not returned."""
        lesson = {"summary": "test"}
        store.cache_lesson("test", lesson, ttl_hours=0)

        # Should not return expired cache
        cached = store.get_cached_lesson("test")
        assert cached is None

    def test_reset_progress(self, store):
        """Test resetting progress."""
        store.upsert_progress(LearningProgress(package_name="docker", topic="basics"))
        store.upsert_progress(LearningProgress(package_name="git", topic="basics"))

        count = store.reset_progress("docker")
        assert count == 1

        remaining = store.get_all_progress()
        assert len(remaining) == 1
        assert remaining[0].package_name == "git"

    def test_get_packages_studied(self, store):
        """Test getting list of studied packages."""
        store.upsert_progress(LearningProgress(package_name="docker", topic="basics"))
        store.upsert_progress(LearningProgress(package_name="git", topic="basics"))

        packages = store.get_packages_studied()
        assert set(packages) == {"docker", "git"}


class TestProgressTrackerTool:
    """Tests for ProgressTrackerTool class."""

    def test_get_progress_action(self, tracker):
        """Test get_progress action."""
        # First add some progress
        tracker._run("mark_completed", package_name="docker", topic="basics", score=0.9)

        result = tracker._run("get_progress", package_name="docker", topic="basics")
        assert result["success"]
        assert result["progress"]["completed"] is True

    def test_get_progress_not_found(self, tracker):
        """Test get_progress for non-existent progress."""
        result = tracker._run("get_progress", package_name="unknown", topic="topic")
        assert result["success"]
        assert result["progress"] is None

    def test_mark_completed_action(self, tracker):
        """Test mark_completed action."""
        result = tracker._run(
            "mark_completed",
            package_name="docker",
            topic="tutorial",
            score=0.85,
        )
        assert result["success"]
        assert result["score"] == pytest.approx(0.85)

    def test_get_stats_action(self, tracker):
        """Test get_stats action."""
        tracker._run("mark_completed", package_name="docker", topic="basics")
        tracker._run("update_progress", package_name="docker", topic="advanced")

        result = tracker._run("get_stats", package_name="docker")
        assert result["success"]
        assert result["stats"]["total"] == 2
        assert result["stats"]["completed"] == 1

    def test_get_profile_action(self, tracker):
        """Test get_profile action."""
        result = tracker._run("get_profile")
        assert result["success"]
        assert "learning_style" in result["profile"]

    def test_update_profile_action(self, tracker):
        """Test update_profile action."""
        result = tracker._run("update_profile", learning_style="visual")
        assert result["success"]

        profile = tracker._run("get_profile")
        assert profile["profile"]["learning_style"] == "visual"

    def test_add_mastered_concept_action(self, tracker):
        """Test add_mastered action."""
        result = tracker._run("add_mastered", concept="docker basics")
        assert result["success"]

    def test_reset_action(self, tracker):
        """Test reset action."""
        tracker._run("mark_completed", package_name="docker", topic="basics")
        result = tracker._run("reset", package_name="docker")
        assert result["success"]

    def test_unknown_action(self, tracker):
        """Test unknown action returns error."""
        result = tracker._run("unknown_action")
        assert not result["success"]
        assert "Unknown action" in result["error"]

    def test_missing_required_params(self, tracker):
        """Test missing required params returns error."""
        result = tracker._run("get_progress")  # Missing package_name and topic
        assert not result["success"]


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_get_learning_progress(self, temp_db):
        """Test get_learning_progress function."""
        from unittest.mock import Mock, patch

        # Mock the global config to use temp_db
        mock_config = Mock()
        mock_config.get_db_path.return_value = temp_db

        with patch(
            "cortex.tutor.tools.deterministic.progress_tracker.get_config", return_value=mock_config
        ):
            # First mark a topic completed
            result = mark_topic_completed("docker", "basics", 0.85)
            assert result is True

            # Now get the progress
            progress = get_learning_progress("docker", "basics")
            assert progress is not None
            assert progress["completed"] is True
            assert progress["score"] == pytest.approx(0.85)

    def test_mark_topic_completed(self, temp_db):
        """Test mark_topic_completed function."""
        from unittest.mock import Mock, patch

        mock_config = Mock()
        mock_config.get_db_path.return_value = temp_db

        with patch(
            "cortex.tutor.tools.deterministic.progress_tracker.get_config", return_value=mock_config
        ):
            result = mark_topic_completed("git", "branching", 0.9)
            assert result is True

            # Verify it was actually saved
            progress = get_learning_progress("git", "branching")
            assert progress is not None
            assert progress["completed"] is True

    def test_get_package_stats(self, temp_db):
        """Test get_package_stats function."""
        from unittest.mock import Mock, patch

        mock_config = Mock()
        mock_config.get_db_path.return_value = temp_db

        with patch(
            "cortex.tutor.tools.deterministic.progress_tracker.get_config", return_value=mock_config
        ):
            # Mark some topics
            mark_topic_completed("nginx", "basics", 0.9)
            mark_topic_completed("nginx", "config", 0.7)

            # Get stats
            stats = get_package_stats("nginx")
            assert stats["total"] == 2
            assert stats["completed"] == 2
            assert stats["avg_score"] == pytest.approx(0.8)  # (0.9 + 0.7) / 2
