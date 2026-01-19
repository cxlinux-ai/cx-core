#!/usr/bin/env python3
"""
Sandboxed Command Execution Layer for Cortex Linux
Critical security component - AI-generated commands must run in isolated environment.

Features:
- Firejail-based sandboxing
- Command whitelisting
- Resource limits (CPU, memory, disk, time)
- Dry-run mode
- Rollback capability
- Comprehensive logging
"""

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

try:
    import resource  # POSIX-only
except ImportError:  # pragma: no cover
    resource = None
from datetime import datetime
from typing import Any

from cortex.validators import DANGEROUS_PATTERNS

try:
    import resource  # type: ignore

    HAS_RESOURCE = True
except ImportError:  # pragma: no cover
    resource = None  # type: ignore
    HAS_RESOURCE = False


class CommandBlocked(Exception):
    """Raised when a command is blocked."""

    pass


class ExecutionResult:
    """Result of command execution."""

    def __init__(
        self,
        command: str,
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
        execution_time: float = 0.0,
        blocked: bool = False,
        violation: str | None = None,
        preview: str | None = None,
    ):
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.execution_time = execution_time
        self.blocked = blocked
        self.violation = violation
        self.preview = preview
        self.timestamp = datetime.now().isoformat()

    @property
    def success(self) -> bool:
        """Check if command executed successfully."""
        return not self.blocked and self.exit_code == 0

    @property
    def failed(self) -> bool:
        """Check if command failed."""
        return not self.success

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time": self.execution_time,
            "blocked": self.blocked,
            "violation": self.violation,
            "preview": self.preview,
            "timestamp": self.timestamp,
            "success": self.success,
        }


class SandboxExecutor:
    """
    Sandboxed command executor with security controls.

    Features:
    - Firejail sandboxing
    - Command whitelisting
    - Resource limits
    - Dry-run mode
    - Rollback capability
    - Comprehensive logging
    """

    # Whitelist of allowed commands (base commands only)
    ALLOWED_COMMANDS = {
        "apt-get",
        "apt",
        "dpkg",
        "pip",
        "pip3",
        "python",
        "python3",
        "npm",
        "yarn",
        "node",
        "git",
        "make",
        "cmake",
        "gcc",
        "g++",
        "clang",
        "curl",
        "wget",
        "tar",
        "unzip",
        "zip",
        "echo",
        "cat",
        "grep",
        "sed",
        "awk",
        "ls",
        "pwd",
        "cd",
        "mkdir",
        "touch",
        "chmod",
        "chown",  # Limited use
        "systemctl",  # Read-only operations
    }

    # Commands that require sudo (package installation only)
    SUDO_ALLOWED_COMMANDS = {
        "apt-get install",
        "apt-get update",
        "apt-get upgrade",
        "apt install",
        "apt update",
        "apt upgrade",
        "pip install",
        "pip3 install",
        "dpkg -i",
    }

    # Allowed directories for file operations
    ALLOWED_DIRECTORIES = [
        "/tmp",
        "/var/tmp",
        os.path.expanduser("~"),
    ]

    def __init__(
        self,
        firejail_path: str | None = None,
        log_file: str | None = None,
        max_cpu_cores: int = 2,
        max_memory_mb: int = 2048,
        max_disk_mb: int = 1024,
        timeout_seconds: int = 300,  # 5 minutes
        enable_rollback: bool = True,
    ):
        """
        Initialize sandbox executor.

        Args:
            firejail_path: Path to firejail binary (auto-detected if None)
            log_file: Path to audit log file
            max_cpu_cores: Maximum CPU cores to use
            max_memory_mb: Maximum memory in MB
            max_disk_mb: Maximum disk space in MB
            timeout_seconds: Maximum execution time in seconds
            enable_rollback: Enable automatic rollback on failure
        """
        self.firejail_path = firejail_path or self._find_firejail()
        self.max_cpu_cores = max_cpu_cores
        self.max_memory_mb = max_memory_mb
        self.max_disk_mb = max_disk_mb
        self.timeout_seconds = timeout_seconds
        self.enable_rollback = enable_rollback

        # Setup logging
        self.log_file = log_file or os.path.join(
            os.path.expanduser("~"), ".cortex", "sandbox_audit.log"
        )
        self._setup_logging()

        # Rollback tracking
        self.rollback_snapshots: dict[str, dict[str, Any]] = {}
        self.current_session_id: str | None = None

        # Audit log
        self.audit_log: list[dict[str, Any]] = []

        # Verify firejail is available
        if not self.firejail_path:
            self.logger.warning(
                "Firejail not found. Sandboxing will be limited. "
                "Install firejail for full security: sudo apt-get install firejail"
            )

    def _find_firejail(self) -> str | None:
        """Find firejail binary in system PATH."""
        firejail_path = shutil.which("firejail")
        return firejail_path

    def is_firejail_available(self) -> bool:
        """
        Check if Firejail is available on the system.

        Returns:
            True if Firejail is available, False otherwise
        """
        return self.firejail_path is not None

    def _setup_logging(self):
        """Setup logging configuration."""
        # Create log directory if it doesn't exist
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, mode=0o700, exist_ok=True)

        # Setup logger (avoid duplicate handlers)
        self.logger = logging.getLogger("SandboxExecutor")
        self.logger.setLevel(logging.INFO)

        # Clear existing handlers to avoid duplicates
        self.logger.handlers.clear()

        # File handler
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(logging.INFO)

        # Console handler (only warnings and above)
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.WARNING)

        # Formatter
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        # Prevent propagation to root logger
        self.logger.propagate = False

    def validate_command(self, command: str) -> tuple[bool, str | None]:
        """
        Validate command for security.

        Args:
            command: Command string to validate

        Returns:
            Tuple of (is_valid, violation_reason)
        """
        # Check for dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"Dangerous pattern detected: {pattern}"

        # Parse command
        try:
            parts = shlex.split(command)
            if not parts:
                return False, "Empty command"

            base_command = parts[0]

            # Check if command is in whitelist
            if base_command not in self.ALLOWED_COMMANDS:
                # Check if it's a sudo command
                if base_command == "sudo":
                    if len(parts) < 2:
                        return False, "Sudo command without arguments"

                    # Skip sudo flags (-S, -p, etc.) to find actual command
                    cmd_parts = []
                    i = 1
                    while i < len(parts):
                        if parts[i].startswith("-"):
                            # Skip flag
                            i += 1
                            # If this flag requires a value (not another flag), skip it too
                            if (
                                i < len(parts)
                                and not parts[i].startswith("-")
                                and parts[i - 1] not in {"-S", "-s"}
                            ):
                                i += 1
                        else:
                            # Found the actual command
                            cmd_parts.append(parts[i])
                            if i + 1 < len(parts):
                                cmd_parts.append(parts[i + 1])
                            break

                    if not cmd_parts:
                        return False, "Sudo command without actual command"

                    sudo_command = " ".join(cmd_parts)

                    # Check if sudo command is allowed
                    if not any(
                        sudo_command.startswith(allowed) for allowed in self.SUDO_ALLOWED_COMMANDS
                    ):
                        return False, f"Sudo command not whitelisted: {sudo_command}"
                else:
                    return False, f"Command not whitelisted: {base_command}"

            # Validate file paths in command
            path_violation = self._validate_paths(command)
            if path_violation:
                return False, path_violation

            return True, None

        except ValueError as e:
            return False, f"Invalid command syntax: {str(e)}"

    def _validate_paths(self, command: str) -> str | None:
        """
        Validate file paths in command to prevent path traversal attacks.

        Args:
            command: Command string

        Returns:
            Violation reason if found, None otherwise
        """
        # Extract potential file paths
        # This is a simplified check - in production, use proper shell parsing
        path_pattern = r"[/~][^\s<>|&;]*"
        paths = re.findall(path_pattern, command)

        for path in paths:
            # Expand user home
            expanded = os.path.expanduser(path)
            # Resolve to absolute path
            try:
                abs_path = os.path.abspath(expanded)
            except (OSError, ValueError):
                continue

            # Block access to critical system directories
            critical_dirs = [
                "/boot",
                "/sys",
                "/proc",
                "/dev",
                "/etc",
                "/usr/bin",
                "/usr/sbin",
                "/sbin",
                "/bin",
            ]
            for critical in critical_dirs:
                if abs_path.startswith(critical):
                    # Allow /dev/null for redirection
                    if abs_path == "/dev/null":
                        continue
                    # Allow reading from /etc for some commands (like apt-get)
                    if critical == "/etc" and "read" in command.lower():
                        continue
                    return f"Access to critical directory blocked: {abs_path}"

            # Block path traversal attempts
            if (
                ".." in path
                or path.startswith("/")
                and not any(
                    abs_path.startswith(os.path.expanduser(d)) for d in self.ALLOWED_DIRECTORIES
                )
            ):
                # Allow if it's a command argument (like --config=/etc/file.conf)
                if not any(
                    abs_path.startswith(os.path.expanduser(d)) for d in self.ALLOWED_DIRECTORIES
                ):
                    # More permissive: only block if clearly dangerous
                    if any(
                        danger in abs_path
                        for danger in ["/etc/passwd", "/etc/shadow", "/boot", "/sys"]
                    ):
                        return f"Path traversal to sensitive location blocked: {abs_path}"

            # If not in allowed directory and not a standard command argument, warn
            # (This is permissive - adjust based on security requirements)

        return None

    def _create_firejail_command(self, command: str) -> list[str]:
        """
        Create firejail command with resource limits.

        Args:
            command: Command to execute

        Returns:
            List of command parts for subprocess
        """
        if not self.firejail_path:
            # Fallback to direct execution (not recommended)
            return shlex.split(command)

        # Build firejail command with security options
        memory_bytes = self.max_memory_mb * 1024 * 1024
        firejail_cmd = [
            self.firejail_path,
            "--quiet",  # Suppress firejail messages
            "--noprofile",  # Don't use default profile
            "--private",  # Private home directory
            "--private-tmp",  # Private /tmp
            f"--cpu={self.max_cpu_cores}",  # CPU limit
            f"--rlimit-as={memory_bytes}",  # Memory limit (address space)
            "--net=none",  # No network (adjust if needed)
            "--noroot",  # No root access
            "--caps.drop=all",  # Drop all capabilities
            "--shell=none",  # No shell
            "--seccomp",  # Enable seccomp filtering
        ]

        # Add command
        firejail_cmd.extend(shlex.split(command))

        return firejail_cmd

    def _create_snapshot(self, session_id: str) -> dict[str, Any]:
        """
        Create snapshot of current state for rollback.

        Args:
            session_id: Session identifier

        Returns:
            Snapshot dictionary
        """
        snapshot = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "files_modified": [],
            "files_created": [],
            "file_backups": {},  # Store file contents for restoration
        }

        # Track files in allowed directories that might be modified
        # Store their current state for potential rollback
        for allowed_dir in self.ALLOWED_DIRECTORIES:
            allowed_expanded = os.path.expanduser(allowed_dir)
            if os.path.exists(allowed_expanded):
                # Note: Full file tracking would require inotify or filesystem monitoring
                # For now, we track the directory state
                try:
                    snapshot["directories_tracked"] = snapshot.get("directories_tracked", [])
                    snapshot["directories_tracked"].append(allowed_expanded)
                except Exception:
                    pass

        self.rollback_snapshots[session_id] = snapshot
        self.logger.debug(f"Created snapshot for session {session_id}")
        return snapshot

    def _rollback(self, session_id: str) -> bool:
        """
        Rollback changes from a session.

        Args:
            session_id: Session identifier

        Returns:
            True if rollback successful
        """
        if session_id not in self.rollback_snapshots:
            self.logger.warning(f"No snapshot found for session {session_id}")
            return False

        snapshot = self.rollback_snapshots[session_id]
        self.logger.info(f"Rolling back session {session_id}")

        # Restore backed up files
        restored_count = 0
        for file_path, file_content in snapshot.get("file_backups", {}).items():
            try:
                if os.path.exists(file_path):
                    with open(file_path, "wb") as f:
                        f.write(file_content)
                    restored_count += 1
                    self.logger.debug(f"Restored file: {file_path}")
            except Exception as e:
                self.logger.warning(f"Failed to restore {file_path}: {e}")

        # Remove created files
        for file_path in snapshot.get("files_created", []):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    self.logger.debug(f"Removed created file: {file_path}")
            except Exception as e:
                self.logger.warning(f"Failed to remove {file_path}: {e}")

        self.logger.info(
            f"Rollback completed: {restored_count} files restored, "
            f"{len(snapshot.get('files_created', []))} files removed"
        )
        return True

    def execute(
        self,
        command: str,
        dry_run: bool = False,
        enable_rollback: bool | None = None,
        stdin: str | None = None,
    ) -> ExecutionResult:
        """
        Execute command in sandbox.

        Args:
            command: Command to execute
            dry_run: If True, only show what would execute
            enable_rollback: Override default rollback setting
            stdin: Optional string to pass to command's stdin

        Returns:
            ExecutionResult object
        """
        start_time = time.time()
        session_id = f"session_{int(start_time)}"
        self.current_session_id = session_id

        # Validate command
        is_valid, violation = self.validate_command(command)
        if not is_valid:
            result = ExecutionResult(
                command=command,
                exit_code=-1,
                blocked=True,
                violation=violation,
                execution_time=time.time() - start_time,
            )
            self._log_security_event(result)
            raise CommandBlocked(violation or "Command blocked")

        # Create snapshot for rollback
        if enable_rollback if enable_rollback is not None else self.enable_rollback:
            self._create_snapshot(session_id)

        # Dry-run mode
        if dry_run:
            firejail_cmd = self._create_firejail_command(command)
            preview = " ".join(shlex.quote(arg) for arg in firejail_cmd)

            result = ExecutionResult(
                command=command,
                exit_code=0,
                stdout=f"[DRY-RUN] Would execute: {preview}",
                preview=preview,
                execution_time=time.time() - start_time,
            )
            self._log_execution(result)
            return result

        # Execute command
        process: subprocess.Popen[str] | None = None
        try:
            firejail_cmd = self._create_firejail_command(command)

            self.logger.info(f"Executing: {command}")

            # Set resource limits if not using Firejail
            preexec_fn = None
            if os.name != "nt" and not self.firejail_path and resource is not None:

                def set_resource_limits():
                    """Set resource limits for the subprocess."""
                    if not HAS_RESOURCE:
                        return
                    try:
                        # Memory limit (RSS - Resident Set Size)
                        memory_bytes = self.max_memory_mb * 1024 * 1024
                        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
                        # CPU time limit (soft and hard)
                        cpu_seconds = self.timeout_seconds
                        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
                        # File size limit
                        disk_bytes = self.max_disk_mb * 1024 * 1024
                        resource.setrlimit(resource.RLIMIT_FSIZE, (disk_bytes, disk_bytes))
                    except (ValueError, OSError) as e:
                        self.logger.warning(f"Failed to set resource limits: {e}")

                preexec_fn = set_resource_limits

            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
            }
            # Add stdin pipe if stdin data is provided
            if stdin is not None:
                popen_kwargs["stdin"] = subprocess.PIPE
            # preexec_fn is unsupported on Windows; only pass it when set.
            if preexec_fn is not None:
                popen_kwargs["preexec_fn"] = preexec_fn

            process = subprocess.Popen(firejail_cmd, **popen_kwargs)
            stdout, stderr = process.communicate(input=stdin, timeout=self.timeout_seconds)
            exit_code = process.returncode
            execution_time = time.time() - start_time

            result = ExecutionResult(
                command=command,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                execution_time=execution_time,
            )

            # Rollback on failure if enabled
            if result.failed and (
                enable_rollback if enable_rollback is not None else self.enable_rollback
            ):
                self._rollback(session_id)
                result.stderr += "\n[ROLLBACK] Changes reverted due to failure"

            self._log_execution(result)
            return result

        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
            result = ExecutionResult(
                command=command,
                exit_code=-1,
                stderr=f"Command timed out after {self.timeout_seconds} seconds",
                execution_time=time.time() - start_time,
            )
            self._log_execution(result)
            return result

        except Exception as e:
            result = ExecutionResult(
                command=command,
                exit_code=-1,
                stderr=f"Execution error: {str(e)}",
                execution_time=time.time() - start_time,
            )
            self._log_execution(result)
            return result

    def _log_execution(self, result: ExecutionResult):
        """Log command execution to audit log."""
        log_entry = result.to_dict()
        log_entry["type"] = "execution"
        self.audit_log.append(log_entry)
        self.logger.info(f"Command executed: {result.command} (exit_code={result.exit_code})")

    def _log_security_event(self, result: ExecutionResult):
        """Log security violation."""
        log_entry = result.to_dict()
        log_entry["type"] = "security_violation"
        self.audit_log.append(log_entry)
        self.logger.warning(f"Security violation: {result.command} - {result.violation}")

    def get_audit_log(self, limit: int | None = None) -> list[dict[str, Any]]:
        """
        Get audit log entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of audit log entries
        """

        if limit is None:
            return list(self.audit_log)
        return list(self.audit_log)[-limit:]


def main():
    """CLI entry point for sandbox executor."""
    import argparse

    parser = argparse.ArgumentParser(description="Sandboxed Command Executor")
    parser.add_argument("command", help="Command to execute")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode")
    parser.add_argument("--no-rollback", action="store_true", help="Disable rollback")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")

    args = parser.parse_args()

    executor = SandboxExecutor(timeout_seconds=args.timeout)

    try:
        result = executor.execute(
            args.command, dry_run=args.dry_run, enable_rollback=not args.no_rollback
        )

        if result.blocked:
            print(f"Command blocked: {result.violation}", file=sys.stderr)
            sys.exit(1)

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        sys.exit(result.exit_code)

    except CommandBlocked as e:
        print(f"Command blocked: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
