#!/usr/bin/env python3
"""
Unit tests for the Unified Package Manager.

Tests cover all major functionality including:
- Package source detection (deb, snap, flatpak)
- Installed package listing
- Package comparison
- Permission management
- Snap redirect detection
- Storage analysis
"""

import os
import sys
import unittest
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.unified_package_manager import (
    PackageFormat,
    PackageInfo,
    StorageAnalysis,
    UnifiedPackageManager,
)


class TestUnifiedPackageManager(unittest.TestCase):
    """Test cases for UnifiedPackageManager class."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock command availability checks
        with patch.object(UnifiedPackageManager, "_check_command_available") as mock_check:
            mock_check.return_value = True
            self.upm = UnifiedPackageManager()

    # =========================================================================
    # Package Source Detection Tests
    # =========================================================================

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_detect_deb_package_installed(self, mock_run):
        """Test detection of installed deb package."""
        mock_run.return_value = (True, "install ok installed|1.0.0|1024", "")

        result = self.upm._check_deb_package("test-package")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "test-package")
        self.assertEqual(result.format, PackageFormat.DEB)
        self.assertEqual(result.version, "1.0.0")
        self.assertTrue(result.installed)

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_detect_deb_package_available(self, mock_run):
        """Test detection of available but not installed deb package."""
        # First call returns not installed, second returns apt-cache info
        mock_run.side_effect = [
            (False, "", ""),
            (True, "Package: test-package\nVersion: 2.0.0\nDescription: A test package", ""),
        ]

        result = self.upm._check_deb_package("test-package")

        self.assertIsNotNone(result)
        self.assertEqual(result.version, "2.0.0")
        self.assertFalse(result.installed)

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_detect_deb_transitional_package(self, mock_run):
        """Test detection of transitional/dummy packages returns None."""
        mock_run.side_effect = [
            (False, "", ""),
            (True, "Package: firefox\nDescription: dummy package for snap", ""),
        ]

        result = self.upm._check_deb_package("firefox")

        self.assertIsNone(result)

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_detect_snap_package_installed(self, mock_run):
        """Test detection of installed snap package."""
        mock_run.return_value = (
            True,
            "Name      Version  Rev    Tracking  Publisher   Notes\nfirefox   120.0    1234   latest    mozilla     -",
            "",
        )

        result = self.upm._check_snap_package("firefox")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "firefox")
        self.assertEqual(result.format, PackageFormat.SNAP)
        self.assertTrue(result.installed)

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_detect_snap_package_available(self, mock_run):
        """Test detection of available snap package."""
        mock_run.side_effect = [
            (False, "", ""),
            (True, "name:      test-snap\nsummary:   A test snap\nstable:    1.0.0 2024-01-01", ""),
        ]

        result = self.upm._check_snap_package("test-snap")

        self.assertIsNotNone(result)
        self.assertEqual(result.format, PackageFormat.SNAP)
        self.assertFalse(result.installed)

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_detect_flatpak_package_installed(self, mock_run):
        """Test detection of installed flatpak package."""
        mock_run.return_value = (
            True,
            "org.mozilla.firefox\t120.0",
            "",
        )

        result = self.upm._check_flatpak_package("firefox")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "org.mozilla.firefox")
        self.assertEqual(result.format, PackageFormat.FLATPAK)
        self.assertTrue(result.installed)

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_detect_flatpak_package_available(self, mock_run):
        """Test detection of available flatpak package."""
        mock_run.side_effect = [
            (True, "", ""),  # Not in installed list
            (True, "org.test.App\t1.0.0\tA test application", ""),
        ]

        result = self.upm._check_flatpak_package("test")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "org.test.App")

    @patch.object(UnifiedPackageManager, "_check_deb_package")
    @patch.object(UnifiedPackageManager, "_check_snap_package")
    @patch.object(UnifiedPackageManager, "_check_flatpak_package")
    def test_detect_package_sources(self, mock_flatpak, mock_snap, mock_deb):
        """Test combined package source detection."""
        mock_deb.return_value = PackageInfo("test", PackageFormat.DEB, "1.0")
        mock_snap.return_value = PackageInfo("test", PackageFormat.SNAP, "2.0")
        mock_flatpak.return_value = None

        result = self.upm.detect_package_sources("test")

        self.assertIn("deb", result)
        self.assertIn("snap", result)
        self.assertIn("flatpak", result)
        self.assertIsNotNone(result["deb"])
        self.assertIsNotNone(result["snap"])
        self.assertIsNone(result["flatpak"])

    # =========================================================================
    # Package Listing Tests
    # =========================================================================

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_list_deb_packages(self, mock_run):
        """Test listing installed deb packages."""
        mock_run.return_value = (
            True,
            "package1|1.0.0|1024\npackage2|2.0.0|2048\n",
            "",
        )

        result = self.upm._list_deb_packages()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "package1")
        self.assertEqual(result[1].name, "package2")
        self.assertEqual(result[0].format, PackageFormat.DEB)

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_list_snap_packages(self, mock_run):
        """Test listing installed snap packages."""
        mock_run.return_value = (
            True,
            "Name           Version  Rev    Tracking  Publisher   Notes\ncore           16-2.58  14447  latest/stable  canonical✓  -\nfirefox        120.0    1234   latest    mozilla     -",
            "",
        )

        result = self.upm._list_snap_packages()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "core")
        self.assertEqual(result[1].name, "firefox")

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_list_flatpak_packages(self, mock_run):
        """Test listing installed flatpak packages."""
        mock_run.return_value = (
            True,
            "org.mozilla.firefox\t120.0\t500 MB",
            "",
        )

        result = self.upm._list_flatpak_packages()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "org.mozilla.firefox")
        self.assertEqual(result[0].format, PackageFormat.FLATPAK)

    @patch.object(UnifiedPackageManager, "_list_deb_packages")
    @patch.object(UnifiedPackageManager, "_list_snap_packages")
    @patch.object(UnifiedPackageManager, "_list_flatpak_packages")
    def test_list_installed_packages_all(self, mock_flatpak, mock_snap, mock_deb):
        """Test listing all installed packages."""
        mock_deb.return_value = [PackageInfo("pkg1", PackageFormat.DEB)]
        mock_snap.return_value = [PackageInfo("pkg2", PackageFormat.SNAP)]
        mock_flatpak.return_value = [PackageInfo("pkg3", PackageFormat.FLATPAK)]

        result = self.upm.list_installed_packages()

        self.assertEqual(len(result["deb"]), 1)
        self.assertEqual(len(result["snap"]), 1)
        self.assertEqual(len(result["flatpak"]), 1)

    @patch.object(UnifiedPackageManager, "_list_deb_packages")
    @patch.object(UnifiedPackageManager, "_list_snap_packages")
    @patch.object(UnifiedPackageManager, "_list_flatpak_packages")
    def test_list_installed_packages_filtered(self, mock_flatpak, mock_snap, mock_deb):
        """Test listing packages with format filter."""
        mock_snap.return_value = [PackageInfo("snap-pkg", PackageFormat.SNAP)]

        result = self.upm.list_installed_packages(format_filter=PackageFormat.SNAP)

        self.assertEqual(len(result["snap"]), 1)
        self.assertEqual(len(result["deb"]), 0)
        self.assertEqual(len(result["flatpak"]), 0)

    # =========================================================================
    # Package Comparison Tests
    # =========================================================================

    @patch.object(UnifiedPackageManager, "detect_package_sources")
    def test_compare_package_options(self, mock_detect):
        """Test package comparison across formats."""
        mock_detect.return_value = {
            "deb": PackageInfo("test", PackageFormat.DEB, "1.0", installed=True),
            "snap": PackageInfo("test", PackageFormat.SNAP, "2.0"),
            "flatpak": None,
        }

        result = self.upm.compare_package_options("test")

        self.assertEqual(result["package_name"], "test")
        self.assertIn("deb", result["available_formats"])
        self.assertIn("snap", result["available_formats"])
        self.assertNotIn("flatpak", result["available_formats"])
        self.assertEqual(result["installed_as"], "deb")

    # =========================================================================
    # Permission Management Tests
    # =========================================================================

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_list_snap_permissions(self, mock_run):
        """Test listing snap permissions."""
        mock_run.return_value = (
            True,
            "Interface        Plug                        Slot        Notes\naudio-playback   firefox:audio-playback      :audio-playback  -\nnetwork          firefox:network             -           -",
            "",
        )

        result = self.upm.list_snap_permissions("firefox")

        self.assertIn("connected", result)
        self.assertIn("available", result)
        self.assertGreaterEqual(len(result["connected"]), 1)

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_list_flatpak_permissions(self, mock_run):
        """Test listing flatpak permissions."""
        mock_run.return_value = (
            True,
            "[Context]\nshared=network;ipc;\n\n[filesystems]\nhome\nxdg-data/themes\n\n[Session Bus Policy]\norg.freedesktop.Notifications=talk\n",
            "",
        )

        result = self.upm.list_flatpak_permissions("org.test.App")

        self.assertIn("Context", result)
        self.assertIsInstance(result["Context"], dict)
        self.assertEqual(result["Context"]["shared"], "network;ipc;")

        self.assertIn("filesystems", result)
        self.assertIsInstance(result["filesystems"], list)
        self.assertEqual(len(result["filesystems"]), 2)
        self.assertIn("home", result["filesystems"])

        self.assertIn("Session Bus Policy", result)
        self.assertIsInstance(result["Session Bus Policy"], dict)
        self.assertEqual(result["Session Bus Policy"]["org.freedesktop.Notifications"], "talk")

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_modify_snap_permission_connect(self, mock_run):
        """Test connecting a snap interface."""
        mock_run.return_value = (True, "", "")

        success, message = self.upm.modify_snap_permission("firefox", "camera", "connect")

        self.assertTrue(success)
        self.assertIn("connect", message.lower())

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_modify_snap_permission_disconnect(self, mock_run):
        """Test disconnecting a snap interface."""
        mock_run.return_value = (True, "", "")

        success, message = self.upm.modify_snap_permission("firefox", "camera", "disconnect")

        self.assertTrue(success)

    def test_modify_snap_permission_invalid_action(self):
        """Test invalid action for snap permission modification."""
        success, message = self.upm.modify_snap_permission("firefox", "camera", "invalid")

        self.assertFalse(success)
        self.assertIn("Invalid action", message)

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_modify_flatpak_permission(self, mock_run):
        """Test modifying flatpak permission."""
        mock_run.return_value = (True, "", "")

        success, message = self.upm.modify_flatpak_permission("org.test.App", "filesystem", "home")

        self.assertTrue(success)

    # =========================================================================
    # Snap Redirect Tests
    # =========================================================================

    @patch.object(UnifiedPackageManager, "_run_command")
    @patch("os.path.exists")
    def test_check_snap_redirects(self, mock_exists, mock_run):
        """Test detection of snap redirects."""
        mock_run.return_value = (
            True,
            "Package: firefox\nDescription: dummy transitional package",
            "",
        )
        mock_exists.return_value = True

        result = self.upm.check_snap_redirects()

        self.assertGreaterEqual(len(result), 1)
        # Should find Firefox as transitional
        firefox_redirect = next((r for r in result if r["package"] == "firefox"), None)
        self.assertIsNotNone(firefox_redirect)

    @patch("pathlib.Path.exists")
    @patch("os.access")
    @patch("shutil.move")
    def test_disable_snap_redirects_success(self, mock_move, mock_access, mock_exists):
        """Test successful disabling of snap redirects."""
        mock_exists.return_value = True
        mock_access.return_value = True
        mock_move.return_value = None

        success, message = self.upm.disable_snap_redirects()

        self.assertTrue(success)
        self.assertIn("disabled", message.lower())

    @patch("pathlib.Path.exists")
    def test_disable_snap_redirects_not_found(self, mock_exists):
        """Test disabling when config doesn't exist."""
        mock_exists.return_value = False

        success, message = self.upm.disable_snap_redirects()

        self.assertTrue(success)
        self.assertIn("not found", message.lower())

    @patch("pathlib.Path.exists")
    @patch("os.access")
    def test_disable_snap_redirects_permission_denied(self, mock_access, mock_exists):
        """Test disabling without root permissions."""
        mock_exists.return_value = True
        mock_access.return_value = False

        success, message = self.upm.disable_snap_redirects()

        self.assertFalse(success)
        self.assertIn("Permission denied", message)

    @patch("pathlib.Path.exists")
    @patch("os.access")
    def test_disable_snap_redirects_backup_already_exists(self, mock_access, mock_exists):
        """Test disabling when backup already exists - should preserve existing backup."""
        # config_path.exists() = True, then backup_path.exists() = True
        mock_exists.side_effect = [True, True]
        mock_access.return_value = True

        success, message = self.upm.disable_snap_redirects()

        self.assertTrue(success)
        self.assertIn("already disabled", message.lower())
        self.assertIn("preserved", message.lower())

    @patch("pathlib.Path.exists")
    @patch("shutil.move")
    def test_restore_snap_redirects_success(self, mock_move, mock_exists):
        """Test successful restore of snap redirects from backup."""
        # backup exists, config doesn't exist
        mock_exists.side_effect = lambda: True  # backup exists

        with patch("pathlib.Path.exists") as mock_path_exists:
            # First call for backup_path.exists() = True, second for config_path.exists() = False
            mock_path_exists.side_effect = [True, False]
            mock_move.return_value = None

            success, message = self.upm.restore_snap_redirects()

            self.assertTrue(success)
            self.assertIn("restored", message.lower())
            mock_move.assert_called_once()

    @patch("pathlib.Path.exists")
    def test_restore_snap_redirects_no_backup(self, mock_exists):
        """Test restore when no backup exists."""
        mock_exists.return_value = False

        success, message = self.upm.restore_snap_redirects()

        self.assertFalse(success)
        self.assertIn("No backup found", message)

    @patch("pathlib.Path.exists")
    def test_restore_snap_redirects_config_exists(self, mock_exists):
        """Test restore when config already exists."""
        # backup exists, config also exists
        mock_exists.side_effect = [True, True]

        success, message = self.upm.restore_snap_redirects()

        self.assertFalse(success)
        self.assertIn("already exists", message)

    @patch("pathlib.Path.exists")
    @patch("shutil.move")
    def test_restore_snap_redirects_move_failure(self, mock_move, mock_exists):
        """Test restore when shutil.move raises an exception."""
        # backup exists, config doesn't exist
        mock_exists.side_effect = [True, False]
        mock_move.side_effect = OSError("Permission denied")

        success, message = self.upm.restore_snap_redirects()

        self.assertFalse(success)
        self.assertIn("Failed to restore", message)
        self.assertIn("Permission denied", message)

    # =========================================================================
    # Storage Analysis Tests
    # =========================================================================

    @patch.object(UnifiedPackageManager, "_list_deb_packages")
    @patch.object(UnifiedPackageManager, "_list_flatpak_packages")
    @patch.object(UnifiedPackageManager, "_run_command")
    def test_analyze_storage(self, mock_run, mock_flatpak, mock_deb):
        """Test storage analysis."""
        mock_deb.return_value = [
            PackageInfo("pkg1", PackageFormat.DEB, "1.0", size=1024000),
            PackageInfo("pkg2", PackageFormat.DEB, "2.0", size=2048000),
        ]
        mock_flatpak.return_value = [
            PackageInfo("org.test.App", PackageFormat.FLATPAK, "1.0", size=500000000),
        ]
        mock_run.return_value = (True, "", "")

        # Mock Path.exists and glob for snap analysis
        with patch("pathlib.Path.exists", return_value=False):
            result = self.upm.analyze_storage()

        self.assertIsInstance(result, StorageAnalysis)
        self.assertEqual(result.deb_total, 3072000)
        self.assertEqual(result.flatpak_total, 500000000)

    def test_parse_size_string(self):
        """Test parsing of size strings."""
        self.assertEqual(self.upm._parse_size_string("1.5 GB"), int(1.5 * 1024**3))
        self.assertEqual(self.upm._parse_size_string("500 MB"), int(500 * 1024**2))
        self.assertEqual(self.upm._parse_size_string("1024 KB"), int(1024 * 1024))
        self.assertEqual(self.upm._parse_size_string(""), 0)

    def test_format_storage_analysis(self):
        """Test formatting of storage analysis."""
        analysis = StorageAnalysis(
            deb_total=1024**3,  # 1 GB
            snap_total=512 * 1024**2,  # 512 MB
            flatpak_total=256 * 1024**2,  # 256 MB
            snap_packages=[("firefox", 200 * 1024**2)],
            flatpak_packages=[("org.test.App", 256 * 1024**2)],
        )

        result = self.upm.format_storage_analysis(analysis)

        self.assertIn("Storage Analysis", result)
        self.assertIn("DEB/APT", result)
        self.assertIn("Snap", result)
        self.assertIn("Flatpak", result)
        self.assertIn("GB", result)  # Should show GB for large sizes

    # =========================================================================
    # Error Handling Tests
    # =========================================================================

    def test_command_not_available(self):
        """Test handling when commands are not available."""
        with patch.object(UnifiedPackageManager, "_check_command_available") as mock_check:
            mock_check.return_value = False
            upm = UnifiedPackageManager()

            self.assertFalse(upm._snap_available)
            self.assertFalse(upm._flatpak_available)

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_list_snap_permissions_unavailable(self, mock_run):
        """Test listing permissions when snap unavailable."""
        self.upm._snap_available = False

        with self.assertRaises(RuntimeError) as context:
            self.upm.list_snap_permissions("test")

        self.assertIn("not available", str(context.exception))

    @patch.object(UnifiedPackageManager, "_run_command")
    def test_list_flatpak_permissions_unavailable(self, mock_run):
        """Test listing permissions when flatpak unavailable."""
        self.upm._flatpak_available = False

        with self.assertRaises(RuntimeError) as context:
            self.upm.list_flatpak_permissions("org.test.App")

        self.assertIn("not available", str(context.exception))


class TestPackageInfo(unittest.TestCase):
    """Test cases for PackageInfo dataclass."""

    def test_package_info_creation(self):
        """Test creation of PackageInfo instance."""
        info = PackageInfo(
            name="test-package",
            format=PackageFormat.DEB,
            version="1.0.0",
            size=1024,
            installed=True,
            description="A test package",
        )

        self.assertEqual(info.name, "test-package")
        self.assertEqual(info.format, PackageFormat.DEB)
        self.assertEqual(info.version, "1.0.0")
        self.assertEqual(info.size, 1024)
        self.assertTrue(info.installed)

    def test_package_info_defaults(self):
        """Test default values for PackageInfo."""
        info = PackageInfo(name="test", format=PackageFormat.SNAP)

        self.assertEqual(info.version, "")
        self.assertEqual(info.size, 0)
        self.assertFalse(info.installed)
        self.assertEqual(info.permissions, [])


class TestStorageAnalysis(unittest.TestCase):
    """Test cases for StorageAnalysis dataclass."""

    def test_storage_analysis_creation(self):
        """Test creation of StorageAnalysis instance."""
        analysis = StorageAnalysis(
            deb_total=1024,
            snap_total=2048,
            flatpak_total=4096,
        )

        self.assertEqual(analysis.deb_total, 1024)
        self.assertEqual(analysis.snap_total, 2048)
        self.assertEqual(analysis.flatpak_total, 4096)

    def test_storage_analysis_defaults(self):
        """Test default values for StorageAnalysis."""
        analysis = StorageAnalysis()

        self.assertEqual(analysis.deb_total, 0)
        self.assertEqual(analysis.snap_total, 0)
        self.assertEqual(analysis.flatpak_total, 0)
        self.assertEqual(analysis.deb_packages, [])
        self.assertEqual(analysis.snap_packages, [])
        self.assertEqual(analysis.flatpak_packages, [])


if __name__ == "__main__":
    unittest.main()
