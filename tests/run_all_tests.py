import os
import sys
import unittest


def main() -> int:
    """Discover and run all unittest modules within the test directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, ".."))

    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    suite = unittest.defaultTestLoader.discover(start_dir=current_dir, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
