#!/usr/bin/env python3
"""
Dependency Resolution System with Visual Tree and Conflict Management.

Provides comprehensive dependency analysis, conflict prediction, impact
communication, alternative suggestions, and orphan package management.

Features:
    - Visual dependency tree with Rich formatting
    - Conflict prediction with actionable alternatives
    - Plain-language impact communication
    - Orphan package detection and cleanup
    - Dry-run mode for safe analysis
"""

import json
import logging
import os
import re
import subprocess
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# DATA MODELS
# =============================================================================


class ConflictType(Enum):
    """Types of package conflicts."""

    PROVIDES_SAME = "provides_same"  # Both provide same virtual package
    PORT_CONFLICT = "port_conflict"  # Both use same port
    FILE_CONFLICT = "file_conflict"  # Both install same file
    VERSION_MISMATCH = "version_mismatch"  # Version requirements conflict
    MUTUALLY_EXCLUSIVE = "mutually_exclusive"  # Declared conflicts


class ImpactSeverity(Enum):
    """Severity levels for dependency impact."""

    LOW = "low"  # Cosmetic, no functionality loss
    MEDIUM = "medium"  # Some features may not work
    HIGH = "high"  # Important functionality affected
    CRITICAL = "critical"  # System stability at risk


@dataclass
class Dependency:
    """Represents a package dependency."""

    name: str
    version: Optional[str] = None
    reason: str = ""
    is_satisfied: bool = False
    installed_version: Optional[str] = None
    is_optional: bool = False
    depth: int = 0  # Depth in dependency tree


@dataclass
class Conflict:
    """Represents a conflict between packages."""

    package_a: str
    package_b: str
    conflict_type: ConflictType
    description: str
    alternatives: list[str] = field(default_factory=list)
    resolution_steps: list[str] = field(default_factory=list)


@dataclass
class ImpactAssessment:
    """Assessment of impact from package changes."""

    package: str
    action: str  # install, remove, upgrade
    severity: ImpactSeverity
    affected_packages: list[str]
    plain_language_explanation: str
    recommendation: str


@dataclass
class OrphanPackage:
    """Represents an orphaned package."""

    name: str
    installed_version: str
    install_date: Optional[str] = None
    size_bytes: int = 0
    reason: str = ""  # Why it's considered orphan


@dataclass
class DependencyGraph:
    """Complete dependency graph for a package."""

    package_name: str
    direct_dependencies: list[Dependency]
    all_dependencies: list[Dependency]
    conflicts: list[Conflict]
    installation_order: list[str]
    reverse_dependencies: list[str] = field(default_factory=list)


# =============================================================================
# VISUAL TREE RENDERER
# =============================================================================


class VisualTreeRenderer:
    """
    Renders dependency trees with visual formatting.

    Supports both simple ASCII and Rich library formatting.
    """

    # Tree drawing characters
    BRANCH = "├── "
    LAST_BRANCH = "└── "
    VERTICAL = "│   "
    EMPTY = "    "

    # Status symbols
    INSTALLED = "✅"
    MISSING = "❌"
    OPTIONAL = "⚪"
    CONFLICT = "⚠️"
    ORPHAN = "🔸"

    def __init__(self, use_rich: bool = True):
        """Initialize renderer with optional Rich support."""
        self.use_rich = use_rich
        self._rich_available = False

        if use_rich:
            try:
                from rich.console import Console
                from rich.tree import Tree
                from rich.panel import Panel

                self._console = Console()
                self._rich_available = True
            except ImportError:
                logger.debug("Rich not available, using ASCII fallback")

    def render_tree(
        self,
        package_name: str,
        dependencies: list[Dependency],
        conflicts: list[Conflict] = None,
        show_versions: bool = True,
    ) -> str:
        """
        Render a dependency tree.

        Args:
            package_name: Root package name
            dependencies: List of dependencies
            conflicts: Optional list of conflicts to highlight
            show_versions: Whether to show version numbers

        Returns:
            Formatted tree string
        """
        if self._rich_available:
            return self._render_rich_tree(
                package_name, dependencies, conflicts, show_versions
            )
        return self._render_ascii_tree(
            package_name, dependencies, conflicts, show_versions
        )

    def _render_ascii_tree(
        self,
        package_name: str,
        dependencies: list[Dependency],
        conflicts: list[Conflict] = None,
        show_versions: bool = True,
    ) -> str:
        """Render tree using ASCII characters."""
        lines = []
        conflict_packages = set()

        if conflicts:
            for c in conflicts:
                conflict_packages.add(c.package_a)
                conflict_packages.add(c.package_b)

        # Root package
        lines.append(f"📦 {package_name}")

        # Sort dependencies: unsatisfied first, then by name
        sorted_deps = sorted(
            dependencies, key=lambda d: (d.is_satisfied, d.name)
        )

        for i, dep in enumerate(sorted_deps):
            is_last = i == len(sorted_deps) - 1
            prefix = self.LAST_BRANCH if is_last else self.BRANCH

            # Status symbol
            if dep.name in conflict_packages:
                status = self.CONFLICT
            elif dep.is_optional:
                status = self.OPTIONAL
            elif dep.is_satisfied:
                status = self.INSTALLED
            else:
                status = self.MISSING

            # Version string
            version_str = ""
            if show_versions and dep.installed_version:
                version_str = f" ({dep.installed_version})"
            elif show_versions and dep.version:
                version_str = f" (needs {dep.version})"

            # Reason
            reason_str = f" - {dep.reason}" if dep.reason else ""

            lines.append(f"{prefix}{status} {dep.name}{version_str}{reason_str}")

        return "\n".join(lines)

    def _render_rich_tree(
        self,
        package_name: str,
        dependencies: list[Dependency],
        conflicts: list[Conflict] = None,
        show_versions: bool = True,
    ) -> str:
        """Render tree using Rich library."""
        from rich.tree import Tree
        from io import StringIO

        conflict_packages = set()
        if conflicts:
            for c in conflicts:
                conflict_packages.add(c.package_a)
                conflict_packages.add(c.package_b)

        tree = Tree(f"📦 [bold blue]{package_name}[/bold blue]")

        # Group dependencies
        required = [d for d in dependencies if not d.is_optional]
        optional = [d for d in dependencies if d.is_optional]

        # Add required dependencies
        if required:
            req_branch = tree.add("[bold]Required[/bold]")
            for dep in sorted(required, key=lambda d: (d.is_satisfied, d.name)):
                self._add_dep_to_tree(
                    req_branch, dep, conflict_packages, show_versions
                )

        # Add optional dependencies
        if optional:
            opt_branch = tree.add("[dim]Optional[/dim]")
            for dep in sorted(optional, key=lambda d: d.name):
                self._add_dep_to_tree(
                    opt_branch, dep, conflict_packages, show_versions
                )

        # Capture output to string
        output = StringIO()
        console = self._console.__class__(file=output, force_terminal=True)
        console.print(tree)
        return output.getvalue()

    def _add_dep_to_tree(
        self,
        parent,
        dep: Dependency,
        conflict_packages: set,
        show_versions: bool,
    ):
        """Add a dependency node to a Rich tree."""
        # Determine style
        if dep.name in conflict_packages:
            style = "[bold yellow]"
            icon = "⚠️"
        elif dep.is_satisfied:
            style = "[green]"
            icon = "✅"
        else:
            style = "[red]"
            icon = "❌"

        # Build label
        label = f"{icon} {style}{dep.name}[/]"

        if show_versions:
            if dep.installed_version:
                label += f" [dim]({dep.installed_version})[/dim]"
            elif dep.version:
                label += f" [dim italic](needs {dep.version})[/dim italic]"

        if dep.reason:
            label += f" [dim]- {dep.reason}[/dim]"

        parent.add(label)


# =============================================================================
# CONFLICT PREDICTOR
# =============================================================================


class ConflictPredictor:
    """
    Predicts and analyzes package conflicts.

    Uses multiple heuristics:
    - Known conflict patterns (mysql vs mariadb, etc.)
    - Port usage conflicts
    - Provides/conflicts metadata from apt
    - Historical conflict data
    """

    # Known mutually exclusive package pairs
    KNOWN_CONFLICTS = {
        "mysql-server": {
            "conflicts": ["mariadb-server"],
            "type": ConflictType.MUTUALLY_EXCLUSIVE,
            "reason": "Both provide MySQL-compatible database",
            "alternatives": ["mariadb-server", "percona-server"],
        },
        "mariadb-server": {
            "conflicts": ["mysql-server"],
            "type": ConflictType.MUTUALLY_EXCLUSIVE,
            "reason": "Both provide MySQL-compatible database",
            "alternatives": ["mysql-server", "percona-server"],
        },
        "apache2": {
            "conflicts": ["nginx"],
            "type": ConflictType.PORT_CONFLICT,
            "reason": "Both use port 80/443 by default",
            "alternatives": ["Configure different ports", "Use reverse proxy"],
        },
        "nginx": {
            "conflicts": ["apache2"],
            "type": ConflictType.PORT_CONFLICT,
            "reason": "Both use port 80/443 by default",
            "alternatives": ["Configure different ports", "Use reverse proxy"],
        },
        "exim4": {
            "conflicts": ["postfix", "sendmail"],
            "type": ConflictType.PROVIDES_SAME,
            "reason": "All provide mail-transport-agent",
            "alternatives": ["postfix", "sendmail", "msmtp"],
        },
        "postfix": {
            "conflicts": ["exim4", "sendmail"],
            "type": ConflictType.PROVIDES_SAME,
            "reason": "All provide mail-transport-agent",
            "alternatives": ["exim4", "sendmail", "msmtp"],
        },
        "python3.11": {
            "conflicts": [],
            "type": ConflictType.VERSION_MISMATCH,
            "reason": "May conflict with packages requiring different Python version",
            "alternatives": ["Use pyenv", "Use virtual environments"],
        },
    }

    # Port to package mapping
    PORT_USAGE = {
        80: ["apache2", "nginx", "lighttpd", "caddy"],
        443: ["apache2", "nginx", "lighttpd", "caddy"],
        3306: ["mysql-server", "mariadb-server", "percona-server"],
        5432: ["postgresql"],
        6379: ["redis-server"],
        27017: ["mongodb"],
    }

    def __init__(self, resolver: "DependencyResolver"):
        """Initialize with reference to resolver."""
        self.resolver = resolver

    def predict_conflicts(
        self,
        packages_to_install: list[str],
        installed_packages: set[str] = None,
    ) -> list[Conflict]:
        """
        Predict conflicts for a set of packages.

        Args:
            packages_to_install: Packages being installed
            installed_packages: Currently installed packages

        Returns:
            List of predicted conflicts
        """
        conflicts = []
        installed = installed_packages or self.resolver.installed_packages

        all_packages = set(packages_to_install) | installed

        # Check known conflicts
        for pkg in packages_to_install:
            if pkg in self.KNOWN_CONFLICTS:
                known = self.KNOWN_CONFLICTS[pkg]
                for conflicting in known["conflicts"]:
                    if conflicting in all_packages:
                        conflicts.append(
                            Conflict(
                                package_a=pkg,
                                package_b=conflicting,
                                conflict_type=known["type"],
                                description=known["reason"],
                                alternatives=known.get("alternatives", []),
                                resolution_steps=self._get_resolution_steps(
                                    pkg, conflicting, known["type"]
                                ),
                            )
                        )

        # Check port conflicts
        conflicts.extend(self._check_port_conflicts(packages_to_install, installed))

        # Check apt conflicts metadata
        conflicts.extend(self._check_apt_conflicts(packages_to_install))

        return conflicts

    def _check_port_conflicts(
        self,
        packages_to_install: list[str],
        installed: set[str],
    ) -> list[Conflict]:
        """Check for port-based conflicts."""
        conflicts = []

        for port, port_packages in self.PORT_USAGE.items():
            installing = [p for p in packages_to_install if p in port_packages]
            already_installed = [p for p in port_packages if p in installed]

            if installing and already_installed:
                for new_pkg in installing:
                    for existing_pkg in already_installed:
                        if new_pkg != existing_pkg:
                            conflicts.append(
                                Conflict(
                                    package_a=new_pkg,
                                    package_b=existing_pkg,
                                    conflict_type=ConflictType.PORT_CONFLICT,
                                    description=f"Both use port {port}",
                                    alternatives=[
                                        f"Configure {new_pkg} to use different port",
                                        f"Stop {existing_pkg} before installing",
                                    ],
                                    resolution_steps=[
                                        f"sudo systemctl stop {existing_pkg}",
                                        f"sudo apt install {new_pkg}",
                                        f"Configure {new_pkg} to use alternate port",
                                        f"sudo systemctl start {existing_pkg}",
                                    ],
                                )
                            )

        return conflicts

    def _check_apt_conflicts(self, packages: list[str]) -> list[Conflict]:
        """Check conflicts using apt-cache."""
        conflicts = []

        for pkg in packages:
            try:
                result = subprocess.run(
                    ["apt-cache", "show", pkg],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if line.startswith("Conflicts:"):
                            conflicting = line.split(":", 1)[1].strip()
                            for c in conflicting.split(","):
                                c = c.strip().split()[0]  # Remove version
                                if self.resolver.is_package_installed(c):
                                    conflicts.append(
                                        Conflict(
                                            package_a=pkg,
                                            package_b=c,
                                            conflict_type=ConflictType.MUTUALLY_EXCLUSIVE,
                                            description=f"Declared conflict in package metadata",
                                            alternatives=[],
                                            resolution_steps=[
                                                f"sudo apt remove {c}",
                                                f"sudo apt install {pkg}",
                                            ],
                                        )
                                    )
            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                logger.debug(f"Error checking apt conflicts for {pkg}: {e}")

        return conflicts

    def _get_resolution_steps(
        self,
        pkg_a: str,
        pkg_b: str,
        conflict_type: ConflictType,
    ) -> list[str]:
        """Generate resolution steps for a conflict."""
        if conflict_type == ConflictType.MUTUALLY_EXCLUSIVE:
            return [
                f"Choose between {pkg_a} or {pkg_b}",
                f"To use {pkg_a}: sudo apt remove {pkg_b} && sudo apt install {pkg_a}",
                f"To use {pkg_b}: sudo apt remove {pkg_a} && sudo apt install {pkg_b}",
            ]
        elif conflict_type == ConflictType.PORT_CONFLICT:
            return [
                f"Option 1: Configure {pkg_a} to use a different port",
                f"Option 2: Stop {pkg_b} temporarily: sudo systemctl stop {pkg_b}",
                f"Option 3: Use a reverse proxy (nginx/caddy) in front of both",
            ]
        return []


# =============================================================================
# IMPACT COMMUNICATOR
# =============================================================================


class ImpactCommunicator:
    """
    Translates technical dependency information into plain language.

    Makes dependency impacts understandable to non-technical users.
    """

    # Plain language templates
    INSTALL_TEMPLATES = {
        ImpactSeverity.LOW: "Installing {package} is safe and won't affect other software.",
        ImpactSeverity.MEDIUM: (
            "Installing {package} will also install {count} other packages. "
            "This is normal and shouldn't cause problems."
        ),
        ImpactSeverity.HIGH: (
            "Installing {package} may change how {affected} works. "
            "You might notice some differences in behavior."
        ),
        ImpactSeverity.CRITICAL: (
            "⚠️ Installing {package} could cause problems with {affected}. "
            "We recommend backing up your system first."
        ),
    }

    REMOVE_TEMPLATES = {
        ImpactSeverity.LOW: "Removing {package} is safe. No other software depends on it.",
        ImpactSeverity.MEDIUM: (
            "Removing {package} will also remove {count} packages that depend on it."
        ),
        ImpactSeverity.HIGH: (
            "⚠️ Removing {package} will break {affected}. "
            "These programs won't work anymore."
        ),
        ImpactSeverity.CRITICAL: (
            "🛑 DANGER: Removing {package} could make your system unstable. "
            "{affected} are critical system components."
        ),
    }

    CONFLICT_TEMPLATES = {
        ConflictType.MUTUALLY_EXCLUSIVE: (
            "{pkg_a} and {pkg_b} cannot be installed together because they "
            "do the same thing. You need to choose one."
        ),
        ConflictType.PORT_CONFLICT: (
            "{pkg_a} and {pkg_b} both try to use the same network port. "
            "Only one can run at a time unless you configure them differently."
        ),
        ConflictType.PROVIDES_SAME: (
            "{pkg_a} and {pkg_b} both provide the same functionality. "
            "Your system only needs one of them."
        ),
        ConflictType.VERSION_MISMATCH: (
            "The version of {pkg_a} you want conflicts with {pkg_b}. "
            "You may need to upgrade or downgrade one of them."
        ),
    }

    def explain_impact(self, assessment: ImpactAssessment) -> str:
        """
        Generate plain language explanation for an impact.

        Args:
            assessment: The impact assessment to explain

        Returns:
            Human-readable explanation
        """
        if assessment.action == "install":
            templates = self.INSTALL_TEMPLATES
        else:
            templates = self.REMOVE_TEMPLATES

        template = templates.get(
            assessment.severity,
            templates[ImpactSeverity.MEDIUM],
        )

        affected_str = ", ".join(assessment.affected_packages[:3])
        if len(assessment.affected_packages) > 3:
            affected_str += f" and {len(assessment.affected_packages) - 3} more"

        return template.format(
            package=assessment.package,
            count=len(assessment.affected_packages),
            affected=affected_str,
        )

    def explain_conflict(self, conflict: Conflict) -> str:
        """
        Generate plain language explanation for a conflict.

        Args:
            conflict: The conflict to explain

        Returns:
            Human-readable explanation
        """
        template = self.CONFLICT_TEMPLATES.get(
            conflict.conflict_type,
            "{pkg_a} conflicts with {pkg_b}.",
        )

        explanation = template.format(
            pkg_a=conflict.package_a,
            pkg_b=conflict.package_b,
        )

        if conflict.alternatives:
            explanation += "\n\nAlternatives you can try:\n"
            for alt in conflict.alternatives:
                explanation += f"  • {alt}\n"

        return explanation

    def generate_summary(
        self,
        package: str,
        dependencies: list[Dependency],
        conflicts: list[Conflict],
    ) -> str:
        """
        Generate a complete plain-language summary.

        Args:
            package: Package being analyzed
            dependencies: List of dependencies
            conflicts: List of conflicts

        Returns:
            Complete summary in plain language
        """
        lines = []
        lines.append(f"📦 What happens when you install {package}?\n")

        # Dependencies summary
        missing = [d for d in dependencies if not d.is_satisfied]
        satisfied = [d for d in dependencies if d.is_satisfied]

        if missing:
            lines.append(f"📥 {len(missing)} additional packages will be installed:")
            for dep in missing[:5]:
                lines.append(f"   • {dep.name}")
            if len(missing) > 5:
                lines.append(f"   • ...and {len(missing) - 5} more")
            lines.append("")

        if satisfied:
            lines.append(
                f"✅ {len(satisfied)} required packages are already installed."
            )
            lines.append("")

        # Conflicts
        if conflicts:
            lines.append("⚠️ Potential issues detected:\n")
            for conflict in conflicts:
                lines.append(self.explain_conflict(conflict))
                lines.append("")
        else:
            lines.append("✅ No conflicts detected. Installation should be smooth.\n")

        return "\n".join(lines)


# =============================================================================
# ORPHAN PACKAGE MANAGER
# =============================================================================


class OrphanPackageManager:
    """
    Identifies and manages orphaned packages.

    Orphans are packages that:
    - Were installed as dependencies but no longer needed
    - Come from removed PPAs
    - Have no reverse dependencies
    """

    def __init__(self, resolver: "DependencyResolver"):
        """Initialize with reference to resolver."""
        self.resolver = resolver
        self.history_db = Path.home() / ".cortex" / "history.db"

    def find_orphans(self) -> list[OrphanPackage]:
        """
        Find all orphaned packages on the system.

        Returns:
            List of orphaned packages
        """
        orphans = []

        # Method 1: Use deborphan if available
        orphans.extend(self._find_with_deborphan())

        # Method 2: Check for packages with no reverse dependencies
        orphans.extend(self._find_no_rdeps())

        # Method 3: Check for packages from removed PPAs
        orphans.extend(self._find_removed_ppa_packages())

        # Deduplicate
        seen = set()
        unique_orphans = []
        for orphan in orphans:
            if orphan.name not in seen:
                seen.add(orphan.name)
                unique_orphans.append(orphan)

        return unique_orphans

    def _find_with_deborphan(self) -> list[OrphanPackage]:
        """Find orphans using deborphan command."""
        orphans = []

        try:
            result = subprocess.run(
                ["deborphan"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        orphans.append(
                            OrphanPackage(
                                name=line.strip(),
                                installed_version=self.resolver.get_installed_version(
                                    line.strip()
                                )
                                or "unknown",
                                reason="No packages depend on this library",
                            )
                        )
        except FileNotFoundError:
            logger.debug("deborphan not installed")
        except subprocess.TimeoutExpired:
            pass

        return orphans

    def _find_no_rdeps(self) -> list[OrphanPackage]:
        """Find packages with no reverse dependencies."""
        orphans = []

        # Get list of automatically installed packages
        try:
            result = subprocess.run(
                ["apt-mark", "showauto"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                auto_packages = set(result.stdout.strip().split("\n"))

                # Check each for reverse dependencies
                for pkg in list(auto_packages)[:50]:  # Limit for performance
                    if not pkg:
                        continue

                    rdeps_result = subprocess.run(
                        ["apt-cache", "rdepends", "--installed", pkg],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if rdeps_result.returncode == 0:
                        lines = rdeps_result.stdout.strip().split("\n")
                        # First line is package name, then "Reverse Depends:"
                        # Actual deps start at line 2
                        rdeps = [
                            l.strip()
                            for l in lines[2:]
                            if l.strip() and not l.strip().startswith("|")
                        ]

                        if len(rdeps) == 0:
                            orphans.append(
                                OrphanPackage(
                                    name=pkg,
                                    installed_version=self.resolver.get_installed_version(
                                        pkg
                                    )
                                    or "unknown",
                                    reason="Automatically installed with no dependents",
                                )
                            )
        except Exception as e:
            logger.debug(f"Error finding no-rdeps orphans: {e}")

        return orphans

    def _find_removed_ppa_packages(self) -> list[OrphanPackage]:
        """Find packages from PPAs that no longer exist."""
        orphans = []

        try:
            # Get list of installed packages and their sources
            result = subprocess.run(
                ["apt-cache", "policy"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                # Parse for packages from unavailable sources
                current_pkg = None
                for line in result.stdout.split("\n"):
                    if not line.startswith(" ") and ":" in line:
                        current_pkg = line.split(":")[0]
                    elif "ppa.launchpad.net" in line and "/404 " in line.lower():
                        if current_pkg:
                            orphans.append(
                                OrphanPackage(
                                    name=current_pkg,
                                    installed_version=self.resolver.get_installed_version(
                                        current_pkg
                                    )
                                    or "unknown",
                                    reason="PPA no longer available",
                                )
                            )
        except Exception as e:
            logger.debug(f"Error finding PPA orphans: {e}")

        return orphans

    def get_orphan_cleanup_commands(
        self,
        orphans: list[OrphanPackage],
        dry_run: bool = True,
    ) -> list[str]:
        """
        Generate commands to clean up orphan packages.

        Args:
            orphans: List of orphans to clean
            dry_run: If True, add --dry-run flag

        Returns:
            List of cleanup commands
        """
        commands = []
        dry_run_flag = " --dry-run" if dry_run else ""

        if orphans:
            package_names = " ".join(o.name for o in orphans)
            commands.append(f"sudo apt remove{dry_run_flag} {package_names}")

        # Also suggest autoremove
        commands.append(f"sudo apt autoremove{dry_run_flag}")

        return commands

    def estimate_space_savings(self, orphans: list[OrphanPackage]) -> int:
        """
        Estimate disk space that would be freed.

        Args:
            orphans: List of orphan packages

        Returns:
            Estimated bytes that would be freed
        """
        total_bytes = 0

        for orphan in orphans:
            try:
                result = subprocess.run(
                    [
                        "dpkg-query",
                        "-W",
                        "-f=${Installed-Size}",
                        orphan.name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    # Size is in KB
                    total_bytes += int(result.stdout.strip()) * 1024
            except Exception:
                pass

        return total_bytes


# =============================================================================
# MAIN DEPENDENCY RESOLVER
# =============================================================================


class DependencyResolver:
    """
    Resolves package dependencies intelligently with visual feedback.

    Combines dependency analysis, conflict prediction, impact communication,
    and orphan management into a unified interface.
    """

    # Common dependency patterns
    DEPENDENCY_PATTERNS = {
        "docker": {
            "direct": ["containerd", "docker-ce-cli", "docker-buildx-plugin"],
            "system": ["iptables", "ca-certificates", "curl", "gnupg"],
        },
        "postgresql": {
            "direct": ["postgresql-common", "postgresql-client"],
            "optional": ["postgresql-contrib"],
        },
        "nginx": {"direct": [], "runtime": ["libc6", "libpcre3", "zlib1g"]},
        "mysql-server": {
            "direct": ["mysql-client", "mysql-common"],
            "system": ["libaio1", "libmecab2"],
        },
        "python3-pip": {
            "direct": ["python3", "python3-setuptools"],
            "system": ["python3-wheel"],
        },
        "nodejs": {"direct": [], "optional": ["npm"]},
        "redis-server": {"direct": [], "runtime": ["libc6", "libjemalloc2"]},
        "apache2": {
            "direct": ["apache2-bin", "apache2-data", "apache2-utils"],
            "runtime": ["libapr1", "libaprutil1"],
        },
    }

    def __init__(self, dry_run: bool = False):
        """
        Initialize the dependency resolver.

        Args:
            dry_run: If True, no changes will be made to the system
        """
        self._cache_lock = threading.Lock()
        self._packages_lock = threading.Lock()
        self.dependency_cache: dict[str, DependencyGraph] = {}
        self.installed_packages: set[str] = set()
        self.dry_run = dry_run

        # Initialize sub-components
        self.tree_renderer = VisualTreeRenderer()
        self.conflict_predictor = ConflictPredictor(self)
        self.impact_communicator = ImpactCommunicator()
        self.orphan_manager = OrphanPackageManager(self)

        # Audit log path
        self.history_db = Path.home() / ".cortex" / "history.db"
        self.history_db.parent.mkdir(parents=True, exist_ok=True)

        self._refresh_installed_packages()

    def _run_command(self, cmd: list[str]) -> tuple[bool, str, str]:
        """Execute command and return success, stdout, stderr."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "", "Command timed out")
        except Exception as e:
            return (False, "", str(e))

    def _refresh_installed_packages(self) -> None:
        """Refresh cache of installed packages."""
        logger.info("Refreshing installed packages cache...")
        success, stdout, _ = self._run_command(["dpkg", "-l"])

        if success:
            new_packages = set()
            for line in stdout.split("\n"):
                if line.startswith("ii"):
                    parts = line.split()
                    if len(parts) >= 2:
                        new_packages.add(parts[1])

            with self._packages_lock:
                self.installed_packages = new_packages
                logger.info(f"Found {len(self.installed_packages)} installed packages")

    def is_package_installed(self, package_name: str) -> bool:
        """Check if package is installed (thread-safe)."""
        with self._packages_lock:
            return package_name in self.installed_packages

    def get_installed_version(self, package_name: str) -> Optional[str]:
        """Get version of installed package."""
        if not self.is_package_installed(package_name):
            return None

        success, stdout, _ = self._run_command(
            ["dpkg-query", "-W", "-f=${Version}", package_name]
        )

        return stdout.strip() if success else None

    def get_apt_dependencies(self, package_name: str) -> list[Dependency]:
        """Get dependencies from apt-cache."""
        dependencies = []

        success, stdout, stderr = self._run_command(
            ["apt-cache", "depends", package_name]
        )

        if not success:
            logger.warning(f"Could not get dependencies for {package_name}: {stderr}")
            return dependencies

        current_dep_name = None
        for line in stdout.split("\n"):
            line = line.strip()

            if line.startswith("Depends:"):
                current_dep_name = line.split(":", 1)[1].strip()
                if "|" in current_dep_name:
                    current_dep_name = current_dep_name.split("|")[0].strip()

                current_dep_name = re.sub(r"\s*\(.*?\)", "", current_dep_name)

                is_installed = self.is_package_installed(current_dep_name)
                installed_ver = (
                    self.get_installed_version(current_dep_name)
                    if is_installed
                    else None
                )

                dependencies.append(
                    Dependency(
                        name=current_dep_name,
                        reason="Required dependency",
                        is_satisfied=is_installed,
                        installed_version=installed_ver,
                    )
                )

            elif line.startswith("Recommends:"):
                dep_name = line.split(":", 1)[1].strip()
                dep_name = re.sub(r"\s*\(.*?\)", "", dep_name)

                dependencies.append(
                    Dependency(
                        name=dep_name,
                        reason="Recommended package",
                        is_satisfied=self.is_package_installed(dep_name),
                        is_optional=True,
                    )
                )

        return dependencies

    def get_reverse_dependencies(self, package_name: str) -> list[str]:
        """Get packages that depend on this package."""
        rdeps = []

        success, stdout, _ = self._run_command(
            ["apt-cache", "rdepends", "--installed", package_name]
        )

        if success:
            lines = stdout.strip().split("\n")
            # Skip first two lines (package name and "Reverse Depends:")
            for line in lines[2:]:
                line = line.strip()
                if line and not line.startswith("|"):
                    rdeps.append(line)

        return rdeps

    def resolve_dependencies(
        self,
        package_name: str,
        recursive: bool = True,
    ) -> DependencyGraph:
        """
        Resolve all dependencies for a package.

        Args:
            package_name: Package to resolve dependencies for
            recursive: Whether to resolve transitive dependencies
        """
        logger.info(f"Resolving dependencies for {package_name}...")

        with self._cache_lock:
            if package_name in self.dependency_cache:
                logger.info(f"Using cached dependencies for {package_name}")
                return self.dependency_cache[package_name]

        # Get dependencies from multiple sources
        apt_deps = self.get_apt_dependencies(package_name)
        predefined_deps = self._get_predefined_dependencies(package_name)

        # Merge dependencies
        all_deps: dict[str, Dependency] = {}
        for dep in predefined_deps + apt_deps:
            if dep.name not in all_deps:
                all_deps[dep.name] = dep

        direct_dependencies = list(all_deps.values())

        # Resolve transitive dependencies
        transitive_deps: dict[str, Dependency] = {}
        if recursive:
            for dep in direct_dependencies:
                if not dep.is_satisfied:
                    sub_deps = self.get_apt_dependencies(dep.name)
                    for sub_dep in sub_deps:
                        sub_dep.depth = dep.depth + 1
                        if (
                            sub_dep.name not in all_deps
                            and sub_dep.name not in transitive_deps
                        ):
                            transitive_deps[sub_dep.name] = sub_dep

        all_dependencies = list(all_deps.values()) + list(transitive_deps.values())

        # Predict conflicts
        packages_to_install = [d.name for d in all_dependencies if not d.is_satisfied]
        packages_to_install.append(package_name)
        conflicts = self.conflict_predictor.predict_conflicts(packages_to_install)

        # Get reverse dependencies
        rdeps = self.get_reverse_dependencies(package_name)

        # Calculate installation order
        installation_order = self._calculate_installation_order(
            package_name, all_dependencies
        )

        graph = DependencyGraph(
            package_name=package_name,
            direct_dependencies=direct_dependencies,
            all_dependencies=all_dependencies,
            conflicts=conflicts,
            installation_order=installation_order,
            reverse_dependencies=rdeps,
        )

        with self._cache_lock:
            self.dependency_cache[package_name] = graph

        return graph

    def _get_predefined_dependencies(self, package_name: str) -> list[Dependency]:
        """Get dependencies from predefined patterns."""
        dependencies = []

        if package_name not in self.DEPENDENCY_PATTERNS:
            return dependencies

        pattern = self.DEPENDENCY_PATTERNS[package_name]

        for dep in pattern.get("direct", []):
            is_installed = self.is_package_installed(dep)
            dependencies.append(
                Dependency(
                    name=dep,
                    reason="Required dependency",
                    is_satisfied=is_installed,
                    installed_version=(
                        self.get_installed_version(dep) if is_installed else None
                    ),
                )
            )

        for dep in pattern.get("system", []):
            is_installed = self.is_package_installed(dep)
            dependencies.append(
                Dependency(
                    name=dep,
                    reason="System dependency",
                    is_satisfied=is_installed,
                    installed_version=(
                        self.get_installed_version(dep) if is_installed else None
                    ),
                )
            )

        for dep in pattern.get("optional", []):
            is_installed = self.is_package_installed(dep)
            dependencies.append(
                Dependency(
                    name=dep,
                    reason="Optional enhancement",
                    is_satisfied=is_installed,
                    is_optional=True,
                )
            )

        return dependencies

    def _calculate_installation_order(
        self,
        package_name: str,
        dependencies: list[Dependency],
    ) -> list[str]:
        """Calculate optimal installation order."""
        no_deps = []
        has_deps = []

        for dep in dependencies:
            if not dep.is_satisfied:
                if "lib" in dep.name or dep.name in [
                    "ca-certificates",
                    "curl",
                    "gnupg",
                ]:
                    no_deps.append(dep.name)
                else:
                    has_deps.append(dep.name)

        order = no_deps + has_deps

        if package_name not in order:
            order.append(package_name)

        return order

    def analyze_installation(self, package_name: str) -> dict:
        """
        Perform comprehensive installation analysis.

        Args:
            package_name: Package to analyze

        Returns:
            Complete analysis with tree, conflicts, impact, and recommendations
        """
        graph = self.resolve_dependencies(package_name)

        # Generate visual tree
        tree = self.tree_renderer.render_tree(
            package_name, graph.all_dependencies, graph.conflicts
        )

        # Generate impact assessment
        missing = [d for d in graph.all_dependencies if not d.is_satisfied]
        severity = ImpactSeverity.LOW
        if len(missing) > 10:
            severity = ImpactSeverity.MEDIUM
        if graph.conflicts:
            severity = ImpactSeverity.HIGH

        assessment = ImpactAssessment(
            package=package_name,
            action="install",
            severity=severity,
            affected_packages=[d.name for d in missing],
            plain_language_explanation=self.impact_communicator.explain_impact(
                ImpactAssessment(
                    package=package_name,
                    action="install",
                    severity=severity,
                    affected_packages=[d.name for d in missing],
                    plain_language_explanation="",
                    recommendation="",
                )
            ),
            recommendation=(
                "Proceed with installation"
                if not graph.conflicts
                else "Resolve conflicts first"
            ),
        )

        # Generate plain language summary
        summary = self.impact_communicator.generate_summary(
            package_name, graph.all_dependencies, graph.conflicts
        )

        return {
            "package": package_name,
            "tree": tree,
            "summary": summary,
            "dependencies": {
                "total": len(graph.all_dependencies),
                "missing": len(missing),
                "satisfied": len(graph.all_dependencies) - len(missing),
            },
            "conflicts": [
                {
                    "packages": [c.package_a, c.package_b],
                    "type": c.conflict_type.value,
                    "description": c.description,
                    "alternatives": c.alternatives,
                    "resolution": c.resolution_steps,
                }
                for c in graph.conflicts
            ],
            "impact": {
                "severity": severity.value,
                "explanation": assessment.plain_language_explanation,
                "recommendation": assessment.recommendation,
            },
            "installation_order": graph.installation_order,
            "reverse_dependencies": graph.reverse_dependencies,
        }

    def analyze_removal(self, package_name: str) -> dict:
        """
        Analyze impact of removing a package.

        Args:
            package_name: Package to analyze for removal

        Returns:
            Complete removal impact analysis
        """
        rdeps = self.get_reverse_dependencies(package_name)

        # Determine severity
        severity = ImpactSeverity.LOW
        if len(rdeps) > 0:
            severity = ImpactSeverity.MEDIUM
        if len(rdeps) > 5:
            severity = ImpactSeverity.HIGH

        # Check for critical packages
        critical = ["systemd", "apt", "dpkg", "libc6", "coreutils"]
        if package_name in critical or any(r in critical for r in rdeps):
            severity = ImpactSeverity.CRITICAL

        assessment = ImpactAssessment(
            package=package_name,
            action="remove",
            severity=severity,
            affected_packages=rdeps,
            plain_language_explanation="",
            recommendation="",
        )
        assessment.plain_language_explanation = (
            self.impact_communicator.explain_impact(assessment)
        )

        if severity == ImpactSeverity.CRITICAL:
            assessment.recommendation = "DO NOT REMOVE - System critical"
        elif severity == ImpactSeverity.HIGH:
            assessment.recommendation = (
                "Carefully review affected packages before removing"
            )
        elif len(rdeps) > 0:
            assessment.recommendation = f"Will also affect: {', '.join(rdeps[:3])}"
        else:
            assessment.recommendation = "Safe to remove"

        return {
            "package": package_name,
            "reverse_dependencies": rdeps,
            "impact": {
                "severity": severity.value,
                "explanation": assessment.plain_language_explanation,
                "recommendation": assessment.recommendation,
            },
            "would_break": rdeps,
            "safe_to_remove": severity in [ImpactSeverity.LOW, ImpactSeverity.MEDIUM],
        }

    def find_orphans(self) -> list[dict]:
        """
        Find orphaned packages on the system.

        Returns:
            List of orphan package information
        """
        orphans = self.orphan_manager.find_orphans()
        space_savings = self.orphan_manager.estimate_space_savings(orphans)

        return {
            "orphans": [
                {
                    "name": o.name,
                    "version": o.installed_version,
                    "reason": o.reason,
                }
                for o in orphans
            ],
            "total_count": len(orphans),
            "estimated_space_mb": space_savings / (1024 * 1024),
            "cleanup_commands": self.orphan_manager.get_orphan_cleanup_commands(
                orphans, dry_run=self.dry_run
            ),
        }

    def print_visual_tree(self, package_name: str) -> None:
        """Print visual dependency tree."""
        graph = self.resolve_dependencies(package_name)
        tree = self.tree_renderer.render_tree(
            package_name, graph.all_dependencies, graph.conflicts
        )
        print(tree)

    def _log_to_history(self, action: str, package: str, details: dict) -> None:
        """Log action to history database."""
        try:
            conn = sqlite3.connect(str(self.history_db))
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dependency_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    action TEXT,
                    package TEXT,
                    details TEXT
                )
            """
            )

            cursor.execute(
                """
                INSERT INTO dependency_actions (timestamp, action, package, details)
                VALUES (?, ?, ?, ?)
            """,
                (datetime.now().isoformat(), action, package, json.dumps(details)),
            )

            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Could not log to history: {e}")


# =============================================================================
# CLI INTERFACE
# =============================================================================


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Dependency Conflict Resolver with Visual Tree",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s docker --tree           Show dependency tree for docker
  %(prog)s nginx --analyze         Full analysis with conflict detection
  %(prog)s mysql-server --remove   Analyze removal impact
  %(prog)s --orphans               Find orphaned packages
  %(prog)s --orphans --clean       Generate cleanup commands
        """,
    )

    parser.add_argument("package", nargs="?", help="Package name to analyze")
    parser.add_argument("--tree", action="store_true", help="Show visual dependency tree")
    parser.add_argument(
        "--analyze", action="store_true", help="Full installation analysis"
    )
    parser.add_argument(
        "--remove", action="store_true", help="Analyze removal impact"
    )
    parser.add_argument("--orphans", action="store_true", help="Find orphaned packages")
    parser.add_argument(
        "--clean", action="store_true", help="Generate cleanup commands for orphans"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run mode (no changes)"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--export", metavar="FILE", help="Export analysis to JSON file"
    )

    args = parser.parse_args()

    resolver = DependencyResolver(dry_run=args.dry_run)

    # Handle orphan management
    if args.orphans:
        result = resolver.find_orphans()

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("\n🔸 Orphaned Packages")
            print("=" * 60)

            if result["orphans"]:
                for orphan in result["orphans"]:
                    print(f"  • {orphan['name']} ({orphan['version']})")
                    print(f"    Reason: {orphan['reason']}")

                print(f"\nTotal: {result['total_count']} packages")
                print(f"Estimated space: {result['estimated_space_mb']:.1f} MB")

                if args.clean:
                    print("\n💻 Cleanup commands:")
                    for cmd in result["cleanup_commands"]:
                        print(f"  {cmd}")
            else:
                print("  No orphaned packages found!")

        return

    # Require package for other commands
    if not args.package:
        parser.print_help()
        return

    # Visual tree
    if args.tree:
        print(f"\n📦 Dependency Tree: {args.package}")
        print("=" * 60)
        resolver.print_visual_tree(args.package)
        return

    # Removal analysis
    if args.remove:
        result = resolver.analyze_removal(args.package)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n🗑️ Removal Impact: {args.package}")
            print("=" * 60)
            print(f"\nSeverity: {result['impact']['severity'].upper()}")
            print(f"\n{result['impact']['explanation']}")
            print(f"\nRecommendation: {result['impact']['recommendation']}")

            if result["reverse_dependencies"]:
                print(f"\n⚠️ Would break {len(result['reverse_dependencies'])} packages:")
                for pkg in result["reverse_dependencies"][:10]:
                    print(f"  • {pkg}")
                if len(result["reverse_dependencies"]) > 10:
                    print(
                        f"  • ...and {len(result['reverse_dependencies']) - 10} more"
                    )

        return

    # Full analysis
    if args.analyze:
        result = resolver.analyze_installation(args.package)

        if args.json:
            print(json.dumps(result, indent=2))
        elif args.export:
            with open(args.export, "w") as f:
                json.dump(result, f, indent=2)
            print(f"Analysis exported to {args.export}")
        else:
            print(result["summary"])
            print("\n" + result["tree"])

            if result["conflicts"]:
                print("\n⚠️ Conflicts Detected:")
                for c in result["conflicts"]:
                    print(f"\n  {c['packages'][0]} ↔ {c['packages'][1]}")
                    print(f"  Type: {c['type']}")
                    print(f"  {c['description']}")
                    if c["alternatives"]:
                        print("  Alternatives:")
                        for alt in c["alternatives"]:
                            print(f"    • {alt}")

        return

    # Default: show summary
    graph = resolver.resolve_dependencies(args.package)
    print(f"\n📦 {args.package} - Dependency Summary")
    print("=" * 60)
    print(f"Direct dependencies: {len(graph.direct_dependencies)}")
    print(f"Total dependencies: {len(graph.all_dependencies)}")
    satisfied = sum(1 for d in graph.all_dependencies if d.is_satisfied)
    print(f"✅ Satisfied: {satisfied}")
    print(f"❌ Missing: {len(graph.all_dependencies) - satisfied}")

    if graph.conflicts:
        print(f"\n⚠️ {len(graph.conflicts)} potential conflict(s) detected!")
        print("Run with --analyze for details")


if __name__ == "__main__":
    main()
