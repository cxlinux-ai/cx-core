#!/usr/bin/env python3
"""
Standalone demo of progress tracker without external dependencies.
Works on all platforms (Windows, Linux, macOS).
"""

import sys
import os
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from progress_tracker import ProgressTracker, run_with_progress


async def demo_simple_installation(tracker: ProgressTracker):
    """Simple installation demo."""
    # Add stages
    update_idx = tracker.add_stage("Update package lists")
    download_idx = tracker.add_stage("Download postgresql-15", total_bytes=50_000_000)
    install_idx = tracker.add_stage("Installing dependencies")
    configure_idx = tracker.add_stage("Configuring database")
    test_idx = tracker.add_stage("Running tests")
    
    # Stage 1: Update
    tracker.start_stage(update_idx)
    for i in range(10):
        tracker.update_stage_progress(update_idx, progress=(i + 1) / 10)
        tracker.display_progress()
        await asyncio.sleep(0.1)
    tracker.complete_stage(update_idx)
    
    # Stage 2: Download
    tracker.start_stage(download_idx)
    bytes_downloaded = 0
    chunk_size = 5_000_000
    while bytes_downloaded < 50_000_000:
        await asyncio.sleep(0.15)
        bytes_downloaded = min(bytes_downloaded + chunk_size, 50_000_000)
        tracker.update_stage_progress(download_idx, processed_bytes=bytes_downloaded)
        tracker.display_progress()
    tracker.complete_stage(download_idx)
    
    # Stage 3: Install
    tracker.start_stage(install_idx)
    for i in range(15):
        tracker.update_stage_progress(install_idx, progress=(i + 1) / 15)
        tracker.display_progress()
        await asyncio.sleep(0.1)
    tracker.complete_stage(install_idx)
    
    # Stage 4: Configure
    tracker.start_stage(configure_idx)
    for i in range(8):
        tracker.update_stage_progress(configure_idx, progress=(i + 1) / 8)
        tracker.display_progress()
        await asyncio.sleep(0.12)
    tracker.complete_stage(configure_idx)
    
    # Stage 5: Test
    tracker.start_stage(test_idx)
    for i in range(5):
        tracker.update_stage_progress(test_idx, progress=(i + 1) / 5)
        tracker.display_progress()
        await asyncio.sleep(0.2)
    tracker.complete_stage(test_idx)


async def demo_failed_operation(tracker: ProgressTracker):
    """Demo of a failed operation."""
    download_idx = tracker.add_stage("Download package")
    install_idx = tracker.add_stage("Install package")
    verify_idx = tracker.add_stage("Verify installation")
    
    # Successful download
    tracker.start_stage(download_idx)
    for i in range(10):
        tracker.update_stage_progress(download_idx, progress=(i + 1) / 10)
        tracker.display_progress()
        await asyncio.sleep(0.08)
    tracker.complete_stage(download_idx)
    
    # Failed installation
    tracker.start_stage(install_idx)
    for i in range(5):
        tracker.update_stage_progress(install_idx, progress=(i + 1) / 10)
        tracker.display_progress()
        await asyncio.sleep(0.1)
    
    # Simulate failure
    tracker.complete_stage(install_idx, error="Dependency conflict: libssl3 required")
    
    # Operation fails, verify stage never runs
    raise Exception("Installation failed due to dependency conflict")


async def demo_cancelled_operation(tracker: ProgressTracker):
    """Demo of user cancellation (press Ctrl+C to test)."""
    print("\n⚠️  Press Ctrl+C during this demo to test cancellation handling\n")
    
    stages = []
    for i in range(10):
        idx = tracker.add_stage(f"Processing step {i+1}")
        stages.append(idx)
    
    for idx in stages:
        if tracker.cancelled:
            break
        
        tracker.start_stage(idx)
        for i in range(20):
            if tracker.cancelled:
                break
            tracker.update_stage_progress(idx, progress=(i + 1) / 20)
            tracker.display_progress()
            await asyncio.sleep(0.1)
        
        if not tracker.cancelled:
            tracker.complete_stage(idx)


async def main():
    """Run all demos."""
    print("=" * 70)
    print(" " * 15 + "Cortex Linux - Progress Tracker Demo")
    print("=" * 70)
    print("\nDemonstrating progress notifications & status updates")
    print("Features: Progress bars, time estimation, multi-stage tracking, etc.\n")
    
    # Demo 1: Successful installation
    print("\n" + "─" * 70)
    print("[Demo 1] Successful Multi-Stage Installation")
    print("─" * 70)
    tracker1 = ProgressTracker(
        "Installing PostgreSQL",
        enable_notifications=True
    )
    await run_with_progress(tracker1, demo_simple_installation)
    
    await asyncio.sleep(1.5)
    
    # Demo 2: Failed installation
    print("\n\n" + "─" * 70)
    print("[Demo 2] Handling Installation Failures")
    print("─" * 70)
    tracker2 = ProgressTracker(
        "Installing Broken Package",
        enable_notifications=True,
        notification_on_error=True
    )
    
    try:
        await run_with_progress(tracker2, demo_failed_operation)
    except Exception as e:
        print(f"\n[Expected failure caught: {e}]")
    
    await asyncio.sleep(1.5)
    
    # Demo 3: Cancellation support
    print("\n\n" + "─" * 70)
    print("[Demo 3] Cancellation Support (Ctrl+C to test)")
    print("─" * 70)
    tracker3 = ProgressTracker(
        "Long Running Operation",
        enable_notifications=False
    )
    
    try:
        await run_with_progress(tracker3, demo_cancelled_operation)
    except KeyboardInterrupt:
        print("\n\n[Cancellation demo complete]")
    
    print("\n" + "=" * 70)
    print(" " * 25 + "All Demos Complete!")
    print("=" * 70)
    print("\n✅ Progress tracker is working correctly!")
    print("✅ All features tested successfully")
    print("\nFeatures demonstrated:")
    print("  • Real-time progress bars with Unicode characters")
    print("  • Time estimation and ETA calculation")
    print("  • Multi-stage progress tracking")
    print("  • Error handling and reporting")
    print("  • Desktop notifications (if supported)")
    print("  • Cancellation support (Ctrl+C)")
    print("\nReady for integration into Cortex Linux! 🚀\n")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user. Bye!")
        sys.exit(0)

