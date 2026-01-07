"""
Daemon management commands for Cortex CLI
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich import print as rprint
from rich.console import Console

# Table import removed - alerts now use custom formatting for AI analysis
from rich.panel import Panel

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
                    panel = Panel(
                        self.client.format_status(status),
                        title="[bold]Daemon Status[/bold]",
                        border_style="green",
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
            result = subprocess.run(["sudo", str(script_path)], check=False)
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

        if not self.confirm("Continue with uninstallation?"):
            return 1

        script_path = Path(__file__).parent.parent / "daemon" / "scripts" / "uninstall.sh"

        if not script_path.exists():
            console.print(f"[red]✗ Uninstall script not found: {script_path}[/red]")
            return 1

        try:
            result = subprocess.run(["sudo", str(script_path)], check=False)
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
                border_style="green",
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

    def alerts(
        self,
        severity: str | None = None,
        acknowledge_all: bool = False,
        dismiss_id: str | None = None,
    ) -> int:
        """Show daemon alerts"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            self.show_daemon_setup_help()
            return 1

        try:
            if dismiss_id:
                if self.client.dismiss_alert(dismiss_id):
                    console.print(f"[green]✓ Dismissed alert: {dismiss_id}[/green]")
                    return 0
                else:
                    console.print(f"[red]✗ Alert not found: {dismiss_id}[/red]")
                    return 1

            if acknowledge_all:
                count = self.client.acknowledge_all_alerts()
                console.print(f"[green]✓ Acknowledged {count} alerts[/green]")
                return 0

            alerts = (
                self.client.get_alerts(severity=severity)
                if severity
                else self.client.get_active_alerts()
            )

            if not alerts:
                console.print("[green]✓ No active alerts[/green]")
                return 0

            console.print(f"\n[bold]Active Alerts ({len(alerts)})[/bold]\n")

            for alert in alerts:
                severity_val = alert.get("severity", "info")
                severity_style = {
                    "info": "blue",
                    "warning": "yellow",
                    "error": "red",
                    "critical": "red bold",
                }.get(severity_val, "white")

                alert_id = alert.get("id", "")[:8]
                alert_type = alert.get("type", "unknown")
                title = alert.get("title", "")
                message = alert.get("message", "")
                metadata = alert.get("metadata", {})
                is_ai_enhanced = metadata.get("ai_enhanced") == "true"

                # Severity icon
                severity_icon = {
                    "info": "ℹ️ ",
                    "warning": "⚠️ ",
                    "error": "❌",
                    "critical": "🚨",
                }.get(severity_val, "•")

                # Print alert header
                console.print(
                    f"{severity_icon} [{severity_style}][bold]{title}[/bold][/{severity_style}]"
                )
                console.print(
                    f"   [dim]ID: {alert_id}... | Type: {alert_type} | Severity: {severity_val}[/dim]"
                )

                # Check if message contains AI analysis
                if "💡 AI Analysis:" in message:
                    # Split into basic message and AI analysis
                    parts = message.split("\n\n💡 AI Analysis:\n", 1)
                    basic_msg = parts[0]
                    ai_analysis = parts[1] if len(parts) > 1 else ""

                    # Print basic message
                    console.print(f"   {basic_msg}")

                    # Print AI analysis in a highlighted box
                    if ai_analysis:
                        console.print()
                        console.print("   [cyan]💡 AI Analysis:[/cyan]")
                        # Indent each line of AI analysis
                        for line in ai_analysis.strip().split("\n"):
                            console.print(f"   [italic]{line}[/italic]")
                else:
                    # Print regular message
                    for line in message.split("\n"):
                        console.print(f"   {line}")

                # Add badge for AI-enhanced alerts
                if is_ai_enhanced:
                    console.print("   [dim cyan]🤖 AI-enhanced[/dim cyan]")

                console.print()  # Blank line between alerts

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
        except DaemonProtocolError as e:
            console.print(f"[red]✗ Protocol error: {e}[/red]")
            return 1

    def version(self) -> int:
        """Show daemon version"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            self.show_daemon_setup_help()
            return 1

        try:
            version_info = self.client.get_version()
            console.print(
                f"[cyan]{version_info.get('name', 'cortexd')}[/cyan] version [green]{version_info.get('version', 'unknown')}[/green]"
            )
            return 0
        except DaemonConnectionError as e:
            console.print(f"[red]✗ Connection error: {e}[/red]")
            console.print("\n[yellow]Hint: Is the daemon running?[/yellow]")
            console.print("  Start it with: [cyan]systemctl start cortexd[/cyan]\n")
            return 1
        except DaemonProtocolError as e:
            console.print(f"[red]✗ Protocol error: {e}[/red]")
            return 1

    def config(self) -> int:
        """Show current daemon configuration"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            self.show_daemon_setup_help()
            return 1

        try:
            config = self.client.get_config()

            # Format config for display
            lines = [
                f"  Socket Path:        {config.get('socket_path', 'N/A')}",
                f"  Model Path:         {config.get('model_path', 'N/A') or 'Not configured'}",
                f"  LLM Context:        {config.get('llm_context_length', 'N/A')}",
                f"  LLM Threads:        {config.get('llm_threads', 'N/A')}",
                f"  Monitor Interval:   {config.get('monitor_interval_sec', 'N/A')}s",
                f"  Log Level:          {config.get('log_level', 'N/A')}",
            ]

            thresholds = config.get("thresholds", {})
            if thresholds:
                lines.append("")
                lines.append("  Thresholds:")
                lines.append(f"    Disk Warning:     {thresholds.get('disk_warn', 0) * 100:.0f}%")
                lines.append(f"    Disk Critical:    {thresholds.get('disk_crit', 0) * 100:.0f}%")
                lines.append(f"    Memory Warning:   {thresholds.get('mem_warn', 0) * 100:.0f}%")
                lines.append(f"    Memory Critical:  {thresholds.get('mem_crit', 0) * 100:.0f}%")

            panel = Panel(
                "\n".join(lines), title="[bold]Daemon Configuration[/bold]", border_style="cyan"
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

    def llm_status(self) -> int:
        """Show LLM engine status"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            self.show_daemon_setup_help()
            return 1

        try:
            status = self.client.get_llm_status()

            lines = [
                f"  Loaded:             {'Yes' if status.get('loaded') else 'No'}",
                f"  Running:            {'Yes' if status.get('running') else 'No'}",
                f"  Healthy:            {'Yes' if status.get('healthy') else 'No'}",
                f"  Queue Size:         {status.get('queue_size', 0)}",
                f"  Memory Usage:       {status.get('memory_bytes', 0) / 1024 / 1024:.1f} MB",
            ]

            if status.get("loaded") and status.get("model"):
                model = status["model"]
                lines.append("")
                lines.append("  Model:")
                lines.append(f"    Name:             {model.get('name', 'unknown')}")
                lines.append(f"    Path:             {model.get('path', 'unknown')}")
                lines.append(f"    Context Length:   {model.get('context_length', 0)}")
                lines.append(f"    Quantized:        {'Yes' if model.get('quantized') else 'No'}")

            panel = Panel(
                "\n".join(lines), title="[bold]LLM Engine Status[/bold]", border_style="cyan"
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

    def llm_load(self, model_path: str) -> int:
        """Load an LLM model"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            self.show_daemon_setup_help()
            return 1

        console.print(f"[cyan]Loading model: {model_path}[/cyan]")
        console.print("[dim]This may take a minute depending on model size...[/dim]")

        try:
            result = self.client.load_model(model_path)
            if result.get("loaded"):
                console.print("[green]✓ Model loaded successfully[/green]")
                if "model" in result:
                    model = result["model"]
                    console.print(f"  Name: {model.get('name', 'unknown')}")
                    console.print(f"  Context: {model.get('context_length', 0)}")
                return 0
            else:
                console.print("[red]✗ Failed to load model[/red]")
                return 1
        except DaemonConnectionError as e:
            console.print(f"[red]✗ Connection error: {e}[/red]")
            return 1
        except DaemonProtocolError as e:
            console.print(f"[red]✗ Error: {e}[/red]")
            return 1

    def llm_unload(self) -> int:
        """Unload the current LLM model"""
        if not self.check_daemon_installed():
            console.print("[red]✗ Daemon is not installed[/red]")
            self.show_daemon_setup_help()
            return 1

        try:
            if self.client.unload_model():
                console.print("[green]✓ Model unloaded[/green]")
                return 0
            else:
                console.print("[red]✗ Failed to unload model[/red]")
                return 1
        except DaemonConnectionError as e:
            console.print(f"[red]✗ Connection error: {e}[/red]")
            return 1
        except DaemonProtocolError as e:
            console.print(f"[red]✗ Error: {e}[/red]")
            return 1

    @staticmethod
    def confirm(message: str) -> bool:
        """Ask user for confirmation"""
        response = console.input(f"[yellow]{message} [y/N][/yellow] ")
        return response.lower() == "y"
