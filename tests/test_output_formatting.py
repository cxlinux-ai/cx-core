"""
Tests for Output Formatting Modules

Issue: #242 - Output Polish: Rich Formatting with Colors, Boxes, Spinners
"""

import io
import re
from unittest.mock import patch

import pytest
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cortex.branding import (
    CORTEX_CYAN,
    CORTEX_ERROR,
    CORTEX_SUCCESS,
    CORTEX_WARNING,
    cx_box,
    cx_divider,
    cx_error,
    cx_header,
    cx_info,
    cx_package_table,
    cx_print,
    cx_status_box,
    cx_step,
    cx_success,
    cx_table,
    cx_warning,
    show_banner,
)
from cortex.output_formatter import (
    COLORS,
    STATUS_ICONS,
    MultiStepProgress,
    OutputStyle,
    ProgressTracker,
    StatusInfo,
    TableColumn,
    format_box,
    format_bytes,
    format_duration,
    format_package_table,
    format_status_box,
    format_table,
    print_divider,
    print_error,
    print_info,
    print_success,
    print_warning,
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text.

    Rich console outputs styling as ANSI escape codes, which can interfere
    with text assertions. This helper removes them for clean text testing.
    """
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestBrandingColors:
    """Tests for branding color constants."""

    def test_color_constants_defined(self):
        """Verify all color constants are defined."""
        assert CORTEX_CYAN == "cyan"
        assert CORTEX_SUCCESS == "green"
        assert CORTEX_WARNING == "yellow"
        assert CORTEX_ERROR == "red"

    def test_colors_dict_complete(self):
        """Verify COLORS dict has all required keys."""
        required_colors = ["primary", "secondary", "success", "warning", "error", "info", "muted"]
        for color in required_colors:
            assert color in COLORS


class TestStatusIcons:
    """Tests for status icon constants."""

    def test_status_icons_defined(self):
        """Verify all status icons are defined."""
        required_icons = ["success", "error", "warning", "info", "pending", "running"]
        for icon in required_icons:
            assert icon in STATUS_ICONS
            assert len(STATUS_ICONS[icon]) >= 1


class TestCxPrint:
    """Tests for cx_print function."""

    def test_cx_print_info(self, capsys):
        """Test info status output."""
        cx_print("Test message", "info")
        captured = capsys.readouterr()
        assert "Test message" in captured.out
        assert "CX" in captured.out

    def test_cx_print_success(self, capsys):
        """Test success status output."""
        cx_print("Success message", "success")
        captured = capsys.readouterr()
        assert "Success message" in captured.out
        assert "✓" in captured.out

    def test_cx_print_error(self, capsys):
        """Test error status output."""
        cx_print("Error message", "error")
        captured = capsys.readouterr()
        assert "Error message" in captured.out
        assert "✗" in captured.out

    def test_cx_print_warning(self, capsys):
        """Test warning status output."""
        cx_print("Warning message", "warning")
        captured = capsys.readouterr()
        assert "Warning message" in captured.out
        assert "⚠" in captured.out

    def test_cx_print_thinking(self, capsys):
        """Test thinking status output."""
        cx_print("Thinking message", "thinking")
        captured = capsys.readouterr()
        assert "Thinking message" in captured.out


class TestCxStep:
    """Tests for cx_step function."""

    def test_cx_step_format(self, capsys):
        """Test step numbering format."""
        cx_step(1, 4, "First step")
        captured = capsys.readouterr()
        output = strip_ansi(captured.out)
        assert "[1/4]" in output
        assert "First step" in output

    def test_cx_step_multiple(self, capsys):
        """Test multiple steps."""
        for i in range(1, 4):
            cx_step(i, 3, f"Step {i}")
        captured = capsys.readouterr()
        output = strip_ansi(captured.out)
        assert "[1/3]" in output
        assert "[2/3]" in output
        assert "[3/3]" in output


class TestCxHeader:
    """Tests for cx_header function."""

    def test_cx_header_format(self, capsys):
        """Test header formatting."""
        cx_header("Test Section")
        captured = capsys.readouterr()
        assert "Test Section" in captured.out
        assert "━" in captured.out


class TestCxBox:
    """Tests for cx_box function."""

    def test_cx_box_basic(self, capsys):
        """Test basic box output."""
        cx_box("Box content")
        captured = capsys.readouterr()
        assert "Box content" in captured.out

    def test_cx_box_with_title(self, capsys):
        """Test box with title."""
        cx_box("Content", title="Title")
        captured = capsys.readouterr()
        assert "Content" in captured.out
        assert "Title" in captured.out

    def test_cx_box_success_style(self, capsys):
        """Test box with success status."""
        cx_box("Success content", status="success")
        captured = capsys.readouterr()
        assert "Success content" in captured.out


class TestCxStatusBox:
    """Tests for cx_status_box function."""

    def test_status_box_basic(self, capsys):
        """Test basic status box."""
        cx_status_box(
            "Status",
            [
                ("Label1", "Value1", "default"),
                ("Label2", "Value2", "success"),
            ],
        )
        captured = capsys.readouterr()
        assert "Status" in captured.out
        assert "Label1" in captured.out
        assert "Value1" in captured.out
        assert "Label2" in captured.out
        assert "Value2" in captured.out

    def test_status_box_alignment(self, capsys):
        """Test that labels are aligned."""
        cx_status_box(
            "Test",
            [
                ("Short", "Value", "default"),
                ("LongerLabel", "Value", "default"),
            ],
        )
        captured = capsys.readouterr()
        # Both labels should appear
        assert "Short" in captured.out
        assert "LongerLabel" in captured.out


class TestCxTable:
    """Tests for cx_table function."""

    def test_table_basic(self, capsys):
        """Test basic table output."""
        cx_table(
            headers=["Col1", "Col2"],
            rows=[["A", "B"], ["C", "D"]],
        )
        captured = capsys.readouterr()
        assert "Col1" in captured.out
        assert "Col2" in captured.out
        assert "A" in captured.out
        assert "D" in captured.out

    def test_table_with_title(self, capsys):
        """Test table with title."""
        cx_table(
            headers=["Header"],
            rows=[["Row"]],
            title="Test Table",
        )
        captured = capsys.readouterr()
        assert "Test Table" in captured.out


class TestCxPackageTable:
    """Tests for cx_package_table function."""

    def test_package_table(self, capsys):
        """Test package table output."""
        cx_package_table(
            [
                ("docker", "24.0", "Install"),
                ("nginx", "1.24", "Update"),
            ],
            title="Packages",
        )
        captured = capsys.readouterr()
        assert "docker" in captured.out
        assert "24.0" in captured.out
        assert "Install" in captured.out

    def test_package_table_action_colors(self, capsys):
        """Test that actions are color-coded."""
        cx_package_table(
            [
                ("pkg1", "1.0", "Install"),
                ("pkg2", "2.0", "Remove"),
                ("pkg3", "3.0", "Update"),
            ],
        )
        captured = capsys.readouterr()
        # All packages should appear
        assert "pkg1" in captured.out
        assert "pkg2" in captured.out
        assert "pkg3" in captured.out


class TestCxDivider:
    """Tests for cx_divider function."""

    def test_divider_no_title(self, capsys):
        """Test divider without title."""
        cx_divider()
        captured = capsys.readouterr()
        assert "━" in captured.out

    def test_divider_with_title(self, capsys):
        """Test divider with title."""
        cx_divider("Section")
        captured = capsys.readouterr()
        assert "Section" in captured.out
        assert "━" in captured.out


class TestStatusMessages:
    """Tests for status message functions."""

    def test_cx_success(self, capsys):
        """Test success message."""
        cx_success("Done")
        captured = capsys.readouterr()
        assert "✓" in captured.out
        assert "Done" in captured.out

    def test_cx_error(self, capsys):
        """Test error message."""
        cx_error("Failed")
        captured = capsys.readouterr()
        assert "✗" in captured.out
        assert "Failed" in captured.out

    def test_cx_warning(self, capsys):
        """Test warning message."""
        cx_warning("Caution")
        captured = capsys.readouterr()
        assert "⚠" in captured.out
        assert "Caution" in captured.out

    def test_cx_info(self, capsys):
        """Test info message."""
        cx_info("Note")
        captured = capsys.readouterr()
        assert "ℹ" in captured.out
        assert "Note" in captured.out


class TestOutputFormatterBox:
    """Tests for output_formatter box functions."""

    def test_format_box_returns_panel(self):
        """Test format_box returns a Panel."""
        result = format_box("Content")
        assert isinstance(result, Panel)

    def test_format_box_with_style(self):
        """Test format_box with different styles."""
        for style in OutputStyle:
            result = format_box("Content", style=style)
            assert isinstance(result, Panel)

    def test_format_status_box_returns_panel(self):
        """Test format_status_box returns a Panel."""
        result = format_status_box(
            "Title",
            [StatusInfo("Label", "Value", OutputStyle.SUCCESS)],
        )
        assert isinstance(result, Panel)


class TestOutputFormatterTable:
    """Tests for output_formatter table functions."""

    def test_format_table_returns_table(self):
        """Test format_table returns a Table."""
        result = format_table(
            columns=[TableColumn("Header")],
            rows=[["Value"]],
        )
        assert isinstance(result, Table)

    def test_format_package_table_returns_table(self):
        """Test format_package_table returns a Table."""
        result = format_package_table(
            packages=[("pkg", "1.0", "Install")],
        )
        assert isinstance(result, Table)

    def test_table_column_defaults(self):
        """Test TableColumn default values."""
        col = TableColumn("Test")
        assert col.header == "Test"
        assert col.style == "cyan"
        assert col.justify == "left"
        assert col.width is None


class TestFormatHelpers:
    """Tests for format helper functions."""

    def test_format_bytes_basic(self):
        """Test format_bytes with various sizes."""
        assert format_bytes(0) == "0.0 B"
        assert format_bytes(1024) == "1.0 KB"
        assert format_bytes(1024 * 1024) == "1.0 MB"
        assert format_bytes(1024 * 1024 * 1024) == "1.0 GB"

    def test_format_bytes_fractional(self):
        """Test format_bytes with fractional values."""
        result = format_bytes(1536)
        assert "KB" in result

    def test_format_duration_seconds(self):
        """Test format_duration with seconds."""
        assert format_duration(0.5) == "0.5s"
        assert format_duration(30) == "30.0s"

    def test_format_duration_minutes(self):
        """Test format_duration with minutes."""
        result = format_duration(90)
        assert "m" in result
        assert "1m 30s" == result

    def test_format_duration_hours(self):
        """Test format_duration with hours."""
        result = format_duration(3661)
        assert "h" in result


class TestStatusInfo:
    """Tests for StatusInfo dataclass."""

    def test_status_info_defaults(self):
        """Test StatusInfo default values."""
        info = StatusInfo("Label", "Value")
        assert info.label == "Label"
        assert info.value == "Value"
        assert info.style == OutputStyle.DEFAULT

    def test_status_info_with_style(self):
        """Test StatusInfo with custom style."""
        info = StatusInfo("Label", "Value", OutputStyle.SUCCESS)
        assert info.style == OutputStyle.SUCCESS


class TestOutputStyle:
    """Tests for OutputStyle enum."""

    def test_output_styles_defined(self):
        """Test all output styles are defined."""
        styles = [OutputStyle.DEFAULT, OutputStyle.SUCCESS, OutputStyle.WARNING, OutputStyle.ERROR]
        assert len(styles) == 4

    def test_output_style_values(self):
        """Test output style values."""
        assert OutputStyle.SUCCESS.value == "success"
        assert OutputStyle.ERROR.value == "error"


class TestPrintFunctions:
    """Tests for print helper functions."""

    def test_print_success(self, capsys):
        """Test print_success."""
        print_success("Success")
        captured = capsys.readouterr()
        assert STATUS_ICONS["success"] in captured.out

    def test_print_error(self, capsys):
        """Test print_error."""
        print_error("Error")
        captured = capsys.readouterr()
        assert STATUS_ICONS["error"] in captured.out

    def test_print_warning(self, capsys):
        """Test print_warning."""
        print_warning("Warning")
        captured = capsys.readouterr()
        assert STATUS_ICONS["warning"] in captured.out

    def test_print_info(self, capsys):
        """Test print_info."""
        print_info("Info")
        captured = capsys.readouterr()
        assert STATUS_ICONS["info"] in captured.out

    def test_print_divider(self, capsys):
        """Test print_divider."""
        print_divider()
        captured = capsys.readouterr()
        assert "━" in captured.out


class TestProgressTracker:
    """Tests for ProgressTracker class."""

    def test_progress_tracker_context(self):
        """Test ProgressTracker as context manager."""
        with ProgressTracker("Test", total=10) as tracker:
            assert tracker._progress is not None
            assert tracker._task_id is not None

    def test_progress_tracker_advance(self):
        """Test ProgressTracker advance method."""
        with ProgressTracker("Test", total=10) as tracker:
            tracker.advance(1)
            # Should not raise

    def test_progress_tracker_update(self):
        """Test ProgressTracker update method."""
        with ProgressTracker("Test", total=10) as tracker:
            tracker.update("New description", advance=2)
            # Should not raise


class TestMultiStepProgress:
    """Tests for MultiStepProgress class."""

    def test_multi_step_initialization(self):
        """Test MultiStepProgress initialization."""
        steps = ["Step 1", "Step 2"]
        progress = MultiStepProgress(steps, "Test")
        assert progress.steps == steps
        assert progress.title == "Test"
        assert all(status == "pending" for status in progress.step_status.values())

    def test_multi_step_start_step(self):
        """Test starting a step."""
        steps = ["Step 1", "Step 2"]
        progress = MultiStepProgress(steps)
        progress.start_step("Step 1")
        assert progress.step_status["Step 1"] == "running"

    def test_multi_step_complete_step(self):
        """Test completing a step."""
        steps = ["Step 1", "Step 2"]
        progress = MultiStepProgress(steps)
        progress.complete_step("Step 1")
        assert progress.step_status["Step 1"] == "completed"

    def test_multi_step_fail_step(self):
        """Test failing a step."""
        steps = ["Step 1", "Step 2"]
        progress = MultiStepProgress(steps)
        progress.fail_step("Step 1")
        assert progress.step_status["Step 1"] == "failed"

    def test_multi_step_skip_step(self):
        """Test skipping a step."""
        steps = ["Step 1", "Step 2"]
        progress = MultiStepProgress(steps)
        progress.skip_step("Step 1")
        assert progress.step_status["Step 1"] == "skipped"


class TestShowBanner:
    """Tests for show_banner function."""

    def test_show_banner_outputs(self, capsys):
        """Test banner output."""
        show_banner()
        captured = capsys.readouterr()
        assert "CX" in captured.out or "██" in captured.out

    def test_show_banner_version(self, capsys):
        """Test banner includes version."""
        show_banner(show_version=True)
        captured = capsys.readouterr()
        assert "v" in captured.out or "0." in captured.out
