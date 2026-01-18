"""Tests for ResolutionManager."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cortex.resolutions import ResolutionManager


class TestResolutionManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.storage_path = Path(self.temp_dir.name) / "resolutions.json"
        self.manager = ResolutionManager(str(self.storage_path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_resolution(self):
        """Test saving a resolution."""
        self.manager.save("Docker failed", "systemctl start docker")

        with open(self.storage_path) as f:
            data = json.load(f)

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["issue"], "Docker failed")
        self.assertEqual(data[0]["fix"], "systemctl start docker")

    def test_search_resolution(self):
        """Test searching for resolutions."""
        self.manager.save("Docker failed to start", "systemctl start docker")
        self.manager.save("Python missing", "apt install python3")
        self.manager.save("Cannot connect to Docker", "usermod -aG docker $USER")

        # Search for "docker"
        results = self.manager.search("I have a docker issue")
        self.assertEqual(len(results), 2)
        issues = [r["issue"] for r in results]
        self.assertIn("Docker failed to start", issues)
        self.assertIn("Cannot connect to Docker", issues)
        self.assertNotIn("Python missing", issues)

    def test_search_limit(self):
        """Test search result limit."""
        for i in range(5):
            self.manager.save(f"Issue {i}", f"Fix {i}")

        results = self.manager.search("Issue", limit=2)
        self.assertEqual(len(results), 2)

    def test_max_resolutions_limit(self):
        """Test that we only keep the last 50 resolutions."""
        for i in range(60):
            self.manager.save(f"Issue {i}", f"Fix {i}")

        with open(self.storage_path) as f:
            data = json.load(f)

        self.assertEqual(len(data), 50)
        self.assertEqual(data[-1]["issue"], "Issue 59")
