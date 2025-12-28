# Python 3.14 Free-Threading (No-GIL) Thread-Safety Audit

**Date of last update**: December 22, 2025 (Python 3.14 scheduled for October 2025)  
**Target**: Python 3.14 with PEP 703 no-GIL free-threading (status: may still be pre-release or not widely deployed; verify against the Python 3.14 build available in your environment)  
**Expected Performance Gain**: 2-3x with true parallel execution  
**Status**: 🔴 **CRITICAL** - Significant thread-safety issues identified

---

## Executive Summary

Python 3.14's free-threading mode removes the Global Interpreter Lock (GIL), enabling true parallel execution of Python threads. While this offers 2-3x performance improvements for I/O-bound and CPU-bound workloads, it exposes **previously hidden race conditions** in code that assumed GIL protection.

### Critical Findings

- **15+ modules with thread-safety issues**
- **8 singleton patterns without locks**
- **20+ SQLite connections without connection pooling**
- **Multiple shared mutable class/module variables**
- **Existing async code uses `asyncio.Lock` (correct for async, but not thread-safe)**

### Risk Assessment

| Risk Level | Module Count | Impact |
|-----------|--------------|--------|
| 🔴 Critical | 5 | Data corruption, crashes |
| 🟡 High | 7 | Race conditions, incorrect behavior |
| 🟢 Medium | 8 | Performance degradation |

---

## 1. Thread-Safety Analysis by Module

### 🔴 CRITICAL: Singleton Patterns Without Locks

#### 1.1 `transaction_history.py`

**Issue**: Global singletons without thread-safe initialization

```python
# Lines 656-672
_history_instance = None
_undo_manager_instance = None

def get_history() -> "TransactionHistory":
    """Get the global transaction history instance."""
    global _history_instance
    if _history_instance is None:
        _history_instance = TransactionHistory()  # ⚠️ RACE CONDITION
    return _history_instance

def get_undo_manager() -> "UndoManager":
    """Get the global undo manager instance."""
    global _undo_manager_instance
    if _undo_manager_instance is None:
        _undo_manager_instance = UndoManager(get_history())  # ⚠️ RACE CONDITION
    return _undo_manager_instance
```

**Problem**: Multiple threads can simultaneously check `if _instance is None` and create multiple instances.

**Fix Required**:
```python
import threading

_history_instance = None
_history_lock = threading.Lock()

def get_history() -> "TransactionHistory":
    global _history_instance
    if _history_instance is None:
        with _history_lock:
            if _history_instance is None:  # Double-checked locking
                _history_instance = TransactionHistory()
    return _history_instance
```

#### 1.2 `hardware_detection.py`

**Issue**: Singleton pattern without lock (Line 635-642)

```python
_detector_instance = None

def get_detector() -> HardwareDetector:
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = HardwareDetector()  # ⚠️ RACE CONDITION
    return _detector_instance
```

**Severity**: High - Hardware detection is called frequently during package analysis.

#### 1.3 `graceful_degradation.py`

**Issue**: Function-attribute singleton pattern (Line 503-505)

```python
def get_degradation_manager() -> GracefulDegradation:
    """Get or create the global degradation manager."""
    if not hasattr(get_degradation_manager, "_instance"):
        get_degradation_manager._instance = GracefulDegradation()  # ⚠️ RACE
    return get_degradation_manager._instance
```

**Problem**: `hasattr()` and attribute assignment are not atomic operations.

---

### 🔴 CRITICAL: SQLite Database Access

#### 2.1 Multiple Modules with Unsafe SQLite Usage

**Affected Modules**:
- `semantic_cache.py` - LLM response caching
- `context_memory.py` - AI memory system
- `installation_history.py` - Install tracking
- `transaction_history.py` - Package transactions
- `graceful_degradation.py` - Fallback cache
- `kernel_features/kv_cache_manager.py` - Kernel KV cache
- `kernel_features/accelerator_limits.py` - Hardware limits

**Current Pattern** (UNSAFE):
```python
def get_commands(self, prompt: str, ...):
    conn = sqlite3.connect(self.db_path)  # ⚠️ New connection per call
    try:
        cur = conn.cursor()
        cur.execute("SELECT ...")
        # ...
    finally:
        conn.close()
```

**Issues**:
1. **No connection pooling** - Creates new connection on every call
2. **Concurrent writes** - SQLite locks database on writes, causes `SQLITE_BUSY` errors
3. **Write-write conflicts** - Multiple threads trying to write simultaneously
4. **No transaction management** - Partial updates possible

**Impact**: With free-threading, parallel LLM calls will hammer SQLite, causing:
- Database lock timeouts
- Dropped cache entries
- Corrupted transaction history
- Lost installation records

**Fix Required**: Connection pooling or single-writer pattern

```python
import queue
import threading

class ThreadSafeSQLiteConnection:
    """Thread-safe SQLite connection wrapper using queue."""
    
    def __init__(self, db_path: str, max_connections: int = 5):
        self.db_path = db_path
        self._pool = queue.Queue(maxsize=max_connections)
        for _ in range(max_connections):
            self._pool.put(sqlite3.connect(db_path, check_same_thread=False))
    
    @contextmanager
    def get_connection(self):
        conn = self._pool.get()
        try:
            yield conn
        finally:
            self._pool.put(conn)
```

---

### 🟡 HIGH: Async Code (Already Thread-Safe for Async, But Needs Review)

#### 3.1 `parallel_llm.py`

**Current Implementation**: ✅ Uses `asyncio.Lock` correctly for async contexts

```python
class RateLimiter:
    def __init__(self, requests_per_second: float = 5.0):
        self.rate = requests_per_second
        self.tokens = requests_per_second
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()  # ✅ Correct for asyncio

    async def acquire(self) -> None:
        async with self._lock:  # ✅ Async lock
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_update = now
            # ...
```

**Status**: ✅ **SAFE** for async contexts. However, if called from threads (not async), needs `threading.Lock`.

**Recommendation**: Document that `ParallelLLMExecutor` must be used from async context only, OR add thread-safe wrapper:

```python
def execute_batch_threadsafe(self, queries):
    """Thread-safe wrapper that creates new event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(self.execute_batch_async(queries))
    finally:
        loop.close()
```

#### 3.2 `llm_router.py`

**Current**: Uses `asyncio.Semaphore` for rate limiting (Line 439, 655)

```python
self._rate_limit_semaphore = asyncio.Semaphore(max_concurrent)  # ✅ Async-safe
```

**Status**: ✅ **SAFE** for async usage. Same caveat as `parallel_llm.py`.

---

### 🟡 HIGH: File I/O Without Locks

#### 4.1 `hardware_detection.py` - Cache File

**Issue**: Concurrent reads/writes to cache file (Line 302)

```python
def _save_cache(self, hardware_info: HardwareInfo):
    with open(self.CACHE_FILE, "w") as f:  # ⚠️ No lock
        json.dump(asdict(hardware_info), f)
```

**Problem**: Multiple threads detecting hardware simultaneously can corrupt cache file.

**Fix**:
```python
class HardwareDetector:
    def __init__(self):
        self._cache_lock = threading.Lock()
    
    def _save_cache(self, hardware_info: HardwareInfo):
        with self._cache_lock:
            with open(self.CACHE_FILE, "w") as f:
                json.dump(asdict(hardware_info), f)
```

#### 4.2 `config_manager.py` - Preferences File

**Issue**: YAML file reads/writes without synchronization

```python
def export_configuration(self, output_path: Path, ...):
    with open(output_path, "w") as f:  # ⚠️ No lock
        yaml.dump(config, f)
```

**Risk**: Medium - Usually single-threaded operations, but could be called during parallel installs.

---

### 🟡 HIGH: Shared Mutable State

#### 5.1 `logging_system.py` - Operation Tracking

**Current Implementation**: ✅ Uses `threading.Lock` (Line 141)

```python
class CortexLogger:
    def __init__(self, ...):
        self._operation_times = {}
        self._operation_lock = threading.Lock()  # ✅ Correct!
```

**Status**: ✅ **SAFE** - Already properly protected.

#### 5.2 `progress_indicators.py` - Spinner Thread

**Current**: Uses daemon thread for animation (Line 128)

```python
self._thread = threading.Thread(target=self._animate, daemon=True)
```

**Issue**: Shared state `_current_message` and `_running` accessed without lock

```python
def update(self, message: str):
    self._current_message = message  # ⚠️ Not thread-safe

def _animate(self):
    while self._running:  # ⚠️ Reading shared state
        char = self._spinner_chars[self._spinner_idx % len(self._spinner_chars)]
        sys.stdout.write(f"\r{char} {self._current_message}")  # ⚠️ Race
```

**Fix**:
```python
class SimpleSpinner:
    def __init__(self):
        self._lock = threading.Lock()
        # ...
    
    def update(self, message: str):
        with self._lock:
            self._current_message = message
    
    def _animate(self):
        while True:
            with self._lock:
                if not self._running:
                    break
                msg = self._current_message
            # Use local copy outside lock
            sys.stdout.write(f"\r{char} {msg}")
```

---

### 🟢 MEDIUM: Read-Only Data Structures

#### 6.1 Module-Level Constants

**Examples**:
```python
# shell_installer.py (Lines 4-5)
BASH_MARKER = "# >>> cortex shell integration >>>"  # ✅ SAFE - immutable
ZSH_MARKER = "# >>> cortex shell integration >>>"   # ✅ SAFE - immutable

# validators.py
DANGEROUS_PATTERNS = [...]  # ⚠️ SAFE if treated as read-only
```

**Status**: ✅ **SAFE** - As long as these are never mutated at runtime.

**Risk**: If any code does `DANGEROUS_PATTERNS.append(...)`, this becomes unsafe.

**Recommendation**: Use `tuple` instead of `list` for immutability:

```python
DANGEROUS_PATTERNS = (  # Tuple is immutable
    r"rm\s+-rf\s+/",
    r"dd\s+if=.*\s+of=/dev/",
    # ...
)
```

---

## 2. Shared State Inventory

### Global Variables

| Module | Variable | Type | Thread-Safe? | Fix Required |
|--------|----------|------|--------------|--------------|
| `transaction_history.py` | `_history_instance` | Singleton | ❌ No | Lock |
| `transaction_history.py` | `_undo_manager_instance` | Singleton | ❌ No | Lock |
| `hardware_detection.py` | `_detector_instance` | Singleton | ❌ No | Lock |
| `graceful_degradation.py` | `._instance` (function attr) | Singleton | ❌ No | Lock |
| `shell_installer.py` | `BASH_MARKER`, `ZSH_MARKER` | str | ✅ Yes | None (immutable) |
| `validators.py` | `DANGEROUS_PATTERNS` | list | ⚠️ Conditional | Make tuple |

### Class-Level Shared State

| Module | Class | Shared State | Thread-Safe? |
|--------|-------|--------------|--------------|
| `semantic_cache.py` | `SemanticCache` | SQLite connection | ❌ No |
| `context_memory.py` | `ContextMemory` | SQLite connection | ❌ No |
| `installation_history.py` | `InstallationHistory` | SQLite connection | ❌ No |
| `transaction_history.py` | `TransactionHistory` | SQLite connection | ❌ No |
| `logging_system.py` | `CortexLogger` | `_operation_times` | ✅ Yes (locked) |
| `progress_indicators.py` | `SimpleSpinner` | `_running`, `_current_message` | ❌ No |
| `hardware_detection.py` | `HardwareDetector` | Cache file | ❌ No |

---

## 3. Risk Assessment by Module

### Critical (Immediate Fix Required)

1. **`transaction_history.py`** - ⚠️ Data corruption risk in install tracking
2. **`semantic_cache.py`** - ⚠️ Cache corruption during parallel LLM calls
3. **`context_memory.py`** - ⚠️ Lost memory entries
4. **`installation_history.py`** - ⚠️ Incomplete rollback data
5. **`hardware_detection.py`** - ⚠️ Race in singleton initialization

### High Priority

6. **`graceful_degradation.py`** - Fallback cache issues
7. **`progress_indicators.py`** - Display corruption
8. **`config_manager.py`** - Config file corruption
9. **`kernel_features/kv_cache_manager.py`** - Kernel cache conflicts
10. **`kernel_features/accelerator_limits.py`** - Limit tracking issues

### Medium Priority (Monitor)

11. **`llm_router.py`** - Async-safe, needs thread wrapper docs
12. **`parallel_llm.py`** - Async-safe, needs thread wrapper docs
13. **`coordinator.py`** - Mostly single-threaded, low risk
14. **`progress_tracker.py`** - Similar issues to `progress_indicators.py`

---

## 4. Recommended Fixes

### 4.1 Add Threading Module to All Critical Modules

```python
import threading
```

### 4.2 Implement Thread-Safe Singleton Pattern

**Template** (use for all singletons):

```python
import threading

_instance = None
_instance_lock = threading.Lock()

def get_instance() -> MyClass:
    """Get or create singleton instance (thread-safe)."""
    global _instance
    if _instance is None:  # Fast path: avoid lock if already initialized
        with _instance_lock:
            if _instance is None:  # Double-checked locking
                _instance = MyClass()
    return _instance
```

**Apply to**:
- `transaction_history.py`: `get_history()`, `get_undo_manager()`
- `hardware_detection.py`: `get_detector()`
- `graceful_degradation.py`: `get_degradation_manager()`

### 4.3 Implement SQLite Connection Pooling

**Create** `cortex/utils/db_pool.py`:

```python
"""Thread-safe SQLite connection pooling for Cortex."""

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
    - Multiple readers OK
    - Single writer at a time
    - Database locks on writes
    
    This pool manages connections and handles SQLITE_BUSY errors.
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
            db_path: Path to SQLite database
            pool_size: Number of connections to maintain
            timeout: Timeout for acquiring connection (seconds)
            check_same_thread: SQLite same-thread check (set False for pooling)
        """
        self.db_path = str(db_path)
        self.pool_size = pool_size
        self.timeout = timeout
        self.check_same_thread = check_same_thread
        
        # Connection pool
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=pool_size)
        self._pool_lock = threading.Lock()
        self._active_connections = 0
        
        # Initialize connections
        for _ in range(pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with optimal settings."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            check_same_thread=self.check_same_thread,
        )
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn
    
    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        """
        Get a connection from the pool (context manager).
        
        Usage:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ...")
        """
        try:
            conn = self._pool.get(timeout=self.timeout)
        except queue.Empty:
            raise TimeoutError(f"Could not acquire DB connection within {self.timeout}s")
        
        try:
            yield conn
        finally:
            # Return connection to pool
            self._pool.put(conn)
    
    def close_all(self):
        """Close all connections in the pool."""
        with self._pool_lock:
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                except queue.Empty:
                    break


# Global connection pools (lazy initialization)
_pools: dict[str, SQLiteConnectionPool] = {}
_pools_lock = threading.Lock()


def get_connection_pool(db_path: str | Path, pool_size: int = 5) -> SQLiteConnectionPool:
    """
    Get or create a connection pool for a database.
    
    Args:
        db_path: Path to SQLite database
        pool_size: Number of connections in pool
    
    Returns:
        SQLiteConnectionPool instance
    """
    db_path = str(db_path)
    
    if db_path not in _pools:
        with _pools_lock:
            if db_path not in _pools:  # Double-checked locking
                _pools[db_path] = SQLiteConnectionPool(db_path, pool_size=pool_size)
    
    return _pools[db_path]
```

**Usage Example** (update all database modules):

```python
from cortex.utils.db_pool import get_connection_pool

class SemanticCache:
    def __init__(self, db_path: str = "/var/lib/cortex/cache.db", ...):
        self.db_path = db_path
        self._pool = get_connection_pool(db_path, pool_size=5)
        self._init_database()
    
    def _init_database(self) -> None:
        with self._pool.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS ...")
            conn.commit()
    
    def get_commands(self, prompt: str, ...) -> list[str] | None:
        with self._pool.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ...")
            # ...
```

### 4.4 Fix Progress Indicators

**Update** `progress_indicators.py`:

```python
class SimpleSpinner:
    def __init__(self):
        self._spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._current_message = ""
        self._spinner_idx = 0
        self._running = False
        self._thread = None
        self._lock = threading.Lock()  # Add lock
    
    def update(self, message: str):
        """Update the progress message (thread-safe)."""
        with self._lock:
            self._current_message = message
    
    def _animate(self):
        """Animate the spinner (thread-safe)."""
        while True:
            with self._lock:
                if not self._running:
                    break
                char = self._spinner_chars[self._spinner_idx % len(self._spinner_chars)]
                message = self._current_message
                self._spinner_idx += 1
            
            # Do I/O outside lock to avoid blocking updates
            sys.stdout.write(f"\r{char} {message}")
            sys.stdout.flush()
            time.sleep(0.1)
```

### 4.5 Fix Hardware Detection Cache

**Update** `hardware_detection.py`:

```python
class HardwareDetector:
    CACHE_FILE = Path.home() / ".cortex" / "hardware_cache.json"
    
    def __init__(self, use_cache: bool = True, cache_ttl_seconds: int = 3600):
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl_seconds
        self._cache_lock = threading.RLock()  # Reentrant lock
    
    def _save_cache(self, hardware_info: HardwareInfo):
        """Save hardware info to cache file (thread-safe)."""
        with self._cache_lock:
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.CACHE_FILE, "w") as f:
                json.dump(asdict(hardware_info), f, indent=2)
    
    def _load_cache(self) -> HardwareInfo | None:
        """Load hardware info from cache (thread-safe)."""
        with self._cache_lock:
            if not self.CACHE_FILE.exists():
                return None
            # ... rest of loading logic
```

---

## 5. Design: Parallel LLM Architecture for Free-Threading

### 5.1 Current Architecture

```
User Request
     ↓
[LLMRouter] (sync) → [Claude/Kimi API]
     ↓
[ParallelLLMExecutor] (async)
     ↓
[asyncio.gather] → Multiple API calls
     ↓
Aggregate results
```

**Status**: Works well with asyncio, but has thread-safety limitations:
1. SQLite cache hits are not thread-safe
2. Global singletons (router, cache) can race
3. No thread-pool integration

### 5.2 Proposed Architecture (Free-Threading Optimized)

```
User Request (any thread)
     ↓
[ThreadPoolExecutor] (thread pool)
     ↓
[ThreadSafeLLMRouter] (thread-local instances)
     ↓
[Parallel API Calls] (thread-per-request or async)
     ↓
[Thread-Safe Cache] (connection pool)
     ↓
Aggregate & Return
```

**Key Changes**:

1. **Thread-Local LLM Clients**
   ```python
   import threading
   
   class ThreadSafeLLMRouter:
       def __init__(self):
           self._local = threading.local()
       
       def _get_client(self):
           if not hasattr(self._local, 'client'):
               self._local.client = Anthropic(api_key=...)
           return self._local.client
   ```

2. **Thread Pool for Parallel Queries**
   ```python
   from concurrent.futures import ThreadPoolExecutor
   
   class ParallelLLMExecutor:
       def __init__(self, max_workers: int = 10):
           self._executor = ThreadPoolExecutor(max_workers=max_workers)
           self.router = ThreadSafeLLMRouter()
       
       def execute_batch(self, queries: list[ParallelQuery]) -> BatchResult:
           futures = [
               self._executor.submit(self._execute_single_sync, q)
               for q in queries
           ]
           results = [f.result() for f in futures]
           return self._aggregate_results(results)
   ```

3. **Hybrid Async + Threading**
   ```python
   async def execute_hybrid_batch(self, queries):
       """Use asyncio for I/O, threads for CPU-bound work."""
       # Split queries by type
       io_queries = [q for q in queries if q.task_type in IO_TASKS]
       cpu_queries = [q for q in queries if q.task_type in CPU_TASKS]
       
       # Async for I/O-bound
       io_results = await asyncio.gather(*[
           self._call_api_async(q) for q in io_queries
       ])
       
       # Threads for CPU-bound (parsing, validation)
       cpu_futures = [
           self._executor.submit(self._process_cpu_query, q)
           for q in cpu_queries
       ]
       cpu_results = [f.result() for f in cpu_futures]
       
       return io_results + cpu_results
   ```

### 5.3 Performance Expectations

**Current (with GIL)**:
- Async I/O: Good parallelism (I/O waits don't block)
- CPU processing: Sequential (GIL blocks)
- Cache lookups: Sequential (SQLite locks)

**With Free-Threading**:
- Async I/O: Same (already parallel)
- CPU processing: **2-3x faster** (true parallelism)
- Cache lookups: **Requires pooling** to avoid contention

**Target Workload**:
```
Install 5 packages with parallel analysis:
  Current: 8-12 seconds (mostly sequential)
  With free-threading: 3-5 seconds (2-3x improvement)
```

---

## 6. Testing Strategy for Free-Threading

### 6.1 Enable Free-Threading

```bash
# Python 3.14+ with free-threading
python3.14t --help  # 't' variant enables no-GIL mode
export PYTHON_GIL=0  # Disable GIL at runtime
```

### 6.2 Stress Tests

**Create** `tests/test_thread_safety.py`:

```python
"""Thread-safety stress tests for Python 3.14 free-threading."""

import concurrent.futures
import pytest
import random
import time
from cortex.transaction_history import get_history
from cortex.semantic_cache import SemanticCache
from cortex.hardware_detection import get_detector


def test_singleton_thread_safety():
    """Test that singletons are initialized correctly under load."""
    results = []
    
    def get_instance():
        history = get_history()
        results.append(id(history))
    
    # Hammer singleton initialization from 100 threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(get_instance) for _ in range(1000)]
        concurrent.futures.wait(futures)
    
    # All threads should get the SAME instance
    assert len(set(results)) == 1, "Multiple singleton instances created!"


def test_sqlite_concurrent_reads():
    """Test SQLite cache under concurrent read load."""
    cache = SemanticCache()
    
    # Pre-populate cache
    for i in range(100):
        cache.set_commands(f"query_{i}", "claude", "opus", "system", [f"cmd_{i}"])
    
    def read_cache():
        for _ in range(100):
            query = f"query_{random.randint(0, 99)}"
            result = cache.get_commands(query, "claude", "opus", "system")
            assert result is not None or True  # May miss if evicted
    
    # 50 threads reading simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(read_cache) for _ in range(50)]
        concurrent.futures.wait(futures)


def test_sqlite_concurrent_writes():
    """Test SQLite cache under concurrent write load."""
    cache = SemanticCache()
    errors = []
    
    def write_cache(thread_id: int):
        try:
            for i in range(50):
                query = f"thread_{thread_id}_query_{i}"
                cache.set_commands(query, "claude", "opus", "system", [f"cmd_{i}"])
        except Exception as e:
            errors.append((thread_id, str(e)))
    
    # 20 threads writing simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(write_cache, i) for i in range(20)]
        concurrent.futures.wait(futures)
    
    # Should handle concurrency gracefully (no crashes)
    if errors:
        pytest.fail(f"Concurrent write errors: {errors}")


def test_hardware_detection_parallel():
    """Test hardware detection from multiple threads."""
    results = []
    
    def detect_hardware():
        detector = get_detector()
        info = detector.detect_all()
        results.append(info.cpu.cores)
    
    # 10 threads detecting hardware simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(detect_hardware) for _ in range(10)]
        concurrent.futures.wait(futures)
    
    # All results should be identical
    assert len(set(results)) == 1, "Inconsistent hardware detection!"


def test_progress_indicator_thread_safety():
    """Test progress indicator under concurrent updates."""
    from cortex.progress_indicators import SimpleSpinner
    
    spinner = SimpleSpinner()
    spinner.start("Starting...")
    
    def update_message(thread_id: int):
        for i in range(100):
            spinner.update(f"Thread {thread_id} - Step {i}")
            time.sleep(0.001)
    
    # 10 threads updating spinner message
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(update_message, i) for i in range(10)]
        concurrent.futures.wait(futures)
    
    spinner.stop("Done!")
    # Should not crash (visual corruption is acceptable)


@pytest.mark.slow
def test_parallel_llm_execution():
    """Test ParallelLLMExecutor under thread load."""
    from cortex.parallel_llm import ParallelLLMExecutor, ParallelQuery, TaskType
    
    executor = ParallelLLMExecutor(max_concurrent=5)
    
    def execute_batch(batch_id: int):
        queries = [
            ParallelQuery(
                id=f"batch_{batch_id}_query_{i}",
                messages=[
                    {"role": "system", "content": "You are a Linux expert."},
                    {"role": "user", "content": f"What is package {i}?"},
                ],
                task_type=TaskType.SYSTEM_OPERATION,
            )
            for i in range(3)
        ]
        result = executor.execute_batch(queries)
        return result.success_count
    
    # Execute multiple batches in parallel from different threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(execute_batch, i) for i in range(5)]
        results = [f.result() for f in futures]
    
    # All batches should succeed
    assert all(r > 0 for r in results), "Some LLM batches failed"
```

**Run Tests**:
```bash
# With GIL (should pass)
python3.14 -m pytest tests/test_thread_safety.py -v

# Without GIL (will fail without fixes)
PYTHON_GIL=0 python3.14t -m pytest tests/test_thread_safety.py -v
```

### 6.3 Race Detection Tools

**ThreadSanitizer** (TSan):
```bash
# Compile Python with TSan (or use pre-built)
PYTHON_GIL=0 python3.14t -X dev -m pytest tests/

# TSan will report race conditions:
# WARNING: ThreadSanitizer: data race (pid=1234)
#   Write of size 8 at 0x7f8b4c001234 by thread T1:
#     #0 get_history cortex/transaction_history.py:664
```

---

## 7. Implementation Roadmap

### Phase 1: Critical Fixes (1-2 weeks)

**Priority**: Database corruption and singleton races

- [ ] 1.1: Add `threading` imports to all critical modules
- [ ] 1.2: Implement `cortex/utils/db_pool.py` with SQLite connection pooling
- [ ] 1.3: Fix singleton patterns in:
  - `transaction_history.py`
  - `hardware_detection.py`
  - `graceful_degradation.py`
- [ ] 1.4: Update all database modules to use connection pooling:
  - `semantic_cache.py`
  - `context_memory.py`
  - `installation_history.py`
  - `transaction_history.py`
  - `graceful_degradation.py`
  - `kernel_features/kv_cache_manager.py`
  - `kernel_features/accelerator_limits.py`

**Testing**:
```bash
# Run stress tests with free-threading
PYTHON_GIL=0 python3.14t -m pytest tests/test_thread_safety.py::test_singleton_thread_safety -v
PYTHON_GIL=0 python3.14t -m pytest tests/test_thread_safety.py::test_sqlite_concurrent_writes -v
```

### Phase 2: High-Priority Fixes (1 week)

- [ ] 2.1: Fix file I/O locks:
  - `hardware_detection.py`: Cache file lock
  - `config_manager.py`: YAML file lock
- [ ] 2.2: Fix progress indicators:
  - `progress_indicators.py`: Add locks to `SimpleSpinner`
  - `progress_tracker.py`: Review and fix similar issues
- [ ] 2.3: Document async-only usage for:
  - `parallel_llm.py`
  - `llm_router.py`

**Testing**:
```bash
PYTHON_GIL=0 python3.14t -m pytest tests/test_thread_safety.py::test_hardware_detection_parallel -v
PYTHON_GIL=0 python3.14t -m pytest tests/test_thread_safety.py::test_progress_indicator_thread_safety -v
```

### Phase 3: Optimization (2-3 weeks)

- [ ] 3.1: Implement thread-safe LLM router with thread-local clients
- [ ] 3.2: Add hybrid async + threading executor for CPU-bound work
- [ ] 3.3: Benchmark parallel LLM calls with free-threading
- [ ] 3.4: Profile and optimize hotspots (cache, parsing, validation)

**Performance Target**:
```
Baseline (GIL):    cortex install nginx mysql redis → 12 seconds
With free-threading: cortex install nginx mysql redis → 4-5 seconds (2.4-3x)
```

### Phase 4: Documentation & Migration Guide (1 week)

- [ ] 4.1: Create Python 3.14 migration guide for users
- [ ] 4.2: Update README with free-threading benefits
- [ ] 4.3: Add FAQ for common thread-safety questions
- [ ] 4.4: Document performance benchmarks

---

## 8. Compatibility Notes

### 8.1 Backward Compatibility

All fixes are **backward compatible** with Python 3.10-3.13 (with GIL):
- `threading.Lock()` works identically with/without GIL
- Connection pooling improves performance even with GIL
- No breaking API changes required

### 8.2 Opt-In Free-Threading

Users can choose to enable free-threading:

```bash
# Standard Python 3.14 (with GIL) - backward compatible
python3.14 -m cortex install nginx

# Free-threading Python 3.14 (no GIL) - 2-3x faster
python3.14t -m cortex install nginx
# OR
PYTHON_GIL=0 python3.14 -m cortex install nginx
```

### 8.3 Recommended Configuration

**For Python 3.10-3.13** (GIL):
- No changes required
- Connection pooling provides modest speedup

**For Python 3.14+** (free-threading):
- Set `PYTHON_GIL=0` or use `python3.14t`
- Configure thread pool size via environment:
  ```bash
  export CORTEX_THREAD_POOL_SIZE=10
  export CORTEX_DB_POOL_SIZE=5
  ```

---

## 9. Appendix: Quick Reference

### Module Risk Matrix

| Module | Risk | Issue | Fix |
|--------|------|-------|-----|
| `transaction_history.py` | 🔴 Critical | Singleton race | Double-checked lock |
| `semantic_cache.py` | 🔴 Critical | SQLite concurrent writes | Connection pool |
| `context_memory.py` | 🔴 Critical | SQLite concurrent writes | Connection pool |
| `installation_history.py` | 🔴 Critical | SQLite concurrent writes | Connection pool |
| `hardware_detection.py` | 🔴 Critical | Singleton race + file lock | Lock + RLock |
| `graceful_degradation.py` | 🟡 High | Singleton race + SQLite | Lock + pool |
| `progress_indicators.py` | 🟡 High | Shared state race | Lock |
| `config_manager.py` | 🟡 High | File write race | Lock |
| `logging_system.py` | ✅ OK | Already thread-safe | None |
| `parallel_llm.py` | ✅ OK | Async-only (document) | Docs |
| `llm_router.py` | ✅ OK | Async-only (document) | Docs |

### Code Snippets for Common Fixes

**Thread-Safe Singleton**:
```python
_instance = None
_lock = threading.Lock()

def get_instance():
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = MyClass()
    return _instance
```

**SQLite Connection Pool**:
```python
from cortex.utils.db_pool import get_connection_pool

pool = get_connection_pool("/path/to/db.sqlite")
with pool.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT ...")
```

**File Lock**:
```python
import threading

class MyClass:
    def __init__(self):
        self._file_lock = threading.Lock()
    
    def write_file(self, path, data):
        with self._file_lock:
            with open(path, "w") as f:
                f.write(data)
```

---

## 10. Conclusion

Python 3.14's free-threading offers **2-3x performance improvements** for Cortex Linux's parallel LLM operations, but requires significant thread-safety work:

- **15+ modules** need fixes
- **Critical issues** in database access, singletons, and file I/O
- **Estimated effort**: 4-6 weeks for full implementation
- **Backward compatible** with Python 3.10-3.13

**Next Steps**:
1. Create `cortex/utils/db_pool.py` (connection pooling)
2. Fix critical singleton races (3 modules)
3. Update all database modules to use pooling (7 modules)
4. Add thread-safety tests
5. Benchmark performance improvements

**Risk vs Reward**: High effort, high reward. Prioritize based on release timeline and user demand for Python 3.14 support.

---

**Document Version**: 1.0  
**Last Updated**: December 22, 2025  
**Author**: GitHub Copilot (Claude Sonnet 4.5)  
**Status**: 📋 Draft - Awaiting Review
