"""
Docker Permission Management Module.

This module provides tools to diagnose and repair file ownership issues
that occur when Docker containers create files in host-mounted directories.
"""

import os
import platform
import subprocess

from cortex.branding import console

# Standard project directories to ignore during scans.
# Grouped into a constant to allow easy extension without modifying logic.
EXCLUDED_DIRS = {
    "venv",
    ".venv",
    ".git",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
}


class PermissionManager:
    """Manages and fixes Docker-related file permission issues for bind mounts.

    Attributes:
        base_path (str): The root directory of the project to scan.
        host_uid (int): The UID of the current host user.
        host_gid (int): The GID of the current host user.
    """

    def __init__(self, base_path: str):
        """Initialize the manager with the project base path and host identity.

        Args:
            base_path: The root directory of the project to scan.

        Raises:
            NotImplementedError: If the operating system is native Windows (outside WSL),
                as Unix UID/GID logic is inapplicable.
        """
        self.base_path = base_path

        # Validate environment compatibility.
        # Native Windows handles file ownership via Docker Desktop settings,
        # making Unix-style permission repairs unnecessary and potentially misleading.
        if platform.system() == "Windows":
            if "microsoft" not in platform.uname().release.lower():
                raise NotImplementedError(
                    "PermissionManager requires a Linux environment or WSL. "
                    "Native Windows handles file ownership differently via Docker Desktop settings."
                )

        # Cache system identities to avoid repeated syscalls during fix operations.
        self.host_uid = os.getuid()
        self.host_gid = os.getgid()

    def diagnose(self) -> list[str]:
        """Scans for files where ownership does not match the active host user.

        Returns:
            List[str]: A list of full file paths requiring ownership reclamation.
        """
        mismatched_files = []
        for root, dirs, files in os.walk(self.base_path):
            # Prune excluded directories in-place to optimize the recursive walk.
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

            for name in files:
                full_path = os.path.join(root, name)
                try:
                    # Capture files owned by root or mismatched container UIDs.
                    if os.stat(full_path).st_uid != self.host_uid:
                        mismatched_files.append(full_path)
                except (PermissionError, FileNotFoundError):
                    # Skip files that are inaccessible or moved during the scan.
                    continue
        return mismatched_files

    def generate_compose_settings(self) -> str:
        """Generates a YAML snippet for correct user mapping in Docker Compose.

        Returns:
            str: A formatted YAML snippet utilizing the host user's UID/GID.
        """
        return (
            f'    user: "{self.host_uid}:{self.host_gid}"\n'
            "    # Note: Indentation is 4 spaces. Adjust as needed for your file.\n"
            '    # user: "${UID}:${GID}"'
        )

    def check_compose_config(self) -> None:
        """Analyzes docker-compose.yml for missing 'user' directives using YAML parsing.

        This method avoids false positives (like occurrences in comments) by
        performing a structural analysis of the service definitions.
        """
        compose_path = os.path.join(self.base_path, "docker-compose.yml")
        if not os.path.exists(compose_path):
            return

        try:
            import yaml

            with open(compose_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            services = data.get("services", {})
            # If at least one service has a user mapping, we consider the file valid.
            has_user_mapping = any("user" in svc for svc in services.values())

            if not has_user_mapping:
                console.print(
                    "\n[bold yellow]💡 Recommended Docker-Compose settings:[/bold yellow]"
                )
                console.print(self.generate_compose_settings())
        except (ImportError, Exception):
            # Silently fallback if PyYAML is missing or the file is malformed.
            pass

    def fix_permissions(self, execute: bool = False) -> bool:
        """Repairs file ownership via sudo or provides a dry-run summary.

        Args:
            execute: If True, applies ownership changes. Defaults to False (dry-run).

        Returns:
            bool: True if operations succeeded or no mismatches were detected.
        """
        mismatches = self.diagnose()

        if not mismatches:
            console.print("[bold green]✅ No permission mismatches detected.[/bold green]")
            return True

        if not execute:
            console.print(
                f"\n[bold cyan]📋 [Dry-run][/bold cyan] Found {len(mismatches)} files mismatched."
            )
            for path in mismatches[:5]:
                console.print(f"  • {path}")
            if len(mismatches) > 5:
                console.print(f"  ... and {len(mismatches) - 5} more.")
            console.print("\n[bold yellow]👉 Run with --execute to apply repairs.[/bold yellow]")
            return True

        console.print(
            f"[bold core_blue]🔧 Applying repairs to {len(mismatches)} paths...[/bold core_blue]"
        )

        # Process in batches to avoid shell ARG_MAX limits on large projects.
        BATCH_SIZE = 100
        try:
            for i in range(0, len(mismatches), BATCH_SIZE):
                batch = mismatches[i : i + BATCH_SIZE]
                subprocess.run(
                    ["sudo", "chown", f"{self.host_uid}:{self.host_gid}"] + batch,
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
            console.print("[bold green]✅ Ownership reclaimed successfully![/bold green]")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, PermissionError) as e:
            console.print(f"[bold red]❌ Failed to fix permissions: {str(e)}[/bold red]")
            return False
