import asyncio
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from cortex.validators import DANGEROUS_PATTERNS


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ParallelTask:
    """Represents a single task in parallel execution."""

    name: str
    command: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    output: str = ""
    error: str = ""
    start_time: float | None = None
    end_time: float | None = None

    def duration(self) -> float | None:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


async def run_single_task(
    task: ParallelTask,
    timeout: int,
    log_callback: Callable[[str, str], None] | None = None,
) -> bool:
    """Run a single task asynchronously.

    Args:
        task: Task to run
        timeout: Command timeout in seconds
        log_callback: Optional callback for logging messages

    Returns:
        True if task succeeded, False otherwise
    """
    task.status = TaskStatus.RUNNING
    task.start_time = time.time()

    # Log task start
    if log_callback:
        log_callback(f"Starting {task.name}…", "info")

    # Validate command for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, task.command, re.IGNORECASE):
            task.status = TaskStatus.FAILED
            task.error = "Command blocked: matches dangerous pattern"
            task.end_time = time.time()
            if log_callback:
                log_callback(f"Finished {task.name} (failed)", "error")
            return False

    try:
        # Use async subprocess for proper async execution
        # shell=True is required to support complex shell commands (e.g., pipes, redirects).
        # Commands are validated against dangerous patterns above.
        process = await asyncio.wait_for(
            asyncio.create_subprocess_shell(
                task.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=timeout,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        task.output = stdout.decode("utf-8", errors="replace")
        task.error = stderr.decode("utf-8", errors="replace")
        task.end_time = time.time()

        if process.returncode == 0:
            task.status = TaskStatus.SUCCESS
            if log_callback:
                log_callback(f"Finished {task.name} (ok)", "success")
            return True
        else:
            task.status = TaskStatus.FAILED
            if log_callback:
                log_callback(f"Finished {task.name} (failed)", "error")
            return False

    except asyncio.TimeoutError:
        task.status = TaskStatus.FAILED
        task.error = f"Command timed out after {timeout} seconds"
        task.end_time = time.time()
        if log_callback:
            log_callback(f"Finished {task.name} (failed)", "error")
        return False

    except Exception as e:
        task.status = TaskStatus.FAILED
        task.error = str(e)
        task.end_time = time.time()
        if log_callback:
            log_callback(f"Finished {task.name} (failed)", "error")
        return False


async def run_parallel_install(
    commands: list[str],
    descriptions: list[str] | None = None,
    dependencies: dict[int, list[int]] | None = None,
    timeout: int = 300,
    stop_on_error: bool = True,
    log_callback: Callable[[str, str], None] | None = None,
) -> tuple[bool, list[ParallelTask]]:
    """Execute installation tasks in parallel based on dependency graph.

    Args:
        commands: List of commands to execute
        descriptions: Optional list of descriptions for each command
        dependencies: Optional dict mapping command index to list of dependent indices
                     e.g., {0: [], 1: [0]} means task 1 depends on task 0
        timeout: Timeout per command in seconds
        stop_on_error: If True, cancel dependent tasks when a task fails
        log_callback: Optional callback for logging (called with message and level)

    Returns:
        tuple[bool, list[ParallelTask]]: Success status and list of all tasks
    """
    if not commands:
        return True, []

    if descriptions and len(descriptions) != len(commands):
        raise ValueError("Number of descriptions must match number of commands")

    # Create tasks
    tasks: dict[str, ParallelTask] = {}
    for i, command in enumerate(commands):
        task_name = f"Task {i + 1}"
        desc = descriptions[i] if descriptions else f"Step {i + 1}"

        # Get dependencies for this task (if any commands depend on it, don't use that)
        # Instead, find which tasks this task depends on
        task_deps: list[str] = []
        if dependencies:
            # Dependencies format: key=task_index -> list of indices it depends on
            for dep_idx in dependencies.get(i, []):
                task_deps.append(f"Task {dep_idx + 1}")

        tasks[task_name] = ParallelTask(
            name=task_name,
            command=command,
            description=desc,
            dependencies=task_deps,
        )

    # Execution tracking
    completed = set()
    running = {}
    pending = set(tasks.keys())
    failed = set()

    # Thread pool for subprocess calls

    try:
        while pending or running:
            # Start tasks whose dependencies are met
            ready_to_start = []
            for task_name in pending.copy():
                task = tasks[task_name]
                # When stop_on_error=False, accept both completed and failed dependencies
                if stop_on_error:
                    deps_met = all(dep in completed for dep in task.dependencies)
                else:
                    deps_met = all(dep in completed or dep in failed for dep in task.dependencies)

                if deps_met:
                    ready_to_start.append(task_name)
                    pending.remove(task_name)

            # If no tasks can be started and none are running, we're stuck (deadlock/cycle detection)
            if not ready_to_start and not running and pending:
                # Mark remaining tasks as skipped - they have unresolvable dependencies
                for task_name in pending:
                    task = tasks[task_name]
                    if task.status == TaskStatus.PENDING:
                        task.status = TaskStatus.SKIPPED
                        task.error = "Task could not run because dependencies never completed"
                        if log_callback:
                            log_callback(
                                f"{task_name} skipped due to unresolved dependencies", "error"
                            )
                failed.update(pending)
                break

            # Create tasks for ready items
            for task_name in ready_to_start:
                coro = run_single_task(tasks[task_name], timeout, log_callback)
                running[task_name] = asyncio.create_task(coro)

            # If nothing is running and nothing is pending, we're done
            if not running and not pending:
                break

            # Wait for at least one task to finish
            if running:
                done, _ = await asyncio.wait(
                    running.values(),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Process completed tasks
                for task_coro in done:
                    # Find which task this is
                    for task_name, running_coro in running.items():
                        if running_coro is task_coro:
                            task = tasks[task_name]

                            # Handle cancelled child tasks (not outer cancellation)
                            try:
                                success = task_coro.result()
                            except asyncio.CancelledError:
                                # Child task was cancelled due to stop_on_error
                                task.status = TaskStatus.SKIPPED
                                task.error = "Task cancelled due to dependency failure"
                                failed.add(task_name)
                                del running[task_name]
                                break  # Continue to next completed task

                            if success:
                                completed.add(task_name)
                            else:
                                failed.add(task_name)

                                # If stop_on_error, skip dependent tasks
                                if stop_on_error:
                                    dependent_tasks = [
                                        name
                                        for name, t in tasks.items()
                                        if task_name in t.dependencies
                                    ]
                                    for dep_task_name in dependent_tasks:
                                        if dep_task_name in pending:
                                            pending.remove(dep_task_name)
                                            tasks[dep_task_name].status = TaskStatus.SKIPPED
                                        elif dep_task_name in running:
                                            running[dep_task_name].cancel()

                            del running[task_name]
                            break

    except asyncio.CancelledError:
        # Cancel all running tasks on outer cancellation
        for task_coro in running.values():
            task_coro.cancel()
        raise
    finally:
        pass  # Cleanup if needed

    # Check overall success
    all_success = len(failed) == 0
    task_list = list(tasks.values())

    return all_success, task_list
