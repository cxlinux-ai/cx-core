import unittest
import json
import datetime
import shutil
from unittest.mock import patch, MagicMock
from pathlib import Path

# Import the class to be tested
from cortex.notification_manager import NotificationManager

class TestNotificationManager(unittest.TestCase):
    def setUp(self):
        """Setup temporary environment for testing."""
        self.mgr = NotificationManager()
        
        # Use a temporary directory
        self.mgr.config_dir = Path("./test_cortex_config")
        self.mgr.config_dir.mkdir(exist_ok=True)
        self.mgr.history_file = self.mgr.config_dir / "test_history.json"
        self.mgr.config_file = self.mgr.config_dir / "test_config.json"
        
        # Default config
        self.mgr.config = {
            "dnd_start": "22:00",
            "dnd_end": "08:00",
            "enabled": True
        }
        self.mgr._save_config()
        self.mgr.history = []

    def tearDown(self):
        """Clean up."""
        if self.mgr.config_dir.exists():
            shutil.rmtree(self.mgr.config_dir)

    def test_dnd_logic_active(self):
        """Scenario: Current time is 23:00 (DND Active)."""
        with patch.object(self.mgr, '_get_current_time') as mock_time:
            mock_time.return_value = datetime.time(23, 0)
            self.assertTrue(self.mgr.is_dnd_active())

    def test_dnd_logic_inactive(self):
        """Scenario: Current time is 12:00 (DND Inactive)."""
        with patch.object(self.mgr, '_get_current_time') as mock_time:
            mock_time.return_value = datetime.time(12, 0)
            self.assertFalse(self.mgr.is_dnd_active())

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_send_notification_with_actions(self, mock_which, mock_run):
        """
        Test if notify-send is called with correct ACTION arguments.
        """
        # Mock environment
        mock_which.return_value = "/usr/bin/notify-send"
        
        # Disable DND
        with patch.object(self.mgr, '_get_current_time') as mock_time:
            mock_time.return_value = datetime.time(12, 0)
            
            # Send with actions
            actions = ["View Logs", "Retry"]
            self.mgr.send("Action Test", "Testing buttons", actions=actions)
            
            # Verify command execution
            mock_run.assert_called_once()
            
            # Check if arguments contain the actions
            args = mock_run.call_args[0][0]
            self.assertIn("notify-send", args)
            # Check if hints for actions were added (implementation dependent, but checking args exist)
            # The code adds "--hint=string:action:View Logs"
            self.assertTrue(any("View Logs" in arg for arg in args))

    def test_history_logging(self):
        """Test logging."""
        self.mgr.send("History Test", "Logging check")
        
        with open(self.mgr.history_file, 'r') as f:
            data = json.load(f)
            
        self.assertTrue(len(data) > 0)
        self.assertEqual(data[-1]['title'], "History Test")

if __name__ == '__main__':
    unittest.main(verbosity=2)