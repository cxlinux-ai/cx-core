"""
Graceful Degradation Module for Cortex Linux

Provides fallback behavior when LLM API is unavailable, ensuring core
functionality continues to work even without AI assistance.

Issue: #257
"""

import hashlib
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from cortex.utils.db_pool import SQLiteConnectionPool, get_connection_pool

logger = logging.getLogger(__name__)


class APIStatus(Enum):
    """Current status of the LLM API connection."""

    AVAILABLE = "available"
    DEGRADED = "degraded"  # Slow responses, partial functionality
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class FallbackMode(Enum):
    """Operating mode when API is unavailable."""

    FULL_AI = "full_ai"  # Normal operation with AI
    CACHED_ONLY = "cached_only"  # Use cached responses only
    PATTERN_MATCHING = "pattern_matching"  # Use local pattern matching
    MANUAL_MODE = "manual_mode"  # Direct apt commands only


@dataclass
class HealthCheckResult:
    """Result of an API health check."""

    status: APIStatus
    latency_ms: float | None = None
    error_message: str | None = None
    checked_at: datetime = field(default_factory=datetime.now)

    def is_healthy(self) -> bool:
        return self.status == APIStatus.AVAILABLE


@dataclass
class CachedResponse:
    """A cached LLM response for offline use."""

    query_hash: str
    query: str
    response: str
    created_at: datetime
    hit_count: int = 0
    last_used: datetime | None = None


class ResponseCache:
    """SQLite-based cache for LLM responses."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or Path.home() / ".cortex" / "response_cache.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._pool: SQLiteConnectionPool | None = None
        self._init_db()

    def _init_db(self):
        """Initialize the cache database."""
        self._pool = get_connection_pool(str(self.db_path), pool_size=5)
        with self._pool.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS response_cache (
                    query_hash TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    response TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    hit_count INTEGER DEFAULT 0,
                    last_used TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_used
                ON response_cache(last_used)
            """)
            conn.commit()

    def _hash_query(self, query: str) -> str:
        """Generate a hash for a query."""
        normalized = query.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def get(self, query: str) -> CachedResponse | None:
        """Retrieve a cached response."""
        query_hash = self._hash_query(query)

        with self._pool.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM response_cache WHERE query_hash = ?", (query_hash,)
            )
            row = cursor.fetchone()

            if row:
                # Update hit count and last_used
                conn.execute(
                    """
                    UPDATE response_cache
                    SET hit_count = hit_count + 1, last_used = CURRENT_TIMESTAMP
                    WHERE query_hash = ?
                """,
                    (query_hash,),
                )
                conn.commit()

                return CachedResponse(
                    query_hash=row["query_hash"],
                    query=row["query"],
                    response=row["response"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    hit_count=row["hit_count"] + 1,
                    last_used=datetime.now(),
                )

        return None

    def put(self, query: str, response: str) -> CachedResponse:
        """Store a response in the cache."""
        query_hash = self._hash_query(query)

        with self._pool.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO response_cache
                (query_hash, query, response, created_at, hit_count, last_used)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, 0, NULL)
            """,
                (query_hash, query, response),
            )
            conn.commit()

        return CachedResponse(
            query_hash=query_hash, query=query, response=response, created_at=datetime.now()
        )

    def get_similar(self, query: str, limit: int = 5) -> list[CachedResponse]:
        """Get similar cached responses using simple keyword matching."""
        keywords = set(query.lower().split())
        results = []

        with self._pool.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM response_cache ORDER BY hit_count DESC LIMIT 100")

            for row in cursor:
                cached_keywords = set(row["query"].lower().split())
                overlap = len(keywords & cached_keywords)
                if overlap > 0:
                    results.append(
                        (
                            overlap,
                            CachedResponse(
                                query_hash=row["query_hash"],
                                query=row["query"],
                                response=row["response"],
                                created_at=datetime.fromisoformat(row["created_at"]),
                                hit_count=row["hit_count"],
                            ),
                        )
                    )

        # Sort by overlap score and return top matches
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    def clear_old_entries(self, days: int = 30) -> int:
        """Remove entries older than specified days."""
        cutoff = datetime.now() - timedelta(days=days)

        with self._pool.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM response_cache WHERE created_at < ?", (cutoff.isoformat(),)
            )
            conn.commit()
            return cursor.rowcount

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._pool.get_connection() as conn:
            conn.row_factory = sqlite3.Row

            total = conn.execute("SELECT COUNT(*) as count FROM response_cache").fetchone()["count"]

            total_hits = (
                conn.execute("SELECT SUM(hit_count) as hits FROM response_cache").fetchone()["hits"]
                or 0
            )

            return {
                "total_entries": total,
                "total_hits": total_hits,
                "db_size_kb": self.db_path.stat().st_size / 1024 if self.db_path.exists() else 0,
            }


class PatternMatcher:
    """Local pattern matching for common package operations."""

    # Common package installation patterns
    INSTALL_PATTERNS = {
        # Web development
        r"(?:install|setup|add)\s+(?:node|nodejs)": "sudo apt install nodejs npm",
        r"(?:install|setup|add)\s+(?:python|python3)": "sudo apt install python3 python3-pip python3-venv",
        r"(?:install|setup|add)\s+(?:docker)": "sudo apt install docker.io docker-compose",
        r"(?:install|setup|add)\s+(?:nginx)": "sudo apt install nginx",
        r"(?:install|setup|add)\s+(?:postgresql|postgres)": "sudo apt install postgresql postgresql-contrib",
        r"(?:install|setup|add)\s+(?:mysql|mariadb)": "sudo apt install mysql-server",
        r"(?:install|setup|add)\s+(?:redis)": "sudo apt install redis-server",
        r"(?:install|setup|add)\s+(?:mongodb)": "sudo apt install mongodb",
        # Development tools
        r"(?:install|setup|add)\s+(?:git)": "sudo apt install git",
        r"(?:install|setup|add)\s+(?:vim|neovim)": "sudo apt install neovim",
        r"(?:install|setup|add)\s+(?:curl)": "sudo apt install curl",
        r"(?:install|setup|add)\s+(?:wget)": "sudo apt install wget",
        r"(?:install|setup|add)\s+(?:htop)": "sudo apt install htop",
        r"(?:install|setup|add)\s+(?:tmux)": "sudo apt install tmux",
        # Languages
        r"(?:install|setup|add)\s+(?:rust|rustc|cargo)": "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
        r"(?:install|setup|add)\s+(?:go|golang)": "sudo apt install golang-go",
        r"(?:install|setup|add)\s+(?:java|openjdk)": "sudo apt install default-jdk",
        # ML/AI
        r"(?:install|setup|add)\s+(?:cuda|nvidia.?driver)": "sudo apt install nvidia-driver-535 nvidia-cuda-toolkit",
        r"(?:install|setup|add)\s+(?:tensorflow)": "pip install tensorflow",
        r"(?:install|setup|add)\s+(?:pytorch|torch)": "pip install torch torchvision torchaudio",
    }

    # Common operations
    OPERATION_PATTERNS = {
        r"(?:update|upgrade)\s+(?:system|all|packages)": "sudo apt update && sudo apt upgrade -y",
        r"(?:clean|cleanup)\s+(?:system|apt|packages)": "sudo apt autoremove -y && sudo apt autoclean",
        r"(?:search|find)\s+(?:package\s+)?(.+)": "apt search {0}",
        r"(?:remove|uninstall|delete)\s+(.+)": "sudo apt remove {0}",
        r"(?:info|details|about)\s+(.+)": "apt show {0}",
        r"(?:list)\s+(?:installed)": "apt list --installed",
    }

    def __init__(self):
        import re

        self.re = re
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for efficiency."""
        self.compiled_install = [
            (self.re.compile(pattern, self.re.IGNORECASE), command)
            for pattern, command in self.INSTALL_PATTERNS.items()
        ]
        self.compiled_ops = [
            (self.re.compile(pattern, self.re.IGNORECASE), command)
            for pattern, command in self.OPERATION_PATTERNS.items()
        ]

    def match(self, query: str) -> dict[str, Any] | None:
        """Try to match query against known patterns."""
        query = query.strip()

        # Try install patterns first
        for pattern, command in self.compiled_install:
            if pattern.search(query):
                return {
                    "matched": True,
                    "type": "install",
                    "command": command,
                    "confidence": 0.8,
                    "source": "pattern_matching",
                }

        # Try operation patterns
        for pattern, command in self.compiled_ops:
            match = pattern.search(query)
            if match:
                # Substitute any captured groups
                final_command = command
                for i, group in enumerate(match.groups()):
                    if group:
                        final_command = final_command.replace(f"{{{i}}}", group)

                return {
                    "matched": True,
                    "type": "operation",
                    "command": final_command,
                    "confidence": 0.7,
                    "source": "pattern_matching",
                }

        return None


class GracefulDegradation:
    """
    Main class for handling graceful degradation when API is unavailable.

    Provides multiple fallback strategies:
    1. Response caching - Use previously cached LLM responses
    2. Pattern matching - Local regex-based command generation
    3. Manual mode - Direct apt command passthrough
    """

    def __init__(
        self,
        cache: ResponseCache | None = None,
        health_check_interval: int = 60,
        api_timeout: float = 10.0,
    ):
        self.cache = cache or ResponseCache()
        self.pattern_matcher = PatternMatcher()
        self.health_check_interval = health_check_interval
        self.api_timeout = api_timeout

        self._last_health_check: HealthCheckResult | None = None
        self._current_mode = FallbackMode.FULL_AI
        self._api_failures = 0
        self._max_failures_before_fallback = 3

    @property
    def current_mode(self) -> FallbackMode:
        """Get the current operating mode."""
        return self._current_mode

    def check_api_health(self, api_check_fn: Callable | None = None) -> HealthCheckResult:
        """
        Check if the LLM API is available.

        Args:
            api_check_fn: Optional function that returns True if API is healthy
        """
        start_time = time.time()

        try:
            if api_check_fn:
                is_healthy = api_check_fn()
            else:
                # Default: check if API key is configured
                is_healthy = bool(
                    os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
                )

            latency = (time.time() - start_time) * 1000

            if is_healthy:
                status = APIStatus.AVAILABLE if latency < 1000 else APIStatus.DEGRADED
                self._api_failures = 0
            else:
                status = APIStatus.UNAVAILABLE
                self._api_failures += 1

            result = HealthCheckResult(status=status, latency_ms=latency)

        except Exception as e:
            self._api_failures += 1
            result = HealthCheckResult(status=APIStatus.UNAVAILABLE, error_message=str(e))

        self._last_health_check = result
        self._update_mode()

        return result

    def _update_mode(self):
        """Update operating mode based on API health."""
        if self._api_failures >= self._max_failures_before_fallback:
            if self.cache.get_stats()["total_entries"] > 0:
                self._current_mode = FallbackMode.CACHED_ONLY
            else:
                self._current_mode = FallbackMode.PATTERN_MATCHING
        elif self._api_failures > 0:
            self._current_mode = FallbackMode.CACHED_ONLY
        else:
            self._current_mode = FallbackMode.FULL_AI

    def process_query(
        self, query: str, llm_fn: Callable[[str], str] | None = None
    ) -> dict[str, Any]:
        """
        Process a query with graceful degradation.

        Args:
            query: The user's natural language query
            llm_fn: Function to call the LLM API (optional)

        Returns:
            Dict with response, source, and confidence
        """
        result = {
            "query": query,
            "response": None,
            "command": None,
            "source": None,
            "confidence": 0.0,
            "mode": self._current_mode.value,
            "cached": False,
        }

        # Strategy 1: Try LLM if available
        if self._current_mode == FallbackMode.FULL_AI and llm_fn:
            try:
                response = llm_fn(query)
                result["response"] = response
                result["source"] = "llm"
                result["confidence"] = 1.0

                # Cache the response for future use
                self.cache.put(query, response)

                return result
            except Exception as e:
                logger.warning(f"LLM call failed: {e}")
                self._api_failures += 1
                self._update_mode()

        # Strategy 2: Check cache
        cached = self.cache.get(query)
        if cached:
            result["response"] = cached.response
            result["source"] = "cache"
            result["confidence"] = 0.9
            result["cached"] = True
            return result

        # Strategy 3: Check similar cached responses
        similar = self.cache.get_similar(query, limit=1)
        if similar:
            result["response"] = similar[0].response
            result["source"] = "cache_similar"
            result["confidence"] = 0.7
            result["cached"] = True
            result["similar_query"] = similar[0].query
            return result

        # Strategy 4: Pattern matching
        pattern_result = self.pattern_matcher.match(query)
        if pattern_result:
            result["command"] = pattern_result["command"]
            result["source"] = "pattern_matching"
            result["confidence"] = pattern_result["confidence"]
            result["response"] = f"Suggested command: {pattern_result['command']}"
            return result

        # Strategy 5: Manual mode fallback
        result["source"] = "manual_mode"
        result["confidence"] = 0.0
        result["response"] = (
            "I couldn't process this request automatically. "
            "Please use apt commands directly:\n"
            "  - apt search <package>  - Search for packages\n"
            "  - apt show <package>    - Show package details\n"
            "  - sudo apt install <package> - Install a package"
        )

        return result

    def get_status(self) -> dict[str, Any]:
        """Get current degradation status."""
        cache_stats = self.cache.get_stats()

        return {
            "mode": self._current_mode.value,
            "api_status": (
                self._last_health_check.status.value if self._last_health_check else "unknown"
            ),
            "api_failures": self._api_failures,
            "cache_entries": cache_stats["total_entries"],
            "cache_hits": cache_stats["total_hits"],
            "last_check": (
                self._last_health_check.checked_at.isoformat() if self._last_health_check else None
            ),
        }

    def force_mode(self, mode: FallbackMode):
        """Force a specific operating mode (for testing)."""
        self._current_mode = mode

    def reset(self):
        """Reset to default state."""
        self._api_failures = 0
        self._current_mode = FallbackMode.FULL_AI
        self._last_health_check = None


# CLI Integration
# Global instance for degradation manager (thread-safe)
_degradation_instance = None
_degradation_lock = threading.Lock()


def get_degradation_manager() -> GracefulDegradation:
    """Get or create the global degradation manager (thread-safe)."""
    global _degradation_instance
    # Fast path: avoid lock if already initialized
    if _degradation_instance is None:
        with _degradation_lock:
            # Double-checked locking pattern
            if _degradation_instance is None:
                _degradation_instance = GracefulDegradation()
    return _degradation_instance


def process_with_fallback(query: str, llm_fn: Callable | None = None) -> dict[str, Any]:
    """Convenience function for processing queries with fallback."""
    manager = get_degradation_manager()
    return manager.process_query(query, llm_fn)


if __name__ == "__main__":
    # Demo usage
    manager = GracefulDegradation()

    # Simulate API being unavailable
    manager.force_mode(FallbackMode.PATTERN_MATCHING)

    test_queries = [
        "install docker",
        "setup python for machine learning",
        "update all packages",
        "search for image editors",
        "remove vim",
    ]

    print("Graceful Degradation Demo")
    print("=" * 50)
    print(f"Current mode: {manager.current_mode.value}")
    print()

    for query in test_queries:
        result = manager.process_query(query)
        print(f"Query: {query}")
        print(f"  Source: {result['source']}")
        print(f"  Confidence: {result['confidence']:.0%}")
        if result["command"]:
            print(f"  Command: {result['command']}")
        print()
