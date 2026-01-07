"""
Unit tests for DependencyResolver with comprehensive coverage.

Tests cover:
- Deterministic semver intersection
- AI fallback for incompatible versions
- Error handling for malformed input
- JSON parsing failures
"""

import unittest
from unittest.mock import MagicMock

from cortex.resolver import DependencyResolver


class TestDependencyResolver(unittest.IsolatedAsyncioTestCase):
    """Test suite for AI-powered dependency conflict resolution."""

    async def asyncSetUp(self):
        """Set up test fixtures before each test."""
        self.resolver = DependencyResolver(api_key="test", provider="fake")
        # Initialize the mock
        self.resolver.handler.ask = MagicMock()

    async def test_deterministic_intersection(self):
        """Test that compatible versions are resolved mathematically."""
        conflict_data = {
            "dependency": "django",
            "package_a": {"name": "app-1", "requires": ">=3.0.0"},
            "package_b": {"name": "app-2", "requires": "<4.0.0"},
        }

        self.resolver.handler.ask.reset_mock()
        strategies = await self.resolver.resolve(conflict_data)

        # Verify Low risk
        self.assertEqual(strategies[0]["risk"], "Low")
        # Verify package name is in the action
        self.assertIn("django", strategies[0]["action"])
        # Verify AI was not called
        self.assertFalse(self.resolver.handler.ask.called)

    async def test_invalid_ai_json_fallback(self):
        """Ensure fallback happens if AI returns garbage."""
        conflict_data = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "~1.9.0"},
        }
        # AI returns garbage
        self.resolver.handler.ask.return_value = "Not JSON"

        strategies = await self.resolver.resolve(conflict_data)

        # Should now be True because of our resolver.py fix
        self.assertTrue(len(strategies) >= 1)
        self.assertEqual(strategies[0]["type"], "Manual")

    async def test_ai_fallback_resolution(self):
        """Ensure AI reasoning is used when versions are incompatible."""
        conflict_data = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "~1.9.0"},
        }

        # Mock the LLM JSON response for incompatible versions
        self.resolver.handler.ask.return_value = (
            '[{"id": 1, "type": "Recommended", "action": "Use lib-x 2.0.0", "risk": "Medium"}]'
        )

        strategies = await self.resolver.resolve(conflict_data)

        self.assertEqual(len(strategies), 1)
        self.assertEqual(strategies[0]["action"], "Use lib-x 2.0.0")
        # Verify AI fallback was triggered
        self.resolver.handler.ask.assert_called_once()

    async def test_missing_keys_raises_error(self):
        """Verify KeyError is raised for malformed input data."""
        bad_data = {"dependency": "lib-x"}
        with self.assertRaises(KeyError):
            await self.resolver.resolve(bad_data)

    async def test_ai_exception_handling(self):
        """Ensure the resolver falls back to manual if AI returns bad JSON."""
        conflict_data = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "~1.9.0"},
        }
        # Simulate AI returning corrupted data
        self.resolver.handler.ask.return_value = "ERROR: SYSTEM OVERLOAD"

        strategies = await self.resolver.resolve(conflict_data)

        # Should return at least the fallback manual/deterministic strategy
        self.assertTrue(len(strategies) >= 1)
        self.assertEqual(strategies[0]["type"], "Manual")

    async def test_empty_intersection_triggers_ai(self):
        """Test that non-overlapping versions trigger AI resolution."""
        conflict_data = {
            "dependency": "pytest",
            "package_a": {"name": "test-suite", "requires": ">=8.0.0"},
            "package_b": {"name": "legacy-tests", "requires": "<7.0.0"},
        }

        # Mock AI response for completely incompatible versions
        self.resolver.handler.ask.return_value = (
            '[{"id": 1, "type": "Breaking", '
            '"action": "Use pytest 8.0.0 and update legacy-tests", '
            '"risk": "High"}]'
        )

        strategies = await self.resolver.resolve(conflict_data)

        # AI should be called
        self.assertTrue(self.resolver.handler.ask.called)

        # Should return high-risk strategy
        self.assertEqual(strategies[0]["risk"], "High")
        self.assertIn("pytest", strategies[0]["action"])

    async def test_exact_version_match(self):
        """Test resolution when both packages require exact same version."""
        conflict_data = {
            "dependency": "numpy",
            "package_a": {"name": "ml-lib", "requires": "==1.24.0"},
            "package_b": {"name": "data-lib", "requires": "==1.24.0"},
        }

        strategies = await self.resolver.resolve(conflict_data)

        # Should resolve deterministically
        self.assertEqual(strategies[0]["risk"], "Low")
        self.assertIn("1.24.0", strategies[0]["action"])
        self.assertFalse(self.resolver.handler.ask.called)

    async def test_ai_returns_multiple_strategies(self):
        """Test handling of multiple resolution strategies from AI."""
        conflict_data = {
            "dependency": "requests",
            "package_a": {"name": "api-client", "requires": "^2.28.0"},
            "package_b": {"name": "web-scraper", "requires": "~2.27.0"},
        }

        # Mock AI returning multiple strategies
        self.resolver.handler.ask.return_value = (
            "["
            '{"id": 1, "type": "Recommended", "action": "Use requests 2.28.1", "risk": "Low"},'
            '{"id": 2, "type": "Alternative", "action": "Use requests 2.27.1", "risk": "Medium"}'
            "]"
        )

        strategies = await self.resolver.resolve(conflict_data)

        # Should return both strategies
        self.assertEqual(len(strategies), 2)
        self.assertEqual(strategies[0]["risk"], "Low")
        self.assertEqual(strategies[1]["risk"], "Medium")

    async def test_whitespace_handling_in_constraints(self):
        """Test that version constraints with whitespace are handled correctly."""
        conflict_data = {
            "dependency": "django",
            "package_a": {"name": "app-1", "requires": " >=3.0.0 "},
            "package_b": {"name": "app-2", "requires": " <4.0.0 "},
        }

        strategies = await self.resolver.resolve(conflict_data)

        # This will now pass because of the .strip() and .match() logic
        self.assertEqual(strategies[0]["risk"], "Low")
        self.assertFalse(self.resolver.handler.ask.called)


if __name__ == "__main__":
    unittest.main()
