"""Docker-backed integration tests that exercise Cortex end-to-end flows."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from .docker_utils import DockerRunResult, docker_available, run_in_docker

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE = os.environ.get("CORTEX_INTEGRATION_IMAGE", "python:3.11-slim")
MOUNT = (REPO_ROOT, "/workspace")
BASE_ENV = {
    "PYTHONUNBUFFERED": "1",
    "PYTHONPATH": "/workspace",
    "PYTHONDONTWRITEBYTECODE": "1",
}
PIP_BOOTSTRAP = "python -m pip install --quiet --upgrade pip setuptools build && python -m pip install --quiet --no-cache-dir -e /workspace"
PIP_BOOTSTRAP_DEV = "python -m pip install --quiet --upgrade pip setuptools build && python -m pip install --quiet --no-cache-dir -e /workspace[dev]"


@unittest.skipUnless(docker_available(), "Docker is required for integration tests")
class TestEndToEndWorkflows(unittest.TestCase):
    """Run Cortex commands inside disposable Docker containers."""

    def _run(self, command: str, env: dict | None = None) -> DockerRunResult:
        effective_env = dict(BASE_ENV)
        if env:
            effective_env.update(env)
        return run_in_docker(
            DEFAULT_IMAGE,
            f"{PIP_BOOTSTRAP} && {command}",
            env=effective_env,
            mounts=[MOUNT],
            workdir="/workspace",
        )

    def test_cli_help_executes(self):
        """`cortex --help` should run successfully in a clean container."""

        result = self._run("python -m cortex.cli --help")
        self.assertTrue(result.succeeded(), msg=result.stderr)
        self.assertIn("AI-powered Linux command interpreter", result.stdout)

    def test_cli_dry_run_with_fake_provider(self):
        """Dry-run installations rely on the fake provider and skip API calls."""

        fake_commands = json.dumps(
            {
                "commands": [
                    "echo Step 1",
                    "echo Step 2",
                ]
            }
        )
        env = {
            "CORTEX_PROVIDER": "fake",
            "CORTEX_FAKE_COMMANDS": fake_commands,
        }
        result = self._run("python -m cortex.cli install docker --dry-run", env=env)

        self.assertTrue(result.succeeded(), msg=result.stderr)
        # i18n: "Commands that would run:" or legacy "Generated commands"
        self.assertTrue(
            "Commands that would run" in result.stdout or "Generated commands" in result.stdout,
            msg=f"Expected dry-run output header not found in: {result.stdout}",
        )
        self.assertIn("echo Step 1", result.stdout)

    def test_cli_execute_with_fake_provider(self):
        """Execution mode should run fake commands without touching the host."""

        fake_commands = json.dumps(
            {
                "commands": [
                    "echo Exec Step 1",
                    "echo Exec Step 2",
                ]
            }
        )
        env = {
            "CORTEX_PROVIDER": "fake",
            "CORTEX_FAKE_COMMANDS": fake_commands,
        }
        result = self._run("python -m cortex.cli install docker --execute", env=env)

        self.assertTrue(result.succeeded(), msg=result.stderr)
        # Output formatting may vary (Rich UI vs legacy), but the success text should be present.
        # i18n: "docker installed successfully" (no exclamation in i18n version)
        self.assertTrue(
            "docker installed successfully" in result.stdout,
            msg=f"Expected success message not found in: {result.stdout}",
        )

    def test_coordinator_executes_in_container(self):
        """InstallationCoordinator should execute simple commands inside Docker."""

        script = (
            "python - <<'PY'\n"
            "from cortex.coordinator import InstallationCoordinator\n"
            "plan = InstallationCoordinator(['echo coordinator step'])\n"
            "result = plan.execute()\n"
            "assert result.success\n"
            "print('STEPS', len(result.steps))\n"
            "PY"
        )
        result = self._run(script)

        self.assertTrue(result.succeeded(), msg=result.stderr)
        self.assertIn("STEPS 1", result.stdout)

    def test_project_tests_run_inside_container(self):
        """The unified test runner should pass within the container."""

        env = {
            "CORTEX_PROVIDER": "fake",
            "CORTEX_FAKE_COMMANDS": json.dumps({"commands": ["echo plan"]}),
        }
        # Use PIP_BOOTSTRAP_DEV to install pytest and other dev dependencies
        effective_env = dict(BASE_ENV)
        effective_env.update(env)
        result = run_in_docker(
            DEFAULT_IMAGE,
            f"{PIP_BOOTSTRAP_DEV} && pytest tests/ -v --ignore=tests/integration",
            env=effective_env,
            mounts=[MOUNT],
            workdir="/workspace",
        )

        self.assertTrue(result.succeeded(), msg=result.stderr)
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertIn("passed", combined_output.lower())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
