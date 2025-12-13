#!/usr/bin/env python3
"""
Demo script showing progress tracker integration with cortex operations.
This demonstrates how to use ProgressTracker for real-world package installations.
"""

import sys
import os
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from progress_tracker import ProgressTracker, run_with_progress
from sandbox_executor import SandboxExecutor


async def demo_package_installation(tracker: ProgressTracker, package_name: str = "curl"):
    """
    Demo installation of a package with progress tracking.
    
    Args:
        tracker: ProgressTracker instance
        package_name: Package to install (default: curl, small and safe)
    """
    executor = SandboxExecutor()
    
    # Add installation stages
    update_idx = tracker.add_stage("Update package lists")
    download_idx = tracker.add_stage(f"Download {package_name}")
    install_idx = tracker.add_stage(f"Install {package_name}")
    verify_idx = tracker.add_stage("Verify installation")
    
    # Setup cancellation with cleanup
    def cleanup():
        print("\nCleaning up partial installation...")
        # In real implementation, remove partial downloads, rollback changes
    
    tracker.setup_cancellation_handler(callback=cleanup)
    
    try:
        # Stage 1: Update package lists
        tracker.start_stage(update_idx)
        
        # Simulate progress for update
        for i in range(10):
            tracker.update_stage_progress(update_idx, progress=(i + 1) / 10)
            tracker.display_progress()
            await asyncio.sleep(0.2)
        
        # Execute actual update in dry-run mode for demo
        result = executor.execute("apt-get update", dry_run=True)
        
        if result.success:
            tracker.complete_stage(update_idx)
        else:
            tracker.complete_stage(update_idx, error="Failed to update package lists")
            tracker.complete(success=False, message="Installation aborted")
            return
        
        # Stage 2: Download package
        tracker.start_stage(download_idx)
        
        # Simulate download with byte tracking
        total_bytes = 2_500_000  # Simulated 2.5MB download
        bytes_downloaded = 0
        chunk_size = 250_000  # 250KB chunks
        
        while bytes_downloaded < total_bytes:
            await asyncio.sleep(0.15)
            bytes_downloaded = min(bytes_downloaded + chunk_size, total_bytes)
            tracker.update_stage_progress(
                download_idx,
                progress=bytes_downloaded / total_bytes
            )
            tracker.display_progress()
        
        tracker.complete_stage(download_idx)
        
        # Stage 3: Install package
        tracker.start_stage(install_idx)
        
        # Simulate installation process
        for i in range(15):
            tracker.update_stage_progress(install_idx, progress=(i + 1) / 15)
            tracker.display_progress()
            await asyncio.sleep(0.15)
        
        # Execute install in dry-run
        result = executor.execute(f"apt-get install -y {package_name}", dry_run=True)
        
        if result.success:
            tracker.complete_stage(install_idx)
        else:
            tracker.complete_stage(install_idx, error="Installation failed")
            tracker.complete(success=False)
            return
        
        # Stage 4: Verify installation
        tracker.start_stage(verify_idx)
        
        for i in range(5):
            tracker.update_stage_progress(verify_idx, progress=(i + 1) / 5)
            tracker.display_progress()
            await asyncio.sleep(0.1)
        
        tracker.complete_stage(verify_idx)
        
    except Exception as e:
        tracker.complete(success=False, message=f"Error: {str(e)}")
        raise


async def demo_multi_package_installation(tracker: ProgressTracker):
    """Demo installing multiple packages."""
    packages = ["git", "curl", "wget"]
    
    for pkg in packages:
        update_idx = tracker.add_stage(f"Update lists for {pkg}")
        download_idx = tracker.add_stage(f"Download {pkg}")
        install_idx = tracker.add_stage(f"Install {pkg}")
        
    current_stage = 0
    for pkg in packages:
        # Update
        tracker.start_stage(current_stage)
        await asyncio.sleep(0.3)
        tracker.complete_stage(current_stage)
        current_stage += 1
        
        # Download
        tracker.start_stage(current_stage)
        for i in range(10):
            tracker.update_stage_progress(current_stage, progress=(i + 1) / 10)
            tracker.display_progress()
            await asyncio.sleep(0.1)
        tracker.complete_stage(current_stage)
        current_stage += 1
        
        # Install
        tracker.start_stage(current_stage)
        for i in range(8):
            tracker.update_stage_progress(current_stage, progress=(i + 1) / 8)
            tracker.display_progress()
            await asyncio.sleep(0.1)
        tracker.complete_stage(current_stage)
        current_stage += 1


async def demo_failed_installation(tracker: ProgressTracker):
    """Demo handling of failed installation."""
    download_idx = tracker.add_stage("Download package")
    install_idx = tracker.add_stage("Install package")
    verify_idx = tracker.add_stage("Verify")
    
    # Success
    tracker.start_stage(download_idx)
    tracker.update_stage_progress(download_idx, progress=1.0)
    tracker.complete_stage(download_idx)
    
    # Failure
    tracker.start_stage(install_idx)
    tracker.update_stage_progress(install_idx, progress=0.3)
    await asyncio.sleep(0.5)
    tracker.complete_stage(install_idx, error="Dependency conflict detected")
    
    # Abort remaining
    tracker.complete(success=False, message="Installation failed: dependency conflict")


async def main():
    """Main demo function."""
    print("=" * 60)
    print("Cortex Linux - Progress Tracker Demo")
    print("=" * 60)
    print("\nThis demo shows different progress tracking scenarios.")
    print("Press Ctrl+C at any time to test cancellation handling.\n")
    
    # Demo 1: Single package installation
    print("\n[Demo 1] Single Package Installation")
    print("-" * 60)
    tracker1 = ProgressTracker(
        "Installing PostgreSQL",
        enable_notifications=True
    )
    await run_with_progress(tracker1, demo_package_installation, package_name="postgresql")
    
    await asyncio.sleep(2)
    
    # Demo 2: Multiple packages
    print("\n\n[Demo 2] Multiple Package Installation")
    print("-" * 60)
    tracker2 = ProgressTracker(
        "Installing Development Tools",
        enable_notifications=False  # Disable notifications for demo
    )
    await run_with_progress(tracker2, demo_multi_package_installation)
    
    await asyncio.sleep(2)
    
    # Demo 3: Failed installation
    print("\n\n[Demo 3] Handling Failures")
    print("-" * 60)
    tracker3 = ProgressTracker(
        "Installing Problematic Package",
        enable_notifications=False
    )
    
    try:
        await run_with_progress(tracker3, demo_failed_installation)
    except Exception:
        pass  # Expected to fail
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDemo cancelled by user.")
        sys.exit(0)

