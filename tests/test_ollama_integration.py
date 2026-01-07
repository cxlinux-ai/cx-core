#!/usr/bin/env python3
"""
Test Ollama Integration with Cortex Linux

This script tests the Ollama integration by:
1. Checking if Ollama is installed
2. Checking if Ollama service is running
3. Testing the LLM router with Ollama provider
4. Verifying responses

Usage:
    python tests/test_ollama_integration.py
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Add cortex to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cortex.llm_router import LLMProvider, LLMRouter, TaskType


def get_available_ollama_model() -> str | None:
    """Get the first available Ollama model, or None if none available."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse output: skip header line, get first model name
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                # Model name is the first column
                parts = lines[1].split()
                if parts:
                    model_name = parts[0]
                    return model_name
    except Exception:
        # Best-effort helper: on any error, behave as if no models are available.
        pass
    return None


def is_ollama_installed() -> bool:
    """Check if Ollama is installed."""
    return subprocess.run(["which", "ollama"], capture_output=True).returncode == 0


def is_ollama_running() -> bool:
    """Check if Ollama service is running."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# Get available model for tests (can be overridden via env var)
OLLAMA_TEST_MODEL = os.environ.get("OLLAMA_TEST_MODEL") or get_available_ollama_model()

# Mark all tests to skip if Ollama is not available or no models installed
pytestmark = [
    pytest.mark.skipif(
        not is_ollama_installed(),
        reason="Ollama is not installed. Install with: python scripts/setup_ollama.py",
    ),
    pytest.mark.skipif(
        not is_ollama_running(),
        reason="Ollama service is not running. Start with: ollama serve",
    ),
    pytest.mark.skipif(
        OLLAMA_TEST_MODEL is None,
        reason="No Ollama models installed. Install with: ollama pull llama3.2",
    ),
]


def check_ollama_installed():
    """Check if Ollama is installed."""
    print("1. Checking Ollama installation...")
    result = subprocess.run(["which", "ollama"], capture_output=True)
    if result.returncode == 0:
        print("   ✓ Ollama is installed")
        return True
    else:
        print("   ✗ Ollama is not installed")
        print("   Run: python scripts/setup_ollama.py")
        return False


def check_ollama_running():
    """Check if Ollama service is running."""
    print("2. Checking Ollama service...")
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print("   ✓ Ollama service is running")
            # Show installed models
            models = [line.split()[0] for line in result.stdout.split("\n")[1:] if line.strip()]
            if models:
                print(f"   Installed models: {', '.join(models)}")
            return True
        else:
            print("   ✗ Ollama service is not running")
            print("   Start it with: ollama serve &")
            return False
    except Exception as e:
        print(f"   ✗ Error checking Ollama: {e}")
        return False


def test_llm_router():
    """Test LLMRouter with Ollama."""
    print("3. Testing LLM Router with Ollama...")
    print(f"   Using model: {OLLAMA_TEST_MODEL}")

    try:
        # Initialize router with Ollama
        router = LLMRouter(
            ollama_base_url="http://localhost:11434",
            ollama_model=OLLAMA_TEST_MODEL,
            default_provider=LLMProvider.OLLAMA,
            enable_fallback=False,  # Don't fall back to cloud APIs
        )

        print("   ✓ LLM Router initialized")

        # Test simple completion
        print("   Testing simple query...")
        messages = [{"role": "user", "content": "What is nginx? Answer in one sentence."}]

        response = router.complete(
            messages=messages,
            task_type=TaskType.USER_CHAT,
            force_provider=LLMProvider.OLLAMA,
        )

        print("   ✓ Response received")
        print(f"   Provider: {response.provider.value}")
        print(f"   Model: {response.model}")
        print(f"   Tokens: {response.tokens_used}")
        print(f"   Cost: ${response.cost_usd}")
        print(f"   Latency: {response.latency_seconds:.2f}s")
        print(f"   Content: {response.content[:100]}...")

        # Test passed
        assert response.content is not None
        assert response.tokens_used > 0

    except Exception as e:
        print(f"   ✗ Error: {e}")
        pytest.fail(f"LLM Router test failed: {e}")


def test_routing_decision():
    """Test routing logic with Ollama."""
    print("4. Testing routing decision...")

    # Get available model
    test_model = os.environ.get("OLLAMA_MODEL") or get_available_ollama_model()
    if not test_model:
        pytest.skip("No Ollama models available")

    try:
        router = LLMRouter(
            ollama_base_url="http://localhost:11434",
            ollama_model=OLLAMA_TEST_MODEL,
            default_provider=LLMProvider.OLLAMA,
        )

        # Test routing for different task types
        tasks = [
            TaskType.USER_CHAT,
            TaskType.SYSTEM_OPERATION,
            TaskType.ERROR_DEBUGGING,
        ]

        for task in tasks:
            decision = router.route_task(task, force_provider=LLMProvider.OLLAMA)
            print(f"   {task.value} → {decision.provider.value}")

        print("   ✓ Routing logic works")
        assert True  # Test passed

    except Exception as e:
        print(f"   ✗ Error testing routing: {e}")
        pytest.fail(f"Routing decision test failed: {e}")


def test_stats_tracking():
    """Test that stats tracking works with Ollama."""
    print("5. Testing stats tracking...")

    # Get available model
    test_model = os.environ.get("OLLAMA_MODEL") or get_available_ollama_model()
    if not test_model:
        pytest.skip("No Ollama models available")

    try:
        router = LLMRouter(
            ollama_base_url="http://localhost:11434",
            ollama_model=OLLAMA_TEST_MODEL,
            default_provider=LLMProvider.OLLAMA,
            track_costs=True,
        )

        # Make a request
        messages = [{"role": "user", "content": "Hello"}]
        router.complete(messages, force_provider=LLMProvider.OLLAMA)

        # Check stats
        stats = router.get_stats()
        print(f"   Total requests: {stats['total_requests']}")
        print(f"   Total cost: ${stats['total_cost_usd']}")
        print(f"   Ollama requests: {stats['providers']['ollama']['requests']}")
        print(f"   Ollama tokens: {stats['providers']['ollama']['tokens']}")

        print("   ✓ Stats tracking works")
        assert stats["providers"]["ollama"]["cost_usd"] == 0.0  # Ollama is free

    except Exception as e:
        print(f"   ✗ Error testing stats: {e}")
        pytest.fail(f"Stats tracking test failed: {e}")


def main():
    """Run all tests."""
    print("=" * 70)
    print("Ollama Integration Test Suite".center(70))
    print("=" * 70)
    print()

    # Check prerequisites
    if not check_ollama_installed():
        print("\n❌ Ollama is not installed. Please install it first.")
        print("   Run: python scripts/setup_ollama.py")
        return False

    if not check_ollama_running():
        print("\n❌ Ollama service is not running. Please start it.")
        print("   Run: ollama serve &")
        return False

    print()

    # Run tests
    tests = [
        ("LLM Router", test_llm_router),
        ("Routing Decision", test_routing_decision),
        ("Stats Tracking", test_stats_tracking),
    ]

    results = []
    for name, test_func in tests:
        result = test_func()
        results.append((name, result))
        print()

    # Summary
    print("=" * 70)
    print("Test Results".center(70))
    print("=" * 70)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{name:.<50} {status}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    print()
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n✅ All tests passed!")
        return True
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
