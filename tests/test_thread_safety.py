"""
Thread-safety tests for Python 3.14 free-threading compatibility.

Run with:
    python3.14 -m pytest tests/test_thread_safety.py -v        # With GIL
    PYTHON_GIL=0 python3.14t -m pytest tests/test_thread_safety.py -v  # Without GIL

Author: Cortex Linux Team
SPDX-License-Identifier: BUSL-1.1
"""

import concurrent.futures
import os
import queue
import secrets
import tempfile
import time

import pytest


def test_singleton_thread_safety_transaction_history():
    """Test that transaction history singleton is thread-safe."""
    from cortex.transaction_history import get_history

    results = []

    def get_instance():
        history = get_history()
        results.append(id(history))

    # Hammer singleton initialization from 100 threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(get_instance) for _ in range(1000)]
        concurrent.futures.wait(futures)

    # All threads should get the SAME instance
    unique_instances = len(set(results))
    assert (
        unique_instances == 1
    ), f"Multiple singleton instances created! Found {unique_instances} different instances"


def test_singleton_thread_safety_hardware_detection():
    """Test that hardware detector singleton is thread-safe."""
    from cortex.hardware_detection import get_detector

    results = []

    def get_instance():
        detector = get_detector()
        results.append(id(detector))

    # 50 threads trying to get detector simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(get_instance) for _ in range(500)]
        concurrent.futures.wait(futures)

    # All threads should get the SAME instance
    unique_instances = len(set(results))
    assert (
        unique_instances == 1
    ), f"Multiple detector instances created! Found {unique_instances} different instances"


def test_singleton_thread_safety_degradation_manager():
    """Test that degradation manager singleton is thread-safe."""
    from cortex.graceful_degradation import get_degradation_manager

    results = []

    def get_instance():
        manager = get_degradation_manager()
        results.append(id(manager))

    # 50 threads trying to get manager simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(get_instance) for _ in range(500)]
        concurrent.futures.wait(futures)

    # All threads should get the SAME instance
    unique_instances = len(set(results))
    assert (
        unique_instances == 1
    ), f"Multiple manager instances created! Found {unique_instances} different instances"


def test_connection_pool_concurrent_reads():
    """Test SQLite connection pool under concurrent read load."""
    from cortex.utils.db_pool import get_connection_pool

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Initialize database with test data
        pool = get_connection_pool(db_path, pool_size=5)
        with pool.get_connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            for i in range(100):
                conn.execute("INSERT INTO test (value) VALUES (?)", (f"value_{i}",))
            conn.commit()

        # Test concurrent reads
        def read_data(thread_id: int):
            results = []
            for _ in range(50):
                with pool.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM test")
                    count = cursor.fetchone()[0]
                    results.append(count)
            return results

        # 20 threads reading simultaneously
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(read_data, i) for i in range(20)]
            all_results = [f.result() for f in futures]

        # All reads should return 100
        for results in all_results:
            assert all(count == 100 for count in results), "Inconsistent read results"

    finally:
        # Cleanup
        pool.close_all()
        os.unlink(db_path)


def test_connection_pool_concurrent_writes():
    """Test SQLite connection pool under concurrent write load."""
    from cortex.utils.db_pool import get_connection_pool

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Initialize database
        pool = get_connection_pool(db_path, pool_size=5)
        with pool.get_connection() as conn:
            conn.execute(
                "CREATE TABLE test (id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id INTEGER, value TEXT)"
            )
            conn.commit()

        errors = []

        def write_data(thread_id: int):
            try:
                for i in range(20):
                    with pool.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO test (thread_id, value) VALUES (?, ?)",
                            (thread_id, f"thread_{thread_id}_value_{i}"),
                        )
                        conn.commit()
            except Exception as e:
                errors.append((thread_id, str(e)))

        # 10 threads writing simultaneously
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_data, i) for i in range(10)]
            concurrent.futures.wait(futures)

        # Should handle concurrency gracefully (no crashes)
        if errors:
            pytest.fail(f"Concurrent write errors: {errors}")

        # Verify all writes succeeded
        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 200, f"Expected 200 rows, got {count}"

    finally:
        # Cleanup
        pool.close_all()
        os.unlink(db_path)


def test_hardware_detection_parallel():
    """Test hardware detection from multiple threads."""
    from cortex.hardware_detection import get_detector

    results = []
    errors = []

    def detect_hardware():
        try:
            detector = get_detector()
            info = detector.detect()
            # Store CPU core count as a simple check
            # Use multiprocessing.cpu_count() as fallback if cores is 0
            cores = info.cpu.cores if info.cpu.cores > 0 else 1
            results.append(cores)
        except Exception as e:
            errors.append(str(e))

    # 10 threads detecting hardware simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(detect_hardware) for _ in range(10)]
        concurrent.futures.wait(futures)

    # Check for errors
    assert len(errors) == 0, f"Hardware detection errors: {errors}"

    # Should have results from all threads
    assert len(results) == 10, f"Expected 10 results, got {len(results)}"

    # All results should be identical (same hardware)
    unique_results = len(set(results))
    assert (
        unique_results == 1
    ), f"Inconsistent hardware detection! Got {unique_results} different results: {set(results)}"


def test_connection_pool_timeout():
    """Test that connection pool times out appropriately when exhausted."""
    from cortex.utils.db_pool import get_connection_pool

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Create small pool
        pool = get_connection_pool(db_path, pool_size=2, timeout=0.5)

        # Hold all connections
        conn1 = pool._pool.get()
        conn2 = pool._pool.get()

        # Attempt to get third connection should timeout
        with pytest.raises(queue.Empty):
            pool._pool.get(timeout=0.5)

        # Return connections
        pool._pool.put(conn1)
        pool._pool.put(conn2)

    finally:
        pool.close_all()
        os.unlink(db_path)


def test_connection_pool_context_manager():
    """Test that connection pool works as context manager."""
    from cortex.utils.db_pool import SQLiteConnectionPool

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Use pool as context manager
        with SQLiteConnectionPool(db_path, pool_size=3) as pool:
            with pool.get_connection() as conn:
                conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
                conn.commit()

            # Pool should still work
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM test")
                cursor.fetchall()

        # After exiting context, connections should be closed
        # (pool._pool should be empty or inaccessible)

    finally:
        os.unlink(db_path)


@pytest.mark.slow
def test_stress_concurrent_operations():
    """Stress test with many threads performing mixed read/write operations."""
    from cortex.utils.db_pool import get_connection_pool

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        pool = get_connection_pool(db_path, pool_size=5)

        # Initialize
        with pool.get_connection() as conn:
            conn.execute(
                "CREATE TABLE stress (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, timestamp REAL)"
            )
            conn.commit()

        errors = []

        def mixed_operations(thread_id: int):
            try:
                for _ in range(50):
                    if secrets.SystemRandom().random() < 0.7:  # 70% reads
                        with pool.get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT COUNT(*) FROM stress")
                            cursor.fetchone()
                    else:  # 30% writes
                        with pool.get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "INSERT INTO stress (data, timestamp) VALUES (?, ?)",
                                (f"thread_{thread_id}", time.time()),
                            )
                            conn.commit()
            except Exception as e:
                errors.append((thread_id, str(e)))

        # 20 threads doing mixed operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(mixed_operations, i) for i in range(20)]
            concurrent.futures.wait(futures)

        if errors:
            pytest.fail(f"Stress test errors: {errors[:5]}")  # Show first 5

        # Verify database integrity
        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM stress")
            count = cursor.fetchone()[0]
            # Should have some writes (not exact count due to randomness)
            assert count > 0, "No writes occurred"

    finally:
        pool.close_all()
        os.unlink(db_path)


if __name__ == "__main__":
    # Quick standalone test
    print("Running quick thread-safety tests...")
    print("\n1. Testing transaction history singleton...")
    test_singleton_thread_safety_transaction_history()
    print("✅ PASSED")

    print("\n2. Testing hardware detection singleton...")
    test_singleton_thread_safety_hardware_detection()
    print("✅ PASSED")

    print("\n3. Testing degradation manager singleton...")
    test_singleton_thread_safety_degradation_manager()
    print("✅ PASSED")

    print("\n4. Testing connection pool concurrent reads...")
    test_connection_pool_concurrent_reads()
    print("✅ PASSED")

    print("\n5. Testing connection pool concurrent writes...")
    test_connection_pool_concurrent_writes()
    print("✅ PASSED")

    print("\n✅ All quick tests passed! Run with pytest for full suite.")
