"""Tests for cortex.updater module."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.update_checker import ReleaseInfo, UpdateCheckResult
from cortex.updater import (
    BackupInfo,
    Updater,
    UpdateResult,
    UpdateStatus,
    download_with_progress,
    verify_checksum,
)
from cortex.version_manager import SemanticVersion, UpdateChannel


class TestUpdater(unittest.TestCase):
    """Tests for Updater class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.backup_patch = patch("cortex.updater.BACKUP_DIR", Path(self.temp_dir))
        self.backup_patch.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.backup_patch.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_creates_backup_dir(self):
        """Test that initializing Updater creates backup directory."""
        backup_dir = Path(self.temp_dir) / "test_backup"
        with patch("cortex.updater.BACKUP_DIR", backup_dir):
            Updater()
            self.assertTrue(backup_dir.exists())

    @patch("cortex.updater.check_for_updates")
    def test_check_update_available(self, mock_check):
        """Test checking for available updates."""
        mock_check.return_value = UpdateCheckResult(
            update_available=True,
            current_version=SemanticVersion.parse("1.0.0"),
            latest_version=SemanticVersion.parse("2.0.0"),
        )

        updater = Updater()
        result = updater.check_update_available()

        self.assertTrue(result.update_available)
        mock_check.assert_called_once()

    @patch("cortex.updater.check_for_updates")
    def test_update_when_already_current(self, mock_check):
        """Test update when already on latest version."""
        mock_check.return_value = UpdateCheckResult(
            update_available=False,
            current_version=SemanticVersion.parse("1.0.0"),
        )

        updater = Updater()
        result = updater.update()

        self.assertTrue(result.success)
        self.assertEqual(result.status, UpdateStatus.SUCCESS)
        self.assertIn("up to date", result.error or "")

    @patch("cortex.updater.Updater._pip_install")
    @patch("cortex.updater.Updater._create_backup")
    @patch("cortex.updater.check_for_updates")
    def test_update_success(self, mock_check, mock_backup, mock_pip):
        """Test successful update."""
        mock_check.return_value = UpdateCheckResult(
            update_available=True,
            current_version=SemanticVersion.parse("1.0.0"),
            latest_version=SemanticVersion.parse("2.0.0"),
            latest_release=ReleaseInfo(
                version=SemanticVersion.parse("2.0.0"),
                tag_name="v2.0.0",
                name="Test",
                body="",
                published_at="2024-01-15T12:00:00Z",
                html_url="https://example.com",
            ),
        )
        mock_backup.return_value = Path(self.temp_dir) / "backup"
        mock_pip.return_value = True

        updater = Updater()
        result = updater.update()

        self.assertTrue(result.success)
        self.assertEqual(result.status, UpdateStatus.SUCCESS)
        self.assertEqual(result.new_version, "2.0.0")
        mock_pip.assert_called()

    @patch("cortex.updater.Updater._rollback")
    @patch("cortex.updater.Updater._pip_install")
    @patch("cortex.updater.Updater._create_backup")
    @patch("cortex.updater.check_for_updates")
    def test_update_failure_triggers_rollback(
        self, mock_check, mock_backup, mock_pip, mock_rollback
    ):
        """Test that failed update triggers rollback."""
        backup_path = Path(self.temp_dir) / "backup"
        backup_path.mkdir(parents=True)

        mock_check.return_value = UpdateCheckResult(
            update_available=True,
            current_version=SemanticVersion.parse("1.0.0"),
            latest_version=SemanticVersion.parse("2.0.0"),
            latest_release=ReleaseInfo(
                version=SemanticVersion.parse("2.0.0"),
                tag_name="v2.0.0",
                name="Test",
                body="",
                published_at="2024-01-15T12:00:00Z",
                html_url="https://example.com",
            ),
        )
        mock_backup.return_value = backup_path
        mock_pip.return_value = False
        mock_rollback.return_value = True

        updater = Updater()
        result = updater.update()

        self.assertFalse(result.success)
        self.assertEqual(result.status, UpdateStatus.ROLLED_BACK)
        mock_rollback.assert_called_with(backup_path)

    def test_dry_run_does_not_install(self):
        """Test that dry run doesn't actually install."""
        with patch("cortex.updater.check_for_updates") as mock_check:
            mock_check.return_value = UpdateCheckResult(
                update_available=True,
                current_version=SemanticVersion.parse("1.0.0"),
                latest_version=SemanticVersion.parse("2.0.0"),
                latest_release=ReleaseInfo(
                    version=SemanticVersion.parse("2.0.0"),
                    tag_name="v2.0.0",
                    name="Test",
                    body="",
                    published_at="2024-01-15T12:00:00Z",
                    html_url="https://example.com",
                ),
            )

            updater = Updater()
            with patch.object(updater, "_pip_install") as mock_pip:
                result = updater.update(dry_run=True)

                self.assertTrue(result.success)
                self.assertEqual(result.status, UpdateStatus.PENDING)
                mock_pip.assert_not_called()

    def test_list_backups_empty(self):
        """Test listing backups when none exist."""
        updater = Updater()
        backups = updater.list_backups()
        self.assertEqual(backups, [])

    def test_list_backups_with_backups(self):
        """Test listing backups when they exist."""
        # Create a fake backup
        backup_path = Path(self.temp_dir) / "cortex_1.0.0_20240115_120000"
        backup_path.mkdir()
        metadata = {
            "version": "1.0.0",
            "timestamp": "2024-01-15T12:00:00",
        }
        with open(backup_path / "backup_metadata.json", "w") as f:
            json.dump(metadata, f)
        # Create a dummy file for size calculation
        (backup_path / "test.py").write_text("print('test')")

        updater = Updater()
        backups = updater.list_backups()

        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].version, "1.0.0")
        self.assertIsInstance(backups[0], BackupInfo)

    def test_progress_callback(self):
        """Test that progress callback is called."""
        messages = []

        def callback(msg, percent):
            messages.append((msg, percent))

        updater = Updater(progress_callback=callback)
        updater._report_progress("Test message", 50)

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0], ("Test message", 50))


class TestDownloadWithProgress(unittest.TestCase):
    """Tests for download_with_progress function."""

    @patch("cortex.updater.requests.get")
    def test_download_success(self, mock_get):
        """Test successful download."""
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "100"}
        mock_response.iter_content.return_value = [b"x" * 50, b"x" * 50]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with tempfile.NamedTemporaryFile(delete=False) as f:
            dest_path = Path(f.name)

        try:
            result = download_with_progress("https://example.com/file.tar.gz", dest_path)
            self.assertTrue(result)
            self.assertEqual(dest_path.read_bytes(), b"x" * 100)
        finally:
            dest_path.unlink(missing_ok=True)

    @patch("cortex.updater.requests.get")
    def test_download_with_progress_callback(self, mock_get):
        """Test download calls progress callback."""
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "100"}
        mock_response.iter_content.return_value = [b"x" * 50, b"x" * 50]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        progress_calls = []

        def callback(downloaded, total):
            progress_calls.append((downloaded, total))

        with tempfile.NamedTemporaryFile(delete=False) as f:
            dest_path = Path(f.name)

        try:
            download_with_progress(
                "https://example.com/file.tar.gz", dest_path, progress_callback=callback
            )
            self.assertEqual(len(progress_calls), 2)
            self.assertEqual(progress_calls[-1], (100, 100))
        finally:
            dest_path.unlink(missing_ok=True)

    @patch("cortex.updater.requests.get")
    def test_download_failure(self, mock_get):
        """Test download failure handling."""
        import requests

        mock_get.side_effect = requests.RequestException("Network error")

        with tempfile.NamedTemporaryFile(delete=False) as f:
            dest_path = Path(f.name)

        try:
            result = download_with_progress("https://example.com/file.tar.gz", dest_path)
            self.assertFalse(result)
        finally:
            dest_path.unlink(missing_ok=True)


class TestVerifyChecksum(unittest.TestCase):
    """Tests for verify_checksum function."""

    def test_verify_valid_checksum(self):
        """Test verifying valid checksum."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            file_path = Path(f.name)

        try:
            # Calculate expected hash
            import hashlib

            expected = hashlib.sha256(b"test content").hexdigest()

            result = verify_checksum(file_path, expected)
            self.assertTrue(result)
        finally:
            file_path.unlink()

    def test_verify_invalid_checksum(self):
        """Test verifying invalid checksum."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            file_path = Path(f.name)

        try:
            result = verify_checksum(file_path, "invalid_hash")
            self.assertFalse(result)
        finally:
            file_path.unlink()

    def test_verify_md5_checksum(self):
        """Test verifying MD5 checksum."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            file_path = Path(f.name)

        try:
            import hashlib

            expected = hashlib.md5(b"test content").hexdigest()

            result = verify_checksum(file_path, expected, algorithm="md5")
            self.assertTrue(result)
        finally:
            file_path.unlink()


class TestUpdateResult(unittest.TestCase):
    """Tests for UpdateResult dataclass."""

    def test_success_result(self):
        """Test creating successful update result."""
        result = UpdateResult(
            success=True,
            status=UpdateStatus.SUCCESS,
            previous_version="1.0.0",
            new_version="2.0.0",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, UpdateStatus.SUCCESS)
        self.assertEqual(result.previous_version, "1.0.0")
        self.assertEqual(result.new_version, "2.0.0")

    def test_failure_result(self):
        """Test creating failed update result."""
        result = UpdateResult(
            success=False,
            status=UpdateStatus.FAILED,
            previous_version="1.0.0",
            error="Installation failed",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Installation failed")


if __name__ == "__main__":
    unittest.main()
