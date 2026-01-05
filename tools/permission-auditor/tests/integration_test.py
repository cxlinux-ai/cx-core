"""Integration tests for Permission Auditor."""

import os
import tempfile
import subprocess
import stat

def test_777_file():
    """Test detection of 777 file permissions."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test")
        temp_path = f.name
    
    try:
    # SECURITY TEST: Intentionally setting dangerous permissions for testing
    # This file is in temp directory and will be deleted immediately
    # NOSONAR - This is a security test for the permission auditor
        os.chmod(temp_path, 0o777)
        
        # Run auditor
        result = subprocess.run(
            ['python3', 'src/auditor.py', temp_path, '--fix'],
            capture_output=True,
            text=True
        )
        
        assert "CRITICAL" in result.stdout
        assert "777" in result.stdout
        print("✅ test_777_file: PASSED")
        return True
        
    finally:
        os.unlink(temp_path)
    
    print("❌ test_777_file: FAILED")
    return False

def test_world_writable():
    """Test detection of world-writable files."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test")
        temp_path = f.name
    
    try:
    # SECURITY TEST: Intentionally setting dangerous permissions for testing
    # This file is in temp directory and will be deleted immediately
    # NOSONAR - This is a security test for the permission auditor
        os.chmod(temp_path, 0o666)
        
        result = subprocess.run(
            ['python3', 'src/auditor.py', temp_path, '--fix'],
            capture_output=True,
            text=True
        )
        
        assert "HIGH" in result.stdout or "WORLD_WRITABLE" in result.stdout
        print("✅ test_world_writable: PASSED")
        return True
        
    finally:
        os.unlink(temp_path)
    
    print("❌ test_world_writable: FAILED")
    return False

if __name__ == "__main__":
    print("Running integration tests...\n")
    
    tests = [test_777_file, test_world_writable]
    passed = 0
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nResults: {passed}/{len(tests)} tests passed")
    exit(0 if passed == len(tests) else 1)
