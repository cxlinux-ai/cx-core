#!/usr/bin/env python3
"""
Unit tests for ConfigManager.
Tests all functionality with mocked system calls.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from cortex.config_manager import ConfigManager


class TestConfigManager(unittest.TestCase):
    """Test cases for ConfigManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = ConfigManager()

        # Override cortex_dir to use temp directory
        self.config_manager.cortex_dir = Path(self.temp_dir) / ".cortex"
        self.config_manager.cortex_dir.mkdir(exist_ok=True)
        self.config_manager.preferences_file = self.config_manager.cortex_dir / "preferences.yaml"

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("subprocess.run")
    def test_detect_apt_packages_success(self, mock_run):
        """Test successful detection of APT packages."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "package1\t1.0.0\npackage2\t2.0.0\n"
        mock_run.return_value = mock_result

        packages = self.config_manager.detect_apt_packages()

        self.assertEqual(len(packages), 2)
        self.assertEqual(packages[0]["name"], "package1")
        self.assertEqual(packages[0]["version"], "1.0.0")
        self.assertEqual(packages[0]["source"], "apt")
        self.assertEqual(packages[1]["name"], "package2")
        self.assertEqual(packages[1]["version"], "2.0.0")

    @patch("subprocess.run")
    def test_detect_apt_packages_failure(self, mock_run):
        """Test APT package detection with failure."""
        mock_run.side_effect = FileNotFoundError()

        packages = self.config_manager.detect_apt_packages()

        self.assertEqual(len(packages), 0)

    @patch("subprocess.run")
    def test_detect_pip_packages_success(self, mock_run):
        """Test successful detection of PIP packages."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            [{"name": "numpy", "version": "1.24.0"}, {"name": "requests", "version": "2.28.0"}]
        )
        mock_run.return_value = mock_result

        packages = self.config_manager.detect_pip_packages()

        self.assertEqual(len(packages), 2)
        self.assertEqual(packages[0]["name"], "numpy")
        self.assertEqual(packages[0]["version"], "1.24.0")
        self.assertEqual(packages[0]["source"], "pip")

    @patch("subprocess.run")
    def test_detect_pip_packages_failure(self, mock_run):
        """Test PIP package detection with failure."""
        mock_run.side_effect = FileNotFoundError()

        packages = self.config_manager.detect_pip_packages()

        self.assertEqual(len(packages), 0)

    @patch("subprocess.run")
    def test_detect_npm_packages_success(self, mock_run):
        """Test successful detection of NPM packages."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {"dependencies": {"typescript": {"version": "5.0.0"}, "eslint": {"version": "8.0.0"}}}
        )
        mock_run.return_value = mock_result

        packages = self.config_manager.detect_npm_packages()

        self.assertEqual(len(packages), 2)
        names = [p["name"] for p in packages]
        self.assertIn("typescript", names)
        self.assertIn("eslint", names)

    @patch("subprocess.run")
    def test_detect_npm_packages_failure(self, mock_run):
        """Test NPM package detection with failure."""
        mock_run.side_effect = FileNotFoundError()

        packages = self.config_manager.detect_npm_packages()

        self.assertEqual(len(packages), 0)

    @patch.object(ConfigManager, "detect_apt_packages")
    @patch.object(ConfigManager, "detect_pip_packages")
    @patch.object(ConfigManager, "detect_npm_packages")
    @patch.object(ConfigManager, "detect_services")
    def test_detect_all_packages(self, mock_services, mock_npm, mock_pip, mock_apt):
        """Test detection of all packages from all sources."""
        mock_apt.return_value = [{"name": "curl", "version": "7.0.0", "source": "apt"}]
        mock_pip.return_value = [{"name": "numpy", "version": "1.24.0", "source": "pip"}]
        mock_npm.return_value = [{"name": "typescript", "version": "5.0.0", "source": "npm"}]
        mock_services.return_value = []

        packages = self.config_manager.detect_installed_packages()

        self.assertEqual(len(packages), 3)
        sources = [p["source"] for p in packages]
        self.assertIn("apt", sources)
        self.assertIn("pip", sources)
        self.assertIn("npm", sources)

    @patch.object(ConfigManager, "detect_apt_packages")
    @patch.object(ConfigManager, "detect_pip_packages")
    def test_detect_selective_packages(self, mock_pip, mock_apt):
        """Test selective package detection."""
        mock_apt.return_value = [{"name": "curl", "version": "7.0.0", "source": "apt"}]
        mock_pip.return_value = [{"name": "numpy", "version": "1.24.0", "source": "pip"}]

        # Only detect apt packages
        packages = self.config_manager.detect_installed_packages(sources=["apt"])

        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0]["source"], "apt")
        mock_apt.assert_called_once()
        mock_pip.assert_not_called()

    @patch.object(ConfigManager, "detect_installed_packages")
    @patch.object(ConfigManager, "_detect_os_version")
    @patch.object(ConfigManager, "_load_preferences")
    def test_export_configuration_minimal(self, mock_prefs, mock_os, mock_packages):
        """Test export with minimal settings."""
        mock_packages.return_value = [{"name": "test-pkg", "version": "1.0.0", "source": "apt"}]
        mock_os.return_value = "ubuntu-24.04"
        mock_prefs.return_value = {"confirmations": "minimal"}

        output_path = os.path.join(self.temp_dir, "config.yaml")

        result = self.config_manager.export_configuration(
            output_path=output_path, include_hardware=False, include_preferences=True
        )

        self.assertIn("exported successfully", result)
        self.assertTrue(os.path.exists(output_path))

        # Verify contents
        with open(output_path) as f:
            config = yaml.safe_load(f)

        self.assertEqual(config["cortex_version"], "0.2.0")
        self.assertEqual(config["os"], "ubuntu-24.04")
        self.assertIn("exported_at", config)
        self.assertEqual(len(config["packages"]), 1)
        self.assertEqual(config["packages"][0]["name"], "test-pkg")
        self.assertIn("preferences", config)
        self.assertEqual(config["preferences"]["confirmations"], "minimal")

    @patch.object(ConfigManager, "detect_installed_packages")
    @patch.object(ConfigManager, "_detect_os_version")
    @patch("cortex.hwprofiler.HardwareProfiler")
    def test_export_configuration_with_hardware(
        self, mock_hwprofiler_class, mock_os, mock_packages
    ):
        """Test export with hardware profile."""
        mock_packages.return_value = []
        mock_os.return_value = "ubuntu-24.04"

        # Mock HardwareProfiler instance
        mock_profiler = MagicMock()
        mock_profiler.profile.return_value = {
            "cpu": {"model": "Intel i7", "cores": 8},
            "ram": 16384,
        }
        mock_hwprofiler_class.return_value = mock_profiler

        output_path = os.path.join(self.temp_dir, "config.yaml")

        self.config_manager.export_configuration(output_path=output_path, include_hardware=True)

        with open(output_path) as f:
            config = yaml.safe_load(f)

        self.assertIn("hardware", config)
        self.assertEqual(config["hardware"]["cpu"]["model"], "Intel i7")
        self.assertEqual(config["hardware"]["ram"], 16384)

    @patch.object(ConfigManager, "detect_installed_packages")
    @patch.object(ConfigManager, "_detect_os_version")
    def test_export_configuration_packages_only(self, mock_os, mock_packages):
        """Test export with packages only."""
        mock_packages.return_value = [{"name": "test-pkg", "version": "1.0.0", "source": "apt"}]
        mock_os.return_value = "ubuntu-24.04"

        output_path = os.path.join(self.temp_dir, "config.yaml")

        self.config_manager.export_configuration(
            output_path=output_path, include_hardware=False, include_preferences=False
        )

        with open(output_path) as f:
            config = yaml.safe_load(f)

        self.assertIn("packages", config)
        self.assertNotIn("hardware", config)

    @patch.object(ConfigManager, "_detect_os_version")
    def test_validate_compatibility_success(self, mock_os):
        """Test validation of compatible configuration."""
        mock_os.return_value = "ubuntu-24.04"

        config = {"cortex_version": "0.2.0", "os": "ubuntu-24.04", "packages": []}

        is_compatible, reason = self.config_manager.validate_compatibility(config)

        self.assertTrue(is_compatible)
        self.assertIsNone(reason)

    def test_validate_compatibility_missing_fields(self):
        """Test validation with missing required fields."""
        config = {"os": "ubuntu-24.04"}

        is_compatible, reason = self.config_manager.validate_compatibility(config)

        self.assertFalse(is_compatible)
        self.assertIn("cortex_version", reason)

    def test_validate_compatibility_version_mismatch(self):
        """Test validation with incompatible version."""
        config = {
            "cortex_version": "1.0.0",  # Major version different
            "os": "ubuntu-24.04",
            "packages": [],
        }

        is_compatible, reason = self.config_manager.validate_compatibility(config)

        self.assertFalse(is_compatible)
        self.assertIn("major version", reason)

    @patch.object(ConfigManager, "_detect_os_version")
    def test_validate_compatibility_os_warning(self, mock_os):
        """Test validation with OS mismatch (warning)."""
        mock_os.return_value = "ubuntu-22.04"

        config = {"cortex_version": "0.2.0", "os": "ubuntu-24.04", "packages": []}

        is_compatible, reason = self.config_manager.validate_compatibility(config)

        self.assertTrue(is_compatible)
        self.assertIsNotNone(reason)
        self.assertIn("Warning", reason)
        self.assertIn("OS mismatch", reason)

    @patch.object(ConfigManager, "detect_installed_packages")
    def test_diff_configuration_no_changes(self, mock_packages):
        """Test diff with identical configurations."""
        current_packages = [{"name": "curl", "version": "7.0.0", "source": "apt"}]
        mock_packages.return_value = current_packages

        config = {"packages": current_packages, "preferences": {}}

        diff = self.config_manager.diff_configuration(config)

        self.assertEqual(len(diff["packages_to_install"]), 0)
        self.assertEqual(len(diff["packages_to_upgrade"]), 0)
        self.assertEqual(len(diff["packages_already_installed"]), 1)

    @patch.object(ConfigManager, "detect_installed_packages")
    def test_diff_configuration_new_packages(self, mock_packages):
        """Test diff with new packages to install."""
        mock_packages.return_value = [{"name": "curl", "version": "7.0.0", "source": "apt"}]

        config = {
            "packages": [
                {"name": "curl", "version": "7.0.0", "source": "apt"},
                {"name": "wget", "version": "1.0.0", "source": "apt"},
            ],
            "preferences": {},
        }

        diff = self.config_manager.diff_configuration(config)

        self.assertEqual(len(diff["packages_to_install"]), 1)
        self.assertEqual(diff["packages_to_install"][0]["name"], "wget")

    @patch.object(ConfigManager, "detect_installed_packages")
    def test_diff_configuration_upgrades(self, mock_packages):
        """Test diff with packages to upgrade."""
        mock_packages.return_value = [{"name": "curl", "version": "7.0.0", "source": "apt"}]

        config = {
            "packages": [{"name": "curl", "version": "8.0.0", "source": "apt"}],
            "preferences": {},
        }

        diff = self.config_manager.diff_configuration(config)

        self.assertEqual(len(diff["packages_to_upgrade"]), 1)
        self.assertEqual(diff["packages_to_upgrade"][0]["name"], "curl")
        self.assertEqual(diff["packages_to_upgrade"][0]["current_version"], "7.0.0")

    @patch.object(ConfigManager, "_load_preferences")
    @patch.object(ConfigManager, "detect_installed_packages")
    def test_diff_configuration_preferences(self, mock_packages, mock_prefs):
        """Test diff with changed preferences."""
        mock_packages.return_value = []
        mock_prefs.return_value = {"confirmations": "normal"}

        config = {"packages": [], "preferences": {"confirmations": "minimal", "verbosity": "high"}}

        diff = self.config_manager.diff_configuration(config)

        self.assertEqual(len(diff["preferences_changed"]), 2)
        self.assertIn("confirmations", diff["preferences_changed"])
        self.assertIn("verbosity", diff["preferences_changed"])

    @patch.object(ConfigManager, "validate_compatibility")
    @patch.object(ConfigManager, "diff_configuration")
    def test_import_configuration_dry_run(self, mock_diff, mock_validate):
        """Test import in dry-run mode."""
        mock_validate.return_value = (True, None)
        mock_diff.return_value = {
            "packages_to_install": [{"name": "wget", "version": "1.0.0", "source": "apt"}],
            "packages_to_upgrade": [],
            "packages_to_downgrade": [],
            "packages_already_installed": [],
            "preferences_changed": {},
            "warnings": [],
        }

        # Create test config file
        config_path = os.path.join(self.temp_dir, "test_config.yaml")
        with open(config_path, "w") as f:
            yaml.safe_dump({"cortex_version": "0.2.0", "os": "ubuntu-24.04", "packages": []}, f)

        result = self.config_manager.import_configuration(config_path=config_path, dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertIn("diff", result)
        self.assertIn("message", result)

    @patch.object(ConfigManager, "validate_compatibility")
    @patch.object(ConfigManager, "diff_configuration")
    @patch.object(ConfigManager, "_install_package")
    @patch.object(ConfigManager, "_save_preferences")
    def test_import_configuration_success(
        self, mock_save_prefs, mock_install, mock_diff, mock_validate
    ):
        """Test successful import."""
        mock_validate.return_value = (True, None)
        mock_diff.return_value = {
            "packages_to_install": [{"name": "wget", "version": "1.0.0", "source": "apt"}],
            "packages_to_upgrade": [],
            "packages_to_downgrade": [],
            "packages_already_installed": [],
            "preferences_changed": {},
            "warnings": [],
        }
        mock_install.return_value = True

        # Create test config file
        config_path = os.path.join(self.temp_dir, "test_config.yaml")
        with open(config_path, "w") as f:
            yaml.safe_dump(
                {
                    "cortex_version": "0.2.0",
                    "os": "ubuntu-24.04",
                    "packages": [{"name": "wget", "version": "1.0.0", "source": "apt"}],
                    "preferences": {"confirmations": "minimal"},
                },
                f,
            )

        result = self.config_manager.import_configuration(config_path=config_path, dry_run=False)

        self.assertEqual(len(result["installed"]), 1)
        self.assertIn("wget", result["installed"])
        self.assertTrue(result["preferences_updated"])
        mock_install.assert_called_once()
        mock_save_prefs.assert_called_once()

    @patch.object(ConfigManager, "validate_compatibility")
    def test_import_configuration_incompatible(self, mock_validate):
        """Test import with incompatible configuration."""
        mock_validate.return_value = (False, "Incompatible version")

        # Create test config file
        config_path = os.path.join(self.temp_dir, "test_config.yaml")
        with open(config_path, "w") as f:
            yaml.safe_dump({"cortex_version": "999.0.0", "os": "ubuntu-24.04", "packages": []}, f)

        with self.assertRaises(RuntimeError) as context:
            self.config_manager.import_configuration(config_path=config_path, dry_run=False)

        self.assertIn("Incompatible", str(context.exception))

    @patch.object(ConfigManager, "validate_compatibility")
    @patch.object(ConfigManager, "diff_configuration")
    @patch.object(ConfigManager, "_install_package")
    def test_import_configuration_selective_packages(self, mock_install, mock_diff, mock_validate):
        """Test selective import (packages only)."""
        mock_validate.return_value = (True, None)
        mock_diff.return_value = {
            "packages_to_install": [{"name": "wget", "version": "1.0.0", "source": "apt"}],
            "packages_to_upgrade": [],
            "packages_to_downgrade": [],
            "packages_already_installed": [],
            "preferences_changed": {},
            "warnings": [],
        }
        mock_install.return_value = True

        # Create test config file
        config_path = os.path.join(self.temp_dir, "test_config.yaml")
        with open(config_path, "w") as f:
            yaml.safe_dump(
                {
                    "cortex_version": "0.2.0",
                    "os": "ubuntu-24.04",
                    "packages": [{"name": "wget", "version": "1.0.0", "source": "apt"}],
                    "preferences": {"confirmations": "minimal"},
                },
                f,
            )

        result = self.config_manager.import_configuration(
            config_path=config_path, dry_run=False, selective=["packages"]
        )

        self.assertEqual(len(result["installed"]), 1)
        self.assertFalse(result["preferences_updated"])

    @patch.object(ConfigManager, "validate_compatibility")
    @patch.object(ConfigManager, "diff_configuration")
    @patch.object(ConfigManager, "_save_preferences")
    def test_import_configuration_selective_preferences(
        self, mock_save_prefs, mock_diff, mock_validate
    ):
        """Test selective import (preferences only)."""
        mock_validate.return_value = (True, None)
        mock_diff.return_value = {
            "packages_to_install": [],
            "packages_to_upgrade": [],
            "packages_to_downgrade": [],
            "packages_already_installed": [],
            "preferences_changed": {},
            "warnings": [],
        }

        # Create test config file
        config_path = os.path.join(self.temp_dir, "test_config.yaml")
        with open(config_path, "w") as f:
            yaml.safe_dump(
                {
                    "cortex_version": "0.2.0",
                    "os": "ubuntu-24.04",
                    "packages": [],
                    "preferences": {"confirmations": "minimal"},
                },
                f,
            )

        result = self.config_manager.import_configuration(
            config_path=config_path, dry_run=False, selective=["preferences"]
        )

        self.assertEqual(len(result["installed"]), 0)
        self.assertTrue(result["preferences_updated"])
        mock_save_prefs.assert_called_once()

    def test_error_handling_invalid_yaml(self):
        """Test error handling with malformed YAML file."""
        config_path = os.path.join(self.temp_dir, "invalid.yaml")
        with open(config_path, "w") as f:
            f.write("{ invalid yaml content [")

        with self.assertRaises(RuntimeError) as context:
            self.config_manager.import_configuration(config_path)

        self.assertIn("Failed to load", str(context.exception))

    def test_error_handling_missing_file(self):
        """Test error handling with missing configuration file."""
        config_path = os.path.join(self.temp_dir, "nonexistent.yaml")

        with self.assertRaises(RuntimeError) as context:
            self.config_manager.import_configuration(config_path)

        self.assertIn("Failed to load", str(context.exception))

    @patch.object(ConfigManager, "validate_compatibility")
    @patch.object(ConfigManager, "diff_configuration")
    @patch.object(ConfigManager, "_install_package")
    def test_error_handling_package_install_fails(self, mock_install, mock_diff, mock_validate):
        """Test handling of package installation failures."""
        mock_validate.return_value = (True, None)
        mock_diff.return_value = {
            "packages_to_install": [
                {"name": "pkg1", "version": "1.0.0", "source": "apt"},
                {"name": "pkg2", "version": "2.0.0", "source": "apt"},
            ],
            "packages_to_upgrade": [],
            "packages_to_downgrade": [],
            "packages_already_installed": [],
            "preferences_changed": {},
            "warnings": [],
        }
        # First package succeeds, second fails
        mock_install.side_effect = [True, False]

        # Create test config file
        config_path = os.path.join(self.temp_dir, "test_config.yaml")
        with open(config_path, "w") as f:
            yaml.safe_dump(
                {
                    "cortex_version": "0.2.0",
                    "os": "ubuntu-24.04",
                    "packages": [
                        {"name": "pkg1", "version": "1.0.0", "source": "apt"},
                        {"name": "pkg2", "version": "2.0.0", "source": "apt"},
                    ],
                },
                f,
            )

        result = self.config_manager.import_configuration(config_path=config_path, dry_run=False)

        self.assertEqual(len(result["installed"]), 1)
        self.assertEqual(len(result["failed"]), 1)

    def test_compare_versions(self):
        """Test version comparison."""
        # Equal versions
        self.assertEqual(self.config_manager._compare_versions("1.0.0", "1.0.0"), 0)

        # First version less than second
        self.assertEqual(self.config_manager._compare_versions("1.0.0", "2.0.0"), -1)
        self.assertEqual(self.config_manager._compare_versions("1.0.0", "1.1.0"), -1)
        self.assertEqual(self.config_manager._compare_versions("1.0.0", "1.0.1"), -1)

        # First version greater than second
        self.assertEqual(self.config_manager._compare_versions("2.0.0", "1.0.0"), 1)
        self.assertEqual(self.config_manager._compare_versions("1.1.0", "1.0.0"), 1)
        self.assertEqual(self.config_manager._compare_versions("1.0.1", "1.0.0"), 1)

    def test_preferences_save_and_load(self):
        """Test saving and loading preferences."""
        preferences = {"confirmations": "minimal", "verbosity": "normal"}

        self.config_manager._save_preferences(preferences)
        loaded = self.config_manager._load_preferences()

        self.assertEqual(loaded, preferences)

    @patch("subprocess.run")
    def test_install_package_apt_with_sandbox(self, mock_run):
        """Test package installation via APT with SandboxExecutor."""
        mock_executor = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_executor.execute.return_value = mock_result

        self.config_manager.sandbox_executor = mock_executor

        pkg = {"name": "curl", "version": "7.0.0", "source": "apt"}
        result = self.config_manager._install_package(pkg)

        self.assertTrue(result)
        mock_executor.execute.assert_called_once()
        call_args = mock_executor.execute.call_args[0][0]
        self.assertIn("curl", call_args)
        self.assertIn("apt-get install", call_args)

    @patch("subprocess.run")
    def test_install_package_pip_direct(self, mock_run):
        """Test package installation via PIP without SandboxExecutor."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        pkg = {"name": "numpy", "version": "1.24.0", "source": "pip"}
        result = self.config_manager._install_package(pkg)

        self.assertTrue(result)
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn("pip3", call_args)
        self.assertIn("numpy==1.24.0", call_args)

    @patch("subprocess.run")
    def test_install_package_npm_direct(self, mock_run):
        """Test package installation via NPM without SandboxExecutor."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        pkg = {"name": "typescript", "version": "5.0.0", "source": "npm"}
        result = self.config_manager._install_package(pkg)

        self.assertTrue(result)
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn("npm", call_args)
        self.assertIn("typescript@5.0.0", call_args)


if __name__ == "__main__":
    unittest.main()
