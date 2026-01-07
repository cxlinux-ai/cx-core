"""
Tests for Permission Auditor & Fixer module.
"""

import os
import stat
import tempfile
from pathlib import Path

import pytest

from cortex.permissions import PermissionAuditor, PermissionManager


class TestPermissionAuditorBasic:
    """Basic functionality tests for PermissionAuditor"""

    def test_auditor_creation(self):
        """Test that PermissionAuditor can be instantiated"""
        auditor = PermissionAuditor()
        assert auditor is not None
        assert hasattr(auditor, "scan_directory")
        assert hasattr(auditor, "suggest_fix")

    def test_scan_directory_returns_dict(self, tmp_path):
        """Test that scan_directory returns proper dictionary structure"""
        auditor = PermissionAuditor()
        result = auditor.scan_directory(tmp_path)

        assert isinstance(result, dict)
        expected_keys = ["world_writable", "dangerous", "suggestions"]
        for key in expected_keys:
            assert key in result, f"Missing key '{key}' in result"
            assert isinstance(result[key], list), f"Key '{key}' should be a list"

    def test_detect_world_writable_file(self, tmp_path):
        """Test detection of world-writable files (777 permissions)"""
        unsafe_file = tmp_path / "test_777.txt"
        unsafe_file.write_text("dangerous content")
        unsafe_file.chmod(0o777)

        auditor = PermissionAuditor()
        result = auditor.scan_directory(tmp_path)

        assert len(result["world_writable"]) > 0

        found_files = [str(p) for p in result["world_writable"]]
        assert str(unsafe_file) in found_files

    def test_ignore_safe_permissions(self, tmp_path):
        """Test that files with safe permissions are not flagged"""
        safe_file = tmp_path / "safe_644.txt"
        safe_file.write_text("safe content")
        safe_file.chmod(0o644)

        auditor = PermissionAuditor()
        result = auditor.scan_directory(tmp_path)

        assert str(safe_file) not in result["world_writable"]

    def test_suggest_fix_method(self, tmp_path):
        """Test that suggest_fix method works"""
        auditor = PermissionAuditor()

        assert hasattr(auditor, "suggest_fix")

        test_file = tmp_path / "test_suggest.txt"
        test_file.write_text("test")
        test_file.chmod(0o777)

        suggestion = auditor.suggest_fix(str(test_file), "777")
        assert isinstance(suggestion, str)
        assert "chmod" in suggestion


class TestDockerHandler:
    """Tests for DockerPermissionHandler"""

    def test_docker_handler_creation(self):
        """Test DockerPermissionHandler can be instantiated"""
        from cortex.permissions.docker_handler import DockerPermissionHandler

        handler = DockerPermissionHandler()
        assert handler is not None
        assert hasattr(handler, "container_info")

    def test_detect_container_environment(self):
        """Test container detection"""
        from cortex.permissions.docker_handler import DockerPermissionHandler

        handler = DockerPermissionHandler(verbose=False)
        info = handler.container_info

        assert "is_container" in info
        assert "host_uid" in info
        assert "host_gid" in info
        assert isinstance(info["is_container"], bool)

    def test_uid_to_name_conversion(self):
        """Test UID to name conversion (simplified)"""
        from cortex.permissions.docker_handler import DockerPermissionHandler

        handler = DockerPermissionHandler()

        # Test with known UID 0 (root)
        result = handler._uid_to_name(0)
        assert "root" in result or "UID0" in result

        # Test with high UID (likely doesn't exist)
        result = handler._uid_to_name(99999)
        assert "UID99999" in result


def test_auditor_with_verbose():
    """Test auditor with verbose mode"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor(verbose=True)
    assert auditor.verbose is True
    assert auditor.dry_run is True  # default


def test_auditor_with_custom_dry_run():
    """Test auditor with custom dry_run setting"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor(dry_run=False)
    assert auditor.dry_run is False


def test_scan_directory_nonexistent():
    """Test scanning non-existent directory"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()
    result = auditor.scan_directory("/nonexistent/path/12345")

    assert isinstance(result, dict)
    assert result["world_writable"] == []
    assert result["dangerous"] == []
    assert result["suggestions"] == []


def test_scan_directory_file_instead_of_dir(tmp_path):
    """Test scanning a file instead of directory"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")

    result = auditor.scan_directory(test_file)

    assert isinstance(result, dict)
    assert result["world_writable"] == []
    assert result["dangerous"] == []
    assert result["suggestions"] == []


def test_suggest_fix_nonexistent_file():
    """Test suggest_fix for non-existent file"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()
    suggestion = auditor.suggest_fix("/nonexistent/file.txt")

    assert "doesn't exist" in suggestion
    assert "# File" in suggestion


def test_fix_permissions_nonexistent():
    """Test fix_permissions for non-existent file"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()
    result = auditor.fix_permissions("/nonexistent/file.txt", "644")

    assert "does not exist" in result
    assert "File" in result


def test_scan_and_fix_with_dry_run_override(tmp_path):
    """Test scan_and_fix with dry_run parameter override"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    # Create auditor with dry_run=True by default
    auditor = PermissionAuditor(dry_run=True)

    # Test with explicit dry_run=False (should override)
    result = auditor.scan_and_fix(str(tmp_path), apply_fixes=False, dry_run=False)
    assert "issues_found" in result

    # Test with explicit dry_run=True
    result = auditor.scan_and_fix(str(tmp_path), apply_fixes=False, dry_run=True)
    assert "issues_found" in result

    # Test with None (should use instance default)
    result = auditor.scan_and_fix(str(tmp_path), apply_fixes=False, dry_run=None)
    assert "issues_found" in result


def test_fix_permissions_dry_run(tmp_path):
    """Test fix_permissions in dry-run mode"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()
    test_file = tmp_path / "test_fix.txt"
    test_file.write_text("test")
    test_file.chmod(0o777)

    result = auditor.fix_permissions(test_file, "644", dry_run=True)
    assert "[DRY RUN]" in result
    assert "777" in result or "644" in result


def test_fix_permissions_actual(tmp_path):
    """Test actual permission fixing"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()
    test_file = tmp_path / "test_fix_actual.txt"
    test_file.write_text("test")
    test_file.chmod(0o777)

    result = auditor.fix_permissions(test_file, "644", dry_run=False)
    assert "Changed" in result
    assert "644" in result

    # Verify permissions actually changed

    mode = test_file.stat().st_mode & 0o777
    assert oct(mode) != "0o777"


def test_scan_and_fix_report(tmp_path):
    """Test scan_and_fix generates proper report"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()

    # Create files with different permissions
    safe_file = tmp_path / "safe.txt"
    safe_file.write_text("safe")
    safe_file.chmod(0o644)

    unsafe_file = tmp_path / "unsafe.txt"
    unsafe_file.write_text("unsafe")
    unsafe_file.chmod(0o777)

    result = auditor.scan_and_fix(str(tmp_path), apply_fixes=False, dry_run=True)

    assert "report" in result
    assert "issues_found" in result
    assert result["issues_found"] >= 1
    assert "PERMISSION AUDIT REPORT" in result["report"]


def test_suggest_fix_for_executable(tmp_path):
    """Test suggest_fix for executable files"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()

    # Create executable script
    script = tmp_path / "script.sh"
    script.write_text("#!/bin/bash\necho hello")
    script.chmod(0o777)

    suggestion = auditor.suggest_fix(script, "777")
    assert "chmod" in suggestion
    assert "755" in suggestion  # Should suggest 755 for executables


def test_suggest_fix_for_data_file(tmp_path):
    """Test suggest_fix for data files"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()

    # Create data file WITHOUT execute bit
    data_file = tmp_path / "data.txt"
    data_file.write_text("data content")
    # Set 666 instead of 777 to avoid execute bit
    data_file.chmod(0o666)

    suggestion = auditor.suggest_fix(data_file, "666")
    assert "chmod" in suggestion
    # File without execute bit should get 644
    assert "644" in suggestion  # Should suggest 644 for non-executable files


def test_config_module():
    """Test that config module can be imported"""
    from cortex.permissions import config

    assert hasattr(config, "DANGEROUS_PERMISSIONS")
    assert hasattr(config, "RECOMMENDED_PERMISSIONS")
    assert isinstance(config.DANGEROUS_PERMISSIONS, dict)
    assert isinstance(config.RECOMMENDED_PERMISSIONS, dict)


def test_docker_handler_module():
    """Test docker_handler module imports"""
    from cortex.permissions.docker_handler import DockerPermissionHandler, detect_docker_uid_mapping

    assert callable(detect_docker_uid_mapping)


def test_cli_integration():
    """Test that CLI can import and use PermissionManager"""

    manager = PermissionManager(verbose=False)
    assert manager is not None

    # Basic functionality check
    assert hasattr(manager, "scan_directory")
    assert hasattr(manager, "suggest_fix")
    assert hasattr(manager, "scan_and_fix")


def test_permission_fixer_alias():
    """Test PermissionFixer alias"""
    from cortex.permissions import PermissionFixer

    fixer = PermissionFixer()
    assert fixer is not None
    assert hasattr(fixer, "scan_directory")


def test_scan_path_function():
    """Test scan_path compatibility function"""
    from cortex.permissions import scan_path

    result = scan_path(".")
    assert isinstance(result, dict)
    assert "world_writable" in result
    assert "dangerous" in result
    assert "suggestions" in result


def test_analyze_permissions_function():
    """Test analyze_permissions compatibility function"""
    from cortex.permissions import analyze_permissions

    result = analyze_permissions(".")
    assert isinstance(result, dict)
    assert "scan" in result
    assert "auditor" in result


def test_pytest_works():
    """Simple test to verify pytest is working"""
    assert 1 + 1 == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_scan_directory_permission_error(tmp_path, mocker):
    """Test scan_directory handles permission errors gracefully"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor(verbose=True)

    # Mock rglob to raise PermissionError
    mocker.patch(
        "cortex.permissions.auditor_fixer.Path.rglob",
        side_effect=PermissionError("Mocked permission error"),
    )
    result = auditor.scan_directory(tmp_path)

    assert isinstance(result, dict)
    assert result["world_writable"] == []
    assert result["dangerous"] == []
    assert result["suggestions"] == []


def test_scan_directory_file_access_error(tmp_path, mocker):
    """Test scan_directory handles file access errors"""
    from unittest.mock import Mock

    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor(verbose=False)

    # Create a mock item that raises OSError on stat()
    mock_item = Mock()
    mock_item.is_file.return_value = True
    mock_item.stat.side_effect = OSError("Mocked access error")

    # Mock rglob to return our mock item
    mocker.patch("cortex.permissions.auditor_fixer.Path.rglob", return_value=[mock_item])
    result = auditor.scan_directory(tmp_path)

    assert isinstance(result, dict)
    # Should continue despite errors


def test_fix_permissions_os_error(tmp_path, mocker):
    """Test fix_permissions handles OSError"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")

    # Mock chmod to raise OSError
    mocker.patch("pathlib.Path.chmod", side_effect=OSError("Mocked OSError"))
    result = auditor.fix_permissions(test_file, "644", dry_run=False)

    assert "Error changing permissions" in result
    assert "Mocked OSError" in result or "OSError" in result


def test_suggest_fix_with_shebang(tmp_path):
    """Test suggest_fix for files with shebang"""
    from cortex.permissions.auditor_fixer import PermissionAuditor

    auditor = PermissionAuditor()

    # Create script with shebang but no execute bit
    script = tmp_path / "script.py"
    script.write_text("#!/usr/bin/env python3\nprint('hello')")
    script.chmod(0o644)  # No execute bit

    suggestion = auditor.suggest_fix(script, "644")
    assert "chmod" in suggestion
    # Should suggest 755 because of shebang
    assert "755" in suggestion
