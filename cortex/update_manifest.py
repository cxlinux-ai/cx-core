"""
Structures and helpers for Cortex update manifests.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

from cortex.versioning import CortexVersion, is_newer_version


class UpdateChannel(str, Enum):
    STABLE = "stable"
    BETA = "beta"

    @classmethod
    def from_string(cls, raw: str) -> "UpdateChannel":
        try:
            return cls(raw.lower())
        except ValueError as exc:
            valid = ", ".join(c.value for c in cls)
            raise ValueError(f"Unknown update channel '{raw}'. Valid options: {valid}") from exc


@dataclass
class SystemInfo:
    python_version: Version
    os_name: str
    architecture: str
    distro: Optional[str] = None

    @classmethod
    def current(cls) -> "SystemInfo":
        return cls(
            python_version=Version(platform.python_version()),
            os_name=platform.system().lower(),
            architecture=platform.machine().lower(),
            distro=_detect_distro(),
        )


def _detect_distro() -> Optional[str]:
    try:
        import distro  # type: ignore

        return distro.id()
    except Exception:
        return None


@dataclass
class CompatibilityRule:
    python_spec: Optional[SpecifierSet] = None
    os_names: List[str] = field(default_factory=list)
    architectures: List[str] = field(default_factory=list)
    distros: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompatibilityRule":
        specifier_value = data.get("python")
        specifier = None
        if specifier_value:
            try:
                specifier = SpecifierSet(specifier_value)
            except InvalidSpecifier as exc:
                raise ValueError(f"Invalid python specifier '{specifier_value}'") from exc

        return cls(
            python_spec=specifier,
            os_names=[name.lower() for name in data.get("os", [])],
            architectures=[arch.lower() for arch in data.get("arch", [])],
            distros=[dist.lower() for dist in data.get("distro", [])],
        )

    def is_compatible(self, system: SystemInfo) -> bool:
        if self.python_spec and system.python_version not in self.python_spec:
            return False

        if self.os_names and system.os_name not in self.os_names:
            return False

        if self.architectures and system.architecture not in self.architectures:
            return False

        if self.distros and system.distro not in self.distros:
            return False

        return True


@dataclass
class ReleaseEntry:
    version: CortexVersion
    channel: UpdateChannel
    download_url: str
    sha256: str
    release_notes: str
    published_at: Optional[str] = None
    compatibility: List[CompatibilityRule] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReleaseEntry":
        compatibility_data = data.get("compatibility", [])
        compatibility = [CompatibilityRule.from_dict(entry) for entry in compatibility_data]

        return cls(
            version=CortexVersion.from_string(data["version"]),
            channel=UpdateChannel.from_string(data.get("channel", UpdateChannel.STABLE.value)),
            download_url=data["download_url"],
            sha256=data["sha256"],
            release_notes=data.get("release_notes", ""),
            published_at=data.get("published_at"),
            compatibility=compatibility,
        )

    def is_compatible(self, system: SystemInfo) -> bool:
        if not self.compatibility:
            return True

        return any(rule.is_compatible(system) for rule in self.compatibility)


@dataclass
class UpdateManifest:
    releases: List[ReleaseEntry]
    signature: Optional[str] = None
    generated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UpdateManifest":
        releases_data = data.get("releases", [])
        releases = [ReleaseEntry.from_dict(entry) for entry in releases_data]
        return cls(
            releases=releases,
            signature=data.get("signature"),
            generated_at=data.get("generated_at"),
        )

    def iter_releases(
        self,
        *,
        channel: Optional[UpdateChannel] = None,
        system: Optional[SystemInfo] = None,
    ) -> Iterable[ReleaseEntry]:
        for release in self.releases:
            if channel and release.channel != channel:
                continue
            if system and not release.is_compatible(system):
                continue
            yield release

    def find_latest(
        self,
        *,
        current_version: CortexVersion,
        channel: UpdateChannel,
        system: Optional[SystemInfo] = None,
    ) -> Optional[ReleaseEntry]:
        system_info = system or SystemInfo.current()

        eligible = [
            release
            for release in self.iter_releases(channel=channel, system=system_info)
            if is_newer_version(current_version, release.version)
        ]

        if not eligible:
            return None

        eligible.sort(key=lambda release: release.version.parsed, reverse=True)
        return eligible[0]

