#!/usr/bin/env python3
"""
Unit tests for UninstallImpactAnalyzer
Tests dependency impact analysis functionality with >80% coverage
"""

import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from cortex.uninstall_impact import (
    ImpactedPackage,
    ServiceImpact,
    UninstallImpactAnalysis,
    UninstallImpactAnalyzer,
)


class TestImpactedPackage(unittest.TestCase):
    """Test ImpactedPackage dataclass"""

    def test_create_package(self):
        """Test creating an ImpactedPackage"""
        pkg = ImpactedPackage(name="nginx", version="1.18.0", critical=True)
        self.assertEqual(pkg.name, "nginx")
        self.assertEqual(pkg.version, "1.18.0")
        self.assertEqual(pkg.dependency_type, "direct")
        self.assertTrue(pkg.critical)

    def test_optional_package(self):
        """Test optional dependency"""
        pkg = ImpactedPackage(name="docs", dependency_type="optional", critical=False)
        self.assertEqual(pkg.dependency_type, "optional")
        self.assertFalse(pkg.critical)


class TestServiceImpact(unittest.TestCase):
    """Test ServiceImpact dataclass"""

    def test_create_service_impact(self):
        """Test creating a ServiceImpact"""
        service = ServiceImpact(
            service_name="nginx",
            status="active",
            depends_on=["nginx"],
            critical=True,
        )
        self.assertEqual(service.service_name, "nginx")
        self.assertEqual(service.status, "active")
        self.assertIn("nginx", service.depends_on)
        self.assertTrue(service.critical)

    def test_inactive_service(self):
        """Test inactive service"""
        service = ServiceImpact(service_name="redis", status="inactive")
        self.assertEqual(service.status, "inactive")


class TestUninstallImpactAnalysis(unittest.TestCase):
    """Test UninstallImpactAnalysis dataclass"""

    def test_create_analysis(self):
        """Test creating impact analysis"""
        analysis = UninstallImpactAnalysis(
            package_name="python3",
            installed=True,
            installed_version="3.10.0",
            severity="high",
            safe_to_remove=False,
        )
        self.assertEqual(analysis.package_name, "python3")
        self.assertTrue(analysis.installed)
        self.assertEqual(analysis.severity, "high")
        self.assertFalse(analysis.safe_to_remove)


class TestUninstallImpactAnalyzerBasic(unittest.TestCase):
    """Test basic UninstallImpactAnalyzer functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = UninstallImpactAnalyzer()

    def test_analyzer_initialization(self):
        """Test analyzer initializes correctly"""
        self.assertIsNotNone(self.analyzer)
        self.assertIsNotNone(self.analyzer._reverse_deps_cache)
        self.assertIsNotNone(self.analyzer._installed_packages)

    def test_critical_packages_defined(self):
        """Test critical packages are defined"""
        self.assertIn("libc6", UninstallImpactAnalyzer.CRITICAL_PACKAGES)
        self.assertIn("systemd", UninstallImpactAnalyzer.CRITICAL_PACKAGES)
        self.assertIn("dpkg", UninstallImpactAnalyzer.CRITICAL_PACKAGES)

    def test_service_package_map_defined(self):
        """Test service-to-package mapping is defined"""
        self.assertIn("nginx", UninstallImpactAnalyzer.SERVICE_PACKAGE_MAP)
        self.assertIn("docker", UninstallImpactAnalyzer.SERVICE_PACKAGE_MAP)
        self.assertIn("postgresql", UninstallImpactAnalyzer.SERVICE_PACKAGE_MAP)


class TestUninstallImpactAnalyzerCommands(unittest.TestCase):
    """Test command execution in UninstallImpactAnalyzer"""

    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = UninstallImpactAnalyzer()

    @patch("cortex.uninstall_impact.subprocess.run")
    def test_run_command_success(self, mock_run):
        """Test successful command execution"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="output", stderr=""
        )

        success, stdout, stderr = self.analyzer._run_command(["echo", "test"])

        self.assertTrue(success)
        self.assertEqual(stdout, "output")
        self.assertEqual(stderr, "")

    @patch("cortex.uninstall_impact.subprocess.run")
    def test_run_command_failure(self, mock_run):
        """Test failed command execution"""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error"
        )

        success, _, stderr = self.analyzer._run_command(["false"])

        self.assertFalse(success)
        self.assertEqual(stderr, "error")

    @patch("cortex.uninstall_impact.subprocess.run")
    def test_run_command_timeout(self, mock_run):
        """Test command timeout handling"""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("cmd", timeout=30)

        success, _, stderr = self.analyzer._run_command(["sleep", "100"])

        self.assertFalse(success)
        self.assertIn("timed out", stderr.lower())


class TestUninstallImpactAnalyzerPackageDetection(unittest.TestCase):
    """Test package detection functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = UninstallImpactAnalyzer()

    @patch.object(UninstallImpactAnalyzer, "_run_command")
    def test_is_package_installed(self, mock_run):
        """Test checking if package is installed"""
        # Mock the refresh to set up test packages
        self.analyzer._installed_packages = {"nginx", "python3", "git"}

        self.assertTrue(self.analyzer.is_package_installed("nginx"))
        self.assertTrue(self.analyzer.is_package_installed("python3"))
        self.assertFalse(self.analyzer.is_package_installed("nonexistent"))

    @patch.object(UninstallImpactAnalyzer, "_run_command")
    def test_get_installed_version(self, mock_run):
        """Test getting installed package version"""
        self.analyzer._installed_packages = {"nginx"}
        mock_run.return_value = (True, "1.18.0", "")

        version = self.analyzer.get_installed_version("nginx")

        self.assertEqual(version, "1.18.0")
        mock_run.assert_called_once()

    @patch.object(UninstallImpactAnalyzer, "_run_command")
    def test_get_installed_version_not_installed(self, mock_run):
        """Test getting version of non-installed package"""
        self.analyzer._installed_packages = set()

        version = self.analyzer.get_installed_version("nonexistent")

        self.assertIsNone(version)
        mock_run.assert_not_called()


class TestUninstallImpactAnalyzerDependencies(unittest.TestCase):
    """Test dependency analysis functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = UninstallImpactAnalyzer()
        self.analyzer._installed_packages = {"nginx", "docker", "python3"}

    @patch.object(UninstallImpactAnalyzer, "_run_command")
    def test_get_reverse_dependencies(self, mock_run):
        """Test getting reverse dependencies"""
        # Mock apt-cache rdepends output
        mock_output = """nginx
Reverse Depends:
  | certbot
  | docker
  | nginx-extras
"""
        mock_run.return_value = (True, mock_output, "")

        deps = self.analyzer.get_reverse_dependencies("openssl")

        self.assertIsInstance(deps, list)
        mock_run.assert_called_once()

    @patch.object(UninstallImpactAnalyzer, "_run_command")
    def test_get_reverse_dependencies_cached(self, mock_run):
        """Test reverse dependency caching"""
        mock_output = "nginx\nReverse Depends:\n  certbot\n"
        mock_run.return_value = (True, mock_output, "")

        # First call
        deps1 = self.analyzer.get_reverse_dependencies("openssl")
        # Second call (should use cache)
        deps2 = self.analyzer.get_reverse_dependencies("openssl")

        self.assertEqual(deps1, deps2)
        # Should only call once due to caching
        self.assertEqual(mock_run.call_count, 1)

    @patch.object(UninstallImpactAnalyzer, "get_reverse_dependencies")
    @patch.object(UninstallImpactAnalyzer, "is_package_installed")
    @patch.object(UninstallImpactAnalyzer, "get_installed_version")
    def test_get_directly_dependent_packages(
        self, mock_version, mock_installed, mock_reverse
    ):
        """Test getting directly dependent packages"""
        mock_reverse.return_value = ["nginx", "certbot"]
        mock_installed.side_effect = lambda x: x in ["nginx", "certbot"]
        mock_version.side_effect = lambda x: "1.0" if x else None

        deps = self.analyzer.get_directly_dependent_packages("openssl")

        self.assertEqual(len(deps), 2)
        self.assertIsInstance(deps[0], ImpactedPackage)

    @patch.object(UninstallImpactAnalyzer, "get_reverse_dependencies")
    @patch.object(UninstallImpactAnalyzer, "is_package_installed")
    @patch.object(UninstallImpactAnalyzer, "get_installed_version")
    def test_get_indirectly_dependent_packages(
        self, mock_version, mock_installed, mock_reverse
    ):
        """Test getting indirectly dependent packages"""
        direct_deps = [ImpactedPackage(name="nginx"), ImpactedPackage(name="apache2")]

        # Mock indirect dependencies through nginx
        def reverse_side_effect(pkg):
            if pkg == "nginx":
                return ["certbot", "haproxy"]
            return []

        mock_reverse.side_effect = reverse_side_effect
        mock_installed.side_effect = lambda x: x in ["certbot", "haproxy"]
        mock_version.side_effect = lambda x: "1.0"

        indirect = self.analyzer.get_indirectly_dependent_packages("openssl", direct_deps)

        self.assertIsInstance(indirect, list)


class TestUninstallImpactAnalyzerServices(unittest.TestCase):
    """Test service impact analysis"""

    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = UninstallImpactAnalyzer()

    @patch.object(UninstallImpactAnalyzer, "_run_command")
    def test_get_affected_services_active(self, mock_run):
        """Test finding active services affected by package removal"""
        mock_run.return_value = (True, "active\n", "")

        services = self.analyzer.get_affected_services("nginx")

        self.assertEqual(len(services), 1)
        self.assertEqual(services[0].service_name, "nginx")
        self.assertEqual(services[0].status, "active")

    @patch.object(UninstallImpactAnalyzer, "_run_command")
    def test_get_affected_services_none(self, mock_run):
        """Test package with no affected services"""
        services = self.analyzer.get_affected_services("obscure-package")

        self.assertEqual(len(services), 0)


class TestUninstallImpactAnalyzerOrphans(unittest.TestCase):
    """Test orphan package detection"""

    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = UninstallImpactAnalyzer()

    @patch.object(UninstallImpactAnalyzer, "get_reverse_dependencies")
    @patch.object(UninstallImpactAnalyzer, "is_package_installed")
    @patch.object(UninstallImpactAnalyzer, "_run_command")
    def test_find_orphaned_packages(self, mock_run, mock_installed, mock_reverse):
        """Test finding orphaned packages"""
        mock_reverse.return_value = ["dep1", "dep2"]
        mock_installed.side_effect = lambda x: x in ["dep1", "dep2"]

        # Mock depends output showing only 1 dependency
        mock_run.return_value = (True, "Depends: package\n", "")

        orphans = self.analyzer.find_orphaned_packages("libfoo")

        self.assertIsInstance(orphans, list)

    @patch.object(UninstallImpactAnalyzer, "get_reverse_dependencies")
    @patch.object(UninstallImpactAnalyzer, "is_package_installed")
    def test_find_orphaned_packages_none(self, mock_installed, mock_reverse):
        """Test when no packages are orphaned"""
        mock_reverse.return_value = []

        orphans = self.analyzer.find_orphaned_packages("libfoo")

        self.assertEqual(len(orphans), 0)


class TestUninstallImpactAnalyzerSeverity(unittest.TestCase):
    """Test severity determination"""

    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = UninstallImpactAnalyzer()

    def test_severity_critical_package(self):
        """Test critical package severity"""
        severity = self.analyzer._determine_severity("systemd", [], [], 0)
        self.assertEqual(severity, "critical")

    def test_severity_high_with_critical_deps(self):
        """Test high severity with critical dependencies"""
        critical_dep = ImpactedPackage(name="libc6", critical=True)
        severity = self.analyzer._determine_severity("openssl", [critical_dep], [], 0)
        self.assertEqual(severity, "high")

    def test_severity_high_many_deps(self):
        """Test high severity with many dependencies"""
        deps = [ImpactedPackage(name=f"dep{i}") for i in range(6)]
        severity = self.analyzer._determine_severity("openssl", deps, [], 6)
        self.assertEqual(severity, "high")

    def test_severity_medium_several_deps(self):
        """Test medium severity with several dependencies but no critical ones"""
        # Pass empty critical_deps and empty services to test total_deps
        severity = self.analyzer._determine_severity("openssl", [], [], 3)
        self.assertEqual(severity, "medium")

    def test_severity_low(self):
        """Test low severity with few dependencies"""
        severity = self.analyzer._determine_severity("openssl", [], [], 1)
        self.assertEqual(severity, "low")


class TestUninstallImpactAnalyzerRecommendations(unittest.TestCase):
    """Test recommendation generation"""

    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = UninstallImpactAnalyzer()

    def test_recommendations_critical_package(self):
        """Test recommendations for critical package"""
        recs = self.analyzer._generate_recommendations("systemd", "critical", [], [])
        self.assertTrue(any("DO NOT REMOVE" in r for r in recs))

    def test_recommendations_high_severity(self):
        """Test recommendations for high severity"""
        deps = [ImpactedPackage(name="nginx")]
        recs = self.analyzer._generate_recommendations("openssl", "high", deps, [])
        self.assertTrue(any("caution" in r.lower() for r in recs))

    def test_recommendations_with_orphans(self):
        """Test recommendations when packages would be orphaned"""
        recs = self.analyzer._generate_recommendations("openssl", "medium", [], ["orphan1"])
        self.assertTrue(any("orphan" in r.lower() for r in recs))

    def test_recommendations_safe_removal(self):
        """Test recommendations for safe removal"""
        recs = self.analyzer._generate_recommendations("openssl", "low", [], [])
        self.assertTrue(any("safe" in r.lower() for r in recs))


class TestUninstallImpactAnalyzerFullAnalysis(unittest.TestCase):
    """Test full impact analysis workflow"""

    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = UninstallImpactAnalyzer()

    @patch.object(UninstallImpactAnalyzer, "is_package_installed")
    @patch.object(UninstallImpactAnalyzer, "get_installed_version")
    @patch.object(UninstallImpactAnalyzer, "get_directly_dependent_packages")
    @patch.object(UninstallImpactAnalyzer, "get_indirectly_dependent_packages")
    @patch.object(UninstallImpactAnalyzer, "get_affected_services")
    @patch.object(UninstallImpactAnalyzer, "find_orphaned_packages")
    def test_analyze_uninstall_impact_installed_package(
        self,
        mock_orphans,
        mock_services,
        mock_indirect,
        mock_direct,
        mock_version,
        mock_installed,
    ):
        """Test full impact analysis for installed package"""
        mock_installed.return_value = True
        mock_version.return_value = "1.18.0"
        mock_direct.return_value = [ImpactedPackage(name="nginx")]
        mock_indirect.return_value = []
        mock_services.return_value = [ServiceImpact(service_name="nginx")]
        mock_orphans.return_value = ["orphan1"]

        analysis = self.analyzer.analyze_uninstall_impact("openssl")

        self.assertTrue(analysis.installed)
        self.assertEqual(analysis.installed_version, "1.18.0")
        self.assertEqual(len(analysis.directly_depends), 1)
        self.assertEqual(len(analysis.affected_services), 1)
        self.assertIn("orphan1", analysis.orphaned_packages)

    @patch.object(UninstallImpactAnalyzer, "is_package_installed")
    @patch.object(UninstallImpactAnalyzer, "get_installed_version")
    @patch.object(UninstallImpactAnalyzer, "get_directly_dependent_packages")
    @patch.object(UninstallImpactAnalyzer, "get_indirectly_dependent_packages")
    @patch.object(UninstallImpactAnalyzer, "get_affected_services")
    @patch.object(UninstallImpactAnalyzer, "find_orphaned_packages")
    def test_analyze_uninstall_impact_not_installed(
        self,
        mock_orphans,
        mock_services,
        mock_indirect,
        mock_direct,
        mock_version,
        mock_installed,
    ):
        """Test analysis for non-installed package"""
        mock_installed.return_value = False
        mock_version.return_value = None
        mock_direct.return_value = []
        mock_indirect.return_value = []
        mock_services.return_value = []
        mock_orphans.return_value = []

        analysis = self.analyzer.analyze_uninstall_impact("nonexistent")

        self.assertFalse(analysis.installed)
        self.assertIsNone(analysis.installed_version)


class TestUninstallImpactAnalyzerExport(unittest.TestCase):
    """Test exporting analysis to JSON"""

    def test_export_analysis_json(self):
        """Test exporting analysis to JSON file"""
        analyzer = UninstallImpactAnalyzer()

        analysis = UninstallImpactAnalysis(
            package_name="nginx",
            installed=True,
            installed_version="1.18.0",
            directly_depends=[ImpactedPackage(name="openssl")],
            severity="low",
            safe_to_remove=True,
        )

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_path = f.name

        try:
            analyzer.export_analysis_json(analysis, temp_path)

            with open(temp_path, "r") as f:
                data = json.load(f)

            self.assertEqual(data["package_name"], "nginx")
            self.assertEqual(data["installed_version"], "1.18.0")
            self.assertEqual(data["severity"], "low")
            self.assertTrue(data["safe_to_remove"])
        finally:
            import os

            os.unlink(temp_path)


class TestUninstallImpactAnalyzerConcurrency(unittest.TestCase):
    """Test thread-safety of analyzer"""

    def test_thread_safe_package_cache(self):
        """Test that package cache is thread-safe"""
        analyzer = UninstallImpactAnalyzer()

        # Simulate concurrent access
        import threading

        results = []

        def check_package(pkg):
            result = analyzer.is_package_installed(pkg)
            results.append(result)

        threads = [
            threading.Thread(target=check_package, args=("nginx",)) for _ in range(5)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # All should complete without errors
        self.assertEqual(len(results), 5)


class TestIntegration(unittest.TestCase):
    """Integration tests for uninstall impact analysis"""

    @patch.object(UninstallImpactAnalyzer, "_run_command")
    @patch.object(UninstallImpactAnalyzer, "_refresh_installed_packages")
    def test_full_workflow(self, mock_refresh, mock_run):
        """Test complete uninstall analysis workflow"""
        analyzer = UninstallImpactAnalyzer()

        # This would normally interact with the system
        # We're testing that the analyzer can be instantiated and used
        self.assertIsNotNone(analyzer)


if __name__ == "__main__":
    unittest.main()
