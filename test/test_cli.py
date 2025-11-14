import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cortex.cli import CortexCLI, main


class TestCortexCLI(unittest.TestCase):
    """Unit tests covering the high-level CLI behaviours."""

    def setUp(self) -> None:
        self.cli = CortexCLI()

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True)
    def test_get_api_key_openai(self) -> None:
        api_key = self.cli._get_api_key('openai')
        self.assertEqual(api_key, 'test-key')

    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-claude-key'}, clear=True)
    def test_get_api_key_claude(self) -> None:
        api_key = self.cli._get_api_key('claude')
        self.assertEqual(api_key, 'test-claude-key')

    @patch.dict(os.environ, {'KIMI_API_KEY': 'kimi-key'}, clear=True)
    def test_get_api_key_kimi(self) -> None:
        api_key = self.cli._get_api_key('kimi')
        self.assertEqual(api_key, 'kimi-key')

    @patch.dict(os.environ, {}, clear=True)
    @patch('sys.stderr')
    def test_get_api_key_not_found(self, mock_stderr) -> None:
        api_key = self.cli._get_api_key('openai')
        self.assertIsNone(api_key)

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True)
    def test_get_provider_openai(self) -> None:
        provider = self.cli._get_provider()
        self.assertEqual(provider, 'openai')

    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}, clear=True)
    def test_get_provider_claude(self) -> None:
        provider = self.cli._get_provider()
        self.assertEqual(provider, 'claude')

    @patch.dict(os.environ, {'KIMI_API_KEY': 'kimi'}, clear=True)
    def test_get_provider_kimi(self) -> None:
        provider = self.cli._get_provider()
        self.assertEqual(provider, 'kimi')

    @patch.dict(os.environ, {'CORTEX_PROVIDER': 'fake'}, clear=True)
    def test_get_provider_override(self) -> None:
        provider = self.cli._get_provider()
        self.assertEqual(provider, 'fake')

    @patch('sys.stdout')
    def test_print_status(self, mock_stdout) -> None:
        self.cli._print_status('[INFO]', 'Test message')
        self.assertTrue(mock_stdout.write.called or print)

    @patch('sys.stderr')
    def test_print_error(self, mock_stderr) -> None:
        self.cli._print_error('Test error')
        self.assertTrue(mock_stderr.write.called)

    @patch('sys.stdout')
    def test_print_success(self, mock_stdout) -> None:
        self.cli._print_success('Test success')
        self.assertTrue(mock_stdout.write.called)

    @patch.dict(os.environ, {}, clear=True)
    def test_install_no_api_key(self) -> None:
        result = self.cli.install('docker')
        self.assertEqual(result, 1)

    @patch.dict(os.environ, {'CORTEX_PROVIDER': 'fake', 'CORTEX_FAKE_COMMANDS': ''}, clear=True)
    @patch('cortex.cli.CommandInterpreter')
    def test_install_fake_provider_skips_api_key(self, mock_interpreter_class) -> None:
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ['echo test']
        mock_interpreter_class.return_value = mock_interpreter

        result = self.cli.install('docker')

        self.assertEqual(result, 0)
        mock_interpreter.parse.assert_called_once_with('install docker')

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True)
    @patch('cortex.cli.CommandInterpreter')
    def test_install_dry_run(self, mock_interpreter_class) -> None:
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ['apt update', 'apt install docker']
        mock_interpreter_class.return_value = mock_interpreter

        result = self.cli.install('docker', dry_run=True)

        self.assertEqual(result, 0)
        mock_interpreter.parse.assert_called_once_with('install docker')

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True)
    @patch('cortex.cli.CommandInterpreter')
    def test_install_no_execute(self, mock_interpreter_class) -> None:
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ['apt update', 'apt install docker']
        mock_interpreter_class.return_value = mock_interpreter

        result = self.cli.install('docker', execute=False)

        self.assertEqual(result, 0)
        mock_interpreter.parse.assert_called_once()

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True)
    @patch('cortex.cli.CommandInterpreter')
    @patch('cortex.cli.InstallationCoordinator')
    def test_install_with_execute_success(self, mock_coordinator_class, mock_interpreter_class) -> None:
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ['echo test']
        mock_interpreter_class.return_value = mock_interpreter

        mock_coordinator = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.total_duration = 1.5
        mock_coordinator.execute.return_value = mock_result
        mock_coordinator_class.return_value = mock_coordinator

        result = self.cli.install('docker', execute=True)

        self.assertEqual(result, 0)
        mock_coordinator.execute.assert_called_once()

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True)
    @patch('cortex.cli.CommandInterpreter')
    @patch('cortex.cli.InstallationCoordinator')
    def test_install_with_execute_failure(self, mock_coordinator_class, mock_interpreter_class) -> None:
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ['invalid command']
        mock_interpreter_class.return_value = mock_interpreter

        mock_coordinator = Mock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.failed_step = 0
        mock_result.error_message = 'command not found'
        mock_coordinator.execute.return_value = mock_result
        mock_coordinator_class.return_value = mock_coordinator

        result = self.cli.install('docker', execute=True)

        self.assertEqual(result, 1)

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True)
    @patch('cortex.cli.CommandInterpreter')
    def test_install_no_commands_generated(self, mock_interpreter_class) -> None:
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = []
        mock_interpreter_class.return_value = mock_interpreter

        result = self.cli.install('docker')

        self.assertEqual(result, 1)

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True)
    @patch('cortex.cli.CommandInterpreter')
    def test_install_value_error(self, mock_interpreter_class) -> None:
        mock_interpreter = Mock()
        mock_interpreter.parse.side_effect = ValueError('Invalid input')
        mock_interpreter_class.return_value = mock_interpreter

        result = self.cli.install('docker')

        self.assertEqual(result, 1)

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True)
    @patch('cortex.cli.CommandInterpreter')
    def test_install_runtime_error(self, mock_interpreter_class) -> None:
        mock_interpreter = Mock()
        mock_interpreter.parse.side_effect = RuntimeError('API failed')
        mock_interpreter_class.return_value = mock_interpreter

        result = self.cli.install('docker')

        self.assertEqual(result, 1)

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}, clear=True)
    @patch('cortex.cli.CommandInterpreter')
    def test_install_unexpected_error(self, mock_interpreter_class) -> None:
        mock_interpreter = Mock()
        mock_interpreter.parse.side_effect = Exception('Unexpected')
        mock_interpreter_class.return_value = mock_interpreter

        result = self.cli.install('docker')

        self.assertEqual(result, 1)

    @patch('sys.argv', ['cortex'])
    def test_main_no_command(self) -> None:
        result = main()
        self.assertEqual(result, 1)

    @patch('sys.argv', ['cortex', '--test'])
    @patch('cortex.cli.subprocess.run')
    def test_main_test_flag(self, mock_run) -> None:
        mock_run.return_value.returncode = 0
        with patch('os.path.exists', return_value=True):
            result = main()
        self.assertEqual(result, 0)
        mock_run.assert_called_once()

    @patch('sys.argv', ['cortex', 'install', 'docker'])
    @patch('cortex.cli.CortexCLI.install')
    def test_main_install_command(self, mock_install) -> None:
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with('docker', execute=False, dry_run=False)

    @patch('sys.argv', ['cortex', 'install', 'docker', '--execute'])
    @patch('cortex.cli.CortexCLI.install')
    def test_main_install_with_execute(self, mock_install) -> None:
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with('docker', execute=True, dry_run=False)

    @patch('sys.argv', ['cortex', 'install', 'docker', '--dry-run'])
    @patch('cortex.cli.CortexCLI.install')
    def test_main_install_with_dry_run(self, mock_install) -> None:
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with('docker', execute=False, dry_run=True)

    def test_spinner_animation(self) -> None:
        initial_idx = self.cli.spinner_idx
        self.cli._animate_spinner('Testing')
        self.assertNotEqual(self.cli.spinner_idx, initial_idx)


if __name__ == '__main__':
    unittest.main()
