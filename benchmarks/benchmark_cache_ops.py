import time


def benchmark() -> float:
    """
    Benchmark cache-like dictionary operations.

    This simulates a hot-path workload similar to internal caching
    mechanisms used by Cortex, measuring insert and lookup performance.
    """
    cache: dict[str, str] = {}

    start = time.perf_counter()
    for i in range(100_000):
        key = f"prompt_{i}"
        cache[key] = f"response_{i}"
        _ = cache.get(key)
    return time.perf_counter() - start


if __name__ == "__main__":
    duration = benchmark()
    print(f"Cache-like Operations Time: {duration:.4f} seconds")
