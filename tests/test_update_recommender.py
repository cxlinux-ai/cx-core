#!/usr/bin/env python3
"""
Unit tests for the Smart Update Recommender.
Validates version parsing, risk scoring, and categorization logic.
"""

import json
import re
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from cortex.update_recommender import (
    ChangeType,
    PackageVersion,
    RiskLevel,
    UpdateCategory,
    UpdateInfo,
    UpdateRecommendation,
    UpdateRecommender,
    recommend_updates,
)


class TestPackageVersion:
    @pytest.mark.parametrize(
        "version_str, expected",
        [
            ("1.2.3", (1, 2, 3, 0, "")),
            ("v2.0.0", (2, 0, 0, 0, "")),
            ("1:2.3.4", (2, 3, 4, 1, "")),
            ("2.0.0-beta1", (2, 0, 0, 0, "-beta1")),
            ("", (0, 0, 0, 0, "")),
            (None, (0, 0, 0, 0, "")),
            ("1.1.1f", (1, 1, 1, 0, "")),
            ("abc:1.2.3", (1, 2, 3, 0, "")),  # Invalid epoch
            ("1.2", (1, 2, 0, 0, "")),
            ("1", (1, 0, 0, 0, "")),
            ("1.2.3~rc1", (1, 2, 3, 0, "~rc1")),
        ],
    )
    def test_parse(self, version_str, expected):
        v = PackageVersion.parse(version_str)
        assert (v.major, v.minor, v.patch, v.epoch) == expected[:4]
        if expected[4]:
            assert expected[4].lower() in v.prerelease.lower()

    def test_comparisons(self):
        v1 = PackageVersion.parse("1.2.3")
        v2 = PackageVersion.parse("1.2.4")
        v3 = PackageVersion.parse("1.3.0")
        v4 = PackageVersion.parse("2.0.0")
        v5 = PackageVersion.parse("1:1.0.0")
        v6 = PackageVersion.parse("1.2.3-beta")

        assert v1 < v2
        assert v2 < v3
        assert v3 < v4
        assert v4 < v5
        assert v6 < v1  # Pre-release is less than final
        assert v1 >= v6
        assert v1 == PackageVersion.parse("1.2.3")
        assert str(v1) == "1.2.3"


class TestUpdateRecommender:
    @pytest.fixture
    def r(self):
        return UpdateRecommender(verbose=True)

    def test_enums_and_groups(self, r):
        assert RiskLevel.LOW.value_str == "low"
        assert r.get_package_group("python3-dev") == "python"
        assert r.get_package_group("nginx") == "nginx"
        assert r.get_package_group("unknown-pkg") == ""

    @pytest.mark.parametrize(
        "curr, new, expected",
        [
            ("1.0.0", "2.0.0", ChangeType.MAJOR),
            ("1.0.0", "1.1.0", ChangeType.MINOR),
            ("1.0.0", "1.0.1", ChangeType.PATCH),
            ("1.1.1", "1.1.1f", ChangeType.PATCH),
            ("1.0.0", "1.0.0", ChangeType.UNKNOWN),
        ],
    )
    def test_change_analysis(self, r, curr, new, expected):
        assert (
            r.analyze_change_type(PackageVersion.parse(curr), PackageVersion.parse(new)) == expected
        )

    @patch("cortex.update_recommender.subprocess.run")
    def test_get_package_metadata(self, mock_run, r):
        # Test APT success path
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="Description: A test package\n Full description here."),
            MagicMock(returncode=0, stdout="* v1.1.0: fixed security hole\n" + "* line\n" * 250),
        ]
        desc, changelog = r._get_package_metadata("test-pkg")
        assert "A test package" in desc
        assert "fixed security hole" in changelog
        assert len(changelog.splitlines()) <= 200  # Truncation check
        assert mock_run.call_args_list[0][0][0] == ["apt-cache", "show", "test-pkg"]
        assert mock_run.call_args_list[1][0][0] == ["apt-get", "changelog", "test-pkg"]

        mock_run.reset_mock()
        # Test DNF success path (APT fails)
        mock_run.side_effect = [
            MagicMock(returncode=1),  # apt-cache show fail
            MagicMock(returncode=0, stdout="Description  : A DNF test package"),
            MagicMock(returncode=0, stdout="* Mon Jan 01 2024 User - 1.0.1-1\n- Breaking change"),
        ]
        desc, changelog = r._get_package_metadata("test-pkg")
        assert "A DNF test package" in desc
        assert "Breaking change" in changelog
        assert mock_run.call_args_list[1][0][0] == ["dnf", "info", "-q", "test-pkg"]
        assert mock_run.call_args_list[2][0][0] == ["dnf", "repoquery", "--changelog", "test-pkg"]

        mock_run.reset_mock()
        # Test YUM fallback path (APT and DNF fail)
        mock_run.side_effect = [
            MagicMock(returncode=1),  # apt-cache show fail
            MagicMock(returncode=1),  # dnf info fail
            MagicMock(returncode=0, stdout="Description  : A YUM test package"),
            MagicMock(returncode=0, stdout="* Mon Jan 01 2024 User - 1.0.1-1\n- Breaking change"),
        ]
        desc, changelog = r._get_package_metadata("test-pkg")
        assert "A YUM test package" in desc
        assert "Breaking change" in changelog
        assert mock_run.call_args_list[2][0][0] == ["yum", "info", "-q", "test-pkg"]
        assert mock_run.call_args_list[3][0][0] == ["yum", "repoquery", "--changelog", "test-pkg"]

    def test_risk_assessment_branches(self, r):
        # High risk package + major version
        risk, warns = r.assess_risk(
            "linux-image-generic", PackageVersion.parse("5.15"), PackageVersion.parse("6.0")
        )
        assert risk == RiskLevel.HIGH
        assert any("Kernel" in w for w in warns)

        # Pre-release risk
        risk, warns = r.assess_risk(
            "some-pkg", PackageVersion.parse("1.0"), PackageVersion.parse("1.1-beta")
        )
        assert risk == RiskLevel.HIGH

        # Changelog keywords
        risk, warns = r.assess_risk(
            "some-pkg",
            PackageVersion.parse("1.0"),
            PackageVersion.parse("1.0.1"),
            "Breaking change and deprecated",
        )
        assert risk == RiskLevel.HIGH

    def test_security_detection(self, r):
        assert r.is_security_update("pkg", "High CVE-2024-0001 fix")
        assert r.is_security_update("pkg", "bug fixes", "security patch")
        assert not r.is_security_update("some-pkg", "random update")

    def test_categorization_matrix(self, r):
        tests = [
            (RiskLevel.LOW, True, ChangeType.PATCH, UpdateCategory.SECURITY),
            (RiskLevel.LOW, False, ChangeType.PATCH, UpdateCategory.IMMEDIATE),
            (RiskLevel.LOW, False, ChangeType.MINOR, UpdateCategory.IMMEDIATE),
            (RiskLevel.MEDIUM, False, ChangeType.MINOR, UpdateCategory.SCHEDULED),
            (RiskLevel.HIGH, False, ChangeType.MINOR, UpdateCategory.DEFERRED),
            (RiskLevel.LOW, False, ChangeType.MAJOR, UpdateCategory.DEFERRED),
            (RiskLevel.LOW, False, ChangeType.UNKNOWN, UpdateCategory.SCHEDULED),
        ]
        for risk, sec, ctype, expected in tests:
            assert r.categorize_update(risk, sec, ctype) == expected

    def test_recommendation_text_branches(self, r):
        # Security updates should highlight urgent priority
        u = UpdateInfo(
            "p",
            PackageVersion.parse("1"),
            PackageVersion.parse("2"),
            ChangeType.PATCH,
            RiskLevel.LOW,
            UpdateCategory.SECURITY,
            is_security=True,
        )
        assert "Security update" in r.generate_recommendation_text(u)

        # Major upgrades should flag potential breaking changes
        u = UpdateInfo(
            "p",
            PackageVersion.parse("1"),
            PackageVersion.parse("2"),
            ChangeType.MAJOR,
            RiskLevel.HIGH,
            UpdateCategory.DEFERRED,
            breaking_changes=["broken"],
        )
        assert "Potential breaking" in r.generate_recommendation_text(u)

        # Grouped updates should mention their parent category
        u = UpdateInfo(
            "p",
            PackageVersion.parse("1"),
            PackageVersion.parse("2"),
            ChangeType.MINOR,
            RiskLevel.MEDIUM,
            UpdateCategory.SCHEDULED,
            group="python",
        )
        assert "part of python" in r.generate_recommendation_text(u).lower()

    @patch("cortex.update_recommender.shutil.which")
    @patch("cortex.update_recommender.subprocess.run")
    def test_pkg_manager_interactions(self, mock_run, mock_which, r):
        mock_which.return_value = True  # Default to APT present
        # Verify DPKG version parsing (Debian/Ubuntu)
        mock_run.return_value = MagicMock(returncode=0, stdout="pkg1 1.0\npkg2 2.0")
        pkgs = r.get_installed_packages()
        assert "pkg1" in pkgs

        # Verify RPM version parsing fallback (Fedora/RHEL)
        mock_run.side_effect = [MagicMock(returncode=1), MagicMock(returncode=0, stdout="pkg3 3.0")]
        pkgs = r.get_installed_packages()
        assert "pkg3" in pkgs

        # Simulate APT upgradable list output
        mock_run.side_effect = [
            MagicMock(returncode=0),  # apt-get update
            MagicMock(returncode=0, stdout="nginx/jammy 1.25.0 amd64 [upgradable from: 1.24.0]"),
        ]
        updates = r.get_available_updates()
        assert len(updates) == 1
        assert updates[0]["name"] == "nginx"
        assert updates[0]["old_version"] == "1.24.0"
        assert updates[0]["new_version"] == "1.25.0"
        assert "jammy" in updates[0]["repo"]

        # Simulate DNF check-update (exit 100 indicates available updates)
        mock_which.return_value = False  # Simulate APT not present
        mock_run.side_effect = [
            MagicMock(
                returncode=100,
                stdout="Last metadata expiration check: 1:00:00 ago\ncurl.x86_64 8.5.0 updates",
            ),  # dnf check-update
            MagicMock(returncode=0, stdout="Version : 8.4.0"),  # dnf info
        ]
        updates = r.get_available_updates()
        assert len(updates) == 1 and updates[0]["name"] == "curl"

        # Handle command timeout or missing manager scenarios
        mock_run.side_effect = subprocess.TimeoutExpired(["cmd"], 30)
        assert r._run_pkg_cmd(["cmd"]) is None

    @patch.object(UpdateRecommender, "_get_package_metadata")
    @patch.object(UpdateRecommender, "get_available_updates")
    def test_get_recommendations_full(self, mock_get, mock_meta, r):
        mock_get.return_value = [
            {"name": "nginx", "old_version": "1.24.0", "new_version": "1.25.0", "repo": "updates"},
            {"name": "postgresql", "old_version": "14.0", "new_version": "15.0", "repo": "updates"},
        ]
        mock_meta.return_value = ("desc", "changelog")
        rec = r.get_recommendations(use_llm=False)
        assert rec.total_updates == 2
        assert rec.overall_risk == RiskLevel.HIGH

        # Verify LLM analysis integration
        mock_router = MagicMock()
        mock_router.complete.return_value = MagicMock(content="AI analysis")
        r.llm_router = mock_router
        with patch.dict("sys.modules", {"cortex.llm_router": MagicMock(TaskType=MagicMock())}):
            rec = r.get_recommendations(use_llm=True)
            assert rec.llm_analysis == "AI analysis"

            # Ensure robustness if LLM provider returns an error
            mock_router.complete.side_effect = Exception("error")
            assert r.analyze_with_llm(rec.immediate_updates) == ""

    def test_display_logic(self, r, capsys):
        # Create a sample recommendation with mixed risk levels
        u1 = UpdateInfo(
            "p1",
            PackageVersion.parse("1"),
            PackageVersion.parse("2"),
            ChangeType.PATCH,
            RiskLevel.LOW,
            UpdateCategory.SECURITY,
            is_security=True,
        )
        u2 = UpdateInfo(
            "p2",
            PackageVersion.parse("1"),
            PackageVersion.parse("1.1"),
            ChangeType.MINOR,
            RiskLevel.LOW,
            UpdateCategory.IMMEDIATE,
        )
        u3 = UpdateInfo(
            "p3",
            PackageVersion.parse("1"),
            PackageVersion.parse("1.2"),
            ChangeType.MINOR,
            RiskLevel.MEDIUM,
            UpdateCategory.SCHEDULED,
        )
        u4 = UpdateInfo(
            "p4",
            PackageVersion.parse("1"),
            PackageVersion.parse("2"),
            ChangeType.MAJOR,
            RiskLevel.HIGH,
            UpdateCategory.DEFERRED,
            group="db",
        )

        rec = UpdateRecommendation(
            "now",
            4,
            immediate_updates=[u2],
            scheduled_updates=[u3],
            deferred_updates=[u4],
            security_updates=[u1],
            groups={"db": [u4]},
            overall_risk=RiskLevel.HIGH,
        )

        r.display_recommendations(rec)
        out = capsys.readouterr().out
        assert "Update Analysis" in out
        assert "Security Updates" in out
        assert "Hold for Now" in out

        # Verify table truncation logic for large update lists
        updates = [u2] * 12
        r._display_update_table(updates)
        out = capsys.readouterr().out
        assert "more" in out.lower()

        # Ensure clean output for healthy systems
        r.display_recommendations(UpdateRecommendation("now", 0))
        assert "up to date" in capsys.readouterr().out.lower()


@patch("cortex.update_recommender.UpdateRecommender")
def test_convenience_function(mock_class):
    mock_instance = mock_class.return_value
    mock_instance.get_recommendations.return_value = UpdateRecommendation("now", 0)
    assert recommend_updates() == 0

    # Error path
    mock_class.side_effect = Exception("error")
    assert recommend_updates(verbose=True) == 1
