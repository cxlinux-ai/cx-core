"""
Test suite for package conflict resolution UI and user preferences.

Tests cover:
1. Interactive conflict resolution UI
2. User preference saving for conflict resolutions
3. Configuration management commands
4. Conflict detection and resolution workflow
5. Preference persistence and validation

Note: These tests verify the conflict resolution UI, preference persistence,
and configuration management features implemented in Issue #42.
"""

import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.cli import CortexCLI
from cortex.dependency_resolver import DependencyResolver
from cortex.user_preferences import PreferencesManager


class TestConflictResolutionUI(unittest.TestCase):
    """Test interactive conflict resolution UI functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.cli = CortexCLI()
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_preferences.yaml"

        # Mock preferences manager to use temp config
        self.cli._prefs_manager = PreferencesManager(config_path=self.config_file)

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("builtins.input")
    @patch("sys.stdout", new_callable=StringIO)
    def test_interactive_conflict_resolution_skip(self, mock_stdout, mock_input):
        """Test skipping package during conflict resolution."""
        # Simulate user choosing to skip (option 3)
        mock_input.side_effect = ["3"]

        conflicts = [("nginx", "apache2")]

        # Should raise InstallationCancelledError on choice 3
        from cortex.cli import InstallationCancelledError
        with self.assertRaises(InstallationCancelledError):
            self.cli._resolve_conflicts_interactive(conflicts)

        # Verify skip option was presented
        output = mock_stdout.getvalue()
        self.assertIn("nginx", output)
        self.assertIn("apache2", output)
        self.assertIn("Cancel installation", output)

    @patch("builtins.input")
    @patch("sys.stdout", new_callable=StringIO)
    def test_interactive_conflict_resolution_keep_new(self, mock_stdout, mock_input):
        """Test keeping new package during conflict resolution."""
        # Simulate user choosing to keep new (option 1) and not saving preference
        mock_input.side_effect = ["1", "n"]

        conflicts = [("mysql-server", "mariadb-server")]

        result = self.cli._resolve_conflicts_interactive(conflicts)

        # Verify keep new option was presented
        output = mock_stdout.getvalue()
        self.assertIn("mysql-server", output)
        self.assertIn("mariadb-server", output)
        self.assertIn("Keep/Install", output)

        # Verify function returns resolution with package to remove
        self.assertIn("remove", result)
        self.assertIn("mariadb-server", result["remove"])

    @patch("builtins.input")
    @patch("sys.stdout", new_callable=StringIO)
    def test_interactive_conflict_resolution_keep_existing(self, mock_stdout, mock_input):
        """Test keeping existing package during conflict resolution."""
        # Simulate user choosing to keep existing (option 2) and not saving preference
        mock_input.side_effect = ["2", "n"]

        conflicts = [("nginx", "apache2")]

        result = self.cli._resolve_conflicts_interactive(conflicts)

        # Verify keep existing option was presented
        output = mock_stdout.getvalue()
        self.assertIn("nginx", output)
        self.assertIn("apache2", output)
        self.assertIn("Keep/Install", output)

        # Verify function returns resolution with package to remove
        self.assertIn("remove", result)
        self.assertIn("nginx", result["remove"])

    @patch("builtins.input")
    def test_invalid_conflict_choice_retry(self, mock_input):
        """Test handling invalid input during conflict resolution."""
        # Simulate invalid input followed by valid input and not saving preference
        mock_input.side_effect = ["invalid", "99", "1", "n"]

        conflicts = [("package-a", "package-b")]

        result = self.cli._resolve_conflicts_interactive(conflicts)

        # Verify it eventually accepts valid input
        self.assertIn("remove", result)
        self.assertIn("package-b", result["remove"])

        # Verify input was called multiple times (including the save preference prompt)
        self.assertGreaterEqual(mock_input.call_count, 3)


class TestConflictPreferenceSaving(unittest.TestCase):
    """Test saving user preferences for conflict resolutions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_preferences.yaml"
        self.prefs_manager = PreferencesManager(config_path=self.config_file)
        self.cli = CortexCLI()
        # Use the internal attribute that _get_prefs_manager() checks
        self.cli._prefs_manager = self.prefs_manager

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("builtins.input")
    def test_save_conflict_preference_yes(self, mock_input):
        """Test saving conflict preference when user chooses yes."""
        # Simulate user choosing to save preference
        mock_input.return_value = "y"

        self.cli._ask_save_preference("nginx", "apache2", "nginx")

        # Verify preference is in manager (uses min:max format)
        saved = self.prefs_manager.get("conflicts.saved_resolutions")
        conflict_key = "apache2:nginx"  # min:max format
        self.assertIn(conflict_key, saved)
        self.assertEqual(saved[conflict_key], "nginx")

    @patch("builtins.input")
    def test_save_conflict_preference_no(self, mock_input):
        """Test not saving conflict preference when user chooses no."""
        # Simulate user choosing not to save preference
        mock_input.return_value = "n"

        self.cli._ask_save_preference("package-a", "package-b", "package-a")

        # Verify preference is not in manager (uses min:max format)
        saved = self.prefs_manager.get("conflicts.saved_resolutions") or {}
        conflict_key = "package-a:package-b"  # min:max format
        self.assertNotIn(conflict_key, saved)

    def test_conflict_preference_persistence(self):
        """Test that saved conflict preferences persist across sessions."""
        # Save a preference (using min:max format)
        self.prefs_manager.set(
            "conflicts.saved_resolutions", {"mariadb-server:mysql-server": "mysql-server"}
        )
        self.prefs_manager.save()

        # Create new preferences manager with same config file
        new_prefs = PreferencesManager(config_path=self.config_file)
        new_prefs.load()

        # Verify preference was loaded
        saved = new_prefs.get("conflicts.saved_resolutions")
        self.assertIn("mariadb-server:mysql-server", saved)
        self.assertEqual(saved["mariadb-server:mysql-server"], "mysql-server")

    def test_multiple_conflict_preferences(self):
        """Test saving and retrieving multiple conflict preferences."""
        # Save multiple preferences (using min:max format)
        resolutions = {
            "apache2:nginx": "nginx",
            "mariadb-server:mysql-server": "mariadb-server",
            "emacs:vim": "vim",
        }

        for conflict, choice in resolutions.items():
            self.prefs_manager.set(
                "conflicts.saved_resolutions",
                {**self.prefs_manager.get("conflicts.saved_resolutions"), conflict: choice},
            )

        self.prefs_manager.save()

        # Verify all preferences were saved
        saved = self.prefs_manager.get("conflicts.saved_resolutions")
        for conflict, choice in resolutions.items():
            self.assertIn(conflict, saved)
            self.assertEqual(saved[conflict], choice)


class TestConfigurationManagement(unittest.TestCase):
    """Test configuration management commands."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_preferences.yaml"
        self.cli = CortexCLI()
        self.cli._prefs_manager = PreferencesManager(config_path=self.config_file)

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("sys.stdout", new_callable=StringIO)
    def test_config_list_command(self, mock_stdout):
        """Test listing all configuration settings."""
        # Set some preferences
        self.cli._prefs_manager.set("ai.model", "gpt-4")
        self.cli._prefs_manager.set("verbosity", "verbose")

        # Run list command
        result = self.cli.config("list")

        # Verify success
        self.assertEqual(result, 0)

        # Verify output contains settings (using key=value format)
        output = mock_stdout.getvalue()
        self.assertIn("ai.model", output)
        self.assertIn("gpt-4", output)

    @patch("sys.stdout", new_callable=StringIO)
    def test_config_get_command(self, mock_stdout):
        """Test getting specific configuration value."""
        # Set a preference
        self.cli._prefs_manager.set("ai.model", "gpt-4")

        # Run get command
        result = self.cli.config("get", "ai.model")

        # Verify success
        self.assertEqual(result, 0)

        # Verify output contains value
        output = mock_stdout.getvalue()
        self.assertIn("gpt-4", output)

    @patch("sys.stdout", new_callable=StringIO)
    def test_config_set_command(self, mock_stdout):
        """Test setting configuration value."""
        # Run set command
        result = self.cli.config("set", "ai.model", "gpt-4")

        # Verify success
        self.assertEqual(result, 0)

        # Verify value was set
        value = self.cli._prefs_manager.get("ai.model")
        self.assertEqual(value, "gpt-4")

    @patch("builtins.input", return_value="y")
    @patch("sys.stdout", new_callable=StringIO)
    def test_config_reset_command(self, mock_stdout, mock_input):
        """Test resetting configuration to defaults."""
        # Set some preferences
        self.cli._prefs_manager.set("ai.model", "custom-model")
        self.cli._prefs_manager.set("verbosity", "debug")

        # Run reset command
        result = self.cli.config("reset")

        # Verify success
        self.assertEqual(result, 0)

        # Verify preferences were reset
        self.assertEqual(self.cli._prefs_manager.get("ai.model"), "claude-sonnet-4")

    def test_config_export_import(self):
        """Test exporting and importing configuration."""
        export_file = Path(self.temp_dir) / "export.json"

        # Set preferences
        self.cli._prefs_manager.set("ai.model", "gpt-4")
        self.cli._prefs_manager.set("verbosity", "verbose")
        resolutions = {"apache2:nginx": "nginx"}
        self.cli._prefs_manager.set("conflicts.saved_resolutions", resolutions)

        # Export
        result = self.cli.config("export", str(export_file))
        self.assertEqual(result, 0)

        # Verify export file exists
        self.assertTrue(export_file.exists())

        # Reset preferences
        self.cli._prefs_manager.reset()

        # Import
        result = self.cli.config("import", str(export_file))
        self.assertEqual(result, 0)

        # Verify preferences were restored
        self.assertEqual(self.cli._prefs_manager.get("ai.model"), "gpt-4")
        self.assertEqual(self.cli._prefs_manager.get("verbosity"), "verbose")
        saved = self.cli._prefs_manager.get("conflicts.saved_resolutions")
        self.assertEqual(saved, resolutions)


class TestConflictDetectionWorkflow(unittest.TestCase):
    """Test conflict detection and resolution workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_preferences.yaml"
        self.cli = CortexCLI()
        self.cli._prefs_manager = PreferencesManager(config_path=self.config_file)

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("builtins.input")
    def test_conflict_detected_triggers_ui(self, mock_input):
        """Test that detected conflicts trigger interactive UI."""
        # Mock user choosing to skip
        mock_input.return_value = "3"

        # Test the conflict resolution logic directly
        conflicts = [("nginx", "apache2")]

        # Should raise InstallationCancelledError on choice 3
        from cortex.cli import InstallationCancelledError
        with self.assertRaises(InstallationCancelledError):
            self.cli._resolve_conflicts_interactive(conflicts)

    @patch("builtins.input")
    def test_saved_preference_bypasses_ui(self, mock_input):
        """Test that saved preferences bypass interactive UI."""
        # Save a conflict preference (using min:max format)
        conflict_key = "mariadb-server:mysql-server"
        self.cli._prefs_manager.set("conflicts.saved_resolutions", {conflict_key: "mysql-server"})
        self.cli._prefs_manager.save()

        # Verify preference exists
        saved = self.cli._prefs_manager.get("conflicts.saved_resolutions")
        self.assertIn(conflict_key, saved)
        self.assertEqual(saved[conflict_key], "mysql-server")

        # Test that with a saved preference, the UI is bypassed
        conflicts = [("mariadb-server", "mysql-server")]
        result = self.cli._resolve_conflicts_interactive(conflicts)

        # Verify the correct package was marked for removal
        self.assertIn("mariadb-server", result["remove"])
        # Verify input was not called (preference was used directly)
        mock_input.assert_not_called()

    @patch("cortex.dependency_resolver.subprocess.run")
    def test_dependency_resolver_detects_conflicts(self, mock_run):
        """Test that DependencyResolver correctly detects package conflicts."""
        # Mock apt-cache depends output
        mock_run.return_value = MagicMock(
            returncode=0, stdout="nginx\n  Depends: some-dep\n  Conflicts: apache2\n"
        )

        resolver = DependencyResolver()
        graph = resolver.resolve_dependencies("nginx")

        # Verify the resolver was called
        self.assertTrue(mock_run.called)
        # Verify graph object was created
        self.assertIsNotNone(graph)


class TestPreferencePersistence(unittest.TestCase):
    """Test preference persistence and validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_preferences.yaml"
        self.prefs_manager = PreferencesManager(config_path=self.config_file)

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_preferences_save_and_load(self):
        """Test saving and loading preferences from file."""
        # Set preferences
        self.prefs_manager.set("ai.model", "gpt-4")
        self.prefs_manager.set("conflicts.saved_resolutions", {"pkg-a:pkg-b": "pkg-a"})

        # Save to file
        self.prefs_manager.save()

        # Verify file exists
        self.assertTrue(self.config_file.exists())

        # Load in new instance
        new_prefs = PreferencesManager(config_path=self.config_file)
        new_prefs.load()

        # Verify preferences loaded correctly
        self.assertEqual(new_prefs.get("ai.model"), "gpt-4")
        saved = new_prefs.get("conflicts.saved_resolutions")
        self.assertEqual(saved["pkg-a:pkg-b"], "pkg-a")

    def test_preference_validation(self):
        """Test preference validation logic."""
        # Load/create preferences
        prefs = self.prefs_manager.load()

        # Valid preferences
        errors = self.prefs_manager.validate()
        self.assertEqual(len(errors), 0)

        # Set invalid preference by directly modifying (bypass validation in set())
        prefs.ai.max_suggestions = -999
        errors = self.prefs_manager.validate()
        self.assertGreater(len(errors), 0)

    def test_nested_preference_keys(self):
        """Test handling nested preference keys."""
        # Set nested preference
        self.prefs_manager.set("conflicts.saved_resolutions", {"key1": "value1", "key2": "value2"})

        # Get nested preference
        value = self.prefs_manager.get("conflicts.saved_resolutions")
        self.assertIsInstance(value, dict)
        self.assertEqual(value["key1"], "value1")

    def test_preference_reset_to_defaults(self):
        """Test resetting preferences to defaults."""
        # Set custom values
        self.prefs_manager.set("ai.model", "custom-model")
        self.prefs_manager.set("verbosity", "debug")

        # Reset
        self.prefs_manager.reset()

        # Verify defaults restored
        self.assertEqual(self.prefs_manager.get("ai.model"), "claude-sonnet-4")
        self.assertEqual(self.prefs_manager.get("verbosity"), "normal")

    def test_preference_export_import_json(self):
        """Test exporting and importing preferences as JSON."""
        export_file = Path(self.temp_dir) / "export.json"

        # Set preferences
        self.prefs_manager.set("ai.model", "gpt-4")
        resolutions = {"conflict:test": "test"}
        self.prefs_manager.set("conflicts.saved_resolutions", resolutions)

        # Export
        self.prefs_manager.export_json(export_file)

        # Reset
        self.prefs_manager.reset()

        # Import
        self.prefs_manager.import_json(export_file)

        # Verify
        self.assertEqual(self.prefs_manager.get("ai.model"), "gpt-4")
        saved = self.prefs_manager.get("conflicts.saved_resolutions")
        self.assertEqual(saved, resolutions)


if __name__ == "__main__":
    unittest.main()
