"""
Tests for Systemd Helper Module

Issue: #448 - Systemd Service Helper (Plain English)
"""

from unittest.mock import MagicMock, patch

import pytest

from cortex.systemd_helper import (
    FAILURE_SOLUTIONS,
    SERVICE_STATE_EXPLANATIONS,
    SUB_STATE_EXPLANATIONS,
    ServiceConfig,
    ServiceStatus,
    ServiceType,
    SystemdHelper,
    run_systemd_helper,
)


class TestServiceConfig:
    """Tests for ServiceConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ServiceConfig(name="test", description="Test service", exec_start="/usr/bin/test")
        assert config.name == "test"
        assert config.service_type == ServiceType.SIMPLE
        assert config.restart == "on-failure"
        assert config.restart_sec == 5
        assert "network.target" in config.after
        assert "multi-user.target" in config.wanted_by

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ServiceConfig(
            name="custom",
            description="Custom service",
            exec_start="/usr/bin/custom",
            service_type=ServiceType.FORKING,
            user="nobody",
            group="nogroup",
            restart="always",
            environment={"KEY": "value"},
        )
        assert config.service_type == ServiceType.FORKING
        assert config.user == "nobody"
        assert config.environment == {"KEY": "value"}


class TestServiceStatus:
    """Tests for ServiceStatus dataclass."""

    def test_default_values(self):
        """Test default status values."""
        status = ServiceStatus(name="test.service")
        assert status.name == "test.service"
        assert status.active_state == ""
        assert status.main_pid == 0
        assert status.docs == []

    def test_with_values(self):
        """Test status with values."""
        status = ServiceStatus(
            name="nginx.service",
            active_state="active",
            sub_state="running",
            main_pid=1234,
            memory="50.0 MB",
        )
        assert status.active_state == "active"
        assert status.main_pid == 1234


class TestServiceStateExplanations:
    """Tests for state explanation constants."""

    def test_all_states_have_explanations(self):
        """Test that common states have explanations."""
        common_states = ["active", "inactive", "failed", "activating", "deactivating"]
        for state in common_states:
            assert state in SERVICE_STATE_EXPLANATIONS
            assert len(SERVICE_STATE_EXPLANATIONS[state]) > 0

    def test_sub_states_have_explanations(self):
        """Test that common sub-states have explanations."""
        common_sub_states = ["running", "dead", "exited", "failed"]
        for state in common_sub_states:
            assert state in SUB_STATE_EXPLANATIONS


class TestFailureSolutions:
    """Tests for failure solution constants."""

    def test_common_failures_have_solutions(self):
        """Test that common failures have solutions."""
        common_failures = ["exit-code", "signal", "timeout", "start-limit-hit"]
        for failure in common_failures:
            assert failure in FAILURE_SOLUTIONS
            assert len(FAILURE_SOLUTIONS[failure]) > 0

    def test_solutions_have_descriptions(self):
        """Test that solutions have proper format."""
        for failure, solutions in FAILURE_SOLUTIONS.items():
            for solution in solutions:
                assert len(solution) == 2  # (description, command)
                assert isinstance(solution[0], str)
                assert isinstance(solution[1], str)


class TestSystemdHelper:
    """Tests for SystemdHelper class."""

    @pytest.fixture
    def helper(self):
        """Create a helper instance."""
        return SystemdHelper(verbose=False)

    def test_initialization(self, helper):
        """Test helper initialization."""
        assert helper.verbose is False

    def test_run_systemctl_not_found(self, helper):
        """Test when systemctl is not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            code, stdout, stderr = helper._run_systemctl("status", "test")
            assert code == 1
            assert "not found" in stderr.lower()

    def test_run_systemctl_success(self, helper):
        """Test successful systemctl command."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ActiveState=active", stderr="")
            code, stdout, stderr = helper._run_systemctl("status", "test")
            assert code == 0
            assert "active" in stdout.lower()

    def test_run_systemctl_timeout(self, helper):
        """Test systemctl timeout handling."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)
            code, stdout, stderr = helper._run_systemctl("status", "test")
            assert code == 1
            assert "timed out" in stderr.lower()


class TestGetStatus:
    """Tests for get_status method."""

    @pytest.fixture
    def helper(self):
        return SystemdHelper()

    def test_get_status_not_found(self, helper):
        """Test status for non-existent service."""
        with patch.object(helper, "_run_systemctl") as mock:
            mock.return_value = (1, "", "")
            status = helper.get_status("nonexistent")
            assert status is None

    def test_get_status_parses_output(self, helper):
        """Test status parsing."""
        output = """LoadState=loaded
ActiveState=active
SubState=running
Description=Test Service
MainPID=1234
MemoryCurrent=52428800
TasksCurrent=5
Result=success
"""
        with patch.object(helper, "_run_systemctl") as mock:
            mock.return_value = (0, output, "")
            status = helper.get_status("test")

            assert status is not None
            assert status.active_state == "active"
            assert status.sub_state == "running"
            assert status.main_pid == 1234
            assert status.tasks == 5

    def test_get_status_adds_service_suffix(self, helper):
        """Test that .service suffix is added."""
        with patch.object(helper, "_run_systemctl") as mock:
            mock.return_value = (0, "ActiveState=active", "")
            helper.get_status("nginx")
            # Verify it was called with .service suffix
            mock.assert_called_once()
            args = mock.call_args[0]
            assert "nginx.service" in args


class TestExplainStatus:
    """Tests for explain_status method."""

    @pytest.fixture
    def helper(self):
        return SystemdHelper()

    def test_explain_not_found(self, helper):
        """Test explanation for missing service."""
        with patch.object(helper, "get_status") as mock:
            mock.return_value = None
            success, explanation = helper.explain_status("missing")
            assert not success
            assert "not found" in explanation.lower()

    def test_explain_active_service(self, helper):
        """Test explanation for active service."""
        status = ServiceStatus(
            name="test.service",
            load_state="loaded",
            active_state="active",
            sub_state="running",
            main_pid=1234,
        )
        with patch.object(helper, "get_status") as mock:
            mock.return_value = status
            success, explanation = helper.explain_status("test")

            assert success
            assert "active" in explanation.lower()
            assert "running" in explanation.lower()

    def test_explain_failed_service(self, helper):
        """Test explanation for failed service."""
        status = ServiceStatus(
            name="test.service",
            load_state="loaded",
            active_state="failed",
            result="exit-code",
        )
        with patch.object(helper, "get_status") as mock:
            mock.return_value = status
            success, explanation = helper.explain_status("test")

            assert success
            assert "failed" in explanation.lower()
            assert "exit-code" in explanation.lower()

    def test_explain_masked_service(self, helper):
        """Test explanation for masked service."""
        status = ServiceStatus(
            name="test.service",
            load_state="masked",
        )
        with patch.object(helper, "get_status") as mock:
            mock.return_value = status
            success, explanation = helper.explain_status("test")

            assert success
            assert "masked" in explanation.lower()


class TestDiagnoseFailure:
    """Tests for diagnose_failure method."""

    @pytest.fixture
    def helper(self):
        return SystemdHelper()

    def test_diagnose_not_found(self, helper):
        """Test diagnosis for missing service."""
        with patch.object(helper, "get_status") as mock:
            mock.return_value = None
            found, explanation, logs = helper.diagnose_failure("missing")
            assert not found
            assert "not found" in explanation.lower()

    def test_diagnose_running_service(self, helper):
        """Test diagnosis for running service."""
        status = ServiceStatus(
            name="test.service",
            active_state="active",
            result="success",
        )
        with patch.object(helper, "get_status") as mock:
            mock.return_value = status
            with patch.object(helper, "_run_journalctl") as mock_log:
                mock_log.return_value = ""
                found, explanation, logs = helper.diagnose_failure("test")

                assert found
                assert "running normally" in explanation.lower()

    def test_diagnose_with_logs(self, helper):
        """Test diagnosis analyzes logs."""
        status = ServiceStatus(
            name="test.service",
            active_state="failed",
            result="exit-code",
        )
        logs = "error: permission denied\nfailed to start"

        with patch.object(helper, "get_status") as mock_status:
            mock_status.return_value = status
            with patch.object(helper, "_run_journalctl") as mock_log:
                mock_log.return_value = logs
                found, explanation, log_lines = helper.diagnose_failure("test")

                assert found
                assert "permission" in explanation.lower()


class TestGetDependencies:
    """Tests for get_dependencies method."""

    @pytest.fixture
    def helper(self):
        return SystemdHelper()

    def test_get_dependencies_parses_output(self, helper):
        """Test dependency parsing."""
        output = """Wants=network-online.target
Requires=basic.target
After=network.target sysinit.target
WantedBy=multi-user.target
"""
        with patch.object(helper, "_run_systemctl") as mock:
            mock.return_value = (0, output, "")
            deps = helper.get_dependencies("test")

            assert "network-online.target" in deps["wants"]
            assert "basic.target" in deps["requires"]
            assert "network.target" in deps["after"]
            assert "multi-user.target" in deps["wanted_by"]


class TestGenerateUnitFile:
    """Tests for generate_unit_file method."""

    @pytest.fixture
    def helper(self):
        return SystemdHelper()

    def test_generate_basic_unit(self, helper):
        """Test basic unit file generation."""
        config = ServiceConfig(
            name="test",
            description="Test service",
            exec_start="/usr/bin/test",
        )
        content = helper.generate_unit_file(config)

        assert "[Unit]" in content
        assert "Description=Test service" in content
        assert "[Service]" in content
        assert "ExecStart=/usr/bin/test" in content
        assert "[Install]" in content
        assert "WantedBy=multi-user.target" in content

    def test_generate_full_unit(self, helper):
        """Test full unit file generation."""
        config = ServiceConfig(
            name="myapp",
            description="My Application",
            exec_start="/usr/bin/myapp start",
            service_type=ServiceType.FORKING,
            user="myuser",
            group="mygroup",
            working_directory="/opt/myapp",
            environment={"NODE_ENV": "production"},
            restart="always",
            after=["network.target", "postgresql.service"],
        )
        content = helper.generate_unit_file(config)

        assert "Type=forking" in content
        assert "User=myuser" in content
        assert "Group=mygroup" in content
        assert "WorkingDirectory=/opt/myapp" in content
        assert "Environment=NODE_ENV=production" in content
        assert "Restart=always" in content
        assert "After=network.target postgresql.service" in content


class TestCreateUnitFromDescription:
    """Tests for create_unit_from_description method."""

    @pytest.fixture
    def helper(self):
        return SystemdHelper()

    def test_create_from_description(self, helper):
        """Test creating unit from description."""
        service_name, content = helper.create_unit_from_description(
            description="My Web Server",
            command="/usr/bin/python3 -m http.server 8080",
        )

        assert service_name.endswith(".service")
        assert "My Web Server" in content
        assert "/usr/bin/python3 -m http.server 8080" in content

    def test_create_with_custom_name(self, helper):
        """Test creating unit with custom name."""
        service_name, content = helper.create_unit_from_description(
            description="My App",
            command="/usr/bin/app",
            name="myapp",
        )

        assert service_name == "myapp.service"

    def test_create_with_user(self, helper):
        """Test creating unit with user."""
        _, content = helper.create_unit_from_description(
            description="Test",
            command="/usr/bin/test",
            user="testuser",
        )

        assert "User=testuser" in content

    def test_auto_name_generation(self, helper):
        """Test automatic name generation from description."""
        service_name, _ = helper.create_unit_from_description(
            description="My Super Cool Application",
            command="/usr/bin/app",
        )

        # Should be lowercase with hyphens
        assert service_name == "my-super-cool-application.service"


class TestDisplayMethods:
    """Tests for display methods."""

    @pytest.fixture
    def helper(self):
        return SystemdHelper()

    def test_display_status_not_found(self, helper, capsys):
        """Test display for missing service."""
        with patch.object(helper, "get_status") as mock:
            mock.return_value = None
            helper.display_status("missing")
            captured = capsys.readouterr()
            assert "not found" in captured.out.lower()

    def test_display_status_active(self, helper, capsys):
        """Test display for active service."""
        status = ServiceStatus(
            name="test.service",
            active_state="active",
            sub_state="running",
            description="Test Service",
            main_pid=1234,
        )
        with patch.object(helper, "get_status") as mock_status:
            mock_status.return_value = status
            with patch.object(helper, "explain_status") as mock_explain:
                mock_explain.return_value = (True, "Service is running.")
                helper.display_status("test")
                captured = capsys.readouterr()
                assert "active" in captured.out.lower()


class TestRunSystemdHelper:
    """Tests for run_systemd_helper entry point."""

    def test_run_status(self, capsys):
        """Test running status action."""
        with patch("cortex.systemd_helper.SystemdHelper") as MockHelper:
            mock_instance = MagicMock()
            MockHelper.return_value = mock_instance

            result = run_systemd_helper("nginx", "status")

            mock_instance.display_status.assert_called_once_with("nginx")
            assert result == 0

    def test_run_diagnose(self):
        """Test running diagnose action."""
        with patch("cortex.systemd_helper.SystemdHelper") as MockHelper:
            mock_instance = MagicMock()
            MockHelper.return_value = mock_instance

            result = run_systemd_helper("nginx", "diagnose")

            mock_instance.display_diagnosis.assert_called_once_with("nginx")
            assert result == 0

    def test_run_deps(self, capsys):
        """Test running deps action."""
        with patch("cortex.systemd_helper.SystemdHelper") as MockHelper:
            mock_instance = MagicMock()
            mock_instance.show_dependencies_tree.return_value = MagicMock()
            MockHelper.return_value = mock_instance

            result = run_systemd_helper("nginx", "deps")

            mock_instance.show_dependencies_tree.assert_called_once_with("nginx")
            assert result == 0

    def test_run_unknown_action(self, capsys):
        """Test unknown action."""
        result = run_systemd_helper("nginx", "unknown")
        assert result == 1
        captured = capsys.readouterr()
        assert "unknown" in captured.out.lower()


class TestServiceType:
    """Tests for ServiceType enum."""

    def test_service_types(self):
        """Test all service types are defined."""
        assert ServiceType.SIMPLE.value == "simple"
        assert ServiceType.FORKING.value == "forking"
        assert ServiceType.ONESHOT.value == "oneshot"
        assert ServiceType.NOTIFY.value == "notify"
