#!/usr/bin/env python3
"""
Cortex Linux - User Preferences & Settings System
Issue #26: Persistent user preferences and configuration management

This module provides comprehensive configuration management for user preferences,
allowing customization of AI behavior, confirmation prompts, verbosity levels,
and other system settings.
"""

import os
import yaml
import json
from pathlib import Path
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, asdict, field
from enum import Enum
from datetime import datetime


class VerbosityLevel(Enum):
    """Verbosity levels for output control"""
    QUIET = "quiet"
    NORMAL = "normal"
    VERBOSE = "verbose"
    DEBUG = "debug"


class AICreativity(Enum):
    """AI creativity/temperature settings"""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    CREATIVE = "creative"


@dataclass
class ConfirmationSettings:
    """Settings for confirmation prompts"""
    before_install: bool = True
    before_remove: bool = True
    before_upgrade: bool = False
    before_system_changes: bool = True
    
    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)


@dataclass
class AutoUpdateSettings:
    """Settings for automatic updates"""
    check_on_start: bool = True
    auto_install: bool = False
    frequency_hours: int = 24
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AISettings:
    """AI behavior configuration"""
    model: str = "claude-sonnet-4"
    creativity: str = AICreativity.BALANCED.value
    explain_steps: bool = True
    suggest_alternatives: bool = True
    learn_from_history: bool = True
    max_suggestions: int = 5
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PackageSettings:
    """Package management preferences"""
    default_sources: List[str] = field(default_factory=lambda: ["official"])
    prefer_latest: bool = False
    auto_cleanup: bool = True
    backup_before_changes: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConflictSettings:
    """Conflict resolution preferences"""
    default_strategy: str = "interactive"
    saved_resolutions: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserPreferences:
    """Complete user preferences configuration"""
    verbosity: str = VerbosityLevel.NORMAL.value
    confirmations: ConfirmationSettings = field(default_factory=ConfirmationSettings)
    auto_update: AutoUpdateSettings = field(default_factory=AutoUpdateSettings)
    ai: AISettings = field(default_factory=AISettings)
    packages: PackageSettings = field(default_factory=PackageSettings)
    conflicts: ConflictSettings = field(default_factory=ConflictSettings)
    theme: str = "default"
    language: str = "en"
    timezone: str = "UTC"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert preferences to dictionary format"""
        return {
            "verbosity": self.verbosity,
            "confirmations": self.confirmations.to_dict(),
            "auto_update": self.auto_update.to_dict(),
            "ai": self.ai.to_dict(),
            "packages": self.packages.to_dict(),
            "conflicts": self.conflicts.to_dict(),
            "theme": self.theme,
            "language": self.language,
            "timezone": self.timezone,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPreferences':
        """Create UserPreferences from dictionary"""
        confirmations = ConfirmationSettings(**data.get("confirmations", {}))
        auto_update = AutoUpdateSettings(**data.get("auto_update", {}))
        ai = AISettings(**data.get("ai", {}))
        packages = PackageSettings(**data.get("packages", {}))
        conflicts = ConflictSettings(**data.get("conflicts", {}))
        
        return cls(
            verbosity=data.get("verbosity", VerbosityLevel.NORMAL.value),
            confirmations=confirmations,
            auto_update=auto_update,
            ai=ai,
            packages=packages,
            conflicts=conflicts,
            theme=data.get("theme", "default"),
            language=data.get("language", "en"),
            timezone=data.get("timezone", "UTC"),
        )


class PreferencesManager:
    """
    User Preferences Manager for Cortex Linux
    
    Features:
    - YAML-based configuration storage
    - Validation and schema enforcement
    - Default configuration management
    - Configuration migration support
    - Safe file operations with backup
    """
    
    DEFAULT_CONFIG_DIR = Path.home() / ".config" / "cortex"
    DEFAULT_CONFIG_FILE = "preferences.yaml"
    BACKUP_SUFFIX = ".backup"
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the preferences manager
        
        Args:
            config_path: Custom path to config file (uses default if None)
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = self.DEFAULT_CONFIG_DIR / self.DEFAULT_CONFIG_FILE
        
        self.config_dir = self.config_path.parent
        self._ensure_config_directory()
        self._preferences: Optional[UserPreferences] = None
    
    def _ensure_config_directory(self):
        """Ensure configuration directory exists"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def _create_backup(self) -> Optional[Path]:
        """
        Create backup of existing config file
        
        Returns:
            Path to backup file or None if no backup created
        """
        if not self.config_path.exists():
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.config_path.with_suffix(f"{self.BACKUP_SUFFIX}.{timestamp}")
        
        try:
            import shutil
            shutil.copy2(self.config_path, backup_path)
            return backup_path
        except Exception as e:
            raise IOError(f"Failed to create backup: {str(e)}")
    
    def load(self) -> UserPreferences:
        """
        Load preferences from config file
        
        Returns:
            UserPreferences object
        """
        if not self.config_path.exists():
            self._preferences = UserPreferences()
            self.save()
            return self._preferences
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not data:
                data = {}
            
            self._preferences = UserPreferences.from_dict(data)
            return self._preferences
        
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {str(e)}")
        except Exception as e:
            raise IOError(f"Failed to load config file: {str(e)}")
    
    def save(self, backup: bool = True) -> Path:
        """
        Save preferences to config file
        
        Args:
            backup: Create backup before saving
        
        Returns:
            Path to saved config file
        """
        if self._preferences is None:
            raise RuntimeError("No preferences loaded. Call load() first.")
        
        if backup and self.config_path.exists():
            self._create_backup()
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    self._preferences.to_dict(),
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    indent=2
                )
            
            return self.config_path
        
        except Exception as e:
            raise IOError(f"Failed to save config file: {str(e)}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a preference value by dot-notation key
        
        Args:
            key: Preference key (e.g., "ai.model", "confirmations.before_install")
            default: Default value if key not found
        
        Returns:
            Preference value or default
        """
        if self._preferences is None:
            self.load()
        
        parts = key.split(".")
        value = self._preferences.to_dict()
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> bool:
        """
        Set a preference value by dot-notation key
        
        Args:
            key: Preference key (e.g., "ai.model")
            value: New value
        
        Returns:
            True if successful, False otherwise
        """
        if self._preferences is None:
            self.load()
        
        parts = key.split(".")
        
        try:
            if parts[0] == "verbosity":
                if value not in [v.value for v in VerbosityLevel]:
                    raise ValueError(f"Invalid verbosity level: {value}")
                self._preferences.verbosity = value
            
            elif parts[0] == "confirmations":
                if len(parts) != 2:
                    raise ValueError("Invalid confirmations key")
                if not isinstance(value, bool):
                    raise ValueError("Confirmation values must be boolean")
                setattr(self._preferences.confirmations, parts[1], value)
            
            elif parts[0] == "auto_update":
                if len(parts) != 2:
                    raise ValueError("Invalid auto_update key")
                if parts[1] == "frequency_hours" and not isinstance(value, int):
                    raise ValueError("frequency_hours must be an integer")
                elif parts[1] != "frequency_hours" and not isinstance(value, bool):
                    raise ValueError("auto_update boolean values required")
                setattr(self._preferences.auto_update, parts[1], value)
            
            elif parts[0] == "ai":
                if len(parts) != 2:
                    raise ValueError("Invalid ai key")
                if parts[1] == "creativity":
                    if value not in [c.value for c in AICreativity]:
                        raise ValueError(f"Invalid creativity level: {value}")
                elif parts[1] == "max_suggestions" and not isinstance(value, int):
                    raise ValueError("max_suggestions must be an integer")
                setattr(self._preferences.ai, parts[1], value)
            
            elif parts[0] == "packages":
                if len(parts) != 2:
                    raise ValueError("Invalid packages key")
                if parts[1] == "default_sources" and not isinstance(value, list):
                    raise ValueError("default_sources must be a list")
                setattr(self._preferences.packages, parts[1], value)
            
            elif parts[0] == "conflicts":
                if len(parts) != 2:
                    raise ValueError("Invalid conflicts key")
                if parts[1] == "saved_resolutions" and not isinstance(value, dict):
                    raise ValueError("saved_resolutions must be a dictionary")
                setattr(self._preferences.conflicts, parts[1], value)
            
            elif parts[0] in ["theme", "language", "timezone"]:
                setattr(self._preferences, parts[0], value)
            
            else:
                raise ValueError(f"Unknown preference key: {key}")
            
            return True
        
        except (AttributeError, ValueError) as e:
            raise ValueError(f"Failed to set preference '{key}': {str(e)}")
    
    def reset(self, key: Optional[str] = None) -> bool:
        """
        Reset preferences to defaults
        
        Args:
            key: Specific key to reset (resets all if None)
        
        Returns:
            True if successful
        """
        if key is None:
            self._preferences = UserPreferences()
            self.save()
            return True
        
        defaults = UserPreferences()
        default_value = defaults.to_dict()
        
        parts = key.split(".")
        for part in parts:
            if isinstance(default_value, dict) and part in default_value:
                default_value = default_value[part]
            else:
                raise ValueError(f"Invalid preference key: {key}")
        
        self.set(key, default_value)
        self.save()
        return True
    
    def validate(self) -> List[str]:
        """
        Validate current configuration
        
        Returns:
            List of validation errors (empty if valid)
        """
        if self._preferences is None:
            self.load()
        
        errors = []
        
        if self._preferences.verbosity not in [v.value for v in VerbosityLevel]:
            errors.append(f"Invalid verbosity level: {self._preferences.verbosity}")
        
        if self._preferences.ai.creativity not in [c.value for c in AICreativity]:
            errors.append(f"Invalid AI creativity level: {self._preferences.ai.creativity}")
        
        valid_models = ["claude-sonnet-4", "gpt-4", "gpt-4-turbo", "claude-3-opus"]
        if self._preferences.ai.model not in valid_models:
            errors.append(f"Unknown AI model: {self._preferences.ai.model}")
        
        if self._preferences.ai.max_suggestions < 1:
            errors.append("ai.max_suggestions must be at least 1")
        
        if self._preferences.auto_update.frequency_hours < 1:
            errors.append("auto_update.frequency_hours must be at least 1")
        
        if not self._preferences.packages.default_sources:
            errors.append("At least one package source required")
        
        return errors
    
    def export_json(self, output_path: Path) -> Path:
        """
        Export preferences to JSON file
        
        Args:
            output_path: Path to output JSON file
        
        Returns:
            Path to exported file
        """
        if self._preferences is None:
            self.load()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self._preferences.to_dict(), f, indent=2)
        
        return output_path
    
    def import_json(self, input_path: Path) -> bool:
        """
        Import preferences from JSON file
        
        Args:
            input_path: Path to JSON file
        
        Returns:
            True if successful
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self._preferences = UserPreferences.from_dict(data)
        
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid configuration: {', '.join(errors)}")
        
        self.save()
        return True
    
    def get_config_info(self) -> Dict[str, Any]:
        """
        Get information about configuration
        
        Returns:
            Dictionary with config file info
        """
        info = {
            "config_path": str(self.config_path),
            "exists": self.config_path.exists(),
            "writable": os.access(self.config_dir, os.W_OK),
        }
        
        if self.config_path.exists():
            stat = self.config_path.stat()
            info["size_bytes"] = stat.st_size
            info["modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
        
        return info
    
    def list_all(self) -> Dict[str, Any]:
        """
        List all preferences with current values
        
        Returns:
            Dictionary of all preferences
        """
        if self._preferences is None:
            self.load()
        
        return self._preferences.to_dict()
