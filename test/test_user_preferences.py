#!/usr/bin/env python3
"""
Comprehensive tests for User Preferences & Settings System
Tests all preference categories, validation, import/export, and persistence
"""

import unittest
import tempfile
import shutil
import json
from pathlib import Path
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cortex.user_preferences import (
    PreferencesManager,
    UserPreferences,
    VerbosityLevel,
    AICreativity,
    ConfirmationSettings,
    AutoUpdateSettings,
    AISettings,
    PackageSettings,
    format_preference_value,
    print_all_preferences
)


class TestUserPreferences(unittest.TestCase):
    """Test UserPreferences dataclass"""
    
    def test_default_initialization(self):
        """Test default values"""
        prefs = UserPreferences()
        self.assertEqual(prefs.verbosity, VerbosityLevel.NORMAL)
        self.assertTrue(prefs.confirmations.before_install)
        self.assertEqual(prefs.ai.model, "claude-sonnet-4")
        self.assertEqual(prefs.theme, "default")
    
    def test_custom_initialization(self):
        """Test custom initialization"""
        prefs = UserPreferences(
            verbosity=VerbosityLevel.VERBOSE,
            theme="dark",
            language="es"
        )
        self.assertEqual(prefs.verbosity, VerbosityLevel.VERBOSE)
        self.assertEqual(prefs.theme, "dark")
        self.assertEqual(prefs.language, "es")


class TestConfirmationSettings(unittest.TestCase):
    """Test ConfirmationSettings"""
    
    def test_defaults(self):
        """Test default confirmation settings"""
        settings = ConfirmationSettings()
        self.assertTrue(settings.before_install)
        self.assertTrue(settings.before_remove)
        self.assertFalse(settings.before_upgrade)
        self.assertTrue(settings.before_system_changes)
    
    def test_custom_values(self):
        """Test custom confirmation settings"""
        settings = ConfirmationSettings(
            before_install=False,
            before_upgrade=True
        )
        self.assertFalse(settings.before_install)
        self.assertTrue(settings.before_upgrade)


class TestAutoUpdateSettings(unittest.TestCase):
    """Test AutoUpdateSettings"""
    
    def test_defaults(self):
        """Test default auto-update settings"""
        settings = AutoUpdateSettings()
        self.assertTrue(settings.check_on_start)
        self.assertFalse(settings.auto_install)
        self.assertEqual(settings.frequency_hours, 24)
    
    def test_custom_frequency(self):
        """Test custom update frequency"""
        settings = AutoUpdateSettings(frequency_hours=12)
        self.assertEqual(settings.frequency_hours, 12)


class TestAISettings(unittest.TestCase):
    """Test AISettings"""
    
    def test_defaults(self):
        """Test default AI settings"""
        settings = AISettings()
        self.assertEqual(settings.model, "claude-sonnet-4")
        self.assertEqual(settings.creativity, AICreativity.BALANCED)
        self.assertTrue(settings.explain_steps)
        self.assertTrue(settings.suggest_alternatives)
        self.assertTrue(settings.learn_from_history)
        self.assertEqual(settings.max_suggestions, 5)
    
    def test_custom_creativity(self):
        """Test custom creativity levels"""
        conservative = AISettings(creativity=AICreativity.CONSERVATIVE)
        self.assertEqual(conservative.creativity, AICreativity.CONSERVATIVE)
        
        creative = AISettings(creativity=AICreativity.CREATIVE)
        self.assertEqual(creative.creativity, AICreativity.CREATIVE)
    
    def test_custom_model(self):
        """Test custom AI model"""
        settings = AISettings(model="gpt-4")
        self.assertEqual(settings.model, "gpt-4")


class TestPackageSettings(unittest.TestCase):
    """Test PackageSettings"""
    
    def test_defaults(self):
        """Test default package settings"""
        settings = PackageSettings()
        self.assertEqual(settings.default_sources, ["official"])
        self.assertFalse(settings.prefer_latest)
        self.assertTrue(settings.auto_cleanup)
        self.assertTrue(settings.backup_before_changes)
    
    def test_custom_sources(self):
        """Test custom package sources"""
        settings = PackageSettings(default_sources=["official", "testing"])
        self.assertEqual(len(settings.default_sources), 2)
        self.assertIn("testing", settings.default_sources)


class TestPreferencesManager(unittest.TestCase):
    """Test PreferencesManager functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_preferences.yaml"
        self.manager = PreferencesManager(config_path=self.config_file)
    
    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_initialization(self):
        """Test manager initialization"""
        self.assertIsNotNone(self.manager.preferences)
        self.assertEqual(self.manager.config_path, self.config_file)
    
    def test_save_and_load(self):
        """Test saving and loading preferences"""
        # Modify preferences
        self.manager.set('verbosity', 'verbose')
        self.manager.set('ai.model', 'gpt-4')
        
        # Create new manager with same config file
        new_manager = PreferencesManager(config_path=self.config_file)
        
        # Verify values persisted
        self.assertEqual(new_manager.get('verbosity'), VerbosityLevel.VERBOSE)
        self.assertEqual(new_manager.get('ai.model'), 'gpt-4')
    
    def test_get_nested_value(self):
        """Test getting nested preference values"""
        self.assertEqual(self.manager.get('ai.model'), 'claude-sonnet-4')
        self.assertTrue(self.manager.get('confirmations.before_install'))
        self.assertEqual(self.manager.get('auto_update.frequency_hours'), 24)
    
    def test_get_with_default(self):
        """Test getting value with default"""
        self.assertEqual(self.manager.get('nonexistent.key', 'default'), 'default')
    
    def test_set_simple_value(self):
        """Test setting simple values"""
        self.manager.set('theme', 'dark')
        self.assertEqual(self.manager.get('theme'), 'dark')
    
    def test_set_nested_value(self):
        """Test setting nested values"""
        self.manager.set('ai.model', 'gpt-4-turbo')
        self.assertEqual(self.manager.get('ai.model'), 'gpt-4-turbo')
        
        self.manager.set('confirmations.before_install', False)
        self.assertFalse(self.manager.get('confirmations.before_install'))
    
    def test_set_boolean_coercion(self):
        """Test boolean value coercion"""
        self.manager.set('confirmations.before_install', 'true')
        self.assertTrue(self.manager.get('confirmations.before_install'))
        
        self.manager.set('confirmations.before_remove', 'false')
        self.assertFalse(self.manager.get('confirmations.before_remove'))
    
    def test_set_integer_coercion(self):
        """Test integer value coercion"""
        self.manager.set('auto_update.frequency_hours', '48')
        self.assertEqual(self.manager.get('auto_update.frequency_hours'), 48)
    
    def test_set_list_coercion(self):
        """Test list value coercion"""
        self.manager.set('packages.default_sources', 'official, testing, experimental')
        sources = self.manager.get('packages.default_sources')
        self.assertEqual(len(sources), 3)
        self.assertIn('testing', sources)
    
    def test_set_enum_coercion(self):
        """Test enum value coercion"""
        self.manager.set('verbosity', 'debug')
        self.assertEqual(self.manager.get('verbosity'), VerbosityLevel.DEBUG)
        
        self.manager.set('ai.creativity', 'creative')
        self.assertEqual(self.manager.get('ai.creativity'), AICreativity.CREATIVE)
    
    def test_reset_preferences(self):
        """Test resetting to defaults"""
        # Modify preferences
        self.manager.set('verbosity', 'debug')
        self.manager.set('theme', 'custom')
        
        # Reset
        self.manager.reset()
        
        # Verify defaults restored
        self.assertEqual(self.manager.get('verbosity'), VerbosityLevel.NORMAL)
        self.assertEqual(self.manager.get('theme'), 'default')
    
    def test_validation_success(self):
        """Test successful validation"""
        errors = self.manager.validate()
        self.assertEqual(len(errors), 0)
    
    def test_validation_max_suggestions_too_low(self):
        """Test validation with max_suggestions too low"""
        self.manager.preferences.ai.max_suggestions = 0
        errors = self.manager.validate()
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('max_suggestions' in e for e in errors))
    
    def test_validation_max_suggestions_too_high(self):
        """Test validation with max_suggestions too high"""
        self.manager.preferences.ai.max_suggestions = 25
        errors = self.manager.validate()
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('max_suggestions' in e for e in errors))
    
    def test_validation_frequency_hours(self):
        """Test validation with invalid frequency_hours"""
        self.manager.preferences.auto_update.frequency_hours = 0
        errors = self.manager.validate()
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('frequency_hours' in e for e in errors))
    
    def test_validation_invalid_language(self):
        """Test validation with invalid language"""
        self.manager.preferences.language = 'invalid'
        errors = self.manager.validate()
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('language' in e for e in errors))
    
    def test_export_json(self):
        """Test exporting to JSON"""
        export_file = Path(self.temp_dir) / "export.json"
        
        # Set some values
        self.manager.set('verbosity', 'verbose')
        self.manager.set('theme', 'dark')
        
        # Export
        self.manager.export_json(export_file)
        
        # Verify file exists and contains data
        self.assertTrue(export_file.exists())
        with open(export_file, 'r') as f:
            data = json.load(f)
        
        self.assertEqual(data['verbosity'], 'verbose')
        self.assertEqual(data['theme'], 'dark')
        self.assertIn('exported_at', data)
    
    def test_import_json(self):
        """Test importing from JSON"""
        import_file = Path(self.temp_dir) / "import.json"
        
        # Create import data
        data = {
            'verbosity': 'debug',
            'theme': 'imported',
            'language': 'es',
            'confirmations': {
                'before_install': False,
                'before_remove': True,
                'before_upgrade': True,
                'before_system_changes': False
            },
            'ai': {
                'model': 'imported-model',
                'creativity': 'creative',
                'explain_steps': False,
                'suggest_alternatives': False,
                'learn_from_history': False,
                'max_suggestions': 10
            }
        }
        
        with open(import_file, 'w') as f:
            json.dump(data, f)
        
        # Import
        self.manager.import_json(import_file)
        
        # Verify imported values
        self.assertEqual(self.manager.get('verbosity'), VerbosityLevel.DEBUG)
        self.assertEqual(self.manager.get('theme'), 'imported')
        self.assertEqual(self.manager.get('language'), 'es')
        self.assertFalse(self.manager.get('confirmations.before_install'))
        self.assertTrue(self.manager.get('confirmations.before_upgrade'))
        self.assertEqual(self.manager.get('ai.model'), 'imported-model')
        self.assertEqual(self.manager.get('ai.creativity'), AICreativity.CREATIVE)
    
    def test_get_all_settings(self):
        """Test retrieving all settings"""
        settings = self.manager.get_all_settings()
        
        self.assertIn('verbosity', settings)
        self.assertIn('confirmations', settings)
        self.assertIn('auto_update', settings)
        self.assertIn('ai', settings)
        self.assertIn('packages', settings)
        self.assertIn('theme', settings)
    
    def test_get_config_info(self):
        """Test getting config metadata"""
        info = self.manager.get_config_info()
        
        self.assertIn('config_path', info)
        self.assertIn('config_exists', info)
        self.assertIn('config_size_bytes', info)
        self.assertTrue(info['config_exists'])
        self.assertGreater(info['config_size_bytes'], 0)
    
    def test_backup_creation(self):
        """Test that backups are created"""
        # Save initial config
        self.manager.save()
        
        # Modify and save again
        self.manager.set('theme', 'modified')
        
        # Check for backup file
        backup_file = self.config_file.with_suffix('.yaml.bak')
        self.assertTrue(backup_file.exists())
    
    def test_atomic_write(self):
        """Test atomic write behavior"""
        # This is implicit in the save() method
        # Just verify that after saving, no .tmp file remains
        self.manager.set('theme', 'test-value')
        
        temp_file = self.config_file.with_suffix('.yaml.tmp')
        self.assertFalse(temp_file.exists())


class TestFormatters(unittest.TestCase):
    """Test formatting helper functions"""
    
    def test_format_bool(self):
        """Test boolean formatting"""
        self.assertEqual(format_preference_value(True), "true")
        self.assertEqual(format_preference_value(False), "false")
    
    def test_format_enum(self):
        """Test enum formatting"""
        self.assertEqual(format_preference_value(VerbosityLevel.VERBOSE), "verbose")
        self.assertEqual(format_preference_value(AICreativity.BALANCED), "balanced")
    
    def test_format_list(self):
        """Test list formatting"""
        result = format_preference_value(['a', 'b', 'c'])
        self.assertEqual(result, "a, b, c")
    
    def test_format_string(self):
        """Test string formatting"""
        self.assertEqual(format_preference_value("test"), "test")


class TestEnums(unittest.TestCase):
    """Test enum definitions"""
    
    def test_verbosity_levels(self):
        """Test verbosity level enum"""
        self.assertEqual(VerbosityLevel.QUIET.value, "quiet")
        self.assertEqual(VerbosityLevel.NORMAL.value, "normal")
        self.assertEqual(VerbosityLevel.VERBOSE.value, "verbose")
        self.assertEqual(VerbosityLevel.DEBUG.value, "debug")
    
    def test_ai_creativity(self):
        """Test AI creativity enum"""
        self.assertEqual(AICreativity.CONSERVATIVE.value, "conservative")
        self.assertEqual(AICreativity.BALANCED.value, "balanced")
        self.assertEqual(AICreativity.CREATIVE.value, "creative")


if __name__ == '__main__':
    # Run tests with verbosity
    unittest.main(verbosity=2)
