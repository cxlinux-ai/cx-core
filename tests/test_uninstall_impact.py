#!/usr/bin/env python3
"""
Tests for Uninstall Impact Analysis Engine

Tests the following components:
- DependencyGraphBuilder
- ServiceImpactMapper
- RecommendationEngine
- ImpactAnalyzer
- UninstallImpactAnalyzer (main interface)
"""

import unittest
from unittest.mock import MagicMock, patch

from cortex.uninstall_impact import (
    DependencyEdge,
    DependencyGraphBuilder,
    ImpactAnalyzer,
    ImpactResult,
    ImpactSeverity,
    PackageNode,
    RecommendationEngine,
    RemovalPlan,
    ServiceImpactMapper,
    ServiceInfo,
    ServiceStatus,
    UninstallImpactAnalyzer,
)


class TestPackageNode(unittest.TestCase):
    """Tests for PackageNode dataclass"""

    def test_package_node_creation(self):
        """Test creating a package node"""
        node = PackageNode(
            name="nginx",
            version="1.18.0",
            is_installed=True,
            is_essential=False,
            is_manually_installed=True,
            description="High performance web server",
        )
        self.assertEqual(node.name, "nginx")
        self.assertEqual(node.version, "1.18.0")
        self.assertTrue(node.is_installed)
        self.assertFalse(node.is_essential)
        self.assertTrue(node.is_manually_installed)

    def test_package_node_defaults(self):
        """Test package node default values"""
        node = PackageNode(name="test-pkg")
        self.assertEqual(node.name, "test-pkg")
        self.assertIsNone(node.version)
        self.assertFalse(node.is_installed)
        self.assertFalse(node.is_essential)
        self.assertFalse(node.is_manually_installed)
        self.assertEqual(node.description, "")


class TestServiceInfo(unittest.TestCase):
    """Tests for ServiceInfo dataclass"""

    def test_service_info_creation(self):
        """Test creating a service info"""
        info = ServiceInfo(
            name="nginx",
            status=ServiceStatus.RUNNING,
            package="nginx",
            description="HTTP server",
            is_critical=False,
        )
        self.assertEqual(info.name, "nginx")
        self.assertEqual(info.status, ServiceStatus.RUNNING)
        self.assertFalse(info.is_critical)

    def test_service_status_enum(self):
        """Test service status enumeration"""
        self.assertEqual(ServiceStatus.RUNNING.value, "running")
        self.assertEqual(ServiceStatus.STOPPED.value, "stopped")
        self.assertEqual(ServiceStatus.NOT_FOUND.value, "not_found")
        self.assertEqual(ServiceStatus.UNKNOWN.value, "unknown")


class TestImpactResult(unittest.TestCase):
    """Tests for ImpactResult dataclass"""

    def test_impact_result_defaults(self):
        """Test impact result default values"""
        result = ImpactResult(target_package="test-pkg")
        self.assertEqual(result.target_package, "test-pkg")
        self.assertEqual(result.direct_dependents, [])
        self.assertEqual(result.transitive_dependents, [])
        self.assertEqual(result.affected_services, [])
        self.assertEqual(result.orphaned_packages, [])
        self.assertEqual(result.cascade_packages, [])
        self.assertEqual(result.severity, ImpactSeverity.SAFE)
        self.assertEqual(result.total_affected, 0)
        self.assertEqual(result.cascade_depth, 0)
        self.assertEqual(result.recommendations, [])
        self.assertEqual(result.warnings, [])
        self.assertTrue(result.safe_to_remove)


class TestImpactSeverity(unittest.TestCase):
    """Tests for ImpactSeverity enumeration"""

    def test_severity_values(self):
        """Test severity enum values"""
        self.assertEqual(ImpactSeverity.SAFE.value, "safe")
        self.assertEqual(ImpactSeverity.LOW.value, "low")
        self.assertEqual(ImpactSeverity.MEDIUM.value, "medium")
        self.assertEqual(ImpactSeverity.HIGH.value, "high")
        self.assertEqual(ImpactSeverity.CRITICAL.value, "critical")

    def test_severity_ordering(self):
        """Test that severity levels can be compared conceptually"""
        severities = [
            ImpactSeverity.SAFE,
            ImpactSeverity.LOW,
            ImpactSeverity.MEDIUM,
            ImpactSeverity.HIGH,
            ImpactSeverity.CRITICAL,
        ]
        self.assertEqual(len(severities), 5)


class TestDependencyGraphBuilder(unittest.TestCase):
    """Tests for DependencyGraphBuilder"""

    def setUp(self):
        self.graph = DependencyGraphBuilder()

    @patch.object(DependencyGraphBuilder, "_run_command")
    def test_load_installed_packages(self, mock_run):
        """Test loading installed packages"""
        mock_run.return_value = (True, "nginx\napache2\nmysql-server\n", "")
        self.graph._load_installed_packages()
        self.assertIn("nginx", self.graph._installed_packages)
        self.assertIn("apache2", self.graph._installed_packages)
        self.assertIn("mysql-server", self.graph._installed_packages)

    @patch.object(DependencyGraphBuilder, "_run_command")
    def test_load_essential_packages(self, mock_run):
        """Test loading essential packages"""
        mock_run.return_value = (True, "base-files yes\nlibc6 no\nbash yes\n", "")
        self.graph._load_essential_packages()
        self.assertIn("base-files", self.graph._essential_packages)
        self.assertIn("bash", self.graph._essential_packages)
        self.assertNotIn("libc6", self.graph._essential_packages)

    @patch.object(DependencyGraphBuilder, "_run_command")
    def test_load_manual_packages(self, mock_run):
        """Test loading manually installed packages"""
        mock_run.return_value = (True, "nginx\nvim\ngit\n", "")
        self.graph._load_manual_packages()
        self.assertIn("nginx", self.graph._manual_packages)
        self.assertIn("vim", self.graph._manual_packages)
        self.assertIn("git", self.graph._manual_packages)

    @patch.object(DependencyGraphBuilder, "_run_command")
    def test_get_dependencies(self, mock_run):
        """Test getting forward dependencies"""
        mock_run.return_value = (
            True,
            "nginx\n  Depends: libc6\n  Depends: libpcre3\n  Recommends: nginx-doc\n",
            "",
        )
        deps = self.graph.get_dependencies("nginx")
        self.assertIn("libc6", deps)
        self.assertIn("libpcre3", deps)

    @patch.object(DependencyGraphBuilder, "_run_command")
    def test_get_reverse_dependencies(self, mock_run):
        """Test getting reverse dependencies"""
        self.graph._installed_packages = {"php-fpm", "nginx-full", "web-app"}
        mock_run.return_value = (
            True,
            "nginx\nReverse Depends:\n  php-fpm\n  nginx-full\n  web-app\n",
            "",
        )
        rdeps = self.graph.get_reverse_dependencies("nginx")
        self.assertIn("php-fpm", rdeps)
        self.assertIn("nginx-full", rdeps)

    @patch.object(DependencyGraphBuilder, "_run_command")
    def test_get_package_info(self, mock_run):
        """Test getting package information"""
        mock_run.return_value = (True, "nginx|1.18.0|High performance web server", "")
        info = self.graph.get_package_info("nginx")
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "nginx")
        self.assertEqual(info.version, "1.18.0")

    def test_is_essential(self):
        """Test essential package check"""
        self.graph._essential_packages = {"base-files", "bash"}
        self.assertTrue(self.graph.is_essential("base-files"))
        self.assertFalse(self.graph.is_essential("nginx"))

    def test_is_installed(self):
        """Test installed package check"""
        self.graph._installed_packages = {"nginx", "apache2"}
        self.assertTrue(self.graph.is_installed("nginx"))
        self.assertFalse(self.graph.is_installed("lighttpd"))

    def test_is_manually_installed(self):
        """Test manual installation check"""
        self.graph._manual_packages = {"nginx", "vim"}
        self.assertTrue(self.graph.is_manually_installed("nginx"))
        self.assertFalse(self.graph.is_manually_installed("libc6"))


class TestServiceImpactMapper(unittest.TestCase):
    """Tests for ServiceImpactMapper"""

    def setUp(self):
        self.mapper = ServiceImpactMapper()

    def test_package_service_mapping_exists(self):
        """Test that package-service mappings are defined"""
        self.assertIn("nginx", self.mapper.PACKAGE_SERVICE_MAP)
        self.assertIn("mysql-server", self.mapper.PACKAGE_SERVICE_MAP)
        self.assertIn("openssh-server", self.mapper.PACKAGE_SERVICE_MAP)

    def test_critical_services_defined(self):
        """Test that critical services are defined"""
        self.assertIn("ssh", self.mapper.CRITICAL_SERVICES)
        self.assertIn("sshd", self.mapper.CRITICAL_SERVICES)
        self.assertIn("docker", self.mapper.CRITICAL_SERVICES)

    @patch.object(ServiceImpactMapper, "_run_command")
    def test_get_service_status_running(self, mock_run):
        """Test getting status of running service"""
        mock_run.return_value = (True, "active", "")
        status = self.mapper.get_service_status("nginx")
        self.assertEqual(status, ServiceStatus.RUNNING)

    @patch.object(ServiceImpactMapper, "_run_command")
    def test_get_service_status_stopped(self, mock_run):
        """Test getting status of stopped service"""
        mock_run.side_effect = [
            (False, "", ""),  # is-active fails
            (True, "", ""),  # cat succeeds (service exists)
        ]
        status = self.mapper.get_service_status("nginx")
        self.assertEqual(status, ServiceStatus.STOPPED)

    @patch.object(ServiceImpactMapper, "_run_command")
    def test_get_service_status_not_found(self, mock_run):
        """Test getting status of non-existent service"""
        mock_run.side_effect = [
            (False, "", ""),  # is-active fails
            (False, "", ""),  # cat fails (service doesn't exist)
        ]
        status = self.mapper.get_service_status("nonexistent")
        self.assertEqual(status, ServiceStatus.NOT_FOUND)

    @patch.object(ServiceImpactMapper, "get_service_status")
    def test_get_services_for_package(self, mock_status):
        """Test getting services for a known package"""
        mock_status.return_value = ServiceStatus.RUNNING
        services = self.mapper.get_services_for_package("nginx")
        self.assertGreater(len(services), 0)
        self.assertEqual(services[0].name, "nginx")

    @patch.object(ServiceImpactMapper, "get_service_status")
    def test_get_affected_services(self, mock_status):
        """Test getting affected services for multiple packages"""
        mock_status.return_value = ServiceStatus.RUNNING
        services = self.mapper.get_affected_services(["nginx", "mysql-server"])
        self.assertGreater(len(services), 0)


class TestRecommendationEngine(unittest.TestCase):
    """Tests for RecommendationEngine"""

    def setUp(self):
        self.graph = MagicMock(spec=DependencyGraphBuilder)
        self.engine = RecommendationEngine(self.graph)

    def test_critical_severity_recommendation(self):
        """Test recommendations for critical severity"""
        result = ImpactResult(
            target_package="base-files",
            severity=ImpactSeverity.CRITICAL,
            safe_to_remove=False,
        )
        recs = self.engine.get_recommendations(result)
        self.assertTrue(any("CRITICAL" in rec for rec in recs))

    def test_high_severity_recommendation(self):
        """Test recommendations for high severity"""
        result = ImpactResult(
            target_package="libc6",
            severity=ImpactSeverity.HIGH,
            direct_dependents=["pkg1", "pkg2", "pkg3", "pkg4", "pkg5", "pkg6"],
            safe_to_remove=False,
        )
        recs = self.engine.get_recommendations(result)
        self.assertTrue(any("HIGH IMPACT" in rec for rec in recs))

    def test_running_services_recommendation(self):
        """Test recommendations when services are running"""
        result = ImpactResult(
            target_package="nginx",
            affected_services=[
                ServiceInfo(
                    name="nginx",
                    status=ServiceStatus.RUNNING,
                    package="nginx",
                    is_critical=False,
                )
            ],
            safe_to_remove=True,
        )
        recs = self.engine.get_recommendations(result)
        self.assertTrue(any("Stop affected services" in rec for rec in recs))

    def test_critical_services_recommendation(self):
        """Test recommendations for critical services"""
        result = ImpactResult(
            target_package="openssh-server",
            affected_services=[
                ServiceInfo(
                    name="sshd",
                    status=ServiceStatus.RUNNING,
                    package="openssh-server",
                    is_critical=True,
                )
            ],
            safe_to_remove=False,
        )
        recs = self.engine.get_recommendations(result)
        self.assertTrue(any("Critical services" in rec for rec in recs))

    def test_orphaned_packages_recommendation(self):
        """Test recommendations for orphaned packages"""
        result = ImpactResult(
            target_package="some-pkg",
            orphaned_packages=["dep1", "dep2", "dep3"],
            safe_to_remove=True,
        )
        recs = self.engine.get_recommendations(result)
        self.assertTrue(any("autoremove" in rec for rec in recs))

    def test_safe_removal_recommendation(self):
        """Test recommendations for safe removal"""
        result = ImpactResult(
            target_package="leafpad",
            safe_to_remove=True,
        )
        recs = self.engine.get_recommendations(result)
        self.assertTrue(any("safely removed" in rec for rec in recs))

    def test_suggest_alternatives(self):
        """Test alternative package suggestions"""
        alternatives = self.engine._suggest_alternatives("nginx")
        self.assertIn("apache2", alternatives)
        self.assertIn("caddy", alternatives)

    def test_safe_removal_order(self):
        """Test safe removal order calculation"""
        self.graph.get_reverse_dependencies.side_effect = lambda x: {
            "dep1": [],
            "dep2": ["dep1"],
            "main-pkg": ["dep2"],
        }.get(x, [])

        order = self.engine.get_safe_removal_order(["main-pkg", "dep1", "dep2"])
        # dep1 should come first (no dependents), then dep2, then main-pkg
        self.assertEqual(order[0], "dep1")


class TestImpactAnalyzer(unittest.TestCase):
    """Tests for ImpactAnalyzer"""

    def setUp(self):
        self.analyzer = ImpactAnalyzer()

    @patch.object(DependencyGraphBuilder, "initialize")
    @patch.object(DependencyGraphBuilder, "get_package_info")
    @patch.object(ImpactAnalyzer, "_package_exists_in_apt")
    def test_analyze_not_installed(self, mock_exists, mock_info, mock_init):
        """Test analyzing a package that's not installed"""
        mock_info.return_value = None
        mock_exists.return_value = False  # Package doesn't exist in repos
        result = self.analyzer.analyze("nonexistent-pkg")
        self.assertTrue(any("not found in repositories" in w for w in result.warnings))

    @patch.object(DependencyGraphBuilder, "initialize")
    @patch.object(DependencyGraphBuilder, "get_package_info")
    @patch.object(ImpactAnalyzer, "_package_exists_in_apt")
    def test_analyze_not_installed_but_exists(self, mock_exists, mock_info, mock_init):
        """Test analyzing a package that exists in repos but is not installed"""
        mock_info.return_value = None
        mock_exists.return_value = True  # Package exists in repos
        # Mock other methods to prevent subprocess calls
        self.analyzer.graph.get_reverse_dependencies = MagicMock(return_value=[])
        self.analyzer.graph.get_transitive_dependents = MagicMock(return_value=([], 0))
        self.analyzer.graph._run_command = MagicMock(return_value=(False, "", ""))
        self.analyzer.service_mapper.get_affected_services = MagicMock(return_value=[])

        result = self.analyzer.analyze("nginx")
        self.assertTrue(any("not currently installed" in w for w in result.warnings))

    @patch.object(DependencyGraphBuilder, "initialize")
    @patch.object(DependencyGraphBuilder, "get_package_info")
    def test_analyze_essential_package(self, mock_info, mock_init):
        """Test analyzing an essential package"""
        mock_info.return_value = PackageNode(
            name="base-files",
            is_installed=True,
            is_essential=True,
        )
        # Mock other methods to prevent subprocess calls
        self.analyzer.graph.get_reverse_dependencies = MagicMock(return_value=[])
        self.analyzer.graph.get_transitive_dependents = MagicMock(return_value=([], 0))
        self.analyzer.graph._run_command = MagicMock(return_value=(False, "", ""))
        self.analyzer.service_mapper.get_affected_services = MagicMock(return_value=[])

        result = self.analyzer.analyze("base-files")
        self.assertEqual(result.severity, ImpactSeverity.CRITICAL)
        self.assertFalse(result.safe_to_remove)

    def test_calculate_severity_safe(self):
        """Test severity calculation for safe package"""
        result = ImpactResult(
            target_package="leafpad",
            total_affected=0,
            affected_services=[],
        )
        severity = self.analyzer._calculate_severity(result)
        self.assertEqual(severity, ImpactSeverity.SAFE)

    def test_calculate_severity_low(self):
        """Test severity calculation for low impact"""
        result = ImpactResult(
            target_package="some-pkg",
            total_affected=3,
            affected_services=[],
        )
        severity = self.analyzer._calculate_severity(result)
        self.assertEqual(severity, ImpactSeverity.LOW)

    def test_calculate_severity_medium(self):
        """Test severity calculation for medium impact"""
        result = ImpactResult(
            target_package="some-pkg",
            total_affected=10,
            affected_services=[],
        )
        severity = self.analyzer._calculate_severity(result)
        self.assertEqual(severity, ImpactSeverity.MEDIUM)

    def test_calculate_severity_high(self):
        """Test severity calculation for high impact"""
        result = ImpactResult(
            target_package="some-pkg",
            total_affected=25,
            affected_services=[],
        )
        severity = self.analyzer._calculate_severity(result)
        self.assertEqual(severity, ImpactSeverity.HIGH)

    def test_calculate_severity_critical_by_count(self):
        """Test severity calculation for critical impact by count"""
        result = ImpactResult(
            target_package="some-pkg",
            total_affected=60,
            affected_services=[],
        )
        severity = self.analyzer._calculate_severity(result)
        self.assertEqual(severity, ImpactSeverity.CRITICAL)

    def test_calculate_severity_critical_service(self):
        """Test severity calculation with critical running service"""
        result = ImpactResult(
            target_package="openssh-server",
            total_affected=1,
            affected_services=[
                ServiceInfo(
                    name="sshd",
                    status=ServiceStatus.RUNNING,
                    package="openssh-server",
                    is_critical=True,
                )
            ],
        )
        severity = self.analyzer._calculate_severity(result)
        self.assertEqual(severity, ImpactSeverity.CRITICAL)


class TestUninstallImpactAnalyzer(unittest.TestCase):
    """Tests for UninstallImpactAnalyzer (main interface)"""

    def setUp(self):
        self.analyzer = UninstallImpactAnalyzer()

    @patch.object(ImpactAnalyzer, "analyze")
    def test_analyze_delegates_to_internal(self, mock_analyze):
        """Test that analyze delegates to internal analyzer"""
        mock_analyze.return_value = ImpactResult(target_package="test")
        result = self.analyzer.analyze("test")
        mock_analyze.assert_called_once_with("test")
        self.assertEqual(result.target_package, "test")

    @patch.object(ImpactAnalyzer, "generate_removal_plan")
    def test_get_removal_plan(self, mock_plan):
        """Test getting removal plan"""
        mock_plan.return_value = RemovalPlan(target_package="test")
        self.analyzer.get_removal_plan("test", purge=True)
        mock_plan.assert_called_once_with("test", True)

    def test_format_impact_report_safe(self):
        """Test formatting a safe impact report"""
        result = ImpactResult(
            target_package="leafpad",
            severity=ImpactSeverity.SAFE,
            safe_to_remove=True,
        )
        report = self.analyzer.format_impact_report(result)
        self.assertIn("leafpad", report)
        self.assertIn("✅", report)
        self.assertIn("Safe to remove", report)

    def test_format_impact_report_critical(self):
        """Test formatting a critical impact report"""
        result = ImpactResult(
            target_package="libc6",
            severity=ImpactSeverity.CRITICAL,
            warnings=["This is an essential package"],
            direct_dependents=["pkg1", "pkg2"],
            affected_services=[
                ServiceInfo(
                    name="critical-service",
                    status=ServiceStatus.RUNNING,
                    package="libc6",
                    is_critical=True,
                )
            ],
            total_affected=100,
            cascade_depth=5,
            recommendations=["Do not remove this package"],
            safe_to_remove=False,
        )
        report = self.analyzer.format_impact_report(result)
        self.assertIn("libc6", report)
        self.assertIn("🔴", report)
        self.assertIn("CRITICAL", report)
        self.assertIn("Review recommendations", report)

    def test_format_impact_report_with_services(self):
        """Test formatting report with affected services"""
        result = ImpactResult(
            target_package="nginx",
            affected_services=[
                ServiceInfo(
                    name="nginx",
                    status=ServiceStatus.RUNNING,
                    package="nginx",
                    is_critical=False,
                ),
                ServiceInfo(
                    name="nginx-helper",
                    status=ServiceStatus.STOPPED,
                    package="nginx",
                    is_critical=False,
                ),
            ],
            safe_to_remove=True,
        )
        report = self.analyzer.format_impact_report(result)
        self.assertIn("Affected services", report)
        self.assertIn("nginx", report)

    def test_format_impact_report_with_cascade(self):
        """Test formatting report with cascade packages"""
        result = ImpactResult(
            target_package="some-pkg",
            cascade_packages=["dep1", "dep2", "dep3"],
            safe_to_remove=True,
        )
        report = self.analyzer.format_impact_report(result)
        self.assertIn("Cascade removal", report)

    def test_format_impact_report_with_orphans(self):
        """Test formatting report with orphaned packages"""
        result = ImpactResult(
            target_package="some-pkg",
            orphaned_packages=["orphan1", "orphan2"],
            safe_to_remove=True,
        )
        report = self.analyzer.format_impact_report(result)
        self.assertIn("orphaned", report.lower())


class TestRemovalPlan(unittest.TestCase):
    """Tests for RemovalPlan dataclass"""

    def test_removal_plan_defaults(self):
        """Test removal plan default values"""
        plan = RemovalPlan(target_package="test")
        self.assertEqual(plan.target_package, "test")
        self.assertEqual(plan.packages_to_remove, [])
        self.assertEqual(plan.autoremove_candidates, [])
        self.assertEqual(plan.config_files_affected, [])
        self.assertEqual(plan.commands, [])
        self.assertEqual(plan.estimated_freed_space, "")

    def test_removal_plan_with_values(self):
        """Test removal plan with values"""
        plan = RemovalPlan(
            target_package="nginx",
            packages_to_remove=["nginx", "nginx-common"],
            autoremove_candidates=["nginx-doc"],
            config_files_affected=["/etc/nginx/nginx.conf"],
            commands=["sudo apt-get remove -y nginx"],
            estimated_freed_space="15.2 MB",
        )
        self.assertEqual(plan.target_package, "nginx")
        self.assertEqual(len(plan.packages_to_remove), 2)
        self.assertEqual(plan.estimated_freed_space, "15.2 MB")


class TestDependencyEdge(unittest.TestCase):
    """Tests for DependencyEdge dataclass"""

    def test_dependency_edge_creation(self):
        """Test creating a dependency edge"""
        edge = DependencyEdge(
            from_package="nginx",
            to_package="libc6",
            dependency_type="depends",
        )
        self.assertEqual(edge.from_package, "nginx")
        self.assertEqual(edge.to_package, "libc6")
        self.assertEqual(edge.dependency_type, "depends")

    def test_dependency_edge_default_type(self):
        """Test dependency edge default type"""
        edge = DependencyEdge(from_package="a", to_package="b")
        self.assertEqual(edge.dependency_type, "depends")


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete analysis flow"""

    @patch.object(DependencyGraphBuilder, "_run_command")
    @patch.object(ServiceImpactMapper, "_run_command")
    def test_full_analysis_flow_mocked(self, mock_service_cmd, mock_graph_cmd):
        """Test complete analysis flow with mocked subprocess calls"""
        # Setup mocks
        mock_graph_cmd.side_effect = self._mock_graph_commands
        mock_service_cmd.return_value = (True, "active", "")

        analyzer = UninstallImpactAnalyzer()

        # Force initialize with mocked data
        analyzer._analyzer.graph._installed_packages = {"test-pkg", "dep1", "dep2"}
        analyzer._analyzer.graph._essential_packages = set()
        analyzer._analyzer.graph._manual_packages = {"test-pkg"}
        analyzer._analyzer.graph._initialized = True

        # Mock package info
        analyzer._analyzer.graph._package_info["test-pkg"] = PackageNode(
            name="test-pkg",
            version="1.0.0",
            is_installed=True,
        )

        # Analysis should complete without errors
        result = analyzer.analyze("test-pkg")
        self.assertEqual(result.target_package, "test-pkg")

    def _mock_graph_commands(self, cmd, timeout=30):
        """Mock responses for graph builder commands"""
        if "dpkg-query" in cmd:
            if "-W" in cmd and "-f" in cmd:
                return (True, "test-pkg|1.0.0|Test package", "")
            return (True, "test-pkg\n", "")
        elif "apt-cache" in cmd:
            if "depends" in cmd:
                return (True, "test-pkg\n  Depends: dep1\n  Depends: dep2\n", "")
            elif "rdepends" in cmd:
                return (True, "test-pkg\nReverse Depends:\n", "")
        elif "apt-get" in cmd:
            return (False, "", "")
        elif "apt-mark" in cmd:
            return (True, "test-pkg\n", "")
        return (False, "", "Unknown command")


if __name__ == "__main__":
    unittest.main()
