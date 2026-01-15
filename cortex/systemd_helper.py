"""
Cortex Systemd Helper Module

Plain English systemd service management with explanations,
unit file creation, failure diagnosis, and dependency visualization.

Issue: #448
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from cortex.branding import CORTEX_CYAN, console, cx_header, cx_print

# Service state explanations in plain English
SERVICE_STATE_EXPLANATIONS = {
    "active": "The service is running normally.",
    "inactive": "The service is stopped and not running.",
    "failed": "The service tried to start but crashed or exited with an error.",
    "activating": "The service is in the process of starting up.",
    "deactivating": "The service is in the process of shutting down.",
    "reloading": "The service is reloading its configuration.",
    "maintenance": "The service is in a maintenance state.",
}

SUB_STATE_EXPLANATIONS = {
    "running": "actively executing",
    "dead": "not running",
    "exited": "started and then finished (one-time task)",
    "waiting": "waiting for something",
    "listening": "waiting for incoming connections",
    "start-pre": "running pre-start commands",
    "start": "in the process of starting",
    "start-post": "running post-start commands",
    "stop-pre": "running pre-stop commands",
    "stop": "in the process of stopping",
    "stop-post": "running post-stop commands",
    "final-sigterm": "sending termination signal",
    "final-sigkill": "force killing the process",
    "auto-restart": "about to restart automatically",
    "failed": "crashed or failed to start",
    "mounted": "filesystem is mounted",
    "mounting": "filesystem is being mounted",
    "unmounting": "filesystem is being unmounted",
}

# Common failure reasons and solutions
FAILURE_SOLUTIONS = {
    "exit-code": [
        ("Check the service logs", "journalctl -u {service} -n 50"),
        ("Check configuration files", "The service may have invalid configuration."),
        ("Verify dependencies are running", "systemctl list-dependencies {service}"),
    ],
    "signal": [
        ("Service was killed by a signal", "Check if OOM killer terminated it: dmesg | grep -i oom"),
        ("Check resource limits", "systemctl show {service} | grep -i limit"),
    ],
    "timeout": [
        ("Service took too long to start", "Increase TimeoutStartSec in the unit file."),
        ("Check if service is blocked", "It may be waiting for a network or dependency."),
    ],
    "core-dump": [
        ("Service crashed", "Check for core dumps in /var/lib/systemd/coredump/"),
        ("Review application logs", "The application has a bug or invalid input."),
    ],
    "start-limit-hit": [
        ("Service crashed too many times", "Reset the failure count: systemctl reset-failed {service}"),
        ("Fix the underlying issue", "Check logs before restarting: journalctl -u {service} -n 100"),
    ],
}


class ServiceType(Enum):
    """Common service types for unit file generation."""

    SIMPLE = "simple"  # Default, main process is the service
    FORKING = "forking"  # Daemon that forks
    ONESHOT = "oneshot"  # Run once and exit
    NOTIFY = "notify"  # Uses sd_notify() to signal readiness
    IDLE = "idle"  # Like simple, but waits for other jobs


@dataclass
class ServiceConfig:
    """Configuration for generating a systemd unit file."""

    name: str
    description: str
    exec_start: str
    service_type: ServiceType = ServiceType.SIMPLE
    user: str | None = None
    group: str | None = None
    working_directory: str | None = None
    environment: dict[str, str] = field(default_factory=dict)
    restart: str = "on-failure"
    restart_sec: int = 5
    wants: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=lambda: ["network.target"])
    wanted_by: list[str] = field(default_factory=lambda: ["multi-user.target"])
    exec_stop: str | None = None
    exec_reload: str | None = None
    timeout_start_sec: int = 90
    timeout_stop_sec: int = 90


@dataclass
class ServiceStatus:
    """Parsed systemd service status."""

    name: str
    load_state: str = ""
    active_state: str = ""
    sub_state: str = ""
    description: str = ""
    main_pid: int = 0
    memory: str = ""
    cpu: str = ""
    tasks: int = 0
    since: str = ""
    result: str = ""
    fragment_path: str = ""
    docs: list[str] = field(default_factory=list)


class SystemdHelper:
    """
    Plain English systemd service helper.

    Features:
    - Explain service status in plain English
    - Create unit files from simple descriptions
    - Diagnose failures with actionable advice
    - Show dependencies visually
    """

    UNIT_DIR = Path("/etc/systemd/system")
    USER_UNIT_DIR = Path.home() / ".config/systemd/user"

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def _run_systemctl(self, *args, capture: bool = True) -> tuple[int, str, str]:
        """Run a systemctl command and return (returncode, stdout, stderr)."""
        cmd = ["systemctl"] + list(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture,
                text=True,
                timeout=30
            )
            return result.returncode, result.stdout, result.stderr
        except FileNotFoundError:
            return 1, "", "systemctl not found. Is systemd installed?"
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"

    def _run_journalctl(self, service: str, lines: int = 50) -> str:
        """Get recent logs for a service."""
        try:
            result = subprocess.run(
                ["journalctl", "-u", service, "-n", str(lines), "--no-pager"],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout
        except Exception:
            return ""

    def get_status(self, service: str) -> ServiceStatus | None:
        """
        Get the status of a systemd service.

        Args:
            service: Service name (with or without .service suffix)

        Returns:
            ServiceStatus object or None if service not found
        """
        if not service.endswith(".service"):
            service = f"{service}.service"

        returncode, stdout, stderr = self._run_systemctl("show", service, "--no-pager")
        if returncode != 0 or not stdout:
            return None

        status = ServiceStatus(name=service)

        # Parse the output
        for line in stdout.split("\n"):
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()

            if key == "LoadState":
                status.load_state = value
            elif key == "ActiveState":
                status.active_state = value
            elif key == "SubState":
                status.sub_state = value
            elif key == "Description":
                status.description = value
            elif key == "MainPID":
                status.main_pid = int(value) if value.isdigit() else 0
            elif key == "MemoryCurrent":
                if value.isdigit():
                    mb = int(value) / 1024 / 1024
                    status.memory = f"{mb:.1f} MB"
            elif key == "CPUUsageNSec":
                if value.isdigit():
                    sec = int(value) / 1_000_000_000
                    status.cpu = f"{sec:.2f}s"
            elif key == "TasksCurrent":
                status.tasks = int(value) if value.isdigit() else 0
            elif key == "ActiveEnterTimestamp":
                status.since = value
            elif key == "Result":
                status.result = value
            elif key == "FragmentPath":
                status.fragment_path = value
            elif key == "Documentation":
                if value:
                    status.docs = value.split()

        return status

    def explain_status(self, service: str) -> tuple[bool, str]:
        """
        Explain a service's status in plain English.

        Returns:
            Tuple of (success, explanation)
        """
        status = self.get_status(service)
        if not status:
            return False, f"Service '{service}' not found or systemd not available."

        if status.load_state == "not-found":
            return False, f"Service '{service}' is not installed on this system."

        if status.load_state == "masked":
            return True, f"Service '{service}' is MASKED (disabled by administrator and cannot be started)."

        # Build explanation
        parts = []

        # Main state
        state_explanation = SERVICE_STATE_EXPLANATIONS.get(
            status.active_state,
            f"in an unknown state ({status.active_state})"
        )
        parts.append(f"**{service}** is **{status.active_state}**: {state_explanation}")

        # Sub-state details
        if status.sub_state:
            sub_explanation = SUB_STATE_EXPLANATIONS.get(status.sub_state, status.sub_state)
            parts.append(f"Specifically, it is {sub_explanation}.")

        # Running info
        if status.active_state == "active" and status.main_pid > 0:
            parts.append(f"Main process ID: {status.main_pid}")
            if status.memory:
                parts.append(f"Memory usage: {status.memory}")
            if status.tasks:
                parts.append(f"Running threads: {status.tasks}")

        # Failure info
        if status.active_state == "failed" or status.result not in ["success", ""]:
            parts.append(f"\n**Failure reason:** {status.result}")
            if status.result in FAILURE_SOLUTIONS:
                parts.append("**Suggested fixes:**")
                for desc, cmd in FAILURE_SOLUTIONS[status.result]:
                    cmd_formatted = cmd.format(service=service)
                    parts.append(f"  - {desc}")
                    if "{service}" in cmd:
                        parts.append(f"    Run: `{cmd_formatted}`")

        # Since timestamp
        if status.since:
            parts.append(f"\nLast state change: {status.since}")

        return True, "\n".join(parts)

    def diagnose_failure(self, service: str) -> tuple[bool, str, list[str]]:
        """
        Diagnose why a service failed.

        Returns:
            Tuple of (found_issues, explanation, log_lines)
        """
        status = self.get_status(service)
        if not status:
            return False, f"Service '{service}' not found.", []

        if status.active_state not in ["failed", "inactive"] and status.result == "success":
            return True, f"Service '{service}' is running normally.", []

        explanation_parts = []
        recommendations = []

        # Get failure result
        if status.result and status.result != "success":
            explanation_parts.append(f"**Exit reason:** {status.result}")

            if status.result in FAILURE_SOLUTIONS:
                for desc, cmd in FAILURE_SOLUTIONS[status.result]:
                    recommendations.append(f"- {desc}")
                    if "{service}" in cmd:
                        recommendations.append(f"  `{cmd.format(service=service)}`")

        # Get recent logs
        logs = self._run_journalctl(service, lines=30)
        log_lines = logs.strip().split("\n") if logs else []

        # Analyze logs for common issues
        log_text = logs.lower()
        if "permission denied" in log_text:
            recommendations.append("- **Permission issue detected**: Check file permissions and service user")
        if "address already in use" in log_text:
            recommendations.append("- **Port conflict**: Another process is using the same port")
            recommendations.append("  Run: `ss -tlnp | grep <port>` to find conflicting process")
        if "no such file" in log_text or "not found" in log_text:
            recommendations.append("- **Missing file/directory**: Check paths in ExecStart")
        if "connection refused" in log_text:
            recommendations.append("- **Connection issue**: Required service/database not running")
        if "out of memory" in log_text or "cannot allocate" in log_text:
            recommendations.append("- **Memory issue**: System may be low on RAM")

        if recommendations:
            explanation_parts.append("\n**Recommendations:**")
            explanation_parts.extend(recommendations)

        return len(recommendations) > 0, "\n".join(explanation_parts), log_lines

    def get_dependencies(self, service: str) -> dict[str, list[str]]:
        """
        Get service dependencies.

        Returns:
            Dict with 'wants', 'requires', 'after', 'before' lists
        """
        deps: dict[str, list[str]] = {
            "wants": [],
            "requires": [],
            "after": [],
            "before": [],
            "wanted_by": [],
            "required_by": [],
        }

        if not service.endswith(".service"):
            service = f"{service}.service"

        # Get dependency info
        returncode, stdout, _ = self._run_systemctl("show", service,
            "-p", "Wants,Requires,After,Before,WantedBy,RequiredBy",
            "--no-pager")

        if returncode == 0:
            for line in stdout.split("\n"):
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key_lower = key.lower().replace("by", "_by")
                if key_lower in deps and value:
                    deps[key_lower] = [v.strip() for v in value.split() if v.strip()]

        return deps

    def show_dependencies_tree(self, service: str) -> Tree:
        """
        Create a visual dependency tree.

        Returns:
            Rich Tree object
        """
        if not service.endswith(".service"):
            service = f"{service}.service"

        tree = Tree(f"[bold cyan]{service}[/bold cyan]")

        deps = self.get_dependencies(service)

        if deps["requires"]:
            req_branch = tree.add("[bold red]Requires[/bold red] (hard dependencies)")
            for dep in deps["requires"][:10]:  # Limit to prevent huge trees
                req_branch.add(f"[cyan]{dep}[/cyan]")

        if deps["wants"]:
            wants_branch = tree.add("[bold yellow]Wants[/bold yellow] (soft dependencies)")
            for dep in deps["wants"][:10]:
                wants_branch.add(f"[cyan]{dep}[/cyan]")

        if deps["after"]:
            after_branch = tree.add("[bold green]After[/bold green] (starts after these)")
            for dep in deps["after"][:10]:
                after_branch.add(f"[cyan]{dep}[/cyan]")

        if deps["wanted_by"]:
            by_branch = tree.add("[bold blue]Wanted By[/bold blue] (enabled in these targets)")
            for dep in deps["wanted_by"][:10]:
                by_branch.add(f"[cyan]{dep}[/cyan]")

        return tree

    def generate_unit_file(self, config: ServiceConfig) -> str:
        """
        Generate a systemd unit file from configuration.

        Args:
            config: ServiceConfig with service settings

        Returns:
            Unit file content as string
        """
        lines = ["[Unit]"]
        lines.append(f"Description={config.description}")

        if config.wants:
            lines.append(f"Wants={' '.join(config.wants)}")
        if config.after:
            lines.append(f"After={' '.join(config.after)}")

        lines.append("")
        lines.append("[Service]")
        lines.append(f"Type={config.service_type.value}")
        lines.append(f"ExecStart={config.exec_start}")

        if config.exec_stop:
            lines.append(f"ExecStop={config.exec_stop}")
        if config.exec_reload:
            lines.append(f"ExecReload={config.exec_reload}")

        if config.user:
            lines.append(f"User={config.user}")
        if config.group:
            lines.append(f"Group={config.group}")
        if config.working_directory:
            lines.append(f"WorkingDirectory={config.working_directory}")

        for key, value in config.environment.items():
            lines.append(f"Environment={key}={value}")

        lines.append(f"Restart={config.restart}")
        lines.append(f"RestartSec={config.restart_sec}")
        lines.append(f"TimeoutStartSec={config.timeout_start_sec}")
        lines.append(f"TimeoutStopSec={config.timeout_stop_sec}")

        lines.append("")
        lines.append("[Install]")
        if config.wanted_by:
            lines.append(f"WantedBy={' '.join(config.wanted_by)}")

        return "\n".join(lines) + "\n"

    def create_unit_from_description(
        self,
        description: str,
        command: str,
        name: str | None = None,
        user: str | None = None,
        working_dir: str | None = None,
    ) -> tuple[str, str]:
        """
        Create a unit file from a simple description.

        Args:
            description: What the service does
            command: The command to run
            name: Service name (auto-generated if not provided)
            user: User to run as
            working_dir: Working directory

        Returns:
            Tuple of (service_name, unit_file_content)
        """
        # Auto-generate name from description if not provided
        if not name:
            name = re.sub(r'[^a-z0-9]+', '-', description.lower())[:40]
            name = name.strip('-')

        # Detect service type
        service_type = ServiceType.SIMPLE
        if command.endswith("&"):
            service_type = ServiceType.FORKING
            command = command.rstrip("& ")

        config = ServiceConfig(
            name=name,
            description=description,
            exec_start=command,
            service_type=service_type,
            user=user,
            working_directory=working_dir,
        )

        return f"{name}.service", self.generate_unit_file(config)

    def display_status(self, service: str):
        """Display formatted service status."""
        status = self.get_status(service)

        if not status:
            cx_print(f"Service '{service}' not found.", "error")
            return

        # Status color
        if status.active_state == "active":
            state_color = "green"
            state_icon = "✓"
        elif status.active_state == "failed":
            state_color = "red"
            state_icon = "✗"
        elif status.active_state == "inactive":
            state_color = "yellow"
            state_icon = "○"
        else:
            state_color = "cyan"
            state_icon = "●"

        cx_header(f"Service: {service}")

        # Status box
        items = [
            ("State", f"[{state_color}]{state_icon} {status.active_state}[/{state_color}]"),
            ("Sub-state", status.sub_state),
            ("Description", status.description or "N/A"),
        ]

        if status.main_pid:
            items.append(("PID", str(status.main_pid)))
        if status.memory:
            items.append(("Memory", status.memory))
        if status.tasks:
            items.append(("Tasks", str(status.tasks)))
        if status.since:
            items.append(("Since", status.since))

        table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        table.add_column("Key", style="dim")
        table.add_column("Value")

        for key, value in items:
            table.add_row(key + ":", value)

        console.print(table)

        # Plain English explanation
        console.print()
        success, explanation = self.explain_status(service)
        if success:
            console.print(Panel(
                explanation,
                title="[bold cyan]Plain English Explanation[/bold cyan]",
                border_style=CORTEX_CYAN,
                padding=(1, 2),
            ))

    def display_diagnosis(self, service: str):
        """Display failure diagnosis for a service."""
        cx_header(f"Diagnosing: {service}")

        found_issues, explanation, logs = self.diagnose_failure(service)

        if explanation:
            console.print(Panel(
                explanation,
                title="[bold yellow]Diagnosis[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            ))

        if logs:
            console.print()
            console.print("[bold]Recent Logs:[/bold]")
            for line in logs[-20:]:  # Last 20 lines
                if "error" in line.lower() or "fail" in line.lower():
                    console.print(f"[red]{line}[/red]")
                elif "warn" in line.lower():
                    console.print(f"[yellow]{line}[/yellow]")
                else:
                    console.print(f"[dim]{line}[/dim]")


def run_systemd_helper(
    service: str,
    action: str = "status",
    verbose: bool = False
) -> int:
    """
    Main entry point for cortex systemd command.

    Args:
        service: Service name
        action: One of "status", "diagnose", "deps"
        verbose: Verbose output

    Returns:
        Exit code
    """
    helper = SystemdHelper(verbose=verbose)

    if action == "status":
        helper.display_status(service)
    elif action == "diagnose":
        helper.display_diagnosis(service)
    elif action == "deps":
        tree = helper.show_dependencies_tree(service)
        console.print(tree)
    else:
        cx_print(f"Unknown action: {action}", "error")
        return 1

    return 0
