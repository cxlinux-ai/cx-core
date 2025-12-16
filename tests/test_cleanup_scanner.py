"""
Tests for Cleanup Scanner Module.

Tests for CleanupScanner class and ScanResult dataclass.
"""

import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from cortex.cleanup.scanner import CleanupScanner, ScanResult


class TestScanResult:
    """Tests for ScanResult dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        result = ScanResult(
            category="Test Category",
            size_bytes=1024,
            count=5
        )
        
        assert result.category == "Test Category"
        assert result.size_bytes == 1024
        assert result.count == 5
        assert result.items == []
    
    def test_with_items(self):
        """Test with items list."""
        items = ["/tmp/file1", "/tmp/file2"]
        result = ScanResult(
            category="Temp Files",
            size_bytes=2048,
            count=2,
            items=items
        )
        
        assert result.items == items
        assert len(result.items) == 2


class TestCleanupScanner:
    """Tests for CleanupScanner class."""
    
    @pytest.fixture
    def scanner(self):
        """Create a scanner instance."""
        return CleanupScanner()
    
    def test_init(self, scanner):
        """Test scanner initialization."""
        assert scanner.apt_cache_dir == Path("/var/cache/apt/archives")
        assert scanner.log_dir == Path("/var/log")
        assert len(scanner.temp_dirs) == 2
    
    def test_scan_all_returns_list(self, scanner):
        """Test scan_all returns a list of results."""
        with patch.object(scanner, 'scan_package_cache') as mock_pkg, \
             patch.object(scanner, 'scan_orphaned_packages') as mock_orphan, \
             patch.object(scanner, 'scan_temp_files') as mock_temp, \
             patch.object(scanner, 'scan_logs') as mock_logs:
            
            mock_pkg.return_value = ScanResult("Package Cache", 0, 0)
            mock_orphan.return_value = ScanResult("Orphaned Packages", 0, 0)
            mock_temp.return_value = ScanResult("Temporary Files", 0, 0)
            mock_logs.return_value = ScanResult("Old Logs", 0, 0)
            
            results = scanner.scan_all()
            
            assert len(results) == 4
            assert all(isinstance(r, ScanResult) for r in results)
    
    def test_scan_package_cache_no_dir(self, scanner):
        """Test scan_package_cache when directory doesn't exist."""
        scanner.apt_cache_dir = Path("/nonexistent/path")
        
        result = scanner.scan_package_cache()
        
        assert result.category == "Package Cache"
        assert result.size_bytes == 0
        assert result.count == 0
    
    def test_scan_package_cache_with_files(self, scanner, tmp_path):
        """Test scan_package_cache with actual files."""
        # Create temp directory with .deb files
        scanner.apt_cache_dir = tmp_path
        
        deb1 = tmp_path / "package1.deb"
        deb2 = tmp_path / "package2.deb"
        deb1.write_bytes(b"x" * 1000)
        deb2.write_bytes(b"x" * 2000)
        
        result = scanner.scan_package_cache()
        
        assert result.category == "Package Cache"
        assert result.size_bytes == 3000
        assert result.count == 2
        assert len(result.items) == 2
    
    @patch('cortex.cleanup.scanner.run_command')
    def test_scan_orphaned_packages_success(self, mock_run, scanner):
        """Test scan_orphaned_packages with successful command."""
        mock_result = Mock()
        mock_result.success = True
        mock_result.stdout = """Reading package lists...
The following packages will be REMOVED:
  package1 package2 package3
After this operation, 50.5 MB disk space will be freed.
"""
        mock_run.return_value = mock_result
        
        result = scanner.scan_orphaned_packages()
        
        assert result.category == "Orphaned Packages"
        assert result.count == 3
        assert "package1" in result.items
        assert result.size_bytes == int(50.5 * 1024 * 1024)
    
    @patch('cortex.cleanup.scanner.run_command')
    def test_scan_orphaned_packages_no_packages(self, mock_run, scanner):
        """Test scan_orphaned_packages with no orphaned packages."""
        mock_result = Mock()
        mock_result.success = True
        mock_result.stdout = "0 upgraded, 0 newly installed, 0 to remove."
        mock_run.return_value = mock_result
        
        result = scanner.scan_orphaned_packages()
        
        assert result.count == 0
        assert result.size_bytes == 0
    
    @patch('cortex.cleanup.scanner.run_command')
    def test_scan_orphaned_packages_failure(self, mock_run, scanner):
        """Test scan_orphaned_packages when command fails."""
        mock_result = Mock()
        mock_result.success = False
        mock_result.stdout = ""
        mock_run.return_value = mock_result
        
        result = scanner.scan_orphaned_packages()
        
        assert result.count == 0
        assert result.size_bytes == 0
    
    def test_scan_temp_files_empty(self, scanner, tmp_path):
        """Test scan_temp_files with no old files."""
        scanner.temp_dirs = [tmp_path]
        
        # Create a new file (not old enough)
        new_file = tmp_path / "new_file.txt"
        new_file.write_text("new content")
        
        result = scanner.scan_temp_files(days_old=7)
        
        assert result.category == "Temporary Files"
        assert result.count == 0
    
    def test_scan_temp_files_with_old_files(self, scanner, tmp_path):
        """Test scan_temp_files with old files."""
        scanner.temp_dirs = [tmp_path]
        
        old_file = tmp_path / "old_file.txt"
        old_file.write_bytes(b"x" * 500)
        
        # Modify mtime to be old
        old_time = time.time() - (10 * 86400)  # 10 days ago
        import os
        os.utime(old_file, (old_time, old_time))
        
        result = scanner.scan_temp_files(days_old=7)
        
        assert result.count == 1
        assert result.size_bytes == 500
    
    def test_scan_logs_no_dir(self, scanner):
        """Test scan_logs when log directory doesn't exist."""
        scanner.log_dir = Path("/nonexistent/log/path")
        
        result = scanner.scan_logs()
        
        assert result.category == "Old Logs"
        assert result.count == 0
    
    def test_scan_logs_with_files(self, scanner, tmp_path):
        """Test scan_logs with log files."""
        scanner.log_dir = tmp_path

        # Create an old log file (size threshold is controlled via min_size_mb)
        log_file = tmp_path / "test.log"
        log_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB

        old_time = time.time() - (10 * 86400)
        import os
        os.utime(log_file, (old_time, old_time))

        result = scanner.scan_logs(min_size_mb=1, days_old=7)

        assert result.count == 1
        assert result.size_bytes == 2 * 1024 * 1024
    
    def test_parse_autoremove_output_kb(self, scanner):
        """Test parsing autoremove output with KB units."""
        output = "After this operation, 512 KB disk space will be freed."
        
        _, size = scanner._parse_autoremove_output(output)
        
        assert size == 512 * 1024
    
    def test_parse_autoremove_output_gb(self, scanner):
        """Test parsing autoremove output with GB units."""
        output = "After this operation, 1.5 GB disk space will be freed."
        
        _, size = scanner._parse_autoremove_output(output)
        
        assert size == int(1.5 * 1024 * 1024 * 1024)
    
    def test_parse_autoremove_output_with_packages(self, scanner):
        """Test parsing autoremove output with package list."""
        output = """The following packages will be REMOVED:
  pkg1 pkg2 pkg3
After this operation, 100 MB disk space will be freed."""
        
        packages, _ = scanner._parse_autoremove_output(output)
        
        assert "pkg1" in packages
        assert "pkg2" in packages
        assert "pkg3" in packages
        assert len(packages) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
