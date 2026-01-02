#!/usr/bin/env python3
"""
Tests for batch installer module
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.batch_installer import (
    BatchInstaller,
    BatchInstallationResult,
    PackageInstallation,
    PackageStatus,
)
from cortex.dependency_resolver import DependencyGraph, Dependency


class TestPackageInstallation(unittest.TestCase):
    """Test PackageInstallation dataclass"""

    def test_package_installation_creation(self):
        """Test creating a PackageInstallation"""
        pkg = PackageInstallation(name="nginx")
        self.assertEqual(pkg.name, "nginx")
        self.assertEqual(pkg.status, PackageStatus.PENDING)
        self.assertEqual(pkg.commands, [])
        self.assertIsNone(pkg.dependency_graph)

    def test_duration_calculation(self):
        """Test duration calculation"""
        pkg = PackageInstallation(name="test")
        self.assertIsNone(pkg.duration())

        pkg.start_time = 100.0
        pkg.end_time = 105.5
        self.assertEqual(pkg.duration(), 5.5)


class TestBatchInstaller(unittest.TestCase):
    """Test BatchInstaller class"""

    def setUp(self):
        """Set up test fixtures"""
        self.installer = BatchInstaller(max_workers=2)

    @patch("cortex.batch_installer.DependencyResolver")
    def test_analyze_packages(self, mock_resolver_class):
        """Test package analysis"""
        # Mock dependency resolver
        mock_resolver = Mock()
        mock_resolver_class.return_value = mock_resolver

        # Create mock dependency graph
        mock_graph = DependencyGraph(
            package_name="nginx",
            direct_dependencies=[],
            all_dependencies=[],
            conflicts=[],
            installation_order=["nginx"],
        )
        mock_resolver.resolve_dependencies.return_value = mock_graph

        installer = BatchInstaller()
        packages = installer.analyze_packages(["nginx", "docker"])

        self.assertEqual(len(packages), 2)
        self.assertIn("nginx", packages)
        self.assertIn("docker", packages)
        self.assertEqual(packages["nginx"].status, PackageStatus.RESOLVING)

    def test_topological_sort(self):
        """Test topological sort algorithm"""
        package_dependencies = {
            "nginx": {"libc6", "libpcre3"},
            "docker": {"libc6", "iptables"},
        }
        all_dependencies = {"libc6", "libpcre3", "iptables"}

        result = self.installer._topological_sort(package_dependencies, all_dependencies)

        # Dependencies should come before packages
        self.assertIn("libc6", result)
        self.assertIn("libpcre3", result)
        self.assertIn("iptables", result)
        self.assertIn("nginx", result)
        self.assertIn("docker", result)

        # Check that dependencies appear before packages
        dep_indices = [result.index(d) for d in all_dependencies]
        pkg_indices = [result.index(p) for p in package_dependencies.keys()]
        self.assertTrue(max(dep_indices) < min(pkg_indices))

    @patch("cortex.batch_installer.DependencyResolver")
    def test_optimize_dependency_graph(self, mock_resolver_class):
        """Test dependency graph optimization"""
        mock_resolver = Mock()
        mock_resolver_class.return_value = mock_resolver
        mock_resolver.is_package_installed.return_value = False

        # Create mock packages with dependencies
        packages = {
            "nginx": PackageInstallation(
                name="nginx",
                dependency_graph=DependencyGraph(
                    package_name="nginx",
                    direct_dependencies=[],
                    all_dependencies=[
                        Dependency(name="libc6", is_satisfied=False),
                        Dependency(name="libpcre3", is_satisfied=False),
                    ],
                    conflicts=[],
                    installation_order=["libc6", "libpcre3", "nginx"],
                ),
            ),
            "docker": PackageInstallation(
                name="docker",
                dependency_graph=DependencyGraph(
                    package_name="docker",
                    direct_dependencies=[],
                    all_dependencies=[
                        Dependency(name="libc6", is_satisfied=False),
                        Dependency(name="iptables", is_satisfied=False),
                    ],
                    conflicts=[],
                    installation_order=["libc6", "iptables", "docker"],
                ),
            ),
        }

        installer = BatchInstaller()
        installer.dependency_resolver = mock_resolver

        optimized = installer.optimize_dependency_graph(packages)

        # Should have shared deps and individual packages
        self.assertIn("_shared_deps", optimized)
        self.assertIn("nginx", optimized)
        self.assertIn("docker", optimized)

        # Shared deps should contain libc6 (common dependency)
        shared_commands = optimized["_shared_deps"]
        self.assertTrue(any("libc6" in cmd for cmd in shared_commands))

    @patch("cortex.batch_installer.DependencyResolver")
    @patch("cortex.batch_installer.InstallationCoordinator")
    def test_install_batch_dry_run(self, mock_coordinator_class, mock_resolver_class):
        """Test batch installation in dry-run mode"""
        mock_resolver = Mock()
        mock_resolver_class.return_value = mock_resolver

        mock_graph = DependencyGraph(
            package_name="nginx",
            direct_dependencies=[],
            all_dependencies=[],
            conflicts=[],
            installation_order=["nginx"],
        )
        mock_resolver.resolve_dependencies.return_value = mock_graph
        mock_resolver.is_package_installed.return_value = False

        installer = BatchInstaller()
        result = installer.install_batch(["nginx"], execute=False, dry_run=True)

        self.assertIsInstance(result, BatchInstallationResult)
        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].status, PackageStatus.SKIPPED)
        self.assertGreater(len(result.packages[0].commands), 0)

    @patch("cortex.batch_installer.DependencyResolver")
    @patch("cortex.batch_installer.InstallationCoordinator")
    def test_install_batch_execute(self, mock_coordinator_class, mock_resolver_class):
        """Test batch installation with execution"""
        mock_resolver = Mock()
        mock_resolver_class.return_value = mock_resolver

        mock_graph = DependencyGraph(
            package_name="nginx",
            direct_dependencies=[],
            all_dependencies=[],
            conflicts=[],
            installation_order=["nginx"],
        )
        mock_resolver.resolve_dependencies.return_value = mock_graph
        mock_resolver.is_package_installed.return_value = False

        # Mock successful installation
        mock_result = Mock()
        mock_result.success = True
        mock_result.total_duration = 10.0
        mock_result.error_message = None

        mock_coordinator = Mock()
        mock_coordinator.execute.return_value = mock_result
        mock_coordinator_class.return_value = mock_coordinator

        installer = BatchInstaller(max_workers=1)
        result = installer.install_batch(["nginx"], execute=True, dry_run=False)

        self.assertIsInstance(result, BatchInstallationResult)
        self.assertEqual(len(result.successful), 1)
        self.assertEqual(len(result.failed), 0)

    def test_batch_installation_result_properties(self):
        """Test BatchInstallationResult properties"""
        packages = [
            PackageInstallation(name="nginx", status=PackageStatus.SUCCESS),
            PackageInstallation(name="docker", status=PackageStatus.FAILED),
        ]

        result = BatchInstallationResult(
            packages=packages,
            total_duration=100.0,
            successful=["nginx"],
            failed=["docker"],
            skipped=[],
            total_dependencies=10,
            optimized_dependencies=5,
        )

        self.assertEqual(result.success_rate, 50.0)
        self.assertEqual(len(result.successful), 1)
        self.assertEqual(len(result.failed), 1)

    @patch("cortex.batch_installer.DependencyResolver")
    def test_rollback_batch(self, mock_resolver_class):
        """Test batch rollback"""
        mock_resolver = Mock()
        mock_resolver_class.return_value = mock_resolver

        packages = [
            PackageInstallation(
                name="nginx",
                status=PackageStatus.SUCCESS,
                rollback_commands=["sudo apt-get remove -y nginx"],
            )
        ]

        result = BatchInstallationResult(
            packages=packages,
            total_duration=100.0,
            successful=["nginx"],
            failed=[],
            skipped=[],
            total_dependencies=5,
            optimized_dependencies=3,
        )

        installer = BatchInstaller(enable_rollback=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            success = installer.rollback_batch(result)
            self.assertTrue(success)
            self.assertTrue(mock_run.called)

    def test_rollback_disabled(self):
        """Test that rollback is skipped when disabled"""
        packages = [
            PackageInstallation(
                name="nginx",
                status=PackageStatus.SUCCESS,
                rollback_commands=["sudo apt-get remove -y nginx"],
            )
        ]

        result = BatchInstallationResult(
            packages=packages,
            total_duration=100.0,
            successful=["nginx"],
            failed=[],
            skipped=[],
            total_dependencies=5,
            optimized_dependencies=3,
        )

        installer = BatchInstaller(enable_rollback=False)
        success = installer.rollback_batch(result)
        self.assertFalse(success)


class TestBatchInstallerIntegration(unittest.TestCase):
    """Integration tests for batch installer"""

    @patch("cortex.batch_installer.DependencyResolver")
    def test_multiple_packages_with_shared_deps(self, mock_resolver_class):
        """Test installing multiple packages with shared dependencies"""
        mock_resolver = Mock()
        mock_resolver_class.return_value = mock_resolver
        mock_resolver.is_package_installed.return_value = False

        # Create dependency graphs with shared dependency (libc6)
        def mock_resolve(package_name):
            if package_name == "nginx":
                return DependencyGraph(
                    package_name="nginx",
                    direct_dependencies=[],
                    all_dependencies=[
                        Dependency(name="libc6", is_satisfied=False),
                        Dependency(name="libpcre3", is_satisfied=False),
                    ],
                    conflicts=[],
                    installation_order=["libc6", "libpcre3", "nginx"],
                )
            elif package_name == "docker":
                return DependencyGraph(
                    package_name="docker",
                    direct_dependencies=[],
                    all_dependencies=[
                        Dependency(name="libc6", is_satisfied=False),
                        Dependency(name="iptables", is_satisfied=False),
                    ],
                    conflicts=[],
                    installation_order=["libc6", "iptables", "docker"],
                )
            return DependencyGraph(
                package_name=package_name,
                direct_dependencies=[],
                all_dependencies=[],
                conflicts=[],
                installation_order=[package_name],
            )

        mock_resolver.resolve_dependencies.side_effect = mock_resolve

        installer = BatchInstaller()
        packages = installer.analyze_packages(["nginx", "docker"])

        self.assertEqual(len(packages), 2)
        self.assertIsNotNone(packages["nginx"].dependency_graph)
        self.assertIsNotNone(packages["docker"].dependency_graph)

        # Test optimization
        optimized = installer.optimize_dependency_graph(packages)

        # Should have shared dependencies
        self.assertIn("_shared_deps", optimized)
        # libc6 should be in shared deps since both packages need it
        shared_commands = " ".join(optimized["_shared_deps"])
        self.assertIn("libc6", shared_commands)


if __name__ == "__main__":
    unittest.main()
