#!/usr/bin/env python3
"""Basic tests for Permission Auditor."""

import os
import sys
import tempfile

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

def test_imports():
    """Test that all required modules can be imported."""
    try:
        from auditor import (
            check_file_permissions,
            scan_directory,
            explain_issue,
            suggest_safe_permissions
        )
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_777_detection():
    """Test detection of 777 permissions."""
    from auditor import check_file_permissions
    
    # Create a temporary file with 777 permissions
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test")
        temp_path = f.name
    
    try:
    # SECURITY TEST: Intentionally setting dangerous permissions for testing
    # This file is in temp directory and will be deleted immediately
    # NOSONAR - This is a security test for the permission auditor
        os.chmod(temp_path, 0o777)
        
        result = check_file_permissions(temp_path)
        
        if result and result['issue'] == 'FULL_777':
            print(f"✅ 777 detection works: {temp_path}")
            return True
        else:
            print(f"❌ Failed to detect 777 on {temp_path}")
            return False
            
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def test_world_writable_detection():
    """Test detection of world-writable files."""
    from auditor import check_file_permissions
    
    # Create a temporary file with 666 permissions
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test")
        temp_path = f.name
    
    try:
    # SECURITY TEST: Intentionally setting dangerous permissions for testing
    # This file is in temp directory and will be deleted immediately
    # NOSONAR - This is a security test for the permission auditor
        os.chmod(temp_path, 0o666)
        
        result = check_file_permissions(temp_path)
        
        if result and result['issue'] == 'WORLD_WRITABLE':
            print(f"✅ World-writable detection works: {temp_path}")
            return True
        else:
            print(f"❌ Failed to detect world-writable on {temp_path}")
            return False
            
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def test_directory_scan():
    """Test directory scanning."""
    from auditor import scan_directory
    
    # Create a temporary directory with a 777 file
    temp_dir = tempfile.mkdtemp()
    test_file = os.path.join(temp_dir, "test-777.sh")
    
    try:
        with open(test_file, 'w') as f:
            f.write("#!/bin/bash\necho 'test'")
    # SECURITY TEST: Intentionally setting dangerous permissions for testing
    # This file is in temp directory and will be deleted immediately
    # NOSONAR - This is a security test for the permission auditor        
        os.chmod(test_file, 0o777)
        
        findings = scan_directory(temp_dir, recursive=True)
        
        if findings:
            print(f"✅ Directory scan found {len(findings)} issues")
            return True
        else:
            print(f"❌ Directory scan found no issues (expected at least 1)")
            return False
            
    finally:
        # Cleanup
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    print("Running basic tests...\n")
    
    tests = [
        test_imports,
        test_777_detection,
        test_world_writable_detection,
        test_directory_scan
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nBasic test results: {passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
