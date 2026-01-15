"""
Tests for Stdin Piping Support

Issue: #271 - Stdin Piping Support for Log Analysis
"""

import io
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from cortex.stdin_handler import (
    StdinData,
    StdinHandler,
    TruncationMode,
    analyze_stdin,
    detect_content_type,
    display_stdin_info,
    run_stdin_handler,
)


class TestTruncationMode:
    """Tests for TruncationMode enum."""

    def test_modes_defined(self):
        """Test all truncation modes are defined."""
        assert TruncationMode.HEAD.value == "head"
        assert TruncationMode.TAIL.value == "tail"
        assert TruncationMode.MIDDLE.value == "middle"
        assert TruncationMode.SAMPLE.value == "sample"


class TestStdinData:
    """Tests for StdinData dataclass."""

    def test_default_values(self):
        """Test default data values."""
        data = StdinData(
            content="test",
            line_count=1,
            byte_count=4,
        )
        assert data.was_truncated is False
        assert data.original_line_count == 0

    def test_is_empty(self):
        """Test is_empty property."""
        empty = StdinData(content="", line_count=0, byte_count=0)
        assert empty.is_empty is True

        not_empty = StdinData(content="x", line_count=1, byte_count=1)
        assert not_empty.is_empty is False


class TestStdinHandler:
    """Tests for StdinHandler class."""

    @pytest.fixture
    def handler(self):
        """Create a handler instance."""
        return StdinHandler(max_lines=10, max_bytes=1000)

    def test_initialization(self, handler):
        """Test handler initialization."""
        assert handler.max_lines == 10
        assert handler.max_bytes == 1000
        assert handler.truncation_mode == TruncationMode.MIDDLE

    def test_has_stdin_data_tty(self, handler):
        """Test stdin detection for TTY."""
        with patch("sys.stdin.isatty", return_value=True):
            assert handler.has_stdin_data() is False

    def test_has_stdin_data_pipe(self, handler):
        """Test stdin detection for pipe."""
        with patch("sys.stdin.isatty", return_value=False):
            with patch("select.select", return_value=([sys.stdin], [], [])):
                assert handler.has_stdin_data() is True

    def test_read_stdin_tty(self, handler):
        """Test reading from TTY returns empty."""
        with patch("sys.stdin.isatty", return_value=True):
            data = handler.read_stdin()
            assert data.is_empty

    def test_read_stdin_content(self, handler):
        """Test reading stdin content."""
        content = "line1\nline2\nline3\n"
        with patch("sys.stdin.isatty", return_value=False):
            with patch("sys.stdin.read", return_value=content):
                data = handler.read_stdin()

                assert data.content == content
                assert data.line_count == 3

    def test_truncate_head(self):
        """Test head truncation."""
        handler = StdinHandler(max_lines=2, truncation_mode=TruncationMode.HEAD)

        data = StdinData(
            content="line1\nline2\nline3\nline4\n",
            line_count=4,
            byte_count=24,
            original_line_count=4,
            original_byte_count=24,
        )

        truncated = handler.truncate(data)

        assert truncated.was_truncated is True
        assert "line1" in truncated.content
        assert "line2" in truncated.content
        assert "line4" not in truncated.content

    def test_truncate_tail(self):
        """Test tail truncation."""
        handler = StdinHandler(max_lines=2, truncation_mode=TruncationMode.TAIL)

        data = StdinData(
            content="line1\nline2\nline3\nline4\n",
            line_count=4,
            byte_count=24,
            original_line_count=4,
            original_byte_count=24,
        )

        truncated = handler.truncate(data)

        assert truncated.was_truncated is True
        assert "line3" in truncated.content
        assert "line4" in truncated.content
        assert "line1" not in truncated.content

    def test_truncate_middle(self):
        """Test middle truncation."""
        handler = StdinHandler(max_lines=4, truncation_mode=TruncationMode.MIDDLE)

        lines = [f"line{i}\n" for i in range(10)]
        content = "".join(lines)

        data = StdinData(
            content=content,
            line_count=10,
            byte_count=len(content),
            original_line_count=10,
            original_byte_count=len(content),
        )

        truncated = handler.truncate(data)

        assert truncated.was_truncated is True
        assert "line0" in truncated.content
        assert "line9" in truncated.content
        assert "truncated" in truncated.content

    def test_no_truncation_needed(self, handler):
        """Test when content fits within limits."""
        data = StdinData(
            content="short\n",
            line_count=1,
            byte_count=6,
        )

        result = handler.truncate(data)

        assert result.was_truncated is False
        assert result.content == "short\n"


class TestDetectContentType:
    """Tests for content type detection."""

    def test_detect_error_log(self):
        """Test error log detection."""
        content = "[ERROR] Something went wrong\nMore details here"
        assert detect_content_type(content) == "error_log"

    def test_detect_git_diff(self):
        """Test git diff detection."""
        content = "diff --git a/file.py b/file.py\nindex abc..def 100644"
        assert detect_content_type(content) == "git_diff"

    def test_detect_json(self):
        """Test JSON detection."""
        content = '{"key": "value"}'
        assert detect_content_type(content) == "json"

        content = "[1, 2, 3]"
        assert detect_content_type(content) == "json"

    def test_detect_python_traceback(self):
        """Test Python traceback detection."""
        content = "Traceback (most recent call last):\n  File..."
        assert detect_content_type(content) == "python_traceback"

    def test_detect_system_log(self):
        """Test system log detection."""
        content = "Jan 14 systemd[1]: Starting service..."
        assert detect_content_type(content) == "system_log"

    def test_detect_plain_text(self):
        """Test plain text fallback."""
        content = "Just some regular text here"
        assert detect_content_type(content) == "text"

    def test_detect_empty(self):
        """Test empty content."""
        assert detect_content_type("") == "empty"


class TestAnalyzeStdin:
    """Tests for stdin analysis."""

    def test_analyze_basic(self):
        """Test basic analysis."""
        data = StdinData(
            content="line1\nline2\n",
            line_count=2,
            byte_count=12,
        )

        result = analyze_stdin(data)

        assert result["line_count"] == 2
        assert result["byte_count"] == 12
        assert "content_type" in result
        assert "analysis" in result

    def test_analyze_error_log(self):
        """Test error log analysis."""
        data = StdinData(
            content="[ERROR] Error 1\nOK\n[ERROR] Error 2\n",
            line_count=3,
            byte_count=36,
        )

        result = analyze_stdin(data)

        assert result["content_type"] == "error_log"
        assert result["analysis"]["error_count"] == 2

    def test_analyze_git_diff(self):
        """Test git diff analysis."""
        data = StdinData(
            content="diff --git a/f.py b/f.py\n+added\n-removed\n+another\n",
            line_count=4,
            byte_count=50,
        )

        result = analyze_stdin(data)

        assert result["content_type"] == "git_diff"
        assert result["analysis"]["files_changed"] == 1
        assert result["analysis"]["additions"] == 2
        assert result["analysis"]["deletions"] == 1

    def test_analyze_json_array(self):
        """Test JSON array analysis."""
        data = StdinData(
            content="[1, 2, 3, 4, 5]",
            line_count=1,
            byte_count=15,
        )

        result = analyze_stdin(data)

        assert result["content_type"] == "json"
        assert result["analysis"]["type"] == "array"
        assert result["analysis"]["length"] == 5

    def test_analyze_json_object(self):
        """Test JSON object analysis."""
        data = StdinData(
            content='{"name": "test", "value": 123}',
            line_count=1,
            byte_count=30,
        )

        result = analyze_stdin(data)

        assert result["content_type"] == "json"
        assert result["analysis"]["type"] == "object"
        assert "name" in result["analysis"]["keys"]


class TestDisplayStdinInfo:
    """Tests for display function."""

    def test_display_runs(self, capsys):
        """Test display function runs without error."""
        data = StdinData(
            content="test content\n",
            line_count=1,
            byte_count=13,
        )

        display_stdin_info(data)
        captured = capsys.readouterr()
        assert "stdin" in captured.out.lower() or "lines" in captured.out.lower()

    def test_display_with_analysis(self, capsys):
        """Test display with analysis data."""
        data = StdinData(
            content="test\n",
            line_count=1,
            byte_count=5,
        )
        analysis = {
            "content_type": "text",
            "analysis": {"sample_key": "sample_value"},
        }

        display_stdin_info(data, analysis)
        captured = capsys.readouterr()
        assert "text" in captured.out.lower()


class TestRunStdinHandler:
    """Tests for run_stdin_handler entry point."""

    def test_run_no_stdin(self, capsys):
        """Test running with no stdin."""
        with patch("sys.stdin.isatty", return_value=True):
            result = run_stdin_handler("info")

        assert result == 0
        captured = capsys.readouterr()
        assert "no stdin" in captured.out.lower() or "usage" in captured.out.lower()

    def test_run_info_action(self, capsys):
        """Test info action."""
        handler = StdinHandler()

        with patch.object(handler, "has_stdin_data", return_value=True):
            with patch.object(
                handler,
                "read_and_truncate",
                return_value=StdinData(content="test\n", line_count=1, byte_count=5),
            ):
                with patch(
                    "cortex.stdin_handler.StdinHandler",
                    return_value=handler,
                ):
                    result = run_stdin_handler("info")

        assert result == 0

    def test_run_unknown_action(self, capsys):
        """Test unknown action."""
        handler = StdinHandler()

        with patch.object(handler, "has_stdin_data", return_value=True):
            with patch.object(
                handler,
                "read_and_truncate",
                return_value=StdinData(content="test\n", line_count=1, byte_count=5),
            ):
                with patch(
                    "cortex.stdin_handler.StdinHandler",
                    return_value=handler,
                ):
                    result = run_stdin_handler("unknown")

        assert result == 1
        captured = capsys.readouterr()
        assert "unknown" in captured.out.lower()

    def test_run_passthrough_action(self, capsys):
        """Test passthrough action."""
        handler = StdinHandler()

        with patch.object(handler, "has_stdin_data", return_value=True):
            with patch.object(
                handler,
                "read_and_truncate",
                return_value=StdinData(content="hello world", line_count=1, byte_count=11),
            ):
                with patch(
                    "cortex.stdin_handler.StdinHandler",
                    return_value=handler,
                ):
                    result = run_stdin_handler("passthrough")

        assert result == 0
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_run_stats_action(self, capsys):
        """Test stats action."""
        handler = StdinHandler()

        with patch.object(handler, "has_stdin_data", return_value=True):
            with patch.object(
                handler,
                "read_and_truncate",
                return_value=StdinData(content="test\n", line_count=1, byte_count=5),
            ):
                with patch(
                    "cortex.stdin_handler.StdinHandler",
                    return_value=handler,
                ):
                    result = run_stdin_handler("stats")

        assert result == 0
        captured = capsys.readouterr()
        # Should be valid JSON
        data = json.loads(captured.out)
        assert "line_count" in data


class TestTruncationModes:
    """Tests for all truncation modes."""

    def test_sample_truncation(self):
        """Test sample truncation mode."""
        handler = StdinHandler(max_lines=3, truncation_mode=TruncationMode.SAMPLE)

        lines = [f"line{i}\n" for i in range(100)]
        content = "".join(lines)

        data = StdinData(
            content=content,
            line_count=100,
            byte_count=len(content),
            original_line_count=100,
            original_byte_count=len(content),
        )

        truncated = handler.truncate(data)

        assert truncated.was_truncated is True
        assert truncated.line_count <= 3


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_stdin(self):
        """Test handling empty stdin."""
        handler = StdinHandler()

        with patch("sys.stdin.isatty", return_value=False):
            with patch("sys.stdin.read", return_value=""):
                data = handler.read_stdin()

        assert data.is_empty

    def test_unicode_content(self):
        """Test handling unicode content."""
        handler = StdinHandler()
        content = "Hello \u4e16\u754c\n\u00e9\u00e0\u00fc\n"

        with patch("sys.stdin.isatty", return_value=False):
            with patch("sys.stdin.read", return_value=content):
                data = handler.read_stdin()

        assert "\u4e16\u754c" in data.content
        assert data.byte_count > 0

    def test_binary_like_content(self):
        """Test handling content with unusual characters."""
        handler = StdinHandler()
        content = "test\x00null\xff\n"

        with patch("sys.stdin.isatty", return_value=False):
            with patch("sys.stdin.read", return_value=content):
                data = handler.read_stdin()

        assert data.line_count >= 1

    def test_read_error(self):
        """Test handling read errors."""
        handler = StdinHandler()

        with patch("sys.stdin.isatty", return_value=False):
            with patch("sys.stdin.read", side_effect=OSError("Read error")):
                data = handler.read_stdin()

        assert data.is_empty
