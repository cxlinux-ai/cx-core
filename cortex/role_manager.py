import json
import logging
import os
import re
import shlex
import shutil
import sqlite3
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import TypedDict

# Explicit type annotation for modules to satisfy type checkers.
# fcntl is used for POSIX advisory locking on Unix-like systems.
fcntl: ModuleType | None = None
try:
    import fcntl
except ImportError:
    fcntl = None

# msvcrt is used for Windows byte-range locking on Windows platforms.
msvcrt: ModuleType | None = None
if sys.platform == "win32":
    try:
        import msvcrt
    except ImportError:
        msvcrt = None

logger = logging.getLogger(__name__)


class SystemContext(TypedDict):
    """Structured type representing core system architectural facts."""

    binaries: list[str]
    has_gpu: bool
    patterns: list[str]
    active_role: str
    has_install_history: bool


class RoleManager:
    """
    Provides system context for LLM-driven role detection and recommendations.

    Serves as the 'sensing layer' for the system architect. It aggregates factual
    signals (binary presence, hardware capabilities, and sanitized shell patterns)
    to provide a synchronized ground truth for AI inference.
    """

    CONFIG_KEY = "CORTEX_SYSTEM_ROLE"

    _SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
        re.compile(p)
        for p in [
            r"(?i)api[-_]?key\s*[:=]\s*[^\s]+",
            r"(?i)token\s*[:=]\s*[^\s]+",
            r"(?i)password\s*[:=]\s*[^\s]+",
            r"(?i)passwd\s*[:=]\s*[^\s]+",
            r"(?i)Authorization:\s*[^\s]+",
            r"(?i)Bearer\s+[^\s]+",
            r"(?i)X-Api-Key:\s*[^\s]+",
            r"(?i)-H\s+['\"][^'\"]*auth[^'\"]*['\"]",
            r"(?i)export\s+(?:[^\s]*(?:key|token|secret|password|passwd|credential|auth)[^\s]*)=[^\s]+",
            r"(?i)AWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY)\s*[:=]\s*[^\s]+",
            r"(?i)GOOGLE_APPLICATION_CREDENTIALS\s*[:=]\s*[^\s]+",
            r"(?i)GCP_(?:SERVICE_ACCOUNT|CREDENTIALS)\s*[:=]\s*[^\s]+",
            r"(?i)AZURE_(?:CLIENT_SECRET|TENANT_ID|SUBSCRIPTION_ID)\s*[:=]\s*[^\s]+",
            r"(?i)(?:GITHUB|GITLAB)_TOKEN\s*[:=]\s*[^\s]+",
            r"(?i)docker\s+login.*-p\s+[^\s]+",
            r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            r"(?i)sshpass\s+-p\s+[^\s]+",
            r"(?i)ssh-add.*-k",
            r"(?i)(?:postgres|mysql|mongodb)://[^@\s]+:[^@\s]+@",
        ]
    )

    def __init__(self, env_path: Path | None = None) -> None:
        """
        Initializes the manager and sets the configuration and history paths.

        Args:
            env_path: Optional path to the environment file. If provided, other
                     Cortex metadata (such as history_db) is relocated to the same
                     parent directory for better test isolation.
        """
        if env_path:
            # During tests, use the provided directory as the home directory.
            self.base_dir = env_path.parent
            self.home_path = env_path.parent
        else:
            # Production behavior: use the actual user home directory.
            self.home_path = Path.home()
            self.base_dir = self.home_path / ".cortex"

        self.env_file = env_path or (self.base_dir / ".env")
        self.history_db = self.base_dir / "history.db"

    def _get_shell_patterns(self) -> list[str]:
        """
        Extracts user activity patterns from local shell history while minimizing privacy risk.

        Returns:
            list[str]: A list of sanitized command patterns or intent tokens.
        """
        if os.environ.get("CORTEX_SENSE_HISTORY", "true").lower() == "false":
            return []

        intent_map = {
            "apt": "intent:install",
            "pip": "intent:install",
            "npm": "intent:install",
            "kubectl": "intent:k8s",
            "helm": "intent:k8s",
            "docker": "intent:container",
            "git": "intent:version_control",
            "systemctl": "intent:service_mgmt",
            "python": "intent:execution",
        }

        try:
            all_history_lines: list[str] = []
            for history_file in [".bash_history", ".zsh_history"]:
                path = self.home_path / history_file
                if not path.exists():
                    continue
                # Use errors="replace" to prevent crashes on corrupted UTF-8 or binary data.
                all_history_lines.extend(
                    path.read_text(encoding="utf-8", errors="replace").splitlines()
                )

            trimmed_commands = [line.strip() for line in all_history_lines if line.strip()]
            recent_commands = trimmed_commands[-15:]

            patterns: list[str] = []
            for cmd in recent_commands:
                # Step 1: Strip Zsh extended history metadata (timestamps and durations).
                if cmd.startswith(":") and ";" in cmd:
                    cmd = cmd.split(";", 1)[1].strip()

                # Step 2: Skip local management commands to prevent circular sensing.
                if cmd.startswith("cortex role set"):
                    patterns.append("intent:role_management")
                    continue

                # Step 3: Redact personally identifiable information (PII) using precompiled regex patterns.
                if any(p.search(cmd) for p in self._SENSITIVE_PATTERNS):
                    patterns.append("<redacted>")
                    continue

                # Step 4: Tokenize the command into parts while handling shell quoting.
                try:
                    parts = shlex.split(cmd)
                except ValueError:
                    # Fallback for malformed quoting (e.g., echo "hello without closing quote).
                    parts = cmd.split()

                if not parts:
                    continue

                # Step 5: Privacy - Strip leading environment variable assignments (KEY=val cmd).
                while parts and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", parts[0]):
                    parts.pop(0)

                if not parts:
                    patterns.append("<redacted>")
                    continue

                # Step 6: Data minimization - Extract the verb (basename) from full paths.
                # Handle both Linux (/) and Windows (\) separators to prevent path leaks.
                raw_verb = parts[0].lower()
                normalized_path = raw_verb.replace("\\", "/")
                verb = os.path.basename(normalized_path)

                # Step 7: Map to generalized intent or coarse-grained command token.
                # Map known commands to intents; use a generic token for unknown commands.
                if verb in intent_map:
                    patterns.append(intent_map[verb])
                elif re.fullmatch(r"[a-z0-9_-]{1,20}", verb):
                    # Only include short, simple command names.
                    patterns.append(f"intent:{verb}")
                else:
                    patterns.append("intent:unknown")

            return patterns

        except OSError as e:
            logger.warning("Access denied to shell history during sensing: %s", e)
            return []
        except Exception as e:
            logger.debug("Unexpected error during shell pattern sensing: %s", e)
            return []

    def get_system_context(self) -> SystemContext:
        """
        Aggregates factual system signals and activity patterns for AI inference.

        This serves as the core sensing layer, fulfilling the 'learning from patterns'
        requirement by merging real-time binary detection, shell history analysis,
        and historical installation data from the local database.

        Returns:
            SystemContext: A dictionary containing system binaries, GPU status, patterns,
                          active role, and installation history status.
        """
        signals = [
            "nginx",
            "apache2",
            "docker",
            "psql",
            "mysql",
            "redis-server",
            "nvidia-smi",
            "rocm-smi",
            "intel_gpu_top",
            "conda",
            "jupyter",
            "gcc",
            "make",
            "git",
            "go",
            "node",
            "ansible",
            "terraform",
            "kubectl",
            "rustc",
            "cargo",
            "python3",
        ]

        # Step 1: Hardware and binary sensing.
        detected_binaries = [signal for signal in signals if shutil.which(signal)]
        has_gpu = any(x in detected_binaries for x in ["nvidia-smi", "rocm-smi", "intel_gpu_top"])

        # Step 2: Pattern learning (shell history + installation history).
        # Merge intent tokens from shell history with actual successful package installations.
        shell_patterns = self._get_shell_patterns()
        learned_installations = self._get_learned_patterns()

        # Combine patterns: Technical intents + Explicitly installed packages.
        all_patterns = shell_patterns + learned_installations

        return {
            "binaries": detected_binaries,
            "has_gpu": has_gpu,
            "patterns": all_patterns,
            "active_role": self.get_saved_role() or "undefined",
            # Consider install history present only if we actually found learned data.
            "has_install_history": len(learned_installations) > 0,
        }

    def save_role(self, role_slug: str) -> None:
        """
        Persists the system role identifier using an atomic update pattern
        and records the change in the audit log.

        Args:
            role_slug: The role identifier to save (e.g., 'ml-workstation').

        Raises:
            ValueError: If the role_slug format is invalid.
            RuntimeError: If the role cannot be persisted to the file.
        """
        # Validate the role_slug format before proceeding.
        if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9_-]*[a-zA-Z0-9])?", role_slug):
            logger.error("Invalid role slug rejected: %r", role_slug)
            raise ValueError(f"Invalid role slug format: {role_slug!r}")

        # Step 1: Extract the previous value for audit logging before performing the update.
        old_value = self.get_saved_role() or ""

        def modifier(existing_content: str, key: str, value: str) -> str:
            """
            Internal helper to modify the .env file content string.

            Args:
                existing_content: The current file content.
                key: The configuration key to update.
                value: The new value for the key.

            Returns:
                str: The modified file content.
            """
            pattern = (
                rf"^(\s*(?:export\s+)?{re.escape(key)}\s*=\s*)(['\"]?)(.*?)(['\"]?\s*(?:#.*)?)$"
            )
            matches = list(re.finditer(pattern, existing_content, flags=re.MULTILINE))

            if matches:
                # Target only the last occurrence (shell "last-one-wins" logic).
                last_match = matches[-1]
                start, end = last_match.span()
                new_line = f"{last_match.group(1)}{last_match.group(2)}{value}{last_match.group(4)}"
                return existing_content[:start] + new_line + existing_content[end:]
            else:
                # Append a new key-value pair if not found.
                if existing_content and not existing_content.endswith("\n"):
                    existing_content += "\n"
                return existing_content + f"{key}={value}\n"

        try:
            # Step 2: Perform the atomic file update using the locked write pattern.
            self._locked_read_modify_write(self.CONFIG_KEY, role_slug, modifier)

            # Step 3: Audit logging - Record the change in history.db.
            try:
                # Use self.history_db defined in __init__ for consistency.
                with sqlite3.connect(self.history_db) as conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS role_changes
                        (timestamp TEXT, key TEXT, old_value TEXT, new_value TEXT)
                    """)
                    conn.execute(
                        "INSERT INTO role_changes VALUES (?, ?, ?, ?)",
                        (
                            datetime.now(timezone.utc).isoformat(),
                            self.CONFIG_KEY,
                            old_value,
                            role_slug,
                        ),
                    )
            except Exception as audit_err:
                # Log audit failures but do not block the primary save operation.
                logger.warning("Audit logging failed for role change: %s", audit_err)

        except Exception as e:
            logger.error("Failed to persist system role: %s", e)
            raise RuntimeError(f"Could not persist role to {self.env_file}") from e

    def get_saved_role(self) -> str | None:
        """
        Reads the active role with tolerant parsing for standard shell file formats.

        Returns:
            str | None: The saved role slug, or None if not found or empty.
        """
        if not self.env_file.exists():
            return None

        try:
            # Read content with 'replace' to handle potentially corrupted data.
            content = self.env_file.read_text(encoding="utf-8", errors="replace")

            # Regex captures the value, supporting optional 'export', quotes, and comments.
            pattern = rf"^\s*(?:export\s+)?{re.escape(self.CONFIG_KEY)}\s*=\s*['\"]?(.*?)['\"]?(?:\s*#.*)?$"
            matches = re.findall(pattern, content, re.MULTILINE)

            if not matches:
                return None

            # Follow shell "last-one-wins" logic by taking the last match.
            value = matches[-1].strip()
            return value if value else None
        except Exception as e:
            logger.error("Error reading saved role: %s", e)
            return None

    def _locked_read_modify_write(
        self,
        key: str,
        value: str,
        modifier_func: Callable[[str, str, str], str],
        target_file: Path | None = None,
    ) -> None:
        """
        Performs a thread-safe, atomic file update with cross-platform locking support.

        Implements POSIX advisory locking (fcntl) or Windows byte-range locking (msvcrt).
        Ensures file integrity via a write-to-temporary-and-swap pattern.

        Args:
            key: The configuration key being modified.
            value: The new value for the key.
            modifier_func: A callable that modifies the file content.
            target_file: Optional override for the target file path.
        """
        target = target_file or self.env_file
        target.parent.mkdir(parents=True, exist_ok=True)

        lock_file = target.parent.joinpath(f"{target.name}.lock")
        lock_file.touch(exist_ok=True)
        # Ensure the lock file is not empty for Windows byte-range locking.
        if lock_file.stat().st_size == 0:
            lock_file.write_bytes(b"\0")

        try:
            lock_file.chmod(0o600)
        except OSError:
            pass

        temp_file = target.parent.joinpath(f"{target.name}.tmp")
        try:
            with open(lock_file, "r+") as lock_fd:
                if fcntl:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)
                elif msvcrt:
                    # Windows precision fix: seek(0) to target a stable byte region.
                    lock_fd.seek(0)
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    logger.warning("No file locking backend available (fcntl/msvcrt missing).")

                try:
                    existing = (
                        target.read_text(encoding="utf-8", errors="replace")
                        if target.exists()
                        else ""
                    )
                    updated = modifier_func(existing, key, value)
                    temp_file.write_text(updated, encoding="utf-8")
                    try:
                        temp_file.chmod(0o600)
                    except OSError:
                        pass
                    temp_file.replace(target)
                finally:
                    if fcntl:
                        fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    elif msvcrt:
                        # Windows precision fix: seek(0) before releasing the lock.
                        lock_fd.seek(0)
                        msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            if temp_file.exists():
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    def _get_learned_patterns(self) -> list[str]:
        """
        Extracts successful package installation history from the database.

        This method serves as a 'learning loop' that analyzes previously successful
        installations to provide better AI context. It specifically addresses
        critical schema requirements by parsing JSON package arrays and
        maintaining chronological relevance.

        Returns:
            list[str]: A list of unique signals in the format 'installed:<pkg>',
                       limited to the 5 most recent entries.
        """
        # Ensure the history database exists before attempting to connect.
        if not self.history_db.exists():
            return []

        try:
            # Use a context manager for the connection to ensure proper cleanup
            # even if an exception occurs during processing.
            with sqlite3.connect(self.history_db) as conn:
                cursor = conn.cursor()

                # Check if the 'installations' table exists in the database.
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='installations'"
                )
                if not cursor.fetchone():
                    return []

                # Query successful installations ordered by most recent first.
                cursor.execute(
                    "SELECT packages FROM installations "
                    "WHERE status = 'success' ORDER BY timestamp DESC LIMIT 10"
                )

                seen = set()  # Track unique packages to prevent duplicates.
                ordered_pkgs = []  # Maintain the recency order of unique signals.

                # Fetch results directly from the cursor to maintain memory efficiency.
                for row in cursor.fetchall():
                    try:
                        # Parse the JSON string containing the package list.
                        # Example format: '["nginx", "docker-ce"]'
                        package_list = json.loads(row[0])

                        if isinstance(package_list, list):
                            for pkg in package_list:
                                signal = f"installed:{pkg}"

                                # Deduplicate while maintaining chronological order.
                                # Because we query in descending order (DESC), the first occurrence
                                # of a package name represents its most recent installation.
                                if signal not in seen:
                                    ordered_pkgs.append(signal)
                                    seen.add(signal)
                    except (json.JSONDecodeError, TypeError):
                        # Skip rows with malformed JSON data without crashing.
                        continue

                # Return the top 5 unique recent packages.
                final_patterns = ordered_pkgs[:5]

                # Log successful sensing at the INFO level for audit purposes.
                if final_patterns:
                    logger.info("Sensed %d learned patterns from history.db", len(final_patterns))

                return final_patterns

        except Exception as e:
            # Log database or schema issues at the ERROR level.
            # This ensures visibility into critical failures that block learning.
            logger.error("Could not parse installation history for learning: %s", e)
            return []
