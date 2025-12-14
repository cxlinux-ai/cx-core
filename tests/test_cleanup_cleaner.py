"""
Tests for Cleanup Cleaner Module.

Tests for DiskCleaner class.
"""

import pytest
import gzip
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from cortex.cleanup.cleaner import DiskCleaner
from cortex.cleanup.scanner import ScanResult


class TestDiskCleaner:
    """Tests for DiskCleaner class."""
    
    @pytest.fixture
    def cleaner(self):
        """Create a cleaner instance."""
        return DiskCleaner(dry_run=False)
    
    @pytest.fixture
    def dry_run_cleaner(self):
        """Create a dry-run cleaner instance."""
        return DiskCleaner(dry_run=True)
    
    def test_init(self, cleaner):
        """Test cleaner initialization."""
        assert cleaner.dry_run is False
        assert cleaner.scanner is not None
        assert cleaner.manager is not None
    
    def test_init_dry_run(self, dry_run_cleaner):
        """Test dry-run cleaner initialization."""
        assert dry_run_cleaner.dry_run is True
    
    @patch('cortex.cleanup.cleaner.run_command')
    def test_clean_package_cache_success(self, mock_run, cleaner):
        """Test clean_package_cache with success."""
        mock_result = Mock()
        mock_result.success = True
        mock_run.return_value = mock_result
        
        with patch.object(cleaner.scanner, 'scan_package_cache') as mock_scan:
            mock_scan.return_value = ScanResult("Package Cache", 1000, 5)
            
            freed = cleaner.clean_package_cache()
            
            assert freed == 1000
            mock_run.assert_called_once()
    
    @patch('cortex.cleanup.cleaner.run_command')
    def test_clean_package_cache_failure(self, mock_run, cleaner):
        """Test clean_package_cache with failure."""
        mock_result = Mock()
        mock_result.success = False
        mock_result.stderr = "Permission denied"
        mock_run.return_value = mock_result
        
        with patch.object(cleaner.scanner, 'scan_package_cache') as mock_scan:
            mock_scan.return_value = ScanResult("Package Cache", 1000, 5)
            
            freed = cleaner.clean_package_cache()
            
            assert freed == 0
    
    def test_clean_package_cache_dry_run(self, dry_run_cleaner):
        """Test clean_package_cache in dry-run mode."""
        with patch.object(dry_run_cleaner.scanner, 'scan_package_cache') as mock_scan:
            mock_scan.return_value = ScanResult("Package Cache", 5000, 10)
            
            freed = dry_run_cleaner.clean_package_cache()
            
            assert freed == 5000
    
    @patch('cortex.cleanup.cleaner.run_command')
    def test_remove_orphaned_packages_empty(self, mock_run, cleaner):
        """Test remove_orphaned_packages with empty list."""
        freed = cleaner.remove_orphaned_packages([])
        
        assert freed == 0
        mock_run.assert_not_called()
    
    @patch('cortex.cleanup.cleaner.run_command')
    def test_remove_orphaned_packages_success(self, mock_run, cleaner):
        """Test remove_orphaned_packages with success."""
        mock_result = Mock()
        mock_result.success = True
        mock_result.stdout = "After this operation, 100 MB disk space will be freed."
        mock_run.return_value = mock_result
        
        freed = cleaner.remove_orphaned_packages(["pkg1", "pkg2"])
        
        assert freed == 100 * 1024 * 1024
    
    def test_remove_orphaned_packages_dry_run(self, dry_run_cleaner):
        """Test remove_orphaned_packages in dry-run mode."""
        freed = dry_run_cleaner.remove_orphaned_packages(["pkg1"])
        
        assert freed == 0  # Dry run returns 0 for orphaned packages
    
    def test_parse_freed_space_mb(self, cleaner):
        """Test parsing freed space with MB."""
        stdout = "After this operation, 50 MB disk space will be freed."
        
        freed = cleaner._parse_freed_space(stdout)
        
        assert freed == 50 * 1024 * 1024
    
    def test_parse_freed_space_kb(self, cleaner):
        """Test parsing freed space with KB."""
        stdout = "After this operation, 256 KB disk space will be freed."
        
        freed = cleaner._parse_freed_space(stdout)
        
        assert freed == 256 * 1024
    
    def test_parse_freed_space_no_match(self, cleaner):
        """Test parsing freed space with no match."""
        stdout = "Nothing to do."
        
        freed = cleaner._parse_freed_space(stdout)
        
        assert freed == 0
    
    def test_clean_temp_files_nonexistent(self, cleaner):
        """Test clean_temp_files with nonexistent files."""
        files = ["/nonexistent/file1.tmp", "/nonexistent/file2.tmp"]
        
        freed = cleaner.clean_temp_files(files)
        
        # Should not raise, just skip
        assert freed == 0
    
    def test_clean_temp_files_dry_run(self, dry_run_cleaner, tmp_path):
        """Test clean_temp_files in dry-run mode."""
        # Create temp files
        file1 = tmp_path / "temp1.txt"
        file2 = tmp_path / "temp2.txt"
        file1.write_bytes(b"x" * 100)
        file2.write_bytes(b"x" * 200)
        
        freed = dry_run_cleaner.clean_temp_files([str(file1), str(file2)])
        
        assert freed == 300
        # Files should still exist (dry run)
        assert file1.exists()
        assert file2.exists()
    
    def test_compress_logs_nonexistent(self, cleaner):
        """Test compress_logs with nonexistent files."""
        files = ["/nonexistent/log1.log", "/nonexistent/log2.log"]
        
        freed = cleaner.compress_logs(files)
        
        assert freed == 0
    
    def test_compress_logs_success(self, cleaner, tmp_path):
        """Test compress_logs with actual files."""
        log_file = tmp_path / "test.log"
        log_content = b"This is a test log " * 1000  # Compressible content
        log_file.write_bytes(log_content)
        original_size = log_file.stat().st_size
        
        freed = cleaner.compress_logs([str(log_file)])
        
        # Original should be gone
        assert not log_file.exists()
        # Compressed should exist
        gz_file = tmp_path / "test.log.gz"
        assert gz_file.exists()
        # Should have freed some space
        assert freed > 0
    
    def test_compress_logs_dry_run(self, dry_run_cleaner, tmp_path):
        """Test compress_logs in dry-run mode."""
        log_file = tmp_path / "test.log"
        log_file.write_bytes(b"x" * 1000)
        
        freed = dry_run_cleaner.compress_logs([str(log_file)])
        
        # Should estimate 90% reduction
        assert freed == int(1000 * 0.9)
        # File should still exist (dry run)
        assert log_file.exists()
    
    def test_run_cleanup_all_categories(self, cleaner):
        """Test run_cleanup with all categories (non-safe mode)."""
        scan_results = [
            ScanResult("Package Cache", 1000, 5, []),
            ScanResult("Orphaned Packages", 2000, 3, ["pkg1"]),
            ScanResult("Temporary Files", 500, 2, ["/tmp/f1"]),
            ScanResult("Old Logs", 800, 1, ["/var/log/old.log"]),
        ]
        
        with patch.object(cleaner, 'clean_package_cache', return_value=1000), \
             patch.object(cleaner, 'remove_orphaned_packages', return_value=2000), \
             patch.object(cleaner, 'clean_temp_files', return_value=500), \
             patch.object(cleaner, 'compress_logs', return_value=800):
            
            # Use safe=False to include orphaned packages
            summary = cleaner.run_cleanup(scan_results, safe=False)
            
            assert summary["Package Cache"] == 1000
            assert summary["Orphaned Packages"] == 2000
            assert summary["Temporary Files"] == 500
            assert summary["Old Logs"] == 800
    
    def test_run_cleanup_empty(self, cleaner):
        """Test run_cleanup with empty results."""
        summary = cleaner.run_cleanup([])
        
        assert summary["Package Cache"] == 0
        assert summary["Orphaned Packages"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
