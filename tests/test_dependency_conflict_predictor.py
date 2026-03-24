"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.

Regression tests for the dependency conflict predictor.
"""

import unittest
from unittest.mock import patch

from cx.dependency_conflict_predictor import (
    ConflictFinding,
    _version_satisfies_constraint,
    inspect_apt_package,
    inspect_pip_requirements,
    predict_conflicts,
    rank_suggestions,
)


class FakeDist:
    def __init__(self, name, version, requires=None):
        self.metadata = {"Name": name}
        self.version = version
        self.requires = requires or []


class TestDependencyConflictPredictor(unittest.TestCase):
    def test_version_constraint_helper(self):
        self.assertTrue(_version_satisfies_constraint("1.2.3", ">=1.0,<2.0"))
        self.assertFalse(_version_satisfies_constraint("2.1.0", ">=1.0,<2.0"))
        self.assertTrue(_version_satisfies_constraint("1.2.3", "==1.2.3"))
        self.assertTrue(_version_satisfies_constraint("1.0a1", "==1.0a1"))
        self.assertTrue(_version_satisfies_constraint("1.2.3", ""))
        self.assertTrue(_version_satisfies_constraint("1.2.3", "!=2.0.0"))
        self.assertFalse(_version_satisfies_constraint("1.2.3", ">>2.0.0"))

    def test_apt_conflict_detection(self):
        installed = {"libssl1.1": "1.1.1", "bash": "5.2"}

        def fake_run(cmd):
            if cmd[:2] == ["apt-cache", "show"]:
                return """Package: demo-app
Depends: libc6, python3
Conflicts: libssl1.1
Breaks: old-demo
"""
            return ""

        findings = inspect_apt_package("demo-app", installed=installed, run_cmd=fake_run)
        issues = {f.issue for f in findings}
        self.assertIn("conflicts-installed-package", issues)

    def test_apt_conflict_detection_with_continuation_lines(self):
        installed = {"libssl1.1": "1.1.1", "legacy-lib": "2.0", "bash": "5.2"}

        def fake_run(cmd):
            if cmd[:2] == ["apt-cache", "show"]:
                return """Package: demo-app
Depends: libc6,
 python3,
 bash
Conflicts: old-lib,
 libssl1.1
Breaks: unused-lib,
 legacy-lib
"""
            return ""

        findings = inspect_apt_package("demo-app", installed=installed, run_cmd=fake_run)
        issues = {f.issue for f in findings}
        evidence = "\n".join(f.evidence for f in findings)

        self.assertIn("conflicts-installed-package", issues)
        self.assertIn("breaks-installed-package", issues)
        self.assertIn("libssl1.1", evidence)
        self.assertIn("legacy-lib", evidence)

    def test_apt_package_not_found(self):
        findings = inspect_apt_package(
            "missing-app",
            installed={},
            run_cmd=lambda _cmd: "",
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].issue, "package-not-found")

    @patch("importlib.metadata.distributions")
    def test_pip_conflict_detection(self, mock_distributions):
        mock_distributions.return_value = [
            FakeDist("requests", "2.28.0", ["urllib3>=1.25,<1.27"]),
            FakeDist("urllib3", "1.26.6", []),
        ]

        findings = inspect_pip_requirements(["urllib3==2.1.0"])
        issues = {f.issue for f in findings}
        self.assertIn("installed-version-violates-requested-constraint", issues)

    @patch("importlib.metadata.distributions")
    def test_pip_reports_unsupported_constraints(self, mock_distributions):
        mock_distributions.return_value = [FakeDist("urllib3", "1.26.6", [])]

        findings = inspect_pip_requirements(["urllib3=>1.26"])
        issues = {f.issue for f in findings}
        evidence = "\n".join(f.evidence for f in findings)

        self.assertIn("unsupported-constraint", issues)
        self.assertIn("=>1.26", evidence)

    @patch("importlib.metadata.distributions")
    def test_predict_conflicts_includes_suggestions(self, mock_distributions):
        mock_distributions.return_value = [FakeDist("urllib3", "1.26.6", [])]

        def fake_run(cmd):
            if cmd[0] == "dpkg-query":
                return "bash\t5.2\n"
            if cmd[:2] == ["apt-cache", "show"]:
                return "Package: demo\nDepends: bash\n"
            return ""

        result = predict_conflicts(
            apt_packages=["demo"],
            pip_requirements=["urllib3==2.0.0"],
            run_cmd=fake_run,
        )
        self.assertGreaterEqual(len(result.suggestions), 1)
        self.assertGreaterEqual(result.overall_confidence, 0.5)
        self.assertTrue(all(f.issue != "unsupported-constraint" for f in result.findings))

    @patch("importlib.metadata.distributions")
    def test_pip_reports_multiple_reverse_dependency_risks_per_distribution(self, mock_distributions):
        mock_distributions.return_value = [
            FakeDist(
                "service-a",
                "1.0.0",
                ["urllib3<2.0", "requests<2.30"],
            ),
            FakeDist("urllib3", "1.26.6", []),
            FakeDist("requests", "2.28.0", []),
        ]

        findings = inspect_pip_requirements(["urllib3==2.1.0", "requests==2.31.0"])
        reverse_dependency_findings = [
            finding for finding in findings if finding.issue == "reverse-dependency-constraint-risk"
        ]

        self.assertEqual(len(reverse_dependency_findings), 2)
        self.assertEqual({finding.package for finding in reverse_dependency_findings}, {"urllib3", "requests"})

    def test_rank_suggestions_preserves_descending_safety_order(self):
        findings = [
            ConflictFinding(
                ecosystem="apt",
                package="demo-app",
                issue="conflicts-installed-package",
                confidence=0.95,
                evidence="demo-app conflicts with installed package libssl1.1",
            )
        ]
        suggestions = rank_suggestions(findings)
        self.assertGreater(len(suggestions), 1)
        self.assertEqual(
            [suggestion.safety_score for suggestion in suggestions],
            sorted((suggestion.safety_score for suggestion in suggestions), reverse=True),
        )


if __name__ == "__main__":
    unittest.main()
