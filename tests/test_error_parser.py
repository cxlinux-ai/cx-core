#!/usr/bin/env python3
"""
Tests for Error Parser System
"""

import unittest
from error_parser import (
    ErrorParser,
    ErrorCategory,
    ErrorAnalysis
)


class TestErrorParser(unittest.TestCase):
    """Test cases for ErrorParser"""
    
    def setUp(self):
        self.parser = ErrorParser()
    
    def test_dependency_missing_error(self):
        """Test parsing of missing dependency errors"""
        error = "E: nginx: Depends: libssl1.1 but it is not installable"
        
        analysis = self.parser.parse_error(error)
        
        self.assertEqual(analysis.primary_category, ErrorCategory.DEPENDENCY_MISSING)
        self.assertTrue(analysis.is_fixable)
        self.assertGreater(len(analysis.suggested_fixes), 0)
    
    def test_package_not_found_error(self):
        """Test parsing of package not found errors"""
        error = "E: Unable to locate package nonexistent-package"
        
        analysis = self.parser.parse_error(error)
        
        self.assertEqual(analysis.primary_category, ErrorCategory.PACKAGE_NOT_FOUND)
        self.assertIn('update', analysis.suggested_fixes[0].lower())
    
    def test_permission_denied_error(self):
        """Test parsing of permission errors"""
        error = "E: Could not open lock file /var/lib/dpkg/lock - open (13: Permission denied)"
        
        analysis = self.parser.parse_error(error)
        
        self.assertIn(analysis.primary_category, [
            ErrorCategory.PERMISSION_DENIED,
            ErrorCategory.LOCK_ERROR
        ])
    
    def test_disk_space_error(self):
        """Test parsing of disk space errors"""
        error = "E: No space left on device"
        
        analysis = self.parser.parse_error(error)
        
        self.assertEqual(analysis.primary_category, ErrorCategory.DISK_SPACE)
        self.assertEqual(analysis.severity, "critical")
        self.assertTrue(analysis.automatic_fix_available)
    
    def test_network_error(self):
        """Test parsing of network errors"""
        error = "Err:1 http://archive.ubuntu.com/ubuntu jammy InRelease\n  Connection failed"
        
        analysis = self.parser.parse_error(error)
        
        self.assertEqual(analysis.primary_category, ErrorCategory.NETWORK_ERROR)
        self.assertFalse(analysis.automatic_fix_available)
    
    def test_conflict_error(self):
        """Test parsing of package conflict errors"""
        error = "E: nginx conflicts with apache2"
        
        analysis = self.parser.parse_error(error)
        
        self.assertEqual(analysis.primary_category, ErrorCategory.CONFLICT)
        self.assertFalse(analysis.automatic_fix_available)
    
    def test_broken_package_error(self):
        """Test parsing of broken package errors"""
        error = "E: You have held broken packages."
        
        analysis = self.parser.parse_error(error)
        
        self.assertEqual(analysis.primary_category, ErrorCategory.BROKEN_PACKAGE)
        self.assertTrue(analysis.automatic_fix_available)
        self.assertIn('install -f', analysis.automatic_fix_command)
    
    def test_gpg_key_error(self):
        """Test parsing of GPG key errors"""
        error = "GPG error: NO_PUBKEY 0EBFCD88"
        
        analysis = self.parser.parse_error(error)
        
        self.assertEqual(analysis.primary_category, ErrorCategory.GPG_KEY_ERROR)
        self.assertTrue(analysis.automatic_fix_available)
        self.assertIn('0EBFCD88', analysis.automatic_fix_command)
    
    def test_lock_error(self):
        """Test parsing of lock file errors"""
        error = "E: Could not get lock /var/lib/dpkg/lock-frontend"
        
        analysis = self.parser.parse_error(error)
        
        self.assertEqual(analysis.primary_category, ErrorCategory.LOCK_ERROR)
        self.assertTrue(analysis.automatic_fix_available)
    
    def test_unknown_error(self):
        """Test parsing of unrecognized errors"""
        error = "Some completely unknown error message"
        
        analysis = self.parser.parse_error(error)
        
        self.assertEqual(analysis.primary_category, ErrorCategory.UNKNOWN)
        self.assertGreater(len(analysis.suggested_fixes), 0)
    
    def test_multiple_patterns_match(self):
        """Test when multiple patterns match"""
        error = """
        E: Unable to locate package test-package
        E: You have held broken packages
        """
        
        analysis = self.parser.parse_error(error)
        
        # Should match multiple patterns
        self.assertGreater(len(analysis.matches), 1)
    
    def test_severity_calculation(self):
        """Test severity level assignment"""
        # Critical error
        disk_error = "E: No space left on device"
        analysis = self.parser.parse_error(disk_error)
        self.assertEqual(analysis.severity, "critical")
        
        # High error
        dep_error = "E: Depends: libtest but it is not installable"
        analysis = self.parser.parse_error(dep_error)
        self.assertEqual(analysis.severity, "high")
    
    def test_data_extraction(self):
        """Test extraction of specific data from errors"""
        error = "E: Unable to locate package my-test-package"
        
        analysis = self.parser.parse_error(error)
        
        # Should extract package name
        if analysis.matches:
            self.assertIn('package', analysis.matches[0].extracted_data.get('group_0', '').lower() or 
                         analysis.matches[0].extracted_data)


if __name__ == '__main__':
    unittest.main()
