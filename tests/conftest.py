from __future__ import annotations

import sys
from pathlib import Path

"""Pytest configuration.

Some tests in this repository import implementation modules as if they were top-level
(e.g. `import config_manager`). In the current layout, those modules live under the
`cortex/` directory.

Insert `cortex/` into `sys.path` early (at conftest import time) so imports resolve
during test collection.
"""

repo_root = Path(__file__).resolve().parents[1]

# Support both layouts used across branches/history:
# - `cortex/` (package modules)
# - `src/` (legacy flat modules)
for path in (repo_root / "src", repo_root / "cortex"):
    path_str = str(path)
    if path.exists() and path_str not in sys.path:
        sys.path.insert(0, path_str)
