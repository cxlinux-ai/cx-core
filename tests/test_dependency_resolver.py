#!/usr/bin/env python3
"""
Comprehensive tests for the Dependency Conflict Resolver with Visual Tree.
Tests all 5 bounty requirements:
  1. Visual Dependency Tree
  2. Conflict Prediction
  3. Impact Communication (Plain Language)
  4. Alternative Suggestions
  5. Orphan Package Management
"""
import sys
import os
import json
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cortex.dependency_resolver import (
    DependencyResolver,
    VisualTreeRenderer,
    ImpactCommunicator,
    OrphanPackageManager,
    Dependency,
    Conflict,
    ConflictType,
    ImpactAssessment,
    ImpactSeverity,
    OrphanPackage,
)


class TestVisualTreeRenderer(unittest.TestCase):
    """Test Bounty Requirement #1: Visual Dependency Tree."""

    def setUp(self):
        self.renderer = VisualTreeRenderer()
        # Create sample dependencies
        self.deps = [
            Dependency(name="dep1", version="2.0", is_satisfied=True, installed_version="2.0"),
            Dependency(name="dep2", version="1.0", is_satisfied=False),
            Dependency(name="dep3", version=None, is_satisfied=True, installed_version="3.0", is_optional=True),
        ]

    def test_render_tree_basic(self):
        """Test basic tree rendering."""
        tree = self.renderer.render_tree("test-package", self.deps)
        self.assertIn("test-package", tree)
        self.assertIn("dep1", tree)
        self.assertIn("dep2", tree)

    def test_render_tree_installed_markers(self):
        """Test that installed vs missing packages are marked differently."""
        tree = self.renderer.render_tree("test-package", self.deps)
        # Installed packages should have checkmark
        self.assertIn("✅", tree)
        # Missing packages should have X
        self.assertIn("❌", tree)

    def test_render_tree_versions(self):
        """Test that versions are displayed."""
        tree = self.renderer.render_tree("test-package", self.deps, show_versions=True)
        self.assertIn("2.0", tree)

    def test_render_with_conflicts(self):
        """Test tree rendering with conflicts."""
        conflicts = [
            Conflict(
                package_a="dep1",
                package_b="other",
                conflict_type=ConflictType.MUTUALLY_EXCLUSIVE,
                description="Test conflict"
            )
        ]
        tree = self.renderer.render_tree("test-package", self.deps, conflicts=conflicts)
        self.assertIn("test-package", tree)

    def test_render_with_optional(self):
        """Test optional dependency rendering."""
        tree = self.renderer.render_tree("test-package", self.deps)
        self.assertIn("Optional", tree)


class TestImpactCommunicator(unittest.TestCase):
    """Test Bounty Requirement #3: Impact Communication (Plain Language)."""

    def setUp(self):
        self.communicator = ImpactCommunicator()

    def test_explain_conflict(self):
        """Test conflict explanation in plain language."""
        conflict = Conflict(
            package_a="docker-ce",
            package_b="docker.io",
            conflict_type=ConflictType.PROVIDES_SAME,
            description="Both provide Docker runtime"
        )
        message = self.communicator.explain_conflict(conflict)
        # Should be understandable
        self.assertIn("docker", message.lower())

    def test_explain_impact(self):
        """Test impact explanation."""
        assessment = ImpactAssessment(
            package="python3",
            action="remove",
            severity=ImpactSeverity.HIGH,
            affected_packages=["pip", "virtualenv"],
            plain_language_explanation="Removing python3 will break pip",
            recommendation="Don't remove"
        )
        message = self.communicator.explain_impact(assessment)
        self.assertIsInstance(message, str)
        self.assertIn("python3", message.lower())

    def test_generate_summary(self):
        """Test summary generation."""
        deps = [
            Dependency(name="libcurl4", version="7.0", is_satisfied=False),
            Dependency(name="libc6", version="2.0", is_satisfied=True, installed_version="2.0"),
        ]
        summary = self.communicator.generate_summary("curl", deps, [])
        self.assertIn("curl", summary.lower())


class TestOrphanPackageManager(unittest.TestCase):
    """Test Bounty Requirement #5: Orphan Package Management."""

    def setUp(self):
        self.resolver = DependencyResolver()
        self.manager = OrphanPackageManager(self.resolver)

    def test_find_orphans_method(self):
        """Test orphan detection method exists."""
        self.assertTrue(hasattr(self.manager, 'find_orphans'))
        # Method should return a list of OrphanPackage
        result = self.manager.find_orphans()
        self.assertIsInstance(result, list)

    def test_get_cleanup_commands(self):
        """Test cleanup command generation."""
        orphans = [
            OrphanPackage(name="libfoo", installed_version="1.0"),
            OrphanPackage(name="libbar", installed_version="2.0"),
        ]
        commands = self.manager.get_orphan_cleanup_commands(orphans)
        self.assertTrue(len(commands) > 0)
        # Should suggest apt remove
        self.assertTrue(any("apt" in cmd for cmd in commands))

    def test_estimate_space_savings(self):
        """Test space savings estimation."""
        orphans = [
            OrphanPackage(name="libfoo", installed_version="1.0"),
            OrphanPackage(name="libbar", installed_version="2.0"),
        ]
        # Method should exist and return a value
        savings = self.manager.estimate_space_savings(orphans)
        self.assertIsInstance(savings, (int, float, str))


class TestDependencyResolver(unittest.TestCase):
    """Test the main DependencyResolver class integration."""

    def setUp(self):
        self.resolver = DependencyResolver()

    def test_analyze_installation(self):
        """Test full installation analysis."""
        result = self.resolver.analyze_installation("wget")
        self.assertIn("tree", result)
        self.assertIn("summary", result)
        self.assertIn("conflicts", result)
        self.assertIn("dependencies", result)

    def test_analyze_removal(self):
        """Test removal impact analysis."""
        result = self.resolver.analyze_removal("wget")
        # Severity is nested under impact
        self.assertIn("impact", result)
        self.assertIn("severity", result["impact"])

    def test_find_orphans(self):
        """Test orphan finding."""
        result = self.resolver.find_orphans()
        self.assertIsInstance(result, dict)


class TestEndToEnd(unittest.TestCase):
    """End-to-end integration tests."""

    def test_full_workflow_install(self):
        """Test complete installation analysis workflow."""
        resolver = DependencyResolver()
        result = resolver.analyze_installation("curl")

        # Should have all required fields
        self.assertIn("tree", result)
        self.assertIn("summary", result)
        self.assertIn("dependencies", result)
        self.assertIn("conflicts", result)
        self.assertIn("impact", result)

    def test_full_workflow_removal(self):
        """Test complete removal analysis workflow."""
        resolver = DependencyResolver()
        result = resolver.analyze_removal("curl")

        # Should have impact information
        self.assertIn("impact", result)
        self.assertIn("severity", result["impact"])

    def test_json_export(self):
        """Test JSON export format."""
        resolver = DependencyResolver()
        result = resolver.analyze_installation("wget")

        # Should be JSON serializable
        json_str = json.dumps(result, default=str)
        parsed = json.loads(json_str)
        self.assertIn("tree", parsed)


class TestBountyRequirements(unittest.TestCase):
    """Verify all bounty requirements are met."""

    def test_requirement_1_visual_tree(self):
        """Bounty #1: Dependency Tree Visualization."""
        resolver = DependencyResolver()
        result = resolver.analyze_installation("curl")
        tree = result.get("tree", "")

        # Tree should have visual characters
        self.assertTrue(any(c in tree for c in ["├", "└", "│", "─"]))
        # Tree should show package hierarchy
        self.assertIn("curl", tree.lower())

    def test_requirement_2_conflict_prediction(self):
        """Bounty #2: Conflict Prediction."""
        resolver = DependencyResolver()
        # The resolver should have conflict prediction
        result = resolver.analyze_installation("curl")
        self.assertIn("conflicts", result)
        self.assertIsInstance(result["conflicts"], list)

    def test_requirement_3_plain_language(self):
        """Bounty #3: Impact Communication (Plain Language)."""
        resolver = DependencyResolver()
        result = resolver.analyze_installation("curl")
        summary = result.get("summary", "")

        # Should not contain overly technical jargon
        jargon = ["dpkg", "transitive closure"]
        for term in jargon:
            self.assertNotIn(term, summary.lower())

    def test_requirement_4_alternatives(self):
        """Bounty #4: Alternative Suggestions."""
        # Test that Conflict class supports alternatives
        conflict = Conflict(
            package_a="docker-ce",
            package_b="docker.io",
            conflict_type=ConflictType.PROVIDES_SAME,
            description="Test",
            alternatives=["podman", "containerd"]
        )
        self.assertEqual(len(conflict.alternatives), 2)
        self.assertIn("podman", conflict.alternatives)

    def test_requirement_5_orphan_management(self):
        """Bounty #5: Orphan Package Management."""
        resolver = DependencyResolver()
        manager = OrphanPackageManager(resolver)

        # Should have detection methods
        self.assertTrue(hasattr(manager, 'find_orphans'))
        # Should have cleanup generation
        self.assertTrue(hasattr(manager, 'get_orphan_cleanup_commands'))
        # Should have space savings estimation
        self.assertTrue(hasattr(manager, 'estimate_space_savings'))


class TestCLI(unittest.TestCase):
    """Test CLI functionality."""

    def test_cli_help(self):
        """Test CLI help output."""
        import subprocess
        result = subprocess.run(
            ["python3", "cortex/dependency_resolver.py", "--help"],
            capture_output=True,
            text=True,
            cwd="/tmp/cortex"
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--tree", result.stdout)
        self.assertIn("--analyze", result.stdout)
        self.assertIn("--orphans", result.stdout)

    def test_cli_tree(self):
        """Test CLI tree output."""
        import subprocess
        result = subprocess.run(
            ["python3", "cortex/dependency_resolver.py", "wget", "--tree"],
            capture_output=True,
            text=True,
            cwd="/tmp/cortex"
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("wget", result.stdout.lower())

    def test_cli_analyze(self):
        """Test CLI analyze output."""
        import subprocess
        result = subprocess.run(
            ["python3", "cortex/dependency_resolver.py", "wget", "--analyze"],
            capture_output=True,
            text=True,
            cwd="/tmp/cortex"
        )
        self.assertEqual(result.returncode, 0)

    def test_cli_json(self):
        """Test CLI JSON output."""
        import subprocess
        result = subprocess.run(
            ["python3", "cortex/dependency_resolver.py", "wget", "--analyze", "--json"],
            capture_output=True,
            text=True,
            cwd="/tmp/cortex"
        )
        self.assertEqual(result.returncode, 0)
        # Should be valid JSON
        data = json.loads(result.stdout)
        self.assertIn("tree", data)


if __name__ == "__main__":
    # Run with verbose output
    unittest.main(verbosity=2)
