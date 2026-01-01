#!/usr/bin/env python3
"""
User Preferences & Settings System
Manages persistent user preferences and configuration for Cortex Linux
"""

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class PreferencesError(Exception):
    """Custom exception for preferences-related errors"""


class VerbosityLevel(str, Enum):
    """Verbosity levels for output"""

    QUIET = "quiet"
    NORMAL = "normal"
    VERBOSE = "verbose"
    DEBUG = "debug"


class AICreativity(str, Enum):
    """AI creativity/temperature settings"""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    CREATIVE = "creative"


@dataclass
class ConfirmationSettings:
    """Settings for user confirmations"""

    before_install: bool = True
    before_remove: bool = True
    before_upgrade: bool = False
    before_system_changes: bool = True


@dataclass
class AutoUpdateSettings:
    """Automatic update settings"""

    check_on_start: bool = True
    auto_install: bool = False
    frequency_hours: int = 24


@dataclass
class AISettings:
    """AI behavior configuration"""

    model: str = "claude-sonnet-4"
    creativity: AICreativity = AICreativity.BALANCED
    explain_steps: bool = True
    suggest_alternatives: bool = True
    learn_from_history: bool = True
    max_suggestions: int = 5


@dataclass
class PackageSettings:
    """Package management preferences"""

    default_sources: list[str] = field(default_factory=lambda: ["official"])
    prefer_latest: bool = False
    auto_cleanup: bool = True
    backup_before_changes: bool = True


@dataclass
class LLMSettings:
    """LLM provider/model preferences (Issue #42 compatibility)."""

    provider: str = "openai"
    model: str = "gpt-4"


@dataclass
class ConflictSettings:
    """Conflict resolution preferences"""

    default_strategy: str = "interactive"
    saved_resolutions: dict[str, str] = field(default_factory=dict)


@dataclass
class UserPreferences:
    """Complete user preferences"""

    verbosity: VerbosityLevel = VerbosityLevel.NORMAL
    confirmations: ConfirmationSettings = field(default_factory=ConfirmationSettings)
    auto_update: AutoUpdateSettings = field(default_factory=AutoUpdateSettings)
    ai: AISettings = field(default_factory=AISettings)
    packages: PackageSettings = field(default_factory=PackageSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    conflicts: ConflictSettings = field(default_factory=ConflictSettings)
    theme: str = "default"
    language: str = "en"
    timezone: str = "UTC"


class PreferencesManager:
    """Manages user preferences with YAML storage"""

    def __init__(self, config_path: Path | None = None):
        """
        Initialize preferences manager

        Args:
            config_path: Custom path for config file (default: ~/.config/cortex/preferences.yaml)
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            # Default config location
            config_dir = Path.home() / ".config" / "cortex"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.config_path = config_dir / "preferences.yaml"

        self.preferences: UserPreferences = UserPreferences()
        self.load()

    def _to_dict(self, include_metadata: bool = False) -> dict[str, Any]:
        """Convert preferences to dictionary representation.

        Args:
            include_metadata: Whether to include export metadata like timestamp

        Returns:
            Dictionary representation of preferences
        """
        data = {
            "verbosity": self.preferences.verbosity.value,
            "confirmations": asdict(self.preferences.confirmations),
            "auto_update": asdict(self.preferences.auto_update),
            "ai": {
                **asdict(self.preferences.ai),
                "creativity": self.preferences.ai.creativity.value,
            },
            "packages": asdict(self.preferences.packages),
            "llm": asdict(self.preferences.llm),
            "conflicts": asdict(self.preferences.conflicts),
            "theme": self.preferences.theme,
            "language": self.preferences.language,
            "timezone": self.preferences.timezone,
        }
        if include_metadata:
            data["exported_at"] = datetime.now().isoformat()
        return data

    def _from_dict(self, data: dict[str, Any]) -> UserPreferences:
        """Create UserPreferences from dictionary representation.

        Args:
            data: Dictionary containing preferences data

        Returns:
            UserPreferences instance
        """
        return UserPreferences(
            verbosity=VerbosityLevel(data.get("verbosity", "normal")),
            confirmations=ConfirmationSettings(**data.get("confirmations", {})),
            auto_update=AutoUpdateSettings(**data.get("auto_update", {})),
            ai=AISettings(
                creativity=AICreativity(data.get("ai", {}).get("creativity", "balanced")),
                **{k: v for k, v in data.get("ai", {}).items() if k != "creativity"},
            ),
            packages=PackageSettings(**data.get("packages", {})),
            llm=LLMSettings(**data.get("llm", {})),
            conflicts=ConflictSettings(**data.get("conflicts", {})),
            theme=data.get("theme", "default"),
            language=data.get("language", "en"),
            timezone=data.get("timezone", "UTC"),
        )

    def load(self) -> UserPreferences:
        """Load preferences from YAML file"""
        if not self.config_path.exists():
            # Create default config file
            self.save()
            return self.preferences

        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            self.preferences = self._from_dict(data)
            return self.preferences

        except Exception as e:
            print(f"[WARNING] Could not load preferences: {e}")
            print("[INFO] Using default preferences")
            return self.preferences

    def save(self) -> None:
        """Save preferences to YAML file with backup"""
        # Create backup if file exists
        if self.config_path.exists():
            backup_path = self.config_path.with_suffix(".yaml.bak")
            shutil.copy2(self.config_path, backup_path)

        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        data = self._to_dict()

        # Write atomically (write to temp, then rename)
        temp_path = self.config_path.with_suffix(".yaml.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            # Atomic rename
            temp_path.replace(self.config_path)

        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise PreferencesError(f"Failed to save preferences: {e}") from e

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get preference value by dot notation key

        Args:
            key: Dot notation key (e.g., 'ai.model', 'confirmations.before_install')
            default: Default value if key not found

        Returns:
            Preference value or default
        """
        parts = key.split(".")
        obj = self.preferences

        try:
            for part in parts:
                obj = getattr(obj, part)
            return obj
        except AttributeError:
            return default

    def set(self, key: str, value: Any) -> None:
        """
        Set preference value by dot notation key

        Args:
            key: Dot notation key (e.g., 'ai.model')
            value: Value to set
        """
        parts = key.split(".")
        obj = self.preferences

        # Navigate to parent object
        for part in parts[:-1]:
            obj = getattr(obj, part)

        # Set the final attribute
        attr_name = parts[-1]
        current_value = getattr(obj, attr_name)

        # Type coercion
        if isinstance(current_value, bool):
            if isinstance(value, str):
                value = value.lower() in ("true", "yes", "1", "on")
        elif isinstance(current_value, int):
            value = int(value)
        elif isinstance(current_value, list):
            if isinstance(value, str):
                value = [v.strip() for v in value.split(",")]
        elif isinstance(current_value, Enum):
            # Convert string to enum
            enum_class = type(current_value)
            value = enum_class(value)

        setattr(obj, attr_name, value)
        self.save()

    def reset(self) -> None:
        """Reset all preferences to defaults"""
        self.preferences = UserPreferences()
        self.save()

    def validate(self) -> list[str]:
        """
        Validate current preferences

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Validate AI settings
        if self.preferences.ai.max_suggestions < 1:
            errors.append("ai.max_suggestions must be at least 1")
        if self.preferences.ai.max_suggestions > 20:
            errors.append("ai.max_suggestions must not exceed 20")

        # Validate auto-update frequency
        if self.preferences.auto_update.frequency_hours < 1:
            errors.append("auto_update.frequency_hours must be at least 1")

        # Validate language code
        valid_languages = ["en", "es", "fr", "de", "ja", "zh", "pt", "ru"]
        if self.preferences.language not in valid_languages:
            errors.append(f"language must be one of: {', '.join(valid_languages)}")

        return errors

    def export_json(self, filepath: Path) -> None:
        """Export preferences to JSON file"""
        data = self._to_dict(include_metadata=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"[SUCCESS] Configuration exported to {filepath}")

    def import_json(self, filepath: Path) -> None:
        """Import preferences from JSON file"""
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        # Remove metadata
        data.pop("exported_at", None)

        self.preferences = self._from_dict(data)
        self.save()
        print(f"[SUCCESS] Configuration imported from {filepath}")

    def get_all_settings(self) -> dict[str, Any]:
        """Get all settings as a flat dictionary"""
        return self._to_dict()

    def get_config_info(self) -> dict[str, Any]:
        """Get configuration metadata"""
        return {
            "config_path": str(self.config_path),
            "config_exists": self.config_path.exists(),
            "config_size_bytes": (
                self.config_path.stat().st_size if self.config_path.exists() else 0
            ),
            "last_modified": (
                datetime.fromtimestamp(self.config_path.stat().st_mtime).isoformat()
                if self.config_path.exists()
                else None
            ),
        }


# CLI integration helpers
def format_preference_value(value: Any) -> str:
    """Format preference value for display"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return yaml.dump(value, default_flow_style=False).strip()
    return str(value)


def print_all_preferences(manager: PreferencesManager) -> None:
    """Print all preferences in a formatted way"""
    settings = manager.get_all_settings()

    print("\n[INFO] Current Configuration:")
    print("=" * 60)
    print(yaml.dump(settings, default_flow_style=False, sort_keys=False))
    print(f"\nConfig file: {manager.config_path}")


if __name__ == "__main__":
    # Quick test
    manager = PreferencesManager()
    print("User Preferences System loaded")
    print(f"Config location: {manager.config_path}")
    print(f"Current verbosity: {manager.get('verbosity')}")
    print(f"AI model: {manager.get('ai.model')}")
