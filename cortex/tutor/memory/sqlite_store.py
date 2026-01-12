"""
SQLite storage for Intelligent Tutor learning progress.

Provides persistence for learning progress, quiz results, and student profiles.
"""

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from pydantic import BaseModel


class LearningProgress(BaseModel):
    """Model for learning progress records."""

    id: int | None = None
    package_name: str
    topic: str
    completed: bool = False
    score: float = 0.0
    last_accessed: str | None = None
    total_time_seconds: int = 0


class QuizResult(BaseModel):
    """Model for quiz result records."""

    id: int | None = None
    package_name: str
    question: str
    user_answer: str | None = None
    correct: bool = False
    timestamp: str | None = None


class StudentProfile(BaseModel):
    """Model for student profile."""

    id: int | None = None
    mastered_concepts: list[str] = []
    weak_concepts: list[str] = []
    learning_style: str = "reading"  # visual, reading, hands-on
    last_session: str | None = None


class SQLiteStore:
    """
    SQLite-based storage for learning progress and student data.

    Thread-safe implementation with connection pooling.

    Attributes:
        db_path: Path to the SQLite database file.
    """

    # SQL schema for database initialization
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS learning_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        package_name TEXT NOT NULL,
        topic TEXT NOT NULL,
        completed BOOLEAN DEFAULT FALSE,
        score REAL DEFAULT 0.0,
        last_accessed TEXT,
        total_time_seconds INTEGER DEFAULT 0,
        UNIQUE(package_name, topic)
    );

    CREATE TABLE IF NOT EXISTS quiz_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        package_name TEXT NOT NULL,
        question TEXT NOT NULL,
        user_answer TEXT,
        correct BOOLEAN DEFAULT FALSE,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS student_profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mastered_concepts TEXT DEFAULT '[]',
        weak_concepts TEXT DEFAULT '[]',
        learning_style TEXT DEFAULT 'reading',
        last_session TEXT
    );

    CREATE TABLE IF NOT EXISTS lesson_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        package_name TEXT NOT NULL UNIQUE,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_progress_package ON learning_progress(package_name);
    CREATE INDEX IF NOT EXISTS idx_quiz_package ON quiz_results(package_name);
    CREATE INDEX IF NOT EXISTS idx_cache_package ON lesson_cache(package_name);
    """

    # SQL query constants to avoid duplication
    _SELECT_PROFILE = "SELECT * FROM student_profile LIMIT 1"

    def __init__(self, db_path: Path) -> None:
        """
        Initialize SQLite store.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._lock = RLock()  # Re-entrant lock to allow nested calls
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the database schema."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            conn.executescript(self.SCHEMA)
            conn.commit()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Get a thread-safe database connection.

        Yields:
            sqlite3.Connection: Database connection.
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    # ==================== Learning Progress Methods ====================

    def get_progress(self, package_name: str, topic: str) -> LearningProgress | None:
        """
        Get learning progress for a specific package and topic.

        Args:
            package_name: Name of the package.
            topic: Topic within the package.

        Returns:
            LearningProgress or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM learning_progress WHERE package_name = ? AND topic = ?",
                (package_name, topic),
            )
            row = cursor.fetchone()
            if row:
                return LearningProgress(
                    id=row["id"],
                    package_name=row["package_name"],
                    topic=row["topic"],
                    completed=bool(row["completed"]),
                    score=row["score"],
                    last_accessed=row["last_accessed"],
                    total_time_seconds=row["total_time_seconds"],
                )
            return None

    def get_all_progress(self, package_name: str | None = None) -> list[LearningProgress]:
        """
        Get all learning progress records.

        Args:
            package_name: Optional filter by package name.

        Returns:
            List of LearningProgress records.
        """
        with self._get_connection() as conn:
            if package_name:
                cursor = conn.execute(
                    "SELECT * FROM learning_progress WHERE package_name = ? ORDER BY topic",
                    (package_name,),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM learning_progress ORDER BY package_name, topic"
                )

            return [
                LearningProgress(
                    id=row["id"],
                    package_name=row["package_name"],
                    topic=row["topic"],
                    completed=bool(row["completed"]),
                    score=row["score"],
                    last_accessed=row["last_accessed"],
                    total_time_seconds=row["total_time_seconds"],
                )
                for row in cursor.fetchall()
            ]

    def upsert_progress(self, progress: LearningProgress) -> int:
        """
        Insert or update learning progress.

        Args:
            progress: LearningProgress record to save.

        Returns:
            Row ID of the inserted/updated record.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO learning_progress
                    (package_name, topic, completed, score, last_accessed, total_time_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(package_name, topic) DO UPDATE SET
                    completed = excluded.completed,
                    score = excluded.score,
                    last_accessed = excluded.last_accessed,
                    total_time_seconds = excluded.total_time_seconds
                """,
                (
                    progress.package_name,
                    progress.topic,
                    progress.completed,
                    progress.score,
                    now,
                    progress.total_time_seconds,
                ),
            )
            conn.commit()
            # lastrowid returns 0 on UPDATE, so fetch the actual ID
            if cursor.lastrowid == 0:
                id_cursor = conn.execute(
                    "SELECT id FROM learning_progress WHERE package_name = ? AND topic = ?",
                    (progress.package_name, progress.topic),
                )
                row = id_cursor.fetchone()
                return row["id"] if row else 0
            return cursor.lastrowid

    def mark_topic_completed(self, package_name: str, topic: str, score: float = 1.0) -> None:
        """
        Mark a topic as completed.

        Args:
            package_name: Name of the package.
            topic: Topic to mark as completed.
            score: Score achieved (0.0 to 1.0).
        """
        progress = LearningProgress(
            package_name=package_name,
            topic=topic,
            completed=True,
            score=score,
        )
        self.upsert_progress(progress)

    def get_completion_stats(self, package_name: str) -> dict[str, Any]:
        """
        Get completion statistics for a package.

        Args:
            package_name: Name of the package.

        Returns:
            Dict with completion statistics.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN completed THEN 1 ELSE 0 END) as completed,
                    AVG(score) as avg_score,
                    SUM(total_time_seconds) as total_time
                FROM learning_progress
                WHERE package_name = ?
                """,
                (package_name,),
            )
            row = cursor.fetchone()
            return {
                "total": row["total"] or 0,
                "completed": row["completed"] or 0,
                "avg_score": row["avg_score"] or 0.0,
                "total_time_seconds": row["total_time"] or 0,
            }

    # ==================== Quiz Results Methods ====================

    def add_quiz_result(self, result: QuizResult) -> int:
        """
        Add a quiz result.

        Args:
            result: QuizResult to save.

        Returns:
            Row ID of the inserted record.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO quiz_results (package_name, question, user_answer, correct)
                VALUES (?, ?, ?, ?)
                """,
                (result.package_name, result.question, result.user_answer, result.correct),
            )
            conn.commit()
            return cursor.lastrowid

    def get_quiz_results(self, package_name: str) -> list[QuizResult]:
        """
        Get quiz results for a package.

        Args:
            package_name: Name of the package.

        Returns:
            List of QuizResult records.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM quiz_results WHERE package_name = ? ORDER BY timestamp DESC",
                (package_name,),
            )
            return [
                QuizResult(
                    id=row["id"],
                    package_name=row["package_name"],
                    question=row["question"],
                    user_answer=row["user_answer"],
                    correct=bool(row["correct"]),
                    timestamp=row["timestamp"],
                )
                for row in cursor.fetchall()
            ]

    # ==================== Student Profile Methods ====================

    def get_student_profile(self) -> StudentProfile:
        """
        Get the student profile (singleton).

        Returns:
            StudentProfile record.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(self._SELECT_PROFILE)
            row = cursor.fetchone()
            if row:
                return StudentProfile(
                    id=row["id"],
                    mastered_concepts=json.loads(row["mastered_concepts"]),
                    weak_concepts=json.loads(row["weak_concepts"]),
                    learning_style=row["learning_style"],
                    last_session=row["last_session"],
                )
            # Create default profile if not exists
            return self._create_default_profile()

    def _create_default_profile(self) -> StudentProfile:
        """Create and return a default student profile (thread-safe)."""
        profile = StudentProfile()
        with self._get_connection() as conn:
            # Use INSERT OR IGNORE to handle race conditions
            conn.execute(
                """
                INSERT OR IGNORE INTO student_profile (mastered_concepts, weak_concepts, learning_style)
                VALUES (?, ?, ?)
                """,
                (
                    json.dumps(profile.mastered_concepts),
                    json.dumps(profile.weak_concepts),
                    profile.learning_style,
                ),
            )
            conn.commit()
            # Re-fetch to return actual profile (in case another thread created it)
            cursor = conn.execute(self._SELECT_PROFILE)
            row = cursor.fetchone()
            if row:
                return StudentProfile(
                    id=row["id"],
                    mastered_concepts=json.loads(row["mastered_concepts"]),
                    weak_concepts=json.loads(row["weak_concepts"]),
                    learning_style=row["learning_style"],
                    last_session=row["last_session"],
                )
        return profile

    def update_student_profile(self, profile: StudentProfile) -> None:
        """
        Update the student profile.

        Args:
            profile: StudentProfile to save.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE student_profile SET
                    mastered_concepts = ?,
                    weak_concepts = ?,
                    learning_style = ?,
                    last_session = ?
                WHERE id = (SELECT id FROM student_profile LIMIT 1)
                """,
                (
                    json.dumps(profile.mastered_concepts),
                    json.dumps(profile.weak_concepts),
                    profile.learning_style,
                    now,
                ),
            )
            conn.commit()

    def add_mastered_concept(self, concept: str) -> None:
        """
        Add a mastered concept to the student profile (atomic operation).

        Args:
            concept: Concept that was mastered.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            # Atomic read-modify-write within single connection
            cursor = conn.execute(self._SELECT_PROFILE)
            row = cursor.fetchone()
            if not row:
                self._create_default_profile()
                cursor = conn.execute(self._SELECT_PROFILE)
                row = cursor.fetchone()

            mastered = json.loads(row["mastered_concepts"])
            weak = json.loads(row["weak_concepts"])

            if concept not in mastered:
                mastered.append(concept)
                # Remove from weak concepts if present
                if concept in weak:
                    weak.remove(concept)

                conn.execute(
                    """UPDATE student_profile SET
                        mastered_concepts = ?,
                        weak_concepts = ?,
                        last_session = ?
                    WHERE id = ?""",
                    (json.dumps(mastered), json.dumps(weak), now, row["id"]),
                )
                conn.commit()

    def add_weak_concept(self, concept: str) -> None:
        """
        Add a weak concept to the student profile (atomic operation).

        Args:
            concept: Concept the student struggles with.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            # Atomic read-modify-write within single connection
            cursor = conn.execute(self._SELECT_PROFILE)
            row = cursor.fetchone()
            if not row:
                self._create_default_profile()
                cursor = conn.execute(self._SELECT_PROFILE)
                row = cursor.fetchone()

            mastered = json.loads(row["mastered_concepts"])
            weak = json.loads(row["weak_concepts"])

            if concept not in weak and concept not in mastered:
                weak.append(concept)
                conn.execute(
                    """UPDATE student_profile SET
                        weak_concepts = ?,
                        last_session = ?
                    WHERE id = ?""",
                    (json.dumps(weak), now, row["id"]),
                )
                conn.commit()

    # ==================== Lesson Cache Methods ====================

    def cache_lesson(self, package_name: str, content: dict[str, Any], ttl_hours: int = 24) -> None:
        """
        Cache lesson content.

        Args:
            package_name: Name of the package.
            content: Lesson content to cache.
            ttl_hours: Time-to-live in hours.
        """
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=ttl_hours)).isoformat()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO lesson_cache (package_name, content, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(package_name) DO UPDATE SET
                    content = excluded.content,
                    created_at = CURRENT_TIMESTAMP,
                    expires_at = excluded.expires_at
                """,
                (package_name, json.dumps(content), expires_at),
            )
            conn.commit()

    def get_cached_lesson(self, package_name: str) -> dict[str, Any] | None:
        """
        Get cached lesson content if not expired.

        Args:
            package_name: Name of the package.

        Returns:
            Cached lesson content or None if not found/expired.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT content FROM lesson_cache
                WHERE package_name = ? AND expires_at > ?
                """,
                (package_name, now),
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row["content"])
            return None

    def clear_expired_cache(self) -> int:
        """
        Clear expired cache entries.

        Returns:
            Number of entries cleared.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM lesson_cache WHERE expires_at <= ?", (now,))
            conn.commit()
            return cursor.rowcount

    # ==================== Utility Methods ====================

    def reset_progress(self, package_name: str | None = None) -> int:
        """
        Reset learning progress.

        Args:
            package_name: Optional filter by package. If None, resets all.

        Returns:
            Number of records deleted.
        """
        with self._get_connection() as conn:
            if package_name:
                cursor = conn.execute(
                    "DELETE FROM learning_progress WHERE package_name = ?", (package_name,)
                )
            else:
                cursor = conn.execute("DELETE FROM learning_progress")
            conn.commit()
            return cursor.rowcount

    def get_packages_studied(self) -> list[str]:
        """
        Get list of all packages that have been studied.

        Returns:
            List of unique package names.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT DISTINCT package_name FROM learning_progress ORDER BY package_name"
            )
            return [row["package_name"] for row in cursor.fetchall()]
