#!/usr/bin/env python3
"""Unit tests for Cortex Logging System"""
import unittest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logging_system import CortexLogger, LogContext

class TestCortexLogger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.logger = CortexLogger("test", log_dir=self.temp_dir)
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_basic_logging(self):
        """Test basic log levels"""
        self.logger.info("Test info message")
        self.logger.debug("Test debug message")
        self.logger.warning("Test warning")
        self.logger.error("Test error")
        
        # Verify log files created
        log_files = list(Path(self.temp_dir).glob("test*.log"))
        self.assertGreater(len(log_files), 0)
        
    def test_context_logging(self):
        """Test logging with context"""
        context = {"user": "test", "action": "install"}
        self.logger.info("Test with context", context)
        
        # Check JSON log
        json_log = Path(self.temp_dir) / "test.json.log"
        if json_log.exists():
            with open(json_log) as f:
                last_line = f.readlines()[-1]
                entry = json.loads(last_line)
                self.assertIn('context', entry)
                
    def test_operation_timing(self):
        """Test operation timing"""
        self.logger.start_operation("test_op")
        import time
        time.sleep(0.01)
        duration = self.logger.end_operation("test_op")
        
        self.assertIsNotNone(duration)
        self.assertGreater(duration, 0)
        
    def test_log_context_manager(self):
        """Test LogContext context manager"""
        with LogContext(self.logger, "test_operation"):
            self.logger.info("Inside context")
            
        # Operation should be logged
        logs = self.logger.search_logs("test_operation")
        self.assertGreater(len(logs), 0)
        
    def test_log_stats(self):
        """Test log statistics"""
        self.logger.info("Test message")
        stats = self.logger.get_log_stats()
        
        self.assertIn('total_size_bytes', stats)
        self.assertIn('file_count', stats)
        self.assertGreater(stats['file_count'], 0)
        
    def test_search_logs(self):
        """Test log search"""
        self.logger.info("Searchable message alpha")
        self.logger.info("Searchable message beta")
        
        results = self.logger.search_logs("Searchable")
        self.assertGreaterEqual(len(results), 2)
        
    def test_export_logs(self):
        """Test log export"""
        self.logger.info("Export test")
        
        export_path = Path(self.temp_dir) / "export.json"
        result = self.logger.export_logs(str(export_path), format="json")
        
        self.assertTrue(Path(result).exists())
        
if __name__ == "__main__":
    unittest.main()
