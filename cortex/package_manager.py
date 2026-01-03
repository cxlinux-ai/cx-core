import shutil
import subprocess
from typing import List, Optional
from rich.prompt import Confirm, Prompt
from rich.table import Table
from cortex.branding import console, cx_print, cx_header

class UnifiedPackageManager:
    """
    Unified manager for Snap and Flatpak packages.
    """
    def __init__(self):
        self.snap_avail = shutil.which("snap") is not None
        self.flatpak_avail = shutil.which("flatpak") is not None

    def check_backends(self):
        if not self.snap_avail and not self.flatpak_avail:
            cx_print("Warning: Neither 'snap' nor 'flatpak' found on this system.", "warning")
            cx_print("Commands will run in DRY-RUN mode or fail.", "info")

    def install(self, package: str, dry_run: bool = False):
        self.check_backends()
        
        backend = self._choose_backend("install")
        if not backend:
            return

        cmd = self._get_install_cmd(backend, package)
        self._run_cmd(cmd, dry_run)

    def remove(self, package: str, dry_run: bool = False):
        self.check_backends()
        
        backend = self._choose_backend("remove")
        if not backend:
            return

        cmd = self._get_remove_cmd(backend, package)
        self._run_cmd(cmd, dry_run)
    
    def list_packages(self):
        cx_header("Installed Packages (Snap & Flatpak)")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Package")
        table.add_column("Backend")
        table.add_column("Version", style="dim")

        # Listings would require parsing output commands like `snap list` and `flatpak list`
        # For MVP, we just show support status
        if self.snap_avail:
            table.add_row("Snap Support", "Detected", "Active")
        else:
            table.add_row("Snap Support", "Not Found", "-")
            
        if self.flatpak_avail:
            table.add_row("Flatpak Support", "Detected", "Active")
        else:
            table.add_row("Flatpak Support", "Not Found", "-")
            
        console.print(table)
        console.print("[dim](Full package listing implementation pending parsing logic)[/dim]")

    def _choose_backend(self, action: str) -> Optional[str]:
        if self.snap_avail and self.flatpak_avail:
            return Prompt.ask(
                f"Choose backend to {action}", 
                choices=["snap", "flatpak"], 
                default="snap"
            )
        elif self.snap_avail:
            return "snap"
        elif self.flatpak_avail:
            return "flatpak"
        else:
            # Fallback for testing/dry-run if forced, or just default to snap for print
            return "snap" 

    def _get_install_cmd(self, backend: str, package: str) -> List[str]:
        if backend == "snap":
            return ["sudo", "snap", "install", package]
        else:
            return ["flatpak", "install", "-y", package]

    def _get_remove_cmd(self, backend: str, package: str) -> List[str]:
        if backend == "snap":
            return ["sudo", "snap", "remove", package]
        else:
            return ["flatpak", "uninstall", "-y", package]

    def _run_cmd(self, cmd: List[str], dry_run: bool):
        cmd_str = " ".join(cmd)
        if dry_run:
            cx_print(f"[Dry Run] would execute: [bold]{cmd_str}[/bold]", "info")
            return

        cx_print(f"Running: {cmd_str}...", "info")
        try:
            subprocess.check_call(cmd)
            cx_print("Command executed successfully.", "success")
        except subprocess.CalledProcessError as e:
            cx_print(f"Command failed: {e}", "error")
        except FileNotFoundError:
             cx_print(f"Executable not found: {cmd[0]}", "error")
