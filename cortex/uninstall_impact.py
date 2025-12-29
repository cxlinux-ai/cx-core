#!/usr/bin/env python3
"""
Uninstall Impact Analysis System
Analyzes impact before uninstalling packages, including:
- Reverse dependencies (what depends on this package)
- Service impact assessment
- Orphan package detection
- Safe removal recommendations
"""

import json
import logging
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ImpactedPackage:
    """Represents a package that depends on the target package"""

    name: str
    version: Optional[str] = None
    dependency_type: str = "direct"  # direct, indirect, optional
    critical: bool = False  # True if system would break without this package


@dataclass
class ServiceImpact:
    """Represents impact on system services"""

    service_name: str
    status: str = "active"  # active, inactive, failed
    depends_on: list[str] = field(default_factory=list)
    description: str = ""
    critical: bool = False


@dataclass
class UninstallImpactAnalysis:
    """Complete impact analysis for package uninstallation"""

    package_name: str
    installed: bool = False
    installed_version: Optional[str] = None
    directly_depends: list[ImpactedPackage] = field(default_factory=list)
    indirectly_depends: list[ImpactedPackage] = field(default_factory=list)
    optional_depends: list[ImpactedPackage] = field(default_factory=list)
    affected_services: list[ServiceImpact] = field(default_factory=list)
    orphaned_packages: list[str] = field(default_factory=list)
    total_affected_packages: int = 0
    total_affected_services: int = 0
    safe_to_remove: bool = True
    severity: str = "low"  # low, medium, high, critical
    recommendations: list[str] = field(default_factory=list)


class UninstallImpactAnalyzer:
    """Analyzes impact of uninstalling packages"""

    # Service-to-package mapping
    SERVICE_PACKAGE_MAP = {
        "nginx": ["nginx"],
        "apache2": ["apache2"],
        "mysql": ["mysql-server", "mariadb-server"],
        "postgresql": ["postgresql"],
        "redis": ["redis-server"],
        "docker": ["docker.io", "docker-ce"],
        "ssh": ["openssh-server"],
        "python3": ["python3"],
        "node": ["nodejs"],
        "git": ["git"],
        "curl": ["curl"],
        "wget": ["wget"],
    }

    # Critical system packages that should not be removed
    CRITICAL_PACKAGES = {
        "libc6",
        "libc-bin",
        "base-files",
        "base-passwd",
        "dpkg",
        "apt",
        "bash",
        "grep",
        "coreutils",
        "util-linux",
        "systemd",
        "linux-image-generic",
    }

    def __init__(self):
        self._cache_lock = threading.Lock()
        self._reverse_deps_cache: dict[str, list[str]] = {}
        self._installed_packages: set[str] = set()
        self._refresh_installed_packages()

    def _run_command(self, cmd: list[str]) -> tuple[bool, str, str]:
        """Execute command and return success, stdout, stderr"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "", "Command timed out")
        except Exception as e:
            return (False, "", str(e))

    def _refresh_installed_packages(self) -> None:
        """Refresh cache of installed packages"""
        logger.info("Refreshing installed packages cache...")
        success, stdout, _ = self._run_command(["dpkg", "-l"])

        if success:
            new_packages = set()
            for line in stdout.split("\n"):
                if line.startswith("ii"):
                    parts = line.split()
                    if len(parts) >= 2:
                        new_packages.add(parts[1])

            with self._cache_lock:
                self._installed_packages = new_packages
                logger.info(f"Found {len(self._installed_packages)} installed packages")

    def is_package_installed(self, package_name: str) -> bool:
        """Check if package is installed (thread-safe)"""
        with self._cache_lock:
            return package_name in self._installed_packages

    def get_installed_version(self, package_name: str) -> Optional[str]:
        """Get version of installed package"""
        if not self.is_package_installed(package_name):
            return None

        success, stdout, _ = self._run_command(["dpkg-query", "-W", "-f=${Version}", package_name])

        return stdout.strip() if success else None

    def get_reverse_dependencies(self, package_name: str) -> list[str]:
        """
        Get packages that depend on this package (reverse dependencies)
        Uses apt-cache rdepends to find packages that depend on this one
        """
        # Check cache
        with self._cache_lock:
            if package_name in self._reverse_deps_cache:
                logger.info(f"Using cached reverse dependencies for {package_name}")
                return self._reverse_deps_cache[package_name]

        dependencies = []
        success, stdout, stderr = self._run_command(["apt-cache", "rdepends", package_name])

        if not success:
            logger.warning(f"Could not get reverse dependencies for {package_name}: {stderr}")
            return dependencies

        for line in stdout.split("\n"):
            line = line.strip()

            # Skip header and separators
            if not line or line == package_name or line.startswith("Reverse Depends:"):
                continue

            # Handle indentation and alternatives
            dep_name = line.strip("|- ").strip()

            # Skip lines with < or > (version constraints)
            if not dep_name or "<" in dep_name or ">" in dep_name:
                continue

            if dep_name and dep_name not in dependencies:
                dependencies.append(dep_name)

        # Cache result
        with self._cache_lock:
            self._reverse_deps_cache[package_name] = dependencies

        return dependencies

    def get_directly_dependent_packages(self, package_name: str) -> list[ImpactedPackage]:
        """Get packages that directly depend on this package"""
        impacted = []
        reverse_deps = self.get_reverse_dependencies(package_name)

        for dep_name in reverse_deps:
            is_installed = self.is_package_installed(dep_name)
            if is_installed:
                version = self.get_installed_version(dep_name)
                critical = dep_name in self.CRITICAL_PACKAGES

                impacted.append(
                    ImpactedPackage(
                        name=dep_name,
                        version=version,
                        dependency_type="direct",
                        critical=critical,
                    )
                )

        return impacted

    def get_indirectly_dependent_packages(
        self, package_name: str, direct_deps: list[ImpactedPackage]
    ) -> list[ImpactedPackage]:
        """Get packages that indirectly depend on this package"""
        impacted = []
        checked = {package_name}

        for direct_dep in direct_deps:
            checked.add(direct_dep.name)

        # For each direct dependency, check what depends on them
        for direct_dep in direct_deps:
            indirect_deps = self.get_reverse_dependencies(direct_dep.name)

            for indirect_name in indirect_deps:
                if indirect_name not in checked:
                    is_installed = self.is_package_installed(indirect_name)
                    if is_installed:
                        version = self.get_installed_version(indirect_name)
                        critical = indirect_name in self.CRITICAL_PACKAGES

                        impacted.append(
                            ImpactedPackage(
                                name=indirect_name,
                                version=version,
                                dependency_type="indirect",
                                critical=critical,
                            )
                        )
                        checked.add(indirect_name)

        return impacted

    def get_affected_services(self, package_name: str) -> list[ServiceImpact]:
        """Get system services that depend on this package"""
        affected = []

        for service_name, packages in self.SERVICE_PACKAGE_MAP.items():
            if package_name in packages:
                # Try to get service status
                success, status_out, _ = self._run_command(
                    ["systemctl", "is-active", service_name]
                )

                status = "active" if success and "active" in status_out else "inactive"

                # Check if service is critical
                critical_services = {"ssh", "docker", "postgresql", "mysql"}
                is_critical = service_name in critical_services

                affected.append(
                    ServiceImpact(
                        service_name=service_name,
                        status=status,
                        depends_on=[package_name],
                        critical=is_critical,
                    )
                )

        return affected

    def find_orphaned_packages(self, package_name: str) -> list[str]:
        """
        Find packages that would become orphaned if this package is removed.
        A package is orphaned if it's not critical, not explicitly installed,
        and only depends on the package being removed.
        """
        orphaned = []
        reverse_deps = self.get_reverse_dependencies(package_name)

        for dep_name in reverse_deps:
            if not self.is_package_installed(dep_name):
                continue

            if dep_name in self.CRITICAL_PACKAGES:
                continue

            # Check if this package only depends on the target package
            success, stdout, _ = self._run_command(["apt-cache", "depends", dep_name])

            if success:
                deps_count = len([line for line in stdout.split("\n") if "Depends:" in line])

                # If package only has 1 dependency (the one being removed), it's orphaned
                if deps_count <= 1:
                    orphaned.append(dep_name)

        return orphaned

    def analyze_uninstall_impact(self, package_name: str) -> UninstallImpactAnalysis:
        """
        Perform complete impact analysis for uninstalling a package
        """
        logger.info(f"Analyzing uninstall impact for {package_name}...")

        is_installed = self.is_package_installed(package_name)
        installed_version = self.get_installed_version(package_name) if is_installed else None

        # Get different types of dependencies
        directly_depends = self.get_directly_dependent_packages(package_name)
        indirectly_depends = self.get_indirectly_dependent_packages(package_name, directly_depends)

        # Separate by criticality
        critical_deps = [d for d in directly_depends if d.critical]
        optional_deps = [d for d in directly_depends if not d.critical]

        # Get affected services
        affected_services = self.get_affected_services(package_name)
        critical_services = [s for s in affected_services if s.critical]

        # Find orphaned packages
        orphaned = self.find_orphaned_packages(package_name)

        # Calculate severity
        severity = self._determine_severity(
            package_name, critical_deps, critical_services, len(directly_depends)
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            package_name, severity, directly_depends, orphaned
        )

        # Determine if safe to remove
        safe_to_remove = (
            severity not in ["high", "critical"] and not self.is_package_installed(package_name)
        ) or (is_installed and severity == "low")

        total_affected = len(directly_depends) + len(indirectly_depends)

        analysis = UninstallImpactAnalysis(
            package_name=package_name,
            installed=is_installed,
            installed_version=installed_version,
            directly_depends=directly_depends,
            indirectly_depends=indirectly_depends,
            optional_depends=optional_deps,
            affected_services=affected_services,
            orphaned_packages=orphaned,
            total_affected_packages=total_affected,
            total_affected_services=len(affected_services),
            safe_to_remove=safe_to_remove,
            severity=severity,
            recommendations=recommendations,
        )

        return analysis

    def _determine_severity(
        self,
        package_name: str,
        critical_deps: list[ImpactedPackage],
        critical_services: list[ServiceImpact],
        total_deps: int,
    ) -> str:
        """Determine severity level of removal"""
        if package_name in self.CRITICAL_PACKAGES:
            return "critical"

        if critical_deps or critical_services:
            return "high"

        if total_deps > 5:
            return "high"

        if total_deps >= 3:
            return "medium"

        return "low"

    def _generate_recommendations(
        self,
        package_name: str,
        severity: str,
        directly_depends: list[ImpactedPackage],
        orphaned: list[str],
    ) -> list[str]:
        """Generate removal recommendations"""
        recommendations = []

        if severity == "critical":
            recommendations.append(f"⚠️  DO NOT REMOVE {package_name.upper()} - This is a critical system package")
            recommendations.append(
                "Removing it will break your system and may require manual recovery."
            )
            return recommendations

        if severity == "high":
            recommendations.append(
                f"⚠️  Use caution when removing {package_name} - it affects critical services"
            )
            recommendations.append(
                "Consider removing dependent packages first using cascading removal"
            )

        if len(directly_depends) > 0:
            dep_names = [d.name for d in directly_depends[:3]]
            more = len(directly_depends) - 3
            more_str = f" and {more} more" if more > 0 else ""
            recommendations.append(f"Remove dependent packages first: {', '.join(dep_names)}{more_str}")

        if orphaned:
            recommendations.append(
                f"These packages would become orphaned: {', '.join(orphaned[:3])}"
            )
            recommendations.append("Consider removing them with: cortex remove --orphans")

        if not recommendations:
            recommendations.append(f"✅ Safe to remove {package_name}")

        return recommendations

    def export_analysis_json(self, analysis: UninstallImpactAnalysis, filepath: str) -> None:
        """Export analysis to JSON file"""
        analysis_dict = {
            "package_name": analysis.package_name,
            "installed": analysis.installed,
            "installed_version": analysis.installed_version,
            "directly_depends": [asdict(d) for d in analysis.directly_depends],
            "indirectly_depends": [asdict(d) for d in analysis.indirectly_depends],
            "optional_depends": [asdict(d) for d in analysis.optional_depends],
            "affected_services": [asdict(s) for s in analysis.affected_services],
            "orphaned_packages": analysis.orphaned_packages,
            "total_affected_packages": analysis.total_affected_packages,
            "total_affected_services": analysis.total_affected_services,
            "safe_to_remove": analysis.safe_to_remove,
            "severity": analysis.severity,
            "recommendations": analysis.recommendations,
        }

        with open(filepath, "w") as f:
            json.dump(analysis_dict, f, indent=2)

        logger.info(f"Impact analysis exported to {filepath}")


# CLI Interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze uninstall impact")
    parser.add_argument("package", help="Package name to analyze")
    parser.add_argument("--export", help="Export analysis to JSON file")

    args = parser.parse_args()

    analyzer = UninstallImpactAnalyzer()
    analysis = analyzer.analyze_uninstall_impact(args.package)

    # Display analysis
    print(f"\n📦 Uninstall Impact Analysis: {analysis.package_name}")
    print("=" * 70)

    if not analysis.installed:
        print(f"ⓘ  Package {analysis.package_name} is not installed")
        print("   Analysis is based on dependency relationships")
    else:
        print(f"✅ Installed version: {analysis.installed_version}")

    print("\n📊 Impact Summary")
    print("-" * 70)
    print(f"Severity: {analysis.severity.upper()}")
    print(f"Safe to remove: {'✅ Yes' if analysis.safe_to_remove else '❌ No'}")

    if analysis.directly_depends:
        print(f"\n📌 Directly depends on {analysis.package_name}:")
        for dep in analysis.directly_depends[:10]:
            critical_str = " ⚠️ CRITICAL" if dep.critical else ""
            print(f"   - {dep.name} ({dep.version or 'unknown'}){critical_str}")
        if len(analysis.directly_depends) > 10:
            print(f"   ... and {len(analysis.directly_depends) - 10} more")

    if analysis.indirectly_depends:
        print("\n🔗 Indirectly depends (through dependencies):")
        for dep in analysis.indirectly_depends[:5]:
            print(f"   - {dep.name}")
        if len(analysis.indirectly_depends) > 5:
            print(f"   ... and {len(analysis.indirectly_depends) - 5} more")

    if analysis.affected_services:
        print("\n🔧 Services that may be affected:")
        for service in analysis.affected_services:
            critical_str = " ⚠️ CRITICAL" if service.critical else ""
            print(f"   - {service.service_name} ({service.status}){critical_str}")

    if analysis.orphaned_packages:
        print("\n🗑️  Orphaned packages (would have no dependencies):")
        for pkg in analysis.orphaned_packages[:5]:
            print(f"   - {pkg}")

    print("\n💡 Recommendations")
    print("-" * 70)
    for i, rec in enumerate(analysis.recommendations, 1):
        print(f"   {rec}")

    if args.export:
        analyzer.export_analysis_json(analysis, args.export)
        print(f"\n✅ Analysis exported to {args.export}")
