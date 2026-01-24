"""Task Tree Executor for advanced command execution with auto-repair."""

import os
import subprocess
import time
from collections.abc import Callable
from typing import Any

from rich.console import Console
from rich.prompt import Confirm

from .models import (
    CommandLog,
    CommandStatus,
    DoRun,
    TaskNode,
    TaskTree,
    TaskType,
)
from .terminal import TerminalMonitor

console = Console()


class TaskTreeExecutor:
    """
    Executes a task tree with auto-repair capabilities.

    This handles:
    - Executing commands in order
    - Spawning repair sub-tasks when commands fail
    - Asking for additional permissions when needed
    - Monitoring terminals during manual intervention
    - Providing detailed reasoning for failures
    """

    def __init__(
        self,
        user_manager: type,
        paths_manager: Any,
        llm_callback: Callable[[str], dict] | None = None,
    ):
        self.user_manager = user_manager
        self.paths_manager = paths_manager
        self.llm_callback = llm_callback
        self.tree = TaskTree()
        self._granted_privileges: list[str] = []
        self._permission_sets_requested: int = 0
        self._terminal_monitor: TerminalMonitor | None = None

        self._in_manual_mode = False
        self._manual_commands_executed: list[dict] = []

    def build_tree_from_commands(
        self,
        commands: list[dict[str, str]],
    ) -> TaskTree:
        """Build a task tree from a list of commands."""
        for cmd in commands:
            self.tree.add_root_task(
                command=cmd.get("command", ""),
                purpose=cmd.get("purpose", ""),
            )
        return self.tree

    def execute_tree(
        self,
        confirm_callback: Callable[[list[TaskNode]], bool] | None = None,
        notify_callback: Callable[[str, str], None] | None = None,
    ) -> tuple[bool, str]:
        """
        Execute the task tree with auto-repair.

        Returns:
            Tuple of (success, summary)
        """
        total_success = 0
        total_failed = 0
        total_repaired = 0
        repair_details = []

        for root_task in self.tree.root_tasks:
            success, repaired = self._execute_task_with_repair(
                root_task,
                confirm_callback,
                notify_callback,
            )

            if success:
                total_success += 1
                if repaired:
                    total_repaired += 1
            else:
                total_failed += 1
                if root_task.failure_reason:
                    repair_details.append(
                        f"- {root_task.command[:40]}...: {root_task.failure_reason}"
                    )

        summary_parts = [
            f"Completed: {total_success}",
            f"Failed: {total_failed}",
        ]
        if total_repaired > 0:
            summary_parts.append(f"Auto-repaired: {total_repaired}")

        summary = f"Tasks: {' | '.join(summary_parts)}"

        if repair_details:
            summary += "\n\nFailure reasons:\n" + "\n".join(repair_details)

        return total_failed == 0, summary

    def _execute_task_with_repair(
        self,
        task: TaskNode,
        confirm_callback: Callable[[list[TaskNode]], bool] | None = None,
        notify_callback: Callable[[str, str], None] | None = None,
    ) -> tuple[bool, bool]:
        """Execute a task and attempt repair if it fails."""
        was_repaired = False

        task.status = CommandStatus.RUNNING
        success, output, error, duration = self._execute_command(task.command)

        task.output = output
        task.error = error
        task.duration_seconds = duration

        if success:
            task.status = CommandStatus.SUCCESS
            console.print(f"[green]✓[/green] {task.purpose}")
            return True, False

        task.status = CommandStatus.NEEDS_REPAIR
        diagnosis = self._diagnose_error(task.command, error, output)
        task.failure_reason = diagnosis.get("description", "Unknown error")

        console.print(f"[yellow]⚠[/yellow] {task.purpose} - {diagnosis['error_type']}")
        console.print(f"[dim]  └─ {diagnosis['description']}[/dim]")

        if diagnosis.get("can_auto_fix") and task.repair_attempts < task.max_repair_attempts:
            task.repair_attempts += 1
            fix_commands = diagnosis.get("fix_commands", [])

            if fix_commands:
                console.print(
                    f"[cyan]🔧 Attempting auto-repair ({task.repair_attempts}/{task.max_repair_attempts})...[/cyan]"
                )

                new_paths = self._identify_paths_needing_privileges(fix_commands)
                if new_paths and confirm_callback:
                    repair_tasks = []
                    for cmd in fix_commands:
                        repair_task = self.tree.add_repair_task(
                            parent=task,
                            command=cmd,
                            purpose=f"Repair: {diagnosis['description'][:50]}",
                            reasoning=diagnosis.get("reasoning", ""),
                        )
                        repair_tasks.append(repair_task)

                    self._permission_sets_requested += 1
                    console.print(
                        f"\n[yellow]🔐 Permission request #{self._permission_sets_requested} for repair commands:[/yellow]"
                    )

                    if confirm_callback(repair_tasks):
                        all_repairs_success = True
                        for repair_task in repair_tasks:
                            repair_success, _ = self._execute_task_with_repair(
                                repair_task, confirm_callback, notify_callback
                            )
                            if not repair_success:
                                all_repairs_success = False

                        if all_repairs_success:
                            console.print("[cyan]↻ Retrying original command...[/cyan]")
                            success, output, error, duration = self._execute_command(task.command)
                            task.output = output
                            task.error = error
                            task.duration_seconds += duration

                            if success:
                                task.status = CommandStatus.SUCCESS
                                task.reasoning = (
                                    f"Auto-repaired after {task.repair_attempts} attempt(s)"
                                )
                                console.print(
                                    f"[green]✓[/green] {task.purpose} [dim](repaired)[/dim]"
                                )
                                return True, True
                else:
                    all_repairs_success = True
                    for cmd in fix_commands:
                        repair_task = self.tree.add_repair_task(
                            parent=task,
                            command=cmd,
                            purpose=f"Repair: {diagnosis['description'][:50]}",
                            reasoning=diagnosis.get("reasoning", ""),
                        )
                        repair_success, _ = self._execute_task_with_repair(
                            repair_task, confirm_callback, notify_callback
                        )
                        if not repair_success:
                            all_repairs_success = False

                    if all_repairs_success:
                        console.print("[cyan]↻ Retrying original command...[/cyan]")
                        success, output, error, duration = self._execute_command(task.command)
                        task.output = output
                        task.error = error
                        task.duration_seconds += duration

                        if success:
                            task.status = CommandStatus.SUCCESS
                            task.reasoning = (
                                f"Auto-repaired after {task.repair_attempts} attempt(s)"
                            )
                            console.print(f"[green]✓[/green] {task.purpose} [dim](repaired)[/dim]")
                            return True, True

        task.status = CommandStatus.FAILED
        task.reasoning = self._generate_failure_reasoning(task, diagnosis)

        if diagnosis.get("manual_suggestion") and notify_callback:
            console.print("\n[yellow]📋 Manual intervention suggested:[/yellow]")
            console.print(f"[dim]{diagnosis['manual_suggestion']}[/dim]")

            if Confirm.ask(
                "Would you like to run this manually while Cortex monitors?", default=False
            ):
                success = self._supervise_manual_intervention(
                    task,
                    diagnosis.get("manual_suggestion", ""),
                    notify_callback,
                )
                if success:
                    task.status = CommandStatus.SUCCESS
                    task.reasoning = "Completed via manual intervention with Cortex monitoring"
                    return True, True

        console.print(f"\n[red]✗ Failed:[/red] {task.purpose}")
        console.print(f"[dim]  Reason: {task.reasoning}[/dim]")

        return False, was_repaired

    def _execute_command(self, command: str) -> tuple[bool, str, str, float]:
        """Execute a command."""
        start_time = time.time()

        try:
            needs_sudo = self._needs_sudo(command)

            if needs_sudo and not command.strip().startswith("sudo"):
                command = f"sudo {command}"

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )

            duration = time.time() - start_time
            success = result.returncode == 0

            return success, result.stdout, result.stderr, duration

        except subprocess.TimeoutExpired:
            return False, "", "Command timed out after 300 seconds", time.time() - start_time
        except Exception as e:
            return False, "", str(e), time.time() - start_time

    def _needs_sudo(self, command: str) -> bool:
        """Determine if a command needs sudo."""
        sudo_keywords = [
            "systemctl",
            "service",
            "apt",
            "apt-get",
            "dpkg",
            "useradd",
            "usermod",
            "userdel",
            "groupadd",
            "chmod",
            "chown",
            "mount",
            "umount",
            "fdisk",
            "iptables",
            "ufw",
            "firewall-cmd",
        ]

        system_paths = ["/etc/", "/var/", "/usr/", "/opt/", "/sys/", "/proc/"]

        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False

        base_cmd = cmd_parts[0]

        if base_cmd in sudo_keywords:
            return True

        for part in cmd_parts:
            for path in system_paths:
                if path in part:
                    if any(
                        op in command
                        for op in [
                            ">",
                            ">>",
                            "cp ",
                            "mv ",
                            "rm ",
                            "mkdir ",
                            "touch ",
                            "sed ",
                            "tee ",
                        ]
                    ):
                        return True

        return False

    def _diagnose_error(
        self,
        command: str,
        stderr: str,
        stdout: str,
    ) -> dict[str, Any]:
        """Diagnose why a command failed and suggest repairs."""
        error_lower = stderr.lower()
        combined = (stderr + stdout).lower()

        if "permission denied" in error_lower:
            import re

            path_match = None
            path_patterns = [
                r"cannot (?:create|open|access|stat|remove|modify) (?:regular file |directory )?['\"]?([^'\":\n]+)['\"]?",
                r"open\(\) ['\"]?([^'\"]+)['\"]? failed",
                r"['\"]([^'\"]+)['\"]?: [Pp]ermission denied",
            ]
            for pattern in path_patterns:
                match = re.search(pattern, stderr)
                if match:
                    path_match = match.group(1).strip()
                    break

            return {
                "error_type": "Permission Denied",
                "description": f"Insufficient permissions to access: {path_match or 'unknown path'}",
                "can_auto_fix": True,
                "fix_commands": (
                    [f"sudo {command}"] if not command.strip().startswith("sudo") else []
                ),
                "manual_suggestion": f"Run with sudo: sudo {command}",
                "reasoning": f"The command tried to access '{path_match or 'a protected resource'}' without sufficient privileges.",
            }

        if "no such file or directory" in error_lower:
            import re

            path_match = re.search(r"['\"]?([^'\"\n]+)['\"]?: [Nn]o such file", stderr)
            missing_path = path_match.group(1) if path_match else None

            if missing_path:
                parent_dir = os.path.dirname(missing_path)
                if parent_dir:
                    return {
                        "error_type": "File Not Found",
                        "description": f"Path does not exist: {missing_path}",
                        "can_auto_fix": True,
                        "fix_commands": [f"sudo mkdir -p {parent_dir}"],
                        "manual_suggestion": f"Create the directory: sudo mkdir -p {parent_dir}",
                        "reasoning": f"The target path '{missing_path}' doesn't exist.",
                    }

            return {
                "error_type": "File Not Found",
                "description": "A required file or directory does not exist",
                "can_auto_fix": False,
                "fix_commands": [],
                "manual_suggestion": "Check the file path and ensure it exists",
                "reasoning": "The command references a non-existent path.",
            }

        if "command not found" in error_lower or "not found" in error_lower:
            import re

            cmd_match = re.search(r"(\w+): (?:command )?not found", stderr)
            missing_cmd = cmd_match.group(1) if cmd_match else None

            return {
                "error_type": "Command Not Found",
                "description": f"Command not installed: {missing_cmd or 'unknown'}",
                "can_auto_fix": bool(missing_cmd),
                "fix_commands": [f"sudo apt install -y {missing_cmd}"] if missing_cmd else [],
                "manual_suggestion": (
                    f"Install: sudo apt install {missing_cmd}"
                    if missing_cmd
                    else "Install the required command"
                ),
                "reasoning": f"The command '{missing_cmd or 'required'}' is not installed.",
            }

        return {
            "error_type": "Unknown Error",
            "description": stderr[:200] if stderr else "Command failed with no error output",
            "can_auto_fix": False,
            "fix_commands": [],
            "manual_suggestion": f"Review the error and try: {command}",
            "reasoning": "The command failed with an unexpected error.",
        }

    def _generate_failure_reasoning(self, task: TaskNode, diagnosis: dict) -> str:
        """Generate detailed reasoning for why a task failed."""
        parts = [
            f"Error type: {diagnosis.get('error_type', 'Unknown')}",
            f"Description: {diagnosis.get('description', 'No details available')}",
        ]

        if task.repair_attempts > 0:
            parts.append(f"Repair attempts: {task.repair_attempts} (all failed)")

        if diagnosis.get("reasoning"):
            parts.append(f"Analysis: {diagnosis['reasoning']}")

        if diagnosis.get("manual_suggestion"):
            parts.append(f"Suggestion: {diagnosis['manual_suggestion']}")

        return " | ".join(parts)

    def _identify_paths_needing_privileges(self, commands: list[str]) -> list[str]:
        """Identify paths in commands that need privilege grants."""
        paths = []
        for cmd in commands:
            parts = cmd.split()
            for part in parts:
                if part.startswith("/") and self.paths_manager.is_protected(part):
                    paths.append(part)
        return paths

    def _supervise_manual_intervention(
        self,
        task: TaskNode,
        instruction: str,
        notify_callback: Callable[[str, str], None],
    ) -> bool:
        """Supervise manual command execution with terminal monitoring."""
        self._in_manual_mode = True

        console.print("\n[bold cyan]═══ Manual Intervention Mode ═══[/bold cyan]")
        console.print("\n[yellow]Run this command in another terminal:[/yellow]")
        console.print(f"[bold]{instruction}[/bold]")

        self._terminal_monitor = TerminalMonitor(
            notification_callback=lambda title, msg: notify_callback(title, msg)
        )
        self._terminal_monitor.start()

        console.print("\n[dim]Cortex is now monitoring your terminal for issues...[/dim]")

        try:
            while True:
                choice = Confirm.ask(
                    "\nHave you completed the manual step?",
                    default=True,
                )

                if choice:
                    success = Confirm.ask("Was it successful?", default=True)

                    if success:
                        console.print("[green]✓ Manual step completed successfully[/green]")
                        return True
                    else:
                        console.print("\n[yellow]What went wrong?[/yellow]")
                        console.print("1. Permission denied")
                        console.print("2. File not found")
                        console.print("3. Other error")

                        try:
                            error_choice = int(input("Enter choice (1-3): "))
                        except ValueError:
                            error_choice = 3

                        if error_choice == 1:
                            console.print(f"[yellow]Try: sudo {instruction}[/yellow]")
                        elif error_choice == 2:
                            console.print("[yellow]Check the file path exists[/yellow]")
                        else:
                            console.print("[yellow]Describe the error and try again[/yellow]")

                        continue_trying = Confirm.ask("Continue trying?", default=True)
                        if not continue_trying:
                            return False
                else:
                    console.print("[dim]Take your time. Cortex is still monitoring...[/dim]")

        finally:
            self._in_manual_mode = False
            if self._terminal_monitor:
                self._terminal_monitor.stop()

    def get_tree_summary(self) -> dict:
        """Get a summary of the task tree execution."""
        return {
            "tree": self.tree.to_dict(),
            "permission_requests": self._permission_sets_requested,
            "manual_commands": self._manual_commands_executed,
        }
