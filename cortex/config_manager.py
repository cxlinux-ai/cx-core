"""
Configuration Manager for Cortex Linux
Handles export/import of system state for reproducibility.

Part of Cortex Linux - AI-native OS that needs to export/import system configurations.
"""

import json
import logging
import os
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import yaml

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Manages configuration export/import for Cortex Linux.

    Features:
    - Export current system state to YAML (packages, configs, preferences)
    - Import configuration from YAML file
    - Validate version compatibility between export and import
    - Support dry-run mode (preview without applying)
    - Generate diff between current state and config file
    - Handle selective export/import (packages only, configs only, etc.)
    """

    CORTEX_VERSION = "0.2.0"

    # Timeout constants
    DETECTION_TIMEOUT = 30  # seconds for package detection
    INSTALLATION_TIMEOUT = 300  # seconds for package installation

    # Package sources
    SOURCE_APT = "apt"
    SOURCE_PIP = "pip"
    SOURCE_NPM = "npm"
    DEFAULT_SOURCES: ClassVar[list[str]] = [SOURCE_APT, SOURCE_PIP, SOURCE_NPM]

    def __init__(self, sandbox_executor=None):
        """
        Initialize ConfigManager.

        Args:
            sandbox_executor: Optional SandboxExecutor instance for safe command execution

        Raises:
            PermissionError: If directory ownership or permissions cannot be secured
        """
        self.sandbox_executor = sandbox_executor
        self.cortex_dir = Path.home() / ".cortex"
        self.preferences_file = self.cortex_dir / "preferences.yaml"
        self._file_lock = threading.Lock()  # Protect file I/O operations

        # Ensure .cortex directory exists with secure permissions
        self.cortex_dir.mkdir(mode=0o700, exist_ok=True)
        self._enforce_directory_security(self.cortex_dir)

    def _enforce_directory_security(self, directory: Path) -> None:
        """
        Enforce ownership and permission security on a directory.

        Ensures the directory is owned by the current user and has mode 0o700
        (read/write/execute for owner only).

        Args:
            directory: Path to the directory to secure

        Raises:
            PermissionError: If ownership or permissions cannot be secured
        """
        # Cortex targets Linux. Ownership APIs are only available on POSIX.
        # On Windows (and some restricted runtimes), os.getuid/os.getgid/os.chown aren't present,
        # so we skip strict enforcement.
        if os.name != "posix" or not hasattr(os, "getuid") or not hasattr(os, "getgid"):
            return

        try:
            # Get directory statistics
            stat_info = directory.stat()
            current_uid = os.getuid()
            current_gid = os.getgid()

            # Check and fix ownership if needed
            if stat_info.st_uid != current_uid or stat_info.st_gid != current_gid:
                try:
                    os.chown(directory, current_uid, current_gid)
                except PermissionError:
                    raise PermissionError(
                        f"Directory {directory} is owned by uid={stat_info.st_uid}, "
                        f"gid={stat_info.st_gid}, but process is running as uid={current_uid}, "
                        f"gid={current_gid}. Insufficient privileges to change ownership."
                    )

            # Enforce mode 0o700
            os.chmod(directory, 0o700)

            # Verify the chmod succeeded
            stat_info = directory.stat()
            actual_mode = stat_info.st_mode & 0o777
            if actual_mode != 0o700:
                raise PermissionError(
                    f"Failed to set secure permissions on {directory}. "
                    f"Expected mode 0o700, but actual mode is {oct(actual_mode)}. "
                    f"Security invariant failed."
                )
        except OSError as e:
            if isinstance(e, PermissionError):
                raise
            raise PermissionError(f"Failed to enforce security on {directory}: {e}")

    def detect_apt_packages(self) -> list[dict[str, Any]]:
        """
        Detect installed APT packages.

        Returns:
            List of package dictionaries with name, version, and source
        """
        packages = []

        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"],
                capture_output=True,
                text=True,
                timeout=self.DETECTION_TIMEOUT,
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            packages.append(
                                {"name": parts[0], "version": parts[1], "source": self.SOURCE_APT}
                            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Silently handle errors - package manager may not be available
            pass

        return packages

    def detect_pip_packages(self) -> list[dict[str, Any]]:
        """
        Detect installed PIP packages.

        Returns:
            List of package dictionaries with name, version, and source
        """
        packages = []

        # Try pip3 first, then pip
        for pip_cmd in ["pip3", "pip"]:
            try:
                result = subprocess.run(
                    [pip_cmd, "list", "--format=json"],
                    capture_output=True,
                    text=True,
                    timeout=self.DETECTION_TIMEOUT,
                )

                if result.returncode == 0:
                    pip_packages = json.loads(result.stdout)
                    for pkg in pip_packages:
                        packages.append(
                            {
                                "name": pkg["name"],
                                "version": pkg["version"],
                                "source": self.SOURCE_PIP,
                            }
                        )
                    break  # Success, no need to try other pip commands
            except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
                continue

        return packages

    def detect_npm_packages(self) -> list[dict[str, Any]]:
        """
        Detect globally installed NPM packages.

        Returns:
            List of package dictionaries with name, version, and source
        """
        packages = []

        try:
            result = subprocess.run(
                ["npm", "list", "-g", "--depth=0", "--json"],
                capture_output=True,
                text=True,
                timeout=self.DETECTION_TIMEOUT,
            )

            if result.returncode == 0:
                npm_data = json.loads(result.stdout)
                dependencies = npm_data.get("dependencies", {})

                for name, info in dependencies.items():
                    version = info.get("version", "unknown")
                    packages.append({"name": name, "version": version, "source": self.SOURCE_NPM})
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            # Silently handle errors - npm may not be installed or global packages unavailable
            pass

        return packages

    def detect_installed_packages(self, sources: list[str] | None = None) -> list[dict[str, Any]]:
        """
        Detect all installed packages from specified sources.

        Args:
            sources: List of package sources to detect ['apt', 'pip', 'npm']
                     If None, detects from all sources

        Returns:
            List of package dictionaries sorted by name
        """
        if sources is None:
            sources = self.DEFAULT_SOURCES

        all_packages = []

        if self.SOURCE_APT in sources:
            all_packages.extend(self.detect_apt_packages())

        if self.SOURCE_PIP in sources:
            all_packages.extend(self.detect_pip_packages())

        if self.SOURCE_NPM in sources:
            all_packages.extend(self.detect_npm_packages())

        # Remove duplicates based on name and source (more efficient)
        unique_packages_dict = {}
        for pkg in all_packages:
            key = (pkg["name"], pkg["source"])
            unique_packages_dict[key] = pkg

        # Sort by name
        unique_packages = sorted(unique_packages_dict.values(), key=lambda x: x["name"])

        return unique_packages

    def _detect_os_version(self) -> str:
        """
        Detect OS version from /etc/os-release.

        Returns:
            OS version string (e.g., 'ubuntu-24.04')
        """
        try:
            os_release_path = Path("/etc/os-release")
            if not os_release_path.exists():
                return "unknown"

            with open(os_release_path) as f:
                os_release = f.read()

            # Extract distribution name and version
            name_match = re.search(r"ID=([^\n]+)", os_release)
            version_match = re.search(r'VERSION_ID="?([^"\n]+)"?', os_release)

            if name_match and version_match:
                name = name_match.group(1).strip().strip('"')
                version = version_match.group(1).strip()
                return f"{name}-{version}"

            return "unknown"
        except Exception as e:
            logger.debug(f"OS version detection failed: {e}", exc_info=True)
            return "unknown"

    def _load_preferences(self) -> dict[str, Any]:
        """
        Load user preferences from ~/.cortex/preferences.yaml.

        Returns:
            Dictionary of preferences
        """
        if self.preferences_file.exists():
            try:
                with self._file_lock:
                    with open(self.preferences_file) as f:
                        return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load preferences: {e}", exc_info=True)

        return {}

    def _save_preferences(self, preferences: dict[str, Any]) -> None:
        """
        Save user preferences to ~/.cortex/preferences.yaml.

        Args:
            preferences: Dictionary of preferences to save
        """
        try:
            with self._file_lock:
                with open(self.preferences_file, "w") as f:
                    yaml.safe_dump(preferences, f, default_flow_style=False)
        except Exception as e:
            raise RuntimeError(f"Failed to save preferences: {e}")

    def export_configuration(
        self,
        output_path: str,
        include_hardware: bool = True,
        include_preferences: bool = True,
        package_sources: list[str] | None = None,
    ) -> str:
        """
        Export current system configuration to YAML file.

        Args:
            output_path: Path to save YAML configuration file
            include_hardware: Include hardware profile from HardwareProfiler
            include_preferences: Include user preferences
            package_sources: List of package sources to export ['apt', 'pip', 'npm']
                           If None, exports all

        Returns:
            Success message with file path
        """
        if package_sources is None:
            package_sources = self.DEFAULT_SOURCES

        # Build configuration dictionary
        config: dict[str, Any] = {
            "cortex_version": self.CORTEX_VERSION,
            "exported_at": datetime.now().isoformat(),
            "os": self._detect_os_version(),
        }

        # Add hardware profile if requested
        if include_hardware:
            try:
                from cortex.hwprofiler import HardwareProfiler

                profiler = HardwareProfiler()
                config["hardware"] = profiler.profile()
            except Exception as e:
                config["hardware"] = {"error": f"Failed to detect hardware: {e}"}

        # Add packages
        config["packages"] = self.detect_installed_packages(sources=package_sources)

        # Add preferences if requested
        if include_preferences:
            config["preferences"] = self._load_preferences()

        # Add environment variables (selected safe ones)
        config["environment_variables"] = {}
        safe_env_vars = ["LANG", "LANGUAGE", "LC_ALL", "PATH", "SHELL"]
        for var in safe_env_vars:
            if var in os.environ:
                config["environment_variables"][var] = os.environ[var]

        # Write to file
        try:
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path_obj, "w") as f:
                yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

            return f"Configuration exported successfully to {output_path}"
        except Exception as e:
            raise RuntimeError(f"Failed to export configuration: {e}")

    def validate_compatibility(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate if configuration can be imported on this system.

        Args:
            config: Configuration dictionary from YAML

        Returns:
            Tuple of (is_compatible, reason_if_not)
        """
        # Check required fields
        if "cortex_version" not in config:
            return False, "Missing cortex_version field in configuration"

        if "os" not in config:
            return False, "Missing os field in configuration"

        if "packages" not in config:
            return False, "Missing packages field in configuration"

        # Check cortex version compatibility
        config_version = config["cortex_version"]
        current_version = self.CORTEX_VERSION

        # Parse versions (simple major.minor.patch comparison)
        try:
            config_parts = [int(x) for x in config_version.split(".")]
            current_parts = [int(x) for x in current_version.split(".")]

            # Major version must match
            if config_parts[0] != current_parts[0]:
                return (
                    False,
                    f"Incompatible major version: config={config_version}, current={current_version}",
                )

            # Minor version: current should be >= config
            if current_parts[1] < config_parts[1]:
                return (
                    False,
                    f"Configuration requires newer Cortex version: {config_version} > {current_version}",
                )
        except Exception as e:
            # If version parsing fails, be lenient
            logger.debug(f"Version parsing failed: {e}", exc_info=True)

        # Check OS compatibility (warn but allow)
        config_os = config.get("os", "unknown")
        current_os = self._detect_os_version()

        if config_os != current_os and config_os != "unknown" and current_os != "unknown":
            # Don't fail, just warn in the return message
            return (
                True,
                f"Warning: OS mismatch (config={config_os}, current={current_os}). Proceed with caution.",
            )

        return True, None

    def _categorize_package(
        self, pkg: dict[str, Any], current_pkg_map: dict[tuple[str, str], str]
    ) -> tuple[str, dict[str, Any] | None]:
        """
        Categorize a package as install, upgrade, downgrade, or already installed.

        Args:
            pkg: Package dictionary from config
            current_pkg_map: Map of (name, source) to current version

        Returns:
            Tuple of (category, package_data) where category is one of:
            'install', 'upgrade', 'downgrade', 'already_installed', 'skip'
            package_data is the modified package dict (with current_version if applicable)
        """
        name = pkg.get("name")
        version = pkg.get("version")
        source = pkg.get("source")

        if not name or not source:
            return "skip", None

        key = (name, source)

        if key not in current_pkg_map:
            return "install", pkg

        current_version = current_pkg_map[key]
        if current_version == version:
            return "already_installed", pkg

        # If the config doesn't specify a version, treat it as an upgrade/install request.
        if not isinstance(version, str) or not version:
            return "upgrade", {**pkg, "current_version": current_version}

        # Compare versions
        try:
            pkg_with_version = {**pkg, "current_version": current_version}
            if self._compare_versions(current_version, version) < 0:
                return "upgrade", pkg_with_version
            else:
                return "downgrade", pkg_with_version
        except Exception as e:
            # If comparison fails, treat as upgrade
            logger.debug(f"Version comparison failed: {e}", exc_info=True)
            return "upgrade", {**pkg, "current_version": current_version}

    def diff_configuration(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Compare current system state with configuration file.

        Args:
            config: Configuration dictionary from YAML

        Returns:
            Dictionary with differences
        """
        diff = {
            "packages_to_install": [],
            "packages_to_upgrade": [],
            "packages_to_downgrade": [],
            "packages_already_installed": [],
            "preferences_changed": {},
            "warnings": [],
        }

        # Get current packages
        current_packages = self.detect_installed_packages()
        current_pkg_map = {(pkg["name"], pkg["source"]): pkg["version"] for pkg in current_packages}

        # Compare packages from config
        config_packages = config.get("packages", [])
        for pkg in config_packages:
            category, pkg_data = self._categorize_package(pkg, current_pkg_map)

            if category == "skip":
                diff["warnings"].append(f"Malformed package entry skipped: {pkg}")
            elif category == "install":
                diff["packages_to_install"].append(pkg_data)
            elif category == "upgrade":
                diff["packages_to_upgrade"].append(pkg_data)
            elif category == "downgrade":
                diff["packages_to_downgrade"].append(pkg_data)
            elif category == "already_installed":
                diff["packages_already_installed"].append(pkg_data)

        # Compare preferences
        current_prefs = self._load_preferences()
        config_prefs = config.get("preferences", {})

        for key, value in config_prefs.items():
            if key not in current_prefs or current_prefs[key] != value:
                diff["preferences_changed"][key] = {"current": current_prefs.get(key), "new": value}

        # Add warnings
        if diff["packages_to_downgrade"]:
            diff["warnings"].append(
                f"Warning: {len(diff['packages_to_downgrade'])} packages will be downgraded"
            )

        return diff

    def _compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings using packaging library for robustness.

        Args:
            version1: First version string
            version2: Second version string

        Returns:
            -1 if version1 < version2, 0 if equal, 1 if version1 > version2
        """
        try:
            from packaging import version

            v1 = version.parse(version1)
            v2 = version.parse(version2)
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
            return 0
        except Exception as e:
            # Fallback to simple numeric comparison
            logger.debug(f"Version parsing failed, using simple comparison: {e}", exc_info=True)
            return self._simple_version_compare(version1, version2)

    def _simple_version_compare(self, version1: str, version2: str) -> int:
        """
        Fallback version comparison using numeric extraction.

        Used when the packaging library is unavailable or fails to parse
        version strings. Extracts numeric components and compares them
        sequentially, padding shorter versions with zeros.

        This method provides a basic version comparison by extracting all
        numeric parts from the version strings and comparing them position
        by position. It handles simple version schemes well but may not
        correctly handle complex pre-release tags or build metadata.

        Args:
            version1: First version string (e.g., "1.2.3", "2.0.0-rc1")
            version2: Second version string to compare against

        Returns:
            int: -1 if version1 < version2
                 0 if versions are equal
                 1 if version1 > version2

        Example:
            >>> _simple_version_compare("1.2.3", "1.2.4")
            -1
            >>> _simple_version_compare("2.0.0", "1.9.9")
            1
            >>> _simple_version_compare("1.0", "1.0.0")
            0

        Note:
            This is a simplified comparison that only considers numeric parts.
            Complex version schemes (pre-release tags, build metadata) may not
            be handled correctly. Prefer using packaging.version when available.
        """
        # Simple version comparison (extract numeric parts)
        v1_parts = re.findall(r"\d+", version1)
        v2_parts = re.findall(r"\d+", version2)

        # Handle case where no numeric parts found
        if not v1_parts and not v2_parts:
            return 0  # Both have no numeric parts, treat as equal
        if not v1_parts:
            return -1  # version1 has no numeric parts, consider it less
        if not v2_parts:
            return 1  # version2 has no numeric parts, consider it greater

        # Pad to same length
        max_len = max(len(v1_parts), len(v2_parts))
        v1_parts += ["0"] * (max_len - len(v1_parts))
        v2_parts += ["0"] * (max_len - len(v2_parts))

        for p1, p2 in zip(v1_parts, v2_parts):
            n1, n2 = int(p1), int(p2)
            if n1 < n2:
                return -1
            elif n1 > n2:
                return 1

        return 0

    def import_configuration(
        self,
        config_path: str,
        dry_run: bool = False,
        selective: list[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Import configuration from YAML file.

        Args:
            config_path: Path to YAML configuration file
            dry_run: If True, preview changes without applying
            selective: Import only specified sections ['packages', 'preferences']
                      If None, imports all
            force: Skip compatibility checks

        Returns:
            Summary dictionary with results
        """
        # Load configuration
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load configuration file: {e}")

        # Validate compatibility
        if not force:
            is_compatible, reason = self.validate_compatibility(config)
            if not is_compatible:
                raise RuntimeError(f"Incompatible configuration: {reason}")
            elif reason:  # Warning
                print(f"⚠️  {reason}")

        # If dry run, return diff
        if dry_run:
            diff = self.diff_configuration(config)
            return {
                "dry_run": True,
                "diff": diff,
                "message": "Dry-run completed. Use import without --dry-run to apply changes.",
            }

        # Determine what to import
        if selective is None:
            selective = ["packages", "preferences"]

        summary = {
            "installed": [],
            "upgraded": [],
            "downgraded": [],
            "failed": [],
            "skipped": [],
            "preferences_updated": False,
        }

        # Import packages
        if "packages" in selective:
            self._import_packages(config, summary)

        # Import preferences
        if "preferences" in selective:
            self._import_preferences(config, summary)

        return summary

    def _import_packages(self, config: dict[str, Any], summary: dict[str, Any]) -> None:
        """
        Import packages from configuration and update system state.

        This method processes package installations by first computing the
        difference between the current system state and the target configuration
        using diff_configuration(). It then attempts to install, upgrade, or
        downgrade packages as needed.

        The method continues processing all packages even if individual packages
        fail to install, ensuring maximum success. Failed installations are
        tracked in the summary for user review.

        Args:
            config: Configuration dictionary containing package specifications
                   Expected to have 'packages' key with list of package dicts
            summary: Summary dictionary to update with results. Modified in-place
                    with keys: 'installed', 'upgraded', 'failed'

        Updates:
            summary['installed']: List of successfully installed package names
            summary['upgraded']: List of successfully upgraded package names
            summary['failed']: List of failed package names (with error details)

        Note:
            Uses _install_package() internally for actual package installation.
            Each package is categorized based on diff results (install vs upgrade).
            Errors are caught and logged to allow processing to continue.
        """
        diff = self.diff_configuration(config)
        packages_to_process = (
            diff["packages_to_install"]
            + diff["packages_to_upgrade"]
            + diff["packages_to_downgrade"]
        )

        for pkg in packages_to_process:
            try:
                success = self._install_package(pkg)
                if success:
                    if pkg in diff["packages_to_install"]:
                        summary["installed"].append(pkg["name"])
                    elif pkg in diff["packages_to_downgrade"]:
                        summary["downgraded"].append(pkg["name"])
                    else:
                        summary["upgraded"].append(pkg["name"])
                else:
                    summary["failed"].append(pkg["name"])
            except Exception as e:
                summary["failed"].append(f"{pkg['name']} ({str(e)})")

    def _import_preferences(self, config: dict[str, Any], summary: dict[str, Any]) -> None:
        """
        Import user preferences from configuration and save to disk.

        Extracts preferences from the configuration dictionary and saves them
        to the user's Cortex preferences file at ~/.cortex/preferences.yaml.
        If preferences are empty or missing, no action is taken.

        This method handles the persistence of user-configurable settings such
        as confirmation levels, verbosity settings, and other behavioral
        preferences for the Cortex system.

        Args:
            config: Configuration dictionary containing optional 'preferences' key
                   with user preference settings as a dictionary
            summary: Summary dictionary to update with results. Modified in-place
                    with keys: 'preferences_updated', 'failed'

        Updates:
            summary['preferences_updated']: Set to True on successful save
            summary['failed']: Appends error message if save fails

        Note:
            Uses _save_preferences() internally to persist to disk.
            Errors during save are caught and added to failed list with details.
            If config has no preferences or they are empty, silently succeeds.
        """
        config_prefs = config.get("preferences", {})
        if config_prefs:
            try:
                self._save_preferences(config_prefs)
                summary["preferences_updated"] = True
            except Exception as e:
                summary["failed"].append(f"preferences ({str(e)})")

    def _validate_package_identifier(self, identifier: str, allow_slash: bool = False) -> bool:
        """
        Validate package name or version contains only safe characters.

        Prevents command injection by ensuring package identifiers only contain
        alphanumeric characters and common package naming characters.
        Supports NPM scoped packages (@scope/package) when allow_slash=True.

        Args:
            identifier: Package name or version string to validate
            allow_slash: Whether to allow a single slash (for NPM scoped packages)

        Returns:
            bool: True if identifier is safe, False otherwise
        """
        # Reject path-like patterns immediately
        if identifier.startswith(".") or identifier.startswith("/") or identifier.startswith("~"):
            return False
        if ".." in identifier or "/." in identifier:
            return False

        # Apply character whitelist with optional slash support
        if allow_slash:
            # Allow exactly one forward slash for NPM scoped packages (@scope/package)
            return bool(re.match(r"^[a-zA-Z0-9._:@=+\-]+(/[a-zA-Z0-9._\-]+)?$", identifier))
        else:
            # No slashes allowed for versions or non-NPM packages
            return bool(re.match(r"^[a-zA-Z0-9._:@=+\-]+$", identifier))

    def _install_with_sandbox(self, name: str, version: str | None, source: str) -> bool:
        """
        Install package using sandbox executor.

        Args:
            name: Package name
            version: Package version (optional)
            source: Package source (apt/pip/npm)

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.sandbox_executor is None:
                # Sandboxed installs are the default. Only allow direct installs
                # if user has explicitly opted in (check CORTEX_ALLOW_DIRECT_INSTALL env var)
                allow_direct = os.environ.get("CORTEX_ALLOW_DIRECT_INSTALL", "").lower() == "true"

                # Log audit entry for this attempt
                self._log_install_audit(
                    package_name=name,
                    version=version,
                    source=source,
                    is_dry_run=False,
                    is_sandboxed=False,
                    is_direct=allow_direct,
                    escalation_consent=allow_direct,
                    error="Sandbox executor unavailable",
                )

                if not allow_direct:
                    # Refuse direct install unless explicitly opted in
                    return False

                # User opted in, proceed with direct install
                return self._install_direct(name=name, version=version, source=source)

            if source == self.SOURCE_APT:
                command = (
                    f"sudo apt-get install -y {name}={version}"
                    if version
                    else f"sudo apt-get install -y {name}"
                )
            elif source == self.SOURCE_PIP:
                command = f"pip3 install {name}=={version}" if version else f"pip3 install {name}"
            elif source == self.SOURCE_NPM:
                command = (
                    f"npm install -g {name}@{version}" if version else f"npm install -g {name}"
                )
            else:
                return False

            result = self.sandbox_executor.execute(command)
            return result.success
        except Exception as e:
            logger.error(f"Sandboxed install failed for {name}: {e}", exc_info=True)
            return False

    def _log_install_audit(
        self,
        package_name: str,
        version: str | None,
        source: str,
        is_dry_run: bool,
        is_sandboxed: bool,
        is_direct: bool,
        escalation_consent: bool,
        error: str | None = None,
    ) -> None:
        """
        Log install attempt to audit database.

        Args:
            package_name: Package name
            version: Package version
            source: Package source
            is_dry_run: Whether this was a dry-run
            is_sandboxed: Whether sandboxed install was used
            is_direct: Whether direct install was used
            escalation_consent: Whether user consented to privilege escalation
            error: Error message if any
        """
        try:
            import sqlite3
            from datetime import datetime

            # Use ~/.cortex/history.db for audit logging
            audit_db_path = Path.home() / ".cortex" / "history.db"
            audit_db_path.parent.mkdir(parents=True, exist_ok=True)

            with sqlite3.connect(str(audit_db_path)) as conn:
                cursor = conn.cursor()

                # Create audit table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS install_audit (
                        timestamp TEXT NOT NULL,
                        package_name TEXT NOT NULL,
                        version TEXT,
                        source TEXT NOT NULL,
                        is_dry_run INTEGER NOT NULL,
                        is_sandboxed INTEGER NOT NULL,
                        is_direct INTEGER NOT NULL,
                        escalation_consent INTEGER NOT NULL,
                        error TEXT
                    )
                """)

                # Insert audit record
                cursor.execute(
                    """
                    INSERT INTO install_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        datetime.now().isoformat(),
                        package_name,
                        version,
                        source,
                        1 if is_dry_run else 0,
                        1 if is_sandboxed else 0,
                        1 if is_direct else 0,
                        1 if escalation_consent else 0,
                        error,
                    ),
                )

                conn.commit()
        except Exception:
            # Don't fail the install if audit logging fails
            logger.warning("Install audit logging failed", exc_info=True)

    def _install_direct(self, name: str, version: str | None, source: str) -> bool:
        """
        Install package directly using subprocess (not recommended in production).

        Args:
            name: Package name
            version: Package version (optional)
            source: Package source (apt/pip/npm)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Log audit entry for direct install
            self._log_install_audit(
                package_name=name,
                version=version,
                source=source,
                is_dry_run=False,
                is_sandboxed=False,
                is_direct=True,
                escalation_consent=True,
            )
            if source == self.SOURCE_APT:
                cmd = ["sudo", "apt-get", "install", "-y", f"{name}={version}" if version else name]
            elif source == self.SOURCE_PIP:
                cmd = (
                    ["pip3", "install", f"{name}=={version}"]
                    if version
                    else ["pip3", "install", name]
                )
            elif source == self.SOURCE_NPM:
                cmd = (
                    ["npm", "install", "-g", f"{name}@{version}"]
                    if version
                    else ["npm", "install", "-g", name]
                )
            else:
                return False

            result = subprocess.run(cmd, capture_output=True, timeout=self.INSTALLATION_TIMEOUT)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Direct install failed for {name}: {e}", exc_info=True)
            return False

    def _install_package(self, pkg: dict[str, Any]) -> bool:
        """
        Install a single package using appropriate package manager.

        Args:
            pkg: Package dictionary with name, version, source

        Returns:
            True if successful, False otherwise
        """
        name = pkg["name"]
        version = pkg.get("version", "")
        source = pkg["source"]

        # Validate package identifiers to prevent command injection
        # Allow slash only for NPM package names (for scoped packages like @scope/package)
        allow_slash = source == self.SOURCE_NPM
        if not self._validate_package_identifier(name, allow_slash=allow_slash):
            return False
        if version and not self._validate_package_identifier(version, allow_slash=False):
            return False

        if self.sandbox_executor:
            return self._install_with_sandbox(name, version or None, source)
        else:
            return self._install_direct(name, version or None, source)


def _setup_argument_parser():
    """Create and configure argument parser for CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="Cortex Configuration Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export system configuration")
    export_parser.add_argument("--output", "-o", required=True, help="Output file path")
    export_parser.add_argument(
        "--include-hardware", action="store_true", help="Include hardware information"
    )
    export_parser.add_argument(
        "--no-preferences", action="store_true", help="Exclude user preferences"
    )
    export_parser.add_argument("--packages-only", action="store_true", help="Export only packages")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import configuration")
    import_parser.add_argument("config_file", help="Configuration file to import")
    import_parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without applying"
    )
    import_parser.add_argument("--force", action="store_true", help="Skip compatibility checks")
    import_parser.add_argument("--packages-only", action="store_true", help="Import only packages")
    import_parser.add_argument(
        "--preferences-only", action="store_true", help="Import only preferences"
    )

    # Diff command
    diff_parser = subparsers.add_parser("diff", help="Show configuration differences")
    diff_parser.add_argument("config_file", help="Configuration file to compare")

    return parser


def _print_package_list(packages: list[dict[str, Any]], max_display: int = 5) -> None:
    """Print a list of packages with optional truncation."""
    for pkg in packages[:max_display]:
        if "current_version" in pkg:
            print(f"   - {pkg['name']} ({pkg.get('current_version')} → {pkg['version']})")
        else:
            print(f"   - {pkg['name']} ({pkg['source']})")

    if len(packages) > max_display:
        print(f"   ... and {len(packages) - max_display} more")


def _print_dry_run_results(result: dict[str, Any]) -> None:
    """Print dry-run results in a formatted manner."""
    print("\n🔍 Dry-run results:\n")
    diff = result["diff"]

    if diff["packages_to_install"]:
        print(f"📦 Packages to install: {len(diff['packages_to_install'])}")
        _print_package_list(diff["packages_to_install"])

    if diff["packages_to_upgrade"]:
        print(f"\n⬆️  Packages to upgrade: {len(diff['packages_to_upgrade'])}")
        _print_package_list(diff["packages_to_upgrade"])

    if diff["packages_to_downgrade"]:
        print(f"\n⬇️  Packages to downgrade: {len(diff['packages_to_downgrade'])}")
        _print_package_list(diff["packages_to_downgrade"])

    if diff["preferences_changed"]:
        print(f"\n⚙️  Preferences to change: {len(diff['preferences_changed'])}")
        for key in diff["preferences_changed"]:
            print(f"   - {key}")

    if diff["warnings"]:
        print("\n⚠️  Warnings:")
        for warning in diff["warnings"]:
            print(f"   {warning}")

    print(f"\n{result['message']}")


def _print_import_results(result: dict[str, Any]) -> None:
    """Print import results in a formatted manner."""
    print("\n✅ Import completed:\n")

    if result["installed"]:
        print(f"📦 Installed: {len(result['installed'])} packages")
    if result["upgraded"]:
        print(f"⬆️  Upgraded: {len(result['upgraded'])} packages")
    if result.get("downgraded"):
        print(f"⬇️  Downgraded: {len(result['downgraded'])} packages")
    if result["failed"]:
        print(f"❌ Failed: {len(result['failed'])} packages")
        for pkg in result["failed"]:
            print(f"   - {pkg}")
    if result["preferences_updated"]:
        print("⚙️  Preferences updated")


def _handle_export_command(manager: "ConfigManager", args) -> None:
    """Handle the export command."""
    include_hardware = args.include_hardware
    include_preferences = not args.no_preferences

    if args.packages_only:
        include_hardware = False
        include_preferences = False

    message = manager.export_configuration(
        output_path=args.output,
        include_hardware=include_hardware,
        include_preferences=include_preferences,
    )
    print(message)


def _handle_import_command(manager: "ConfigManager", args) -> None:
    """Handle the import command."""
    selective = None
    if args.packages_only:
        selective = ["packages"]
    elif args.preferences_only:
        selective = ["preferences"]

    result = manager.import_configuration(
        config_path=args.config_file, dry_run=args.dry_run, selective=selective, force=args.force
    )

    if args.dry_run:
        _print_dry_run_results(result)
    else:
        _print_import_results(result)


def _handle_diff_command(manager: "ConfigManager", args) -> None:
    """Handle the diff command."""
    with open(args.config_file) as f:
        config = yaml.safe_load(f)

    diff = manager.diff_configuration(config)

    print("\n📊 Configuration Differences:\n")
    print(f"Packages to install: {len(diff['packages_to_install'])}")
    print(f"Packages to upgrade: {len(diff['packages_to_upgrade'])}")
    print(f"Packages to downgrade: {len(diff['packages_to_downgrade'])}")
    print(f"Packages already installed: {len(diff['packages_already_installed'])}")
    print(f"Preferences changed: {len(diff['preferences_changed'])}")

    if diff["warnings"]:
        print("\n⚠️  Warnings:")
        for warning in diff["warnings"]:
            print(f"   {warning}")


def main():
    """CLI entry point for configuration manager."""
    import sys

    parser = _setup_argument_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    manager = ConfigManager()

    try:
        if args.command == "export":
            _handle_export_command(manager, args)
        elif args.command == "import":
            _handle_import_command(manager, args)
        elif args.command == "diff":
            _handle_diff_command(manager, args)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
