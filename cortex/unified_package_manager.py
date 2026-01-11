#!/usr/bin/env python3
"""
Unified Package Manager for Cortex Linux

Provides a unified interface for managing packages across multiple formats:
- APT/DEB (traditional Debian packages)
- Snap (Canonical's universal packages)
- Flatpak (cross-distribution application packages)

Addresses issue #450: Snap/Flatpak confusion and transparency.
"""

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PackageFormat(Enum):
    """Supported package formats."""

    DEB = "deb"
    SNAP = "snap"
    FLATPAK = "flatpak"


@dataclass
class PackageInfo:
    """Information about a package in a specific format."""

    name: str
    format: PackageFormat
    version: str = ""
    size: int = 0  # Size in bytes
    installed: bool = False
    description: str = ""
    permissions: list[str] = field(default_factory=list)


@dataclass
class StorageAnalysis:
    """Storage usage analysis by package format."""

    deb_total: int = 0
    snap_total: int = 0
    flatpak_total: int = 0
    deb_packages: list[tuple[str, int]] = field(default_factory=list)
    snap_packages: list[tuple[str, int]] = field(default_factory=list)
    flatpak_packages: list[tuple[str, int]] = field(default_factory=list)


class UnifiedPackageManager:
    """
    Unified manager for APT, Snap, and Flatpak packages.

    Provides transparency about package sources and enables users to:
    - See true package source (deb vs snap vs flatpak)
    - Compare package options across formats
    - Manage permissions for sandboxed packages
    - Detect and optionally disable snap redirects
    - Analyze storage usage by format
    """

    # Known transitional packages that redirect to snap
    KNOWN_SNAP_REDIRECTS = {
        "firefox",
        "chromium-browser",
        "thunderbird",
        "libreoffice",
        "gnome-calculator",
        "gnome-characters",
        "gnome-logs",
        "gnome-system-monitor",
    }

    SNAP_REDIRECT_CONFIG = "/etc/apt/apt.conf.d/20snapd.conf"

    def __init__(self) -> None:
        """Initialize the unified package manager."""
        self._snap_available = self._check_command_available("snap")
        self._flatpak_available = self._check_command_available("flatpak")
        self._apt_available = self._check_command_available("apt")

    def _check_command_available(self, command: str) -> bool:
        """Check if a command is available on the system."""
        return shutil.which(command) is not None

    def _run_command(
        self, cmd: list[str], timeout: int = 30
    ) -> tuple[bool, str, str]:
        """
        Run a shell command and return success status, stdout, stderr.

        Args:
            cmd: Command to run as list of arguments
            timeout: Timeout in seconds

        Returns:
            Tuple of (success, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out: {' '.join(cmd)}")
            return False, "", "Command timed out"
        except FileNotFoundError:
            logger.warning(f"Command not found: {cmd[0]}")
            return False, "", f"Command not found: {cmd[0]}"
        except Exception as e:
            logger.error(f"Error running command {cmd}: {e}")
            return False, "", str(e)

    # =========================================================================
    # Package Source Detection
    # =========================================================================

    def detect_package_sources(self, package_name: str) -> dict[str, PackageInfo | None]:
        """
        Detect all available sources for a package.

        Args:
            package_name: Name of the package to search for

        Returns:
            Dictionary with keys 'deb', 'snap', 'flatpak' containing PackageInfo or None
        """
        return {
            "deb": self._check_deb_package(package_name),
            "snap": self._check_snap_package(package_name),
            "flatpak": self._check_flatpak_package(package_name),
        }

    def _check_deb_package(self, package_name: str) -> PackageInfo | None:
        """Check if package is available as .deb."""
        if not self._apt_available:
            return None

        # First check if installed
        success, stdout, _ = self._run_command(
            ["dpkg-query", "-W", "-f=${Status}|${Version}|${Installed-Size}", package_name]
        )

        if success and "install ok installed" in stdout:
            parts = stdout.strip().split("|")
            version = parts[1] if len(parts) > 1 else ""
            size = int(parts[2]) * 1024 if len(parts) > 2 and parts[2].isdigit() else 0
            return PackageInfo(
                name=package_name,
                format=PackageFormat.DEB,
                version=version,
                size=size,
                installed=True,
            )

        # Check if available in apt cache
        success, stdout, _ = self._run_command(["apt-cache", "show", package_name])
        if success and stdout:
            # Check if this is a transitional/dummy package
            if "dummy" in stdout.lower() or "transitional" in stdout.lower():
                # This is likely a snap redirect
                return None

            version = ""
            size = 0
            description = ""
            for line in stdout.split("\n"):
                if line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
                elif line.startswith("Installed-Size:"):
                    size_str = line.split(":", 1)[1].strip()
                    size = int(size_str) * 1024 if size_str.isdigit() else 0
                elif line.startswith("Description:"):
                    description = line.split(":", 1)[1].strip()

            return PackageInfo(
                name=package_name,
                format=PackageFormat.DEB,
                version=version,
                size=size,
                installed=False,
                description=description,
            )

        return None

    def _check_snap_package(self, package_name: str) -> PackageInfo | None:
        """Check if package is available as snap."""
        if not self._snap_available:
            return None

        # Check if installed
        success, stdout, _ = self._run_command(["snap", "list", package_name])
        if success and package_name in stdout:
            lines = stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                version = parts[1] if len(parts) > 1 else ""
                return PackageInfo(
                    name=package_name,
                    format=PackageFormat.SNAP,
                    version=version,
                    installed=True,
                )

        # Check if available in snap store
        success, stdout, _ = self._run_command(["snap", "info", package_name])
        if success and stdout:
            version = ""
            description = ""
            for line in stdout.split("\n"):
                if line.startswith("stable:"):
                    version = line.split()[1] if len(line.split()) > 1 else ""
                elif line.startswith("summary:"):
                    description = line.split(":", 1)[1].strip()

            return PackageInfo(
                name=package_name,
                format=PackageFormat.SNAP,
                version=version,
                installed=False,
                description=description,
            )

        return None

    def _check_flatpak_package(self, package_name: str) -> PackageInfo | None:
        """Check if package is available as flatpak."""
        if not self._flatpak_available:
            return None

        # Check if installed (by partial match)
        success, stdout, _ = self._run_command(
            ["flatpak", "list", "--app", "--columns=application,version"]
        )
        if success:
            for line in stdout.strip().split("\n"):
                if package_name.lower() in line.lower():
                    parts = line.split("\t")
                    app_id = parts[0] if parts else ""
                    version = parts[1] if len(parts) > 1 else ""
                    return PackageInfo(
                        name=app_id,
                        format=PackageFormat.FLATPAK,
                        version=version,
                        installed=True,
                    )

        # Search in remote repos
        success, stdout, _ = self._run_command(
            ["flatpak", "search", package_name, "--columns=application,version,description"]
        )
        if success and stdout:
            lines = stdout.strip().split("\n")
            for line in lines:
                # Skip empty lines and "No matches" messages
                if not line or "no matches" in line.lower() or "no results" in line.lower():
                    continue
                parts = line.split("\t")
                # Validate: app_id should look like org.something.App
                app_id = parts[0] if parts else ""
                if app_id and "." in app_id:
                    version = parts[1] if len(parts) > 1 else ""
                    description = parts[2] if len(parts) > 2 else ""
                    return PackageInfo(
                        name=app_id,
                        format=PackageFormat.FLATPAK,
                        version=version,
                        installed=False,
                        description=description,
                    )

        return None

    # =========================================================================
    # Installed Package Listing
    # =========================================================================

    def list_installed_packages(
        self, format_filter: PackageFormat | None = None
    ) -> dict[str, list[PackageInfo]]:
        """
        List all installed packages, optionally filtered by format.

        Args:
            format_filter: Optional filter to show only packages of specific format

        Returns:
            Dictionary with keys 'deb', 'snap', 'flatpak' containing lists of PackageInfo
        """
        result: dict[str, list[PackageInfo]] = {"deb": [], "snap": [], "flatpak": []}

        if format_filter is None or format_filter == PackageFormat.DEB:
            result["deb"] = self._list_deb_packages()

        if format_filter is None or format_filter == PackageFormat.SNAP:
            result["snap"] = self._list_snap_packages()

        if format_filter is None or format_filter == PackageFormat.FLATPAK:
            result["flatpak"] = self._list_flatpak_packages()

        return result

    def _list_deb_packages(self) -> list[PackageInfo]:
        """List installed .deb packages."""
        if not self._apt_available:
            return []

        success, stdout, _ = self._run_command(
            ["dpkg-query", "-W", "-f=${Package}|${Version}|${Installed-Size}\n"]
        )

        packages = []
        if success:
            for line in stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|")
                name = parts[0]
                version = parts[1] if len(parts) > 1 else ""
                size = int(parts[2]) * 1024 if len(parts) > 2 and parts[2].isdigit() else 0
                packages.append(
                    PackageInfo(
                        name=name,
                        format=PackageFormat.DEB,
                        version=version,
                        size=size,
                        installed=True,
                    )
                )

        return packages

    def _list_snap_packages(self) -> list[PackageInfo]:
        """List installed snap packages."""
        if not self._snap_available:
            return []

        success, stdout, _ = self._run_command(["snap", "list"])

        packages = []
        if success:
            lines = stdout.strip().split("\n")
            for line in lines[1:]:  # Skip header
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    version = parts[1]
                    # Parse size from notes column if available
                    packages.append(
                        PackageInfo(
                            name=name,
                            format=PackageFormat.SNAP,
                            version=version,
                            installed=True,
                        )
                    )

        return packages

    def _list_flatpak_packages(self) -> list[PackageInfo]:
        """List installed flatpak packages."""
        if not self._flatpak_available:
            return []

        success, stdout, _ = self._run_command(
            ["flatpak", "list", "--app", "--columns=application,version,size"]
        )

        packages = []
        if success:
            for line in stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                app_id = parts[0] if parts else ""
                version = parts[1] if len(parts) > 1 else ""
                size_str = parts[2] if len(parts) > 2 else "0"
                # Parse size (e.g., "1.2 GB" -> bytes)
                size = self._parse_size_string(size_str)
                packages.append(
                    PackageInfo(
                        name=app_id,
                        format=PackageFormat.FLATPAK,
                        version=version,
                        size=size,
                        installed=True,
                    )
                )

        return packages

    def _parse_size_string(self, size_str: str) -> int:
        """Parse a human-readable size string to bytes."""
        size_str = size_str.strip()
        if not size_str:
            return 0

        multipliers = {
            "B": 1,
            "KB": 1024,
            "MB": 1024**2,
            "GB": 1024**3,
            "kB": 1024,
            "mB": 1024**2,
            "gB": 1024**3,
        }

        match = re.match(r"([\d.]+)\s*([A-Za-z]+)", size_str)
        if match:
            value = float(match.group(1))
            unit = match.group(2)
            return int(value * multipliers.get(unit, 1))

        return 0

    # =========================================================================
    # Package Comparison
    # =========================================================================

    def compare_package_options(self, package_name: str) -> dict[str, Any]:
        """
        Compare a package across all available formats.

        Args:
            package_name: Name of the package to compare

        Returns:
            Dictionary with comparison data including versions, sizes, permissions
        """
        sources = self.detect_package_sources(package_name)

        comparison = {
            "package_name": package_name,
            "available_formats": [],
            "installed_as": None,
            "comparison": {},
        }

        for format_name, info in sources.items():
            if info is not None:
                comparison["available_formats"].append(format_name)
                comparison["comparison"][format_name] = {
                    "version": info.version,
                    "size": info.size,
                    "installed": info.installed,
                    "description": info.description,
                }
                if info.installed:
                    comparison["installed_as"] = format_name

        return comparison

    # =========================================================================
    # Permission Management
    # =========================================================================

    def list_snap_permissions(self, snap_name: str) -> dict[str, list[dict[str, str]]]:
        """
        List permissions/interfaces for a snap package.

        Args:
            snap_name: Name of the snap package

        Returns:
            Dictionary with 'connected' and 'available' interface lists
        """
        if not self._snap_available:
            return {"error": "Snap is not available on this system"}

        success, stdout, _ = self._run_command(["snap", "connections", snap_name])

        result: dict[str, list[dict[str, str]]] = {"connected": [], "available": []}

        if success:
            lines = stdout.strip().split("\n")
            for line in lines[1:]:  # Skip header
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    interface = parts[0]
                    plug = parts[1]
                    slot = parts[2]
                    notes = parts[3] if len(parts) > 3 else ""

                    entry = {
                        "interface": interface,
                        "plug": plug,
                        "slot": slot,
                        "notes": notes,
                    }

                    if slot != "-":
                        result["connected"].append(entry)
                    else:
                        result["available"].append(entry)

        return result

    def list_flatpak_permissions(self, app_id: str) -> dict[str, Any]:
        """
        List permissions for a flatpak application.

        Args:
            app_id: Flatpak application ID (e.g., org.mozilla.firefox)

        Returns:
            Dictionary with permission categories and values
        """
        if not self._flatpak_available:
            return {"error": "Flatpak is not available on this system"}

        success, stdout, _ = self._run_command(
            ["flatpak", "info", "--show-permissions", app_id]
        )

        if not success:
            return {"error": f"Could not get permissions for {app_id}"}

        permissions: dict[str, Any] = {}
        current_section = ""

        for line in stdout.strip().split("\n"):
            if not line:
                continue

            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                permissions[current_section] = {}
            elif "=" in line and current_section:
                key, value = line.split("=", 1)
                permissions[current_section][key] = value
            elif current_section:
                # Single value without key
                if current_section not in permissions:
                    permissions[current_section] = []
                if isinstance(permissions[current_section], list):
                    permissions[current_section].append(line)

        return permissions

    def modify_snap_permission(
        self, snap_name: str, interface: str, action: str
    ) -> tuple[bool, str]:
        """
        Modify a snap permission (connect/disconnect an interface).

        Args:
            snap_name: Name of the snap package
            interface: Interface to modify
            action: 'connect' or 'disconnect'

        Returns:
            Tuple of (success, message)
        """
        if action not in ("connect", "disconnect"):
            return False, f"Invalid action: {action}. Use 'connect' or 'disconnect'"

        if not self._snap_available:
            return False, "Snap is not available on this system"

        cmd = ["snap", action, f"{snap_name}:{interface}"]
        success, stdout, stderr = self._run_command(cmd)

        if success:
            return True, f"Successfully {action}ed {interface} for {snap_name}"
        else:
            return False, f"Failed to {action} {interface}: {stderr}"

    def modify_flatpak_permission(
        self, app_id: str, permission: str, value: str
    ) -> tuple[bool, str]:
        """
        Modify a flatpak permission using flatpak override.

        Args:
            app_id: Flatpak application ID
            permission: Permission flag (e.g., '--filesystem=home')
            value: Value for the permission

        Returns:
            Tuple of (success, message)
        """
        if not self._flatpak_available:
            return False, "Flatpak is not available on this system"

        # Construct the override command
        cmd = ["flatpak", "override", "--user", f"--{permission}={value}", app_id]
        success, stdout, stderr = self._run_command(cmd)

        if success:
            return True, f"Successfully modified {permission} for {app_id}"
        else:
            return False, f"Failed to modify permission: {stderr}"

    # =========================================================================
    # Snap Redirect Detection & Management
    # =========================================================================

    def check_snap_redirects(self) -> list[dict[str, str]]:
        """
        Detect packages that redirect apt install to snap.

        Returns:
            List of dictionaries with 'package' and 'reason' keys
        """
        redirects = []

        # Check for known transitional packages
        for pkg in self.KNOWN_SNAP_REDIRECTS:
            success, stdout, _ = self._run_command(["apt-cache", "show", pkg])
            if success:
                if "dummy" in stdout.lower() or "transitional" in stdout.lower():
                    redirects.append({
                        "package": pkg,
                        "type": "transitional",
                        "reason": "APT package is a dummy that installs snap version",
                    })
                elif "snap" in stdout.lower():
                    redirects.append({
                        "package": pkg,
                        "type": "snap_meta",
                        "reason": "Package description mentions snap installation",
                    })

        # Check snap preference config file
        if os.path.exists(self.SNAP_REDIRECT_CONFIG):
            redirects.append({
                "package": "system",
                "type": "config",
                "reason": f"Snap preference config exists: {self.SNAP_REDIRECT_CONFIG}",
            })

        return redirects

    def disable_snap_redirects(self, backup: bool = True) -> tuple[bool, str]:
        """
        Disable snap redirects by moving the APT config file.

        WARNING: This modifies system configuration and requires root.

        Args:
            backup: Whether to create a backup of the config file

        Returns:
            Tuple of (success, message)
        """
        config_path = Path(self.SNAP_REDIRECT_CONFIG)

        if not config_path.exists():
            return True, "Snap redirect config not found - redirects may already be disabled"

        # Check if we have write permission
        if not os.access(config_path.parent, os.W_OK):
            return False, "Permission denied. Run with sudo to disable snap redirects."

        try:
            if backup:
                backup_path = config_path.with_suffix(".conf.disabled")
                shutil.move(str(config_path), str(backup_path))
                return True, f"Snap redirects disabled. Backup saved to: {backup_path}"
            else:
                config_path.unlink()
                return True, "Snap redirects disabled. Config file removed."
        except Exception as e:
            return False, f"Failed to disable snap redirects: {e}"

    def restore_snap_redirects(self) -> tuple[bool, str]:
        """
        Restore snap redirects from backup.

        Returns:
            Tuple of (success, message)
        """
        backup_path = Path(self.SNAP_REDIRECT_CONFIG + ".disabled")
        config_path = Path(self.SNAP_REDIRECT_CONFIG)

        if not backup_path.exists():
            return False, "No backup found to restore"

        if config_path.exists():
            return False, "Snap redirect config already exists"

        try:
            shutil.move(str(backup_path), str(config_path))
            return True, "Snap redirects restored from backup"
        except Exception as e:
            return False, f"Failed to restore snap redirects: {e}"

    # =========================================================================
    # Storage Analysis
    # =========================================================================

    def analyze_storage(self) -> StorageAnalysis:
        """
        Analyze disk usage by package format.

        Returns:
            StorageAnalysis with totals and top packages per format
        """
        analysis = StorageAnalysis()

        # Analyze DEB packages
        deb_packages = self._list_deb_packages()
        for pkg in deb_packages:
            analysis.deb_total += pkg.size
            analysis.deb_packages.append((pkg.name, pkg.size))

        # Sort and keep top 10
        analysis.deb_packages.sort(key=lambda x: x[1], reverse=True)
        analysis.deb_packages = analysis.deb_packages[:10]

        # Analyze Snap packages
        if self._snap_available:
            success, stdout, _ = self._run_command(["snap", "list", "--all"])
            if success:
                # Get snap directory size
                snap_dir = Path("/var/lib/snapd/snaps")
                if snap_dir.exists():
                    for snap_file in snap_dir.glob("*.snap"):
                        size = snap_file.stat().st_size
                        name = snap_file.stem.rsplit("_", 1)[0]
                        analysis.snap_total += size
                        analysis.snap_packages.append((name, size))

            analysis.snap_packages.sort(key=lambda x: x[1], reverse=True)
            # Deduplicate (keep largest per name) and limit to top 10
            seen = set()
            deduped = []
            for name, size in analysis.snap_packages:
                if name not in seen:
                    seen.add(name)
                    deduped.append((name, size))
            analysis.snap_packages = deduped[:10]

        # Analyze Flatpak packages
        flatpak_packages = self._list_flatpak_packages()
        for pkg in flatpak_packages:
            analysis.flatpak_total += pkg.size
            analysis.flatpak_packages.append((pkg.name, pkg.size))

        analysis.flatpak_packages.sort(key=lambda x: x[1], reverse=True)
        analysis.flatpak_packages = analysis.flatpak_packages[:10]

        return analysis

    def format_storage_analysis(self, analysis: StorageAnalysis) -> str:
        """
        Format storage analysis for display.

        Args:
            analysis: StorageAnalysis object

        Returns:
            Formatted string for display
        """
        lines = []
        lines.append("=" * 60)
        lines.append("Storage Analysis by Package Format")
        lines.append("=" * 60)

        def format_size(size: int) -> str:
            if size >= 1024**3:
                return f"{size / 1024**3:.2f} GB"
            elif size >= 1024**2:
                return f"{size / 1024**2:.2f} MB"
            elif size >= 1024:
                return f"{size / 1024:.2f} KB"
            return f"{size} B"

        # Summary
        total = analysis.deb_total + analysis.snap_total + analysis.flatpak_total
        lines.append(f"\nTotal Package Storage: {format_size(total)}")
        lines.append("-" * 40)
        lines.append(f"  DEB/APT:   {format_size(analysis.deb_total)}")
        lines.append(f"  Snap:      {format_size(analysis.snap_total)}")
        lines.append(f"  Flatpak:   {format_size(analysis.flatpak_total)}")

        # Top packages per format
        if analysis.snap_packages:
            lines.append("\nTop Snap Packages:")
            for name, size in analysis.snap_packages[:5]:
                lines.append(f"  {name}: {format_size(size)}")

        if analysis.flatpak_packages:
            lines.append("\nTop Flatpak Packages:")
            for name, size in analysis.flatpak_packages[:5]:
                lines.append(f"  {name}: {format_size(size)}")

        return "\n".join(lines)
