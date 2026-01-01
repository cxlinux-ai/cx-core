# Python 3.14 Free-Threading - Developer Quick Reference

**Purpose**: Quick checklist for implementing thread-safety fixes  
**Target**: Developers working on Cortex Python 3.14 migration

---

## 🚨 Critical Patterns to Fix

### 1. Singleton Pattern (3 occurrences)

**Files**: 
- `cortex/transaction_history.py` (lines 656-672)
- `cortex/hardware_detection.py` (lines 635-642)
- `cortex/graceful_degradation.py` (line 503-505)

**Before** ❌:
```python
_instance = None

def get_instance():
    global _instance
    if _instance is None:
        _instance = MyClass()  # RACE CONDITION
    return _instance
```

**After** ✅:
```python
import threading

_instance = None
_lock = threading.Lock()

def get_instance():
    global _instance
    if _instance is None:  # Fast path (no lock)
        with _lock:
            if _instance is None:  # Double-check inside lock
                _instance = MyClass()
    return _instance
```

---

### 2. SQLite Database Access (7 modules)

**Files**:
- `cortex/semantic_cache.py`
- `cortex/context_memory.py`
- `cortex/installation_history.py`
- `cortex/transaction_history.py`
- `cortex/graceful_degradation.py`
- `cortex/kernel_features/kv_cache_manager.py`
- `cortex/kernel_features/accelerator_limits.py`

**Before** ❌:
```python
def get_data(self):
    conn = sqlite3.connect(self.db_path)  # New connection every call
    cur = conn.cursor()
    cur.execute("SELECT ...")
    result = cur.fetchall()
    conn.close()
    return result
```

**After** ✅:
```python
from cortex.utils.db_pool import get_connection_pool

class MyClass:
    def __init__(self):
        self._pool = get_connection_pool(self.db_path, pool_size=5)
    
    def get_data(self):
        with self._pool.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ...")
            return cur.fetchall()
```

---

### 3. File I/O (3 modules)

**Files**:
- `cortex/hardware_detection.py` (line 302)
- `cortex/config_manager.py` (YAML writes)
- `cortex/shell_installer.py` (RC file writes)

**Before** ❌:
```python
def save_file(self, data):
    with open(self.file_path, "w") as f:  # RACE CONDITION
        json.dump(data, f)
```

**After** ✅:
```python
import threading

class MyClass:
    def __init__(self):
        self._file_lock = threading.Lock()
    
    def save_file(self, data):
        with self._file_lock:
            with open(self.file_path, "w") as f:
                json.dump(data, f)
```

---

### 4. Shared Mutable State

**File**: `cortex/progress_indicators.py` (lines 120-160)

**Before** ❌:
```python
class SimpleSpinner:
    def __init__(self):
        self._running = False
        self._current_message = ""
    
    def update(self, message: str):
        self._current_message = message  # RACE
    
    def _animate(self):
        while self._running:  # RACE
            sys.stdout.write(f"\r{self._current_message}")
```

**After** ✅:
```python
import threading

class SimpleSpinner:
    def __init__(self):
        self._running = False
        self._current_message = ""
        self._lock = threading.Lock()
    
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
            sys.stdout.write(f"\r{msg}")
```

---

## 📋 Implementation Checklist

### Phase 1: Create Utilities (Week 1)

- [ ] Create `cortex/utils/db_pool.py`
  ```python
  """SQLite connection pooling for thread-safe database access."""
  import queue
  import sqlite3
  import threading
  from contextlib import contextmanager
  
  class SQLiteConnectionPool:
      def __init__(self, db_path: str, pool_size: int = 5):
          self.db_path = db_path
          self._pool = queue.Queue(maxsize=pool_size)
          for _ in range(pool_size):
              conn = sqlite3.connect(db_path, check_same_thread=False)
              conn.execute("PRAGMA journal_mode=WAL")
              self._pool.put(conn)
      
      @contextmanager
      def get_connection(self):
          conn = self._pool.get(timeout=5.0)
          try:
              yield conn
          finally:
              self._pool.put(conn)
  
  _pools = {}
  _pools_lock = threading.Lock()
  
  def get_connection_pool(db_path: str, pool_size: int = 5):
      if db_path not in _pools:
          with _pools_lock:
              if db_path not in _pools:
                  _pools[db_path] = SQLiteConnectionPool(db_path, pool_size)
      return _pools[db_path]
  ```

- [ ] Create `cortex/utils/thread_utils.py`
  ```python
  """Thread-safety utilities."""
  import threading
  
  def thread_safe_singleton(cls):
      """Decorator for thread-safe singleton pattern."""
      instances = {}
      lock = threading.Lock()
      
      def get_instance(*args, **kwargs):
          key = (cls, args, tuple(sorted(kwargs.items())))
          if key not in instances:
              with lock:
                  if key not in instances:
                      instances[key] = cls(*args, **kwargs)
          return instances[key]
      
      return get_instance
  ```

### Phase 2: Fix Critical Modules (Week 2)

- [ ] Fix `cortex/transaction_history.py`
  - [ ] Add lock to `get_history()`
  - [ ] Add lock to `get_undo_manager()`
  - [ ] Convert to use connection pool
  - [ ] Test with `tests/test_thread_safety.py::test_singleton_thread_safety`

- [ ] Fix `cortex/semantic_cache.py`
  - [ ] Convert to use connection pool
  - [ ] Test with `tests/test_thread_safety.py::test_sqlite_concurrent_writes`

- [ ] Fix `cortex/context_memory.py`
  - [ ] Convert to use connection pool
  - [ ] Test concurrent memory writes

- [ ] Fix `cortex/installation_history.py`
  - [ ] Convert to use connection pool
  - [ ] Test concurrent history writes

- [ ] Fix `cortex/hardware_detection.py`
  - [ ] Add lock to `get_detector()`
  - [ ] Add lock to `_save_cache()`
  - [ ] Test with `tests/test_thread_safety.py::test_hardware_detection_parallel`

### Phase 3: Fix High-Priority Modules (Week 3)

- [ ] Fix `cortex/graceful_degradation.py`
  - [ ] Fix singleton pattern
  - [ ] Convert to use connection pool

- [ ] Fix `cortex/progress_indicators.py`
  - [ ] Add locks to `SimpleSpinner`
  - [ ] Test with `tests/test_thread_safety.py::test_progress_indicator_thread_safety`

- [ ] Fix `cortex/config_manager.py`
  - [ ] Add file lock for YAML writes

- [ ] Fix `cortex/kernel_features/kv_cache_manager.py`
  - [ ] Convert to use connection pool

- [ ] Fix `cortex/kernel_features/accelerator_limits.py`
  - [ ] Convert to use connection pool

### Phase 4: Add Tests (Week 4)

- [ ] Create `tests/test_thread_safety.py`
  - [ ] `test_singleton_thread_safety()` - 100 threads
  - [ ] `test_sqlite_concurrent_reads()` - 50 threads reading
  - [ ] `test_sqlite_concurrent_writes()` - 20 threads writing
  - [ ] `test_hardware_detection_parallel()` - 10 threads
  - [ ] `test_progress_indicator_thread_safety()` - 10 threads
  - [ ] `test_parallel_llm_execution()` - 5 batches in parallel

- [ ] Run tests with GIL:
  ```bash
  python3.14 -m pytest tests/test_thread_safety.py -v
  ```

- [ ] Run tests without GIL:
  ```bash
  PYTHON_GIL=0 python3.14t -m pytest tests/test_thread_safety.py -v
  ```

### Phase 5: Optimize & Document (Week 5-6)

- [ ] Create `cortex/parallel_llm_threaded.py`
- [ ] Benchmark performance
- [ ] Write migration guide
- [ ] Update README

---

## 🧪 Testing Commands

### Quick Validation

```bash
# Test specific module thread-safety
PYTHON_GIL=0 python3.14t -c "
from cortex.transaction_history import get_history
import concurrent.futures

# Create 100 threads simultaneously
with concurrent.futures.ThreadPoolExecutor(100) as ex:
    instances = list(ex.map(lambda _: id(get_history()), range(1000)))

# All should be same instance
assert len(set(instances)) == 1, f'Multiple instances: {len(set(instances))}'
print('✅ Singleton thread-safe!')
"
```

### Full Test Suite

```bash
# With GIL (should pass after fixes)
python3.14 -m pytest tests/test_thread_safety.py -v

# Without GIL (stress test)
PYTHON_GIL=0 python3.14t -m pytest tests/test_thread_safety.py -v

# With ThreadSanitizer (race detection)
PYTHON_GIL=0 python3.14t -X dev -m pytest tests/test_thread_safety.py -v
```

### Benchmarking

```bash
# Baseline (with GIL)
python3.14 benchmarks/parallel_llm_bench.py
# Output: 18.2s for 5 packages

# Free-threading (without GIL)
PYTHON_GIL=0 python3.14t benchmarks/parallel_llm_bench.py
# Target: <10s for 5 packages (1.8x speedup)
```

---

## 🐛 Common Pitfalls

### 1. Lock Granularity

❌ **Too coarse** (holds lock too long):
```python
with self._lock:
    data = self._fetch_from_db()  # Slow I/O under lock
    result = self._process(data)  # CPU work under lock
    return result
```

✅ **Just right** (minimal critical section):
```python
with self._lock:
    data = self._fetch_from_db()

# Process outside lock
result = self._process(data)
return result
```

### 2. Deadlocks

❌ **Nested locks** (can deadlock):
```python
with lock_a:
    with lock_b:  # Thread 1
        ...

with lock_b:
    with lock_a:  # Thread 2 - DEADLOCK!
        ...
```

✅ **Single lock or ordered locks**:
```python
# Always acquire in same order
with lock_a:
    with lock_b:  # Both threads use same order
        ...
```

### 3. Forgetting to Return to Pool

❌ **Connection leak**:
```python
conn = self._pool.get()
cursor = conn.cursor()
if error:
    return  # Forgot to put back!
```

✅ **Use context manager**:
```python
with self._pool.get_connection() as conn:
    cursor = conn.cursor()
    # Automatically returned even on exception
```

---

## 📊 Performance Targets

| Module | Operation | Threads | Target Latency |
|--------|-----------|---------|----------------|
| `semantic_cache.py` | Cache hit | 50 | <5ms |
| `semantic_cache.py` | Cache write | 20 | <50ms |
| `transaction_history.py` | Record txn | 10 | <100ms |
| `hardware_detection.py` | Detect all | 10 | <200ms |
| `parallel_llm.py` | 5 packages | 5 | <10s |

---

## 🔍 Debugging

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# In modules
logger = logging.getLogger(__name__)
logger.debug(f"Thread {threading.current_thread().name}: Acquiring lock")
```

### Detect Deadlocks

```python
import sys
import threading

def dump_threads():
    """Dump all thread stacks (for debugging deadlocks)."""
    for thread_id, frame in sys._current_frames().items():
        thread = threading._active.get(thread_id)
        print(f"\nThread: {thread.name if thread else thread_id}")
        traceback.print_stack(frame)

# Call when hung
dump_threads()
```

### Profile Lock Contention

```bash
# Use py-spy to find lock hotspots
py-spy record -o profile.svg --native -- python3.14t -m cortex install nginx
```

---

## 📚 Additional Resources

- [Full Audit](PYTHON_314_THREAD_SAFETY_AUDIT.md) - Comprehensive analysis
- [Design Doc](PARALLEL_LLM_FREE_THREADING_DESIGN.md) - Architecture details
- [Summary](PYTHON_314_ANALYSIS_SUMMARY.md) - Executive summary
- [PEP 703](https://peps.python.org/pep-0703/) - Free-threading proposal

---

## ✅ Sign-Off Checklist

Before marking a module as "thread-safe":

- [ ] Added necessary locks/synchronization
- [ ] Converted to use connection pooling (if using SQLite)
- [ ] Wrote unit test for thread-safety
- [ ] Ran test with `PYTHON_GIL=0`
- [ ] Verified with ThreadSanitizer
- [ ] Updated module docstring to note "Thread-safe"
- [ ] Added to regression test suite

---

**Last Updated**: December 22, 2025  
**Status**: ✅ Ready for Use
