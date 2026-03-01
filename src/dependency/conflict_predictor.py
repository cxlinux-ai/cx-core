#!/usr/bin/env python3
"""
AI-Powered Dependency Conflict Predictor for Cortex.

Predicts package dependency conflicts BEFORE installation begins by:
1. Parsing current system state from /var/lib/dpkg/status
2. Building a transitive dependency DAG via apt-cache
3. Checking version constraint intersections
4. Ranking resolution suggestions by safety

WHY this file exists: apt/dpkg only surface conflicts after install begins,
causing failed deploys. This module gives users actionable warnings upfront.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Generator, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PackageInfo:
    """Represents a single installed package and its direct dependencies."""
    name: str
    version: str                          # installed version string
    depends: List[Tuple[str, str]] = field(default_factory=list)
    # Each dep is (pkg_name, version_constraint) e.g. ("numpy", "<2.0")


@dataclass
class Conflict:
    """A detected version conflict between a candidate dep and the system."""
    package: str          # e.g. "numpy"
    required: str         # constraint from the new package, e.g. "<2.0"
    installed: str        # currently installed version, e.g. "2.1.0"
    required_by: str      # which transitive dep introduced this constraint
    confidence: float     # 0.0-1.0; 1.0 = definite conflict


@dataclass
class Resolution:
    """A ranked suggestion for resolving a conflict."""
    description: str
    safety_score: float   # 0.0 (risky) – 1.0 (safest)
    command: Optional[str] = None


# ---------------------------------------------------------------------------
# Version comparison helpers
# ---------------------------------------------------------------------------

def _parse_version(v: str) -> Tuple[int, ...]:
    """
    Convert a version string to a comparable tuple of ints.
    Non-numeric segments are dropped so '2.1.0~rc1' -> (2, 1, 0).
    WHY: stdlib has no built-in that handles Debian epoch/tilde syntax well
    for our lightweight needs; packaging.version would be better in a full
    implementation but we avoid the extra dependency here.
    """
    return tuple(int(x) for x in re.findall(r'\d+', v))


def _satisfies(installed_ver: str, constraint: str) -> bool:
    """
    Check whether *installed_ver* satisfies *constraint*.
    Constraint examples: ">=1.21", "<2.0", "==1.26.4", "!=2.0"
    Returns True (no conflict) when constraint is empty/unknown.
    """
    if not constraint:
        return True

    # Match leading operator then version digits
    m = re.match(r'^([><=!]+)([\d.]+)', constraint.strip())
    if not m:
        # Can't parse – conservative: assume satisfied to avoid false positives
        return True

    op, req_ver = m.group(1), m.group(2)
    iv = _parse_version(installed_ver)
    rv = _parse_version(req_ver)

    return {
        '>':  iv > rv,
        '>=': iv >= rv,
        '<':  iv < rv,
        '<=': iv <= rv,
        '==': iv == rv,
        '!=': iv != rv,
    }.get(op, True)  # unknown op → assume ok


# ---------------------------------------------------------------------------
# System state reader
# ---------------------------------------------------------------------------

DPKG_STATUS = Path("/var/lib/dpkg/status")


def parse_dpkg_status(status_path: Path = DPKG_STATUS) -> Dict[str, PackageInfo]:
    """
    Parse /var/lib/dpkg/status into a dict keyed by package name.

    WHY we read this file directly: `dpkg -l` output is less structured;
    the status file gives us Version + Depends in one pass with no
    subprocess overhead per package.

    Handles packages missing Version gracefully (version set to "").
    """
    packages: Dict[str, PackageInfo] = {}

    if not status_path.exists():
        # Running outside a Debian system (e.g. CI) – return empty dict
        return packages

    current: Dict[str, str] = {}

    def _flush(rec: Dict[str, str]) -> None:
        name = rec.get("Package", "").strip()
        if not name:
            return
        version = rec.get("Version", "").strip()
        depends_raw = rec.get("Depends", "")
        deps = _parse_depends_field(depends_raw)
        packages[name] = PackageInfo(name=name, version=version, depends=deps)

    with status_path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line == "":
                _flush(current)
                current = {}
            elif ":" in line and not line.startswith(" "):
                key, _, val = line.partition(":")
                current[key.strip()] = val.strip()

    _flush(current)  # last stanza if file doesn't end with blank line
    return packages


def _parse_depends_field(raw: str) -> List[Tuple[str, str]]:
    """
    Parse a Depends: field like:
      libc6 (>= 2.17), python3 (<< 4), python3-numpy (>= 1.21)
    Returns list of (name, constraint) pairs.

    WHY: we need the constraint string separately for version comparison;
    splitting on commas then extracting parens is robust enough for Debian
    format without a full parser.
    """
    deps: List[Tuple[str, str]] = []
    if not raw:
        return deps

    # Handle alternates ("a | b") by taking first option only (conservative)
    for segment in raw.split(","):
        segment = segment.strip().split("|")[0].strip()
        m = re.match(r'^([\w.+\-]+)\s*(?:\(([^)]+)\))?', segment)
        if m:
            pkg_name = m.group(1)
            constraint = m.group(2) or ""  # e.g. ">= 2.17" or ""
            # Normalise spaces inside constraint: ">= 2.17" -> ">=2.17"
            constraint = re.sub(r'\s+', '', constraint)
            deps.append((pkg_name, constraint))
    return deps


# ---------------------------------------------------------------------------
# Transitive dependency walker
# ---------------------------------------------------------------------------

def _apt_cache_depends(package: str, version_hint: str = "") -> List[Tuple[str, str]]:
    """
    Query `apt-cache depends` for *package* and return its direct dependencies.
    Falls back to empty list if apt-cache unavailable (e.g. non-Debian CI).

    WHY apt-cache instead of only dpkg status: we need deps of packages that
    are NOT yet installed (the candidate and its transitive deps).
    """
    try:
        pkg_spec = f"{package}={version_hint}" if version_hint else package
        result = subprocess.run(
            ["apt-cache", "depends", pkg_spec],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    deps: List[Tuple[str, str]] = []
    # apt-cache depends output lines look like:
    #   Depends: libfoo (>= 1.2)
    #   PreDepends: libc6 (>= 2.17)
    for line in result.stdout.splitlines():
        m = re.match(
            r'^\s+(?:Depends|PreDepends|Recommends):\s+([\w.+\-]+)\s*(?:\(([^)]+)\))?',
            line
        )
        if m:
            name = m.group(1)
            constraint = re.sub(r'\s+', '', m.group(2) or "")
            deps.append((name, constraint))
    return deps


def build_transitive_deps(
    package: str,
    version_hint: str = "",
    visited: Optional[Set[str]] = None,
    depth: int = 0,
    max_depth: int = 10,
) -> Generator[Tuple[str, str, str], None, None]:
    """
    Yield (dep_name, constraint, required_by) tuples for every transitive
    dependency of *package*.

    WHY explicit visited set + max_depth: apt-cache can return cycles in
    virtual package scenarios; we must guard against infinite recursion.
    """
    if visited is None:
        visited = set()

    if package in visited or depth > max_depth:
        return
    visited.add(package)

    for dep_name, constraint in _apt_cache_depends(package, version_hint):
        yield dep_name, constraint, package
        # Recurse – we don't pass a version hint for transitive deps
        # because we only know what apt-cache resolves at runtime
        yield from build_transitive_deps(
            dep_name, "", visited=visited, depth=depth + 1, max_depth=max_depth
        )


# ---------------------------------------------------------------------------
# Conflict detector
# ---------------------------------------------------------------------------

class DependencyConflictPredictor:
    """
    Main entry point.  Usage::

        predictor = DependencyConflictPredictor()
        conflicts = predictor.predict("tensorflow", "2.15")
        if conflicts:
            predictor.print_report(conflicts, "tensorflow", "2.15")
    """

    def __init__(self, dpkg_status_path: Path = DPKG_STATUS):
        # Cache installed packages once; re-parse only if asked
        self._installed: Dict[str, PackageInfo] = parse_dpkg_status(dpkg_status_path)

    def predict(self, package: str, version: str = "") -> List[Conflict]:
        """
        Walk the transitive deps of *package*==*version* and return every
        constraint that conflicts with the currently installed system.

        Confidence scoring:
          - 1.0  → installed version definitely violates the constraint
          - 0.7  → package present but version unknown (conservative warning)
          - 0.0  → no conflict
        """
        conflicts: List[Conflict] = []
        seen_pairs: Set[Tuple[str, str]] = set()  # avoid duplicate reports

        for dep_name, constraint, required_by in build_transitive_deps(package, version):
            key = (dep_name, constraint)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)

            info = self._installed.get(dep_name)
            if info is None:
                # Not installed → apt will pull it in; no conflict
                continue

            if not info.version:
                # Package present but version unknown → warn conservatively
                conflicts.append(Conflict(
                    package=dep_name,
                    required=constraint,
                    installed="unknown",
                    required_by=required_by,
                    confidence=0.7,
                ))
                continue

            if constraint and not _satisfies(info.version, constraint):
                conflicts.append(Conflict(
                    package=dep_name,
                    required=constraint,
                    installed=info.version,
                    required_by=required_by,
                    confidence=1.0,
                ))

        # Sort by confidence descending so the most certain conflicts surface first
        conflicts.sort(key=lambda c: c.confidence, reverse=True)
        return conflicts

    # ------------------------------------------------------------------
    # Resolution suggestions
    # ------------------------------------------------------------------

    def suggest_resolutions(
        self, conflict: Conflict, target_pkg: str, target_ver: str
    ) -> List[Resolution]:
        """
        Generate ranked resolution strategies for a single conflict.

        WHY three tiers:
          1. Upgrade the *target* package (safest – no existing installs change)
          2. Adjust the *conflicting* dependency version (medium risk)
          3. Virtualenv isolation (always possible, most disruptive to workflow)
        """
        suggestions: List[Resolution] = []

        # 1. Try a newer version of the target package that relaxes the constraint
        suggestions.append(Resolution(
            description=(
                f"Install a newer version of {target_pkg} "
                f"compatible with {conflict.package} {conflict.installed}"
            ),
            safety_score=0.9,
            command=f"cortex install {target_pkg}  # let solver pick compatible version",
        ))

        # 2. Downgrade/adjust the conflicting package
        # We surface the constraint so the user knows the target range
        suggestions.append(Resolution(
            description=(
                f"Adjust {conflict.package} to satisfy {conflict.required} "
                f"(currently {conflict.installed})"
            ),
            safety_score=0.5,
            command=(
                f"cortex install '{conflict.package}{conflict.required}'"
                f"  # may affect packages depending on {conflict.package}"
            ),
        ))

        # 3. Isolate in a virtual environment
        suggestions.append(Resolution(
            description=(
                f"Use a virtual environment to isolate {target_pkg} "
                f"from the system {conflict.package}"
            ),
            safety_score=0.8,
            command=(
                f"python -m venv .venv && source .venv/bin/activate && "
                f"pip install {target_pkg}=={target_ver}"
            ),
        ))

        suggestions.sort(key=lambda r: r.safety_score, reverse=True)
        return suggestions

    # ------------------------------------------------------------------
    # Human-readable report
    # ------------------------------------------------------------------

    def print_report(self, conflicts: List[Conflict], package: str, version: str) -> None:
        """
        Print a coloured terminal report.  Mirrors the UX described in the
        issue so that the experience matches the design spec exactly.
        """
        ver_display = f" {version}" if version else ""
        print(f"\n⚠️  Conflict analysis for {package}{ver_display}")
        print("=" * 60)

        for i, conflict in enumerate(conflicts, 1):
            print(
                f"\nConflict #{i} (confidence {conflict.confidence:.0%}):\n"
                f"  {conflict.package} {conflict.required} required by {conflict.required_by}\n"
                f"  Your system has {conflict.package} {conflict.installed}"
            )
            resolutions = self.suggest_resolutions(conflict, package, version)
            print("\n  Suggestions (ranked by safety):")
            for j, res in enumerate(resolutions, 1):
                tag = "[RECOMMENDED]" if j == 1 else ""
                print(f"    {j}. {res.description} {tag}")
                if res.command:
                    print(f"       $ {res.command}")

        if not conflicts:
            print(f"  ✅ No conflicts detected for {package}{ver_display}")
        print()


# ---------------------------------------------------------------------------
# CLI entry point (thin wrapper – real CLI lives in cortex's click app)
# ---------------------------------------------------------------------------

def main(argv: List[str] = sys.argv[1:]) -> int:
    """
    Minimal CLI for standalone testing:
      python conflict_predictor.py tensorflow 2.15
    """
    if len(argv) < 1:
        print("Usage: conflict_predictor.py <package> [version]", file=sys.stderr)
        return 1

    pkg = argv[0]
    ver = argv[1] if len(argv) > 1 else ""

    predictor = DependencyConflictPredictor()
    conflicts = predictor.predict(pkg, ver)
    predictor.print_report(conflicts, pkg, ver)
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
