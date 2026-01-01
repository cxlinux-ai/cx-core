"""Helpers for running Cortex integration tests inside Docker containers."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DockerRunResult:
    """Container execution result metadata."""

    returncode: int
    stdout: str
    stderr: str

    def succeeded(self) -> bool:
        """Return ``True`` when the container exited successfully."""
        return self.returncode == 0


def docker_available() -> bool:
    """Return ``True`` when the Docker client is available on the host."""

    docker_path = shutil.which("docker")
    if not docker_path:
        return False

    try:
        subprocess.run(
            [docker_path, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        subprocess.run(
            [docker_path, "info"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def run_in_docker(
    image: str,
    command: str,
    *,
    env: dict[str, str] | None = None,
    mounts: Iterable[tuple[Path, str]] | None = None,
    workdir: str = "/workspace",
    timeout: int = 300,
) -> DockerRunResult:
    """Run ``command`` inside the specified Docker ``image``.

    Parameters
    ----------
    image:
        Docker image tag to use.
    command:
        Shell command executed via ``bash -lc`` inside the container.
    env:
        Optional environment variables exported inside the container.
    mounts:
        Iterable of (host_path, container_path) tuples for mounting directories.

    workdir:
        Working directory set inside the container.
    timeout:
        Maximum run time in seconds before raising ``TimeoutExpired``.
    """

    docker_cmd: list[str] = ["docker", "run", "--rm"]

    for key, value in (env or {}).items():
        docker_cmd.extend(["-e", f"{key}={value}"])

    for host_path, container_path in mounts or []:
        docker_cmd.extend(
            [
                "-v",
                f"{str(host_path.resolve())}:{container_path}",
            ]
        )

    docker_cmd.extend(["-w", workdir])

    docker_cmd.append(image)
    docker_cmd.extend(["bash", "-lc", command])

    result = subprocess.run(
        docker_cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",  # Replace undecodable characters instead of failing
        timeout=timeout,
    )

    return DockerRunResult(result.returncode, result.stdout, result.stderr)
