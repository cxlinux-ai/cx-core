"""
Thread-safe SQLite connection pooling for Cortex Linux.

Provides connection pooling to prevent database lock contention
and enable safe concurrent access in Python 3.14 free-threading mode.

Author: Cortex Linux Team
License: Apache 2.0
"""

import queue
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


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
        Initialize the connection pool and pre-create the configured SQLite connections.
        
        Parameters:
            db_path: File system path to the SQLite database.
            pool_size: Maximum number of connections to maintain in the pool.
            timeout: Default timeout (seconds) used when acquiring a connection.
            check_same_thread: If False, allows connections to be used across threads; set True to enforce SQLite's same-thread restriction.
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
        Create a new SQLite connection configured for pooled concurrent access.
        
        The connection is tuned for concurrency and performance using these PRAGMA settings:
        journal_mode=WAL, synchronous=NORMAL, cache_size=-64000 (64MB), temp_store=MEMORY, and foreign_keys=ON.
        
        Returns:
            A configured sqlite3.Connection connected to the pool's database path.
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
        Acquire a connection from the pool and return it to the pool when the context exits.
        
        Used as a context manager; yields a `sqlite3.Connection` that callers can use for database operations. The connection is returned to the pool after the context block completes, even if an exception is raised.
        
        Returns:
            sqlite3.Connection: A connection from the pool.
        
        Raises:
            TimeoutError: If a connection cannot be acquired within the pool's configured timeout.
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
        Close all connections currently stored in the pool in a thread-safe manner.
        
        Returns:
            closed_count (int): Number of connections that were closed.
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
        """
        Enter the runtime context and provide the pool instance.
        
        Returns:
            SQLiteConnectionPool: The same pool instance to be used as the context manager target.
        """
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
    Retrieve or create a shared SQLiteConnectionPool for the given database path.
    
    If a pool already exists for the path, that pool is returned; otherwise a new pool is created, registered, and returned.
    
    Parameters:
        db_path (str | Path): Filesystem path to the SQLite database.
        pool_size (int): Maximum number of connections the pool will hold.
        timeout (float): Maximum seconds to wait when acquiring a connection from the pool.
    
    Returns:
        SQLiteConnectionPool: The connection pool associated with the given database path.
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
    Close and remove all global SQLiteConnectionPool instances.
    
    Closes every connection in the global pool registry and clears the registry.
    
    Returns:
        int: Total number of connections closed.
    """
    with _pools_lock:
        total_closed = 0
        for pool in _pools.values():
            total_closed += pool.close_all()
        _pools.clear()
        return total_closed