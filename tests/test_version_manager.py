"""Tests for cortex.version_manager module."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.version_manager import (
    SemanticVersion,
    UpdateChannel,
    get_current_version,
    get_version_string,
    is_compatible,
    is_newer,
)


class TestSemanticVersion(unittest.TestCase):
    """Tests for SemanticVersion class."""

    def test_parse_simple_version(self):
        """Test parsing simple version strings."""
        v = SemanticVersion.parse("1.2.3")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 2)
        self.assertEqual(v.patch, 3)
        self.assertIsNone(v.prerelease)
        self.assertIsNone(v.build)

    def test_parse_version_with_v_prefix(self):
        """Test parsing version with 'v' prefix."""
        v = SemanticVersion.parse("v1.2.3")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 2)
        self.assertEqual(v.patch, 3)

    def test_parse_prerelease_version(self):
        """Test parsing prerelease versions."""
        v = SemanticVersion.parse("1.0.0-beta.1")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 0)
        self.assertEqual(v.patch, 0)
        self.assertEqual(v.prerelease, "beta.1")

    def test_parse_version_with_build(self):
        """Test parsing version with build metadata."""
        v = SemanticVersion.parse("1.0.0+build.123")
        self.assertEqual(v.build, "build.123")

    def test_parse_full_version(self):
        """Test parsing full version with prerelease and build."""
        v = SemanticVersion.parse("1.0.0-rc.1+build.456")
        self.assertEqual(v.prerelease, "rc.1")
        self.assertEqual(v.build, "build.456")

    def test_parse_invalid_version_raises(self):
        """Test that invalid versions raise ValueError."""
        with self.assertRaises(ValueError):
            SemanticVersion.parse("not-a-version")

        with self.assertRaises(ValueError):
            SemanticVersion.parse("1.2")

        with self.assertRaises(ValueError):
            SemanticVersion.parse("1")

    def test_str_representation(self):
        """Test string representation of version."""
        v = SemanticVersion(1, 2, 3)
        self.assertEqual(str(v), "1.2.3")

        v_pre = SemanticVersion(1, 0, 0, prerelease="beta.1")
        self.assertEqual(str(v_pre), "1.0.0-beta.1")

        v_full = SemanticVersion(1, 0, 0, prerelease="rc.1", build="build.123")
        self.assertEqual(str(v_full), "1.0.0-rc.1+build.123")

    def test_equality(self):
        """Test version equality comparison."""
        v1 = SemanticVersion.parse("1.2.3")
        v2 = SemanticVersion.parse("1.2.3")
        v3 = SemanticVersion.parse("1.2.4")

        self.assertEqual(v1, v2)
        self.assertNotEqual(v1, v3)

    def test_comparison_major(self):
        """Test version comparison by major version."""
        v1 = SemanticVersion.parse("1.0.0")
        v2 = SemanticVersion.parse("2.0.0")

        self.assertTrue(v1 < v2)
        self.assertTrue(v2 > v1)

    def test_comparison_minor(self):
        """Test version comparison by minor version."""
        v1 = SemanticVersion.parse("1.1.0")
        v2 = SemanticVersion.parse("1.2.0")

        self.assertTrue(v1 < v2)

    def test_comparison_patch(self):
        """Test version comparison by patch version."""
        v1 = SemanticVersion.parse("1.0.1")
        v2 = SemanticVersion.parse("1.0.2")

        self.assertTrue(v1 < v2)

    def test_prerelease_less_than_release(self):
        """Test that prerelease versions are less than releases."""
        v_pre = SemanticVersion.parse("1.0.0-beta.1")
        v_release = SemanticVersion.parse("1.0.0")

        self.assertTrue(v_pre < v_release)

    def test_prerelease_comparison(self):
        """Test comparison between prerelease versions."""
        v1 = SemanticVersion.parse("1.0.0-alpha.1")
        v2 = SemanticVersion.parse("1.0.0-beta.1")

        self.assertTrue(v1 < v2)

        v3 = SemanticVersion.parse("1.0.0-beta.1")
        v4 = SemanticVersion.parse("1.0.0-beta.2")

        self.assertTrue(v3 < v4)

    def test_is_prerelease(self):
        """Test is_prerelease property."""
        v_release = SemanticVersion.parse("1.0.0")
        v_pre = SemanticVersion.parse("1.0.0-beta.1")

        self.assertFalse(v_release.is_prerelease)
        self.assertTrue(v_pre.is_prerelease)

    def test_channel_detection(self):
        """Test channel detection from version."""
        v_stable = SemanticVersion.parse("1.0.0")
        self.assertEqual(v_stable.channel, UpdateChannel.STABLE)

        v_beta = SemanticVersion.parse("1.0.0-beta.1")
        self.assertEqual(v_beta.channel, UpdateChannel.BETA)

        v_alpha = SemanticVersion.parse("1.0.0-alpha.1")
        self.assertEqual(v_alpha.channel, UpdateChannel.DEV)

        v_dev = SemanticVersion.parse("1.0.0-dev.1")
        self.assertEqual(v_dev.channel, UpdateChannel.DEV)


class TestVersionFunctions(unittest.TestCase):
    """Tests for version utility functions."""

    def test_get_current_version(self):
        """Test getting current version."""
        version = get_current_version()
        self.assertIsInstance(version, SemanticVersion)
        self.assertGreaterEqual(version.major, 0)

    def test_get_version_string(self):
        """Test getting version string."""
        version_str = get_version_string()
        self.assertIsInstance(version_str, str)
        # Should be parseable
        SemanticVersion.parse(version_str)

    def test_is_newer_with_newer_version(self):
        """Test is_newer with a newer version."""
        self.assertTrue(is_newer("2.0.0", "1.0.0"))
        self.assertTrue(is_newer("1.1.0", "1.0.0"))
        self.assertTrue(is_newer("1.0.1", "1.0.0"))

    def test_is_newer_with_older_version(self):
        """Test is_newer with an older version."""
        self.assertFalse(is_newer("1.0.0", "2.0.0"))
        self.assertFalse(is_newer("1.0.0", "1.0.0"))

    def test_is_newer_with_semantic_version(self):
        """Test is_newer with SemanticVersion objects."""
        v1 = SemanticVersion.parse("2.0.0")
        v2 = SemanticVersion.parse("1.0.0")
        self.assertTrue(is_newer(v1, v2))

    def test_is_compatible(self):
        """Test is_compatible function."""
        self.assertTrue(is_compatible("1.0.0", "0.1.0"))
        self.assertTrue(is_compatible("1.0.0", "1.0.0"))
        self.assertFalse(is_compatible("0.0.9", "1.0.0"))


if __name__ == "__main__":
    unittest.main()
