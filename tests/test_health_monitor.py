import unittest
from unittest.mock import patch, MagicMock, mock_open
from cortex.health.monitor import HealthMonitor, CheckResult
from cortex.health.checks.disk import DiskCheck
from cortex.health.checks.performance import PerformanceCheck
from cortex.health.checks.security import SecurityCheck
from cortex.health.checks.updates import UpdateCheck

class TestDiskCheck(unittest.TestCase):
    @patch('shutil.disk_usage')
    def test_disk_usage_scoring(self, mock_usage):
        # Case 1: Healthy (50% used) -> 100 pts
        # total=100, used=50, free=50
        mock_usage.return_value = (100, 50, 50)
        check = DiskCheck()
        result = check.run()
        self.assertEqual(result.score, 100)
        self.assertEqual(result.status, "OK")

        # Case 2: Warning (85% used) -> 50 pts
        mock_usage.return_value = (100, 85, 15)
        result = check.run()
        self.assertEqual(result.score, 50)
        self.assertEqual(result.status, "WARNING")

        # Case 3: Critical (95% used) -> 0 pts
        mock_usage.return_value = (100, 95, 5)
        result = check.run()
        self.assertEqual(result.score, 0)
        self.assertEqual(result.status, "CRITICAL")

class TestPerformanceCheck(unittest.TestCase):
    @patch('os.getloadavg')
    @patch('multiprocessing.cpu_count')
    def test_load_average(self, mock_cpu, mock_load):
        # Case 1: Load OK (Load 2.0 / 4 Cores = 0.5 ratio)
        mock_cpu.return_value = 4
        mock_load.return_value = (2.0, 2.0, 2.0)
        
        # Mock reading /proc/meminfo (Normal case)
        mem_data = "MemTotal: 1000 kB\nMemAvailable: 500 kB\n"
        with patch('builtins.open', mock_open(read_data=mem_data)):
            check = PerformanceCheck()
            result = check.run()
            self.assertEqual(result.score, 100) # No penalty

    @patch('os.getloadavg')
    @patch('multiprocessing.cpu_count')
    def test_high_load_penalty(self, mock_cpu, mock_load):
        # Case 2: High Load (Load 5.0 / 4 Cores = 1.25 ratio) -> -50 pts
        mock_cpu.return_value = 4
        mock_load.return_value = (5.0, 5.0, 5.0)
        
        # Assume memory is normal
        mem_data = "MemTotal: 1000 kB\nMemAvailable: 500 kB\n"
        with patch('builtins.open', mock_open(read_data=mem_data)):
            check = PerformanceCheck()
            result = check.run()
            self.assertEqual(result.score, 50) # 100 - 50 = 50

class TestSecurityCheck(unittest.TestCase):
    @patch('subprocess.run')
    def test_ufw_status(self, mock_run):
        # Case 1: UFW Inactive -> 0 pts
        mock_run.return_value.stdout = "inactive"
        mock_run.return_value.returncode = 0
        
        check = SecurityCheck()
        result = check.run()
        self.assertEqual(result.score, 0)
        self.assertIn("Firewall Inactive", result.details)

    @patch('subprocess.run')
    def test_ufw_active(self, mock_run):
        # Case 2: UFW Active -> 100 pts (SSH config is safe by default mock)
        mock_run.return_value.stdout = "active"
        mock_run.return_value.returncode = 0
        
        # Test error handling when sshd_config does not exist
        with patch('os.path.exists', return_value=False):
            check = SecurityCheck()
            result = check.run()
            self.assertEqual(result.score, 100)

class TestUpdateCheck(unittest.TestCase):
    @patch('subprocess.run')
    def test_apt_updates(self, mock_run):
        # Mock output for apt list --upgradable
        # Ignore first line, packages start from 2nd line
        apt_output = """Listing... Done
package1/stable 1.0.0 amd64 [upgradable from: 0.9.9]
package2/stable 2.0.0 amd64 [upgradable from: 1.9.9]
security-pkg/stable 1.0.1 amd64 [upgradable from: 1.0.0] - Security Update
"""
        mock_run.return_value.stdout = apt_output
        mock_run.return_value.returncode = 0
        
        check = UpdateCheck()
        result = check.run()
        
        # Calculation: 
        # Total packages: 3
        # Security packages: 1 (line containing "security")
        # Penalty: (3 * 2) + (1 * 10) = 6 + 10 = 16 pts
        # Expected score: 100 - 16 = 84 pts
        
        self.assertEqual(result.score, 84)
        self.assertIn("3 pending", result.details)

class TestHealthMonitor(unittest.TestCase):
    def test_monitor_aggregation(self):
        monitor = HealthMonitor()
        # Register mock checks instead of real check classes
        
        mock_check1 = MagicMock()
        mock_check1.run.return_value = CheckResult(
            name="Check1", category="test", score=100, status="OK", details="", weight=0.5
        )
        
        mock_check2 = MagicMock()
        mock_check2.run.return_value = CheckResult(
            name="Check2", category="test", score=0, status="CRITICAL", details="", weight=0.5
        )
        
        monitor.checks = [mock_check1, mock_check2]
        
        # Mock history saving to prevent file write
        with patch.object(monitor, '_save_history'):
            report = monitor.run_all()
            
            # Weighted average calculation:
            # (100 * 0.5) + (0 * 0.5) = 50 / (0.5 + 0.5) = 50 pts
            self.assertEqual(report['total_score'], 50)
            self.assertEqual(len(report['results']), 2)

if __name__ == '__main__':
    unittest.main()