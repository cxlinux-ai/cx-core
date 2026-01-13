#!/usr/bin/env python3
"""
Installation History and Rollback System

Tracks all installations and enables safe rollback for Cortex Linux.
"""

import datetime
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from cortex.utils.db_pool import SQLiteConnectionPool, get_connection_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InstallationType(Enum):
    """Type of installation operation"""

    INSTALL = "install"
    UPGRADE = "upgrade"
    REMOVE = "remove"
    PURGE = "purge"
    ROLLBACK = "rollback"


class InstallationStatus(Enum):
    """Status of installation"""

    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    IN_PROGRESS = "in_progress"


@dataclass
class PackageSnapshot:
    """Snapshot of a package state"""

    package_name: str
    version: str
    status: str  # installed, not-installed, config-files
    dependencies: list[str]
    config_files: list[str]


@dataclass
class InstallationRecord:
    """Record of an installation operation"""

    id: str  # Unique ID (hash of timestamp + packages)
    timestamp: str
    operation_type: InstallationType
    packages: list[str]
    status: InstallationStatus
    before_snapshot: list[PackageSnapshot]
    after_snapshot: list[PackageSnapshot]
    commands_executed: list[str]
    error_message: str | None = None
    rollback_available: bool = True
    duration_seconds: float | None = None


class InstallationHistory:
    """Manages installation history and rollback"""

    def __init__(self, db_path: str = "/var/lib/cortex/history.db"):
        self.db_path = db_path
        self._ensure_db_directory()
        self._pool: SQLiteConnectionPool | None = None
        self._init_database()

    def _ensure_db_directory(self):
        """Ensure database directory exists and is writable"""
        db_dir = Path(self.db_path).parent
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
            # Also check if we can actually write to this directory
            if not os.access(db_dir, os.W_OK):
                raise PermissionError(f"No write permission to {db_dir}")
        except PermissionError:
            # Fallback to user directory if system directory not accessible
            user_dir = Path.home() / ".cortex"
            user_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(user_dir / "history.db")
            logger.warning(f"Using user directory for database: {self.db_path}")

    def _init_database(self):
        """Initialize SQLite database"""
        try:
            self._pool = get_connection_pool(self.db_path, pool_size=5)

            with self._pool.get_connection() as conn:
                cursor = conn.cursor()

                # Create installations table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS installations (
                        id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        operation_type TEXT NOT NULL,
                        packages TEXT NOT NULL,
                        status TEXT NOT NULL,
                        before_snapshot TEXT,
                        after_snapshot TEXT,
                        commands_executed TEXT,
                        error_message TEXT,
                        rollback_available INTEGER,
                        duration_seconds REAL
                    )
                """
                )

                # Create index on timestamp
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_timestamp
                    ON installations(timestamp)
                """
                )

                conn.commit()

            logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def _run_command(self, cmd: list[str]) -> tuple[bool, str, str]:
        """Execute command and return success, stdout, stderr"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "", "Command timed out")
        except FileNotFoundError:
            return (False, "", f"Command not found: {cmd[0]}")
        except Exception as e:
            return (False, "", str(e))

    def _get_package_info(self, package_name: str) -> PackageSnapshot | None:
        """Get current state of a package"""
        # Check if package is installed
        success, stdout, _ = self._run_command(
            ["dpkg-query", "-W", "-f=${Status}|${Version}", package_name]
        )

        if not success:
            return PackageSnapshot(
                package_name=package_name,
                version="not-installed",
                status="not-installed",
                dependencies=[],
                config_files=[],
            )

        # Parse status and version
        parts = stdout.strip().split("|")
        if len(parts) != 2:
            return None

        status_parts = parts[0].split()
        status = status_parts[-1] if status_parts else "unknown"
        version = parts[1]

        # Get dependencies
        dependencies = []
        dep_success, dep_stdout, _ = self._run_command(["apt-cache", "depends", package_name])
        if dep_success:
            for line in dep_stdout.split("\n"):
                if line.strip().startswith("Depends:"):
                    dep = line.split(":", 1)[1].strip()
                    # Clean up dependency string
                    dep = re.sub(r"\s*\(.*?\)", "", dep)  # Remove version constraints
                    dep = dep.split("|")[0].strip()  # Take first alternative
                    if dep:
                        dependencies.append(dep)

        # Get config files
        config_files = []
        conf_success, conf_stdout, _ = self._run_command(["dpkg-query", "-L", package_name])
        if conf_success:
            for line in conf_stdout.split("\n"):
                line = line.strip()
                if line and "/etc/" in line and Path(line).exists():
                    config_files.append(line)

        return PackageSnapshot(
            package_name=package_name,
            version=version,
            status=status,
            dependencies=dependencies[:10],  # Limit to first 10
            config_files=config_files[:20],  # Limit to first 20
        )

    def _create_snapshot(self, packages: list[str]) -> list[PackageSnapshot]:
        """Create snapshot of package states"""
        snapshots = []

        for package in packages:
            snapshot = self._get_package_info(package)
            if snapshot:
                snapshots.append(snapshot)

        return snapshots

    def _extract_packages_from_commands(self, commands: list[str]) -> list[str]:
        """Extract package names from installation commands"""
        packages = set()

        # Patterns to match package names in commands
        patterns = [
            r"apt-get\s+(?:install|remove|purge)\s+(?:-y\s+)?(.+?)(?:\s*[|&<>]|$)",
            r"apt\s+(?:install|remove|purge)\s+(?:-y\s+)?(.+?)(?:\s*[|&<>]|$)",
            r"dpkg\s+-i\s+(.+?)(?:\s*[|&<>]|$)",
        ]

        for cmd in commands:
            # Remove sudo if present
            cmd_clean = re.sub(r"^sudo\s+", "", cmd.strip())

            for pattern in patterns:
                matches = re.findall(pattern, cmd_clean)
                for match in matches:
                    # Split by comma, space, or pipe for multiple packages
                    # Handle packages like "nginx docker.io postgresql"
                    pkgs = re.split(r"[,\s|]+", match.strip())
                    for pkg in pkgs:
                        pkg = pkg.strip()
                        # Filter out flags and invalid package names
                        if pkg and not pkg.startswith("-") and len(pkg) > 1:
                            # Remove version constraints (e.g., package=1.0.0)
                            pkg = re.sub(r"[=:].*$", "", pkg)
                            # Remove any trailing special characters
                            pkg = re.sub(r"[^\w\.\-\+]+$", "", pkg)
                            if pkg:
                                packages.add(pkg)

        return sorted(packages)

    def _generate_id(self, packages: list[str]) -> str:
        """Generate unique ID for installation"""
        timestamp = datetime.datetime.now().isoformat()
        data = f"{timestamp}:{':'.join(sorted(packages))}"
        return hashlib.md5(data.encode()).hexdigest()[:16]

    def record_installation(
        self,
        operation_type: InstallationType,
        packages: list[str],
        commands: list[str],
        start_time: datetime.datetime,
    ) -> str:
        """
        Record an installation operation

        Returns:
            Installation ID
        """
        # If packages list is empty, try to extract from commands
        if not packages:
            packages = self._extract_packages_from_commands(commands)

        if not packages:
            logger.warning("No packages found in installation record")

        # Create before snapshot
        before_snapshot = self._create_snapshot(packages)

        # Generate ID
        install_id = self._generate_id(packages)

        # Store initial record (in progress)
        timestamp = start_time.isoformat()

        try:
            with self._pool.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO installations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                    (
                        install_id,
                        timestamp,
                        operation_type.value,
                        json.dumps(packages),
                        InstallationStatus.IN_PROGRESS.value,
                        json.dumps([asdict(s) for s in before_snapshot]),
                        None,  # after_snapshot - will be updated
                        json.dumps(commands),
                        None,  # error_message
                        1,  # rollback_available
                        None,  # duration
                    ),
                )

            conn.commit()

            logger.info(f"Installation {install_id} recorded")
            return install_id
        except Exception as e:
            logger.error(f"Failed to record installation: {e}")
            raise

    def update_installation(
        self, install_id: str, status: InstallationStatus, error_message: str | None = None
    ):
        """Update installation record after completion"""
        try:
            with self._pool.get_connection() as conn:
                cursor = conn.cursor()

                # Get packages from record
                cursor.execute(
                    "SELECT packages, timestamp FROM installations WHERE id = ?", (install_id,)
                )
                result = cursor.fetchone()

                if not result:
                    logger.error(f"Installation {install_id} not found")
                    return

                packages = json.loads(result[0])
            start_time = datetime.datetime.fromisoformat(result[1])
            duration = (datetime.datetime.now() - start_time).total_seconds()

            # Create after snapshot
            after_snapshot = self._create_snapshot(packages)

            # Update record
            cursor.execute(
                """
                UPDATE installations
                SET status = ?,
                    after_snapshot = ?,
                    error_message = ?,
                    duration_seconds = ?
                WHERE id = ?
            """,
                (
                    status.value,
                    json.dumps([asdict(s) for s in after_snapshot]),
                    error_message,
                    duration,
                    install_id,
                ),
            )

            conn.commit()

            logger.info(f"Installation {install_id} updated: {status.value}")
        except Exception as e:
            logger.error(f"Failed to update installation: {e}")
            raise

    def get_history(
        self, limit: int = 50, status_filter: InstallationStatus | None = None
    ) -> list[InstallationRecord]:
        """Get installation history"""
        try:
            with self._pool.get_connection() as conn:
                cursor = conn.cursor()

                if status_filter:
                    cursor.execute(
                        """
                        SELECT * FROM installations
                        WHERE status = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                """,
                        (status_filter.value, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM installations
                        ORDER BY timestamp DESC
                        LIMIT ?
                """,
                        (limit,),
                    )

                records = []
                for row in cursor.fetchall():
                    try:
                        record = InstallationRecord(
                            id=row[0],
                            timestamp=row[1],
                            operation_type=InstallationType(row[2]),
                            packages=json.loads(row[3]) if row[3] else [],
                            status=InstallationStatus(row[4]),
                            before_snapshot=[
                                PackageSnapshot(**s) for s in (json.loads(row[5]) if row[5] else [])
                            ],
                            after_snapshot=[
                                PackageSnapshot(**s) for s in (json.loads(row[6]) if row[6] else [])
                            ],
                            commands_executed=json.loads(row[7]) if row[7] else [],
                            error_message=row[8],
                            rollback_available=bool(row[9]) if row[9] is not None else True,
                            duration_seconds=row[10],
                        )
                        records.append(record)
                    except Exception as e:
                        logger.warning(f"Failed to parse record {row[0]}: {e}")
                        continue

                return records
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return []

    def get_installation(self, install_id: str) -> InstallationRecord | None:
        """Get specific installation by ID"""
        try:
            with self._pool.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT * FROM installations WHERE id = ?", (install_id,))

                row = cursor.fetchone()

                if not row:
                    return None

            return InstallationRecord(
                id=row[0],
                timestamp=row[1],
                operation_type=InstallationType(row[2]),
                packages=json.loads(row[3]) if row[3] else [],
                status=InstallationStatus(row[4]),
                before_snapshot=[
                    PackageSnapshot(**s) for s in (json.loads(row[5]) if row[5] else [])
                ],
                after_snapshot=[
                    PackageSnapshot(**s) for s in (json.loads(row[6]) if row[6] else [])
                ],
                commands_executed=json.loads(row[7]) if row[7] else [],
                error_message=row[8],
                rollback_available=bool(row[9]) if row[9] is not None else True,
                duration_seconds=row[10],
            )
        except Exception as e:
            logger.error(f"Failed to get installation: {e}")
            return None

    def rollback(self, install_id: str, dry_run: bool = False) -> tuple[bool, str]:
        """
        Rollback an installation

        Args:
            install_id: Installation to rollback
            dry_run: If True, only show what would be done

        Returns:
            (success, message)
        """
        # Get installation record
        record = self.get_installation(install_id)

        if not record:
            return (False, f"Installation {install_id} not found")

        if not record.rollback_available:
            return (False, "Rollback not available for this installation")

        if record.status == InstallationStatus.ROLLED_BACK:
            return (False, "Installation already rolled back")

        # Determine rollback actions
        actions = []

        # Create maps for easier lookup
        before_map = {s.package_name: s for s in record.before_snapshot}
        after_map = {s.package_name: s for s in record.after_snapshot}

        # Check all packages that were affected
        all_packages = set(before_map.keys()) | set(after_map.keys())

        for package_name in all_packages:
            before = before_map.get(package_name)
            after = after_map.get(package_name)

            if not before and after:
                # Package was installed, need to remove it
                if after.status == "installed":
                    actions.append(f"sudo apt-get remove -y {package_name}")
            elif before and not after:
                # Package was removed, need to reinstall it
                if before.status == "installed":
                    actions.append(f"sudo apt-get install -y {package_name}={before.version}")
            elif before and after:
                # Package state changed
                if before.status == "not-installed" and after.status == "installed":
                    # Package was installed, need to remove it
                    actions.append(f"sudo apt-get remove -y {package_name}")
                elif before.status == "installed" and after.status == "not-installed":
                    # Package was removed, need to reinstall it
                    actions.append(f"sudo apt-get install -y {package_name}={before.version}")
                elif before.version != after.version and before.status == "installed":
                    # Package was upgraded/downgraded
                    actions.append(f"sudo apt-get install -y {package_name}={before.version}")

        if not actions:
            return (True, "No rollback actions needed")

        if dry_run:
            return (True, "\n".join(actions))

        # Execute rollback
        logger.info(f"Rolling back installation {install_id}")

        rollback_start = datetime.datetime.now()

        # Record rollback operation
        rollback_id = self.record_installation(
            InstallationType.ROLLBACK, record.packages, actions, rollback_start
        )

        all_success = True
        error_messages = []

        for action in actions:
            logger.info(f"Executing: {action}")
            success, stdout, stderr = self._run_command(action.split())

            if not success:
                all_success = False
                error_messages.append(f"{action}: {stderr}")
                logger.error(f"Failed: {stderr}")

        # Update rollback record
        if all_success:
            self.update_installation(rollback_id, InstallationStatus.SUCCESS)

            # Mark original as rolled back
            try:
                with self._pool.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE installations SET status = ? WHERE id = ?",
                        (InstallationStatus.ROLLED_BACK.value, install_id),
                    )
                    conn.commit()
            except Exception as e:
                logger.error(f"Failed to update rollback status: {e}")

            return (True, f"Rollback successful (ID: {rollback_id})")
        else:
            self.update_installation(
                rollback_id, InstallationStatus.FAILED, "\n".join(error_messages)
            )
            return (False, f"Rollback failed: {'; '.join(error_messages)}")

    def export_history(self, filepath: str, format: str = "json"):
        """Export history to file"""
        history = self.get_history(limit=1000)

        if format == "json":
            data = [
                {
                    "id": r.id,
                    "timestamp": r.timestamp,
                    "operation": r.operation_type.value,
                    "packages": r.packages,
                    "status": r.status.value,
                    "duration": r.duration_seconds,
                    "error": r.error_message,
                }
                for r in history
            ]

            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)

        elif format == "csv":
            import csv

            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["ID", "Timestamp", "Operation", "Packages", "Status", "Duration", "Error"]
                )

                for r in history:
                    writer.writerow(
                        [
                            r.id,
                            r.timestamp,
                            r.operation_type.value,
                            ", ".join(r.packages),
                            r.status.value,
                            r.duration_seconds or "",
                            r.error_message or "",
                        ]
                    )

        logger.info(f"History exported to {filepath}")

    def cleanup_old_records(self, days: int = 90):
        """Remove records older than specified days"""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        try:
            with self._pool.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("DELETE FROM installations WHERE timestamp < ?", (cutoff_str,))

                deleted = cursor.rowcount
                conn.commit()

                logger.info(f"Deleted {deleted} old records")
            return deleted
        except Exception as e:
            logger.error(f"Failed to cleanup records: {e}")
            return 0


# CLI Interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manage installation history and rollback")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List history
    list_parser = subparsers.add_parser("list", help="List installation history")
    list_parser.add_argument("--limit", type=int, default=20, help="Number of records")
    list_parser.add_argument(
        "--status", choices=["success", "failed", "rolled_back", "in_progress"]
    )

    # Show details
    show_parser = subparsers.add_parser("show", help="Show installation details")
    show_parser.add_argument("id", help="Installation ID")

    # Rollback
    rollback_parser = subparsers.add_parser("rollback", help="Rollback installation")
    rollback_parser.add_argument("id", help="Installation ID")
    rollback_parser.add_argument("--dry-run", action="store_true", help="Show actions only")

    # Export
    export_parser = subparsers.add_parser("export", help="Export history")
    export_parser.add_argument("file", help="Output file")
    export_parser.add_argument("--format", choices=["json", "csv"], default="json")

    # Cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean old records")
    cleanup_parser.add_argument("--days", type=int, default=90, help="Delete older than")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    history = InstallationHistory()

    exit_code = 0

    try:
        if args.command == "list":
            status_filter = InstallationStatus(args.status) if args.status else None
            records = history.get_history(args.limit, status_filter)

            if not records:
                print("No installation records found.")
                sys.exit(0)

            print(f"\n{'ID':<18} {'Date':<20} {'Operation':<12} {'Packages':<30} {'Status':<15}")
            print("=" * 100)

            for r in records:
                date = r.timestamp[:19].replace("T", " ")
                packages = ", ".join(r.packages[:2])
                if len(r.packages) > 2:
                    packages += f" +{len(r.packages) - 2}"

                print(
                    f"{r.id:<18} {date:<20} {r.operation_type.value:<12} {packages:<30} {r.status.value:<15}"
                )

        elif args.command == "show":
            record = history.get_installation(args.id)

            if not record:
                print(f"❌ Installation {args.id} not found", file=sys.stderr)
                sys.exit(1)

            print(f"\nInstallation Details: {record.id}")
            print("=" * 60)
            print(f"Timestamp: {record.timestamp}")
            print(f"Operation: {record.operation_type.value}")
            print(f"Status: {record.status.value}")
            if record.duration_seconds:
                print(f"Duration: {record.duration_seconds:.2f}s")
            else:
                print("Duration: N/A")
            print(f"\nPackages: {', '.join(record.packages)}")

            if record.error_message:
                print(f"\nError: {record.error_message}")

            if record.commands_executed:
                print("\nCommands executed:")
                for cmd in record.commands_executed:
                    print(f"  {cmd}")

            print(f"\nRollback available: {record.rollback_available}")

        elif args.command == "rollback":
            success, message = history.rollback(args.id, args.dry_run)

            if args.dry_run:
                print("\nRollback actions (dry run):")
                print(message)
            elif success:
                print(f"✅ {message}")
            else:
                print(f"❌ {message}", file=sys.stderr)
                exit_code = 1

        elif args.command == "export":
            history.export_history(args.file, args.format)
            print(f"✅ History exported to {args.file}")

        elif args.command == "cleanup":
            deleted = history.cleanup_old_records(args.days)
            print(f"✅ Deleted {deleted} records older than {args.days} days")

        else:
            parser.print_help()
            exit_code = 1

    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        logger.exception("CLI error")
        sys.exit(1)

    sys.exit(exit_code)
