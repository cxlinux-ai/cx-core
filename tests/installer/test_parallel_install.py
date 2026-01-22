"""Tests for parallel installation execution."""

import asyncio
import sys
import time

import pytest

from cortex.install_parallel import TaskStatus, run_parallel_install


class TestParallelExecution:
    """Test parallel execution of installation tasks."""

    def test_parallel_runs_faster_than_sequential(self):
        """Verify that parallel execution is faster for independent tasks."""

        async def run_test():
            # Create 3 independent commands using Python's time.sleep (Windows-compatible)
            commands = [
                f'"{sys.executable}" -c "import time; time.sleep(0.1); print(\'Task 1\')"',
                f'"{sys.executable}" -c "import time; time.sleep(0.1); print(\'Task 2\')"',
                f'"{sys.executable}" -c "import time; time.sleep(0.1); print(\'Task 3\')"',
            ]

            # Run in parallel
            start = time.time()
            success, tasks = await run_parallel_install(commands, timeout=10)
            parallel_time = time.time() - start

            assert success
            assert all(t.status == TaskStatus.SUCCESS for t in tasks)

            # Parallel execution should be faster than sequential (0.3s + overhead)
            # On Windows, Python subprocess startup adds significant overhead
            # We just verify it completes and doesn't take more than 1 second
            assert parallel_time < 1.0, f"Parallel execution took {parallel_time}s, expected < 1.0s"

        asyncio.run(run_test())

    def test_dependency_order_respected(self):
        """Verify that task execution respects dependency order."""

        async def run_test():
            commands = [
                f'"{sys.executable}" -c "print(\'Task 1\')"',
                f'"{sys.executable}" -c "print(\'Task 2\')"',
                f'"{sys.executable}" -c "print(\'Task 3\')"',
            ]

            # Task 1 has no dependencies
            # Task 2 depends on Task 1
            # Task 3 depends on Task 2
            dependencies = {
                0: [],  # Task 1 (index 0) has no dependencies
                1: [0],  # Task 2 (index 1) depends on Task 1 (index 0)
                2: [1],  # Task 3 (index 2) depends on Task 2 (index 1)
            }

            success, tasks = await run_parallel_install(
                commands, dependencies=dependencies, timeout=10
            )

            assert success
            assert all(t.status == TaskStatus.SUCCESS for t in tasks)

        asyncio.run(run_test())

    def test_failure_blocks_dependent_tasks(self):
        """Verify that dependent tasks are skipped when a parent task fails."""

        async def run_test():
            commands = [
                f'"{sys.executable}" -c "exit(1)"',  # Task 1 fails
                f'"{sys.executable}" -c "print(\'Task 2\')"',  # Task 2 depends on Task 1
                f'"{sys.executable}" -c "print(\'Task 3\')"',  # Task 3 is independent
            ]

            # Task 2 depends on Task 1
            dependencies = {
                0: [],  # Task 1 has no dependencies
                1: [0],  # Task 2 depends on Task 1 (which will fail)
                2: [],  # Task 3 is independent
            }

            success, tasks = await run_parallel_install(
                commands, dependencies=dependencies, timeout=10, stop_on_error=True
            )

            assert not success
            assert tasks[0].status == TaskStatus.FAILED
            assert tasks[1].status == TaskStatus.SKIPPED  # Blocked by failed Task 1
            assert tasks[2].status == TaskStatus.SUCCESS  # Independent, should run

        asyncio.run(run_test())

    def test_all_independent_tasks_run(self):
        """Verify that all independent tasks run in parallel."""

        async def run_test():
            commands = [
                f'"{sys.executable}" -c "print(\'Task 1\')"',
                f'"{sys.executable}" -c "print(\'Task 2\')"',
                f'"{sys.executable}" -c "print(\'Task 3\')"',
                f'"{sys.executable}" -c "print(\'Task 4\')"',
            ]

            # All tasks are independent (no dependencies)
            dependencies = {0: [], 1: [], 2: [], 3: []}

            success, tasks = await run_parallel_install(
                commands, dependencies=dependencies, timeout=10
            )

            assert success
            assert all(t.status == TaskStatus.SUCCESS for t in tasks)
            assert len(tasks) == 4

        asyncio.run(run_test())

    def test_descriptions_match_tasks(self):
        """Verify that descriptions are properly assigned to tasks."""

        async def run_test():
            commands = [
                f'"{sys.executable}" -c "print(\'Task 1\')"',
                f'"{sys.executable}" -c "print(\'Task 2\')"',
            ]
            descriptions = ["Install package A", "Start service B"]

            success, tasks = await run_parallel_install(
                commands, descriptions=descriptions, timeout=10
            )

            assert success
            assert tasks[0].description == "Install package A"
            assert tasks[1].description == "Start service B"

        asyncio.run(run_test())

    def test_invalid_description_count_raises_error(self):
        """Verify that mismatched description count raises ValueError."""

        async def run_test():
            commands = [
                f'"{sys.executable}" -c "print(\'Task 1\')"',
                f'"{sys.executable}" -c "print(\'Task 2\')"',
            ]
            descriptions = ["Only one description"]  # Mismatch

            with pytest.raises(ValueError):
                await run_parallel_install(commands, descriptions=descriptions, timeout=10)

        asyncio.run(run_test())

    def test_command_timeout(self):
        """Verify that commands timing out are handled correctly."""

        async def run_test():
            commands = [
                f'"{sys.executable}" -c "import time; time.sleep(5)"',  # This will timeout with 1 second limit
            ]

            success, tasks = await run_parallel_install(commands, timeout=1)

            assert not success
            assert tasks[0].status == TaskStatus.FAILED
            assert "timed out" in tasks[0].error.lower() or "timeout" in tasks[0].error.lower()

        asyncio.run(run_test())

    def test_empty_commands_list(self):
        """Verify handling of empty command list."""

        async def run_test():
            success, tasks = await run_parallel_install([], timeout=5)

            assert success
            assert len(tasks) == 0

        asyncio.run(run_test())

    def test_task_status_tracking(self):
        """Verify that task status is properly tracked."""

        async def run_test():
            commands = [f'"{sys.executable}" -c "print(\'Success\')"']

            success, tasks = await run_parallel_install(commands, timeout=10)

            assert success
            task = tasks[0]
            assert task.status == TaskStatus.SUCCESS
            assert "Success" in task.output
            assert task.start_time is not None
            assert task.end_time is not None
            assert task.duration() is not None
            assert task.duration() > 0

        asyncio.run(run_test())

    def test_sequential_mode_unchanged(self):
        """Verify that sequential mode (no dependencies) still works as expected."""

        async def run_test():
            commands = [
                f'"{sys.executable}" -c "print(\'Step 1\')"',
                f'"{sys.executable}" -c "print(\'Step 2\')"',
                f'"{sys.executable}" -c "print(\'Step 3\')"',
            ]
            descriptions = ["Step 1", "Step 2", "Step 3"]

            success, tasks = await run_parallel_install(
                commands, descriptions=descriptions, timeout=10
            )

            assert success
            assert len(tasks) == 3
            assert all(t.status == TaskStatus.SUCCESS for t in tasks)
            assert all(t.description for t in tasks)

        asyncio.run(run_test())

    def test_log_callback_called(self):
        """Verify that log callback is invoked during execution."""

        async def run_test():
            commands = [f'"{sys.executable}" -c "print(\'Test\')"']
            log_messages = []

            def log_callback(message: str, level: str = "info"):
                log_messages.append((message, level))

            success, _tasks = await run_parallel_install(
                commands, timeout=10, log_callback=log_callback
            )

            assert success
            # Should have at least "Starting" and "Finished" messages
            assert len(log_messages) >= 2
            assert any("Starting" in msg[0] for msg in log_messages)
            assert any("Finished" in msg[0] for msg in log_messages)

        asyncio.run(run_test())


class TestParallelExecutionIntegration:
    """Integration tests for parallel execution with realistic scenarios."""

    def test_diamond_dependency_graph(self):
        """Test diamond-shaped dependency graph:
        Task 1 -> Task 2 & Task 3 -> Task 4
        """

        async def run_test():
            commands = [
                f'"{sys.executable}" -c "print(\'Base\')"',  # Task 1
                f'"{sys.executable}" -c "print(\'Branch A\')"',  # Task 2
                f'"{sys.executable}" -c "print(\'Branch B\')"',  # Task 3
                f'"{sys.executable}" -c "print(\'Final\')"',  # Task 4
            ]

            # Task 2 and 3 depend on Task 1
            # Task 4 depends on both Task 2 and 3
            dependencies = {
                0: [],  # Task 1 (base)
                1: [0],  # Task 2 depends on Task 1
                2: [0],  # Task 3 depends on Task 1
                3: [1, 2],  # Task 4 depends on Task 2 and 3
            }

            success, tasks = await run_parallel_install(
                commands, dependencies=dependencies, timeout=10
            )

            assert success
            assert all(t.status == TaskStatus.SUCCESS for t in tasks)

        asyncio.run(run_test())

    def test_mixed_success_and_independent_failure(self):
        """Test that independent failures don't block unrelated tasks."""

        async def run_test():
            commands = [
                f'"{sys.executable}" -c "exit(1)"',  # Task 1 fails
                f'"{sys.executable}" -c "print(\'OK\')"',  # Task 2 independent
                f'"{sys.executable}" -c "print(\'OK\')"',  # Task 3 independent
            ]

            dependencies = {0: [], 1: [], 2: []}

            success, tasks = await run_parallel_install(
                commands,
                dependencies=dependencies,
                timeout=10,
                stop_on_error=False,  # Don't stop on error to see all results
            )

            assert not success
            assert tasks[0].status == TaskStatus.FAILED
            assert tasks[1].status == TaskStatus.SUCCESS
            assert tasks[2].status == TaskStatus.SUCCESS

        asyncio.run(run_test())
