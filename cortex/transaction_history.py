"""
Transaction History and Undo Module for Cortex Linux

Tracks all package operations and provides undo/rollback capabilities
for safe package management.

Issue: #258
"""

import hashlib
import json
import logging
import os
import sqlite3
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


import threading  # For thread-safe singleton pattern


class TransactionType(Enum):
    """Types of package transactions."""

    INSTALL = "install"
    REMOVE = "remove"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    AUTOREMOVE = "autoremove"
    PURGE = "purge"
    CONFIGURE = "configure"
    BATCH = "batch"  # Multiple operations in one transaction


class TransactionStatus(Enum):
    """Status of a transaction."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIALLY_COMPLETED = "partially_completed"


@dataclass
class PackageState:
    """Represents the state of a package at a point in time."""

    name: str
    version: str | None = None
    installed: bool = False
    config_files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PackageState":
        return cls(**data)


@dataclass
class Transaction:
    """Represents a single package transaction."""

    id: str
    transaction_type: TransactionType
    packages: list[str]
    timestamp: datetime
    status: TransactionStatus = TransactionStatus.PENDING

    # State tracking
    before_state: dict[str, PackageState] = field(default_factory=dict)
    after_state: dict[str, PackageState] = field(default_factory=dict)

    # Metadata
    command: str = ""
    user: str = ""
    duration_seconds: float = 0.0
    error_message: str | None = None

    # Rollback info
    rollback_commands: list[str] = field(default_factory=list)
    is_rollback_safe: bool = True
    rollback_warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "transaction_type": self.transaction_type.value,
            "packages": self.packages,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "before_state": {k: v.to_dict() for k, v in self.before_state.items()},
            "after_state": {k: v.to_dict() for k, v in self.after_state.items()},
            "command": self.command,
            "user": self.user,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "rollback_commands": self.rollback_commands,
            "is_rollback_safe": self.is_rollback_safe,
            "rollback_warning": self.rollback_warning,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        return cls(
            id=data["id"],
            transaction_type=TransactionType(data["transaction_type"]),
            packages=data["packages"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            status=TransactionStatus(data["status"]),
            before_state={
                k: PackageState.from_dict(v) for k, v in data.get("before_state", {}).items()
            },
            after_state={
                k: PackageState.from_dict(v) for k, v in data.get("after_state", {}).items()
            },
            command=data.get("command", ""),
            user=data.get("user", ""),
            duration_seconds=data.get("duration_seconds", 0.0),
            error_message=data.get("error_message"),
            rollback_commands=data.get("rollback_commands", []),
            is_rollback_safe=data.get("is_rollback_safe", True),
            rollback_warning=data.get("rollback_warning"),
        )


class TransactionHistory:
    """
    Manages transaction history with SQLite storage.

    Provides:
    - Recording of all package operations
    - State snapshots before/after operations
    - Undo/rollback capabilities
    - Search and filtering
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or Path.home() / ".cortex" / "transaction_history.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    transaction_type TEXT NOT NULL,
                    packages TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    before_state TEXT,
                    after_state TEXT,
                    command TEXT,
                    user TEXT,
                    duration_seconds REAL,
                    error_message TEXT,
                    rollback_commands TEXT,
                    is_rollback_safe INTEGER,
                    rollback_warning TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON transactions(timestamp DESC)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status
                ON transactions(status)
            """)

            conn.commit()

    def _generate_id(self) -> str:
        """Generate a unique transaction ID."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        random_part = hashlib.sha256(os.urandom(16)).hexdigest()[:8]
        return f"tx_{timestamp}_{random_part}"

    def begin_transaction(
        self, transaction_type: TransactionType, packages: list[str], command: str = ""
    ) -> Transaction:
        """
        Begin a new transaction and capture before state.

        Args:
            transaction_type: Type of operation
            packages: List of package names involved
            command: The command being executed

        Returns:
            Transaction object for tracking
        """
        transaction = Transaction(
            id=self._generate_id(),
            transaction_type=transaction_type,
            packages=packages,
            timestamp=datetime.now(),
            status=TransactionStatus.IN_PROGRESS,
            command=command,
            user=os.environ.get("USER", "unknown"),
        )

        # Capture before state
        for pkg in packages:
            state = self._capture_package_state(pkg)
            transaction.before_state[pkg] = state

        # Calculate rollback commands
        transaction.rollback_commands = self._calculate_rollback_commands(
            transaction_type, transaction.before_state
        )

        # Save initial transaction
        self._save_transaction(transaction)

        return transaction

    def complete_transaction(
        self, transaction: Transaction, success: bool = True, error_message: str | None = None
    ):
        """
        Complete a transaction and capture after state.

        Args:
            transaction: The transaction to complete
            success: Whether the operation succeeded
            error_message: Error message if failed
        """
        transaction.duration_seconds = (datetime.now() - transaction.timestamp).total_seconds()

        if success:
            transaction.status = TransactionStatus.COMPLETED

            # Capture after state
            for pkg in transaction.packages:
                state = self._capture_package_state(pkg)
                transaction.after_state[pkg] = state
        else:
            transaction.status = TransactionStatus.FAILED
            transaction.error_message = error_message

        # Update rollback safety
        self._assess_rollback_safety(transaction)

        self._save_transaction(transaction)

    def _capture_package_state(self, package: str) -> PackageState:
        """Capture the current state of a package."""
        state = PackageState(name=package)

        try:
            # Check if installed and get version
            result = subprocess.run(
                ["dpkg-query", "-W", "-f=${Status}|${Version}", package],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                parts = result.stdout.strip().split("|")
                if len(parts) >= 2 and "installed" in parts[0]:
                    state.installed = True
                    state.version = parts[1]

            # Get config files
            if state.installed:
                config_result = subprocess.run(
                    ["dpkg-query", "-L", package], capture_output=True, text=True
                )
                if config_result.returncode == 0:
                    for line in config_result.stdout.strip().split("\n"):
                        if "/etc/" in line or line.endswith(".conf"):
                            state.config_files.append(line)

            # Get dependencies
            dep_result = subprocess.run(
                ["apt-cache", "depends", package, "--installed"], capture_output=True, text=True
            )
            if dep_result.returncode == 0:
                for line in dep_result.stdout.strip().split("\n"):
                    if "Depends:" in line:
                        dep = line.split("Depends:")[-1].strip()
                        if dep and not dep.startswith("<"):
                            state.dependencies.append(dep)

        except Exception as e:
            logger.warning(f"Error capturing state for {package}: {e}")

        return state

    def _calculate_rollback_commands(
        self, transaction_type: TransactionType, before_state: dict[str, PackageState]
    ) -> list[str]:
        """Calculate commands needed to rollback this transaction."""
        commands = []

        for pkg, state in before_state.items():
            if transaction_type == TransactionType.INSTALL:
                if not state.installed:
                    commands.append(f"sudo apt remove -y {pkg}")

            elif transaction_type == TransactionType.REMOVE:
                if state.installed:
                    if state.version:
                        commands.append(f"sudo apt install -y {pkg}={state.version}")
                    else:
                        commands.append(f"sudo apt install -y {pkg}")

            elif transaction_type == TransactionType.UPGRADE:
                if state.installed and state.version:
                    commands.append(f"sudo apt install -y {pkg}={state.version}")

            elif transaction_type == TransactionType.PURGE:
                # Purge cannot be fully undone (config files lost)
                if state.installed:
                    commands.append(f"sudo apt install -y {pkg}")
                    commands.append(f"# Warning: Config files for {pkg} cannot be restored")

        return commands

    def _assess_rollback_safety(self, transaction: Transaction):
        """Assess whether a transaction can be safely rolled back."""
        # Check for system-critical packages
        critical_packages = {
            "apt",
            "dpkg",
            "libc6",
            "systemd",
            "bash",
            "coreutils",
            "linux-image",
            "grub",
            "init",
        }

        for pkg in transaction.packages:
            if any(crit in pkg for crit in critical_packages):
                transaction.is_rollback_safe = False
                transaction.rollback_warning = (
                    f"Rolling back {pkg} may affect system stability. Proceed with caution."
                )
                break

        # Check for purge operations
        if transaction.transaction_type == TransactionType.PURGE:
            transaction.rollback_warning = (
                "Purge operations cannot fully restore configuration files."
            )

    def _save_transaction(self, transaction: Transaction):
        """Save transaction to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO transactions VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """,
                (
                    transaction.id,
                    transaction.transaction_type.value,
                    json.dumps(transaction.packages),
                    transaction.timestamp.isoformat(),
                    transaction.status.value,
                    json.dumps({k: v.to_dict() for k, v in transaction.before_state.items()}),
                    json.dumps({k: v.to_dict() for k, v in transaction.after_state.items()}),
                    transaction.command,
                    transaction.user,
                    transaction.duration_seconds,
                    transaction.error_message,
                    json.dumps(transaction.rollback_commands),
                    1 if transaction.is_rollback_safe else 0,
                    transaction.rollback_warning,
                ),
            )
            conn.commit()

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        """Get a specific transaction by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_transaction(row)

        return None

    def get_recent(
        self, limit: int = 10, status_filter: TransactionStatus | None = None
    ) -> list[Transaction]:
        """Get recent transactions."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if status_filter:
                cursor = conn.execute(
                    "SELECT * FROM transactions WHERE status = ? ORDER BY timestamp DESC LIMIT ?",
                    (status_filter.value, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?", (limit,)
                )

            return [self._row_to_transaction(row) for row in cursor]

    def search(
        self,
        package: str | None = None,
        transaction_type: TransactionType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> list[Transaction]:
        """Search transactions with filters."""
        query = "SELECT * FROM transactions WHERE 1=1"
        params = []

        if package:
            query += " AND packages LIKE ?"
            params.append(f'%"{package}"%')

        if transaction_type:
            query += " AND transaction_type = ?"
            params.append(transaction_type.value)

        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())

        if until:
            query += " AND timestamp <= ?"
            params.append(until.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            return [self._row_to_transaction(row) for row in cursor]

    def _row_to_transaction(self, row: sqlite3.Row) -> Transaction:
        """Convert a database row to a Transaction object."""
        return Transaction(
            id=row["id"],
            transaction_type=TransactionType(row["transaction_type"]),
            packages=json.loads(row["packages"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            status=TransactionStatus(row["status"]),
            before_state={
                k: PackageState.from_dict(v)
                for k, v in json.loads(row["before_state"] or "{}").items()
            },
            after_state={
                k: PackageState.from_dict(v)
                for k, v in json.loads(row["after_state"] or "{}").items()
            },
            command=row["command"],
            user=row["user"],
            duration_seconds=row["duration_seconds"],
            error_message=row["error_message"],
            rollback_commands=json.loads(row["rollback_commands"] or "[]"),
            is_rollback_safe=bool(row["is_rollback_safe"]),
            rollback_warning=row["rollback_warning"],
        )

    def get_stats(self) -> dict[str, Any]:
        """Get transaction statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

            by_type = {}
            for t in TransactionType:
                count = conn.execute(
                    "SELECT COUNT(*) FROM transactions WHERE transaction_type = ?", (t.value,)
                ).fetchone()[0]
                by_type[t.value] = count

            by_status = {}
            for s in TransactionStatus:
                count = conn.execute(
                    "SELECT COUNT(*) FROM transactions WHERE status = ?", (s.value,)
                ).fetchone()[0]
                by_status[s.value] = count

            return {
                "total_transactions": total,
                "by_type": by_type,
                "by_status": by_status,
                "db_size_kb": self.db_path.stat().st_size / 1024,
            }


class UndoManager:
    """
    Manages undo operations for package transactions.

    Provides safe rollback with confirmation and progress tracking.
    """

    def __init__(self, history: TransactionHistory | None = None):
        self.history = history or TransactionHistory()

    def can_undo(self, transaction_id: str) -> tuple[bool, str]:
        """
        Check if a transaction can be undone.

        Returns:
            Tuple of (can_undo, reason)
        """
        transaction = self.history.get_transaction(transaction_id)

        if not transaction:
            return False, "Transaction not found"

        if transaction.status != TransactionStatus.COMPLETED:
            return False, f"Cannot undo transaction with status: {transaction.status.value}"

        if not transaction.rollback_commands:
            return False, "No rollback commands available"

        # Check if already rolled back
        if transaction.status == TransactionStatus.ROLLED_BACK:
            return False, "Transaction already rolled back"

        return True, transaction.rollback_warning or "Safe to undo"

    def preview_undo(self, transaction_id: str) -> dict[str, Any]:
        """
        Preview what an undo operation would do.

        Returns:
            Dict with rollback details
        """
        transaction = self.history.get_transaction(transaction_id)

        if not transaction:
            return {"error": "Transaction not found"}

        return {
            "transaction_id": transaction.id,
            "original_type": transaction.transaction_type.value,
            "packages": transaction.packages,
            "commands": transaction.rollback_commands,
            "is_safe": transaction.is_rollback_safe,
            "warning": transaction.rollback_warning,
            "state_changes": {
                pkg: {
                    "before": transaction.before_state.get(pkg, PackageState(pkg)).to_dict(),
                    "after": transaction.after_state.get(pkg, PackageState(pkg)).to_dict(),
                }
                for pkg in transaction.packages
            },
        }

    def undo(
        self, transaction_id: str, dry_run: bool = False, force: bool = False
    ) -> dict[str, Any]:
        """
        Undo a transaction.

        Args:
            transaction_id: ID of transaction to undo
            dry_run: If True, only show what would be done
            force: If True, ignore safety warnings

        Returns:
            Dict with result of undo operation
        """
        can_undo, reason = self.can_undo(transaction_id)

        transaction = self.history.get_transaction(transaction_id)

        if not transaction:
            return {"success": False, "error": "Transaction not found"}

        if not can_undo and not force:
            return {"success": False, "error": reason}

        if not transaction.is_rollback_safe and not force:
            return {
                "success": False,
                "error": "Unsafe rollback - use force=True to override",
                "warning": transaction.rollback_warning,
            }

        result = {
            "transaction_id": transaction_id,
            "commands": transaction.rollback_commands,
            "dry_run": dry_run,
        }

        if dry_run:
            result["success"] = True
            result["message"] = "Dry run - no changes made"
            return result

        # Execute rollback commands
        errors = []
        for cmd in transaction.rollback_commands:
            if cmd.startswith("#"):
                continue  # Skip comments

            try:
                proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if proc.returncode != 0:
                    errors.append(f"{cmd}: {proc.stderr}")
            except Exception as e:
                errors.append(f"{cmd}: {str(e)}")

        if errors:
            result["success"] = False
            result["errors"] = errors
            transaction.status = TransactionStatus.PARTIALLY_COMPLETED
        else:
            result["success"] = True
            result["message"] = "Rollback completed successfully"
            transaction.status = TransactionStatus.ROLLED_BACK

        # Save updated status
        self.history._save_transaction(transaction)

        return result

    def undo_last(self, dry_run: bool = False) -> dict[str, Any]:
        """Undo the most recent successful transaction."""
        recent = self.history.get_recent(limit=1, status_filter=TransactionStatus.COMPLETED)

        if not recent:
            return {"success": False, "error": "No completed transactions to undo"}

        return self.undo(recent[0].id, dry_run=dry_run)


# Global instances for easy access (thread-safe singletons)
_history_instance = None
_history_lock = threading.Lock()
_undo_manager_instance = None
_undo_manager_lock = threading.Lock()


def get_history() -> "TransactionHistory":
    """Get the global transaction history instance (thread-safe)."""
    global _history_instance
    # Fast path: avoid lock if already initialized
    if _history_instance is None:
        with _history_lock:
            # Double-checked locking pattern
            if _history_instance is None:
                _history_instance = TransactionHistory()
    return _history_instance


def get_undo_manager() -> "UndoManager":
    """Get the global undo manager instance (thread-safe)."""
    global _undo_manager_instance
    # Fast path: avoid lock if already initialized
    if _undo_manager_instance is None:
        with _undo_manager_lock:
            # Double-checked locking pattern
            if _undo_manager_instance is None:
                _undo_manager_instance = UndoManager(get_history())
    return _undo_manager_instance


def record_install(packages: list[str], command: str = "") -> Transaction:
    """Record an install operation."""
    history = get_history()
    return history.begin_transaction(TransactionType.INSTALL, packages, command)


def record_remove(packages: list[str], command: str = "") -> Transaction:
    """Record a remove operation."""
    history = get_history()
    return history.begin_transaction(TransactionType.REMOVE, packages, command)


def show_history(limit: int = 10) -> list[dict[str, Any]]:
    """Show recent transaction history."""
    history = get_history()
    transactions = history.get_recent(limit)
    return [t.to_dict() for t in transactions]


def undo_last(dry_run: bool = False) -> dict[str, Any]:
    """Undo the last transaction."""
    manager = get_undo_manager()
    return manager.undo_last(dry_run)


if __name__ == "__main__":
    # Demo
    print("Transaction History Demo")
    print("=" * 50)

    history = TransactionHistory()
    undo_manager = UndoManager(history)

    # Simulate an install transaction
    print("\n1. Recording install transaction...")
    tx = history.begin_transaction(
        TransactionType.INSTALL, ["nginx", "redis"], "cortex install nginx redis"
    )
    print(f"   Transaction ID: {tx.id}")
    print(f"   Packages: {tx.packages}")

    # Complete the transaction
    history.complete_transaction(tx, success=True)
    print(f"   Status: {tx.status.value}")
    print(f"   Rollback commands: {tx.rollback_commands}")

    # Show history
    print("\n2. Transaction History:")
    for t in history.get_recent(5):
        print(
            f"   {t.timestamp.strftime('%Y-%m-%d %H:%M')} | {t.transaction_type.value:10} | {', '.join(t.packages)}"
        )

    # Preview undo
    print("\n3. Preview Undo:")
    preview = undo_manager.preview_undo(tx.id)
    print(f"   Commands to execute: {preview['commands']}")
    print(f"   Safe to undo: {preview['is_safe']}")

    # Show stats
    print("\n4. Statistics:")
    stats = history.get_stats()
    print(f"   Total transactions: {stats['total_transactions']}")
    print(f"   By type: {stats['by_type']}")

    print("\n✅ Demo complete!")
