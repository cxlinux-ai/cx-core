"""
Tests for the i18n (internationalization) module.

Tests cover:
- Core translation functionality
- Language switching
- Auto-detection from OS environment
- Locale-aware formatting
- Missing translation handling
- Configuration persistence
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


class TestTranslator(unittest.TestCase):
    """Tests for the Translator class."""

    def setUp(self):
        """Set up test fixtures."""
        # Reset global translator before each test
        from cortex.i18n.translator import reset_translator

        reset_translator()

    def tearDown(self):
        """Clean up after tests."""
        from cortex.i18n.translator import reset_translator

        reset_translator()

    def test_default_language_is_english(self):
        """Test that default language is English."""
        from cortex.i18n.translator import DEFAULT_LANGUAGE, Translator

        translator = Translator()
        self.assertEqual(translator.language, DEFAULT_LANGUAGE)
        self.assertEqual(translator.language, "en")

    def test_set_language(self):
        """Test setting language to supported languages."""
        from cortex.i18n.translator import Translator

        translator = Translator()

        for lang in ["en", "es", "fr", "de", "zh"]:
            translator.language = lang
            self.assertEqual(translator.language, lang)

    def test_set_unsupported_language_raises(self):
        """Test that setting unsupported language raises ValueError."""
        from cortex.i18n.translator import Translator

        translator = Translator()

        with self.assertRaises(ValueError) as context:
            translator.language = "xx"

        self.assertIn("Unsupported language", str(context.exception))

    def test_translate_basic_key(self):
        """Test basic translation of a key."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="en")

        # Test a key that should exist in all languages
        result = translator.translate("common.success")
        self.assertEqual(result, "Success")

    def test_translate_with_variables(self):
        """Test translation with variable interpolation."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="en")

        # Test interpolation
        result = translator.translate("language.changed", language="English")
        self.assertEqual(result, "Language changed to English")

    def test_translate_missing_key_returns_key(self):
        """Test that missing keys return the key itself."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="en")

        result = translator.translate("nonexistent.key.path")
        self.assertEqual(result, "nonexistent.key.path")

    def test_translate_fallback_to_english(self):
        """Test fallback to English for missing translations."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="es")

        # Test a key that exists in English
        result = translator.translate("common.success")
        # Should return Spanish translation if available
        self.assertIsNotNone(result)
        self.assertNotEqual(result, "common.success")

    def test_debug_mode(self):
        """Test debug mode shows translation keys."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="en", debug=True)

        result = translator.translate("common.success")
        self.assertEqual(result, "[common.success]")

    def test_debug_mode_toggle(self):
        """Test toggling debug mode."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="en")
        self.assertFalse(translator.debug)

        translator.debug = True
        self.assertTrue(translator.debug)

        result = translator.translate("common.success")
        self.assertEqual(result, "[common.success]")

    def test_global_translator_singleton(self):
        """Test that get_translator returns the same instance."""
        from cortex.i18n.translator import get_translator

        t1 = get_translator()
        t2 = get_translator()
        self.assertIs(t1, t2)

    def test_shorthand_t_function(self):
        """Test the shorthand t() function."""
        from cortex.i18n import set_language, t

        # Ensure we're using English for this test
        set_language("en")
        result = t("common.success")
        self.assertEqual(result, "Success")

    def test_set_language_global(self):
        """Test set_language function."""
        from cortex.i18n import get_language, set_language

        set_language("es")
        self.assertEqual(get_language(), "es")

        set_language("en")
        self.assertEqual(get_language(), "en")

    def test_spanish_translations(self):
        """Test Spanish translations."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="es")

        self.assertEqual(translator.translate("common.success"), "Éxito")
        self.assertEqual(translator.translate("common.error"), "Error")

    def test_french_translations(self):
        """Test French translations."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="fr")

        self.assertEqual(translator.translate("common.success"), "Succès")
        self.assertEqual(translator.translate("common.error"), "Erreur")

    def test_german_translations(self):
        """Test German translations."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="de")

        self.assertEqual(translator.translate("common.success"), "Erfolg")
        self.assertEqual(translator.translate("common.error"), "Fehler")

    def test_chinese_translations(self):
        """Test Chinese translations."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="zh")

        self.assertEqual(translator.translate("common.success"), "成功")
        self.assertEqual(translator.translate("common.error"), "错误")

    def test_get_all_keys(self):
        """Test getting all translation keys."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="en")
        keys = translator.get_all_keys()

        self.assertIn("common.success", keys)
        self.assertIn("common.error", keys)
        self.assertIn("install.success", keys)

    def test_get_missing_translations(self):
        """Test finding missing translations."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="en")

        # All keys should be present in English (source)
        missing = translator.get_missing_translations("en")
        self.assertEqual(len(missing), 0)


class TestLanguageConfig(unittest.TestCase):
    """Tests for language configuration persistence."""

    def setUp(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_home = Path(self.temp_dir.name)

        # Reset global translator
        from cortex.i18n.translator import reset_translator

        reset_translator()

    def tearDown(self):
        """Clean up temp directory."""
        self.temp_dir.cleanup()

        from cortex.i18n.translator import reset_translator

        reset_translator()

    def test_malformed_yaml_returns_empty_dict(self):
        """Test that malformed YAML in preferences file returns empty dict and doesn't crash."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()

            # Create malformed YAML file
            prefs_file = self.temp_home / ".cortex" / "preferences.yaml"
            prefs_file.parent.mkdir(parents=True, exist_ok=True)
            prefs_file.write_text("invalid: yaml: content: [broken")

            # Should not crash, should return default language
            lang = config.get_language()
            self.assertEqual(lang, "en")

    def test_empty_yaml_file_returns_empty_dict(self):
        """Test that empty preferences file returns empty dict."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()

            # Create empty file
            prefs_file = self.temp_home / ".cortex" / "preferences.yaml"
            prefs_file.parent.mkdir(parents=True, exist_ok=True)
            prefs_file.write_text("")

            # Should not crash, should return default language
            lang = config.get_language()
            self.assertEqual(lang, "en")

    def test_whitespace_only_yaml_file_returns_empty_dict(self):
        """Test that whitespace-only preferences file returns empty dict."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()

            # Create whitespace-only file
            prefs_file = self.temp_home / ".cortex" / "preferences.yaml"
            prefs_file.parent.mkdir(parents=True, exist_ok=True)
            prefs_file.write_text("   \n\t\n  ")

            # Should not crash, should return default language
            lang = config.get_language()
            self.assertEqual(lang, "en")

    def test_invalid_type_in_yaml_returns_empty_dict(self):
        """Test that YAML with invalid root type (not dict) returns empty dict."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()

            # Create YAML file with list instead of dict
            prefs_file = self.temp_home / ".cortex" / "preferences.yaml"
            prefs_file.parent.mkdir(parents=True, exist_ok=True)
            prefs_file.write_text("- item1\n- item2\n- item3")

            # Should not crash, should return default language
            lang = config.get_language()
            self.assertEqual(lang, "en")

    def test_yaml_with_string_root_returns_empty_dict(self):
        """Test that YAML with string root type returns empty dict."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()

            # Create YAML file with just a string
            prefs_file = self.temp_home / ".cortex" / "preferences.yaml"
            prefs_file.parent.mkdir(parents=True, exist_ok=True)
            prefs_file.write_text("just a plain string")

            # Should not crash, should return default language
            lang = config.get_language()
            self.assertEqual(lang, "en")

    def test_yaml_with_invalid_language_type_uses_default(self):
        """Test that YAML with non-string language value uses default."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()

            # Create YAML file with integer language
            prefs_file = self.temp_home / ".cortex" / "preferences.yaml"
            prefs_file.parent.mkdir(parents=True, exist_ok=True)
            prefs_file.write_text("language: 123")

            # Should not crash, should return default language
            lang = config.get_language()
            self.assertEqual(lang, "en")

    def test_yaml_with_null_language_uses_default(self):
        """Test that YAML with null language value uses default."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()

            # Create YAML file with null language
            prefs_file = self.temp_home / ".cortex" / "preferences.yaml"
            prefs_file.parent.mkdir(parents=True, exist_ok=True)
            prefs_file.write_text("language: null")

            # Should not crash, should return default language
            lang = config.get_language()
            self.assertEqual(lang, "en")

    def test_get_language_default(self):
        """Test default language when no preference is set."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            with patch.dict(os.environ, {}, clear=True):
                from cortex.i18n.config import LanguageConfig

                config = LanguageConfig()
                lang = config.get_language()
                # Should fall back to English since no env var, no config, and no OS detection
                self.assertEqual(lang, "en")

    def test_set_and_get_language(self):
        """Test setting and getting language preference."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()
            config.set_language("es")

            # Create new config instance to test persistence
            config2 = LanguageConfig()
            self.assertEqual(config2.get_language(), "es")

    def test_set_invalid_language_raises(self):
        """Test that setting invalid language raises ValueError."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()

            with self.assertRaises(ValueError):
                config.set_language("invalid")

    def test_env_variable_override(self):
        """Test CORTEX_LANGUAGE environment variable takes precedence."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            with patch.dict(os.environ, {"CORTEX_LANGUAGE": "fr"}, clear=True):
                from cortex.i18n.config import LanguageConfig

                config = LanguageConfig()
                # First set a different language
                config.set_language("de")

                # But env var should take precedence
                self.assertEqual(config.get_language(), "fr")

    def test_clear_language(self):
        """Test clearing language preference."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            with patch.dict(os.environ, {}, clear=True):
                from cortex.i18n.config import LanguageConfig

                config = LanguageConfig()
                config.set_language("de")
                self.assertEqual(config.get_language(), "de")

                config.clear_language()
                # Should fall back to default
                self.assertEqual(config.get_language(), "en")

    def test_get_language_info(self):
        """Test getting detailed language info."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()
            config.set_language("es")

            info = config.get_language_info()

            self.assertEqual(info["language"], "es")
            self.assertEqual(info["source"], "config")
            self.assertEqual(info["name"], "Spanish")
            self.assertEqual(info["native_name"], "Español")


class TestLanguageDetector(unittest.TestCase):
    """Tests for OS language auto-detection."""

    def test_detect_english_from_lang(self):
        """Test detection of English from LANG variable."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(os.environ, {"LANG": "en_US.UTF-8"}, clear=True):
            lang = detect_os_language()
            self.assertEqual(lang, "en")

    def test_detect_spanish_from_lang(self):
        """Test detection of Spanish from LANG variable."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(os.environ, {"LANG": "es_ES.UTF-8"}, clear=True):
            lang = detect_os_language()
            self.assertEqual(lang, "es")

    def test_detect_french_from_lang(self):
        """Test detection of French from LANG variable."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(os.environ, {"LANG": "fr_FR.UTF-8"}, clear=True):
            lang = detect_os_language()
            self.assertEqual(lang, "fr")

    def test_detect_german_from_lang(self):
        """Test detection of German from LANG variable."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(os.environ, {"LANG": "de_DE.UTF-8"}, clear=True):
            lang = detect_os_language()
            self.assertEqual(lang, "de")

    def test_detect_chinese_from_lang(self):
        """Test detection of Chinese from LANG variable."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(os.environ, {"LANG": "zh_CN.UTF-8"}, clear=True):
            lang = detect_os_language()
            self.assertEqual(lang, "zh")

    def test_lc_all_takes_precedence(self):
        """Test that LC_ALL takes precedence over LANG."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(os.environ, {"LANG": "en_US.UTF-8", "LC_ALL": "fr_FR.UTF-8"}, clear=True):
            lang = detect_os_language()
            self.assertEqual(lang, "fr")

    def test_language_variable_takes_precedence(self):
        """Test that LANGUAGE takes precedence over LC_ALL."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(
            os.environ,
            {"LANGUAGE": "de", "LC_ALL": "fr_FR.UTF-8", "LANG": "en_US.UTF-8"},
            clear=True,
        ):
            lang = detect_os_language()
            self.assertEqual(lang, "de")

    def test_fallback_to_english(self):
        """Test fallback to English when no supported language detected."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(os.environ, {"LANG": "ja_JP.UTF-8"}, clear=True):
            lang = detect_os_language()
            self.assertEqual(lang, "en")

    def test_c_locale_returns_english(self):
        """Test that C locale returns English."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(os.environ, {"LANG": "C"}, clear=True):
            lang = detect_os_language()
            self.assertEqual(lang, "en")

    def test_posix_locale_returns_english(self):
        """Test that POSIX locale returns English."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(os.environ, {"LANG": "POSIX"}, clear=True):
            lang = detect_os_language()
            self.assertEqual(lang, "en")

    def test_empty_env_returns_english(self):
        """Test fallback to English when no env vars set."""
        from cortex.i18n.detector import detect_os_language

        with patch.dict(os.environ, {}, clear=True):
            lang = detect_os_language()
            self.assertEqual(lang, "en")

    def test_get_os_locale_info(self):
        """Test getting OS locale info for debugging."""
        from cortex.i18n.detector import get_os_locale_info

        with patch.dict(os.environ, {"LANG": "en_US.UTF-8", "LC_ALL": ""}, clear=True):
            info = get_os_locale_info()

            self.assertIn("LANG", info)
            self.assertIn("detected_language", info)
            self.assertEqual(info["detected_language"], "en")


class TestLocaleFormatter(unittest.TestCase):
    """Tests for locale-aware formatting."""

    def test_format_date_english(self):
        """Test date formatting in English locale."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")
        dt = datetime(2024, 3, 15)

        result = formatter.format_date(dt)
        self.assertEqual(result, "2024-03-15")

    def test_format_date_german(self):
        """Test date formatting in German locale."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="de")
        dt = datetime(2024, 3, 15)

        result = formatter.format_date(dt)
        self.assertEqual(result, "15.03.2024")

    def test_format_date_french(self):
        """Test date formatting in French locale."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="fr")
        dt = datetime(2024, 3, 15)

        result = formatter.format_date(dt)
        self.assertEqual(result, "15/03/2024")

    def test_format_number_english(self):
        """Test number formatting in English locale."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")

        result = formatter.format_number(1234567)
        self.assertEqual(result, "1,234,567")

    def test_format_number_german(self):
        """Test number formatting in German locale."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="de")

        result = formatter.format_number(1234567)
        self.assertEqual(result, "1.234.567")

    def test_format_number_french(self):
        """Test number formatting in French locale."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="fr")

        result = formatter.format_number(1234567)
        self.assertEqual(result, "1 234 567")

    def test_format_number_with_decimals(self):
        """Test number formatting with decimal places."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")

        result = formatter.format_number(1234.567, decimals=2)
        self.assertEqual(result, "1,234.57")

    def test_format_file_size_bytes(self):
        """Test file size formatting for bytes."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")

        result = formatter.format_file_size(500)
        self.assertEqual(result, "500 B")

    def test_format_file_size_kb(self):
        """Test file size formatting for kilobytes."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")

        result = formatter.format_file_size(1536)
        self.assertIn("KB", result)

    def test_format_file_size_mb(self):
        """Test file size formatting for megabytes."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")

        result = formatter.format_file_size(1536 * 1024)
        self.assertIn("MB", result)

    def test_format_file_size_gb(self):
        """Test file size formatting for gigabytes."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")

        result = formatter.format_file_size(2 * 1024 * 1024 * 1024)
        self.assertIn("GB", result)

    def test_format_time_ago_just_now(self):
        """Test relative time for just now."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")
        now = datetime.now()

        result = formatter.format_time_ago(now, now)
        self.assertEqual(result, "just now")

    def test_format_time_ago_seconds(self):
        """Test relative time for seconds."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")
        now = datetime.now()
        past = now - timedelta(seconds=30)

        result = formatter.format_time_ago(past, now)
        self.assertIn("seconds ago", result)

    def test_format_time_ago_minutes(self):
        """Test relative time for minutes."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")
        now = datetime.now()
        past = now - timedelta(minutes=5)

        result = formatter.format_time_ago(past, now)
        self.assertIn("minutes ago", result)

    def test_format_time_ago_hours(self):
        """Test relative time for hours."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")
        now = datetime.now()
        past = now - timedelta(hours=3)

        result = formatter.format_time_ago(past, now)
        self.assertIn("hours ago", result)

    def test_format_time_ago_spanish(self):
        """Test relative time in Spanish."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="es")
        now = datetime.now()
        past = now - timedelta(minutes=5)

        result = formatter.format_time_ago(past, now)
        self.assertIn("hace", result)
        self.assertIn("minutos", result)

    def test_format_time_ago_chinese(self):
        """Test relative time in Chinese."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="zh")
        now = datetime.now()
        past = now - timedelta(minutes=5)

        result = formatter.format_time_ago(past, now)
        self.assertIn("分钟前", result)

    def test_format_duration_milliseconds(self):
        """Test duration formatting for milliseconds."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")

        result = formatter.format_duration(0.5)
        self.assertIn("ms", result)

    def test_format_duration_seconds(self):
        """Test duration formatting for seconds."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")

        result = formatter.format_duration(45.2)
        self.assertIn("s", result)
        self.assertIn("45", result)

    def test_format_duration_minutes(self):
        """Test duration formatting for minutes."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")

        result = formatter.format_duration(150)  # 2m 30s
        self.assertIn("m", result)

    def test_format_duration_hours(self):
        """Test duration formatting for hours."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")

        result = formatter.format_duration(3700)  # 1h 1m
        self.assertIn("h", result)

    def test_formatter_language_setter(self):
        """Test setting language on formatter."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="en")
        self.assertEqual(formatter.language, "en")

        formatter.language = "de"
        self.assertEqual(formatter.language, "de")

    def test_formatter_invalid_language_fallback(self):
        """Test that invalid language falls back to English."""
        from cortex.i18n.formatter import LocaleFormatter

        formatter = LocaleFormatter(language="invalid")
        self.assertEqual(formatter.language, "en")


class TestSupportedLanguages(unittest.TestCase):
    """Tests for supported languages metadata."""

    def test_all_supported_languages_have_catalogs(self):
        """Test that all supported languages have message catalogs."""
        from pathlib import Path

        from cortex.i18n.translator import SUPPORTED_LANGUAGES

        locales_dir = Path(__file__).parent.parent / "cortex" / "i18n" / "locales"

        for lang_code in SUPPORTED_LANGUAGES:
            catalog_path = locales_dir / f"{lang_code}.yaml"
            self.assertTrue(catalog_path.exists(), f"Missing catalog for language: {lang_code}")

    def test_all_languages_have_metadata(self):
        """Test that all supported languages have name and native fields."""
        from cortex.i18n.translator import SUPPORTED_LANGUAGES

        for lang_code, info in SUPPORTED_LANGUAGES.items():
            self.assertIn("name", info, f"Missing 'name' for {lang_code}")
            self.assertIn("native", info, f"Missing 'native' for {lang_code}")

    def test_required_languages_supported(self):
        """Test that all required languages are supported."""
        from cortex.i18n.translator import SUPPORTED_LANGUAGES

        required = ["en", "es", "fr", "de", "zh"]
        for lang in required:
            self.assertIn(lang, SUPPORTED_LANGUAGES)


class TestTranslationCompleteness(unittest.TestCase):
    """Tests to verify translation completeness."""

    def test_all_languages_have_common_keys(self):
        """Test that all languages have the common keys."""
        from cortex.i18n.translator import SUPPORTED_LANGUAGES, Translator

        translator = Translator(language="en")
        en_keys = translator.get_all_keys("en")

        common_keys = [
            "common.success",
            "common.error",
            "common.warning",
            "install.success",
            "language.changed",
        ]

        for lang in SUPPORTED_LANGUAGES:
            translator.language = lang
            for key in common_keys:
                result = translator.translate(key)
                self.assertNotEqual(result, key, f"Key '{key}' not translated in {lang}")

    def test_no_english_leaks_in_spanish(self):
        """Test that Spanish doesn't have English strings for key messages."""
        from cortex.i18n.translator import Translator

        translator = Translator(language="es")

        # These should NOT be English
        success = translator.translate("common.success")
        self.assertNotEqual(success, "Success")
        self.assertEqual(success, "Éxito")

    def test_variable_interpolation_all_languages(self):
        """Test that variable interpolation works in all languages."""
        from cortex.i18n.translator import SUPPORTED_LANGUAGES, Translator

        for lang in SUPPORTED_LANGUAGES:
            translator = Translator(language=lang)
            result = translator.translate("language.changed", language="Test")
            self.assertIn("Test", result, f"Interpolation failed for {lang}")
            self.assertNotIn("{language}", result, f"Variable not replaced in {lang}")


class TestCLIIntegration(unittest.TestCase):
    """Tests for CLI integration with i18n."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_home = Path(self.temp_dir.name)

        from cortex.i18n.translator import reset_translator

        reset_translator()

    def tearDown(self):
        """Clean up after tests."""
        self.temp_dir.cleanup()

        from cortex.i18n.translator import reset_translator

        reset_translator()

    def test_cli_language_list(self):
        """Test CLI language list command."""
        import sys
        from unittest.mock import patch

        with patch("pathlib.Path.home", return_value=self.temp_home):
            import argparse

            from cortex.cli import CortexCLI

            cli = CortexCLI()
            args = argparse.Namespace(config_action="language", list=True, info=False, code=None)

            result = cli.config(args)
            self.assertEqual(result, 0)

    def test_cli_language_set(self):
        """Test CLI language set command."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            import argparse

            from cortex.cli import CortexCLI

            cli = CortexCLI()
            args = argparse.Namespace(config_action="language", list=False, info=False, code="es")

            result = cli.config(args)
            self.assertEqual(result, 0)

            # Verify language was set
            from cortex.i18n.config import LanguageConfig

            config = LanguageConfig()
            self.assertEqual(config.get_language(), "es")

    def test_cli_language_invalid(self):
        """Test CLI with invalid language code."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            import argparse

            from cortex.cli import CortexCLI

            cli = CortexCLI()
            args = argparse.Namespace(
                config_action="language", list=False, info=False, code="invalid"
            )

            result = cli.config(args)
            self.assertEqual(result, 1)

    def test_cli_language_auto(self):
        """Test CLI language auto detection."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            with patch.dict(os.environ, {}, clear=True):
                import argparse

                from cortex.cli import CortexCLI

                cli = CortexCLI()

                # First set a language
                args = argparse.Namespace(
                    config_action="language", list=False, info=False, code="de"
                )
                cli.config(args)

                # Then set to auto
                args = argparse.Namespace(
                    config_action="language", list=False, info=False, code="auto"
                )
                result = cli.config(args)
                self.assertEqual(result, 0)


class TestGlobalFunctions(unittest.TestCase):
    """Tests for global convenience functions."""

    def setUp(self):
        """Reset translator before each test."""
        from cortex.i18n.translator import reset_translator

        reset_translator()

    def tearDown(self):
        """Reset translator after each test."""
        from cortex.i18n.translator import reset_translator

        reset_translator()

    def test_format_functions(self):
        """Test global format functions."""
        from cortex.i18n.formatter import (
            format_date,
            format_datetime,
            format_duration,
            format_file_size,
            format_number,
            format_time,
        )

        dt = datetime(2024, 3, 15, 14, 30)

        self.assertIsInstance(format_date(dt), str)
        self.assertIsInstance(format_time(dt), str)
        self.assertIsInstance(format_datetime(dt), str)
        self.assertIsInstance(format_number(1234), str)
        self.assertIsInstance(format_file_size(1024), str)
        self.assertIsInstance(format_duration(60), str)


class TestResolveLanguageName(unittest.TestCase):
    """Tests for the _resolve_language_name function."""

    def test_resolve_language_code(self):
        """Test resolving language codes."""
        from cortex.cli import _resolve_language_name

        self.assertEqual(_resolve_language_name("en"), "en")
        self.assertEqual(_resolve_language_name("es"), "es")
        self.assertEqual(_resolve_language_name("fr"), "fr")
        self.assertEqual(_resolve_language_name("de"), "de")
        self.assertEqual(_resolve_language_name("zh"), "zh")

    def test_resolve_english_names(self):
        """Test resolving English language names."""
        from cortex.cli import _resolve_language_name

        self.assertEqual(_resolve_language_name("English"), "en")
        self.assertEqual(_resolve_language_name("Spanish"), "es")
        self.assertEqual(_resolve_language_name("French"), "fr")
        self.assertEqual(_resolve_language_name("German"), "de")
        self.assertEqual(_resolve_language_name("Chinese"), "zh")

    def test_resolve_native_names(self):
        """Test resolving native language names."""
        from cortex.cli import _resolve_language_name

        self.assertEqual(_resolve_language_name("Español"), "es")
        self.assertEqual(_resolve_language_name("Français"), "fr")
        self.assertEqual(_resolve_language_name("Deutsch"), "de")
        self.assertEqual(_resolve_language_name("中文"), "zh")

    def test_resolve_case_insensitive(self):
        """Test case-insensitive resolution."""
        from cortex.cli import _resolve_language_name

        self.assertEqual(_resolve_language_name("ENGLISH"), "en")
        self.assertEqual(_resolve_language_name("spanish"), "es")
        self.assertEqual(_resolve_language_name("FRENCH"), "fr")
        self.assertEqual(_resolve_language_name("german"), "de")

    def test_resolve_invalid_returns_none(self):
        """Test that invalid language names return None."""
        from cortex.cli import _resolve_language_name

        self.assertIsNone(_resolve_language_name("Japanese"))
        self.assertIsNone(_resolve_language_name("invalid"))
        self.assertIsNone(_resolve_language_name(""))

    def test_resolve_non_latin_scripts_no_collision(self):
        """Test that non-Latin scripts don't create key collisions."""
        from cortex.cli import _resolve_language_name

        # Chinese should resolve correctly
        self.assertEqual(_resolve_language_name("中文"), "zh")

        # Different non-Latin strings should not collide
        self.assertIsNone(_resolve_language_name("日本語"))  # Japanese
        self.assertIsNone(_resolve_language_name("한국어"))  # Korean

    def test_resolve_mixed_case_non_latin(self):
        """Test that non-Latin scripts are matched exactly."""
        from cortex.cli import _resolve_language_name

        # Non-Latin script should work exactly as-is
        self.assertEqual(_resolve_language_name("中文"), "zh")

    def test_resolve_with_whitespace(self):
        """Test that whitespace is handled."""
        from cortex.cli import _resolve_language_name

        self.assertEqual(_resolve_language_name("  English  "), "en")
        self.assertEqual(_resolve_language_name(" es "), "es")


class TestSetLanguageFlag(unittest.TestCase):
    """Tests for the --set-language CLI flag."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_home = Path(self.temp_dir.name)

        from cortex.i18n.translator import reset_translator

        reset_translator()

    def tearDown(self):
        """Clean up after tests."""
        self.temp_dir.cleanup()

        from cortex.i18n.translator import reset_translator

        reset_translator()

    def test_set_language_flag_with_english_name(self):
        """Test --set-language with English language name."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.cli import _handle_set_language

            result = _handle_set_language("Spanish")
            self.assertEqual(result, 0)

            from cortex.i18n import get_language

            self.assertEqual(get_language(), "es")

    def test_set_language_flag_with_native_name(self):
        """Test --set-language with native language name."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.cli import _handle_set_language

            result = _handle_set_language("Français")
            self.assertEqual(result, 0)

            from cortex.i18n import get_language

            self.assertEqual(get_language(), "fr")

    def test_set_language_flag_with_code(self):
        """Test --set-language with language code."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.cli import _handle_set_language

            result = _handle_set_language("de")
            self.assertEqual(result, 0)

            from cortex.i18n import get_language

            self.assertEqual(get_language(), "de")

    def test_set_language_flag_invalid(self):
        """Test --set-language with invalid language."""
        with patch("pathlib.Path.home", return_value=self.temp_home):
            from cortex.cli import _handle_set_language

            result = _handle_set_language("InvalidLanguage")
            self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
