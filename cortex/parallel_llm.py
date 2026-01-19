#!/usr/bin/env python3
"""
Parallel LLM Executor for Cortex Linux

Enables concurrent LLM API calls with rate limiting for 2-3x speedup.
Batches independent queries and aggregates responses.

Use cases:
- Multi-package queries (analyze multiple packages simultaneously)
- Parallel error diagnosis
- Concurrent hardware config checks

Author: Cortex Linux Team
SPDX-License-Identifier: BUSL-1.1
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cortex.llm_router import LLMProvider, LLMResponse, LLMRouter, TaskType

logger = logging.getLogger(__name__)


@dataclass
class ParallelQuery:
    """A single query to be executed in parallel."""

    id: str
    messages: list[dict[str, str]]
    task_type: TaskType = TaskType.USER_CHAT
    force_provider: LLMProvider | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParallelResult:
    """Result of a parallel query execution."""

    query_id: str
    response: LLMResponse | None
    error: str | None = None
    success: bool = True
    execution_time: float = 0.0


@dataclass
class BatchResult:
    """Aggregated results from a batch of parallel queries."""

    results: list[ParallelResult]
    total_time: float
    total_tokens: int
    total_cost: float
    success_count: int
    failure_count: int

    def get_result(self, query_id: str) -> ParallelResult | None:
        """Get result by query ID."""
        for r in self.results:
            if r.query_id == query_id:
                return r
        return None

    def successful_responses(self) -> list[LLMResponse]:
        """Get all successful LLM responses."""
        return [r.response for r in self.results if r.success and r.response]


class RateLimiter:
    """
    Token bucket rate limiter for API calls.

    Limits requests per second to avoid hitting provider rate limits.
    """

    def __init__(self, requests_per_second: float = 5.0):
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Max requests allowed per second
        """
        self.rate = requests_per_second
        self.tokens = requests_per_second
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request token is available."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class ParallelLLMExecutor:
    """
    Executor for parallel LLM API calls.

    Batches independent queries and executes them concurrently
    with configurable rate limiting and error handling.
    """

    def __init__(
        self,
        router: LLMRouter | None = None,
        max_concurrent: int = 5,
        requests_per_second: float = 5.0,
        retry_failed: bool = True,
        max_retries: int = 2,
    ):
        """
        Initialize parallel executor.

        Args:
            router: LLMRouter instance (creates new one if None)
            max_concurrent: Maximum concurrent API calls
            requests_per_second: Rate limit for API calls
            retry_failed: Whether to retry failed requests
            max_retries: Maximum retry attempts per request
        """
        self.router = router or LLMRouter()
        self.max_concurrent = max_concurrent
        self.rate_limiter = RateLimiter(requests_per_second)
        self.retry_failed = retry_failed
        self.max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _execute_single(self, query: ParallelQuery, attempt: int = 0) -> ParallelResult:
        """Execute a single query with rate limiting and retries."""
        start_time = time.time()

        try:
            await self.rate_limiter.acquire()

            async with self._semaphore:
                # Run sync router.complete in thread pool
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.router.complete(
                        messages=query.messages,
                        task_type=query.task_type,
                        force_provider=query.force_provider,
                        temperature=query.temperature,
                        max_tokens=query.max_tokens,
                    ),
                )

                return ParallelResult(
                    query_id=query.id,
                    response=response,
                    success=True,
                    execution_time=time.time() - start_time,
                )

        except Exception as e:
            logger.warning(f"Query {query.id} failed (attempt {attempt + 1}): {e}")

            if self.retry_failed and attempt < self.max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))  # exponential backoff
                return await self._execute_single(query, attempt + 1)

            return ParallelResult(
                query_id=query.id,
                response=None,
                error=str(e),
                success=False,
                execution_time=time.time() - start_time,
            )

    async def execute_batch_async(self, queries: list[ParallelQuery]) -> BatchResult:
        """
        Execute a batch of queries concurrently.

        Args:
            queries: List of queries to execute in parallel

        Returns:
            BatchResult with all responses and statistics
        """
        if not queries:
            return BatchResult(
                results=[],
                total_time=0.0,
                total_tokens=0,
                total_cost=0.0,
                success_count=0,
                failure_count=0,
            )

        start_time = time.time()

        # Execute all queries concurrently
        tasks = [self._execute_single(q) for q in queries]
        results = await asyncio.gather(*tasks)

        total_time = time.time() - start_time
        total_tokens = sum(r.response.tokens_used for r in results if r.success and r.response)
        total_cost = sum(r.response.cost_usd for r in results if r.success and r.response)
        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count

        logger.info(
            f"Batch complete: {success_count}/{len(results)} succeeded "
            f"in {total_time:.2f}s ({total_tokens} tokens, ${total_cost:.4f})"
        )

        return BatchResult(
            results=list(results),
            total_time=total_time,
            total_tokens=total_tokens,
            total_cost=total_cost,
            success_count=success_count,
            failure_count=failure_count,
        )

    def execute_batch(self, queries: list[ParallelQuery]) -> BatchResult:
        """
        Synchronous wrapper for execute_batch_async.

        Args:
            queries: List of queries to execute

        Returns:
            BatchResult with all responses
        """
        return asyncio.run(self.execute_batch_async(queries))

    async def execute_with_callback_async(
        self,
        queries: list[ParallelQuery],
        on_complete: Callable[[ParallelResult], None] | None = None,
    ) -> BatchResult:
        """
        Execute batch with per-query callback for progress tracking.

        Args:
            queries: List of queries to execute
            on_complete: Callback invoked when each query completes

        Returns:
            BatchResult with all responses
        """
        if not queries:
            return BatchResult(
                results=[],
                total_time=0.0,
                total_tokens=0,
                total_cost=0.0,
                success_count=0,
                failure_count=0,
            )

        start_time = time.time()
        results = []

        async def execute_with_notify(query: ParallelQuery) -> ParallelResult:
            result = await self._execute_single(query)
            if on_complete:
                on_complete(result)
            return result

        tasks = [execute_with_notify(q) for q in queries]
        results = await asyncio.gather(*tasks)

        total_time = time.time() - start_time
        total_tokens = sum(r.response.tokens_used for r in results if r.success and r.response)
        total_cost = sum(r.response.cost_usd for r in results if r.success and r.response)
        success_count = sum(1 for r in results if r.success)

        return BatchResult(
            results=list(results),
            total_time=total_time,
            total_tokens=total_tokens,
            total_cost=total_cost,
            success_count=success_count,
            failure_count=len(results) - success_count,
        )


def create_package_queries(
    packages: list[str],
    system_prompt: str = "You are a Linux package expert.",
    query_template: str = "Analyze the package '{package}' and describe its purpose.",
) -> list[ParallelQuery]:
    """
    Helper to create parallel queries for multiple packages.

    Args:
        packages: List of package names
        system_prompt: System message for the LLM
        query_template: Template with {package} placeholder

    Returns:
        List of ParallelQuery objects
    """
    queries = []
    for pkg in packages:
        queries.append(
            ParallelQuery(
                id=f"pkg_{pkg}",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query_template.format(package=pkg)},
                ],
                task_type=TaskType.SYSTEM_OPERATION,
                metadata={"package": pkg},
            )
        )
    return queries


def create_error_diagnosis_queries(
    errors: list[dict[str, str]],
) -> list[ParallelQuery]:
    """
    Create parallel queries for diagnosing multiple errors.

    Args:
        errors: List of dicts with 'id' and 'message' keys

    Returns:
        List of ParallelQuery objects
    """
    queries = []
    for err in errors:
        queries.append(
            ParallelQuery(
                id=f"err_{err['id']}",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a Linux system debugging expert.",
                    },
                    {
                        "role": "user",
                        "content": f"Diagnose this error: {err['message']}",
                    },
                ],
                task_type=TaskType.ERROR_DEBUGGING,
                metadata={"original_error": err},
            )
        )
    return queries


def create_hardware_check_queries(
    checks: list[str],
) -> list[ParallelQuery]:
    """
    Create parallel queries for hardware configuration checks.

    Args:
        checks: List of hardware aspects to check (e.g., "GPU", "CPU", "RAM")

    Returns:
        List of ParallelQuery objects
    """
    queries = []
    for check in checks:
        queries.append(
            ParallelQuery(
                id=f"hw_{check.lower()}",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a hardware configuration expert.",
                    },
                    {
                        "role": "user",
                        "content": f"Provide optimal configuration recommendations for {check}.",
                    },
                ],
                task_type=TaskType.CONFIGURATION,
                metadata={"hardware_type": check},
            )
        )
    return queries
