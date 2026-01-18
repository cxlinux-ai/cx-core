"""
Deterministic Tools for Intelligent Tutor.

These tools do NOT use LLM calls - they are fast, free, and predictable.
"""

import logging
from pathlib import Path
from typing import Any

from cortex.tutor.config import get_config
from cortex.tutor.sqlite_store import LearningProgress, SQLiteStore

logger = logging.getLogger(__name__)


# ==============================================================================
# Lesson Loader Tool
# ==============================================================================


class LessonLoaderTool:
    """Deterministic tool for loading cached lesson content."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the lesson loader tool."""
        if db_path is None:
            config = get_config()
            db_path = config.get_db_path()
        self.store = SQLiteStore(db_path)

    def _run(
        self,
        package_name: str,
        force_fresh: bool = False,
    ) -> dict[str, Any]:
        """Load cached lesson content."""
        if force_fresh:
            return {
                "success": True,
                "cache_hit": False,
                "lesson": None,
                "reason": "Force fresh requested",
            }

        try:
            cached = self.store.get_cached_lesson(package_name)

            if cached:
                return {
                    "success": True,
                    "cache_hit": True,
                    "lesson": cached,
                    "cost_saved_gbp": 0.02,
                }

            return {
                "success": True,
                "cache_hit": False,
                "lesson": None,
                "reason": "No valid cache found",
            }

        except Exception as e:
            logger.exception("Lesson loader failed for package '%s'", package_name)
            return {
                "success": False,
                "cache_hit": False,
                "lesson": None,
                "error": str(e),
            }

    def cache_lesson(
        self,
        package_name: str,
        lesson: dict[str, Any],
        ttl_hours: int | None = None,
    ) -> bool:
        """Cache a lesson for future retrieval."""
        try:
            if ttl_hours is None:
                config = get_config()
                ttl_hours = config.cache_ttl_hours
            self.store.cache_lesson(package_name, lesson, ttl_hours)
            return True
        except Exception:
            logger.exception("Failed to cache lesson for package '%s'", package_name)
            return False

    def clear_cache(self, package_name: str | None = None) -> int:
        """Clear cached lessons.

        Args:
            package_name: If provided, clears cache for specific package.
                         If None, clears only expired cache entries.

        Returns:
            Number of cache entries cleared.
        """
        if package_name:
            try:
                self.store.cache_lesson(package_name, {}, ttl_hours=0)
                return 1
            except Exception:
                logger.exception("Failed to clear cache for package '%s'", package_name)
                return 0
        else:
            return self.store.clear_expired_cache()


# Pre-built lesson templates for common packages
FALLBACK_LESSONS = {
    "docker": {
        "package_name": "docker",
        "summary": "Docker is a containerization platform for packaging and running applications.",
        "explanation": (
            "Docker enables you to package applications with their dependencies into "
            "standardized units called containers. Containers are lightweight, portable, "
            "and isolated from the host system, making deployment consistent across environments."
        ),
        "use_cases": [
            "Development environment consistency",
            "Microservices deployment",
            "CI/CD pipelines",
            "Application isolation",
        ],
        "best_practices": [
            "Use official base images when possible",
            "Keep images small with multi-stage builds",
            "Never store secrets in images",
            "Use .dockerignore to exclude unnecessary files",
        ],
        "installation_command": "apt install docker.io",
        "confidence": 0.7,
    },
    "git": {
        "package_name": "git",
        "summary": "Git is a distributed version control system for tracking code changes.",
        "explanation": (
            "Git tracks changes to files over time, allowing you to recall specific versions "
            "later. It supports collaboration through branching, merging, and remote repositories."
        ),
        "use_cases": [
            "Source code version control",
            "Team collaboration",
            "Code review workflows",
            "Release management",
        ],
        "best_practices": [
            "Write clear, descriptive commit messages",
            "Use feature branches for new work",
            "Pull before push to avoid conflicts",
            "Review changes before committing",
        ],
        "installation_command": "apt install git",
        "confidence": 0.7,
    },
    "nginx": {
        "package_name": "nginx",
        "summary": "Nginx is a high-performance web server and reverse proxy.",
        "explanation": (
            "Nginx (pronounced 'engine-x') is known for its high performance, stability, "
            "and low resource consumption. It can serve static content, act as a reverse proxy, "
            "and handle load balancing."
        ),
        "use_cases": [
            "Static file serving",
            "Reverse proxy for applications",
            "Load balancing",
            "SSL/TLS termination",
        ],
        "best_practices": [
            "Use separate config files for each site",
            "Enable gzip compression",
            "Configure proper caching headers",
            "Set up SSL with strong ciphers",
        ],
        "installation_command": "apt install nginx",
        "confidence": 0.7,
    },
}


def get_fallback_lesson(package_name: str) -> dict[str, Any] | None:
    """Get a fallback lesson template for common packages."""
    return FALLBACK_LESSONS.get(package_name.lower())


def load_lesson_with_fallback(
    package_name: str,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Load lesson from cache with fallback to templates."""
    loader = LessonLoaderTool(db_path)
    result = loader._run(package_name)

    if result.get("cache_hit") and result.get("lesson"):
        return {
            "source": "cache",
            "lesson": result["lesson"],
            "cost_saved_gbp": result.get("cost_saved_gbp", 0),
        }

    fallback = get_fallback_lesson(package_name)
    if fallback:
        return {
            "source": "fallback_template",
            "lesson": fallback,
            "cost_saved_gbp": 0.02,
        }

    return {
        "source": "none",
        "lesson": None,
        "needs_generation": True,
    }


# ==============================================================================
# Progress Tracker Tool
# ==============================================================================


class ProgressTrackerTool:
    """Deterministic tool for tracking learning progress."""

    _ERR_PKG_TOPIC_REQUIRED: str = "package_name and topic required"

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the progress tracker tool."""
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
        """Execute a progress tracking action."""
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
            logger.exception("Progress tracker action '%s' failed", action)
            return {"success": False, "error": str(e)}

    def _get_progress(
        self,
        package_name: str | None,
        topic: str | None,
        **_kwargs: Any,
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
        **_kwargs: Any,
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
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """Mark a topic as completed."""
        if not package_name or not topic:
            return {"success": False, "error": self._ERR_PKG_TOPIC_REQUIRED}

        effective_score = score if score is not None else 1.0
        self.store.mark_topic_completed(package_name, topic, effective_score)
        return {
            "success": True,
            "message": f"Marked {package_name}/{topic} as completed",
            "score": effective_score,
        }

    def _update_progress(
        self,
        package_name: str | None,
        topic: str | None,
        score: float | None = None,
        time_seconds: int | None = None,
        completed: bool | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """Update progress for a topic."""
        if not package_name or not topic:
            return {"success": False, "error": self._ERR_PKG_TOPIC_REQUIRED}

        existing = self.store.get_progress(package_name, topic)
        total_time = (existing.total_time_seconds if existing else 0) + (time_seconds or 0)

        # Preserve existing values if not explicitly provided
        if completed is not None:
            final_completed = completed
        else:
            final_completed = existing.completed if existing else False

        if score is not None:
            final_score = score
        else:
            final_score = existing.score if existing else 0.0

        progress = LearningProgress(
            package_name=package_name,
            topic=topic,
            completed=final_completed,
            score=final_score,
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
        **_kwargs: Any,
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

    def _get_profile(self, **_kwargs: Any) -> dict[str, Any]:
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
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """Update student profile."""
        profile = self.store.get_student_profile()
        if learning_style is not None:
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
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """Reset learning progress."""
        count = self.store.reset_progress(package_name)
        scope = f"for {package_name}" if package_name else "all"
        return {
            "success": True,
            "count": count,
            "message": f"Reset {count} progress records {scope}",
        }

    def _get_packages_studied(self, **_kwargs: Any) -> dict[str, Any]:
        """Get list of packages that have been studied."""
        packages = self.store.get_packages_studied()
        return {"success": True, "packages": packages, "count": len(packages)}


# Convenience functions for direct usage


def get_learning_progress(package_name: str, topic: str) -> dict[str, Any] | None:
    """Get learning progress for a specific topic."""
    tool = ProgressTrackerTool()
    result = tool._run("get_progress", package_name=package_name, topic=topic)
    return result.get("progress")


def mark_topic_completed(package_name: str, topic: str, score: float = 1.0) -> bool:
    """Mark a topic as completed."""
    tool = ProgressTrackerTool()
    result = tool._run("mark_completed", package_name=package_name, topic=topic, score=score)
    return result.get("success", False)


def get_package_stats(package_name: str) -> dict[str, Any]:
    """Get completion statistics for a package."""
    tool = ProgressTrackerTool()
    result = tool._run("get_stats", package_name=package_name)
    return result.get("stats", {})
