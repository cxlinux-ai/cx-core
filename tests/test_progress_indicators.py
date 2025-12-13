"""
Tests for Progress Indicators Module

Issue: #259
"""

import pytest
import time
import io
import sys
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from cortex.progress_indicators import (
    ProgressIndicator,
    OperationType,
    OperationStep,
    OperationContext,
    FallbackProgress,
    DownloadTracker,
    MultiStepTracker,
    get_progress_indicator,
    spinner,
    operation,
    progress_bar,
    RICH_AVAILABLE
)


class TestOperationStep:
    """Tests for OperationStep dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        step = OperationStep(name="Test", description="Test step")
        
        assert step.name == "Test"
        assert step.description == "Test step"
        assert step.status == "pending"
        assert step.progress == 0.0
        assert step.start_time is None
        assert step.end_time is None
    
    def test_duration_not_started(self):
        """Test duration when not started."""
        step = OperationStep(name="Test", description="Test")
        assert step.duration_seconds is None
    
    def test_duration_running(self):
        """Test duration while running."""
        step = OperationStep(name="Test", description="Test")
        step.start_time = datetime.now()
        
        time.sleep(0.1)
        
        assert step.duration_seconds is not None
        assert step.duration_seconds >= 0.1
    
    def test_duration_completed(self):
        """Test duration after completion."""
        step = OperationStep(name="Test", description="Test")
        step.start_time = datetime.now()
        time.sleep(0.1)
        step.end_time = datetime.now()
        
        duration = step.duration_seconds
        assert duration is not None
        assert 0.1 <= duration < 0.5


class TestOperationContext:
    """Tests for OperationContext dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        context = OperationContext(
            operation_type=OperationType.INSTALL,
            title="Test Operation"
        )
        
        assert context.operation_type == OperationType.INSTALL
        assert context.title == "Test Operation"
        assert context.steps == []
        assert context.current_step == 0
        assert context.status == "running"
    
    def test_total_steps(self):
        """Test total_steps property."""
        context = OperationContext(
            operation_type=OperationType.INSTALL,
            title="Test",
            steps=[
                OperationStep("Step1", "First"),
                OperationStep("Step2", "Second"),
            ]
        )
        
        assert context.total_steps == 2
    
    def test_completed_steps(self):
        """Test completed_steps property."""
        context = OperationContext(
            operation_type=OperationType.INSTALL,
            title="Test",
            steps=[
                OperationStep("Step1", "First", status="completed"),
                OperationStep("Step2", "Second", status="running"),
                OperationStep("Step3", "Third", status="pending"),
            ]
        )
        
        assert context.completed_steps == 1
    
    def test_overall_progress(self):
        """Test overall_progress property."""
        context = OperationContext(
            operation_type=OperationType.INSTALL,
            title="Test",
            steps=[
                OperationStep("Step1", "First", status="completed"),
                OperationStep("Step2", "Second", status="completed"),
                OperationStep("Step3", "Third", status="pending"),
                OperationStep("Step4", "Fourth", status="pending"),
            ]
        )
        
        assert context.overall_progress == 0.5
    
    def test_overall_progress_empty(self):
        """Test overall_progress with no steps."""
        context = OperationContext(
            operation_type=OperationType.INSTALL,
            title="Test"
        )
        
        assert context.overall_progress == 0.0


class TestFallbackProgress:
    """Tests for FallbackProgress class."""
    
    def test_start_and_stop(self, capsys):
        """Test starting and stopping progress."""
        progress = FallbackProgress()
        progress.start("Loading")
        time.sleep(0.2)
        progress.stop("Complete")
        
        captured = capsys.readouterr()
        assert "Complete" in captured.out
    
    def test_update(self, capsys):
        """Test updating message."""
        progress = FallbackProgress()
        progress.start("Initial")
        progress.update("Updated")
        time.sleep(0.2)
        progress.stop()
        
        # Should complete without error
        assert True
    
    def test_fail(self, capsys):
        """Test failure indication."""
        progress = FallbackProgress()
        progress.start("Working")
        progress.fail("Error occurred")
        
        captured = capsys.readouterr()
        assert "Error occurred" in captured.out


class TestProgressIndicator:
    """Tests for main ProgressIndicator class."""
    
    @pytest.fixture
    def indicator(self):
        """Create indicator without Rich for testing."""
        return ProgressIndicator(use_rich=False)
    
    def test_init_without_rich(self, indicator):
        """Test initialization without Rich."""
        assert indicator.use_rich is False
        assert indicator.console is None
    
    def test_operation_icons(self):
        """Test that all operation types have icons."""
        for op_type in OperationType:
            assert op_type in ProgressIndicator.OPERATION_ICONS
    
    def test_status_colors(self):
        """Test that all statuses have colors."""
        expected_statuses = ["pending", "running", "completed", "failed", "skipped"]
        for status in expected_statuses:
            assert status in ProgressIndicator.STATUS_COLORS
    
    def test_operation_context_manager(self, indicator, capsys):
        """Test operation context manager."""
        with indicator.operation("Test Operation", OperationType.INSTALL) as op:
            op.update("Working...")
            op.complete("Finished")
        
        captured = capsys.readouterr()
        assert "Finished" in captured.out
    
    def test_operation_with_failure(self, indicator, capsys):
        """Test operation that fails."""
        with indicator.operation("Test Operation") as op:
            op.fail("Something went wrong")
        
        captured = capsys.readouterr()
        assert "went wrong" in captured.out
    
    def test_spinner_context_manager(self, indicator, capsys):
        """Test spinner context manager."""
        with indicator.spinner("Loading..."):
            time.sleep(0.2)
        
        # Should complete without error
        assert True
    
    def test_progress_bar_iteration(self, indicator):
        """Test progress bar iteration."""
        items = [1, 2, 3, 4, 5]
        result = []
        
        for item in indicator.progress_bar(items, "Processing"):
            result.append(item)
        
        assert result == items
    
    def test_progress_bar_empty(self, indicator):
        """Test progress bar with empty list."""
        items = []
        result = list(indicator.progress_bar(items, "Processing"))
        assert result == []
    
    def test_print_success(self, indicator, capsys):
        """Test success message printing."""
        indicator.print_success("Operation successful")
        
        captured = capsys.readouterr()
        assert "successful" in captured.out
        assert "✓" in captured.out
    
    def test_print_error(self, indicator, capsys):
        """Test error message printing."""
        indicator.print_error("Operation failed")
        
        captured = capsys.readouterr()
        assert "failed" in captured.out
        assert "✗" in captured.out
    
    def test_print_warning(self, indicator, capsys):
        """Test warning message printing."""
        indicator.print_warning("Be careful")
        
        captured = capsys.readouterr()
        assert "careful" in captured.out
        assert "⚠" in captured.out
    
    def test_print_info(self, indicator, capsys):
        """Test info message printing."""
        indicator.print_info("For your information")
        
        captured = capsys.readouterr()
        assert "information" in captured.out
        assert "ℹ" in captured.out


class TestDownloadTracker:
    """Tests for DownloadTracker class."""
    
    @pytest.fixture
    def indicator(self):
        return ProgressIndicator(use_rich=False)
    
    def test_init(self, indicator):
        """Test tracker initialization."""
        tracker = DownloadTracker(indicator, 1000, "Test Download")
        
        assert tracker.total_bytes == 1000
        assert tracker.downloaded == 0
        assert tracker.description == "Test Download"
    
    def test_update_progress(self, indicator):
        """Test updating download progress."""
        tracker = DownloadTracker(indicator, 1000, "Test")
        
        tracker.update(100)
        assert tracker.downloaded == 100
        
        tracker.update(200)
        assert tracker.downloaded == 300
    
    def test_complete(self, indicator, capsys):
        """Test download completion."""
        tracker = DownloadTracker(indicator, 1000, "Test")
        tracker.update(1000)
        tracker.complete()
        
        captured = capsys.readouterr()
        assert "Downloaded" in captured.out or "✓" in captured.out
    
    def test_fail(self, indicator, capsys):
        """Test download failure."""
        tracker = DownloadTracker(indicator, 1000, "Test")
        tracker.update(500)
        tracker.fail("Connection lost")
        
        captured = capsys.readouterr()
        assert "failed" in captured.out or "Connection lost" in captured.out


class TestMultiStepTracker:
    """Tests for MultiStepTracker class."""
    
    @pytest.fixture
    def indicator(self):
        return ProgressIndicator(use_rich=False)
    
    @pytest.fixture
    def steps(self):
        return [
            {"name": "Step 1", "description": "First step"},
            {"name": "Step 2", "description": "Second step"},
            {"name": "Step 3", "description": "Third step"},
        ]
    
    def test_init(self, indicator, steps):
        """Test tracker initialization."""
        tracker = MultiStepTracker(indicator, steps, "Test Operation")
        
        assert len(tracker.steps) == 3
        assert tracker.title == "Test Operation"
        assert tracker.current_step == -1
    
    def test_start_step(self, indicator, steps, capsys):
        """Test starting a step."""
        tracker = MultiStepTracker(indicator, steps, "Test")
        tracker.start_step(0)
        
        assert tracker.steps[0].status == "running"
        assert tracker.steps[0].start_time is not None
        assert tracker.current_step == 0
    
    def test_complete_step(self, indicator, steps, capsys):
        """Test completing a step."""
        tracker = MultiStepTracker(indicator, steps, "Test")
        tracker.start_step(0)
        time.sleep(0.1)
        tracker.complete_step(0)
        
        assert tracker.steps[0].status == "completed"
        assert tracker.steps[0].end_time is not None
        assert tracker.steps[0].progress == 1.0
    
    def test_fail_step(self, indicator, steps, capsys):
        """Test failing a step."""
        tracker = MultiStepTracker(indicator, steps, "Test")
        tracker.start_step(0)
        tracker.fail_step(0, "Something broke")
        
        assert tracker.steps[0].status == "failed"
        assert tracker.steps[0].error_message == "Something broke"
    
    def test_skip_step(self, indicator, steps, capsys):
        """Test skipping a step."""
        tracker = MultiStepTracker(indicator, steps, "Test")
        tracker.skip_step(1, "Not needed")
        
        assert tracker.steps[1].status == "skipped"
    
    def test_finish_all_completed(self, indicator, steps, capsys):
        """Test finishing with all steps completed."""
        tracker = MultiStepTracker(indicator, steps, "Test")
        
        for i in range(3):
            tracker.start_step(i)
            tracker.complete_step(i)
        
        tracker.finish()
        
        captured = capsys.readouterr()
        assert "3/3" in captured.out
    
    def test_finish_with_failure(self, indicator, steps, capsys):
        """Test finishing with some failures."""
        tracker = MultiStepTracker(indicator, steps, "Test")
        
        tracker.start_step(0)
        tracker.complete_step(0)
        
        tracker.start_step(1)
        tracker.fail_step(1, "Error")
        
        tracker.finish()
        
        captured = capsys.readouterr()
        assert "1/3" in captured.out or "failed" in captured.out
    
    def test_out_of_bounds_step(self, indicator, steps):
        """Test handling out of bounds step index."""
        tracker = MultiStepTracker(indicator, steps, "Test")
        
        # Should not raise
        tracker.start_step(99)
        tracker.complete_step(-1)
        tracker.fail_step(100)


class TestGlobalFunctions:
    """Tests for module-level convenience functions."""
    
    def test_get_progress_indicator_singleton(self):
        """Test that get_progress_indicator returns singleton."""
        indicator1 = get_progress_indicator()
        indicator2 = get_progress_indicator()
        
        assert indicator1 is indicator2
    
    def test_spinner_convenience(self):
        """Test spinner convenience function."""
        ctx = spinner("Test")
        assert ctx is not None
    
    def test_operation_convenience(self):
        """Test operation convenience function."""
        ctx = operation("Test", OperationType.INSTALL)
        assert ctx is not None
    
    def test_progress_bar_convenience(self):
        """Test progress_bar convenience function."""
        items = [1, 2, 3]
        result = list(progress_bar(items, "Test"))
        assert result == items


class TestOperationTypes:
    """Tests for OperationType enum."""
    
    def test_all_operation_types(self):
        """Test all operation types are defined."""
        expected = [
            "INSTALL", "REMOVE", "UPDATE", "DOWNLOAD",
            "CONFIGURE", "VERIFY", "ANALYZE", "LLM_QUERY",
            "DEPENDENCY_RESOLVE", "ROLLBACK", "GENERIC"
        ]
        
        actual = [op.name for op in OperationType]
        
        for expected_op in expected:
            assert expected_op in actual
    
    def test_operation_type_values(self):
        """Test operation type values are strings."""
        for op_type in OperationType:
            assert isinstance(op_type.value, str)


class TestEdgeCases:
    """Tests for edge cases."""
    
    @pytest.fixture
    def indicator(self):
        return ProgressIndicator(use_rich=False)
    
    def test_empty_operation_title(self, indicator):
        """Test operation with empty title."""
        with indicator.operation("") as op:
            op.complete()
        # Should complete without error
    
    def test_operation_exception(self, indicator):
        """Test operation that raises exception."""
        with pytest.raises(ValueError):
            with indicator.operation("Test") as op:
                raise ValueError("Test error")
    
    def test_nested_operations(self, indicator):
        """Test nested operations."""
        with indicator.operation("Outer") as outer:
            outer.update("Starting inner")
            with indicator.operation("Inner") as inner:
                inner.complete()
            outer.complete()
        # Should complete without error
    
    def test_very_long_message(self, indicator, capsys):
        """Test with very long message."""
        long_message = "x" * 1000
        indicator.print_info(long_message)
        
        captured = capsys.readouterr()
        assert long_message in captured.out
    
    def test_unicode_messages(self, indicator, capsys):
        """Test with unicode characters."""
        indicator.print_info("日本語テスト 🎉 émojis")
        
        captured = capsys.readouterr()
        assert "日本語" in captured.out


@pytest.mark.skipif(not RICH_AVAILABLE, reason="Rich not installed")
class TestRichIntegration:
    """Tests for Rich library integration."""
    
    def test_rich_indicator_init(self):
        """Test initialization with Rich."""
        indicator = ProgressIndicator(use_rich=True)
        
        assert indicator.use_rich is True
        assert indicator.console is not None
    
    def test_rich_spinner(self):
        """Test Rich spinner."""
        indicator = ProgressIndicator(use_rich=True)
        
        with indicator.spinner("Testing Rich spinner"):
            time.sleep(0.1)
        # Should complete without error
    
    def test_rich_operation(self):
        """Test Rich operation display."""
        indicator = ProgressIndicator(use_rich=True)
        
        with indicator.operation("Testing Rich", OperationType.INSTALL) as op:
            op.update("Working...")
            time.sleep(0.1)
            op.complete("Done!")
        # Should complete without error
    
    def test_rich_progress_bar(self):
        """Test Rich progress bar."""
        indicator = ProgressIndicator(use_rich=True)
        
        items = list(range(5))
        result = list(indicator.progress_bar(items, "Rich progress"))
        
        assert result == items


class TestIntegration:
    """Integration tests for progress indicators."""
    
    @pytest.fixture
    def indicator(self):
        return ProgressIndicator(use_rich=False)
    
    def test_full_installation_flow(self, indicator, capsys):
        """Test a complete installation flow."""
        # Create multi-step tracker
        tracker = indicator.multi_step([
            {"name": "Download", "description": "Downloading package"},
            {"name": "Verify", "description": "Verifying checksum"},
            {"name": "Install", "description": "Installing files"},
            {"name": "Configure", "description": "Configuring service"},
        ], "Installing nginx")
        
        # Simulate installation
        for i in range(4):
            tracker.start_step(i)
            time.sleep(0.05)
            tracker.complete_step(i)
        
        tracker.finish()
        
        captured = capsys.readouterr()
        assert "4/4" in captured.out
    
    def test_download_then_install(self, indicator, capsys):
        """Test download followed by installation."""
        # Download phase
        download_tracker = indicator.download_progress(1000, "Downloading")
        for _ in range(10):
            download_tracker.update(100)
        download_tracker.complete()
        
        # Install phase
        with indicator.operation("Installing", OperationType.INSTALL) as op:
            op.update("Extracting...")
            op.update("Configuring...")
            op.complete()
        
        captured = capsys.readouterr()
        assert "Downloaded" in captured.out or "✓" in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
