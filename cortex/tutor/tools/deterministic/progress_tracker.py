"""
Progress Tracker Tool - Deterministic tool for learning progress management.

This tool does NOT use LLM calls - it is fast, free, and predictable.
Used for tracking learning progress via SQLite operations.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from langchain.tools import BaseTool
from pydantic import Field

from cortex.tutor.config import get_config
from cortex.tutor.memory.sqlite_store import (
    LearningProgress,
    SQLiteStore,
    StudentProfile,
)


class ProgressTrackerTool(BaseTool):
    """
    Deterministic tool for tracking learning progress.

    This tool manages SQLite-based progress tracking including:
    - Recording topic completions
    - Tracking time spent
    - Managing student profiles
    - Retrieving progress statistics

    No LLM calls are made - pure database operations.
    """

    name: str = "progress_tracker"
    description: str = (
        "Track learning progress for packages and topics. "
        "Use this to record completions, get progress stats, and manage student profiles. "
        "This is a fast, deterministic tool with no LLM cost."
    )

    store: SQLiteStore | None = Field(default=None, exclude=True)

    # Error message constants
    _ERR_PKG_TOPIC_REQUIRED: str = "package_name and topic required"

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, db_path: Path | None = None) -> None:
        """
        Initialize the progress tracker tool.

        Args:
            db_path: Path to SQLite database. Uses config default if not provided.
        """
        super().__init__()
        if db_path is None:
            config = get_config()
            db_path = config.get_db_path()
        self.store = SQLiteStore(db_path)

    def _run(
        self,
        action: str,
        package_name: str | None = None,
        topic: str | None = None,
        score: float | None = None,
        time_seconds: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute a progress tracking action.

        Args:
            action: Action to perform (get_progress, mark_completed, get_stats, etc.)
            package_name: Name of the package (required for most actions)
            topic: Topic within the package
            score: Score achieved (0.0 to 1.0)
            time_seconds: Time spent in seconds
            **kwargs: Additional arguments for specific actions

        Returns:
            Dict containing action results
        """
        actions = {
            "get_progress": self._get_progress,
            "get_all_progress": self._get_all_progress,
            "mark_completed": self._mark_completed,
            "update_progress": self._update_progress,
            "get_stats": self._get_stats,
            "get_profile": self._get_profile,
            "update_profile": self._update_profile,
            "add_mastered": self._add_mastered_concept,
            "add_weak": self._add_weak_concept,
            "reset": self._reset_progress,
            "get_packages": self._get_packages_studied,
        }

        if action not in actions:
            return {
                "success": False,
                "error": f"Unknown action: {action}. Valid actions: {list(actions.keys())}",
            }

        try:
            return actions[action](
                package_name=package_name,
                topic=topic,
                score=score,
                time_seconds=time_seconds,
                **kwargs,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _arun(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Async version - delegates to sync implementation."""
        return self._run(*args, **kwargs)

    def _get_progress(
        self,
        package_name: str | None,
        topic: str | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get progress for a specific package/topic."""
        if not package_name or not topic:
            return {"success": False, "error": self._ERR_PKG_TOPIC_REQUIRED}

        progress = self.store.get_progress(package_name, topic)
        if progress:
            return {
                "success": True,
                "progress": {
                    "package_name": progress.package_name,
                    "topic": progress.topic,
                    "completed": progress.completed,
                    "score": progress.score,
                    "last_accessed": progress.last_accessed,
                    "total_time_seconds": progress.total_time_seconds,
                },
            }
        return {"success": True, "progress": None, "message": "No progress found"}

    def _get_all_progress(
        self,
        package_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get all progress, optionally filtered by package."""
        progress_list = self.store.get_all_progress(package_name)
        return {
            "success": True,
            "progress": [
                {
                    "package_name": p.package_name,
                    "topic": p.topic,
                    "completed": p.completed,
                    "score": p.score,
                    "total_time_seconds": p.total_time_seconds,
                }
                for p in progress_list
            ],
            "count": len(progress_list),
        }

    def _mark_completed(
        self,
        package_name: str | None,
        topic: str | None,
        score: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Mark a topic as completed."""
        if not package_name or not topic:
            return {"success": False, "error": self._ERR_PKG_TOPIC_REQUIRED}

        self.store.mark_topic_completed(package_name, topic, score or 1.0)
        return {
            "success": True,
            "message": f"Marked {package_name}/{topic} as completed",
            "score": score or 1.0,
        }

    def _update_progress(
        self,
        package_name: str | None,
        topic: str | None,
        score: float | None = None,
        time_seconds: int | None = None,
        completed: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update progress for a topic."""
        if not package_name or not topic:
            return {"success": False, "error": self._ERR_PKG_TOPIC_REQUIRED}

        # Get existing progress to preserve values
        existing = self.store.get_progress(package_name, topic)
        total_time = (existing.total_time_seconds if existing else 0) + (time_seconds or 0)

        progress = LearningProgress(
            package_name=package_name,
            topic=topic,
            completed=completed,
            score=score or (existing.score if existing else 0.0),
            total_time_seconds=total_time,
        )
        row_id = self.store.upsert_progress(progress)
        return {
            "success": True,
            "row_id": row_id,
            "total_time_seconds": total_time,
        }

    def _get_stats(
        self,
        package_name: str | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get completion statistics for a package."""
        if not package_name:
            return {"success": False, "error": "package_name required"}

        stats = self.store.get_completion_stats(package_name)
        return {
            "success": True,
            "stats": stats,
            "completion_percentage": (
                (stats["completed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            ),
        }

    def _get_profile(self, **kwargs: Any) -> dict[str, Any]:
        """Get student profile."""
        profile = self.store.get_student_profile()
        return {
            "success": True,
            "profile": {
                "mastered_concepts": profile.mastered_concepts,
                "weak_concepts": profile.weak_concepts,
                "learning_style": profile.learning_style,
                "last_session": profile.last_session,
            },
        }

    def _update_profile(
        self,
        learning_style: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update student profile."""
        profile = self.store.get_student_profile()
        if learning_style:
            profile.learning_style = learning_style
        self.store.update_student_profile(profile)
        return {"success": True, "message": "Profile updated"}

    def _add_mastered_concept(
        self,
        concept: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add a mastered concept to student profile."""
        concept = kwargs.get("concept") or concept
        if not concept:
            return {"success": False, "error": "concept required"}
        self.store.add_mastered_concept(concept)
        return {"success": True, "message": f"Added mastered concept: {concept}"}

    def _add_weak_concept(
        self,
        concept: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add a weak concept to student profile."""
        concept = kwargs.get("concept") or concept
        if not concept:
            return {"success": False, "error": "concept required"}
        self.store.add_weak_concept(concept)
        return {"success": True, "message": f"Added weak concept: {concept}"}

    def _reset_progress(
        self,
        package_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Reset learning progress."""
        count = self.store.reset_progress(package_name)
        scope = f"for {package_name}" if package_name else "all"
        return {"success": True, "message": f"Reset {count} progress records {scope}"}

    def _get_packages_studied(self, **kwargs: Any) -> dict[str, Any]:
        """Get list of packages that have been studied."""
        packages = self.store.get_packages_studied()
        return {"success": True, "packages": packages, "count": len(packages)}


# Convenience functions for direct usage


def get_learning_progress(package_name: str, topic: str) -> dict[str, Any] | None:
    """
    Get learning progress for a specific topic.

    Args:
        package_name: Name of the package.
        topic: Topic within the package.

    Returns:
        Progress dictionary or None.
    """
    tool = ProgressTrackerTool()
    result = tool._run("get_progress", package_name=package_name, topic=topic)
    return result.get("progress")


def mark_topic_completed(package_name: str, topic: str, score: float = 1.0) -> bool:
    """
    Mark a topic as completed.

    Args:
        package_name: Name of the package.
        topic: Topic to mark as completed.
        score: Score achieved (0.0 to 1.0).

    Returns:
        True if successful.
    """
    tool = ProgressTrackerTool()
    result = tool._run("mark_completed", package_name=package_name, topic=topic, score=score)
    return result.get("success", False)


def get_package_stats(package_name: str) -> dict[str, Any]:
    """
    Get completion statistics for a package.

    Args:
        package_name: Name of the package.

    Returns:
        Statistics dictionary.
    """
    tool = ProgressTrackerTool()
    result = tool._run("get_stats", package_name=package_name)
    return result.get("stats", {})
