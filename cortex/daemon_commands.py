"""
Daemon management commands for Cortex CLI
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console

# Table import removed - alerts now use custom formatting for AI analysis
from rich.panel import Panel

from cortex.daemon_client import CortexDaemonClient, DaemonConnectionError, DaemonProtocolError

console = Console()

# Paths for LLM service
LLM_SERVICE_NAME = "cortex-llm.service"
LLM_ENV_FILE = Path("/etc/cortex/llm.env")
DAEMON_CONFIG_FILE = Path("/etc/cortex/daemon.yaml")
INSTALL_LLM_SCRIPT = Path(__file__).parent.parent / "daemon" / "scripts" / "install-llm.sh"


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

    def check_llm_service_installed(self) -> bool:
        """Check if cortex-llm.service is installed"""
        result = subprocess.run(
            ["systemctl", "list-unit-files", LLM_SERVICE_NAME],
            capture_output=True,
            text=True,
            check=False,
        )
        return LLM_SERVICE_NAME in result.stdout

    def check_llm_service_running(self) -> bool:
        """Check if cortex-llm.service is running"""
        result = subprocess.run(
            ["systemctl", "is-active", LLM_SERVICE_NAME],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() == "active"

    def get_llm_backend(self) -> str:
        """Get the configured LLM backend from daemon config or environment.
        
        Returns:
            str: "cloud", "local", or "none"
        """
        # Check environment variable first
        provider = os.environ.get("CORTEX_PROVIDER", "").lower()
        if provider == "llama_cpp":
            return "local"
        elif provider in ("claude", "openai", "ollama"):
            return "cloud"
        
        # Check daemon config
        if DAEMON_CONFIG_FILE.exists():
            try:
                with open(DAEMON_CONFIG_FILE) as f:
                    config = yaml.safe_load(f) or {}
                llm_config = config.get("llm", {})
                backend = llm_config.get("backend", "none")
                return backend
            except (yaml.YAMLError, OSError):
                pass
        
        return "none"

    def get_llm_service_info(self) -> dict:
        """Get information about the cortex-llm.service"""
        info = {
            "installed": self.check_llm_service_installed(),
            "running": False,
            "model_path": None,
            "threads": None,
            "ctx_size": None,
            "error": None,
        }
        
        if info["installed"]:
            info["running"] = self.check_llm_service_running()
            
            # Get service status/error if not running
            if not info["running"]:
                result = subprocess.run(
                    ["systemctl", "status", LLM_SERVICE_NAME],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                # Extract error from status output
                if "code=exited" in result.stdout:
                    info["error"] = "Service exited with error"
                elif "not-found" in result.stdout.lower():
                    info["error"] = "llama-server not found"
        
        # Read config from env file (may need sudo, try both ways)
        env_content = None
        if LLM_ENV_FILE.exists():
            try:
                with open(LLM_ENV_FILE) as f:
                    env_content = f.read()
            except PermissionError:
                # Try with sudo
                result = subprocess.run(
                    ["sudo", "cat", str(LLM_ENV_FILE)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    env_content = result.stdout
            except OSError:
                pass
        
        if env_content:
            for line in env_content.splitlines():
                line = line.strip()
                if line.startswith("CORTEX_LLM_MODEL_PATH="):
                    info["model_path"] = line.split("=", 1)[1]
                elif line.startswith("CORTEX_LLM_THREADS="):
                    info["threads"] = line.split("=", 1)[1]
                elif line.startswith("CORTEX_LLM_CTX_SIZE="):
                    info["ctx_size"] = line.split("=", 1)[1]
        
        return info

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
        """Install and start the daemon with interactive setup"""
        console.print("[cyan]Starting cortexd daemon setup...[/cyan]\n")

        # Use the interactive setup_daemon.py script
        script_path = Path(__file__).parent.parent / "daemon" / "scripts" / "setup_daemon.py"

        if not script_path.exists():
            console.print(f"[red]✗ Setup script not found: {script_path}[/red]")
            return 1

        try:
            # Run the setup script with Python
            result = subprocess.run([sys.executable, str(script_path)], check=False)
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
            
            # Also show LLM service status if using local backend
            backend = self.get_llm_backend()
            if backend == "local":
                llm_info = self.get_llm_service_info()
                lines = [
                    f"  Backend:            Local (llama.cpp)",
                    f"  Service Installed:  {'Yes' if llm_info['installed'] else 'No'}",
                    f"  Service Running:    {'Yes' if llm_info['running'] else 'No'}",
                ]
                if llm_info["model_path"]:
                    lines.append(f"  Model:              {llm_info['model_path']}")
                if llm_info["threads"]:
                    lines.append(f"  Threads:            {llm_info['threads']}")
                
                panel = Panel(
                    "\n".join(lines),
                    title="[bold]LLM Service Status[/bold]",
                    border_style="cyan",
                )
                console.print(panel)
            elif backend == "cloud":
                provider = os.environ.get("CORTEX_PROVIDER", "unknown")
                console.print(f"\n[cyan]LLM Backend: Cloud API ({provider})[/cyan]")
            
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
        alert_type: str | None = None,
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

            # Filter alerts by severity and/or type
            if severity or alert_type:
                alerts = self.client.get_alerts(severity=severity, alert_type=alert_type)
            else:
                alerts = self.client.get_active_alerts()

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

                alert_id_full = alert.get("id", "")
                alert_type_val = alert.get("type", "unknown")
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
                console.print(f"   [dim]Type: {alert_type_val} | Severity: {severity_val}[/dim]")
                # Show full ID on separate line for easy copying (needed for dismiss command)
                console.print(f"   [dim]ID: [/dim][cyan]{alert_id_full}[/cyan]")

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

            # Show helpful commands
            console.print("[dim]─" * 50 + "[/dim]")
            console.print(
                "[dim]To dismiss an alert: [/dim][cyan]cortex daemon alerts --dismiss <ID>[/cyan]"
            )
            console.print(
                "[dim]To acknowledge all:  [/dim][cyan]cortex daemon alerts --acknowledge-all[/cyan]"
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

            # Format daemon config for display
            lines = [
                f"  Socket Path:        {config.get('socket_path', 'N/A')}",
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
            
            # Show LLM configuration based on backend
            backend = self.get_llm_backend()
            llm_lines = [f"  Backend:            {backend.capitalize() if backend else 'None'}"]
            
            if backend == "local":
                llm_info = self.get_llm_service_info()
                if llm_info["model_path"]:
                    llm_lines.append(f"  Model Path:         {llm_info['model_path']}")
                else:
                    llm_lines.append(f"  Model Path:         [yellow]Not configured[/yellow]")
                if llm_info["threads"]:
                    llm_lines.append(f"  Threads:            {llm_info['threads']}")
                if llm_info["ctx_size"]:
                    llm_lines.append(f"  Context Size:       {llm_info['ctx_size']}")
                llm_url = os.environ.get("LLAMA_CPP_BASE_URL", "http://127.0.0.1:8085")
                llm_lines.append(f"  API URL:            {llm_url}")
            elif backend == "cloud":
                provider = os.environ.get("CORTEX_PROVIDER", "unknown")
                llm_lines.append(f"  Provider:           {provider.capitalize()}")
            else:
                llm_lines.append(f"  [dim]Run setup: python daemon/scripts/setup_daemon.py[/dim]")
            
            llm_panel = Panel(
                "\n".join(llm_lines), title="[bold]LLM Configuration[/bold]", border_style="cyan"
            )
            console.print(llm_panel)
            
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
        backend = self.get_llm_backend()
        
        if backend == "local":
            # Show cortex-llm.service status
            return self._llm_status_local()
        elif backend == "cloud":
            # Show cloud provider info
            return self._llm_status_cloud()
        else:
            console.print("[yellow]LLM backend not configured[/yellow]")
            console.print("\n[cyan]Configure LLM with:[/cyan]")
            console.print("  [bold]python daemon/scripts/setup_daemon.py[/bold]\n")
            return 0

    def _llm_status_local(self) -> int:
        """Show status for local llama.cpp service"""
        llm_info = self.get_llm_service_info()
        
        if not llm_info["installed"]:
            console.print("[yellow]⚠ cortex-llm.service is not installed[/yellow]")
            console.print("\n[cyan]Install with:[/cyan]")
            console.print("  [bold]sudo daemon/scripts/install-llm.sh install <model_path>[/bold]\n")
            return 1
        
        status_icon = "✓" if llm_info["running"] else "✗"
        status_color = "green" if llm_info["running"] else "red"
        status_text = "Running" if llm_info["running"] else "Stopped"
        
        lines = [
            f"  Backend:            Local (llama.cpp)",
            f"  Service:            cortex-llm.service",
            f"  Status:             [{status_color}]{status_icon} {status_text}[/{status_color}]",
        ]
        
        if llm_info["model_path"]:
            model_path = Path(llm_info["model_path"])
            lines.append(f"  Model:              {model_path.name}")
            lines.append(f"  Model Path:         {llm_info['model_path']}")
            
            # Check if model file exists
            if not Path(llm_info["model_path"]).expanduser().exists():
                lines.append(f"  [red]⚠ Model file not found![/red]")
        else:
            lines.append(f"  Model:              [yellow]Not configured[/yellow]")
            
        if llm_info["threads"]:
            lines.append(f"  Threads:            {llm_info['threads']}")
        if llm_info["ctx_size"]:
            lines.append(f"  Context Size:       {llm_info['ctx_size']}")
        
        # Get URL
        llm_url = os.environ.get("LLAMA_CPP_BASE_URL", "http://127.0.0.1:8085")
        lines.append(f"  API URL:            {llm_url}")
        
        panel = Panel(
            "\n".join(lines),
            title="[bold]LLM Engine Status (Local)[/bold]",
            border_style="cyan",
        )
        console.print(panel)
        
        # Show troubleshooting info if not running
        if not llm_info["running"]:
            console.print()
            
            # Check for common issues
            issues = []
            
            # Check if llama-server is installed
            llama_server_check = subprocess.run(
                ["which", "llama-server"],
                capture_output=True,
                text=True,
                check=False,
            )
            if llama_server_check.returncode != 0:
                issues.append("llama-server is not installed")
                console.print("[red]✗ llama-server not found in PATH[/red]")
                console.print("  Install from: https://github.com/ggerganov/llama.cpp")
            
            # Check if model is configured
            if not llm_info["model_path"]:
                issues.append("No model configured")
                console.print("[red]✗ No model path configured in /etc/cortex/llm.env[/red]")
                console.print("  Configure with: [bold]cortex daemon llm load <model_path>[/bold]")
            elif not Path(llm_info["model_path"]).expanduser().exists():
                issues.append("Model file not found")
                console.print(f"[red]✗ Model file not found: {llm_info['model_path']}[/red]")
            
            if not issues:
                console.print("[cyan]Start the service with:[/cyan]")
                console.print("  [bold]sudo systemctl start cortex-llm[/bold]")
                console.print("\n[dim]View logs with: journalctl -u cortex-llm -f[/dim]")
            
            console.print()
        
        return 0

    def _llm_status_cloud(self) -> int:
        """Show status for cloud LLM provider"""
        provider = os.environ.get("CORTEX_PROVIDER", "unknown")
        
        # Check API key
        api_key_vars = {
            "claude": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "ollama": "OLLAMA_BASE_URL",
        }
        api_key_var = api_key_vars.get(provider, f"{provider.upper()}_API_KEY")
        has_key = bool(os.environ.get(api_key_var))
        
        key_status = "[green]✓ Configured[/green]" if has_key else "[red]✗ Not set[/red]"
        
        lines = [
            f"  Backend:            Cloud API",
            f"  Provider:           {provider.capitalize()}",
            f"  API Key ({api_key_var}): {key_status}",
        ]
        
        panel = Panel(
            "\n".join(lines),
            title="[bold]LLM Engine Status (Cloud)[/bold]",
            border_style="cyan",
        )
        console.print(panel)
        
        if not has_key:
            console.print(f"\n[yellow]Set your API key:[/yellow]")
            console.print(f"  [bold]export {api_key_var}=your-api-key[/bold]\n")
        
        return 0

    def llm_load(self, model_path: str) -> int:
        """Load an LLM model"""
        backend = self.get_llm_backend()
        
        if backend == "cloud":
            console.print("[yellow]Cloud backend is configured - no local model loading needed[/yellow]")
            console.print("\n[cyan]To switch to local llama.cpp:[/cyan]")
            console.print("  [bold]export CORTEX_PROVIDER=llama_cpp[/bold]")
            console.print("  [bold]cortex daemon llm load <model_path>[/bold]\n")
            return 1
        else:
            # Use cortex-llm.service for local backend
            return self._llm_load_local(model_path)

    def _llm_load_local(self, model_path: str) -> int:
        """Load model using cortex-llm.service"""
        model_file = Path(model_path).expanduser().resolve()
        
        if not model_file.exists():
            console.print(f"[red]✗ Model file not found: {model_path}[/red]")
            return 1
        
        if not model_file.suffix == ".gguf":
            console.print(f"[yellow]⚠ Expected .gguf file, got: {model_file.suffix}[/yellow]")
        
        console.print(f"[cyan]Configuring cortex-llm service with model: {model_file.name}[/cyan]")
        
        # Check if install script exists
        if not INSTALL_LLM_SCRIPT.exists():
            console.print(f"[red]✗ Install script not found: {INSTALL_LLM_SCRIPT}[/red]")
            return 1
        
        # Configure the service with the new model
        try:
            result = subprocess.run(
                ["sudo", str(INSTALL_LLM_SCRIPT), "configure", str(model_file)],
                check=False,
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                console.print(f"[red]✗ Failed to configure service[/red]")
                if result.stderr:
                    console.print(f"[dim]{result.stderr}[/dim]")
                return 1
            
            console.print("[green]✓ Model configured successfully[/green]")
            console.print(f"  Model: {model_file.name}")
            console.print(f"  Path: {model_file}")
            
            # Check if service is running
            if self.check_llm_service_running():
                console.print("[green]✓ Service restarted with new model[/green]")
            else:
                console.print("\n[cyan]Start the service with:[/cyan]")
                console.print("  [bold]sudo systemctl start cortex-llm[/bold]\n")
            
            return 0
            
        except Exception as e:
            console.print(f"[red]✗ Error: {e}[/red]")
            return 1

    def llm_unload(self) -> int:
        """Unload the current LLM model"""
        backend = self.get_llm_backend()
        
        if backend == "cloud":
            console.print("[yellow]Cloud backend - no local model to unload[/yellow]")
            return 0
        else:
            # Use cortex-llm.service for local backend
            return self._llm_unload_local()

    def _llm_unload_local(self) -> int:
        """Unload model by stopping cortex-llm.service"""
        if not self.check_llm_service_installed():
            console.print("[yellow]cortex-llm.service is not installed[/yellow]")
            return 0
        
        if not self.check_llm_service_running():
            console.print("[yellow]cortex-llm.service is not running[/yellow]")
            return 0
        
        console.print("[cyan]Stopping cortex-llm service...[/cyan]")
        
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "stop", LLM_SERVICE_NAME],
                check=False,
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                console.print("[green]✓ Model unloaded (service stopped)[/green]")
                return 0
            else:
                console.print(f"[red]✗ Failed to stop service[/red]")
                if result.stderr:
                    console.print(f"[dim]{result.stderr}[/dim]")
                return 1
                
        except Exception as e:
            console.print(f"[red]✗ Error: {e}[/red]")
            return 1

    @staticmethod
    def confirm(message: str) -> bool:
        """Ask user for confirmation"""
        response = console.input(f"[yellow]{message} [y/N][/yellow] ")
        return response.lower() == "y"
