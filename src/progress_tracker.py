#!/usr/bin/env python3
"""
Progress Notifications & Status Updates for Cortex Linux
Real-time progress tracking with time estimates and desktop notifications.

Features:
- Beautiful progress bars with rich formatting
- Multi-stage progress tracking
- Time estimation algorithm
- Background operation support
- Desktop notifications
- Cancellation support with cleanup
"""

import asyncio
import time
import sys
import signal
from typing import Optional, Callable, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from contextlib import asynccontextmanager


try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, BarColumn, TextColumn,
        TimeElapsedColumn, TimeRemainingColumn, TaskProgressColumn
    )
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


try:
    from plyer import notification as plyer_notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


class StageStatus(Enum):
    """Status of a progress stage."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProgressStage:
    """Represents a single stage in a multi-stage operation."""
    name: str
    status: StageStatus = StageStatus.PENDING
    progress: float = 0.0  # 0.0 to 1.0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[str] = None
    total_bytes: Optional[int] = None
    processed_bytes: int = 0
    
    @property
    def elapsed_time(self) -> float:
        """Calculate elapsed time for this stage."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time
    
    @property
    def is_complete(self) -> bool:
        """Check if stage is complete."""
        return self.status in (StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.CANCELLED)
    
    def format_elapsed(self) -> str:
        """Format elapsed time as human-readable string."""
        elapsed = self.elapsed_time
        if elapsed < 60:
            return f"{elapsed:.0f}s"
        elif elapsed < 3600:
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            return f"{hours}h {minutes}m"


class ProgressTracker:
    """
    Multi-stage progress tracker with time estimation and notifications.
    
    Features:
    - Rich terminal progress bars
    - Time estimation based on throughput
    - Multi-stage operation tracking
    - Desktop notifications (optional)
    - Cancellation support
    - Background operation support
    """
    
    def __init__(self, 
                 operation_name: str,
                 enable_notifications: bool = True,
                 notification_on_complete: bool = True,
                 notification_on_error: bool = True,
                 console: Optional[Any] = None):
        """
        Initialize progress tracker.
        
        Args:
            operation_name: Name of the operation (e.g., "Installing PostgreSQL")
            enable_notifications: Enable desktop notifications
            notification_on_complete: Send notification on completion
            notification_on_error: Send notification on error
            console: Rich console instance (created if None)
        """
        self.operation_name = operation_name
        self.enable_notifications = enable_notifications and PLYER_AVAILABLE
        self.notification_on_complete = notification_on_complete
        self.notification_on_error = notification_on_error
        
        # Rich console
        if RICH_AVAILABLE:
            self.console = console or Console()
        else:
            self.console = None
        
        # Stages
        self.stages: List[ProgressStage] = []
        self.current_stage_index: int = -1
        
        # Timing
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        
        # Cancellation
        self.cancelled: bool = False
        self.cancel_callback: Optional[Callable] = None
        
        # Background task
        self.background_task: Optional[asyncio.Task] = None
    
    def add_stage(self, name: str, total_bytes: Optional[int] = None) -> int:
        """
        Add a stage to the operation.
        
        Args:
            name: Name of the stage
            total_bytes: Total bytes for this stage (for download/install tracking)
            
        Returns:
            Index of the added stage
        """
        stage = ProgressStage(name=name, total_bytes=total_bytes)
        self.stages.append(stage)
        return len(self.stages) - 1
    
    def start(self):
        """Start tracking progress."""
        self.start_time = time.time()
        if RICH_AVAILABLE:
            self.console.print(f"\n[bold cyan]{self.operation_name}[/bold cyan]")
        else:
            print(f"\n{self.operation_name}")
    
    def start_stage(self, stage_index: int):
        """
        Start a specific stage.
        
        Args:
            stage_index: Index of the stage to start
        """
        if 0 <= stage_index < len(self.stages):
            self.current_stage_index = stage_index
            stage = self.stages[stage_index]
            stage.status = StageStatus.IN_PROGRESS
            stage.start_time = time.time()
    
    def update_stage_progress(self, stage_index: int, progress: float = None, 
                             processed_bytes: int = None):
        """
        Update progress for a specific stage.
        
        Args:
            stage_index: Index of the stage
            progress: Progress value (0.0 to 1.0)
            processed_bytes: Number of bytes processed
        """
        if 0 <= stage_index < len(self.stages):
            stage = self.stages[stage_index]
            
            if progress is not None:
                stage.progress = min(1.0, max(0.0, progress))
            
            if processed_bytes is not None:
                stage.processed_bytes = processed_bytes
                if stage.total_bytes and stage.total_bytes > 0:
                    stage.progress = min(1.0, processed_bytes / stage.total_bytes)
    
    def complete_stage(self, stage_index: int, error: Optional[str] = None):
        """
        Mark a stage as complete or failed.
        
        Args:
            stage_index: Index of the stage
            error: Error message if stage failed
        """
        if 0 <= stage_index < len(self.stages):
            stage = self.stages[stage_index]
            stage.end_time = time.time()
            
            if error:
                stage.status = StageStatus.FAILED
                stage.error = error
            else:
                stage.status = StageStatus.COMPLETED
                stage.progress = 1.0
    
    def estimate_remaining_time(self) -> Optional[float]:
        """
        Estimate remaining time based on completed stages and current progress.
        
        Returns:
            Estimated seconds remaining, or None if cannot estimate
        """
        if not self.stages or self.start_time is None:
            return None
        
        # Calculate average time per completed stage
        completed_stages = [s for s in self.stages if s.status == StageStatus.COMPLETED]
        if not completed_stages:
            # No completed stages yet - use current stage progress
            if self.current_stage_index >= 0:
                current_stage = self.stages[self.current_stage_index]
                if current_stage.progress > 0 and current_stage.start_time:
                    elapsed = time.time() - current_stage.start_time
                    estimated_stage_time = elapsed / current_stage.progress
                    remaining_in_stage = estimated_stage_time - elapsed
                    
                    # Add time for remaining stages (estimate equal time)
                    remaining_stages = len(self.stages) - self.current_stage_index - 1
                    return remaining_in_stage + (remaining_stages * estimated_stage_time)
            
            return None
        
        avg_stage_time = sum(s.elapsed_time for s in completed_stages) / len(completed_stages)
        
        # Calculate remaining stages
        remaining_stages = len(self.stages) - len(completed_stages)
        
        # If there's a current stage in progress, estimate its remaining time
        if self.current_stage_index >= 0:
            current_stage = self.stages[self.current_stage_index]
            if current_stage.status == StageStatus.IN_PROGRESS:
                if current_stage.progress > 0:
                    elapsed = current_stage.elapsed_time
                    estimated_total = elapsed / current_stage.progress
                    remaining_in_current = estimated_total - elapsed
                    return remaining_in_current + ((remaining_stages - 1) * avg_stage_time)
        
        return remaining_stages * avg_stage_time
    
    def format_time_remaining(self) -> str:
        """Format estimated time remaining as human-readable string."""
        remaining = self.estimate_remaining_time()
        if remaining is None:
            return "calculating..."
        
        if remaining < 60:
            return f"{int(remaining)}s"
        elif remaining < 3600:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            return f"{hours}h {minutes}m"
    
    def get_overall_progress(self) -> float:
        """
        Calculate overall progress across all stages.
        
        Returns:
            Overall progress (0.0 to 1.0)
        """
        if not self.stages:
            return 0.0
        
        total_progress = sum(s.progress for s in self.stages)
        return total_progress / len(self.stages)
    
    def render_text_progress(self) -> str:
        """
        Render progress as plain text (fallback when rich is not available).
        
        Returns:
            Plain text progress representation
        """
        lines = [f"\n{self.operation_name}"]
        
        overall_progress = self.get_overall_progress()
        bar_width = 40
        filled = int(bar_width * overall_progress)
        bar = "=" * filled + "-" * (bar_width - filled)
        lines.append(f"[{bar}] {overall_progress * 100:.0f}%")
        
        # Time estimate
        time_remaining = self.format_time_remaining()
        lines.append(f"⏱️  Estimated time remaining: {time_remaining}")
        lines.append("")
        
        # Stages
        for i, stage in enumerate(self.stages):
            if stage.status == StageStatus.COMPLETED:
                icon = "[✓]"
                info = f"({stage.format_elapsed()})"
            elif stage.status == StageStatus.IN_PROGRESS:
                icon = "[→]"
                info = "(current)"
            elif stage.status == StageStatus.FAILED:
                icon = "[✗]"
                info = f"(failed: {stage.error})"
            elif stage.status == StageStatus.CANCELLED:
                icon = "[⊗]"
                info = "(cancelled)"
            else:
                icon = "[ ]"
                info = ""
            
            lines.append(f"{icon} {stage.name} {info}")
        
        return "\n".join(lines)
    
    def render_rich_progress(self) -> Table:
        """
        Render progress using rich formatting.
        
        Returns:
            Rich table with progress information
        """
        if not RICH_AVAILABLE:
            return None
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Icon", width=3)
        table.add_column("Stage", ratio=1)
        table.add_column("Info", justify="right")
        
        for stage in self.stages:
            if stage.status == StageStatus.COMPLETED:
                icon = "[green]✓[/green]"
                info = f"[dim]({stage.format_elapsed()})[/dim]"
                style = "green"
            elif stage.status == StageStatus.IN_PROGRESS:
                icon = "[cyan]→[/cyan]"
                info = "[cyan](current)[/cyan]"
                style = "cyan bold"
            elif stage.status == StageStatus.FAILED:
                icon = "[red]✗[/red]"
                info = f"[red](failed)[/red]"
                style = "red"
            elif stage.status == StageStatus.CANCELLED:
                icon = "[yellow]⊗[/yellow]"
                info = "[yellow](cancelled)[/yellow]"
                style = "yellow"
            else:
                icon = "[dim][ ][/dim]"
                info = ""
                style = "dim"
            
            table.add_row(icon, f"[{style}]{stage.name}[/{style}]", info)
        
        return table
    
    def display_progress(self):
        """Display current progress to console."""
        if RICH_AVAILABLE and self.console:
            # Clear and redraw
            self.console.clear()
            
            # Overall progress
            overall = self.get_overall_progress()
            time_remaining = self.format_time_remaining()
            
            self.console.print(f"\n[bold cyan]{self.operation_name}[/bold cyan]")
            
            # Progress bar
            bar_width = 40
            filled = int(bar_width * overall)
            bar = "━" * filled + "─" * (bar_width - filled)
            self.console.print(f"[cyan]{bar}[/cyan] {overall * 100:.0f}%")
            self.console.print(f"⏱️  Estimated time remaining: [yellow]{time_remaining}[/yellow]\n")
            
            # Stages table
            table = self.render_rich_progress()
            if table:
                self.console.print(table)
        else:
            # Fallback to plain text
            print("\033[2J\033[H", end="")  # Clear screen
            print(self.render_text_progress())
    
    def complete(self, success: bool = True, message: Optional[str] = None):
        """
        Mark operation as complete.
        
        Args:
            success: Whether operation completed successfully
            message: Optional completion message
        """
        self.end_time = time.time()
        
        # Complete any in-progress stages
        for stage in self.stages:
            if stage.status == StageStatus.IN_PROGRESS:
                self.complete_stage(
                    self.stages.index(stage),
                    error=None if success else message
                )
        
        # Final display
        self.display_progress()
        
        # Calculate total time
        total_time = self.end_time - self.start_time if self.start_time else 0
        
        # Display completion message
        if RICH_AVAILABLE and self.console:
            if success:
                elapsed_str = self._format_duration(total_time)
                final_msg = message or f"{self.operation_name} completed"
                self.console.print(f"\n[green]✅ {final_msg}[/green] [dim]({elapsed_str})[/dim]")
            else:
                self.console.print(f"\n[red]❌ {message or 'Operation failed'}[/red]")
        else:
            if success:
                print(f"\n✅ {message or 'Completed'} ({total_time:.1f}s)")
            else:
                print(f"\n❌ {message or 'Failed'}")
        
        # Send desktop notification
        if self.enable_notifications:
            if success and self.notification_on_complete:
                self._send_notification(
                    f"{self.operation_name} Complete",
                    f"Finished in {self._format_duration(total_time)}"
                )
            elif not success and self.notification_on_error:
                self._send_notification(
                    f"{self.operation_name} Failed",
                    message or "Operation failed",
                    timeout=10
                )
    
    def cancel(self, message: str = "Cancelled by user"):
        """
        Cancel the operation.
        
        Args:
            message: Cancellation message
        """
        self.cancelled = True
        
        # Mark all pending/in-progress stages as cancelled
        for stage in self.stages:
            if stage.status in (StageStatus.PENDING, StageStatus.IN_PROGRESS):
                stage.status = StageStatus.CANCELLED
                if stage.start_time and not stage.end_time:
                    stage.end_time = time.time()
        
        # Call cancel callback if provided
        if self.cancel_callback:
            try:
                self.cancel_callback()
            except Exception as e:
                if RICH_AVAILABLE and self.console:
                    self.console.print(f"[yellow]Warning: Cancel callback failed: {e}[/yellow]")
        
        # Display cancellation
        if RICH_AVAILABLE and self.console:
            self.console.print(f"\n[yellow]⊗ {message}[/yellow]")
        else:
            print(f"\n⊗ {message}")
        
        # Send notification
        if self.enable_notifications:
            self._send_notification(
                f"{self.operation_name} Cancelled",
                message,
                timeout=5
            )
    
    def _send_notification(self, title: str, message: str, timeout: int = 5):
        """
        Send desktop notification.
        
        Args:
            title: Notification title
            message: Notification message
            timeout: Notification timeout in seconds
        """
        if not PLYER_AVAILABLE:
            return
        
        try:
            plyer_notification.notify(
                title=title,
                message=message,
                app_name="Cortex Linux",
                timeout=timeout
            )
        except Exception:
            # Silently fail if notifications aren't supported
            pass
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as human-readable string."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    
    def setup_cancellation_handler(self, callback: Optional[Callable] = None):
        """
        Setup signal handler for graceful cancellation (Ctrl+C).
        
        Args:
            callback: Optional callback to run on cancellation
        """
        self.cancel_callback = callback
        
        def signal_handler(signum, frame):
            self.cancel("Operation cancelled by user (Ctrl+C)")
            sys.exit(130)  # Exit code for Ctrl+C
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


class RichProgressTracker(ProgressTracker):
    """
    Enhanced progress tracker using rich library for beautiful terminal output.
    """
    
    def __init__(self, *args, **kwargs):
        if not RICH_AVAILABLE:
            raise ImportError("rich library is required for RichProgressTracker. Install with: pip install rich")
        super().__init__(*args, **kwargs)
        self.progress_obj: Optional[Progress] = None
        self.live: Optional[Live] = None
        self.task_ids: Dict[int, Any] = {}
    
    @asynccontextmanager
    async def live_progress(self):
        """Context manager for live progress updates."""
        self.progress_obj = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )
        
        # Add tasks for each stage
        for i, stage in enumerate(self.stages):
            task_id = self.progress_obj.add_task(
                stage.name,
                total=100,
                visible=(i == 0)  # Only show first stage initially
            )
            self.task_ids[i] = task_id
        
        try:
            with self.progress_obj:
                yield self
        finally:
            self.progress_obj = None
            self.task_ids = {}
    
    def start_stage(self, stage_index: int):
        """Start a stage and make its progress bar visible."""
        super().start_stage(stage_index)
        
        if self.progress_obj and stage_index in self.task_ids:
            task_id = self.task_ids[stage_index]
            self.progress_obj.update(task_id, visible=True)
    
    def update_stage_progress(self, stage_index: int, progress: float = None,
                             processed_bytes: int = None):
        """Update stage progress and refresh progress bar."""
        super().update_stage_progress(stage_index, progress, processed_bytes)
        
        if self.progress_obj and stage_index in self.task_ids:
            stage = self.stages[stage_index]
            task_id = self.task_ids[stage_index]
            self.progress_obj.update(task_id, completed=stage.progress * 100)
    
    def complete_stage(self, stage_index: int, error: Optional[str] = None):
        """Complete a stage and update its status."""
        super().complete_stage(stage_index, error)
        
        if self.progress_obj and stage_index in self.task_ids:
            task_id = self.task_ids[stage_index]
            if error:
                self.progress_obj.update(task_id, description=f"[red]{self.stages[stage_index].name} (failed)[/red]")
            else:
                self.progress_obj.update(task_id, completed=100)


async def run_with_progress(tracker: ProgressTracker, 
                            operation_func: Callable,
                            *args, **kwargs) -> Any:
    """
    Run an async operation with progress tracking.
    
    Args:
        tracker: ProgressTracker instance
        operation_func: Async function to execute
        *args, **kwargs: Arguments to pass to operation_func
        
    Returns:
        Result from operation_func
    """
    tracker.start()
    tracker.setup_cancellation_handler()
    
    try:
        result = await operation_func(tracker, *args, **kwargs)
        tracker.complete(success=True)
        return result
    except asyncio.CancelledError:
        tracker.cancel("Operation cancelled")
        raise
    except Exception as e:
        tracker.complete(success=False, message=str(e))
        raise


# Example usage demonstrating the API
async def example_installation(tracker: ProgressTracker):
    """Example installation with multiple stages."""
    
    # Add stages
    update_idx = tracker.add_stage("Update package lists")
    download_idx = tracker.add_stage("Download postgresql-15", total_bytes=50_000_000)  # 50MB
    install_idx = tracker.add_stage("Installing dependencies")
    configure_idx = tracker.add_stage("Configuring database")
    test_idx = tracker.add_stage("Running tests")
    
    # Stage 1: Update package lists
    tracker.start_stage(update_idx)
    await asyncio.sleep(1)  # Simulate work
    for i in range(10):
        tracker.update_stage_progress(update_idx, progress=(i + 1) / 10)
        tracker.display_progress()
        await asyncio.sleep(0.1)
    tracker.complete_stage(update_idx)
    
    # Stage 2: Download
    tracker.start_stage(download_idx)
    bytes_downloaded = 0
    chunk_size = 5_000_000  # 5MB chunks
    while bytes_downloaded < 50_000_000:
        await asyncio.sleep(0.2)
        bytes_downloaded = min(bytes_downloaded + chunk_size, 50_000_000)
        tracker.update_stage_progress(download_idx, processed_bytes=bytes_downloaded)
        tracker.display_progress()
    tracker.complete_stage(download_idx)
    
    # Stage 3: Install dependencies
    tracker.start_stage(install_idx)
    for i in range(15):
        tracker.update_stage_progress(install_idx, progress=(i + 1) / 15)
        tracker.display_progress()
        await asyncio.sleep(0.15)
    tracker.complete_stage(install_idx)
    
    # Stage 4: Configure
    tracker.start_stage(configure_idx)
    for i in range(8):
        tracker.update_stage_progress(configure_idx, progress=(i + 1) / 8)
        tracker.display_progress()
        await asyncio.sleep(0.2)
    tracker.complete_stage(configure_idx)
    
    # Stage 5: Test
    tracker.start_stage(test_idx)
    for i in range(5):
        tracker.update_stage_progress(test_idx, progress=(i + 1) / 5)
        tracker.display_progress()
        await asyncio.sleep(0.3)
    tracker.complete_stage(test_idx)


async def main():
    """Demo of progress tracking."""
    tracker = ProgressTracker(
        operation_name="Installing PostgreSQL",
        enable_notifications=True
    )
    
    await run_with_progress(tracker, example_installation)


if __name__ == '__main__':
    print("Progress Tracker Demo")
    print("=" * 50)
    asyncio.run(main())

