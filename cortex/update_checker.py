"""
Cortex Update Checker

Checks for updates from GitHub releases API.
Supports multiple update channels (stable, beta, dev).
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from cortex.version_manager import SemanticVersion, UpdateChannel, get_current_version, is_newer

logger = logging.getLogger(__name__)

# GitHub repository info
GITHUB_OWNER = "cortexlinux"
GITHUB_REPO = "cortex"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

# Cache settings
CACHE_DIR = Path.home() / ".cortex" / "cache"
UPDATE_CACHE_FILE = CACHE_DIR / "update_check.json"
CACHE_TTL_SECONDS = 3600  # 1 hour


@dataclass
class ReleaseInfo:
    """Information about a release."""

    version: SemanticVersion
    tag_name: str
    name: str
    body: str  # Release notes (markdown)
    published_at: str
    html_url: str
    download_url: str | None = None
    assets: list[dict] = field(default_factory=list)

    @classmethod
    def from_github_response(cls, data: dict) -> "ReleaseInfo":
        """Create ReleaseInfo from GitHub API response."""
        tag = data.get("tag_name", "v0.0.0")
        version = SemanticVersion.parse(tag)

        # Find wheel or tarball download URL
        download_url = None
        assets = data.get("assets", [])
        for asset in assets:
            name = asset.get("name", "")
            if name.endswith(".whl") or name.endswith(".tar.gz"):
                download_url = asset.get("browser_download_url")
                break

        return cls(
            version=version,
            tag_name=tag,
            name=data.get("name", f"Release {tag}"),
            body=data.get("body", ""),
            published_at=data.get("published_at", ""),
            html_url=data.get("html_url", ""),
            download_url=download_url,
            assets=assets,
        )

    @property
    def release_notes_summary(self) -> str:
        """Get a summary of release notes (first 5 lines)."""
        if not self.body:
            return "No release notes available."

        lines = self.body.strip().split("\n")
        # Filter out empty lines and take first 5
        significant_lines = [ln for ln in lines if ln.strip()][:5]
        return "\n".join(significant_lines)

    @property
    def formatted_date(self) -> str:
        """Get formatted publish date."""
        if not self.published_at:
            return "Unknown"
        try:
            dt = datetime.fromisoformat(self.published_at.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return self.published_at[:10]


@dataclass
class UpdateCheckResult:
    """Result of checking for updates."""

    update_available: bool
    current_version: SemanticVersion
    latest_version: SemanticVersion | None = None
    latest_release: ReleaseInfo | None = None
    error: str | None = None
    checked_at: str | None = None
    from_cache: bool = False


class UpdateChecker:
    """Checks for Cortex updates from GitHub."""

    def __init__(
        self,
        channel: UpdateChannel = UpdateChannel.STABLE,
        cache_enabled: bool = True,
        timeout: int = 10,
    ):
        self.channel = channel
        self.cache_enabled = cache_enabled
        self.timeout = timeout
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _get_cached_result(self) -> UpdateCheckResult | None:
        """Get cached update check result if valid."""
        if not self.cache_enabled or not UPDATE_CACHE_FILE.exists():
            return None

        try:
            with open(UPDATE_CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)

            # Check if cache is still valid
            cached_time = data.get("checked_at", 0)
            if time.time() - cached_time > CACHE_TTL_SECONDS:
                return None

            # Check if channel matches
            if data.get("channel") != self.channel.value:
                return None

            # Reconstruct result
            current = SemanticVersion.parse(data["current_version"])
            latest = None
            latest_release = None

            if data.get("latest_version"):
                latest = SemanticVersion.parse(data["latest_version"])

            if data.get("latest_release"):
                latest_release = ReleaseInfo(
                    version=latest,
                    tag_name=data["latest_release"].get("tag_name", ""),
                    name=data["latest_release"].get("name", ""),
                    body=data["latest_release"].get("body", ""),
                    published_at=data["latest_release"].get("published_at", ""),
                    html_url=data["latest_release"].get("html_url", ""),
                    download_url=data["latest_release"].get("download_url"),
                )

            return UpdateCheckResult(
                update_available=data.get("update_available", False),
                current_version=current,
                latest_version=latest,
                latest_release=latest_release,
                checked_at=datetime.fromtimestamp(cached_time).isoformat(),
                from_cache=True,
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug(f"Cache read error: {e}")
            return None

    def _cache_result(self, result: UpdateCheckResult) -> None:
        """Cache update check result."""
        if not self.cache_enabled:
            return

        try:
            data = {
                "channel": self.channel.value,
                "current_version": str(result.current_version),
                "update_available": result.update_available,
                "checked_at": time.time(),
            }

            if result.latest_version:
                data["latest_version"] = str(result.latest_version)

            if result.latest_release:
                data["latest_release"] = {
                    "tag_name": result.latest_release.tag_name,
                    "name": result.latest_release.name,
                    "body": result.latest_release.body,
                    "published_at": result.latest_release.published_at,
                    "html_url": result.latest_release.html_url,
                    "download_url": result.latest_release.download_url,
                }

            with open(UPDATE_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        except OSError as e:
            logger.debug(f"Cache write error: {e}")

    def check(self, force: bool = False) -> UpdateCheckResult:
        """Check for available updates.

        Args:
            force: If True, bypass cache and check GitHub directly

        Returns:
            UpdateCheckResult with update information
        """
        current = get_current_version()

        # Check cache first (unless forced)
        if not force:
            cached = self._get_cached_result()
            if cached:
                # Update current version in case we've upgraded
                cached.current_version = current
                cached.update_available = cached.latest_version is not None and is_newer(
                    cached.latest_version, current
                )
                return cached

        # Fetch from GitHub
        try:
            releases = self._fetch_releases()

            if not releases:
                return UpdateCheckResult(
                    update_available=False,
                    current_version=current,
                    error="No releases found",
                    checked_at=datetime.now().isoformat(),
                )

            # Filter by channel
            eligible = self._filter_by_channel(releases)

            if not eligible:
                return UpdateCheckResult(
                    update_available=False,
                    current_version=current,
                    checked_at=datetime.now().isoformat(),
                )

            # Get latest eligible release
            latest = max(eligible, key=lambda r: r.version)

            update_available = is_newer(latest.version, current)

            result = UpdateCheckResult(
                update_available=update_available,
                current_version=current,
                latest_version=latest.version,
                latest_release=latest,
                checked_at=datetime.now().isoformat(),
            )

            # Cache the result
            self._cache_result(result)

            return result

        except requests.RequestException as e:
            logger.error(f"Failed to check for updates: {e}")
            return UpdateCheckResult(
                update_available=False,
                current_version=current,
                error=f"Network error: {e}",
                checked_at=datetime.now().isoformat(),
            )
        except ValueError as e:
            logger.error(f"Failed to parse release data: {e}")
            return UpdateCheckResult(
                update_available=False,
                current_version=current,
                error=f"Parse error: {e}",
                checked_at=datetime.now().isoformat(),
            )

    def _fetch_releases(self) -> list[ReleaseInfo]:
        """Fetch releases from GitHub API."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Cortex-Update-Checker",
        }

        # Add GitHub token if available (for rate limiting)
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        response = requests.get(GITHUB_API_URL, headers=headers, timeout=self.timeout)
        response.raise_for_status()

        releases = []
        for release_data in response.json():
            # Skip drafts
            if release_data.get("draft", False):
                continue

            try:
                releases.append(ReleaseInfo.from_github_response(release_data))
            except ValueError as e:
                logger.debug(f"Skipping invalid release: {e}")
                continue

        return releases

    def _filter_by_channel(self, releases: list[ReleaseInfo]) -> list[ReleaseInfo]:
        """Filter releases by update channel."""
        if self.channel == UpdateChannel.STABLE:
            # Only stable releases (no prerelease)
            return [r for r in releases if not r.version.is_prerelease]

        if self.channel == UpdateChannel.BETA:
            # Stable + beta releases
            return [
                r
                for r in releases
                if r.version.channel in (UpdateChannel.STABLE, UpdateChannel.BETA)
            ]

        # DEV channel - all releases
        return releases

    def get_all_releases(self, limit: int = 10) -> list[ReleaseInfo]:
        """Get list of recent releases.

        Args:
            limit: Maximum number of releases to return

        Returns:
            List of ReleaseInfo objects
        """
        try:
            releases = self._fetch_releases()
            # Sort by version descending
            releases.sort(key=lambda r: r.version, reverse=True)
            return releases[:limit]
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Failed to fetch releases: {e}")
            return []


def check_for_updates(
    channel: UpdateChannel = UpdateChannel.STABLE,
    force: bool = False,
) -> UpdateCheckResult:
    """Convenience function to check for updates.

    Args:
        channel: Update channel to check
        force: If True, bypass cache

    Returns:
        UpdateCheckResult
    """
    checker = UpdateChecker(channel=channel)
    return checker.check(force=force)


def should_notify_update() -> ReleaseInfo | None:
    """Check if we should notify user about an update.

    This is called on CLI startup. Uses cache to avoid
    network calls on every command.

    Returns:
        ReleaseInfo if update available, None otherwise
    """
    # Don't check if disabled
    if os.environ.get("CORTEX_UPDATE_CHECK", "1") == "0":
        return None

    try:
        result = check_for_updates()
        if result.update_available and result.latest_release:
            return result.latest_release
    except Exception as e:
        logger.debug(f"Update check failed: {e}")

    return None
