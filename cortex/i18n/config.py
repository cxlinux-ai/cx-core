"""
Language configuration persistence for Cortex Linux CLI.

Handles:
- Reading/writing language preference to ~/.cortex/preferences.yaml
- Language validation
- Integration with existing Cortex configuration system
- Thread-safe and process-safe file access

Concurrency Safety:
- Thread locks (threading.Lock) protect against race conditions within a single process
- File locks (fcntl.flock) protect against race conditions between multiple processes
- Both are needed because thread locks don't work across process boundaries
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

import yaml

from cortex.i18n.detector import detect_os_language

# Get logger for this module
logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"


def get_supported_language_codes() -> set[str]:
    """
    Get the set of supported language codes from the single source of truth.

    This dynamically derives language codes from SUPPORTED_LANGUAGES in translator.py,
    ensuring there's only one place where supported languages are defined.

    Returns:
        Set of supported language codes (e.g., {"en", "es", "fr", "de", "zh"})
    """
    from cortex.i18n.translator import SUPPORTED_LANGUAGES

    return set(SUPPORTED_LANGUAGES.keys())


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

    Thread Safety:
        Uses threading.Lock for intra-process synchronization and fcntl.flock
        for inter-process synchronization. This ensures safe concurrent access
        from multiple threads and multiple processes.
    """

    def __init__(self) -> None:
        """Initialize the language configuration manager."""
        self.cortex_dir = Path.home() / ".cortex"
        self.preferences_file = self.cortex_dir / "preferences.yaml"
        self._thread_lock = threading.Lock()

        # Ensure directory exists
        self.cortex_dir.mkdir(mode=0o700, exist_ok=True)

    def _acquire_file_lock(self, file_obj: Any, exclusive: bool = False) -> None:
        """
        Acquire a file lock for concurrent access.

        Uses fcntl.flock on Unix systems for inter-process synchronization.
        On Windows, falls back to no file locking (thread lock still applies).

        Args:
            file_obj: Open file object to lock
            exclusive: If True, acquire exclusive lock for writing;
                      if False, acquire shared lock for reading

        Note:
            Thread locks alone are insufficient because they only protect
            against concurrent access within the same process. When multiple
            Cortex processes run simultaneously (e.g., multiple terminal windows),
            file locks prevent data corruption.
        """
        if sys.platform != "win32":
            import fcntl

            lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            try:
                fcntl.flock(file_obj.fileno(), lock_type)
            except (OSError, IOError) as e:
                logger.debug(f"Could not acquire file lock: {e}")

    def _release_file_lock(self, file_obj: Any) -> None:
        """
        Release a file lock.

        Args:
            file_obj: Open file object to unlock
        """
        if sys.platform != "win32":
            import fcntl

            try:
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
            except (OSError, IOError) as e:
                logger.debug(f"Could not release file lock: {e}")

    def _load_preferences(self) -> dict[str, Any]:
        """
        Load preferences from file with proper locking.

        Returns:
            Dictionary of preferences, or empty dict on failure

        Handles:
            - Missing file (returns empty dict)
            - Malformed YAML (returns empty dict, logs warning)
            - Empty file (returns empty dict)
            - Invalid types (returns empty dict if not a dict)
            - Race conditions (uses both thread and file locks)

        Note:
            The exists() check and file read are both inside the critical section
            to prevent TOCTOU (time-of-check to time-of-use) race conditions.
        """
        try:
            with self._thread_lock:
                if not self.preferences_file.exists():
                    return {}

                with open(self.preferences_file, encoding="utf-8") as f:
                    self._acquire_file_lock(f, exclusive=False)  # Shared lock for reading
                    try:
                        content = f.read()
                        if not content.strip():
                            # Empty file
                            return {}

                        data = yaml.safe_load(content)

                        # Validate that we got a dict
                        if data is None:
                            return {}
                        if not isinstance(data, dict):
                            logger.warning(
                                f"Preferences file contains invalid type: {type(data).__name__}, "
                                "expected dict. Using defaults."
                            )
                            return {}

                        return data
                    finally:
                        self._release_file_lock(f)

        except yaml.YAMLError as e:
            # Log the YAML parsing error but don't crash
            logger.warning(f"Malformed YAML in preferences file: {e}. Using defaults.")
            return {}
        except OSError as e:
            # Handle file system errors (file deleted between check and read, permissions, etc.)
            logger.debug(f"Could not read preferences file: {e}")
            return {}

    def _save_preferences(self, preferences: dict[str, Any]) -> None:
        """
        Save preferences to file with proper locking.

        Args:
            preferences: Dictionary of preferences to save

        Raises:
            RuntimeError: If preferences cannot be saved

        Note:
            Uses exclusive file lock to prevent concurrent writes from
            corrupting the preferences file.
        """
        from cortex.i18n import t

        try:
            with self._thread_lock:
                # Write atomically by writing to temp file first, then renaming
                temp_file = self.preferences_file.with_suffix(".yaml.tmp")

                with open(temp_file, "w", encoding="utf-8") as f:
                    self._acquire_file_lock(f, exclusive=True)  # Exclusive lock for writing
                    try:
                        yaml.safe_dump(preferences, f, default_flow_style=False, allow_unicode=True)
                    finally:
                        self._release_file_lock(f)

                # Atomic rename
                temp_file.rename(self.preferences_file)

        except OSError as e:
            error_msg = t("language.set_failed", error=str(e))
            raise RuntimeError(error_msg) from e

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
        supported_codes = get_supported_language_codes()

        # 1. Environment variable override
        env_lang = os.environ.get("CORTEX_LANGUAGE", "").lower()
        if env_lang in supported_codes:
            return env_lang

        # 2. User preference from config file
        preferences = self._load_preferences()
        saved_lang = preferences.get("language", "")
        if isinstance(saved_lang, str):
            saved_lang = saved_lang.lower()
            if saved_lang in supported_codes:
                return saved_lang

        # 3. OS-detected language
        detected_lang = detect_os_language()
        if detected_lang in supported_codes:
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
        from cortex.i18n import t

        supported_codes = get_supported_language_codes()
        language = language.lower()

        if language not in supported_codes:
            raise ValueError(
                t("language.invalid_code", code=language)
                + " "
                + t("language.supported_codes")
                + ": "
                + ", ".join(sorted(supported_codes))
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

        supported_codes = get_supported_language_codes()

        # Check each source
        env_lang = os.environ.get("CORTEX_LANGUAGE", "").lower()
        preferences = self._load_preferences()
        saved_lang = preferences.get("language", "")
        if isinstance(saved_lang, str):
            saved_lang = saved_lang.lower()
        else:
            saved_lang = ""
        detected_lang = detect_os_language()

        # Determine effective language and its source
        # Note: source values are internal keys, translated at display time via t()
        if env_lang in supported_codes:
            effective_lang = env_lang
            source = "environment"  # Translated via t("language.set_from_env")
        elif saved_lang in supported_codes:
            effective_lang = saved_lang
            source = "config"  # Translated via t("language.set_from_config")
        elif detected_lang in supported_codes:
            effective_lang = detected_lang
            source = "auto-detected"  # Translated via t("language.auto_detected")
        else:
            effective_lang = DEFAULT_LANGUAGE
            source = "default"  # Translated via t("language.default")

        return {
            "language": effective_lang,
            "source": source,
            "name": LANG_INFO.get(effective_lang, {}).get("name", ""),
            "native_name": LANG_INFO.get(effective_lang, {}).get("native", ""),
            "env_override": env_lang if env_lang else None,
            "saved_preference": saved_lang if saved_lang else None,
            "detected_language": detected_lang,
        }
