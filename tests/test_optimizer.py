
import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
from cortex.optimizer import DiskOptimizer
from cortex.packages import PackageManager

class TestDiskOptimizer(unittest.TestCase):
    
    def setUp(self):
        self.optimizer = DiskOptimizer()
        # Mock PackageManager
        self.optimizer.pm = MagicMock(spec=PackageManager)
        self.optimizer.pm.pm_type = "apt"

    @patch('os.path.getsize')
    @patch('os.path.isfile')
    @patch('glob.glob')
    def test_scan_and_clean_cache(self, mock_glob, mock_isfile, mock_getsize):
        # Setup mocks
        mock_glob.return_value = []
        mock_isfile.return_value = True
        mock_getsize.return_value = 1000
        
        # Mock PM methods
        self.optimizer.pm.clean_cache.return_value = (True, "Cleaned")
        self.optimizer.pm.get_orphaned_packages.return_value = []
        
        # Mock internal helper to return fixed size
        with patch.object(self.optimizer, '_get_package_cache_size', return_value=5000):
            # Scan
            result = self.optimizer.scan()
            self.assertEqual(result['package_cache'], 5000)
            
            # Clean
            stats = self.optimizer.clean()
            self.optimizer.pm.clean_cache.assert_called_with(execute=True)
            self.assertIn("Cleaned package cache", stats['actions'][0])
            self.assertEqual(stats['freed_bytes'], 5000)

    def test_clean_orphans(self):
        # Mock orphans
        self.optimizer.pm.get_orphaned_packages.return_value = ["libunused", "python-old"]
        self.optimizer.pm.remove_packages.return_value = (True, "Removed")
        
        with patch.object(self.optimizer, '_get_package_cache_size', return_value=0), \
             patch('glob.glob', return_value=[]):
             
            result = self.optimizer.scan()
            self.assertEqual(len(result['orphaned_packages']), 2)
            
            stats = self.optimizer.clean()
            self.optimizer.pm.remove_packages.assert_called_with(["libunused", "python-old"], execute=True)
            self.assertIn("Removed 2 orphaned packages", stats['actions'][0])

    @patch('os.remove')
    @patch('os.path.getsize')
    @patch('glob.glob')
    def test_clean_temp_files(self, mock_glob, mock_getsize, mock_remove):
        # Setup mocks to find one temp file
        mock_glob.side_effect = lambda p: ["/tmp/cortex-test.tmp"] if "/tmp/cortex-*" in p else []
        mock_getsize.return_value = 1024
        self.optimizer.pm.get_orphaned_packages.return_value = [] # Ensure no orphans to clean
        
        with patch('os.path.isfile', return_value=True), \
             patch.object(self.optimizer, '_get_package_cache_size', return_value=0):
             
            result = self.optimizer.scan()
            self.assertIn("/tmp/cortex-test.tmp", result['temp_files'])
            
            stats = self.optimizer.clean()
            mock_remove.assert_called_with("/tmp/cortex-test.tmp")
            self.assertEqual(stats['freed_bytes'], 1024)

if __name__ == '__main__':
    unittest.main()
