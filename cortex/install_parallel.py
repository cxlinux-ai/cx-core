import asyncio
import time
import subprocess
import re
import concurrent.futures
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


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
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    output: str = ""
    error: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


async def run_single_task(task: ParallelTask, executor, timeout: int, log_callback: Optional[Callable] = None) -> bool:
    """Run a single task asynchronously.
    
    Args:
        task: Task to run
        executor: Thread pool executor for running blocking subprocess calls
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
    DANGEROUS_PATTERNS = [
        r'rm\s+-rf\s+[/\*]',
        r'rm\s+--no-preserve-root',
        r'dd\s+if=.*of=/dev/',
        r'curl\s+.*\|\s*sh',
        r'curl\s+.*\|\s*bash',
        r'wget\s+.*\|\s*sh',
        r'wget\s+.*\|\s*bash',
        r'\beval\s+',
        r'base64\s+-d\s+.*\|',
        r'>\s*/etc/',
        r'chmod\s+777',
        r'chmod\s+\+s',
    ]
    
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, task.command, re.IGNORECASE):
            task.status = TaskStatus.FAILED
            task.error = f"Command blocked: matches dangerous pattern"
            task.end_time = time.time()
            if log_callback:
                log_callback(f"Finished {task.name} (failed)", "error")
            return False
    
    try:
        # Run command in executor (thread pool) to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                executor,
                lambda: subprocess.run(
                    task.command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
            ),
            timeout=timeout + 5  # Slight buffer for asyncio overhead
        )
        
        task.output = result.stdout
        task.error = result.stderr
        task.end_time = time.time()
        
        if result.returncode == 0:
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
    commands: List[str],
    descriptions: Optional[List[str]] = None,
    dependencies: Optional[Dict[int, List[int]]] = None,
    timeout: int = 300,
    stop_on_error: bool = True,
    log_callback: Optional[Callable] = None
) -> tuple:
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
        Tuple of (success: bool, tasks: List[ParallelTask])
    """
    if not commands:
        return True, []
    
    if descriptions and len(descriptions) != len(commands):
        raise ValueError("Number of descriptions must match number of commands")
    
    # Create tasks
    tasks: Dict[str, ParallelTask] = {}
    for i, command in enumerate(commands):
        task_name = f"Task {i+1}"
        desc = descriptions[i] if descriptions else f"Step {i+1}"
        
        # Get dependencies for this task (if any commands depend on it, don't use that)
        # Instead, find which tasks this task depends on
        task_deps = []
        if dependencies:
            # Dependencies format: key=task_index -> list of indices it depends on
            for dep_idx in dependencies.get(i, []):
                task_deps.append(f"Task {dep_idx+1}")
        
        tasks[task_name] = ParallelTask(
            name=task_name,
            command=command,
            description=desc,
            dependencies=task_deps
        )
    
    # Execution tracking
    completed = set()
    running = {}
    pending = set(tasks.keys())
    failed = set()
    
    # Thread pool for subprocess calls
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    
    try:
        while pending or running:
            # Start tasks whose dependencies are met
            ready_to_start = []
            for task_name in list(pending):
                task = tasks[task_name]
                deps_met = all(dep in completed for dep in task.dependencies)
                
                if deps_met:
                    ready_to_start.append(task_name)
                    pending.remove(task_name)
            
            # Create tasks for ready items
            for task_name in ready_to_start:
                coro = run_single_task(tasks[task_name], executor, timeout, log_callback)
                running[task_name] = asyncio.create_task(coro)
            
            # If nothing is running and nothing is pending, we're done
            if not running and not pending:
                break
            
            # Wait for at least one task to finish
            if running:
                done, _ = await asyncio.wait(
                    running.values(),
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Process completed tasks
                for task_coro in done:
                    # Find which task this is
                    for task_name, running_coro in list(running.items()):
                        if running_coro is task_coro:
                            task = tasks[task_name]
                            success = task_coro.result()
                            
                            if success:
                                completed.add(task_name)
                            else:
                                failed.add(task_name)
                                
                                # If stop_on_error, skip dependent tasks
                                if stop_on_error:
                                    dependent_tasks = [
                                        name for name, t in tasks.items()
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
    
    finally:
        executor.shutdown(wait=True)
    
    # Check overall success
    all_success = len(failed) == 0
    task_list = list(tasks.values())
    
    return all_success, task_list
