#!/usr/bin/env python3
"""
Quick test script to verify parallel LLM calls are working.

Run this to test:
1. Async completion works
2. Batch processing works
3. Rate limiting works
4. Helper functions work
"""

import asyncio
import os
import sys
import time

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from cortex.llm_router import (
    LLMRouter,
    TaskType,
    check_hardware_configs_parallel,
    diagnose_errors_parallel,
    query_multiple_packages,
)


async def test_async_completion():
    """Test basic async completion."""
    print("=" * 60)
    print("Test 1: Async Completion")
    print("=" * 60)

    router = LLMRouter()

    if not router.claude_client_async and not router.kimi_client_async:
        print("⚠️  No API keys found. Set ANTHROPIC_API_KEY or MOONSHOT_API_KEY")
        print("   Skipping async completion test...")
        return False

    try:
        start = time.time()
        response = await router.acomplete(
            messages=[{"role": "user", "content": "Say 'Hello from async'"}],
            task_type=TaskType.USER_CHAT,
            max_tokens=50,
        )
        elapsed = time.time() - start

        print("✅ Async completion successful!")
        print(f"   Provider: {response.provider.value}")
        print(f"   Latency: {elapsed:.2f}s")
        print(f"   Response: {response.content[:100]}")
        print(f"   Tokens: {response.tokens_used}")
        return True
    except Exception as e:
        print(f"❌ Async completion failed: {e}")
        return False


async def test_batch_processing():
    """Test batch processing."""
    print("\n" + "=" * 60)
    print("Test 2: Batch Processing")
    print("=" * 60)

    router = LLMRouter()

    if not router.claude_client_async and not router.kimi_client_async:
        print("⚠️  No API keys found. Skipping batch test...")
        return False

    try:
        requests = [
            {
                "messages": [{"role": "user", "content": "What is 1+1?"}],
                "task_type": TaskType.USER_CHAT,
                "max_tokens": 20,
            },
            {
                "messages": [{"role": "user", "content": "What is 2+2?"}],
                "task_type": TaskType.USER_CHAT,
                "max_tokens": 20,
            },
            {
                "messages": [{"role": "user", "content": "What is 3+3?"}],
                "task_type": TaskType.USER_CHAT,
                "max_tokens": 20,
            },
        ]

        print(f"Processing {len(requests)} requests in parallel...")
        start = time.time()
        responses = await router.complete_batch(requests, max_concurrent=3)
        elapsed = time.time() - start

        print("✅ Batch processing successful!")
        print(f"   Total time: {elapsed:.2f}s")
        print(f"   Average per request: {elapsed / len(requests):.2f}s")

        for i, response in enumerate(responses, 1):
            if response.model == "error":
                print(f"   Request {i}: ❌ Error - {response.content}")
            else:
                print(f"   Request {i}: ✅ {response.content[:50]}...")

        return all(r.model != "error" for r in responses)
    except Exception as e:
        print(f"❌ Batch processing failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_rate_limiting():
    """Test rate limiting."""
    print("\n" + "=" * 60)
    print("Test 3: Rate Limiting")
    print("=" * 60)

    router = LLMRouter()
    router.set_rate_limit(max_concurrent=2)

    if not router.claude_client_async and not router.kimi_client_async:
        print("⚠️  No API keys found. Skipping rate limit test...")
        return False

    try:
        # Create 5 requests but limit to 2 concurrent
        requests = [
            {
                "messages": [{"role": "user", "content": f"Count: {i}"}],
                "task_type": TaskType.USER_CHAT,
                "max_tokens": 10,
            }
            for i in range(5)
        ]

        print(f"Processing {len(requests)} requests with max_concurrent=2...")
        start = time.time()
        responses = await router.complete_batch(requests, max_concurrent=2)
        elapsed = time.time() - start

        print("✅ Rate limiting working!")
        print(f"   Total time: {elapsed:.2f}s")
        print(f"   Semaphore value: {router._rate_limit_semaphore._value}")
        return True
    except Exception as e:
        print(f"❌ Rate limiting test failed: {e}")
        return False


async def test_helper_functions():
    """Test helper functions."""
    print("\n" + "=" * 60)
    print("Test 4: Helper Functions")
    print("=" * 60)

    router = LLMRouter()

    if not router.claude_client_async and not router.kimi_client_async:
        print("⚠️  No API keys found. Skipping helper function tests...")
        return False

    results = []

    # Test query_multiple_packages
    try:
        print("\n4a. Testing query_multiple_packages...")
        packages = ["nginx", "postgresql"]
        responses = await query_multiple_packages(router, packages, max_concurrent=2)
        print(f"   ✅ Queried {len(responses)} packages")
        results.append(True)
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        results.append(False)

    # Test diagnose_errors_parallel
    try:
        print("\n4b. Testing diagnose_errors_parallel...")
        errors = ["Test error 1", "Test error 2"]
        diagnoses = await diagnose_errors_parallel(router, errors, max_concurrent=2)
        print(f"   ✅ Diagnosed {len(diagnoses)} errors")
        results.append(True)
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        results.append(False)

    # Test check_hardware_configs_parallel
    try:
        print("\n4c. Testing check_hardware_configs_parallel...")
        components = ["nvidia_gpu", "intel_cpu"]
        configs = await check_hardware_configs_parallel(router, components, max_concurrent=2)
        print(f"   ✅ Checked {len(configs)} components")
        results.append(True)
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        results.append(False)

    return all(results)


async def test_performance_comparison():
    """Compare sequential vs parallel performance."""
    print("\n" + "=" * 60)
    print("Test 5: Performance Comparison")
    print("=" * 60)

    router = LLMRouter()

    if not router.claude_client_async and not router.kimi_client_async:
        print("⚠️  No API keys found. Skipping performance test...")
        return False

    try:
        requests = [
            {
                "messages": [{"role": "user", "content": f"Request {i}"}],
                "task_type": TaskType.USER_CHAT,
                "max_tokens": 20,
            }
            for i in range(3)
        ]

        # Simulate sequential (would be slower)
        print("Simulating sequential execution...")
        start_seq = time.time()
        for req in requests:
            await router.acomplete(
                **{k: v for k, v in req.items() if k != "task_type"}, task_type=req["task_type"]
            )
        elapsed_seq = time.time() - start_seq

        # Parallel execution
        print("Running parallel execution...")
        start_par = time.time()
        await router.complete_batch(requests, max_concurrent=3)
        elapsed_par = time.time() - start_par

        speedup = elapsed_seq / elapsed_par if elapsed_par > 0 else 1.0
        print("\n✅ Performance comparison:")
        print(f"   Sequential: {elapsed_seq:.2f}s")
        print(f"   Parallel: {elapsed_par:.2f}s")
        print(f"   Speedup: {speedup:.2f}x")

        return speedup > 1.0
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Parallel LLM Calls - Test Suite")
    print("=" * 60)
    print("\nChecking API keys...")

    # Check for API keys
    has_claude = bool(os.getenv("ANTHROPIC_API_KEY"))
    has_kimi = bool(os.getenv("MOONSHOT_API_KEY"))

    if has_claude:
        print("✅ ANTHROPIC_API_KEY found")
    else:
        print("⚠️  ANTHROPIC_API_KEY not set")

    if has_kimi:
        print("✅ MOONSHOT_API_KEY found")
    else:
        print("⚠️  MOONSHOT_API_KEY not set")

    if not has_claude and not has_kimi:
        print("\n❌ No API keys found!")
        print("   Set at least one:")
        print("   export ANTHROPIC_API_KEY='your-key'")
        print("   export MOONSHOT_API_KEY='your-key'")
        return

    print("\n" + "=" * 60)
    print("Running tests...")
    print("=" * 60)

    results = []

    # Run tests
    results.append(await test_async_completion())
    results.append(await test_batch_processing())
    results.append(await test_rate_limiting())
    results.append(await test_helper_functions())
    results.append(await test_performance_comparison())

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"\n✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")

    if all(results):
        print("\n🎉 All tests passed! Parallel LLM calls are working correctly.")
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")

    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
