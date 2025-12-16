"""
Tests for Cleanup Scheduler Module.

Tests for CleanupScheduler class and ScheduleConfig dataclass.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess

from cortex.cleanup.scheduler import (
    CleanupScheduler,
    ScheduleConfig,
    ScheduleInterval,
)


class TestScheduleInterval:
    """Tests for ScheduleInterval enum."""
    
    def test_values(self):
        """Test enum values."""
        assert ScheduleInterval.DAILY.value == "daily"
        assert ScheduleInterval.WEEKLY.value == "weekly"
        assert ScheduleInterval.MONTHLY.value == "monthly"


class TestScheduleConfig:
    """Tests for ScheduleConfig dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        config = ScheduleConfig()
        
        assert config.enabled is False
        assert config.interval == ScheduleInterval.WEEKLY
        assert config.safe_mode is True
        assert config.last_run is None
    
    def test_to_dict(self):
        """Test serialization to dict."""
        config = ScheduleConfig(
            enabled=True,
            interval=ScheduleInterval.DAILY,
            safe_mode=False,
            last_run=1234567890.0
        )
        
        data = config.to_dict()
        
        assert data["enabled"] is True
        assert data["interval"] == "daily"
        assert data["safe_mode"] is False
        assert data["last_run"] is not None  # Check existence, not exact value
    
    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "enabled": True,
            "interval": "monthly",
            "safe_mode": True,
            "last_run": 9876543210.0
        }
        
        config = ScheduleConfig.from_dict(data)
        
        assert config.enabled is True
        assert config.interval == ScheduleInterval.MONTHLY
        assert config.safe_mode is True
        assert config.last_run is not None  # Check existence, not exact value
    
    def test_from_dict_defaults(self):
        """Test from_dict with missing keys uses defaults."""
        data = {}
        
        config = ScheduleConfig.from_dict(data)
        
        assert config.enabled is False
        assert config.interval == ScheduleInterval.WEEKLY


class TestCleanupScheduler:
    """Tests for CleanupScheduler class."""
    
    @pytest.fixture
    def scheduler(self, tmp_path):
        """Create a scheduler instance with temp config directory."""
        with patch.object(CleanupScheduler, '__init__', lambda self: None):
            sched = CleanupScheduler.__new__(CleanupScheduler)
            sched.config_dir = tmp_path / ".cortex"
            sched.config_file = sched.config_dir / "cleanup_schedule.json"
            sched._ensure_config_dir()
            return sched
    
    def test_ensure_config_dir(self, scheduler):
        """Test config directory creation."""
        assert scheduler.config_dir.exists()
    
    def test_load_config_no_file(self, scheduler):
        """Test loading config when file doesn't exist."""
        config = scheduler.load_config()
        
        assert config.enabled is False
        assert config.interval == ScheduleInterval.WEEKLY
    
    def test_save_and_load_config(self, scheduler):
        """Test saving and loading config."""
        config = ScheduleConfig(
            enabled=True,
            interval=ScheduleInterval.DAILY,
            safe_mode=True
        )
        
        scheduler.save_config(config)
        loaded = scheduler.load_config()
        
        assert loaded.enabled is True
        assert loaded.interval == ScheduleInterval.DAILY
    
    def test_load_config_invalid_json(self, scheduler):
        """Test loading invalid JSON config."""
        scheduler.config_file.write_text("not valid json")
        
        config = scheduler.load_config()
        
        assert config.enabled is False  # Default
    
    def test_get_status_disabled(self, scheduler):
        """Test get_status when disabled."""
        with patch.object(scheduler, '_check_systemd_timer', return_value=False), \
             patch.object(scheduler, '_check_cron', return_value=False):
            
            status = scheduler.get_status()
            
            assert status["enabled"] is False
            assert status["interval"] is None
    
    def test_get_status_enabled(self, scheduler):
        """Test get_status when enabled."""
        config = ScheduleConfig(enabled=True, interval=ScheduleInterval.DAILY)
        scheduler.save_config(config)
        
        with patch.object(scheduler, '_check_systemd_timer', return_value=True), \
             patch.object(scheduler, '_check_cron', return_value=False):
            
            status = scheduler.get_status()
            
            assert status["enabled"] is True
            assert status["interval"] == "daily"
            assert status["systemd_active"] is True
    
    def test_get_interval_calendar(self, scheduler):
        """Test systemd OnCalendar generation."""
        daily = scheduler._get_interval_calendar(ScheduleInterval.DAILY)
        weekly = scheduler._get_interval_calendar(ScheduleInterval.WEEKLY)
        monthly = scheduler._get_interval_calendar(ScheduleInterval.MONTHLY)
        
        assert "03:00:00" in daily
        assert "Sun" in weekly
        assert "*-*-01" in monthly
    
    def test_get_cron_schedule(self, scheduler):
        """Test cron schedule generation."""
        daily = scheduler._get_cron_schedule(ScheduleInterval.DAILY)
        weekly = scheduler._get_cron_schedule(ScheduleInterval.WEEKLY)
        monthly = scheduler._get_cron_schedule(ScheduleInterval.MONTHLY)
        
        assert daily == "0 3 * * *"
        assert weekly == "0 3 * * 0"
        assert monthly == "0 3 1 * *"
    
    @patch('subprocess.run')
    def test_enable_schedule_systemd_success(self, mock_run, scheduler, tmp_path):
        """Test enable_schedule with systemd success."""
        # Mock systemctl commands
        mock_run.return_value = MagicMock(returncode=0)
        
        # Mock systemd user directory (used via Path.home() patch)
        _ = tmp_path / ".config" / "systemd" / "user"  # Path for reference
        with patch.object(Path, 'home', return_value=tmp_path):
            result = scheduler.enable_schedule(
                interval=ScheduleInterval.WEEKLY,
                safe_mode=True
            )
        
        assert result["success"] is True
        assert result["method"] == "systemd"
    
    @patch('subprocess.run')
    def test_enable_schedule_fallback_to_cron(self, mock_run, scheduler):
        """Test enable_schedule falls back to cron when systemd fails."""
        def side_effect(*args, **kwargs):
            if "is-system-running" in args[0]:
                return MagicMock(returncode=2)  # Not available
            elif "crontab" in args[0]:
                if "-l" in args[0]:
                    return MagicMock(returncode=0, stdout="")
                else:
                    return MagicMock(returncode=0)
            return MagicMock(returncode=0)
        
        mock_run.side_effect = side_effect
        
        result = scheduler.enable_schedule()
        
        assert result["success"] is True
        assert result["method"] == "cron"
    
    @patch('subprocess.run')
    def test_disable_schedule(self, mock_run, scheduler):
        """Test disable_schedule."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        
        # First enable
        config = ScheduleConfig(enabled=True)
        scheduler.save_config(config)
        
        result = scheduler.disable_schedule()
        
        assert result["success"] is True
        
        # Check config is disabled
        loaded = scheduler.load_config()
        assert loaded.enabled is False
    
    @patch('subprocess.run')
    def test_check_systemd_timer_active(self, mock_run, scheduler):
        """Test checking systemd timer when active."""
        mock_run.return_value = MagicMock(returncode=0, stdout="active\n")
        
        active = scheduler._check_systemd_timer()
        
        assert active is True
    
    @patch('subprocess.run')
    def test_check_systemd_timer_inactive(self, mock_run, scheduler):
        """Test checking systemd timer when inactive."""
        mock_run.return_value = MagicMock(returncode=1, stdout="inactive\n")
        
        active = scheduler._check_systemd_timer()
        
        assert active is False
    
    @patch('subprocess.run')
    def test_check_cron_exists(self, mock_run, scheduler):
        """Test checking cron when entry exists."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="0 3 * * 0 /usr/bin/env cortex cleanup run --safe --yes # cortex-cleanup\n"
        )
        
        exists = scheduler._check_cron()
        
        assert exists is True
    
    @patch('subprocess.run')
    def test_check_cron_not_exists(self, mock_run, scheduler):
        """Test checking cron when entry doesn't exist."""
        mock_run.return_value = MagicMock(returncode=0, stdout="# other cron entry\n")
        
        exists = scheduler._check_cron()
        
        assert exists is False
    
    @patch('subprocess.run')
    def test_setup_cron_success(self, mock_run, scheduler):
        """Test setting up cron job."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        
        result = scheduler._setup_cron(ScheduleInterval.WEEKLY)
        
        assert result["success"] is True
    
    @patch('subprocess.run')
    def test_setup_cron_timeout(self, mock_run, scheduler):
        """Test cron setup with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="crontab", timeout=10)
        
        result = scheduler._setup_cron(ScheduleInterval.WEEKLY)
        
        assert result["success"] is False
        assert "timed out" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
