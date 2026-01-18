#!/usr/bin/env python3
"""
Uninstall Impact Analysis Engine for Cortex Linux

Performs pre-uninstall impact analysis to evaluate dependencies,
affected services, and cascading effects before package removal.

Components:
- DependencyGraphBuilder: Constructs directed graph with reverse lookup
- ImpactAnalyzer: Calculates cascade depth and blast radius
- ServiceImpactMapper: Maps packages to services
- RecommendationEngine: Suggests safe uninstall alternatives
"""

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Constants
SERVICE_SUFFIX = ".service"

# Module logger - does not configure global logging when imported
logger = logging.getLogger(__name__)


class ImpactSeverity(Enum):
    """Severity level of uninstall impact"""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ServiceStatus(Enum):
    """Status of a service"""

    RUNNING = "running"
    STOPPED = "stopped"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass
class PackageNode:
    """Represents a package in the dependency graph"""

    name: str
    version: str | None = None
    is_installed: bool = False
    is_essential: bool = False
    is_manually_installed: bool = False
    description: str = ""


@dataclass
class ServiceInfo:
    """Information about a system service"""

    name: str
    status: ServiceStatus
    package: str  # Package that provides this service
    description: str = ""
    is_critical: bool = False


@dataclass
class DependencyEdge:
    """Edge in the dependency graph"""

    from_package: str
    to_package: str
    dependency_type: str = "depends"  # depends, recommends, suggests, pre-depends


@dataclass
class ImpactResult:
    """Result of impact analysis for a package removal"""

    target_package: str
    direct_dependents: list[str] = field(default_factory=list)
    transitive_dependents: list[str] = field(default_factory=list)
    affected_services: list[ServiceInfo] = field(default_factory=list)
    orphaned_packages: list[str] = field(default_factory=list)
    cascade_packages: list[str] = field(default_factory=list)
    severity: ImpactSeverity = ImpactSeverity.SAFE
    total_affected: int = 0
    cascade_depth: int = 0
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    safe_to_remove: bool = True


@dataclass
class RemovalPlan:
    """Plan for package removal"""

    target_package: str
    packages_to_remove: list[str] = field(default_factory=list)
    autoremove_candidates: list[str] = field(default_factory=list)
    config_files_affected: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    estimated_freed_space: str = ""


class DependencyGraphBuilder:
    """
    Constructs a directed graph of packages with support for reverse dependency lookup.

    The graph supports:
    - Forward dependencies (what a package depends on)
    - Reverse dependencies (what depends on a package)
    - Transitive dependency resolution
    - File-based caching for faster subsequent loads
    """

    CACHE_FILE = Path.home() / ".cortex" / "dep_graph_cache.json"
    CACHE_MAX_AGE_SECONDS = 3600  # 1 hour

    def __init__(self, use_cache: bool = True):
        self._lock = threading.Lock()
        self._forward_graph: dict[str, set[str]] = {}  # package -> dependencies
        self._reverse_graph: dict[str, set[str]] = {}  # package -> dependents
        self._package_info: dict[str, PackageNode] = {}
        self._installed_packages: set[str] = set()
        self._essential_packages: set[str] = set()
        self._manual_packages: set[str] = set()
        self._initialized = False
        self._use_cache = use_cache

    def _run_command(self, cmd: list[str], timeout: int = 30) -> tuple[bool, str, str]:
        """Execute command and return (success, stdout, stderr)"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "", "Command timed out")
        except FileNotFoundError:
            return (False, "", f"Command not found: {cmd[0]}")
        except Exception as e:
            return (False, "", str(e))

    def initialize(self, force_refresh: bool = False) -> None:
        """Initialize the dependency graph with system packages"""
        with self._lock:
            if self._initialized and not force_refresh:
                return

            # Try loading from cache first (much faster)
            if self._use_cache and not force_refresh and self._load_cache():
                self._initialized = True
                logger.info(
                    f"Dependency graph loaded from cache: {len(self._installed_packages)} packages"
                )
                return

            logger.info("Building dependency graph...")
            self._load_installed_packages()
            self._load_essential_packages()
            self._load_manual_packages()
            self._initialized = True

            # Save to cache for next time
            if self._use_cache:
                self._save_cache()

            logger.info(f"Dependency graph built: {len(self._installed_packages)} packages")

    def _load_cache(self) -> bool:
        """Load dependency graph from cache file"""
        try:
            if not self.CACHE_FILE.exists():
                return False

            # Check cache age
            cache_age = time.time() - self.CACHE_FILE.stat().st_mtime
            if cache_age > self.CACHE_MAX_AGE_SECONDS:
                logger.debug("Cache expired, rebuilding...")
                return False

            with open(self.CACHE_FILE) as f:
                data = json.load(f)

            self._installed_packages = set(data.get("installed", []))
            self._essential_packages = set(data.get("essential", []))
            self._manual_packages = set(data.get("manual", []))
            return True
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.debug(f"Cache load failed: {e}")
            return False

    def _save_cache(self) -> None:
        """Save dependency graph to cache file"""
        try:
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "installed": list(self._installed_packages),
                "essential": list(self._essential_packages),
                "manual": list(self._manual_packages),
                "timestamp": time.time(),
            }
            with open(self.CACHE_FILE, "w") as f:
                json.dump(data, f)
        except OSError as e:
            logger.debug(f"Cache save failed: {e}")

    def _load_installed_packages(self) -> None:
        """Load list of installed packages"""
        success, stdout, _ = self._run_command(["dpkg-query", "-W", "-f=${Package}\n"])
        if success:
            self._installed_packages = {pkg.strip() for pkg in stdout.split("\n") if pkg.strip()}

    def _load_essential_packages(self) -> None:
        """Load list of essential packages"""
        success, stdout, _ = self._run_command(["dpkg-query", "-W", "-f=${Package} ${Essential}\n"])
        if success:
            for line in stdout.split("\n"):
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1].lower() == "yes":
                    self._essential_packages.add(parts[0])

    def _load_manual_packages(self) -> None:
        """Load list of manually installed packages (not auto-installed as dependencies)"""
        success, stdout, _ = self._run_command(["apt-mark", "showmanual"])
        if success:
            self._manual_packages = {pkg.strip() for pkg in stdout.split("\n") if pkg.strip()}

    def get_package_info(self, package_name: str) -> PackageNode | None:
        """Get information about a specific package"""
        if package_name in self._package_info:
            return self._package_info[package_name]

        success, stdout, _ = self._run_command(
            ["dpkg-query", "-W", "-f=${Package}|${Version}|${Description}", package_name]
        )

        if not success:
            return None

        parts = stdout.strip().split("|")
        if len(parts) >= 2:
            node = PackageNode(
                name=parts[0],
                version=parts[1],
                is_installed=package_name in self._installed_packages,
                is_essential=package_name in self._essential_packages,
                is_manually_installed=package_name in self._manual_packages,
                description=parts[2] if len(parts) > 2 else "",
            )
            self._package_info[package_name] = node
            return node

        return None

    def get_dependencies(self, package_name: str) -> list[str]:
        """Get forward dependencies of a package (what it depends on)"""
        if package_name in self._forward_graph:
            return list(self._forward_graph[package_name])

        dependencies = set()
        success, stdout, _ = self._run_command(["apt-cache", "depends", package_name])

        if success:
            for line in stdout.split("\n"):
                dep = self._parse_dependency_line(line.strip())
                if dep:
                    dependencies.add(dep)

        self._forward_graph[package_name] = dependencies
        return list(dependencies)

    def _parse_dependency_line(self, line: str) -> str | None:
        """Parse a single dependency line and return cleaned package name."""
        if not line.startswith(("Depends:", "PreDepends:")):
            return None

        dep = line.split(":", 1)[1].strip()
        # Handle alternatives (package1 | package2) - take first option
        if "|" in dep:
            dep = dep.split("|")[0].strip()
        # Remove version constraints without regex (safer than regex)
        dep = self._remove_version_constraints(dep)

        if dep and not dep.startswith("<"):
            return dep
        return None

    def _remove_version_constraints(self, dep: str) -> str:
        """Remove version constraints like (>= 1.0) and <pkg> from dependency string.

        Uses string operations instead of regex to avoid any ReDoS concerns.
        """
        result = []
        i = 0
        paren_depth = 0
        angle_depth = 0

        while i < len(dep):
            char = dep[i]
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth = max(0, paren_depth - 1)
            elif char == "<":
                angle_depth += 1
            elif char == ">":
                angle_depth = max(0, angle_depth - 1)
            elif paren_depth == 0 and angle_depth == 0:
                result.append(char)
            i += 1

        return "".join(result).strip()

    def get_reverse_dependencies(self, package_name: str) -> list[str]:
        """Get reverse dependencies (what depends on this package)"""
        if package_name in self._reverse_graph:
            return list(self._reverse_graph[package_name])

        dependents = set()
        success, stdout, _ = self._run_command(["apt-cache", "rdepends", package_name])

        if success:
            lines = stdout.split("\n")
            # Skip header line
            for line in lines[1:]:
                line = line.strip()
                # Filter out version constraints and markers
                if line and not line.startswith("|") and not line.startswith("<"):
                    # Only include installed packages
                    if line in self._installed_packages:
                        dependents.add(line)

        self._reverse_graph[package_name] = dependents
        return list(dependents)

    def get_transitive_dependents(
        self, package_name: str, max_depth: int = 10
    ) -> tuple[list[str], int]:
        """
        Get all packages that transitively depend on the target.
        Returns (list of dependents, cascade depth)
        """
        visited = set()
        all_dependents = []
        current_level = {package_name}
        depth = 0

        while current_level and depth < max_depth:
            next_level = set()
            for pkg in current_level:
                direct_deps = self.get_reverse_dependencies(pkg)
                for dep in direct_deps:
                    if dep not in visited and dep != package_name:
                        visited.add(dep)
                        all_dependents.append(dep)
                        next_level.add(dep)
            current_level = next_level
            if next_level:
                depth += 1

        return all_dependents, depth

    def is_essential(self, package_name: str) -> bool:
        """Check if a package is marked as essential"""
        return package_name in self._essential_packages

    def is_installed(self, package_name: str) -> bool:
        """Check if a package is installed"""
        return package_name in self._installed_packages

    def is_manually_installed(self, package_name: str) -> bool:
        """Check if a package was manually installed (not as a dependency)"""
        return package_name in self._manual_packages


class ServiceImpactMapper:
    """
    Maps packages to services and predicts service impact from package removal.
    """

    # Known package-to-service mappings
    PACKAGE_SERVICE_MAP = {
        # Web servers
        "nginx": ["nginx"],
        "nginx-core": ["nginx"],
        "apache2": ["apache2"],
        "apache2-bin": ["apache2"],
        # Databases
        "mysql-server": ["mysql", "mysqld"],
        "mariadb-server": ["mariadb", "mysql"],
        "postgresql": ["postgresql", "postgresql@*"],
        "postgresql-14": ["postgresql", "postgresql@14-main"],
        "redis-server": ["redis-server", "redis"],
        "mongodb-server": ["mongod", "mongodb"],
        # Application servers
        "tomcat9": ["tomcat9"],
        "uwsgi": ["uwsgi"],
        "gunicorn": ["gunicorn"],
        # System services
        "openssh-server": ["ssh", "sshd"],
        "systemd": ["systemd-*"],
        "cron": ["cron", "crond"],
        "rsyslog": ["rsyslog"],
        "docker.io": ["docker"],
        "docker-ce": ["docker"],
        "containerd": ["containerd"],
        # Language runtimes
        "python3": [],  # Not a service but critical
        "nodejs": [],  # Not a service but may affect apps
        # Networking
        "network-manager": ["NetworkManager"],
        "avahi-daemon": ["avahi-daemon"],
        "cups": ["cups"],
        # Mail
        "postfix": ["postfix"],
        "exim4": ["exim4"],
    }

    # Critical services that should trigger high severity
    CRITICAL_SERVICES = {
        "ssh",
        "sshd",
        "systemd",
        "NetworkManager",
        "docker",
        "postgresql",
        "mysql",
        "mysqld",
        "nginx",
        "apache2",
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._service_cache: dict[str, ServiceInfo] = {}

    def _run_command(self, cmd: list[str], timeout: int = 10) -> tuple[bool, str, str]:
        """Execute command and return (success, stdout, stderr)"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return (result.returncode == 0, result.stdout, result.stderr)
        except (subprocess.TimeoutExpired, OSError) as e:
            return (False, "", str(e))

    def get_service_status(self, service_name: str) -> ServiceStatus:
        """Get the current status of a service"""
        success, stdout, _ = self._run_command(["systemctl", "is-active", service_name])

        if not success:
            # Check if service exists
            exists_success, _, _ = self._run_command(["systemctl", "cat", service_name])
            if not exists_success:
                return ServiceStatus.NOT_FOUND
            return ServiceStatus.STOPPED

        status = stdout.strip().lower()
        if status == "active":
            return ServiceStatus.RUNNING
        elif status in ("inactive", "failed"):
            return ServiceStatus.STOPPED
        return ServiceStatus.UNKNOWN

    def get_services_for_package(self, package_name: str) -> list[ServiceInfo]:
        """Get list of services associated with a package"""
        services = []

        # Check predefined mappings
        service_names = self.PACKAGE_SERVICE_MAP.get(package_name, [])

        # Also try to detect services from package files
        if not service_names:
            service_names = self._detect_services_from_package(package_name)

        for service_name in service_names:
            # Handle wildcard patterns
            if "*" in service_name:
                matched_services = self._expand_service_pattern(service_name)
                for svc in matched_services:
                    services.append(self._create_service_info(svc, package_name))
            else:
                services.append(self._create_service_info(service_name, package_name))

        return services

    def _detect_services_from_package(self, package_name: str) -> list[str]:
        """Detect service files provided by a package"""
        services = []
        success, stdout, _ = self._run_command(["dpkg-query", "-L", package_name])

        if success:
            for line in stdout.split("\n"):
                line = line.strip()
                # Look for systemd service files
                if "/systemd/" in line and line.endswith(SERVICE_SUFFIX):
                    service_name = line.split("/")[-1].replace(SERVICE_SUFFIX, "")
                    services.append(service_name)

        return services

    def _expand_service_pattern(self, pattern: str) -> list[str]:
        """Expand service patterns like postgresql@*"""
        services = []
        base_pattern = pattern.replace("*", "")

        success, stdout, _ = self._run_command(
            ["systemctl", "list-units", "--type=service", "--all", "--no-legend"]
        )

        if success:
            for line in stdout.split("\n"):
                if line.strip():
                    service_name = line.split()[0].replace(SERVICE_SUFFIX, "")
                    if base_pattern in service_name:
                        services.append(service_name)

        return services or [pattern.replace("*", "")]

    def _create_service_info(self, service_name: str, package_name: str) -> ServiceInfo:
        """Create ServiceInfo object for a service"""
        with self._lock:
            if service_name in self._service_cache:
                return self._service_cache[service_name]

        status = self.get_service_status(service_name)
        is_critical = service_name in self.CRITICAL_SERVICES

        info = ServiceInfo(
            name=service_name,
            status=status,
            package=package_name,
            description=f"Service provided by {package_name}",
            is_critical=is_critical,
        )

        with self._lock:
            self._service_cache[service_name] = info

        return info

    def get_affected_services(self, packages: list[str]) -> list[ServiceInfo]:
        """Get all services affected by removing a list of packages"""
        affected = []
        seen_services = set()

        for package in packages:
            services = self.get_services_for_package(package)
            for service in services:
                if service.name not in seen_services:
                    seen_services.add(service.name)
                    affected.append(service)

        return affected


class RecommendationEngine:
    """
    Provides recommendations for safe package removal.
    """

    def __init__(self, graph_builder: DependencyGraphBuilder):
        self.graph = graph_builder

    def get_recommendations(self, impact: ImpactResult) -> list[str]:
        """Generate recommendations based on impact analysis"""
        recommendations = []

        # Check severity and provide appropriate recommendations
        if impact.severity == ImpactSeverity.CRITICAL:
            recommendations.append(
                "⚠️  CRITICAL: This package is essential to the system. "
                "Removal may break your system. Consider keeping it installed."
            )

        if impact.severity == ImpactSeverity.HIGH:
            recommendations.append(
                "⚠️  HIGH IMPACT: Many packages depend on this. "
                "Consider removing dependent packages first."
            )

        # Service-related recommendations
        running_services = [
            s for s in impact.affected_services if s.status == ServiceStatus.RUNNING
        ]
        if running_services:
            service_names = ", ".join(s.name for s in running_services[:3])
            if len(running_services) > 3:
                service_names += f" (+{len(running_services) - 3} more)"
            recommendations.append(f"Stop affected services before removal: {service_names}")

        # Critical services
        critical_services = [s for s in impact.affected_services if s.is_critical]
        if critical_services:
            recommendations.append(
                "⚠️  Critical services will be affected. Ensure you have "
                "alternative access (e.g., physical console) before proceeding."
            )

        # Dependent package recommendations
        if len(impact.direct_dependents) > 5:
            recommendations.append(
                f"Consider removing these dependent packages first: "
                f"{', '.join(impact.direct_dependents[:5])}"
            )

        # Orphaned packages
        if impact.orphaned_packages:
            recommendations.append(
                f"Run 'apt autoremove' after removal to clean up "
                f"{len(impact.orphaned_packages)} orphaned package(s)."
            )

        # Safe removal path
        if impact.safe_to_remove:
            recommendations.append(
                "This package can be safely removed. Use 'cortex remove <package>' to proceed. "
                "Add --purge to also remove configuration files."
            )
        else:
            recommendations.append(
                "⚠️  This package is NOT safe to remove due to dependencies or critical services. "
                "Review the impact details above before proceeding. Use 'cortex remove <package> --force' "
                "only after careful consideration and ensuring you have backups."
            )

        # Alternative suggestions
        alternatives = self._suggest_alternatives(impact.target_package)
        if alternatives:
            recommendations.append(f"Alternative packages: {', '.join(alternatives)}")

        return recommendations

    def _suggest_alternatives(self, package_name: str) -> list[str]:
        """Suggest alternative packages"""
        # Common alternatives mapping
        alternatives_map = {
            "nginx": ["apache2", "caddy", "lighttpd"],
            "apache2": ["nginx", "caddy", "lighttpd"],
            "mysql-server": ["mariadb-server", "postgresql"],
            "mariadb-server": ["mysql-server", "postgresql"],
            "postgresql": ["mysql-server", "mariadb-server"],
            "vim": ["neovim", "nano", "emacs"],
            "nano": ["vim", "neovim", "emacs"],
        }

        return alternatives_map.get(package_name, [])

    def get_safe_removal_order(self, packages: list[str]) -> list[str]:
        """Calculate the safest order to remove packages"""
        # Remove dependents first, then the package itself
        ordered = []
        remaining = set(packages)

        while remaining:
            # Find packages with no remaining dependents
            safe_to_remove = []
            for pkg in remaining:
                dependents = set(self.graph.get_reverse_dependencies(pkg))
                if not (dependents & remaining):
                    safe_to_remove.append(pkg)

            if safe_to_remove:
                ordered.extend(safe_to_remove)
                remaining -= set(safe_to_remove)
            else:
                # Circular dependency - just add remaining
                ordered.extend(remaining)
                break

        return ordered


class ImpactAnalyzer:
    """
    Main analyzer that orchestrates the impact analysis.
    """

    # Threshold for severity classification
    SEVERITY_THRESHOLDS = {
        "critical_dependents": 50,
        "high_dependents": 20,
        "medium_dependents": 5,
    }

    def __init__(self):
        self.graph = DependencyGraphBuilder()
        self.service_mapper = ServiceImpactMapper()
        self.recommender = RecommendationEngine(self.graph)
        self._initialized = False

    def initialize(self) -> None:
        """Initialize all components"""
        if self._initialized:
            return
        self.graph.initialize()
        self._initialized = True

    def analyze(self, package_name: str) -> ImpactResult:
        """
        Perform comprehensive impact analysis for removing a package.

        Args:
            package_name: Name of the package to analyze

        Returns:
            ImpactResult with complete analysis
        """
        self.initialize()

        result = ImpactResult(target_package=package_name)

        # Check if package exists and is installed
        pkg_info = self.graph.get_package_info(package_name)
        is_installed = pkg_info and pkg_info.is_installed

        if not is_installed:
            # Check if package exists in apt repositories
            pkg_exists = self._package_exists_in_apt(package_name)
            if not pkg_exists:
                result.warnings.append(f"Package '{package_name}' not found in repositories")
                result.recommendations.append(
                    f"Check package name spelling or search with: apt search {package_name}"
                )
                return result
            else:
                result.warnings.append(f"Package '{package_name}' is not currently installed")
                result.recommendations.append(
                    "Showing potential impact if this package were installed and removed."
                )

        # Check if essential (only for installed packages)
        if is_installed and pkg_info and pkg_info.is_essential:
            result.warnings.append(
                f"⚠️  '{package_name}' is marked as ESSENTIAL. "
                "Removing it may break your system!"
            )
            result.severity = ImpactSeverity.CRITICAL
            result.safe_to_remove = False

        # Get direct dependents (works for both installed and available packages)
        result.direct_dependents = self.graph.get_reverse_dependencies(package_name)

        # Get transitive dependents
        result.transitive_dependents, result.cascade_depth = self.graph.get_transitive_dependents(
            package_name
        )

        # Calculate total affected
        all_affected = set(result.direct_dependents + result.transitive_dependents)
        result.total_affected = len(all_affected)

        # Get cascade packages (what would be auto-removed)
        result.cascade_packages = self._get_cascade_packages(package_name)

        # Get orphaned packages
        result.orphaned_packages = self._get_orphaned_packages(package_name)

        # Get affected services
        packages_to_check = [package_name] + list(all_affected)
        result.affected_services = self.service_mapper.get_affected_services(packages_to_check)

        # Determine severity
        result.severity = self._calculate_severity(result)

        # Update safe_to_remove based on analysis
        if result.severity in (ImpactSeverity.CRITICAL, ImpactSeverity.HIGH):
            result.safe_to_remove = False

        # Get recommendations
        result.recommendations = self.recommender.get_recommendations(result)

        return result

    def _package_exists_in_apt(self, package_name: str) -> bool:
        """Check if a package exists in apt repositories"""
        success, stdout, _ = self.graph._run_command(["apt-cache", "show", package_name])
        return success and bool(stdout.strip())

    def _get_cascade_packages(self, package_name: str) -> list[str]:
        """Get packages that would be auto-removed due to broken dependencies"""
        cascade = []
        success, stdout, _ = self.graph._run_command(["apt-get", "-s", "remove", package_name])

        if success:
            for line in stdout.split("\n"):
                if line.startswith("Remv "):
                    pkg = line.split()[1]
                    if pkg != package_name:
                        cascade.append(pkg)

        return cascade

    def _get_orphaned_packages(self, package_name: str) -> list[str]:
        """Get packages that would become orphaned after removing the target package.

        This simulates the removal first, then checks what would be auto-removed.
        Note: This returns current autoremove candidates as apt simulation doesn't
        fully cascade dependency changes in a single pass.
        """
        orphaned = []

        # First simulate removing the target package
        remove_success, _, _ = self.graph._run_command(["apt-get", "-s", "remove", package_name])

        if not remove_success:
            # If removal simulation fails, fall back to current autoremove candidates
            pass

        # Then check for autoremove candidates
        success, stdout, _ = self.graph._run_command(["apt-get", "-s", "autoremove", "--purge"])

        if success:
            for line in stdout.split("\n"):
                if line.startswith("Remv "):
                    pkg = line.split()[1]
                    orphaned.append(pkg)

        return orphaned

    def _calculate_severity(self, result: ImpactResult) -> ImpactSeverity:
        """Calculate impact severity based on analysis results"""
        # Already critical (essential package)
        if result.severity == ImpactSeverity.CRITICAL:
            return ImpactSeverity.CRITICAL

        total = result.total_affected

        # Check for critical services
        critical_running = any(
            s.is_critical and s.status == ServiceStatus.RUNNING for s in result.affected_services
        )
        if critical_running:
            return ImpactSeverity.CRITICAL

        # Based on number of affected packages
        if total >= self.SEVERITY_THRESHOLDS["critical_dependents"]:
            return ImpactSeverity.CRITICAL
        elif total >= self.SEVERITY_THRESHOLDS["high_dependents"]:
            return ImpactSeverity.HIGH
        elif total >= self.SEVERITY_THRESHOLDS["medium_dependents"]:
            return ImpactSeverity.MEDIUM
        elif total > 0:
            return ImpactSeverity.LOW
        else:
            return ImpactSeverity.SAFE

    def generate_removal_plan(self, package_name: str, purge: bool = False) -> RemovalPlan:
        """Generate a removal plan for the package"""
        self.initialize()

        plan = RemovalPlan(target_package=package_name)

        # Get cascade packages
        plan.packages_to_remove = self._get_cascade_packages(package_name)
        plan.packages_to_remove.insert(0, package_name)

        # Get autoremove candidates
        plan.autoremove_candidates = self._get_orphaned_packages(package_name)

        # Get config files
        plan.config_files_affected = self._get_config_files(package_name)

        # Get estimated space
        plan.estimated_freed_space = self._estimate_freed_space(plan.packages_to_remove)

        # Generate commands (without -y flag for interactive confirmation)
        # The -y flag should only be added after explicit user confirmation
        if purge:
            plan.commands = [
                f"sudo apt-get purge {package_name}",
                "sudo apt-get autoremove",
            ]
        else:
            plan.commands = [
                f"sudo apt-get remove {package_name}",
                "sudo apt-get autoremove",
            ]

        return plan

    def _get_config_files(self, package_name: str) -> list[str]:
        """Get configuration files for a package"""
        config_files = []
        success, stdout, _ = self.graph._run_command(["dpkg-query", "-L", package_name])

        if success:
            for line in stdout.split("\n"):
                line = line.strip()
                if line.startswith("/etc/"):
                    config_files.append(line)

        return config_files

    def _estimate_freed_space(self, packages: list[str]) -> str:
        """Estimate space that would be freed"""
        total_bytes = 0

        for pkg in packages:
            success, stdout, _ = self.graph._run_command(
                ["dpkg-query", "-W", "-f=${Installed-Size}", pkg]
            )
            if success and stdout.strip().isdigit():
                total_bytes += int(stdout.strip()) * 1024  # Convert KB to bytes

        # Format size
        if total_bytes >= 1024 * 1024 * 1024:
            return f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"
        elif total_bytes >= 1024 * 1024:
            return f"{total_bytes / (1024 * 1024):.2f} MB"
        elif total_bytes >= 1024:
            return f"{total_bytes / 1024:.2f} KB"
        else:
            return f"{total_bytes} bytes"


class UninstallImpactAnalyzer:
    """
    Main entry point for uninstall impact analysis.
    Provides a simple interface for the CLI.
    """

    def __init__(self):
        self._analyzer = ImpactAnalyzer()

    def analyze(self, package_name: str) -> ImpactResult:
        """Analyze the impact of removing a package"""
        return self._analyzer.analyze(package_name)

    def get_removal_plan(self, package_name: str, purge: bool = False) -> RemovalPlan:
        """Get a detailed removal plan"""
        return self._analyzer.generate_removal_plan(package_name, purge)

    def format_impact_report(self, result: ImpactResult) -> str:
        """Format the impact result as a human-readable report"""
        lines = []

        # Header with severity indicator
        severity_icons = {
            ImpactSeverity.SAFE: "✅",
            ImpactSeverity.LOW: "💚",
            ImpactSeverity.MEDIUM: "🟡",
            ImpactSeverity.HIGH: "🟠",
            ImpactSeverity.CRITICAL: "🔴",
        }

        icon = severity_icons.get(result.severity, "❓")
        lines.append(f"\n{icon} Impact Analysis: {result.target_package}")
        lines.append("=" * 60)

        # Build report sections
        self._format_warnings(lines, result.warnings)
        self._format_package_section(
            lines, "📦 Direct dependents", result.direct_dependents, 10, show_empty=True
        )
        self._format_services_section(lines, result.affected_services)
        self._format_summary_section(lines, result)
        self._format_package_section(lines, "🗑️  Cascade removal", result.cascade_packages, 5)
        self._format_package_section(lines, "👻 Would become orphaned", result.orphaned_packages, 5)
        self._format_list_section(lines, "💡 Recommendations", result.recommendations)

        # Final verdict
        lines.append("\n" + "=" * 60)
        verdict = (
            "✅ Safe to remove"
            if result.safe_to_remove
            else "⚠️  Review recommendations before proceeding"
        )
        lines.append(verdict)

        return "\n".join(lines)

    def _format_warnings(self, lines: list, warnings: list) -> None:
        """Format warnings section."""
        if warnings:
            lines.append("\n⚠️  Warnings:")
            for warning in warnings:
                lines.append(f"   {warning}")

    def _format_package_section(
        self, lines: list, title: str, packages: list, limit: int, show_empty: bool = False
    ) -> None:
        """Format a package list section with truncation."""
        if packages:
            lines.append(f"\n{title} ({len(packages)}):")
            for pkg in packages[:limit]:
                lines.append(f"   • {pkg}")
            if len(packages) > limit:
                lines.append(f"   ... and {len(packages) - limit} more")
        elif show_empty:
            lines.append(f"\n{title}: None")

    def _format_services_section(self, lines: list, services: list) -> None:
        """Format affected services section."""
        if services:
            lines.append(f"\n🔧 Affected services ({len(services)}):")
            for service in services:
                status_icon = "🟢" if service.status == ServiceStatus.RUNNING else "⚪"
                critical_marker = " [CRITICAL]" if service.is_critical else ""
                lines.append(f"   {status_icon} {service.name}{critical_marker}")
        else:
            lines.append("\n🔧 Affected services: None")

    def _format_summary_section(self, lines: list, result: ImpactResult) -> None:
        """Format impact summary section."""
        lines.append("\n📊 Impact Summary:")
        lines.append(f"   • Total packages affected: {result.total_affected}")
        lines.append(f"   • Cascade depth: {result.cascade_depth}")
        lines.append(f"   • Services at risk: {len(result.affected_services)}")
        lines.append(f"   • Severity: {result.severity.value.upper()}")

    def _format_list_section(self, lines: list, title: str, items: list) -> None:
        """Format a simple list section."""
        if items:
            lines.append(f"\n{title}:")
            for item in items:
                lines.append(f"   • {item}")


# CLI Interface for standalone usage
if __name__ == "__main__":
    import argparse
    import datetime
    import sys

    # Configure logging only when running as standalone script
    logging.basicConfig(level=logging.INFO)

    from cortex.installation_history import (
        InstallationHistory,
        InstallationStatus,
        InstallationType,
    )

    parser = argparse.ArgumentParser(description="Analyze impact of package removal")
    parser.add_argument("package", help="Package name to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--plan", action="store_true", help="Generate removal plan")
    parser.add_argument("--purge", action="store_true", help="Include purge in removal plan")

    args = parser.parse_args()

    analyzer = UninstallImpactAnalyzer()
    history = InstallationHistory()
    start_time = datetime.datetime.now()
    exit_code = 0

    # Determine operation type for audit logging
    if args.plan:
        operation_type = InstallationType.REMOVE  # Plan is pre-removal analysis
        operation_desc = "plan"
    else:
        operation_type = InstallationType.REMOVE  # Analyze is also pre-removal
        operation_desc = "analyze"

    try:
        if args.plan:
            plan = analyzer.get_removal_plan(args.package, args.purge)
            print(f"\nRemoval Plan for: {plan.target_package}")
            print("=" * 60)
            print(f"Packages to remove: {', '.join(plan.packages_to_remove)}")
            print(f"Autoremove candidates: {len(plan.autoremove_candidates)}")
            print(f"Config files affected: {len(plan.config_files_affected)}")
            print(f"Estimated freed space: {plan.estimated_freed_space}")
            print("\nCommands:")
            for cmd in plan.commands:
                print(f"  {cmd}")

            # Record successful plan operation
            install_id = history.record_installation(
                operation_type=operation_type,
                packages=[args.package],
                commands=[
                    f"uninstall_impact --plan {'--purge' if args.purge else ''} {args.package}"
                ],
                start_time=start_time,
            )
            history.update_installation(install_id, InstallationStatus.SUCCESS)
        else:
            result = analyzer.analyze(args.package)

            if args.json:
                # Convert to dict (handle enums)
                data = {
                    "target_package": result.target_package,
                    "direct_dependents": result.direct_dependents,
                    "transitive_dependents": result.transitive_dependents,
                    "affected_services": [
                        {
                            "name": s.name,
                            "status": s.status.value,
                            "package": s.package,
                            "is_critical": s.is_critical,
                        }
                        for s in result.affected_services
                    ],
                    "orphaned_packages": result.orphaned_packages,
                    "cascade_packages": result.cascade_packages,
                    "severity": result.severity.value,
                    "total_affected": result.total_affected,
                    "cascade_depth": result.cascade_depth,
                    "recommendations": result.recommendations,
                    "warnings": result.warnings,
                    "safe_to_remove": result.safe_to_remove,
                }
                print(json.dumps(data, indent=2))
            else:
                print(analyzer.format_impact_report(result))

            # Record successful analyze operation
            install_id = history.record_installation(
                operation_type=operation_type,
                packages=[args.package],
                commands=[f"uninstall_impact {'--json' if args.json else ''} {args.package}"],
                start_time=start_time,
            )
            history.update_installation(install_id, InstallationStatus.SUCCESS)

    except Exception as e:
        # Record failed operation
        try:
            install_id = history.record_installation(
                operation_type=operation_type,
                packages=[args.package],
                commands=[f"uninstall_impact {operation_desc} {args.package}"],
                start_time=start_time,
            )
            history.update_installation(install_id, InstallationStatus.FAILED, error_message=str(e))
        except Exception:
            pass  # Don't fail on audit logging errors
        print(f"Error: {e}", file=sys.stderr)
        exit_code = 1

    sys.exit(exit_code)
