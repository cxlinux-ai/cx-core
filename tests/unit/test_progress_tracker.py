#!/usr/bin/env python3
"""
Tests for Progress Tracker module.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, MagicMock
from progress_tracker import (
    ProgressTracker, RichProgressTracker, ProgressStage,
    StageStatus, run_with_progress
)


class TestProgressStage:
    """Test ProgressStage class."""
    
    def test_stage_creation(self):
        """Test creating a progress stage."""
        stage = ProgressStage(name="Test Stage")
        assert stage.name == "Test Stage"
        assert stage.status == StageStatus.PENDING
        assert stage.progress == 0.0
        assert stage.start_time is None
        assert stage.end_time is None
    
    def test_stage_elapsed_time(self):
        """Test elapsed time calculation."""
        stage = ProgressStage(name="Test")
        assert stage.elapsed_time == 0.0
        
        stage.start_time = time.time()
        time.sleep(0.1)
        assert stage.elapsed_time > 0.09
        
        stage.end_time = stage.start_time + 1.5
        assert stage.elapsed_time == 1.5
    
    def test_stage_is_complete(self):
        """Test is_complete property."""
        stage = ProgressStage(name="Test")
        assert not stage.is_complete
        
        stage.status = StageStatus.IN_PROGRESS
        assert not stage.is_complete
        
        stage.status = StageStatus.COMPLETED
        assert stage.is_complete
        
        stage.status = StageStatus.FAILED
        assert stage.is_complete
        
        stage.status = StageStatus.CANCELLED
        assert stage.is_complete
    
    def test_format_elapsed(self):
        """Test elapsed time formatting."""
        stage = ProgressStage(name="Test")
        stage.start_time = time.time()
        
        # Less than 1 minute
        stage.end_time = stage.start_time + 30
        assert "30s" in stage.format_elapsed()
        
        # Minutes
        stage.end_time = stage.start_time + 125  # 2m 5s
        formatted = stage.format_elapsed()
        assert "2m" in formatted
        
        # Hours
        stage.end_time = stage.start_time + 7350  # 2h 2m
        formatted = stage.format_elapsed()
        assert "2h" in formatted


class TestProgressTracker:
    """Test ProgressTracker class."""
    
    def test_tracker_creation(self):
        """Test creating a progress tracker."""
        tracker = ProgressTracker("Test Operation")
        assert tracker.operation_name == "Test Operation"
        assert len(tracker.stages) == 0
        assert tracker.current_stage_index == -1
        assert not tracker.cancelled
    
    def test_add_stage(self):
        """Test adding stages."""
        tracker = ProgressTracker("Test")
        
        idx1 = tracker.add_stage("Stage 1")
        assert idx1 == 0
        assert len(tracker.stages) == 1
        assert tracker.stages[0].name == "Stage 1"
        
        idx2 = tracker.add_stage("Stage 2", total_bytes=1000)
        assert idx2 == 1
        assert tracker.stages[1].total_bytes == 1000
    
    def test_start_tracking(self):
        """Test starting progress tracking."""
        tracker = ProgressTracker("Test")
        tracker.start()
        
        assert tracker.start_time is not None
        assert tracker.start_time <= time.time()
    
    def test_start_stage(self):
        """Test starting a stage."""
        tracker = ProgressTracker("Test")
        idx = tracker.add_stage("Stage 1")
        
        tracker.start_stage(idx)
        
        assert tracker.current_stage_index == idx
        assert tracker.stages[idx].status == StageStatus.IN_PROGRESS
        assert tracker.stages[idx].start_time is not None
    
    def test_update_stage_progress(self):
        """Test updating stage progress."""
        tracker = ProgressTracker("Test")
        idx = tracker.add_stage("Stage 1", total_bytes=1000)
        tracker.start_stage(idx)
        
        # Update by progress value
        tracker.update_stage_progress(idx, progress=0.5)
        assert tracker.stages[idx].progress == 0.5
        
        # Update by bytes
        tracker.update_stage_progress(idx, processed_bytes=750)
        assert tracker.stages[idx].progress == 0.75
        assert tracker.stages[idx].processed_bytes == 750
    
    def test_complete_stage(self):
        """Test completing a stage."""
        tracker = ProgressTracker("Test")
        idx = tracker.add_stage("Stage 1")
        tracker.start_stage(idx)
        
        # Successful completion
        tracker.complete_stage(idx)
        assert tracker.stages[idx].status == StageStatus.COMPLETED
        assert tracker.stages[idx].progress == 1.0
        assert tracker.stages[idx].end_time is not None
        
        # Failed completion
        idx2 = tracker.add_stage("Stage 2")
        tracker.start_stage(idx2)
        tracker.complete_stage(idx2, error="Test error")
        assert tracker.stages[idx2].status == StageStatus.FAILED
        assert tracker.stages[idx2].error == "Test error"
    
    def test_overall_progress(self):
        """Test overall progress calculation."""
        tracker = ProgressTracker("Test")
        
        # No stages
        assert tracker.get_overall_progress() == 0.0
        
        # Add stages with different progress
        idx1 = tracker.add_stage("Stage 1")
        idx2 = tracker.add_stage("Stage 2")
        idx3 = tracker.add_stage("Stage 3")
        
        tracker.update_stage_progress(idx1, progress=1.0)  # Complete
        tracker.update_stage_progress(idx2, progress=0.5)  # Half done
        tracker.update_stage_progress(idx3, progress=0.0)  # Not started
        
        overall = tracker.get_overall_progress()
        assert overall == 0.5  # (1.0 + 0.5 + 0.0) / 3
    
    def test_estimate_remaining_time_no_data(self):
        """Test time estimation with no data."""
        tracker = ProgressTracker("Test")
        assert tracker.estimate_remaining_time() is None
        
        tracker.start()
        assert tracker.estimate_remaining_time() is None
    
    def test_estimate_remaining_time_with_progress(self):
        """Test time estimation with progress."""
        tracker = ProgressTracker("Test")
        tracker.start()
        
        # Add and complete one stage
        idx1 = tracker.add_stage("Stage 1")
        tracker.start_stage(idx1)
        time.sleep(0.1)
        tracker.complete_stage(idx1)
        
        # Add pending stages
        idx2 = tracker.add_stage("Stage 2")
        idx3 = tracker.add_stage("Stage 3")
        
        # Should estimate based on completed stage time
        estimate = tracker.estimate_remaining_time()
        assert estimate is not None
        assert estimate > 0
    
    def test_format_time_remaining(self):
        """Test time formatting."""
        tracker = ProgressTracker("Test")
        
        # No estimate yet
        formatted = tracker.format_time_remaining()
        assert formatted == "calculating..."
        
        # Mock estimate
        with patch.object(tracker, 'estimate_remaining_time', return_value=45):
            formatted = tracker.format_time_remaining()
            assert "45s" in formatted
        
        with patch.object(tracker, 'estimate_remaining_time', return_value=125):
            formatted = tracker.format_time_remaining()
            assert "2m" in formatted
        
        with patch.object(tracker, 'estimate_remaining_time', return_value=7350):
            formatted = tracker.format_time_remaining()
            assert "2h" in formatted
    
    def test_cancellation(self):
        """Test operation cancellation."""
        tracker = ProgressTracker("Test")
        
        idx1 = tracker.add_stage("Stage 1")
        idx2 = tracker.add_stage("Stage 2")
        
        tracker.start_stage(idx1)
        tracker.cancel("User cancelled")
        
        assert tracker.cancelled is True
        assert tracker.stages[idx1].status == StageStatus.CANCELLED
        assert tracker.stages[idx2].status == StageStatus.CANCELLED
    
    def test_cancel_callback(self):
        """Test cancel callback is called."""
        tracker = ProgressTracker("Test")
        callback_called = False
        
        def cancel_callback():
            nonlocal callback_called
            callback_called = True
        
        tracker.setup_cancellation_handler(callback=cancel_callback)
        tracker.cancel()
        
        assert callback_called
    
    def test_complete_operation(self):
        """Test completing the operation."""
        tracker = ProgressTracker("Test", enable_notifications=False)
        tracker.start()
        
        idx = tracker.add_stage("Stage 1")
        tracker.start_stage(idx)
        tracker.complete_stage(idx)
        
        tracker.complete(success=True, message="All done")
        
        assert tracker.end_time is not None
        assert tracker.stages[idx].status == StageStatus.COMPLETED
    
    def test_notifications_disabled_when_plyer_unavailable(self):
        """Test that notifications gracefully fail when plyer is unavailable."""
        with patch('progress_tracker.PLYER_AVAILABLE', False):
            tracker = ProgressTracker("Test", enable_notifications=True)
            # Should not raise an error
            tracker.complete(success=True)
    
    @patch('progress_tracker.PLYER_AVAILABLE', True)
    @patch('progress_tracker.plyer_notification')
    def test_notifications_sent(self, mock_notification):
        """Test that notifications are sent when enabled."""
        mock_notification.notify = Mock()
        
        tracker = ProgressTracker("Test", enable_notifications=True)
        tracker.start()
        tracker.complete(success=True, message="Done")
        
        # Should have sent a notification
        mock_notification.notify.assert_called_once()
        call_args = mock_notification.notify.call_args
        assert "Test Complete" in call_args[1]['title']
    
    def test_render_text_progress(self):
        """Test plain text progress rendering."""
        tracker = ProgressTracker("Test Operation", enable_notifications=False)
        tracker.add_stage("Stage 1")
        tracker.add_stage("Stage 2")
        
        text = tracker.render_text_progress()
        
        assert "Test Operation" in text
        assert "Stage 1" in text
        assert "Stage 2" in text
        assert "[ ]" in text  # Pending stages


@pytest.mark.asyncio
class TestAsyncProgress:
    """Test async progress tracking."""
    
    async def test_run_with_progress_success(self):
        """Test running async operation with progress."""
        async def test_operation(tracker):
            idx = tracker.add_stage("Test")
            tracker.start_stage(idx)
            await asyncio.sleep(0.1)
            tracker.complete_stage(idx)
            return "success"
        
        tracker = ProgressTracker("Test", enable_notifications=False)
        result = await run_with_progress(tracker, test_operation)
        
        assert result == "success"
        assert tracker.end_time is not None
    
    async def test_run_with_progress_failure(self):
        """Test async operation that fails."""
        async def test_operation(tracker):
            raise ValueError("Test error")
        
        tracker = ProgressTracker("Test", enable_notifications=False)
        
        with pytest.raises(ValueError):
            await run_with_progress(tracker, test_operation)
        
        assert tracker.end_time is not None
    
    async def test_run_with_progress_cancelled(self):
        """Test cancelling async operation."""
        async def test_operation(tracker):
            await asyncio.sleep(10)
        
        tracker = ProgressTracker("Test", enable_notifications=False)
        task = asyncio.create_task(run_with_progress(tracker, test_operation))
        
        await asyncio.sleep(0.1)
        task.cancel()
        
        with pytest.raises(asyncio.CancelledError):
            await task
        
        assert tracker.cancelled


class TestRichProgressTracker:
    """Test RichProgressTracker class."""
    
    def test_rich_tracker_requires_rich(self):
        """Test that RichProgressTracker requires rich library."""
        with patch('progress_tracker.RICH_AVAILABLE', False):
            with pytest.raises(ImportError):
                RichProgressTracker("Test")
    
    @patch('progress_tracker.RICH_AVAILABLE', True)
    def test_rich_tracker_creation(self):
        """Test creating a rich progress tracker."""
        with patch('progress_tracker.Console'):
            with patch('progress_tracker.Progress'):
                tracker = RichProgressTracker("Test")
                assert tracker.operation_name == "Test"
                assert tracker.progress_obj is None
    
    @pytest.mark.asyncio
    @patch('progress_tracker.RICH_AVAILABLE', True)
    async def test_live_progress_context(self):
        """Test live progress context manager."""
        with patch('progress_tracker.Console'):
            with patch('progress_tracker.Progress') as MockProgress:
                mock_progress = MagicMock()
                MockProgress.return_value = mock_progress
                mock_progress.__enter__ = Mock(return_value=mock_progress)
                mock_progress.__exit__ = Mock(return_value=False)
                mock_progress.add_task = Mock(return_value=1)
                
                tracker = RichProgressTracker("Test")
                tracker.add_stage("Stage 1")
                
                async with tracker.live_progress():
                    assert tracker.progress_obj is not None


class TestIntegration:
    """Integration tests."""
    
    @pytest.mark.asyncio
    async def test_multi_stage_operation(self):
        """Test a complete multi-stage operation."""
        tracker = ProgressTracker("Multi-Stage Test", enable_notifications=False)
        
        # Add stages
        download_idx = tracker.add_stage("Download", total_bytes=1000)
        install_idx = tracker.add_stage("Install")
        config_idx = tracker.add_stage("Configure")
        
        tracker.start()
        
        # Download stage
        tracker.start_stage(download_idx)
        for bytes_done in range(0, 1001, 200):
            tracker.update_stage_progress(download_idx, processed_bytes=bytes_done)
            await asyncio.sleep(0.01)
        tracker.complete_stage(download_idx)
        
        assert tracker.stages[download_idx].status == StageStatus.COMPLETED
        assert tracker.stages[download_idx].progress == 1.0
        
        # Install stage
        tracker.start_stage(install_idx)
        for i in range(10):
            tracker.update_stage_progress(install_idx, progress=(i + 1) / 10)
            await asyncio.sleep(0.01)
        tracker.complete_stage(install_idx)
        
        # Config stage
        tracker.start_stage(config_idx)
        tracker.update_stage_progress(config_idx, progress=1.0)
        tracker.complete_stage(config_idx)
        
        tracker.complete(success=True)
        
        # Verify overall progress
        assert tracker.get_overall_progress() == 1.0
        assert tracker.end_time is not None
    
    @pytest.mark.asyncio
    async def test_operation_with_failure(self):
        """Test operation that fails mid-way."""
        tracker = ProgressTracker("Failed Operation", enable_notifications=False)
        
        stage1_idx = tracker.add_stage("Stage 1")
        stage2_idx = tracker.add_stage("Stage 2")
        stage3_idx = tracker.add_stage("Stage 3")
        
        tracker.start()
        
        # Complete first stage
        tracker.start_stage(stage1_idx)
        tracker.complete_stage(stage1_idx)
        
        # Fail second stage
        tracker.start_stage(stage2_idx)
        tracker.update_stage_progress(stage2_idx, progress=0.3)
        tracker.complete_stage(stage2_idx, error="Installation failed")
        
        assert tracker.stages[stage2_idx].status == StageStatus.FAILED
        assert tracker.stages[stage3_idx].status == StageStatus.PENDING
        
        tracker.complete(success=False, message="Operation failed")
    
    def test_progress_percentage_boundaries(self):
        """Test that progress is clamped to 0-100%."""
        tracker = ProgressTracker("Test")
        idx = tracker.add_stage("Stage")
        
        # Test upper boundary
        tracker.update_stage_progress(idx, progress=1.5)
        assert tracker.stages[idx].progress == 1.0
        
        # Test lower boundary
        tracker.update_stage_progress(idx, progress=-0.5)
        assert tracker.stages[idx].progress == 0.0
    
    def test_time_estimation_accuracy(self):
        """Test that time estimation improves with more data."""
        tracker = ProgressTracker("Test")
        tracker.start()
        
        # Add 3 stages
        for i in range(3):
            idx = tracker.add_stage(f"Stage {i+1}")
        
        # Complete first stage in 0.2s
        tracker.start_stage(0)
        time.sleep(0.2)
        tracker.complete_stage(0)
        
        # Start second stage
        tracker.start_stage(1)
        tracker.update_stage_progress(1, progress=0.5)
        
        # Get estimate
        estimate = tracker.estimate_remaining_time()
        
        # Should have an estimate now
        assert estimate is not None
        # Should be roughly 0.1s (remaining in stage 2) + 0.2s (stage 3) = 0.3s
        # Allow for timing variations
        assert 0.1 < estimate < 1.0


class TestCancellationSupport:
    """Test cancellation and cleanup."""
    
    def test_cancel_pending_stages(self):
        """Test that pending stages are cancelled."""
        tracker = ProgressTracker("Test")
        
        idx1 = tracker.add_stage("Stage 1")
        idx2 = tracker.add_stage("Stage 2")
        idx3 = tracker.add_stage("Stage 3")
        
        tracker.start_stage(idx1)
        tracker.cancel()
        
        assert tracker.stages[idx1].status == StageStatus.CANCELLED
        assert tracker.stages[idx2].status == StageStatus.CANCELLED
        assert tracker.stages[idx3].status == StageStatus.CANCELLED
    
    def test_cleanup_callback_on_cancel(self):
        """Test that cleanup callback is called on cancel."""
        cleanup_called = False
        
        def cleanup():
            nonlocal cleanup_called
            cleanup_called = True
        
        tracker = ProgressTracker("Test")
        tracker.setup_cancellation_handler(callback=cleanup)
        tracker.cancel()
        
        assert cleanup_called


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_invalid_stage_index(self):
        """Test handling of invalid stage indices."""
        tracker = ProgressTracker("Test")
        tracker.add_stage("Stage 1")
        
        # Should not raise errors for invalid indices
        tracker.start_stage(999)
        tracker.update_stage_progress(999, progress=0.5)
        tracker.complete_stage(999)
    
    def test_empty_stages(self):
        """Test tracker with no stages."""
        tracker = ProgressTracker("Test")
        tracker.start()
        
        assert tracker.get_overall_progress() == 0.0
        assert tracker.estimate_remaining_time() is None
        
        tracker.complete(success=True)
        assert tracker.end_time is not None
    
    def test_render_without_rich(self):
        """Test rendering when rich is not available."""
        with patch('progress_tracker.RICH_AVAILABLE', False):
            tracker = ProgressTracker("Test")
            tracker.add_stage("Stage 1")
            
            text = tracker.render_text_progress()
            assert "Test" in text
            assert "Stage 1" in text


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

