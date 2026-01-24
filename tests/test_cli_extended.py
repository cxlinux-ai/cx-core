"""Extended CLI tests - originally from test/ folder.

These tests provide additional coverage with type hints and more thorough
mocking of internal methods.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.cli import CortexCLI, main
from tests.cli_test_base import CLITestBase


class TestCortexCLIExtended(CLITestBase):
    """Extended unit tests covering CLI behaviours with thorough mocking."""

    def test_get_api_key_openai(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}, clear=True):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                api_key = self.cli._get_api_key()
                self.assertEqual(api_key, "sk-test-key")

    def test_get_api_key_claude(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-claude-key"}, clear=True):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                api_key = self.cli._get_api_key()
                self.assertEqual(api_key, "sk-ant-test-claude-key")

    def test_get_api_key_not_found(self) -> None:
        # When no API key is set and user selects Ollama, falls back to Ollama local mode
        from cortex.api_key_detector import PROVIDER_MENU_CHOICES

        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                with patch("pathlib.Path.cwd", return_value=self._temp_home):
                    with patch("builtins.input", return_value=PROVIDER_MENU_CHOICES["ollama"]):
                        api_key = self.cli._get_api_key()
                        self.assertEqual(api_key, "ollama-local")

    def test_get_provider_openai(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                # Call _get_api_key first to populate _detected_provider
                self.cli._get_api_key()
                provider = self.cli._get_provider()
                self.assertEqual(provider, "openai")

    def test_get_provider_claude(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                # Call _get_api_key first to populate _detected_provider
                self.cli._get_api_key()
                provider = self.cli._get_provider()
                self.assertEqual(provider, "claude")

    def test_get_provider_override(self) -> None:
        with patch.dict(
            os.environ,
            {"CORTEX_PROVIDER": "claude", "OPENAI_API_KEY": "test-key"},
            clear=True,
        ):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                provider = self.cli._get_provider()
                self.assertEqual(provider, "claude")

                del os.environ["CORTEX_PROVIDER"]
                # Call _get_api_key first to populate _detected_provider
                self.cli._get_api_key()
                provider = self.cli._get_provider()
                self.assertEqual(provider, "openai")

    @patch("cortex.cli.cx_print")
    def test_print_status(self, mock_cx_print) -> None:
        self.cli._print_status("🧠", "Test message")
        mock_cx_print.assert_called_once_with("Test message", "thinking")

    @patch("cortex.cli.cx_print")
    def test_print_error(self, mock_cx_print) -> None:
        self.cli._print_error("Test error")
        mock_cx_print.assert_called_once()

    @patch("cortex.cli.cx_print")
    def test_print_success(self, mock_cx_print) -> None:
        self.cli._print_success("Test success")
        mock_cx_print.assert_called_once_with("Test success", "success")

    @patch.object(CortexCLI, "_get_api_key", return_value=None)
    def test_install_no_api_key(self, _mock_get_api_key) -> None:
        result = self.cli.install("docker")
        self.assertEqual(result, 1)

    @patch.object(CortexCLI, "_get_provider", return_value="openai")
    @patch.object(CortexCLI, "_get_api_key", return_value="sk-test-key")
    @patch.object(CortexCLI, "_animate_spinner", return_value=None)
    @patch.object(CortexCLI, "_clear_line", return_value=None)
    @patch("cortex.cli.PredictiveErrorManager")
    @patch("cortex.cli.CommandInterpreter")
    def test_install_dry_run(
        self,
        mock_interpreter_class,
        mock_predictive_class,
        _mock_clear_line,
        _mock_spinner,
        _mock_get_api_key,
        _mock_get_provider,
    ) -> None:
        mock_interpreter = self._setup_interpreter_mock(mock_interpreter_class)
        self._setup_predictive_mock(mock_predictive_class)

        result = self.cli.install("docker", dry_run=True)

        self.assertEqual(result, 0)
        mock_interpreter.parse.assert_called_once_with("install docker")

    @patch.object(CortexCLI, "_get_provider", return_value="openai")
    @patch.object(CortexCLI, "_get_api_key", return_value="sk-test-key")
    @patch.object(CortexCLI, "_animate_spinner", return_value=None)
    @patch.object(CortexCLI, "_clear_line", return_value=None)
    @patch("cortex.cli.PredictiveErrorManager")
    @patch("cortex.cli.CommandInterpreter")
    def test_install_no_execute(
        self,
        mock_interpreter_class,
        mock_predictive_class,
        _mock_clear_line,
        _mock_spinner,
        _mock_get_api_key,
        _mock_get_provider,
    ) -> None:
        mock_interpreter = self._setup_interpreter_mock(mock_interpreter_class)
        self._setup_predictive_mock(mock_predictive_class)

        result = self.cli.install("docker", execute=False)

        self.assertEqual(result, 0)
        mock_interpreter.parse.assert_called_once()

    @patch.object(CortexCLI, "_get_provider", return_value="openai")
    @patch.object(CortexCLI, "_get_api_key", return_value="sk-test-key")
    @patch.object(CortexCLI, "_animate_spinner", return_value=None)
    @patch.object(CortexCLI, "_clear_line", return_value=None)
    @patch("cortex.cli.PredictiveErrorManager")
    @patch("cortex.cli.CommandInterpreter")
    @patch("cortex.cli.InstallationCoordinator")
    def test_install_with_execute_success(
        self,
        mock_coordinator_class,
        mock_interpreter_class,
        mock_predictive_class,
        _mock_clear_line,
        _mock_spinner,
        _mock_get_api_key,
        _mock_get_provider,
    ) -> None:
        self._setup_interpreter_mock(mock_interpreter_class, commands=["echo test"])
        self._setup_predictive_mock(mock_predictive_class)
        mock_coordinator = self._setup_coordinator_mock(mock_coordinator_class, success=True)

        result = self.cli.install("docker", execute=True)

        self.assertEqual(result, 0)
        mock_coordinator.execute.assert_called_once()

    @patch.object(CortexCLI, "_get_provider", return_value="openai")
    @patch.object(CortexCLI, "_get_api_key", return_value="sk-test-key")
    @patch.object(CortexCLI, "_animate_spinner", return_value=None)
    @patch.object(CortexCLI, "_clear_line", return_value=None)
    @patch("cortex.cli.PredictiveErrorManager")
    @patch("cortex.cli.CommandInterpreter")
    @patch("cortex.cli.InstallationCoordinator")
    def test_install_with_execute_failure(
        self,
        mock_coordinator_class,
        mock_interpreter_class,
        mock_predictive_class,
        _mock_clear_line,
        _mock_spinner,
        _mock_get_api_key,
        _mock_get_provider,
    ) -> None:
        self._setup_interpreter_mock(mock_interpreter_class, commands=["invalid command"])
        self._setup_predictive_mock(mock_predictive_class)
        self._setup_coordinator_mock(
            mock_coordinator_class, success=False, error_message="command not found"
        )

        result = self.cli.install("docker", execute=True)

        self.assertEqual(result, 1)

    @patch.object(CortexCLI, "_get_provider", return_value="openai")
    @patch.object(CortexCLI, "_get_api_key", return_value="sk-test-key")
    @patch.object(CortexCLI, "_animate_spinner", return_value=None)
    @patch.object(CortexCLI, "_clear_line", return_value=None)
    @patch("cortex.cli.CommandInterpreter")
    def test_install_no_commands_generated(
        self,
        mock_interpreter_class,
        _mock_clear_line,
        _mock_spinner,
        _mock_get_api_key,
        _mock_get_provider,
    ) -> None:
        self._setup_interpreter_mock(mock_interpreter_class, commands=[])

        result = self.cli.install("docker")

        self.assertEqual(result, 1)

    @patch.object(CortexCLI, "_get_provider", return_value="openai")
    @patch.object(CortexCLI, "_get_api_key", return_value="sk-test-key")
    @patch.object(CortexCLI, "_animate_spinner", return_value=None)
    @patch.object(CortexCLI, "_clear_line", return_value=None)
    @patch("cortex.cli.CommandInterpreter")
    def test_install_value_error(
        self,
        mock_interpreter_class,
        _mock_clear_line,
        _mock_spinner,
        _mock_get_api_key,
        _mock_get_provider,
    ) -> None:
        mock_interpreter = self._setup_interpreter_mock(mock_interpreter_class)
        mock_interpreter.parse.side_effect = ValueError("Invalid input")

        result = self.cli.install("docker")

        self.assertEqual(result, 1)

    @patch.object(CortexCLI, "_get_provider", return_value="openai")
    @patch.object(CortexCLI, "_get_api_key", return_value="sk-test-key")
    @patch.object(CortexCLI, "_animate_spinner", return_value=None)
    @patch.object(CortexCLI, "_clear_line", return_value=None)
    @patch("cortex.cli.CommandInterpreter")
    def test_install_runtime_error(
        self,
        mock_interpreter_class,
        _mock_clear_line,
        _mock_spinner,
        _mock_get_api_key,
        _mock_get_provider,
    ) -> None:
        mock_interpreter = self._setup_interpreter_mock(mock_interpreter_class)
        mock_interpreter.parse.side_effect = RuntimeError("API failed")

        result = self.cli.install("docker")

        self.assertEqual(result, 1)

    @patch.object(CortexCLI, "_get_provider", return_value="openai")
    @patch.object(CortexCLI, "_get_api_key", return_value="sk-test-key")
    @patch.object(CortexCLI, "_animate_spinner", return_value=None)
    @patch.object(CortexCLI, "_clear_line", return_value=None)
    @patch("cortex.cli.CommandInterpreter")
    def test_install_unexpected_error(
        self,
        mock_interpreter_class,
        _mock_clear_line,
        _mock_spinner,
        _mock_get_api_key,
        _mock_get_provider,
    ) -> None:
        mock_interpreter = self._setup_interpreter_mock(mock_interpreter_class)
        mock_interpreter.parse.side_effect = Exception("Unexpected")

        result = self.cli.install("docker")

        self.assertEqual(result, 1)

    @patch("sys.argv", ["cortex"])
    def test_main_no_command(self) -> None:
        result = main()
        self.assertEqual(result, 0)

    @patch("sys.argv", ["cortex", "install", "docker"])
    @patch("cortex.cli.CortexCLI.install")
    def test_main_install_command(self, mock_install) -> None:
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with(
            "docker", execute=False, dry_run=False, parallel=False, json_output=False
        )

    @patch("sys.argv", ["cortex", "install", "docker", "--execute"])
    @patch("cortex.cli.CortexCLI.install")
    def test_main_install_with_execute(self, mock_install) -> None:
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with(
            "docker", execute=True, dry_run=False, parallel=False, json_output=False
        )

    @patch("sys.argv", ["cortex", "install", "docker", "--dry-run"])
    @patch("cortex.cli.CortexCLI.install")
    def test_main_install_with_dry_run(self, mock_install) -> None:
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with(
            "docker", execute=False, dry_run=True, parallel=False, json_output=False
        )

    def test_spinner_animation(self) -> None:
        initial_idx = self.cli.spinner_idx
        self.cli._animate_spinner("Testing")
        self.assertNotEqual(self.cli.spinner_idx, initial_idx)


if __name__ == "__main__":
    unittest.main()
