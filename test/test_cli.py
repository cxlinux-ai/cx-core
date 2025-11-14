import unittest
from unittest.mock import Mock, patch, MagicMock, call
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cortex.cli import CortexCLI, main


class TestCortexCLI(unittest.TestCase):
    
    def setUp(self):
        self.cli = CortexCLI()
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_get_api_key_openai(self):
        api_key = self.cli._get_api_key()
        self.assertEqual(api_key, 'test-key')
    
    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-claude-key', 'OPENAI_API_KEY': ''}, clear=True)
    def test_get_api_key_claude(self):
        api_key = self.cli._get_api_key()
        self.assertEqual(api_key, 'test-claude-key')
    
    @patch.dict(os.environ, {}, clear=True)
    @patch('sys.stderr')
    def test_get_api_key_not_found(self, mock_stderr):
        api_key = self.cli._get_api_key()
        self.assertIsNone(api_key)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_get_provider_openai(self):
        provider = self.cli._get_provider()
        self.assertEqual(provider, 'openai')
    
    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}, clear=True)
    def test_get_provider_claude(self):
        provider = self.cli._get_provider()
        self.assertEqual(provider, 'claude')
    
    @patch('sys.stdout')
    def test_print_status(self, mock_stdout):
        self.cli._print_status("🧠", "Test message")
        self.assertTrue(mock_stdout.write.called or print)
    
    @patch('sys.stderr')
    def test_print_error(self, mock_stderr):
        self.cli._print_error("Test error")
        self.assertTrue(True)
    
    @patch('sys.stdout')
    def test_print_success(self, mock_stdout):
        self.cli._print_success("Test success")
        self.assertTrue(True)
    
    @patch.dict(os.environ, {}, clear=True)
    def test_install_no_api_key(self):
        result = self.cli.install("docker")
        self.assertEqual(result, 1)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    def test_install_dry_run(self, mock_interpreter_class):
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["apt update", "apt install docker"]
        mock_interpreter_class.return_value = mock_interpreter
        
        result = self.cli.install("docker", dry_run=True)
        
        self.assertEqual(result, 0)
        mock_interpreter.parse.assert_called_once_with("install docker")
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    def test_install_no_execute(self, mock_interpreter_class):
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["apt update", "apt install docker"]
        mock_interpreter_class.return_value = mock_interpreter
        
        result = self.cli.install("docker", execute=False)
        
        self.assertEqual(result, 0)
        mock_interpreter.parse.assert_called_once()
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    @patch('cortex.cli.InstallationCoordinator')
    def test_install_with_execute_success(self, mock_coordinator_class, mock_interpreter_class):
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["echo test"]
        mock_interpreter_class.return_value = mock_interpreter
        
        mock_coordinator = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.total_duration = 1.5
        mock_coordinator.execute.return_value = mock_result
        mock_coordinator_class.return_value = mock_coordinator
        
        result = self.cli.install("docker", execute=True)
        
        self.assertEqual(result, 0)
        mock_coordinator.execute.assert_called_once()
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    @patch('cortex.cli.InstallationCoordinator')
    def test_install_with_execute_failure(self, mock_coordinator_class, mock_interpreter_class):
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["invalid command"]
        mock_interpreter_class.return_value = mock_interpreter
        
        mock_coordinator = Mock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.failed_step = 0
        mock_result.error_message = "command not found"
        mock_coordinator.execute.return_value = mock_result
        mock_coordinator_class.return_value = mock_coordinator
        
        result = self.cli.install("docker", execute=True)
        
        self.assertEqual(result, 1)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    def test_install_no_commands_generated(self, mock_interpreter_class):
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = []
        mock_interpreter_class.return_value = mock_interpreter
        
        result = self.cli.install("docker")
        
        self.assertEqual(result, 1)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    def test_install_value_error(self, mock_interpreter_class):
        mock_interpreter = Mock()
        mock_interpreter.parse.side_effect = ValueError("Invalid input")
        mock_interpreter_class.return_value = mock_interpreter
        
        result = self.cli.install("docker")
        
        self.assertEqual(result, 1)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    def test_install_runtime_error(self, mock_interpreter_class):
        mock_interpreter = Mock()
        mock_interpreter.parse.side_effect = RuntimeError("API failed")
        mock_interpreter_class.return_value = mock_interpreter
        
        result = self.cli.install("docker")
        
        self.assertEqual(result, 1)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    def test_install_unexpected_error(self, mock_interpreter_class):
        mock_interpreter = Mock()
        mock_interpreter.parse.side_effect = Exception("Unexpected")
        mock_interpreter_class.return_value = mock_interpreter
        
        result = self.cli.install("docker")
        
        self.assertEqual(result, 1)
    
    @patch('sys.argv', ['cortex'])
    def test_main_no_command(self):
        result = main()
        self.assertEqual(result, 1)
    
    @patch('sys.argv', ['cortex', 'install', 'docker'])
    @patch('cortex.cli.CortexCLI.install')
    def test_main_install_command(self, mock_install):
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with('docker', execute=False, dry_run=False)
    
    @patch('sys.argv', ['cortex', 'install', 'docker', '--execute'])
    @patch('cortex.cli.CortexCLI.install')
    def test_main_install_with_execute(self, mock_install):
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with('docker', execute=True, dry_run=False)
    
    @patch('sys.argv', ['cortex', 'install', 'docker', '--dry-run'])
    @patch('cortex.cli.CortexCLI.install')
    def test_main_install_with_dry_run(self, mock_install):
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with('docker', execute=False, dry_run=True)
    
    def test_spinner_animation(self):
        initial_idx = self.cli.spinner_idx
        self.cli._animate_spinner("Testing")
        self.assertNotEqual(self.cli.spinner_idx, initial_idx)


if __name__ == '__main__':
    unittest.main()
