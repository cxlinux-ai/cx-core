#!/usr/bin/env python3
"""
Smart Update Recommender for Cortex Linux

AI-powered system to recommend when and what to update.
Analyzes installed packages, checks for available updates,
assesses risks, and provides intelligent timing recommendations.

Issue: #91 - Smart Update Recommendations
"""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import total_ordering
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cortex.context_memory import ContextMemory, MemoryEntry
from cortex.i18n.translator import t
from cortex.installation_history import InstallationHistory, InstallationStatus

# Configure logging
logger = logging.getLogger(__name__)

console = Console()


class RiskLevel(Enum):
    """Risk level for package updates."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def value_str(self) -> str:
        """Get string value for translation keys."""
        return {1: "low", 2: "medium", 3: "high", 4: "critical"}[self.value]


class UpdateCategory(Enum):
    """Category of update based on recommended timing."""

    IMMEDIATE = "immediate"  # Safe to update now
    SCHEDULED = "scheduled"  # Recommended for maintenance window
    DEFERRED = "deferred"  # Hold for now
    SECURITY = "security"  # Security update - prioritize


class ChangeType(Enum):
    """Type of version change."""

    PATCH = "patch"  # Bug fixes only
    MINOR = "minor"  # New features, backward compatible
    MAJOR = "major"  # Breaking changes possible
    SECURITY = "security"  # Security fix
    UNKNOWN = "unknown"


@total_ordering
@dataclass
class PackageVersion:
    """Represents a package version with parsed components."""

    raw: str
    major: int = 0
    minor: int = 0
    patch: int = 0
    prerelease: str = ""
    epoch: int = 0

    @classmethod
    def parse(cls, version_str: str) -> "PackageVersion":
        """Parse a version string into components."""
        if not version_str:
            return cls(raw="0.0.0")

        raw_str = str(version_str).strip()

        # Handle epoch (e.g., "1:2.3.4")
        epoch, clean_raw = cls._parse_epoch(raw_str)

        # Remove common suffixes like -1ubuntu1, +dfsg, etc.
        core_ver = re.sub(r"[-+~].*$", "", clean_raw)

        # Parse major.minor.patch
        major, minor, patch = cls._parse_components(core_ver)

        pr_match = re.search(r"[-+~](alpha|beta|rc|dev|pre)[\d.]*", raw_str, re.I)
        pr = pr_match.group(0) if pr_match else ""

        return cls(raw_str, major, minor, patch, pr, epoch)

    @staticmethod
    def _parse_epoch(raw: str) -> tuple[int, str]:
        if ":" not in raw:
            return 0, raw
        parts = raw.split(":", 1)
        try:
            return int(parts[0]), parts[1]
        except (ValueError, IndexError):
            logger.warning("Failed to parse epoch from version string: '%s'. Defaulting to 0.", raw)
            return 0, raw

    @staticmethod
    def _parse_components(core: str) -> tuple[int, int, int]:
        parts = core.split(".")
        major, minor, patch = 0, 0, 0
        try:
            if len(parts) >= 1:
                major_clean = re.sub(r"^\D+", "", parts[0])
                major = int(re.sub(r"\D.*", "", major_clean) or 0)
            if len(parts) >= 2:
                minor = int(re.sub(r"\D.*", "", parts[1]) or 0)
            if len(parts) >= 3:
                p_match = re.search(r"(\d+)", parts[2])
                patch = int(p_match.group(1)) if p_match else 0
        except (ValueError, IndexError):
            pass
        return major, minor, patch

    def __str__(self) -> str:
        return self.raw

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PackageVersion):
            return NotImplemented
        return (
            self.epoch == other.epoch
            and self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
        )

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PackageVersion):
            return NotImplemented

        # Compare components in priority order
        if self.epoch != other.epoch:
            return self.epoch < other.epoch
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.patch != other.patch:
            return self.patch < other.patch

        # Pre-release comparison: pre-release < final release
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        if self.prerelease and other.prerelease:
            return self.prerelease < other.prerelease

        return False


@dataclass
class UpdateInfo:
    """Information about a package update."""

    package_name: str
    current_version: PackageVersion
    new_version: PackageVersion
    change_type: ChangeType
    risk_level: RiskLevel
    category: UpdateCategory
    description: str = ""
    changelog: str = ""
    dependencies: list[str] = field(default_factory=list)
    is_security: bool = False
    breaking_changes: list[str] = field(default_factory=list)
    recommended_action: str = ""
    group: str = ""  # For grouping related updates

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "package": self.package_name,
            "current": str(self.current_version),
            "new": str(self.new_version),
            "risk": self.risk_level.value_str,
            "type": self.change_type.value,
            "is_security": self.is_security,
            "breaking_changes": self.breaking_changes,
            "group": self.group,
        }


@dataclass
class UpdateRecommendation:
    """Full update recommendation for a system."""

    timestamp: str
    total_updates: int
    immediate_updates: list[UpdateInfo] = field(default_factory=list)
    scheduled_updates: list[UpdateInfo] = field(default_factory=list)
    deferred_updates: list[UpdateInfo] = field(default_factory=list)
    security_updates: list[UpdateInfo] = field(default_factory=list)
    groups: dict[str, list[UpdateInfo]] = field(default_factory=dict)
    llm_analysis: str = ""
    overall_risk: RiskLevel = RiskLevel.LOW

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "timestamp": self.timestamp,
            "total_updates": self.total_updates,
            "overall_risk": self.overall_risk.value_str,
            "security_updates": [u.to_dict() for u in self.security_updates],
            "immediate_updates": [u.to_dict() for u in self.immediate_updates],
            "scheduled_updates": [u.to_dict() for u in self.scheduled_updates],
            "deferred_updates": [u.to_dict() for u in self.deferred_updates],
            "groups": {k: [u.package_name for u in v] for k, v in self.groups.items()},
            "llm_analysis": self.llm_analysis,
        }


class UpdateRecommender:
    """
    AI-powered update recommendation system.

    Analyzes installed packages, checks for updates, assesses risks,
    and provides intelligent recommendations on when and what to update.
    """

    # Package groups for related updates
    PACKAGE_GROUPS = {
        "python": ["python3", "python3-pip", "python3-dev", "python3-venv"],
        "docker": ["docker.io", "docker-ce", "docker-compose", "containerd"],
        "postgresql": ["postgresql", "postgresql-client", "postgresql-contrib"],
        "mysql": ["mysql-server", "mysql-client", "mariadb-server"],
        "nginx": ["nginx", "nginx-common", "nginx-core"],
        "nodejs": ["nodejs", "npm", "node-gyp"],
        "php": ["php", "php-fpm", "php-mysql", "php-pgsql", "php-cli"],
        "kernel": ["linux-image", "linux-headers", "linux-modules"],
        "gcc": ["gcc", "g++", "cpp", "build-essential"],
        "ssl": ["openssl", "libssl-dev", "ca-certificates"],
    }

    # Known high-risk packages
    HIGH_RISK_PACKAGES = {
        "linux-image": "Kernel update - requires reboot",
        "linux-headers": "Kernel headers - may break compiled modules",
        "glibc": "Core library - system-wide impact",
        "libc6": "Core library - system-wide impact",
        "systemd": "Init system - critical for boot",
        "grub": "Bootloader - could affect boot",
        "docker": "Container runtime - affects running containers",
        "postgresql": "Database - may require dump/restore",
        "mysql": "Database - may require migration",
        "openssl": "Encryption - may affect all TLS connections",
    }

    # Security update indicators
    SECURITY_INDICATORS = [
        "security",
        "cve",
        "vulnerability",
        "exploit",
        "patch",
        "critical",
        "urgent",
    ]

    # Breaking change indicators for changelog scanning
    BREAKING_CHANGE_INDICATORS = [
        "breaking change",
        "backwards incompatible",
        "deprecated",
        "removed",
        "migration required",
        "manual action",
    ]

    # Timeouts for external commands (in seconds)
    DEFAULT_TIMEOUT = 30
    CHECK_UPDATE_TIMEOUT = 120

    # Risk score thresholds
    RISK_THRESHOLD_HIGH = 35
    RISK_THRESHOLD_MEDIUM = 15

    # Risk score penalties
    PENALTY_HIGH_IMPACT_PKG = 30
    PENALTY_MAJOR_VERSION = 40
    PENALTY_MINOR_VERSION = 15
    PENALTY_PATCH_VERSION = 5
    PENALTY_PRERELEASE = 25
    PENALTY_CHANGELOG_KEYWORD = 15
    PENALTY_HISTORY_FAILURE = 25
    PENALTY_MEMORY_ISSUE = 10

    # UI and LLM limits
    MAX_LLM_UPDATES = 10
    MAX_DISPLAY_UPDATES = 10

    def __init__(
        self,
        llm_router: Any | None = None,
        history: InstallationHistory | None = None,
        memory: ContextMemory | None = None,
        verbose: bool = False,
        timeout: int | None = None,
        check_timeout: int | None = None,
    ) -> None:
        """
        Initialize the Update Recommender.

        Args:
            llm_router: Optional LLM router for AI-powered analysis
            history: Optional installation history for learning
            memory: Optional context memory for pattern recognition
            verbose: Enable verbose output
            timeout: Timeout for external commands
            check_timeout: Timeout for update check commands
        """
        self.llm_router = llm_router
        self.verbose = verbose
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.check_timeout = check_timeout or self.CHECK_UPDATE_TIMEOUT

        # Graceful initialization of subsystems
        try:
            self.history = history or InstallationHistory()
        except (RuntimeError, OSError, ImportError) as e:
            logger.warning("Installation history unavailable: %s", e)
            self.history = None

        try:
            self.memory = memory or ContextMemory()
        except (RuntimeError, OSError, ImportError) as e:
            # We use lazy logging formatting to satisfy SonarQube
            logger.warning("Context memory unavailable: %s", e)
            self.memory = None

    def _run_pkg_cmd(self, cmd: list[str], timeout: int | None = None) -> str | None:
        """Internal helper to run package manager commands."""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout or self.timeout
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _get_package_metadata(self, package_name: str) -> tuple[str, str]:
        """Fetch package description and changelog metadata."""
        description, changelog = "", ""

        # Try APT: parse line-by-line to avoid complex regex issues
        output = self._run_pkg_cmd(["apt-cache", "show", package_name])
        if output:
            desc_lines = []
            capturing = False
            for line in output.splitlines():
                if line.startswith("Description"):
                    capturing = True
                    # Remove "Description-en: " or similar
                    clean_line = re.sub(r"^Description(?:-[\w-]+)?:\s*", "", line)
                    desc_lines.append(clean_line)
                elif capturing:
                    if line.startswith(" "):
                        desc_lines.append(line.strip())
                    else:
                        break
            if desc_lines:
                description = " ".join(desc_lines).strip()
            else:
                description = t("update_recommend.no_description")

            # Fetch changelog (best-effort, trimmed)
            changelog_out = self._run_pkg_cmd(["apt-get", "changelog", package_name])
            if changelog_out:
                changelog = "\n".join(changelog_out.splitlines()[:200])

            return description, changelog

        # Try DNF/YUM
        for pm in ("dnf", "yum"):
            output = self._run_pkg_cmd([pm, "info", "-q", package_name])
            if output:
                lines = output.splitlines()
                for i, line in enumerate(lines):
                    if line.startswith("Description  :"):
                        description = " ".join(lines[i:]).replace("Description  :", "").strip()
                        break

                # Fetch changelog (best-effort, trimmed)
                changelog_out = self._run_pkg_cmd([pm, "repoquery", "--changelog", package_name])
                if changelog_out:
                    changelog = "\n".join(changelog_out.splitlines()[:200])

                return description or t("update_recommend.no_description"), changelog

        return description or t("update_recommend.no_description"), changelog

    def get_installed_packages(self) -> dict[str, PackageVersion]:
        """Get all installed packages with their versions."""
        packages = {}

        # Query installed packages via dpkg-query (Debian/Ubuntu)
        output = self._run_pkg_cmd(["dpkg-query", "-W", "-f=${Package} ${Version}\n"])
        if output:
            for line in output.split("\n"):
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    packages[parts[0]] = PackageVersion.parse(parts[1])
            return packages

        # Fallback to RPM query for RHEL/Fedora/Suse systems
        output = self._run_pkg_cmd(["rpm", "-qa", "--qf", "%{NAME} %{VERSION}-%{RELEASE}\n"])
        if output:
            for line in output.split("\n"):
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    packages[parts[0]] = PackageVersion.parse(parts[1])
        return packages

    def get_available_updates(self) -> list[dict[str, Any]]:
        """Get list of packages with available updates."""
        if shutil.which("apt-get") and shutil.which("apt"):
            return self._get_apt_updates()

        return self._get_rpm_updates()

    def _get_apt_updates(self) -> list[dict[str, Any]]:
        """Helper to get updates via APT."""
        updates = []
        if self._run_pkg_cmd(["apt-get", "update", "-q"], timeout=self.check_timeout) is None:
            logger.warning("APT update check failed. Skipping APT updates.")
            return updates

        output = self._run_pkg_cmd(["apt", "list", "--upgradable"], timeout=self.check_timeout)
        if not output:
            return updates

        for line in output.splitlines():
            # Pattern: package/suite new_version arch [upgradable from: old_version]
            match = re.search(
                r"^([^/\s]+)/([^\s]+)\s+([^\s]+)\s+[^\s]+\s+\[upgradable from:\s+([^\s]+)\]",
                line,
            )
            if match:
                pkg, suite, new_v, old_v = match.groups()
                updates.append(
                    {"name": pkg, "old_version": old_v, "new_version": new_v, "repo": suite}
                )
        return updates

    def _get_rpm_updates(self) -> list[dict[str, Any]]:
        """Helper to get updates via DNF/YUM."""
        updates = []
        for pm in ("dnf", "yum"):
            try:
                result = subprocess.run(
                    [pm, "check-update", "-q"],
                    capture_output=True,
                    text=True,
                    timeout=self.check_timeout,
                )
                if result.returncode in (0, 100) and result.stdout:
                    installed = self.get_installed_packages()
                    updates.extend(self._parse_rpm_check_update(result.stdout, installed))
                    if updates:
                        return updates
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
            except subprocess.SubprocessError as e:
                logger.warning("Package manager check failed: %s", e)
                continue
        return updates

    def _parse_rpm_check_update(
        self, output: str, installed: dict[str, PackageVersion]
    ) -> list[dict[str, Any]]:
        """Helper to parse DNF/YUM check-update output."""
        updates = []
        for line in output.strip().splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue

            # Skip non-package/status lines (e.g., metadata expiration notices)
            if not re.search(r"\d", parts[1]):
                continue

            full_name = parts[0]
            new_ver = parts[1]
            repo = parts[2] if len(parts) >= 3 else ""

            # Resolve name: prefer architecture-specific if installed
            name = self._resolve_rpm_name(full_name, installed)
            current = installed.get(name)
            old_ver = str(current) if current else "0.0.0"

            updates.append(
                {"name": name, "old_version": old_ver, "new_version": new_ver, "repo": repo}
            )
        return updates

    def _resolve_rpm_name(self, full_name: str, installed: dict[str, PackageVersion]) -> str:
        """Resolve RPM package name by handling architecture suffixes."""
        if "." not in full_name:
            return full_name

        name_no_arch = full_name.rsplit(".", 1)[0]
        if full_name in installed:
            return full_name

        return name_no_arch

    def analyze_change_type(self, current: PackageVersion, new: PackageVersion) -> ChangeType:
        """Classify the semantic version delta between current and new versions."""
        if new.major > current.major:
            return ChangeType.MAJOR
        if new.minor > current.minor:
            return ChangeType.MINOR
        if new.patch > current.patch:
            return ChangeType.PATCH
        if str(new) != str(current):
            return ChangeType.PATCH  # Tie-breaker for alphanumeric patches
        return ChangeType.UNKNOWN

    def assess_risk(
        self, package_name: str, current: PackageVersion, new: PackageVersion, changelog: str = ""
    ) -> tuple[RiskLevel, list[str]]:
        """Assess update risk."""
        warnings, score = [], 0

        # Score penalty for known high-impact system packages
        for pkg, reason in self.HIGH_RISK_PACKAGES.items():
            if pkg in package_name.lower():
                score += self.PENALTY_HIGH_IMPACT_PKG
                warnings.append(reason)
                break

        # Score penalty based on Semantic Versioning delta severity
        ctype = self.analyze_change_type(current, new)
        score += {
            ChangeType.MAJOR: self.PENALTY_MAJOR_VERSION,
            ChangeType.MINOR: self.PENALTY_MINOR_VERSION,
            ChangeType.PATCH: self.PENALTY_PATCH_VERSION,
        }.get(ctype, 0)
        if ctype == ChangeType.MAJOR:
            warnings.append(f"Major version change ({current.major} → {new.major})")

        # Additional penalty for unstable pre-release versions
        if new.prerelease:
            score += self.PENALTY_PRERELEASE
            warnings.append(f"Pre-release version: {new.prerelease}")

        # Scan changelogs for keyword indicators of breaking changes
        for ind in self.BREAKING_CHANGE_INDICATORS:
            if ind in changelog.lower():
                score += self.PENALTY_CHANGELOG_KEYWORD
                warnings.append(f"Changelog mentions: {ind}")

        # Map aggregate score to RiskLevel enum
        level = self._map_score_to_risk(score)

        # Learning Enhancement: Check history to refine risk
        hist_adjustment, hist_notes = self._get_historical_risk_adjustment(package_name)
        if hist_adjustment:
            score += hist_adjustment
            warnings.extend(hist_notes)
            # Re-evaluate level if score changed significantly
            level = self._map_score_to_risk(score)

        return level, warnings

    def _map_score_to_risk(self, score: int) -> RiskLevel:
        """Map aggregate risk score to RiskLevel enum."""
        if score >= self.RISK_THRESHOLD_HIGH:
            return RiskLevel.HIGH
        if score >= self.RISK_THRESHOLD_MEDIUM:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _get_historical_risk_adjustment(self, package_name: str) -> tuple[int, list[str]]:
        """Query history and memory to refine risk scores base on past performance."""
        adj, notes = 0, []

        try:
            h_adj, h_notes = self._check_history_risk(package_name)
            adj += h_adj
            notes.extend(h_notes)

            m_adj, m_notes = self._check_memory_risk(package_name)
            adj += m_adj
            notes.extend(m_notes)
        except (OSError, AttributeError) as e:
            logger.debug("Historical risk lookup failed: %s", e)

        return adj, notes

    def _check_history_risk(self, package_name: str) -> tuple[int, list[str]]:
        """Check installation history for previous failures."""
        if not self.history:
            return 0, []

        past_records = self.history.get_history(limit=50)
        for record in past_records:
            if not record.packages or package_name not in record.packages:
                continue

            if record.status in (InstallationStatus.FAILED, InstallationStatus.ROLLED_BACK):
                return self.PENALTY_HISTORY_FAILURE, [
                    "Historical instability: previous updates failed or were rolled back"
                ]

        return 0, []

    def _check_memory_risk(self, package_name: str) -> tuple[int, list[str]]:
        """Check context memory for recurring issues."""
        if not self.memory:
            return 0, []

        memories = self.memory.get_similar_interactions(package_name, limit=5)
        for m in memories:
            if not m.success:
                return self.PENALTY_MEMORY_ISSUE, [
                    f"Memory: Previously caused issues during {m.action}"
                ]

        return 0, []

    def is_security_update(
        self, package_name: str, changelog: str = "", description: str = "", repo: str = ""
    ) -> bool:
        """
        Determine if an update is security-related.

        Args:
            package_name: Name of the package
            changelog: Changelog content
            description: Update description
            repo: Origin repository or suite (e.g., 'jammy-security')

        Returns:
            True if this appears to be a security update
        """
        combined_text = f"{package_name} {changelog} {description} {repo}".lower()

        # Check for repo origin signals (high confidence)
        if "security" in repo.lower():
            return True

        for indicator in self.SECURITY_INDICATORS:
            if indicator in combined_text:
                return True

        # Check for CVE pattern
        if re.search(r"cve-\d{4}-\d+", combined_text, re.I):
            return True

        return False

    def get_package_group(self, package_name: str) -> str:
        """
        Get the group a package belongs to.

        Args:
            package_name: Name of the package

        Returns:
            Group name or empty string if not in a group
        """
        for group_name, packages in self.PACKAGE_GROUPS.items():
            for pkg in packages:
                if pkg in package_name.lower() or package_name.lower().startswith(pkg):
                    return group_name
        return ""

    def categorize_update(
        self,
        risk_level: RiskLevel,
        is_security: bool,
        change_type: ChangeType,
    ) -> UpdateCategory:
        """
        Determine the recommended update category/timing.

        Args:
            risk_level: Assessed risk level
            is_security: Whether it's a security update
            change_type: Type of version change

        Returns:
            UpdateCategory for recommended timing
        """
        # Security updates should be applied ASAP
        if is_security:
            return UpdateCategory.SECURITY

        # High risk or major updates should be deferred
        if risk_level == RiskLevel.HIGH or change_type == ChangeType.MAJOR:
            return UpdateCategory.DEFERRED

        # Low risk updates can go immediately
        if risk_level == RiskLevel.LOW and change_type in (
            ChangeType.PATCH,
            ChangeType.MINOR,
        ):
            return UpdateCategory.IMMEDIATE

        # Medium risk or minor updates for scheduled maintenance
        if risk_level == RiskLevel.MEDIUM or change_type == ChangeType.MINOR:
            return UpdateCategory.SCHEDULED

        # Default to scheduled for unknown cases
        return UpdateCategory.SCHEDULED

    def generate_recommendation_text(self, update: UpdateInfo) -> str:
        """Generate human-readable recommendation for an update."""
        # Use a mapping to avoid nested ternary expressions (SonarQube)
        category_keys = {
            UpdateCategory.SECURITY: "security_urgent",
            UpdateCategory.IMMEDIATE: "safe_immediate",
            UpdateCategory.SCHEDULED: "maintenance_window",
            UpdateCategory.DEFERRED: "consider_deferring",
        }
        key = category_keys.get(update.category, "maintenance_window")
        res = [t(f"update_recommend.recommendations.{key}")]
        if update.change_type == ChangeType.MAJOR:
            res.append(
                t(
                    "update_recommend.recommendations.major_upgrade",
                    current=str(update.current_version),
                    new=str(update.new_version),
                )
            )
        if update.breaking_changes:
            res.append(t("update_recommend.recommendations.potential_breaking"))
            res.extend(f"  - {bc}" for bc in update.breaking_changes[:3])
        if update.group:
            res.append(t("update_recommend.recommendations.part_of_group", group=update.group))
        return "\n".join(res)

    # Risk colors for display
    RISK_COLORS = {
        RiskLevel.LOW: "green",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.HIGH: "red",
        RiskLevel.CRITICAL: "bold red",
    }

    def analyze_with_llm(self, updates: list[UpdateInfo]) -> str:
        """
        Use LLM to provide additional analysis of updates.

        Args:
            updates: List of update information

        Returns:
            LLM analysis text
        """
        if not self.llm_router or not updates:
            return ""

        try:
            # Build a summary for the LLM
            update_summary = []
            for u in updates[: self.MAX_LLM_UPDATES]:  # Limit for context length
                update_summary.append(
                    f"- {u.package_name}: {u.current_version} → {u.new_version} "
                    f"({u.change_type.value}, {u.risk_level.value} risk)"
                )

            prompt = f"""Analyze these pending system updates and provide a brief recommendation:

{chr(10).join(update_summary)}

Provide:
1. Overall assessment (1-2 sentences)
2. Any specific concerns or recommendations
3. Suggested update order if dependencies exist

Keep response concise (under 150 words)."""

            from cortex.llm_router import TaskType

            response = self.llm_router.complete(
                messages=[{"role": "user", "content": prompt}],
                task_type=TaskType.SYSTEM_OPERATION,
                temperature=0.3,
                max_tokens=300,
            )

            if not response or not hasattr(response, "content"):
                return ""

            return response.content

        except (ImportError, RuntimeError, ConnectionError) as e:
            logger.warning("LLM analysis context error: %s", e)
            return ""
        except Exception as e:
            logger.error("Unexpected LLM analysis error: %s", e, exc_info=True)
            return ""

    def get_recommendations(self, use_llm: bool = True) -> UpdateRecommendation:
        """
        Get complete update recommendations for the system.

        Args:
            use_llm: Whether to use LLM for additional analysis

        Returns:
            UpdateRecommendation with categorized updates
        """
        timestamp = datetime.now().isoformat()
        updates = self.get_available_updates()

        if not updates:
            return UpdateRecommendation(
                timestamp=timestamp,
                total_updates=0,
            )

        update_infos = []
        groups: dict[str, list[UpdateInfo]] = {}

        for update in updates:
            pkg_name = update["name"]
            old_ver = update["old_version"]
            new_ver = update["new_version"]
            repo = update.get("repo", "")

            # Fetch extra metadata for better analysis
            description, changelog = self._get_package_metadata(pkg_name)

            current, new = PackageVersion.parse(old_ver), PackageVersion.parse(new_ver)
            change_type = self.analyze_change_type(current, new)
            risk_level, breaking_changes = self.assess_risk(
                pkg_name, current, new, changelog=changelog
            )
            group = self.get_package_group(pkg_name)
            is_security = self.is_security_update(
                pkg_name, changelog=changelog, description=description, repo=repo
            )

            info = UpdateInfo(
                pkg_name,
                current,
                new,
                change_type,
                risk_level,
                self.categorize_update(risk_level, is_security, change_type),
                description=description,
                changelog=changelog,
                breaking_changes=breaking_changes,
                group=group,
                is_security=is_security,
            )
            info.recommended_action = self.generate_recommendation_text(info)
            update_infos.append(info)
            if group:
                groups.setdefault(group, []).append(info)

        # Categorize updates
        immediate = [u for u in update_infos if u.category == UpdateCategory.IMMEDIATE]
        scheduled = [u for u in update_infos if u.category == UpdateCategory.SCHEDULED]
        deferred = [u for u in update_infos if u.category == UpdateCategory.DEFERRED]
        security = [u for u in update_infos if u.category == UpdateCategory.SECURITY]

        # Determine overall risk
        overall_risk = max(
            (u.risk_level for u in update_infos), key=lambda x: x.value, default=RiskLevel.LOW
        )

        # Get LLM analysis if requested
        llm_analysis = ""
        if use_llm and self.llm_router:
            llm_analysis = self.analyze_with_llm(update_infos)

        return UpdateRecommendation(
            timestamp=timestamp,
            total_updates=len(update_infos),
            immediate_updates=immediate,
            scheduled_updates=scheduled,
            deferred_updates=deferred,
            security_updates=security,
            groups=groups,
            llm_analysis=llm_analysis,
            overall_risk=overall_risk,
        )

    def display_recommendations(self, recommendation: UpdateRecommendation) -> None:
        """
        Display recommendations in a formatted output.

        Args:
            recommendation: The update recommendation to display
        """
        if recommendation.total_updates == 0:
            console.print(f"[green]✅ {t('update_recommend.no_updates')}[/green]")
            return

        console.print()
        overall_risk_display = t(f"update_recommend.risks.{recommendation.overall_risk.value_str}")
        color = self.RISK_COLORS.get(recommendation.overall_risk, "white")
        console.print(
            Panel(
                f"[bold cyan]📊 {t('update_recommend.header')}[/bold cyan]\n"
                f"{t('update_recommend.total_updates', count=recommendation.total_updates)}\n"
                f"{t('update_recommend.overall_risk', risk=f'[{color}]{overall_risk_display}[/]')}",
                title="Cortex Update Recommender",
            )
        )

        # Security updates (highest priority)
        if recommendation.security_updates:
            console.print()
            console.print(f"[bold red]🔒 {t('update_recommend.categories.security')}:[/bold red]")
            self._display_update_table(recommendation.security_updates)

        # Immediate updates
        if recommendation.immediate_updates:
            console.print()
            console.print(
                f"[bold green]✅ {t('update_recommend.categories.immediate')}:[/bold green]"
            )
            self._display_update_table(recommendation.immediate_updates)

        # Scheduled updates
        if recommendation.scheduled_updates:
            console.print()
            console.print(
                f"[bold yellow]📅 {t('update_recommend.categories.scheduled')}:[/bold yellow]"
            )
            self._display_update_table(recommendation.scheduled_updates)

        # Deferred updates
        if recommendation.deferred_updates:
            console.print()
            console.print(
                f"[bold magenta]⏸️ {t('update_recommend.categories.deferred')}:[/bold magenta]"
            )
            self._display_update_table(recommendation.deferred_updates)

        # Related update groups
        if recommendation.groups:
            console.print()
            console.print(f"[bold cyan]📦 {t('update_recommend.categories.groups')}:[/bold cyan]")
            for group_name, group_updates in recommendation.groups.items():
                update_names = [u.package_name for u in group_updates]
                console.print(
                    f"  [cyan]{group_name}[/cyan]: {', '.join(update_names[:5])}"
                    + (f" +{len(update_names) - 5} more" if len(update_names) > 5 else "")
                )

        # LLM Analysis
        if recommendation.llm_analysis:
            console.print()
            console.print(
                Panel(
                    recommendation.llm_analysis,
                    title=f"[bold]🤖 {t('update_recommend.ai_analysis')}[/bold]",
                    border_style="blue",
                )
            )

    def _display_update_table(self, updates: list[UpdateInfo]) -> None:
        """Display a table of updates."""
        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Package", style="cyan")
        table.add_column("Current", style="dim")
        table.add_column("New", style="green")
        table.add_column("Type")
        table.add_column("Risk")
        table.add_column("Notes")

        for update in updates[: self.MAX_DISPLAY_UPDATES]:  # Limit display
            risk_color = self.RISK_COLORS.get(update.risk_level, "white")
            risk_display = t(f"update_recommend.risks.{update.risk_level.value_str}")
            type_str = update.change_type.value

            notes = []
            if update.is_security:
                notes.append(f"🔒 {t('update_recommend.notes.security')}")
            if update.breaking_changes:
                notes.append(
                    f"⚠️ {t('update_recommend.notes.warnings', count=len(update.breaking_changes))}"
                )
            if update.group:
                notes.append(f"📦 {t('update_recommend.notes.group', name=update.group)}")

            table.add_row(
                update.package_name,
                str(update.current_version),
                str(update.new_version),
                type_str,
                f"[{risk_color}]{risk_display}[/]",
                " | ".join(notes) if notes else "-",
            )

        if len(updates) > self.MAX_DISPLAY_UPDATES:
            table.add_row(
                t("update_recommend.more_updates", count=len(updates) - self.MAX_DISPLAY_UPDATES),
                "",
                "",
                "",
                "",
                "",
            )

        console.print(table)


def recommend_updates(
    use_llm: bool = True,
    verbose: bool = False,
) -> int:
    """
    Convenience function to run update recommendations.

    Args:
        use_llm: Whether to use LLM for analysis
        verbose: Enable verbose output

    Returns:
        Exit code (0 for success)
    """
    try:
        # Try to get LLM router if available
        llm_router = None
        if use_llm:
            try:
                from cortex.llm_router import LLMRouter

                llm_router = LLMRouter()
            except (ImportError, RuntimeError) as e:
                logger.debug("LLM router not available: %s", e)

        recommender = UpdateRecommender(
            llm_router=llm_router,
            verbose=verbose,
        )

        recommendation = recommender.get_recommendations(use_llm=use_llm)
        recommender.display_recommendations(recommendation)

        return 0

    except (RuntimeError, subprocess.SubprocessError, OSError) as e:
        console.print(f"[red]System Error: {e}[/red]")
        return 1
    except Exception as e:
        console.print(f"[red]Unexpected Error: {e}[/red]")
        if verbose:
            import traceback

            traceback.print_exc()
        return 1
