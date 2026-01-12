"""
Shell Environment Variable Analyzer for Cortex CLI.

Analyzes shell configuration files to:
- Trace where environment variables are defined
- Detect PATH duplicates and conflicts
- Safely modify shell configs with backup and atomic writes
- Support bash, zsh, and fish shells

Supported config files:
- Bash: ~/.bashrc, ~/.bash_profile, ~/.profile, /etc/profile, /etc/bash.bashrc
- Zsh: ~/.zshrc, ~/.zprofile, ~/.zshenv, /etc/zsh/zshrc
- Fish: ~/.config/fish/config.fish, /etc/fish/config.fish
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Shell(Enum):
    """Supported shell types."""

    BASH = "bash"
    ZSH = "zsh"
    FISH = "fish"
    UNKNOWN = "unknown"


class ConflictSeverity(Enum):
    """Severity levels for environment variable conflicts."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class VariableSource:
    """Represents where an environment variable is defined."""

    file: Path
    line_number: int
    raw_line: str
    variable_name: str
    value: str
    is_export: bool = True
    shell: Shell = Shell.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file": str(self.file),
            "line_number": self.line_number,
            "raw_line": self.raw_line,
            "variable_name": self.variable_name,
            "value": self.value,
            "is_export": self.is_export,
            "shell": self.shell.value,
        }


@dataclass
class VariableConflict:
    """Represents a conflict between variable definitions."""

    variable_name: str
    sources: list[VariableSource]
    severity: ConflictSeverity
    description: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "variable_name": self.variable_name,
            "sources": [s.to_dict() for s in self.sources],
            "severity": self.severity.value,
            "description": self.description,
        }


@dataclass
class PathEntry:
    """Represents a single entry in PATH."""

    path: str
    source: VariableSource | None = None
    exists: bool = True
    is_duplicate: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": self.path,
            "source": self.source.to_dict() if self.source else None,
            "exists": self.exists,
            "is_duplicate": self.is_duplicate,
        }


@dataclass
class EnvironmentAudit:
    """Complete audit of shell environment."""

    variables: dict[str, list[VariableSource]] = field(default_factory=dict)
    path_entries: list[PathEntry] = field(default_factory=list)
    conflicts: list[VariableConflict] = field(default_factory=list)
    shell: Shell = Shell.UNKNOWN
    config_files_scanned: list[Path] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "variables": {k: [s.to_dict() for s in v] for k, v in self.variables.items()},
            "path_entries": [p.to_dict() for p in self.path_entries],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "shell": self.shell.value,
            "config_files_scanned": [str(f) for f in self.config_files_scanned],
        }


class ShellConfigParser:
    """Parser for shell configuration files."""

    # Regex patterns for variable extraction
    # Bash/Zsh: export VAR=value, VAR=value, export VAR="value"
    BASH_EXPORT_PATTERN = re.compile(
        r'^[ \t]{0,50}(?:export[ \t]{1,20})?([A-Za-z_][A-Za-z0-9_]{0,100})=(["\']?)([^"\']{0,10000})\2[ \t]{0,50}(?:#[^\n]{0,1000})?$'
    )
    BASH_EXPORT_SIMPLE = re.compile(
        r"^[ \t]{0,50}(?:export[ \t]{1,20})?([A-Za-z_][A-Za-z0-9_]{0,100})=([^\n]{0,10000})$"
    )

    # Fish: set -gx VAR value, set -x VAR value, set VAR value
    # Note: fish has 4 flags (g,x,U,u) but allow up to 10 for redundant usage
    FISH_SET_PATTERN = re.compile(
        r"^[ \t]{0,50}set[ \t]{1,20}(?:-[gxUu]{1,10}[ \t]{1,20})?([A-Za-z_][A-Za-z0-9_]{0,100})[ \t]{1,20}([^\n]{0,10000})$"
    )

    # PATH modification patterns
    BASH_PATH_APPEND = re.compile(
        r"^[ \t]{0,50}(?:export[ \t]{1,20})?PATH=[^\n]{0,10000}\$\{?PATH\}?"
    )
    BASH_PATH_PREPEND = re.compile(
        r"^[ \t]{0,50}(?:export[ \t]{1,20})?PATH=[^\n]{0,10000}\$\{?PATH\}?"
    )
    FISH_PATH_PATTERN = re.compile(
        r"^[ \t]{0,50}(?:set[ \t]{1,20})?(?:-[gxUu]{1,10}[ \t]{1,20})?(?:fish_user_paths|PATH)[ \t]{1,20}([^\n]{0,10000})$"
    )

    def __init__(self, shell: Shell | None = None):
        """Initialize parser with optional shell type."""
        self.shell = shell or self._detect_shell()

    def _detect_shell(self) -> Shell:
        """Detect the current shell from environment."""
        shell_path = os.environ.get("SHELL", "")
        shell_name = Path(shell_path).name.lower()

        if "bash" in shell_name:
            return Shell.BASH
        elif "zsh" in shell_name:
            return Shell.ZSH
        elif "fish" in shell_name:
            return Shell.FISH
        return Shell.UNKNOWN

    def get_config_files(self, shell: Shell | None = None) -> list[Path]:
        """Get list of config files for the specified shell."""
        shell = shell or self.shell
        home = Path.home()
        files: list[Path] = []

        if shell == Shell.BASH:
            files = [
                Path("/etc/profile"),
                Path("/etc/bash.bashrc"),
                Path("/etc/profile.d"),  # Directory - will be expanded
                home / ".profile",
                home / ".bash_profile",
                home / ".bashrc",
            ]
        elif shell == Shell.ZSH:
            files = [
                Path("/etc/zsh/zshenv"),
                Path("/etc/zsh/zprofile"),
                Path("/etc/zsh/zshrc"),
                home / ".zshenv",
                home / ".zprofile",
                home / ".zshrc",
            ]
        elif shell == Shell.FISH:
            files = [
                Path("/etc/fish/config.fish"),
                home / ".config" / "fish" / "config.fish",
                home / ".config" / "fish" / "conf.d",  # Directory - will be expanded
            ]
        else:
            # Fallback - scan common files
            files = [
                Path("/etc/profile"),
                home / ".profile",
                home / ".bashrc",
                home / ".zshrc",
            ]

        # Expand directories
        expanded: list[Path] = []
        for f in files:
            if f.is_dir():
                # Add all .sh files in profile.d or .fish files in conf.d
                if f.name == "profile.d":
                    expanded.extend(sorted(f.glob("*.sh")))
                elif f.name == "conf.d":
                    expanded.extend(sorted(f.glob("*.fish")))
            else:
                expanded.append(f)

        return expanded

    def parse_file(self, filepath: Path) -> list[VariableSource]:
        """Parse a shell config file and extract variable definitions."""
        if not filepath.exists() or not filepath.is_file():
            return []

        sources: list[VariableSource] = []
        shell = self._detect_file_shell(filepath)

        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except (PermissionError, OSError):
            return []

        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            source = self._parse_line(line, line_num, filepath, shell)
            if source:
                sources.append(source)

        return sources

    def _detect_file_shell(self, filepath: Path) -> Shell:
        """Detect shell type from file path/extension."""
        name = filepath.name.lower()
        suffix = filepath.suffix.lower()

        if suffix == ".fish" or "fish" in name:
            return Shell.FISH
        elif "zsh" in name:
            return Shell.ZSH
        elif "bash" in name or suffix == ".sh" or name in (".profile", ".bashrc"):
            return Shell.BASH
        return self.shell

    def _parse_line(
        self, line: str, line_num: int, filepath: Path, shell: Shell
    ) -> VariableSource | None:
        """Parse a single line for variable definition."""
        stripped = line.strip()

        if shell == Shell.FISH:
            return self._parse_fish_line(line, line_num, filepath)
        else:
            return self._parse_bash_line(line, line_num, filepath, shell)

    def _parse_bash_line(
        self, line: str, line_num: int, filepath: Path, shell: Shell
    ) -> VariableSource | None:
        """Parse bash/zsh style variable definition."""
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            return None

        # Check for export statement
        is_export = stripped.startswith("export ")

        # Try to match export VAR=value or VAR=value
        match = self.BASH_EXPORT_SIMPLE.match(stripped)
        if match:
            var_name = match.group(1)
            raw_value = match.group(2)

            # Clean up value - remove quotes and trailing comments
            value = self._clean_value(raw_value)

            return VariableSource(
                file=filepath,
                line_number=line_num,
                raw_line=line,
                variable_name=var_name,
                value=value,
                is_export=is_export,
                shell=shell,
            )

        return None

    def _parse_fish_line(self, line: str, line_num: int, filepath: Path) -> VariableSource | None:
        """Parse fish shell variable definition."""
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            return None

        match = self.FISH_SET_PATTERN.match(stripped)
        if match:
            var_name = match.group(1)
            value = match.group(2).strip()

            # Fish uses -gx for exported global vars
            is_export = "-x" in stripped or "-gx" in stripped

            return VariableSource(
                file=filepath,
                line_number=line_num,
                raw_line=line,
                variable_name=var_name,
                value=value,
                is_export=is_export,
                shell=Shell.FISH,
            )

        return None

    def _clean_value(self, value: str) -> str:
        """Clean a variable value by removing quotes and comments."""
        value = value.strip()

        # Remove inline comments first (but be careful with # in paths)
        # Only remove if there's whitespace before #
        if " #" in value:
            value = value.split(" #")[0].strip()

        # Remove surrounding quotes after comment removal
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        return value


class ShellConfigEditor:
    """Editor for shell configuration files with backup and atomic writes."""

    CORTEX_MARKER_START = "# >>> cortex managed >>>"
    CORTEX_MARKER_END = "# <<< cortex managed <<<"

    def __init__(self, backup_dir: Path | None = None):
        """Initialize editor with optional backup directory."""
        self.backup_dir = backup_dir or Path.home() / ".cortex" / "backups"

    def backup_file(self, filepath: Path) -> Path:
        """Create a timestamped backup of a file."""
        if not filepath.exists():
            raise FileNotFoundError(f"Cannot backup non-existent file: {filepath}")

        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{filepath.name}.cortex-backup.{timestamp}"
        backup_path = self.backup_dir / backup_name

        shutil.copy2(filepath, backup_path)
        return backup_path

    def restore_backup(self, backup_path: Path, target: Path) -> bool:
        """Restore a file from backup."""
        if not backup_path.exists():
            return False

        shutil.copy2(backup_path, target)
        return True

    def add_to_config(
        self,
        filepath: Path,
        content: str,
        marker_id: str | None = None,
        backup: bool = True,
    ) -> bool:
        """Add content to shell config file idempotently."""
        marker_start = self.CORTEX_MARKER_START
        marker_end = self.CORTEX_MARKER_END

        if marker_id:
            marker_start = f"# >>> cortex:{marker_id} >>>"
            marker_end = f"# <<< cortex:{marker_id} <<<"

        # Read existing content
        existing = ""
        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8")

        # Check if marker already exists - update if so
        if marker_start in existing:
            # Replace existing block
            pattern = re.escape(marker_start) + r".*?" + re.escape(marker_end)
            new_block = f"{marker_start}\n{content}\n{marker_end}"
            new_content = re.sub(pattern, new_block, existing, flags=re.DOTALL)
        else:
            # Append new block
            new_block = f"\n{marker_start}\n{content}\n{marker_end}\n"
            new_content = existing + new_block

        # Backup before modifying
        if backup and filepath.exists():
            self.backup_file(filepath)

        # Atomic write
        self._atomic_write(filepath, new_content)
        return True

    def remove_from_config(
        self, filepath: Path, marker_id: str | None = None, backup: bool = True
    ) -> bool:
        """Remove cortex-managed content from shell config file."""
        if not filepath.exists():
            return False

        marker_start = self.CORTEX_MARKER_START
        marker_end = self.CORTEX_MARKER_END

        if marker_id:
            marker_start = f"# >>> cortex:{marker_id} >>>"
            marker_end = f"# <<< cortex:{marker_id} <<<"

        existing = filepath.read_text(encoding="utf-8")

        if marker_start not in existing:
            return False

        # Backup before modifying
        if backup:
            self.backup_file(filepath)

        # Remove the block
        pattern = r"\n?" + re.escape(marker_start) + r".*?" + re.escape(marker_end) + r"\n?"
        new_content = re.sub(pattern, "\n", existing, flags=re.DOTALL)

        self._atomic_write(filepath, new_content)
        return True

    def _atomic_write(self, filepath: Path, content: str) -> None:
        """Write content to file atomically."""
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file in same directory, then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=filepath.parent, prefix=f".{filepath.name}.", suffix=".tmp"
        )
        fd_closed = False
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            fd_closed = True
            # Preserve permissions if file exists
            if filepath.exists():
                st = filepath.stat()
                os.chmod(tmp_path, st.st_mode)
            os.replace(tmp_path, filepath)
        except Exception:
            if not fd_closed:
                os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


class ShellEnvironmentAnalyzer:
    """Main analyzer for shell environment variables."""

    def __init__(self, shell: Shell | None = None):
        """Initialize analyzer with optional shell type."""
        self.parser = ShellConfigParser(shell)
        self.editor = ShellConfigEditor()
        self.shell = shell or self.parser.shell

    def audit(self, include_system: bool = True) -> EnvironmentAudit:
        """Perform complete audit of shell environment."""
        audit = EnvironmentAudit(shell=self.shell)

        # Get config files to scan
        config_files = self.parser.get_config_files()
        if not include_system:
            home = Path.home()
            config_files = [f for f in config_files if str(f).startswith(str(home))]

        audit.config_files_scanned = [f for f in config_files if f.exists()]

        # Parse all config files
        all_sources: list[VariableSource] = []
        for config_file in config_files:
            sources = self.parser.parse_file(config_file)
            all_sources.extend(sources)

        # Group by variable name
        for source in all_sources:
            if source.variable_name not in audit.variables:
                audit.variables[source.variable_name] = []
            audit.variables[source.variable_name].append(source)

        # Analyze PATH specifically
        audit.path_entries = self._analyze_path(audit.variables.get("PATH", []))

        # Detect conflicts
        audit.conflicts = self._detect_conflicts(audit.variables)

        return audit

    def _analyze_path(self, path_sources: list[VariableSource]) -> list[PathEntry]:
        """Analyze PATH variable entries."""
        # Get current PATH from environment
        current_path = os.environ.get("PATH", "")
        entries = current_path.split(os.pathsep)

        seen: set[str] = set()
        path_entries: list[PathEntry] = []

        for entry in entries:
            if not entry:
                continue

            # Normalize the entry for comparison
            normalized_entry = os.path.normpath(os.path.expanduser(entry))

            # Find source if available - use exact path matching
            source = None
            for ps in path_sources:
                # Split the source value by path separator and normalize each
                source_paths = ps.value.split(os.pathsep)
                for sp in source_paths:
                    # Skip empty or variable references like $PATH
                    if not sp or sp.startswith("$"):
                        continue
                    normalized_source = os.path.normpath(os.path.expanduser(sp))
                    if normalized_entry == normalized_source:
                        source = ps
                        break
                if source:
                    break

            is_duplicate = entry in seen
            seen.add(entry)

            path_entries.append(
                PathEntry(
                    path=entry,
                    source=source,
                    exists=Path(entry).exists(),
                    is_duplicate=is_duplicate,
                )
            )

        return path_entries

    def _detect_conflicts(
        self, variables: dict[str, list[VariableSource]]
    ) -> list[VariableConflict]:
        """Detect conflicts in variable definitions."""
        conflicts: list[VariableConflict] = []

        for var_name, sources in variables.items():
            if len(sources) <= 1:
                continue

            # Check for different values
            unique_values = set()
            for source in sources:
                # Normalize value for comparison
                normalized = self._normalize_value(source.value)
                unique_values.add(normalized)

            if len(unique_values) > 1:
                # Different values defined - this is a conflict
                conflicts.append(
                    VariableConflict(
                        variable_name=var_name,
                        sources=sources,
                        severity=ConflictSeverity.WARNING,
                        description=f"Variable '{var_name}' is defined with different values in {len(sources)} files",
                    )
                )
            elif len(sources) > 1:
                # Same value defined multiple times - duplicate
                conflicts.append(
                    VariableConflict(
                        variable_name=var_name,
                        sources=sources,
                        severity=ConflictSeverity.INFO,
                        description=f"Variable '{var_name}' is defined identically in {len(sources)} files",
                    )
                )

        return conflicts

    def _normalize_value(self, value: str) -> str:
        """Normalize a value for comparison."""
        # Expand common variables
        normalized = value.strip()
        # Remove quotes
        if (normalized.startswith('"') and normalized.endswith('"')) or (
            normalized.startswith("'") and normalized.endswith("'")
        ):
            normalized = normalized[1:-1]
        return normalized

    def get_path_duplicates(self) -> list[str]:
        """Get list of duplicate PATH entries."""
        current_path = os.environ.get("PATH", "")
        entries = current_path.split(os.pathsep)

        seen: set[str] = set()
        duplicates: list[str] = []

        for entry in entries:
            if not entry:
                continue
            if entry in seen:
                duplicates.append(entry)
            else:
                seen.add(entry)

        return duplicates

    def get_missing_paths(self) -> list[str]:
        """Get list of PATH entries that don't exist."""
        current_path = os.environ.get("PATH", "")
        entries = current_path.split(os.pathsep)

        missing: list[str] = []
        for entry in entries:
            if entry and not Path(entry).exists():
                missing.append(entry)

        return missing

    def dedupe_path(self, path: str | None = None) -> str:
        """Remove duplicate entries from PATH."""
        if path is None:
            path = os.environ.get("PATH", "")

        entries = path.split(os.pathsep)
        seen: set[str] = set()
        unique: list[str] = []

        for entry in entries:
            if entry and entry not in seen:
                seen.add(entry)
                unique.append(entry)

        return os.pathsep.join(unique)

    def clean_path(self, path: str | None = None, remove_missing: bool = False) -> str:
        """Clean PATH by removing duplicates and optionally non-existent entries."""
        if path is None:
            path = os.environ.get("PATH", "")

        entries = path.split(os.pathsep)
        seen: set[str] = set()
        clean: list[str] = []

        for entry in entries:
            if not entry:
                continue
            if entry in seen:
                continue
            if remove_missing and not Path(entry).exists():
                continue
            seen.add(entry)
            clean.append(entry)

        return os.pathsep.join(clean)

    def safe_add_path(
        self,
        new_path: str,
        prepend: bool = True,
        path: str | None = None,
    ) -> str:
        """Safely add a path entry (idempotent)."""
        if path is None:
            path = os.environ.get("PATH", "")

        entries = path.split(os.pathsep)

        # Check if already present
        if new_path in entries:
            return path

        if prepend:
            entries.insert(0, new_path)
        else:
            entries.append(new_path)

        return os.pathsep.join(entries)

    def safe_remove_path(self, target_path: str, path: str | None = None) -> str:
        """Safely remove a path entry."""
        if path is None:
            path = os.environ.get("PATH", "")

        entries = path.split(os.pathsep)
        entries = [e for e in entries if e != target_path]

        return os.pathsep.join(entries)

    def get_shell_config_path(self, shell: Shell | None = None) -> Path:
        """Get the primary config file path for the shell."""
        shell = shell or self.shell
        home = Path.home()

        if shell == Shell.BASH:
            # Prefer .bashrc for interactive shells
            bashrc = home / ".bashrc"
            if bashrc.exists():
                return bashrc
            return home / ".bash_profile"
        elif shell == Shell.ZSH:
            return home / ".zshrc"
        elif shell == Shell.FISH:
            return home / ".config" / "fish" / "config.fish"
        else:
            return home / ".profile"

    def _escape_shell_string(self, value: str, shell: Shell) -> str:
        """Escape a string for safe use in shell commands.

        Args:
            value: The string to escape
            shell: The target shell type

        Returns:
            Escaped string safe for embedding in shell commands
        """
        if shell == Shell.FISH:
            # Fish uses different escaping rules
            # Escape backslashes, double quotes, and dollar signs
            escaped = value.replace("\\", "\\\\")
            escaped = escaped.replace('"', '\\"')
            escaped = escaped.replace("$", "\\$")
            return escaped
        else:
            # Bash/Zsh: escape backslashes, double quotes, dollar signs, and backticks
            escaped = value.replace("\\", "\\\\")
            escaped = escaped.replace('"', '\\"')
            escaped = escaped.replace("$", "\\$")
            escaped = escaped.replace("`", "\\`")
            return escaped

    def _generate_marker_id(self, prefix: str, value: str) -> str:
        """Generate a unique marker ID for a value.

        Uses rstrip (not strip) to preserve leading '-' from absolute paths,
        avoiding collisions between '/a/b' (-a-b) and 'a/b' (a-b).
        """
        # Replace path separators, only strip trailing dashes
        sanitized = value.replace("/", "-").replace("\\", "-").rstrip("-")
        return f"{prefix}-{sanitized}"

    def add_path_to_config(
        self,
        new_path: str,
        prepend: bool = True,
        shell: Shell | None = None,
        backup: bool = True,
    ) -> bool:
        """Add a PATH entry to shell config file."""
        shell = shell or self.shell
        config_path = self.get_shell_config_path(shell)

        # Escape the path for safe shell embedding
        escaped_path = self._escape_shell_string(new_path, shell)

        if shell == Shell.FISH:
            if prepend:
                content = f'set -gx PATH "{escaped_path}" $PATH'
            else:
                content = f'set -gx PATH $PATH "{escaped_path}"'
        else:
            if prepend:
                content = f'export PATH="{escaped_path}:$PATH"'
            else:
                content = f'export PATH="$PATH:{escaped_path}"'

        return self.editor.add_to_config(
            config_path,
            content,
            marker_id=self._generate_marker_id("path", new_path),
            backup=backup,
        )

    def remove_path_from_config(
        self,
        target_path: str,
        shell: Shell | None = None,
        backup: bool = True,
    ) -> bool:
        """Remove a PATH entry from shell config file."""
        shell = shell or self.shell
        config_path = self.get_shell_config_path(shell)

        marker_id = self._generate_marker_id("path", target_path)
        return self.editor.remove_from_config(config_path, marker_id=marker_id, backup=backup)

    def add_variable_to_config(
        self,
        var_name: str,
        value: str,
        shell: Shell | None = None,
        backup: bool = True,
    ) -> bool:
        """Add an environment variable to shell config file."""
        shell = shell or self.shell
        config_path = self.get_shell_config_path(shell)

        # Escape the value for safe shell embedding
        escaped_value = self._escape_shell_string(value, shell)

        if shell == Shell.FISH:
            content = f'set -gx {var_name} "{escaped_value}"'
        else:
            content = f'export {var_name}="{escaped_value}"'

        return self.editor.add_to_config(
            config_path,
            content,
            marker_id=f"var-{var_name}",
            backup=backup,
        )

    def remove_variable_from_config(
        self,
        var_name: str,
        shell: Shell | None = None,
        backup: bool = True,
    ) -> bool:
        """Remove an environment variable from shell config file."""
        shell = shell or self.shell
        config_path = self.get_shell_config_path(shell)

        return self.editor.remove_from_config(
            config_path, marker_id=f"var-{var_name}", backup=backup
        )

    def generate_path_fix_script(self, shell: Shell | None = None) -> str:
        """Generate a shell script to fix PATH issues."""
        shell = shell or self.shell
        duplicates = self.get_path_duplicates()
        missing = self.get_missing_paths()

        if not duplicates and not missing:
            return "# PATH is clean - no fixes needed"

        if shell == Shell.FISH:
            lines = ["# Fish shell PATH cleanup"]
            if duplicates or missing:
                lines.append("# Current PATH has issues - run this to fix:")
                clean = self.clean_path(remove_missing=True)
                entries = clean.split(os.pathsep)
                lines.append(f"set -gx PATH {' '.join(entries)}")
        else:
            lines = ["# Bash/Zsh PATH cleanup"]
            if duplicates or missing:
                lines.append("# Current PATH has issues - run this to fix:")
                clean = self.clean_path(remove_missing=True)
                lines.append(f'export PATH="{clean}"')

        if duplicates:
            lines.insert(1, f"# Duplicates found: {', '.join(duplicates[:5])}")
        if missing:
            lines.insert(1, f"# Missing paths: {', '.join(missing[:5])}")

        return "\n".join(lines)
