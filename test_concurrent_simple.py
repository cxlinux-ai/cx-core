#!/usr/bin/env python3
"""Quick test for multi-process snapshot creation."""

import subprocess
import time

def test_concurrent_snapshots():
    """Test creating snapshots concurrently"""
    print("🧪 Testing concurrent snapshot creation (3 processes)...")
    print("=" * 60)
    
    # Start 3 processes in background
    processes = []
    start_time = time.time()
    
    for i in range(1, 4):
        proc = subprocess.Popen(
            ["cortex", "snapshot", "create", f"Test {i}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        processes.append((i, proc))
        print(f"📤 Started process {i}")
    
    # Wait for all to complete
    results = []
    for i, proc in processes:
        stdout, stderr = proc.communicate(timeout=60)
        results.append({
            "id": i,
            "code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr
        })
    
    elapsed = time.time() - start_time
    
    # Check results
    print(f"\n⏱️  Completed in {elapsed:.2f}s\n")
    
    errors = []
    for r in results:
        failed = False
        if r["code"] == 0:
            print(f"✅ Process {r['id']}: SUCCESS")
        else:
            print(f"❌ Process {r['id']}: FAILED (code {r['code']})")
            failed = True
        
        # Check for JSON corruption
        if "Expecting property name" in r["stderr"] or "Expecting ',' delimiter" in r["stderr"]:
            print(f"   🚨 JSON CORRUPTION DETECTED!")
            failed = True
        
        # Add to errors only once if any failure detected
        if failed:
            errors.append(r)
    
    print("\n" + "=" * 60)
    if errors:
        print(f"❌ TEST FAILED: {len(errors)} errors detected")
        for err in errors:
            if err.get("stderr"):
                print(f"\nProcess {err['id']} stderr:")
                print(err["stderr"][:300])
        return False
    else:
        print("✅ TEST PASSED: All snapshots created successfully")
        return True

if __name__ == "__main__":
    try:
        success = test_concurrent_snapshots()
        exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
