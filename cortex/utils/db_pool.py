"""
Thread-safe SQLite connection pooling for Cortex Linux.

Provides connection pooling to prevent database lock contention
and enable safe concurrent access in Python 3.14 free-threading mode.

Author: Cortex Linux Team
SPDX-License-Identifier: BUSL-1.1
"""

import queue
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class SQLiteConnectionPool:
    """
    Thread-safe SQLite connection pool.

    SQLite has limited concurrency support:
    - Multiple readers are OK with WAL mode
    - Single writer at a time (database-level locking)
    - SQLITE_BUSY errors occur under high write contention

    This pool manages connections and handles concurrent access gracefully.

    Usage:
        pool = SQLiteConnectionPool("/path/to/db.sqlite", pool_size=5)
        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ...")
    """

    def __init__(
        self,
        db_path: str | Path,
        pool_size: int = 5,
        timeout: float = 5.0,
        check_same_thread: bool = False,
    ):
        """
        Initialize connection pool.

        Args:
            db_path: Path to SQLite database file
            pool_size: Number of connections to maintain in pool
            timeout: Timeout for acquiring connection (seconds)
            check_same_thread: SQLite same-thread check (False for pooling)
        """
        self.db_path = str(db_path)
        self.pool_size = pool_size
        self.timeout = timeout
        self.check_same_thread = check_same_thread

        # Connection pool (thread-safe queue)
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=pool_size)
        self._pool_lock = threading.Lock()

        # Initialize connections
        for _ in range(pool_size):
            conn = self._create_connection()
            self._pool.put(conn)

    def _create_connection(self) -> sqlite3.Connection:
        """
        Create a new SQLite connection with optimal settings.

        Returns:
            Configured SQLite connection
        """
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            check_same_thread=self.check_same_thread,
        )

        # Enable WAL mode for better concurrency
        # WAL allows multiple readers + single writer simultaneously
        conn.execute("PRAGMA journal_mode=WAL")

        # NORMAL synchronous mode (faster, still safe with WAL)
        conn.execute("PRAGMA synchronous=NORMAL")

        # Larger cache for better performance
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache

        # Store temp tables in memory
        conn.execute("PRAGMA temp_store=MEMORY")

        # Enable foreign keys (if needed)
        conn.execute("PRAGMA foreign_keys=ON")

        return conn

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        """
        Get a connection from the pool (context manager).

        Automatically returns connection to pool when done,
        even if an exception occurs.

        Yields:
            SQLite connection from pool

        Raises:
            TimeoutError: If connection cannot be acquired within timeout

        Example:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
                results = cursor.fetchall()
        """
        try:
            conn = self._pool.get(timeout=self.timeout)
        except queue.Empty:
            raise TimeoutError(
                f"Could not acquire database connection within {self.timeout}s. "
                f"Pool size: {self.pool_size}. Consider increasing pool size or timeout."
            )

        try:
            yield conn
        finally:
            # Always return connection to pool
            try:
                self._pool.put(conn, block=False)
            except queue.Full:
                # Should never happen, but log if it does
                import logging

                logging.error(f"Connection pool overflow for {self.db_path}")

    def close_all(self):
        """
        Close all connections in the pool.

        Call this during shutdown to clean up resources.
        """
        with self._pool_lock:
            closed_count = 0
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                    closed_count += 1
                except queue.Empty:
                    break
            return closed_count

    def __enter__(self):
        """Support using pool as context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Close all connections when exiting context.

        For pools managed as global singletons via get_connection_pool(),
        avoid closing connections here to prevent affecting other users
        of the same shared pool.
        """
        # If this pool is a global singleton, do not close it on context exit.
        # This ensures that using a globally shared pool in a `with` block
        # does not disrupt other parts of the application.
        if self not in _pools.values():
            self.close_all()
        return False


# Global connection pools (one per database path)
# Thread-safe lazy initialization
_pools: dict[str, SQLiteConnectionPool] = {}
_pools_lock = threading.Lock()


def get_connection_pool(
    db_path: str | Path,
    pool_size: int = 5,
    timeout: float = 5.0,
) -> SQLiteConnectionPool:
    """
    Get or create a connection pool for a database.

    Uses double-checked locking for thread-safe singleton pattern.
    Returns existing pool if one exists for this database path.

    Args:
        db_path: Path to SQLite database file
        pool_size: Number of connections in pool (default: 5)
        timeout: Connection acquisition timeout in seconds (default: 5.0)

    Returns:
        SQLiteConnectionPool instance for the database

    Example:
        from cortex.utils.db_pool import get_connection_pool

        pool = get_connection_pool("/var/lib/cortex/cache.db")
        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ...")
    """
    db_path = str(db_path)

    # Fast path: check without lock
    if db_path in _pools:
        return _pools[db_path]

    # Slow path: acquire lock and double-check
    with _pools_lock:
        if db_path not in _pools:
            _pools[db_path] = SQLiteConnectionPool(
                db_path,
                pool_size=pool_size,
                timeout=timeout,
            )
        return _pools[db_path]


def close_all_pools():
    """
    Close all connection pools.

    Call this during application shutdown to clean up resources.

    Returns:
        Total number of connections closed
    """
    with _pools_lock:
        total_closed = 0
        for pool in _pools.values():
            total_closed += pool.close_all()
        _pools.clear()
        return total_closed
