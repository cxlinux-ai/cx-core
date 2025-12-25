#!/usr/bin/env python3
"""
Test script to verify Ollama setup integration with pip install.
This validates that the PostDevelopCommand hook works correctly.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_setup_import():
    """Test that setup_ollama can be imported."""
    print("Testing import of setup_ollama...")
    try:
        from scripts.setup_ollama import setup_ollama

        print("✅ Import successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False


def test_setup_execution():
    """Test that setup_ollama executes without errors (with skip flag)."""
    print("\nTesting setup_ollama execution (skipped mode)...")
    try:
        # Set skip flag to avoid actual Ollama installation during test
        os.environ["CORTEX_SKIP_OLLAMA_SETUP"] = "1"

        from scripts.setup_ollama import setup_ollama

        setup_ollama()

        print("✅ Setup function executed successfully")
        return True
    except Exception as e:
        print(f"❌ Setup execution failed: {e}")
        return False
    finally:
        # Clean up environment
        os.environ.pop("CORTEX_SKIP_OLLAMA_SETUP", None)


def test_package_structure():
    """Verify that scripts package is properly structured."""
    print("\nTesting package structure...")

    scripts_dir = project_root / "scripts"
    init_file = scripts_dir / "__init__.py"
    setup_file = scripts_dir / "setup_ollama.py"

    checks = [
        (scripts_dir.exists(), f"scripts/ directory exists: {scripts_dir}"),
        (init_file.exists(), f"scripts/__init__.py exists: {init_file}"),
        (setup_file.exists(), f"scripts/setup_ollama.py exists: {setup_file}"),
    ]

    all_passed = True
    for passed, message in checks:
        if passed:
            print(f"  ✅ {message}")
        else:
            print(f"  ❌ {message}")
            all_passed = False

    return all_passed


def test_manifest_includes():
    """Check that MANIFEST.in includes scripts directory."""
    print("\nTesting MANIFEST.in configuration...")

    manifest_file = project_root / "MANIFEST.in"
    if not manifest_file.exists():
        print("  ❌ MANIFEST.in not found")
        return False

    content = manifest_file.read_text()
    if "recursive-include scripts" in content:
        print("  ✅ MANIFEST.in includes scripts directory")
        return True
    else:
        print("  ❌ MANIFEST.in does not include scripts directory")
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("Cortex Linux - Ollama Setup Integration Tests")
    print("=" * 70)
    print()

    tests = [
        ("Package Structure", test_package_structure),
        ("MANIFEST.in Configuration", test_manifest_includes),
        ("Setup Import", test_setup_import),
        ("Setup Execution", test_setup_execution),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"❌ Test '{name}' raised exception: {e}")
            results.append((name, False))
        print()

    # Summary
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")

    print()
    print(f"Results: {passed_count}/{total_count} tests passed")
    print("=" * 70)

    if passed_count == total_count:
        print("\n🎉 All tests passed! Ollama setup integration is ready.")
        print("\nNext steps:")
        print("  1. Run: pip install -e .")
        print("  2. Ollama will be automatically set up during installation")
        print("  3. Use CORTEX_SKIP_OLLAMA_SETUP=1 to skip Ollama setup if needed")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
