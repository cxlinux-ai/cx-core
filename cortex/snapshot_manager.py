#!/usr/bin/env python3
"""
System Snapshot and Rollback Points Manager

Provides system-wide snapshot capabilities for Cortex Linux.
Complements installation_history.py with full system state snapshots.

Issue: #45
"""

import json
import logging
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    - Auto-cleanup old snapshots (retention policy: 10 max)
    """

    RETENTION_LIMIT = 10
    TIMEOUT = 30  # seconds for package detection

    def __init__(self, snapshots_dir: Optional[Path] = None):
        """
        Initialize SnapshotManager.

        Args:
            snapshots_dir: Directory to store snapshots (defaults to ~/.cortex/snapshots)
        """
        self.snapshots_dir = snapshots_dir or Path.home() / ".cortex" / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self._enforce_directory_security()

    def _enforce_directory_security(self) -> None:
        """Ensure snapshots directory has secure permissions (700)"""
        try:
            self.snapshots_dir.chmod(0o700)
        except Exception as e:
            logger.warning(f"Could not set directory permissions: {e}")

    def _generate_snapshot_id(self) -> str:
        """Generate unique snapshot ID based on timestamp with microseconds"""
        return datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    def _get_snapshot_path(self, snapshot_id: str) -> Path:
        """Get path to snapshot directory"""
        return self.snapshots_dir / snapshot_id

    def _get_metadata_path(self, snapshot_id: str) -> Path:
        """Get path to snapshot metadata file"""
        return self._get_snapshot_path(snapshot_id) / "metadata.json"

    def _detect_apt_packages(self) -> list[dict[str, str]]:
        """Detect installed APT packages"""
        packages = []
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"],
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT,
                check=False,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            packages.append({"name": parts[0], "version": parts[1]})
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"APT package detection failed: {e}")
        return packages

    def _detect_pip_packages(self) -> list[dict[str, str]]:
        """Detect installed PIP packages"""
        packages = []
        try:
            result = subprocess.run(
                ["pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT,
                check=False,
            )
            if result.returncode == 0:
                pip_packages = json.loads(result.stdout)
                for pkg in pip_packages:
                    packages.append({"name": pkg["name"], "version": pkg["version"]})
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"PIP package detection failed: {e}")
        return packages

    def _detect_npm_packages(self) -> list[dict[str, str]]:
        """Detect installed NPM packages (global)"""
        packages = []
        try:
            result = subprocess.run(
                ["npm", "list", "-g", "--json", "--depth=0"],
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT,
                check=False,
            )
            if result.returncode == 0:
                npm_data = json.loads(result.stdout)
                if "dependencies" in npm_data:
                    for name, info in npm_data["dependencies"].items():
                        packages.append({"name": name, "version": info.get("version", "unknown")})
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"NPM package detection failed: {e}")
        return packages

    def _get_system_info(self) -> dict[str, str]:
        """Gather system information"""
        info = {}
        try:
            # OS information
            with open("/etc/os-release", "r") as f:
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
            )
            if result.returncode == 0:
                info["kernel"] = result.stdout.strip()
                
            # Architecture
            result = subprocess.run(
                ["uname", "-m"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                info["arch"] = result.stdout.strip()
                
        except Exception as e:
            logger.warning(f"System info detection failed: {e}")
        return info

    def create_snapshot(self, description: str = "") -> tuple[bool, Optional[str], str]:
        """
        Create a new system snapshot.

        Args:
            description: Human-readable snapshot description

        Returns:
            Tuple of (success, snapshot_id, message)
        """
        try:
            snapshot_id = self._generate_snapshot_id()
            snapshot_path = self._get_snapshot_path(snapshot_id)
            snapshot_path.mkdir(parents=True, exist_ok=True)

            # Detect installed packages
            logger.info("Detecting installed packages...")
            packages = {
                "apt": self._detect_apt_packages(),
                "pip": self._detect_pip_packages(),
                "npm": self._detect_npm_packages(),
            }

            # Get system info
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

            # Save metadata
            metadata_path = self._get_metadata_path(snapshot_id)
            with open(metadata_path, "w") as f:
                json.dump(asdict(metadata), f, indent=2)

            # Apply retention policy
            self._apply_retention_policy()

            logger.info(f"Snapshot created: {snapshot_id}")
            return (
                True,
                snapshot_id,
                f"Snapshot {snapshot_id} created successfully with {metadata.file_count} packages",
            )

        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            return (False, None, f"Failed to create snapshot: {e}")

    def list_snapshots(self) -> list[SnapshotMetadata]:
        """
        List all available snapshots.

        Returns:
            List of SnapshotMetadata objects sorted by timestamp (newest first)
        """
        snapshots = []
        try:
            for snapshot_dir in sorted(self.snapshots_dir.iterdir(), reverse=True):
                if snapshot_dir.is_dir():
                    metadata_path = snapshot_dir / "metadata.json"
                    if metadata_path.exists():
                        with open(metadata_path, "r") as f:
                            data = json.load(f)
                            snapshots.append(SnapshotMetadata(**data))
        except Exception as e:
            logger.error(f"Failed to list snapshots: {e}")
        return snapshots

    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotMetadata]:
        """
        Get metadata for a specific snapshot.

        Args:
            snapshot_id: ID of the snapshot

        Returns:
            SnapshotMetadata object or None if not found
        """
        try:
            metadata_path = self._get_metadata_path(snapshot_id)
            if metadata_path.exists():
                with open(metadata_path, "r") as f:
                    data = json.load(f)
                    return SnapshotMetadata(**data)
        except Exception as e:
            logger.error(f"Failed to get snapshot {snapshot_id}: {e}")
        return None

    def delete_snapshot(self, snapshot_id: str) -> tuple[bool, str]:
        """
        Delete a snapshot.

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
                    ["sudo", "-n", "true"],
                    capture_output=True,
                    timeout=5,
                    check=False
                )
                if result.returncode != 0:
                    return (
                        False,
                        "Restore requires sudo privileges. Please run: sudo -v",
                        []
                    )
            except Exception as e:
                logger.warning(f"Could not verify sudo permissions: {e}")

        commands = []
        try:
            # Get current package state
            current_apt = {pkg["name"]: pkg["version"] for pkg in self._detect_apt_packages()}
            current_pip = {pkg["name"]: pkg["version"] for pkg in self._detect_pip_packages()}
            current_npm = {pkg["name"]: pkg["version"] for pkg in self._detect_npm_packages()}

            # Calculate differences for APT
            snapshot_apt = {pkg["name"]: pkg["version"] for pkg in snapshot.packages.get("apt", [])}
            apt_to_install = set(snapshot_apt.keys()) - set(current_apt.keys())
            apt_to_remove = set(current_apt.keys()) - set(snapshot_apt.keys())

            if apt_to_remove:
                # Use list-based command to prevent shell injection
                cmd_list = ["sudo", "apt-get", "remove", "-y"] + sorted(apt_to_remove)
                commands.append(" ".join(cmd_list))  # For display
                if not dry_run:
                    subprocess.run(cmd_list, check=True, capture_output=True, text=True)

            if apt_to_install:
                # Use list-based command to prevent shell injection
                cmd_list = ["sudo", "apt-get", "install", "-y"] + sorted(apt_to_install)
                commands.append(" ".join(cmd_list))  # For display
                if not dry_run:
                    subprocess.run(cmd_list, check=True, capture_output=True, text=True)

            # Calculate differences for PIP
            snapshot_pip = {pkg["name"]: pkg["version"] for pkg in snapshot.packages.get("pip", [])}
            pip_to_install = set(snapshot_pip.keys()) - set(current_pip.keys())
            pip_to_remove = set(current_pip.keys()) - set(snapshot_pip.keys())

            if pip_to_remove:
                # Use list-based command to prevent shell injection
                cmd_list = ["pip", "uninstall", "-y"] + sorted(pip_to_remove)
                commands.append(" ".join(cmd_list))  # For display
                if not dry_run:
                    subprocess.run(cmd_list, check=True, capture_output=True, text=True)

            if pip_to_install:
                # Use list-based command to prevent shell injection
                packages_with_versions = [f"{name}=={snapshot_pip[name]}" for name in sorted(pip_to_install)]
                cmd_list = ["pip", "install"] + packages_with_versions
                commands.append(" ".join(cmd_list))  # For display
                if not dry_run:
                    subprocess.run(cmd_list, check=True, capture_output=True, text=True)

            # Calculate differences for NPM
            snapshot_npm = {pkg["name"]: pkg["version"] for pkg in snapshot.packages.get("npm", [])}
            npm_to_install = set(snapshot_npm.keys()) - set(current_npm.keys())
            npm_to_remove = set(current_npm.keys()) - set(snapshot_npm.keys())

            if npm_to_remove:
                # Use list-based command to prevent shell injection
                cmd_list = ["npm", "uninstall", "-g"] + sorted(npm_to_remove)
                commands.append(" ".join(cmd_list))  # For display
                if not dry_run:
                    subprocess.run(cmd_list, check=True, capture_output=True, text=True)

            if npm_to_install:
                # Use list-based command to prevent shell injection
                packages_with_versions = [f"{name}@{snapshot_npm[name]}" for name in sorted(npm_to_install)]
                cmd_list = ["npm", "install", "-g"] + packages_with_versions
                commands.append(" ".join(cmd_list))  # For display
                if not dry_run:
                    subprocess.run(cmd_list, check=True, capture_output=True, text=True)

            if dry_run:
                return (True, f"Dry-run complete. {len(commands)} commands would be executed.", commands)
            else:
                return (True, f"Successfully restored snapshot {snapshot_id}", commands)

        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed during restore: {e}")
            stderr_msg = e.stderr if hasattr(e, 'stderr') and e.stderr else str(e)
            error_msg = f"Restore failed. Command: {' '.join(e.cmd) if isinstance(e.cmd, list) else e.cmd}. Error: {stderr_msg}"
            return (False, error_msg, commands)
        except Exception as e:
            logger.error(f"Failed to restore snapshot {snapshot_id}: {e}")
            return (False, f"Failed to restore snapshot: {e}", commands)

    def _apply_retention_policy(self) -> None:
        """Remove oldest snapshots if count exceeds RETENTION_LIMIT"""
        try:
            snapshots = self.list_snapshots()
            if len(snapshots) > self.RETENTION_LIMIT:
                # Sort by timestamp (oldest first)
                snapshots.sort(key=lambda s: s.timestamp)
                
                # Delete oldest snapshots
                to_delete = len(snapshots) - self.RETENTION_LIMIT
                for i in range(to_delete):
                    snapshot_id = snapshots[i].id
                    self.delete_snapshot(snapshot_id)
                    logger.info(f"Retention policy: deleted old snapshot {snapshot_id}")
                    
        except Exception as e:
            logger.warning(f"Failed to apply retention policy: {e}")
