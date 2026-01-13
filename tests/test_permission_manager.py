import os
import platform
from unittest.mock import MagicMock, patch

import pytest

from cortex.permission_manager import PermissionManager


@pytest.fixture
def manager():
    """Create a permission manager instance simulating a Linux environment.

    This prevents the NotImplementedError from being raised during object creation.
    """
    with (
        patch("os.getuid", create=True, return_value=1000),
        patch("os.getgid", create=True, return_value=1000),
        patch("platform.system", return_value="Linux"),
    ):
        return PermissionManager(os.path.normpath("/dummy/path"))


def test_init_native_windows_raises_error():
    """Verify that PermissionManager blocks execution on native Windows."""
    mock_uname = MagicMock()
    mock_uname.release = "10.0.22631"  # Standard Windows release, no 'microsoft'

    with (
        patch("platform.system", return_value="Windows"),
        patch("platform.uname", return_value=mock_uname),
    ):
        with pytest.raises(NotImplementedError) as excinfo:
            PermissionManager("/any/path")
        assert "requires a Linux environment or WSL" in str(excinfo.value)


def test_init_wsl_detection():
    """Verify that the manager correctly detects WSL on Windows host."""
    mock_uname = MagicMock()
    mock_uname.release = "5.15.133.1-microsoft-standard-WSL2"

    with (
        patch("platform.system", return_value="Windows"),
        patch("platform.uname", return_value=mock_uname),
        patch("os.getuid", create=True, return_value=1001),
        patch("os.getgid", create=True, return_value=1001),
    ):
        manager = PermissionManager("/any/path")
        # Should successfully instantiate and use real IDs in WSL
        assert manager.host_uid == 1001
        assert manager.host_gid == 1001


def test_diagnose_finds_mismatched_uids(manager):
    """Confirm the tool identifies files not owned by the host (UID 1000)."""
    with (
        patch("cortex.permission_manager.os.walk") as mock_walk,
        patch("cortex.permission_manager.os.stat") as mock_stat,
    ):
        base = os.path.normpath("/dummy/path")
        # File 1: Owned by root (0) - Should be flagged
        # File 2: Owned by host (1000) - Should be ignored
        mock_walk.return_value = [(base, [], ["root_file.txt", "user_file.txt"])]

        root_stat = MagicMock()
        root_stat.st_uid = 0

        user_stat = MagicMock()
        user_stat.st_uid = 1000

        mock_stat.side_effect = [root_stat, user_stat]

        results = manager.diagnose()

        assert len(results) == 1
        assert os.path.join(base, "root_file.txt") in results


def test_check_compose_config_with_valid_yaml(manager):
    """Confirm YAML parsing correctly identifies existing user mappings."""
    dummy_yaml = {
        "services": {"db": {"image": "postgres", "user": "1000:1000"}, "web": {"image": "nginx"}}
    }

    with (
        patch("cortex.permission_manager.os.path.exists", return_value=True),
        patch("yaml.safe_load", return_value=dummy_yaml),
        patch("builtins.open", MagicMock()),
        patch("cortex.permission_manager.console.print") as mock_console,
    ):
        manager.check_compose_config()
        # Should NOT print recommendation because one service already has a user mapping
        mock_console.assert_not_called()


def test_check_compose_config_recommends_settings(manager):
    """Confirm recommendation is printed when no services have user mappings."""
    dummy_yaml = {"services": {"web": {"image": "nginx"}}}

    with (
        patch("cortex.permission_manager.os.path.exists", return_value=True),
        patch("yaml.safe_load", return_value=dummy_yaml),
        patch("builtins.open", MagicMock()),
        patch("cortex.permission_manager.console.print") as mock_console,
    ):
        manager.check_compose_config()
        mock_console.assert_called()

        combined_output = "".join([str(call.args[0]) for call in mock_console.call_args_list])
        assert "user:" in combined_output
        assert "1000:1000" in combined_output


@patch("cortex.permission_manager.subprocess.run")
@patch("cortex.permission_manager.platform.system", return_value="Linux")
def test_fix_permissions_uses_batching(mock_platform, mock_run, manager, mocker):
    """Confirm the repair command uses batching to avoid ARG_MAX issues."""
    # Simulate 250 files to trigger 3 batches (100, 100, 50)
    test_files = [f"/path/file_{i}.txt" for i in range(250)]
    mocker.patch.object(manager, "diagnose", return_value=test_files)

    success = manager.fix_permissions(execute=True)

    assert success is True
    # Verify subprocess.run was called 3 times due to BATCH_SIZE=100
    assert mock_run.call_count == 3

    # Verify the first batch call structure
    # Args are: ["sudo", "chown", "1000:1000"] + 100 files
    first_call_args = mock_run.call_args_list[0][0][0]
    assert first_call_args[0:3] == ["sudo", "chown", "1000:1000"]
    assert len(first_call_args) == 103
