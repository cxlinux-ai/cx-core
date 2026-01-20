"""
Tests for daemon command functionality in CortexCLI.

Tests cover:
- install, uninstall, config, reload-config, version, ping, shutdown, run-tests
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock, Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.cli import CortexCLI


class TestDaemonCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.cli = CortexCLI()
        self._temp_dir = tempfile.TemporaryDirectory()
        self._temp_home = Path(self._temp_dir.name)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def _create_mock_uninstall_script(self, exists=True):
        """Helper to create a mock uninstall script Path object."""
        mock_uninstall_script = Mock()
        mock_uninstall_script.exists.return_value = exists
        mock_uninstall_script.chmod = Mock()
        mock_uninstall_script.stat.return_value = Mock()
        mock_uninstall_script.__str__ = lambda x: "/path/to/uninstall.sh"
        mock_uninstall_script.__fspath__ = lambda x: "/path/to/uninstall.sh"
        return mock_uninstall_script

    def _setup_path_side_effect(self, mock_path_class, mock_uninstall_script):
        """Helper to set up Path class side effect."""

        def path_side_effect(*args, **kwargs):
            path_str = str(args[0]) if args else ""
            if "uninstall.sh" in path_str:
                return mock_uninstall_script
            # Return a regular mock for other paths
            mock_path = Mock()
            mock_path.exists.return_value = False
            return mock_path

        mock_path_class.side_effect = path_side_effect

    def _setup_subprocess_side_effect(self, mock_subprocess, handle_script=False):
        """Helper to set up subprocess side effect."""

        def subprocess_side_effect(*args, **kwargs):
            mock_result = Mock()
            if "dpkg-query" in str(args[0]):
                # InstallationHistory call
                mock_result.returncode = 0
                mock_result.stdout = "install ok installed|1.0.0"
                mock_result.stderr = ""
            elif handle_script and "bash" in str(args[0]) and "uninstall" in str(args[0]):
                # Uninstall script execution
                mock_result.returncode = 0
                mock_result.stderr = ""
            else:
                # Manual uninstall commands or other calls
                mock_result.returncode = 0
                mock_result.stderr = ""
            return mock_result

        mock_subprocess.side_effect = subprocess_side_effect

    def test_daemon_no_action(self):
        """Test daemon command with no action shows help."""
        args = Mock()
        args.daemon_action = None
        result = self.cli.daemon(args)
        self.assertEqual(result, 0)

    @patch("cortex.cli.cx_header")
    @patch("cortex.cli.cx_print")
    @patch("cortex.cli.Path.exists")
    @patch("subprocess.run")
    def test_daemon_install_dry_run(self, mock_subprocess, mock_exists, mock_print, mock_header):
        """Test daemon install without --execute flag (dry run)."""
        args = Mock()
        args.execute = False
        args.daemon_action = "install"
        mock_exists.return_value = True

        # Mock subprocess for InstallationHistory calls
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "install ok installed|1.0.0"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        result = self.cli._daemon_install(args)
        self.assertEqual(result, 0)
        # Should not call subprocess for setup script (only for package checks)
        # Allow for InstallationHistory calls but verify no setup script execution
        setup_calls = [
            call for call in mock_subprocess.call_args_list if "setup_daemon.py" in str(call)
        ]
        self.assertEqual(len(setup_calls), 0)

    @patch("cortex.cli.cx_header")
    @patch("cortex.cli.cx_print")
    @patch("cortex.cli.Path.exists")
    def test_daemon_install_script_not_found(self, mock_exists, mock_print, mock_header):
        """Test daemon install when setup script is missing."""
        args = Mock()
        args.execute = True
        args.daemon_action = "install"
        mock_exists.return_value = False

        result = self.cli._daemon_install(args)
        self.assertEqual(result, 1)

    @patch("cortex.cli.cx_header")
    @patch("cortex.cli.cx_print")
    @patch("cortex.cli.Path.exists")
    @patch("subprocess.run")
    def test_daemon_uninstall_dry_run(self, mock_subprocess, mock_exists, mock_print, mock_header):
        """Test daemon uninstall without --execute flag (dry run)."""
        args = Mock()
        args.execute = False
        args.daemon_action = "uninstall"
        mock_exists.return_value = True

        # Mock subprocess for InstallationHistory calls
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "install ok installed|1.0.0"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        result = self.cli._daemon_uninstall(args)
        self.assertEqual(result, 0)
        # Should not call subprocess for uninstall (only for package checks)
        # Allow for InstallationHistory calls but verify no uninstall execution
        uninstall_calls = [
            call
            for call in mock_subprocess.call_args_list
            if "uninstall" in str(call) or "systemctl" in str(call)
        ]
        self.assertEqual(len(uninstall_calls), 0)

    @patch("cortex.cli.cx_header")
    @patch("cortex.cli.cx_print")
    @patch("cortex.cli.Path")
    @patch("subprocess.run")
    def test_daemon_uninstall_with_script(
        self, mock_subprocess, mock_path_class, mock_print, mock_header
    ):
        """Test daemon uninstall with uninstall script."""
        args = Mock()
        args.execute = True
        args.daemon_action = "uninstall"

        # Create a mock Path object
        mock_uninstall_script = self._create_mock_uninstall_script(exists=True)
        self._setup_path_side_effect(mock_path_class, mock_uninstall_script)
        self._setup_subprocess_side_effect(mock_subprocess, handle_script=True)

        result = self.cli._daemon_uninstall(args)
        self.assertEqual(result, 0)
        # Should have called subprocess for both package check and script execution
        self.assertGreater(mock_subprocess.call_count, 0)

    @patch("cortex.cli.cx_header")
    @patch("cortex.cli.cx_print")
    @patch("cortex.cli.Path")
    @patch("subprocess.run")
    def test_daemon_uninstall_manual(
        self, mock_subprocess, mock_path_class, mock_print, mock_header
    ):
        """Test daemon uninstall with manual commands (no script)."""
        args = Mock()
        args.execute = True
        args.daemon_action = "uninstall"

        # Create a mock Path object for uninstall script that doesn't exist
        mock_uninstall_script = self._create_mock_uninstall_script(exists=False)
        self._setup_path_side_effect(mock_path_class, mock_uninstall_script)
        self._setup_subprocess_side_effect(mock_subprocess, handle_script=False)

        result = self.cli._daemon_uninstall(args)
        self.assertEqual(result, 0)
        # Should have called subprocess multiple times for manual commands
        self.assertGreater(mock_subprocess.call_count, 1)

    @patch("cortex.cli.CortexCLI._daemon_ipc_call")
    def test_daemon_config_success(self, mock_ipc_call):
        """Test daemon config command with successful response."""
        from cortex.daemon_client import DaemonResponse

        mock_response = DaemonResponse(
            success=True,
            result={"socket_path": "/run/cortex/cortex.sock", "log_level": "info"},
        )
        mock_ipc_call.return_value = (True, mock_response)

        result = self.cli._daemon_config()
        self.assertEqual(result, 0)
        mock_ipc_call.assert_called_once()

    @patch("cortex.cli.CortexCLI._daemon_ipc_call")
    def test_daemon_config_failure(self, mock_ipc_call):
        """Test daemon config command with failed response."""
        from cortex.daemon_client import DaemonResponse

        mock_response = DaemonResponse(success=False, error="Connection failed")
        mock_ipc_call.return_value = (True, mock_response)

        result = self.cli._daemon_config()
        self.assertEqual(result, 1)

    @patch("cortex.cli.CortexCLI._daemon_ipc_call")
    def test_daemon_config_connection_error(self, mock_ipc_call):
        """Test daemon config command when connection fails."""
        mock_ipc_call.return_value = (False, None)

        result = self.cli._daemon_config()
        self.assertEqual(result, 1)

    @patch("cortex.cli.CortexCLI._daemon_ipc_call")
    def test_daemon_reload_config_success(self, mock_ipc_call):
        """Test daemon reload-config command with successful response."""
        from cortex.daemon_client import DaemonResponse

        mock_response = DaemonResponse(success=True, result={"reloaded": True})
        mock_ipc_call.return_value = (True, mock_response)

        result = self.cli._daemon_reload_config()
        self.assertEqual(result, 0)

    @patch("cortex.cli.CortexCLI._daemon_ipc_call")
    def test_daemon_reload_config_failure(self, mock_ipc_call):
        """Test daemon reload-config command with failed response."""
        from cortex.daemon_client import DaemonResponse

        mock_response = DaemonResponse(success=False, error="Config reload failed")
        mock_ipc_call.return_value = (True, mock_response)

        result = self.cli._daemon_reload_config()
        self.assertEqual(result, 1)

    @patch("cortex.cli.CortexCLI._daemon_ipc_call")
    def test_daemon_version_success(self, mock_ipc_call):
        """Test daemon version command with successful response."""
        from cortex.daemon_client import DaemonResponse

        mock_response = DaemonResponse(success=True, result={"version": "1.0.0", "name": "cortexd"})
        mock_ipc_call.return_value = (True, mock_response)

        result = self.cli._daemon_version()
        self.assertEqual(result, 0)

    @patch("cortex.cli.CortexCLI._daemon_ipc_call")
    def test_daemon_ping_success(self, mock_ipc_call):
        """Test daemon ping command with successful response."""
        from cortex.daemon_client import DaemonResponse

        mock_response = DaemonResponse(success=True, result={"pong": True})
        mock_ipc_call.return_value = (True, mock_response)

        result = self.cli._daemon_ping()
        self.assertEqual(result, 0)

    @patch("cortex.cli.CortexCLI._daemon_ipc_call")
    def test_daemon_shutdown_success(self, mock_ipc_call):
        """Test daemon shutdown command with successful response."""
        from cortex.daemon_client import DaemonResponse

        mock_response = DaemonResponse(success=True, result={"shutdown": "initiated"})
        mock_ipc_call.return_value = (True, mock_response)

        result = self.cli._daemon_shutdown()
        self.assertEqual(result, 0)

    @patch("cortex.cli.cx_header")
    @patch("cortex.cli.cx_print")
    @patch("cortex.cli.Path.exists")
    def test_daemon_run_tests_not_built(self, mock_exists, mock_print, mock_header):
        """Test daemon run-tests when tests are not built."""
        args = Mock()
        args.test = None
        args.unit = False
        args.integration = False
        args.verbose = False

        # Mock tests directory doesn't exist
        mock_exists.return_value = False

        result = self.cli._daemon_run_tests(args)
        self.assertEqual(result, 1)

    @patch("cortex.cli.cx_header")
    @patch("cortex.cli.cx_print")
    @patch("cortex.cli.Path.exists")
    @patch("subprocess.run")
    def test_daemon_run_tests_success(self, mock_subprocess, mock_exists, mock_print, mock_header):
        """Test daemon run-tests with successful execution."""
        args = Mock()
        args.test = None
        args.unit = False
        args.integration = False
        args.verbose = False

        # Mock Path.exists to return True for test files
        # _daemon_run_tests checks (tests_dir / test).exists() for each test
        # We need to return True when checking for test file existence
        mock_exists.return_value = True

        # Mock subprocess result
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        result = self.cli._daemon_run_tests(args)
        self.assertEqual(result, 0)
        mock_subprocess.assert_called()

    @patch("cortex.cli.cx_print")
    @patch("cortex.cli.InstallationHistory")
    @patch("cortex.daemon_client.DaemonClient")
    def test_daemon_ipc_call_success(
        self, mock_daemon_client_class, mock_history_class, mock_print
    ):
        """Test _daemon_ipc_call helper with successful IPC call."""
        from cortex.daemon_client import DaemonResponse

        # Setup mocks
        mock_history = Mock()
        mock_history_class.return_value = mock_history
        mock_history.record_installation.return_value = "test-install-id"

        mock_client = Mock()
        mock_daemon_client_class.return_value = mock_client

        mock_response = DaemonResponse(success=True, result={"test": "data"})

        # Create a mock IPC function that uses the client and returns the response
        def mock_ipc_func(client):
            # Verify the client is passed correctly
            self.assertIs(client, mock_client)
            return mock_response

        # Test _daemon_ipc_call directly
        success, response = self.cli._daemon_ipc_call("test_operation", mock_ipc_func)

        # Verify results
        self.assertTrue(success)
        self.assertIsNotNone(response)
        self.assertEqual(response, mock_response)
        mock_daemon_client_class.assert_called_once()
        mock_history.record_installation.assert_called_once()
        mock_history.update_installation.assert_called_once_with("test-install-id", ANY)

    @patch("cortex.cli.InstallationHistory")
    def test_update_history_on_failure(self, mock_history_class):
        """Test _update_history_on_failure helper method."""
        mock_history = Mock()
        mock_history_class.return_value = mock_history

        history = mock_history
        install_id = "123"
        error_msg = "Test error"

        self.cli._update_history_on_failure(history, install_id, error_msg)
        mock_history.update_installation.assert_called_once_with(install_id, ANY, error_msg)

    @patch("cortex.cli.InstallationHistory")
    def test_update_history_on_failure_no_id(self, mock_history_class):
        """Test _update_history_on_failure with no install_id."""
        mock_history = Mock()
        mock_history_class.return_value = mock_history

        history = mock_history
        install_id = None
        error_msg = "Test error"

        self.cli._update_history_on_failure(history, install_id, error_msg)
        # Should not call update_installation when install_id is None
        mock_history.update_installation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
