"""
Tests for System Health Score and Recommendations

Issue: #128 - System Health Score and Recommendations
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.health_score import (
    HealthCategory,
    HealthChecker,
    HealthFactor,
    HealthReport,
    HealthStatus,
    run_health_check,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self):
        """Test all status values are defined."""
        assert HealthStatus.EXCELLENT.value == "excellent"
        assert HealthStatus.GOOD.value == "good"
        assert HealthStatus.FAIR.value == "fair"
        assert HealthStatus.POOR.value == "poor"
        assert HealthStatus.CRITICAL.value == "critical"


class TestHealthCategory:
    """Tests for HealthCategory enum."""

    def test_category_values(self):
        """Test all category values are defined."""
        assert HealthCategory.SECURITY.value == "security"
        assert HealthCategory.UPDATES.value == "updates"
        assert HealthCategory.PERFORMANCE.value == "performance"
        assert HealthCategory.DISK.value == "disk"
        assert HealthCategory.MEMORY.value == "memory"
        assert HealthCategory.SERVICES.value == "services"


class TestHealthFactor:
    """Tests for HealthFactor dataclass."""

    def test_default_values(self):
        """Test default factor values."""
        factor = HealthFactor(
            name="Test",
            category=HealthCategory.DISK,
            score=85,
        )
        assert factor.weight == 1.0
        assert factor.details == ""
        assert factor.recommendation == ""

    def test_status_excellent(self):
        """Test excellent status."""
        factor = HealthFactor(
            name="Test",
            category=HealthCategory.DISK,
            score=95,
        )
        assert factor.status == HealthStatus.EXCELLENT

    def test_status_good(self):
        """Test good status."""
        factor = HealthFactor(
            name="Test",
            category=HealthCategory.DISK,
            score=80,
        )
        assert factor.status == HealthStatus.GOOD

    def test_status_fair(self):
        """Test fair status."""
        factor = HealthFactor(
            name="Test",
            category=HealthCategory.DISK,
            score=60,
        )
        assert factor.status == HealthStatus.FAIR

    def test_status_poor(self):
        """Test poor status."""
        factor = HealthFactor(
            name="Test",
            category=HealthCategory.DISK,
            score=30,
        )
        assert factor.status == HealthStatus.POOR

    def test_status_critical(self):
        """Test critical status."""
        factor = HealthFactor(
            name="Test",
            category=HealthCategory.DISK,
            score=10,
        )
        assert factor.status == HealthStatus.CRITICAL

    def test_status_icon(self):
        """Test status icons."""
        factor = HealthFactor(
            name="Test",
            category=HealthCategory.DISK,
            score=95,
        )
        assert "✓" in factor.status_icon or "green" in factor.status_icon


class TestHealthReport:
    """Tests for HealthReport dataclass."""

    def test_empty_report(self):
        """Test empty report."""
        report = HealthReport()
        assert report.overall_score == 0
        assert report.factors == []

    def test_overall_score(self):
        """Test overall score calculation."""
        report = HealthReport(
            factors=[
                HealthFactor(
                    name="Test1",
                    category=HealthCategory.DISK,
                    score=100,
                    weight=1.0,
                ),
                HealthFactor(
                    name="Test2",
                    category=HealthCategory.MEMORY,
                    score=50,
                    weight=1.0,
                ),
            ]
        )
        assert report.overall_score == 75

    def test_weighted_score(self):
        """Test weighted score calculation."""
        report = HealthReport(
            factors=[
                HealthFactor(
                    name="Test1",
                    category=HealthCategory.DISK,
                    score=100,
                    weight=2.0,  # Weight 2
                ),
                HealthFactor(
                    name="Test2",
                    category=HealthCategory.MEMORY,
                    score=50,
                    weight=1.0,  # Weight 1
                ),
            ]
        )
        # (100*2 + 50*1) / (2+1) = 250/3 = 83
        assert report.overall_score == 83

    def test_report_status(self):
        """Test report status."""
        report = HealthReport(
            factors=[
                HealthFactor(
                    name="Test",
                    category=HealthCategory.DISK,
                    score=80,
                ),
            ]
        )
        assert report.status == HealthStatus.GOOD

    def test_get_recommendations(self):
        """Test getting recommendations."""
        report = HealthReport(
            factors=[
                HealthFactor(
                    name="Test1",
                    category=HealthCategory.DISK,
                    score=50,
                    recommendation="Clean disk",
                    fix_points=10,
                ),
                HealthFactor(
                    name="Test2",
                    category=HealthCategory.UPDATES,
                    score=60,
                    recommendation="Update packages",
                    fix_points=15,
                ),
                HealthFactor(
                    name="Test3",
                    category=HealthCategory.MEMORY,
                    score=90,
                    # No recommendation
                ),
            ]
        )

        recs = report.get_recommendations()
        assert len(recs) == 2
        # Should be sorted by fix_points descending
        assert recs[0].fix_points == 15


class TestHealthChecker:
    """Tests for HealthChecker class."""

    @pytest.fixture
    def checker(self):
        """Create a checker instance."""
        return HealthChecker(verbose=False)

    def test_initialization(self, checker):
        """Test checker initialization."""
        assert checker.verbose is False

    def test_check_disk_space(self, checker):
        """Test disk space check."""
        df_output = """Filesystem     Size  Used Avail Use% Mounted on
/dev/sda1       50G   25G   25G  50% /"""

        with patch.object(checker, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, df_output, "")

            factor = checker.check_disk_space()

            assert factor.name == "Disk Space"
            assert factor.category == HealthCategory.DISK
            assert factor.score == 50

    def test_check_disk_space_critical(self, checker):
        """Test disk space check with high usage."""
        df_output = """Filesystem     Size  Used Avail Use% Mounted on
/dev/sda1       50G   45G    5G  90% /"""

        with patch.object(checker, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, df_output, "")

            factor = checker.check_disk_space()

            assert factor.score == 10
            assert factor.recommendation != ""

    def test_check_memory(self, checker):
        """Test memory check."""
        free_output = """              total        used        free
Mem:          16000        8000        8000
Swap:          4000           0        4000"""

        with patch.object(checker, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, free_output, "")

            factor = checker.check_memory()

            assert factor.name == "Memory"
            assert factor.category == HealthCategory.MEMORY
            assert factor.score == 50

    def test_check_updates_none(self, checker):
        """Test updates check with no updates."""
        apt_output = """Listing..."""

        with patch.object(checker, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, apt_output, "")

            factor = checker.check_updates()

            assert factor.name == "System Updates"
            assert factor.score == 100

    def test_check_updates_many(self, checker):
        """Test updates check with many updates."""
        apt_output = """Listing...
package1/stable 1.2.3 amd64 [upgradable]
package2/stable 2.3.4 amd64 [upgradable]
package3/stable 3.4.5 amd64 [upgradable]
package4/stable 4.5.6 amd64 [upgradable]
package5/stable 5.6.7 amd64 [upgradable]
package6/stable 6.7.8 amd64 [upgradable]"""

        with patch.object(checker, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, apt_output, "")

            factor = checker.check_updates()

            assert factor.score < 100
            assert factor.recommendation != ""

    def test_check_security(self, checker):
        """Test security check."""
        with patch.object(checker, "_run_command") as mock_cmd:
            mock_cmd.side_effect = [
                (0, "Status: active", ""),  # ufw status
                (0, "", ""),  # dpkg unattended-upgrades
            ]

            with patch("pathlib.Path.exists", return_value=False):
                factor = checker.check_security()

            assert factor.name == "Security"
            assert factor.category == HealthCategory.SECURITY

    def test_check_services(self, checker):
        """Test services check."""
        systemctl_output = """UNIT LOAD ACTIVE SUB DESCRIPTION"""

        with patch.object(checker, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, systemctl_output, "")

            factor = checker.check_services()

            assert factor.name == "System Services"
            assert factor.score == 100

    def test_check_services_failed(self, checker):
        """Test services check with failures."""
        systemctl_output = """UNIT                    LOAD   ACTIVE SUB    DESCRIPTION
failed-service.service  loaded failed failed Test Service
another.service         loaded failed failed Another"""

        with patch.object(checker, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, systemctl_output, "")

            factor = checker.check_services()

            assert factor.score < 100
            assert factor.recommendation != ""

    def test_check_performance(self, checker):
        """Test performance check."""
        with patch.object(checker, "_run_command") as mock_cmd:
            mock_cmd.side_effect = [
                (0, "0.5 0.3 0.2 1/100 1234", ""),  # loadavg
                (0, "4", ""),  # nproc
                (0, "", ""),  # swapon
            ]

            factor = checker.check_performance()

            assert factor.name == "Performance"
            assert factor.category == HealthCategory.PERFORMANCE


class TestHealthHistory:
    """Tests for health history functionality."""

    @pytest.fixture
    def checker(self, tmp_path):
        """Create a checker with temp history path."""
        checker = HealthChecker()
        checker.history_path = tmp_path / "health_history.json"
        return checker

    def test_save_history(self, checker):
        """Test saving history."""
        report = HealthReport(
            factors=[
                HealthFactor(
                    name="Test",
                    category=HealthCategory.DISK,
                    score=85,
                )
            ]
        )

        checker.save_history(report)

        assert checker.history_path.exists()
        with open(checker.history_path) as f:
            history = json.load(f)
        assert len(history) == 1
        assert history[0]["overall_score"] == 85

    def test_load_history(self, checker):
        """Test loading history."""
        # Save some history first
        history = [
            {"timestamp": "2024-01-14T10:00:00", "overall_score": 80, "factors": {}},
            {"timestamp": "2024-01-14T11:00:00", "overall_score": 85, "factors": {}},
        ]
        checker.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checker.history_path, "w") as f:
            json.dump(history, f)

        loaded = checker.load_history()

        assert len(loaded) == 2
        assert loaded[0]["overall_score"] == 80

    def test_load_empty_history(self, checker):
        """Test loading non-existent history."""
        loaded = checker.load_history()
        assert loaded == []


class TestDisplayMethods:
    """Tests for display methods."""

    @pytest.fixture
    def checker(self):
        return HealthChecker()

    def test_display_report(self, checker, capsys):
        """Test displaying report."""
        report = HealthReport(
            factors=[
                HealthFactor(
                    name="Test",
                    category=HealthCategory.DISK,
                    score=85,
                )
            ]
        )

        checker.display_report(report)
        captured = capsys.readouterr()
        assert "health" in captured.out.lower()

    def test_display_history(self, checker, tmp_path, capsys):
        """Test displaying history."""
        checker.history_path = tmp_path / "health_history.json"

        # Save some history
        history = [
            {"timestamp": "2024-01-14T10:00:00", "overall_score": 80, "factors": {}},
        ]
        checker.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checker.history_path, "w") as f:
            json.dump(history, f)

        checker.display_history()
        captured = capsys.readouterr()
        assert "history" in captured.out.lower()

    def test_display_empty_history(self, checker, tmp_path, capsys):
        """Test displaying empty history."""
        checker.history_path = tmp_path / "nonexistent.json"

        checker.display_history()
        captured = capsys.readouterr()
        assert "no" in captured.out.lower()


class TestRunHealthCheck:
    """Tests for run_health_check entry point."""

    def test_run_check(self, capsys):
        """Test running health check."""
        with patch("cortex.health_score.HealthChecker") as MockChecker:
            mock_instance = MagicMock()
            mock_report = HealthReport(
                factors=[
                    HealthFactor(
                        name="Test",
                        category=HealthCategory.DISK,
                        score=85,
                    )
                ]
            )
            mock_instance.run_all_checks.return_value = mock_report
            MockChecker.return_value = mock_instance

            result = run_health_check("check")

            assert result == 0
            mock_instance.display_report.assert_called_once()
            mock_instance.save_history.assert_called_once()

    def test_run_check_poor_health(self, capsys):
        """Test running check with poor health."""
        with patch("cortex.health_score.HealthChecker") as MockChecker:
            mock_instance = MagicMock()
            mock_report = HealthReport(
                factors=[
                    HealthFactor(
                        name="Test",
                        category=HealthCategory.DISK,
                        score=30,
                    )
                ]
            )
            mock_instance.run_all_checks.return_value = mock_report
            MockChecker.return_value = mock_instance

            result = run_health_check("check")

            assert result == 1  # Poor health returns 1

    def test_run_history(self, capsys):
        """Test running history action."""
        with patch("cortex.health_score.HealthChecker") as MockChecker:
            mock_instance = MagicMock()
            MockChecker.return_value = mock_instance

            result = run_health_check("history")

            assert result == 0
            mock_instance.display_history.assert_called_once()

    def test_run_factors(self, capsys):
        """Test running factors action."""
        result = run_health_check("factors")

        assert result == 0
        captured = capsys.readouterr()
        assert "disk" in captured.out.lower()

    def test_run_quick(self, capsys):
        """Test running quick check."""
        with patch("cortex.health_score.HealthChecker") as MockChecker:
            mock_instance = MagicMock()
            mock_report = HealthReport(
                factors=[
                    HealthFactor(
                        name="Test",
                        category=HealthCategory.DISK,
                        score=85,
                    )
                ]
            )
            mock_instance.run_all_checks.return_value = mock_report
            MockChecker.return_value = mock_instance

            result = run_health_check("quick")

            assert result == 0
            captured = capsys.readouterr()
            assert "85" in captured.out

    def test_run_unknown_action(self, capsys):
        """Test running unknown action."""
        result = run_health_check("unknown")

        assert result == 1
        captured = capsys.readouterr()
        assert "unknown" in captured.out.lower()
