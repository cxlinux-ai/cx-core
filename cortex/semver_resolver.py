"""
Semantic Version Conflict Resolution

Issue: #154 - Semantic Version Conflict Resolution

Intelligent semantic versioning conflict resolution.
Parses constraints, detects conflicts, suggests resolutions.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class ConstraintType(Enum):
    """Types of version constraints."""

    EXACT = "exact"  # =1.0.0
    CARET = "caret"  # ^1.0.0
    TILDE = "tilde"  # ~1.0.0
    GREATER = "greater"  # >1.0.0
    GREATER_EQ = "greater_eq"  # >=1.0.0
    LESS = "less"  # <1.0.0
    LESS_EQ = "less_eq"  # <=1.0.0
    RANGE = "range"  # >=1.0.0 <2.0.0
    ANY = "any"  # *


class BreakingChangeRisk(Enum):
    """Risk level for breaking changes."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class SemVer:
    """Semantic version representation."""

    major: int
    minor: int
    patch: int
    prerelease: str = ""
    build: str = ""

    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        if self.build:
            version += f"+{self.build}"
        return version

    def __lt__(self, other: "SemVer") -> bool:
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.patch != other.patch:
            return self.patch < other.patch
        # Prerelease versions are lower than release
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        return self.prerelease < other.prerelease

    def __le__(self, other: "SemVer") -> bool:
        return self == other or self < other

    def __gt__(self, other: "SemVer") -> bool:
        return not self <= other

    def __ge__(self, other: "SemVer") -> bool:
        return not self < other

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return False
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
        )

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))

    def is_compatible_with(self, other: "SemVer") -> bool:
        """Check if versions are compatible (same major version)."""
        return self.major == other.major

    def breaking_change_from(self, other: "SemVer") -> BreakingChangeRisk:
        """Determine breaking change risk from other to self."""
        if self.major > other.major:
            return BreakingChangeRisk.HIGH
        if self.major < other.major:
            return BreakingChangeRisk.MEDIUM
        if self.minor != other.minor:
            return BreakingChangeRisk.LOW
        return BreakingChangeRisk.NONE


@dataclass
class VersionConstraint:
    """Version constraint specification."""

    raw: str
    constraint_type: ConstraintType
    version: SemVer | None = None
    max_version: SemVer | None = None  # For range constraints

    def satisfies(self, version: SemVer) -> bool:
        """Check if a version satisfies this constraint."""
        if self.constraint_type == ConstraintType.ANY:
            return True

        if not self.version:
            return False

        if self.constraint_type == ConstraintType.EXACT:
            return version == self.version

        elif self.constraint_type == ConstraintType.CARET:
            # ^1.2.3 means >=1.2.3 <2.0.0 (for major > 0)
            # ^0.2.3 means >=0.2.3 <0.3.0 (for major = 0)
            if version < self.version:
                return False
            if self.version.major == 0:
                return version.major == 0 and version.minor == self.version.minor
            return version.major == self.version.major

        elif self.constraint_type == ConstraintType.TILDE:
            # ~1.2.3 means >=1.2.3 <1.3.0
            if version < self.version:
                return False
            return version.major == self.version.major and version.minor == self.version.minor

        elif self.constraint_type == ConstraintType.GREATER:
            return version > self.version

        elif self.constraint_type == ConstraintType.GREATER_EQ:
            return version >= self.version

        elif self.constraint_type == ConstraintType.LESS:
            return version < self.version

        elif self.constraint_type == ConstraintType.LESS_EQ:
            return version <= self.version

        elif self.constraint_type == ConstraintType.RANGE:
            if not self.max_version:
                return version >= self.version
            return self.version <= version < self.max_version

        return False


@dataclass
class Dependency:
    """Package dependency with version constraint."""

    name: str
    constraint: VersionConstraint
    source: str = ""  # Which package requires this


@dataclass
class VersionConflict:
    """Represents a version conflict between dependencies."""

    package: str
    dependencies: list[Dependency] = field(default_factory=list)
    resolved_version: SemVer | None = None

    @property
    def is_conflicting(self) -> bool:
        """Check if dependencies have conflicting constraints."""
        if len(self.dependencies) < 2:
            return False

        # Check if any version satisfies all constraints
        # (simplified check - in reality would need version enumeration)
        constraints = [d.constraint for d in self.dependencies]

        # Quick conflict detection
        for i, c1 in enumerate(constraints):
            for c2 in constraints[i + 1 :]:
                if not self._constraints_compatible(c1, c2):
                    return True
        return False

    def _constraints_compatible(self, c1: VersionConstraint, c2: VersionConstraint) -> bool:
        """Check if two constraints can be satisfied simultaneously."""
        if c1.constraint_type == ConstraintType.ANY:
            return True
        if c2.constraint_type == ConstraintType.ANY:
            return True

        if not c1.version or not c2.version:
            return True

        # Caret vs Tilde with different major versions
        if c1.constraint_type == ConstraintType.CARET:
            if c2.constraint_type == ConstraintType.TILDE:
                if c1.version.major != c2.version.major:
                    return False
                if c2.version.minor < c1.version.minor:
                    return False

        # Different major versions in caret constraints
        if (
            c1.constraint_type == ConstraintType.CARET
            and c2.constraint_type == ConstraintType.CARET
        ):
            if c1.version.major != c2.version.major and c1.version.major > 0:
                return False

        return True


@dataclass
class ResolutionStrategy:
    """A strategy for resolving version conflicts."""

    name: str
    description: str
    risk: BreakingChangeRisk
    changes: list[str] = field(default_factory=list)
    recommended: bool = False


class SemVerResolver:
    """Semantic version conflict resolver."""

    SEMVER_PATTERN = re.compile(
        r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
        r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
        r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
        r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
    )

    def __init__(self, verbose: bool = False):
        """Initialize the resolver."""
        self.verbose = verbose
        self.dependencies: dict[str, list[Dependency]] = {}
        self.conflicts: list[VersionConflict] = []

    def parse_version(self, version_str: str) -> SemVer | None:
        """Parse a semantic version string.

        Args:
            version_str: Version string like "1.2.3" or "1.2.3-beta.1"

        Returns:
            SemVer object or None if invalid
        """
        version_str = version_str.strip()
        match = self.SEMVER_PATTERN.match(version_str)
        if not match:
            return None

        return SemVer(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=match.group("prerelease") or "",
            build=match.group("build") or "",
        )

    def parse_constraint(self, constraint_str: str) -> VersionConstraint | None:
        """Parse a version constraint string.

        Args:
            constraint_str: Constraint like "^1.2.3", "~1.0.0", ">=1.0.0 <2.0.0"

        Returns:
            VersionConstraint object or None if invalid
        """
        constraint_str = constraint_str.strip()

        if not constraint_str or constraint_str == "*":
            return VersionConstraint(
                raw=constraint_str,
                constraint_type=ConstraintType.ANY,
            )

        # Range constraint
        if " " in constraint_str:
            parts = constraint_str.split()
            if len(parts) == 2:
                min_part = parts[0]
                max_part = parts[1]

                min_version = None
                max_version = None

                if min_part.startswith(">="):
                    min_version = self.parse_version(min_part[2:])
                elif min_part.startswith(">"):
                    min_version = self.parse_version(min_part[1:])

                if max_part.startswith("<"):
                    max_version = self.parse_version(max_part[1:])

                if min_version:
                    return VersionConstraint(
                        raw=constraint_str,
                        constraint_type=ConstraintType.RANGE,
                        version=min_version,
                        max_version=max_version,
                    )

        # Caret constraint
        if constraint_str.startswith("^"):
            version = self.parse_version(constraint_str[1:])
            if version:
                return VersionConstraint(
                    raw=constraint_str,
                    constraint_type=ConstraintType.CARET,
                    version=version,
                )

        # Tilde constraint
        if constraint_str.startswith("~"):
            version = self.parse_version(constraint_str[1:])
            if version:
                return VersionConstraint(
                    raw=constraint_str,
                    constraint_type=ConstraintType.TILDE,
                    version=version,
                )

        # Comparison operators
        if constraint_str.startswith(">="):
            version = self.parse_version(constraint_str[2:])
            if version:
                return VersionConstraint(
                    raw=constraint_str,
                    constraint_type=ConstraintType.GREATER_EQ,
                    version=version,
                )

        if constraint_str.startswith(">"):
            version = self.parse_version(constraint_str[1:])
            if version:
                return VersionConstraint(
                    raw=constraint_str,
                    constraint_type=ConstraintType.GREATER,
                    version=version,
                )

        if constraint_str.startswith("<="):
            version = self.parse_version(constraint_str[2:])
            if version:
                return VersionConstraint(
                    raw=constraint_str,
                    constraint_type=ConstraintType.LESS_EQ,
                    version=version,
                )

        if constraint_str.startswith("<"):
            version = self.parse_version(constraint_str[1:])
            if version:
                return VersionConstraint(
                    raw=constraint_str,
                    constraint_type=ConstraintType.LESS,
                    version=version,
                )

        if constraint_str.startswith("="):
            version = self.parse_version(constraint_str[1:])
            if version:
                return VersionConstraint(
                    raw=constraint_str,
                    constraint_type=ConstraintType.EXACT,
                    version=version,
                )

        # Try exact version
        version = self.parse_version(constraint_str)
        if version:
            return VersionConstraint(
                raw=constraint_str,
                constraint_type=ConstraintType.EXACT,
                version=version,
            )

        return None

    def add_dependency(self, package: str, constraint_str: str, source: str = "") -> bool:
        """Add a dependency constraint.

        Args:
            package: Package name
            constraint_str: Version constraint
            source: Source package requiring this dependency

        Returns:
            True if successfully added
        """
        constraint = self.parse_constraint(constraint_str)
        if not constraint:
            return False

        dep = Dependency(name=package, constraint=constraint, source=source)

        if package not in self.dependencies:
            self.dependencies[package] = []
        self.dependencies[package].append(dep)

        return True

    def detect_conflicts(self) -> list[VersionConflict]:
        """Detect version conflicts among dependencies.

        Returns:
            List of detected conflicts
        """
        self.conflicts = []

        for package, deps in self.dependencies.items():
            if len(deps) < 2:
                continue

            conflict = VersionConflict(package=package, dependencies=deps)
            if conflict.is_conflicting:
                self.conflicts.append(conflict)

        return self.conflicts

    def suggest_resolutions(self, conflict: VersionConflict) -> list[ResolutionStrategy]:
        """Suggest resolution strategies for a conflict.

        Args:
            conflict: The version conflict to resolve

        Returns:
            List of resolution strategies
        """
        strategies = []

        deps = conflict.dependencies
        if len(deps) < 2:
            return strategies

        # Strategy 1: Find common version (if possible)
        common_strategy = self._find_common_version_strategy(conflict)
        if common_strategy:
            strategies.append(common_strategy)

        # Strategy 2: Update newer dependency
        for dep in deps:
            if dep.constraint.constraint_type in (
                ConstraintType.CARET,
                ConstraintType.TILDE,
            ):
                update_strategy = ResolutionStrategy(
                    name=f"Update {dep.source}",
                    description=f"Update {dep.source} to a version compatible with other constraints",
                    risk=BreakingChangeRisk.LOW,
                    changes=[f"Update {dep.source} to latest compatible version"],
                )
                strategies.append(update_strategy)

        # Strategy 3: Pin to specific version
        pin_strategy = ResolutionStrategy(
            name="Pin versions",
            description="Pin all packages to specific compatible versions",
            risk=BreakingChangeRisk.MEDIUM,
            changes=[
                f"Pin {conflict.package} to a specific version",
                "May require manual testing for compatibility",
            ],
        )
        strategies.append(pin_strategy)

        # Strategy 4: Use resolutions/overrides
        override_strategy = ResolutionStrategy(
            name="Use version override",
            description="Force a specific version using package manager overrides",
            risk=BreakingChangeRisk.HIGH,
            changes=[
                f"Add resolution override for {conflict.package}",
                "May cause runtime issues if incompatible",
            ],
        )
        strategies.append(override_strategy)

        # Mark recommended
        if strategies:
            strategies[0].recommended = True

        return strategies

    def _find_common_version_strategy(self, conflict: VersionConflict) -> ResolutionStrategy | None:
        """Try to find a common version that satisfies all constraints."""
        constraints = [d.constraint for d in conflict.dependencies]

        # Simple heuristic: if all are caret/tilde with same major, suggest latest
        all_compatible = True
        major_versions = set()

        for c in constraints:
            if c.version:
                major_versions.add(c.version.major)
            if c.constraint_type not in (
                ConstraintType.CARET,
                ConstraintType.TILDE,
                ConstraintType.GREATER_EQ,
            ):
                all_compatible = False

        if all_compatible and len(major_versions) == 1:
            major = list(major_versions)[0]
            return ResolutionStrategy(
                name="Use latest compatible",
                description=f"Use the latest {major}.x.x version",
                risk=BreakingChangeRisk.NONE,
                changes=[
                    f"All constraints are compatible within {major}.x range",
                    "Install the latest version that satisfies all constraints",
                ],
                recommended=True,
            )

        return None

    def display_conflicts(self):
        """Display detected conflicts."""
        if not self.conflicts:
            console.print("[green]No version conflicts detected[/green]")
            return

        console.print(
            Panel(
                f"[bold red]Found {len(self.conflicts)} version conflict(s)[/bold red]",
                style="red",
            )
        )

        for conflict in self.conflicts:
            console.print()
            console.print(f"[bold cyan]Package: {conflict.package}[/bold cyan]")

            table = Table(show_header=True)
            table.add_column("Required by")
            table.add_column("Constraint")
            table.add_column("Type")

            for dep in conflict.dependencies:
                table.add_row(
                    dep.source or "(direct)",
                    dep.constraint.raw,
                    dep.constraint.constraint_type.value,
                )

            console.print(table)

    def display_resolutions(self, conflict: VersionConflict):
        """Display resolution strategies for a conflict."""
        strategies = self.suggest_resolutions(conflict)

        if not strategies:
            console.print("[yellow]No resolution strategies available[/yellow]")
            return

        console.print()
        console.print(
            Panel(
                "[bold]Resolution Strategies[/bold]",
                style="cyan",
            )
        )

        for i, strategy in enumerate(strategies, 1):
            rec = " [green](Recommended)[/green]" if strategy.recommended else ""
            risk_color = {
                BreakingChangeRisk.NONE: "green",
                BreakingChangeRisk.LOW: "yellow",
                BreakingChangeRisk.MEDIUM: "orange3",
                BreakingChangeRisk.HIGH: "red",
            }.get(strategy.risk, "white")

            console.print(f"\n[bold]Strategy {i}: {strategy.name}[/bold]{rec}")
            console.print(f"  {strategy.description}")
            console.print(f"  Risk: [{risk_color}]{strategy.risk.value}[/{risk_color}]")

            if strategy.changes:
                console.print("  Changes:")
                for change in strategy.changes:
                    console.print(f"    - {change}")


def run_semver_resolver(
    action: str = "analyze",
    packages: list[str] | None = None,
    verbose: bool = False,
) -> int:
    """Run the semantic version resolver.

    Args:
        action: Action to perform (analyze, parse, check)
        packages: Package constraints to analyze
        verbose: Enable verbose output

    Returns:
        Exit code (0 for success)
    """
    resolver = SemVerResolver(verbose=verbose)

    if action == "analyze":
        if not packages:
            console.print("[yellow]No package constraints provided[/yellow]")
            console.print("\nUsage examples:")
            console.print("  cortex deps resolve 'lib-x:^2.0.0:pkg-a' 'lib-x:~1.9.0:pkg-b'")
            console.print("  cortex deps check '^1.2.3'")
            console.print("  cortex deps parse '>=1.0.0 <2.0.0'")
            return 0

        # Parse package constraints: format "package:constraint:source"
        for pkg_spec in packages:
            parts = pkg_spec.split(":")
            if len(parts) >= 2:
                package = parts[0]
                constraint = parts[1]
                source = parts[2] if len(parts) > 2 else ""
                resolver.add_dependency(package, constraint, source)

        conflicts = resolver.detect_conflicts()
        resolver.display_conflicts()

        for conflict in conflicts:
            resolver.display_resolutions(conflict)

        return 0 if not conflicts else 1

    elif action == "parse":
        if not packages:
            console.print("[yellow]No version string provided[/yellow]")
            return 1

        for version_str in packages:
            # Try parsing as version
            version = resolver.parse_version(version_str)
            if version:
                console.print(f"[green]Version:[/green] {version}")
                console.print(f"  Major: {version.major}")
                console.print(f"  Minor: {version.minor}")
                console.print(f"  Patch: {version.patch}")
                if version.prerelease:
                    console.print(f"  Prerelease: {version.prerelease}")
                continue

            # Try parsing as constraint
            constraint = resolver.parse_constraint(version_str)
            if constraint:
                console.print(f"[green]Constraint:[/green] {constraint.raw}")
                console.print(f"  Type: {constraint.constraint_type.value}")
                if constraint.version:
                    console.print(f"  Version: {constraint.version}")
                if constraint.max_version:
                    console.print(f"  Max version: {constraint.max_version}")
            else:
                console.print(f"[red]Invalid: {version_str}[/red]")

        return 0

    elif action == "check":
        if not packages or len(packages) < 2:
            console.print("[yellow]Usage: cortex deps check <constraint> <version>[/yellow]")
            return 1

        constraint_str = packages[0]
        version_str = packages[1]

        constraint = resolver.parse_constraint(constraint_str)
        version = resolver.parse_version(version_str)

        if not constraint:
            console.print(f"[red]Invalid constraint: {constraint_str}[/red]")
            return 1

        if not version:
            console.print(f"[red]Invalid version: {version_str}[/red]")
            return 1

        if constraint.satisfies(version):
            console.print(f"[green]Version {version} satisfies constraint {constraint_str}[/green]")
            return 0
        else:
            console.print(
                f"[red]Version {version} does NOT satisfy constraint {constraint_str}[/red]"
            )
            return 1

    elif action == "compare":
        if not packages or len(packages) < 2:
            console.print("[yellow]Usage: cortex deps compare <version1> <version2>[/yellow]")
            return 1

        v1 = resolver.parse_version(packages[0])
        v2 = resolver.parse_version(packages[1])

        if not v1 or not v2:
            console.print("[red]Invalid version(s)[/red]")
            return 1

        if v1 < v2:
            console.print(f"[cyan]{v1}[/cyan] < [cyan]{v2}[/cyan]")
        elif v1 > v2:
            console.print(f"[cyan]{v1}[/cyan] > [cyan]{v2}[/cyan]")
        else:
            console.print(f"[cyan]{v1}[/cyan] = [cyan]{v2}[/cyan]")

        risk = v2.breaking_change_from(v1)
        if risk != BreakingChangeRisk.NONE:
            console.print(f"Breaking change risk: [yellow]{risk.value}[/yellow]")

        return 0

    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Available actions: analyze, parse, check, compare")
        return 1
