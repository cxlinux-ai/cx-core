#!/usr/bin/env python3
"""
Tests for Security Scheduler Module
"""

import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from cortex.autonomous_patcher import PatchStrategy
from cortex.security_scheduler import (
    ScheduleFrequency,
    SecuritySchedule,
    SecurityScheduler,
)


class TestScheduleFrequencyEnum(unittest.TestCase):
    """Test cases for ScheduleFrequency enum"""

    def test_frequency_values(self):
        """Test frequency enum has correct values"""
        self.assertEqual(ScheduleFrequency.DAILY.value, "daily")
        self.assertEqual(ScheduleFrequency.WEEKLY.value, "weekly")
        self.assertEqual(ScheduleFrequency.MONTHLY.value, "monthly")

    def test_custom_frequency(self):
        """Test custom frequency value"""
        self.assertEqual(ScheduleFrequency.CUSTOM.value, "custom")


class TestSecuritySchedule(unittest.TestCase):
    """Test cases for SecuritySchedule dataclass"""

    def test_schedule_creation(self):
        """Test creating security schedule object"""
        schedule = SecuritySchedule(
            schedule_id="monthly_scan",
            frequency=ScheduleFrequency.MONTHLY,
            scan_enabled=True,
            patch_enabled=False,
        )

        self.assertEqual(schedule.schedule_id, "monthly_scan")
        self.assertEqual(schedule.frequency, ScheduleFrequency.MONTHLY)
        self.assertTrue(schedule.scan_enabled)
        self.assertFalse(schedule.patch_enabled)
        self.assertTrue(schedule.dry_run)  # Default value

    def test_schedule_defaults(self):
        """Test schedule default values"""
        schedule = SecuritySchedule(
            schedule_id="test",
            frequency=ScheduleFrequency.DAILY,
        )

        self.assertTrue(schedule.scan_enabled)
        self.assertFalse(schedule.patch_enabled)
        self.assertEqual(schedule.patch_strategy, PatchStrategy.CRITICAL_ONLY)
        self.assertTrue(schedule.dry_run)
        self.assertIsNone(schedule.last_run)
        self.assertIsNone(schedule.next_run)
        self.assertIsNone(schedule.custom_cron)

    def test_schedule_with_patch_enabled(self):
        """Test schedule with patching enabled"""
        schedule = SecuritySchedule(
            schedule_id="auto_patch",
            frequency=ScheduleFrequency.WEEKLY,
            scan_enabled=True,
            patch_enabled=True,
            patch_strategy=PatchStrategy.HIGH_AND_ABOVE,
            dry_run=False,
        )

        self.assertTrue(schedule.patch_enabled)
        self.assertEqual(schedule.patch_strategy, PatchStrategy.HIGH_AND_ABOVE)
        self.assertFalse(schedule.dry_run)

    def test_schedule_with_custom_cron(self):
        """Test schedule with custom cron expression"""
        schedule = SecuritySchedule(
            schedule_id="custom_schedule",
            frequency=ScheduleFrequency.CUSTOM,
            scan_enabled=True,
            custom_cron="0 3 * * 0",  # Every Sunday at 3 AM
        )

        self.assertEqual(schedule.frequency, ScheduleFrequency.CUSTOM)
        self.assertEqual(schedule.custom_cron, "0 3 * * 0")


class TestSecurityScheduler(unittest.TestCase):
    """Test cases for SecurityScheduler"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "security_schedule.json")
        # Patch the config path
        self.config_patcher = patch.object(
            SecurityScheduler,
            "__init__",
            lambda self_obj: self._init_scheduler(self_obj),
        )

    def _init_scheduler(self, scheduler_obj):
        """Custom init for testing with temp config path"""
        from pathlib import Path

        scheduler_obj.config_path = Path(self.config_path)
        scheduler_obj.schedules = {}
        # Don't call _load_schedules since config doesn't exist yet

    def tearDown(self):
        """Clean up temporary files"""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Test scheduler initializes correctly"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.config_path = None
            scheduler.schedules = {}
            self.assertIsNotNone(scheduler)
            self.assertIsInstance(scheduler.schedules, dict)

    def test_create_schedule(self):
        """Test creating a schedule"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            from pathlib import Path

            scheduler.config_path = Path(self.config_path)
            scheduler.schedules = {}

            schedule = scheduler.create_schedule(
                schedule_id="test_schedule",
                frequency=ScheduleFrequency.WEEKLY,
                scan_enabled=True,
                patch_enabled=False,
            )

            self.assertEqual(schedule.schedule_id, "test_schedule")
            self.assertIn("test_schedule", scheduler.schedules)

    def test_create_schedule_with_patch(self):
        """Test creating schedule with patching enabled"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            from pathlib import Path

            scheduler.config_path = Path(self.config_path)
            scheduler.schedules = {}

            schedule = scheduler.create_schedule(
                schedule_id="patch_schedule",
                frequency=ScheduleFrequency.MONTHLY,
                scan_enabled=True,
                patch_enabled=True,
                patch_strategy=PatchStrategy.HIGH_AND_ABOVE,
                dry_run=False,
            )

            self.assertTrue(schedule.patch_enabled)
            self.assertEqual(schedule.patch_strategy, PatchStrategy.HIGH_AND_ABOVE)
            self.assertFalse(schedule.dry_run)

    def test_get_schedule(self):
        """Test getting a schedule by ID"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            from pathlib import Path

            scheduler.config_path = Path(self.config_path)
            scheduler.schedules = {}

            scheduler.create_schedule(
                schedule_id="get_test",
                frequency=ScheduleFrequency.DAILY,
                scan_enabled=True,
            )

            schedule = scheduler.get_schedule("get_test")

            self.assertIsNotNone(schedule)
            self.assertEqual(schedule.schedule_id, "get_test")

    def test_get_nonexistent_schedule(self):
        """Test getting non-existent schedule returns None"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            schedule = scheduler.get_schedule("nonexistent")
            self.assertIsNone(schedule)

    def test_delete_schedule(self):
        """Test deleting a schedule"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            from pathlib import Path

            scheduler.config_path = Path(self.config_path)
            scheduler.schedules = {}

            scheduler.create_schedule(
                schedule_id="to_delete",
                frequency=ScheduleFrequency.DAILY,
                scan_enabled=True,
            )

            success = scheduler.delete_schedule("to_delete")

            self.assertTrue(success)
            self.assertNotIn("to_delete", scheduler.schedules)

    def test_delete_nonexistent_schedule(self):
        """Test deleting non-existent schedule returns False"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            from pathlib import Path

            scheduler.config_path = Path(self.config_path)
            scheduler.schedules = {}

            success = scheduler.delete_schedule("nonexistent")
            self.assertFalse(success)

    def test_list_schedules(self):
        """Test listing all schedules"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            from pathlib import Path

            scheduler.config_path = Path(self.config_path)
            scheduler.schedules = {}

            scheduler.create_schedule(
                schedule_id="schedule_1",
                frequency=ScheduleFrequency.DAILY,
                scan_enabled=True,
            )
            scheduler.create_schedule(
                schedule_id="schedule_2",
                frequency=ScheduleFrequency.WEEKLY,
                scan_enabled=True,
            )

            schedules = scheduler.list_schedules()

            self.assertEqual(len(schedules), 2)
            schedule_ids = [s.schedule_id for s in schedules]
            self.assertIn("schedule_1", schedule_ids)
            self.assertIn("schedule_2", schedule_ids)

    def test_calculate_next_run_daily(self):
        """Test calculating next run time for daily schedule"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            next_run = scheduler._calculate_next_run(ScheduleFrequency.DAILY)

            self.assertIsNotNone(next_run)
            # Should be roughly 1 day from now
            delta = next_run - datetime.now()
            self.assertGreater(delta.total_seconds(), 23 * 3600)  # At least 23 hours
            self.assertLess(delta.total_seconds(), 25 * 3600)  # Less than 25 hours

    def test_calculate_next_run_weekly(self):
        """Test calculating next run time for weekly schedule"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            next_run = scheduler._calculate_next_run(ScheduleFrequency.WEEKLY)

            self.assertIsNotNone(next_run)
            # Should be roughly 1 week from now
            delta = next_run - datetime.now()
            self.assertGreaterEqual(delta.days, 6)
            self.assertLessEqual(delta.days, 8)

    def test_calculate_next_run_monthly(self):
        """Test calculating next run time for monthly schedule"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            next_run = scheduler._calculate_next_run(ScheduleFrequency.MONTHLY)

            self.assertIsNotNone(next_run)
            # Should be roughly 30 days from now
            delta = next_run - datetime.now()
            self.assertGreaterEqual(delta.days, 29)
            self.assertLessEqual(delta.days, 31)

    def test_calculate_next_run_custom(self):
        """Test calculating next run for custom frequency returns None"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            next_run = scheduler._calculate_next_run(ScheduleFrequency.CUSTOM)
            self.assertIsNone(next_run)


class TestSecuritySchedulerSystemd(unittest.TestCase):
    """Test systemd timer generation"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "security_schedule.json")

    def tearDown(self):
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_frequency_to_systemd_daily(self):
        """Test converting daily frequency to systemd format"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            result = scheduler._frequency_to_systemd(ScheduleFrequency.DAILY)
            self.assertEqual(result, "daily")

    def test_frequency_to_systemd_weekly(self):
        """Test converting weekly frequency to systemd format"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            result = scheduler._frequency_to_systemd(ScheduleFrequency.WEEKLY)
            self.assertEqual(result, "weekly")

    def test_frequency_to_systemd_monthly(self):
        """Test converting monthly frequency to systemd format"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            result = scheduler._frequency_to_systemd(ScheduleFrequency.MONTHLY)
            self.assertEqual(result, "monthly")

    def test_frequency_to_systemd_custom(self):
        """Test custom frequency defaults to monthly"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            result = scheduler._frequency_to_systemd(ScheduleFrequency.CUSTOM)
            self.assertEqual(result, "monthly")  # Default fallback

    @patch("os.geteuid")
    def test_has_root_privileges_as_root(self, mock_geteuid):
        """Test root privilege check when running as root"""
        mock_geteuid.return_value = 0

        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            has_root = scheduler._has_root_privileges()
            self.assertTrue(has_root)

    @patch("os.geteuid")
    @patch("subprocess.run")
    def test_has_root_privileges_with_sudo(self, mock_run, mock_geteuid):
        """Test root privilege check with passwordless sudo"""
        mock_geteuid.return_value = 1000  # Non-root
        mock_run.return_value = MagicMock(returncode=0)

        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            has_root = scheduler._has_root_privileges()
            self.assertTrue(has_root)

    @patch("os.geteuid")
    @patch("subprocess.run")
    def test_has_root_privileges_without_sudo(self, mock_run, mock_geteuid):
        """Test root privilege check without sudo access"""
        mock_geteuid.return_value = 1000  # Non-root
        mock_run.return_value = MagicMock(returncode=1)

        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            has_root = scheduler._has_root_privileges()
            self.assertFalse(has_root)

    @patch.object(SecurityScheduler, "_has_root_privileges")
    def test_install_systemd_timer_no_privileges(self, mock_has_root):
        """Test installing timer fails without root"""
        mock_has_root.return_value = False

        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            from pathlib import Path

            scheduler = SecurityScheduler()
            scheduler.config_path = Path(self.config_path)
            scheduler.cortex_binary = "/usr/bin/cortex"
            scheduler.schedules = {}

            scheduler.create_schedule(
                schedule_id="no_root_test",
                frequency=ScheduleFrequency.DAILY,
                scan_enabled=True,
            )

            success = scheduler.install_systemd_timer("no_root_test")
            self.assertFalse(success)

    def test_install_systemd_timer_nonexistent_schedule(self):
        """Test installing timer for non-existent schedule fails"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            success = scheduler.install_systemd_timer("nonexistent")
            self.assertFalse(success)


class TestSecuritySchedulerExecution(unittest.TestCase):
    """Test schedule execution"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "security_schedule.json")

    def tearDown(self):
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("cortex.security_scheduler.VulnerabilityScanner")
    def test_run_schedule_scan_only(self, mock_scanner_class):
        """Test running schedule with scan only"""
        mock_scanner = MagicMock()
        mock_scan_result = MagicMock()
        mock_scan_result.vulnerabilities = []
        mock_scan_result.vulnerabilities_found = 0
        mock_scan_result.critical_count = 0
        mock_scan_result.high_count = 0
        mock_scan_result.medium_count = 0
        mock_scan_result.low_count = 0
        mock_scanner.scan_all_packages.return_value = mock_scan_result
        mock_scanner_class.return_value = mock_scanner

        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            from pathlib import Path

            scheduler = SecurityScheduler()
            scheduler.config_path = Path(self.config_path)
            scheduler.schedules = {}

            scheduler.create_schedule(
                schedule_id="scan_only",
                frequency=ScheduleFrequency.DAILY,
                scan_enabled=True,
                patch_enabled=False,
            )

            result = scheduler.run_schedule("scan_only")

            self.assertTrue(result["success"])
            self.assertIsNotNone(result["scan_result"])
            mock_scanner.scan_all_packages.assert_called_once()

    def test_run_nonexistent_schedule(self):
        """Test running non-existent schedule raises error"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            scheduler = SecurityScheduler()
            scheduler.schedules = {}

            with self.assertRaises(ValueError) as context:
                scheduler.run_schedule("nonexistent")

            self.assertIn("not found", str(context.exception).lower())

    @patch("cortex.security_scheduler.VulnerabilityScanner")
    @patch("cortex.security_scheduler.AutonomousPatcher")
    def test_run_schedule_with_patching(self, mock_patcher_class, mock_scanner_class):
        """Test running schedule with patching enabled"""
        # Setup mock scanner
        mock_scanner = MagicMock()
        mock_vuln = MagicMock()
        mock_vuln.severity.value = "critical"
        mock_scan_result = MagicMock()
        mock_scan_result.vulnerabilities = [mock_vuln]
        mock_scan_result.vulnerabilities_found = 1
        mock_scan_result.critical_count = 1
        mock_scan_result.high_count = 0
        mock_scan_result.medium_count = 0
        mock_scan_result.low_count = 0
        mock_scanner.scan_all_packages.return_value = mock_scan_result
        mock_scanner_class.return_value = mock_scanner

        # Setup mock patcher
        mock_patcher = MagicMock()
        mock_patch_result = MagicMock()
        mock_patch_result.packages_updated = ["test-pkg"]
        mock_patch_result.vulnerabilities_patched = 1
        mock_patch_result.success = True
        mock_patch_result.errors = []
        mock_patcher.patch_vulnerabilities.return_value = mock_patch_result
        mock_patcher_class.return_value = mock_patcher

        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            from pathlib import Path

            scheduler = SecurityScheduler()
            scheduler.config_path = Path(self.config_path)
            scheduler.schedules = {}

            scheduler.create_schedule(
                schedule_id="patch_test",
                frequency=ScheduleFrequency.DAILY,
                scan_enabled=True,
                patch_enabled=True,
            )

            result = scheduler.run_schedule("patch_test")

            self.assertTrue(result["success"])
            self.assertIsNotNone(result["patch_result"])
            self.assertEqual(result["patch_result"]["packages_updated"], 1)


class TestSecuritySchedulerSaveLoad(unittest.TestCase):
    """Test schedule persistence"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "security_schedule.json")

    def tearDown(self):
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_save_schedules(self):
        """Test saving schedules to file"""
        with patch.object(SecurityScheduler, "__init__", lambda x: None):
            from pathlib import Path

            scheduler = SecurityScheduler()
            scheduler.config_path = Path(self.config_path)
            scheduler.schedules = {}

            scheduler.create_schedule(
                schedule_id="save_test",
                frequency=ScheduleFrequency.WEEKLY,
                scan_enabled=True,
                patch_enabled=True,
            )

            # Verify file was created
            self.assertTrue(os.path.exists(self.config_path))

            # Verify content
            with open(self.config_path) as f:
                data = json.load(f)

            self.assertIn("schedules", data)
            self.assertEqual(len(data["schedules"]), 1)
            self.assertEqual(data["schedules"][0]["schedule_id"], "save_test")

    def test_load_schedules(self):
        """Test loading schedules from file"""
        # Create a config file manually
        from pathlib import Path

        config_path = Path(self.config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        config_data = {
            "schedules": [
                {
                    "schedule_id": "loaded_schedule",
                    "frequency": "monthly",
                    "scan_enabled": True,
                    "patch_enabled": False,
                    "patch_strategy": "critical_only",
                    "dry_run": True,
                    "last_run": None,
                    "next_run": None,
                    "custom_cron": None,
                }
            ]
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # Create scheduler with patched home path
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            with patch("pathlib.Path.exists", return_value=True):
                # Manually load
                scheduler = SecurityScheduler.__new__(SecurityScheduler)
                scheduler.config_path = config_path
                scheduler.schedules = {}
                scheduler._load_schedules()

                self.assertIn("loaded_schedule", scheduler.schedules)
                schedule = scheduler.schedules["loaded_schedule"]
                self.assertEqual(schedule.frequency, ScheduleFrequency.MONTHLY)


if __name__ == "__main__":
    unittest.main()
