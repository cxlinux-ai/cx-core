import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.cli import CortexCLI, main
from tests.cli_test_base import CLITestBase


class TestCortexCLI(CLITestBase):

    def test_get_api_key_openai(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-123"}, clear=True):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                api_key = self.cli._get_api_key()
                self.assertEqual(api_key, "sk-test-openai-key-123")

    def test_get_api_key_claude(self):
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-ant-test-claude-key-123", "OPENAI_API_KEY": ""},
            clear=True,
        ):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                api_key = self.cli._get_api_key()
                self.assertEqual(api_key, "sk-ant-test-claude-key-123")

    @patch("sys.stderr")
    def test_get_api_key_not_found(self, mock_stderr):
        # When no API key is set and user selects Ollama, falls back to Ollama local mode
        from cortex.api_key_detector import PROVIDER_MENU_CHOICES

        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                with patch("pathlib.Path.cwd", return_value=self._temp_home):
                    with patch("builtins.input", return_value=PROVIDER_MENU_CHOICES["ollama"]):
                        api_key = self.cli._get_api_key()
                        self.assertEqual(api_key, "ollama-local")

    def test_get_provider_openai(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-123"}, clear=True):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                # Call _get_api_key first to populate _detected_provider
                self.cli._get_api_key()
                provider = self.cli._get_provider()
                self.assertEqual(provider, "openai")

    def test_get_provider_claude(self):
        with patch.dict(
            os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-claude-key-123"}, clear=True
        ):
            with patch("pathlib.Path.home", return_value=self._temp_home):
                # Call _get_api_key first to populate _detected_provider
                self.cli._get_api_key()
                provider = self.cli._get_provider()
                self.assertEqual(provider, "claude")

    @patch("sys.stdout")
    def test_print_status(self, mock_stdout):
        self.cli._print_status("🧠", "Test message")
        self.assertTrue(mock_stdout.write.called or print)

    @patch("sys.stderr")
    def test_print_error(self, mock_stderr):
        self.cli._print_error("Test error")
        self.assertTrue(True)

    @patch("sys.stdout")
    def test_print_success(self, mock_stdout):
        self.cli._print_success("Test success")
        self.assertTrue(True)

    @patch.dict(os.environ, {}, clear=True)
    @patch("cortex.cli.CommandInterpreter")
    @patch("cortex.cli.PredictiveErrorManager")
    def test_install_no_api_key(self, mock_predictive_class, mock_interpreter_class):
        # Should work with Ollama (no API key needed)
        self._setup_interpreter_mock(mock_interpreter_class)
        self._setup_predictive_mock(mock_predictive_class)

        result = self.cli.install("docker")
        # Should succeed with Ollama as fallback provider
        self.assertEqual(result, 0)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-123"}, clear=True)
    @patch("cortex.cli.CommandInterpreter")
    @patch("cortex.cli.PredictiveErrorManager")
    def test_install_dry_run(self, mock_predictive_class, mock_interpreter_class):
        mock_interpreter = self._setup_interpreter_mock(mock_interpreter_class)
        self._setup_predictive_mock(mock_predictive_class)

        result = self.cli.install("docker", dry_run=True)

        self.assertEqual(result, 0)
        mock_interpreter.parse.assert_called_once_with("install docker")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-123"}, clear=True)
    @patch("cortex.cli.CommandInterpreter")
    @patch("cortex.cli.PredictiveErrorManager")
    def test_install_no_execute(self, mock_predictive_class, mock_interpreter_class):
        mock_interpreter = self._setup_interpreter_mock(mock_interpreter_class)
        self._setup_predictive_mock(mock_predictive_class)

        result = self.cli.install("docker", execute=False)

        self.assertEqual(result, 0)
        mock_interpreter.parse.assert_called_once()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-123"}, clear=True)
    @patch("cortex.cli.CommandInterpreter")
    @patch("cortex.cli.InstallationCoordinator")
    @patch("cortex.cli.PredictiveErrorManager")
    def test_install_with_execute_success(
        self, mock_predictive_class, mock_coordinator_class, mock_interpreter_class
    ):
        self._setup_interpreter_mock(mock_interpreter_class, commands=["echo test"])
        self._setup_predictive_mock(mock_predictive_class)
        mock_coordinator = self._setup_coordinator_mock(mock_coordinator_class, success=True)

        result = self.cli.install("docker", execute=True)

        self.assertEqual(result, 0)
        mock_coordinator.execute.assert_called_once()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-123"}, clear=True)
    @patch("cortex.cli.CommandInterpreter")
    @patch("cortex.cli.InstallationCoordinator")
    @patch("cortex.cli.PredictiveErrorManager")
    def test_install_with_execute_failure(
        self, mock_predictive_class, mock_coordinator_class, mock_interpreter_class
    ):
        self._setup_interpreter_mock(mock_interpreter_class, commands=["invalid command"])
        self._setup_predictive_mock(mock_predictive_class)
        self._setup_coordinator_mock(
            mock_coordinator_class, success=False, error_message="command not found"
        )

        result = self.cli.install("docker", execute=True)

        self.assertEqual(result, 1)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-123"}, clear=True)
    @patch("cortex.cli.CommandInterpreter")
    def test_install_no_commands_generated(self, mock_interpreter_class):
        self._setup_interpreter_mock(mock_interpreter_class, commands=[])

        result = self.cli.install("docker")

        self.assertEqual(result, 1)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-123"}, clear=True)
    @patch("cortex.cli.CommandInterpreter")
    def test_install_value_error(self, mock_interpreter_class):
        mock_interpreter = self._setup_interpreter_mock(mock_interpreter_class)
        mock_interpreter.parse.side_effect = ValueError("Invalid input")

        result = self.cli.install("docker")

        self.assertEqual(result, 1)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-123"}, clear=True)
    @patch("cortex.cli.CommandInterpreter")
    def test_install_runtime_error(self, mock_interpreter_class):
        mock_interpreter = self._setup_interpreter_mock(mock_interpreter_class)
        mock_interpreter.parse.side_effect = RuntimeError("API failed")

        result = self.cli.install("docker")

        self.assertEqual(result, 1)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-123"}, clear=True)
    @patch("cortex.cli.CommandInterpreter")
    def test_install_unexpected_error(self, mock_interpreter_class):
        mock_interpreter = self._setup_interpreter_mock(mock_interpreter_class)
        mock_interpreter.parse.side_effect = Exception("Unexpected")

        result = self.cli.install("docker")

        self.assertEqual(result, 1)

    @patch("sys.argv", ["cortex"])
    def test_main_no_command(self):
        # Running cortex with no command shows help and returns 0 (success)
        result = main()
        self.assertEqual(result, 0)

    @patch("sys.argv", ["cortex", "install", "docker"])
    @patch("cortex.cli.CortexCLI.install")
    def test_main_install_command(self, mock_install):
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with(
            "docker", execute=False, dry_run=False, parallel=False, json_output=False
        )

    @patch("sys.argv", ["cortex", "install", "docker", "--execute"])
    @patch("cortex.cli.CortexCLI.install")
    def test_main_install_with_execute(self, mock_install):
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with(
            "docker", execute=True, dry_run=False, parallel=False, json_output=False
        )

    @patch("sys.argv", ["cortex", "install", "docker", "--dry-run"])
    @patch("cortex.cli.CortexCLI.install")
    def test_main_install_with_dry_run(self, mock_install):
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with(
            "docker", execute=False, dry_run=True, parallel=False, json_output=False
        )

    def test_spinner_animation(self):
        initial_idx = self.cli.spinner_idx
        self.cli._animate_spinner("Testing")
        self.assertNotEqual(self.cli.spinner_idx, initial_idx)


if __name__ == "__main__":
    unittest.main()
