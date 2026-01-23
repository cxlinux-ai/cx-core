"""
Netplan/NetworkManager Configuration Validator

Validates network configuration YAML files before applying them to prevent
network outages from simple typos. Provides semantic validation, diff preview,
dry-run mode with auto-revert, and plain English error messages.

Addresses GitHub Issue #445 - Network Config Validator
"""

import difflib
import ipaddress
import logging
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    info: list[str]


@dataclass
class NetworkInterface:
    """Represents a network interface configuration."""

    name: str
    dhcp4: bool = False
    dhcp6: bool = False
    addresses: list[str] = field(default_factory=list)
    gateway4: str | None = None
    gateway6: str | None = None
    nameservers: dict[str, Any] = field(default_factory=dict)
    routes: list[dict[str, str]] = field(default_factory=list)


class NetplanValidator:
    """
    Validates Netplan network configuration files.

    Features:
    - YAML syntax validation
    - Semantic validation (IPs, routes, gateways)
    - Configuration diff preview
    - Dry-run mode with auto-revert timer
    - Plain English error messages
    """

    NETPLAN_DIR = Path("/etc/netplan")
    BACKUP_DIR = Path.home() / ".cortex" / "netplan_backups"
    DEFAULT_REVERT_TIMEOUT = 60  # seconds

    def __init__(self, config_file: Path | str | None = None):
        """
        Initialize the validator.

        Args:
            config_file: Path to netplan YAML file to validate.
                        If None, will find the first .yaml file in /etc/netplan
        """
        self.config_file = Path(config_file) if config_file else self._find_netplan_config()
        self.backup_dir = self.BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _find_netplan_config(self) -> Path:
        """
        Find the netplan configuration file.

        Returns:
            Path to the netplan config file

        Raises:
            FileNotFoundError: If no netplan config found
        """
        if not self.NETPLAN_DIR.exists():
            raise FileNotFoundError(f"Netplan directory {self.NETPLAN_DIR} not found")

        yaml_files = list(self.NETPLAN_DIR.glob("*.yaml"))
        # Also check for .yml extension
        yml_files = list(self.NETPLAN_DIR.glob("*.yml"))
        all_files = yaml_files + yml_files

        if not all_files:
            raise FileNotFoundError(f"No .yaml or .yml files found in {self.NETPLAN_DIR}")

        # Use the first yaml file (typically 00-installer-config.yaml or 01-netcfg.yaml)
        return sorted(all_files)[0]

    def validate_yaml_syntax(self, content: str) -> ValidationResult:
        """
        Validate YAML syntax.

        Args:
            content: YAML content to validate

        Returns:
            ValidationResult with syntax validation results
        """
        errors = []
        warnings = []
        info = []

        try:
            data = yaml.safe_load(content)
            if data is None:
                errors.append("YAML file is empty")
                return ValidationResult(False, errors, warnings, info)

            info.append("✓ YAML syntax is valid")
            return ValidationResult(True, errors, warnings, info)

        except yaml.YAMLError as e:
            error_msg = str(e)
            # Extract line and column info for better error messages
            if hasattr(e, "problem_mark"):
                mark = e.problem_mark
                errors.append(
                    f"YAML syntax error at line {mark.line + 1}, column {mark.column + 1}: {e.problem}"
                )
            else:
                errors.append(f"YAML syntax error: {error_msg}")

            return ValidationResult(False, errors, warnings, info)

    def validate_ip_address(self, ip_str: str, allow_cidr: bool = True) -> tuple[bool, str]:
        """
        Validate an IP address.

        Args:
            ip_str: IP address string to validate
            allow_cidr: Whether to allow CIDR notation (e.g., 192.168.1.1/24)

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if "/" in ip_str:
                if not allow_cidr:
                    return False, f"CIDR notation not allowed for '{ip_str}'"
                # Validate CIDR notation
                ipaddress.ip_network(ip_str, strict=False)
            else:
                # Validate plain IP
                ipaddress.ip_address(ip_str)
            return True, ""
        except ValueError as e:
            return False, f"Invalid IP address '{ip_str}': {str(e)}"

    def validate_route(self, route: dict[str, str]) -> tuple[bool, list[str]]:
        """
        Validate a route configuration.

        Args:
            route: Route dictionary with 'to' and 'via' keys

        Returns:
            Tuple of (is_valid, list of errors)
        """
        errors = []

        if "to" not in route:
            errors.append("Route missing required 'to' field")
            return False, errors

        if "via" not in route:
            errors.append("Route missing required 'via' field")
            return False, errors

        # Validate destination network
        valid, error = self.validate_ip_address(route["to"], allow_cidr=True)
        if not valid:
            errors.append(f"Invalid route destination: {error}")

        # Validate gateway
        valid, error = self.validate_ip_address(route["via"], allow_cidr=False)
        if not valid:
            errors.append(f"Invalid route gateway: {error}")

        return len(errors) == 0, errors

    def validate_semantics(self, config: dict[str, Any]) -> ValidationResult:
        """
        Validate semantic correctness of network configuration.

        Args:
            config: Parsed YAML configuration

        Returns:
            ValidationResult with semantic validation results
        """
        errors = []
        warnings = []
        info = []

        # Check for required 'network' key
        if "network" not in config:
            errors.append("Configuration must have a 'network' key")
            return ValidationResult(False, errors, warnings, info)

        network = config["network"]

        # Validate version
        if "version" not in network:
            warnings.append("Missing 'version' key (recommended: version: 2)")
        elif network["version"] != 2:
            warnings.append(f"Using version {network['version']}, version 2 is recommended")

        # Validate ethernet interfaces
        if "ethernets" in network:
            if not isinstance(network["ethernets"], dict):
                errors.append("'ethernets' must be a mapping/dictionary")
            else:
                for iface_name, iface_config in network["ethernets"].items():
                    self._validate_interface(iface_name, iface_config, errors, warnings, info)

        # Validate WiFi interfaces
        if "wifis" in network:
            if not isinstance(network["wifis"], dict):
                errors.append("'wifis' must be a mapping/dictionary")
            else:
                for iface_name, iface_config in network["wifis"].items():
                    self._validate_interface(iface_name, iface_config, errors, warnings, info)

        # Validate bridges
        if "bridges" in network:
            if not isinstance(network["bridges"], dict):
                errors.append("'bridges' must be a mapping/dictionary")
            else:
                for bridge_name, bridge_config in network["bridges"].items():
                    self._validate_interface(bridge_name, bridge_config, errors, warnings, info)

        if not errors:
            info.append("✓ Semantic validation passed")

        return ValidationResult(len(errors) == 0, errors, warnings, info)

    def _validate_interface(
        self,
        iface_name: str,
        iface_config: dict[str, Any],
        errors: list[str],
        warnings: list[str],
        info: list[str],
    ) -> None:
        """
        Validate a single network interface configuration.

        Args:
            iface_name: Interface name
            iface_config: Interface configuration dictionary
            errors: List to append errors to
            warnings: List to append warnings to
            info: List to append info messages to
        """
        # Type check: ensure iface_config is a mapping/dict
        if not isinstance(iface_config, dict):
            errors.append(
                f"Interface '{iface_name}' config must be a mapping/dictionary, got {type(iface_config).__name__}"
            )
            return

        # Validate interface name format
        if not re.match(r"^[a-zA-Z0-9_-]+$", iface_name):
            errors.append(
                f"Invalid interface name '{iface_name}': must contain only alphanumeric, dash, or underscore"
            )

        # Check for DHCP vs static IP conflict
        has_dhcp4 = iface_config.get("dhcp4", False)
        has_dhcp6 = iface_config.get("dhcp6", False)
        has_addresses = "addresses" in iface_config and iface_config["addresses"]

        if (has_dhcp4 or has_dhcp6) and has_addresses:
            warnings.append(
                f"Interface '{iface_name}' has both DHCP and static addresses configured"
            )

        if not has_dhcp4 and not has_dhcp6 and not has_addresses:
            warnings.append(
                f"Interface '{iface_name}' has neither DHCP nor static addresses configured"
            )

        # Validate IP addresses
        if has_addresses:
            for addr in iface_config["addresses"]:
                valid, error = self.validate_ip_address(addr, allow_cidr=True)
                if not valid:
                    errors.append(f"Interface '{iface_name}': {error}")
                elif "/" not in addr:
                    warnings.append(
                        f"Interface '{iface_name}': Address '{addr}' missing CIDR notation (e.g., /24)"
                    )

        # Validate gateway
        if "gateway4" in iface_config:
            valid, error = self.validate_ip_address(iface_config["gateway4"], allow_cidr=False)
            if not valid:
                errors.append(f"Interface '{iface_name}' gateway4: {error}")

        if "gateway6" in iface_config:
            valid, error = self.validate_ip_address(iface_config["gateway6"], allow_cidr=False)
            if not valid:
                errors.append(f"Interface '{iface_name}' gateway6: {error}")

        # Validate nameservers
        if "nameservers" in iface_config:
            ns_config = iface_config["nameservers"]
            if "addresses" in ns_config:
                for ns_addr in ns_config["addresses"]:
                    valid, error = self.validate_ip_address(ns_addr, allow_cidr=False)
                    if not valid:
                        errors.append(f"Interface '{iface_name}' nameserver: {error}")

        # Validate routes
        if "routes" in iface_config:
            for route in iface_config["routes"]:
                valid, route_errors = self.validate_route(route)
                if not valid:
                    for err in route_errors:
                        errors.append(f"Interface '{iface_name}' route: {err}")

    def validate_file(self, config_file: Path | str | None = None) -> ValidationResult:
        """
        Validate a netplan configuration file.

        Args:
            config_file: Path to config file. If None, uses self.config_file

        Returns:
            ValidationResult with all validation results
        """
        file_path = Path(config_file) if config_file else self.config_file

        if not file_path.exists():
            return ValidationResult(False, [f"Configuration file not found: {file_path}"], [], [])

        try:
            content = file_path.read_text()
        except PermissionError:
            return ValidationResult(
                False, [f"Permission denied reading {file_path}. Try running with sudo."], [], []
            )
        except Exception as e:
            return ValidationResult(False, [f"Error reading file {file_path}: {str(e)}"], [], [])

        # Validate YAML syntax
        syntax_result = self.validate_yaml_syntax(content)
        if not syntax_result.is_valid:
            return syntax_result

        # Parse and validate semantics
        config = yaml.safe_load(content)
        semantic_result = self.validate_semantics(config)

        # Combine results
        return ValidationResult(
            syntax_result.is_valid and semantic_result.is_valid,
            syntax_result.errors + semantic_result.errors,
            syntax_result.warnings + semantic_result.warnings,
            syntax_result.info + semantic_result.info,
        )

    def generate_diff(self, new_config_file: Path | str) -> str:
        """
        Generate a diff between current and new configuration.

        Args:
            new_config_file: Path to new configuration file

        Returns:
            Unified diff string
        """
        new_path = Path(new_config_file)

        if not self.config_file.exists():
            return f"Current config {self.config_file} does not exist"

        if not new_path.exists():
            return f"New config {new_path} does not exist"

        try:
            current_lines = self.config_file.read_text().splitlines(keepends=True)
            new_lines = new_path.read_text().splitlines(keepends=True)

            diff = difflib.unified_diff(
                current_lines,
                new_lines,
                fromfile=str(self.config_file),
                tofile=str(new_path),
                lineterm="",
            )

            return "".join(diff)
        except Exception as e:
            return f"Error generating diff: {str(e)}"

    def show_diff(self, new_config_file: Path | str) -> None:
        """
        Display a colored diff in the terminal.

        Args:
            new_config_file: Path to new configuration file
        """
        diff_text = self.generate_diff(new_config_file)

        if not diff_text:
            console.print("[green]No changes detected[/green]")
            return

        console.print("\n[bold]Configuration Changes:[/bold]\n")

        # Color diff output
        for line in diff_text.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"[green]{line}[/green]")
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"[red]{line}[/red]")
            elif line.startswith("@@"):
                console.print(f"[cyan]{line}[/cyan]")
            else:
                console.print(line)

    def backup_current_config(self) -> Path:
        """
        Create a backup of the current configuration.

        Returns:
            Path to backup file

        Raises:
            IOError: If backup fails
        """
        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file {self.config_file} not found")

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"{self.config_file.stem}_{timestamp}.yaml"
        backup_path = self.backup_dir / backup_name

        try:
            shutil.copy2(self.config_file, backup_path)
            logger.info(f"Created backup: {backup_path}")
            return backup_path
        except Exception as e:
            raise OSError(f"Failed to create backup: {str(e)}") from e

    def apply_config(self, new_config_file: Path | str, backup: bool = True) -> tuple[bool, str]:
        """
        Apply a new network configuration.

        Args:
            new_config_file: Path to new configuration file
            backup: Whether to create a backup first

        Returns:
            Tuple of (success, message)
        """
        new_path = Path(new_config_file)

        if not new_path.exists():
            return False, f"New config file {new_path} not found"

        # Validate first
        result = self.validate_file(new_path)
        if not result.is_valid:
            error_msg = "\n".join(result.errors)
            return False, f"Validation failed:\n{error_msg}"

        # Create backup
        if backup:
            try:
                self.backup_current_config()
            except Exception as e:
                return False, f"Backup failed: {str(e)}"

        # Apply configuration
        backup_path = None
        try:
            # Get backup path before applying
            if backup:
                backup_files = sorted(self.backup_dir.glob("*.yaml"))
                if backup_files:
                    backup_path = backup_files[-1]  # Most recent backup

            # Copy new config to netplan directory
            shutil.copy2(new_path, self.config_file)

            # Run netplan apply
            result = subprocess.run(
                ["netplan", "apply"],
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
            )

            if result.returncode == 0:
                return True, "Configuration applied successfully"
            else:
                # Revert to backup if apply failed
                if backup and backup_path and backup_path.exists():
                    shutil.copy2(backup_path, self.config_file)
                    console.print("[yellow]Reverted to backup after netplan apply failure[/yellow]")
                return False, f"netplan apply failed: {result.stderr}"

        except subprocess.TimeoutExpired:
            # Revert to backup on timeout
            if backup and backup_path and backup_path.exists():
                shutil.copy2(backup_path, self.config_file)
                console.print("[yellow]Reverted to backup after timeout[/yellow]")
            return False, "netplan apply timed out"
        except Exception as e:
            # Revert to backup on any error
            if backup and backup_path and backup_path.exists():
                shutil.copy2(backup_path, self.config_file)
                console.print("[yellow]Reverted to backup after error[/yellow]")
            return False, f"Failed to apply config: {str(e)}"

    def dry_run_with_revert(
        self, new_config_file: Path | str, timeout: int = DEFAULT_REVERT_TIMEOUT
    ) -> bool:
        """
        Apply configuration with automatic revert if not confirmed.

        Args:
            new_config_file: Path to new configuration file
            timeout: Seconds to wait for confirmation before reverting

        Returns:
            True if config was confirmed and kept, False if reverted
        """
        console.print(
            Panel.fit(
                f"[bold yellow]DRY-RUN MODE[/bold yellow]\n\n"
                f"Configuration will be applied temporarily.\n"
                f"You have {timeout} seconds to confirm the changes.\n"
                f"If not confirmed, configuration will auto-revert.",
                title="⚠️  Safety Mode",
            )
        )

        # Validate first
        result = self.validate_file(new_config_file)
        if not result.is_valid:
            console.print("\n[bold red]Validation Failed:[/bold red]")
            for error in result.errors:
                console.print(f"  [red]✗[/red] {error}")
            return False

        # Show diff
        self.show_diff(new_config_file)

        # Create backup
        try:
            backup_path = self.backup_current_config()
        except Exception as e:
            console.print(f"\n[bold red]Backup failed:[/bold red] {str(e)}")
            return False

        # Apply configuration
        success, message = self.apply_config(new_config_file, backup=False)
        if not success:
            console.print(f"\n[bold red]Apply failed:[/bold red] {message}")
            # Revert to backup since apply failed
            if backup_path.exists():
                console.print("[yellow]Reverting to backup...[/yellow]")
                self._revert_config(backup_path)
            return False

        console.print("\n[bold green]✓[/bold green] Configuration applied")
        console.print("[bold]Testing network connectivity...[/bold]")

        # Test connectivity
        if not self._test_connectivity():
            console.print("[bold red]Network connectivity lost![/bold red]")
            console.print("[yellow]Auto-reverting in 5 seconds...[/yellow]")
            time.sleep(5)
            revert_success = self._revert_config(backup_path)
            if not revert_success:
                console.print(
                    "[bold red]⚠️  REVERT FAILED - System may be in unstable state![/bold red]"
                )
            return False

        console.print("[bold green]✓[/bold green] Network is working\n")

        # Start countdown timer
        confirmed = self._countdown_confirmation(timeout)

        if confirmed:
            console.print("\n[bold green]✓ Configuration confirmed and saved[/bold green]")
            return True
        else:
            console.print("\n[bold yellow]⟳ Reverting to previous configuration...[/bold yellow]")
            revert_success = self._revert_config(backup_path)
            if not revert_success:
                console.print(
                    "[bold red]⚠️  REVERT FAILED - System may be in unstable state![/bold red]"
                )
                console.print(
                    "[yellow]Please follow the manual recovery steps shown above.[/yellow]"
                )
            return False

    def _test_connectivity(self) -> bool:
        """
        Test network connectivity by pinging common DNS servers.

        Returns:
            True if network is working
        """
        test_hosts = ["8.8.8.8", "1.1.1.1"]

        for host in test_hosts:
            try:
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", host],
                    capture_output=True,
                    timeout=3,
                    shell=False,
                )
                if result.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, Exception):
                continue

        return False

    def _countdown_confirmation(self, timeout: int) -> bool:
        """
        Display countdown and wait for user confirmation.

        Args:
            timeout: Seconds to wait

        Returns:
            True if user confirmed, False if timeout
        """
        console.print(f"[bold]Press 'y' to keep changes, or wait {timeout}s to auto-revert[/bold]")

        confirmed = threading.Event()

        def wait_for_input():
            try:
                import sys
                import termios
                import tty

                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                try:
                    tty.setraw(sys.stdin.fileno())
                    ch = sys.stdin.read(1)
                    if ch.lower() == "y":
                        confirmed.set()
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except (AttributeError, OSError) as e:
                # Fallback for non-Unix systems or no TTY
                # IOError/OSError: stdin issues, AttributeError: termios missing
                response = input().strip().lower()
                if response == "y":
                    confirmed.set()

        # Start input thread
        input_thread = threading.Thread(target=wait_for_input, daemon=True)
        input_thread.start()

        # Countdown
        for remaining in range(timeout, 0, -1):
            if confirmed.is_set():
                break
            console.print(f"\r⏱ Reverting in [{remaining}] seconds... ", end="")
            time.sleep(1)

        console.print()  # New line
        return confirmed.is_set()

    def _revert_config(self, backup_path: Path) -> bool:
        """
        Revert to backup configuration.

        Args:
            backup_path: Path to backup file

        Returns:
            True if revert was successful, False otherwise
        """
        try:
            # Copy backup to active config location
            shutil.copy2(backup_path, self.config_file)
            logger.info(f"Copied backup {backup_path} to {self.config_file}")

            # Apply the reverted configuration
            result = subprocess.run(
                ["netplan", "apply"],
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
            )

            # Check if netplan apply succeeded
            if result.returncode != 0:
                console.print(
                    "[bold red]✗ CRITICAL: Revert failed - netplan apply returned non-zero exit code[/bold red]"
                )
                console.print(f"\n[bold]Exit Code:[/bold] {result.returncode}")

                if result.stderr:
                    console.print("\n[bold red]Error Output:[/bold red]")
                    console.print(f"[red]{result.stderr}[/red]")

                if result.stdout:
                    console.print("\n[bold]Standard Output:[/bold]")
                    console.print(result.stdout)

                console.print("\n[bold yellow]Configuration State:[/bold yellow]")
                console.print(f"  Current config: {self.config_file}")
                console.print(f"  Backup location: {backup_path}")

                console.print("\n[bold red]⚠️  MANUAL RECOVERY REQUIRED:[/bold red]")
                console.print("  1. Restore backup manually:")
                console.print(f"     [cyan]sudo cp {backup_path} {self.config_file}[/cyan]")
                console.print("     [cyan]sudo netplan apply[/cyan]")
                console.print("  2. If network is completely broken:")
                console.print("     [cyan]sudo systemctl restart systemd-networkd[/cyan]")
                console.print("  3. If still not working, reboot into recovery mode:")
                console.print("     - Reboot and select 'Advanced options' > 'Recovery mode'")
                console.print("     - Select 'network' to enable networking")
                console.print("     - Manually restore the backup file")
                console.print("  4. Last resort - restore default config:")
                console.print(f"     [cyan]sudo rm {self.config_file}[/cyan]")
                console.print("     [cyan]sudo netplan generate[/cyan]")

                logger.error(f"Revert failed: netplan apply returned {result.returncode}")
                logger.error(f"stderr: {result.stderr}")
                logger.error(f"stdout: {result.stdout}")

                return False

            # Success case
            console.print("[bold green]✓ Reverted to previous configuration[/bold green]")
            logger.info("Successfully reverted to backup configuration")
            return True

        except subprocess.TimeoutExpired as e:
            console.print(
                "[bold red]✗ CRITICAL: Revert failed - netplan apply timed out[/bold red]"
            )
            console.print("\n[bold yellow]Configuration State:[/bold yellow]")
            console.print(f"  Current config: {self.config_file}")
            console.print(f"  Backup location: {backup_path}")
            console.print(
                "\n[bold red]⚠️  MANUAL RECOVERY REQUIRED (timeout after 30s):[/bold red]"
            )
            console.print("  1. Try applying manually:")
            console.print("     [cyan]sudo netplan apply[/cyan]")
            console.print("  2. Restart networking:")
            console.print("     [cyan]sudo systemctl restart systemd-networkd[/cyan]")
            console.print("  3. Restore backup manually:")
            console.print(f"     [cyan]sudo cp {backup_path} {self.config_file}[/cyan]")
            console.print("  4. Reboot if necessary")
            logger.error(f"Revert timeout: {e}")
            return False

        except Exception as e:
            console.print("[bold red]✗ CRITICAL: Failed to revert configuration[/bold red]")
            console.print(f"[red]Error: {str(e)}[/red]")
            console.print("\n[bold yellow]Configuration State:[/bold yellow]")
            console.print(f"  Current config: {self.config_file}")
            console.print(f"  Backup location: {backup_path}")
            console.print("\n[bold red]⚠️  MANUAL RECOVERY REQUIRED:[/bold red]")
            console.print("  1. Restore backup manually:")
            console.print(f"     [cyan]sudo cp {backup_path} {self.config_file}[/cyan]")
            console.print("     [cyan]sudo netplan apply[/cyan]")
            console.print("  2. If network is broken, reboot into recovery mode")
            logger.error(f"Revert exception: {e}", exc_info=True)
            return False

    def print_validation_results(self, result: ValidationResult) -> None:
        """
        Print validation results in a user-friendly format.

        Args:
            result: ValidationResult to display
        """
        if result.is_valid:
            console.print("\n[bold green]✓ Validation Passed[/bold green]\n")
        else:
            console.print("\n[bold red]✗ Validation Failed[/bold red]\n")

        if result.errors:
            console.print("[bold red]Errors:[/bold red]")
            for error in result.errors:
                console.print(f"  [red]✗[/red] {error}")
            console.print()

        if result.warnings:
            console.print("[bold yellow]Warnings:[/bold yellow]")
            for warning in result.warnings:
                console.print(f"  [yellow]⚠[/yellow] {warning}")
            console.print()

        if result.info:
            for info_msg in result.info:
                console.print(f"  [blue]ℹ[/blue] {info_msg}")


def validate_netplan_config(config_file: Path | str | None = None) -> bool:
    """
    Convenience function to validate a netplan configuration file.

    Args:
        config_file: Path to config file, or None to auto-detect

    Returns:
        True if validation passed, False otherwise
    """
    try:
        validator = NetplanValidator(config_file)
        result = validator.validate_file()
        validator.print_validation_results(result)
        return result.is_valid
    except Exception as e:
        console.print(f"[bold red]Validation error:[/bold red] {str(e)}")
        return False
