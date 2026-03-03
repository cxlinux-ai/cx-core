import unittest
from unittest.mock import patch

from cx.dependency_conflict_predictor import (
    _version_satisfies_constraint,
    inspect_apt_package,
    inspect_pip_requirements,
    predict_conflicts,
)


class TestDependencyConflictPredictor(unittest.TestCase):
    def test_version_constraint_helper(self):
        self.assertTrue(_version_satisfies_constraint("1.2.3", ">=1.0,<2.0"))
        self.assertFalse(_version_satisfies_constraint("2.1.0", ">=1.0,<2.0"))
        self.assertTrue(_version_satisfies_constraint("1.2.3", "==1.2.3"))

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
        class FakeDist:
            def __init__(self, name, version, requires=None):
                self.metadata = {"Name": name}
                self.version = version
                self.requires = requires or []

        mock_distributions.return_value = [
            FakeDist("requests", "2.28.0", ["urllib3>=1.25,<1.27"]),
            FakeDist("urllib3", "1.26.6", []),
        ]

        findings = inspect_pip_requirements(["urllib3==2.1.0"])
        issues = {f.issue for f in findings}
        self.assertIn("installed-version-violates-requested-constraint", issues)

    @patch("importlib.metadata.distributions")
    def test_predict_conflicts_includes_suggestions(self, mock_distributions):
        class FakeDist:
            def __init__(self, name, version, requires=None):
                self.metadata = {"Name": name}
                self.version = version
                self.requires = requires or []

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


if __name__ == "__main__":
    unittest.main()
