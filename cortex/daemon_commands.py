"""
Daemon management commands for Cortex CLI
"""

import sys
import os
import subprocess
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from cortex.daemon_client import CortexDaemonClient, DaemonConnectionError, DaemonProtocolError

console = Console()

class DaemonManager:
    """Manages cortexd daemon operations"""

    def __init__(self):
        self.client = CortexDaemonClient()

    def check_daemon_installed(self) -> bool:
        """Check if cortexd binary is installed"""
        return Path("/usr/local/bin/cortexd").exists()

    def check_daemon_built(self) -> bool:
        """Check if cortexd is built in the project"""
        build_dir = Path(__file__).parent.parent / "daemon" / "build" / "cortexd"
        return build_dir.exists()

    def show_daemon_setup_help(self) -> None:
        """Show help for setting up the daemon"""
        console.print("\n[yellow]Cortexd daemon is not set up.[/yellow]\n")
        console.print("[cyan]To build and install the daemon:[/cyan]")
        console.print("  1. Build: [bold]cd daemon && ./scripts/build.sh Release[/bold]")
        console.print("  2. Install: [bold]sudo ./daemon/scripts/install.sh[/bold]")
        console.print("\n[cyan]Or use cortex CLI:[/cyan]")
        console.print("  [bold]cortex daemon install[/bold]\n")

    def status(self, verbose: bool = False) -> int:
        """Check daemon status"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            self.show_daemon_setup_help()
            return 1

        try:
            if not self.client.is_running():
                console.print("[red]✗ Daemon is not running[/red]")
                console.print("Start it with: [cyan]systemctl start cortexd[/cyan]")
                return 1

            console.print("[green]✓ Daemon is running[/green]")

            if verbose:
                try:
                    status = self.client.get_status()
                    health = self.client.get_health()

                    panel = Panel(
                        self.client.format_health_snapshot(health),
                        title="[bold]Daemon Status[/bold]",
                        border_style="green"
                    )
                    console.print(panel)
                except (DaemonConnectionError, DaemonProtocolError) as e:
                    console.print(f"[yellow]Warning: Could not get detailed status: {e}[/yellow]")

            return 0

        except DaemonConnectionError as e:
            console.print(f"[red]✗ Connection error: {e}[/red]")
            return 1

    def install(self) -> int:
        """Install and start the daemon"""
        console.print("[cyan]Installing cortexd daemon...[/cyan]")

        # Check if daemon is built
        if not self.check_daemon_built():
            console.print("\n[red]✗ Cortexd binary not found![/red]")
            console.print("\n[cyan]Please build the daemon first:[/cyan]")
            console.print("  [bold]cd daemon && ./scripts/build.sh Release[/bold]\n")
            return 1

        script_path = Path(__file__).parent.parent / "daemon" / "scripts" / "install.sh"

        if not script_path.exists():
            console.print(f"[red]✗ Install script not found: {script_path}[/red]")
            return 1

        try:
            result = subprocess.run(
                ["sudo", str(script_path)],
                check=False
            )
            return result.returncode
        except Exception as e:
            console.print(f"[red]✗ Installation failed: {e}[/red]")
            return 1

    def uninstall(self) -> int:
        """Uninstall and stop the daemon"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            console.print("[yellow]Nothing to uninstall[/yellow]\n")
            return 1

        console.print("[yellow]Uninstalling cortexd daemon...[/yellow]")

        if not self.confirm("Continue with uninstallation?(y/n)"):
            return 1

        script_path = Path(__file__).parent.parent / "daemon" / "scripts" / "uninstall.sh"

        if not script_path.exists():
            console.print(f"[red]✗ Uninstall script not found: {script_path}[/red]")
            return 1

        try:
            result = subprocess.run(
                ["sudo", str(script_path)],
                check=False
            )
            return result.returncode
        except Exception as e:
            console.print(f"[red]✗ Uninstallation failed: {e}[/red]")
            return 1

    def health(self) -> int:
        """Show daemon health snapshot"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            self.show_daemon_setup_help()
            return 1

        try:
            health = self.client.get_health()
            panel = Panel(
                self.client.format_health_snapshot(health),
                title="[bold]Daemon Health[/bold]",
                border_style="green"
            )
            console.print(panel)
            return 0
        except DaemonConnectionError as e:
            console.print(f"[red]✗ Connection error: {e}[/red]")
            console.print("\n[yellow]Hint: Is the daemon running?[/yellow]")
            console.print("  Start it with: [cyan]systemctl start cortexd[/cyan]\n")
            return 1
        except DaemonProtocolError as e:
            console.print(f"[red]✗ Protocol error: {e}[/red]")
            return 1

    def alerts(self, severity: Optional[str] = None, acknowledge_all: bool = False) -> int:
        """Show daemon alerts"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            self.show_daemon_setup_help()
            return 1

        try:
            alerts = self.client.get_alerts(severity=severity) if severity else self.client.get_active_alerts()

            if not alerts:
                console.print("[green]✓ No alerts[/green]")
                return 0

            # Display alerts in table
            table = Table(title="Active Alerts")
            table.add_column("ID", style="dim")
            table.add_column("Severity")
            table.add_column("Type")
            table.add_column("Title")
            table.add_column("Description")

            for alert in alerts:
                severity_style = {
                    "info": "blue",
                    "warning": "yellow",
                    "error": "red",
                    "critical": "red bold"
                }.get(alert.get("severity", "info"), "white")

                table.add_row(
                    alert.get("id", "")[:8],
                    f"[{severity_style}]{alert.get('severity', 'unknown')}[/{severity_style}]",
                    alert.get("type", "unknown"),
                    alert.get("title", ""),
                    alert.get("description", "")[:50]
                )

            console.print(table)

            if acknowledge_all:
                for alert in alerts:
                    self.client.acknowledge_alert(alert.get("id", ""))
                console.print("[green]✓ All alerts acknowledged[/green]")

            return 0

        except DaemonConnectionError as e:
            console.print(f"[red]✗ Connection error: {e}[/red]")
            console.print("\n[yellow]Hint: Is the daemon running?[/yellow]")
            console.print("  Start it with: [cyan]systemctl start cortexd[/cyan]\n")
            return 1
        except DaemonProtocolError as e:
            console.print(f"[red]✗ Protocol error: {e}[/red]")
            return 1

    def reload_config(self) -> int:
        """Reload daemon configuration"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            self.show_daemon_setup_help()
            return 1

        try:
            if self.client.reload_config():
                console.print("[green]✓ Configuration reloaded[/green]")
                return 0
            else:
                console.print("[red]✗ Failed to reload configuration[/red]")
                return 1
        except DaemonConnectionError as e:
            console.print(f"[red]✗ Connection error: {e}[/red]")
            console.print("\n[yellow]Hint: Is the daemon running?[/yellow]")
            console.print("  Start it with: [cyan]systemctl start cortexd[/cyan]\n")
            return 1

    @staticmethod
    def confirm(message: str) -> bool:
        """Ask user for confirmation"""
        response = console.input(f"[yellow]{message} [y/N][/yellow] ")
        return response.lower() == 'y'
