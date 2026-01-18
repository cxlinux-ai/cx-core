#!/usr/bin/env python3
"""
Cortex Linux - AI Context Memory System
Issue #24: Intelligent learning and pattern recognition for user interactions

This module provides persistent memory for the AI to learn from user patterns,
remember preferences, suggest optimizations, and personalize the experience.
"""

import hashlib
import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cortex.utils.db_pool import SQLiteConnectionPool, get_connection_pool


@dataclass
class MemoryEntry:
    """Represents a single memory entry in the system"""

    id: int | None = None
    timestamp: str = ""
    category: str = ""  # package, command, pattern, preference, error
    context: str = ""
    action: str = ""
    result: str = ""
    success: bool = True
    confidence: float = 1.0
    frequency: int = 1
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if self.metadata is None:
            self.metadata = {}


@dataclass
class Pattern:
    """Represents a learned pattern"""

    pattern_id: str
    pattern_type: str  # installation, configuration, workflow
    description: str
    frequency: int
    last_seen: str
    confidence: float
    actions: list[str]
    context: dict[str, Any]


@dataclass
class Suggestion:
    """Represents an AI-generated suggestion"""

    suggestion_id: str
    suggestion_type: str  # optimization, alternative, warning
    title: str
    description: str
    confidence: float
    based_on: list[str]  # Memory entry IDs
    created_at: str


class ContextMemory:
    """
    AI Context Memory System for Cortex Linux

    Features:
    - Persistent storage of user interactions
    - Pattern recognition and learning
    - Intelligent suggestions based on history
    - Context-aware recommendations
    - Privacy-preserving anonymization
    """

    def __init__(self, db_path: str = "~/.cortex/context_memory.db"):
        """Initialize the context memory system"""
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._pool: SQLiteConnectionPool | None = None
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database schema"""
        # Initialize connection pool (thread-safe singleton)
        self._pool = get_connection_pool(str(self.db_path), pool_size=5)

        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            # Memory entries table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    category TEXT NOT NULL,
                    context TEXT,
                    action TEXT NOT NULL,
                    result TEXT,
                    success BOOLEAN DEFAULT 1,
                    confidence REAL DEFAULT 1.0,
                    frequency INTEGER DEFAULT 1,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Patterns table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    pattern_id TEXT PRIMARY KEY,
                    pattern_type TEXT NOT NULL,
                    description TEXT,
                    frequency INTEGER DEFAULT 1,
                    last_seen TEXT,
                    confidence REAL DEFAULT 0.0,
                    actions TEXT,
                    context TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Suggestions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS suggestions (
                    suggestion_id TEXT PRIMARY KEY,
                    suggestion_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    confidence REAL DEFAULT 0.0,
                    based_on TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    dismissed BOOLEAN DEFAULT 0
                )
            """)

            # User preferences table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    category TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for performance
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_category ON memory_entries(category)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_timestamp ON memory_entries(timestamp)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_suggestions_type ON suggestions(suggestion_type)"
            )

            conn.commit()

    def record_interaction(self, entry: MemoryEntry) -> int:
        """
        Record a user interaction in memory

        Args:
            entry: MemoryEntry object containing interaction details

        Returns:
            ID of the inserted memory entry
        """
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO memory_entries
                (timestamp, category, context, action, result, success, confidence, frequency, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.timestamp,
                    entry.category,
                    entry.context,
                    entry.action,
                    entry.result,
                    entry.success,
                    entry.confidence,
                    entry.frequency,
                    json.dumps(entry.metadata),
                ),
            )

            entry_id = cursor.lastrowid
            conn.commit()

        # Trigger pattern analysis
        self._analyze_patterns(entry)

        return entry_id

    def get_similar_interactions(self, context: str, limit: int = 10) -> list[MemoryEntry]:
        """
        Find similar past interactions based on context

        Args:
            context: Context string to match against
            limit: Maximum number of results

        Returns:
            List of similar MemoryEntry objects
        """
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            # Simple keyword-based similarity for now
            keywords = self._extract_keywords(context)

            results = []
            for keyword in keywords:
                cursor.execute(
                    """
                    SELECT * FROM memory_entries
                    WHERE context LIKE ? OR action LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """,
                    (f"%{keyword}%", f"%{keyword}%", limit),
                )

                for row in cursor.fetchall():
                    entry = self._row_to_memory_entry(row)
                    if entry not in results:
                        results.append(entry)

        return results[:limit]

    def _row_to_memory_entry(self, row: tuple) -> MemoryEntry:
        """Convert database row to MemoryEntry object"""
        return MemoryEntry(
            id=row[0],
            timestamp=row[1],
            category=row[2],
            context=row[3],
            action=row[4],
            result=row[5],
            success=bool(row[6]),
            confidence=row[7],
            frequency=row[8],
            metadata=json.loads(row[9]) if row[9] else {},
        )

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from text"""
        # Remove common words and extract significant terms
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
        }
        words = re.findall(r"\b\w+\b", text.lower())
        return [w for w in words if w not in stopwords and len(w) > 2]

    def _analyze_patterns(self, entry: MemoryEntry):
        """
        Analyze entry for patterns and update pattern database

        This runs after each new entry to detect recurring patterns
        """
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            # Look for similar actions in recent history
            cursor.execute(
                """
                SELECT action, COUNT(*) as count
                FROM memory_entries
                WHERE category = ?
                AND timestamp > datetime('now', '-30 days')
                GROUP BY action
                HAVING count >= 3
            """,
                (entry.category,),
            )

            for row in cursor.fetchall():
                action, frequency = row
                pattern_id = self._generate_pattern_id(entry.category, action)

                # Update or create pattern
                cursor.execute(
                    """
                    INSERT INTO patterns (pattern_id, pattern_type, description, frequency, last_seen, confidence, actions, context)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(pattern_id) DO UPDATE SET
                        frequency = ?,
                        last_seen = ?,
                        confidence = MIN(1.0, confidence + 0.1)
                """,
                    (
                        pattern_id,
                        entry.category,
                        f"Recurring pattern: {action}",
                        frequency,
                        entry.timestamp,
                        min(1.0, frequency / 10.0),  # Confidence increases with frequency
                        json.dumps([action]),
                        json.dumps({"category": entry.category}),
                        frequency,
                        entry.timestamp,
                    ),
                )

            conn.commit()

    def _generate_pattern_id(self, category: str, action: str) -> str:
        """Generate unique pattern ID"""
        content = f"{category}:{action}".encode()
        return hashlib.sha256(content).hexdigest()[:16]

    def get_patterns(
        self, pattern_type: str | None = None, min_confidence: float = 0.5
    ) -> list[Pattern]:
        """
        Retrieve learned patterns

        Args:
            pattern_type: Filter by pattern type
            min_confidence: Minimum confidence threshold

        Returns:
            List of Pattern objects
        """
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT * FROM patterns
                WHERE confidence >= ?
            """
            params = [min_confidence]

            if pattern_type:
                query += " AND pattern_type = ?"
                params.append(pattern_type)

            query += " ORDER BY confidence DESC, frequency DESC"

            cursor.execute(query, params)

            patterns = []
            for row in cursor.fetchall():
                pattern = Pattern(
                    pattern_id=row[0],
                    pattern_type=row[1],
                    description=row[2],
                    frequency=row[3],
                    last_seen=row[4],
                    confidence=row[5],
                    actions=json.loads(row[6]),
                    context=json.loads(row[7]),
                )
                patterns.append(pattern)

        return patterns

    def generate_suggestions(self, context: str = None) -> list[Suggestion]:
        """
        Generate intelligent suggestions based on memory and patterns

        Args:
            context: Optional context to focus suggestions

        Returns:
            List of Suggestion objects
        """
        suggestions = []

        # Get high-confidence patterns
        patterns = self.get_patterns(min_confidence=0.7)

        # Get recent memory entries
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM memory_entries
                WHERE timestamp > datetime('now', '-7 days')
                ORDER BY timestamp DESC
                LIMIT 50
            """)

            recent_entries = [self._row_to_memory_entry(row) for row in cursor.fetchall()]

        # Analyze for optimization opportunities
        suggestions.extend(self._suggest_optimizations(recent_entries, patterns))

        # Suggest alternatives based on failures
        suggestions.extend(self._suggest_alternatives(recent_entries))

        # Suggest proactive actions based on patterns
        suggestions.extend(self._suggest_proactive_actions(patterns))

        # Store suggestions
        for suggestion in suggestions:
            self._store_suggestion(suggestion)

        return suggestions

    def _suggest_optimizations(
        self, entries: list[MemoryEntry], patterns: list[Pattern]
    ) -> list[Suggestion]:
        """Generate optimization suggestions"""
        suggestions = []

        # Check for repeated installations
        package_counts = Counter([e.action for e in entries if e.category == "package"])

        for package, count in package_counts.items():
            if count >= 3:
                suggestion = Suggestion(
                    suggestion_id=self._generate_suggestion_id("optimization", package),
                    suggestion_type="optimization",
                    title=f"Frequent Installation: {package}",
                    description=f"You've installed {package} {count} times recently. Consider adding it to your default setup script.",
                    confidence=min(1.0, count / 5.0),
                    based_on=[str(e.id) for e in entries if e.action == package],
                    created_at=datetime.now().isoformat(),
                )
                suggestions.append(suggestion)

        return suggestions

    def _suggest_alternatives(self, entries: list[MemoryEntry]) -> list[Suggestion]:
        """Suggest alternatives for failed operations"""
        suggestions = []

        failed = [e for e in entries if not e.success]

        for entry in failed:
            # Look for successful similar operations
            similar = self.get_similar_interactions(entry.context, limit=5)
            successful = [s for s in similar if s.success and s.action != entry.action]

            if successful:
                suggestion = Suggestion(
                    suggestion_id=self._generate_suggestion_id("alternative", entry.action),
                    suggestion_type="alternative",
                    title=f"Alternative to: {entry.action}",
                    description=f"Based on your history, try: {successful[0].action}",
                    confidence=0.7,
                    based_on=[str(entry.id)],
                    created_at=datetime.now().isoformat(),
                )
                suggestions.append(suggestion)

        return suggestions

    def _suggest_proactive_actions(self, patterns: list[Pattern]) -> list[Suggestion]:
        """Suggest proactive actions based on patterns"""
        suggestions = []

        for pattern in patterns:
            if pattern.confidence > 0.8 and pattern.frequency >= 5:
                suggestion = Suggestion(
                    suggestion_id=self._generate_suggestion_id("proactive", pattern.pattern_id),
                    suggestion_type="optimization",
                    title=f"Automate: {pattern.description}",
                    description=f"You frequently do this ({pattern.frequency} times). Would you like to automate it?",
                    confidence=pattern.confidence,
                    based_on=[pattern.pattern_id],
                    created_at=datetime.now().isoformat(),
                )
                suggestions.append(suggestion)

        return suggestions

    def _generate_suggestion_id(self, suggestion_type: str, identifier: str) -> str:
        """Generate unique suggestion ID"""
        content = f"{suggestion_type}:{identifier}:{datetime.now().date()}".encode()
        return hashlib.sha256(content).hexdigest()[:16]

    def _store_suggestion(self, suggestion: Suggestion):
        """Store suggestion in database"""
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR IGNORE INTO suggestions
                (suggestion_id, suggestion_type, title, description, confidence, based_on, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    suggestion.suggestion_id,
                    suggestion.suggestion_type,
                    suggestion.title,
                    suggestion.description,
                    suggestion.confidence,
                    json.dumps(suggestion.based_on),
                    suggestion.created_at,
                ),
            )

            conn.commit()

    def get_active_suggestions(self, limit: int = 10) -> list[Suggestion]:
        """Get active (non-dismissed) suggestions"""
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM suggestions
                WHERE dismissed = 0
                ORDER BY confidence DESC, created_at DESC
                LIMIT ?
            """,
                (limit,),
            )

            suggestions = []
            for row in cursor.fetchall():
                suggestion = Suggestion(
                    suggestion_id=row[0],
                    suggestion_type=row[1],
                    title=row[2],
                    description=row[3],
                    confidence=row[4],
                    based_on=json.loads(row[5]),
                    created_at=row[6],
                )
                suggestions.append(suggestion)

        return suggestions

    def dismiss_suggestion(self, suggestion_id: str):
        """Mark a suggestion as dismissed"""
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE suggestions
                SET dismissed = 1
                WHERE suggestion_id = ?
            """,
                (suggestion_id,),
            )

            conn.commit()

    def set_preference(self, key: str, value: Any, category: str = "general"):
        """Store a user preference"""
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO preferences (key, value, category, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = ?,
                    updated_at = ?
            """,
                (
                    key,
                    json.dumps(value),
                    category,
                    datetime.now().isoformat(),
                    json.dumps(value),
                    datetime.now().isoformat(),
                ),
            )

            conn.commit()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Retrieve a user preference"""
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT value FROM preferences WHERE key = ?
            """,
                (key,),
            )

            row = cursor.fetchone()

        if row:
            return json.loads(row[0])
        return default

    def get_statistics(self) -> dict[str, Any]:
        """Get memory system statistics"""
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            # Total entries
            cursor.execute("SELECT COUNT(*) FROM memory_entries")
            stats["total_entries"] = cursor.fetchone()[0]

            # Entries by category
            cursor.execute("""
                SELECT category, COUNT(*)
                FROM memory_entries
                GROUP BY category
            """)
            stats["by_category"] = dict(cursor.fetchall())

            # Success rate
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate
                FROM memory_entries
            """)
            stats["success_rate"] = (
                round(cursor.fetchone()[0], 2) if stats["total_entries"] > 0 else 0
            )

            # Total patterns
            cursor.execute("SELECT COUNT(*) FROM patterns")
            stats["total_patterns"] = cursor.fetchone()[0]

            # Active suggestions
            cursor.execute("SELECT COUNT(*) FROM suggestions WHERE dismissed = 0")
            stats["active_suggestions"] = cursor.fetchone()[0]

            # Recent activity
            cursor.execute("""
                SELECT COUNT(*) FROM memory_entries
                WHERE timestamp > datetime('now', '-7 days')
            """)
            stats["recent_activity"] = cursor.fetchone()[0]

        return stats

    def export_memory(self, output_path: str, include_dismissed: bool = False):
        """Export all memory data to JSON"""
        with self._pool.get_connection() as conn:
            cursor = conn.cursor()

            data = {
                "exported_at": datetime.now().isoformat(),
                "entries": [],
                "patterns": [],
                "suggestions": [],
                "preferences": [],
            }

            # Export entries
            cursor.execute("SELECT * FROM memory_entries")
            for row in cursor.fetchall():
                entry = self._row_to_memory_entry(row)
                data["entries"].append(asdict(entry))

            # Export patterns
            cursor.execute("SELECT * FROM patterns")
            for row in cursor.fetchall():
                pattern = {
                    "pattern_id": row[0],
                    "pattern_type": row[1],
                    "description": row[2],
                    "frequency": row[3],
                    "last_seen": row[4],
                    "confidence": row[5],
                    "actions": json.loads(row[6]),
                    "context": json.loads(row[7]),
                }
                data["patterns"].append(pattern)

            # Export suggestions
            query = "SELECT * FROM suggestions"
            if not include_dismissed:
                query += " WHERE dismissed = 0"
            cursor.execute(query)

            for row in cursor.fetchall():
                suggestion = {
                    "suggestion_id": row[0],
                    "suggestion_type": row[1],
                    "title": row[2],
                    "description": row[3],
                    "confidence": row[4],
                    "based_on": json.loads(row[5]),
                    "created_at": row[6],
                }
                data["suggestions"].append(suggestion)

            # Export preferences
            cursor.execute("SELECT key, value, category FROM preferences")
            for row in cursor.fetchall():
                pref = {"key": row[0], "value": json.loads(row[1]), "category": row[2]}
                data["preferences"].append(pref)

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        return output_path


def main():
    """Example usage of the Context Memory System"""
    memory = ContextMemory()

    # Record some interactions
    entry1 = MemoryEntry(
        category="package",
        context="User wants to install Docker",
        action="install docker-ce docker-compose",
        result="Successfully installed Docker 24.0.5",
        success=True,
        metadata={"packages": ["docker-ce", "docker-compose"]},
    )
    memory.record_interaction(entry1)

    entry2 = MemoryEntry(
        category="package",
        context="User wants to install PostgreSQL",
        action="install postgresql-15",
        result="Successfully installed PostgreSQL 15.3",
        success=True,
        metadata={"packages": ["postgresql-15"]},
    )
    memory.record_interaction(entry2)

    # Generate suggestions
    suggestions = memory.generate_suggestions()

    print("📊 Memory Statistics:")
    stats = memory.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n💡 Active Suggestions:")
    active_suggestions = memory.get_active_suggestions()
    for sugg in active_suggestions:
        print(f"  [{sugg.suggestion_type}] {sugg.title}")
        print(f"    {sugg.description}")
        print(f"    Confidence: {sugg.confidence:.0%}\n")

    print("✅ Context Memory System demo complete!")


if __name__ == "__main__":
    main()
