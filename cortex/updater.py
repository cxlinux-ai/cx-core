"""
Update checking and coordination for Cortex.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
from cortex.update_manifest import (
    ReleaseEntry,
    SystemInfo,
    UpdateChannel,
    UpdateManifest,
)
from cortex.versioning import PACKAGE_NAME, CortexVersion, get_installed_version

DEFAULT_MANIFEST_URL = "https://updates.cortexlinux.com/manifest.json"
STATE_DIR = Path.home() / ".config" / "cortex" / "updater"
STATE_FILE = STATE_DIR / "state.json"
DEFAULT_LOG_FILE = STATE_DIR / "update.log"
CACHE_TTL = timedelta(hours=6)


@dataclass
class UpdateCheckResult:
    update_available: bool
    release: Optional[ReleaseEntry]
    channel: UpdateChannel
    last_checked: datetime
    from_cache: bool = False


@dataclass
class UpdatePerformResult:
    success: bool
    updated: bool
    release: Optional[ReleaseEntry]
    previous_version: CortexVersion
    current_version: CortexVersion
    log_path: Path
    message: Optional[str] = None


class UpdateError(Exception):
    """Generic update failure."""


class ChecksumMismatch(UpdateError):
    """Raised when downloaded artifacts do not match expected checksum."""


class InstallError(UpdateError):
    """Raised when pip install fails."""


class UpdateService:
    def __init__(
        self,
        *,
        manifest_url: Optional[str] = None,
        state_file: Optional[Path] = None,
        system_info: Optional[SystemInfo] = None,
        log_file: Optional[Path] = None,
    ) -> None:
        self.manifest_url = manifest_url or os.environ.get("CORTEX_UPDATE_MANIFEST_URL", DEFAULT_MANIFEST_URL)
        self.state_file = state_file or STATE_FILE
        self.system_info = system_info or SystemInfo.current()
        self.log_file = log_file or DEFAULT_LOG_FILE
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ State
    def _load_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {}
        try:
            with self.state_file.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        tmp_path = self.state_file.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        tmp_path.replace(self.state_file)

    # ---------------------------------------------------------------- Channels
    def get_channel(self) -> UpdateChannel:
        state = self._load_state()
        channel_raw = state.get("channel", UpdateChannel.STABLE.value)
        try:
            return UpdateChannel.from_string(channel_raw)
        except ValueError:
            return UpdateChannel.STABLE

    def set_channel(self, channel: UpdateChannel) -> None:
        state = self._load_state()
        state["channel"] = channel.value
        self._save_state(state)

    # --------------------------------------------------------------- Manifest
    def _fetch_manifest(self) -> UpdateManifest:
        response = requests.get(self.manifest_url, timeout=10)
        response.raise_for_status()
        payload = response.json()
        return UpdateManifest.from_dict(payload)

    def _should_use_cache(self, last_checked: Optional[str]) -> bool:
        if not last_checked:
            return False
        try:
            last_dt = datetime.fromisoformat(last_checked)
        except ValueError:
            return False
        return datetime.now(timezone.utc) - last_dt < CACHE_TTL

    # --------------------------------------------------------------- Checking
    def check_for_updates(
        self,
        *,
        force: bool = False,
        channel: Optional[UpdateChannel] = None,
        current_version: Optional[CortexVersion] = None,
    ) -> UpdateCheckResult:
        state = self._load_state()
        resolved_channel = channel or self.get_channel()
        current = current_version or get_installed_version()

        if not force and self._should_use_cache(state.get("last_checked")):
            cached_release = state.get("cached_release")
            release = ReleaseEntry.from_dict(cached_release) if cached_release else None
            last_checked = datetime.fromisoformat(state.get("last_checked")).astimezone(timezone.utc)
            return UpdateCheckResult(
                update_available=bool(release),
                release=release,
                channel=resolved_channel,
                last_checked=last_checked,
                from_cache=True,
            )

        manifest = self._fetch_manifest()
        release = manifest.find_latest(
            current_version=current,
            channel=resolved_channel,
            system=self.system_info,
        )

        last_checked = datetime.now(timezone.utc)
        state["last_checked"] = last_checked.isoformat()
        state["cached_release"] = _release_to_dict(release) if release else None
        state["channel"] = resolved_channel.value
        self._save_state(state)

        return UpdateCheckResult(
            update_available=release is not None,
            release=release,
            channel=resolved_channel,
            last_checked=last_checked,
            from_cache=False,
        )

    # --------------------------------------------------------------- Upgrades
    def perform_update(
        self,
        *,
        force: bool = False,
        channel: Optional[UpdateChannel] = None,
        dry_run: bool = False,
    ) -> UpdatePerformResult:
        current_version = get_installed_version()
        check_result = self.check_for_updates(force=force, channel=channel, current_version=current_version)

        if not check_result.update_available or not check_result.release:
            return UpdatePerformResult(
                success=True,
                updated=False,
                release=None,
                previous_version=current_version,
                current_version=current_version,
                log_path=self.log_file,
                message="Already up to date.",
            )

        release = check_result.release

        if dry_run:
            return UpdatePerformResult(
                success=True,
                updated=False,
                release=release,
                previous_version=current_version,
                current_version=current_version,
                log_path=self.log_file,
                message=f"Update available (dry run): {release.version.raw}",
            )

        temp_dir: Optional[Path] = None
        try:
            artifact_path, temp_dir = self._download_release(release)
            self._log(f"Installing Cortex {release.version.raw} from {artifact_path}")
            self._install_artifact(artifact_path)
            self._record_last_upgrade(previous=current_version, new_version=release.version)

            return UpdatePerformResult(
                success=True,
                updated=True,
                release=release,
                previous_version=current_version,
                current_version=release.version,
                log_path=self.log_file,
                message=f"Updated to {release.version.raw}",
            )
        except UpdateError as exc:
            self._log(f"Update error: {exc}. Rolling back to {current_version.raw}.")
            self._rollback(previous=current_version)
            raise
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ----------------------------------------------------------- Implementation
    def _download_release(self, release: ReleaseEntry) -> Tuple[Path, Path]:
        temp_dir = Path(tempfile.mkdtemp(prefix="cortex-update-"))
        artifact_name = release.download_url.split("/")[-1] or f"cortex-{release.version.raw}.whl"
        artifact_path = temp_dir / artifact_name

        with requests.get(release.download_url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with artifact_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        fh.write(chunk)

        self._log(f"Downloaded release to {artifact_path}")
        self._verify_checksum(artifact_path, release.sha256)
        return artifact_path, temp_dir

    def _verify_checksum(self, path: Path, expected_sha256: str) -> None:
        sha256 = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                sha256.update(chunk)
        computed = sha256.hexdigest()
        if computed.lower() != expected_sha256.lower():
            raise ChecksumMismatch(
                f"Checksum mismatch for {path.name}: expected {expected_sha256}, got {computed}"
            )
        self._log(f"Checksum verified for {path.name}")

    def _install_artifact(self, artifact_path: Path) -> None:
        self._log(f"Running pip install for {artifact_path}")
        self._run_pip(["install", str(artifact_path)])

    def _rollback(self, previous: CortexVersion) -> None:
        self._log(f"Rolling back to Cortex {previous.raw}")
        self._run_pip(["install", f"{PACKAGE_NAME}=={previous.raw}"])

    def _run_pip(self, args: list[str]) -> None:
        cmd = [sys.executable, "-m", "pip"] + args
        self._log(f"Executing command: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
            self._log(f"Pip output: {result.stdout.strip()}")
        except subprocess.CalledProcessError as exc:
            self._log(f"Pip failed: {exc.stderr}")
            raise InstallError(f"pip exited with code {exc.returncode}") from exc

    def _record_last_upgrade(self, *, previous: CortexVersion, new_version: CortexVersion) -> None:
        state = self._load_state()
        state["last_success_version"] = new_version.raw
        state["previous_version"] = previous.raw
        state["last_upgrade_at"] = datetime.now(timezone.utc).isoformat()
        self._save_state(state)

    def _log(self, message: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        log_line = f"[{timestamp}] {message}\n"
        with self.log_file.open("a", encoding="utf-8") as fh:
            fh.write(log_line)


def _release_to_dict(release: Optional[ReleaseEntry]) -> Optional[Dict[str, Any]]:
    if not release:
        return None

    return {
        "version": release.version.raw,
        "channel": release.channel.value,
        "download_url": release.download_url,
        "sha256": release.sha256,
        "release_notes": release.release_notes,
        "published_at": release.published_at,
        "compatibility": [
            {
                "python": str(rule.python_spec) if rule.python_spec else None,
                "os": rule.os_names,
                "arch": rule.architectures,
                "distro": rule.distros,
            }
            for rule in release.compatibility
        ],
    }

