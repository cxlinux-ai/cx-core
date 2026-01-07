"""
Dependency Check Module for Cortex Linux
Verifies all required dependencies are installed before the main application runs.
"""

import sys
from typing import NamedTuple


class DependencyStatus(NamedTuple):
    name: str
    installed: bool
    import_name: str


REQUIRED_DEPENDENCIES = [
    ("pyyaml", "yaml"),
    ("rich", "rich"),
    ("anthropic", "anthropic"),
    ("openai", "openai"),
    ("python-dotenv", "dotenv"),
    ("requests", "requests"),
]


def check_dependency(package_name: str, import_name: str) -> DependencyStatus:
    try:
        __import__(import_name)
        return DependencyStatus(package_name, True, import_name)
    except ImportError:
        return DependencyStatus(package_name, False, import_name)


def get_missing_dependencies() -> list[str]:
    return [pkg for pkg, imp in REQUIRED_DEPENDENCIES if not check_dependency(pkg, imp).installed]


def format_installation_instructions(missing: list[str]) -> str:
    packages = " ".join(missing)
    return f"""
╭─────────────────────────────────────────────────────────────────╮
│  ⚠️  Missing Dependencies Detected                              │
╰─────────────────────────────────────────────────────────────────╯

Cortex requires the following packages that are not installed:
  {", ".join(missing)}

To fix this, run ONE of the following:

  Option 1 - Install Cortex properly (recommended):
    pip install -e .

  Option 2 - Install just the missing packages:
    pip install {packages}

  Option 3 - Install all requirements:
    pip install -r requirements.txt

After installing, run 'cortex' again.
"""


def verify_dependencies_or_exit() -> None:
    missing = get_missing_dependencies()
    if missing:
        print(format_installation_instructions(missing), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    missing = get_missing_dependencies()
    if missing:
        print(format_installation_instructions(missing))
        sys.exit(1)
    print("✅ All dependencies are installed correctly.")
