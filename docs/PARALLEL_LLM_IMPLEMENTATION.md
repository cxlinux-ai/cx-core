# Parallel LLM Calls Implementation

**Issue:** [#276](https://github.com/cortexlinux/cortex/issues/276)  
**Author:** Cortex Linux Team  
**Status:** Implemented

## Overview

This implementation adds parallel/concurrent LLM API call support to Cortex Linux, enabling 2-3x speedup for batch operations.

## Problem Solved

The previous architecture made sequential LLM calls, which was slow for:
- Multi-package queries
- Parallel error diagnosis
- Concurrent hardware configuration checks

## Solution

New module `cortex/parallel_llm.py` provides:

### Core Components

| Component | Purpose |
|-----------|---------|
| `ParallelLLMExecutor` | Main executor for concurrent API calls |
| `RateLimiter` | Token bucket rate limiting to avoid API throttling |
| `ParallelQuery` | Dataclass representing a single query |
| `ParallelResult` | Result of a single parallel query |
| `BatchResult` | Aggregated results with statistics |

### Features

1. **Concurrent Execution** - Uses `asyncio` with semaphore-based concurrency control
2. **Rate Limiting** - Token bucket algorithm prevents API rate limit errors
3. **Automatic Retries** - Configurable retry with exponential backoff
4. **Progress Callbacks** - Optional per-query completion callbacks
5. **Statistics Tracking** - Total tokens, cost, success/failure counts

## Usage Examples

### Basic Batch Execution

```python
from cortex.parallel_llm import ParallelLLMExecutor, ParallelQuery
from cortex.llm_router import TaskType

executor = ParallelLLMExecutor(max_concurrent=5, requests_per_second=10.0)

queries = [
    ParallelQuery(
        id="q1",
        messages=[{"role": "user", "content": "Analyze nginx package"}],
        task_type=TaskType.SYSTEM_OPERATION,
    ),
    ParallelQuery(
        id="q2", 
        messages=[{"role": "user", "content": "Analyze redis package"}],
        task_type=TaskType.SYSTEM_OPERATION,
    ),
]

result = executor.execute_batch(queries)
print(f"Completed: {result.success_count}/{len(queries)}")
print(f"Total cost: ${result.total_cost:.4f}")
```

### Multi-Package Analysis

```python
from cortex.parallel_llm import ParallelLLMExecutor, create_package_queries

packages = ["nginx", "postgresql", "redis", "memcached", "mysql-server"]
queries = create_package_queries(packages)

executor = ParallelLLMExecutor()
result = executor.execute_batch(queries)

for r in result.successful_responses():
    print(r.content[:100])
```

### Async Usage

```python
import asyncio
from cortex.parallel_llm import ParallelLLMExecutor, create_hardware_check_queries

async def analyze_hardware():
    executor = ParallelLLMExecutor()
    queries = create_hardware_check_queries(["GPU", "CPU", "RAM", "Storage"])
    
    result = await executor.execute_batch_async(queries)
    return result

result = asyncio.run(analyze_hardware())
```

### With Progress Callback

```python
from cortex.parallel_llm import ParallelLLMExecutor, ParallelQuery

def on_complete(result):
    status = "✓" if result.success else "✗"
    print(f"{status} {result.query_id} completed in {result.execution_time:.2f}s")

executor = ParallelLLMExecutor()
# Use execute_with_callback_async for progress tracking
```

## Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_concurrent` | 5 | Maximum simultaneous API calls |
| `requests_per_second` | 5.0 | Rate limit for API calls |
| `retry_failed` | True | Retry failed requests |
| `max_retries` | 2 | Maximum retry attempts |

## Helper Functions

- `create_package_queries(packages)` - Create queries for multiple packages
- `create_error_diagnosis_queries(errors)` - Create queries for parallel error diagnosis
- `create_hardware_check_queries(checks)` - Create queries for hardware config checks

## Performance

Typical speedup for 5 concurrent calls:
- Sequential: 5 × 1s = 5s
- Parallel: ~1.2s (accounting for rate limiting overhead)

**Speedup: ~4x for 5 queries**

## Files Changed

- `cortex/parallel_llm.py` - New module with parallel execution support
- `tests/test_parallel_llm.py` - Unit tests

## Testing

```bash
pytest tests/test_parallel_llm.py -v
```

## Future Enhancements

- Integration with Python 3.13 free-threading (no-GIL)
- Adaptive rate limiting based on provider response headers
- Priority queue for urgent queries
