"""Database module for storing do run history."""

import datetime
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from rich.console import Console

from .models import CommandLog, CommandStatus, DoRun, RunMode

console = Console()


class DoRunDatabase:
    """SQLite database for storing do run history."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or Path.home() / ".cortex" / "do_runs.db"
        self._ensure_directory()
        self._init_db()

    def _ensure_directory(self):
        """Ensure the database directory exists with proper permissions."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            if not os.access(self.db_path.parent, os.W_OK):
                raise OSError(f"Directory {self.db_path.parent} is not writable")
        except OSError:
            alt_path = Path("/tmp") / ".cortex" / "do_runs.db"
            alt_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = alt_path
            console.print(
                f"[yellow]Warning: Using alternate database path: {self.db_path}[/yellow]"
            )

    def _init_db(self):
        """Initialize the database schema."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS do_runs (
                        run_id TEXT PRIMARY KEY,
                        session_id TEXT,
                        summary TEXT NOT NULL,
                        commands_log TEXT NOT NULL,
                        commands_list TEXT,
                        mode TEXT NOT NULL,
                        user_query TEXT,
                        started_at TEXT,
                        completed_at TEXT,
                        files_accessed TEXT,
                        privileges_granted TEXT,
                        full_data TEXT,
                        total_commands INTEGER DEFAULT 0,
                        successful_commands INTEGER DEFAULT 0,
                        failed_commands INTEGER DEFAULT 0,
                        skipped_commands INTEGER DEFAULT 0
                    )
                """)

                # Create sessions table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS do_sessions (
                        session_id TEXT PRIMARY KEY,
                        started_at TEXT,
                        ended_at TEXT,
                        total_runs INTEGER DEFAULT 0,
                        total_queries TEXT
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS do_run_commands (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL,
                        command_index INTEGER NOT NULL,
                        command TEXT NOT NULL,
                        purpose TEXT,
                        status TEXT NOT NULL,
                        output_truncated TEXT,
                        error_truncated TEXT,
                        duration_seconds REAL DEFAULT 0,
                        timestamp TEXT,
                        useful INTEGER DEFAULT 1,
                        FOREIGN KEY (run_id) REFERENCES do_runs(run_id)
                    )
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_do_runs_started
                    ON do_runs(started_at DESC)
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_do_run_commands_run_id
                    ON do_run_commands(run_id)
                """)

                self._migrate_schema(conn)
                conn.commit()
        except sqlite3.OperationalError as e:
            raise OSError(f"Failed to initialize database at {self.db_path}: {e}")

    def _migrate_schema(self, conn: sqlite3.Connection):
        """Add new columns to existing tables if they don't exist."""
        cursor = conn.execute("PRAGMA table_info(do_runs)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        new_columns = [
            ("total_commands", "INTEGER DEFAULT 0"),
            ("successful_commands", "INTEGER DEFAULT 0"),
            ("failed_commands", "INTEGER DEFAULT 0"),
            ("skipped_commands", "INTEGER DEFAULT 0"),
            ("commands_list", "TEXT"),
            ("session_id", "TEXT"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                try:
                    conn.execute(f"ALTER TABLE do_runs ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass

        cursor = conn.execute("""
            SELECT run_id, full_data FROM do_runs
            WHERE total_commands IS NULL OR total_commands = 0 OR commands_list IS NULL
        """)

        for row in cursor.fetchall():
            run_id = row[0]
            try:
                full_data = json.loads(row[1]) if row[1] else {}
                commands = full_data.get("commands", [])
                total = len(commands)
                success = sum(1 for c in commands if c.get("status") == "success")
                failed = sum(1 for c in commands if c.get("status") == "failed")
                skipped = sum(1 for c in commands if c.get("status") == "skipped")

                commands_list = json.dumps([c.get("command", "") for c in commands])

                conn.execute(
                    """
                    UPDATE do_runs SET
                        total_commands = ?,
                        successful_commands = ?,
                        failed_commands = ?,
                        skipped_commands = ?,
                        commands_list = ?
                    WHERE run_id = ?
                """,
                    (total, success, failed, skipped, commands_list, run_id),
                )

                for idx, cmd in enumerate(commands):
                    exists = conn.execute(
                        "SELECT 1 FROM do_run_commands WHERE run_id = ? AND command_index = ?",
                        (run_id, idx),
                    ).fetchone()

                    if not exists:
                        output = cmd.get("output", "")[:250] if cmd.get("output") else ""
                        error = cmd.get("error", "")[:250] if cmd.get("error") else ""
                        conn.execute(
                            """
                            INSERT INTO do_run_commands
                            (run_id, command_index, command, purpose, status,
                             output_truncated, error_truncated, duration_seconds, timestamp, useful)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                run_id,
                                idx,
                                cmd.get("command", ""),
                                cmd.get("purpose", ""),
                                cmd.get("status", "pending"),
                                output,
                                error,
                                cmd.get("duration_seconds", 0),
                                cmd.get("timestamp", ""),
                                1 if cmd.get("useful", True) else 0,
                            ),
                        )
            except (json.JSONDecodeError, KeyError):
                pass

    def _generate_run_id(self) -> str:
        """Generate a unique run ID."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
        random_part = hashlib.sha256(os.urandom(16)).hexdigest()[:8]
        return f"do_{timestamp}_{random_part}"

    def _truncate_output(self, text: str, max_length: int = 250) -> str:
        """Truncate output to specified length."""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return text[:max_length] + "... [truncated]"

    def save_run(self, run: DoRun) -> str:
        """Save a do run to the database with detailed command information."""
        if not run.run_id:
            run.run_id = self._generate_run_id()

        commands_log = run.get_commands_log_string()

        total_commands = len(run.commands)
        successful_commands = sum(1 for c in run.commands if c.status == CommandStatus.SUCCESS)
        failed_commands = sum(1 for c in run.commands if c.status == CommandStatus.FAILED)
        skipped_commands = sum(1 for c in run.commands if c.status == CommandStatus.SKIPPED)

        commands_list = json.dumps([cmd.command for cmd in run.commands])

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO do_runs
                (run_id, session_id, summary, commands_log, commands_list, mode, user_query, started_at,
                 completed_at, files_accessed, privileges_granted, full_data,
                 total_commands, successful_commands, failed_commands, skipped_commands)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    run.run_id,
                    run.session_id or None,
                    run.summary,
                    commands_log,
                    commands_list,
                    run.mode.value,
                    run.user_query,
                    run.started_at,
                    run.completed_at,
                    json.dumps(run.files_accessed),
                    json.dumps(run.privileges_granted),
                    json.dumps(run.to_dict()),
                    total_commands,
                    successful_commands,
                    failed_commands,
                    skipped_commands,
                ),
            )

            conn.execute("DELETE FROM do_run_commands WHERE run_id = ?", (run.run_id,))

            for idx, cmd in enumerate(run.commands):
                conn.execute(
                    """
                    INSERT INTO do_run_commands
                    (run_id, command_index, command, purpose, status,
                     output_truncated, error_truncated, duration_seconds, timestamp, useful)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        run.run_id,
                        idx,
                        cmd.command,
                        cmd.purpose,
                        cmd.status.value,
                        self._truncate_output(cmd.output, 250),
                        self._truncate_output(cmd.error, 250),
                        cmd.duration_seconds,
                        cmd.timestamp,
                        1 if cmd.useful else 0,
                    ),
                )

            conn.commit()

        return run.run_id

    def get_run(self, run_id: str) -> DoRun | None:
        """Get a specific run by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM do_runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()

            if row:
                full_data = json.loads(row["full_data"])
                run = DoRun(
                    run_id=full_data["run_id"],
                    summary=full_data["summary"],
                    mode=RunMode(full_data["mode"]),
                    commands=[CommandLog.from_dict(c) for c in full_data["commands"]],
                    started_at=full_data.get("started_at", ""),
                    completed_at=full_data.get("completed_at", ""),
                    user_query=full_data.get("user_query", ""),
                    files_accessed=full_data.get("files_accessed", []),
                    privileges_granted=full_data.get("privileges_granted", []),
                    session_id=row["session_id"] if "session_id" in row.keys() else "",
                )
                return run
        return None

    def get_run_commands(self, run_id: str) -> list[dict[str, Any]]:
        """Get detailed command information for a run."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT command_index, command, purpose, status,
                       output_truncated, error_truncated, duration_seconds, timestamp, useful
                FROM do_run_commands
                WHERE run_id = ?
                ORDER BY command_index
            """,
                (run_id,),
            )

            commands = []
            for row in cursor:
                commands.append(
                    {
                        "index": row["command_index"],
                        "command": row["command"],
                        "purpose": row["purpose"],
                        "status": row["status"],
                        "output": row["output_truncated"],
                        "error": row["error_truncated"],
                        "duration": row["duration_seconds"],
                        "timestamp": row["timestamp"],
                        "useful": bool(row["useful"]),
                    }
                )
            return commands

    def get_run_stats(self, run_id: str) -> dict[str, Any] | None:
        """Get command statistics for a run."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT run_id, summary, total_commands, successful_commands,
                       failed_commands, skipped_commands, started_at, completed_at
                FROM do_runs WHERE run_id = ?
            """,
                (run_id,),
            )
            row = cursor.fetchone()

            if row:
                return {
                    "run_id": row["run_id"],
                    "summary": row["summary"],
                    "total_commands": row["total_commands"] or 0,
                    "successful_commands": row["successful_commands"] or 0,
                    "failed_commands": row["failed_commands"] or 0,
                    "skipped_commands": row["skipped_commands"] or 0,
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                }
        return None

    def get_commands_list(self, run_id: str) -> list[str]:
        """Get just the list of commands for a run."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT commands_list FROM do_runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()

            if row and row["commands_list"]:
                try:
                    return json.loads(row["commands_list"])
                except (json.JSONDecodeError, TypeError):
                    pass

            cursor = conn.execute(
                "SELECT command FROM do_run_commands WHERE run_id = ? ORDER BY command_index",
                (run_id,),
            )
            return [row["command"] for row in cursor.fetchall()]

    def get_recent_runs(self, limit: int = 20) -> list[DoRun]:
        """Get recent do runs."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT full_data, session_id FROM do_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            runs = []
            for row in cursor:
                full_data = json.loads(row["full_data"])
                run = DoRun(
                    run_id=full_data["run_id"],
                    summary=full_data["summary"],
                    mode=RunMode(full_data["mode"]),
                    commands=[CommandLog.from_dict(c) for c in full_data["commands"]],
                    started_at=full_data.get("started_at", ""),
                    completed_at=full_data.get("completed_at", ""),
                    user_query=full_data.get("user_query", ""),
                    files_accessed=full_data.get("files_accessed", []),
                    privileges_granted=full_data.get("privileges_granted", []),
                )
                run.session_id = row["session_id"]
                runs.append(run)
            return runs

    def create_session(self) -> str:
        """Create a new session and return the session ID."""
        session_id = f"session_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}_{hashlib.md5(str(datetime.datetime.now().timestamp()).encode()).hexdigest()[:8]}"

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO do_sessions (session_id, started_at, total_runs, total_queries)
                   VALUES (?, ?, 0, '[]')""",
                (session_id, datetime.datetime.now().isoformat()),
            )
            conn.commit()

        return session_id

    def update_session(
        self, session_id: str, query: str | None = None, increment_runs: bool = False
    ):
        """Update a session with new query or run count."""
        with sqlite3.connect(str(self.db_path)) as conn:
            if increment_runs:
                conn.execute(
                    "UPDATE do_sessions SET total_runs = total_runs + 1 WHERE session_id = ?",
                    (session_id,),
                )

            if query:
                # Get current queries
                cursor = conn.execute(
                    "SELECT total_queries FROM do_sessions WHERE session_id = ?", (session_id,)
                )
                row = cursor.fetchone()
                if row:
                    queries = json.loads(row[0]) if row[0] else []
                    queries.append(query)
                    conn.execute(
                        "UPDATE do_sessions SET total_queries = ? WHERE session_id = ?",
                        (json.dumps(queries), session_id),
                    )

            conn.commit()

    def end_session(self, session_id: str):
        """Mark a session as ended."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE do_sessions SET ended_at = ? WHERE session_id = ?",
                (datetime.datetime.now().isoformat(), session_id),
            )
            conn.commit()

    def get_session_runs(self, session_id: str) -> list[DoRun]:
        """Get all runs in a session."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT full_data FROM do_runs WHERE session_id = ? ORDER BY started_at ASC",
                (session_id,),
            )
            runs = []
            for row in cursor:
                full_data = json.loads(row["full_data"])
                run = DoRun(
                    run_id=full_data["run_id"],
                    summary=full_data["summary"],
                    mode=RunMode(full_data["mode"]),
                    commands=[CommandLog.from_dict(c) for c in full_data["commands"]],
                    started_at=full_data.get("started_at", ""),
                    completed_at=full_data.get("completed_at", ""),
                    user_query=full_data.get("user_query", ""),
                )
                run.session_id = session_id
                runs.append(run)
            return runs

    def get_recent_sessions(self, limit: int = 10) -> list[dict]:
        """Get recent sessions with their run counts."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT session_id, started_at, ended_at, total_runs, total_queries
                   FROM do_sessions ORDER BY started_at DESC LIMIT ?""",
                (limit,),
            )
            sessions = []
            for row in cursor:
                sessions.append(
                    {
                        "session_id": row["session_id"],
                        "started_at": row["started_at"],
                        "ended_at": row["ended_at"],
                        "total_runs": row["total_runs"],
                        "queries": json.loads(row["total_queries"]) if row["total_queries"] else [],
                    }
                )
            return sessions
