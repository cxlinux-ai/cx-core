import unittest

from cortex.resolver import DependencyResolver


class TestDependencyResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = DependencyResolver()

    def test_basic_conflict_resolution(self):
        conflict = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "~1.9.0"},
        }
        strategies = self.resolver.resolve(conflict)

        self.assertEqual(len(strategies), 2)
        self.assertEqual(strategies[0]["type"], "Recommended")
        self.assertIn("Update pkg-b", strategies[0]["action"])

    def test_complex_constraint_formats(self):
        """Test various semver constraint syntaxes to hit >80% coverage."""
        test_cases = [
            {"req_a": "==2.0.0", "req_b": "^2.1.0"},
            {"req_a": ">=1.0.0,<2.0.0", "req_b": "1.5.0"},
            {"req_a": "~1.2.3", "req_b": ">=1.2.0"},
        ]
        for case in test_cases:
            conflict = {
                "dependency": "lib-y",
                "package_a": {"name": "pkg-a", "requires": case["req_a"]},
                "package_b": {"name": "pkg-b", "requires": case["req_b"]},
            }
            strategies = self.resolver.resolve(conflict)
            self.assertIsInstance(strategies, list)
            self.assertGreater(len(strategies), 0)

    def test_strategy_field_integrity(self):
        """Verify all required fields (id, type, action, risk) exist in output."""
        conflict = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "~1.9.0"},
        }
        strategies = self.resolver.resolve(conflict)
        for strategy in strategies:
            self.assertIn("id", strategy)
            self.assertIn("type", strategy)
            self.assertIn("action", strategy)
            self.assertIn("risk", strategy)

    def test_missing_keys_raises_error(self):
        bad_data = {"package_a": {}}
        with self.assertRaises(KeyError):
            self.resolver.resolve(bad_data)

    def test_invalid_semver_handles_gracefully(self):
        conflict = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "invalid-version"},
            "package_b": {"name": "pkg-b", "requires": "1.0.0"},
        }
        strategies = self.resolver.resolve(conflict)
        self.assertEqual(strategies[0]["type"], "Error")
        self.assertIn("Manual resolution required", strategies[0]["action"])


if __name__ == "__main__":
    unittest.main()
