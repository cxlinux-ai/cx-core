"""
Cortex Output Formatter Module

Rich terminal output formatting with colors, boxes, spinners, and progress bars.
Provides investor-ready polished display for all CLI output.

Issue: #242
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Tuple

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.spinner import Spinner
from rich.status import Status
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

console = Console()

# Color scheme matching Cortex branding
COLORS = {
    "primary": "cyan",
    "secondary": "dark_cyan",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "info": "blue",
    "muted": "dim",
    "highlight": "bold cyan",
}

# Status icons for consistent visual language
STATUS_ICONS = {
    "success": "✓",
    "error": "✗",
    "warning": "⚠",
    "info": "ℹ",
    "pending": "○",
    "running": "●",
    "skipped": "◌",
    "active": "▶",
    "installed": "📦",
    "removed": "🗑️",
    "updated": "🔄",
}


class OutputStyle(Enum):
    """Predefined output styles for consistent formatting."""

    DEFAULT = "default"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"
    MUTED = "muted"


@dataclass
class TableColumn:
    """Configuration for a table column."""

    header: str
    style: str = "cyan"
    justify: str = "left"
    width: int | None = None
    no_wrap: bool = False


@dataclass
class StatusInfo:
    """Information for status display."""

    label: str
    value: str
    style: OutputStyle = OutputStyle.DEFAULT


def format_box(
    content: str,
    title: str | None = None,
    subtitle: str | None = None,
    style: OutputStyle = OutputStyle.DEFAULT,
    border_style: str = "cyan",
    padding: tuple[int, int] = (1, 2),
    expand: bool = False,
) -> Panel:
    """
    Create a formatted box/panel around content.

    Args:
        content: The content to display inside the box
        title: Optional title for the box header
        subtitle: Optional subtitle for the box footer
        style: Output style affecting content color
        border_style: Color of the box border
        padding: Tuple of (vertical, horizontal) padding
        expand: Whether to expand to full terminal width

    Returns:
        Rich Panel object ready to print
    """
    style_colors = {
        OutputStyle.SUCCESS: "green",
        OutputStyle.WARNING: "yellow",
        OutputStyle.ERROR: "red",
        OutputStyle.INFO: "blue",
        OutputStyle.MUTED: "dim",
        OutputStyle.DEFAULT: "white",
    }

    content_style = style_colors.get(style, "white")
    styled_content = f"[{content_style}]{content}[/{content_style}]"

    return Panel(
        styled_content,
        title=f"[bold]{title}[/bold]" if title else None,
        subtitle=f"[dim]{subtitle}[/dim]" if subtitle else None,
        border_style=border_style,
        padding=padding,
        expand=expand,
        box=box.ROUNDED,
    )


def format_status_box(
    title: str,
    items: list[StatusInfo],
    border_style: str = "cyan",
) -> Panel:
    """
    Create a formatted status box with key-value pairs.

    Example output:
    ┌─────────────────────────────────────────┐
    │  CORTEX ML SCHEDULER                    │
    ├─────────────────────────────────────────┤
    │  Status:    Active                      │
    │  Uptime:    0.5 seconds                 │
    └─────────────────────────────────────────┘

    Args:
        title: Box title
        items: List of StatusInfo with label/value pairs
        border_style: Border color

    Returns:
        Rich Panel object
    """
    style_colors = {
        OutputStyle.SUCCESS: "green",
        OutputStyle.WARNING: "yellow",
        OutputStyle.ERROR: "red",
        OutputStyle.INFO: "cyan",
        OutputStyle.MUTED: "dim",
        OutputStyle.DEFAULT: "white",
    }

    # Build content with aligned labels
    max_label_len = max(len(item.label) for item in items) if items else 0
    lines = []

    for item in items:
        color = style_colors.get(item.style, "white")
        padded_label = item.label.ljust(max_label_len)
        lines.append(f"  [dim]{padded_label}:[/dim]  [{color}]{item.value}[/{color}]")

    content = "\n".join(lines)

    return Panel(
        content,
        title=f"[bold cyan]{title}[/bold cyan]",
        border_style=border_style,
        padding=(1, 2),
        box=box.ROUNDED,
    )


def format_table(
    columns: list[TableColumn],
    rows: list[list[str]],
    title: str | None = None,
    show_header: bool = True,
    show_lines: bool = False,
    row_styles: list[str] | None = None,
) -> Table:
    """
    Create a formatted table.

    Args:
        columns: List of TableColumn configurations
        rows: List of rows, each row is a list of cell values
        title: Optional table title
        show_header: Whether to show column headers
        show_lines: Whether to show row separator lines
        row_styles: Optional list of styles for each row

    Returns:
        Rich Table object
    """
    table = Table(
        title=f"[bold cyan]{title}[/bold cyan]" if title else None,
        show_header=show_header,
        header_style="bold cyan",
        border_style="cyan",
        show_lines=show_lines,
        box=box.ROUNDED,
        padding=(0, 1),
    )

    for col in columns:
        table.add_column(
            col.header,
            style=col.style,
            justify=col.justify,
            width=col.width,
            no_wrap=col.no_wrap,
        )

    for i, row in enumerate(rows):
        style = row_styles[i] if row_styles and i < len(row_styles) else None
        table.add_row(*row, style=style)

    return table


def format_package_table(
    packages: list[tuple[str, str, str]],
    title: str = "Packages",
) -> Table:
    """
    Create a formatted package table.

    Args:
        packages: List of (name, version, action) tuples
        title: Table title

    Returns:
        Rich Table object
    """
    columns = [
        TableColumn("Package", style="cyan", no_wrap=True),
        TableColumn("Version", style="white"),
        TableColumn("Action", style="green"),
    ]

    rows = [[pkg[0], pkg[1], pkg[2]] for pkg in packages]
    return format_table(columns, rows, title=title)


def format_dependency_tree(
    package: str,
    dependencies: dict,
    title: str | None = None,
) -> Tree:
    """
    Create a formatted dependency tree.

    Args:
        package: Root package name
        dependencies: Dict of {package: [dependencies]}
        title: Optional tree title

    Returns:
        Rich Tree object
    """
    tree = Tree(
        f"[bold cyan]{title or package}[/bold cyan]",
        guide_style="dim",
    )

    def add_deps(parent_tree: Tree, pkg: str, visited: set):
        if pkg in visited:
            parent_tree.add(f"[dim]{pkg} (circular)[/dim]")
            return
        visited.add(pkg)

        deps = dependencies.get(pkg, [])
        for dep in deps:
            branch = parent_tree.add(f"[cyan]{dep}[/cyan]")
            add_deps(branch, dep, visited.copy())

    add_deps(tree, package, set())
    return tree


@contextmanager
def spinner_context(
    message: str,
    success_message: str | None = None,
    error_message: str | None = None,
    spinner_type: str = "dots",
) -> Generator[Status, None, None]:
    """
    Context manager for showing a spinner during long operations.

    Args:
        message: Message to display while spinning
        success_message: Message to show on success (or None to stay quiet)
        error_message: Message to show on error (or None for default)
        spinner_type: Type of spinner animation

    Yields:
        Rich Status object for updating message

    Example:
        with spinner_context("Loading...", "Done!") as status:
            do_work()
            status.update("Still working...")
    """
    with console.status(f"[cyan]{message}[/cyan]", spinner=spinner_type) as status:
        try:
            yield status
            if success_message:
                console.print(f"[green]{STATUS_ICONS['success']}[/green] {success_message}")
        except Exception:
            if error_message:
                console.print(f"[red]{STATUS_ICONS['error']}[/red] {error_message}")
            raise


class ProgressTracker:
    """
    Progress bar tracker for multi-step operations.

    Example:
        with ProgressTracker("Installing packages") as tracker:
            for pkg in packages:
                tracker.update(f"Installing {pkg}")
                install(pkg)
                tracker.advance()
    """

    def __init__(
        self,
        description: str,
        total: int | None = None,
        show_speed: bool = False,
    ):
        self.description = description
        self.total = total
        self.show_speed = show_speed
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None

    def __enter__(self) -> "ProgressTracker":
        columns = [
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(bar_width=40, style="cyan", complete_style="green"),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        ]

        if self.total is not None:
            columns.append(TimeRemainingColumn())

        self._progress = Progress(*columns, console=console)
        self._progress.start()
        self._task_id = self._progress.add_task(
            self.description,
            total=self.total,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._progress:
            self._progress.stop()

    def update(self, description: str | None = None, advance: int = 0):
        """Update progress description and/or advance by given amount."""
        if self._progress and self._task_id is not None:
            self._progress.update(
                self._task_id,
                description=description or self.description,
                advance=advance,
            )

    def advance(self, amount: int = 1):
        """Advance progress by the given amount."""
        if self._progress and self._task_id is not None:
            self._progress.advance(self._task_id, amount)

    def set_total(self, total: int):
        """Set the total for the progress bar."""
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, total=total)


class MultiStepProgress:
    """
    Multi-step progress display for complex operations.

    Example:
        steps = ["Downloading", "Extracting", "Installing", "Configuring"]
        with MultiStepProgress(steps, "Package Installation") as progress:
            for step in steps:
                progress.start_step(step)
                do_work()
                progress.complete_step(step)
    """

    def __init__(self, steps: list[str], title: str = "Operation Progress"):
        self.steps = steps
        self.title = title
        self.step_status: dict = dict.fromkeys(steps, "pending")
        self._live: Live | None = None

    def __enter__(self) -> "MultiStepProgress":
        self._live = Live(self._render(), console=console, refresh_per_second=10)
        self._live.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._live:
            self._live.stop()
            # Show final state
            console.print(self._render())

    def _render(self) -> Panel:
        """Render the current step status."""
        lines = []
        for step in self.steps:
            status = self.step_status[step]
            if status == "pending":
                icon = f"[dim]{STATUS_ICONS['pending']}[/dim]"
                style = "dim"
            elif status == "running":
                icon = f"[cyan]{STATUS_ICONS['running']}[/cyan]"
                style = "cyan"
            elif status == "completed":
                icon = f"[green]{STATUS_ICONS['success']}[/green]"
                style = "green"
            elif status == "failed":
                icon = f"[red]{STATUS_ICONS['error']}[/red]"
                style = "red"
            else:
                icon = f"[dim]{STATUS_ICONS['skipped']}[/dim]"
                style = "dim"

            lines.append(f"  {icon} [{style}]{step}[/{style}]")

        content = "\n".join(lines)
        return Panel(
            content,
            title=f"[bold cyan]{self.title}[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
            box=box.ROUNDED,
        )

    def start_step(self, step: str):
        """Mark a step as running."""
        if step in self.step_status:
            self.step_status[step] = "running"
            if self._live:
                self._live.update(self._render())

    def complete_step(self, step: str):
        """Mark a step as completed."""
        if step in self.step_status:
            self.step_status[step] = "completed"
            if self._live:
                self._live.update(self._render())

    def fail_step(self, step: str):
        """Mark a step as failed."""
        if step in self.step_status:
            self.step_status[step] = "failed"
            if self._live:
                self._live.update(self._render())

    def skip_step(self, step: str):
        """Mark a step as skipped."""
        if step in self.step_status:
            self.step_status[step] = "skipped"
            if self._live:
                self._live.update(self._render())


def print_success(message: str):
    """Print a success message with icon."""
    console.print(f"[green]{STATUS_ICONS['success']}[/green] {message}")


def print_error(message: str):
    """Print an error message with icon."""
    console.print(f"[red]{STATUS_ICONS['error']}[/red] [red]{message}[/red]")


def print_warning(message: str):
    """Print a warning message with icon."""
    console.print(f"[yellow]{STATUS_ICONS['warning']}[/yellow] [yellow]{message}[/yellow]")


def print_info(message: str):
    """Print an info message with icon."""
    console.print(f"[blue]{STATUS_ICONS['info']}[/blue] {message}")


def print_box(content: str, **kwargs):
    """Print content in a formatted box."""
    console.print(format_box(content, **kwargs))


def print_status_box(title: str, items: list[StatusInfo], **kwargs):
    """Print a status box with key-value pairs."""
    console.print(format_status_box(title, items, **kwargs))


def print_table(columns: list[TableColumn], rows: list[list[str]], **kwargs):
    """Print a formatted table."""
    console.print(format_table(columns, rows, **kwargs))


def print_divider(title: str | None = None, style: str = "cyan"):
    """Print a horizontal divider with optional title."""
    if title:
        console.print(f"\n[bold {style}]━━━ {title} ━━━[/bold {style}]\n")
    else:
        console.print(f"[{style}]{'━' * 50}[/{style}]")


def format_bytes(num_bytes: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format seconds to human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


# Demo/test output
if __name__ == "__main__":
    # Demo the formatting capabilities
    console.print("\n[bold cyan]Cortex Output Formatter Demo[/bold cyan]\n")

    # Status box demo
    print_status_box(
        "CORTEX ML SCHEDULER",
        [
            StatusInfo("Status", "Active", OutputStyle.SUCCESS),
            StatusInfo("Uptime", "0.5 seconds", OutputStyle.DEFAULT),
            StatusInfo("CPU Usage", "12%", OutputStyle.INFO),
            StatusInfo("Memory", "256 MB", OutputStyle.WARNING),
        ],
    )

    console.print()

    # Table demo
    print_table(
        columns=[
            TableColumn("Package", style="cyan"),
            TableColumn("Version", style="white"),
            TableColumn("Status", style="green"),
        ],
        rows=[
            ["docker.io", "24.0.5", "Installed"],
            ["nginx", "1.24.0", "Available"],
            ["python3", "3.11.2", "Installed"],
        ],
        title="System Packages",
    )

    console.print()

    # Box demo
    print_box(
        "Installation completed successfully!\nAll packages are now available.",
        title="Success",
        style=OutputStyle.SUCCESS,
        border_style="green",
    )

    console.print()

    # Divider demo
    print_divider("Installation Plan")

    # Status messages
    print_success("Package installed successfully")
    print_warning("Disk space running low")
    print_error("Installation failed")
    print_info("Checking dependencies...")
