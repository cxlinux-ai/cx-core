"""
Comprehensive unit tests for cortex/shell_env_analyzer.py - Shell Environment Analyzer

Tests cover:
- Shell config file parsing (bash, zsh, fish)
- PATH analysis and deduplication
- Conflict detection
- Shell config editing with backup
- Safe atomic file operations

"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.shell_env_analyzer import (
    ConflictSeverity,
    EnvironmentAudit,
    PathEntry,
    Shell,
    ShellConfigEditor,
    ShellConfigParser,
    ShellEnvironmentAnalyzer,
    VariableConflict,
    VariableSource,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def bash_config(temp_dir):
    """Create a sample .bashrc file."""
    bashrc = temp_dir / ".bashrc"
    bashrc.write_text("""# Sample bashrc
export PATH="/usr/local/bin:$PATH"
export EDITOR="vim"
export NODE_ENV="development"
LANG=en_US.UTF-8

# Another PATH modification
export PATH="$HOME/bin:$PATH"
""")
    return bashrc


@pytest.fixture
def zsh_config(temp_dir):
    """Create a sample .zshrc file."""
    zshrc = temp_dir / ".zshrc"
    zshrc.write_text("""# Sample zshrc
export PATH="/opt/homebrew/bin:$PATH"
export EDITOR="nvim"
export ZSH_THEME="robbyrussell"
""")
    return zshrc


@pytest.fixture
def fish_config(temp_dir):
    """Create a sample fish config.fish file."""
    fish_dir = temp_dir / ".config" / "fish"
    fish_dir.mkdir(parents=True)
    config_fish = fish_dir / "config.fish"
    config_fish.write_text("""# Sample fish config
set -gx PATH /usr/local/bin $PATH
set -gx EDITOR vim
set -x NODE_ENV production
set fish_greeting ""
""")
    return config_fish


@pytest.fixture
def parser():
    """Create a ShellConfigParser instance."""
    return ShellConfigParser(shell=Shell.BASH)


@pytest.fixture
def editor(temp_dir):
    """Create a ShellConfigEditor instance."""
    return ShellConfigEditor(backup_dir=temp_dir / "backups")


@pytest.fixture
def analyzer():
    """Create a ShellEnvironmentAnalyzer instance."""
    return ShellEnvironmentAnalyzer(shell=Shell.BASH)


# =============================================================================
# Shell Enum Tests
# =============================================================================


class TestShellEnum:
    """Tests for Shell enum."""

    def test_shell_values(self):
        """Test shell enum values."""
        assert Shell.BASH.value == "bash"
        assert Shell.ZSH.value == "zsh"
        assert Shell.FISH.value == "fish"
        assert Shell.UNKNOWN.value == "unknown"


# =============================================================================
# VariableSource Tests
# =============================================================================


class TestVariableSource:
    """Tests for VariableSource dataclass."""

    def test_create_variable_source(self, temp_dir):
        """Test creating a variable source."""
        source = VariableSource(
            file=temp_dir / ".bashrc",
            line_number=5,
            raw_line='export PATH="/usr/local/bin:$PATH"',
            variable_name="PATH",
            value="/usr/local/bin:$PATH",
            is_export=True,
            shell=Shell.BASH,
        )
        assert source.variable_name == "PATH"
        assert source.line_number == 5
        assert source.is_export is True

    def test_to_dict(self, temp_dir):
        """Test serialization to dictionary."""
        source = VariableSource(
            file=temp_dir / ".bashrc",
            line_number=5,
            raw_line='export EDITOR="vim"',
            variable_name="EDITOR",
            value="vim",
            is_export=True,
            shell=Shell.BASH,
        )
        d = source.to_dict()
        assert d["variable_name"] == "EDITOR"
        assert d["value"] == "vim"
        assert d["line_number"] == 5
        assert d["shell"] == "bash"


# =============================================================================
# ShellConfigParser Tests
# =============================================================================


class TestShellConfigParser:
    """Tests for ShellConfigParser class."""

    def test_detect_shell_bash(self):
        """Test shell detection for bash."""
        with patch.dict(os.environ, {"SHELL": "/bin/bash"}):
            parser = ShellConfigParser()
            assert parser.shell == Shell.BASH

    def test_detect_shell_zsh(self):
        """Test shell detection for zsh."""
        with patch.dict(os.environ, {"SHELL": "/usr/bin/zsh"}):
            parser = ShellConfigParser()
            assert parser.shell == Shell.ZSH

    def test_detect_shell_fish(self):
        """Test shell detection for fish."""
        with patch.dict(os.environ, {"SHELL": "/usr/bin/fish"}):
            parser = ShellConfigParser()
            assert parser.shell == Shell.FISH

    def test_parse_bash_export(self, bash_config):
        """Test parsing bash export statements."""
        parser = ShellConfigParser(shell=Shell.BASH)
        sources = parser.parse_file(bash_config)

        # Should find PATH, EDITOR, NODE_ENV, LANG
        var_names = [s.variable_name for s in sources]
        assert "PATH" in var_names
        assert "EDITOR" in var_names
        assert "NODE_ENV" in var_names
        assert "LANG" in var_names

    def test_parse_bash_quoted_values(self, temp_dir):
        """Test parsing quoted values in bash."""
        bashrc = temp_dir / ".bashrc"
        bashrc.write_text("""export SINGLE='single quoted'
export DOUBLE="double quoted"
export UNQUOTED=unquoted
""")
        parser = ShellConfigParser(shell=Shell.BASH)
        sources = parser.parse_file(bashrc)

        values = {s.variable_name: s.value for s in sources}
        assert values["SINGLE"] == "single quoted"
        assert values["DOUBLE"] == "double quoted"
        assert values["UNQUOTED"] == "unquoted"

    def test_parse_fish_set(self, fish_config):
        """Test parsing fish set statements."""
        parser = ShellConfigParser(shell=Shell.FISH)
        sources = parser.parse_file(fish_config)

        var_names = [s.variable_name for s in sources]
        assert "PATH" in var_names
        assert "EDITOR" in var_names
        assert "NODE_ENV" in var_names

    def test_parse_nonexistent_file(self, parser, temp_dir):
        """Test parsing nonexistent file returns empty list."""
        sources = parser.parse_file(temp_dir / "nonexistent")
        assert sources == []

    def test_get_config_files_bash(self):
        """Test getting config files for bash."""
        parser = ShellConfigParser(shell=Shell.BASH)
        files = parser.get_config_files()

        # Should include common bash files
        file_names = [f.name for f in files]
        assert ".bashrc" in file_names or "profile" in str(files)

    def test_get_config_files_fish(self):
        """Test getting config files for fish."""
        parser = ShellConfigParser(shell=Shell.FISH)
        files = parser.get_config_files()

        # Should include fish config paths
        assert any("fish" in str(f) for f in files)

    def test_clean_value_removes_quotes(self, parser):
        """Test that _clean_value removes quotes."""
        assert parser._clean_value('"quoted"') == "quoted"
        assert parser._clean_value("'single'") == "single"
        assert parser._clean_value("unquoted") == "unquoted"

    def test_clean_value_removes_inline_comments(self, parser):
        """Test that _clean_value removes inline comments."""
        assert parser._clean_value("value # comment") == "value"
        assert parser._clean_value('"value" # comment') == "value"


# =============================================================================
# ShellConfigEditor Tests
# =============================================================================


class TestShellConfigEditor:
    """Tests for ShellConfigEditor class."""

    def test_backup_file(self, editor, temp_dir):
        """Test creating file backup."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("original content")

        backup_path = editor.backup_file(test_file)

        assert backup_path.exists()
        assert backup_path.read_text() == "original content"
        assert "cortex-backup" in backup_path.name

    def test_backup_nonexistent_file(self, editor, temp_dir):
        """Test backing up nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            editor.backup_file(temp_dir / "nonexistent")

    def test_add_to_config_new_file(self, editor, temp_dir):
        """Test adding content to new config file."""
        config_file = temp_dir / "newconfig"

        editor.add_to_config(config_file, "export FOO=bar", backup=False)

        content = config_file.read_text()
        assert "export FOO=bar" in content
        assert ">>> cortex managed >>>" in content
        assert "<<< cortex managed <<<" in content

    def test_add_to_config_existing_file(self, editor, bash_config):
        """Test adding content to existing config file."""
        original_content = bash_config.read_text()

        editor.add_to_config(bash_config, "export NEW_VAR=value", backup=False)

        new_content = bash_config.read_text()
        assert original_content in new_content
        assert "export NEW_VAR=value" in new_content

    def test_add_to_config_idempotent(self, editor, temp_dir):
        """Test that adding same marker twice updates rather than duplicates."""
        config_file = temp_dir / "config"
        config_file.write_text("# existing content\n")

        editor.add_to_config(config_file, "first", marker_id="test", backup=False)
        editor.add_to_config(config_file, "second", marker_id="test", backup=False)

        content = config_file.read_text()
        # Should only have one marker block, containing "second"
        assert content.count(">>> cortex:test >>>") == 1
        assert "second" in content
        # "first" should be replaced, not present
        assert "first" not in content

    def test_remove_from_config(self, editor, temp_dir):
        """Test removing cortex-managed content."""
        config_file = temp_dir / "config"

        editor.add_to_config(config_file, "export TEST=value", marker_id="test", backup=False)
        assert "export TEST=value" in config_file.read_text()

        editor.remove_from_config(config_file, marker_id="test", backup=False)
        assert "export TEST=value" not in config_file.read_text()

    def test_remove_from_config_nonexistent_marker(self, editor, temp_dir):
        """Test removing nonexistent marker returns False."""
        config_file = temp_dir / "config"
        config_file.write_text("# no cortex content\n")

        result = editor.remove_from_config(config_file, marker_id="nonexistent", backup=False)
        assert result is False

    def test_restore_backup(self, editor, temp_dir):
        """Test restoring from backup."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("original")
        backup_path = editor.backup_file(test_file)

        test_file.write_text("modified")
        editor.restore_backup(backup_path, test_file)

        assert test_file.read_text() == "original"


# =============================================================================
# ShellEnvironmentAnalyzer Tests
# =============================================================================


class TestShellEnvironmentAnalyzer:
    """Tests for ShellEnvironmentAnalyzer class."""

    def test_dedupe_path(self, analyzer):
        """Test PATH deduplication."""
        path = "/usr/bin:/usr/local/bin:/usr/bin:/home/user/bin:/usr/bin"
        deduped = analyzer.dedupe_path(path)

        entries = deduped.split(os.pathsep)
        assert entries.count("/usr/bin") == 1
        assert len(entries) == 3

    def test_dedupe_path_preserves_order(self, analyzer):
        """Test that deduplication preserves first occurrence order."""
        path = "/first:/second:/first:/third"
        deduped = analyzer.dedupe_path(path)

        entries = deduped.split(os.pathsep)
        assert entries == ["/first", "/second", "/third"]

    def test_clean_path_removes_duplicates(self, analyzer):
        """Test clean_path removes duplicates."""
        path = "/a:/b:/a:/c"
        cleaned = analyzer.clean_path(path)

        assert cleaned.count("/a") == 1

    def test_clean_path_removes_missing(self, analyzer, temp_dir):
        """Test clean_path removes non-existent paths."""
        existing = temp_dir / "existing"
        existing.mkdir()

        path = f"{existing}:/nonexistent/path"
        cleaned = analyzer.clean_path(path, remove_missing=True)

        assert str(existing) in cleaned
        assert "/nonexistent/path" not in cleaned

    def test_safe_add_path_prepend(self, analyzer):
        """Test safe_add_path prepends by default."""
        path = "/usr/bin:/usr/local/bin"
        new_path = analyzer.safe_add_path("/new/path", prepend=True, path=path)

        entries = new_path.split(os.pathsep)
        assert entries[0] == "/new/path"

    def test_safe_add_path_append(self, analyzer):
        """Test safe_add_path can append."""
        path = "/usr/bin:/usr/local/bin"
        new_path = analyzer.safe_add_path("/new/path", prepend=False, path=path)

        entries = new_path.split(os.pathsep)
        assert entries[-1] == "/new/path"

    def test_safe_add_path_idempotent(self, analyzer):
        """Test safe_add_path doesn't duplicate existing entries."""
        path = "/usr/bin:/usr/local/bin"
        new_path = analyzer.safe_add_path("/usr/bin", path=path)

        # Should be unchanged - /usr/bin already exists
        assert new_path == path

    def test_safe_remove_path(self, analyzer):
        """Test safe_remove_path removes entry."""
        path = "/usr/bin:/usr/local/bin:/home/user/bin"
        new_path = analyzer.safe_remove_path("/usr/local/bin", path=path)

        assert "/usr/local/bin" not in new_path.split(os.pathsep)
        assert "/usr/bin" in new_path.split(os.pathsep)

    def test_get_path_duplicates(self, analyzer):
        """Test detecting PATH duplicates."""
        with patch.dict(os.environ, {"PATH": "/usr/bin:/usr/local/bin:/usr/bin"}):
            duplicates = analyzer.get_path_duplicates()
            assert "/usr/bin" in duplicates

    def test_get_missing_paths(self, analyzer):
        """Test detecting missing PATH entries."""
        with patch.dict(os.environ, {"PATH": "/usr/bin:/definitely/not/real/path"}):
            missing = analyzer.get_missing_paths()
            assert "/definitely/not/real/path" in missing

    def test_get_shell_config_path_bash(self):
        """Test getting bash config path."""
        analyzer = ShellEnvironmentAnalyzer(shell=Shell.BASH)
        config_path = analyzer.get_shell_config_path()

        assert config_path.name in (".bashrc", ".bash_profile")

    def test_get_shell_config_path_zsh(self):
        """Test getting zsh config path."""
        analyzer = ShellEnvironmentAnalyzer(shell=Shell.ZSH)
        config_path = analyzer.get_shell_config_path()

        assert config_path.name == ".zshrc"

    def test_get_shell_config_path_fish(self):
        """Test getting fish config path."""
        analyzer = ShellEnvironmentAnalyzer(shell=Shell.FISH)
        config_path = analyzer.get_shell_config_path()

        assert "fish" in str(config_path)
        assert config_path.name == "config.fish"

    def test_generate_path_fix_script_clean(self, analyzer):
        """Test fix script when PATH is clean."""
        with patch.object(analyzer, "get_path_duplicates", return_value=[]):
            with patch.object(analyzer, "get_missing_paths", return_value=[]):
                script = analyzer.generate_path_fix_script()
                assert "no fixes needed" in script

    def test_generate_path_fix_script_with_issues(self, analyzer):
        """Test fix script when PATH has issues."""
        with patch.object(analyzer, "get_path_duplicates", return_value=["/dup"]):
            with patch.object(analyzer, "get_missing_paths", return_value=["/missing"]):
                with patch.object(analyzer, "clean_path", return_value="/clean/path"):
                    script = analyzer.generate_path_fix_script()
                    assert "Duplicates found" in script or "Missing paths" in script


# =============================================================================
# VariableConflict Tests
# =============================================================================


class TestVariableConflict:
    """Tests for VariableConflict dataclass."""

    def test_create_conflict(self, temp_dir):
        """Test creating a variable conflict."""
        sources = [
            VariableSource(
                file=temp_dir / ".bashrc",
                line_number=5,
                raw_line='export FOO="bar"',
                variable_name="FOO",
                value="bar",
                shell=Shell.BASH,
            ),
            VariableSource(
                file=temp_dir / ".profile",
                line_number=10,
                raw_line='export FOO="baz"',
                variable_name="FOO",
                value="baz",
                shell=Shell.BASH,
            ),
        ]
        conflict = VariableConflict(
            variable_name="FOO",
            sources=sources,
            severity=ConflictSeverity.WARNING,
            description="Variable defined with different values",
        )

        assert conflict.variable_name == "FOO"
        assert len(conflict.sources) == 2
        assert conflict.severity == ConflictSeverity.WARNING

    def test_conflict_to_dict(self, temp_dir):
        """Test conflict serialization."""
        conflict = VariableConflict(
            variable_name="TEST",
            sources=[],
            severity=ConflictSeverity.INFO,
            description="Test conflict",
        )
        d = conflict.to_dict()

        assert d["variable_name"] == "TEST"
        assert d["severity"] == "info"
        assert d["description"] == "Test conflict"


# =============================================================================
# PathEntry Tests
# =============================================================================


class TestPathEntry:
    """Tests for PathEntry dataclass."""

    def test_create_path_entry(self):
        """Test creating a path entry."""
        entry = PathEntry(
            path="/usr/local/bin",
            source=None,
            exists=True,
            is_duplicate=False,
        )
        assert entry.path == "/usr/local/bin"
        assert entry.exists is True
        assert entry.is_duplicate is False

    def test_path_entry_to_dict(self):
        """Test path entry serialization."""
        entry = PathEntry(
            path="/home/user/bin",
            source=None,
            exists=False,
            is_duplicate=True,
        )
        d = entry.to_dict()

        assert d["path"] == "/home/user/bin"
        assert d["exists"] is False
        assert d["is_duplicate"] is True


# =============================================================================
# EnvironmentAudit Tests
# =============================================================================


class TestEnvironmentAudit:
    """Tests for EnvironmentAudit dataclass."""

    def test_create_audit(self):
        """Test creating an audit result."""
        audit = EnvironmentAudit(
            shell=Shell.BASH,
            variables={},
            path_entries=[],
            conflicts=[],
            config_files_scanned=[],
        )
        assert audit.shell == Shell.BASH

    def test_audit_to_dict(self, temp_dir):
        """Test audit serialization."""
        audit = EnvironmentAudit(
            shell=Shell.ZSH,
            variables={"PATH": []},
            path_entries=[PathEntry(path="/bin", exists=True, is_duplicate=False)],
            conflicts=[],
            config_files_scanned=[temp_dir / ".zshrc"],
        )
        d = audit.to_dict()

        assert d["shell"] == "zsh"
        assert "PATH" in d["variables"]
        assert len(d["path_entries"]) == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the shell environment analyzer."""

    def test_full_audit_workflow(self, temp_dir):
        """Test complete audit workflow."""
        # Create mock home directory structure
        home = temp_dir / "home"
        home.mkdir()
        bashrc = home / ".bashrc"
        bashrc.write_text("""export PATH="/custom/bin:$PATH"
export EDITOR="vim"
export EDITOR="nano"
""")

        with patch.object(Path, "home", return_value=home):
            analyzer = ShellEnvironmentAnalyzer(shell=Shell.BASH)

            # Mock get_config_files to only return our test file
            with patch.object(analyzer.parser, "get_config_files", return_value=[bashrc]):
                audit = analyzer.audit()

                # Should detect EDITOR being defined twice
                assert "EDITOR" in audit.variables
                assert len(audit.variables["EDITOR"]) == 2

    def test_path_add_and_persist(self, temp_dir):
        """Test adding path entry with persistence."""
        home = temp_dir / "home"
        home.mkdir()
        bashrc = home / ".bashrc"
        bashrc.write_text("# original bashrc\n")

        with patch.object(Path, "home", return_value=home):
            analyzer = ShellEnvironmentAnalyzer(shell=Shell.BASH)

            # Override get_shell_config_path for testing
            with patch.object(analyzer, "get_shell_config_path", return_value=bashrc):
                analyzer.add_path_to_config("/new/test/path", prepend=True, backup=False)

                content = bashrc.read_text()
                assert "/new/test/path" in content
                assert "export PATH" in content

    def test_variable_add_to_config(self, temp_dir):
        """Test adding variable to config."""
        home = temp_dir / "home"
        home.mkdir()
        zshrc = home / ".zshrc"
        zshrc.write_text("# original zshrc\n")

        with patch.object(Path, "home", return_value=home):
            analyzer = ShellEnvironmentAnalyzer(shell=Shell.ZSH)

            with patch.object(analyzer, "get_shell_config_path", return_value=zshrc):
                analyzer.add_variable_to_config("MY_VAR", "my_value", backup=False)

                content = zshrc.read_text()
                assert 'export MY_VAR="my_value"' in content

    def test_fish_variable_syntax(self, temp_dir):
        """Test fish shell variable syntax."""
        home = temp_dir / "home"
        home.mkdir()
        fish_config = home / "config.fish"
        fish_config.write_text("# fish config\n")

        with patch.object(Path, "home", return_value=home):
            analyzer = ShellEnvironmentAnalyzer(shell=Shell.FISH)

            with patch.object(analyzer, "get_shell_config_path", return_value=fish_config):
                analyzer.add_variable_to_config("FISH_VAR", "fish_value", backup=False)

                content = fish_config.read_text()
                assert 'set -gx FISH_VAR "fish_value"' in content


class TestShellEscaping:
    """Tests for shell string escaping and marker ID generation."""

    def test_escape_shell_string_bash_special_chars(self):
        """Test escaping special characters for bash."""
        analyzer = ShellEnvironmentAnalyzer(shell=Shell.BASH)

        # Test double quotes
        assert analyzer._escape_shell_string('hello"world', Shell.BASH) == 'hello\\"world'
        # Test dollar sign
        assert analyzer._escape_shell_string("$HOME", Shell.BASH) == "\\$HOME"
        # Test backtick
        assert analyzer._escape_shell_string("hello`cmd`", Shell.BASH) == "hello\\`cmd\\`"
        # Test backslash
        assert analyzer._escape_shell_string("path\\to", Shell.BASH) == "path\\\\to"

    def test_escape_shell_string_fish_special_chars(self):
        """Test escaping special characters for fish."""
        analyzer = ShellEnvironmentAnalyzer(shell=Shell.FISH)

        # Test double quotes
        assert analyzer._escape_shell_string('hello"world', Shell.FISH) == 'hello\\"world'
        # Test dollar sign
        assert analyzer._escape_shell_string("$HOME", Shell.FISH) == "\\$HOME"
        # Fish doesn't use backticks for command substitution
        assert analyzer._escape_shell_string("hello`cmd`", Shell.FISH) == "hello`cmd`"

    def test_escape_shell_string_safe_path(self):
        """Test that normal paths are unchanged."""
        analyzer = ShellEnvironmentAnalyzer(shell=Shell.BASH)

        assert analyzer._escape_shell_string("/usr/local/bin", Shell.BASH) == "/usr/local/bin"
        assert (
            analyzer._escape_shell_string("/home/user/.local/bin", Shell.BASH)
            == "/home/user/.local/bin"
        )

    def test_generate_marker_id_absolute_path(self):
        """Test marker ID for absolute paths preserves leading dash."""
        analyzer = ShellEnvironmentAnalyzer(shell=Shell.BASH)

        marker = analyzer._generate_marker_id("path", "/usr/local/bin")
        assert marker == "path--usr-local-bin"
        assert marker.startswith("path--")  # Leading dash preserved

    def test_generate_marker_id_relative_path(self):
        """Test marker ID for relative paths."""
        analyzer = ShellEnvironmentAnalyzer(shell=Shell.BASH)

        marker = analyzer._generate_marker_id("path", "usr/local/bin")
        assert marker == "path-usr-local-bin"

    def test_generate_marker_id_no_collision(self):
        """Test that /a/b and a/b produce different markers."""
        analyzer = ShellEnvironmentAnalyzer(shell=Shell.BASH)

        marker_absolute = analyzer._generate_marker_id("path", "/a/b")
        marker_relative = analyzer._generate_marker_id("path", "a/b")

        assert marker_absolute != marker_relative
        assert marker_absolute == "path--a-b"
        assert marker_relative == "path-a-b"

    def test_add_path_escapes_special_chars(self, tmp_path):
        """Test that adding paths with special chars escapes them properly."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text("# test\n")

        analyzer = ShellEnvironmentAnalyzer(shell=Shell.BASH)

        with patch.object(analyzer, "get_shell_config_path", return_value=bashrc):
            # Path with dollar sign (could be mistaken for variable)
            analyzer.add_path_to_config("/path/with$dollar", backup=False)

            content = bashrc.read_text()
            # Should be escaped
            assert "\\$dollar" in content
