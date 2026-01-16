"""
Cortex Updater

Handles downloading, verifying, and installing Cortex updates.
Supports safe upgrades with rollback capability.
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import requests

from cortex.update_checker import ReleaseInfo, UpdateCheckResult, check_for_updates
from cortex.version_manager import SemanticVersion, UpdateChannel, get_version_string

logger = logging.getLogger(__name__)

# Backup settings
BACKUP_DIR = Path.home() / ".cortex" / "backups"
MAX_BACKUPS = 3  # Keep last 3 backups

# PyPI package name
PYPI_PACKAGE = "cortex-linux"


class UpdateStatus(Enum):
    """Status of an update operation."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    INSTALLING = "installing"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class UpdateResult:
    """Result of an update operation."""

    success: bool
    status: UpdateStatus
    previous_version: str
    new_version: str | None = None
    error: str | None = None
    backup_path: Path | None = None
    duration_seconds: float | None = None


@dataclass
class BackupInfo:
    """Information about a backup."""

    version: str
    timestamp: str
    path: Path
    size_bytes: int


class Updater:
    """Handles Cortex self-update operations."""

    def __init__(
        self,
        channel: UpdateChannel = UpdateChannel.STABLE,
        progress_callback: Callable[[str, float], None] | None = None,
    ):
        """Initialize the updater.

        Args:
            channel: Update channel (stable, beta, dev)
            progress_callback: Optional callback for progress updates (message, percent)
        """
        self.channel = channel
        self.progress_callback = progress_callback
        self._ensure_backup_dir()

    def _ensure_backup_dir(self) -> None:
        """Ensure backup directory exists with proper permissions."""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        # Secure permissions - owner only
        os.chmod(BACKUP_DIR, 0o700)

    def _report_progress(self, message: str, percent: float = -1) -> None:
        """Report progress to callback if set."""
        if self.progress_callback:
            self.progress_callback(message, percent)

    def check_update_available(self, force: bool = False) -> UpdateCheckResult:
        """Check if an update is available.

        Args:
            force: Bypass cache and check GitHub directly

        Returns:
            UpdateCheckResult with update information
        """
        return check_for_updates(channel=self.channel, force=force)

    def update(
        self,
        target_version: str | None = None,
        dry_run: bool = False,
    ) -> UpdateResult:
        """Perform the update.

        Args:
            target_version: Specific version to update to (None = latest)
            dry_run: If True, don't actually install

        Returns:
            UpdateResult with outcome information
        """
        start_time = datetime.now()
        current_version = get_version_string()
        backup_path = None

        try:
            # Step 1: Check for updates
            self._report_progress("Checking for updates...", 0)

            if target_version:
                # Specific version requested
                target = SemanticVersion.parse(target_version)
                release_info = self._get_specific_release(target_version)
                if not release_info:
                    return UpdateResult(
                        success=False,
                        status=UpdateStatus.FAILED,
                        previous_version=current_version,
                        error=f"Version {target_version} not found",
                    )
            else:
                # Get latest version
                check_result = self.check_update_available(force=True)

                if not check_result.update_available:
                    return UpdateResult(
                        success=True,
                        status=UpdateStatus.SUCCESS,
                        previous_version=current_version,
                        new_version=current_version,
                        error="Already up to date",
                    )

                release_info = check_result.latest_release
                target = check_result.latest_version

            if not release_info:
                return UpdateResult(
                    success=False,
                    status=UpdateStatus.FAILED,
                    previous_version=current_version,
                    error="No release information available",
                )

            self._report_progress(f"Found version {target}", 10)

            if dry_run:
                return UpdateResult(
                    success=True,
                    status=UpdateStatus.PENDING,
                    previous_version=current_version,
                    new_version=str(target),
                )

            # Step 2: Create backup
            self._report_progress("Creating backup...", 20)
            backup_path = self._create_backup()

            # Step 3: Download and install
            self._report_progress("Downloading update...", 30)

            # Use pip to install from PyPI (most reliable method)
            version_spec = f"=={target}" if target_version else ""
            success = self._pip_install(f"{PYPI_PACKAGE}{version_spec}")

            if not success:
                # Try installing from GitHub release if PyPI fails
                if release_info.download_url:
                    self._report_progress("Trying GitHub release...", 60)
                    success = self._pip_install(release_info.download_url)

            if not success:
                # Rollback
                self._report_progress("Installation failed, rolling back...", 80)
                self._rollback(backup_path)
                return UpdateResult(
                    success=False,
                    status=UpdateStatus.ROLLED_BACK,
                    previous_version=current_version,
                    error="Installation failed",
                    backup_path=backup_path,
                )

            self._report_progress("Update complete!", 100)

            # Clean up old backups
            self._cleanup_old_backups()

            duration = (datetime.now() - start_time).total_seconds()

            return UpdateResult(
                success=True,
                status=UpdateStatus.SUCCESS,
                previous_version=current_version,
                new_version=str(target),
                backup_path=backup_path,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"Update failed: {e}")

            # Try to rollback if we have a backup
            if backup_path and backup_path.exists():
                try:
                    self._rollback(backup_path)
                    return UpdateResult(
                        success=False,
                        status=UpdateStatus.ROLLED_BACK,
                        previous_version=current_version,
                        error=str(e),
                        backup_path=backup_path,
                    )
                except Exception as rollback_error:
                    logger.error(f"Rollback also failed: {rollback_error}")

            return UpdateResult(
                success=False,
                status=UpdateStatus.FAILED,
                previous_version=current_version,
                error=str(e),
            )

    def _get_specific_release(self, version: str) -> ReleaseInfo | None:
        """Get information about a specific release version."""
        from cortex.update_checker import UpdateChecker

        checker = UpdateChecker(channel=UpdateChannel.DEV)  # Allow all channels
        releases = checker.get_all_releases(limit=50)

        version = version.lstrip("v")
        for release in releases:
            if str(release.version) == version:
                return release

        return None

    def _create_backup(self) -> Path:
        """Create a backup of the current installation.

        Returns:
            Path to backup directory
        """
        current_version = get_version_string()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"cortex_{current_version}_{timestamp}"
        backup_path = BACKUP_DIR / backup_name

        # Get the cortex package location
        import cortex

        package_dir = Path(cortex.__file__).parent

        # Create backup
        shutil.copytree(package_dir, backup_path, dirs_exist_ok=True)

        # Save metadata
        metadata = {
            "version": current_version,
            "timestamp": datetime.now().isoformat(),
            "python_version": sys.version,
            "package_dir": str(package_dir),
        }

        with open(backup_path / "backup_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Created backup at {backup_path}")
        return backup_path

    def _pip_install(self, package_spec: str) -> bool:
        """Install using pip.

        Args:
            package_spec: Package specifier (name==version or URL)

        Returns:
            True if successful
        """
        try:
            cmd = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--no-cache-dir",
                package_spec,
            ]

            self._report_progress(f"Installing {package_spec}...", 50)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"pip install failed: {result.stderr}")
                return False

            return True

        except subprocess.TimeoutExpired:
            logger.error("Installation timed out")
            return False
        except Exception as e:
            logger.error(f"Installation error: {e}")
            return False

    def _rollback(self, backup_path: Path) -> bool:
        """Rollback to a backup.

        Args:
            backup_path: Path to backup directory

        Returns:
            True if successful
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        # Load metadata
        metadata_file = backup_path / "backup_metadata.json"
        if not metadata_file.exists():
            raise ValueError("Invalid backup: missing metadata")

        with open(metadata_file, encoding="utf-8") as f:
            metadata = json.load(f)

        version = metadata.get("version", "unknown")

        # Reinstall the backed up version from PyPI
        logger.info(f"Rolling back to version {version}")
        return self._pip_install(f"{PYPI_PACKAGE}=={version}")

    def _cleanup_old_backups(self) -> None:
        """Remove old backups, keeping only MAX_BACKUPS most recent."""
        try:
            backups = list(BACKUP_DIR.glob("cortex_*"))
            backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            for old_backup in backups[MAX_BACKUPS:]:
                shutil.rmtree(old_backup, ignore_errors=True)
                logger.debug(f"Removed old backup: {old_backup}")

        except Exception as e:
            logger.warning(f"Failed to cleanup backups: {e}")

    def list_backups(self) -> list[BackupInfo]:
        """List available backups.

        Returns:
            List of BackupInfo objects
        """
        backups = []

        for backup_dir in BACKUP_DIR.glob("cortex_*"):
            if not backup_dir.is_dir():
                continue

            metadata_file = backup_dir / "backup_metadata.json"
            if not metadata_file.exists():
                continue

            try:
                with open(metadata_file, encoding="utf-8") as f:
                    metadata = json.load(f)

                # Calculate size
                size = sum(f.stat().st_size for f in backup_dir.rglob("*") if f.is_file())

                backups.append(
                    BackupInfo(
                        version=metadata.get("version", "unknown"),
                        timestamp=metadata.get("timestamp", "unknown"),
                        path=backup_dir,
                        size_bytes=size,
                    )
                )
            except (json.JSONDecodeError, OSError):
                continue

        # Sort by timestamp descending
        backups.sort(key=lambda b: b.timestamp, reverse=True)
        return backups

    def rollback_to_backup(self, backup_path: str | Path) -> UpdateResult:
        """Rollback to a specific backup.

        Args:
            backup_path: Path to backup directory

        Returns:
            UpdateResult
        """
        backup_path = Path(backup_path)
        current_version = get_version_string()

        try:
            success = self._rollback(backup_path)

            if success:
                # Get the version we rolled back to
                with open(backup_path / "backup_metadata.json", encoding="utf-8") as f:
                    metadata = json.load(f)
                rolled_back_version = metadata.get("version", "unknown")

                return UpdateResult(
                    success=True,
                    status=UpdateStatus.ROLLED_BACK,
                    previous_version=current_version,
                    new_version=rolled_back_version,
                    backup_path=backup_path,
                )

            return UpdateResult(
                success=False,
                status=UpdateStatus.FAILED,
                previous_version=current_version,
                error="Rollback failed",
            )

        except Exception as e:
            return UpdateResult(
                success=False,
                status=UpdateStatus.FAILED,
                previous_version=current_version,
                error=str(e),
            )


def download_with_progress(
    url: str,
    dest_path: Path,
    progress_callback: Callable[[int, int], None] | None = None,
    chunk_size: int = 8192,
) -> bool:
    """Download a file with progress reporting.

    Args:
        url: URL to download
        dest_path: Destination path
        progress_callback: Optional callback(downloaded, total)
        chunk_size: Download chunk size

    Returns:
        True if successful
    """
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_size)

        return True

    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False


def verify_checksum(file_path: Path, expected_hash: str, algorithm: str = "sha256") -> bool:
    """Verify file checksum.

    Args:
        file_path: Path to file
        expected_hash: Expected hash value
        algorithm: Hash algorithm (sha256, md5)

    Returns:
        True if checksum matches
    """
    hasher = hashlib.new(algorithm)

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)

    actual_hash = hasher.hexdigest()
    return actual_hash.lower() == expected_hash.lower()
