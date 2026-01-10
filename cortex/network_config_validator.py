"""
Network Configuration Validator for Netplan/NetworkManager

Validates and analyzes network configurations for Debian/Ubuntu systems.
Provides YAML syntax validation, semantic correctness checks, diff display,
dry-run mode with revert timer, and plain English error messages.

Features:
- Validates YAML syntax before apply
- Checks semantic correctness (valid IPs, routes, gateways)
- Shows diff of what will change
- Dry-run mode with automatic revert timer
- Plain English error messages with suggestions

Issue: #445
"""

import ipaddress
import logging
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()


# === Enums ===


class ValidationSeverity(Enum):
    """Severity level for validation issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ConfigType(Enum):
    """Type of network configuration system."""

    NETPLAN = "netplan"
    NETWORKMANAGER = "networkmanager"
    UNKNOWN = "unknown"


# === Data Classes ===


@dataclass
class ValidationIssue:
    """A single validation issue found in configuration."""

    rule_id: str
    message: str
    severity: ValidationSeverity
    file_path: str = ""
    line_number: int = 0
    suggestion: str = ""
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "rule_id": self.rule_id,
            "message": self.message,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "suggestion": self.suggestion,
            "context": self.context,
        }


@dataclass
class ValidationReport:
    """Complete validation report for network configuration."""

    config_type: ConfigType
    is_valid: bool
    timestamp: str
    config_files: list[str] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def info_count(self) -> int:
        """Count of info-level issues."""
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.INFO)

    @property
    def warning_count(self) -> int:
        """Count of warning-level issues."""
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.WARNING)

    @property
    def error_count(self) -> int:
        """Count of error-level issues."""
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.ERROR)

    @property
    def critical_count(self) -> int:
        """Count of critical issues."""
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.CRITICAL)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "config_type": self.config_type.value,
            "is_valid": self.is_valid,
            "timestamp": self.timestamp,
            "config_files": self.config_files,
            "issues": [i.to_dict() for i in self.issues],
            "summary": {
                "info": self.info_count,
                "warnings": self.warning_count,
                "errors": self.error_count,
                "critical": self.critical_count,
            },
        }


@dataclass
class ConfigDiff:
    """Represents a diff between two configurations."""

    file_path: str
    original: str
    modified: str
    changes: list[str] = field(default_factory=list)


# === Plain English Error Messages ===

ERROR_MESSAGES = {
    "yaml_syntax": (
        "Your configuration file has a formatting error. "
        "YAML is very picky about spaces and indentation."
    ),
    "invalid_ip": (
        "The IP address '{value}' doesn't look right. "
        "IP addresses should be like 192.168.1.100 or 10.0.0.1."
    ),
    "invalid_cidr": (
        "The network notation '{value}' isn't valid. "
        "It should be like 192.168.1.0/24 (IP address followed by /subnet)."
    ),
    "invalid_gateway": (
        "The gateway '{value}' doesn't appear to be a valid IP address. "
        "This should be your router's IP address."
    ),
    "invalid_dns": (
        "The DNS server '{value}' isn't a valid IP address. "
        "Common DNS servers are 8.8.8.8 (Google) or 1.1.1.1 (Cloudflare)."
    ),
    "invalid_mac": (
        "The MAC address '{value}' isn't in the right format. "
        "It should look like 00:11:22:33:44:55 or 00-11-22-33-44-55."
    ),
    "missing_renderer": (
        "Your Netplan config doesn't specify a renderer. "
        "Add 'renderer: networkd' or 'renderer: NetworkManager'."
    ),
    "duplicate_ip": (
        "The IP address '{value}' is used more than once. "
        "Each interface needs a unique IP address."
    ),
    "gateway_unreachable": (
        "The gateway '{gateway}' isn't in the same network as your IP '{ip}'. "
        "Make sure they're on the same subnet."
    ),
    "dhcp_with_static": (
        "You have both DHCP enabled and static IP addresses set. "
        "Usually you want one or the other, not both."
    ),
    "missing_version": (
        "Your Netplan config is missing 'network: version: 2'. "
        "This is required for Netplan to work properly."
    ),
    "indent_error": (
        "There's an indentation problem around line {line}. "
        "Make sure you're using consistent spaces (not tabs) for indentation."
    ),
    "unknown_key": (
        "The setting '{key}' isn't recognized. "
        "Check the spelling or refer to Netplan documentation."
    ),
    "file_permission": (
        "The config file should only be readable by root for security. "
        "Run: sudo chmod 600 {file}"
    ),
    "empty_config": (
        "The configuration file appears to be empty or only has comments. "
        "You need to define at least one network interface."
    ),
}


def get_error_message(error_type: str, **kwargs: Any) -> str:
    """Get a plain English error message with variable substitution."""
    template = ERROR_MESSAGES.get(error_type, f"Configuration error: {error_type}")
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


# === Validation Functions ===


def validate_ip_address(ip: str) -> tuple[bool, str | None]:
    """
    Validate an IPv4 or IPv6 address.

    Args:
        ip: IP address string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        ipaddress.ip_address(ip)
        return (True, None)
    except ValueError:
        return (False, get_error_message("invalid_ip", value=ip))


def validate_cidr(cidr: str) -> tuple[bool, str | None]:
    """
    Validate a CIDR notation network address (e.g., 192.168.1.0/24).

    Args:
        cidr: CIDR notation string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        ipaddress.ip_network(cidr, strict=False)
        return (True, None)
    except ValueError:
        return (False, get_error_message("invalid_cidr", value=cidr))


def validate_mac_address(mac: str) -> tuple[bool, str | None]:
    """
    Validate a MAC address.

    Args:
        mac: MAC address string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Support both : and - separators
    mac_pattern = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
    if re.match(mac_pattern, mac):
        return (True, None)
    return (False, get_error_message("invalid_mac", value=mac))


def validate_gateway_reachable(gateway: str, ip_cidr: str) -> tuple[bool, str | None]:
    """
    Check if a gateway is reachable from the given IP/subnet.

    Args:
        gateway: Gateway IP address
        ip_cidr: IP address with CIDR notation (e.g., 192.168.1.100/24)

    Returns:
        Tuple of (is_reachable, error_message)
    """
    try:
        network = ipaddress.ip_network(ip_cidr, strict=False)
        gateway_ip = ipaddress.ip_address(gateway)

        if gateway_ip in network:
            return (True, None)
        else:
            ip_only = ip_cidr.split("/")[0]
            return (False, get_error_message("gateway_unreachable", gateway=gateway, ip=ip_only))
    except ValueError:
        return (False, "Could not validate gateway reachability")


# === Main Validator Class ===


class NetworkConfigValidator:
    """
    Validates Netplan and NetworkManager configurations.

    Features:
    - YAML syntax validation
    - Semantic validation (IPs, routes, gateways)
    - Configuration diff display
    - Dry-run mode with automatic revert
    - Plain English error messages
    """

    def __init__(
        self,
        netplan_dir: str = "/etc/netplan",
        nm_dir: str = "/etc/NetworkManager",
    ):
        """
        Initialize the network configuration validator.

        Args:
            netplan_dir: Path to Netplan configuration directory
            nm_dir: Path to NetworkManager configuration directory
        """
        self.netplan_dir = Path(netplan_dir)
        self.nm_dir = Path(nm_dir)
        self._revert_timer: threading.Timer | None = None
        self._backup_configs: dict[str, str] = {}

    # === Detection Methods ===

    def detect_config_system(self) -> ConfigType:
        """
        Detect which network configuration system is in use.

        Returns:
            ConfigType enum indicating the active system
        """
        # Check for Netplan first (common on Ubuntu 18.04+)
        if self.netplan_dir.exists():
            netplan_files = list(self.netplan_dir.glob("*.yaml"))
            if netplan_files:
                return ConfigType.NETPLAN

        # Check for NetworkManager
        if self.nm_dir.exists():
            nm_conf = self.nm_dir / "NetworkManager.conf"
            if nm_conf.exists():
                return ConfigType.NETWORKMANAGER

        # Also check via systemd
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "NetworkManager"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return ConfigType.NETWORKMANAGER
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return ConfigType.UNKNOWN

    def get_config_files(self) -> list[Path]:
        """
        Get all configuration files for the detected system.

        Returns:
            List of Path objects to configuration files
        """
        config_type = self.detect_config_system()

        if config_type == ConfigType.NETPLAN:
            if self.netplan_dir.exists():
                return sorted(self.netplan_dir.glob("*.yaml"))
            return []

        elif config_type == ConfigType.NETWORKMANAGER:
            files = []
            # Main config
            main_conf = self.nm_dir / "NetworkManager.conf"
            if main_conf.exists():
                files.append(main_conf)
            # Connection profiles
            conn_dir = self.nm_dir / "system-connections"
            if conn_dir.exists():
                files.extend(sorted(conn_dir.glob("*")))
            return files

        return []

    # === YAML Validation ===

    def validate_yaml_syntax(self, file_path: Path) -> list[ValidationIssue]:
        """
        Validate YAML file syntax.

        Args:
            file_path: Path to the YAML file

        Returns:
            List of validation issues found
        """
        issues: list[ValidationIssue] = []

        try:
            # Import yaml here to handle optional dependency
            import yaml
        except ImportError:
            issues.append(
                ValidationIssue(
                    rule_id="YAML001",
                    message="PyYAML is not installed. Cannot validate YAML syntax.",
                    severity=ValidationSeverity.WARNING,
                    file_path=str(file_path),
                    suggestion="Install with: pip install pyyaml",
                )
            )
            return issues

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                issues.append(
                    ValidationIssue(
                        rule_id="YAML002",
                        message=get_error_message("empty_config"),
                        severity=ValidationSeverity.ERROR,
                        file_path=str(file_path),
                    )
                )
                return issues

            yaml.safe_load(content)

        except yaml.YAMLError as e:
            error_msg = str(e)
            line_num = 0

            # Extract line number from YAML error
            if hasattr(e, "problem_mark") and e.problem_mark:
                line_num = e.problem_mark.line + 1

            # Provide plain English explanation
            plain_msg = get_error_message("yaml_syntax")

            if "expected" in error_msg.lower() and "indent" in error_msg.lower():
                plain_msg = get_error_message("indent_error", line=line_num)
            elif "mapping values" in error_msg.lower():
                plain_msg = (
                    f"There's a problem with the format around line {line_num}. "
                    "Make sure each setting has a colon followed by a space, "
                    "like 'addresses: [192.168.1.1/24]'"
                )

            issues.append(
                ValidationIssue(
                    rule_id="YAML003",
                    message=plain_msg,
                    severity=ValidationSeverity.ERROR,
                    file_path=str(file_path),
                    line_number=line_num,
                    context=error_msg,
                    suggestion="Check indentation uses spaces (not tabs) and colons are followed by spaces",
                )
            )

        except (OSError, PermissionError) as e:
            issues.append(
                ValidationIssue(
                    rule_id="YAML004",
                    message=f"Cannot read file: {e}",
                    severity=ValidationSeverity.ERROR,
                    file_path=str(file_path),
                )
            )

        return issues

    # === Netplan Validation ===

    def validate_netplan_config(self, file_path: Path) -> list[ValidationIssue]:
        """
        Validate a Netplan configuration file.

        Args:
            file_path: Path to the Netplan YAML file

        Returns:
            List of validation issues found
        """
        issues: list[ValidationIssue] = []

        # First check YAML syntax
        yaml_issues = self.validate_yaml_syntax(file_path)
        if any(i.severity == ValidationSeverity.ERROR for i in yaml_issues):
            return yaml_issues  # Can't continue if YAML is broken

        issues.extend(yaml_issues)

        try:
            import yaml
        except ImportError:
            return issues

        try:
            with open(file_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not config:
                return issues

            # Check for network key
            if "network" not in config:
                issues.append(
                    ValidationIssue(
                        rule_id="NP001",
                        message=get_error_message("missing_version"),
                        severity=ValidationSeverity.ERROR,
                        file_path=str(file_path),
                        suggestion="Add 'network:\\n  version: 2' at the start of your config",
                    )
                )
                return issues

            network = config["network"]

            # Check version
            if "version" not in network:
                issues.append(
                    ValidationIssue(
                        rule_id="NP002",
                        message="Missing version number in network configuration.",
                        severity=ValidationSeverity.WARNING,
                        file_path=str(file_path),
                        suggestion="Add 'version: 2' under the 'network:' key",
                    )
                )

            # Check renderer
            if "renderer" not in network:
                issues.append(
                    ValidationIssue(
                        rule_id="NP003",
                        message=get_error_message("missing_renderer"),
                        severity=ValidationSeverity.INFO,
                        file_path=str(file_path),
                    )
                )

            # Validate each interface type
            for iface_type in ["ethernets", "wifis", "bonds", "bridges", "vlans"]:
                if iface_type in network:
                    iface_issues = self._validate_interfaces(
                        network[iface_type], iface_type, str(file_path)
                    )
                    issues.extend(iface_issues)

        except (OSError, yaml.YAMLError) as e:
            issues.append(
                ValidationIssue(
                    rule_id="NP099",
                    message=f"Error reading config: {e}",
                    severity=ValidationSeverity.ERROR,
                    file_path=str(file_path),
                )
            )

        return issues

    def _validate_interfaces(
        self, interfaces: dict[str, Any], iface_type: str, file_path: str
    ) -> list[ValidationIssue]:
        """Validate interface configurations."""
        issues: list[ValidationIssue] = []

        if not isinstance(interfaces, dict):
            return issues

        seen_ips: set[str] = set()

        for iface_name, iface_config in interfaces.items():
            if not isinstance(iface_config, dict):
                continue

            # Check for DHCP + static IP conflict
            dhcp4 = iface_config.get("dhcp4", False)
            dhcp6 = iface_config.get("dhcp6", False)
            addresses = iface_config.get("addresses", [])

            if (dhcp4 or dhcp6) and addresses:
                issues.append(
                    ValidationIssue(
                        rule_id="NP010",
                        message=get_error_message("dhcp_with_static"),
                        severity=ValidationSeverity.WARNING,
                        file_path=file_path,
                        context=f"Interface: {iface_name}",
                    )
                )

            # Validate addresses
            for addr in addresses:
                if isinstance(addr, str):
                    is_valid, error = validate_cidr(addr)
                    if not is_valid:
                        issues.append(
                            ValidationIssue(
                                rule_id="NP011",
                                message=error or f"Invalid address: {addr}",
                                severity=ValidationSeverity.ERROR,
                                file_path=file_path,
                                context=f"Interface: {iface_name}",
                            )
                        )
                    else:
                        # Check for duplicate IPs
                        ip_only = addr.split("/")[0]
                        if ip_only in seen_ips:
                            issues.append(
                                ValidationIssue(
                                    rule_id="NP012",
                                    message=get_error_message("duplicate_ip", value=ip_only),
                                    severity=ValidationSeverity.ERROR,
                                    file_path=file_path,
                                    context=f"Interface: {iface_name}",
                                )
                            )
                        seen_ips.add(ip_only)

            # Validate gateway (legacy gateway4/gateway6)
            for gw_key in ["gateway4", "gateway6"]:
                if gw_key in iface_config:
                    gateway = iface_config[gw_key]
                    is_valid, error = validate_ip_address(str(gateway))
                    if not is_valid:
                        issues.append(
                            ValidationIssue(
                                rule_id="NP013",
                                message=get_error_message("invalid_gateway", value=gateway),
                                severity=ValidationSeverity.ERROR,
                                file_path=file_path,
                                context=f"Interface: {iface_name}",
                            )
                        )
                    elif addresses:
                        # Check gateway reachability
                        for addr in addresses:
                            if isinstance(addr, str):
                                is_reach, reach_error = validate_gateway_reachable(
                                    str(gateway), addr
                                )
                                if not is_reach:
                                    issues.append(
                                        ValidationIssue(
                                            rule_id="NP014",
                                            message=reach_error or "Gateway unreachable",
                                            severity=ValidationSeverity.WARNING,
                                            file_path=file_path,
                                            context=f"Interface: {iface_name}",
                                        )
                                    )

            # Validate routes
            routes = iface_config.get("routes", [])
            for route in routes:
                if isinstance(route, dict):
                    route_issues = self._validate_route(route, iface_name, file_path)
                    issues.extend(route_issues)

            # Validate nameservers
            nameservers = iface_config.get("nameservers", {})
            if isinstance(nameservers, dict):
                dns_addresses = nameservers.get("addresses", [])
                for dns in dns_addresses:
                    is_valid, error = validate_ip_address(str(dns))
                    if not is_valid:
                        issues.append(
                            ValidationIssue(
                                rule_id="NP015",
                                message=get_error_message("invalid_dns", value=dns),
                                severity=ValidationSeverity.ERROR,
                                file_path=file_path,
                                context=f"Interface: {iface_name}",
                            )
                        )

            # Validate MAC address
            macaddress = iface_config.get("macaddress")
            if macaddress:
                is_valid, error = validate_mac_address(str(macaddress))
                if not is_valid:
                    issues.append(
                        ValidationIssue(
                            rule_id="NP016",
                            message=error or f"Invalid MAC: {macaddress}",
                            severity=ValidationSeverity.ERROR,
                            file_path=file_path,
                            context=f"Interface: {iface_name}",
                        )
                    )

        return issues

    def _validate_route(
        self, route: dict[str, Any], iface_name: str, file_path: str
    ) -> list[ValidationIssue]:
        """Validate a single route configuration."""
        issues: list[ValidationIssue] = []

        # Validate 'to' destination
        if "to" in route:
            to_dest = route["to"]
            if to_dest != "default":
                is_valid, error = validate_cidr(str(to_dest))
                if not is_valid:
                    issues.append(
                        ValidationIssue(
                            rule_id="NP020",
                            message=f"Invalid route destination '{to_dest}': {error}",
                            severity=ValidationSeverity.ERROR,
                            file_path=file_path,
                            context=f"Interface: {iface_name}",
                        )
                    )

        # Validate 'via' gateway
        if "via" in route:
            via_gw = route["via"]
            is_valid, error = validate_ip_address(str(via_gw))
            if not is_valid:
                issues.append(
                    ValidationIssue(
                        rule_id="NP021",
                        message=f"Invalid route gateway '{via_gw}': {error}",
                        severity=ValidationSeverity.ERROR,
                        file_path=file_path,
                        context=f"Interface: {iface_name}",
                    )
                )

        return issues

    # === Full Validation ===

    def validate(self) -> ValidationReport:
        """
        Run full validation on all detected configuration files.

        Returns:
            ValidationReport with all issues found
        """
        config_type = self.detect_config_system()
        config_files = self.get_config_files()
        all_issues: list[ValidationIssue] = []

        for config_file in config_files:
            if config_type == ConfigType.NETPLAN:
                issues = self.validate_netplan_config(config_file)
            else:
                issues = self.validate_yaml_syntax(config_file)
            all_issues.extend(issues)

        # Check file permissions
        for config_file in config_files:
            perm_issues = self._check_file_permissions(config_file)
            all_issues.extend(perm_issues)

        # Determine overall validity
        is_valid = not any(
            i.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
            for i in all_issues
        )

        return ValidationReport(
            config_type=config_type,
            is_valid=is_valid,
            timestamp=datetime.now().isoformat(),
            config_files=[str(f) for f in config_files],
            issues=all_issues,
        )

    def _check_file_permissions(self, file_path: Path) -> list[ValidationIssue]:
        """Check if file permissions are secure."""
        issues: list[ValidationIssue] = []

        try:
            mode = file_path.stat().st_mode
            # Check if file is world-readable (others can read)
            if mode & 0o004:
                issues.append(
                    ValidationIssue(
                        rule_id="SEC001",
                        message=get_error_message("file_permission", file=str(file_path)),
                        severity=ValidationSeverity.WARNING,
                        file_path=str(file_path),
                        suggestion=f"Run: sudo chmod 600 {file_path}",
                    )
                )
        except OSError:
            pass

        return issues

    # === Diff Display ===

    def show_diff(self, original_path: Path, new_content: str) -> ConfigDiff:
        """
        Generate and display a diff between original config and new content.

        Args:
            original_path: Path to the original configuration file
            new_content: The proposed new configuration content

        Returns:
            ConfigDiff object with the differences
        """
        try:
            with open(original_path, encoding="utf-8") as f:
                original_content = f.read()
        except (OSError, FileNotFoundError):
            original_content = ""

        # Generate unified diff
        import difflib

        diff_lines = list(
            difflib.unified_diff(
                original_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=str(original_path),
                tofile=f"{original_path} (proposed)",
                lineterm="",
            )
        )

        return ConfigDiff(
            file_path=str(original_path),
            original=original_content,
            modified=new_content,
            changes=diff_lines,
        )

    def print_diff(self, diff: ConfigDiff) -> None:
        """Print a colorized diff to the console."""
        if not diff.changes:
            console.print("[dim]No changes detected[/dim]")
            return

        console.print(f"\n[bold]Changes for {diff.file_path}:[/bold]")
        diff_text = "".join(diff.changes)
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
        console.print(syntax)

    # === Dry-Run Mode ===

    def dry_run(self, timeout_seconds: int = 120) -> bool:
        """
        Apply configuration in dry-run mode with automatic revert.

        This applies the configuration temporarily and automatically reverts
        after the timeout unless the user confirms the changes.

        Args:
            timeout_seconds: Seconds before automatic revert (default: 120)

        Returns:
            True if configuration was applied and confirmed, False otherwise
        """
        config_type = self.detect_config_system()

        if config_type != ConfigType.NETPLAN:
            console.print(
                "[yellow]Dry-run mode is currently only supported for Netplan[/yellow]"
            )
            return False

        # Backup current configs
        if not self._backup_configs_to_memory():
            console.print("[red]Failed to backup current configuration[/red]")
            return False

        console.print(
            f"\n[yellow]Applying configuration in dry-run mode...[/yellow]"
            f"\n[yellow]Configuration will automatically revert in {timeout_seconds} seconds[/yellow]"
            f"\n[yellow]if you don't confirm the changes.[/yellow]\n"
        )

        # Start revert timer
        self._revert_timer = threading.Timer(
            timeout_seconds, self._auto_revert, args=[config_type]
        )
        self._revert_timer.start()

        # Apply configuration
        try:
            result = subprocess.run(
                ["sudo", "netplan", "try", f"--timeout={timeout_seconds}"],
                capture_output=True,
                text=True,
                timeout=timeout_seconds + 30,
            )

            if result.returncode == 0:
                console.print("[green]Configuration applied successfully![/green]")
                self._cancel_revert_timer()
                self._backup_configs.clear()
                return True
            else:
                console.print(f"[red]Failed to apply configuration:[/red]\n{result.stderr}")
                self._revert_configs()
                return False

        except subprocess.TimeoutExpired:
            console.print("[yellow]Timeout expired, configuration reverted[/yellow]")
            return False
        except FileNotFoundError:
            console.print("[red]netplan command not found. Is Netplan installed?[/red]")
            self._cancel_revert_timer()
            return False
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Error applying configuration: {e}[/red]")
            self._revert_configs()
            return False

    def _backup_configs_to_memory(self) -> bool:
        """Backup current configuration files to memory."""
        self._backup_configs.clear()
        config_files = self.get_config_files()

        for config_file in config_files:
            try:
                with open(config_file, encoding="utf-8") as f:
                    self._backup_configs[str(config_file)] = f.read()
            except (OSError, PermissionError) as e:
                logger.warning(f"Could not backup {config_file}: {e}")
                return False

        return True

    def _auto_revert(self, config_type: ConfigType) -> None:
        """Automatically revert configuration after timeout."""
        console.print("\n[yellow]Timeout expired! Reverting configuration...[/yellow]")
        self._revert_configs()

    def _revert_configs(self) -> None:
        """Revert to backed up configurations."""
        for file_path, content in self._backup_configs.items():
            try:
                # Write to temp file and move with sudo
                with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name

                subprocess.run(
                    ["sudo", "cp", tmp_path, file_path],
                    check=True,
                    capture_output=True,
                )
                Path(tmp_path).unlink()
            except (OSError, subprocess.CalledProcessError) as e:
                logger.error(f"Failed to revert {file_path}: {e}")

        # Re-apply reverted config
        try:
            subprocess.run(["sudo", "netplan", "apply"], capture_output=True, check=True)
            console.print("[green]Configuration reverted successfully[/green]")
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            logger.error(f"Failed to apply reverted config: {e}")

        self._backup_configs.clear()

    def _cancel_revert_timer(self) -> None:
        """Cancel the automatic revert timer."""
        if self._revert_timer:
            self._revert_timer.cancel()
            self._revert_timer = None

    # === Display Methods ===

    def print_report(self, report: ValidationReport) -> None:
        """
        Print a formatted validation report to the console.

        Args:
            report: ValidationReport to display
        """
        # Header
        status_color = "green" if report.is_valid else "red"
        status_text = "VALID" if report.is_valid else "INVALID"

        console.print(
            Panel(
                f"[bold {status_color}]Configuration Status: {status_text}[/bold {status_color}]",
                title="Network Config Validator",
                subtitle=f"Type: {report.config_type.value.title()}",
            )
        )

        # Files checked
        if report.config_files:
            console.print("\n[bold]Files Checked:[/bold]")
            for f in report.config_files:
                console.print(f"  - {f}")

        # Summary
        console.print("\n[bold]Summary:[/bold]")
        summary_table = Table(show_header=False, box=None)
        summary_table.add_column("Label", style="dim")
        summary_table.add_column("Count")

        if report.critical_count > 0:
            summary_table.add_row("Critical", f"[red bold]{report.critical_count}[/red bold]")
        if report.error_count > 0:
            summary_table.add_row("Errors", f"[red]{report.error_count}[/red]")
        if report.warning_count > 0:
            summary_table.add_row("Warnings", f"[yellow]{report.warning_count}[/yellow]")
        if report.info_count > 0:
            summary_table.add_row("Info", f"[blue]{report.info_count}[/blue]")

        if not report.issues:
            summary_table.add_row("", "[green]No issues found![/green]")

        console.print(summary_table)

        # Issues detail
        if report.issues:
            console.print("\n[bold]Issues Found:[/bold]")
            for i, issue in enumerate(report.issues, 1):
                severity_colors = {
                    ValidationSeverity.INFO: "blue",
                    ValidationSeverity.WARNING: "yellow",
                    ValidationSeverity.ERROR: "red",
                    ValidationSeverity.CRITICAL: "red bold",
                }
                color = severity_colors.get(issue.severity, "white")

                console.print(f"\n[{color}]{i}. [{issue.severity.value.upper()}] {issue.message}[/{color}]")

                if issue.file_path:
                    loc = issue.file_path
                    if issue.line_number:
                        loc += f":{issue.line_number}"
                    console.print(f"   [dim]Location: {loc}[/dim]")

                if issue.context:
                    console.print(f"   [dim]Context: {issue.context}[/dim]")

                if issue.suggestion:
                    console.print(f"   [cyan]Suggestion: {issue.suggestion}[/cyan]")

    def print_config_summary(self) -> None:
        """Print a summary of the current network configuration."""
        config_type = self.detect_config_system()
        config_files = self.get_config_files()

        console.print("\n[bold]Network Configuration Summary[/bold]")
        console.print(f"  System: [cyan]{config_type.value.title()}[/cyan]")
        console.print(f"  Config files: [cyan]{len(config_files)}[/cyan]")

        if config_type == ConfigType.NETPLAN:
            self._print_netplan_summary()

    def _print_netplan_summary(self) -> None:
        """Print Netplan-specific configuration summary."""
        try:
            import yaml
        except ImportError:
            return

        for config_file in self.get_config_files():
            try:
                with open(config_file, encoding="utf-8") as f:
                    config = yaml.safe_load(f)

                if not config or "network" not in config:
                    continue

                network = config["network"]
                console.print(f"\n  [bold]{config_file.name}:[/bold]")

                for iface_type in ["ethernets", "wifis", "bonds", "bridges"]:
                    if iface_type in network:
                        for iface_name, iface_config in network[iface_type].items():
                            console.print(f"    {iface_name} ({iface_type[:-1]}):")

                            if isinstance(iface_config, dict):
                                if iface_config.get("dhcp4"):
                                    console.print("      [green]DHCP: Enabled[/green]")

                                addresses = iface_config.get("addresses", [])
                                for addr in addresses:
                                    console.print(f"      IP: {addr}")

                                gw = iface_config.get("gateway4") or iface_config.get("routes", [{}])[0].get("via")
                                if gw:
                                    console.print(f"      Gateway: {gw}")

            except (OSError, yaml.YAMLError):
                continue


# === CLI Integration Functions ===


def run_validation(verbose: bool = False) -> int:
    """
    Run network configuration validation and print results.

    Args:
        verbose: If True, show detailed output

    Returns:
        Exit code (0 for valid, 1 for invalid)
    """
    validator = NetworkConfigValidator()
    report = validator.validate()
    validator.print_report(report)

    if verbose:
        console.print("\n")
        validator.print_config_summary()

    return 0 if report.is_valid else 1


def run_dry_run(timeout: int = 120) -> int:
    """
    Run configuration in dry-run mode with automatic revert.

    Args:
        timeout: Seconds before automatic revert

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    validator = NetworkConfigValidator()

    # First validate
    report = validator.validate()
    if not report.is_valid:
        console.print("[red]Cannot apply configuration with errors. Fix issues first.[/red]")
        validator.print_report(report)
        return 1

    # Then dry-run
    success = validator.dry_run(timeout_seconds=timeout)
    return 0 if success else 1


def show_config_diff(file_path: str, new_content: str) -> int:
    """
    Show diff between current config and proposed changes.

    Args:
        file_path: Path to configuration file
        new_content: Proposed new content

    Returns:
        Exit code (always 0)
    """
    validator = NetworkConfigValidator()
    diff = validator.show_diff(Path(file_path), new_content)
    validator.print_diff(diff)
    return 0
