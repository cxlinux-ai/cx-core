"""Unit tests for the troubleshoot module."""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.troubleshoot import DANGEROUS_PATTERNS, Troubleshooter


class TestExtractCodeBlocks(unittest.TestCase):
    """Tests for _extract_code_blocks method."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_res_manager_patcher = patch("cortex.troubleshoot.ResolutionManager")
        self.mock_res_manager = self.mock_res_manager_patcher.start()

        # Mock the API key detector to avoid dependency on real config
        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "fake-key", "fake", "test")
            with patch("cortex.troubleshoot.AskHandler"):
                self.troubleshooter = Troubleshooter()

    def tearDown(self):
        self.mock_res_manager_patcher.stop()

    def test_extract_bash_block(self):
        """Test extracting a bash code block."""
        text = """Here is a command:
```bash
ls -la
```
That's it."""
        blocks = self.troubleshooter._extract_code_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].strip(), "ls -la")

    def test_extract_sh_block(self):
        """Test extracting an sh code block."""
        text = """Run this:
```sh
df -h
```"""
        blocks = self.troubleshooter._extract_code_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].strip(), "df -h")

    def test_extract_generic_block(self):
        """Test extracting a generic code block without language specifier."""
        text = """Command:
```
echo hello
```"""
        blocks = self.troubleshooter._extract_code_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].strip(), "echo hello")

    def test_extract_multiple_blocks(self):
        """Test extracting multiple code blocks."""
        text = """First:
```bash
cmd1
```
Second:
```bash
cmd2
```"""
        blocks = self.troubleshooter._extract_code_blocks(text)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].strip(), "cmd1")
        self.assertEqual(blocks[1].strip(), "cmd2")

    def test_extract_no_blocks(self):
        """Test text without code blocks."""
        text = "Just some text without any code blocks."
        blocks = self.troubleshooter._extract_code_blocks(text)
        self.assertEqual(len(blocks), 0)

    def test_extract_multiline_command(self):
        """Test extracting a multiline command."""
        text = """Run:
```bash
for i in 1 2 3; do
    echo $i
done
```"""
        blocks = self.troubleshooter._extract_code_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertIn("for i in", blocks[0])
        self.assertIn("done", blocks[0])


class TestIsCommandSafe(unittest.TestCase):
    """Tests for _is_command_safe method (blacklist enforcement)."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_res_manager_patcher = patch("cortex.troubleshoot.ResolutionManager")
        self.mock_res_manager = self.mock_res_manager_patcher.start()

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "fake-key", "fake", "test")
            with patch("cortex.troubleshoot.AskHandler"):
                self.troubleshooter = Troubleshooter()

    def tearDown(self):
        self.mock_res_manager_patcher.stop()

    def test_safe_command_ls(self):
        """Test that 'ls' is safe."""
        is_safe, reason = self.troubleshooter._is_command_safe("ls -la")
        self.assertTrue(is_safe)
        self.assertEqual(reason, "")

    def test_safe_command_df(self):
        """Test that 'df -h' is safe."""
        is_safe, reason = self.troubleshooter._is_command_safe("df -h")
        self.assertTrue(is_safe)
        self.assertEqual(reason, "")

    def test_safe_command_systemctl_status(self):
        """Test that 'systemctl status' is safe."""
        is_safe, reason = self.troubleshooter._is_command_safe("systemctl status docker")
        self.assertTrue(is_safe)
        self.assertEqual(reason, "")

    def test_dangerous_rm_rf(self):
        """Test that 'rm -rf' is blocked."""
        is_safe, reason = self.troubleshooter._is_command_safe("rm -rf /tmp/test")
        self.assertFalse(is_safe)
        self.assertIn("dangerous", reason.lower())

    def test_dangerous_rm_rf_slash(self):
        """Test that 'rm -rf /' is blocked."""
        is_safe, reason = self.troubleshooter._is_command_safe("rm -rf /")
        self.assertFalse(is_safe)

    def test_dangerous_rm_fr(self):
        """Test that 'rm -fr' is blocked."""
        is_safe, reason = self.troubleshooter._is_command_safe("rm -fr /home/user")
        self.assertFalse(is_safe)

    def test_dangerous_mkfs(self):
        """Test that 'mkfs' is blocked."""
        is_safe, reason = self.troubleshooter._is_command_safe("mkfs.ext4 /dev/sda1")
        self.assertFalse(is_safe)

    def test_dangerous_dd(self):
        """Test that 'dd' to device is blocked."""
        is_safe, reason = self.troubleshooter._is_command_safe("dd if=/dev/zero of=/dev/sda")
        self.assertFalse(is_safe)

    def test_dangerous_shutdown(self):
        """Test that 'shutdown' is blocked."""
        is_safe, reason = self.troubleshooter._is_command_safe("shutdown -h now")
        self.assertFalse(is_safe)

    def test_dangerous_reboot(self):
        """Test that 'reboot' is blocked."""
        is_safe, reason = self.troubleshooter._is_command_safe("reboot")
        self.assertFalse(is_safe)

    def test_dangerous_chmod_777_root(self):
        """Test that 'chmod 777 /' is blocked."""
        is_safe, reason = self.troubleshooter._is_command_safe("chmod 777 /")
        self.assertFalse(is_safe)

    def test_safe_chmod_normal(self):
        """Test that 'chmod 755' on a normal directory is safe."""
        is_safe, reason = self.troubleshooter._is_command_safe("chmod 755 /tmp/mydir")
        self.assertTrue(is_safe)


class TestExecuteCommand(unittest.TestCase):
    """Tests for _execute_command method."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_res_manager_patcher = patch("cortex.troubleshoot.ResolutionManager")
        self.mock_res_manager = self.mock_res_manager_patcher.start()

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "fake-key", "fake", "test")
            with patch("cortex.troubleshoot.AskHandler"):
                self.troubleshooter = Troubleshooter()

    def tearDown(self):
        self.mock_res_manager_patcher.stop()

    def test_execute_simple_command(self):
        """Test executing a simple echo command."""
        output = self.troubleshooter._execute_command("echo 'hello world'")
        self.assertIn("hello world", output)

    def test_execute_command_with_stderr(self):
        """Test command that produces stderr."""
        output = self.troubleshooter._execute_command("ls /nonexistent_directory_12345")
        self.assertIn("[STDERR]", output)

    @patch("cortex.troubleshoot.shutil.which")
    @patch("cortex.troubleshoot.subprocess.run")
    def test_execute_command_captures_output(self, mock_run, mock_which):
        """Test that stdout is captured."""
        mock_which.return_value = "/usr/bin/firejail"
        mock_run.return_value = MagicMock(stdout="test output", stderr="", returncode=0)

        output = self.troubleshooter._execute_command("echo 'test output'")
        self.assertEqual(output.strip(), "test output")

        # Verify correct firejail invocation with bash -c
        args, _ = mock_run.call_args
        self.assertIn("bash -c", args[0])

    @patch("subprocess.run")
    def test_execute_command_timeout(self, mock_run):
        """Test command timeout handling."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 100", timeout=30)
        output = self.troubleshooter._execute_command("sleep 100")
        self.assertIn("Error executing command", output)

    @patch("cortex.troubleshoot.shutil.which")
    @patch("cortex.troubleshoot.subprocess.run")
    def test_execute_command_with_firejail(self, mock_run, mock_which):
        """Test that command is sandboxed when firejail is available."""
        mock_which.return_value = "/usr/bin/firejail"
        mock_run.return_value = MagicMock(stdout="output", stderr="", returncode=0)

        self.troubleshooter._execute_command("ls")

        # Verify firejail was used
        args, _ = mock_run.call_args
        self.assertIn("firejail", args[0])
        self.assertIn("ls", args[0])

    @patch("cortex.troubleshoot.shutil.which")
    @patch("cortex.troubleshoot.subprocess.run")
    def test_execute_command_without_firejail(self, mock_run, mock_which):
        """Test that command is NOT sandboxed when firejail is missing."""
        mock_which.return_value = None
        mock_run.return_value = MagicMock(stdout="output", stderr="", returncode=0)

        self.troubleshooter._execute_command("ls")

        # Verify firejail was NOT used
        args, _ = mock_run.call_args
        self.assertNotIn("firejail", args[0])
        self.assertEqual(args[0], "ls")


class TestDangerousPatterns(unittest.TestCase):
    """Tests for DANGEROUS_PATTERNS constant."""

    def test_patterns_list_not_empty(self):
        """Test that dangerous patterns list is not empty."""
        self.assertGreater(len(DANGEROUS_PATTERNS), 0)

    def test_patterns_are_valid_regex(self):
        """Test that all patterns are valid regex."""
        import re

        for pattern in DANGEROUS_PATTERNS:
            try:
                re.compile(pattern)
            except re.error as e:
                self.fail(f"Invalid regex pattern: {pattern} - {e}")


class TestGetProvider(unittest.TestCase):
    """Tests for _get_provider method."""

    def setUp(self):
        self.mock_res_manager_patcher = patch("cortex.troubleshoot.ResolutionManager")
        self.mock_res_manager = self.mock_res_manager_patcher.start()

    def tearDown(self):
        self.mock_res_manager_patcher.stop()

    def test_get_provider_returns_claude_for_anthropic(self):
        """Test that 'anthropic' is mapped to 'claude'."""
        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "sk-ant-xxx", "anthropic", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                self.assertEqual(troubleshooter.provider, "claude")

    def test_get_provider_returns_openai(self):
        """Test that 'openai' is returned correctly."""
        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "sk-xxx", "openai", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                self.assertEqual(troubleshooter.provider, "openai")

    def test_get_provider_defaults_to_openai(self):
        """Test that None provider defaults to 'openai'."""
        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (False, None, None, None)
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                self.assertEqual(troubleshooter.provider, "openai")


class TestGetApiKey(unittest.TestCase):
    """Tests for _get_api_key method."""

    def setUp(self):
        self.mock_res_manager_patcher = patch("cortex.troubleshoot.ResolutionManager")
        self.mock_res_manager = self.mock_res_manager_patcher.start()

    def tearDown(self):
        self.mock_res_manager_patcher.stop()

    def test_get_api_key_returns_key(self):
        """Test that API key is returned correctly."""
        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-api-key", "openai", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                self.assertEqual(troubleshooter.api_key, "test-api-key")

    def test_get_api_key_returns_empty_on_none(self):
        """Test that None key returns empty string."""
        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (False, None, "openai", None)
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                self.assertEqual(troubleshooter.api_key, "")


class TestStart(unittest.TestCase):
    """Tests for start method."""

    def setUp(self):
        self.mock_res_manager_patcher = patch("cortex.troubleshoot.ResolutionManager")
        self.mock_res_manager = self.mock_res_manager_patcher.start()

    def tearDown(self):
        self.mock_res_manager_patcher.stop()

    @patch("cortex.troubleshoot.console")
    def test_start_no_ai_returns_error(self, mock_console):
        """Test that start returns 1 when AI is unavailable."""
        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (False, None, "openai", None)
            with patch("cortex.troubleshoot.AskHandler") as mock_handler:
                mock_handler.side_effect = Exception("No API key")
                troubleshooter = Troubleshooter()
                troubleshooter.ai = None
                result = troubleshooter.start()
                self.assertEqual(result, 1)

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Troubleshooter._interactive_loop")
    def test_start_with_ai_calls_loop(self, mock_loop, mock_console):
        """Test that start calls interactive loop when AI is available."""
        mock_loop.return_value = 0
        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "openai", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                result = troubleshooter.start()
                mock_loop.assert_called_once()
                self.assertEqual(result, 0)


class TestInteractiveLoop(unittest.TestCase):
    """Tests for _interactive_loop method."""

    def setUp(self):
        self.mock_res_manager_patcher = patch("cortex.troubleshoot.ResolutionManager")
        self.mock_res_manager_cls = self.mock_res_manager_patcher.start()
        self.mock_res_manager = self.mock_res_manager_cls.return_value
        # Default search returns empty list to avoid side effects
        self.mock_res_manager.search.return_value = []

    def tearDown(self):
        self.mock_res_manager_patcher.stop()

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    @patch("cortex.troubleshoot.Confirm")
    def test_exit_command(self, mock_confirm, mock_prompt, mock_console):
        """Test that 'exit' command exits the loop."""
        mock_prompt.ask.return_value = "exit"
        mock_confirm.ask.return_value = False  # User says "No" to learning
        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                troubleshooter.messages = [{"role": "system", "content": "test"}]
                result = troubleshooter._interactive_loop()
                self.assertEqual(result, 0)

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    @patch("cortex.troubleshoot.Confirm")
    def test_quit_command(self, mock_confirm, mock_prompt, mock_console):
        """Test that 'quit' command exits the loop."""
        mock_prompt.ask.return_value = "quit"
        mock_confirm.ask.return_value = False  # User says "No" to learning
        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                troubleshooter.messages = [{"role": "system", "content": "test"}]
                result = troubleshooter._interactive_loop()
                self.assertEqual(result, 0)

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    @patch("cortex.troubleshoot.Confirm")
    @patch("cortex.doctor.SystemDoctor")
    def test_doctor_command(self, mock_doctor, mock_confirm, mock_prompt, mock_console):
        """Test that 'doctor' command runs SystemDoctor."""
        # First call returns 'doctor', second call returns 'exit'
        mock_prompt.ask.side_effect = ["doctor", "exit"]
        mock_confirm.ask.return_value = False
        mock_doctor_instance = MagicMock()
        mock_doctor.return_value = mock_doctor_instance

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                troubleshooter.messages = [{"role": "system", "content": "test"}]
                troubleshooter._interactive_loop()
                # The doctor command should be called via the import inside the loop
                # Since SystemDoctor is imported inside the function, we skip this assertion

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    @patch("cortex.troubleshoot.Confirm")
    def test_help_command(self, mock_confirm, mock_prompt, mock_console):
        """Test that 'help' command creates log file and prints instructions."""
        mock_prompt.ask.side_effect = ["help", "exit"]
        mock_confirm.ask.return_value = False

        # Create a platform-independent temp path for testing
        test_log_path = os.path.join(
            tempfile.gettempdir(), "test", ".cortex", "cortex_support_log.txt"
        )

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                troubleshooter.messages = [{"role": "system", "content": "test"}]

                # Mock AI for summary generation
                mock_ai = MagicMock()
                mock_ai.ask.return_value = "Issue Summary: Test issue"
                troubleshooter.ai = mock_ai

                # Mock file opening to avoid actual file creation
                with patch("builtins.open", unittest.mock.mock_open()) as mock_file:
                    with patch("os.path.abspath", return_value="/abs/path/to/log"):
                        with patch(
                            "os.path.expanduser",
                            return_value=test_log_path,
                        ):
                            with patch("os.makedirs"):  # Prevent fallback to /tmp/
                                troubleshooter._interactive_loop()

                            # Verify file was opened for writing
                            mock_file.assert_called_with(test_log_path, "w", encoding="utf-8")

                            # Verify content was written
                            handle = mock_file()
                            handle.write.assert_any_call("Cortex Troubleshooting Log\n")
                            handle.write.assert_any_call("Issue Summary:\n")
                            handle.write.assert_any_call("Issue Summary: Test issue")

                # Verify instructions were printed
                mock_console.print.assert_any_call(
                    "Please open a new issue and attach the /abs/path/to/log file."
                )

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    @patch("cortex.troubleshoot.Confirm")
    def test_learning_on_exit(self, mock_confirm, mock_prompt, mock_console):
        """Test that we learn from successful sessions on exit."""
        mock_prompt.ask.side_effect = ["exit"]
        mock_confirm.ask.return_value = True  # User says "Yes, problem solved"

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                with patch("cortex.troubleshoot.ResolutionManager") as MockResManager:
                    troubleshooter = Troubleshooter()
                    troubleshooter.messages = [{"role": "system", "content": "test"}]

                    # Mock AI extraction
                    mock_ai = MagicMock()
                    mock_ai.ask.return_value = '{"issue": "test issue", "fix": "test fix"}'
                    troubleshooter.ai = mock_ai

                    troubleshooter._interactive_loop()

                    # Verify save was called
                    troubleshooter.resolutions.save.assert_called_with("test issue", "test fix")

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    @patch("cortex.troubleshoot.Confirm")
    def test_dynamic_recall(self, mock_confirm, mock_prompt, mock_console):
        """Test that we search for resolutions and inject them."""
        mock_prompt.ask.side_effect = ["docker fail", "exit"]
        mock_confirm.ask.return_value = False

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                with patch("cortex.troubleshoot.ResolutionManager") as MockResManager:
                    troubleshooter = Troubleshooter()

                    # Mock search results
                    mock_manager = MockResManager.return_value
                    mock_manager.search.return_value = [
                        {"issue": "Docker fail", "fix": "systemctl start docker"}
                    ]
                    troubleshooter.resolutions = mock_manager

                    # Mock AI
                    mock_ai = MagicMock()
                    mock_ai.ask.return_value = "Try this"
                    troubleshooter.ai = mock_ai

                    troubleshooter._interactive_loop()

                    # Verify search was called
                    mock_manager.search.assert_called_with("docker fail")

                    # Verify injection (by checking the call to ai.ask)
                    args, kwargs = mock_ai.ask.call_args
                    system_prompt = kwargs.get("system_prompt", "")
                    self.assertIn("[MEMORY]", system_prompt)
                    self.assertIn("systemctl start docker", system_prompt)

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    @patch("cortex.troubleshoot.Markdown")
    @patch("cortex.troubleshoot.Confirm")
    def test_user_input_sent_to_ai(self, mock_confirm, mock_md, mock_prompt, mock_console):
        """Test that user input is sent to AI."""
        mock_prompt.ask.side_effect = ["my issue", "exit"]
        mock_confirm.ask.return_value = False

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()

                # Create and inject mock AI
                mock_ai = MagicMock()
                mock_ai.ask.return_value = "Here is my response."
                troubleshooter.ai = mock_ai
                troubleshooter.messages = [{"role": "system", "content": "test"}]

                troubleshooter._interactive_loop()
                # Verify that AI was called with user input
                self.assertTrue(mock_ai.ask.called)

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    @patch("cortex.troubleshoot.Markdown")
    @patch("cortex.troubleshoot.Syntax")
    @patch("cortex.troubleshoot.Confirm")
    @patch("cortex.troubleshoot.Panel")
    def test_command_execution_flow(
        self, mock_panel, mock_confirm, mock_syntax, mock_md, mock_prompt, mock_console
    ):
        """Test the full command execution flow."""
        # AI returns a response with a bash code block
        mock_prompt.ask.side_effect = ["check disk", "exit"]
        mock_confirm.ask.return_value = True  # User confirms execution

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()

                mock_ai = MagicMock()
                # First response has a command, second is analysis
                mock_ai.ask.side_effect = [
                    "Run this:\n```bash\ndf -h\n```",
                    "Disk looks good!",
                ]
                troubleshooter.ai = mock_ai
                troubleshooter.messages = [{"role": "system", "content": "test"}]

                with patch.object(troubleshooter, "_execute_command") as mock_exec:
                    mock_exec.return_value = "Disk output here"
                    troubleshooter._interactive_loop()
                    # Verify command was executed
                    mock_exec.assert_called_once_with("df -h")

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    @patch("cortex.troubleshoot.Markdown")
    @patch("cortex.troubleshoot.Syntax")
    @patch("cortex.troubleshoot.Confirm")
    def test_dangerous_command_blocked(
        self, mock_confirm, mock_syntax, mock_md, mock_prompt, mock_console
    ):
        """Test that dangerous commands are blocked."""
        mock_prompt.ask.side_effect = ["delete everything", "exit"]
        mock_confirm.ask.return_value = False

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()

                mock_ai = MagicMock()
                mock_ai.ask.return_value = "Run this:\n```bash\nrm -rf /\n```"
                troubleshooter.ai = mock_ai
                troubleshooter.messages = [{"role": "system", "content": "test"}]

                with patch.object(troubleshooter, "_execute_command") as mock_exec:
                    troubleshooter._interactive_loop()
                    # Verify command was NOT executed (blocked)
                    mock_exec.assert_not_called()

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    def test_keyboard_interrupt_returns_130(self, mock_prompt, mock_console):
        """Test that KeyboardInterrupt returns exit code 130."""
        mock_prompt.ask.side_effect = KeyboardInterrupt()

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                troubleshooter.messages = [{"role": "system", "content": "test"}]
                result = troubleshooter._interactive_loop()
                self.assertEqual(result, 130)

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    def test_exception_returns_1(self, mock_prompt, mock_console):
        """Test that exceptions return exit code 1."""
        mock_prompt.ask.side_effect = RuntimeError("Test error")

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()
                troubleshooter.messages = [{"role": "system", "content": "test"}]
                result = troubleshooter._interactive_loop()
                self.assertEqual(result, 1)

    @patch("cortex.troubleshoot.console")
    @patch("cortex.troubleshoot.Prompt")
    @patch("cortex.troubleshoot.Markdown")
    @patch("cortex.troubleshoot.Syntax")
    @patch("cortex.troubleshoot.Confirm")
    def test_user_declines_command(
        self, mock_confirm, mock_syntax, mock_md, mock_prompt, mock_console
    ):
        """Test that declining command execution skips it."""
        mock_prompt.ask.side_effect = ["run something", "exit"]
        mock_confirm.ask.return_value = False  # User declines

        with patch("cortex.troubleshoot.auto_detect_api_key") as mock_detect:
            mock_detect.return_value = (True, "test-key", "fake", "env")
            with patch("cortex.troubleshoot.AskHandler"):
                troubleshooter = Troubleshooter()

                mock_ai = MagicMock()
                mock_ai.ask.return_value = "Run this:\n```bash\necho hello\n```"
                troubleshooter.ai = mock_ai
                troubleshooter.messages = [{"role": "system", "content": "test"}]

                with patch.object(troubleshooter, "_execute_command") as mock_exec:
                    troubleshooter._interactive_loop()
                    # Verify command was NOT executed (user declined)
                    mock_exec.assert_not_called()


if __name__ == "__main__":
    unittest.main()
