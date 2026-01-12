"""
Systemd Service Helper for Cortex Linux.
Provides plain-English explanations, unit file generation,
failure diagnostics, and dependency visualization.
"""

import re
import shlex
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.tree import Tree

from cortex.branding import console


class ServiceState(Enum):
    """Possible states of a systemd service."""

    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    INACTIVE = "inactive"
    ACTIVATING = "activating"
    DEACTIVATING = "deactivating"
    UNKNOWN = "unknown"


@dataclass
class ServiceStatus:
    """Parsed status information for a systemd service.

    Attributes:
        name: The service name (without .service suffix).
        state: Current state of the service.
        description: Human-readable description of the service.
        load_state: Whether the unit file is loaded.
        active_state: Active state (active, inactive, failed).
        sub_state: Sub-state providing more detail.
        pid: Process ID if running.
        memory: Memory usage if available.
        cpu: CPU time if available.
        started_at: When the service started.
        exit_code: Exit code if service failed.
        main_pid_code: The exit status of the main process.
    """

    name: str
    state: ServiceState
    description: str = ""
    load_state: str = ""
    active_state: str = ""
    sub_state: str = ""
    pid: Optional[int] = None
    memory: str = ""
    cpu: str = ""
    started_at: str = ""
    exit_code: Optional[int] = None
    main_pid_code: str = ""


class SystemdHelper:
    """
    Helper for managing and understanding systemd services.

    Provides plain-English explanations of service status,
    generates unit files from simple descriptions, diagnoses
    failures, and visualizes service dependencies.
    """

    def __init__(self) -> None:
        """Initialize the SystemdHelper."""
        self._check_systemd_available()

    def _check_systemd_available(self) -> None:
        """Check if systemd is available on the system.

        Raises:
            RuntimeError: If systemd is not available.
        """
        try:
            result = subprocess.run(
                ["systemctl", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise RuntimeError("systemd is not available on this system")
        except FileNotFoundError:
            raise RuntimeError("systemctl command not found - is systemd installed?")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Timeout checking systemd availability")

    def get_service_status(self, service_name: str) -> ServiceStatus:
        """Get the status of a systemd service.

        Args:
            service_name: Name of the service (with or without .service suffix).

        Returns:
            ServiceStatus object with parsed information.

        Raises:
            ValueError: If the service name is empty.
        """
        if not service_name:
            raise ValueError("Service name cannot be empty")

        # Normalize service name
        if not service_name.endswith(".service"):
            service_name = f"{service_name}.service"

        try:
            result = subprocess.run(
                ["systemctl", "show", service_name, "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to get service status for {service_name}: {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Timeout getting service status for {service_name}")

        properties = {}
        for line in result.stdout.strip().split("\n"):
            if "=" in line:
                key, _, value = line.partition("=")
                properties[key] = value

        # Determine state
        active_state = properties.get("ActiveState", "unknown")
        sub_state = properties.get("SubState", "")

        if active_state == "active" and sub_state == "running":
            state = ServiceState.RUNNING
        elif active_state == "failed":
            state = ServiceState.FAILED
        elif active_state == "inactive":
            state = ServiceState.INACTIVE
        elif active_state == "activating":
            state = ServiceState.ACTIVATING
        elif active_state == "deactivating":
            state = ServiceState.DEACTIVATING
        else:
            state = ServiceState.UNKNOWN

        # Parse PID
        pid = None
        main_pid = properties.get("MainPID", "0")
        if main_pid.isdigit() and int(main_pid) > 0:
            pid = int(main_pid)

        # Parse exit code
        exit_code = None
        exec_main_status = properties.get("ExecMainStatus", "0")
        if exec_main_status.isdigit():
            exit_code = int(exec_main_status)

        return ServiceStatus(
            name=service_name.replace(".service", ""),
            state=state,
            description=properties.get("Description", ""),
            load_state=properties.get("LoadState", ""),
            active_state=active_state,
            sub_state=sub_state,
            pid=pid,
            memory=properties.get("MemoryCurrent", ""),
            cpu=properties.get("CPUUsageNSec", ""),
            started_at=properties.get("ActiveEnterTimestamp", ""),
            exit_code=exit_code,
            main_pid_code=properties.get("ExecMainCode", ""),
        )

    def explain_status(self, service_name: str) -> str:
        """Explain a service's status in plain English.

        Args:
            service_name: Name of the service to explain.

        Returns:
            Human-readable explanation of the service status.
        """
        status = self.get_service_status(service_name)

        explanations = []

        # Main status
        if status.state == ServiceState.RUNNING:
            explanations.append(f"[green]'{status.name}' is running normally.[/green]")
            if status.pid:
                explanations.append(f"  Process ID: {status.pid}")
            if status.started_at:
                explanations.append(f"  Started: {status.started_at}")
        elif status.state == ServiceState.FAILED:
            explanations.append(f"[red]'{status.name}' has failed![/red]")
            if status.exit_code and status.exit_code != 0:
                explanations.append(f"  Exit code: {status.exit_code}")
                explanations.append(self._explain_exit_code(status.exit_code))
        elif status.state == ServiceState.INACTIVE:
            explanations.append(f"[yellow]'{status.name}' is not running (inactive).[/yellow]")
            explanations.append("  The service is stopped but can be started.")
        elif status.state == ServiceState.ACTIVATING:
            explanations.append(f"[cyan]'{status.name}' is starting up...[/cyan]")
        elif status.state == ServiceState.DEACTIVATING:
            explanations.append(f"[cyan]'{status.name}' is shutting down...[/cyan]")
        else:
            explanations.append(f"[yellow]'{status.name}' is in an unknown state.[/yellow]")

        if status.description:
            explanations.append(f"  Description: {status.description}")

        return "\n".join(explanations)

    def _explain_exit_code(self, exit_code: int) -> str:
        """Provide explanation for common exit codes.

        Args:
            exit_code: The exit code to explain.

        Returns:
            Human-readable explanation of the exit code.
        """
        common_codes = {
            1: "  Likely cause: General error or misconfiguration",
            2: "  Likely cause: Misuse of command or invalid arguments",
            126: "  Likely cause: Command found but not executable (permission issue)",
            127: "  Likely cause: Command not found (check if binary exists)",
            128: "  Likely cause: Invalid exit argument",
            130: "  Likely cause: Script terminated by Ctrl+C",
            137: "  Likely cause: Process killed (SIGKILL) - possibly out of memory",
            139: "  Likely cause: Segmentation fault (SIGSEGV) - program crash",
            143: "  Likely cause: Process terminated (SIGTERM) - graceful shutdown requested",
            255: "  Likely cause: Exit status out of range or SSH error",
        }
        return common_codes.get(
            exit_code, f"  Exit code {exit_code} - check service logs for details"
        )

    def diagnose_failure(self, service_name: str, lines: int = 50) -> str:
        """Diagnose why a service failed using journal logs.

        Args:
            service_name: Name of the service to diagnose.
            lines: Number of log lines to analyze.

        Returns:
            Diagnostic report with actionable advice.
        """
        status = self.get_service_status(service_name)

        report = []
        report.append(f"[bold]Diagnostic Report for '{service_name}'[/bold]\n")

        # Get status explanation
        report.append(self.explain_status(service_name))
        report.append("")

        # Get recent logs
        result = subprocess.run(
            ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        logs = result.stdout

        # Analyze logs for common issues
        report.append("[bold]Log Analysis:[/bold]")

        issues_found = []

        # Check for common error patterns
        error_patterns = [
            (
                r"permission denied",
                "Permission issue detected",
                "Try: Check file permissions and user/group settings in the unit file",
            ),
            (
                r"address already in use",
                "Port conflict detected",
                "Try: Check what's using the port with 'ss -tlnp | grep <port>'",
            ),
            (
                r"no such file or directory",
                "Missing file or directory",
                "Try: Verify all paths in the unit file exist",
            ),
            (
                r"connection refused",
                "Network connection issue",
                "Try: Check if the target service is running and accessible",
            ),
            (
                r"out of memory|cannot allocate|oom",
                "Memory issue",
                "Try: Increase available memory or add memory limits to prevent OOM",
            ),
            (
                r"timeout|timed out",
                "Timeout occurred",
                "Try: Increase TimeoutStartSec/TimeoutStopSec in the unit file",
            ),
            (
                r"dependency|requires|wants",
                "Dependency issue",
                "Try: Check if required services are running with 'systemctl status <dep>'",
            ),
        ]

        for pattern, issue, advice in error_patterns:
            if re.search(pattern, logs, re.IGNORECASE):
                issues_found.append((issue, advice))

        if issues_found:
            for issue, advice in issues_found:
                report.append(f"  [red]! {issue}[/red]")
                report.append(f"    {advice}")
        else:
            report.append("  No common error patterns detected in logs.")
            report.append("  Review the full logs below for details.")

        report.append("")
        report.append("[bold]Recent Logs:[/bold]")
        # Show last 20 lines of logs
        log_lines = logs.strip().split("\n")[-20:]
        for line in log_lines:
            if "error" in line.lower() or "fail" in line.lower():
                report.append(f"  [red]{line}[/red]")
            elif "warn" in line.lower():
                report.append(f"  [yellow]{line}[/yellow]")
            else:
                report.append(f"  {line}")

        return "\n".join(report)

    def show_dependencies(self, service_name: str) -> Tree:
        """Show service dependencies as a visual tree.

        Args:
            service_name: Name of the service.

        Returns:
            Rich Tree object showing dependencies.
        """
        if not service_name.endswith(".service"):
            service_name = f"{service_name}.service"

        tree = Tree(f"[bold cyan]{service_name}[/bold cyan]")

        try:
            result = subprocess.run(
                ["systemctl", "list-dependencies", service_name, "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            tree.add("[yellow]Timed out fetching dependencies[/yellow]")
            return tree

        lines = result.stdout.strip().split("\n")[1:]  # Skip header

        # Parse the tree structure
        current_nodes = {0: tree}

        for line in lines:
            if not line.strip():
                continue

            # Count indentation (each level is 2 spaces or tree chars)
            indent = 0
            clean_line = line
            for char in line:
                if char in " │├└─":
                    indent += 1
                else:
                    break

            # Get the service name
            clean_line = re.sub(r"[│├└─\s]+", "", line).strip()
            if not clean_line:
                continue

            level = indent // 2

            # Color based on state
            if ".target" in clean_line:
                styled = f"[blue]{clean_line}[/blue]"
            elif ".socket" in clean_line:
                styled = f"[magenta]{clean_line}[/magenta]"
            elif ".service" in clean_line:
                styled = f"[green]{clean_line}[/green]"
            else:
                styled = clean_line

            # Add to tree
            parent_level = max(0, level - 1)
            if parent_level in current_nodes:
                new_node = current_nodes[parent_level].add(styled)
                current_nodes[level] = new_node

        return tree

    def generate_unit_file(
        self,
        description: str,
        exec_start: str,
        service_name: Optional[str] = None,
        user: Optional[str] = None,
        working_dir: Optional[str] = None,
        restart: bool = True,
        after: Optional[list[str]] = None,
        environment: Optional[dict[str, str]] = None,
    ) -> str:
        """Generate a systemd unit file from simple parameters.

        Args:
            description: Human-readable description of the service.
            exec_start: Command to run when starting the service.
            service_name: Name for the service (optional).
            user: User to run the service as (optional).
            working_dir: Working directory for the service (optional).
            restart: Whether to restart on failure (default True).
            after: List of units to start after (optional).
            environment: Environment variables to set (optional).

        Returns:
            Complete systemd unit file content as a string.
        """
        lines = []

        # [Unit] section
        lines.append("[Unit]")
        lines.append(f"Description={description}")

        if after:
            lines.append(f"After={' '.join(after)}")
        else:
            lines.append("After=network.target")

        lines.append("")

        # [Service] section
        lines.append("[Service]")
        lines.append("Type=simple")
        lines.append(f"ExecStart={exec_start}")

        if user:
            lines.append(f"User={user}")

        if working_dir:
            lines.append(f"WorkingDirectory={working_dir}")

        if environment:
            for key, value in environment.items():
                # Quote values that contain spaces or special characters
                if " " in value or '"' in value or "'" in value or "\\" in value:
                    # Escape existing double quotes and backslashes
                    escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
                    lines.append(f'Environment={key}="{escaped_value}"')
                else:
                    lines.append(f"Environment={key}={value}")

        if restart:
            lines.append("Restart=on-failure")
            lines.append("RestartSec=5")

        lines.append("")

        # [Install] section
        lines.append("[Install]")
        lines.append("WantedBy=multi-user.target")
        lines.append("")

        return "\n".join(lines)

    def interactive_unit_generator(self) -> str:
        """Interactive CLI wizard for generating a unit file.

        Asks the user simple questions and generates a complete
        systemd unit file based on their answers.

        Returns:
            Generated unit file content as a string.
        """
        console.print("\n[bold cyan]Systemd Unit File Generator[/bold cyan]")
        console.print("Answer a few questions to create your service file.\n")

        # Service name
        service_name = Prompt.ask("[cyan]Service name[/cyan]", default="my-service")

        # Description
        description = Prompt.ask(
            "[cyan]What does this service do?[/cyan]", default="My custom service"
        )

        # Command
        exec_start = Prompt.ask("[cyan]Command to run[/cyan]", default="/usr/local/bin/my-app")

        # User
        run_as_root = Confirm.ask("[cyan]Run as root?[/cyan]", default=False)
        user = None
        if not run_as_root:
            user = Prompt.ask("[cyan]Run as which user?[/cyan]", default="nobody")

        # Working directory
        has_workdir = Confirm.ask("[cyan]Set a working directory?[/cyan]", default=False)
        working_dir = None
        if has_workdir:
            working_dir = Prompt.ask(
                "[cyan]Working directory path[/cyan]", default="/var/lib/my-service"
            )

        # Restart on failure
        restart = Confirm.ask("[cyan]Restart automatically on failure?[/cyan]", default=True)

        # Start on boot
        start_on_boot = Confirm.ask("[cyan]Start automatically on boot?[/cyan]", default=True)

        # Generate the unit file
        unit_content = self.generate_unit_file(
            description=description,
            exec_start=exec_start,
            service_name=service_name,
            user=user,
            working_dir=working_dir,
            restart=restart,
        )

        console.print("\n[bold green]Generated Unit File:[/bold green]\n")
        console.print(Panel(unit_content, title=f"{service_name}.service", border_style="green"))

        # Installation instructions
        console.print("\n[bold]Installation Instructions:[/bold]")
        console.print(f"1. Save to: /etc/systemd/system/{service_name}.service")
        console.print("2. Reload systemd: sudo systemctl daemon-reload")
        if start_on_boot:
            console.print(f"3. Enable service: sudo systemctl enable {service_name}")
        console.print(f"4. Start service: sudo systemctl start {service_name}")
        console.print(f"5. Check status: sudo systemctl status {service_name}")

        return unit_content


def run_status_command(service_name: str) -> None:
    """Run the status explanation command.

    Args:
        service_name: Name of the service to check.
    """
    helper = SystemdHelper()
    explanation = helper.explain_status(service_name)
    console.print(Panel(explanation, title="Service Status", border_style="cyan"))


def run_diagnose_command(service_name: str, lines: int = 50) -> None:
    """Run the diagnostic command for a failed service.

    Args:
        service_name: Name of the service to diagnose.
        lines: Number of log lines to analyze.
    """
    helper = SystemdHelper()
    report = helper.diagnose_failure(service_name, lines=lines)
    console.print(report)


def run_deps_command(service_name: str) -> None:
    """Show dependencies for a service.

    Args:
        service_name: Name of the service.
    """
    helper = SystemdHelper()
    tree = helper.show_dependencies(service_name)
    console.print("\n[bold]Service Dependencies:[/bold]")
    console.print(tree)


def run_generate_command() -> None:
    """Run the interactive unit file generator."""
    helper = SystemdHelper()
    helper.interactive_unit_generator()
