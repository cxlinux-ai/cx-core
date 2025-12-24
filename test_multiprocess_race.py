#!/usr/bin/env python3
"""Test multi-process race condition fix for snapshot manager."""

import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

def create_snapshot(index):
    """Create a snapshot in a separate process"""
    try:
        result = subprocess.run(
            ["cortex", "snapshot", "create", f"Race test {index}"],
            capture_output=True,
            text=True,
            timeout=60
        )
        return {
            "index": index,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
    except Exception as e:
        return {
            "index": index,
            "error": str(e),
            "success": False
        }

def main():
    """Run multiple cortex snapshot create commands in parallel"""
    print("=" * 70)
    print("Multi-Process Race Condition Test")
    print("=" * 70)
    print("\n🔄 Creating 5 snapshots concurrently (separate processes)...\n")
    
    start_time = time.time()
    
    # Run 5 snapshot creations in parallel (separate processes)
    with ProcessPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(create_snapshot, i) for i in range(1, 6)]
        
        results = []
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            
            if result["success"]:
                print(f"✅ Snapshot {result['index']} created successfully")
            else:
                print(f"❌ Snapshot {result['index']} FAILED")
                if "error" in result:
                    print(f"   Error: {result['error']}")
                else:
                    print(f"   Return code: {result['returncode']}")
                    if result.get("stderr"):
                        print(f"   Stderr: {result['stderr'][:200]}")
    
    elapsed = time.time() - start_time
    
    # Summary
    print(f"\n{'=' * 70}")
    print(f"⏱️  Total time: {elapsed:.2f}s")
    
    success_count = sum(1 for r in results if r["success"])
    print(f"✅ Successful: {success_count}/5")
    print(f"❌ Failed: {5 - success_count}/5")
    
    # Check for JSON corruption errors
    json_errors = []
    for result in results:
        stderr = result.get("stderr", "")
        if "Expecting property name" in stderr or "Expecting ',' delimiter" in stderr:
            json_errors.append(result["index"])
    
    if json_errors:
        print(f"\n⚠️  JSON CORRUPTION detected in snapshots: {json_errors}")
        print("❌ TEST FAILED: Race condition still exists")
        return 1
    elif success_count == 5:
        print("\n✅ TEST PASSED: All snapshots created without corruption")
        return 0
    else:
        print(f"\n⚠️  TEST INCOMPLETE: {5 - success_count} snapshots failed (check errors above)")
        return 1

if __name__ == "__main__":
    sys.exit(main())
