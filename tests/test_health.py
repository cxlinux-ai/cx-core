import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from cortex.health import HealthEngine, HealthFactor, HealthHistory, check_health

mock_path_obj = MagicMock()
mock_path_obj.exists.return_value = False
mock_path_obj.parent.mkdir.return_value = None

class TestHealth(unittest.TestCase):
    @patch("cortex.health.HISTORY_FILE", mock_path_obj)
    def test_history(self):
        with patch.object(mock_path_obj, 'exists', return_value=True), \
             patch("builtins.open", new_callable=mock_open, read_data='[{"score": 90}]'):
            h = HealthHistory()
            self.assertEqual(len(h.history), 1)

    @patch('shutil.disk_usage')
    def test_engine_logic(self, mock_disk):
        with patch("cortex.health.HealthHistory._load", return_value=[]), \
             patch("cortex.health.HISTORY_FILE.parent.mkdir"):
            e = HealthEngine()
            mock_disk.return_value = (100, 20, 80)
            e._check_disk()
            self.assertEqual(e.score, 100)

    @patch('cortex.health.HealthEngine')
    @patch('rich.console.Console.print')
    def test_cli(self, mock_print, mock_cls):
        mock_inst = mock_cls.return_value
        mock_inst.run_diagnostics.return_value = (100, [], "Trend")
        check_health(fix=False)
        self.assertTrue(mock_print.called)

if __name__ == '__main__':
    unittest.main()
