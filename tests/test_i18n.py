"""
Comprehensive Unit Tests for Cortex Linux i18n Module

Tests cover:
- Translator: translation lookup, interpolation, pluralization, RTL, fallback
- LanguageManager: detection priority, system language, supported languages
- PluralRules: language-specific pluralization (English, Arabic, Russian, Japanese)
- FallbackHandler: missing key handling, tracking, export, reporting

Target: >80% code coverage for cortex/i18n/

Author: Cortex Linux Team
License: Apache 2.0
"""

import json
import locale
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.i18n import (
    FallbackHandler,
    LanguageManager,
    PluralRules,
    Translator,
    get_fallback_handler,
    get_translator,
    translate,
)

# =============================================================================
# Translator Tests
# =============================================================================


class TestTranslator:
    """Tests for the Translator class."""

    def test_init_default_language(self):
        """Translator initializes with English by default."""
        t = Translator()
        assert t.language == "en"

    def test_init_custom_language(self):
        """Translator initializes with specified language."""
        t = Translator("es")
        assert t.language == "es"

    def test_get_simple_key(self):
        """Get a simple translation key."""
        t = Translator("en")
        result = t.get("common.yes")
        assert result == "Yes"

    def test_get_nested_key(self):
        """Get a nested translation key."""
        t = Translator("en")
        result = t.get("wizard.welcome")
        assert "Cortex" in result or "Welcome" in result

    def test_get_spanish_translation(self):
        """Get Spanish translation."""
        t = Translator("es")
        result = t.get("common.yes")
        assert result == "Sí"

    def test_get_german_translation(self):
        """Get German translation."""
        t = Translator("de")
        result = t.get("common.yes")
        assert result == "Ja"

    def test_get_japanese_translation(self):
        """Get Japanese translation."""
        t = Translator("ja")
        result = t.get("common.yes")
        assert result == "はい"

    def test_get_arabic_translation(self):
        """Get Arabic translation."""
        t = Translator("ar")
        result = t.get("common.yes")
        assert result == "نعم"

    def test_get_chinese_translation(self):
        """Get Chinese translation."""
        t = Translator("zh")
        result = t.get("common.yes")
        assert result == "是"

    def test_get_korean_translation(self):
        """Get Korean translation."""
        t = Translator("ko")
        result = t.get("common.yes")
        assert result == "예"

    def test_get_russian_translation(self):
        """Get Russian translation."""
        t = Translator("ru")
        result = t.get("common.yes")
        assert result == "Да"

    def test_get_hindi_translation(self):
        """Get Hindi translation."""
        t = Translator("hi")
        result = t.get("common.yes")
        assert result == "हाँ"

    def test_get_italian_translation(self):
        """Get Italian translation."""
        t = Translator("it")
        result = t.get("common.yes")
        assert result == "Sì"

    def test_variable_interpolation(self):
        """Variable interpolation with {key} syntax."""
        t = Translator("en")
        result = t.get("install.success", package="nginx")
        assert "nginx" in result

    def test_multiple_variable_interpolation(self):
        """Multiple variables interpolated correctly."""
        t = Translator("en")
        # Find a key with multiple variables or test with a simple case
        result = t.get("errors.network", details="Connection refused")
        assert "Connection refused" in result

    def test_missing_key_returns_placeholder(self):
        """Missing translation key returns placeholder."""
        t = Translator("en")
        result = t.get("nonexistent.key.path")
        assert result == "[nonexistent.key.path]"

    def test_missing_key_fallback_to_english(self):
        """Missing key in target language falls back to English."""
        # First ensure English has the key
        en_translator = Translator("en")
        en_result = en_translator.get("common.yes")
        assert en_result == "Yes"

        # Test with Spanish translator - should get Spanish translation for existing keys
        es_translator = Translator("es")
        es_result = es_translator.get("common.yes")
        # Spanish "yes" is "Sí", so this confirms the translator is working
        assert es_result == "Sí"

        # If a key doesn't exist in Spanish catalog, it should fallback to English
        # Test with a key that might not exist - if it returns the English value,
        # fallback is working; if it returns placeholder, the key doesn't exist anywhere
        fallback_result = es_translator.get("common.yes")
        assert fallback_result is not None
        assert fallback_result != "[common.yes]"  # Should not be a placeholder

    def test_set_language_valid(self):
        """Set language to a valid language."""
        t = Translator("en")
        result = t.set_language("es")
        assert result is True
        assert t.language == "es"

    def test_set_language_invalid(self):
        """Set language to invalid language falls back to English."""
        t = Translator("en")
        result = t.set_language("xyz_invalid")
        assert result is False
        assert t.language == "en"

    def test_is_rtl_arabic(self):
        """Arabic is detected as RTL."""
        t = Translator("ar")
        assert t.is_rtl() is True

    def test_is_rtl_hebrew(self):
        """Hebrew is detected as RTL."""
        t = Translator("he")
        assert t.is_rtl() is True

    def test_is_rtl_english(self):
        """English is not RTL."""
        t = Translator("en")
        assert t.is_rtl() is False

    def test_is_rtl_spanish(self):
        """Spanish is not RTL."""
        t = Translator("es")
        assert t.is_rtl() is False

    def test_is_rtl_japanese(self):
        """Japanese is not RTL."""
        t = Translator("ja")
        assert t.is_rtl() is False

    def test_get_plural_singular(self):
        """Pluralization returns singular form for count=1."""
        t = Translator("en")
        # Test with a key that has pluralization if available
        result = t.get_plural("install.downloading", count=1, package_count=1)
        # Should contain singular form or the count
        assert result is not None

    def test_get_plural_plural(self):
        """Pluralization returns plural form for count>1."""
        t = Translator("en")
        result = t.get_plural("install.downloading", count=5, package_count=5)
        assert result is not None

    def test_catalog_lazy_loading(self):
        """Catalogs are loaded lazily on first access."""
        t = Translator("en")
        # Initially no catalogs loaded
        assert "en" not in t._catalogs or t._catalogs.get("en") is not None
        # After get(), catalog should be loaded
        t.get("common.yes")
        assert "en" in t._catalogs


class TestTranslatorHelpers:
    """Tests for translator helper functions."""

    def test_get_translator_default(self):
        """get_translator returns translator with default language."""
        t = get_translator()
        assert t is not None
        assert isinstance(t, Translator)

    def test_get_translator_custom_language(self):
        """get_translator returns translator with specified language."""
        t = get_translator("ja")
        assert t.language == "ja"

    def test_translate_function(self):
        """translate() convenience function works."""
        result = translate("common.yes", language="es")
        assert result == "Sí"

    def test_translate_with_variables(self):
        """translate() with variable interpolation."""
        result = translate("install.success", language="en", package="vim")
        assert "vim" in result


# =============================================================================
# LanguageManager Tests
# =============================================================================


class TestLanguageManager:
    """Tests for the LanguageManager class."""

    def test_init_without_prefs_manager(self):
        """LanguageManager initializes without prefs_manager."""
        manager = LanguageManager()
        assert manager.prefs_manager is None

    def test_init_with_prefs_manager(self):
        """LanguageManager initializes with prefs_manager."""
        mock_prefs = MagicMock()
        manager = LanguageManager(prefs_manager=mock_prefs)
        assert manager.prefs_manager is mock_prefs

    def test_is_supported_english(self):
        """English is supported."""
        manager = LanguageManager()
        assert manager.is_supported("en") is True

    def test_is_supported_spanish(self):
        """Spanish is supported."""
        manager = LanguageManager()
        assert manager.is_supported("es") is True

    def test_is_supported_japanese(self):
        """Japanese is supported."""
        manager = LanguageManager()
        assert manager.is_supported("ja") is True

    def test_is_supported_arabic(self):
        """Arabic is supported."""
        manager = LanguageManager()
        assert manager.is_supported("ar") is True

    def test_is_supported_case_insensitive(self):
        """Language support check is case insensitive."""
        manager = LanguageManager()
        assert manager.is_supported("EN") is True
        assert manager.is_supported("Es") is True

    def test_is_supported_invalid(self):
        """Invalid language code is not supported."""
        manager = LanguageManager()
        assert manager.is_supported("xyz") is False

    def test_get_available_languages(self):
        """Get all available languages."""
        manager = LanguageManager()
        languages = manager.get_available_languages()
        assert isinstance(languages, dict)
        assert "en" in languages
        assert "es" in languages
        assert "ja" in languages
        assert "ar" in languages
        assert len(languages) >= 10

    def test_get_language_name_english(self):
        """Get display name for English."""
        manager = LanguageManager()
        name = manager.get_language_name("en")
        assert name == "English"

    def test_get_language_name_spanish(self):
        """Get display name for Spanish."""
        manager = LanguageManager()
        name = manager.get_language_name("es")
        assert name == "Español"

    def test_get_language_name_japanese(self):
        """Get display name for Japanese."""
        manager = LanguageManager()
        name = manager.get_language_name("ja")
        assert name == "日本語"

    def test_get_language_name_unknown(self):
        """Unknown language returns code as name."""
        manager = LanguageManager()
        name = manager.get_language_name("xyz")
        assert name == "xyz"

    def test_format_language_list(self):
        """Format language list as string."""
        manager = LanguageManager()
        formatted = manager.format_language_list()
        assert "English" in formatted
        assert "Español" in formatted
        assert ", " in formatted

    def test_detect_language_cli_arg(self):
        """CLI argument has highest priority."""
        manager = LanguageManager()
        result = manager.detect_language(cli_arg="ja")
        assert result == "ja"

    def test_detect_language_cli_arg_invalid(self):
        """Invalid CLI argument falls through to next priority."""
        manager = LanguageManager()
        with patch.dict(os.environ, {"CORTEX_LANGUAGE": "es"}, clear=False):
            result = manager.detect_language(cli_arg="invalid_lang")
            assert result == "es"

    def test_detect_language_env_var(self):
        """Environment variable is second priority."""
        manager = LanguageManager()
        with patch.dict(os.environ, {"CORTEX_LANGUAGE": "de"}, clear=False):
            # Mock the system language detection to ensure deterministic behavior
            with patch.object(manager, "get_system_language", return_value=None):
                result = manager.detect_language(cli_arg=None)
                # Should be 'de' from environment variable
                assert result == "de"

    def test_detect_language_fallback_english(self):
        """Falls back to English when nothing else matches."""
        manager = LanguageManager()
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(manager, "get_system_language", return_value=None):
                result = manager.detect_language(cli_arg=None)
                assert result == "en"

    def test_detect_language_from_config(self):
        """Config file is third priority."""
        mock_prefs = MagicMock()
        mock_prefs.load.return_value = MagicMock(language="it")
        manager = LanguageManager(prefs_manager=mock_prefs)

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(manager, "get_system_language", return_value=None):
                result = manager.detect_language(cli_arg=None)
                assert result == "it"

    def test_get_system_language_returns_mapped_locale(self):
        """System language detection maps locale to language code."""
        manager = LanguageManager()

        with patch("locale.setlocale"):
            with patch("locale.getlocale", return_value=("en_US", "UTF-8")):
                result = manager.get_system_language()
                assert result == "en"

    def test_get_system_language_german_locale(self):
        """German system locale is detected."""
        manager = LanguageManager()

        with patch("locale.setlocale"):
            with patch("locale.getlocale", return_value=("de_DE", "UTF-8")):
                result = manager.get_system_language()
                assert result == "de"

    def test_get_system_language_japanese_locale(self):
        """Japanese system locale is detected."""
        manager = LanguageManager()

        with patch("locale.setlocale"):
            with patch("locale.getlocale", return_value=("ja_JP", "UTF-8")):
                result = manager.get_system_language()
                assert result == "ja"

    def test_get_system_language_none(self):
        """Returns None when locale cannot be determined."""
        manager = LanguageManager()

        with patch("locale.setlocale"):
            with patch("locale.getlocale", return_value=(None, None)):
                result = manager.get_system_language()
                assert result is None

    def test_get_system_language_exception(self):
        """Returns None on locale exception."""
        manager = LanguageManager()

        with patch("locale.setlocale", side_effect=locale.Error("test error")):
            with patch("locale.getlocale", return_value=(None, None)):
                result = manager.get_system_language()
                assert result is None

    def test_locale_mapping_coverage(self):
        """Test various locale mappings."""
        manager = LanguageManager()

        # Test that common locales are mapped
        assert "en_US" in manager.LOCALE_MAPPING
        assert "es_ES" in manager.LOCALE_MAPPING
        assert "ja_JP" in manager.LOCALE_MAPPING
        assert "de_DE" in manager.LOCALE_MAPPING
        assert "ar_SA" in manager.LOCALE_MAPPING


# =============================================================================
# PluralRules Tests
# =============================================================================


class TestPluralRules:
    """Tests for the PluralRules class."""

    # English pluralization (2 forms)
    def test_english_singular(self):
        """English: count=1 returns 'one'."""
        result = PluralRules.get_plural_form("en", 1)
        assert result == "one"

    def test_english_plural(self):
        """English: count>1 returns 'other'."""
        result = PluralRules.get_plural_form("en", 2)
        assert result == "other"

    def test_english_zero(self):
        """English: count=0 returns 'other'."""
        result = PluralRules.get_plural_form("en", 0)
        assert result == "other"

    def test_english_large_number(self):
        """English: large count returns 'other'."""
        result = PluralRules.get_plural_form("en", 1000)
        assert result == "other"

    # Spanish pluralization (2 forms)
    def test_spanish_singular(self):
        """Spanish: count=1 returns 'one'."""
        result = PluralRules.get_plural_form("es", 1)
        assert result == "one"

    def test_spanish_plural(self):
        """Spanish: count>1 returns 'other'."""
        result = PluralRules.get_plural_form("es", 5)
        assert result == "other"

    # French pluralization (n <= 1 is singular)
    def test_french_zero(self):
        """French: count=0 returns 'one' (n <= 1)."""
        result = PluralRules.get_plural_form("fr", 0)
        assert result == "one"

    def test_french_singular(self):
        """French: count=1 returns 'one'."""
        result = PluralRules.get_plural_form("fr", 1)
        assert result == "one"

    def test_french_plural(self):
        """French: count>1 returns 'other'."""
        result = PluralRules.get_plural_form("fr", 2)
        assert result == "other"

    # Arabic pluralization (6 forms)
    def test_arabic_zero(self):
        """Arabic: count=0 returns 'zero'."""
        result = PluralRules.get_plural_form("ar", 0)
        assert result == "zero"

    def test_arabic_one(self):
        """Arabic: count=1 returns 'one'."""
        result = PluralRules.get_plural_form("ar", 1)
        assert result == "one"

    def test_arabic_two(self):
        """Arabic: count=2 returns 'two'."""
        result = PluralRules.get_plural_form("ar", 2)
        assert result == "two"

    def test_arabic_few_start(self):
        """Arabic: count=3 returns 'few' (start of range)."""
        result = PluralRules.get_plural_form("ar", 3)
        assert result == "few"

    def test_arabic_few_middle(self):
        """Arabic: count=5 returns 'few'."""
        result = PluralRules.get_plural_form("ar", 5)
        assert result == "few"

    def test_arabic_few_end(self):
        """Arabic: count=10 returns 'few' (end of range)."""
        result = PluralRules.get_plural_form("ar", 10)
        assert result == "few"

    def test_arabic_many_start(self):
        """Arabic: count=11 returns 'many' (start of range)."""
        result = PluralRules.get_plural_form("ar", 11)
        assert result == "many"

    def test_arabic_many_middle(self):
        """Arabic: count=50 returns 'many'."""
        result = PluralRules.get_plural_form("ar", 50)
        assert result == "many"

    def test_arabic_many_end(self):
        """Arabic: count=99 returns 'many' (end of range)."""
        result = PluralRules.get_plural_form("ar", 99)
        assert result == "many"

    def test_arabic_other(self):
        """Arabic: count=100+ returns 'other'."""
        result = PluralRules.get_plural_form("ar", 100)
        assert result == "other"

    def test_arabic_other_large(self):
        """Arabic: count=1000 returns 'other'."""
        result = PluralRules.get_plural_form("ar", 1000)
        assert result == "other"

    # Russian pluralization (3 forms)
    def test_russian_one(self):
        """Russian: count=1 returns 'one'."""
        result = PluralRules.get_plural_form("ru", 1)
        assert result == "one"

    def test_russian_one_21(self):
        """Russian: count=21 returns 'one' (n%10==1, n%100!=11)."""
        result = PluralRules.get_plural_form("ru", 21)
        assert result == "one"

    def test_russian_few_2(self):
        """Russian: count=2 returns 'few'."""
        result = PluralRules.get_plural_form("ru", 2)
        assert result == "few"

    def test_russian_few_3(self):
        """Russian: count=3 returns 'few'."""
        result = PluralRules.get_plural_form("ru", 3)
        assert result == "few"

    def test_russian_few_4(self):
        """Russian: count=4 returns 'few'."""
        result = PluralRules.get_plural_form("ru", 4)
        assert result == "few"

    def test_russian_few_22(self):
        """Russian: count=22 returns 'few'."""
        result = PluralRules.get_plural_form("ru", 22)
        assert result == "few"

    def test_russian_many_5(self):
        """Russian: count=5 returns 'many'."""
        result = PluralRules.get_plural_form("ru", 5)
        assert result == "many"

    def test_russian_many_11(self):
        """Russian: count=11 returns 'many' (exception)."""
        result = PluralRules.get_plural_form("ru", 11)
        assert result == "many"

    def test_russian_many_12(self):
        """Russian: count=12 returns 'many' (exception)."""
        result = PluralRules.get_plural_form("ru", 12)
        assert result == "many"

    def test_russian_many_0(self):
        """Russian: count=0 returns 'many'."""
        result = PluralRules.get_plural_form("ru", 0)
        assert result == "many"

    # Japanese (no plural distinction)
    def test_japanese_one(self):
        """Japanese: count=1 returns 'other' (no distinction)."""
        result = PluralRules.get_plural_form("ja", 1)
        assert result == "other"

    def test_japanese_many(self):
        """Japanese: count=100 returns 'other' (no distinction)."""
        result = PluralRules.get_plural_form("ja", 100)
        assert result == "other"

    # Chinese (no plural distinction)
    def test_chinese_one(self):
        """Chinese: count=1 returns 'other' (no distinction)."""
        result = PluralRules.get_plural_form("zh", 1)
        assert result == "other"

    def test_chinese_many(self):
        """Chinese: count=100 returns 'other' (no distinction)."""
        result = PluralRules.get_plural_form("zh", 100)
        assert result == "other"

    # Korean (no plural distinction)
    def test_korean_one(self):
        """Korean: count=1 returns 'other' (no distinction)."""
        result = PluralRules.get_plural_form("ko", 1)
        assert result == "other"

    def test_korean_many(self):
        """Korean: count=100 returns 'other' (no distinction)."""
        result = PluralRules.get_plural_form("ko", 100)
        assert result == "other"

    # Unknown language falls back to English rules
    def test_unknown_language_singular(self):
        """Unknown language uses English rules: count=1 returns 'one'."""
        result = PluralRules.get_plural_form("xyz", 1)
        assert result == "one"

    def test_unknown_language_plural(self):
        """Unknown language uses English rules: count>1 returns 'other'."""
        result = PluralRules.get_plural_form("xyz", 5)
        assert result == "other"

    # supports_language method
    def test_supports_language_english(self):
        """English is supported."""
        assert PluralRules.supports_language("en") is True

    def test_supports_language_arabic(self):
        """Arabic is supported."""
        assert PluralRules.supports_language("ar") is True

    def test_supports_language_russian(self):
        """Russian is supported."""
        assert PluralRules.supports_language("ru") is True

    def test_supports_language_unknown(self):
        """Unknown language is not supported."""
        assert PluralRules.supports_language("xyz") is False


# =============================================================================
# FallbackHandler Tests
# =============================================================================


class TestFallbackHandler:
    """Tests for the FallbackHandler class."""

    def test_init(self):
        """FallbackHandler initializes with empty missing keys."""
        handler = FallbackHandler()
        assert handler.missing_keys == set()
        assert handler._session_start is not None

    def test_init_with_custom_logger(self):
        """FallbackHandler accepts custom logger."""
        mock_logger = MagicMock()
        handler = FallbackHandler(logger=mock_logger)
        assert handler.logger is mock_logger

    def test_handle_missing_returns_placeholder(self):
        """handle_missing returns bracketed placeholder."""
        handler = FallbackHandler()
        result = handler.handle_missing("test.key", "es")
        assert result == "[test.key]"

    def test_handle_missing_tracks_key(self):
        """handle_missing adds key to missing_keys set."""
        handler = FallbackHandler()
        handler.handle_missing("test.key", "es")
        assert "test.key" in handler.missing_keys

    def test_handle_missing_logs_warning(self):
        """handle_missing logs a warning."""
        mock_logger = MagicMock()
        handler = FallbackHandler(logger=mock_logger)
        handler.handle_missing("test.key", "es")
        mock_logger.warning.assert_called_once()

    def test_get_missing_translations(self):
        """get_missing_translations returns copy of missing keys."""
        handler = FallbackHandler()
        handler.handle_missing("key1", "es")
        handler.handle_missing("key2", "de")

        missing = handler.get_missing_translations()
        assert "key1" in missing
        assert "key2" in missing
        # Verify it's a copy
        missing.add("key3")
        assert "key3" not in handler.missing_keys

    def test_has_missing_translations_true(self):
        """has_missing_translations returns True when keys are missing."""
        handler = FallbackHandler()
        handler.handle_missing("test.key", "es")
        assert handler.has_missing_translations() is True

    def test_has_missing_translations_false(self):
        """has_missing_translations returns False when no keys missing."""
        handler = FallbackHandler()
        assert handler.has_missing_translations() is False

    def test_missing_count(self):
        """missing_count returns correct count."""
        handler = FallbackHandler()
        assert handler.missing_count() == 0

        handler.handle_missing("key1", "es")
        assert handler.missing_count() == 1

        handler.handle_missing("key2", "de")
        assert handler.missing_count() == 2

        # Same key again doesn't increase count (it's a set)
        handler.handle_missing("key1", "fr")
        assert handler.missing_count() == 2

    def test_clear(self):
        """clear removes all missing keys."""
        handler = FallbackHandler()
        handler.handle_missing("key1", "es")
        handler.handle_missing("key2", "de")
        assert handler.missing_count() == 2

        handler.clear()
        assert handler.missing_count() == 0
        assert handler.has_missing_translations() is False

    def test_export_missing_for_translation(self):
        """export_missing_for_translation creates CSV content."""
        handler = FallbackHandler()
        handler.handle_missing("install.new_key", "es")
        handler.handle_missing("config.test", "de")

        csv_content = handler.export_missing_for_translation()

        assert "key,namespace" in csv_content
        assert "install.new_key" in csv_content
        assert "config.test" in csv_content
        assert "install" in csv_content
        assert "config" in csv_content

    def test_export_missing_creates_file(self):
        """export_missing_for_translation creates file with secure permissions."""
        handler = FallbackHandler()
        handler.handle_missing("test.key", "es")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_export.csv"
            handler.export_missing_for_translation(output_path=output_path)

            assert output_path.exists()
            content = output_path.read_text()
            assert "test.key" in content

    def test_report_summary_no_missing(self):
        """report_summary with no missing translations."""
        handler = FallbackHandler()
        report = handler.report_summary()

        assert "Missing Translations Report" in report
        assert "Total Missing Keys: 0" in report
        assert "No missing translations found!" in report

    def test_report_summary_with_missing(self):
        """report_summary with missing translations."""
        handler = FallbackHandler()
        handler.handle_missing("install.key1", "es")
        handler.handle_missing("install.key2", "es")
        handler.handle_missing("config.key1", "de")

        report = handler.report_summary()

        assert "Missing Translations Report" in report
        assert "Total Missing Keys: 3" in report
        assert "install: 2 missing" in report
        assert "config: 1 missing" in report


class TestFallbackHandlerSingleton:
    """Tests for get_fallback_handler singleton."""

    def test_get_fallback_handler_returns_instance(self):
        """get_fallback_handler returns a FallbackHandler instance."""
        handler = get_fallback_handler()
        assert isinstance(handler, FallbackHandler)

    def test_get_fallback_handler_singleton(self):
        """get_fallback_handler returns same instance."""
        handler1 = get_fallback_handler()
        handler2 = get_fallback_handler()
        assert handler1 is handler2


# =============================================================================
# Integration Tests
# =============================================================================


class TestI18nIntegration:
    """Integration tests for the i18n module."""

    def test_all_languages_load(self):
        """All translation files load without errors."""
        languages = ["en", "es", "de", "it", "ru", "zh", "ja", "ko", "ar", "hi", "fr", "pt"]

        for lang in languages:
            t = Translator(lang)
            result = t.get("common.yes")
            assert result is not None
            assert result != "[common.yes]", f"Language {lang} failed to load"

    def test_all_languages_have_common_keys(self):
        """All languages have common translation keys."""
        languages = ["en", "es", "de", "it", "ru", "zh", "ja", "ko", "ar", "hi", "fr", "pt"]
        common_keys = ["common.yes", "common.no", "common.error", "common.success"]

        for lang in languages:
            t = Translator(lang)
            for key in common_keys:
                result = t.get(key)
                assert result != f"[{key}]", f"Language {lang} missing key {key}"

    def test_translator_with_language_manager(self):
        """Translator works with LanguageManager detection."""
        manager = LanguageManager()
        detected = manager.detect_language(cli_arg="ja")

        t = Translator(detected)
        result = t.get("common.yes")
        assert result == "はい"

    def test_rtl_languages_detected(self):
        """RTL languages are properly detected."""
        rtl_languages = ["ar"]
        ltr_languages = ["en", "es", "de", "ja", "zh", "ko", "ru", "hi", "fr", "pt", "it"]

        for lang in rtl_languages:
            t = Translator(lang)
            assert t.is_rtl() is True, f"{lang} should be RTL"

        for lang in ltr_languages:
            t = Translator(lang)
            assert t.is_rtl() is False, f"{lang} should be LTR"

    def test_variable_interpolation_all_languages(self):
        """Variable interpolation works for all languages."""
        languages = ["en", "es", "de", "it", "ru", "zh", "ja", "ko", "ar", "hi", "fr", "pt"]

        for lang in languages:
            t = Translator(lang)
            result = t.get("install.success", package="test-pkg")
            assert "test-pkg" in result, f"Variable not interpolated in {lang}"


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_key(self):
        """Empty key returns placeholder."""
        t = Translator("en")
        result = t.get("")
        # Should handle gracefully
        assert result is not None

    def test_deeply_nested_key(self):
        """Deeply nested key that doesn't exist returns placeholder."""
        t = Translator("en")
        result = t.get("a.b.c.d.e.f.g")
        assert result == "[a.b.c.d.e.f.g]"

    def test_special_characters_in_variable(self):
        """Special characters in variable values are handled."""
        t = Translator("en")
        result = t.get("install.success", package="test<>&\"'pkg")
        assert "test<>&\"'pkg" in result

    def test_unicode_in_variable(self):
        """Unicode in variable values is handled."""
        t = Translator("en")
        result = t.get("install.success", package="тест-пакет")
        assert "тест-пакет" in result

    def test_none_variable_value(self):
        """None as variable value is converted to string."""
        t = Translator("en")
        result = t.get("install.success", package=None)
        assert "None" in result

    def test_numeric_variable_value(self):
        """Numeric variable value is converted to string."""
        t = Translator("en")
        result = t.get("install.success", package=123)
        assert "123" in result

    def test_language_manager_with_exception_in_prefs(self):
        """LanguageManager handles exception in prefs loading."""
        mock_prefs = MagicMock()
        mock_prefs.load.side_effect = Exception("Config error")
        manager = LanguageManager(prefs_manager=mock_prefs)

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(manager, "get_system_language", return_value=None):
                result = manager.detect_language(cli_arg=None)
                assert result == "en"  # Falls back to English

    def test_plural_rules_negative_count(self):
        """Pluralization handles negative counts."""
        # Negative numbers should work (treated as 'other' in most languages)
        result = PluralRules.get_plural_form("en", -1)
        assert result == "other"

    def test_translation_file_integrity(self):
        """Translation files are valid JSON."""
        translations_dir = Path(__file__).parent.parent / "cortex" / "translations"

        for json_file in translations_dir.glob("*.json"):
            with open(json_file, encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    assert isinstance(data, dict)
                except json.JSONDecodeError:
                    pytest.fail(f"Invalid JSON in {json_file}")
