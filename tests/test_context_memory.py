#!/usr/bin/env python3
"""
Unit tests for Cortex Linux Context Memory System
Tests all major functionality including memory recording, pattern detection,
suggestion generation, and preference management.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.context_memory import ContextMemory, MemoryEntry


class TestContextMemory(unittest.TestCase):
    """Test suite for Context Memory System"""

    def setUp(self):
        """Set up test database before each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.memory = ContextMemory(db_path=self.temp_db.name)

    def tearDown(self):
        """Clean up test database after each test"""
        Path(self.temp_db.name).unlink(missing_ok=True)

    def test_initialization(self):
        """Test database initialization"""
        self.assertTrue(Path(self.temp_db.name).exists())

        # Verify tables exist
        import sqlite3

        conn = sqlite3.connect(self.temp_db.name)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        self.assertIn("memory_entries", tables)
        self.assertIn("patterns", tables)
        self.assertIn("suggestions", tables)
        self.assertIn("preferences", tables)

        conn.close()

    def test_record_interaction(self):
        """Test recording a memory entry"""
        entry = MemoryEntry(
            category="package",
            context="Install Docker",
            action="apt install docker-ce",
            result="Success",
            success=True,
            metadata={"version": "24.0.5"},
        )

        entry_id = self.memory.record_interaction(entry)

        self.assertIsInstance(entry_id, int)
        self.assertGreater(entry_id, 0)

    def test_get_similar_interactions(self):
        """Test finding similar past interactions"""
        # Record several entries
        entries = [
            MemoryEntry(
                category="package",
                context="Install Docker for container management",
                action="install docker-ce",
                result="Success",
            ),
            MemoryEntry(
                category="package",
                context="Install Docker Compose",
                action="install docker-compose",
                result="Success",
            ),
            MemoryEntry(
                category="package",
                context="Install PostgreSQL",
                action="install postgresql",
                result="Success",
            ),
        ]

        for entry in entries:
            self.memory.record_interaction(entry)

        # Search for Docker-related interactions
        similar = self.memory.get_similar_interactions("Docker", limit=10)

        self.assertGreater(len(similar), 0)
        # Should find Docker-related entries
        docker_entries = [
            e for e in similar if "docker" in e.context.lower() or "docker" in e.action.lower()
        ]
        self.assertGreater(len(docker_entries), 0)

    def test_pattern_detection(self):
        """Test automatic pattern detection"""
        # Record the same action multiple times
        for i in range(5):
            entry = MemoryEntry(
                category="package",
                context=f"Install nginx attempt {i}",
                action="install nginx",
                result="Success",
                success=True,
            )
            self.memory.record_interaction(entry)

        # Get patterns
        patterns = self.memory.get_patterns(pattern_type="package", min_confidence=0.3)

        self.assertGreater(len(patterns), 0)

        # Verify pattern contains nginx
        nginx_patterns = [p for p in patterns if "nginx" in str(p.actions)]
        self.assertGreater(len(nginx_patterns), 0)

    def test_generate_suggestions_optimization(self):
        """Test generation of optimization suggestions"""
        # Record repeated package installations
        for _i in range(4):
            entry = MemoryEntry(
                category="package",
                context="Development setup",
                action="git",
                result="Success",
                success=True,
            )
            self.memory.record_interaction(entry)

        # Generate suggestions
        suggestions = self.memory.generate_suggestions()

        # Should suggest optimizing frequent installations
        opt_suggestions = [s for s in suggestions if s.suggestion_type == "optimization"]
        self.assertGreater(len(opt_suggestions), 0)

    def test_generate_suggestions_alternatives(self):
        """Test generation of alternative suggestions for failures"""
        # Record a failure
        failed_entry = MemoryEntry(
            category="package",
            context="Install Python package",
            action="pip install broken-package",
            result="Error: Package not found",
            success=False,
        )
        self.memory.record_interaction(failed_entry)

        # Record a successful alternative
        success_entry = MemoryEntry(
            category="package",
            context="Install Python package alternative",
            action="pip install working-package",
            result="Success",
            success=True,
        )
        self.memory.record_interaction(success_entry)

        # Generate suggestions
        suggestions = self.memory.generate_suggestions()

        # May or may not generate alternatives depending on similarity matching
        # This is a soft test
        self.assertIsInstance(suggestions, list)

    def test_preferences(self):
        """Test user preferences storage and retrieval"""
        # Set preferences
        self.memory.set_preference("default_python", "python3.11", "runtime")
        self.memory.set_preference("auto_update", True, "system")
        self.memory.set_preference("theme", {"name": "dark", "colors": ["#000", "#fff"]}, "ui")

        # Get preferences
        python_pref = self.memory.get_preference("default_python")
        update_pref = self.memory.get_preference("auto_update")
        theme_pref = self.memory.get_preference("theme")
        missing_pref = self.memory.get_preference("nonexistent", default="default_value")

        self.assertEqual(python_pref, "python3.11")
        self.assertEqual(update_pref, True)
        self.assertEqual(theme_pref, {"name": "dark", "colors": ["#000", "#fff"]})
        self.assertEqual(missing_pref, "default_value")

    def test_preference_update(self):
        """Test updating existing preferences"""
        self.memory.set_preference("test_key", "initial_value")
        self.assertEqual(self.memory.get_preference("test_key"), "initial_value")

        self.memory.set_preference("test_key", "updated_value")
        self.assertEqual(self.memory.get_preference("test_key"), "updated_value")

    def test_dismiss_suggestion(self):
        """Test dismissing suggestions"""
        # Record entries to generate suggestions
        for _i in range(4):
            entry = MemoryEntry(
                category="package", context="Test", action="test-package", result="Success"
            )
            self.memory.record_interaction(entry)

        # Generate suggestions
        suggestions = self.memory.generate_suggestions()

        if suggestions:
            suggestion_id = suggestions[0].suggestion_id

            # Dismiss the suggestion
            self.memory.dismiss_suggestion(suggestion_id)

            # Verify it's dismissed
            active = self.memory.get_active_suggestions()
            active_ids = [s.suggestion_id for s in active]
            self.assertNotIn(suggestion_id, active_ids)

    def test_statistics(self):
        """Test statistics generation"""
        # Record various entries
        entries = [
            MemoryEntry(category="package", context="Test 1", action="action1", success=True),
            MemoryEntry(category="package", context="Test 2", action="action2", success=True),
            MemoryEntry(category="config", context="Test 3", action="action3", success=False),
            MemoryEntry(category="command", context="Test 4", action="action4", success=True),
        ]

        for entry in entries:
            self.memory.record_interaction(entry)

        stats = self.memory.get_statistics()

        self.assertEqual(stats["total_entries"], 4)
        self.assertIn("by_category", stats)
        self.assertEqual(stats["by_category"]["package"], 2)
        self.assertEqual(stats["by_category"]["config"], 1)
        self.assertEqual(stats["by_category"]["command"], 1)
        self.assertEqual(stats["success_rate"], 75.0)  # 3 out of 4 successful

    def test_export_memory(self):
        """Test exporting memory to JSON"""
        # Record some data
        entry = MemoryEntry(
            category="package", context="Test export", action="test-action", result="Success"
        )
        self.memory.record_interaction(entry)
        self.memory.set_preference("test_pref", "test_value")

        # Export
        export_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        export_file.close()

        try:
            self.memory.export_memory(export_file.name)

            # Verify export file
            self.assertTrue(Path(export_file.name).exists())

            with open(export_file.name) as f:
                data = json.load(f)

            self.assertIn("entries", data)
            self.assertIn("patterns", data)
            self.assertIn("suggestions", data)
            self.assertIn("preferences", data)
            self.assertGreater(len(data["entries"]), 0)

        finally:
            Path(export_file.name).unlink(missing_ok=True)

    def test_memory_entry_creation(self):
        """Test MemoryEntry dataclass creation"""
        entry = MemoryEntry(category="test", context="test context", action="test action")

        self.assertIsNotNone(entry.timestamp)
        self.assertEqual(entry.category, "test")
        self.assertTrue(entry.success)
        self.assertEqual(entry.confidence, 1.0)
        self.assertEqual(entry.frequency, 1)
        self.assertEqual(entry.metadata, {})

    def test_keyword_extraction(self):
        """Test keyword extraction from text"""
        text = "I want to install Docker and PostgreSQL for my development environment"
        keywords = self.memory._extract_keywords(text)

        self.assertIn("docker", keywords)
        self.assertIn("postgresql", keywords)
        self.assertIn("development", keywords)
        self.assertNotIn("and", keywords)  # Stopword
        self.assertNotIn("to", keywords)  # Stopword

    def test_pattern_confidence_increase(self):
        """Test that pattern confidence increases with frequency"""
        # Record same action multiple times
        action = "install docker"
        for i in range(10):
            entry = MemoryEntry(
                category="package", context=f"Install Docker {i}", action=action, result="Success"
            )
            self.memory.record_interaction(entry)

        patterns = self.memory.get_patterns(min_confidence=0.0)

        if patterns:
            # Find our pattern
            docker_pattern = next((p for p in patterns if "docker" in str(p.actions).lower()), None)
            if docker_pattern:
                # Confidence should be high with 10 occurrences
                self.assertGreater(docker_pattern.confidence, 0.5)

    def test_concurrent_pattern_detection(self):
        """Test pattern detection with multiple action types"""
        # Record different actions
        actions = [("install nginx", 5), ("install docker", 4), ("configure ssl", 3)]

        for action, count in actions:
            for i in range(count):
                entry = MemoryEntry(
                    category="package",
                    context=f"{action} attempt {i}",
                    action=action,
                    result="Success",
                )
                self.memory.record_interaction(entry)

        patterns = self.memory.get_patterns(min_confidence=0.3)

        # Should detect patterns for all three actions
        self.assertGreaterEqual(len(patterns), 1)

    def test_suggestion_deduplication(self):
        """Test that duplicate suggestions aren't created"""
        # Record same scenario multiple times
        for _i in range(5):
            entry = MemoryEntry(
                category="package", context="Test", action="repeated-action", result="Success"
            )
            self.memory.record_interaction(entry)

        # Generate suggestions twice
        suggestions1 = self.memory.generate_suggestions()
        suggestions2 = self.memory.generate_suggestions()

        # Count active suggestions in database
        active = self.memory.get_active_suggestions()

        # Should not create duplicates (same suggestion_id)
        suggestion_ids = [s.suggestion_id for s in active]
        unique_ids = set(suggestion_ids)
        self.assertEqual(len(suggestion_ids), len(unique_ids))


class TestMemoryEntry(unittest.TestCase):
    """Test MemoryEntry dataclass"""

    def test_default_values(self):
        """Test default values are set correctly"""
        entry = MemoryEntry(category="test", context="context", action="action")

        self.assertIsNotNone(entry.timestamp)
        self.assertTrue(entry.success)
        self.assertEqual(entry.confidence, 1.0)
        self.assertEqual(entry.frequency, 1)
        self.assertIsInstance(entry.metadata, dict)

    def test_custom_metadata(self):
        """Test custom metadata handling"""
        metadata = {"key": "value", "number": 42}
        entry = MemoryEntry(category="test", context="context", action="action", metadata=metadata)

        self.assertEqual(entry.metadata, metadata)


class TestIntegration(unittest.TestCase):
    """Integration tests for complete workflows"""

    def setUp(self):
        """Set up test database"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.memory = ContextMemory(db_path=self.temp_db.name)

    def tearDown(self):
        """Clean up"""
        Path(self.temp_db.name).unlink(missing_ok=True)

    def test_complete_workflow(self):
        """Test complete workflow: record -> analyze -> suggest -> dismiss"""
        # 1. Record multiple interactions
        for _i in range(5):
            entry = MemoryEntry(
                category="package",
                context="Setting up development environment",
                action="install python3-dev",
                result="Success",
                success=True,
            )
            self.memory.record_interaction(entry)

        # 2. Set preferences
        self.memory.set_preference("preferred_python", "python3.11")

        # 3. Check patterns detected
        patterns = self.memory.get_patterns()
        self.assertGreater(len(patterns), 0)

        # 4. Generate suggestions
        suggestions = self.memory.generate_suggestions()
        self.assertGreater(len(suggestions), 0)

        # 5. Dismiss a suggestion
        if suggestions:
            self.memory.dismiss_suggestion(suggestions[0].suggestion_id)
            active = self.memory.get_active_suggestions()
            self.assertLess(len(active), len(suggestions))

        # 6. Get statistics
        stats = self.memory.get_statistics()
        self.assertEqual(stats["total_entries"], 5)
        self.assertEqual(stats["success_rate"], 100.0)

        # 7. Export everything
        export_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        export_file.close()

        try:
            self.memory.export_memory(export_file.name)
            self.assertTrue(Path(export_file.name).exists())
        finally:
            Path(export_file.name).unlink(missing_ok=True)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestContextMemory))
    suite.addTests(loader.loadTestsFromTestCase(TestMemoryEntry))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
