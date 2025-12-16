"""
Cleanup Scheduler Module.

Provides automatic cleanup scheduling functionality using systemd timers or cron.
"""

import json
import logging
import subprocess
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Cron tag for identifying cleanup entries
CRON_TAG = "# cortex-cleanup"


class ScheduleInterval(Enum):
    """Supported scheduling intervals."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class ScheduleConfig:
    """
    Configuration for cleanup scheduling.
    
    Args:
        enabled: Whether scheduling is enabled.
        interval: Scheduling interval (daily/weekly/monthly).
        safe_mode: If True, only run safe cleanup operations.
        last_run: Timestamp of last scheduled run.
    """
    enabled: bool = False
    interval: ScheduleInterval = ScheduleInterval.WEEKLY
    safe_mode: bool = True
    last_run: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "enabled": self.enabled,
            "interval": self.interval.value,
            "safe_mode": self.safe_mode,
            "last_run": self.last_run,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleConfig":
        """Deserialize from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            interval=ScheduleInterval(data.get("interval", "weekly")),
            safe_mode=data.get("safe_mode", True),
            last_run=data.get("last_run"),
        )


class CleanupScheduler:
    """
    Manages automatic cleanup scheduling.
    
    Supports both systemd timers and cron for scheduling.
    """
    
    SYSTEMD_SERVICE_NAME = "cortex-cleanup"
    CONFIG_FILENAME = "cleanup_schedule.json"
    
    def __init__(self) -> None:
        """Initialize the CleanupScheduler."""
        self.config_dir = Path.home() / ".cortex"
        self.config_file = self.config_dir / self.CONFIG_FILENAME
        self._ensure_config_dir()
    
    def _ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, mode=0o700)
    
    def load_config(self) -> ScheduleConfig:
        """
        Load schedule configuration from file.
        
        Returns:
            ScheduleConfig: Current configuration.
        """
        if not self.config_file.exists():
            return ScheduleConfig()
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return ScheduleConfig.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load schedule config: {e}")
            return ScheduleConfig()
    
    def save_config(self, config: ScheduleConfig) -> bool:
        """
        Save schedule configuration to file.
        
        Args:
            config: Configuration to save.
            
        Returns:
            bool: True if saved successfully.
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config.to_dict(), f, indent=2)
            return True
        except OSError as e:
            logger.error(f"Failed to save schedule config: {e}")
            return False
    
    def enable_schedule(
        self,
        interval: ScheduleInterval = ScheduleInterval.WEEKLY,
        safe_mode: bool = True
    ) -> Dict[str, Any]:
        """
        Enable automatic cleanup scheduling.
        
        Args:
            interval: How often to run cleanup.
            safe_mode: If True, only run safe operations.
            
        Returns:
            dict: Result with success status and message.
        """
        config = ScheduleConfig(
            enabled=True,
            interval=interval,
            safe_mode=safe_mode,
        )
        
        # Try to set up systemd timer first
        systemd_result = self._setup_systemd_timer(interval, safe_mode)
        if systemd_result["success"]:
            self.save_config(config)
            return {
                "success": True,
                "method": "systemd",
                "message": f"Enabled {interval.value} cleanup via systemd timer",
            }
        
        # Fall back to cron
        cron_result = self._setup_cron(interval, safe_mode)
        if cron_result["success"]:
            self.save_config(config)
            return {
                "success": True,
                "method": "cron",
                "message": f"Enabled {interval.value} cleanup via cron",
            }
        
        return {
            "success": False,
            "message": "Failed to set up scheduling (neither systemd nor cron available)",
            "systemd_error": systemd_result.get("error"),
            "cron_error": cron_result.get("error"),
        }
    
    def disable_schedule(self) -> Dict[str, Any]:
        """
        Disable automatic cleanup scheduling.
        
        Returns:
            dict: Result with success status and message.
        """
        config = self.load_config()
        config.enabled = False
        self.save_config(config)
        
        # Remove systemd timer
        self._remove_systemd_timer()
        
        # Remove cron entry
        self._remove_cron()
        
        return {
            "success": True,
            "message": "Disabled automatic cleanup scheduling",
        }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current scheduling status.
        
        Returns:
            dict: Current status information.
        """
        config = self.load_config()
        
        return {
            "enabled": config.enabled,
            "interval": config.interval.value if config.enabled else None,
            "safe_mode": config.safe_mode,
            "last_run": config.last_run,
            "systemd_active": self._check_systemd_timer(),
            "cron_active": self._check_cron(),
        }
    
    def _get_interval_calendar(self, interval: ScheduleInterval) -> str:
        """
        Get systemd OnCalendar value for interval.
        
        Args:
            interval: Scheduling interval.
            
        Returns:
            str: OnCalendar specification.
        """
        if interval == ScheduleInterval.DAILY:
            return "*-*-* 03:00:00"  # 3 AM daily
        elif interval == ScheduleInterval.WEEKLY:
            return "Sun *-*-* 03:00:00"  # 3 AM Sunday
        else:  # monthly
            return "*-*-01 03:00:00"  # 3 AM 1st of month
    
    def _get_cron_schedule(self, interval: ScheduleInterval) -> str:
        """
        Get cron schedule expression for interval.
        
        Args:
            interval: Scheduling interval.
            
        Returns:
            str: Cron expression.
        """
        if interval == ScheduleInterval.DAILY:
            return "0 3 * * *"  # 3 AM daily
        elif interval == ScheduleInterval.WEEKLY:
            return "0 3 * * 0"  # 3 AM Sunday
        else:  # monthly
            return "0 3 1 * *"  # 3 AM 1st of month
    
    def _setup_systemd_timer(self, interval: ScheduleInterval, safe_mode: bool = True) -> Dict[str, Any]:
        """
        Set up systemd timer for scheduling.
        
        Args:
            interval: Scheduling interval.
            safe_mode: If True, run with --safe flag; otherwise --force.
            
        Returns:
            dict: Result with success status.
        """
        try:
            # Check if systemd is available
            result = subprocess.run(
                ["systemctl", "--user", "is-system-running"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode not in (0, 1):  # 1 is "degraded" which is OK
                return {"success": False, "error": "systemd not available"}
            
            # Determine cleanup mode flag
            mode_flag = "--safe" if safe_mode else "--force"
            
            # Create service file
            service_content = f"""[Unit]
Description=Cortex Disk Cleanup Service
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/env cortex cleanup run {mode_flag} --yes
"""
            
            # Create timer file
            timer_content = f"""[Unit]
Description=Cortex Disk Cleanup Timer

[Timer]
OnCalendar={self._get_interval_calendar(interval)}
Persistent=true
RandomizedDelaySec=1800

[Install]
WantedBy=timers.target
"""
            
            user_systemd_dir = Path.home() / ".config" / "systemd" / "user"
            user_systemd_dir.mkdir(parents=True, exist_ok=True)
            
            service_path = user_systemd_dir / f"{self.SYSTEMD_SERVICE_NAME}.service"
            timer_path = user_systemd_dir / f"{self.SYSTEMD_SERVICE_NAME}.timer"
            
            service_path.write_text(service_content)
            timer_path.write_text(timer_content)
            
            # Reload and enable timer
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=True,
                timeout=30,
            )
            subprocess.run(
                ["systemctl", "--user", "enable", "--now", f"{self.SYSTEMD_SERVICE_NAME}.timer"],
                check=True,
                timeout=30,
            )
            
            return {"success": True}
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "systemctl command timed out"}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": str(e)}
        except OSError as e:
            return {"success": False, "error": str(e)}
    
    def _remove_systemd_timer(self) -> None:
        """Remove systemd timer and service files."""
        try:
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", f"{self.SYSTEMD_SERVICE_NAME}.timer"],
                capture_output=True,
                timeout=30,
            )
            
            user_systemd_dir = Path.home() / ".config" / "systemd" / "user"
            service_path = user_systemd_dir / f"{self.SYSTEMD_SERVICE_NAME}.service"
            timer_path = user_systemd_dir / f"{self.SYSTEMD_SERVICE_NAME}.timer"
            
            if service_path.exists():
                service_path.unlink()
            if timer_path.exists():
                timer_path.unlink()
                
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass  # Best effort removal
    
    def _check_systemd_timer(self) -> bool:
        """Check if systemd timer is active."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", f"{self.SYSTEMD_SERVICE_NAME}.timer"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() == "active"
        except (subprocess.TimeoutExpired, OSError):
            return False
    
    def _setup_cron(self, interval: ScheduleInterval, safe_mode: bool = True) -> Dict[str, Any]:
        """
        Set up cron job for scheduling.
        
        Args:
            interval: Scheduling interval.
            safe_mode: If True, run with --safe flag; otherwise --force.
            
        Returns:
            dict: Result with success status.
        """
        try:
            cron_schedule = self._get_cron_schedule(interval)
            mode_flag = "--safe" if safe_mode else "--force"
            cron_command = f"{cron_schedule} /usr/bin/env cortex cleanup run {mode_flag} --yes {CRON_TAG}"
            
            # Get current crontab
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            current_crontab = result.stdout if result.returncode == 0 else ""
            
            # Remove existing cortex-cleanup entries
            lines = [
                line for line in current_crontab.splitlines()
                if CRON_TAG not in line
            ]
            
            # Add new entry
            lines.append(cron_command)
            new_crontab = "\n".join(lines) + "\n"
            
            # Set new crontab
            process = subprocess.run(
                ["crontab", "-"],
                input=new_crontab,
                text=True,
                capture_output=True,
                timeout=10,
            )
            
            if process.returncode != 0:
                return {"success": False, "error": process.stderr}
            
            return {"success": True}
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "crontab command timed out"}
        except OSError as e:
            return {"success": False, "error": str(e)}
    
    def _remove_cron(self) -> None:
        """Remove cron entry for cleanup."""
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode != 0:
                return
            
            # Remove cortex-cleanup entries
            lines = [
                line for line in result.stdout.splitlines()
                if CRON_TAG not in line
            ]
            
            new_crontab = "\n".join(lines) + "\n" if lines else ""
            
            subprocess.run(
                ["crontab", "-"],
                input=new_crontab,
                text=True,
                capture_output=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass  # Best effort removal
    
    def _check_cron(self) -> bool:
        """Check if cron entry exists."""
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return CRON_TAG in result.stdout
        except (subprocess.TimeoutExpired, OSError):
            return False
