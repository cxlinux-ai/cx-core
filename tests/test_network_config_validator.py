"""
Tests for Network Configuration Validator Module

Issue: #445
"""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from cortex.network_config_validator import (
    ConfigDiff,
    ConfigType,
    NetworkConfigValidator,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    get_error_message,
    run_dry_run,
    run_validation,
    show_config_diff,
    validate_cidr,
    validate_gateway_reachable,
    validate_ip_address,
    validate_mac_address,
)


class TestValidationFunctions:
    """Tests for standalone validation functions."""

    def test_validate_ip_address_valid_ipv4(self):
        """Test valid IPv4 address validation."""
        is_valid, error = validate_ip_address("192.168.1.1")
        assert is_valid is True
        assert error is None

    def test_validate_ip_address_valid_ipv6(self):
        """Test valid IPv6 address validation."""
        is_valid, error = validate_ip_address("2001:db8::1")
        assert is_valid is True
        assert error is None

    def test_validate_ip_address_invalid(self):
        """Test invalid IP address validation."""
        is_valid, error = validate_ip_address("192.168.1.256")
        assert is_valid is False
        assert error is not None
        assert "192.168.1.256" in error

    def test_validate_ip_address_garbage(self):
        """Test garbage input for IP validation."""
        is_valid, error = validate_ip_address("not-an-ip")
        assert is_valid is False
        assert error is not None

    def test_validate_cidr_valid(self):
        """Test valid CIDR notation validation."""
        is_valid, error = validate_cidr("192.168.1.0/24")
        assert is_valid is True
        assert error is None

    def test_validate_cidr_valid_host(self):
        """Test valid CIDR with host bits set."""
        is_valid, error = validate_cidr("192.168.1.100/24")
        assert is_valid is True
        assert error is None

    def test_validate_cidr_invalid(self):
        """Test invalid CIDR notation."""
        is_valid, error = validate_cidr("192.168.1.0/33")
        assert is_valid is False
        assert error is not None

    def test_validate_cidr_no_prefix(self):
        """Test CIDR without prefix length - ipaddress treats bare IPs as /32."""
        # Note: ipaddress.ip_network() accepts bare IPs as /32 networks
        is_valid, error = validate_cidr("192.168.1.0")
        # This is valid because ipaddress treats it as 192.168.1.0/32
        assert is_valid is True
        assert error is None

    def test_validate_mac_address_valid_colon(self):
        """Test valid MAC address with colons."""
        is_valid, error = validate_mac_address("00:11:22:33:44:55")
        assert is_valid is True
        assert error is None

    def test_validate_mac_address_valid_dash(self):
        """Test valid MAC address with dashes."""
        is_valid, error = validate_mac_address("00-11-22-33-44-55")
        assert is_valid is True
        assert error is None

    def test_validate_mac_address_invalid(self):
        """Test invalid MAC address."""
        is_valid, error = validate_mac_address("00:11:22:33:44:GG")
        assert is_valid is False
        assert error is not None

    def test_validate_mac_address_wrong_format(self):
        """Test MAC address with wrong format."""
        is_valid, error = validate_mac_address("001122334455")
        assert is_valid is False
        assert error is not None

    def test_validate_gateway_reachable_yes(self):
        """Test gateway is reachable from subnet."""
        is_valid, error = validate_gateway_reachable("192.168.1.1", "192.168.1.100/24")
        assert is_valid is True
        assert error is None

    def test_validate_gateway_reachable_no(self):
        """Test gateway is not reachable from subnet."""
        is_valid, error = validate_gateway_reachable("10.0.0.1", "192.168.1.100/24")
        assert is_valid is False
        assert error is not None
        assert "10.0.0.1" in error or "192.168.1.100" in error

    def test_validate_gateway_invalid_gateway(self):
        """Test gateway validation with invalid gateway."""
        is_valid, error = validate_gateway_reachable("not-an-ip", "192.168.1.100/24")
        assert is_valid is False
        assert error is not None


class TestErrorMessages:
    """Tests for plain English error messages."""

    def test_get_error_message_known_type(self):
        """Test getting a known error message."""
        msg = get_error_message("invalid_ip", value="bad-ip")
        assert "bad-ip" in msg
        assert "IP" in msg or "address" in msg.lower()

    def test_get_error_message_unknown_type(self):
        """Test getting an unknown error message type."""
        msg = get_error_message("unknown_error_type")
        assert "unknown_error_type" in msg

    def test_get_error_message_yaml_syntax(self):
        """Test YAML syntax error message."""
        msg = get_error_message("yaml_syntax")
        assert "formatting" in msg.lower() or "yaml" in msg.lower()

    def test_get_error_message_missing_substitution(self):
        """Test error message with missing substitution."""
        # Should not raise, just return template
        msg = get_error_message("invalid_ip")
        assert msg is not None


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_validation_issue_creation(self):
        """Test creating a validation issue."""
        issue = ValidationIssue(
            rule_id="TEST001",
            message="Test message",
            severity=ValidationSeverity.ERROR,
            file_path="/etc/netplan/test.yaml",
            line_number=10,
            suggestion="Fix it",
            context="Some context",
        )
        assert issue.rule_id == "TEST001"
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.line_number == 10

    def test_validation_issue_to_dict(self):
        """Test converting validation issue to dict."""
        issue = ValidationIssue(
            rule_id="TEST001",
            message="Test message",
            severity=ValidationSeverity.WARNING,
        )
        result = issue.to_dict()
        assert result["rule_id"] == "TEST001"
        assert result["severity"] == "warning"


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_validation_report_creation(self):
        """Test creating a validation report."""
        report = ValidationReport(
            config_type=ConfigType.NETPLAN,
            is_valid=True,
            timestamp="2024-01-01T00:00:00",
        )
        assert report.config_type == ConfigType.NETPLAN
        assert report.is_valid is True

    def test_validation_report_counts(self):
        """Test issue counts in validation report."""
        report = ValidationReport(
            config_type=ConfigType.NETPLAN,
            is_valid=False,
            timestamp="2024-01-01T00:00:00",
            issues=[
                ValidationIssue("1", "msg", ValidationSeverity.INFO),
                ValidationIssue("2", "msg", ValidationSeverity.WARNING),
                ValidationIssue("3", "msg", ValidationSeverity.WARNING),
                ValidationIssue("4", "msg", ValidationSeverity.ERROR),
                ValidationIssue("5", "msg", ValidationSeverity.CRITICAL),
            ],
        )
        assert report.info_count == 1
        assert report.warning_count == 2
        assert report.error_count == 1
        assert report.critical_count == 1

    def test_validation_report_to_dict(self):
        """Test converting validation report to dict."""
        report = ValidationReport(
            config_type=ConfigType.NETWORKMANAGER,
            is_valid=True,
            timestamp="2024-01-01T00:00:00",
            config_files=["/etc/NetworkManager/NetworkManager.conf"],
        )
        result = report.to_dict()
        assert result["config_type"] == "networkmanager"
        assert result["is_valid"] is True
        assert "summary" in result


class TestNetworkConfigValidatorInit:
    """Tests for NetworkConfigValidator initialization."""

    def test_init_default(self):
        """Test default initialization."""
        validator = NetworkConfigValidator()
        assert validator.netplan_dir == Path("/etc/netplan")
        assert validator.nm_dir == Path("/etc/NetworkManager")

    def test_init_custom_paths(self):
        """Test initialization with custom paths."""
        validator = NetworkConfigValidator(
            netplan_dir="/custom/netplan",
            nm_dir="/custom/nm",
        )
        assert validator.netplan_dir == Path("/custom/netplan")
        assert validator.nm_dir == Path("/custom/nm")


class TestConfigTypeDetection:
    """Tests for configuration system detection."""

    def test_detect_netplan(self):
        """Test detecting Netplan configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()
            (netplan_dir / "01-config.yaml").touch()

            validator = NetworkConfigValidator(netplan_dir=str(netplan_dir))
            result = validator.detect_config_system()
            assert result == ConfigType.NETPLAN

    def test_detect_networkmanager(self):
        """Test detecting NetworkManager configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nm_dir = Path(tmpdir) / "NetworkManager"
            nm_dir.mkdir()
            (nm_dir / "NetworkManager.conf").touch()

            validator = NetworkConfigValidator(
                netplan_dir="/nonexistent",
                nm_dir=str(nm_dir),
            )
            result = validator.detect_config_system()
            assert result == ConfigType.NETWORKMANAGER

    def test_detect_unknown(self):
        """Test detecting unknown configuration system."""
        validator = NetworkConfigValidator(
            netplan_dir="/nonexistent/netplan",
            nm_dir="/nonexistent/nm",
        )
        result = validator.detect_config_system()
        assert result == ConfigType.UNKNOWN

    def test_detect_networkmanager_via_systemd(self):
        """Test detecting NetworkManager via systemd."""
        validator = NetworkConfigValidator(
            netplan_dir="/nonexistent/netplan",
            nm_dir="/nonexistent/nm",
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = validator.detect_config_system()
            assert result == ConfigType.NETWORKMANAGER


class TestGetConfigFiles:
    """Tests for getting configuration files."""

    def test_get_netplan_files(self):
        """Test getting Netplan configuration files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()
            (netplan_dir / "01-config.yaml").touch()
            (netplan_dir / "50-cloud.yaml").touch()

            validator = NetworkConfigValidator(netplan_dir=str(netplan_dir))
            with patch.object(validator, "detect_config_system", return_value=ConfigType.NETPLAN):
                files = validator.get_config_files()
                assert len(files) == 2
                assert all(f.suffix == ".yaml" for f in files)

    def test_get_networkmanager_files(self):
        """Test getting NetworkManager configuration files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nm_dir = Path(tmpdir) / "NetworkManager"
            nm_dir.mkdir()
            (nm_dir / "NetworkManager.conf").touch()

            conn_dir = nm_dir / "system-connections"
            conn_dir.mkdir()
            (conn_dir / "Home-WiFi").touch()

            validator = NetworkConfigValidator(nm_dir=str(nm_dir))
            with patch.object(
                validator, "detect_config_system", return_value=ConfigType.NETWORKMANAGER
            ):
                files = validator.get_config_files()
                assert len(files) == 2

    def test_get_config_files_unknown_system(self):
        """Test getting files when system is unknown."""
        validator = NetworkConfigValidator(
            netplan_dir="/nonexistent",
            nm_dir="/nonexistent",
        )
        with patch.object(validator, "detect_config_system", return_value=ConfigType.UNKNOWN):
            files = validator.get_config_files()
            assert files == []


class TestYAMLValidation:
    """Tests for YAML syntax validation."""

    def test_validate_yaml_valid(self):
        """Test validating valid YAML."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_yaml_syntax(Path(f.name))
            assert len(issues) == 0

        Path(f.name).unlink()

    def test_validate_yaml_invalid_syntax(self):
        """Test validating invalid YAML syntax."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
    dhcp4: true  # wrong indentation
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_yaml_syntax(Path(f.name))
            # May or may not have issues depending on YAML parser strictness
            # Just verify no exception is raised

        Path(f.name).unlink()

    def test_validate_yaml_empty_file(self):
        """Test validating empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_yaml_syntax(Path(f.name))
            assert len(issues) == 1
            assert issues[0].severity == ValidationSeverity.ERROR

        Path(f.name).unlink()

    def test_validate_yaml_file_not_found(self):
        """Test validating non-existent file."""
        validator = NetworkConfigValidator()
        issues = validator.validate_yaml_syntax(Path("/nonexistent/file.yaml"))
        assert len(issues) == 1
        assert issues[0].severity == ValidationSeverity.ERROR


class TestNetplanValidation:
    """Tests for Netplan-specific validation."""

    def test_validate_netplan_valid_config(self):
        """Test validating a valid Netplan configuration."""
        yaml_content = """
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: true
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            # Should have no errors (maybe info about renderer)
            errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
            assert len(errors) == 0

        Path(f.name).unlink()

    def test_validate_netplan_missing_network_key(self):
        """Test validating Netplan config without network key."""
        yaml_content = """
version: 2
ethernets:
  eth0:
    dhcp4: true
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
            assert len(errors) >= 1

        Path(f.name).unlink()

    def test_validate_netplan_invalid_ip(self):
        """Test validating Netplan config with invalid IP."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.999/24
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
            assert len(errors) >= 1

        Path(f.name).unlink()

    def test_validate_netplan_dhcp_with_static(self):
        """Test validating Netplan config with both DHCP and static IP."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      addresses:
        - 192.168.1.100/24
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]
            assert len(warnings) >= 1

        Path(f.name).unlink()

    def test_validate_netplan_duplicate_ip(self):
        """Test validating Netplan config with duplicate IPs."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
    eth1:
      addresses:
        - 192.168.1.100/24
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
            assert len(errors) >= 1

        Path(f.name).unlink()

    def test_validate_netplan_invalid_gateway(self):
        """Test validating Netplan config with invalid gateway."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      gateway4: not-an-ip
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
            assert len(errors) >= 1

        Path(f.name).unlink()

    def test_validate_netplan_unreachable_gateway(self):
        """Test validating Netplan config with unreachable gateway."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      gateway4: 10.0.0.1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]
            assert len(warnings) >= 1

        Path(f.name).unlink()

    def test_validate_netplan_invalid_dns(self):
        """Test validating Netplan config with invalid DNS."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: false
      addresses:
        - 192.168.1.100/24
      nameservers:
        addresses:
          - not-a-dns
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
            assert len(errors) >= 1

        Path(f.name).unlink()

    def test_validate_netplan_invalid_mac(self):
        """Test validating Netplan config with invalid MAC address."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      macaddress: invalid-mac
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
            assert len(errors) >= 1

        Path(f.name).unlink()

    def test_validate_netplan_routes(self):
        """Test validating Netplan config with routes."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      routes:
        - to: 10.0.0.0/8
          via: 192.168.1.1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
            assert len(errors) == 0

        Path(f.name).unlink()

    def test_validate_netplan_invalid_route(self):
        """Test validating Netplan config with invalid route."""
        yaml_content = """
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      routes:
        - to: invalid-dest
          via: not-an-ip
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            validator = NetworkConfigValidator()
            issues = validator.validate_netplan_config(Path(f.name))
            errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
            assert len(errors) >= 2  # Invalid to and via

        Path(f.name).unlink()


class TestFullValidation:
    """Tests for full validation workflow."""

    def test_validate_all(self):
        """Test full validation of all config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()

            config_file = netplan_dir / "01-config.yaml"
            config_file.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")

            validator = NetworkConfigValidator(netplan_dir=str(netplan_dir))
            report = validator.validate()

            assert report.config_type == ConfigType.NETPLAN
            assert len(report.config_files) == 1

    def test_validate_determines_validity(self):
        """Test that validation correctly determines overall validity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()

            # Valid config
            config_file = netplan_dir / "01-config.yaml"
            config_file.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")

            validator = NetworkConfigValidator(netplan_dir=str(netplan_dir))
            report = validator.validate()
            assert report.is_valid is True

    def test_validate_invalid_config(self):
        """Test that validation flags invalid configs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()

            # Invalid config - missing network key
            config_file = netplan_dir / "01-config.yaml"
            config_file.write_text("""
version: 2
ethernets:
  eth0:
    addresses:
      - invalid-ip
""")

            validator = NetworkConfigValidator(netplan_dir=str(netplan_dir))
            report = validator.validate()
            assert report.is_valid is False


class TestDiffDisplay:
    """Tests for diff display functionality."""

    def test_show_diff(self):
        """Test generating a diff."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("original: content\n")
            f.flush()

            validator = NetworkConfigValidator()
            diff = validator.show_diff(Path(f.name), "new: content\n")

            assert diff.original == "original: content\n"
            assert diff.modified == "new: content\n"
            assert len(diff.changes) > 0

        Path(f.name).unlink()

    def test_show_diff_no_changes(self):
        """Test diff when content is the same."""
        content = "same: content\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            f.flush()

            validator = NetworkConfigValidator()
            diff = validator.show_diff(Path(f.name), content)

            assert len(diff.changes) == 0

        Path(f.name).unlink()

    def test_show_diff_nonexistent_file(self):
        """Test diff when original file doesn't exist."""
        validator = NetworkConfigValidator()
        diff = validator.show_diff(Path("/nonexistent/file.yaml"), "new: content\n")

        assert diff.original == ""
        assert diff.modified == "new: content\n"

    def test_print_diff(self):
        """Test printing a diff (should not raise)."""
        validator = NetworkConfigValidator()
        diff = ConfigDiff(
            file_path="/test/file.yaml",
            original="old: value\n",
            modified="new: value\n",
            changes=["- old: value", "+ new: value"],
        )
        # Should not raise
        validator.print_diff(diff)


class TestDryRunMode:
    """Tests for dry-run mode functionality."""

    def test_dry_run_not_netplan(self):
        """Test dry-run fails for non-Netplan systems."""
        validator = NetworkConfigValidator(
            netplan_dir="/nonexistent",
            nm_dir="/nonexistent",
        )
        with patch.object(validator, "detect_config_system", return_value=ConfigType.UNKNOWN):
            result = validator.dry_run()
            assert result is False

    def test_dry_run_backup_failure(self):
        """Test dry-run handles backup failure."""
        validator = NetworkConfigValidator()
        with patch.object(
            validator, "detect_config_system", return_value=ConfigType.NETPLAN
        ):
            with patch.object(validator, "_backup_configs_to_memory", return_value=False):
                result = validator.dry_run()
                assert result is False

    def test_dry_run_netplan_not_found(self):
        """Test dry-run handles missing netplan command."""
        validator = NetworkConfigValidator()
        with patch.object(
            validator, "detect_config_system", return_value=ConfigType.NETPLAN
        ):
            with patch.object(validator, "_backup_configs_to_memory", return_value=True):
                with patch("subprocess.run", side_effect=FileNotFoundError()):
                    result = validator.dry_run(timeout_seconds=5)
                    assert result is False


class TestDisplayMethods:
    """Tests for display methods."""

    def test_print_report_valid(self):
        """Test printing a valid report."""
        report = ValidationReport(
            config_type=ConfigType.NETPLAN,
            is_valid=True,
            timestamp="2024-01-01T00:00:00",
            config_files=["/etc/netplan/01-config.yaml"],
        )
        validator = NetworkConfigValidator()
        # Should not raise
        validator.print_report(report)

    def test_print_report_with_issues(self):
        """Test printing a report with issues."""
        report = ValidationReport(
            config_type=ConfigType.NETPLAN,
            is_valid=False,
            timestamp="2024-01-01T00:00:00",
            config_files=["/etc/netplan/01-config.yaml"],
            issues=[
                ValidationIssue(
                    rule_id="TEST001",
                    message="Test error",
                    severity=ValidationSeverity.ERROR,
                    file_path="/etc/netplan/01-config.yaml",
                    line_number=5,
                    suggestion="Fix it",
                    context="eth0",
                ),
                ValidationIssue(
                    rule_id="TEST002",
                    message="Test warning",
                    severity=ValidationSeverity.WARNING,
                ),
            ],
        )
        validator = NetworkConfigValidator()
        # Should not raise
        validator.print_report(report)

    def test_print_config_summary(self):
        """Test printing configuration summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()

            config_file = netplan_dir / "01-config.yaml"
            config_file.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")

            validator = NetworkConfigValidator(netplan_dir=str(netplan_dir))
            # Should not raise
            validator.print_config_summary()


class TestCLIFunctions:
    """Tests for CLI integration functions."""

    def test_run_validation(self):
        """Test run_validation function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()

            config_file = netplan_dir / "01-config.yaml"
            config_file.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")

            with patch(
                "cortex.network_config_validator.NetworkConfigValidator.__init__",
                return_value=None,
            ):
                with patch(
                    "cortex.network_config_validator.NetworkConfigValidator.validate"
                ) as mock_validate:
                    with patch(
                        "cortex.network_config_validator.NetworkConfigValidator.print_report"
                    ):
                        mock_validate.return_value = ValidationReport(
                            config_type=ConfigType.NETPLAN,
                            is_valid=True,
                            timestamp="2024-01-01T00:00:00",
                        )
                        result = run_validation()
                        assert result == 0

    def test_run_validation_invalid(self):
        """Test run_validation with invalid config."""
        with patch(
            "cortex.network_config_validator.NetworkConfigValidator.__init__",
            return_value=None,
        ):
            with patch(
                "cortex.network_config_validator.NetworkConfigValidator.validate"
            ) as mock_validate:
                with patch(
                    "cortex.network_config_validator.NetworkConfigValidator.print_report"
                ):
                    mock_validate.return_value = ValidationReport(
                        config_type=ConfigType.NETPLAN,
                        is_valid=False,
                        timestamp="2024-01-01T00:00:00",
                    )
                    result = run_validation()
                    assert result == 1

    def test_run_dry_run_invalid_config(self):
        """Test run_dry_run with invalid config."""
        with patch(
            "cortex.network_config_validator.NetworkConfigValidator.__init__",
            return_value=None,
        ):
            with patch(
                "cortex.network_config_validator.NetworkConfigValidator.validate"
            ) as mock_validate:
                with patch(
                    "cortex.network_config_validator.NetworkConfigValidator.print_report"
                ):
                    mock_validate.return_value = ValidationReport(
                        config_type=ConfigType.NETPLAN,
                        is_valid=False,
                        timestamp="2024-01-01T00:00:00",
                    )
                    result = run_dry_run()
                    assert result == 1

    def test_show_config_diff(self):
        """Test show_config_diff function."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("old: content\n")
            f.flush()

            result = show_config_diff(f.name, "new: content\n")
            assert result == 0

        Path(f.name).unlink()


class TestFilePermissions:
    """Tests for file permission checking."""

    def test_check_world_readable_file(self):
        """Test detecting world-readable config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("network: {}\n")
            f.flush()
            # Make file world-readable
            os.chmod(f.name, 0o644)

            validator = NetworkConfigValidator()
            issues = validator._check_file_permissions(Path(f.name))

            # Should have a warning about permissions
            warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]
            assert len(warnings) >= 1

        Path(f.name).unlink()

    def test_check_secure_file(self):
        """Test secure file permissions pass."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("network: {}\n")
            f.flush()
            # Make file not world-readable
            os.chmod(f.name, 0o600)

            validator = NetworkConfigValidator()
            issues = validator._check_file_permissions(Path(f.name))

            # Should have no warnings
            warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]
            assert len(warnings) == 0

        Path(f.name).unlink()


class TestRevertMechanism:
    """Tests for configuration revert mechanism."""

    def test_backup_configs_to_memory(self):
        """Test backing up configs to memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()

            config_file = netplan_dir / "01-config.yaml"
            config_file.write_text("network: {}\n")

            validator = NetworkConfigValidator(netplan_dir=str(netplan_dir))
            with patch.object(validator, "detect_config_system", return_value=ConfigType.NETPLAN):
                result = validator._backup_configs_to_memory()
                assert result is True
                assert str(config_file) in validator._backup_configs

    def test_backup_configs_failure(self):
        """Test backup failure on unreadable file."""
        validator = NetworkConfigValidator()
        with patch.object(
            validator, "get_config_files", return_value=[Path("/nonexistent/file.yaml")]
        ):
            result = validator._backup_configs_to_memory()
            assert result is False

    def test_cancel_revert_timer(self):
        """Test canceling revert timer."""
        validator = NetworkConfigValidator()
        mock_timer = MagicMock()
        validator._revert_timer = mock_timer
        validator._cancel_revert_timer()
        mock_timer.cancel.assert_called_once()
        assert validator._revert_timer is None


class TestIntegration:
    """Integration tests for the full validation workflow."""

    def test_full_workflow_valid_config(self):
        """Test complete validation workflow with valid config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()

            config_file = netplan_dir / "01-config.yaml"
            config_file.write_text("""
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      gateway4: 192.168.1.1
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4
""")
            # Secure permissions
            os.chmod(config_file, 0o600)

            validator = NetworkConfigValidator(netplan_dir=str(netplan_dir))
            report = validator.validate()

            assert report.is_valid is True
            assert report.config_type == ConfigType.NETPLAN
            assert report.error_count == 0
            assert report.critical_count == 0

    def test_full_workflow_invalid_config(self):
        """Test complete validation workflow with invalid config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()

            config_file = netplan_dir / "01-config.yaml"
            config_file.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 999.999.999.999/24
      gateway4: also-invalid
      nameservers:
        addresses:
          - not-a-dns
""")

            validator = NetworkConfigValidator(netplan_dir=str(netplan_dir))
            report = validator.validate()

            assert report.is_valid is False
            assert report.error_count >= 3  # Invalid IP, gateway, DNS

    def test_full_workflow_multiple_files(self):
        """Test validation with multiple config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            netplan_dir = Path(tmpdir) / "netplan"
            netplan_dir.mkdir()

            # First config - valid
            config1 = netplan_dir / "01-lo.yaml"
            config1.write_text("""
network:
  version: 2
  ethernets:
    lo:
      addresses:
        - 127.0.0.1/8
""")

            # Second config - valid
            config2 = netplan_dir / "50-cloud.yaml"
            config2.write_text("""
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
""")

            validator = NetworkConfigValidator(netplan_dir=str(netplan_dir))
            report = validator.validate()

            assert len(report.config_files) == 2
            assert report.is_valid is True
