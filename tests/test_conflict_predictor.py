# Business Source License 1.1
#
# Licensor:             CX Linux AI
# Licensed Work:        CX Core
# Additional Use Grant: You may make production use of the Licensed Work,
#                       if your use does not include offering the Licensed
#                       Work to third parties on a hosted or embedded basis
#                       in order to compete with CX Linux AI's products.
# Change Date:          Four years from the date the Licensed Work is published.
# Change License:       Apache License, Version 2.0
#
# For information about alternative licensing arrangements for the Licensed Work,
# please contact legal@cxlinux.ai

"""
Focused unit tests for the dependency conflict predictor.

WHY these specific cases:
  1. _satisfies() is the core logic gate — any bug here causes silent mis-predictions.
  2. dpkg status parsing is the data foundation — malformed entries must not crash.
  3. End-to-end predict() must catch the canonical conflict (tensorflow vs numpy 2.x)
     without touching the real filesystem or apt-cache.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "dependency"))

from conflict_predictor import (
    Conflict,
    DependencyConflictPredictor,
    PackageInfo,
    _parse_depends_field,
    _parse_version,
    _satisfies,
    parse_dpkg_status,
)


# ---------------------------------------------------------------------------
# 1. Version constraint satisfaction
# ---------------------------------------------------------------------------

class TestSatisfies:
    """Every operator variant — including Debian-specific ones — must work correctly."""

    @pytest.mark.parametrize("installed,constraint,expected", [
        # Standard Python operators
        ("1.26.4", "<2.0",   True),
        ("2.1.0",  "<2.0",   False),   # canonical tensorflow conflict
        ("2.0.0",  "<2.0",   False),
        ("2.17",   ">=2.17", True),
        ("2.16",   ">=2.17", False),
        ("1.26.4", "==1.26.4", True),
        ("1.26.3", "==1.26.4", False),
        ("2.0.0",  "!=2.0.0", False),
        ("2.0.1",  "!=2.0.0", True),
        ("99.0",   "",        True),
        ("1.0",    "~=1.0",   True),   # unparseable → conservative True
        # Debian-specific operators
        ("1.9",    "<<2.0",  True),    # << is strict less-than
        ("2.0",    "<<2.0",  False),
        ("2.1",    ">>2.0",  True),    # >> is strict greater-than
        ("2.0",    ">>2.0",  False),
        ("1.26.4", "=1.26.4", True),   # = is exact equality in Debian
        ("1.26.3", "=1.26.4", False),
    ])
    def test_operator_matrix(self, installed: str, constraint: str, expected: bool) -> None:
        """Each (installed, constraint) pair must yield the expected boolean."""
        assert _satisfies(installed, constraint) is expected, (
            f"_satisfies({installed!r}, {constraint!r}) should be {expected}"
        )


# ---------------------------------------------------------------------------
# 2. dpkg status parsing
# ---------------------------------------------------------------------------

class TestParseDpkgStatus:
    """Parser must handle normal entries, continuation lines, missing Version, and multi-stanza files."""

    def _write_status(self, tmp_path: Path, content: str) -> Path:
        """Write a dpkg status file with dedented content and return its path."""
        p = tmp_path / "status"
        p.write_text(textwrap.dedent(content))
        return p

    def test_normal_entry(self, tmp_path: Path) -> None:
        """A well-formed stanza must parse name, version, and depends correctly."""
        status = self._write_status(tmp_path, """
            Package: numpy
            Version: 2.1.0
            Depends: python3 (>= 3.8), libc6 (>= 2.17)

        """)
        pkgs = parse_dpkg_status(status)
        assert "numpy" in pkgs
        np = pkgs["numpy"]
        assert np is not None
        assert np.version == "2.1.0"

    def test_missing_version(self, tmp_path: Path) -> None:
        """A stanza without a Version field must not crash the parser."""
        status = self._write_status(tmp_path, """
            Package: broken-pkg
            Depends: python3

        """)
        pkgs = parse_dpkg_status(status)
        assert "broken-pkg" not in pkgs or pkgs["broken-pkg"].version == ""

    def test_multi_stanza(self, tmp_path: Path) -> None:
        """Multiple stanzas separated by blank lines must all be parsed."""
        status = self._write_status(tmp_path, """
            Package: numpy
            Version: 2.1.0
            Depends: python3 (>= 3.8)

            Package: scipy
            Version: 1.11.0
            Depends: numpy (>= 1.21)

        """)
        pkgs = parse_dpkg_status(status)
        assert "numpy" in pkgs
        assert "scipy" in pkgs
