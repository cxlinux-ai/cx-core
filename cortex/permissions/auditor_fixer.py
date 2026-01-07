"""
Unified Permission Auditor & Fixer.
"""

import os
import stat
from pathlib import Path
from typing import Optional

from .config import DANGEROUS_PERMISSIONS, IGNORE_PATTERNS, RECOMMENDED_PERMISSIONS
from .docker_handler import DockerPermissionHandler


class PermissionAuditor:
    """Audit permissions."""

    def __init__(self, verbose=False):
        self.verbose = verbose

    def scan(self, path=".", recursive=True):
        """Scan path for permission issues."""
        path = Path(path).resolve()
        issues = []

        try:
            if path.is_file():
                issues = self._scan_file(path)
            elif path.is_dir():
                issues = self._scan_directory(path, recursive)
        except Exception as e:
            if self.verbose:
                print(f"Scan error: {e}")

        return issues

    def _scan_directory(self, directory, recursive):
        """Scan directory."""
        issues = []

        try:
            items = list(directory.rglob("*")) if recursive else list(directory.iterdir())

            for item in items:
                if self._should_ignore(item):
                    continue

                if item.is_file():
                    file_issues = self._check_file(item)
                    if file_issues:
                        issues.extend(file_issues)
                elif item.is_dir():
                    dir_issues = self._check_directory(item)
                    if dir_issues:
                        issues.extend(dir_issues)

        except Exception as e:
            if self.verbose:
                print(f"Directory scan error: {e}")

        return issues

    def _scan_file(self, filepath):
        """Scan single file."""
        if self._should_ignore(filepath):
            return []
        return self._check_file(filepath)

    def _should_ignore(self, path):
        """Check if path should be ignored."""
        str_path = str(path)
        return any(pattern in str_path for pattern in IGNORE_PATTERNS)

    def _check_file(self, filepath):
        """Check file permissions."""
        try:
            stats = filepath.stat()
            current_perms = stat.S_IMODE(stats.st_mode)

            issues = []

            # Check dangerous permissions
            if current_perms in DANGEROUS_PERMISSIONS:
                issues.append(
                    {
                        "type": "dangerous_permission",
                        "path": str(filepath),
                        "permission": oct(current_perms),
                        "description": DANGEROUS_PERMISSIONS[current_perms],
                        "is_directory": False,
                    }
                )

            # Check world-writable
            if current_perms & 0o002:  # S_IWOTH
                issues.append(
                    {
                        "type": "world_writable",
                        "path": str(filepath),
                        "permission": oct(current_perms),
                        "description": "File is writable by all users",
                        "is_directory": False,
                    }
                )

            return issues

        except Exception as e:
            if self.verbose:
                print(f"File check error {filepath}: {e}")
            return []

    def _check_directory(self, directory):
        """Check directory permissions."""
        try:
            stats = directory.stat()
            current_perms = stat.S_IMODE(stats.st_mode)

            issues = []

            if current_perms in DANGEROUS_PERMISSIONS:
                issues.append(
                    {
                        "type": "dangerous_permission",
                        "path": str(directory),
                        "permission": oct(current_perms),
                        "description": DANGEROUS_PERMISSIONS[current_perms],
                        "is_directory": True,
                    }
                )

            return issues

        except Exception as e:
            if self.verbose:
                print(f"Directory check error {directory}: {e}")
            return []


class PermissionFixer:
    """Fix permissions safely."""

    def __init__(self, dry_run=True):
        self.dry_run = dry_run

    def calculate_fix(self, issue):
        """Calculate fix for issue."""
        is_dir = issue.get("is_directory", False)

        if is_dir:
            recommended = RECOMMENDED_PERMISSIONS["directory"]
            reason = "Directories should have 755 permissions"
        else:
            recommended = RECOMMENDED_PERMISSIONS["config_file"]
            reason = "Files should have 644 permissions"

        return {
            "recommended": oct(recommended),
            "reason": reason,
            "command": f"chmod {oct(recommended)[2:]} '{issue['path']}'",
        }

    def apply_fix(self, issue, fix_info):
        """Apply fix."""
        if self.dry_run:
            return True

        try:
            path = Path(issue["path"])
            perm = int(fix_info["recommended"], 8)
            os.chmod(path, perm)
            return True
        except Exception as e:
            print(f"Fix error: {e}")
            return False


class PermissionManager:
    """Main manager combining auditor, fixer, and docker handler."""

    def __init__(self, verbose=False, dry_run=True):
        self.verbose = verbose
        self.dry_run = dry_run
        self.auditor = PermissionAuditor(verbose)
        self.fixer = PermissionFixer(dry_run)
        self.docker_handler = DockerPermissionHandler(verbose)  # NEW

    def scan_and_fix(self, path=".", apply_fixes=False, docker_context=False):
        """Scan and optionally fix with Docker support."""
        issues = self.auditor.scan(path)

        result = {
            "issues_found": len(issues),
            "fixes_applied": 0,
            "backups_created": 0,
            "dry_run": self.dry_run,
            "docker_context": docker_context,
        }

        if not issues:
            result["report"] = "✅ No permission issues found.\n"
            return result

        # Apply Docker adjustments if requested
        adjusted_issues = []
        for issue in issues:
            if docker_context:
                adjusted_issue = self.docker_handler.adjust_issue_for_container(issue)
            else:
                adjusted_issue = issue
            adjusted_issues.append(adjusted_issue)

        # Generate report
        report_lines = ["🔍 PERMISSION AUDIT REPORT"]

        if docker_context:
            report_lines.append("🐳 Docker Context: Enabled")
            report_lines.append(self.docker_handler.generate_docker_permission_report(path))

        report_lines.append(f"📊 Issues found: {len(adjusted_issues)}\n")

        for i, issue in enumerate(adjusted_issues, 1):
            report_lines.append(f"{i}. {issue['path']}")

            # Add Docker UID/GID info if available
            if docker_context and "uid_info" in issue:
                report_lines.append(
                    f"   Owner: {issue['uid_info']}, Group: {issue.get('gid_info', 'N/A')}"
                )

            report_lines.append(f"   Permission: {issue['permission']}")
            report_lines.append(f"   Issue: {issue['description']}")

            # Get fix with Docker adjustments
            fix_info = self.fixer.calculate_fix(issue)
            if docker_context:
                fix_info = self.docker_handler.get_container_specific_fix(issue, fix_info)

            report_lines.append(f"   💡 Fix: {fix_info['command']}")
            if docker_context and "container_advice" in fix_info:
                report_lines.append(f"   🐳 Docker Advice: {fix_info['container_advice']}")

            if apply_fixes and not self.dry_run:
                if self.fixer.apply_fix(issue, fix_info):
                    result["fixes_applied"] += 1

            report_lines.append("")

        # Special Docker fixes
        if docker_context and apply_fixes and not self.dry_run:
            docker_result = self.docker_handler.fix_docker_bind_mount_permissions(
                path, dry_run=False
            )
            if docker_result["success"] and docker_result["actions"]:
                report_lines.append("🐳 Docker-specific fixes applied:")
                for action in docker_result["actions"]:
                    report_lines.append(f"   ✓ {action['description']}")

        result["report"] = "\n".join(report_lines)
        result["issues"] = adjusted_issues

        return result


# Convenience functions
def scan_path(path=".", recursive=True):
    """Scan path for issues."""
    auditor = PermissionAuditor()
    return auditor.scan(path, recursive)


def analyze_permissions(issue):
    """Analyze permission issue."""
    return issue.get("description", "No analysis available")
