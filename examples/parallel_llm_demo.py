#!/usr/bin/env python3
"""
Example: Parallel LLM Calls with Cortex Linux

Demonstrates how to use parallel LLM calls for:
- Multi-package queries
- Parallel error diagnosis
- Concurrent hardware config checks

Expected speedup: 2-3x compared to sequential calls
"""

import asyncio
import time

from cortex.llm_router import (
    LLMRouter,
    TaskType,
    check_hardware_configs_parallel,
    diagnose_errors_parallel,
    query_multiple_packages,
)


async def demo_multi_package_queries():
    """Demonstrate parallel package queries."""
    print("=" * 60)
    print("Demo: Multi-Package Queries (Parallel)")
    print("=" * 60)

    router = LLMRouter()
    router.set_rate_limit(max_concurrent=5)  # Limit concurrent requests

    packages = ["nginx", "postgresql", "redis", "docker", "kubernetes"]

    print(f"\nQuerying {len(packages)} packages in parallel...")
    start_time = time.time()

    responses = await query_multiple_packages(router, packages, max_concurrent=5)

    elapsed = time.time() - start_time

    print(f"\n✅ Completed in {elapsed:.2f} seconds")
    print(f"   Average time per package: {elapsed / len(packages):.2f}s\n")

    for pkg, response in responses.items():
        print(f"📦 {pkg}:")
        print(f"   Provider: {response.provider.value}")
        print(f"   Tokens: {response.tokens_used}")
        print(f"   Cost: ${response.cost_usd:.6f}")
        print(f"   Response preview: {response.content[:100]}...")
        print()


async def demo_parallel_error_diagnosis():
    """Demonstrate parallel error diagnosis."""
    print("=" * 60)
    print("Demo: Parallel Error Diagnosis")
    print("=" * 60)

    router = LLMRouter()
    router.set_rate_limit(max_concurrent=3)

    errors = [
        "Package 'nginx' has unmet dependencies: libssl1.1",
        "Permission denied: /etc/nginx/nginx.conf",
        "Failed to start service: postgresql.service",
        "CUDA driver version mismatch: expected 535.0, got 525.0",
    ]

    print(f"\nDiagnosing {len(errors)} errors in parallel...")
    start_time = time.time()

    diagnoses = await diagnose_errors_parallel(
        router,
        errors,
        context="Ubuntu 22.04, NVIDIA RTX 4090",
        max_concurrent=4,
    )

    elapsed = time.time() - start_time

    print(f"\n✅ Completed in {elapsed:.2f} seconds")
    print(f"   Average time per error: {elapsed / len(errors):.2f}s\n")

    for error, diagnosis in zip(errors, diagnoses):
        print(f"🔍 Error: {error[:60]}...")
        print(f"   Diagnosis: {diagnosis.content[:150]}...")
        print(f"   Provider: {diagnosis.provider.value}")
        print()


async def demo_hardware_config_checks():
    """Demonstrate parallel hardware config checks."""
    print("=" * 60)
    print("Demo: Concurrent Hardware Config Checks")
    print("=" * 60)

    router = LLMRouter()
    router.set_rate_limit(max_concurrent=4)

    components = ["nvidia_gpu", "intel_cpu", "amd_gpu", "network_interface"]
    hardware_info = {
        "nvidia_gpu": {"model": "RTX 4090", "driver": "535.0"},
        "intel_cpu": {"model": "i9-13900K", "cores": 24},
    }

    print(f"\nChecking {len(components)} hardware components in parallel...")
    start_time = time.time()

    configs = await check_hardware_configs_parallel(
        router, components, hardware_info=hardware_info, max_concurrent=4
    )

    elapsed = time.time() - start_time

    print(f"\n✅ Completed in {elapsed:.2f} seconds")
    print(f"   Average time per component: {elapsed / len(components):.2f}s\n")

    for component, config in configs.items():
        print(f"🖥️  {component}:")
        print(f"   Provider: {config.provider.value}")
        print(f"   Config: {config.content[:150]}...")
        print()


async def demo_batch_completion():
    """Demonstrate generic batch completion."""
    print("=" * 60)
    print("Demo: Generic Batch Completion")
    print("=" * 60)

    router = LLMRouter()
    router.set_rate_limit(max_concurrent=5)

    # Mix of different task types
    requests = [
        {
            "messages": [{"role": "user", "content": "What is Python?"}],
            "task_type": TaskType.USER_CHAT,
        },
        {
            "messages": [{"role": "user", "content": "Install nginx with SSL"}],
            "task_type": TaskType.SYSTEM_OPERATION,
        },
        {
            "messages": [{"role": "user", "content": "Debug: apt update failed"}],
            "task_type": TaskType.ERROR_DEBUGGING,
        },
        {
            "messages": [{"role": "user", "content": "Generate bash script to backup database"}],
            "task_type": TaskType.CODE_GENERATION,
        },
    ]

    print(f"\nProcessing {len(requests)} mixed requests in parallel...")
    start_time = time.time()

    responses = await router.complete_batch(requests, max_concurrent=4)

    elapsed = time.time() - start_time

    print(f"\n✅ Completed in {elapsed:.2f} seconds")
    print(f"   Average time per request: {elapsed / len(requests):.2f}s\n")

    task_names = ["Chat", "System Op", "Error Debug", "Code Gen"]
    for i, (task_name, response) in enumerate(zip(task_names, responses)):
        print(f"📋 {task_name}:")
        print(f"   Provider: {response.provider.value}")
        print(f"   Latency: {response.latency_seconds:.2f}s")
        print(f"   Tokens: {response.tokens_used}")
        print(f"   Cost: ${response.cost_usd:.6f}")
        print(f"   Response: {response.content[:100]}...")
        print()

    # Show stats
    stats = router.get_stats()
    print("📊 Usage Statistics:")
    print(f"   Total requests: {stats['total_requests']}")
    print(f"   Total cost: ${stats['total_cost_usd']:.4f}")
    print()


async def demo_sequential_vs_parallel():
    """Compare sequential vs parallel performance."""
    print("=" * 60)
    print("Demo: Sequential vs Parallel Performance")
    print("=" * 60)

    router = LLMRouter()
    router.set_rate_limit(max_concurrent=5)

    packages = ["nginx", "postgresql", "redis"]

    # Sequential
    print("\n1️⃣ Sequential execution:")
    start_seq = time.time()
    for pkg in packages:
        # Simulate sequential call (would use router.complete() in real scenario)
        await asyncio.sleep(0.1)  # Simulate API call delay
    elapsed_seq = time.time() - start_seq
    print(f"   Time: {elapsed_seq:.2f}s")

    # Parallel
    print("\n2️⃣ Parallel execution:")
    start_par = time.time()
    await asyncio.gather(*[asyncio.sleep(0.1) for _ in packages])
    elapsed_par = time.time() - start_par
    print(f"   Time: {elapsed_par:.2f}s")

    speedup = elapsed_seq / elapsed_par if elapsed_par > 0 else 1.0
    print(f"\n⚡ Speedup: {speedup:.2f}x")
    print(
        f"   Time saved: {elapsed_seq - elapsed_par:.2f}s ({((elapsed_seq - elapsed_par) / elapsed_seq * 100):.1f}%)"
    )


async def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("Cortex Linux - Parallel LLM Calls Demo")
    print("=" * 60)
    print("\nThis demo shows how parallel LLM calls can achieve 2-3x speedup")
    print("compared to sequential calls.\n")

    try:
        await demo_multi_package_queries()
        await asyncio.sleep(1)

        await demo_parallel_error_diagnosis()
        await asyncio.sleep(1)

        await demo_hardware_config_checks()
        await asyncio.sleep(1)

        await demo_batch_completion()
        await asyncio.sleep(1)

        await demo_sequential_vs_parallel()

        print("\n" + "=" * 60)
        print("✅ All demos completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nNote: This demo requires valid API keys:")
        print("  - ANTHROPIC_API_KEY for Claude")
        print("  - MOONSHOT_API_KEY for Kimi K2")
        print("\nSet them as environment variables or pass to LLMRouter()")


if __name__ == "__main__":
    asyncio.run(main())
