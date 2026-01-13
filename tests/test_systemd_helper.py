"""
Unit tests for cortex/systemd_helper.py - Systemd Service Helper.
Tests the SystemdHelper class used by 'cortex systemd' commands.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from cortex.systemd_helper import (
    JOURNALCTL_TIMEOUT,
    SERVICE_NAME_PATTERN,
    SYSTEMCTL_TIMEOUT,
    ServiceState,
    ServiceStatus,
    SystemdHelper,
    _validate_service_name,
    run_deps_command,
    run_diagnose_command,
    run_generate_command,
    run_status_command,
)


class TestServiceStateEnum:
    """Test the ServiceState enum values."""

    def test_all_states_exist(self):
        assert ServiceState.RUNNING.value == "running"
        assert ServiceState.STOPPED.value == "stopped"
        assert ServiceState.FAILED.value == "failed"
        assert ServiceState.INACTIVE.value == "inactive"
        assert ServiceState.ACTIVATING.value == "activating"
        assert ServiceState.DEACTIVATING.value == "deactivating"
        assert ServiceState.UNKNOWN.value == "unknown"


class TestServiceStatusDataclass:
    """Test the ServiceStatus dataclass."""

    def test_basic_creation(self):
        status = ServiceStatus(name="nginx", state=ServiceState.RUNNING)
        assert status.name == "nginx"
        assert status.state == ServiceState.RUNNING
        assert status.description == ""
        assert status.pid is None
        assert status.exit_code is None

    def test_full_creation(self):
        status = ServiceStatus(
            name="nginx",
            state=ServiceState.RUNNING,
            description="A high performance web server",
            load_state="loaded",
            active_state="active",
            sub_state="running",
            pid=1234,
            memory="50M",
            cpu="100ns",
            started_at="2024-01-01 12:00:00",
            exit_code=0,
            main_pid_code="exited",
        )
        assert status.pid == 1234
        assert status.memory == "50M"
        assert status.started_at == "2024-01-01 12:00:00"


class TestValidateServiceName:
    """Test service name validation."""

    def test_valid_simple_name(self):
        assert _validate_service_name("nginx") == "nginx.service"

    def test_valid_with_suffix(self):
        assert _validate_service_name("nginx.service") == "nginx.service"

    def test_valid_with_hyphen(self):
        assert _validate_service_name("my-service") == "my-service.service"

    def test_valid_with_underscore(self):
        assert _validate_service_name("my_service") == "my_service.service"

    def test_valid_with_dots(self):
        assert _validate_service_name("my.service.name") == "my.service.name.service"

    def test_valid_with_at_sign(self):
        # Instantiated services like getty@tty1
        assert _validate_service_name("getty@tty1") == "getty@tty1.service"

    def test_valid_with_numbers(self):
        assert _validate_service_name("service123") == "service123.service"

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            _validate_service_name("")

    def test_invalid_shell_chars(self):
        with pytest.raises(ValueError, match="Invalid service name"):
            _validate_service_name("nginx; rm -rf /")

    def test_invalid_path_separator(self):
        with pytest.raises(ValueError, match="Invalid service name"):
            _validate_service_name("../../etc/passwd")

    def test_invalid_dollar_sign(self):
        with pytest.raises(ValueError, match="Invalid service name"):
            _validate_service_name("$HOME/service")

    def test_invalid_backtick(self):
        with pytest.raises(ValueError, match="Invalid service name"):
            _validate_service_name("`whoami`")


class TestServiceNamePattern:
    """Test the SERVICE_NAME_PATTERN regex."""

    def test_valid_patterns(self):
        valid_names = [
            "nginx",
            "my-service",
            "my_service",
            "service123",
            "My.Service",
            "getty@tty1",
            "user-1000",
            "a",
            "ABC123",
        ]
        for name in valid_names:
            assert SERVICE_NAME_PATTERN.match(name), f"{name} should be valid"

    def test_invalid_patterns(self):
        invalid_names = [
            "",
            " nginx",
            "nginx ",
            "nginx;rm",
            "../test",
            "$HOME",
            "`cmd`",
            "service\nname",
            "service\tname",
        ]
        for name in invalid_names:
            # Empty string doesn't match, others shouldn't match the full pattern
            if name:
                match = SERVICE_NAME_PATTERN.match(name)
                # Should either not match or not match the full string
                assert match is None or match.group() != name, f"{name!r} should be invalid"


class TestSystemdHelperInit:
    """Test SystemdHelper initialization."""

    def test_init_success(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            helper = SystemdHelper()
            assert helper is not None

    def test_init_systemd_not_available(self):
        mock_result = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="systemd is not available"):
                SystemdHelper()

    def test_init_systemctl_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="systemctl command not found"):
                SystemdHelper()

    def test_init_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            with pytest.raises(RuntimeError, match="Timeout"):
                SystemdHelper()


class TestGetServiceStatus:
    """Test get_service_status method."""

    def _create_helper(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            return SystemdHelper()

    def test_get_status_running(self):
        helper = self._create_helper()
        mock_output = """ActiveState=active
SubState=running
Description=The NGINX HTTP Server
MainPID=1234
LoadState=loaded
MemoryCurrent=52428800
"""
        mock_result = MagicMock(returncode=0, stdout=mock_output)
        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("nginx")

        assert status.name == "nginx"
        assert status.state == ServiceState.RUNNING
        assert status.pid == 1234
        assert status.description == "The NGINX HTTP Server"

    def test_get_status_failed(self):
        helper = self._create_helper()
        mock_output = """ActiveState=failed
SubState=failed
ExecMainStatus=1
"""
        mock_result = MagicMock(returncode=0, stdout=mock_output)
        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("nginx")

        assert status.state == ServiceState.FAILED
        assert status.exit_code == 1

    def test_get_status_inactive(self):
        helper = self._create_helper()
        mock_output = """ActiveState=inactive
SubState=dead
"""
        mock_result = MagicMock(returncode=0, stdout=mock_output)
        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("nginx")

        assert status.state == ServiceState.INACTIVE

    def test_get_status_activating(self):
        helper = self._create_helper()
        mock_output = """ActiveState=activating
SubState=start
"""
        mock_result = MagicMock(returncode=0, stdout=mock_output)
        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("nginx")

        assert status.state == ServiceState.ACTIVATING

    def test_get_status_deactivating(self):
        helper = self._create_helper()
        mock_output = """ActiveState=deactivating
SubState=stop-sigterm
"""
        mock_result = MagicMock(returncode=0, stdout=mock_output)
        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("nginx")

        assert status.state == ServiceState.DEACTIVATING

    def test_get_status_invalid_service_name(self):
        helper = self._create_helper()
        with pytest.raises(ValueError, match="Invalid service name"):
            helper.get_service_status("nginx; rm -rf /")

    def test_get_status_command_fails(self):
        helper = self._create_helper()
        mock_result = MagicMock(returncode=1, stderr="Unit not found")
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="Failed to get service status"):
                helper.get_service_status("nginx")

    def test_get_status_filenotfound(self):
        helper = self._create_helper()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="systemctl command not found"):
                helper.get_service_status("nginx")

    def test_get_status_timeout(self):
        helper = self._create_helper()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 10)):
            with pytest.raises(RuntimeError, match="Timeout"):
                helper.get_service_status("nginx")


class TestExplainStatus:
    """Test explain_status method."""

    def _create_helper(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            return SystemdHelper()

    def test_explain_running(self):
        helper = self._create_helper()
        mock_output = """ActiveState=active
SubState=running
Description=Web Server
MainPID=1234
ActiveEnterTimestamp=Mon 2024-01-01 12:00:00 UTC
"""
        mock_result = MagicMock(returncode=0, stdout=mock_output)
        with patch("subprocess.run", return_value=mock_result):
            explanation = helper.explain_status("nginx")

        assert "running normally" in explanation
        assert "1234" in explanation

    def test_explain_failed(self):
        helper = self._create_helper()
        mock_output = """ActiveState=failed
SubState=failed
ExecMainStatus=137
"""
        mock_result = MagicMock(returncode=0, stdout=mock_output)
        with patch("subprocess.run", return_value=mock_result):
            explanation = helper.explain_status("nginx")

        assert "failed" in explanation
        assert "137" in explanation
        assert "SIGKILL" in explanation or "killed" in explanation.lower()

    def test_explain_inactive(self):
        helper = self._create_helper()
        mock_output = """ActiveState=inactive
SubState=dead
"""
        mock_result = MagicMock(returncode=0, stdout=mock_output)
        with patch("subprocess.run", return_value=mock_result):
            explanation = helper.explain_status("nginx")

        assert "not running" in explanation or "inactive" in explanation


class TestExplainExitCode:
    """Test _explain_exit_code method."""

    def _create_helper(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            return SystemdHelper()

    def test_common_codes(self):
        helper = self._create_helper()

        # Test specific exit codes
        assert "General error" in helper._explain_exit_code(1)
        assert (
            "Misuse" in helper._explain_exit_code(2)
            or "invalid" in helper._explain_exit_code(2).lower()
        )
        assert (
            "not executable" in helper._explain_exit_code(126)
            or "permission" in helper._explain_exit_code(126).lower()
        )
        assert "not found" in helper._explain_exit_code(127)
        assert (
            "SIGKILL" in helper._explain_exit_code(137)
            or "killed" in helper._explain_exit_code(137).lower()
        )
        assert "Segmentation" in helper._explain_exit_code(
            139
        ) or "SIGSEGV" in helper._explain_exit_code(139)
        assert (
            "SIGTERM" in helper._explain_exit_code(143)
            or "terminated" in helper._explain_exit_code(143).lower()
        )

    def test_signal_calculation(self):
        helper = self._create_helper()
        # Exit codes > 128 are signal codes (128 + signal number)
        explanation = helper._explain_exit_code(129)  # 128 + 1 = SIGHUP
        assert "signal" in explanation.lower()

    def test_unknown_code(self):
        helper = self._create_helper()
        explanation = helper._explain_exit_code(42)
        assert "42" in explanation


class TestDiagnoseFailure:
    """Test diagnose_failure method."""

    def _create_helper(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            return SystemdHelper()

    def test_diagnose_with_permission_error(self):
        helper = self._create_helper()

        # First call: systemctl show
        status_output = """ActiveState=failed
SubState=failed
ExecMainStatus=1
"""
        # Second call: journalctl
        log_output = (
            "Jan 01 12:00:00 server myapp[1234]: Error: permission denied opening /var/log/app.log"
        )

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "show" in cmd:
                result.stdout = status_output
            else:
                result.stdout = log_output
            return result

        with patch("subprocess.run", side_effect=mock_run):
            report = helper.diagnose_failure("myapp")

        assert "Permission issue" in report

    def test_diagnose_with_port_conflict(self):
        helper = self._create_helper()

        status_output = "ActiveState=failed\nSubState=failed\n"
        log_output = "Error: address already in use :8080"

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "show" in cmd:
                result.stdout = status_output
            else:
                result.stdout = log_output
            return result

        with patch("subprocess.run", side_effect=mock_run):
            report = helper.diagnose_failure("myapp")

        assert "Port conflict" in report

    def test_diagnose_lines_validation(self):
        helper = self._create_helper()

        status_output = "ActiveState=active\nSubState=running\n"
        log_output = ""

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "show" in cmd:
                result.stdout = status_output
            else:
                result.stdout = log_output
                # Verify lines parameter is clamped
                if "-n" in cmd:
                    idx = cmd.index("-n")
                    lines_val = int(cmd[idx + 1])
                    assert 1 <= lines_val <= 1000
            return result

        with patch("subprocess.run", side_effect=mock_run):
            # Test negative value gets clamped to 1
            helper.diagnose_failure("myapp", lines=-10)
            # Test huge value gets clamped to 1000
            helper.diagnose_failure("myapp", lines=999999)

    def test_diagnose_journalctl_not_found(self):
        helper = self._create_helper()

        status_output = "ActiveState=failed\nSubState=failed\n"

        def mock_run(cmd, *args, **kwargs):
            if "journalctl" in cmd:
                raise FileNotFoundError()
            result = MagicMock()
            result.returncode = 0
            result.stdout = status_output
            return result

        with patch("subprocess.run", side_effect=mock_run):
            report = helper.diagnose_failure("myapp")

        assert "journalctl command not found" in report

    def test_diagnose_journalctl_timeout(self):
        helper = self._create_helper()

        status_output = "ActiveState=failed\nSubState=failed\n"

        def mock_run(cmd, *args, **kwargs):
            if "journalctl" in cmd:
                raise subprocess.TimeoutExpired("journalctl", 30)
            result = MagicMock()
            result.returncode = 0
            result.stdout = status_output
            return result

        with patch("subprocess.run", side_effect=mock_run):
            report = helper.diagnose_failure("myapp")

        assert "Timeout" in report


class TestShowDependencies:
    """Test show_dependencies method."""

    def _create_helper(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            return SystemdHelper()

    def test_show_deps_success(self):
        helper = self._create_helper()

        # First call: init check, Second call: dependencies
        deps_output = """nginx.service
├─system.slice
│ └─-.slice
└─network.target
  └─network-pre.target
"""
        mock_result = MagicMock(returncode=0, stdout=deps_output)
        with patch("subprocess.run", return_value=mock_result):
            tree = helper.show_dependencies("nginx")

        # Tree should exist
        assert tree is not None

    def test_show_deps_invalid_service_name(self):
        helper = self._create_helper()
        with pytest.raises(ValueError, match="Invalid service name"):
            helper.show_dependencies("nginx; rm -rf /")

    def test_show_deps_filenotfound(self):
        helper = self._create_helper()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            tree = helper.show_dependencies("nginx")
        # Should return a tree with error message
        assert tree is not None

    def test_show_deps_timeout(self):
        helper = self._create_helper()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 10)):
            tree = helper.show_dependencies("nginx")
        # Should return a tree with timeout message
        assert tree is not None


class TestGenerateUnitFile:
    """Test generate_unit_file method."""

    def _create_helper(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            return SystemdHelper()

    def test_generate_basic(self):
        helper = self._create_helper()
        unit = helper.generate_unit_file(
            description="My Test Service",
            exec_start="/usr/bin/myapp",
        )

        assert "[Unit]" in unit
        assert "Description=My Test Service" in unit
        assert "[Service]" in unit
        assert "ExecStart=/usr/bin/myapp" in unit
        assert "[Install]" in unit
        assert "WantedBy=multi-user.target" in unit

    def test_generate_with_user(self):
        helper = self._create_helper()
        unit = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            user="nobody",
        )

        assert "User=nobody" in unit

    def test_generate_with_working_dir(self):
        helper = self._create_helper()
        unit = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            working_dir="/var/lib/myapp",
        )

        assert "WorkingDirectory=/var/lib/myapp" in unit

    def test_generate_with_restart(self):
        helper = self._create_helper()
        unit = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            restart=True,
        )

        assert "Restart=on-failure" in unit
        assert "RestartSec=5" in unit

    def test_generate_without_restart(self):
        helper = self._create_helper()
        unit = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            restart=False,
        )

        assert "Restart=" not in unit

    def test_generate_with_after(self):
        helper = self._create_helper()
        unit = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            after=["postgresql.service", "redis.service"],
        )

        assert "After=postgresql.service redis.service" in unit

    def test_generate_with_simple_environment(self):
        helper = self._create_helper()
        unit = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            environment={"FOO": "bar", "DEBUG": "true"},
        )

        assert "Environment=FOO=bar" in unit
        assert "Environment=DEBUG=true" in unit

    def test_generate_with_escaped_environment(self):
        helper = self._create_helper()
        unit = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            environment={
                "PATH_WITH_SPACE": "/some path/with spaces",
                "DOLLAR_VAR": "$HOME/test",
                "BACKTICK_VAR": "`whoami`",
                "QUOTE_VAR": 'say "hello"',
                "NEWLINE_VAR": "line1\nline2",
                "BACKSLASH_VAR": "C:\\Windows\\Path",
            },
        )

        # Check proper escaping
        assert 'Environment=PATH_WITH_SPACE="/some path/with spaces"' in unit
        assert r'Environment=DOLLAR_VAR="\$HOME/test"' in unit
        assert r'Environment=BACKTICK_VAR="\`whoami\`"' in unit
        assert r'Environment=QUOTE_VAR="say \"hello\""' in unit
        # Newlines should be replaced with spaces
        assert "line1 line2" in unit
        # Backslashes should be escaped
        assert r"\\" in unit


class TestInteractiveUnitGenerator:
    """Test interactive_unit_generator method."""

    def _create_helper(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            return SystemdHelper()

    def test_interactive_generator(self):
        helper = self._create_helper()

        # Mock user inputs
        with patch("cortex.systemd_helper.Prompt.ask") as mock_prompt:
            with patch("cortex.systemd_helper.Confirm.ask") as mock_confirm:
                with patch("cortex.systemd_helper.console.print"):
                    mock_prompt.side_effect = [
                        "my-service",  # service name
                        "My Test Service",  # description
                        "/usr/bin/myapp",  # command
                        "appuser",  # user
                        "/var/lib/myapp",  # working dir
                    ]
                    mock_confirm.side_effect = [
                        False,  # run as root
                        True,  # set working dir
                        True,  # restart on failure
                        True,  # start on boot
                    ]

                    unit = helper.interactive_unit_generator()

        assert "Description=My Test Service" in unit
        assert "ExecStart=/usr/bin/myapp" in unit


class TestRunCommands:
    """Test the run_* command functions."""

    def test_run_status_command(self):
        status_output = "ActiveState=active\nSubState=running\n"
        mock_result = MagicMock(returncode=0, stdout=status_output)

        with patch("subprocess.run", return_value=mock_result):
            with patch("cortex.systemd_helper.console.print"):
                run_status_command("nginx")

    def test_run_diagnose_command(self):
        status_output = "ActiveState=failed\nSubState=failed\n"
        log_output = "Some logs here"

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "show" in cmd:
                result.stdout = status_output
            else:
                result.stdout = log_output
            return result

        with patch("subprocess.run", side_effect=mock_run):
            with patch("cortex.systemd_helper.console.print"):
                run_diagnose_command("nginx", lines=50)

    def test_run_deps_command(self):
        deps_output = "nginx.service\n├─system.slice\n"
        mock_result = MagicMock(returncode=0, stdout=deps_output)

        with patch("subprocess.run", return_value=mock_result):
            with patch("cortex.systemd_helper.console.print"):
                run_deps_command("nginx")

    def test_run_generate_command(self):
        mock_result = MagicMock(returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            with patch("cortex.systemd_helper.Prompt.ask") as mock_prompt:
                with patch("cortex.systemd_helper.Confirm.ask") as mock_confirm:
                    with patch("cortex.systemd_helper.console.print"):
                        mock_prompt.side_effect = [
                            "test-service",
                            "Test Service",
                            "/usr/bin/test",
                            "testuser",
                            "/var/lib/test",
                        ]
                        mock_confirm.side_effect = [False, True, True, True]
                        run_generate_command()


class TestConstants:
    """Test module constants."""

    def test_timeout_constants_reasonable(self):
        assert SYSTEMCTL_TIMEOUT > 0
        assert SYSTEMCTL_TIMEOUT <= 60
        assert JOURNALCTL_TIMEOUT > 0
        assert JOURNALCTL_TIMEOUT <= 120


class TestEdgeCases:
    """Test edge cases and error handling."""

    def _create_helper(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            return SystemdHelper()

    def test_empty_systemctl_output(self):
        helper = self._create_helper()
        mock_result = MagicMock(returncode=0, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("nginx")

        assert status.state == ServiceState.UNKNOWN

    def test_malformed_systemctl_output(self):
        helper = self._create_helper()
        mock_result = MagicMock(returncode=0, stdout="no equals sign here\n")

        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("nginx")

        # Should handle gracefully
        assert status.state == ServiceState.UNKNOWN

    def test_environment_with_all_special_chars(self):
        helper = self._create_helper()
        unit = helper.generate_unit_file(
            description="Test",
            exec_start="/bin/test",
            environment={
                "COMPLEX": 'Value with $var, `cmd`, "quotes", \\backslash, and\nnewline',
            },
        )

        # Should produce valid output without crashes
        assert "Environment=COMPLEX=" in unit
        # Critical characters should be escaped
        assert r"\$" in unit
        assert r"\`" in unit


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
