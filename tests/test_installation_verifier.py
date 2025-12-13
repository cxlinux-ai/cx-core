#!/usr/bin/env python3
"""
Tests for Installation Verification System
"""

import unittest
from installation_verifier import (
    InstallationVerifier,
    VerificationStatus,
    VerificationTest
)


class TestInstallationVerifier(unittest.TestCase):
    """Test cases for InstallationVerifier"""
    
    def setUp(self):
        self.verifier = InstallationVerifier()
    
    def test_verify_existing_package(self):
        """Test verification of an existing package (python3)"""
        result = self.verifier.verify_package('python3')
        
        self.assertIsNotNone(result)
        self.assertEqual(result.package_name, 'python3')
        self.assertTrue(len(result.tests) > 0)
    
    def test_verify_nonexistent_package(self):
        """Test verification of non-existent package"""
        result = self.verifier.verify_package('nonexistent-package-xyz')
        
        self.assertEqual(result.status, VerificationStatus.FAILED)
    
    def test_multiple_packages(self):
        """Test verifying multiple packages"""
        packages = ['git', 'curl']
        results = self.verifier.verify_multiple_packages(packages)
        
        self.assertEqual(len(results), 2)
    
    def test_summary_generation(self):
        """Test summary statistics"""
        self.verifier.verify_package('git')
        self.verifier.verify_package('nonexistent-xyz')
        
        summary = self.verifier.get_summary()
        
        self.assertEqual(summary['total'], 2)
        self.assertGreaterEqual(summary['success'] + summary['failed'], 1)
    
    def test_custom_tests(self):
        """Test custom test definitions"""
        custom_tests = [
            {'type': 'command', 'command': 'echo test'},
            {'type': 'file', 'path': '/bin/bash'}
        ]
        
        result = self.verifier.verify_package(
            'test-package',
            custom_tests=custom_tests
        )
        
        self.assertTrue(len(result.tests) >= 2)
    
    def test_json_export(self):
        """Test JSON export functionality"""
        import tempfile
        import os
        
        self.verifier.verify_package('git')
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            self.verifier.export_results_json(temp_path)
            self.assertTrue(os.path.exists(temp_path))
            
            # Verify JSON is valid
            import json
            with open(temp_path, 'r') as f:
                data = json.load(f)
            
            self.assertTrue(isinstance(data, list))
            self.assertTrue(len(data) > 0)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == '__main__':
    unittest.main()
