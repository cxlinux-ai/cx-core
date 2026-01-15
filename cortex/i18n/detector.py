"""
OS language auto-detection for Cortex Linux CLI.

Detects the system language from environment variables:
- LANGUAGE
- LC_ALL
- LC_MESSAGES
- LANG
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def _get_supported_language_codes() -> set[str]:
    """
    Get supported language codes from the single source of truth.

    This dynamically derives language codes from SUPPORTED_LANGUAGES in translator.py,
    eliminating duplication and ensuring consistency across the codebase.

    Returns:
        Set of supported language codes (e.g., {"en", "es", "fr", "de", "zh"})
    """
    # Import here to avoid circular import
    from cortex.i18n.translator import SUPPORTED_LANGUAGES

    return set(SUPPORTED_LANGUAGES.keys())


# Extended language code mappings (handle variants)
LANGUAGE_MAPPINGS = {
    # English variants
    "en": "en",
    "en_us": "en",
    "en_gb": "en",
    "en_au": "en",
    "en_ca": "en",
    # Spanish variants
    "es": "es",
    "es_es": "es",
    "es_mx": "es",
    "es_ar": "es",
    "es_co": "es",
    "es_cl": "es",
    # French variants
    "fr": "fr",
    "fr_fr": "fr",
    "fr_ca": "fr",
    "fr_be": "fr",
    "fr_ch": "fr",
    # German variants
    "de": "de",
    "de_de": "de",
    "de_at": "de",
    "de_ch": "de",
    # Chinese variants
    "zh": "zh",
    "zh_cn": "zh",
    "zh_tw": "zh",
    "zh_hk": "zh",
    "chinese": "zh",
    # Handle common variations
    "c": "en",  # C locale defaults to English
    "posix": "en",  # POSIX locale defaults to English
}


def _parse_locale(locale_string: str) -> str | None:
    """
    Parse a locale string and extract the language code.

    Handles formats like:
    - en_US.UTF-8
    - es_ES
    - fr.UTF-8
    - de
    - zh_CN.utf8

    Args:
        locale_string: Raw locale string from environment

    Returns:
        Normalized language code or None if cannot parse
    """
    if not locale_string:
        return None

    # Normalize to lowercase
    locale_lower = locale_string.lower().strip()

    # Handle empty or C/POSIX locale
    if not locale_lower or locale_lower in ("c", "posix"):
        return "en"

    # Remove encoding suffix (e.g., .UTF-8, .utf8)
    locale_lower = re.sub(r"\.[a-z0-9-]+$", "", locale_lower)

    # Try direct mapping first
    if locale_lower in LANGUAGE_MAPPINGS:
        return LANGUAGE_MAPPINGS[locale_lower]

    # Try just the language part (before underscore)
    if "_" in locale_lower:
        lang_part = locale_lower.split("_")[0]
        if lang_part in LANGUAGE_MAPPINGS:
            return LANGUAGE_MAPPINGS[lang_part]

    # Try with underscore for regional variants
    if "_" in locale_lower:
        full_locale = locale_lower.replace("-", "_")
        if full_locale in LANGUAGE_MAPPINGS:
            return LANGUAGE_MAPPINGS[full_locale]

    return None


def detect_os_language() -> str:
    """
    Detect the OS language from environment variables.

    Checks environment variables in order:
    1. LANGUAGE (GNU gettext)
    2. LC_ALL (overrides all LC_* variables)
    3. LC_MESSAGES (controls message language)
    4. LANG (general locale setting)

    The first valid, supported language found is returned.

    Returns:
        Detected language code, or 'en' as fallback

    Examples:
        With LANG=es_ES.UTF-8: returns 'es'
        With LC_ALL=fr_FR: returns 'fr'
        With LANGUAGE=de: returns 'de'
    """
    # Environment variables to check, in priority order
    env_vars = ["LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"]

    for var in env_vars:
        value = os.environ.get(var, "")
        if not value:
            continue

        # LANGUAGE can have multiple values separated by ':'
        if var == "LANGUAGE":
            for lang_part in value.split(":"):
                parsed = _parse_locale(lang_part)
                if parsed and parsed in _get_supported_language_codes():
                    return parsed
        else:
            parsed = _parse_locale(value)
            if parsed and parsed in _get_supported_language_codes():
                return parsed

    # Default fallback
    return "en"


def get_os_locale_info() -> dict[str, str | None]:
    """
    Get detailed OS locale information for debugging.

    Returns:
        Dictionary with all relevant locale environment variables
    """
    env_vars = ["LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG", "LC_CTYPE", "LC_TIME", "LC_NUMERIC"]

    info = {}
    for var in env_vars:
        info[var] = os.environ.get(var)

    info["detected_language"] = detect_os_language()

    return info
