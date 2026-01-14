"""
Language configuration persistence for Cortex Linux CLI.

Handles:
- Reading/writing language preference to ~/.cortex/preferences.yaml
- Language validation
- Integration with existing Cortex configuration system
"""

import os
import threading
from pathlib import Path
from typing import Any

import yaml

from cortex.i18n.detector import detect_os_language

# Supported language codes for membership checking (set, not dict)
# Named differently from translator.SUPPORTED_LANGUAGES (dict with full info)
# to avoid confusion - this is just for validation
SUPPORTED_LANGUAGE_CODES = {"en", "es", "fr", "de", "zh"}
DEFAULT_LANGUAGE = "en"


class LanguageConfig:
    """
    Manages language preference persistence.

    Language preference is stored in ~/.cortex/preferences.yaml
    alongside other Cortex preferences.

    Preference resolution order:
    1. CORTEX_LANGUAGE environment variable
    2. User preference in ~/.cortex/preferences.yaml
    3. OS-detected language
    4. Default (English)
    """

    def __init__(self):
        """Initialize the language configuration manager."""
        self.cortex_dir = Path.home() / ".cortex"
        self.preferences_file = self.cortex_dir / "preferences.yaml"
        self._file_lock = threading.Lock()

        # Ensure directory exists
        self.cortex_dir.mkdir(mode=0o700, exist_ok=True)

    def _load_preferences(self) -> dict[str, Any]:
        """
        Load preferences from file.

        Returns:
            Dictionary of preferences

        Note:
            The exists() check and file read are both inside the critical section
            to prevent TOCTOU (time-of-check to time-of-use) race conditions.
        """
        try:
            with self._file_lock:
                if self.preferences_file.exists():
                    with open(self.preferences_file, encoding="utf-8") as f:
                        return yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            # Handle race-related failures (file deleted between check and read)
            # or YAML parsing errors gracefully
            pass
        return {}

    def _save_preferences(self, preferences: dict[str, Any]) -> None:
        """
        Save preferences to file.

        Args:
            preferences: Dictionary of preferences to save
        """
        try:
            with self._file_lock:
                with open(self.preferences_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(preferences, f, default_flow_style=False, allow_unicode=True)
        except OSError as e:
            raise RuntimeError(f"Failed to save language preference: {e}")

    def get_language(self) -> str:
        """
        Get the current language preference.

        Resolution order:
        1. CORTEX_LANGUAGE environment variable
        2. User preference in config file
        3. OS-detected language
        4. Default (English)

        Returns:
            Language code
        """
        # 1. Environment variable override
        env_lang = os.environ.get("CORTEX_LANGUAGE", "").lower()
        if env_lang in SUPPORTED_LANGUAGE_CODES:
            return env_lang

        # 2. User preference from config file
        preferences = self._load_preferences()
        saved_lang = preferences.get("language", "").lower()
        if saved_lang in SUPPORTED_LANGUAGE_CODES:
            return saved_lang

        # 3. OS-detected language
        detected_lang = detect_os_language()
        if detected_lang in SUPPORTED_LANGUAGE_CODES:
            return detected_lang

        # 4. Default
        return DEFAULT_LANGUAGE

    def set_language(self, language: str) -> None:
        """
        Set the language preference.

        Args:
            language: Language code to set

        Raises:
            ValueError: If language code is not supported
        """
        language = language.lower()
        if language not in SUPPORTED_LANGUAGE_CODES:
            raise ValueError(
                f"Unsupported language: {language}. "
                f"Supported: {', '.join(sorted(SUPPORTED_LANGUAGE_CODES))}"
            )

        preferences = self._load_preferences()
        preferences["language"] = language
        self._save_preferences(preferences)

    def clear_language(self) -> None:
        """
        Clear the saved language preference (use auto-detection instead).
        """
        preferences = self._load_preferences()
        if "language" in preferences:
            del preferences["language"]
            self._save_preferences(preferences)

    def get_language_info(self) -> dict[str, Any]:
        """
        Get detailed language configuration info.

        Returns:
            Dictionary with language info including source
        """
        from cortex.i18n.translator import SUPPORTED_LANGUAGES as LANG_INFO

        # Check each source
        env_lang = os.environ.get("CORTEX_LANGUAGE", "").lower()
        preferences = self._load_preferences()
        saved_lang = preferences.get("language", "").lower()
        detected_lang = detect_os_language()

        # Determine effective language and its source
        if env_lang in SUPPORTED_LANGUAGE_CODES:
            effective_lang = env_lang
            source = "environment"
        elif saved_lang in SUPPORTED_LANGUAGE_CODES:
            effective_lang = saved_lang
            source = "config"
        elif detected_lang in SUPPORTED_LANGUAGE_CODES:
            effective_lang = detected_lang
            source = "auto-detected"
        else:
            effective_lang = DEFAULT_LANGUAGE
            source = "default"

        return {
            "language": effective_lang,
            "source": source,
            "name": LANG_INFO.get(effective_lang, {}).get("name", "Unknown"),
            "native_name": LANG_INFO.get(effective_lang, {}).get("native", "Unknown"),
            "env_override": env_lang if env_lang else None,
            "saved_preference": saved_lang if saved_lang else None,
            "detected_language": detected_lang,
        }
