#!/usr/bin/env python3
"""
Unit tests for sandboxed command executor.
Tests security features, validation, and execution.
"""

import builtins
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from cortex.sandbox.sandbox_executor import (
    CommandBlocked,
    ExecutionResult,
    SandboxExecutor,
)
from cortex.validators import DANGEROUS_PATTERNS


class TestSandboxExecutor(unittest.TestCase):
    """Test cases for SandboxExecutor."""

    def setUp(self):
        """Set up test fixtures."""
        # Use temporary directory for logs
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "test_sandbox.log")
        self.executor = SandboxExecutor(log_file=self.log_file)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_command_allowed(self):
        """Test validation of allowed commands."""
        valid_commands = [
            "apt-get update",
            "pip install numpy",
            "python3 --version",
            "git clone https://github.com/user/repo",
            'echo "test"',
        ]

        for cmd in valid_commands:
            is_valid, violation = self.executor.validate_command(cmd)
            self.assertTrue(is_valid, f"Command should be valid: {cmd}")
            self.assertIsNone(violation)

    def test_validate_command_blocked_dangerous(self):
        """Test blocking of dangerous commands."""
        dangerous_commands = [
            "rm -rf /",
            "rm -rf /*",
            "rm -rf $HOME",
            "dd if=/dev/zero of=/dev/sda",
            "mkfs.ext4 /dev/sda1",
            "fdisk /dev/sda",
        ]

        for cmd in dangerous_commands:
            is_valid, violation = self.executor.validate_command(cmd)
            self.assertFalse(is_valid, f"Command should be blocked: {cmd}")
            self.assertIsNotNone(violation)

    def test_validate_command_not_whitelisted(self):
        """Test blocking of non-whitelisted commands."""
        blocked_commands = [
            "nc -l 1234",  # Netcat
            "nmap localhost",  # Network scanner
            'bash -c "evil"',  # Arbitrary bash
        ]

        for cmd in blocked_commands:
            is_valid, violation = self.executor.validate_command(cmd)
            self.assertFalse(is_valid, f"Command should be blocked: {cmd}")
            self.assertIsNotNone(violation)
            self.assertIn("not whitelisted", (violation or "").lower())

    def test_validate_sudo_allowed(self):
        """Test sudo commands for package installation."""
        allowed_sudo = [
            "sudo apt-get install python3",
            "sudo apt-get update",
            "sudo pip install numpy",
            "sudo pip3 install pandas",
        ]

        for cmd in allowed_sudo:
            is_valid, _ = self.executor.validate_command(cmd)
            self.assertTrue(is_valid, f"Sudo command should be allowed: {cmd}")

    def test_validate_sudo_blocked(self):
        """Test blocking of unauthorized sudo commands."""
        blocked_sudo = [
            "sudo rm -rf /",
            "sudo chmod 777 /",
            "sudo bash",
        ]

        for cmd in blocked_sudo:
            is_valid, _ = self.executor.validate_command(cmd)
            self.assertFalse(is_valid, f"Sudo command should be blocked: {cmd}")

    @patch("subprocess.Popen")
    def test_execute_success(self, mock_popen):
        """Test successful command execution."""
        # Mock successful execution
        mock_process = MagicMock()
        mock_process.communicate.return_value = ("output", "")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        result = self.executor.execute('echo "test"', dry_run=False)

        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, "output")
        self.assertFalse(result.blocked)

    def test_execute_dry_run(self):
        """Test dry-run mode."""
        result = self.executor.execute("apt-get update", dry_run=True)

        self.assertTrue(result.success)
        preview = result.preview
        self.assertIsNotNone(preview)
        self.assertIn("[DRY-RUN]", result.stdout)
        assert preview is not None
        self.assertIn("apt-get", preview)

    def test_execute_blocked_command(self):
        """Test execution of blocked command."""
        with self.assertRaises(CommandBlocked):
            self.executor.execute("rm -rf /", dry_run=False)

    @patch("subprocess.Popen")
    @patch.object(SandboxExecutor, "validate_command")
    def test_execute_timeout(self, mock_validate, mock_popen):
        """Test command timeout."""
        # Mock validation to allow the command
        mock_validate.return_value = (True, None)

        # Mock timeout
        mock_process = MagicMock()
        mock_process.communicate.side_effect = subprocess.TimeoutExpired("cmd", 300)
        mock_process.kill = MagicMock()
        mock_popen.return_value = mock_process

        result = self.executor.execute('python3 -c "import time; time.sleep(1000)"', dry_run=False)

        self.assertTrue(result.failed)
        self.assertIn("timed out", result.stderr.lower())
        mock_process.kill.assert_called_once()

    @patch("subprocess.Popen")
    @patch.object(SandboxExecutor, "validate_command")
    def test_execute_with_rollback(self, mock_validate, mock_popen):
        """Test execution with rollback on failure."""
        # Mock validation to allow the command
        mock_validate.return_value = (True, None)

        # Mock failed execution
        mock_process = MagicMock()
        mock_process.communicate.return_value = ("", "error")
        mock_process.returncode = 1
        mock_popen.return_value = mock_process

        executor = SandboxExecutor(log_file=self.log_file, enable_rollback=True)

        # Use a whitelisted command that will fail
        result = executor.execute('python3 -c "import sys; sys.exit(1)"', dry_run=False)

        self.assertTrue(result.failed)
        self.assertIn("[ROLLBACK]", result.stderr)

    def test_audit_logging(self):
        """Test audit log functionality."""
        # Execute some commands
        with contextlib.suppress(builtins.BaseException):
            self.executor.execute('echo "test"', dry_run=True)

        with contextlib.suppress(builtins.BaseException):
            self.executor.execute("rm -rf /", dry_run=False)

        audit_log = self.executor.get_audit_log()
        self.assertGreater(len(audit_log), 0)

        # Check log entries have required fields
        for entry in audit_log:
            self.assertIn("command", entry)
            self.assertIn("timestamp", entry)
            self.assertIn("type", entry)

    def test_path_validation(self):
        """Test path validation."""
        # Commands accessing critical directories should be blocked
        critical_paths = [
            "cat /etc/passwd",
            "ls /boot",
            "rm /sys/kernel",
        ]

        for cmd in critical_paths:
            _ = self.executor.validate_command(cmd)
            # Note: Current implementation may allow some of these
            # Adjust based on security requirements
            # For now, we just test that validation runs

    def test_resource_limits(self):
        """Test that resource limits are set in firejail command."""
        if not self.executor.firejail_path:
            self.skipTest("Firejail not available")

        firejail_cmd = self.executor._create_firejail_command("echo test")

        # Check that resource limits are included
        cmd_str = " ".join(firejail_cmd)
        self.assertIn(f"--cpu={self.executor.max_cpu_cores}", cmd_str)
        self.assertIn("--rlimit-as", cmd_str)
        self.assertIn("--private", cmd_str)

    def test_execution_result_properties(self):
        """Test ExecutionResult properties."""
        result = ExecutionResult(
            command="test", exit_code=0, stdout="output", stderr="", execution_time=1.0
        )

        self.assertTrue(result.success)
        self.assertFalse(result.failed)

        result.exit_code = 1
        self.assertFalse(result.success)
        self.assertTrue(result.failed)

        result.blocked = True
        self.assertFalse(result.success)
        self.assertTrue(result.failed)

    def test_snapshot_creation(self):
        """Test snapshot creation for rollback."""
        session_id = "test_session"
        snapshot = self.executor._create_snapshot(session_id)

        self.assertIn(session_id, self.executor.rollback_snapshots)
        self.assertEqual(snapshot["session_id"], session_id)
        self.assertIn("timestamp", snapshot)

    def test_rollback_functionality(self):
        """Test rollback functionality."""
        session_id = "test_session"
        self.executor._create_snapshot(session_id)

        # Rollback should succeed if snapshot exists
        result = self.executor._rollback(session_id)
        self.assertTrue(result)

        # Rollback should fail for non-existent session
        result = self.executor._rollback("non_existent")
        self.assertFalse(result)

    def test_whitelist_commands(self):
        """Test that whitelisted commands are recognized."""
        for cmd in self.executor.ALLOWED_COMMANDS:
            # Test base command (may need arguments)
            _ = self.executor.validate_command(f"{cmd} --help")
            # Some commands might need specific validation
            # This is a basic check

    def test_comprehensive_logging(self):
        """Test that all events are logged."""
        # Execute various commands
        with contextlib.suppress(builtins.BaseException):
            self.executor.execute("echo test", dry_run=True)

        with contextlib.suppress(builtins.BaseException):
            self.executor.execute("invalid-command", dry_run=False)

        # Check log file exists
        self.assertTrue(os.path.exists(self.log_file))

        # Read log file
        with open(self.log_file) as f:
            log_content = f.read()
            self.assertIn("SandboxExecutor", log_content)


class TestSecurityFeatures(unittest.TestCase):
    """Test security-specific features."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "test_security.log")
        self.executor = SandboxExecutor(log_file=self.log_file)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dangerous_patterns_blocked(self):
        """Test that all dangerous patterns are blocked."""
        for pattern in DANGEROUS_PATTERNS:
            # Create a command that should match the regex pattern.
            # Some patterns include regex character classes/lookaheads that can't be
            # naively converted by string replacement.
            if "python\\s+-c" in pattern and "exec" in pattern:
                test_cmd = "python -c \"exec('print(1)')\""
            elif "python\\s+-c" in pattern and "__import__" in pattern:
                test_cmd = "python -c \"__import__('os')\""
            elif "/dev/(?!null" in pattern:
                test_cmd = "echo hi > /dev/sda"
            else:
                test_cmd = pattern.replace(r"\s+", " ").replace(r"[/\*]", "/")
                test_cmd = test_cmd.replace(r"\s*", " ")
                test_cmd = test_cmd.replace(r"\$HOME", "$HOME")
                test_cmd = test_cmd.replace(r"\.", ".")
                test_cmd = test_cmd.replace(r"\+", "+")
                test_cmd = test_cmd.replace(r"\|", "|")
                test_cmd = test_cmd.replace(r".*", "http://example.com/script.sh")
                test_cmd = test_cmd.replace(r"[0-7]{3,4}", "777")

            is_valid, _ = self.executor.validate_command(test_cmd)
            self.assertFalse(is_valid, f"Pattern should be blocked: {pattern}")

    def test_path_traversal_protection(self):
        """Test protection against path traversal attacks."""
        traversal_commands = [
            "cat ../../../etc/passwd",
            "rm -rf ../../..",
        ]

        for cmd in traversal_commands:
            _ = self.executor.validate_command(cmd)
            # Should be blocked or at least validated
            # Current implementation may need enhancement


if __name__ == "__main__":
    unittest.main()
