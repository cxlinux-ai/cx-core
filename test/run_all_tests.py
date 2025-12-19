"""Unified test runner that discovers unit and integration suites."""

from __future__ import annotations

import argparse
import os
import sys
import unittest


def discover_tests(pattern: str = "test_*.py") -> unittest.TestSuite:
    """Discover tests starting from the repository's ``test`` directory."""

    start_dir = os.path.dirname(__file__)
    loader = unittest.TestLoader()
    return loader.discover(start_dir=start_dir, pattern=pattern)


def main(argv: list[str] | None = None) -> int:
    """Execute all test suites and return the exit code."""

    parser = argparse.ArgumentParser(description="Run Cortex unit/integration tests")
    parser.add_argument(
        "--pattern",
        default="test_*.py",
        help="Glob pattern used for discovery (defaults to test_*.py)",
    )
    args = parser.parse_args(argv)

    suite = discover_tests(pattern=args.pattern)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
