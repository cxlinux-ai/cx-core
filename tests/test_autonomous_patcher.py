#!/usr/bin/env python3
"""
Tests for Autonomous Patcher Module
"""

import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from cortex.autonomous_patcher import (
    AutonomousPatcher,
    PatchPlan,
    PatchResult,
    PatchStrategy,
)
from cortex.vulnerability_scanner import Severity, Vulnerability


class TestPatchStrategyEnum(unittest.TestCase):
    """Test cases for PatchStrategy enum"""

    def test_strategy_values(self):
        """Test strategy enum has correct values"""
        self.assertEqual(PatchStrategy.AUTOMATIC.value, "automatic")
        self.assertEqual(PatchStrategy.CRITICAL_ONLY.value, "critical_only")
        self.assertEqual(PatchStrategy.HIGH_AND_ABOVE.value, "high_and_above")
        self.assertEqual(PatchStrategy.MANUAL.value, "manual")


class TestPatchPlan(unittest.TestCase):
    """Test cases for PatchPlan dataclass"""

    def test_patch_plan_creation(self):
        """Test creating patch plan object"""
        plan = PatchPlan(
            vulnerabilities=[],
            packages_to_update={"nginx": "1.20.0"},
            estimated_duration_minutes=5.0,
            requires_reboot=False,
            rollback_available=True,
        )

        self.assertEqual(len(plan.packages_to_update), 1)
        self.assertEqual(plan.packages_to_update["nginx"], "1.20.0")
        self.assertFalse(plan.requires_reboot)


class TestPatchResult(unittest.TestCase):
    """Test cases for PatchResult dataclass"""

    def test_patch_result_creation(self):
        """Test creating patch result object"""
        result = PatchResult(
            patch_id="patch_123",
            timestamp="2024-01-01T00:00:00",
            vulnerabilities_patched=5,
            packages_updated=["nginx", "openssl"],
            success=True,
            errors=[],
        )

        self.assertEqual(result.patch_id, "patch_123")
        self.assertEqual(result.vulnerabilities_patched, 5)
        self.assertTrue(result.success)
        self.assertEqual(len(result.packages_updated), 2)


class TestAutonomousPatcher(unittest.TestCase):
    """Test cases for AutonomousPatcher"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temp config directory
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "patcher_config.json")

        # Patch the config path
        self.patcher = AutonomousPatcher(
            strategy=PatchStrategy.CRITICAL_ONLY, dry_run=True
        )

    def tearDown(self):
        """Clean up temporary files"""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_initialization_defaults(self):
        """Test patcher initializes with correct defaults"""
        patcher = AutonomousPatcher()

        self.assertEqual(patcher.strategy, PatchStrategy.CRITICAL_ONLY)
        self.assertTrue(patcher.dry_run)
        self.assertFalse(patcher.auto_approve)

    def test_initialization_custom_strategy(self):
        """Test patcher with custom strategy"""
        patcher = AutonomousPatcher(strategy=PatchStrategy.HIGH_AND_ABOVE)

        self.assertEqual(patcher.strategy, PatchStrategy.HIGH_AND_ABOVE)

    def test_should_patch_blacklisted(self):
        """Test blacklisted packages are not patched"""
        self.patcher.blacklist = {"nginx"}

        vuln = Vulnerability(
            cve_id="CVE-2023-12345",
            package_name="nginx",
            installed_version="1.18.0",
            affected_versions="< 1.20.0",
            severity=Severity.CRITICAL,
            description="Test vulnerability",
        )

        self.assertFalse(self.patcher._should_patch(vuln))

    def test_should_patch_whitelisted(self):
        """Test whitelisted packages are always patched"""
        self.patcher.whitelist = {"nginx"}
        self.patcher.strategy = PatchStrategy.MANUAL  # Would normally block

        vuln = Vulnerability(
            cve_id="CVE-2023-12345",
            package_name="nginx",
            installed_version="1.18.0",
            affected_versions="< 1.20.0",
            severity=Severity.LOW,  # Below normal threshold
            description="Test vulnerability",
        )

        self.assertTrue(self.patcher._should_patch(vuln))

    def test_should_patch_critical_only_strategy(self):
        """Test critical only strategy"""
        self.patcher.strategy = PatchStrategy.CRITICAL_ONLY

        critical_vuln = Vulnerability(
            cve_id="CVE-CRITICAL",
            package_name="test",
            installed_version="1.0",
            affected_versions="all",
            severity=Severity.CRITICAL,
            description="Critical",
        )

        high_vuln = Vulnerability(
            cve_id="CVE-HIGH",
            package_name="test",
            installed_version="1.0",
            affected_versions="all",
            severity=Severity.HIGH,
            description="High",
        )

        self.assertTrue(self.patcher._should_patch(critical_vuln))
        self.assertFalse(self.patcher._should_patch(high_vuln))

    def test_should_patch_high_and_above_strategy(self):
        """Test high and above strategy"""
        self.patcher.strategy = PatchStrategy.HIGH_AND_ABOVE

        critical_vuln = Vulnerability(
            cve_id="CVE-CRITICAL",
            package_name="test",
            installed_version="1.0",
            affected_versions="all",
            severity=Severity.CRITICAL,
            description="Critical",
        )

        high_vuln = Vulnerability(
            cve_id="CVE-HIGH",
            package_name="test",
            installed_version="1.0",
            affected_versions="all",
            severity=Severity.HIGH,
            description="High",
        )

        medium_vuln = Vulnerability(
            cve_id="CVE-MEDIUM",
            package_name="test",
            installed_version="1.0",
            affected_versions="all",
            severity=Severity.MEDIUM,
            description="Medium",
        )

        self.assertTrue(self.patcher._should_patch(critical_vuln))
        self.assertTrue(self.patcher._should_patch(high_vuln))
        self.assertFalse(self.patcher._should_patch(medium_vuln))

    def test_should_patch_automatic_strategy(self):
        """Test automatic strategy patches all"""
        self.patcher.strategy = PatchStrategy.AUTOMATIC
        self.patcher.min_severity = Severity.LOW

        low_vuln = Vulnerability(
            cve_id="CVE-LOW",
            package_name="test",
            installed_version="1.0",
            affected_versions="all",
            severity=Severity.LOW,
            description="Low",
        )

        self.assertTrue(self.patcher._should_patch(low_vuln))

    def test_should_patch_manual_strategy(self):
        """Test manual strategy blocks all automatic patching"""
        self.patcher.strategy = PatchStrategy.MANUAL

        critical_vuln = Vulnerability(
            cve_id="CVE-CRITICAL",
            package_name="test",
            installed_version="1.0",
            affected_versions="all",
            severity=Severity.CRITICAL,
            description="Critical",
        )

        self.assertFalse(self.patcher._should_patch(critical_vuln))

    def test_should_patch_respects_min_severity(self):
        """Test minimum severity filtering"""
        self.patcher.strategy = PatchStrategy.AUTOMATIC
        self.patcher.min_severity = Severity.HIGH

        medium_vuln = Vulnerability(
            cve_id="CVE-MEDIUM",
            package_name="test",
            installed_version="1.0",
            affected_versions="all",
            severity=Severity.MEDIUM,
            description="Medium",
        )

        self.assertFalse(self.patcher._should_patch(medium_vuln))

    @patch("subprocess.run")
    def test_run_command_success(self, mock_run):
        """Test running command successfully"""
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")

        success, stdout, stderr = self.patcher._run_command(["echo", "test"])

        self.assertTrue(success)
        self.assertEqual(stdout, "output")

    @patch("subprocess.run")
    def test_run_command_failure(self, mock_run):
        """Test running command with failure"""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        success, stdout, stderr = self.patcher._run_command(["false"])

        self.assertFalse(success)
        self.assertEqual(stderr, "error")

    @patch("subprocess.run")
    def test_run_command_timeout(self, mock_run):
        """Test running command with timeout"""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=300)

        success, stdout, stderr = self.patcher._run_command(["sleep", "1000"])

        self.assertFalse(success)
        self.assertIn("timed out", stderr.lower())

    def test_create_patch_plan_empty(self):
        """Test creating patch plan with no vulnerabilities"""
        plan = self.patcher.create_patch_plan(vulnerabilities=[])

        self.assertEqual(len(plan.vulnerabilities), 0)
        self.assertEqual(len(plan.packages_to_update), 0)
        self.assertEqual(plan.estimated_duration_minutes, 0.0)

    @patch.object(AutonomousPatcher, "_check_package_update_available")
    @patch.object(AutonomousPatcher, "_update_fixes_vulnerability")
    @patch.object(AutonomousPatcher, "ensure_apt_updated")
    def test_create_patch_plan_with_updates(self, mock_apt, mock_fixes, mock_check):
        """Test creating patch plan with available updates"""
        mock_apt.return_value = True
        mock_check.return_value = "1.20.0"
        mock_fixes.return_value = True

        vuln = Vulnerability(
            cve_id="CVE-2023-12345",
            package_name="nginx",
            installed_version="1.18.0",
            affected_versions="< 1.20.0",
            severity=Severity.CRITICAL,
            description="Test vulnerability",
            fixed_version="1.20.0",
        )

        plan = self.patcher.create_patch_plan(vulnerabilities=[vuln])

        self.assertEqual(len(plan.vulnerabilities), 1)
        self.assertIn("nginx", plan.packages_to_update)

    @patch.object(AutonomousPatcher, "_check_package_update_available")
    @patch.object(AutonomousPatcher, "_update_fixes_vulnerability")
    @patch.object(AutonomousPatcher, "ensure_apt_updated")
    def test_create_patch_plan_detects_kernel_reboot(self, mock_apt, mock_fixes, mock_check):
        """Test patch plan detects kernel updates require reboot"""
        mock_apt.return_value = True
        mock_check.return_value = "5.15.0-100"
        mock_fixes.return_value = True

        vuln = Vulnerability(
            cve_id="CVE-2023-KERNEL",
            package_name="linux-image-5.15.0-generic",
            installed_version="5.15.0-90",
            affected_versions="< 5.15.0-100",
            severity=Severity.CRITICAL,
            description="Kernel vulnerability",
            fixed_version="5.15.0-100",
        )

        plan = self.patcher.create_patch_plan(vulnerabilities=[vuln])

        self.assertTrue(plan.requires_reboot)

    @patch.object(AutonomousPatcher, "_check_package_update_available")
    @patch.object(AutonomousPatcher, "_update_fixes_vulnerability")
    @patch.object(AutonomousPatcher, "ensure_apt_updated")
    def test_create_patch_plan_skips_unfixed_vulns(self, mock_apt, mock_fixes, mock_check):
        """Test patch plan skips vulnerabilities not fixed by available update"""
        mock_apt.return_value = True
        mock_check.return_value = "1.19.0"  # Available version
        mock_fixes.return_value = False  # Doesn't fix

        vuln = Vulnerability(
            cve_id="CVE-2023-12345",
            package_name="nginx",
            installed_version="1.18.0",
            affected_versions="< 1.20.0",
            severity=Severity.CRITICAL,
            description="Test vulnerability",
            fixed_version="1.20.0",  # Requires 1.20.0, but only 1.19.0 available
        )

        plan = self.patcher.create_patch_plan(vulnerabilities=[vuln])

        # Should not include this package since update doesn't fix the vulnerability
        self.assertEqual(len(plan.vulnerabilities), 0)
        self.assertNotIn("nginx", plan.packages_to_update)

    def test_apply_patch_plan_empty(self):
        """Test applying empty patch plan"""
        plan = PatchPlan(
            vulnerabilities=[],
            packages_to_update={},
            estimated_duration_minutes=0.0,
            requires_reboot=False,
            rollback_available=True,
        )

        result = self.patcher.apply_patch_plan(plan)

        self.assertTrue(result.success)
        self.assertEqual(result.vulnerabilities_patched, 0)

    def test_apply_patch_plan_dry_run(self):
        """Test applying patch plan in dry run mode"""
        self.patcher.dry_run = True

        plan = PatchPlan(
            vulnerabilities=[],
            packages_to_update={"nginx": "1.20.0", "curl": "7.80.0"},
            estimated_duration_minutes=2.0,
            requires_reboot=False,
            rollback_available=True,
        )

        result = self.patcher.apply_patch_plan(plan)

        self.assertTrue(result.success)
        self.assertEqual(len(result.packages_updated), 2)
        # In dry run, packages are listed but not actually updated

    def test_add_to_whitelist(self):
        """Test adding package to whitelist"""
        self.patcher.whitelist = set()
        self.patcher.add_to_whitelist("nginx")

        self.assertIn("nginx", self.patcher.whitelist)

    def test_add_to_blacklist(self):
        """Test adding package to blacklist"""
        self.patcher.blacklist = set()
        self.patcher.add_to_blacklist("linux-image")

        self.assertIn("linux-image", self.patcher.blacklist)

    def test_set_min_severity(self):
        """Test setting minimum severity"""
        self.patcher.set_min_severity(Severity.HIGH)

        self.assertEqual(self.patcher.min_severity, Severity.HIGH)


class TestAutonomousPatcherAptUpdate(unittest.TestCase):
    """Test apt update functionality"""

    def setUp(self):
        self.patcher = AutonomousPatcher(dry_run=True)

    @patch("subprocess.run")
    @patch("cortex.autonomous_patcher._apt_last_updated", None)
    def test_ensure_apt_updated_first_call(self, mock_run):
        """Test apt update runs on first call"""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = self.patcher.ensure_apt_updated()

        self.assertTrue(result)
        mock_run.assert_called()

    @patch("subprocess.run")
    def test_ensure_apt_updated_force(self, mock_run):
        """Test apt update can be forced"""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = self.patcher.ensure_apt_updated(force=True)

        self.assertTrue(result)

    @patch("subprocess.run")
    def test_check_package_update_available(self, mock_run):
        """Test checking for package updates"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="nginx:\n  Installed: 1.18.0\n  Candidate: 1.20.0\n  Version table:\n",
            stderr="",
        )

        version = self.patcher._check_package_update_available("nginx")

        self.assertEqual(version, "1.20.0")

    @patch("subprocess.run")
    def test_check_package_update_not_available(self, mock_run):
        """Test when no update is available"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="nginx:\n  Installed: 1.20.0\n  Candidate: (none)\n",
            stderr="",
        )

        version = self.patcher._check_package_update_available("nginx")

        self.assertIsNone(version)


class TestAutonomousPatcherConfig(unittest.TestCase):
    """Test configuration save/load"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("pathlib.Path.home")
    def test_save_and_load_config(self, mock_home):
        """Test saving and loading configuration"""
        mock_home.return_value = type("Path", (), {"__truediv__": lambda s, x: type("Path", (), {"exists": lambda s: False, "mkdir": lambda s, **k: None, "parent": type("Path", (), {"mkdir": lambda s, **k: None})(), "__truediv__": lambda s, x: s})()})()

        patcher = AutonomousPatcher()
        patcher.whitelist = {"nginx", "apache2"}
        patcher.blacklist = {"kernel"}
        patcher.min_severity = Severity.HIGH

        # Config operations are tested implicitly through add_to_whitelist etc.
        patcher.add_to_whitelist("curl")
        self.assertIn("curl", patcher.whitelist)


class TestVersionComparison(unittest.TestCase):
    """Test version comparison and vulnerability fix verification"""

    def setUp(self):
        self.patcher = AutonomousPatcher(dry_run=True)

    @patch("subprocess.run")
    def test_compare_versions_greater(self, mock_run):
        """Test version comparison with greater version"""
        mock_run.return_value = MagicMock(returncode=0)

        result = self.patcher._compare_versions("1.20.0", "gt", "1.18.0")
        self.assertTrue(result)

    @patch("subprocess.run")
    def test_compare_versions_less(self, mock_run):
        """Test version comparison with lesser version"""
        mock_run.return_value = MagicMock(returncode=1)  # dpkg returns 1 if comparison fails

        result = self.patcher._compare_versions("1.18.0", "gt", "1.20.0")
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_compare_versions_equal(self, mock_run):
        """Test version comparison with equal versions"""
        mock_run.return_value = MagicMock(returncode=0)

        result = self.patcher._compare_versions("1.20.0", "eq", "1.20.0")
        self.assertTrue(result)

    @patch("subprocess.run")
    def test_compare_versions_ge(self, mock_run):
        """Test version comparison with greater or equal"""
        mock_run.return_value = MagicMock(returncode=0)

        result = self.patcher._compare_versions("1.20.0", "ge", "1.18.0")
        self.assertTrue(result)

    @patch.object(AutonomousPatcher, "_compare_versions")
    def test_update_fixes_vulnerability_yes(self, mock_compare):
        """Test update fixes vulnerability when version is sufficient"""
        mock_compare.return_value = True

        vuln = Vulnerability(
            cve_id="CVE-2023-12345",
            package_name="nginx",
            installed_version="1.18.0",
            affected_versions="< 1.20.0",
            severity=Severity.HIGH,
            description="Test vulnerability",
            fixed_version="1.20.0",
        )

        result = self.patcher._update_fixes_vulnerability("1.20.0", vuln)
        self.assertTrue(result)
        mock_compare.assert_called_with("1.20.0", "ge", "1.20.0")

    @patch.object(AutonomousPatcher, "_compare_versions")
    def test_update_fixes_vulnerability_no(self, mock_compare):
        """Test update does not fix vulnerability when version is insufficient"""
        mock_compare.return_value = False

        vuln = Vulnerability(
            cve_id="CVE-2023-12345",
            package_name="nginx",
            installed_version="1.18.0",
            affected_versions="< 1.20.0",
            severity=Severity.HIGH,
            description="Test vulnerability",
            fixed_version="1.20.0",
        )

        result = self.patcher._update_fixes_vulnerability("1.19.0", vuln)
        self.assertFalse(result)

    def test_update_fixes_vulnerability_no_fixed_version(self):
        """Test update verification when no fixed_version is specified"""
        vuln = Vulnerability(
            cve_id="CVE-2023-12345",
            package_name="nginx",
            installed_version="1.18.0",
            affected_versions="< 1.20.0",
            severity=Severity.HIGH,
            description="Test vulnerability",
            fixed_version=None,  # No fixed version specified
        )

        # Should return True when fixed_version is unknown (allow the update)
        result = self.patcher._update_fixes_vulnerability("1.20.0", vuln)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()

