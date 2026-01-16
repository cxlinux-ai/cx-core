"""Tests for cortex.update_checker module."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.update_checker import (
    CACHE_TTL_SECONDS,
    ReleaseInfo,
    UpdateChecker,
    UpdateCheckResult,
    check_for_updates,
    should_notify_update,
)
from cortex.version_manager import SemanticVersion, UpdateChannel


class TestReleaseInfo(unittest.TestCase):
    """Tests for ReleaseInfo class."""

    def test_from_github_response(self):
        """Test creating ReleaseInfo from GitHub API response."""
        github_data = {
            "tag_name": "v1.0.0",
            "name": "Release 1.0.0",
            "body": "## What's New\n- Feature 1\n- Bug fix",
            "published_at": "2024-01-15T12:00:00Z",
            "html_url": "https://github.com/cortexlinux/cortex/releases/tag/v1.0.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "cortex-1.0.0.tar.gz",
                    "browser_download_url": "https://github.com/download/cortex-1.0.0.tar.gz",
                }
            ],
        }

        release = ReleaseInfo.from_github_response(github_data)

        self.assertEqual(release.tag_name, "v1.0.0")
        self.assertEqual(str(release.version), "1.0.0")
        self.assertEqual(release.name, "Release 1.0.0")
        self.assertIn("Feature 1", release.body)
        self.assertIsNotNone(release.download_url)

    def test_release_notes_summary(self):
        """Test release notes summary extraction."""
        release = ReleaseInfo(
            version=SemanticVersion.parse("1.0.0"),
            tag_name="v1.0.0",
            name="Test",
            body="Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7",
            published_at="2024-01-15T12:00:00Z",
            html_url="https://example.com",
        )

        summary = release.release_notes_summary
        lines = summary.split("\n")
        self.assertLessEqual(len(lines), 5)

    def test_release_notes_empty(self):
        """Test release notes when body is empty."""
        release = ReleaseInfo(
            version=SemanticVersion.parse("1.0.0"),
            tag_name="v1.0.0",
            name="Test",
            body="",
            published_at="2024-01-15T12:00:00Z",
            html_url="https://example.com",
        )

        self.assertEqual(release.release_notes_summary, "No release notes available.")

    def test_formatted_date(self):
        """Test formatted date output."""
        release = ReleaseInfo(
            version=SemanticVersion.parse("1.0.0"),
            tag_name="v1.0.0",
            name="Test",
            body="",
            published_at="2024-01-15T12:00:00Z",
            html_url="https://example.com",
        )

        self.assertEqual(release.formatted_date, "2024-01-15")


class TestUpdateChecker(unittest.TestCase):
    """Tests for UpdateChecker class."""

    def setUp(self):
        """Set up test fixtures."""
        # Use temp directory for cache
        self.temp_dir = tempfile.mkdtemp()
        self.cache_patch = patch("cortex.update_checker.CACHE_DIR", Path(self.temp_dir))
        self.cache_patch.start()
        self.cache_file_patch = patch(
            "cortex.update_checker.UPDATE_CACHE_FILE",
            Path(self.temp_dir) / "update_check.json",
        )
        self.cache_file_patch.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.cache_patch.stop()
        self.cache_file_patch.stop()
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("cortex.update_checker.requests.get")
    def test_check_fetches_releases(self, mock_get):
        """Test that check fetches releases from GitHub."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "tag_name": "v2.0.0",
                "name": "Release 2.0.0",
                "body": "New features",
                "published_at": "2024-01-15T12:00:00Z",
                "html_url": "https://github.com/test",
                "draft": False,
                "prerelease": False,
                "assets": [],
            }
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        checker = UpdateChecker(cache_enabled=False)
        result = checker.check()

        mock_get.assert_called_once()
        self.assertIsInstance(result, UpdateCheckResult)

    @patch("cortex.update_checker.requests.get")
    def test_check_handles_network_error(self, mock_get):
        """Test that check handles network errors gracefully."""
        import requests

        mock_get.side_effect = requests.RequestException("Network error")

        checker = UpdateChecker(cache_enabled=False)
        result = checker.check()

        self.assertFalse(result.update_available)
        self.assertIsNotNone(result.error)
        self.assertIn("Network error", result.error)

    @patch("cortex.update_checker.requests.get")
    def test_check_filters_by_stable_channel(self, mock_get):
        """Test that stable channel filters out prereleases."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "tag_name": "v2.0.0-beta.1",
                "name": "Beta Release",
                "body": "",
                "published_at": "2024-01-15T12:00:00Z",
                "html_url": "https://github.com/test",
                "draft": False,
                "prerelease": True,
                "assets": [],
            },
            {
                "tag_name": "v1.5.0",
                "name": "Stable Release",
                "body": "",
                "published_at": "2024-01-10T12:00:00Z",
                "html_url": "https://github.com/test",
                "draft": False,
                "prerelease": False,
                "assets": [],
            },
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        checker = UpdateChecker(channel=UpdateChannel.STABLE, cache_enabled=False)
        result = checker.check()

        # Should find 1.5.0 as latest stable, not 2.0.0-beta.1
        if result.latest_version:
            self.assertFalse(result.latest_version.is_prerelease)

    @patch("cortex.update_checker.requests.get")
    def test_check_includes_beta_in_beta_channel(self, mock_get):
        """Test that beta channel includes beta releases."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "tag_name": "v2.0.0-beta.1",
                "name": "Beta Release",
                "body": "",
                "published_at": "2024-01-15T12:00:00Z",
                "html_url": "https://github.com/test",
                "draft": False,
                "prerelease": True,
                "assets": [],
            },
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        checker = UpdateChecker(channel=UpdateChannel.BETA, cache_enabled=False)
        releases = checker._fetch_releases()
        filtered = checker._filter_by_channel(releases)

        self.assertEqual(len(filtered), 1)

    @patch("cortex.update_checker.requests.get")
    def test_check_skips_drafts(self, mock_get):
        """Test that draft releases are skipped."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "tag_name": "v3.0.0",
                "name": "Draft Release",
                "body": "",
                "published_at": "2024-01-20T12:00:00Z",
                "html_url": "https://github.com/test",
                "draft": True,  # Draft!
                "prerelease": False,
                "assets": [],
            },
            {
                "tag_name": "v2.0.0",
                "name": "Published Release",
                "body": "",
                "published_at": "2024-01-15T12:00:00Z",
                "html_url": "https://github.com/test",
                "draft": False,
                "prerelease": False,
                "assets": [],
            },
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        checker = UpdateChecker(cache_enabled=False)
        releases = checker._fetch_releases()

        # Should only have 1 release (the non-draft)
        self.assertEqual(len(releases), 1)
        self.assertEqual(str(releases[0].version), "2.0.0")

    def test_cache_result(self):
        """Test that results are cached."""
        checker = UpdateChecker(cache_enabled=True)

        result = UpdateCheckResult(
            update_available=True,
            current_version=SemanticVersion.parse("1.0.0"),
            latest_version=SemanticVersion.parse("2.0.0"),
            latest_release=ReleaseInfo(
                version=SemanticVersion.parse("2.0.0"),
                tag_name="v2.0.0",
                name="Test",
                body="Notes",
                published_at="2024-01-15T12:00:00Z",
                html_url="https://example.com",
            ),
        )

        checker._cache_result(result)

        # Check cache file exists
        cache_file = Path(self.temp_dir) / "update_check.json"
        self.assertTrue(cache_file.exists())

        # Read and verify
        with open(cache_file) as f:
            data = json.load(f)
        self.assertEqual(data["current_version"], "1.0.0")
        self.assertEqual(data["latest_version"], "2.0.0")
        self.assertTrue(data["update_available"])


class TestConvenienceFunctions(unittest.TestCase):
    """Tests for module-level convenience functions."""

    @patch("cortex.update_checker.UpdateChecker.check")
    def test_check_for_updates(self, mock_check):
        """Test check_for_updates convenience function."""
        mock_check.return_value = UpdateCheckResult(
            update_available=False,
            current_version=SemanticVersion.parse("1.0.0"),
        )

        result = check_for_updates()

        self.assertIsInstance(result, UpdateCheckResult)
        mock_check.assert_called_once()

    @patch("cortex.update_checker.check_for_updates")
    def test_should_notify_update_returns_release_when_available(self, mock_check):
        """Test should_notify_update returns release info when update available."""
        release = ReleaseInfo(
            version=SemanticVersion.parse("2.0.0"),
            tag_name="v2.0.0",
            name="Test",
            body="",
            published_at="2024-01-15T12:00:00Z",
            html_url="https://example.com",
        )
        mock_check.return_value = UpdateCheckResult(
            update_available=True,
            current_version=SemanticVersion.parse("1.0.0"),
            latest_version=SemanticVersion.parse("2.0.0"),
            latest_release=release,
        )

        result = should_notify_update()

        self.assertIsNotNone(result)
        self.assertEqual(str(result.version), "2.0.0")

    @patch("cortex.update_checker.check_for_updates")
    def test_should_notify_update_returns_none_when_up_to_date(self, mock_check):
        """Test should_notify_update returns None when up to date."""
        mock_check.return_value = UpdateCheckResult(
            update_available=False,
            current_version=SemanticVersion.parse("1.0.0"),
        )

        result = should_notify_update()

        self.assertIsNone(result)

    @patch.dict(os.environ, {"CORTEX_UPDATE_CHECK": "0"})
    def test_should_notify_update_respects_env_var(self):
        """Test that CORTEX_UPDATE_CHECK=0 disables checks."""
        result = should_notify_update()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
