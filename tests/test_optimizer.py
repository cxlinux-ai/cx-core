import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import time
from cortex.optimizer import CleanupOptimizer, LogManager, TempCleaner, CleanupOpportunity

class TestCleanupOptimizer(unittest.TestCase):
    def setUp(self):
        self.optimizer = CleanupOptimizer()
        # Mock the internal managers to isolate tests
        self.optimizer.pm = MagicMock()
        self.optimizer.log_manager = MagicMock()
        self.optimizer.temp_cleaner = MagicMock()

    def test_scan_aggregates_opportunities(self):
        # Setup mocks
        self.optimizer.pm.get_cleanable_items.return_value = {
            "cache_size_bytes": 1024,
            "orphaned_packages": ["pkg1"],
            "orphaned_size_bytes": 2048
        }
        self.optimizer.log_manager.scan.return_value = CleanupOpportunity(
            type="logs", size_bytes=500, description="Old logs", items=[]
        )
        self.optimizer.temp_cleaner.scan.return_value = None

        opportunities = self.optimizer.scan()

        self.assertEqual(len(opportunities), 3) # pkg cache, orphans, logs
        self.assertEqual(opportunities[0].type, "package_cache")
        self.assertEqual(opportunities[1].type, "orphans")
        self.assertEqual(opportunities[2].type, "logs")

    def test_get_cleanup_plan(self):
        self.optimizer.pm.get_cleanup_commands.side_effect = lambda x: [f"clean {x}"]
        self.optimizer.log_manager.get_cleanup_commands.return_value = ["compress logs"]
        self.optimizer.temp_cleaner.get_cleanup_commands.return_value = ["clean temp"]

        plan = self.optimizer.get_cleanup_plan()
        
        expected = ["clean cache", "clean orphans", "compress logs", "clean temp"]
        self.assertEqual(plan, expected)

class TestLogManager(unittest.TestCase):
    @patch('os.path.exists', return_value=True)
    @patch('glob.glob')
    @patch('os.stat')
    def test_scan_finds_old_logs(self, mock_stat, mock_glob, mock_exists):
        manager = LogManager()
        
        # Setup mock file
        def glob_side_effect(path, recursive=False):
            if path.endswith("*.log"):
                return ["/var/log/old.log"]
            return []
        
        mock_glob.side_effect = glob_side_effect
        
        # Mock stat to return old time
        old_time = time.time() - (8 * 86400) # 8 days ago
        mock_stat_obj = MagicMock()
        mock_stat_obj.st_mtime = old_time
        mock_stat_obj.st_size = 100
        mock_stat.return_value = mock_stat_obj
        
        opp = manager.scan()
        
        self.assertIsNotNone(opp)
        self.assertEqual(opp.type, "logs")
        self.assertEqual(opp.size_bytes, 100)
        self.assertEqual(opp.items, ["/var/log/old.log"])

class TestTempCleaner(unittest.TestCase):
    @patch('os.path.exists', return_value=True)
    @patch('os.walk')
    @patch('os.stat')
    def test_scan_finds_temp_files(self, mock_stat, mock_walk, mock_exists):
        manager = TempCleaner(temp_dirs=["/tmp"])
        
        # Setup mock walk
        mock_walk.return_value = [("/tmp", [], ["tempfile"])]
        
        # Mock stat to return old time
        old_time = time.time() - (8 * 86400) # 8 days ago
        mock_stat_obj = MagicMock()
        mock_stat_obj.st_atime = old_time
        mock_stat_obj.st_mtime = old_time
        mock_stat_obj.st_size = 50
        mock_stat.return_value = mock_stat_obj
        
        opp = manager.scan()
        
        self.assertIsNotNone(opp)
        self.assertEqual(opp.type, "temp")
        self.assertEqual(opp.size_bytes, 50)

if __name__ == '__main__':
    unittest.main()
