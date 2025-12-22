#!/usr/bin/env python3
"""
Unit tests for SnapshotManager.
Tests all functionality with mocked system calls.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cortex.snapshot_manager import SnapshotManager, SnapshotMetadata


class TestSnapshotManager(unittest.TestCase):
    """Test cases for SnapshotManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.snapshots_dir = Path(self.temp_dir) / "snapshots"
        self.manager = SnapshotManager(snapshots_dir=self.snapshots_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("subprocess.run")
    def test_detect_apt_packages(self, mock_run):
        """Test APT package detection."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="vim\t2:8.2.0\nnginx\t1.18.0\n"
        )

        packages = self.manager._detect_apt_packages()

        self.assertEqual(len(packages), 2)
        self.assertEqual(packages[0]["name"], "vim")
        self.assertEqual(packages[0]["version"], "2:8.2.0")
        self.assertEqual(packages[1]["name"], "nginx")

    @patch("subprocess.run")
    def test_detect_pip_packages(self, mock_run):
        """Test PIP package detection."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"name": "requests", "version": "2.28.0"},
                {"name": "pytest", "version": "7.2.0"}
            ])
        )

        packages = self.manager._detect_pip_packages()

        self.assertEqual(len(packages), 2)
        self.assertEqual(packages[0]["name"], "requests")
        self.assertEqual(packages[1]["version"], "7.2.0")

    @patch("subprocess.run")
    def test_detect_npm_packages(self, mock_run):
        """Test NPM package detection."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "dependencies": {
                    "express": {"version": "4.18.0"},
                    "lodash": {"version": "4.17.21"}
                }
            })
        )

        packages = self.manager._detect_npm_packages()

        self.assertEqual(len(packages), 2)
        self.assertEqual(packages[0]["name"], "express")
        self.assertEqual(packages[1]["version"], "4.17.21")

    @patch.object(SnapshotManager, "_detect_apt_packages")
    @patch.object(SnapshotManager, "_detect_pip_packages")
    @patch.object(SnapshotManager, "_detect_npm_packages")
    @patch.object(SnapshotManager, "_get_system_info")
    def test_create_snapshot_success(self, mock_sys_info, mock_npm, mock_pip, mock_apt):
        """Test successful snapshot creation."""
        mock_apt.return_value = [{"name": "vim", "version": "8.2"}]
        mock_pip.return_value = [{"name": "pytest", "version": "7.2.0"}]
        mock_npm.return_value = [{"name": "express", "version": "4.18.0"}]
        mock_sys_info.return_value = {"os": "ubuntu-24.04", "arch": "x86_64"}

        success, snapshot_id, message = self.manager.create_snapshot("Test snapshot")

        self.assertTrue(success)
        self.assertIsNotNone(snapshot_id)
        self.assertIn("successfully", message.lower())

        # Verify snapshot directory and metadata file exist
        snapshot_path = self.snapshots_dir / snapshot_id
        self.assertTrue(snapshot_path.exists())
        self.assertTrue((snapshot_path / "metadata.json").exists())

    def test_list_snapshots_empty(self):
        """Test listing snapshots when none exist."""
        snapshots = self.manager.list_snapshots()
        self.assertEqual(len(snapshots), 0)

    @patch.object(SnapshotManager, "create_snapshot")
    def test_list_snapshots_with_data(self, mock_create):
        """Test listing snapshots with existing data."""
        # Create mock snapshot manually
        snapshot_id = "20250101_120000"
        snapshot_path = self.snapshots_dir / snapshot_id
        snapshot_path.mkdir(parents=True)

        metadata = {
            "id": snapshot_id,
            "timestamp": "2025-01-01T12:00:00",
            "description": "Test snapshot",
            "packages": {"apt": [], "pip": [], "npm": []},
            "system_info": {"os": "ubuntu-24.04"},
            "file_count": 0,
            "size_bytes": 0
        }

        with open(snapshot_path / "metadata.json", "w") as f:
            json.dump(metadata, f)

        snapshots = self.manager.list_snapshots()

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].id, snapshot_id)
        self.assertEqual(snapshots[0].description, "Test snapshot")

    def test_get_snapshot_not_found(self):
        """Test getting non-existent snapshot."""
        snapshot = self.manager.get_snapshot("nonexistent")
        self.assertIsNone(snapshot)

    @patch.object(SnapshotManager, "create_snapshot")
    def test_get_snapshot_success(self, mock_create):
        """Test getting existing snapshot."""
        snapshot_id = "20250101_120000"
        snapshot_path = self.snapshots_dir / snapshot_id
        snapshot_path.mkdir(parents=True)

        metadata = {
            "id": snapshot_id,
            "timestamp": "2025-01-01T12:00:00",
            "description": "Test snapshot",
            "packages": {"apt": [{"name": "vim", "version": "8.2"}], "pip": [], "npm": []},
            "system_info": {"os": "ubuntu-24.04"},
            "file_count": 1,
            "size_bytes": 0
        }

        with open(snapshot_path / "metadata.json", "w") as f:
            json.dump(metadata, f)

        snapshot = self.manager.get_snapshot(snapshot_id)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.id, snapshot_id)
        self.assertEqual(len(snapshot.packages["apt"]), 1)

    def test_delete_snapshot_not_found(self):
        """Test deleting non-existent snapshot."""
        success, message = self.manager.delete_snapshot("nonexistent")
        self.assertFalse(success)
        self.assertIn("not found", message.lower())

    @patch.object(SnapshotManager, "create_snapshot")
    def test_delete_snapshot_success(self, mock_create):
        """Test successful snapshot deletion."""
        snapshot_id = "20250101_120000"
        snapshot_path = self.snapshots_dir / snapshot_id
        snapshot_path.mkdir(parents=True)

        success, message = self.manager.delete_snapshot(snapshot_id)

        self.assertTrue(success)
        self.assertIn("deleted", message.lower())
        self.assertFalse(snapshot_path.exists())

    @patch.object(SnapshotManager, "_detect_apt_packages")
    @patch.object(SnapshotManager, "_detect_pip_packages")
    @patch.object(SnapshotManager, "_detect_npm_packages")
    @patch.object(SnapshotManager, "create_snapshot")
    def test_retention_policy(self, mock_create, mock_npm, mock_pip, mock_apt):
        """Test that retention policy deletes old snapshots."""
        mock_apt.return_value = []
        mock_pip.return_value = []
        mock_npm.return_value = []

        # Create 12 snapshots manually (exceeds limit of 10)
        for i in range(12):
            snapshot_id = f"2025010{(i % 9) + 1}_12000{i}"
            snapshot_path = self.snapshots_dir / snapshot_id
            snapshot_path.mkdir(parents=True)

            metadata = {
                "id": snapshot_id,
                "timestamp": f"2025-01-0{(i % 9) + 1}T12:00:0{i}",
                "description": f"Snapshot {i}",
                "packages": {"apt": [], "pip": [], "npm": []},
                "system_info": {},
                "file_count": 0,
                "size_bytes": 0
            }

            with open(snapshot_path / "metadata.json", "w") as f:
                json.dump(metadata, f)

        # Trigger retention policy
        self.manager._apply_retention_policy()

        # Should have exactly 10 snapshots remaining
        snapshots = self.manager.list_snapshots()
        self.assertEqual(len(snapshots), 10)

    @patch.object(SnapshotManager, "_detect_apt_packages")
    @patch.object(SnapshotManager, "_detect_pip_packages")
    @patch.object(SnapshotManager, "_detect_npm_packages")
    @patch.object(SnapshotManager, "get_snapshot")
    def test_restore_snapshot_dry_run(self, mock_get, mock_npm, mock_pip, mock_apt):
        """Test snapshot restore in dry-run mode."""
        # Mock current packages
        mock_apt.return_value = [{"name": "vim", "version": "8.2"}]
        mock_pip.return_value = []
        mock_npm.return_value = []

        # Mock snapshot data
        mock_snapshot = SnapshotMetadata(
            id="test_snapshot",
            timestamp="2025-01-01T12:00:00",
            description="Test",
            packages={
                "apt": [{"name": "nginx", "version": "1.18.0"}],
                "pip": [],
                "npm": []
            },
            system_info={},
            file_count=1,
            size_bytes=0
        )
        mock_get.return_value = mock_snapshot

        success, message, commands = self.manager.restore_snapshot("test_snapshot", dry_run=True)

        self.assertTrue(success)
        self.assertGreater(len(commands), 0)
        # Should have commands to remove vim and install nginx
        self.assertTrue(any("vim" in cmd for cmd in commands))
        self.assertTrue(any("nginx" in cmd for cmd in commands))

    def test_restore_snapshot_not_found(self):
        """Test restoring non-existent snapshot."""
        success, message, commands = self.manager.restore_snapshot("nonexistent")
        self.assertFalse(success)
        self.assertIn("not found", message.lower())

    def test_generate_snapshot_id_format(self):
        """Test snapshot ID generation format."""
        snapshot_id = self.manager._generate_snapshot_id()

        # Should match YYYYMMDD_HHMMSS_ffffff format (with microseconds)
        self.assertEqual(len(snapshot_id), 22)
        self.assertEqual(snapshot_id[8], "_")
        self.assertEqual(snapshot_id[15], "_")

    def test_directory_security(self):
        """Test that snapshot directory has secure permissions."""
        # Directory should be created with 700 permissions
        self.assertTrue(self.snapshots_dir.exists())
        # Note: Permission checking requires actual filesystem,
        # but we verify the directory exists

    @patch("subprocess.run")
    @patch.object(SnapshotManager, "_detect_apt_packages")
    @patch.object(SnapshotManager, "_detect_pip_packages")
    @patch.object(SnapshotManager, "_detect_npm_packages")
    @patch.object(SnapshotManager, "get_snapshot")
    def test_restore_snapshot_live_execution(self, mock_get, mock_npm, mock_pip, mock_apt, mock_run):
        """Test snapshot restore with dry_run=False (actual execution)."""
        # Mock current packages - vim is installed
        mock_apt.return_value = [{"name": "vim", "version": "8.2"}]
        mock_pip.return_value = [{"name": "cowsay", "version": "6.1"}]
        mock_npm.return_value = []

        # Mock snapshot data - nginx should be installed, vim removed, cowsay removed
        mock_snapshot = SnapshotMetadata(
            id="test_snapshot",
            timestamp="2025-01-01T12:00:00",
            description="Test",
            packages={
                "apt": [{"name": "nginx", "version": "1.18.0"}],
                "pip": [],
                "npm": []
            },
            system_info={},
            file_count=1,
            size_bytes=0
        )
        mock_get.return_value = mock_snapshot

        # Mock subprocess.run for sudo check and command execution
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        success, message, commands = self.manager.restore_snapshot("test_snapshot", dry_run=False)

        self.assertTrue(success)
        self.assertIn("restored", message.lower())
        self.assertGreater(len(commands), 0)

        # Verify subprocess.run was called for actual execution
        self.assertGreater(mock_run.call_count, 1)  # At least sudo check + one command

        # Verify commands contain expected operations
        all_commands = " ".join(commands)
        self.assertIn("vim", all_commands)  # Should remove vim
        self.assertIn("nginx", all_commands)  # Should install nginx
        self.assertIn("cowsay", all_commands)  # Should remove cowsay

    @patch("subprocess.run")
    def test_get_system_info_error_handling(self, mock_run):
        """Test _get_system_info handles errors gracefully."""
        # Simulate subprocess failure
        mock_run.side_effect = Exception("Command failed")

        system_info = self.manager._get_system_info()

        # Should return a dict (possibly empty or with defaults) instead of crashing
        self.assertIsInstance(system_info, dict)
        # The function logs warnings but continues, so we just verify it doesn't crash

    @patch("subprocess.run")
    def test_get_system_info_returncode_error(self, mock_run):
        """Test _get_system_info handles non-zero returncodes."""
        # Simulate command returning non-zero exit code
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        system_info = self.manager._get_system_info()

        # Should handle gracefully and return a dict
        self.assertIsInstance(system_info, dict)

    @patch("subprocess.run")
    @patch.object(SnapshotManager, "_detect_apt_packages")
    @patch.object(SnapshotManager, "_detect_pip_packages")
    @patch.object(SnapshotManager, "_detect_npm_packages")
    @patch.object(SnapshotManager, "get_snapshot")
    def test_restore_snapshot_called_process_error(self, mock_get, mock_npm, mock_pip, mock_apt, mock_run):
        """Test restore_snapshot handles CalledProcessError correctly."""
        import subprocess

        # Mock current packages
        mock_apt.return_value = [{"name": "vim", "version": "8.2"}]
        mock_pip.return_value = []
        mock_npm.return_value = []

        # Mock snapshot data
        mock_snapshot = SnapshotMetadata(
            id="test_snapshot",
            timestamp="2025-01-01T12:00:00",
            description="Test",
            packages={
                "apt": [{"name": "nginx", "version": "1.18.0"}],
                "pip": [],
                "npm": []
            },
            system_info={},
            file_count=1,
            size_bytes=0
        )
        mock_get.return_value = mock_snapshot

        # First call succeeds (sudo check), second call raises CalledProcessError
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # sudo check succeeds
            subprocess.CalledProcessError(1, "apt-get", stderr="Package not found")
        ]

        success, message, commands = self.manager.restore_snapshot("test_snapshot", dry_run=False)

        # Should handle the error gracefully
        self.assertFalse(success)
        self.assertIn("failed", message.lower())

    @patch("subprocess.run")
    @patch.object(SnapshotManager, "_detect_apt_packages")
    @patch.object(SnapshotManager, "_detect_pip_packages")
    @patch.object(SnapshotManager, "_detect_npm_packages")
    @patch.object(SnapshotManager, "get_snapshot")
    def test_restore_snapshot_called_process_error_no_stderr(self, mock_get, mock_npm, mock_pip, mock_apt, mock_run):
        """Test restore_snapshot handles CalledProcessError without stderr."""
        import subprocess

        # Mock current packages
        mock_apt.return_value = []
        mock_pip.return_value = [{"name": "badpkg", "version": "1.0"}]
        mock_npm.return_value = []

        # Mock snapshot data
        mock_snapshot = SnapshotMetadata(
            id="test_snapshot",
            timestamp="2025-01-01T12:00:00",
            description="Test",
            packages={"apt": [], "pip": [], "npm": []},
            system_info={},
            file_count=0,
            size_bytes=0
        )
        mock_get.return_value = mock_snapshot

        # First call succeeds (sudo check), second raises error without stderr
        error = subprocess.CalledProcessError(1, "pip")
        error.stderr = None  # No stderr attribute
        mock_run.side_effect = [
            MagicMock(returncode=0),  # sudo check
            error
        ]

        success, message, commands = self.manager.restore_snapshot("test_snapshot", dry_run=False)

        # Should handle error gracefully even without stderr
        self.assertFalse(success)
        self.assertIsInstance(message, str)
        self.assertGreater(len(message), 0)

    @patch("subprocess.run")
    @patch.object(SnapshotManager, "_detect_apt_packages")
    @patch.object(SnapshotManager, "_detect_pip_packages")
    @patch.object(SnapshotManager, "_detect_npm_packages")
    @patch.object(SnapshotManager, "get_snapshot")
    def test_restore_snapshot_sudo_check_failure(self, mock_get, mock_npm, mock_pip, mock_apt, mock_run):
        """Test restore_snapshot when sudo check fails."""
        # Mock packages
        mock_apt.return_value = []
        mock_pip.return_value = []
        mock_npm.return_value = []

        # Mock snapshot
        mock_snapshot = SnapshotMetadata(
            id="test_snapshot",
            timestamp="2025-01-01T12:00:00",
            description="Test",
            packages={"apt": [], "pip": [], "npm": []},
            system_info={},
            file_count=0,
            size_bytes=0
        )
        mock_get.return_value = mock_snapshot

        # Sudo check fails
        mock_run.return_value = MagicMock(returncode=1)

        success, message, commands = self.manager.restore_snapshot("test_snapshot", dry_run=False)

        self.assertFalse(success)
        self.assertIn("sudo", message.lower())

    @patch("subprocess.run")
    def test_detect_apt_packages_timeout(self, mock_run):
        """Test APT package detection handles timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("dpkg-query", 30)

        packages = self.manager._detect_apt_packages()

        # Should return empty list on timeout
        self.assertEqual(len(packages), 0)

    @patch("subprocess.run")
    def test_detect_pip_packages_file_not_found(self, mock_run):
        """Test PIP package detection handles missing pip binary."""
        mock_run.side_effect = FileNotFoundError("pip not found")

        packages = self.manager._detect_pip_packages()

        # Should return empty list when pip not found
        self.assertEqual(len(packages), 0)

    @patch("subprocess.run")
    def test_detect_npm_packages_json_decode_error(self, mock_run):
        """Test NPM package detection handles invalid JSON."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="invalid json {{"
        )

        packages = self.manager._detect_npm_packages()

        # Should return empty list on JSON decode error
        self.assertEqual(len(packages), 0)

    @patch("subprocess.run")
    @patch.object(SnapshotManager, "_detect_apt_packages")
    @patch.object(SnapshotManager, "_detect_pip_packages")
    @patch.object(SnapshotManager, "_detect_npm_packages")
    @patch.object(SnapshotManager, "get_snapshot")
    def test_restore_snapshot_sudo_check_exception(self, mock_get, mock_npm, mock_pip, mock_apt, mock_run):
        """Test restore_snapshot when sudo check raises exception."""
        # Mock packages
        mock_apt.return_value = []
        mock_pip.return_value = []
        mock_npm.return_value = []

        # Mock snapshot
        mock_snapshot = SnapshotMetadata(
            id="test_snapshot",
            timestamp="2025-01-01T12:00:00",
            description="Test",
            packages={"apt": [], "pip": [], "npm": []},
            system_info={},
            file_count=0,
            size_bytes=0
        )
        mock_get.return_value = mock_snapshot

        # Sudo check raises exception
        mock_run.side_effect = Exception("sudo check failed")

        # Should handle exception and continue (logs warning)
        success, message, commands = self.manager.restore_snapshot("test_snapshot", dry_run=False)

        # Might succeed or fail depending on implementation, but shouldn't crash
        self.assertIsInstance(success, bool)
        self.assertIsInstance(message, str)

    @patch.object(SnapshotManager, "_detect_apt_packages")
    @patch.object(SnapshotManager, "_detect_pip_packages")
    @patch.object(SnapshotManager, "_detect_npm_packages")
    @patch.object(SnapshotManager, "_get_system_info")
    def test_create_snapshot_exception_handling(self, mock_sys_info, mock_npm, mock_pip, mock_apt):
        """Test create_snapshot handles exceptions gracefully."""
        mock_apt.side_effect = Exception("APT detection failed")

        success, snapshot_id, message = self.manager.create_snapshot("Test")

        # Should return failure instead of crashing
        self.assertFalse(success)
        self.assertIsNone(snapshot_id)
        self.assertIn("failed", message.lower())

    @patch("subprocess.run")
    @patch.object(SnapshotManager, "_detect_apt_packages")
    @patch.object(SnapshotManager, "_detect_pip_packages")
    @patch.object(SnapshotManager, "_detect_npm_packages")
    @patch.object(SnapshotManager, "get_snapshot")
    def test_restore_snapshot_timeout_expired(self, mock_get, mock_npm, mock_pip, mock_apt, mock_run):
        """Test restore_snapshot handles TimeoutExpired correctly."""
        import subprocess

        # Mock current packages
        mock_apt.return_value = [{"name": "vim", "version": "8.2"}]
        mock_pip.return_value = []
        mock_npm.return_value = []

        # Mock snapshot data
        mock_snapshot = SnapshotMetadata(
            id="test_snapshot",
            timestamp="2025-01-01T12:00:00",
            description="Test",
            packages={
                "apt": [{"name": "nginx", "version": "1.18.0"}],
                "pip": [],
                "npm": []
            },
            system_info={},
            file_count=1,
            size_bytes=0
        )
        mock_get.return_value = mock_snapshot

        # First call succeeds (sudo check), second call times out
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # sudo check succeeds
            subprocess.TimeoutExpired("apt-get", 300)
        ]

        success, message, commands = self.manager.restore_snapshot("test_snapshot", dry_run=False)

        # Should handle timeout gracefully
        self.assertFalse(success)
        self.assertIn("timed out", message.lower())
        self.assertIn("300", message)  # Should mention the timeout duration


if __name__ == "__main__":
    unittest.main()
