"""
Basic tests for DockerPermissionHandler.
"""

import pytest

from cortex.permissions.docker_handler import DockerPermissionHandler, detect_docker_uid_mapping


def test_docker_handler_import():
    """Test that DockerPermissionHandler can be imported"""
    assert DockerPermissionHandler is not None


def test_docker_handler_creation():
    """Test DockerPermissionHandler instantiation"""
    handler = DockerPermissionHandler()
    assert handler is not None
    assert hasattr(handler, "container_info")
    assert hasattr(handler, "verbose")
    assert hasattr(handler, "dry_run")


def test_container_info_structure():
    """Test container_info has expected structure"""
    handler = DockerPermissionHandler()
    info = handler.container_info

    assert isinstance(info, dict)
    assert "is_container" in info
    assert "container_runtime" in info
    assert "host_uid" in info
    assert "host_gid" in info
    assert "uid_mapping" in info
    assert "gid_mapping" in info

    assert isinstance(info["is_container"], bool)
    assert isinstance(info["host_uid"], int)
    assert isinstance(info["host_gid"], int)
    assert isinstance(info["uid_mapping"], dict)
    assert isinstance(info["gid_mapping"], dict)


def test_detect_docker_uid_mapping():
    """Test convenience function"""
    result = detect_docker_uid_mapping()
    assert isinstance(result, dict)
    assert "is_container" in result


def test_adjust_issue_for_container():
    """Test adjust_issue_for_container method"""
    handler = DockerPermissionHandler()

    test_issue = {"path": "/some/path", "type": "world_writable"}

    adjusted = handler.adjust_issue_for_container(test_issue)
    assert isinstance(adjusted, dict)
    assert "path" in adjusted

    # If not in container, should return same issue
    if not handler.container_info["is_container"]:
        assert adjusted == test_issue


def test_get_container_specific_fix():
    """Test get_container_specific_fix method"""
    handler = DockerPermissionHandler()

    test_issue = {"path": "/some/path", "is_directory": False}

    base_fix = {"command": "chmod 644 /some/path", "reason": "standard fix"}

    result = handler.get_container_specific_fix(test_issue, base_fix)
    assert isinstance(result, dict)
    assert "command" in result
    assert "reason" in result


def test_uid_to_name_method():
    """Test _uid_to_name method"""
    handler = DockerPermissionHandler()

    # Test with root UID (0)
    result = handler._uid_to_name(0)
    assert isinstance(result, str)

    # Test with current user UID
    import os

    current_uid = os.getuid()
    result = handler._uid_to_name(current_uid)
    assert isinstance(result, str)

    # Test with high UID (likely doesn't exist)
    result = handler._uid_to_name(99999)
    assert "UID99999" in result


def test_gid_to_name_method():
    """Test _gid_to_name method"""
    handler = DockerPermissionHandler()

    # Test with root GID (0)
    result = handler._gid_to_name(0)
    assert isinstance(result, str)

    # Test with high GID (likely doesn't exist)
    result = handler._gid_to_name(99999)
    assert "GID99999" in result


def test_generate_docker_permission_report():
    """Test generate_docker_permission_report method"""
    handler = DockerPermissionHandler()

    report = handler.generate_docker_permission_report(".")
    assert isinstance(report, str)
    assert "DOCKER PERMISSION AUDIT" in report or "Docker Permission Audit" in report


def test_fix_docker_bind_mount_permissions_dry_run(tmp_path):
    """Test fix_docker_bind_mount_permissions in dry-run mode"""
    from cortex.permissions.docker_handler import DockerPermissionHandler

    handler = DockerPermissionHandler()

    # Create test directory
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()

    result = handler.fix_docker_bind_mount_permissions(
        str(test_dir), host_uid=1000, host_gid=1000, dry_run=True
    )

    assert isinstance(result, dict)
    assert "success" in result
    assert "actions" in result
    assert "warnings" in result
    assert result["dry_run"] is True

    # Check structure
    assert "current" in result or "warnings" in result


def test_fix_docker_bind_mount_permissions_nonexistent():
    """Test fix_docker_bind_mount_permissions with non-existent path"""
    from cortex.permissions.docker_handler import DockerPermissionHandler

    handler = DockerPermissionHandler()

    result = handler.fix_docker_bind_mount_permissions(
        "/nonexistent/path/12345", host_uid=1000, host_gid=1000, dry_run=True
    )

    assert isinstance(result, dict)
    assert "warnings" in result
    assert any("does not exist" in str(w).lower() for w in result["warnings"])


def test_discover_uid_mapping():
    """Test _discover_uid_mapping method"""
    from cortex.permissions.docker_handler import DockerPermissionHandler

    handler = DockerPermissionHandler()
    mapping = handler._discover_uid_mapping()

    assert isinstance(mapping, dict)
    # At least root (0) should be in mapping
    assert 0 in mapping or len(mapping) > 0


def test_discover_gid_mapping():
    """Test _discover_gid_mapping method"""
    from cortex.permissions.docker_handler import DockerPermissionHandler

    handler = DockerPermissionHandler()
    mapping = handler._discover_gid_mapping()

    assert isinstance(mapping, dict)
    # At least root (0) should be in mapping
    assert 0 in mapping or len(mapping) > 0


def test_generate_docker_permission_report_with_path(tmp_path):
    """Test generate_docker_permission_report with custom path"""
    from cortex.permissions.docker_handler import DockerPermissionHandler

    handler = DockerPermissionHandler()
    report = handler.generate_docker_permission_report(str(tmp_path))

    assert isinstance(report, str)
    assert len(report) > 0
    assert "DOCKER" in report.upper() or "PERMISSION" in report.upper()


def test_container_info_types():
    """Test container_info has correct types"""
    from cortex.permissions.docker_handler import DockerPermissionHandler

    handler = DockerPermissionHandler(verbose=False)
    info = handler.container_info

    # Check types
    assert isinstance(info["is_container"], bool)
    assert isinstance(info["host_uid"], int)
    assert isinstance(info["host_gid"], int)
    assert isinstance(info["uid_mapping"], dict)
    assert isinstance(info["gid_mapping"], dict)
    assert isinstance(info["container_runtime"], str | None)

    # Check UID/GID are valid
    assert info["host_uid"] >= 0
    assert info["host_gid"] >= 0


def test_adjust_issue_with_stat(tmp_path):
    """Test adjust_issue_for_container with stat info"""
    import os

    from cortex.permissions.docker_handler import DockerPermissionHandler

    handler = DockerPermissionHandler()

    # Create test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")

    # Get file stat
    stat_info = os.stat(test_file)

    test_issue = {
        "path": str(test_file),
        "stat": {"uid": stat_info.st_uid, "gid": stat_info.st_gid},
    }

    adjusted = handler.adjust_issue_for_container(test_issue)
    assert isinstance(adjusted, dict)
    assert "path" in adjusted

    # If in container, should have uid_info/gid_info
    if handler.container_info["is_container"]:
        assert "uid_info" in adjusted or "gid_info" in adjusted


def test_get_container_specific_fix_with_docker_path():
    """Test get_container_specific_fix with docker path"""
    from cortex.permissions.docker_handler import DockerPermissionHandler

    handler = DockerPermissionHandler()

    test_issue = {"path": "/var/lib/docker/volumes/test", "permission": "755"}
    base_fix = {"command": "chmod 755 /var/lib/docker/volumes/test", "reason": "standard fix"}

    result = handler.get_container_specific_fix(test_issue, base_fix)

    assert "command" in result
    assert "reason" in result
    assert result["command"] == "chmod 755 /var/lib/docker/volumes/test"
    assert result["reason"] == "standard fix"
