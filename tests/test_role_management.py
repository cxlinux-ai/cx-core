import importlib
import logging
import sys
import threading
from importlib import reload
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

from cortex.role_manager import RoleManager

# Global lock to prevent race conditions during module reloads in parallel test execution.
reload_lock = threading.Lock()


@pytest.fixture
def temp_cortex_dir(tmp_path):
    """
    Creates a temporary directory structure for hermetic file I/O testing.

    This fixture provides an isolated filesystem namespace to prevent tests from
    interacting with the actual user configuration (~/.cortex) on the developer's
    machine.

    Args:
        tmp_path: pytest's built-in temporary directory fixture.

    Returns:
        Path: Path to the temporary .cortex directory.
    """
    cortex_dir = tmp_path / ".cortex"
    cortex_dir.mkdir()
    return cortex_dir


@pytest.fixture
def role_manager(temp_cortex_dir, monkeypatch):
    """
    Provides a pre-configured RoleManager instance with isolated paths.

    This fixture provides an env_path within the temporary directory, which
    causes RoleManager to use env_path.parent as its base_dir and home_path,
    isolating all derived paths (e.g., history_db) from the real user home.

    Args:
        temp_cortex_dir: The temporary .cortex directory fixture.
        monkeypatch: pytest's monkeypatch fixture for environment patching.

    Returns:
        RoleManager: A configured RoleManager instance for testing.
    """
    env_path = temp_cortex_dir / ".env"
    return RoleManager(env_path=env_path)


def test_get_system_context_fact_gathering(temp_cortex_dir):
    """
    Verifies system signal aggregation, database parsing, and shell intent detection.

    This test ensures that the RoleManager correctly:
    - Detects installed binaries
    - Parses shell history for intent patterns
    - Retrieves learned patterns from the installation database
    """
    import json
    import sqlite3

    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    # Step 1: Seed the mock installation history database.
    db_path = temp_cortex_dir / "history.db"
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE installations (
                packages TEXT,
                status TEXT,
                timestamp DATETIME
            )
        """)
        # Insert a JSON array of packages as a successful installation.
        cursor.execute(
            "INSERT INTO installations (packages, status, timestamp) VALUES (?, ?, ?)",
            (json.dumps(["docker-ce", "kubectl"]), "success", "2024-01-01 12:00:00"),
        )

    # Step 2: Mock binary presence and shell history.
    with patch("cortex.role_manager.shutil.which") as mock_which:
        bash_history = temp_cortex_dir / ".bash_history"
        bash_history.write_text("git commit -m 'feat'\npip install torch\n", encoding="utf-8")

        # Simulate Nginx being installed on the system.
        mock_which.side_effect = lambda x: "/usr/bin/" + x if x in ["nginx"] else None

        context = manager.get_system_context()

        # Factual assertions.
        assert "nginx" in context["binaries"]
        # Verify shell history pattern sensing.
        assert "intent:version_control" in context["patterns"]
        # Verify SQLite learning loop sensing.
        assert "installed:docker-ce" in context["patterns"]
        assert "installed:kubectl" in context["patterns"]


def test_get_shell_patterns_privacy_hardening(role_manager, temp_cortex_dir):
    """
    Validates privacy-hardening and path normalization logic.

    Ensures that technical signals are preserved while local metadata,
    secrets, and absolute paths (both POSIX and Windows) are properly scrubbed.
    """
    history_file = temp_cortex_dir / ".bash_history"
    # Note: Using double-escaped backslashes to ensure shlex correctly parses
    # the path on a Linux test runner.
    content = (
        ": 1612345678:0;git pull\n"
        "DATABASE_URL=secret psql -d db\n"
        "/usr/local/bin/docker build .\n"
        "C:\\\\Users\\\\Admin\\\\bin\\\\kubectl get pods\n"
        "echo 'unclosed quote\n"
    )
    history_file.write_text(content, encoding="utf-8")

    patterns = role_manager._get_shell_patterns()

    assert "intent:version_control" in patterns
    assert "intent:psql" in patterns
    assert "intent:container" in patterns
    assert "intent:k8s" in patterns

    # Verify privacy hardening: raw paths should not leak into the patterns.
    assert not any("/usr/local/bin" in p for p in patterns)
    assert not any("C:\\" in p or "Users" in p for p in patterns)


def test_save_role_formatting_preservation(role_manager, temp_cortex_dir):
    """
    Ensures the persistence layer respects existing shell file formatting.

    Verifies that updating a role preserves 'export' prefixes and quoting
    styles used manually by the user, while preventing line duplication.
    """
    env_path = temp_cortex_dir / ".env"
    env_path.write_text('export CORTEX_SYSTEM_ROLE="initial" # manual comment\n', encoding="utf-8")

    role_manager.save_role("updated")

    content = env_path.read_text()
    # Confirm the regex correctly captured the prefix and quote style.
    assert 'export CORTEX_SYSTEM_ROLE="updated" # manual comment' in content
    assert content.count("CORTEX_SYSTEM_ROLE") == 1


def test_get_saved_role_tolerant_parsing_advanced(role_manager, temp_cortex_dir):
    """
    Validates parsing resilience against shell file variations.

    Handles optional whitespace, duplicate keys (last match wins),
    and trailing inline comments.
    """
    env_path = temp_cortex_dir / ".env"
    content = (
        "CORTEX_SYSTEM_ROLE=first\n" "export CORTEX_SYSTEM_ROLE = 'second' # Override comment\n"
    )
    env_path.write_text(content, encoding="utf-8")

    # 'second' should be selected as it follows standard shell overwrite behavior.
    assert role_manager.get_saved_role() == "second"


def test_locked_write_concurrency_degraded_logging(role_manager, monkeypatch, caplog):
    """
    Verifies system warnings when concurrency protection backends are missing.

    Tests the fallback state where neither fcntl nor msvcrt is available
    to ensure the user is notified of the lack of atomicity guarantees.
    """
    # Remove both platform-specific locking backends.
    monkeypatch.setattr("cortex.role_manager.fcntl", None)
    monkeypatch.setattr("cortex.role_manager.msvcrt", None)

    # Explicitly set log level to ensure warning capture is deterministic.
    caplog.set_level(logging.WARNING, logger="cortex.role_manager")

    role_manager.save_role("test-role")
    assert "No file locking backend available" in caplog.text


def test_locked_write_windows_locking_precision(role_manager, monkeypatch):
    """
    Validates the precision of Windows byte-range locking and mandatory seek(0).

    Ensures that msvcrt targets exactly 1 byte and that the file pointer is
    explicitly reset to the start of the file before locking, satisfying
    deterministic locking requirements.
    """
    mock_msvcrt = MagicMock()
    # Set up mock constants for Windows locking.
    mock_msvcrt.LK_LOCK = 1
    mock_msvcrt.LK_UNLCK = 0

    monkeypatch.setattr("cortex.role_manager.msvcrt", mock_msvcrt)
    monkeypatch.setattr("cortex.role_manager.fcntl", None)

    # Create a mock file handle to track .seek() calls.
    mock_file_handle = MagicMock()
    # Ensure the mock handle works as a context manager (supports 'with open(...)').
    mock_file_handle.__enter__.return_value = mock_file_handle

    with patch("builtins.open", return_value=mock_file_handle):
        role_manager.save_role("win-test")

    # Verification 1: Confirm that seek(0) was called.
    # It should be called at least twice: once before locking, once before unlocking.
    mock_file_handle.seek.assert_any_call(0)
    assert mock_file_handle.seek.call_count >= 2

    # Verification 2: Confirm msvcrt.locking parameters (precision requirement).
    # Signature: msvcrt.locking(fileno, mode, nbytes)
    # First call should be LK_LOCK with exactly 1 byte.
    assert mock_msvcrt.locking.call_args_list[0][0][1] == mock_msvcrt.LK_LOCK
    assert mock_msvcrt.locking.call_args_list[0][0][2] == 1


def test_get_shell_patterns_corrupted_data(role_manager, temp_cortex_dir):
    """
    Verifies sensing stability when processing corrupted binary history data.

    Ensures that the 'replace' error handler prevents crashes when history files
    contain non-UTF-8 bytes (e.g., binary blobs or corrupted log entries).
    """
    history_file = temp_cortex_dir / ".bash_history"
    # Seed file with valid text followed by invalid binary bytes.
    history_file.write_bytes(b"ls -la\n\xff\xfe\xfd\ngit commit -m 'test'")

    patterns = role_manager._get_shell_patterns()
    assert "intent:ls" in patterns
    assert "intent:version_control" in patterns


def test_shell_pattern_redaction_robustness(role_manager, temp_cortex_dir):
    """
    Verifies that the redaction logic successfully scrubs personally identifiable information (PII).

    Checks that API keys, authorization headers, and secrets are redacted while ensuring
    safe technical signals (e.g., ls, git) remain in the pattern sequence.
    """
    bash_history = temp_cortex_dir / ".bash_history"
    leaking_commands = (
        "export MY_API_KEY=abc123\n" 'curl -H "X-Api-Key: secret" http://api.com\n' "ls -la\n"
    )
    bash_history.write_text(leaking_commands, encoding="utf-8")

    patterns = role_manager._get_shell_patterns()

    # Raw secrets should not be present in the extracted patterns.
    assert not any("abc123" in p for p in patterns)
    assert patterns.count("<redacted>") == 2
    assert "intent:ls" in patterns


def test_save_role_slug_validation(role_manager):
    """
    Tests the security boundaries of the role slug validation regex.

    Validates legitimate variants like 'ml' and uppercase workstation slugs while
    rejecting potentially malicious input (e.g., newline or assignment injection).
    """
    # Test valid slug variants.
    valid_slugs = ["ml", "ML-Workstation", "dev_ops", "a"]
    for slug in valid_slugs:
        role_manager.save_role(slug)
        assert role_manager.get_saved_role() == slug

    # Test rejection of malformed or dangerous slugs.
    invalid_slugs = ["-dev", "dev-", "_dev", "dev_", "dev\n", "role!", ""]
    for slug in invalid_slugs:
        with pytest.raises(ValueError):
            role_manager.save_role(slug)


def test_get_shell_patterns_opt_out(role_manager, monkeypatch):
    """
    Validates the user privacy opt-out mechanism.

    Ensures the sensing layer respects the CORTEX_SENSE_HISTORY
    environment variable and returns zero signals when disabled.
    """
    monkeypatch.setenv("CORTEX_SENSE_HISTORY", "false")
    assert role_manager._get_shell_patterns() == []


def test_get_system_context_multi_gpu_vendors(role_manager):
    """
    Coverage test: Verifies detection of AMD and Intel GPU hardware.

    Ensures the has_gpu flag is set correctly when AMD (rocm-smi) or
    Intel (intel_gpu_top) GPU binaries are present.
    """
    with patch("cortex.role_manager.shutil.which") as mock_which:
        # Simulate AMD and Intel GPU binaries being present on the system.
        mock_which.side_effect = lambda x: (
            "/usr/bin/" + x if x in ["rocm-smi", "intel_gpu_top"] else None
        )
        context = role_manager.get_system_context()
        assert context["has_gpu"] is True


def test_get_shell_patterns_malformed_quoting_fallback(role_manager, temp_cortex_dir):
    """
    Coverage test: Ensures fallback handling for malformed shell quoting.

    When shlex.split encounters an unclosed quote and raises ValueError,
    the code should fall back to a simple .split() operation.
    """
    history_file = temp_cortex_dir / ".bash_history"
    # An unclosed quote forces shlex to raise ValueError, triggering the .split() fallback.
    history_file.write_text("echo 'unclosed quote", encoding="utf-8")
    patterns = role_manager._get_shell_patterns()
    assert "intent:echo" in patterns


def test_locked_write_chmod_oserror_handling(role_manager):
    """
    Coverage test: Verifies silent handling of chmod OSError exceptions.

    Ensures that permission errors during chmod operations do not crash
    the file locking mechanism.
    """
    with patch("cortex.role_manager.Path.chmod", side_effect=OSError("Operation not permitted")):
        # This should execute without raising an error.
        role_manager.save_role("chmod-test")


def test_get_saved_role_corrupted_or_empty(role_manager, temp_cortex_dir):
    """
    Coverage test: Handles the case where a key exists but has no value.

    Verifies that empty values are correctly interpreted as None rather
    than causing parsing errors.
    """
    env_path = temp_cortex_dir / ".env"
    # Write a file that exists but has no value for the key.
    env_path.write_text("CORTEX_SYSTEM_ROLE=", encoding="utf-8")
    assert role_manager.get_saved_role() is None


def test_locking_import_handling(monkeypatch):
    """
    Coverage test: Verifies conditional import handling for locking modules.

    Tests that the module gracefully handles ImportError for fcntl and msvcrt
    when they are unavailable. Uses a thread lock to ensure safety during
    parallel test execution.
    """
    with reload_lock:
        import cortex.role_manager

        # Save original values to restore after the test.
        original_fcntl = cortex.role_manager.fcntl
        original_msvcrt = cortex.role_manager.msvcrt

        try:
            # Remove modules from sys.modules to force ImportError on reload.
            monkeypatch.setitem(sys.modules, "fcntl", None)
            monkeypatch.setitem(sys.modules, "msvcrt", None)
            importlib.invalidate_caches()

            reload(cortex.role_manager)

            # Verify the branches where fcntl and msvcrt are set to None were executed.
            assert cortex.role_manager.fcntl is None
            assert cortex.role_manager.msvcrt is None
        finally:
            # Restore original state for other tests to prevent pollution.
            # Note: We only restore modules that were originally available on this platform.
            # monkeypatch cleanup will handle sys.modules restoration automatically.
            if original_fcntl is not None:
                monkeypatch.setitem(sys.modules, "fcntl", original_fcntl)
            if original_msvcrt is not None:
                monkeypatch.setitem(sys.modules, "msvcrt", original_msvcrt)

            importlib.invalidate_caches()
            reload(cortex.role_manager)


def test_get_saved_role_corrupted_data_replace(role_manager, temp_cortex_dir):
    """
    Coverage test: Verifies the errors='replace' branch in get_saved_role.

    Ensures that invalid UTF-8 bytes in the environment file are replaced
    with the Unicode replacement character rather than causing a crash.
    """
    env_path = temp_cortex_dir / ".env"
    # Write invalid UTF-8 bytes to the environment file.
    env_path.write_bytes(b"CORTEX_SYSTEM_ROLE=\xff\xfe\xfd\n")
    # Should not crash; should return a string containing replacement characters.
    role = role_manager.get_saved_role()
    assert role is not None
    # The replacement character for invalid UTF-8 bytes.
    assert "\ufffd" in role


def test_locked_write_cleanup_on_failure(role_manager, temp_cortex_dir):
    """
    Quality test: Verifies that orphaned temporary files are removed after crashes.

    Ensures that if an exception occurs during the write operation,
    the temporary file is properly cleaned up in the finally block.
    """

    def breaking_modifier(content, key, value):
        """Modifier function that intentionally crashes after creating a temp file."""
        temp_file = temp_cortex_dir / ".env.tmp"
        temp_file.touch()
        raise RuntimeError("Unexpected crash during write")

    with pytest.raises(RuntimeError, match="Unexpected crash during write"):
        role_manager._locked_read_modify_write("KEY", "VAL", breaking_modifier)

    assert not (temp_cortex_dir / ".env.tmp").exists()


def test_locked_write_unlocking_on_failure(role_manager, monkeypatch):
    """
    Quality test: Verifies that file locks are always released (LOCK_UN).

    Ensures that the file lock is released even if the atomic file replacement
    fails, preventing concurrent processes from being permanently blocked by
    a stale lock file.
    """
    if sys.platform == "win32":
        pytest.skip("Testing POSIX flock behavior; Windows uses msvcrt locking")

    mock_fcntl = MagicMock()
    # Apply the mock to the specific module where fcntl is used.
    monkeypatch.setattr("cortex.role_manager.fcntl", mock_fcntl)

    # Simulate a critical OS failure (e.g., disk full) during the file swap phase.
    with patch("pathlib.Path.replace", side_effect=OSError("Disk Full")):
        with pytest.raises(RuntimeError):
            role_manager.save_role("test-role")

    # Verification: Ensure fcntl.flock was called to unlock the file.
    # We use ANY for the file descriptor because its numeric value is determined at runtime.
    mock_fcntl.flock.assert_any_call(ANY, mock_fcntl.LOCK_UN)


def test_locked_read_error_handling(role_manager, temp_cortex_dir):
    """
    Coverage test: Verifies error handling when file reading fails inside the lock.

    Ensures that read failures within the locked section are properly propagated
    as RuntimeError exceptions.
    """
    env_path = temp_cortex_dir / ".env"
    env_path.touch()

    # Force a failure specifically when reading the file text.
    with patch("pathlib.Path.read_text", side_effect=OSError("Read error")):
        with pytest.raises(RuntimeError):
            role_manager.save_role("any-role")


def test_shell_pattern_privacy_script_leak(role_manager, temp_cortex_dir):
    """
    Verifies that sensitive or long script names are masked as 'intent:unknown'.

    This confirms the 'safe harbor' logic which prevents leaking descriptive
    filenames or paths that could contain sensitive project or security information.
    """
    history_file = temp_cortex_dir / ".bash_history"
    # A long, potentially sensitive script name (more than 20 characters).
    history_file.write_text("./deploy-prod-internal-service-v2.sh\n", encoding="utf-8")

    patterns = role_manager._get_shell_patterns()

    # Step 1: Ensure the complex name was caught by the fallback mechanism.
    assert "intent:unknown" in patterns
    # Step 2: Verify the actual sensitive string was not emitted in the patterns.
    assert not any("deploy-prod" in p for p in patterns)
