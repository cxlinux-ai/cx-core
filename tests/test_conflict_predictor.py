"""
Focused unit tests for the dependency conflict predictor.

WHY these specific cases:
  1. _satisfies() is the core logic gate – any bug here causes silent mis-predictions.
  2. dpkg status parsing is the data foundation – malformed entries must not crash.
  3. End-to-end predict() must catch the canonical conflict (tensorflow vs numpy 2.x)
     without touching the real filesystem or apt-cache.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Adjust import path if running from repo root
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "dependency"))

from conflict_predictor import (
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
    """Every operator variant must work correctly."""

    @pytest.mark.parametrize("installed,constraint,expected", [
        # Less-than: numpy <2.0 scenario from the issue
        ("1.26.4", "<2.0",   True),
        ("2.1.0",  "<2.0",   False),   # THE canonical tensorflow conflict
        ("2.0.0",  "<2.0",   False),
        # Greater-than-or-equal
        ("2.17",   ">=2.17", True),
        ("2.16",   ">=2.17", False),
        # Exact
        ("1.26.4", "==1.26.4", True),
        ("1.26.3", "==1.26.4", False),
        # Not-equal
        ("2.0.0",  "!=2.0.0", False),
        ("2.0.1",  "!=2.0.0", True),
        # Empty constraint → always satisfied
        ("99.0",   "",        True),
        # Unparseable constraint → conservative True (no false positive)
        ("1.0",    "~=1.0",   True),
    ])
    def test_operator_matrix(self, installed: str, constraint: str, expected: bool):
        assert _satisfies(installed, constraint) is expected, (
            f"_satisfies({installed!r}, {constraint!r}) should be {expected}"
        )


# ---------------------------------------------------------------------------
# 2. dpkg status parsing
# ---------------------------------------------------------------------------

class TestParseDpkgStatus:
    """Parser must handle normal entries, missing Version, and multi-stanza files."""

    def _write_status(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "status"
        p.write_text(textwrap.dedent(content))
        return p

    def test_normal_entry(self, tmp_path):
        status = self._write_status(tmp_path, """
            Package: numpy
            Version: 2.1.0
            Depends: python3 (>= 3.8), libc6 (>= 2.17)

        """)
        pkgs = parse_dpkg_status(status)
        assert "numpy" in pkgs
        np = pkgs["numpy"]
        assert np.version == "2.1.0"
        assert ("python3", ">=3.8") in np.depends
        assert ("libc6", ">=2.17") in np.depends

    def test_missing_version_is_empty_string(self, tmp_path):
        """Packages without a Version field must not raise; version defaults to ''."""
        status = self._write_status(tmp_path, """
            Package: some-meta-pkg
            Depends: bash

        """)
        pkgs = parse_dpkg_status(status)
        assert pkgs["some-meta-pkg"].version == ""

    def test_multiple_packages(self, tmp_path):
        status = self._write_status(tmp_path, """
            Package: pandas
            Version: 1.5.3
            Depends: numpy (>= 1.21)

            Package: numpy
            Version: 2.1.0

        """)
        pkgs = parse_dpkg_status(status)
        assert set(pkgs.keys()) == {"pandas", "numpy"}
        assert pkgs["pandas"].depends[0] == ("numpy", ">=1.21")

    def test_nonexistent_file_returns_empty(self):
        pkgs = parse_dpkg_status(Path("/nonexistent/path/status"))
        assert pkgs == {}


# ---------------------------------------------------------------------------
# 3. End-to-end predict(): tensorflow vs numpy 2.x
# ---------------------------------------------------------------------------

class TestPredictEndToEnd:
    """
    Simulate the canonical scenario from the issue:
      - System has numpy 2.1.0 (installed by pandas)
      - tensorflow 2.15 transitively requires numpy<2.0
    Expected: one Conflict returned with confidence 1.0
    """

    def _make_predictor_with_numpy(self, tmp_path: Path) -> DependencyConflictPredictor:
        """Build a predictor whose 'installed' state contains numpy 2.1.0."""
        status = tmp_path / "status"
        status.write_text(textwrap.dedent("""
            Package: numpy
            Version: 2.1.0

            Package: pandas
            Version: 1.5.3
            Depends: numpy (>= 1.21)

        """))
        return DependencyConflictPredictor(dpkg_status_path=status)

    def test_detects_numpy_conflict(self, tmp_path):
        predictor = self._make_predictor_with_numpy(tmp_path)

        # Patch apt-cache so we control what transitive deps tensorflow declares
        # WHY: we cannot run apt-cache in CI, and we want deterministic results.
        fake_deps = [
            # tensorflow 2.15 directly requires numpy<2.0
            ("numpy", "<2.0", "tensorflow"),
        ]

        with patch(
            "conflict_predictor.build_transitive_deps",
            return_value=iter(fake_deps),
        ):
            conflicts = predictor.predict("tensorflow", "2.15")

        assert len(conflicts) == 1, "Expected exactly one conflict"
        c = conflicts[0]
        assert c.package == "numpy"
        assert c.required == "<2.0"
        assert c.installed == "2.1.0"
        assert c.confidence == 1.0
        assert c.required_by == "tensorflow"

    def test_no_conflict_when_constraint_satisfied(self, tmp_path):
        """If tensorflow requires numpy>=1.21 and we have 2.1.0, no conflict."""
        predictor = self._make_predictor_with_numpy(tmp_path)

        compatible_deps = [("numpy", ">=1.21", "tensorflow")]

        with patch(
            "conflict_predictor.build_transitive_deps",
            return_value=iter(compatible_deps),
        ):
            conflicts = predictor.predict("tensorflow", "2.16")

        assert conflicts == [], "No conflict expected when constraint is satisfied"

    def test_unknown_version_yields_low_confidence_warning(self, tmp_path):
        """Package present without version → confidence 0.7 warning, not hard error."""
        status = tmp_path / "status"
        # numpy present but Version field absent
        status.write_text("Package: numpy\n\n")
        predictor = DependencyConflictPredictor(dpkg_status_path=status)

        deps = [("numpy", "<2.0", "tensorflow")]
        with patch(
            "conflict_predictor.build_transitive_deps",
            return_value=iter(deps),
        ):
            conflicts = predictor.predict("tensorflow", "2.15")

        assert len(conflicts) == 1
        assert conflicts[0].confidence == 0.7
        assert conflicts[0].installed == "unknown"

    def test_suggest_resolutions_returns_three_ranked(self, tmp_path):
        """Resolution list must have 3 entries, ordered by safety_score desc."""
        predictor = self._make_predictor_with_numpy(tmp_path)
        from conflict_predictor import Conflict
        conflict = Conflict(
            package="numpy",
            required="<2.0",
            installed="2.1.0",
            required_by="tensorflow",
            confidence=1.0,
        )
        resolutions = predictor.suggest_resolutions(conflict, "tensorflow", "2.15")
        assert len(resolutions) == 3
        scores = [r.safety_score for r in resolutions]
        assert scores == sorted(scores, reverse=True), "Must be sorted safest-first"
        # The top suggestion must reference the target package
        assert "tensorflow" in resolutions[0].description
