#!/usr/bin/env python3
"""
Unit tests for the intelligent package manager wrapper.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cortex.packages import PackageManager, PackageManagerType


class TestPackageManager(unittest.TestCase):
    """Test cases for PackageManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock package manager detection to use apt for consistent testing
        with patch('cortex.packages.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            self.pm = PackageManager(pm_type=PackageManagerType.APT)
    
    def test_python_installation(self):
        """Test basic Python installation request."""
        commands = self.pm.parse("install python")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        self.assertIn("python3", commands[0])
        self.assertIn("apt install", commands[0])
    
    def test_python_development_tools(self):
        """Test Python development tools installation."""
        commands = self.pm.parse("install python development tools")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("python3-dev", cmd)
        self.assertIn("build-essential", cmd)
    
    def test_python_data_science(self):
        """Test Python data science libraries installation."""
        commands = self.pm.parse("install python with data science libraries")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("python3", cmd)
        self.assertIn("python3-numpy", cmd)
        self.assertIn("python3-pandas", cmd)
        self.assertIn("python3-scipy", cmd)
    
    def test_python_machine_learning(self):
        """Test Python machine learning libraries."""
        commands = self.pm.parse("install python machine learning libraries")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("python3", cmd)
        self.assertIn("python3-numpy", cmd)
        self.assertIn("python3-scipy", cmd)
    
    def test_web_development(self):
        """Test web development tools installation."""
        commands = self.pm.parse("install web development tools")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("nodejs", cmd)
        self.assertIn("npm", cmd)
        self.assertIn("git", cmd)
    
    def test_docker_installation(self):
        """Test Docker installation."""
        commands = self.pm.parse("install docker")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("docker.io", cmd)
        self.assertIn("docker-compose", cmd)
    
    def test_database_installations(self):
        """Test various database installations."""
        # MySQL
        commands = self.pm.parse("install mysql")
        self.assertIsInstance(commands, list)
        self.assertIn("mysql-server", commands[0])
        
        # PostgreSQL
        commands = self.pm.parse("install postgresql")
        self.assertIsInstance(commands, list)
        self.assertIn("postgresql", commands[0])
        
        # Redis
        commands = self.pm.parse("install redis")
        self.assertIsInstance(commands, list)
        self.assertIn("redis-server", commands[0])
    
    def test_build_tools(self):
        """Test build tools installation."""
        commands = self.pm.parse("install build tools")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("build-essential", cmd)
        self.assertIn("gcc", cmd)
        self.assertIn("make", cmd)
    
    def test_system_monitoring(self):
        """Test system monitoring tools."""
        commands = self.pm.parse("install system monitoring tools")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("htop", cmd)
        self.assertIn("iotop", cmd)
    
    def test_network_tools(self):
        """Test network tools installation."""
        commands = self.pm.parse("install network tools")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("net-tools", cmd)
        self.assertIn("tcpdump", cmd)
    
    def test_security_tools(self):
        """Test security tools installation."""
        commands = self.pm.parse("install security tools")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("ufw", cmd)
        self.assertIn("fail2ban", cmd)
    
    def test_nginx_installation(self):
        """Test Nginx web server installation."""
        commands = self.pm.parse("install nginx")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        self.assertIn("nginx", commands[0])
    
    def test_apache_installation(self):
        """Test Apache web server installation."""
        commands = self.pm.parse("install apache")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        self.assertIn("apache2", commands[0])
    
    def test_git_installation(self):
        """Test Git installation."""
        commands = self.pm.parse("install git")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        self.assertIn("git", commands[0])
    
    def test_text_editors(self):
        """Test text editors installation."""
        commands = self.pm.parse("install text editors")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("vim", cmd)
        self.assertIn("nano", cmd)
    
    def test_version_control(self):
        """Test version control tools."""
        commands = self.pm.parse("install version control")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("git", cmd)
        self.assertIn("subversion", cmd)
    
    def test_compression_tools(self):
        """Test compression tools installation."""
        commands = self.pm.parse("install compression tools")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("zip", cmd)
        self.assertIn("unzip", cmd)
        self.assertIn("gzip", cmd)
    
    def test_image_tools(self):
        """Test image processing tools."""
        commands = self.pm.parse("install image tools")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        self.assertIn("imagemagick", cmd)
        self.assertIn("ffmpeg", cmd)
    
    def test_kubernetes_tools(self):
        """Test Kubernetes tools installation."""
        commands = self.pm.parse("install kubernetes")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        self.assertIn("kubectl", commands[0])
    
    def test_remove_action(self):
        """Test package removal."""
        commands = self.pm.parse("remove python")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        self.assertIn("apt remove", commands[0])
    
    def test_update_action(self):
        """Test package update."""
        commands = self.pm.parse("update python")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        # Update should include both update and upgrade commands for apt
        self.assertTrue(any("apt update" in cmd for cmd in commands))
    
    def test_search_action(self):
        """Test package search."""
        commands = self.pm.parse("search python")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        self.assertIn("apt search", commands[0])
    
    def test_empty_request(self):
        """Test that empty request raises ValueError."""
        with self.assertRaises(ValueError):
            self.pm.parse("")
    
    def test_unknown_package(self):
        """Test that unknown packages raise ValueError."""
        with self.assertRaises(ValueError):
            self.pm.parse("install xyzabc123unknownpackage")
    
    def test_case_insensitive(self):
        """Test that parsing is case insensitive."""
        commands1 = self.pm.parse("INSTALL PYTHON")
        commands2 = self.pm.parse("install python")
        self.assertEqual(commands1, commands2)
    
    def test_yum_package_manager(self):
        """Test YUM package manager commands."""
        pm_yum = PackageManager(pm_type=PackageManagerType.YUM)
        commands = pm_yum.parse("install python")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        self.assertIn("yum install", commands[0])
        # YUM should use different package names
        self.assertIn("python3", commands[0])
    
    def test_dnf_package_manager(self):
        """Test DNF package manager commands."""
        pm_dnf = PackageManager(pm_type=PackageManagerType.DNF)
        commands = pm_dnf.parse("install python")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        self.assertIn("dnf install", commands[0])
    
    def test_yum_apache_package_name(self):
        """Test that YUM uses correct package name for Apache."""
        pm_yum = PackageManager(pm_type=PackageManagerType.YUM)
        commands = pm_yum.parse("install apache")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        # YUM uses httpd, not apache2
        self.assertIn("httpd", commands[0])
    
    def test_package_name_variations(self):
        """Test that package name variations are handled."""
        # Test different ways to request Python
        commands1 = self.pm.parse("install python")
        commands2 = self.pm.parse("setup python3")
        commands3 = self.pm.parse("get python")
        
        # All should result in similar commands
        self.assertTrue(all("python3" in cmd for cmd in commands1))
        self.assertTrue(all("python3" in cmd for cmd in commands2))
        self.assertTrue(all("python3" in cmd for cmd in commands3))
    
    def test_multiple_software_requests(self):
        """Test requests that match multiple software categories."""
        commands = self.pm.parse("install python and docker and git")
        self.assertIsInstance(commands, list)
        self.assertTrue(len(commands) > 0)
        cmd = commands[0]
        # Should include packages from multiple categories
        self.assertIn("python3", cmd)
        self.assertIn("docker", cmd)
        self.assertIn("git", cmd)
    
    def test_normalize_text(self):
        """Test text normalization."""
        normalized = self.pm._normalize_text("  INSTALL   Python!!!  ")
        self.assertEqual(normalized, "install python")
    
    def test_extract_action(self):
        """Test action extraction."""
        self.assertEqual(self.pm._extract_action("install python"), "install")
        self.assertEqual(self.pm._extract_action("remove docker"), "remove")
        self.assertEqual(self.pm.parse("setup git")[0], "apt install -y git")
    
    @patch('cortex.packages.subprocess.run')
    def test_get_package_info_apt(self, mock_run):
        """Test getting package info for apt."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Package: python3\nVersion: 3.10.0\nDescription: Python interpreter"
        )
        info = self.pm.get_package_info("python3")
        self.assertIsNotNone(info)
        self.assertIn("Package", info)
    
    @patch('cortex.packages.subprocess.run')
    def test_get_package_info_yum(self, mock_run):
        """Test getting package info for yum."""
        pm_yum = PackageManager(pm_type=PackageManagerType.YUM)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Name: python3\nVersion: 3.10.0\nDescription: Python interpreter"
        )
        info = pm_yum.get_package_info("python3")
        self.assertIsNotNone(info)
    
    def test_comprehensive_software_requests(self):
        """Test 20+ common software requests as per requirements."""
        test_cases = [
            ("install python", ["python3"]),
            ("install python development tools", ["python3-dev", "build-essential"]),
            ("install python with data science libraries", ["python3-numpy", "python3-pandas"]),
            ("install docker", ["docker.io"]),
            ("install mysql", ["mysql-server"]),
            ("install postgresql", ["postgresql"]),
            ("install nginx", ["nginx"]),
            ("install apache", ["apache2"]),
            ("install git", ["git"]),
            ("install nodejs", ["nodejs"]),
            ("install redis", ["redis-server"]),
            ("install build tools", ["build-essential"]),
            ("install system monitoring", ["htop"]),
            ("install network tools", ["net-tools"]),
            ("install security tools", ["ufw"]),
            ("install text editors", ["vim"]),
            ("install version control", ["git"]),
            ("install compression tools", ["zip"]),
            ("install image tools", ["imagemagick"]),
            ("install kubernetes", ["kubectl"]),
            ("install web development", ["nodejs", "npm"]),
            ("install python machine learning", ["python3-numpy"]),
        ]
        
        for request, expected_packages in test_cases:
            with self.subTest(request=request):
                commands = self.pm.parse(request)
                self.assertIsInstance(commands, list)
                self.assertTrue(len(commands) > 0)
                cmd = commands[0]
                # Check that at least one expected package is in the command
                self.assertTrue(
                    any(pkg in cmd for pkg in expected_packages),
                    f"Expected one of {expected_packages} in command: {cmd}"
                )


if __name__ == "__main__":
    unittest.main()

