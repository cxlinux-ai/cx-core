#!/usr/bin/env python3
"""
Unit tests for Parallel LLM Executor.

Tests concurrent API calls, rate limiting, batching, and response aggregation.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.llm_router import LLMProvider, LLMResponse, TaskType
from cortex.parallel_llm import (
    BatchResult,
    ParallelLLMExecutor,
    ParallelQuery,
    ParallelResult,
    RateLimiter,
    create_error_diagnosis_queries,
    create_hardware_check_queries,
    create_package_queries,
)


class TestParallelQuery(unittest.TestCase):
    """Test ParallelQuery dataclass."""

    def test_query_creation(self):
        """Test creating a basic query."""
        query = ParallelQuery(
            id="test_1",
            messages=[{"role": "user", "content": "Hello"}],
            task_type=TaskType.USER_CHAT,
        )
        self.assertEqual(query.id, "test_1")
        self.assertEqual(query.task_type, TaskType.USER_CHAT)
        self.assertEqual(query.temperature, 0.7)
        self.assertEqual(query.max_tokens, 4096)

    def test_query_with_metadata(self):
        """Test query with custom metadata."""
        query = ParallelQuery(
            id="pkg_nginx",
            messages=[{"role": "user", "content": "Analyze nginx"}],
            task_type=TaskType.SYSTEM_OPERATION,
            metadata={"package": "nginx", "priority": 1},
        )
        self.assertEqual(query.metadata["package"], "nginx")
        self.assertEqual(query.metadata["priority"], 1)


class TestParallelResult(unittest.TestCase):
    """Test ParallelResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful result."""
        response = LLMResponse(
            content="Test response",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4",
            tokens_used=100,
            cost_usd=0.001,
            latency_seconds=0.5,
        )
        result = ParallelResult(
            query_id="test_1",
            response=response,
            success=True,
            execution_time=0.5,
        )
        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(result.response.content, "Test response")

    def test_failed_result(self):
        """Test creating a failed result."""
        result = ParallelResult(
            query_id="test_2",
            response=None,
            error="API rate limit exceeded",
            success=False,
            execution_time=0.1,
        )
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIsNone(result.response)


class TestBatchResult(unittest.TestCase):
    """Test BatchResult aggregation."""

    def setUp(self):
        """Create sample results."""
        self.response1 = LLMResponse(
            content="Response 1",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4",
            tokens_used=100,
            cost_usd=0.001,
            latency_seconds=0.5,
        )
        self.response2 = LLMResponse(
            content="Response 2",
            provider=LLMProvider.KIMI_K2,
            model="kimi-k2-instruct",
            tokens_used=150,
            cost_usd=0.0005,
            latency_seconds=0.3,
        )

    def test_batch_statistics(self):
        """Test batch result statistics."""
        results = [
            ParallelResult(query_id="q1", response=self.response1, success=True),
            ParallelResult(query_id="q2", response=self.response2, success=True),
            ParallelResult(query_id="q3", response=None, error="Failed", success=False),
        ]
        batch = BatchResult(
            results=results,
            total_time=1.5,
            total_tokens=250,
            total_cost=0.0015,
            success_count=2,
            failure_count=1,
        )
        self.assertEqual(batch.success_count, 2)
        self.assertEqual(batch.failure_count, 1)
        self.assertEqual(batch.total_tokens, 250)

    def test_get_result_by_id(self):
        """Test retrieving result by query ID."""
        results = [
            ParallelResult(query_id="q1", response=self.response1, success=True),
            ParallelResult(query_id="q2", response=self.response2, success=True),
        ]
        batch = BatchResult(
            results=results,
            total_time=1.0,
            total_tokens=250,
            total_cost=0.0015,
            success_count=2,
            failure_count=0,
        )
        result = batch.get_result("q1")
        self.assertIsNotNone(result)
        self.assertEqual(result.query_id, "q1")

        missing = batch.get_result("nonexistent")
        self.assertIsNone(missing)

    def test_successful_responses(self):
        """Test filtering successful responses."""
        results = [
            ParallelResult(query_id="q1", response=self.response1, success=True),
            ParallelResult(query_id="q2", response=None, error="Failed", success=False),
            ParallelResult(query_id="q3", response=self.response2, success=True),
        ]
        batch = BatchResult(
            results=results,
            total_time=1.0,
            total_tokens=250,
            total_cost=0.0015,
            success_count=2,
            failure_count=1,
        )
        successful = batch.successful_responses()
        self.assertEqual(len(successful), 2)
        self.assertIn(self.response1, successful)
        self.assertIn(self.response2, successful)


class TestRateLimiter(unittest.TestCase):
    """Test rate limiting functionality."""

    def test_initial_tokens(self):
        """Test rate limiter initializes with full tokens."""
        limiter = RateLimiter(requests_per_second=10.0)
        self.assertEqual(limiter.rate, 10.0)
        self.assertEqual(limiter.tokens, 10.0)

    def test_acquire_consumes_token(self):
        """Test acquiring reduces tokens."""
        limiter = RateLimiter(requests_per_second=5.0)

        async def run_test():
            await limiter.acquire()
            self.assertLess(limiter.tokens, 5.0)

        asyncio.run(run_test())

    def test_multiple_rapid_acquires(self):
        """Test multiple rapid acquires work correctly."""
        limiter = RateLimiter(requests_per_second=10.0)

        async def run_test():
            for _ in range(5):
                await limiter.acquire()
            # Should have consumed 5 tokens
            self.assertLessEqual(limiter.tokens, 5.5)

        asyncio.run(run_test())


class TestParallelLLMExecutor(unittest.TestCase):
    """Test parallel executor functionality."""

    def setUp(self):
        """Create mock router."""
        self.mock_router = Mock()
        self.mock_response = LLMResponse(
            content="Mock response",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4",
            tokens_used=100,
            cost_usd=0.001,
            latency_seconds=0.1,
        )
        self.mock_router.complete.return_value = self.mock_response

    def test_executor_initialization(self):
        """Test executor initializes with correct defaults."""
        executor = ParallelLLMExecutor(
            router=self.mock_router,
            max_concurrent=5,
            requests_per_second=10.0,
        )
        self.assertEqual(executor.max_concurrent, 5)
        self.assertEqual(executor.rate_limiter.rate, 10.0)
        self.assertTrue(executor.retry_failed)

    def test_empty_batch(self):
        """Test executing empty batch returns empty result."""
        executor = ParallelLLMExecutor(router=self.mock_router)
        result = executor.execute_batch([])
        self.assertEqual(result.success_count, 0)
        self.assertEqual(result.failure_count, 0)
        self.assertEqual(len(result.results), 0)

    def test_single_query_execution(self):
        """Test executing single query."""
        executor = ParallelLLMExecutor(router=self.mock_router)
        query = ParallelQuery(
            id="test_1",
            messages=[{"role": "user", "content": "Test"}],
        )
        result = executor.execute_batch([query])

        self.assertEqual(result.success_count, 1)
        self.assertEqual(result.failure_count, 0)
        self.assertEqual(len(result.results), 1)
        self.mock_router.complete.assert_called_once()

    def test_multiple_queries_execution(self):
        """Test executing multiple queries in parallel."""
        executor = ParallelLLMExecutor(router=self.mock_router)
        queries = [
            ParallelQuery(id=f"test_{i}", messages=[{"role": "user", "content": f"Query {i}"}])
            for i in range(3)
        ]
        result = executor.execute_batch(queries)

        self.assertEqual(result.success_count, 3)
        self.assertEqual(result.failure_count, 0)
        self.assertEqual(self.mock_router.complete.call_count, 3)

    def test_failed_query_handling(self):
        """Test handling of failed queries."""
        self.mock_router.complete.side_effect = Exception("API Error")
        executor = ParallelLLMExecutor(
            router=self.mock_router,
            retry_failed=False,  # Disable retries for test
        )
        query = ParallelQuery(
            id="fail_test",
            messages=[{"role": "user", "content": "This will fail"}],
        )
        result = executor.execute_batch([query])

        self.assertEqual(result.success_count, 0)
        self.assertEqual(result.failure_count, 1)
        self.assertFalse(result.results[0].success)
        self.assertIn("API Error", result.results[0].error)

    def test_retry_on_failure(self):
        """Test retry logic on failures."""
        call_count = 0

        def fail_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return self.mock_response

        self.mock_router.complete.side_effect = fail_then_succeed
        executor = ParallelLLMExecutor(
            router=self.mock_router,
            retry_failed=True,
            max_retries=3,
        )
        query = ParallelQuery(
            id="retry_test",
            messages=[{"role": "user", "content": "Test"}],
        )
        result = executor.execute_batch([query])

        self.assertEqual(result.success_count, 1)
        self.assertGreaterEqual(call_count, 3)

    def test_callback_on_complete(self):
        """Test callback is invoked for each completed query."""
        executor = ParallelLLMExecutor(router=self.mock_router)
        completed_ids = []

        def on_complete(result):
            completed_ids.append(result.query_id)

        queries = [
            ParallelQuery(id=f"cb_{i}", messages=[{"role": "user", "content": f"Query {i}"}])
            for i in range(3)
        ]

        async def run_test():
            await executor.execute_with_callback_async(queries, on_complete)

        asyncio.run(run_test())
        self.assertEqual(len(completed_ids), 3)
        self.assertIn("cb_0", completed_ids)
        self.assertIn("cb_1", completed_ids)
        self.assertIn("cb_2", completed_ids)


class TestQueryHelpers(unittest.TestCase):
    """Test helper functions for creating queries."""

    def test_create_package_queries(self):
        """Test package query creation helper."""
        packages = ["nginx", "postgresql", "redis"]
        queries = create_package_queries(packages)

        self.assertEqual(len(queries), 3)
        self.assertEqual(queries[0].id, "pkg_nginx")
        self.assertEqual(queries[1].id, "pkg_postgresql")
        self.assertEqual(queries[2].id, "pkg_redis")
        self.assertEqual(queries[0].task_type, TaskType.SYSTEM_OPERATION)
        self.assertEqual(queries[0].metadata["package"], "nginx")

    def test_create_package_queries_custom_template(self):
        """Test package queries with custom template."""
        packages = ["vim"]
        queries = create_package_queries(
            packages,
            system_prompt="Custom system",
            query_template="Check if {package} is secure.",
        )
        self.assertIn("vim", queries[0].messages[1]["content"])
        self.assertEqual(queries[0].messages[0]["content"], "Custom system")

    def test_create_error_diagnosis_queries(self):
        """Test error diagnosis query creation."""
        errors = [
            {"id": "1", "message": "Permission denied"},
            {"id": "2", "message": "Package not found"},
        ]
        queries = create_error_diagnosis_queries(errors)

        self.assertEqual(len(queries), 2)
        self.assertEqual(queries[0].id, "err_1")
        self.assertEqual(queries[0].task_type, TaskType.ERROR_DEBUGGING)
        self.assertIn("Permission denied", queries[0].messages[1]["content"])

    def test_create_hardware_check_queries(self):
        """Test hardware check query creation."""
        checks = ["GPU", "CPU", "RAM"]
        queries = create_hardware_check_queries(checks)

        self.assertEqual(len(queries), 3)
        self.assertEqual(queries[0].id, "hw_gpu")
        self.assertEqual(queries[1].id, "hw_cpu")
        self.assertEqual(queries[2].id, "hw_ram")
        self.assertEqual(queries[0].task_type, TaskType.CONFIGURATION)


class TestAsyncExecution(unittest.TestCase):
    """Test async execution patterns."""

    def setUp(self):
        """Create mock router."""
        self.mock_router = Mock()
        self.mock_response = LLMResponse(
            content="Async response",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4",
            tokens_used=50,
            cost_usd=0.0005,
            latency_seconds=0.05,
        )
        self.mock_router.complete.return_value = self.mock_response

    def test_async_batch_execution(self):
        """Test async batch execution directly."""
        executor = ParallelLLMExecutor(router=self.mock_router)
        queries = [
            ParallelQuery(id="async_1", messages=[{"role": "user", "content": "Test 1"}]),
            ParallelQuery(id="async_2", messages=[{"role": "user", "content": "Test 2"}]),
        ]

        async def run_test():
            result = await executor.execute_batch_async(queries)
            self.assertEqual(result.success_count, 2)
            return result

        result = asyncio.run(run_test())
        self.assertEqual(len(result.results), 2)

    def test_concurrent_execution_time(self):
        """Test that parallel execution is faster than sequential."""
        import time

        delay_time = 0.1

        def slow_complete(*args, **kwargs):
            time.sleep(delay_time)
            return self.mock_response

        self.mock_router.complete.side_effect = slow_complete
        executor = ParallelLLMExecutor(
            router=self.mock_router,
            max_concurrent=5,
            requests_per_second=100.0,  # High rate to not limit
        )
        queries = [
            ParallelQuery(id=f"speed_{i}", messages=[{"role": "user", "content": f"Test {i}"}])
            for i in range(3)
        ]

        start = time.time()
        result = executor.execute_batch(queries)
        elapsed = time.time() - start

        # Parallel should complete faster than 3 * delay_time
        # Allow some overhead but should be significantly faster
        self.assertLess(elapsed, 3 * delay_time * 0.9)
        self.assertEqual(result.success_count, 3)


if __name__ == "__main__":
    unittest.main()
