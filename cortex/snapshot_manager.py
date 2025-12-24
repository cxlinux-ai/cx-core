#!/usr/bin/env python3
"""
System Snapshot and Rollback Points Manager

Provides system-wide snapshot capabilities for Cortex Linux.
Complements installation_history.py with full system state snapshots.

Issue: #45
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from filelock import FileLock, Timeout as FileLockTimeout

logger = logging.getLogger(__name__)


@dataclass
class SnapshotMetadata:
    """Metadata for a system snapshot"""

    id: str
    timestamp: str
    description: str
    packages: dict[str, list[dict[str, str]]]  # source -> [{"name": "", "version": ""}]
    system_info: dict[str, str]
    file_count: int = 0
    size_bytes: int = 0


class SnapshotManager:
    """
    Manages system snapshots for rollback capability.

    Features:
    - Create snapshots of installed packages (APT, PIP, NPM)
    - Store snapshot metadata with descriptions
    - List all available snapshots
    - Restore system to a previous snapshot state
    - Auto-cleanup old snapshots (configurable retention policy)
    - User-configurable via preferences
    """

    DEFAULT_RETENTION_LIMIT = 10
    TIMEOUT = 30  # seconds for package detection
    RESTORE_TIMEOUT = 300  # seconds for package install/remove operations

    def __init__(self, snapshots_dir: Path | None = None, retention_limit: int | None = None):
        """
        Initialize SnapshotManager.

        Args:
            snapshots_dir: Directory to store snapshots (defaults to ~/.cortex/snapshots)
            retention_limit: Maximum snapshots to keep (defaults to user preference or 10)
        """
        self.snapshots_dir = snapshots_dir or Path.home() / ".cortex" / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Thread safety lock for concurrent operations
        self._lock = threading.RLock()
        
        # File lock path for multi-process synchronization
        self._file_lock_path = self.snapshots_dir / ".snapshots.lock"
        
        # Load retention limit from preferences or use provided/default
        if retention_limit is not None:
            self.retention_limit = retention_limit
        else:
            self.retention_limit = self._load_retention_from_preferences()
        
        self._enforce_directory_security()

    def _load_retention_from_preferences(self) -> int:
        """Load retention limit from user preferences"""
        try:
            from cortex.user_preferences import PreferencesManager
            prefs_manager = PreferencesManager()
            prefs = prefs_manager.get_preferences()
            return prefs.snapshots.retention_limit
        except Exception:
            # Fall back to default if preferences not available
            return self.DEFAULT_RETENTION_LIMIT

    def _enforce_directory_security(self) -> None:
        """Ensure snapshots directory has secure permissions (700)"""
        try:
            self.snapshots_dir.chmod(0o700)
        except Exception as e:
            logger.warning(f"Could not set directory permissions: {e}")

    def _generate_snapshot_id(self) -> str:
        """Generate unique snapshot ID with timestamp and UUID to prevent collisions"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_suffix = uuid.uuid4().hex[:8]
        return f"{timestamp}_{unique_suffix}"

    def _get_snapshot_path(self, snapshot_id: str) -> Path:
        """Get path to snapshot directory"""
        return self.snapshots_dir / snapshot_id

    def _get_metadata_path(self, snapshot_id: str) -> Path:
        """Get path to snapshot metadata file"""
        return self._get_snapshot_path(snapshot_id) / "metadata.json"
    
    def _safe_read_json(self, file_path: Path, max_retries: int = 3) -> dict | None:
        """Safely read JSON file with retry on corruption.
        
        Args:
            file_path: Path to JSON file
            max_retries: Maximum number of retry attempts
            
        Returns:
            Parsed JSON data or None if file is corrupted/missing
        """
        for attempt in range(max_retries):
            try:
                if not file_path.exists():
                    return None
                with open(file_path) as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"JSON corruption detected in {file_path}, retry {attempt + 1}/{max_retries}")
                    import time
                    time.sleep(0.1)  # Brief delay before retry
                else:
                    logger.error(f"Failed to read JSON after {max_retries} attempts: {e}")
                    return None
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")
                return None
        return None

    def _run_package_detection(
        self, cmd: list[str], parser_func: Callable[[str], list[dict[str, str]]], manager_name: str
    ) -> list[dict[str, str]]:
        """Generic package detection with command execution and parsing.

        Args:
            cmd: Command to execute as list
            parser_func: Function to parse stdout into package list
            manager_name: Name of package manager for logging

        Returns:
            List of package dictionaries with 'name' and 'version' keys
        """
        packages = []
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT,
                check=False,
            )
            if result.returncode == 0:
                packages = parser_func(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"{manager_name} package detection failed: {e}")
        return packages

    def _parse_apt_output(self, stdout: str) -> list[dict[str, str]]:
        """Parse APT package output."""
        packages = []
        for line in stdout.strip().split("\n"):
            if line.strip():
                parts = line.split("\t")
                if len(parts) >= 2:
                    packages.append({"name": parts[0], "version": parts[1]})
        return packages

    def _parse_pip_output(self, stdout: str) -> list[dict[str, str]]:
        """Parse PIP package output."""
        packages = []
        pip_packages = json.loads(stdout)
        for pkg in pip_packages:
            packages.append({"name": pkg["name"], "version": pkg["version"]})
        return packages

    def _parse_npm_output(self, stdout: str) -> list[dict[str, str]]:
        """Parse NPM package output."""
        packages = []
        npm_data = json.loads(stdout)
        if "dependencies" in npm_data:
            for name, info in npm_data["dependencies"].items():
                packages.append({"name": name, "version": info.get("version", "")})
        return packages

    def _detect_apt_packages(self) -> list[dict[str, str]]:
        """Detect installed APT packages"""
        return self._run_package_detection(
            ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"], self._parse_apt_output, "APT"
        )

    def _detect_pip_packages(self) -> list[dict[str, str]]:
        """Detect installed PIP packages"""
        return self._run_package_detection(
            [sys.executable, "-m", "pip", "list", "--format=json"], self._parse_pip_output, "PIP"
        )

    def _detect_npm_packages(self) -> list[dict[str, str]]:
        """Detect installed NPM packages (global)"""
        return self._run_package_detection(
            ["npm", "list", "-g", "--json", "--depth=0"], self._parse_npm_output, "NPM"
        )

    def _get_system_info(self) -> dict[str, str]:
        """Gather system information"""
        info = {}
        try:
            # OS information
            with open("/etc/os-release") as f:
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        info[key.lower()] = value.strip('"')

            # Kernel version
            result = subprocess.run(
                ["uname", "-r"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0:
                info["kernel"] = result.stdout.strip()

            # Architecture
            result = subprocess.run(
                ["uname", "-m"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0:
                info["arch"] = result.stdout.strip()

        except Exception as e:
            logger.warning(f"System info detection failed: {e}")
        return info

    def create_snapshot(self, description: str = "") -> tuple[bool, str | None, str]:
        """
        Create a new system snapshot (thread-safe and process-safe).

        Args:
            description: Human-readable snapshot description

        Returns:
            Tuple of (success, snapshot_id, message)
        """
        snapshot_path = None
        try:
            # Generate ID and create directory (quick, lock not needed for UUID-based IDs)
            snapshot_id = self._generate_snapshot_id()
            snapshot_path = self._get_snapshot_path(snapshot_id)
            
            # Check for collision (shouldn't happen with UUID, but be safe)
            if snapshot_path.exists():
                logger.warning(f"Snapshot ID collision detected: {snapshot_id}")
                snapshot_id = self._generate_snapshot_id()
                snapshot_path = self._get_snapshot_path(snapshot_id)
            
            snapshot_path.mkdir(parents=True, exist_ok=False)
            # Enforce strict permissions; initial mkdir permissions are subject to umask
            os.chmod(snapshot_path, 0o700)

            # Detect installed packages (SLOW - no lock needed, each process reads independently)
            logger.info("Detecting installed packages...")
            packages = {
                "apt": self._detect_apt_packages(),
                "pip": self._detect_pip_packages(),
                "npm": self._detect_npm_packages(),
            }

            # Get system info (quick, no lock needed)
            system_info = self._get_system_info()

            # Create metadata
            metadata = SnapshotMetadata(
                id=snapshot_id,
                timestamp=datetime.now().isoformat(),
                description=description,
                packages=packages,
                system_info=system_info,
                file_count=sum(len(pkgs) for pkgs in packages.values()),
                size_bytes=0,  # Could calculate actual size if needed
            )

            # CRITICAL SECTION: Lock only for JSON writes and retention policy
            # This is fast (~100ms), so multiple processes can queue quickly
            file_lock = FileLock(str(self._file_lock_path), timeout=10)
            try:
                with file_lock, self._lock:
                    # Save metadata with secure permissions (600) using atomic write
                    metadata_path = self._get_metadata_path(snapshot_id)
                    temp_path = metadata_path.with_suffix(".tmp")
                    
                    # Write to temporary file first (atomic operation)
                    fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "w") as f:
                        json.dump(asdict(metadata), f, indent=2)
                    
                    # Atomic rename
                    temp_path.rename(metadata_path)

                    # Apply retention policy (fast - just directory listing and deletes)
                    self._apply_retention_policy()
            except FileLockTimeout:
                # Lock timeout only for the final write - shouldn't happen with 10s timeout
                logger.error("Timeout waiting for file lock during snapshot finalization")
                raise  # Re-raise to trigger cleanup

            logger.info(f"Snapshot created: {snapshot_id}")
            return (
                True,
                snapshot_id,
                f"Snapshot {snapshot_id} created successfully with {metadata.file_count} packages",
            )

        except FileLockTimeout:
            logger.error("Timeout waiting for file lock - another process is writing snapshot")
            # Cleanup on failure
            try:
                if snapshot_path and snapshot_path.exists():
                    shutil.rmtree(snapshot_path)
            except Exception:
                pass
            return (False, None, "Timeout during snapshot finalization, please retry")
        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            # Cleanup on failure
            try:
                if snapshot_path and snapshot_path.exists():
                    shutil.rmtree(snapshot_path)
            except Exception:
                pass
            return (False, None, f"Failed to create snapshot: {e}")

    def _list_snapshots_unsafe(self) -> list[SnapshotMetadata]:
        """
        List snapshots WITHOUT acquiring lock (for internal use within locked context).
        
        Returns:
            List of SnapshotMetadata objects sorted by timestamp (newest first)
        """
        snapshots = []
        try:
            for snapshot_dir in sorted(self.snapshots_dir.iterdir(), reverse=True):
                if snapshot_dir.is_dir() and snapshot_dir.name != ".snapshots.lock":
                    metadata_path = snapshot_dir / "metadata.json"
                    data = self._safe_read_json(metadata_path)
                    if data:
                        try:
                            snapshots.append(SnapshotMetadata(**data))
                        except Exception as e:
                            logger.warning(f"Invalid metadata in {snapshot_dir.name}: {e}")
        except Exception as e:
            logger.error(f"Failed to list snapshots: {e}")
        return snapshots

    def list_snapshots(self) -> list[SnapshotMetadata]:
        """
        List all available snapshots (process-safe).

        Returns:
            List of SnapshotMetadata objects sorted by timestamp (newest first)
        """
        file_lock = FileLock(str(self._file_lock_path), timeout=10)
        
        try:
            with file_lock:
                return self._list_snapshots_unsafe()
        except FileLockTimeout:
            logger.warning("Timeout waiting for file lock while listing snapshots")
            return []
        except Exception as e:
            logger.error(f"Failed to list snapshots: {e}")
            return []

    def get_snapshot(self, snapshot_id: str) -> SnapshotMetadata | None:
        """
        Get metadata for a specific snapshot.

        Args:
            snapshot_id: ID of the snapshot

        Returns:
            SnapshotMetadata object or None if not found
        """
        try:
            metadata_path = self._get_metadata_path(snapshot_id)
            data = self._safe_read_json(metadata_path)
            if data:
                return SnapshotMetadata(**data)
        except Exception as e:
            logger.error(f"Failed to get snapshot {snapshot_id}: {e}")
        return None

    def _delete_snapshot_unsafe(self, snapshot_id: str) -> tuple[bool, str]:
        """
        Delete snapshot WITHOUT acquiring lock (for internal use within locked context).
        
        Args:
            snapshot_id: ID of the snapshot to delete
            
        Returns:
            Tuple of (success, message)
        """
        try:
            snapshot_path = self._get_snapshot_path(snapshot_id)
            if not snapshot_path.exists():
                return (False, f"Snapshot {snapshot_id} not found")

            shutil.rmtree(snapshot_path)
            logger.info(f"Snapshot deleted: {snapshot_id}")
            return (True, f"Snapshot {snapshot_id} deleted successfully")

        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return (False, f"Failed to delete snapshot: {e}")

    def delete_snapshot(self, snapshot_id: str) -> tuple[bool, str]:
        """
        Delete a snapshot (thread-safe and process-safe).

        Args:
            snapshot_id: ID of the snapshot to delete

        Returns:
            Tuple of (success, message)
        """
        file_lock = FileLock(str(self._file_lock_path), timeout=10)
        
        try:
            with file_lock, self._lock:
                return self._delete_snapshot_unsafe(snapshot_id)
        
        except FileLockTimeout:
            logger.error("Timeout waiting for file lock during deletion")
            return (False, "Snapshot deletion in progress by another process, please wait")

    def _execute_package_command(self, cmd_list: list[str], dry_run: bool) -> None:
        """Execute a package management command with timeout protection.

        Args:
            cmd_list: Command and arguments as a list
            dry_run: If True, skip execution

        Raises:
            subprocess.CalledProcessError: If command fails
            subprocess.TimeoutExpired: If command times out
        """
        if not dry_run:
            subprocess.run(
                cmd_list, check=True, capture_output=True, text=True, timeout=self.RESTORE_TIMEOUT
            )

    def _restore_package_manager(
        self,
        manager: str,
        snapshot_packages: dict[str, str],
        current_packages: dict[str, str],
        dry_run: bool,
        commands: list[str],
    ) -> None:
        """Restore packages for a specific package manager.

        Args:
            manager: Package manager name ('apt', 'pip', 'npm')
            snapshot_packages: Packages in snapshot {name: version}
            current_packages: Currently installed packages {name: version}
            dry_run: If True, only record commands without executing
            commands: List to append commands to
        """
        to_install = set(snapshot_packages.keys()) - set(current_packages.keys())
        to_remove = set(current_packages.keys()) - set(snapshot_packages.keys())

        # Define manager-specific command templates
        remove_cmds = {
            "apt": ["sudo", "apt-get", "remove", "-y"],
            "pip": ["pip", "uninstall", "-y"],
            "npm": ["npm", "uninstall", "-g"],
        }
        install_cmds = {
            "apt": ["sudo", "apt-get", "install", "-y"],
            "pip": ["pip", "install"],
            "npm": ["npm", "install", "-g"],
        }
        version_formats = {
            "apt": lambda name, ver: f"{name}={ver}" if ver else name,
            "pip": lambda name, ver: f"{name}=={ver}" if ver else name,
            "npm": lambda name, ver: f"{name}@{ver}" if ver else name,
        }

        if to_remove:
            cmd_list = remove_cmds[manager] + sorted(to_remove)
            commands.append(" ".join(cmd_list))
            self._execute_package_command(cmd_list, dry_run)

        if to_install:
            fmt = version_formats[manager]
            packages = [fmt(name, snapshot_packages[name]) for name in sorted(to_install)]
            cmd_list = install_cmds[manager] + packages
            commands.append(" ".join(cmd_list))
            self._execute_package_command(cmd_list, dry_run)

    def restore_snapshot(
        self, snapshot_id: str, dry_run: bool = False
    ) -> tuple[bool, str, list[str]]:
        """
        Restore system to a previous snapshot state.

        Args:
            snapshot_id: ID of the snapshot to restore
            dry_run: If True, only show what would be done

        Returns:
            Tuple of (success, message, commands_executed)
        """
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return (False, f"Snapshot {snapshot_id} not found", [])

        # Check sudo permissions before attempting restore (unless dry-run)
        if not dry_run:
            try:
                result = subprocess.run(
                    ["sudo", "-n", "true"], capture_output=True, timeout=5, check=False
                )
                if result.returncode != 0:
                    return (False, "Restore requires sudo privileges. Please run: sudo -v", [])
            except Exception as e:
                logger.warning(f"Could not verify sudo permissions: {e}")

        commands = []
        try:
            # Get current package state
            current_apt = {pkg["name"]: pkg["version"] for pkg in self._detect_apt_packages()}
            current_pip = {pkg["name"]: pkg["version"] for pkg in self._detect_pip_packages()}
            current_npm = {pkg["name"]: pkg["version"] for pkg in self._detect_npm_packages()}

            # Restore packages for each manager
            snapshot_apt = {pkg["name"]: pkg["version"] for pkg in snapshot.packages.get("apt", [])}
            self._restore_package_manager("apt", snapshot_apt, current_apt, dry_run, commands)

            snapshot_pip = {pkg["name"]: pkg["version"] for pkg in snapshot.packages.get("pip", [])}
            self._restore_package_manager("pip", snapshot_pip, current_pip, dry_run, commands)

            snapshot_npm = {pkg["name"]: pkg["version"] for pkg in snapshot.packages.get("npm", [])}
            self._restore_package_manager("npm", snapshot_npm, current_npm, dry_run, commands)

            if dry_run:
                return (
                    True,
                    f"Dry-run complete. {len(commands)} commands would be executed.",
                    commands,
                )
            else:
                return (True, f"Successfully restored snapshot {snapshot_id}", commands)

        except subprocess.TimeoutExpired as e:
            logger.error(f"Command timed out during restore: {e}")
            cmd_str = " ".join(e.cmd) if isinstance(e.cmd, list) else str(e.cmd)
            error_msg = f"Restore failed. Command timed out after {e.timeout}s: {cmd_str}"
            return (False, error_msg, commands)
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed during restore: {e}")
            stderr_msg = e.stderr if hasattr(e, "stderr") and e.stderr else str(e)
            error_msg = f"Restore failed. Command: {' '.join(e.cmd) if isinstance(e.cmd, list) else e.cmd}. Error: {stderr_msg}"
            return (False, error_msg, commands)
        except Exception as e:
            logger.error(f"Failed to restore snapshot {snapshot_id}: {e}")
            return (False, f"Failed to restore snapshot: {e}", commands)

    def _apply_retention_policy(self) -> None:
        """Remove oldest snapshots if count exceeds retention_limit (called within lock)"""
        try:
            # Use unsafe version since we're already holding the lock
            snapshots = self._list_snapshots_unsafe()
            if len(snapshots) > self.retention_limit:
                # Sort by timestamp (oldest first)
                snapshots.sort(key=lambda s: s.timestamp)

                # Delete oldest snapshots using unsafe version (already holding lock)
                to_delete = len(snapshots) - self.retention_limit
                for i in range(to_delete):
                    snapshot_id = snapshots[i].id
                    success, message = self._delete_snapshot_unsafe(snapshot_id)
                    if success:
                        logger.info(f"Retention policy: deleted old snapshot {snapshot_id}")
                    else:
                        logger.warning(f"Retention policy: failed to delete {snapshot_id}: {message}")

        except Exception as e:
            logger.warning(f"Failed to apply retention policy: {e}")
