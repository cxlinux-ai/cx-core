"""
Permission Auditor & Fixer module.
Fixes security issues with dangerous file permissions (777, world-writable).
"""

import logging
import os
import stat
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


class PermissionAuditor:
    """
    Auditor for detecting and fixing dangerous file permissions.

    Detects:
    - World-writable files (others have write permission)
    - Files with 777 permissions
    - Insecure directory permissions
    """

    def __init__(self, verbose=False, dry_run=True, docker_context=False):
        self.verbose = verbose
        self.dry_run = dry_run
        self.docker_handler = None
        self.logger = logging.getLogger(__name__)

        if docker_context:
            from .docker_handler import DockerPermissionHandler

            self.docker_handler = DockerPermissionHandler()

        if verbose:
            self.logger.setLevel(logging.DEBUG)

    def explain_issue_plain_english(self, filepath: str, issue_type: str) -> str:
        """
        Explain permission issue in plain English.

        Args:
            filepath: Path to the file
            issue_type: Type of issue ('world_writable', 'dangerous_777')

        Returns:
            Plain English explanation
        """
        filename = os.path.basename(filepath)

        explanations = {
            "world_writable": (
                f"⚠️ SECURITY RISK: '{filename}' is WORLD-WRITABLE.\n"
                "   This means ANY user on the system can MODIFY this file.\n"
                "   Attackers could: inject malicious code, delete data, or tamper with configurations.\n"
                "   FIX: Restrict write permissions to owner only."
            ),
            "dangerous_777": (
                f"🚨 CRITICAL RISK: '{filename}' has 777 permissions (rwxrwxrwx).\n"
                "   This means EVERYONE can read, write, and execute this file.\n"
                "   This is like leaving your house with doors unlocked and keys in the lock.\n"
                "   FIX: Set appropriate permissions (644 for files, 755 for scripts)."
            ),
        }
        return explanations.get(issue_type, f"Permission issue detected in '{filename}'")

    def scan_directory(self, directory_path: str | Path) -> dict[str, list[str]]:
        """
        Scan directory for dangerous permissions.

        Args:
            directory_path: Path to directory to scan

        Returns:
            Dictionary with keys:
            - 'world_writable': List of world-writable files
            - 'dangerous': List of files with dangerous permissions (777)
            - 'suggestions': List of suggested fixes
            - 'docker_context': True if Docker files found
        """
        path = Path(directory_path).resolve()
        result = {"world_writable": [], "dangerous": [], "suggestions": [], "docker_context": False}

        if not path.exists():
            logger.warning(f"Directory does not exist: {path}")
            return result

        if not path.is_dir():
            logger.warning(f"Path is not a directory: {path}")
            return result

        # Check for Docker context
        docker_files = ["docker-compose.yml", "docker-compose.yaml", "Dockerfile", ".dockerignore"]
        for docker_file in docker_files:
            docker_path = path / docker_file
            if docker_path.exists():
                result["docker_context"] = True
                if self.verbose:
                    logger.debug(f"Docker context detected: {docker_file}")
                break

        # Also check parent directories for Docker files
        if not result["docker_context"]:
            for parent in path.parents:
                for docker_file in docker_files:
                    if (parent / docker_file).exists():
                        result["docker_context"] = True
                        if self.verbose:
                            logger.debug(
                                f"Docker context detected in parent: {parent}/{docker_file}"
                            )
                        break
                if result["docker_context"]:
                    break

        try:
            for item in path.rglob("*"):
                if item.is_file():
                    try:
                        mode = item.stat().st_mode
                        file_path = str(item)

                        # Check for world-writable (others have write permission)
                        if mode & stat.S_IWOTH:  # Others write (0o002)
                            result["world_writable"].append(file_path)
                            suggestion = self.suggest_fix(
                                file_path, current_perms=oct(mode & 0o777)
                            )
                            result["suggestions"].append(suggestion)

                        # Check for 777 permissions
                        if (mode & 0o777) == 0o777:
                            if file_path not in result["dangerous"]:
                                result["dangerous"].append(file_path)
                                if file_path not in [
                                    s.split()[2].strip("'")
                                    for s in result["suggestions"]
                                    if len(s.split()) > 2
                                ]:
                                    suggestion = self.suggest_fix(file_path, current_perms="777")
                                    result["suggestions"].append(suggestion)

                    except (OSError, PermissionError) as e:
                        if self.verbose:
                            logger.debug(f"Cannot access {item}: {e}")
                        continue

        except (OSError, PermissionError) as e:
            logger.error(f"Error scanning directory {path}: {e}")

        return result

    def suggest_fix(self, filepath: str | Path, current_perms: str | None = None) -> str:
        """
        Suggest correct permissions for a file.

        Args:
            filepath: Path to the file
            current_perms: Current permissions in octal (e.g., '777')

        Returns:
            Suggested chmod command to fix permissions
        """
        path = Path(filepath)

        if not path.exists():
            return f"# File {filepath} doesn't exist"

        try:
            mode = path.stat().st_mode

            # Get file extension and check if executable
            is_executable = mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            is_script = path.suffix in [".sh", ".py", ".pl", ".rb", ".bash"]

            # Suggested permissions based on file type
            if is_executable or is_script:
                suggested = "755"  # rwxr-xr-x
                reason = "executable/script file"
            else:
                suggested = "644"  # rw-r--r--
                reason = "data file"

            current = oct(mode & 0o777)[-3:] if current_perms is None else current_perms

            return f"chmod {suggested} '{filepath}'  # Fix: {current} → {suggested} ({reason})"

        except (OSError, PermissionError) as e:
            return f"# Cannot access {filepath}: {e}"

    def fix_permissions(
        self, filepath: str | Path, permissions: str = "644", dry_run: bool = True
    ) -> str:
        """
        Fix permissions for a single file.

        Args:
            filepath: Path to the file
            permissions: Permissions in octal (e.g., '644', '755')
            dry_run: If True, only show what would be changed

        Returns:
            Report of the change made or that would be made
        """
        path = Path(filepath)

        if not path.exists():
            return f"File does not exist: {filepath}"

        try:
            current_mode = path.stat().st_mode
            current_perms = oct(current_mode & 0o777)[-3:]

            if dry_run:
                return f"[DRY RUN] Would change {filepath}: {current_perms} → {permissions}"
            else:
                # Preserve file type bits, only change permission bits
                new_mode = (current_mode & ~0o777) | int(permissions, 8)
                path.chmod(new_mode)

                # Verify the change
                verified = oct(path.stat().st_mode & 0o777)[-3:]
                return f"Changed {filepath}: {current_perms} → {verified}"

        except (OSError, PermissionError) as e:
            return f"Error changing permissions on {filepath}: {e}"

    def scan_and_fix(self, path=".", apply_fixes=False, dry_run=None):
        """
        Scan directory and optionally fix issues.
        Used by CLI command.

        Args:
            path: Directory to scan
            apply_fixes: If True, apply fixes
            dry_run: If None, use self.dry_run; if True/False, override
        """
        # Use instance dry_run if not specified
        if dry_run is None:
            dry_run = self.dry_run

        # Scan for issues
        scan_result = self.scan_directory(path)

        issues_found = len(scan_result["world_writable"]) + len(scan_result["dangerous"])

        # Generate report
        report_lines = []
        report_lines.append("🔒 PERMISSION AUDIT REPORT")
        report_lines.append("=" * 50)
        report_lines.append(f"Scanned: {path}")
        report_lines.append(f"Total issues found: {issues_found}")
        report_lines.append("")

        if self.docker_handler and scan_result.get("docker_context"):
            report_lines.append("🐳 DOCKER/CONTAINER CONTEXT:")
            report_lines.append(
                f"   Running in: {self.docker_handler.container_info['container_runtime'] or 'Native'}"
            )
            report_lines.append(
                f"   Host UID/GID: {self.docker_handler.container_info['host_uid']}/{self.docker_handler.container_info['host_gid']}"
            )
            report_lines.append("")

        # World-writable files
        if scan_result["world_writable"]:
            report_lines.append("🚨 WORLD-WRITABLE FILES (others can write):")
            for file in scan_result["world_writable"][:10]:  # Show first 10
                report_lines.append(f"  • {file}")
            if len(scan_result["world_writable"]) > 10:
                report_lines.append(f"  ... and {len(scan_result['world_writable']) - 10} more")
            report_lines.append("")

        # Dangerous permissions (777)
        if scan_result["dangerous"]:
            report_lines.append("⚠️ DANGEROUS PERMISSIONS (777):")
            for file in scan_result["dangerous"][:10]:
                report_lines.append(f"  • {file}")
            if len(scan_result["dangerous"]) > 10:
                report_lines.append(f"  ... and {len(scan_result['dangerous']) - 10} more")
            report_lines.append("")

        # Suggestions
        if scan_result["suggestions"]:
            report_lines.append("💡 SUGGESTED FIXES:")
            for suggestion in scan_result["suggestions"][:5]:
                report_lines.append(f"  {suggestion}")
            if len(scan_result["suggestions"]) > 5:
                report_lines.append(f"  ... and {len(scan_result['suggestions']) - 5} more")

        # ONE COMMAND TO FIX ALL - добавлено с правильным отступом
        if scan_result["suggestions"]:
            report_lines.append("💡 ONE COMMAND TO FIX ALL ISSUES:")
            fix_commands = []
            for file_path in scan_result["world_writable"][:10]:  # Limit to 10 files
                suggestion = self.suggest_fix(file_path)
                if "chmod" in suggestion:
                    parts = suggestion.split()
                    if len(parts) >= 3:
                        fix_commands.append(f"{parts[0]} {parts[1]} '{parts[2]}'")

            if fix_commands:
                report_lines.append("   Run this command:")
                report_lines.append("   " + " && ".join(fix_commands[:3]))  # Max 3 commands
                if len(fix_commands) > 3:
                    report_lines.append(f"   ... and {len(fix_commands) - 3} more commands")
            report_lines.append("")

        # Apply fixes if requested
        if apply_fixes:
            report_lines.append("")
            report_lines.append("🛠️ APPLYING FIXES:")
            fixed_count = 0

            for file_path in scan_result["world_writable"]:
                try:
                    # Get suggested fix
                    suggestion = self.suggest_fix(file_path)
                    if "chmod" in suggestion:
                        # Extract permissions from suggestion
                        parts = suggestion.split()
                        if len(parts) >= 2:
                            cmd = parts[0]
                            perms = parts[1]
                            if cmd == "chmod" and perms.isdigit():
                                if not dry_run:
                                    # Actually fix the file
                                    fix_result = self.fix_permissions(
                                        file_path, permissions=perms, dry_run=False
                                    )
                                    report_lines.append(f"  ✓ Fixed: {file_path}")
                                    fixed_count += 1
                                else:
                                    report_lines.append(f"  [DRY RUN] Would fix: {file_path}")
                except Exception as e:
                    report_lines.append(f"  ✗ Error fixing {file_path}: {e}")

            report_lines.append(f"Fixed {fixed_count} files")

        report_lines.append("")
        report_lines.append("✅ Scan complete")

        return {
            "report": "\n".join(report_lines),
            "issues_found": issues_found,
            "scan_result": scan_result,
            "fixed": apply_fixes and not dry_run,
        }
