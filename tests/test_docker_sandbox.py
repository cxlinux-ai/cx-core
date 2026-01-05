#!/usr/bin/env python3
"""
Tests for Docker-based Package Sandbox Testing Environment.

Tests cover:
- DockerSandbox class methods (create, install, test, promote, cleanup)
- Docker detection and error handling
- Edge cases and error conditions
"""

import json
import os
import shutil as shutil_module
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.sandbox.docker_sandbox import (
    DockerNotFoundError,
    DockerSandbox,
    SandboxAlreadyExistsError,
    SandboxInfo,
    SandboxNotFoundError,
    SandboxState,
    SandboxTestStatus,
    docker_available,
)


def create_sandbox_metadata(
    name: str = "test-env",
    packages: list[str] | None = None,
    state: str = "running",
) -> dict[str, Any]:
    """Create a sandbox metadata dictionary."""
    return {
        "name": name,
        "container_id": f"abc123{name}",
        "state": state,
        "created_at": "2024-01-01T00:00:00",
        "image": "ubuntu:22.04",
        "packages": packages or [],
    }


def mock_docker_available() -> tuple[str, Mock]:
    """Return mocks configured for Docker available."""
    return "/usr/bin/docker", Mock(returncode=0, stdout="Docker info", stderr="")


class SandboxTestBase(unittest.TestCase):
    """Base class for sandbox tests with common setup/teardown."""

    def setUp(self) -> None:
        """Set up temp directory for sandbox metadata."""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "sandboxes"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        shutil_module.rmtree(self.temp_dir, ignore_errors=True)

    def write_metadata(
        self,
        name: str = "test-env",
        packages: list[str] | None = None,
        state: str = "running",
    ) -> dict[str, Any]:
        """Helper to write sandbox metadata to disk."""
        metadata = create_sandbox_metadata(name, packages, state)
        with open(self.data_dir / f"{name}.json", "w") as f:
            json.dump(metadata, f)
        return metadata

    def create_sandbox_instance(self) -> DockerSandbox:
        """Create a DockerSandbox instance with test data directory."""
        return DockerSandbox(data_dir=self.data_dir)


class TestDockerDetection(unittest.TestCase):
    """Tests for Docker availability detection."""

    @patch("shutil.which")
    def test_docker_not_installed(self, mock_which: Mock) -> None:
        """Test detection when Docker is not installed."""
        mock_which.return_value = None
        self.assertFalse(DockerSandbox().check_docker())

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_docker_installed_but_not_running(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test detection when Docker is installed but daemon not running."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.side_effect = [
            Mock(returncode=0, stdout="Docker version 24.0.0"),
            Mock(returncode=1, stderr="Cannot connect to Docker daemon"),
        ]
        self.assertFalse(DockerSandbox().check_docker())

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_docker_available(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test detection when Docker is fully available."""
        mock_which.return_value, mock_run.return_value = mock_docker_available()
        self.assertTrue(DockerSandbox().check_docker())

    @patch("shutil.which")
    def test_require_docker_raises_when_not_found(self, mock_which: Mock) -> None:
        """Test require_docker raises DockerNotFoundError when not installed."""
        mock_which.return_value = None
        with self.assertRaises(DockerNotFoundError) as ctx:
            DockerSandbox().require_docker()
        self.assertIn("Docker is required", str(ctx.exception))

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_require_docker_raises_when_daemon_not_running(
        self, mock_run: Mock, mock_which: Mock
    ) -> None:
        """Test require_docker raises when daemon not running."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(returncode=1, stderr="Cannot connect")
        with self.assertRaises(DockerNotFoundError) as ctx:
            DockerSandbox().require_docker()
        self.assertIn("not running", str(ctx.exception))


class TestSandboxCreate(SandboxTestBase):
    """Tests for sandbox creation."""

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_create_sandbox_success(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test successful sandbox creation."""
        mock_which.return_value, _ = mock_docker_available()
        mock_run.return_value = Mock(returncode=0, stdout="abc123def456", stderr="")

        result = self.create_sandbox_instance().create("test-env")

        self.assertTrue(result.success)
        self.assertIn("test-env", result.message)
        self.assertTrue((self.data_dir / "test-env.json").exists())

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_create_sandbox_already_exists(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test error when sandbox already exists."""
        mock_which.return_value, mock_run.return_value = mock_docker_available()

        sandbox = self.create_sandbox_instance()
        sandbox.create("test-env")

        with self.assertRaises(SandboxAlreadyExistsError):
            sandbox.create("test-env")

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_create_sandbox_with_custom_image(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test sandbox creation with custom image."""
        mock_which.return_value, mock_run.return_value = mock_docker_available()

        sandbox = self.create_sandbox_instance()
        sandbox.create("test-env", image="debian:12")

        self.assertEqual(sandbox.get_sandbox("test-env").image, "debian:12")


class TestSandboxInstall(SandboxTestBase):
    """Tests for package installation in sandbox."""

    def setUp(self) -> None:
        super().setUp()
        self.write_metadata("test-env", packages=[])

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_install_package_success(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test successful package installation."""
        mock_which.return_value, mock_run.return_value = mock_docker_available()

        result = self.create_sandbox_instance().install("test-env", "nginx")

        self.assertTrue(result.success)
        self.assertIn("nginx", result.packages_installed)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_install_package_failure(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test package installation failure."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.side_effect = [
            Mock(returncode=0, stdout="Docker info", stderr=""),
            Mock(returncode=100, stdout="", stderr="E: Unable to locate package"),
        ]

        result = self.create_sandbox_instance().install("test-env", "nonexistent")

        self.assertFalse(result.success)
        self.assertIn("Failed to install", result.message)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_install_sandbox_not_found(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test installation in non-existent sandbox."""
        mock_which.return_value, mock_run.return_value = mock_docker_available()

        with self.assertRaises(SandboxNotFoundError):
            self.create_sandbox_instance().install("nonexistent", "nginx")


class TestSandboxTest(SandboxTestBase):
    """Tests for sandbox testing functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.write_metadata("test-env", packages=["nginx"])

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_test_all_pass(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test when all tests pass."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.side_effect = [
            Mock(returncode=0, stdout="/usr/bin/docker"),
            Mock(returncode=0, stdout="/usr/sbin/nginx"),
            Mock(returncode=0, stdout="nginx version: 1.18"),
            Mock(returncode=0, stdout=""),
        ]

        result = self.create_sandbox_instance().test("test-env")

        self.assertTrue(result.success)
        passed = [t for t in result.test_results if t.result == SandboxTestStatus.PASSED]
        self.assertTrue(len(passed) > 0)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_test_no_packages(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test when no packages installed."""
        mock_which.return_value, mock_run.return_value = mock_docker_available()
        self.write_metadata("empty-env", packages=[])

        result = self.create_sandbox_instance().test("empty-env")

        self.assertTrue(result.success)
        self.assertEqual(len(result.test_results), 0)


# =============================================================================
# Sandbox Promote Tests
# =============================================================================


class TestSandboxPromote(SandboxTestBase):
    """Tests for package promotion to main system."""

    def setUp(self) -> None:
        super().setUp()
        self.write_metadata("test-env", packages=["nginx"])

    @patch("subprocess.run")
    def test_promote_dry_run(self, mock_run: Mock) -> None:
        """Test promotion in dry-run mode."""
        result = self.create_sandbox_instance().promote("test-env", "nginx", dry_run=True)

        self.assertTrue(result.success)
        self.assertIn("Would run", result.message)

    def test_promote_package_not_in_sandbox(self) -> None:
        """Test promotion of package not installed in sandbox."""
        result = self.create_sandbox_instance().promote("test-env", "redis", dry_run=False)

        self.assertFalse(result.success)
        self.assertIn("not installed in sandbox", result.message)

    @patch("subprocess.run")
    def test_promote_success(self, mock_run: Mock) -> None:
        """Test successful promotion."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        result = self.create_sandbox_instance().promote("test-env", "nginx", dry_run=False)

        self.assertTrue(result.success)
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args, ["sudo", "apt-get", "install", "-y", "nginx"])


class TestSandboxCleanup(SandboxTestBase):
    """Tests for sandbox cleanup."""

    def setUp(self) -> None:
        super().setUp()
        self.write_metadata("test-env")

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_cleanup_success(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test successful cleanup."""
        mock_which.return_value, mock_run.return_value = mock_docker_available()

        result = self.create_sandbox_instance().cleanup("test-env")

        self.assertTrue(result.success)
        self.assertFalse((self.data_dir / "test-env.json").exists())

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_cleanup_force(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test force cleanup."""
        mock_which.return_value, mock_run.return_value = mock_docker_available()

        result = self.create_sandbox_instance().cleanup("test-env", force=True)

        self.assertTrue(result.success)


class TestSandboxList(SandboxTestBase):
    """Tests for listing sandboxes."""

    def test_list_empty(self) -> None:
        """Test listing when no sandboxes exist."""
        self.assertEqual(len(self.create_sandbox_instance().list_sandboxes()), 0)

    def test_list_multiple(self) -> None:
        """Test listing multiple sandboxes."""
        for name in ["env1", "env2", "env3"]:
            self.write_metadata(name)

        sandboxes = self.create_sandbox_instance().list_sandboxes()

        self.assertEqual(len(sandboxes), 3)
        self.assertEqual({s.name for s in sandboxes}, {"env1", "env2", "env3"})


class TestSandboxExec(SandboxTestBase):
    """Tests for command execution in sandbox."""

    def setUp(self) -> None:
        super().setUp()
        self.write_metadata("test-env")

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_exec_success(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test successful command execution."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(returncode=0, stdout="Hello\n", stderr="")

        result = self.create_sandbox_instance().exec_command("test-env", ["echo", "Hello"])

        self.assertTrue(result.success)
        self.assertIn("Hello", result.stdout)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_exec_blocked_command(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test blocked command is rejected."""
        mock_which.return_value, mock_run.return_value = mock_docker_available()

        result = self.create_sandbox_instance().exec_command(
            "test-env", ["systemctl", "start", "nginx"]
        )

        self.assertFalse(result.success)
        self.assertIn("not supported", result.message)


class TestSandboxCompatibility(unittest.TestCase):
    """Tests for command compatibility checking."""

    def test_allowed_commands(self) -> None:
        """Test that normal commands are allowed."""
        self.assertTrue(DockerSandbox.is_sandbox_compatible("apt install nginx")[0])
        self.assertTrue(DockerSandbox.is_sandbox_compatible("nginx --version")[0])

    def test_blocked_commands(self) -> None:
        """Test that blocked commands are rejected."""
        is_compat, reason = DockerSandbox.is_sandbox_compatible("systemctl start nginx")
        self.assertFalse(is_compat)
        self.assertIn("systemctl", reason)

        self.assertFalse(DockerSandbox.is_sandbox_compatible("sudo service nginx restart")[0])
        self.assertFalse(DockerSandbox.is_sandbox_compatible("modprobe loop")[0])


class TestSandboxInfo(unittest.TestCase):
    """Tests for SandboxInfo data class."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        info = SandboxInfo(
            name="test",
            container_id="abc123",
            state=SandboxState.RUNNING,
            created_at="2024-01-01T00:00:00",
            image="ubuntu:22.04",
            packages=["nginx", "redis"],
        )
        data = info.to_dict()

        self.assertEqual(data["name"], "test")
        self.assertEqual(data["state"], "running")
        self.assertEqual(data["packages"], ["nginx", "redis"])

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        info = SandboxInfo.from_dict(create_sandbox_metadata("test", ["nginx"]))

        self.assertEqual(info.name, "test")
        self.assertEqual(info.state, SandboxState.RUNNING)
        self.assertIn("nginx", info.packages)


class TestDockerAvailableFunction(unittest.TestCase):
    """Tests for docker_available() convenience function."""

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_docker_available_true(self, mock_run: Mock, mock_which: Mock) -> None:
        """Test when Docker is available."""
        mock_which.return_value, mock_run.return_value = mock_docker_available()
        self.assertTrue(docker_available())

    @patch("shutil.which")
    def test_docker_available_false(self, mock_which: Mock) -> None:
        """Test when Docker is not available."""
        mock_which.return_value = None
        self.assertFalse(docker_available())


if __name__ == "__main__":
    unittest.main()
