#!/usr/bin/env python3
"""
Docker-based Package Sandbox Testing Environment for Cortex Linux.

Provides isolated Docker containers for testing packages before installing
to the main system. Docker is required only for sandbox commands.

Features:
- Create isolated Docker environments
- Install packages in sandbox
- Run automated tests
- Validate functionality
- Promote to main system (fresh install on host)
- Automatic cleanup
"""

import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SandboxState(Enum):
    """State of a sandbox environment."""

    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    DESTROYED = "destroyed"


class SandboxTestStatus(Enum):
    """Result of a sandbox test."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SandboxTestResult:
    """Result of a single test in sandbox."""

    name: str
    result: SandboxTestStatus
    message: str = ""
    duration: float = 0.0


@dataclass
class SandboxInfo:
    """Information about a sandbox environment."""

    name: str
    container_id: str
    state: SandboxState
    created_at: str
    image: str
    packages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "container_id": self.container_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "image": self.image,
            "packages": self.packages,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SandboxInfo":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            container_id=data["container_id"],
            state=SandboxState(data["state"]),
            created_at=data["created_at"],
            image=data["image"],
            packages=data.get("packages", []),
        )


@dataclass
class SandboxExecutionResult:
    """Result of sandbox operation."""

    success: bool
    message: str
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    test_results: list[SandboxTestResult] = field(default_factory=list)
    packages_installed: list[str] = field(default_factory=list)


class DockerNotFoundError(Exception):
    """Raised when Docker is not installed or not running."""

    pass


class SandboxNotFoundError(Exception):
    """Raised when a sandbox environment is not found."""

    pass


class SandboxAlreadyExistsError(Exception):
    """Raised when trying to create a sandbox that already exists."""

    pass


class DockerSandbox:
    """
    Docker-based sandbox manager for package testing.

    Provides isolated environments using Docker containers for safe
    package testing before installation on the host system.

    Example:
        sandbox = DockerSandbox()
        sandbox.create("test-env")
        sandbox.install("test-env", "nginx")
        result = sandbox.test("test-env")
        if result.success:
            sandbox.promote("test-env", "nginx")
        sandbox.cleanup("test-env")
    """

    # Default base image for sandboxes
    DEFAULT_IMAGE = "ubuntu:22.04"

    # Container name prefix
    CONTAINER_PREFIX = "cortex-sandbox-"

    # Commands that cannot run in Docker sandbox
    SANDBOX_BLOCKED_COMMANDS = {
        "systemctl",
        "service",
        "journalctl",
        "modprobe",
        "insmod",
        "rmmod",
        "lsmod",
        "sysctl",
        "mount",
        "umount",
        "fdisk",
        "mkfs",
        "reboot",
        "shutdown",
        "halt",
        "poweroff",
        "init",
    }

    def __init__(
        self,
        data_dir: Path | None = None,
        image: str | None = None,
    ):
        """
        Initialize Docker sandbox manager.

        Args:
            data_dir: Directory to store sandbox metadata. Defaults to ~/.cortex/sandboxes
            image: Default Docker image to use. Defaults to ubuntu:22.04
        """
        self.data_dir = data_dir or Path.home() / ".cortex" / "sandboxes"
        self.default_image = image or self.DEFAULT_IMAGE
        self._docker_path: str | None = None

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def check_docker(self) -> bool:
        """
        Check if Docker is installed and running.

        Returns:
            True if Docker is available and running, False otherwise.
        """
        docker_path = shutil.which("docker")
        if not docker_path:
            return False

        try:
            # Check if docker command works
            result = subprocess.run(
                [docker_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return False

            # Check if docker daemon is running
            result = subprocess.run(
                [docker_path, "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.debug(f"Docker check failed: {e}")
            return False

    def require_docker(self) -> str:
        """
        Ensure Docker is available, raising an error if not.

        Returns:
            Path to docker executable.

        Raises:
            DockerNotFoundError: If Docker is not installed or not running.
        """
        if self._docker_path:
            return self._docker_path

        docker_path = shutil.which("docker")
        if not docker_path:
            raise DockerNotFoundError(
                "Docker is required for sandbox commands.\n"
                "Install Docker from https://docs.docker.com/get-docker/"
            )

        # Verify Docker daemon is running
        try:
            result = subprocess.run(
                [docker_path, "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise DockerNotFoundError(
                    "Docker daemon is not running.\nStart Docker with: sudo systemctl start docker"
                )
        except subprocess.TimeoutExpired:
            raise DockerNotFoundError("Docker daemon is not responding.")
        except FileNotFoundError:
            raise DockerNotFoundError("Docker executable not found.")

        self._docker_path = docker_path
        return docker_path

    def _get_container_name(self, sandbox_name: str) -> str:
        """Get Docker container name for a sandbox."""
        return f"{self.CONTAINER_PREFIX}{sandbox_name}"

    def _get_metadata_path(self, sandbox_name: str) -> Path:
        """Get path to sandbox metadata file."""
        return self.data_dir / f"{sandbox_name}.json"

    def _save_metadata(self, info: SandboxInfo) -> None:
        """Save sandbox metadata to disk."""
        metadata_path = self._get_metadata_path(info.name)
        with open(metadata_path, "w") as f:
            json.dump(info.to_dict(), f, indent=2)

    def _load_metadata(self, sandbox_name: str) -> SandboxInfo | None:
        """Load sandbox metadata from disk."""
        metadata_path = self._get_metadata_path(sandbox_name)
        if not metadata_path.exists():
            return None
        try:
            with open(metadata_path) as f:
                return SandboxInfo.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load sandbox metadata: {e}")
            return None

    def _delete_metadata(self, sandbox_name: str) -> None:
        """Delete sandbox metadata from disk."""
        metadata_path = self._get_metadata_path(sandbox_name)
        if metadata_path.exists():
            metadata_path.unlink()

    def _run_docker(
        self,
        args: list[str],
        timeout: int = 60,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Run a docker command.

        Args:
            args: Arguments to pass to docker (without 'docker' prefix)
            timeout: Command timeout in seconds
            check: Whether to raise on non-zero exit

        Returns:
            CompletedProcess result
        """
        docker_path = self.require_docker()
        cmd = [docker_path] + args

        logger.debug(f"Running: {' '.join(cmd)}")

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )

    def create(
        self,
        name: str,
        image: str | None = None,
    ) -> SandboxExecutionResult:
        """
        Create a new sandbox environment.

        Args:
            name: Unique name for the sandbox
            image: Docker image to use (default: ubuntu:22.04)

        Returns:
            SandboxExecutionResult with success status and message

        Raises:
            SandboxAlreadyExistsError: If sandbox with name already exists
            DockerNotFoundError: If Docker is not available
        """
        self.require_docker()

        # Check if sandbox already exists
        existing = self._load_metadata(name)
        if existing:
            raise SandboxAlreadyExistsError(f"Sandbox '{name}' already exists")

        container_name = self._get_container_name(name)
        image = image or self.default_image

        try:
            # Pull image if needed
            logger.info(f"Pulling image {image}...")
            self._run_docker(["pull", image], timeout=300, check=False)

            # Create and start container
            logger.info(f"Creating container {container_name}...")
            result = self._run_docker(
                [
                    "run",
                    "-d",  # Detached mode
                    "--name",
                    container_name,
                    "--hostname",
                    f"sandbox-{name}",
                    image,
                    "tail",
                    "-f",
                    "/dev/null",  # Keep container running
                ],
                timeout=60,
            )

            container_id = result.stdout.strip()[:12]

            # Update apt cache in container
            logger.info("Updating package cache...")
            self._run_docker(
                ["exec", container_name, "apt-get", "update", "-qq"],
                timeout=120,
                check=False,
            )

            # Save metadata
            info = SandboxInfo(
                name=name,
                container_id=container_id,
                state=SandboxState.RUNNING,
                created_at=datetime.now().isoformat(),
                image=image,
                packages=[],
            )
            self._save_metadata(info)

            return SandboxExecutionResult(
                success=True,
                message=f"Sandbox '{name}' created successfully",
                stdout=f"Container ID: {container_id}",
            )

        except subprocess.CalledProcessError as e:
            return SandboxExecutionResult(
                success=False,
                message=f"Failed to create sandbox: {e.stderr}",
                exit_code=e.returncode,
                stderr=e.stderr,
            )
        except subprocess.TimeoutExpired:
            return SandboxExecutionResult(
                success=False,
                message="Timeout while creating sandbox",
                exit_code=1,
            )

    def install(
        self,
        name: str,
        package: str,
        options: list[str] | None = None,
    ) -> SandboxExecutionResult:
        """
        Install a package in the sandbox environment.

        Args:
            name: Sandbox name
            package: Package to install (e.g., "nginx", "docker.io")
            options: Additional apt options

        Returns:
            SandboxExecutionResult with installation status
        """
        self.require_docker()

        # Load sandbox metadata
        info = self._load_metadata(name)
        if not info:
            raise SandboxNotFoundError(f"Sandbox '{name}' not found")

        container_name = self._get_container_name(name)
        options = options or []

        try:
            # Install package
            apt_cmd = ["apt-get", "install", "-y", "-qq"] + options + [package]

            result = self._run_docker(
                ["exec", container_name] + apt_cmd,
                timeout=300,
                check=False,
            )

            if result.returncode == 0:
                # Update metadata with installed package
                if package not in info.packages:
                    info.packages.append(package)
                    self._save_metadata(info)

                return SandboxExecutionResult(
                    success=True,
                    message=f"Package '{package}' installed in sandbox '{name}'",
                    stdout=result.stdout,
                    packages_installed=[package],
                )
            else:
                return SandboxExecutionResult(
                    success=False,
                    message=f"Failed to install '{package}': {result.stderr}",
                    exit_code=result.returncode,
                    stderr=result.stderr,
                )

        except subprocess.TimeoutExpired:
            return SandboxExecutionResult(
                success=False,
                message=f"Timeout while installing '{package}'",
                exit_code=1,
            )

    def test(
        self,
        name: str,
        package: str | None = None,
    ) -> SandboxExecutionResult:
        """
        Run tests in the sandbox environment.

        Tests include:
        - Package functionality (--version, --help)
        - Binary existence (which)
        - No conflicts detected

        Args:
            name: Sandbox name
            package: Specific package to test (if None, tests all installed)

        Returns:
            SandboxExecutionResult with test results
        """
        self.require_docker()

        info = self._load_metadata(name)
        if not info:
            raise SandboxNotFoundError(f"Sandbox '{name}' not found")

        container_name = self._get_container_name(name)
        packages_to_test = [package] if package else info.packages

        if not packages_to_test:
            return SandboxExecutionResult(
                success=True,
                message="No packages to test",
                test_results=[],
            )

        test_results: list[SandboxTestResult] = []
        all_passed = True

        for pkg in packages_to_test:
            # Test 1: Check if package binary exists
            start_time = time.time()
            try:
                result = self._run_docker(
                    ["exec", container_name, "which", pkg],
                    timeout=10,
                    check=False,
                )
                binary_exists = result.returncode == 0
                binary_path = result.stdout.strip() if binary_exists else None
            except subprocess.TimeoutExpired:
                binary_exists = False
                binary_path = None

            if binary_exists:
                test_results.append(
                    SandboxTestResult(
                        name=f"{pkg}: binary exists",
                        result=SandboxTestStatus.PASSED,
                        message=f"Found at {binary_path}",
                        duration=time.time() - start_time,
                    )
                )
            else:
                # Binary might have different name - check if package is installed
                result = self._run_docker(
                    ["exec", container_name, "dpkg", "-s", pkg],
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    test_results.append(
                        SandboxTestResult(
                            name=f"{pkg}: package installed",
                            result=SandboxTestStatus.PASSED,
                            message="Package is installed (binary may have different name)",
                            duration=time.time() - start_time,
                        )
                    )
                else:
                    test_results.append(
                        SandboxTestResult(
                            name=f"{pkg}: package check",
                            result=SandboxTestStatus.FAILED,
                            message="Package not found",
                            duration=time.time() - start_time,
                        )
                    )
                    all_passed = False

            # Test 2: Try --version or --help
            start_time = time.time()
            version_checked = False

            for version_flag in ["--version", "-v", "--help"]:
                try:
                    result = self._run_docker(
                        ["exec", container_name, pkg, version_flag],
                        timeout=10,
                        check=False,
                    )
                    if result.returncode == 0:
                        test_results.append(
                            SandboxTestResult(
                                name=f"{pkg}: functional ({version_flag})",
                                result=SandboxTestStatus.PASSED,
                                message=result.stdout[:100].strip(),
                                duration=time.time() - start_time,
                            )
                        )
                        version_checked = True
                        break
                except subprocess.TimeoutExpired:
                    continue

            if not version_checked and binary_exists:
                test_results.append(
                    SandboxTestResult(
                        name=f"{pkg}: functional check",
                        result=SandboxTestStatus.SKIPPED,
                        message="Could not verify with --version/--help",
                        duration=time.time() - start_time,
                    )
                )

            # Test 3: Check for conflicts (dpkg errors)
            start_time = time.time()
            result = self._run_docker(
                ["exec", container_name, "dpkg", "--audit"],
                timeout=30,
                check=False,
            )
            if result.returncode == 0 and not result.stdout.strip():
                test_results.append(
                    SandboxTestResult(
                        name=f"{pkg}: no conflicts",
                        result=SandboxTestStatus.PASSED,
                        message="No package conflicts detected",
                        duration=time.time() - start_time,
                    )
                )
            elif result.stdout.strip():
                test_results.append(
                    SandboxTestResult(
                        name=f"{pkg}: conflict check",
                        result=SandboxTestStatus.FAILED,
                        message=result.stdout[:200],
                        duration=time.time() - start_time,
                    )
                )
                all_passed = False

        return SandboxExecutionResult(
            success=all_passed,
            message="All tests passed" if all_passed else "Some tests failed",
            test_results=test_results,
        )

    def promote(
        self,
        name: str,
        package: str,
        dry_run: bool = False,
    ) -> SandboxExecutionResult:
        """
        Promote a tested package to the main system.

        This performs a fresh install on the host system (NOT container export).
        The sandbox is only used for validation.

        Args:
            name: Sandbox name (for validation)
            package: Package to install on host
            dry_run: If True, show command without executing

        Returns:
            SandboxExecutionResult with promotion status
        """
        # Verify sandbox exists and package was tested
        info = self._load_metadata(name)
        if not info:
            raise SandboxNotFoundError(f"Sandbox '{name}' not found")

        if package not in info.packages:
            return SandboxExecutionResult(
                success=False,
                message=f"Package '{package}' was not installed in sandbox '{name}'",
                exit_code=1,
            )

        # Build the host install command
        install_cmd = ["sudo", "apt-get", "install", "-y", package]

        if dry_run:
            return SandboxExecutionResult(
                success=True,
                message=f"Would run: {' '.join(install_cmd)}",
                stdout=f"Command: {' '.join(install_cmd)}",
            )

        try:
            # Ensure host package lists are fresh before installing
            update_cmd = ["sudo", "apt-get", "update", "-qq"]
            try:
                subprocess.run(
                    update_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                # If update times out, continue to attempt install but surface warning
                logger.warning("Host apt-get update timed out before promote/install")

            # Run apt install on the HOST (not in container)
            result = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                return SandboxExecutionResult(
                    success=True,
                    message=f"Package '{package}' installed on main system",
                    stdout=result.stdout,
                    packages_installed=[package],
                )
            else:
                # Provide a helpful hint when package cannot be located
                hint = ""
                combined_output = (result.stderr or "") + "\n" + (result.stdout or "")
                if "Unable to locate package" in combined_output:
                    hint = (
                        "\nHint: run 'sudo apt-get update' on the host and retry, "
                        "or check your APT sources/repositories."
                    )

                return SandboxExecutionResult(
                    success=False,
                    message=f"Failed to install '{package}' on main system{hint}",
                    exit_code=result.returncode,
                    stderr=result.stderr,
                )

        except subprocess.TimeoutExpired:
            return SandboxExecutionResult(
                success=False,
                message="Timeout while installing on main system",
                exit_code=1,
            )

    def cleanup(self, name: str, force: bool = False) -> SandboxExecutionResult:
        """
        Remove a sandbox environment.

        Args:
            name: Sandbox name to remove
            force: Force removal even if running

        Returns:
            SandboxExecutionResult with cleanup status
        """
        self.require_docker()

        container_name = self._get_container_name(name)

        # If metadata is missing, only allow cleanup when forced; otherwise report not found
        info = self._load_metadata(name)
        if not info and not force:
            return SandboxExecutionResult(
                success=False,
                message=f"Sandbox '{name}' not found",
                exit_code=1,
            )

        try:
            # Stop container if running (ignore errors)
            self._run_docker(["stop", container_name], timeout=30, check=False)

            # Remove container
            rm_args = ["rm"]
            if force:
                rm_args.append("-f")
            rm_args.append(container_name)

            self._run_docker(rm_args, timeout=30, check=False)

            # Delete metadata (if exists)
            self._delete_metadata(name)

            return SandboxExecutionResult(
                success=True,
                message=f"Sandbox '{name}' removed",
            )

        except subprocess.TimeoutExpired:
            return SandboxExecutionResult(
                success=False,
                message="Timeout while removing sandbox",
                exit_code=1,
            )

    def list_sandboxes(self) -> list[SandboxInfo]:
        """
        List all sandbox environments.

        Returns:
            List of SandboxInfo objects
        """
        sandboxes = []

        for metadata_file in self.data_dir.glob("*.json"):
            try:
                with open(metadata_file) as f:
                    data = json.load(f)
                    sandboxes.append(SandboxInfo.from_dict(data))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load {metadata_file}: {e}")

        return sandboxes

    def get_sandbox(self, name: str) -> SandboxInfo | None:
        """
        Get information about a specific sandbox.

        Args:
            name: Sandbox name

        Returns:
            SandboxInfo or None if not found
        """
        return self._load_metadata(name)

    def exec_command(
        self,
        name: str,
        command: list[str],
        timeout: int = 60,
    ) -> SandboxExecutionResult:
        """
        Execute an arbitrary command in the sandbox.

        Args:
            name: Sandbox name
            command: Command and arguments to execute
            timeout: Command timeout in seconds

        Returns:
            SandboxExecutionResult with command output
        """
        self.require_docker()

        info = self._load_metadata(name)
        if not info:
            raise SandboxNotFoundError(f"Sandbox '{name}' not found")

        # Check for blocked commands
        if command and command[0] in self.SANDBOX_BLOCKED_COMMANDS:
            return SandboxExecutionResult(
                success=False,
                message=f"Command '{command[0]}' is not supported in sandbox",
                exit_code=1,
                stderr="This command requires system-level access not available in Docker",
            )

        container_name = self._get_container_name(name)

        try:
            result = self._run_docker(
                ["exec", container_name] + command,
                timeout=timeout,
                check=False,
            )

            return SandboxExecutionResult(
                success=result.returncode == 0,
                message="Command executed" if result.returncode == 0 else "Command failed",
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        except subprocess.TimeoutExpired:
            return SandboxExecutionResult(
                success=False,
                message="Command timed out",
                exit_code=1,
            )

    @classmethod
    def is_sandbox_compatible(cls, command: str) -> tuple[bool, str]:
        """
        Check if a command is compatible with sandbox execution.

        Used by LLM command generator to filter incompatible commands.

        Args:
            command: Command to check

        Returns:
            Tuple of (is_compatible, reason)
        """
        # Extract base command
        parts = command.split()
        if not parts:
            return True, ""

        base_cmd = parts[0]

        # Check against blocked commands
        if base_cmd in cls.SANDBOX_BLOCKED_COMMANDS:
            return False, f"'{base_cmd}' requires system-level access not available in Docker"

        # Check for sudo with blocked commands
        if base_cmd == "sudo" and len(parts) > 1:
            actual_cmd = parts[1]
            if actual_cmd in cls.SANDBOX_BLOCKED_COMMANDS:
                return False, f"'{actual_cmd}' requires system-level access not available in Docker"

        return True, ""


# Convenience function for checking Docker availability
def docker_available() -> bool:
    """Check if Docker is available for sandbox commands."""
    return DockerSandbox().check_docker()
