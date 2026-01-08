#!/usr/bin/env python3
"""
Security Scheduler for Cortex Linux

Schedules regular vulnerability scans and autonomous patching.
Supports systemd timers, cron, and manual scheduling.
"""

import calendar
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from cortex.autonomous_patcher import AutonomousPatcher, PatchStrategy
from cortex.vulnerability_scanner import VulnerabilityScanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScheduleFrequency(Enum):
    """Schedule frequency options"""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


@dataclass
class SecuritySchedule:
    """Security scan/patch schedule configuration"""

    schedule_id: str
    frequency: ScheduleFrequency
    scan_enabled: bool = True
    patch_enabled: bool = False
    patch_strategy: PatchStrategy = PatchStrategy.CRITICAL_ONLY
    dry_run: bool = True
    last_run: str | None = None
    next_run: str | None = None
    custom_cron: str | None = None  # For custom frequency


class SecurityScheduler:
    """Manages scheduled security scans and patches"""

    def __init__(self, cortex_binary: str = "/usr/bin/cortex"):
        """Initialize the security scheduler.

        Args:
            cortex_binary: Path to the cortex binary for systemd service files
        """
        self.config_path = Path.home() / ".cortex" / "security_schedule.json"
        self.cortex_binary = cortex_binary
        self.schedules: dict[str, SecuritySchedule] = {}
        self._load_schedules()

    def _load_schedules(self):
        """Load schedules from configuration file"""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)

                for schedule_data in data.get("schedules", []):
                    schedule = SecuritySchedule(
                        schedule_id=schedule_data["schedule_id"],
                        frequency=ScheduleFrequency(schedule_data["frequency"]),
                        scan_enabled=schedule_data.get("scan_enabled", True),
                        patch_enabled=schedule_data.get("patch_enabled", False),
                        patch_strategy=PatchStrategy(
                            schedule_data.get("patch_strategy", "critical_only")
                        ),
                        dry_run=schedule_data.get("dry_run", True),
                        last_run=schedule_data.get("last_run"),
                        next_run=schedule_data.get("next_run"),
                        custom_cron=schedule_data.get("custom_cron"),
                    )
                    self.schedules[schedule.schedule_id] = schedule

                logger.info(f"Loaded {len(self.schedules)} schedules")
            except Exception as e:
                logger.warning(f"Failed to load schedules: {e}")

    def _save_schedules(self):
        """Save schedules to configuration file"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = {
                "schedules": [
                    {
                        "schedule_id": s.schedule_id,
                        "frequency": s.frequency.value,
                        "scan_enabled": s.scan_enabled,
                        "patch_enabled": s.patch_enabled,
                        "patch_strategy": s.patch_strategy.value,
                        "dry_run": s.dry_run,
                        "last_run": s.last_run,
                        "next_run": s.next_run,
                        "custom_cron": s.custom_cron,
                    }
                    for s in self.schedules.values()
                ]
            }

            with open(self.config_path, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save schedules: {e}")

    def create_schedule(
        self,
        schedule_id: str,
        frequency: ScheduleFrequency,
        scan_enabled: bool = True,
        patch_enabled: bool = False,
        patch_strategy: PatchStrategy = PatchStrategy.CRITICAL_ONLY,
        dry_run: bool = True,
        custom_cron: str | None = None,
    ) -> SecuritySchedule:
        """
        Create a new security schedule.

        Args:
            schedule_id: Unique identifier for the schedule
            frequency: How often to run
            scan_enabled: Enable vulnerability scanning
            patch_enabled: Enable autonomous patching
            patch_strategy: Patching strategy
            dry_run: Run patches in dry-run mode
            custom_cron: Custom cron expression (for CUSTOM frequency)

        Returns:
            Created SecuritySchedule
        """
        # Calculate next run time
        next_run = self._calculate_next_run(frequency, custom_cron)

        schedule = SecuritySchedule(
            schedule_id=schedule_id,
            frequency=frequency,
            scan_enabled=scan_enabled,
            patch_enabled=patch_enabled,
            patch_strategy=patch_strategy,
            dry_run=dry_run,
            next_run=next_run.isoformat() if next_run else None,
            custom_cron=custom_cron,
        )

        self.schedules[schedule_id] = schedule
        self._save_schedules()

        logger.info(f"Created schedule: {schedule_id} ({frequency.value})")
        return schedule

    def _calculate_next_run(
        self, frequency: ScheduleFrequency, custom_cron: str | None = None
    ) -> datetime | None:
        """Calculate next run time based on frequency"""
        now = datetime.now()

        if frequency == ScheduleFrequency.DAILY:
            return now + timedelta(days=1)
        elif frequency == ScheduleFrequency.WEEKLY:
            return now + timedelta(weeks=1)
        elif frequency == ScheduleFrequency.MONTHLY:
            # Properly calculate next month, handling varying month lengths
            year = now.year
            month = now.month + 1
            if month > 12:
                month = 1
                year += 1
            # Clamp day to max days in target month (e.g., Jan 31 -> Feb 28)
            max_day = calendar.monthrange(year, month)[1]
            day = min(now.day, max_day)
            return now.replace(year=year, month=month, day=day)
        elif frequency == ScheduleFrequency.CUSTOM:
            # For custom, we'd need a cron parser, but for now just return None
            # and let the user manage it manually
            return None

        return None

    def run_schedule(self, schedule_id: str) -> dict[str, Any]:
        """
        Execute a scheduled scan/patch.

        Args:
            schedule_id: Schedule to run

        Returns:
            Dictionary with execution results
        """
        if schedule_id not in self.schedules:
            raise ValueError(f"Schedule {schedule_id} not found")

        schedule = self.schedules[schedule_id]
        results = {
            "schedule_id": schedule_id,
            "timestamp": datetime.now().isoformat(),
            "scan_result": None,
            "patch_result": None,
            "success": True,
            "errors": [],
        }

        try:
            # Run scan if enabled
            if schedule.scan_enabled:
                logger.info(f"Running vulnerability scan for schedule {schedule_id}...")
                scanner = VulnerabilityScanner()
                scan_result = scanner.scan_all_packages()

                results["scan_result"] = {
                    "vulnerabilities_found": scan_result.vulnerabilities_found,
                    "critical_count": scan_result.critical_count,
                    "high_count": scan_result.high_count,
                    "medium_count": scan_result.medium_count,
                    "low_count": scan_result.low_count,
                }

                logger.info(
                    f"Scan complete: {scan_result.vulnerabilities_found} vulnerabilities found"
                )

                # Run patch if enabled and vulnerabilities found
                if schedule.patch_enabled and scan_result.vulnerabilities_found > 0:
                    logger.info(f"Running autonomous patch for schedule {schedule_id}...")
                    patcher = AutonomousPatcher(
                        strategy=schedule.patch_strategy, dry_run=schedule.dry_run
                    )

                    # Let AutonomousPatcher apply its own strategy/severity filters
                    patch_result = patcher.patch_vulnerabilities(scan_result.vulnerabilities)

                    results["patch_result"] = {
                        "packages_updated": len(patch_result.packages_updated),
                        "vulnerabilities_patched": patch_result.vulnerabilities_patched,
                        "success": patch_result.success,
                        "errors": patch_result.errors,
                    }

                    if not patch_result.success:
                        results["success"] = False
                        results["errors"].extend(patch_result.errors)

            # Update schedule
            schedule.last_run = datetime.now().isoformat()
            next_run_time = self._calculate_next_run(schedule.frequency, schedule.custom_cron)
            schedule.next_run = next_run_time.isoformat() if next_run_time else None
            self._save_schedules()

        except Exception as e:
            error_msg = f"Schedule execution failed: {e}"
            logger.error(error_msg)
            results["success"] = False
            results["errors"].append(error_msg)

        return results

    def install_systemd_timer(self, schedule_id: str) -> bool:
        """
        Install a systemd timer for the schedule.

        Args:
            schedule_id: Schedule to install

        Returns:
            True if successful
        """
        if schedule_id not in self.schedules:
            logger.error(f"Schedule {schedule_id} not found")
            return False

        schedule = self.schedules[schedule_id]

        # Generate systemd service file
        service_content = f"""[Unit]
Description=Cortex Security Scan/Patch - {schedule_id}
After=network.target

[Service]
Type=oneshot
ExecStart={self.cortex_binary} security schedule run {schedule_id}
User=root
"""

        # Generate systemd timer file
        timer_content = f"""[Unit]
Description=Cortex Security Timer - {schedule_id}
Requires=cortex-security-{schedule_id}.service

[Timer]
OnCalendar={self._frequency_to_systemd(schedule.frequency)}
Persistent=true

[Install]
WantedBy=timers.target
"""

        try:
            # Check for root privileges first (required to write to /etc/systemd/system)
            if not self._has_root_privileges():
                logger.warning("Cannot install systemd timer: root privileges required")
                logger.info(
                    "Try running with sudo: sudo cortex security schedule install-timer "
                    + schedule_id
                )
                return False

            # Write service file
            service_path = Path(f"/etc/systemd/system/cortex-security-{schedule_id}.service")
            with open(service_path, "w") as f:
                f.write(service_content)

            # Write timer file
            timer_path = Path(f"/etc/systemd/system/cortex-security-{schedule_id}.timer")
            with open(timer_path, "w") as f:
                f.write(timer_content)

            # Reload systemd and enable timer
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            subprocess.run(
                ["systemctl", "enable", f"cortex-security-{schedule_id}.timer"], check=True
            )
            subprocess.run(
                ["systemctl", "start", f"cortex-security-{schedule_id}.timer"], check=True
            )

            logger.info(f"✅ Installed systemd timer for {schedule_id}")
            return True

        except PermissionError as e:
            logger.error(f"Permission denied: {e}")
            logger.info(
                "Try running with sudo: sudo cortex security schedule install-timer " + schedule_id
            )
            return False
        except Exception as e:
            logger.error(f"Failed to install systemd timer: {e}")
            return False

    def _frequency_to_systemd(self, frequency: ScheduleFrequency) -> str:
        """Convert frequency to systemd OnCalendar format"""
        if frequency == ScheduleFrequency.DAILY:
            return "daily"
        elif frequency == ScheduleFrequency.WEEKLY:
            return "weekly"
        elif frequency == ScheduleFrequency.MONTHLY:
            return "monthly"
        else:
            return "monthly"  # Default

    def _has_root_privileges(self) -> bool:
        """Check if we have root privileges (running as root or have passwordless sudo)"""
        import os

        # Check if running as root
        if os.geteuid() == 0:
            return True

        # Check if we have passwordless sudo access
        try:
            result = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=2)
            return result.returncode == 0
        except Exception:
            return False

    def list_schedules(self) -> list[SecuritySchedule]:
        """List all schedules"""
        return list(self.schedules.values())

    def get_schedule(self, schedule_id: str) -> SecuritySchedule | None:
        """Get a specific schedule"""
        return self.schedules.get(schedule_id)

    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a schedule"""
        if schedule_id in self.schedules:
            del self.schedules[schedule_id]
            self._save_schedules()
            logger.info(f"Deleted schedule: {schedule_id}")
            return True
        return False


# CLI Interface
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Security scheduler for Cortex Linux")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Create schedule
    create_parser = subparsers.add_parser("create", help="Create a new schedule")
    create_parser.add_argument("id", help="Schedule ID")
    create_parser.add_argument(
        "--frequency",
        choices=["daily", "weekly", "monthly"],
        default="monthly",
        help="Schedule frequency",
    )
    create_parser.add_argument("--no-scan", action="store_true", help="Disable scanning")
    create_parser.add_argument("--enable-patch", action="store_true", help="Enable patching")
    create_parser.add_argument(
        "--patch-strategy",
        choices=["automatic", "critical_only", "high_and_above"],
        default="critical_only",
        help="Patching strategy",
    )
    create_parser.add_argument("--no-dry-run", action="store_true", help="Disable dry-run")

    # List schedules
    subparsers.add_parser("list", help="List all schedules")

    # Run schedule
    run_parser = subparsers.add_parser("run", help="Run a schedule")
    run_parser.add_argument("id", help="Schedule ID")

    # Install systemd timer
    install_parser = subparsers.add_parser("install-timer", help="Install systemd timer")
    install_parser.add_argument("id", help="Schedule ID")

    # Delete schedule
    delete_parser = subparsers.add_parser("delete", help="Delete a schedule")
    delete_parser.add_argument("id", help="Schedule ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    scheduler = SecurityScheduler()

    try:
        if args.command == "create":
            schedule = scheduler.create_schedule(
                schedule_id=args.id,
                frequency=ScheduleFrequency(args.frequency),
                scan_enabled=not args.no_scan,
                patch_enabled=args.enable_patch,
                patch_strategy=PatchStrategy(args.patch_strategy),
                dry_run=not args.no_dry_run,
            )
            print(f"✅ Created schedule: {args.id}")
            print(f"   Frequency: {schedule.frequency.value}")
            print(f"   Scan: {'enabled' if schedule.scan_enabled else 'disabled'}")
            print(f"   Patch: {'enabled' if schedule.patch_enabled else 'disabled'}")

        elif args.command == "list":
            schedules = scheduler.list_schedules()
            if schedules:
                print("\n📅 Security Schedules:")
                print("=" * 80)
                for s in schedules:
                    print(f"\nID: {s.schedule_id}")
                    print(f"  Frequency: {s.frequency.value}")
                    print(f"  Scan: {'✅' if s.scan_enabled else '❌'}")
                    print(f"  Patch: {'✅' if s.patch_enabled else '❌'}")
                    print(f"  Dry-run: {'✅' if s.dry_run else '❌'}")
                    if s.last_run:
                        print(f"  Last run: {s.last_run}")
                    if s.next_run:
                        print(f"  Next run: {s.next_run}")
            else:
                print("No schedules configured")

        elif args.command == "run":
            results = scheduler.run_schedule(args.id)
            if results["success"]:
                print("✅ Schedule execution complete")
                if results["scan_result"]:
                    print(
                        f"  Vulnerabilities found: {results['scan_result']['vulnerabilities_found']}"
                    )
                if results["patch_result"]:
                    print(f"  Packages updated: {results['patch_result']['packages_updated']}")
            else:
                print("❌ Schedule execution failed")
                for error in results["errors"]:
                    print(f"  - {error}")
                sys.exit(1)

        elif args.command == "install-timer":
            if scheduler.install_systemd_timer(args.id):
                print(f"✅ Installed systemd timer for {args.id}")
            else:
                print("❌ Failed to install systemd timer")
                sys.exit(1)

        elif args.command == "delete":
            if scheduler.delete_schedule(args.id):
                print(f"✅ Deleted schedule: {args.id}")
            else:
                print(f"❌ Schedule {args.id} not found")
                sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        logger.exception("CLI error")
        sys.exit(1)
