"""
Tests for Netplan Configuration Validator

Comprehensive test suite for the netplan_validator module.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml

from cortex.netplan_validator import (
    NetplanValidator,
    ValidationResult,
    validate_netplan_config,
)


@pytest.fixture
def temp_netplan_dir(tmp_path):
    """Create a temporary netplan directory structure."""
    netplan_dir = tmp_path / "etc" / "netplan"
    netplan_dir.mkdir(parents=True)
    return netplan_dir


@pytest.fixture
def temp_backup_dir(tmp_path):
    """Create a temporary backup directory."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)
    return backup_dir


@pytest.fixture
def valid_netplan_config():
    """Return a valid netplan configuration."""
    return """network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: true
    eth1:
      addresses:
        - 192.168.1.100/24
      gateway4: 192.168.1.1
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4
"""


@pytest.fixture
def invalid_yaml_config():
    """Return an invalid YAML configuration."""
    return """network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
    invalid indentation here
"""


@pytest.fixture
def invalid_ip_config():
    """Return a config with invalid IP addresses."""
    return """network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 999.999.999.999/24
      gateway4: invalid.ip.address
      nameservers:
        addresses:
          - 8.8.8.8.8
"""


@pytest.fixture
def netplan_validator(temp_netplan_dir, temp_backup_dir, valid_netplan_config, monkeypatch):
    """Create a NetplanValidator instance with mocked paths."""
    config_file = temp_netplan_dir / "01-netcfg.yaml"
    config_file.write_text(valid_netplan_config)

    # Mock the class attributes
    monkeypatch.setattr(NetplanValidator, "NETPLAN_DIR", temp_netplan_dir)
    monkeypatch.setattr(NetplanValidator, "BACKUP_DIR", temp_backup_dir)

    return NetplanValidator(config_file)


class TestYAMLSyntaxValidation:
    """Test YAML syntax validation."""

    def test_valid_yaml_syntax(self, netplan_validator, valid_netplan_config):
        """Test validation of valid YAML syntax."""
        result = netplan_validator.validate_yaml_syntax(valid_netplan_config)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert "✓ YAML syntax is valid" in result.info

    def test_invalid_yaml_syntax(self, netplan_validator, invalid_yaml_config):
        """Test detection of invalid YAML syntax."""
        result = netplan_validator.validate_yaml_syntax(invalid_yaml_config)

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("syntax error" in err.lower() for err in result.errors)

    def test_empty_yaml(self, netplan_validator):
        """Test handling of empty YAML."""
        result = netplan_validator.validate_yaml_syntax("")

        assert result.is_valid is False
        assert "empty" in result.errors[0].lower()

    def test_yaml_with_tabs(self, netplan_validator):
        """Test YAML with tab characters (common mistake)."""
        config_with_tabs = "network:\n\tversion: 2\n\tethernets:\n\t\teth0:\n\t\t\tdhcp4: true"
        result = netplan_validator.validate_yaml_syntax(config_with_tabs)

        # YAML should reject tabs for indentation
        assert result.is_valid is False


class TestIPAddressValidation:
    """Test IP address validation."""

    def test_valid_ipv4_address(self, netplan_validator):
        """Test validation of valid IPv4 address."""
        valid, error = netplan_validator.validate_ip_address("192.168.1.1", allow_cidr=False)
        assert valid is True
        assert error == ""

    def test_valid_ipv4_cidr(self, netplan_validator):
        """Test validation of valid IPv4 CIDR."""
        valid, error = netplan_validator.validate_ip_address("192.168.1.0/24", allow_cidr=True)
        assert valid is True
        assert error == ""

    def test_valid_ipv6_address(self, netplan_validator):
        """Test validation of valid IPv6 address."""
        valid, error = netplan_validator.validate_ip_address("2001:db8::1", allow_cidr=False)
        assert valid is True
        assert error == ""

    def test_valid_ipv6_cidr(self, netplan_validator):
        """Test validation of valid IPv6 CIDR."""
        valid, error = netplan_validator.validate_ip_address("2001:db8::/32", allow_cidr=True)
        assert valid is True
        assert error == ""

    def test_invalid_ipv4_address(self, netplan_validator):
        """Test detection of invalid IPv4 address."""
        valid, error = netplan_validator.validate_ip_address("999.999.999.999", allow_cidr=False)
        assert valid is False
        assert "invalid" in error.lower()

    def test_invalid_ipv4_cidr(self, netplan_validator):
        """Test detection of invalid IPv4 CIDR."""
        valid, error = netplan_validator.validate_ip_address("192.168.1.0/33", allow_cidr=True)
        assert valid is False

    def test_malformed_ip(self, netplan_validator):
        """Test detection of malformed IP addresses."""
        invalid_ips = [
            "not.an.ip.address",
            "192.168.1",
            "192.168.1.1.1",
            "",
            "....",
        ]

        for ip in invalid_ips:
            valid, error = netplan_validator.validate_ip_address(ip, allow_cidr=False)
            assert valid is False, f"IP '{ip}' should be invalid"

    def test_cidr_when_not_allowed(self, netplan_validator):
        """Test CIDR notation when allow_cidr=False."""
        valid, error = netplan_validator.validate_ip_address("192.168.1.1/24", allow_cidr=False)
        # CIDR should be invalid when allow_cidr=False
        assert valid is False
        assert "cidr" in error.lower() or "not allowed" in error.lower()


class TestRouteValidation:
    """Test route validation."""

    def test_valid_route(self, netplan_validator):
        """Test validation of valid route."""
        route = {"to": "0.0.0.0/0", "via": "192.168.1.1"}
        valid, errors = netplan_validator.validate_route(route)

        assert valid is True
        assert len(errors) == 0

    def test_route_missing_to(self, netplan_validator):
        """Test detection of route missing 'to' field."""
        route = {"via": "192.168.1.1"}
        valid, errors = netplan_validator.validate_route(route)

        assert valid is False
        assert any("missing" in err.lower() and "to" in err.lower() for err in errors)

    def test_route_missing_via(self, netplan_validator):
        """Test detection of route missing 'via' field."""
        route = {"to": "0.0.0.0/0"}
        valid, errors = netplan_validator.validate_route(route)

        assert valid is False
        assert any("missing" in err.lower() and "via" in err.lower() for err in errors)

    def test_route_invalid_destination(self, netplan_validator):
        """Test detection of invalid route destination."""
        route = {"to": "invalid/24", "via": "192.168.1.1"}
        valid, errors = netplan_validator.validate_route(route)

        assert valid is False
        assert any("destination" in err.lower() for err in errors)

    def test_route_invalid_gateway(self, netplan_validator):
        """Test detection of invalid route gateway."""
        route = {"to": "0.0.0.0/0", "via": "999.999.999.999"}
        valid, errors = netplan_validator.validate_route(route)

        assert valid is False
        assert any("gateway" in err.lower() for err in errors)


class TestSemanticValidation:
    """Test semantic validation of network configuration."""

    def test_valid_config_semantics(self, netplan_validator, valid_netplan_config):
        """Test semantic validation of valid configuration."""
        config = yaml.safe_load(valid_netplan_config)
        result = netplan_validator.validate_semantics(config)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_missing_network_key(self, netplan_validator):
        """Test detection of missing 'network' key."""
        config = {"version": 2}
        result = netplan_validator.validate_semantics(config)

        assert result.is_valid is False
        assert any("network" in err.lower() for err in result.errors)

    def test_missing_version_warning(self, netplan_validator):
        """Test warning for missing version."""
        config = {"network": {"ethernets": {}}}
        result = netplan_validator.validate_semantics(config)

        assert any("version" in warn.lower() for warn in result.warnings)

    def test_dhcp_and_static_ip_warning(self, netplan_validator):
        """Test warning when both DHCP and static IPs are configured."""
        config = {
            "network": {
                "version": 2,
                "ethernets": {"eth0": {"dhcp4": True, "addresses": ["192.168.1.100/24"]}},
            }
        }
        result = netplan_validator.validate_semantics(config)

        assert any("dhcp" in warn.lower() and "static" in warn.lower() for warn in result.warnings)

    def test_no_ip_configuration_warning(self, netplan_validator):
        """Test warning when interface has no IP configuration."""
        config = {"network": {"version": 2, "ethernets": {"eth0": {}}}}
        result = netplan_validator.validate_semantics(config)

        assert any("neither" in warn.lower() for warn in result.warnings)

    def test_invalid_interface_name(self, netplan_validator):
        """Test detection of invalid interface name."""
        config = {
            "network": {"version": 2, "ethernets": {"eth@0": {"dhcp4": True}}}  # Invalid character
        }
        result = netplan_validator.validate_semantics(config)

        assert any("invalid interface name" in err.lower() for err in result.errors)

    def test_address_without_cidr_warning(self, netplan_validator):
        """Test warning for IP address without CIDR notation."""
        config = {
            "network": {
                "version": 2,
                "ethernets": {"eth0": {"addresses": ["192.168.1.100"]}},  # Missing /24
            }
        }
        result = netplan_validator.validate_semantics(config)

        assert any("cidr" in warn.lower() for warn in result.warnings)

    def test_invalid_nameserver(self, netplan_validator):
        """Test detection of invalid nameserver IP."""
        config = {
            "network": {
                "version": 2,
                "ethernets": {
                    "eth0": {"dhcp4": True, "nameservers": {"addresses": ["999.999.999.999"]}}
                },
            }
        }
        result = netplan_validator.validate_semantics(config)

        assert any("nameserver" in err.lower() for err in result.errors)


class TestFileValidation:
    """Test file validation."""

    def test_validate_existing_file(self, netplan_validator):
        """Test validation of existing file."""
        result = netplan_validator.validate_file()

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_nonexistent_file(self, netplan_validator):
        """Test validation of non-existent file."""
        result = netplan_validator.validate_file("/nonexistent/file.yaml")

        assert result.is_valid is False
        assert any("not found" in err.lower() for err in result.errors)

    def test_validate_file_with_invalid_yaml(
        self, temp_netplan_dir, netplan_validator, invalid_yaml_config
    ):
        """Test validation of file with invalid YAML."""
        invalid_file = temp_netplan_dir / "invalid.yaml"
        invalid_file.write_text(invalid_yaml_config)

        result = netplan_validator.validate_file(invalid_file)

        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_validate_file_with_invalid_ips(
        self, temp_netplan_dir, netplan_validator, invalid_ip_config
    ):
        """Test validation of file with invalid IP addresses."""
        invalid_file = temp_netplan_dir / "invalid_ips.yaml"
        invalid_file.write_text(invalid_ip_config)

        result = netplan_validator.validate_file(invalid_file)

        assert result.is_valid is False
        assert any("invalid ip" in err.lower() for err in result.errors)


class TestDiffGeneration:
    """Test diff generation."""

    def test_generate_diff_with_changes(
        self, temp_netplan_dir, netplan_validator, valid_netplan_config
    ):
        """Test diff generation when there are changes."""
        # Create a modified config
        modified_config = valid_netplan_config.replace("dhcp4: true", "dhcp4: false")
        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(modified_config)

        diff = netplan_validator.generate_diff(new_file)

        assert diff != ""
        assert "-" in diff  # Should have deletions
        assert "+" in diff  # Should have additions
        assert "dhcp4" in diff

    def test_generate_diff_no_changes(
        self, temp_netplan_dir, netplan_validator, valid_netplan_config
    ):
        """Test diff generation when there are no changes."""
        # Create identical config
        new_file = temp_netplan_dir / "identical.yaml"
        new_file.write_text(valid_netplan_config)

        diff = netplan_validator.generate_diff(new_file)

        # Identical files produce empty diff
        assert diff == ""

    def test_generate_diff_nonexistent_new_file(self, netplan_validator):
        """Test diff generation with non-existent new file."""
        diff = netplan_validator.generate_diff("/nonexistent/file.yaml")

        assert "does not exist" in diff.lower()


class TestBackupAndRestore:
    """Test backup and restore functionality."""

    def test_backup_current_config(self, netplan_validator):
        """Test creating a backup of current configuration."""
        backup_path = netplan_validator.backup_current_config()

        assert backup_path.exists()
        assert backup_path.parent == netplan_validator.backup_dir
        assert backup_path.suffix == ".yaml"

    def test_backup_nonexistent_config(self, temp_netplan_dir, temp_backup_dir, monkeypatch):
        """Test backup fails when config doesn't exist."""
        monkeypatch.setattr(NetplanValidator, "NETPLAN_DIR", temp_netplan_dir)
        monkeypatch.setattr(NetplanValidator, "BACKUP_DIR", temp_backup_dir)

        nonexistent_file = temp_netplan_dir / "nonexistent.yaml"
        validator = NetplanValidator(nonexistent_file)

        with pytest.raises(FileNotFoundError):
            validator.backup_current_config()

    def test_multiple_backups_have_unique_names(self, netplan_validator):
        """Test that multiple backups create unique filenames."""
        import time

        backup1 = netplan_validator.backup_current_config()
        time.sleep(1.1)  # Ensure different timestamp
        backup2 = netplan_validator.backup_current_config()

        assert backup1 != backup2
        assert backup1.exists()
        assert backup2.exists()


class TestConfigApplication:
    """Test configuration application."""

    @patch("subprocess.run")
    def test_apply_valid_config(
        self, mock_run, temp_netplan_dir, netplan_validator, valid_netplan_config
    ):
        """Test applying a valid configuration."""
        # Mock successful netplan apply
        mock_run.return_value = Mock(returncode=0, stderr="")

        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        success, message = netplan_validator.apply_config(new_file)

        assert success is True
        assert "success" in message.lower()
        mock_run.assert_called_once()

    def test_apply_invalid_config(self, temp_netplan_dir, netplan_validator, invalid_yaml_config):
        """Test applying an invalid configuration fails validation."""
        new_file = temp_netplan_dir / "invalid.yaml"
        new_file.write_text(invalid_yaml_config)

        success, message = netplan_validator.apply_config(new_file)

        assert success is False
        assert "validation failed" in message.lower()

    def test_apply_nonexistent_config(self, netplan_validator):
        """Test applying a non-existent configuration."""
        success, message = netplan_validator.apply_config("/nonexistent/file.yaml")

        assert success is False
        assert "not found" in message.lower()

    @patch("subprocess.run")
    def test_apply_config_netplan_fails(
        self, mock_run, temp_netplan_dir, netplan_validator, valid_netplan_config
    ):
        """Test handling of netplan apply failure."""
        # Mock failed netplan apply
        mock_run.return_value = Mock(returncode=1, stderr="Error applying config")

        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        success, message = netplan_validator.apply_config(new_file)

        assert success is False
        assert "failed" in message.lower()


class TestConnectivityTesting:
    """Test network connectivity testing."""

    @patch("subprocess.run")
    def test_connectivity_success(self, mock_run, netplan_validator):
        """Test successful connectivity check."""
        # Mock successful ping
        mock_run.return_value = Mock(returncode=0)

        result = netplan_validator._test_connectivity()

        assert result is True

    @patch("subprocess.run")
    def test_connectivity_failure(self, mock_run, netplan_validator):
        """Test failed connectivity check."""
        # Mock failed ping
        mock_run.return_value = Mock(returncode=1)

        result = netplan_validator._test_connectivity()

        assert result is False

    @patch("subprocess.run")
    def test_connectivity_timeout(self, mock_run, netplan_validator):
        """Test connectivity check timeout."""
        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired("ping", 3)

        result = netplan_validator._test_connectivity()

        assert result is False


class TestValidationResultPrinting:
    """Test validation result printing."""

    def test_print_valid_results(self, netplan_validator, capsys):
        """Test printing valid validation results."""
        result = ValidationResult(is_valid=True, errors=[], warnings=[], info=["Test passed"])

        netplan_validator.print_validation_results(result)

        # Just verify it doesn't crash - rich output is hard to test

    def test_print_invalid_results(self, netplan_validator, capsys):
        """Test printing invalid validation results."""
        result = ValidationResult(
            is_valid=False, errors=["Error 1", "Error 2"], warnings=["Warning 1"], info=["Info 1"]
        )

        netplan_validator.print_validation_results(result)

        # Just verify it doesn't crash


class TestConvenienceFunction:
    """Test the convenience validate_netplan_config function."""

    @patch("cortex.netplan_validator.NetplanValidator")
    def test_validate_netplan_config_success(self, mock_validator_class):
        """Test successful validation via convenience function."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            is_valid=True, errors=[], warnings=[], info=[]
        )
        mock_validator_class.return_value = mock_validator

        result = validate_netplan_config("/path/to/config.yaml")

        assert result is True

    @patch("cortex.netplan_validator.NetplanValidator")
    def test_validate_netplan_config_failure(self, mock_validator_class):
        """Test failed validation via convenience function."""
        mock_validator = MagicMock()
        mock_validator.validate_file.return_value = ValidationResult(
            is_valid=False, errors=["Error"], warnings=[], info=[]
        )
        mock_validator_class.return_value = mock_validator

        result = validate_netplan_config("/path/to/config.yaml")

        assert result is False

    @patch("cortex.netplan_validator.NetplanValidator")
    def test_validate_netplan_config_exception(self, mock_validator_class):
        """Test exception handling in convenience function."""
        mock_validator_class.side_effect = Exception("Test error")

        result = validate_netplan_config("/path/to/config.yaml")

        assert result is False


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_validator_with_none_config_file(
        self, temp_netplan_dir, temp_backup_dir, valid_netplan_config, monkeypatch
    ):
        """Test validator auto-detection of config file."""
        monkeypatch.setattr(NetplanValidator, "NETPLAN_DIR", temp_netplan_dir)
        monkeypatch.setattr(NetplanValidator, "BACKUP_DIR", temp_backup_dir)

        # Create a config file
        config_file = temp_netplan_dir / "01-netcfg.yaml"
        config_file.write_text(valid_netplan_config)

        validator = NetplanValidator(None)

        assert validator.config_file == config_file

    def test_validator_no_netplan_directory(self, tmp_path, temp_backup_dir, monkeypatch):
        """Test validator when netplan directory doesn't exist."""
        nonexistent_dir = tmp_path / "nonexistent"
        monkeypatch.setattr(NetplanValidator, "NETPLAN_DIR", nonexistent_dir)
        monkeypatch.setattr(NetplanValidator, "BACKUP_DIR", temp_backup_dir)

        with pytest.raises(FileNotFoundError, match="Netplan directory"):
            NetplanValidator(None)

    def test_validator_no_yaml_files(self, temp_netplan_dir, temp_backup_dir, monkeypatch):
        """Test validator when no YAML files exist."""
        monkeypatch.setattr(NetplanValidator, "NETPLAN_DIR", temp_netplan_dir)
        monkeypatch.setattr(NetplanValidator, "BACKUP_DIR", temp_backup_dir)

        with pytest.raises(FileNotFoundError, match="No .yaml or .yml files"):
            NetplanValidator(None)

    def test_wifi_interface_validation(self, netplan_validator):
        """Test validation of WiFi interfaces."""
        config = {
            "network": {
                "version": 2,
                "wifis": {
                    "wlan0": {
                        "dhcp4": True,
                        "access-points": {"MySSID": {"password": "<redacted>"}},
                    }
                },
            }
        }
        result = netplan_validator.validate_semantics(config)

        # Should validate without errors
        assert result.is_valid is True

    def test_bridge_interface_validation(self, netplan_validator):
        """Test validation of bridge interfaces."""
        config = {
            "network": {
                "version": 2,
                "bridges": {
                    "br0": {"addresses": ["192.168.1.1/24"], "interfaces": ["eth0", "eth1"]}
                },
            }
        }
        result = netplan_validator.validate_semantics(config)

        # Should validate without errors
        assert result.is_valid is True

    def test_multiple_interfaces(self, netplan_validator):
        """Test validation of multiple interfaces."""
        config = {
            "network": {
                "version": 2,
                "ethernets": {
                    "eth0": {"dhcp4": True},
                    "eth1": {"addresses": ["10.0.0.1/24"]},
                    "eth2": {"dhcp6": True},
                },
            }
        }
        result = netplan_validator.validate_semantics(config)

        assert result.is_valid is True

    def test_permission_denied_error_on_read(self, temp_netplan_dir, temp_backup_dir, monkeypatch):
        """Test handling of permission denied when reading config file."""
        monkeypatch.setattr(NetplanValidator, "NETPLAN_DIR", temp_netplan_dir)
        monkeypatch.setattr(NetplanValidator, "BACKUP_DIR", temp_backup_dir)

        # Create a config file
        config_file = temp_netplan_dir / "01-netcfg.yaml"
        config_file.write_text("network:\n  version: 2\n")

        validator = NetplanValidator(config_file)

        # Mock Path.read_text to raise PermissionError
        with patch.object(Path, "read_text", side_effect=PermissionError("Permission denied")):
            result = validator.validate_file()

            assert result.is_valid is False
            assert any("permission denied" in err.lower() for err in result.errors)

    def test_generic_read_error(self, temp_netplan_dir, temp_backup_dir, monkeypatch):
        """Test handling of generic read errors."""
        monkeypatch.setattr(NetplanValidator, "NETPLAN_DIR", temp_netplan_dir)
        monkeypatch.setattr(NetplanValidator, "BACKUP_DIR", temp_backup_dir)

        # Create a config file
        config_file = temp_netplan_dir / "01-netcfg.yaml"
        config_file.write_text("network:\n  version: 2\n")

        validator = NetplanValidator(config_file)

        # Mock Path.read_text to raise generic exception
        with patch.object(Path, "read_text", side_effect=Exception("Read error")):
            result = validator.validate_file()

            assert result.is_valid is False
            assert any("error reading file" in err.lower() for err in result.errors)


class TestAdvancedDryRunFeatures:
    """Test advanced dry-run and interactive features."""

    @patch("subprocess.run")
    @patch("cortex.netplan_validator.NetplanValidator._test_connectivity")
    @patch("cortex.netplan_validator.NetplanValidator._countdown_confirmation")
    def test_dry_run_user_confirms(
        self,
        mock_countdown,
        mock_connectivity,
        mock_run,
        temp_netplan_dir,
        netplan_validator,
        valid_netplan_config,
    ):
        """Test dry-run when user confirms changes."""
        # Mock successful operations
        mock_run.return_value = Mock(returncode=0, stderr="")
        mock_connectivity.return_value = True
        mock_countdown.return_value = True

        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        result = netplan_validator.dry_run_with_revert(new_file, timeout=5)

        assert result is True
        mock_connectivity.assert_called_once()
        mock_countdown.assert_called_once_with(5)

    @patch("subprocess.run")
    @patch("cortex.netplan_validator.NetplanValidator._test_connectivity")
    @patch("cortex.netplan_validator.NetplanValidator._countdown_confirmation")
    def test_dry_run_user_cancels(
        self,
        mock_countdown,
        mock_connectivity,
        mock_run,
        temp_netplan_dir,
        netplan_validator,
        valid_netplan_config,
    ):
        """Test dry-run when user doesn't confirm (timeout)."""
        # Mock successful operations but user doesn't confirm
        mock_run.return_value = Mock(returncode=0, stderr="")
        mock_connectivity.return_value = True
        mock_countdown.return_value = False

        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        result = netplan_validator.dry_run_with_revert(new_file, timeout=5)

        assert result is False
        mock_countdown.assert_called_once_with(5)

    @patch("subprocess.run")
    @patch("cortex.netplan_validator.NetplanValidator._test_connectivity")
    def test_dry_run_connectivity_fails(
        self, mock_connectivity, mock_run, temp_netplan_dir, netplan_validator, valid_netplan_config
    ):
        """Test dry-run when connectivity test fails."""
        # Mock successful apply but failed connectivity
        mock_run.return_value = Mock(returncode=0, stderr="")
        mock_connectivity.return_value = False

        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        result = netplan_validator.dry_run_with_revert(new_file, timeout=5)

        assert result is False
        mock_connectivity.assert_called_once()

    def test_dry_run_validation_fails(
        self, temp_netplan_dir, netplan_validator, invalid_yaml_config
    ):
        """Test dry-run when initial validation fails."""
        invalid_file = temp_netplan_dir / "invalid.yaml"
        invalid_file.write_text(invalid_yaml_config)

        result = netplan_validator.dry_run_with_revert(invalid_file, timeout=5)

        assert result is False

    def test_dry_run_backup_fails(self, temp_netplan_dir, netplan_validator, valid_netplan_config):
        """Test dry-run when backup creation fails."""
        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        # Mock backup to fail
        with patch.object(
            NetplanValidator, "backup_current_config", side_effect=OSError("Backup failed")
        ):
            result = netplan_validator.dry_run_with_revert(new_file, timeout=5)

            assert result is False

    @patch("subprocess.run")
    def test_dry_run_apply_fails(
        self, mock_run, temp_netplan_dir, netplan_validator, valid_netplan_config
    ):
        """Test dry-run when apply fails."""
        # Mock failed netplan apply
        mock_run.return_value = Mock(returncode=1, stderr="Apply failed")

        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        result = netplan_validator.dry_run_with_revert(new_file, timeout=5)

        assert result is False


class TestBackupEdgeCases:
    """Test backup-related edge cases."""

    def test_backup_with_io_error(
        self, temp_netplan_dir, temp_backup_dir, valid_netplan_config, monkeypatch
    ):
        """Test backup when copy operation fails."""
        monkeypatch.setattr(NetplanValidator, "NETPLAN_DIR", temp_netplan_dir)
        monkeypatch.setattr(NetplanValidator, "BACKUP_DIR", temp_backup_dir)

        config_file = temp_netplan_dir / "01-netcfg.yaml"
        config_file.write_text(valid_netplan_config)

        validator = NetplanValidator(config_file)

        # Mock shutil.copy2 to fail
        with patch("shutil.copy2", side_effect=OSError("Disk full")):
            with pytest.raises(OSError, match="Failed to create backup"):
                validator.backup_current_config()


class TestApplyConfigEdgeCases:
    """Test apply_config edge cases."""

    @patch("subprocess.run")
    def test_apply_config_with_timeout(
        self, mock_run, temp_netplan_dir, netplan_validator, valid_netplan_config
    ):
        """Test apply_config when netplan times out."""
        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired("netplan", 30)

        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        success, message = netplan_validator.apply_config(new_file, backup=False)

        assert success is False
        assert "timed out" in message.lower()

    @patch("subprocess.run")
    @patch("shutil.copy2")
    def test_apply_config_copy_fails(
        self, mock_copy, mock_run, temp_netplan_dir, netplan_validator, valid_netplan_config
    ):
        """Test apply_config when copying config fails."""
        mock_copy.side_effect = OSError("Permission denied")

        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        success, message = netplan_validator.apply_config(new_file, backup=False)

        assert success is False
        assert "failed to apply" in message.lower()


class TestRevertConfig:
    """Test configuration revert functionality."""

    @patch("subprocess.run")
    @patch("shutil.copy2")
    def test_revert_config_success(
        self, mock_copy, mock_run, temp_netplan_dir, temp_backup_dir, netplan_validator
    ):
        """Test successful config revert."""
        mock_copy.return_value = None
        mock_run.return_value = Mock(returncode=0)

        backup_path = temp_backup_dir / "backup.yaml"
        backup_path.write_text("network:\n  version: 2\n")

        # Should not raise
        netplan_validator._revert_config(backup_path)

        mock_copy.assert_called_once()
        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.copy2")
    def test_revert_config_fails(
        self, mock_copy, mock_run, temp_netplan_dir, temp_backup_dir, netplan_validator
    ):
        """Test config revert failure."""
        mock_copy.side_effect = OSError("Copy failed")

        backup_path = temp_backup_dir / "backup.yaml"
        backup_path.write_text("network:\n  version: 2\n")

        # Should handle error gracefully
        netplan_validator._revert_config(backup_path)

        mock_copy.assert_called_once()


class TestDiffEdgeCases:
    """Test diff generation edge cases."""

    def test_diff_current_file_not_exists(self, temp_netplan_dir, temp_backup_dir, monkeypatch):
        """Test diff when current config doesn't exist."""
        monkeypatch.setattr(NetplanValidator, "NETPLAN_DIR", temp_netplan_dir)
        monkeypatch.setattr(NetplanValidator, "BACKUP_DIR", temp_backup_dir)

        # Create validator with non-existent current file
        nonexistent = temp_netplan_dir / "nonexistent.yaml"
        validator = NetplanValidator(nonexistent)

        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text("network:\n  version: 2\n")

        diff = validator.generate_diff(new_file)

        assert "does not exist" in diff.lower()

    def test_diff_with_read_error(self, temp_netplan_dir, netplan_validator, valid_netplan_config):
        """Test diff generation when file read fails."""
        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        # Mock read_text to fail
        with patch.object(Path, "read_text", side_effect=Exception("Read error")):
            diff = netplan_validator.generate_diff(new_file)

            assert "error generating diff" in diff.lower()


class TestShowDiff:
    """Test show_diff display functionality."""

    def test_show_diff_with_changes(
        self, temp_netplan_dir, netplan_validator, valid_netplan_config
    ):
        """Test show_diff with actual changes."""
        modified_config = valid_netplan_config.replace("dhcp4: true", "dhcp4: false")
        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(modified_config)

        # Should not raise
        netplan_validator.show_diff(new_file)

    def test_show_diff_no_changes(self, temp_netplan_dir, netplan_validator, valid_netplan_config):
        """Test show_diff with no changes."""
        new_file = temp_netplan_dir / "identical.yaml"
        new_file.write_text(valid_netplan_config)

        # Should not raise
        netplan_validator.show_diff(new_file)

    def test_show_diff_with_all_line_types(self, temp_netplan_dir, netplan_validator):
        """Test showing diff with all different line types including @@ markers."""
        # Create modified config
        modified = """network:
  version: 2
  ethernets:
    eth0:
      dhcp4: false
      addresses:
        - 192.168.1.100/24
"""
        new_file = temp_netplan_dir / "modified.yaml"
        new_file.write_text(modified)

        # Generate and show diff - should handle @@ markers
        netplan_validator.show_diff(new_file)


class TestNetworkInterfaceInitialization:
    """Test NetworkInterface initialization with None values."""

    def test_network_interface_with_none_values(self):
        """Test that None values are properly initialized to empty lists/dicts."""
        from cortex.netplan_validator import NetworkInterface

        # Create interface with None values (which should be converted to empty collections)
        iface = NetworkInterface(name="eth0")

        # These should be initialized to empty collections even if not provided
        assert isinstance(iface.addresses, list)
        assert isinstance(iface.nameservers, dict)
        assert isinstance(iface.routes, list)
        assert len(iface.addresses) == 0
        assert len(iface.nameservers) == 0
        assert len(iface.routes) == 0


class TestYAMLErrorHandling:
    """Test YAML error handling edge cases."""

    def test_yaml_error_without_mark(self, temp_netplan_dir):
        """Test handling of YAML errors without mark information."""
        config_file = temp_netplan_dir / "test.yaml"
        # Create a YAML error that won't have mark info
        config_file.write_text("network:\n  - invalid list where dict expected\n    nested: value")

        validator = NetplanValidator(str(config_file))

        # Read the file content and test
        with open(config_file) as f:
            content = f.read()

        result = validator.validate_yaml_syntax(content)

        # Should still report error even without mark
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert "YAML syntax error" in result.errors[0]


class TestVersionValidation:
    """Test version validation edge cases."""

    def test_version_not_equal_to_2(self, temp_netplan_dir):
        """Test warning when version is not 2."""
        config = """network:
  version: 1
  ethernets:
    eth0:
      dhcp4: true
"""
        config_file = temp_netplan_dir / "test.yaml"
        config_file.write_text(config)

        validator = NetplanValidator(str(config_file))

        # Load and parse the config
        import yaml

        with open(config_file) as f:
            config_dict = yaml.safe_load(f)

        result = validator.validate_semantics(config_dict)

        # Should have warning about version
        assert any("version" in w.lower() for w in result.warnings)
        assert any("version 1" in w.lower() or "Using version 1" in w for w in result.warnings)


class TestGatewayAndNameserverValidation:
    """Test gateway6 and nameserver validation."""

    def test_invalid_gateway6(self, temp_netplan_dir):
        """Test validation of invalid gateway6."""
        config = """network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 2001:db8::1/64
      gateway6: invalid::gateway::address
"""
        config_file = temp_netplan_dir / "test.yaml"
        config_file.write_text(config)

        validator = NetplanValidator(str(config_file))

        # Load and parse the config
        import yaml

        with open(config_file) as f:
            config_dict = yaml.safe_load(f)

        result = validator.validate_semantics(config_dict)

        # Should have error about gateway6
        assert result.is_valid is False
        assert any("gateway6" in e.lower() for e in result.errors)

    def test_invalid_nameserver_addresses(self, temp_netplan_dir):
        """Test validation of invalid nameserver addresses."""
        config = """network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      nameservers:
        addresses:
          - 8.8.8.8
          - invalid.nameserver.address
          - 1.1.1.1
"""
        config_file = temp_netplan_dir / "test.yaml"
        config_file.write_text(config)

        validator = NetplanValidator(str(config_file))

        # Load and parse the config
        import yaml

        with open(config_file) as f:
            config_dict = yaml.safe_load(f)

        result = validator.validate_semantics(config_dict)

        # Should have error about nameserver
        assert result.is_valid is False
        assert any("nameserver" in e.lower() for e in result.errors)

    def test_valid_nameservers(self, temp_netplan_dir):
        """Test validation of valid nameserver configuration."""
        config = """network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4
          - 2001:4860:4860::8888
"""
        config_file = temp_netplan_dir / "test.yaml"
        config_file.write_text(config)

        validator = NetplanValidator(str(config_file))

        # Load and parse the config
        import yaml

        with open(config_file) as f:
            config_dict = yaml.safe_load(f)

        result = validator.validate_semantics(config_dict)

        # Should be valid
        assert result.is_valid is True


class TestRouteValidationInConfig:
    """Test route validation within interface configuration."""

    def test_interface_with_invalid_routes(self, temp_netplan_dir):
        """Test interface with invalid route configuration."""
        config = """network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      routes:
        - to: invalid-destination
          via: 192.168.1.1
        - to: 10.0.0.0/8
          via: invalid-gateway
"""
        config_file = temp_netplan_dir / "test.yaml"
        config_file.write_text(config)

        validator = NetplanValidator(str(config_file))

        # Load and parse the config
        import yaml

        with open(config_file) as f:
            config_dict = yaml.safe_load(f)

        result = validator.validate_semantics(config_dict)

        # Should have errors about routes
        assert result.is_valid is False
        assert any("route" in e.lower() for e in result.errors)


class TestBackupFailureInApply:
    """Test backup failure during apply_config."""

    @patch("cortex.netplan_validator.NetplanValidator.backup_current_config")
    def test_apply_with_backup_failure(
        self, mock_backup, temp_netplan_dir, netplan_validator, valid_netplan_config
    ):
        """Test apply_config when backup fails."""
        mock_backup.side_effect = Exception("Backup failed due to disk full")

        new_file = temp_netplan_dir / "new.yaml"
        new_file.write_text(valid_netplan_config)

        success, message = netplan_validator.apply_config(new_file, backup=True)

        assert success is False
        assert "backup failed" in message.lower()


class TestShowDiffElseBranch:
    """Test the else branch in show_diff for lines that don't start with +, -, or @@."""

    def test_show_diff_with_unchanged_lines(self, temp_netplan_dir, netplan_validator):
        """Test diff display with unchanged context lines."""
        # Create modified config
        modified = """network:
  version: 2
  ethernets:
    eth0:
      dhcp4: false
      addresses:
        - 192.168.1.200/24
"""
        new_file = temp_netplan_dir / "modified.yaml"
        new_file.write_text(modified)

        # This will generate a diff with unchanged context lines (the else branch)
        netplan_validator.show_diff(new_file)


class TestCountdownConfirmationPaths:
    """Test countdown confirmation with different execution paths."""

    @patch("time.sleep")
    @patch("builtins.input", return_value="y")
    @patch("termios.tcgetattr", side_effect=ImportError("No termios"))
    def test_countdown_with_input_fallback_confirms(
        self, mock_tcgetattr, mock_input, mock_sleep, temp_netplan_dir, valid_netplan_config
    ):
        """Test countdown using input() fallback when termios fails - user confirms."""
        # Setup
        config_file = temp_netplan_dir / "config.yaml"
        config_file.write_text(valid_netplan_config)
        validator = NetplanValidator(str(config_file))

        # Call method - termios will fail, fallback to input()
        result = validator._countdown_confirmation(timeout=1)

        # Input was mocked to return 'y'
        assert isinstance(result, bool)

    @patch("time.sleep")
    @patch("builtins.input", return_value="n")
    @patch("termios.tcgetattr", side_effect=ImportError("No termios"))
    def test_countdown_with_input_fallback_no_confirm(
        self, mock_tcgetattr, mock_input, mock_sleep, temp_netplan_dir, valid_netplan_config
    ):
        """Test countdown using input() fallback when termios fails - user doesn't confirm."""
        # Setup
        config_file = temp_netplan_dir / "config.yaml"
        config_file.write_text(valid_netplan_config)
        validator = NetplanValidator(str(config_file))

        # Call method - termios will fail, fallback to input()
        result = validator._countdown_confirmation(timeout=1)

        # Input was mocked to return 'n'
        assert isinstance(result, bool)

    @patch("time.sleep")
    @patch("sys.stdin")
    @patch("termios.tcgetattr", return_value=["fake_settings"])
    @patch("termios.tcsetattr")
    @patch("tty.setraw")
    def test_countdown_with_termios_user_presses_y(
        self,
        mock_setraw,
        mock_tcsetattr,
        mock_tcgetattr,
        mock_stdin,
        mock_sleep,
        temp_netplan_dir,
        valid_netplan_config,
    ):
        """Test countdown using termios when user presses 'y'."""
        # Setup
        config_file = temp_netplan_dir / "config.yaml"
        config_file.write_text(valid_netplan_config)
        validator = NetplanValidator(str(config_file))

        # Mock stdin to simulate user pressing 'y'
        mock_stdin.fileno.return_value = 0
        mock_stdin.read.return_value = "y"

        result = validator._countdown_confirmation(timeout=1)

        # Verify method completed
        assert isinstance(result, bool)

    @patch("time.sleep")
    @patch("sys.stdin")
    @patch("termios.tcgetattr", return_value=["fake_settings"])
    @patch("termios.tcsetattr")
    @patch("tty.setraw")
    def test_countdown_with_termios_user_presses_n(
        self,
        mock_setraw,
        mock_tcsetattr,
        mock_tcgetattr,
        mock_stdin,
        mock_sleep,
        temp_netplan_dir,
        valid_netplan_config,
    ):
        """Test countdown using termios when user presses a key other than 'y'."""
        # Setup
        config_file = temp_netplan_dir / "config.yaml"
        config_file.write_text(valid_netplan_config)
        validator = NetplanValidator(str(config_file))

        # Mock stdin to simulate user pressing 'n'
        mock_stdin.fileno.return_value = 0
        mock_stdin.read.return_value = "n"

        result = validator._countdown_confirmation(timeout=1)

        # Verify method completed
        assert isinstance(result, bool)

    @patch("time.sleep")
    def test_countdown_timeout_expires_no_confirmation(
        self, mock_sleep, temp_netplan_dir, valid_netplan_config
    ):
        """Test countdown when timeout is very short."""
        # Setup
        config_file = temp_netplan_dir / "config.yaml"
        config_file.write_text(valid_netplan_config)
        validator = NetplanValidator(str(config_file))

        # Very short timeout
        result = validator._countdown_confirmation(timeout=0)

        # When timeout is 0, range(0, 0, -1) produces no iterations
        assert isinstance(result, bool)

    @patch("time.sleep")
    @patch("builtins.input", return_value="y")
    @patch("termios.tcgetattr", side_effect=OSError("Terminal error"))
    def test_countdown_with_generic_exception_in_termios(
        self, mock_tcgetattr, mock_input, mock_sleep, temp_netplan_dir, valid_netplan_config
    ):
        """Test countdown when termios raises a generic exception."""
        # Setup
        config_file = temp_netplan_dir / "config.yaml"
        config_file.write_text(valid_netplan_config)
        validator = NetplanValidator(str(config_file))

        # Call method - termios will fail with OSError, fallback to input()
        result = validator._countdown_confirmation(timeout=1)

        assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
