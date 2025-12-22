"""
Progress Indicators Module for Cortex Linux

Provides beautiful, informative progress indicators for all Cortex operations
using the Rich library for terminal UI.

Issue: #259
"""

import logging
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )
    from rich.status import Status
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of operations that can show progress."""

    INSTALL = "install"
    REMOVE = "remove"
    UPDATE = "update"
    DOWNLOAD = "download"
    CONFIGURE = "configure"
    VERIFY = "verify"
    ANALYZE = "analyze"
    LLM_QUERY = "llm_query"
    DEPENDENCY_RESOLVE = "dependency_resolve"
    ROLLBACK = "rollback"
    GENERIC = "generic"


@dataclass
class OperationStep:
    """Represents a single step in a multi-step operation."""

    name: str
    description: str
    status: str = "pending"  # pending, running, completed, failed, skipped
    progress: float = 0.0  # 0.0 to 1.0
    start_time: datetime | None = None
    end_time: datetime | None = None
    error_message: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        elif self.start_time:
            return (datetime.now() - self.start_time).total_seconds()
        return None


@dataclass
class OperationContext:
    """Context for a tracked operation."""

    operation_type: OperationType
    title: str
    steps: list[OperationStep] = field(default_factory=list)
    current_step: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    status: str = "running"  # running, completed, failed, cancelled
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == "completed")

    @property
    def overall_progress(self) -> float:
        if not self.steps:
            return 0.0
        return self.completed_steps / self.total_steps


# Fallback implementation when Rich is not available
class FallbackProgress:
    """Simple fallback progress indicator without Rich."""

    def __init__(self):
        self._current_message = ""
        self._spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self._spinner_idx = 0
        self._running = False
        self._thread = None
        self._lock = threading.Lock()  # Protect shared state

    def start(self, message: str):
        """Start showing progress."""
        with self._lock:
            self._current_message = message
            self._running = True
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()

    def _animate(self):
        """Animate the spinner."""
        while True:
            with self._lock:
                if not self._running:
                    break
                char = self._spinner_chars[self._spinner_idx % len(self._spinner_chars)]
                message = self._current_message
                self._spinner_idx += 1

            sys.stdout.write(f"\r{char} {message}")
            sys.stdout.flush()
            time.sleep(0.1)

    def update(self, message: str):
        """Update the progress message."""
        with self._lock:
            self._current_message = message

    def stop(self, final_message: str = ""):
        """Stop the progress indicator."""
        with self._lock:
            self._running = False
            thread = self._thread
            message = final_message or self._current_message

        if thread:
            thread.join(timeout=0.5)
        sys.stdout.write(f"\r✓ {message}\n")
        sys.stdout.flush()

    def fail(self, message: str = ""):
        """Show failure."""
        with self._lock:
            self._running = False
            thread = self._thread
            msg = message or self._current_message

        if thread:
            thread.join(timeout=0.5)
        sys.stdout.write(f"\r✗ {msg}\n")
        sys.stdout.flush()


class ProgressIndicator:
    """
    Main progress indicator class supporting multiple display modes.

    Automatically uses Rich library if available, falls back to simple
    terminal output otherwise.
    """

    # Icons for different operation types
    OPERATION_ICONS = {
        OperationType.INSTALL: "📦",
        OperationType.REMOVE: "🗑️",
        OperationType.UPDATE: "🔄",
        OperationType.DOWNLOAD: "⬇️",
        OperationType.CONFIGURE: "⚙️",
        OperationType.VERIFY: "✅",
        OperationType.ANALYZE: "🔍",
        OperationType.LLM_QUERY: "🧠",
        OperationType.DEPENDENCY_RESOLVE: "🔗",
        OperationType.ROLLBACK: "⏪",
        OperationType.GENERIC: "▶️",
    }

    # Colors for different statuses
    STATUS_COLORS = {
        "pending": "dim",
        "running": "yellow",
        "completed": "green",
        "failed": "red",
        "skipped": "dim cyan",
    }

    def __init__(self, use_rich: bool = True):
        self.use_rich = use_rich and RICH_AVAILABLE
        self.console = Console() if self.use_rich else None
        self._active_context: OperationContext | None = None
        self._progress: Progress | None = None
        self._task_id = None

    @contextmanager
    def operation(
        self,
        title: str,
        operation_type: OperationType = OperationType.GENERIC,
        steps: list[str] | None = None,
    ):
        """
        Context manager for tracking an operation with progress.

        Usage:
            with progress.operation("Installing Docker", OperationType.INSTALL) as op:
                op.update("Downloading...")
                # do work
                op.update("Configuring...")
                # more work
        """
        context = OperationContext(
            operation_type=operation_type,
            title=title,
            steps=[OperationStep(name=s, description=s) for s in (steps or [])],
        )

        self._active_context = context
        icon = self.OPERATION_ICONS.get(operation_type, "▶️")

        try:
            if self.use_rich:
                yield RichOperationHandle(self, context, icon)
            else:
                yield FallbackOperationHandle(self, context)
        except Exception:
            context.status = "failed"
            context.end_time = datetime.now()
            raise
        finally:
            context.end_time = datetime.now()
            if context.status == "running":
                context.status = "completed"
            self._active_context = None

    @contextmanager
    def spinner(self, message: str):
        """
        Simple spinner for indeterminate operations.

        Usage:
            with progress.spinner("Thinking..."):
                result = call_llm()
        """
        if self.use_rich:
            with self.console.status(f"[bold blue]{message}") as status:
                yield SpinnerHandle(status)
        else:
            fallback = FallbackProgress()
            fallback.start(message)
            try:
                yield FallbackSpinnerHandle(fallback)
            finally:
                fallback.stop(message)

    def progress_bar(
        self, items: list[Any], description: str = "Processing", show_speed: bool = False
    ) -> Iterator[Any]:
        """
        Iterate over items with a progress bar.

        Usage:
            for package in progress.progress_bar(packages, "Installing"):
                install(package)
        """
        total = len(items)

        if self.use_rich:
            columns = [
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=40),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
            ]

            if show_speed:
                columns.append(TransferSpeedColumn())

            with Progress(*columns, console=self.console) as progress:
                task = progress.add_task(description, total=total)
                for item in items:
                    yield item
                    progress.advance(task)
        else:
            for i, item in enumerate(items):
                pct = (i + 1) / total * 100
                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                sys.stdout.write(f"\r{description}: [{bar}] {i + 1}/{total}")
                sys.stdout.flush()
                yield item
            print()  # Newline after completion

    def download_progress(
        self, total_bytes: int, description: str = "Downloading"
    ) -> "DownloadTracker":
        """
        Create a download progress tracker.

        Usage:
            tracker = progress.download_progress(file_size, "Downloading package")
            for chunk in download():
                tracker.update(len(chunk))
            tracker.complete()
        """
        return DownloadTracker(self, total_bytes, description)

    def multi_step(
        self, steps: list[dict[str, str]], title: str = "Operation Progress"
    ) -> "MultiStepTracker":
        """
        Create a multi-step operation tracker.

        Usage:
            tracker = progress.multi_step([
                {"name": "Download", "description": "Downloading package"},
                {"name": "Install", "description": "Installing files"},
                {"name": "Configure", "description": "Configuring service"},
            ])

            tracker.start_step(0)
            # do download
            tracker.complete_step(0)

            tracker.start_step(1)
            # do install
            tracker.complete_step(1)
        """
        return MultiStepTracker(self, steps, title)

    def print_success(self, message: str):
        """Print a success message."""
        if self.use_rich:
            self.console.print(f"[green]✓[/green] {message}")
        else:
            print(f"✓ {message}")

    def print_error(self, message: str):
        """Print an error message."""
        if self.use_rich:
            self.console.print(f"[red]✗[/red] {message}")
        else:
            print(f"✗ {message}")

    def print_warning(self, message: str):
        """Print a warning message."""
        if self.use_rich:
            self.console.print(f"[yellow]⚠[/yellow] {message}")
        else:
            print(f"⚠ {message}")

    def print_info(self, message: str):
        """Print an info message."""
        if self.use_rich:
            self.console.print(f"[blue]ℹ[/blue] {message}")
        else:
            print(f"ℹ {message}")


class RichOperationHandle:
    """Handle for Rich-based operation progress."""

    def __init__(self, indicator: ProgressIndicator, context: OperationContext, icon: str):
        self.indicator = indicator
        self.context = context
        self.icon = icon
        self._status = None
        self._start()

    def _start(self):
        """Start the progress display."""
        self._status = self.indicator.console.status(
            f"[bold blue]{self.icon} {self.context.title}[/bold blue]"
        )
        self._status.start()

    def update(self, message: str):
        """Update the progress message."""
        if self._status:
            self._status.update(
                f"[bold blue]{self.icon} {self.context.title}[/bold blue] - {message}"
            )

    def log(self, message: str, style: str = ""):
        """Log a message while progress is shown."""
        if self._status:
            self._status.stop()
            self.indicator.console.print(f"  {message}", style=style)
            self._status.start()

    def complete(self, message: str = "Done"):
        """Mark operation as complete."""
        if self._status:
            self._status.stop()
        self.context.status = "completed"
        self.indicator.console.print(f"[green]✓[/green] {self.context.title} - {message}")

    def fail(self, message: str = "Failed"):
        """Mark operation as failed."""
        if self._status:
            self._status.stop()
        self.context.status = "failed"
        self.indicator.console.print(f"[red]✗[/red] {self.context.title} - {message}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._status:
            self._status.stop()
        if exc_type:
            self.fail(str(exc_val))
        elif self.context.status == "running":
            self.complete()
        return False


class FallbackOperationHandle:
    """Handle for fallback operation progress."""

    def __init__(self, indicator: ProgressIndicator, context: OperationContext):
        self.indicator = indicator
        self.context = context
        self._progress = FallbackProgress()
        self._progress.start(context.title)

    def update(self, message: str):
        """Update the progress message."""
        self._progress.update(f"{self.context.title} - {message}")

    def log(self, message: str, style: str = ""):
        """Log a message."""
        print(f"  {message}")

    def complete(self, message: str = "Done"):
        """Mark operation as complete."""
        self._progress.stop(f"{self.context.title} - {message}")
        self.context.status = "completed"

    def fail(self, message: str = "Failed"):
        """Mark operation as failed."""
        self._progress.fail(f"{self.context.title} - {message}")
        self.context.status = "failed"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.fail(str(exc_val))
        elif self.context.status == "running":
            self.complete()
        return False


class SpinnerHandle:
    """Handle for Rich spinner."""

    def __init__(self, status: Status):
        self._status = status

    def update(self, message: str):
        """Update spinner message."""
        self._status.update(f"[bold blue]{message}")


class FallbackSpinnerHandle:
    """Handle for fallback spinner."""

    def __init__(self, progress: FallbackProgress):
        self._progress = progress

    def update(self, message: str):
        """Update spinner message."""
        self._progress.update(message)


class DownloadTracker:
    """Tracks download progress with speed and ETA."""

    def __init__(self, indicator: ProgressIndicator, total_bytes: int, description: str):
        self.indicator = indicator
        self.total_bytes = total_bytes
        self.description = description
        self.downloaded = 0
        self.start_time = time.time()
        self._progress = None
        self._task = None
        self._start()

    def _start(self):
        """Start the download progress display."""
        if self.indicator.use_rich:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=40),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=self.indicator.console,
            )
            self._progress.start()
            self._task = self._progress.add_task(self.description, total=self.total_bytes)

    def update(self, bytes_received: int):
        """Update with bytes received."""
        self.downloaded += bytes_received

        if self.indicator.use_rich and self._progress:
            self._progress.update(self._task, completed=self.downloaded)
        else:
            pct = self.downloaded / self.total_bytes * 100
            speed = self.downloaded / (time.time() - self.start_time) / 1024
            sys.stdout.write(f"\r{self.description}: {pct:.1f}% ({speed:.1f} KB/s)")
            sys.stdout.flush()

    def complete(self):
        """Mark download as complete."""
        if self.indicator.use_rich and self._progress:
            self._progress.stop()
        else:
            print()

        duration = time.time() - self.start_time
        speed = self.total_bytes / duration / 1024 / 1024
        self.indicator.print_success(
            f"Downloaded {self.total_bytes / 1024 / 1024:.1f} MB in {duration:.1f}s ({speed:.1f} MB/s)"
        )

    def fail(self, error: str):
        """Mark download as failed."""
        if self.indicator.use_rich and self._progress:
            self._progress.stop()
        self.indicator.print_error(f"Download failed: {error}")


class MultiStepTracker:
    """Tracks multi-step operations with visual progress."""

    def __init__(self, indicator: ProgressIndicator, steps: list[dict[str, str]], title: str):
        self.indicator = indicator
        self.steps = [
            OperationStep(name=s["name"], description=s.get("description", s["name"]))
            for s in steps
        ]
        self.title = title
        self.current_step = -1
        self._live = None
        self._start()

    def _start(self):
        """Start the multi-step display."""
        if self.indicator.use_rich:
            self._render()

    def _render(self):
        """Render the current state."""
        if not self.indicator.use_rich:
            return

        table = Table(title=self.title, show_header=False, box=None)
        table.add_column("Status", width=3)
        table.add_column("Step", width=20)
        table.add_column("Description")

        for _i, step in enumerate(self.steps):
            if step.status == "completed":
                icon = "[green]✓[/green]"
            elif step.status == "running":
                icon = "[yellow]●[/yellow]"
            elif step.status == "failed":
                icon = "[red]✗[/red]"
            elif step.status == "skipped":
                icon = "[dim]○[/dim]"
            else:
                icon = "[dim]○[/dim]"

            style = ProgressIndicator.STATUS_COLORS.get(step.status, "")
            table.add_row(icon, step.name, step.description, style=style)

        self.indicator.console.print(table)

    def start_step(self, index: int):
        """Start a specific step."""
        if 0 <= index < len(self.steps):
            self.steps[index].status = "running"
            self.steps[index].start_time = datetime.now()
            self.current_step = index

            if not self.indicator.use_rich:
                print(f"  → {self.steps[index].name}...")

    def complete_step(self, index: int):
        """Complete a specific step."""
        if 0 <= index < len(self.steps):
            self.steps[index].status = "completed"
            self.steps[index].end_time = datetime.now()
            self.steps[index].progress = 1.0

            if not self.indicator.use_rich:
                duration = self.steps[index].duration_seconds
                print(f"  ✓ {self.steps[index].name} ({duration:.1f}s)")

    def fail_step(self, index: int, error: str = ""):
        """Fail a specific step."""
        if 0 <= index < len(self.steps):
            self.steps[index].status = "failed"
            self.steps[index].end_time = datetime.now()
            self.steps[index].error_message = error

            if not self.indicator.use_rich:
                print(f"  ✗ {self.steps[index].name}: {error}")

    def skip_step(self, index: int, reason: str = ""):
        """Skip a specific step."""
        if 0 <= index < len(self.steps):
            self.steps[index].status = "skipped"

            if not self.indicator.use_rich:
                print(f"  ○ {self.steps[index].name} (skipped: {reason})")

    def finish(self):
        """Finish and display final state."""
        if self.indicator.use_rich:
            self._render()

        completed = sum(1 for s in self.steps if s.status == "completed")
        failed = sum(1 for s in self.steps if s.status == "failed")

        if failed > 0:
            self.indicator.print_error(
                f"Completed {completed}/{len(self.steps)} steps ({failed} failed)"
            )
        else:
            self.indicator.print_success(f"Completed {completed}/{len(self.steps)} steps")


# Global instance for convenience
_global_progress = None
_global_progress_lock = threading.Lock()


def get_progress_indicator() -> ProgressIndicator:
    """Get or create the global progress indicator."""
    global _global_progress
    if _global_progress is None:  # Fast path
        with _global_progress_lock:
            if _global_progress is None:  # Double-check
                _global_progress = ProgressIndicator()
    return _global_progress


# Convenience functions
def spinner(message: str):
    """Convenience function for spinner context manager."""
    return get_progress_indicator().spinner(message)


def operation(
    title: str,
    operation_type: OperationType = OperationType.GENERIC,
    steps: list[str] | None = None,
):
    """Convenience function for operation context manager."""
    return get_progress_indicator().operation(title, operation_type, steps)


def progress_bar(items: list[Any], description: str = "Processing"):
    """Convenience function for progress bar iterator."""
    return get_progress_indicator().progress_bar(items, description)


if __name__ == "__main__":
    # Demo
    progress = ProgressIndicator()

    print("Progress Indicators Demo")
    print("=" * 50)

    # Demo 1: Simple spinner
    print("\n1. Simple Spinner:")
    with progress.spinner("Analyzing system..."):
        time.sleep(2)
    progress.print_success("Analysis complete!")

    # Demo 2: Operation with updates
    print("\n2. Operation with updates:")
    with progress.operation("Installing Docker", OperationType.INSTALL) as op:
        op.update("Checking dependencies...")
        time.sleep(1)
        op.update("Downloading package...")
        time.sleep(1)
        op.update("Configuring...")
        time.sleep(1)
        op.complete("Docker installed successfully")

    # Demo 3: Progress bar
    print("\n3. Progress bar:")
    packages = ["nginx", "redis", "postgresql", "nodejs", "python3"]
    for _pkg in progress.progress_bar(packages, "Installing packages"):
        time.sleep(0.5)

    # Demo 4: Multi-step tracker
    print("\n4. Multi-step operation:")
    tracker = progress.multi_step(
        [
            {"name": "Download", "description": "Downloading package files"},
            {"name": "Verify", "description": "Verifying checksums"},
            {"name": "Install", "description": "Installing to system"},
            {"name": "Configure", "description": "Configuring service"},
        ],
        "Package Installation",
    )

    for i in range(4):
        tracker.start_step(i)
        time.sleep(0.8)
        tracker.complete_step(i)

    tracker.finish()

    print("\n✅ Demo complete!")
