"""
Utilities for working with Cortex package versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Optional

from packaging.version import InvalidVersion, Version

PACKAGE_NAME = "cortex-linux"
__all__ = [
    "PACKAGE_NAME",
    "CortexVersion",
    "get_installed_version",
    "is_newer_version",
]


@dataclass(frozen=True)
class CortexVersion:
    """Wrapper that keeps both raw and parsed versions."""

    raw: str
    parsed: Version

    @classmethod
    def from_string(cls, raw_version: str) -> "CortexVersion":
        try:
            parsed = Version(raw_version)
        except InvalidVersion as exc:
            raise ValueError(f"Invalid Cortex version string: {raw_version}") from exc
        return cls(raw=raw_version, parsed=parsed)

    def __str__(self) -> str:
        return self.raw


def get_installed_version() -> CortexVersion:
    """
    Return the version of Cortex that is currently installed.

    Falls back to the package's __version__ attribute when metadata is unavailable.
    """

    raw_version: Optional[str] = None

    try:
        raw_version = metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        try:
            from cortex import __version__ as package_version  # type: ignore

            raw_version = package_version
        except Exception:
            raw_version = "0.0.0"

    return CortexVersion.from_string(raw_version)


def is_newer_version(current: CortexVersion, candidate: CortexVersion) -> bool:
    """Return True when ``candidate`` is newer than ``current``."""

    return candidate.parsed > current.parsed


