"""
Cortex Version Manager

Single source of truth for version information and comparison.
Handles semantic versioning operations for the self-update feature.
"""

import re
from dataclasses import dataclass
from enum import Enum
from functools import total_ordering
from typing import Optional

# Single source of truth for version
__version__ = "0.1.0"

# Update channels
class UpdateChannel(Enum):
    STABLE = "stable"
    BETA = "beta"
    DEV = "dev"


@total_ordering
@dataclass
class SemanticVersion:
    """Semantic version representation with comparison support."""

    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    @classmethod
    def parse(cls, version_str: str) -> "SemanticVersion":
        """Parse a version string into a SemanticVersion object.

        Supports formats:
        - 1.2.3
        - v1.2.3
        - 1.2.3-beta.1
        - 1.2.3-rc.1+build.123
        """
        # Strip leading 'v' if present
        version_str = version_str.lstrip("v").strip()

        # Regex for semantic versioning
        pattern = r"""
            ^(?P<major>\d+)\.
            (?P<minor>\d+)\.
            (?P<patch>\d+)
            (?:-(?P<prerelease>[0-9A-Za-z.-]+))?
            (?:\+(?P<build>[0-9A-Za-z.-]+))?$
        """

        match = re.match(pattern, version_str, re.VERBOSE)
        if not match:
            raise ValueError(f"Invalid semantic version: {version_str}")

        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=match.group("prerelease"),
            build=match.group("build"),
        )

    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        if self.build:
            version += f"+{self.build}"
        return version

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
        )

    def __lt__(self, other: "SemanticVersion") -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented

        # Compare major.minor.patch
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

        # Prerelease versions have lower precedence than release
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False

        # Compare prereleases
        if self.prerelease and other.prerelease:
            return self._compare_prerelease(self.prerelease, other.prerelease) < 0

        return False

    @staticmethod
    def _compare_prerelease(pre1: str, pre2: str) -> int:
        """Compare prerelease identifiers per semver spec."""
        parts1 = pre1.split(".")
        parts2 = pre2.split(".")

        for p1, p2 in zip(parts1, parts2):
            # Numeric identifiers compare as integers
            if p1.isdigit() and p2.isdigit():
                diff = int(p1) - int(p2)
                if diff != 0:
                    return diff
            # Numeric has lower precedence than alphanumeric
            elif p1.isdigit():
                return -1
            elif p2.isdigit():
                return 1
            # Both alphanumeric - compare lexically
            elif p1 != p2:
                return -1 if p1 < p2 else 1

        # Longer prerelease has higher precedence
        return len(parts1) - len(parts2)

    @property
    def is_prerelease(self) -> bool:
        return self.prerelease is not None

    @property
    def channel(self) -> UpdateChannel:
        """Determine update channel from version."""
        if not self.prerelease:
            return UpdateChannel.STABLE
        if "beta" in self.prerelease.lower():
            return UpdateChannel.BETA
        if "alpha" in self.prerelease.lower() or "dev" in self.prerelease.lower():
            return UpdateChannel.DEV
        return UpdateChannel.BETA  # Default prerelease to beta


def get_current_version() -> SemanticVersion:
    """Get the current installed version of Cortex."""
    return SemanticVersion.parse(__version__)


def get_version_string() -> str:
    """Get the current version as a string."""
    return __version__


def is_newer(version: str | SemanticVersion, current: str | SemanticVersion | None = None) -> bool:
    """Check if a version is newer than current.

    Args:
        version: Version to check
        current: Current version (defaults to installed version)

    Returns:
        True if version is newer than current
    """
    if isinstance(version, str):
        version = SemanticVersion.parse(version)

    if current is None:
        current = get_current_version()
    elif isinstance(current, str):
        current = SemanticVersion.parse(current)

    return version > current


def is_compatible(version: str | SemanticVersion, min_version: str = "0.1.0") -> bool:
    """Check if a version meets minimum compatibility requirements.

    Args:
        version: Version to check
        min_version: Minimum required version

    Returns:
        True if version is compatible
    """
    if isinstance(version, str):
        version = SemanticVersion.parse(version)

    min_ver = SemanticVersion.parse(min_version)
    return version >= min_ver
