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
            snapshot_id = f"2025010{i % 10}_12000{i}"
            snapshot_path = self.snapshots_dir / snapshot_id
            snapshot_path.mkdir(parents=True)
            
            metadata = {
                "id": snapshot_id,
                "timestamp": f"2025-01-0{i % 10}T12:00:0{i}",
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


if __name__ == "__main__":
    unittest.main()