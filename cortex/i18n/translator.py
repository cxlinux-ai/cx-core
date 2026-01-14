"""
Core translation module for Cortex Linux CLI.

Provides message translation with:
- Message catalog loading from YAML files
- Variable interpolation in messages
- Graceful fallback to English for missing translations
- Debug mode for showing translation keys
"""

import os
from pathlib import Path
from typing import Any

import yaml

# Supported languages with their display names
SUPPORTED_LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"name": "English", "native": "English"},
    "es": {"name": "Spanish", "native": "Español"},
    "fr": {"name": "French", "native": "Français"},
    "de": {"name": "German", "native": "Deutsch"},
    "zh": {"name": "Chinese", "native": "中文"},
}

DEFAULT_LANGUAGE = "en"


class Translator:
    """
    Handles message translation with catalog management.

    Features:
    - Loads message catalogs from YAML files
    - Supports variable interpolation using {variable} syntax
    - Falls back to English if translation is missing
    - Supports debug mode to show translation keys
    """

    def __init__(self, language: str = DEFAULT_LANGUAGE, debug: bool = False):
        """
        Initialize the translator.

        Args:
            language: Language code (e.g., 'en', 'es', 'fr')
            debug: If True, show translation keys instead of translated text
        """
        self._language = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        self._debug = debug
        self._catalogs: dict[str, dict[str, Any]] = {}
        self._locales_dir = Path(__file__).parent / "locales"

        # Load English as fallback
        self._load_catalog("en")

        # Load requested language if different from English
        if self._language != "en":
            self._load_catalog(self._language)

    @property
    def language(self) -> str:
        """Get the current language code."""
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        """
        Set the current language.

        Args:
            value: Language code to switch to

        Raises:
            ValueError: If language code is not supported
        """
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language: {value}. "
                f"Supported: {', '.join(SUPPORTED_LANGUAGES.keys())}"
            )
        self._language = value
        if value not in self._catalogs:
            self._load_catalog(value)

    @property
    def debug(self) -> bool:
        """Get debug mode status."""
        return self._debug

    @debug.setter
    def debug(self, value: bool) -> None:
        """Set debug mode."""
        self._debug = value

    def _load_catalog(self, language: str) -> None:
        """
        Load a message catalog from YAML file.

        Args:
            language: Language code to load

        Note:
            Silently fails if catalog file doesn't exist.
            Missing catalogs will fall back to English.
        """
        catalog_path = self._locales_dir / f"{language}.yaml"

        if catalog_path.exists():
            try:
                with open(catalog_path, encoding="utf-8") as f:
                    self._catalogs[language] = yaml.safe_load(f) or {}
            except (yaml.YAMLError, OSError) as e:
                # Log error but continue with empty catalog
                self._catalogs[language] = {}
        else:
            self._catalogs[language] = {}

    def _get_nested_value(self, data: dict[str, Any], key: str) -> str | None:
        """
        Get a nested value from a dictionary using dot notation.

        Args:
            data: Dictionary to search
            key: Dot-separated key (e.g., 'install.success')

        Returns:
            The value if found, None otherwise
        """
        parts = key.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return str(current) if current is not None else None

    def translate(self, key: str, **kwargs: Any) -> str:
        """
        Translate a message key with optional variable interpolation.

        Args:
            key: Message key using dot notation (e.g., 'install.success')
            **kwargs: Variables to interpolate into the message

        Returns:
            Translated message with variables replaced, or the key itself
            if no translation is found.

        Examples:
            >>> translator.translate("install.success")
            "Installation complete!"

            >>> translator.translate("install.package_installed", package="docker")
            "docker installed successfully"
        """
        if self._debug:
            return f"[{key}]"

        # Try current language first
        message = self._get_nested_value(self._catalogs.get(self._language, {}), key)

        # Fall back to English
        if message is None and self._language != "en":
            message = self._get_nested_value(self._catalogs.get("en", {}), key)

        # If still not found, return the key
        if message is None:
            return key

        # Interpolate variables
        if kwargs:
            try:
                message = message.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                # If interpolation fails, return message without interpolation
                # KeyError: missing named argument, IndexError: missing positional,
                # ValueError: malformed format string
                pass

        return message

    def get_all_keys(self, language: str | None = None) -> set[str]:
        """
        Get all translation keys for a language.

        Args:
            language: Language code, defaults to current language

        Returns:
            Set of all translation keys
        """
        lang = language or self._language
        catalog = self._catalogs.get(lang, {})
        return self._extract_keys(catalog)

    def _extract_keys(self, data: dict[str, Any], prefix: str = "") -> set[str]:
        """
        Recursively extract all keys from a nested dictionary.

        Args:
            data: Dictionary to extract keys from
            prefix: Current key prefix

        Returns:
            Set of dot-notation keys
        """
        keys = set()
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                keys.update(self._extract_keys(value, full_key))
            else:
                keys.add(full_key)
        return keys

    def get_missing_translations(self, language: str) -> set[str]:
        """
        Find keys that exist in English but not in the target language.

        Args:
            language: Target language to check

        Returns:
            Set of missing translation keys
        """
        if language not in self._catalogs:
            self._load_catalog(language)

        en_keys = self.get_all_keys("en")
        target_keys = self.get_all_keys(language)

        return en_keys - target_keys

    def reload_catalogs(self) -> None:
        """Reload all message catalogs from disk."""
        self._catalogs.clear()
        self._load_catalog("en")
        if self._language != "en":
            self._load_catalog(self._language)


# Global translator instance
_translator: Translator | None = None


def get_translator() -> Translator:
    """
    Get or create the global translator instance.

    Returns:
        The global Translator instance
    """
    global _translator
    if _translator is None:
        from cortex.i18n.config import LanguageConfig

        config = LanguageConfig()
        language = config.get_language()
        debug = os.environ.get("CORTEX_I18N_DEBUG", "").lower() in ("1", "true", "yes")
        _translator = Translator(language=language, debug=debug)
    return _translator


def set_language(language: str) -> None:
    """
    Set the global language.

    Args:
        language: Language code to switch to

    Raises:
        ValueError: If language code is not supported
    """
    translator = get_translator()
    translator.language = language


def get_language() -> str:
    """
    Get the current global language.

    Returns:
        Current language code
    """
    return get_translator().language


def t(key: str, **kwargs: Any) -> str:
    """
    Translate a message key (shorthand function).

    This is the primary function for translation throughout the codebase.

    Args:
        key: Message key using dot notation
        **kwargs: Variables to interpolate

    Returns:
        Translated message

    Examples:
        >>> t("install.success")
        "Installation complete!"

        >>> t("install.package_installed", package="docker")
        "docker installed successfully"
    """
    return get_translator().translate(key, **kwargs)


def reset_translator() -> None:
    """Reset the global translator (mainly for testing)."""
    global _translator
    _translator = None


def get_language_info() -> dict[str, str]:
    """
    Get information about the current language.

    Returns:
        Dictionary with language details:
        - code: Language code (e.g., 'es')
        - name: English name (e.g., 'Spanish')
        - native: Native name (e.g., 'Español')
    """
    lang = get_language()
    info = SUPPORTED_LANGUAGES.get(lang, SUPPORTED_LANGUAGES["en"])
    return {
        "code": lang,
        "name": info["name"],
        "native": info["native"],
    }


def get_supported_languages() -> dict[str, dict[str, str]]:
    """
    Get all supported languages.

    Returns:
        Dictionary mapping language codes to their info.
    """
    return SUPPORTED_LANGUAGES.copy()
