"""User and path management for the Do Runner module."""

import json
import os
import pwd
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()


class ProtectedPathsManager:
    """Manages the list of protected files and folders requiring user authentication."""

    SYSTEM_PROTECTED_PATHS: set[str] = {
        # System configuration
        "/etc",
        "/etc/passwd",
        "/etc/shadow",
        "/etc/sudoers",
        "/etc/sudoers.d",
        "/etc/ssh",
        "/etc/ssl",
        "/etc/pam.d",
        "/etc/security",
        "/etc/cron.d",
        "/etc/cron.daily",
        "/etc/crontab",
        "/etc/systemd",
        "/etc/init.d",
        # Boot and kernel
        "/boot",
        "/boot/grub",
        # System binaries
        "/usr/bin",
        "/usr/sbin",
        "/sbin",
        "/bin",
        # Root directory
        "/root",
        # System libraries
        "/lib",
        "/lib64",
        "/usr/lib",
        # Var system data
        "/var/log",
        "/var/lib/apt",
        "/var/lib/dpkg",
        # Proc and sys (virtual filesystems)
        "/proc",
        "/sys",
    }

    USER_PROTECTED_PATHS: set[str] = set()

    def __init__(self):
        self.config_file = Path.home() / ".cortex" / "protected_paths.json"
        self._ensure_config_dir()
        self._load_user_paths()

    def _ensure_config_dir(self):
        """Ensure the config directory exists."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.config_file = Path("/tmp") / ".cortex" / "protected_paths.json"
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_user_paths(self):
        """Load user-configured protected paths."""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    data = json.load(f)
                    self.USER_PROTECTED_PATHS = set(data.get("paths", []))
            except (json.JSONDecodeError, OSError):
                pass

    def _save_user_paths(self):
        """Save user-configured protected paths."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump({"paths": list(self.USER_PROTECTED_PATHS)}, f, indent=2)
        except OSError as e:
            console.print(f"[yellow]Warning: Could not save protected paths: {e}[/yellow]")

    def add_protected_path(self, path: str) -> bool:
        """Add a path to user-protected paths."""
        self.USER_PROTECTED_PATHS.add(path)
        self._save_user_paths()
        return True

    def remove_protected_path(self, path: str) -> bool:
        """Remove a path from user-protected paths."""
        if path in self.USER_PROTECTED_PATHS:
            self.USER_PROTECTED_PATHS.discard(path)
            self._save_user_paths()
            return True
        return False

    def is_protected(self, path: str) -> bool:
        """Check if a path requires authentication for access."""
        path = os.path.abspath(path)
        all_protected = self.SYSTEM_PROTECTED_PATHS | self.USER_PROTECTED_PATHS

        if path in all_protected:
            return True

        for protected in all_protected:
            if path.startswith(protected + "/") or path == protected:
                return True

        return False

    def get_all_protected(self) -> list[str]:
        """Get all protected paths."""
        return sorted(self.SYSTEM_PROTECTED_PATHS | self.USER_PROTECTED_PATHS)


class CortexUserManager:
    """Manages the cortex system user for privilege-limited execution."""

    CORTEX_USER = "cortex"
    CORTEX_GROUP = "cortex"

    @classmethod
    def user_exists(cls) -> bool:
        """Check if the cortex user exists."""
        try:
            pwd.getpwnam(cls.CORTEX_USER)
            return True
        except KeyError:
            return False

    @classmethod
    def create_user(cls) -> tuple[bool, str]:
        """Create the cortex user with basic privileges."""
        if cls.user_exists():
            return True, "Cortex user already exists"

        try:
            subprocess.run(
                ["sudo", "groupadd", "-f", cls.CORTEX_GROUP],
                check=True,
                capture_output=True,
            )

            subprocess.run(
                [
                    "sudo",
                    "useradd",
                    "-r",
                    "-g",
                    cls.CORTEX_GROUP,
                    "-d",
                    "/var/lib/cortex",
                    "-s",
                    "/bin/bash",
                    "-m",
                    cls.CORTEX_USER,
                ],
                check=True,
                capture_output=True,
            )

            subprocess.run(
                ["sudo", "mkdir", "-p", "/var/lib/cortex/workspace"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["sudo", "chown", "-R", f"{cls.CORTEX_USER}:{cls.CORTEX_GROUP}", "/var/lib/cortex"],
                check=True,
                capture_output=True,
            )

            return True, "Cortex user created successfully"

        except subprocess.CalledProcessError as e:
            return (
                False,
                f"Failed to create cortex user: {e.stderr.decode() if e.stderr else str(e)}",
            )

    @classmethod
    def grant_privilege(cls, file_path: str, mode: str = "rw") -> tuple[bool, str]:
        """Grant cortex user privilege to access a specific file."""
        if not cls.user_exists():
            return False, "Cortex user does not exist. Run setup first."

        try:
            acl_mode = ""
            if "r" in mode:
                acl_mode += "r"
            if "w" in mode:
                acl_mode += "w"
            if "x" in mode:
                acl_mode += "x"

            if not acl_mode:
                acl_mode = "r"

            subprocess.run(
                ["sudo", "setfacl", "-m", f"u:{cls.CORTEX_USER}:{acl_mode}", file_path],
                check=True,
                capture_output=True,
            )

            return True, f"Granted {acl_mode} access to {file_path}"

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            if "setfacl" in error_msg or "not found" in error_msg.lower():
                return cls._grant_privilege_chmod(file_path, mode)
            return False, f"Failed to grant privilege: {error_msg}"

    @classmethod
    def _grant_privilege_chmod(cls, file_path: str, mode: str) -> tuple[bool, str]:
        """Fallback privilege granting using chmod."""
        try:
            chmod_mode = ""
            if "r" in mode:
                chmod_mode = "o+r"
            if "w" in mode:
                chmod_mode = "o+rw" if chmod_mode else "o+w"
            if "x" in mode:
                chmod_mode = chmod_mode + "x" if chmod_mode else "o+x"

            subprocess.run(
                ["sudo", "chmod", chmod_mode, file_path],
                check=True,
                capture_output=True,
            )
            return True, f"Granted {mode} access to {file_path} (chmod fallback)"

        except subprocess.CalledProcessError as e:
            return False, f"Failed to grant privilege: {e.stderr.decode() if e.stderr else str(e)}"

    @classmethod
    def revoke_privilege(cls, file_path: str) -> tuple[bool, str]:
        """Revoke cortex user's privilege from a specific file."""
        try:
            subprocess.run(
                ["sudo", "setfacl", "-x", f"u:{cls.CORTEX_USER}", file_path],
                check=True,
                capture_output=True,
            )
            return True, f"Revoked access to {file_path}"

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            if "setfacl" in error_msg or "not found" in error_msg.lower():
                return cls._revoke_privilege_chmod(file_path)
            return False, f"Failed to revoke privilege: {error_msg}"

    @classmethod
    def _revoke_privilege_chmod(cls, file_path: str) -> tuple[bool, str]:
        """Fallback privilege revocation using chmod."""
        try:
            subprocess.run(
                ["sudo", "chmod", "o-rwx", file_path],
                check=True,
                capture_output=True,
            )
            return True, f"Revoked access to {file_path} (chmod fallback)"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to revoke privilege: {e.stderr.decode() if e.stderr else str(e)}"

    @classmethod
    def run_as_cortex(cls, command: str, timeout: int = 60) -> tuple[bool, str, str]:
        """Execute a command as the cortex user."""
        if not cls.user_exists():
            return False, "", "Cortex user does not exist"

        try:
            result = subprocess.run(
                ["sudo", "-u", cls.CORTEX_USER, "bash", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return (
                result.returncode == 0,
                result.stdout.strip(),
                result.stderr.strip(),
            )
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", str(e)
