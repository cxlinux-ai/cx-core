"""Data models and enums for the Do Runner module."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rich.console import Console

console = Console()


class CommandStatus(str, Enum):
    """Status of a command execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_REPAIR = "needs_repair"
    INTERRUPTED = "interrupted"  # Command stopped by Ctrl+Z/Ctrl+C


class RunMode(str, Enum):
    """Mode of execution for a do run."""

    CORTEX_EXEC = "cortex_exec"
    USER_MANUAL = "user_manual"


class TaskType(str, Enum):
    """Type of task in the task tree."""

    COMMAND = "command"
    DIAGNOSTIC = "diagnostic"
    REPAIR = "repair"
    VERIFY = "verify"
    ALTERNATIVE = "alternative"


@dataclass
class TaskNode:
    """A node in the task tree representing a command or action."""

    id: str
    task_type: TaskType
    command: str
    purpose: str
    status: CommandStatus = CommandStatus.PENDING

    # Execution results
    output: str = ""
    error: str = ""
    duration_seconds: float = 0.0

    # Tree structure
    parent_id: str | None = None
    children: list["TaskNode"] = field(default_factory=list)

    # Repair context
    failure_reason: str = ""
    repair_attempts: int = 0
    max_repair_attempts: int = 3

    # Reasoning
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_type": self.task_type.value,
            "command": self.command,
            "purpose": self.purpose,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "parent_id": self.parent_id,
            "children": [c.to_dict() for c in self.children],
            "failure_reason": self.failure_reason,
            "repair_attempts": self.repair_attempts,
            "reasoning": self.reasoning,
        }

    def add_child(self, child: "TaskNode"):
        """Add a child task."""
        child.parent_id = self.id
        self.children.append(child)

    def get_depth(self) -> int:
        """Get the depth of this node in the tree."""
        depth = 0
        node = self
        while node.parent_id:
            depth += 1
            node = node
        return depth


class TaskTree:
    """A tree structure for managing commands with auto-repair capabilities."""

    def __init__(self):
        self.root_tasks: list[TaskNode] = []
        self._task_counter = 0
        self._all_tasks: dict[str, TaskNode] = {}

    def _generate_task_id(self, prefix: str = "task") -> str:
        """Generate a unique task ID."""
        self._task_counter += 1
        return f"{prefix}_{self._task_counter}"

    def add_root_task(
        self,
        command: str,
        purpose: str,
        task_type: TaskType = TaskType.COMMAND,
    ) -> TaskNode:
        """Add a root-level task."""
        task = TaskNode(
            id=self._generate_task_id(task_type.value),
            task_type=task_type,
            command=command,
            purpose=purpose,
        )
        self.root_tasks.append(task)
        self._all_tasks[task.id] = task
        return task

    def add_repair_task(
        self,
        parent: TaskNode,
        command: str,
        purpose: str,
        reasoning: str = "",
    ) -> TaskNode:
        """Add a repair sub-task to a failed task."""
        task = TaskNode(
            id=self._generate_task_id("repair"),
            task_type=TaskType.REPAIR,
            command=command,
            purpose=purpose,
            reasoning=reasoning,
        )
        parent.add_child(task)
        self._all_tasks[task.id] = task
        return task

    def add_diagnostic_task(
        self,
        parent: TaskNode,
        command: str,
        purpose: str,
    ) -> TaskNode:
        """Add a diagnostic sub-task to investigate a failure."""
        task = TaskNode(
            id=self._generate_task_id("diag"),
            task_type=TaskType.DIAGNOSTIC,
            command=command,
            purpose=purpose,
        )
        parent.add_child(task)
        self._all_tasks[task.id] = task
        return task

    def add_verify_task(
        self,
        parent: TaskNode,
        command: str,
        purpose: str,
    ) -> TaskNode:
        """Add a verification task after a repair."""
        task = TaskNode(
            id=self._generate_task_id("verify"),
            task_type=TaskType.VERIFY,
            command=command,
            purpose=purpose,
        )
        parent.add_child(task)
        self._all_tasks[task.id] = task
        return task

    def add_alternative_task(
        self,
        parent: TaskNode,
        command: str,
        purpose: str,
        reasoning: str = "",
    ) -> TaskNode:
        """Add an alternative approach when the original fails."""
        task = TaskNode(
            id=self._generate_task_id("alt"),
            task_type=TaskType.ALTERNATIVE,
            command=command,
            purpose=purpose,
            reasoning=reasoning,
        )
        parent.add_child(task)
        self._all_tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> TaskNode | None:
        """Get a task by ID."""
        return self._all_tasks.get(task_id)

    def get_pending_tasks(self) -> list[TaskNode]:
        """Get all pending tasks in order."""
        pending = []
        for root in self.root_tasks:
            self._collect_pending(root, pending)
        return pending

    def _collect_pending(self, node: TaskNode, pending: list[TaskNode]):
        """Recursively collect pending tasks."""
        if node.status == CommandStatus.PENDING:
            pending.append(node)
        for child in node.children:
            self._collect_pending(child, pending)

    def get_failed_tasks(self) -> list[TaskNode]:
        """Get all failed tasks."""
        return [t for t in self._all_tasks.values() if t.status == CommandStatus.FAILED]

    def get_summary(self) -> dict[str, int]:
        """Get a summary of task statuses."""
        summary = {status.value: 0 for status in CommandStatus}
        for task in self._all_tasks.values():
            summary[task.status.value] += 1
        return summary

    def to_dict(self) -> dict[str, Any]:
        """Convert tree to dictionary."""
        return {
            "root_tasks": [t.to_dict() for t in self.root_tasks],
            "summary": self.get_summary(),
        }

    def print_tree(self, indent: str = ""):
        """Print the task tree structure."""
        for i, root in enumerate(self.root_tasks):
            is_last = i == len(self.root_tasks) - 1
            self._print_node(root, indent, is_last)

    def _print_node(self, node: TaskNode, indent: str, is_last: bool):
        """Print a single node with its children."""
        status_icons = {
            CommandStatus.PENDING: "[dim]○[/dim]",
            CommandStatus.RUNNING: "[cyan]◐[/cyan]",
            CommandStatus.SUCCESS: "[green]✓[/green]",
            CommandStatus.FAILED: "[red]✗[/red]",
            CommandStatus.SKIPPED: "[yellow]○[/yellow]",
            CommandStatus.NEEDS_REPAIR: "[yellow]⚡[/yellow]",
        }

        type_colors = {
            TaskType.COMMAND: "white",
            TaskType.DIAGNOSTIC: "cyan",
            TaskType.REPAIR: "yellow",
            TaskType.VERIFY: "blue",
            TaskType.ALTERNATIVE: "magenta",
        }

        icon = status_icons.get(node.status, "?")
        color = type_colors.get(node.task_type, "white")
        prefix = "└── " if is_last else "├── "

        console.print(
            f"{indent}{prefix}{icon} [{color}][{node.task_type.value}][/{color}] {node.command[:50]}..."
        )

        if node.reasoning:
            console.print(
                f"{indent}{'    ' if is_last else '│   '}[dim]Reason: {node.reasoning}[/dim]"
            )

        child_indent = indent + ("    " if is_last else "│   ")
        for j, child in enumerate(node.children):
            self._print_node(child, child_indent, j == len(node.children) - 1)


@dataclass
class CommandLog:
    """Log entry for a single command execution."""

    command: str
    purpose: str
    timestamp: str
    status: CommandStatus
    output: str = ""
    error: str = ""
    duration_seconds: float = 0.0
    useful: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "purpose": self.purpose,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "useful": self.useful,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommandLog":
        return cls(
            command=data["command"],
            purpose=data["purpose"],
            timestamp=data["timestamp"],
            status=CommandStatus(data["status"]),
            output=data.get("output", ""),
            error=data.get("error", ""),
            duration_seconds=data.get("duration_seconds", 0.0),
            useful=data.get("useful", True),
        )


@dataclass
class DoRun:
    """Represents a complete do run session."""

    run_id: str
    summary: str
    mode: RunMode
    commands: list[CommandLog] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    user_query: str = ""
    files_accessed: list[str] = field(default_factory=list)
    privileges_granted: list[str] = field(default_factory=list)
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "summary": self.summary,
            "mode": self.mode.value,
            "commands": [cmd.to_dict() for cmd in self.commands],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "user_query": self.user_query,
            "files_accessed": self.files_accessed,
            "privileges_granted": self.privileges_granted,
            "session_id": self.session_id,
        }

    def get_commands_log_string(self) -> str:
        """Get all commands as a formatted string for storage."""
        lines = []
        for cmd in self.commands:
            lines.append(f"[{cmd.timestamp}] [{cmd.status.value.upper()}] {cmd.command}")
            lines.append(f"  Purpose: {cmd.purpose}")
            if cmd.output:
                lines.append(f"  Output: {cmd.output[:500]}...")
            if cmd.error:
                lines.append(f"  Error: {cmd.error}")
            lines.append(f"  Duration: {cmd.duration_seconds:.2f}s | Useful: {cmd.useful}")
            lines.append("")
        return "\n".join(lines)
