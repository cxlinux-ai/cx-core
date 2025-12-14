"""Pytest configuration for the `tests/` suite.

These tests historically import modules as top-level (e.g. `import context_memory`)
while the project sources live under `cortex/` and `src/`.

In CI we install the package (editable), which exposes `cortex.*` but does not
create top-level modules for those files. To keep the existing tests stable and
avoid a large import rewrite, we add the relevant source roots to `sys.path`.

This file only affects the `tests/` suite (not `test/`).
"""

from __future__ import annotations

import sys
from pathlib import Path


def _prepend_sys_path(path: Path) -> None:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


_REPO_ROOT = Path(__file__).resolve().parents[1]

# Prepend in reverse order (each insert goes to index 0), resulting in:
#   src/ -> cortex/ -> repo root
_prepend_sys_path(_REPO_ROOT)
_prepend_sys_path(_REPO_ROOT / "cortex")
_prepend_sys_path(_REPO_ROOT / "src")
