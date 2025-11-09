"""
Unit tests for PackageManager class.
"""

import unittest
from unittest.mock import patch, MagicMock
from cortex.packages import (
    PackageManager,
    PackageManagerType,
    PackageManagerError,
    UnsupportedPackageManagerError
)


class TestPackageManager(unittest.TestCase):
    """Test cases for PackageManager class."""
    
    def test_init_with_apt(self):
        """Test initialization with apt package manager."""
        pm = PackageManager(package_manager="apt")
        self.assertEqual(pm.pm_type, PackageManagerType.APT)
    
    def test_init_with_yum(self):
        """Test initialization with yum package manager."""
        pm = PackageManager(package_manager="yum")
        self.assertEqual(pm.pm_type, PackageManagerType.YUM)
    
    def test_init_with_dnf(self):
        """Test initialization with dnf package manager."""
        pm = PackageManager(package_manager="dnf")
        self.assertEqual(pm.pm_type, PackageManagerType.DNF)
    
    def test_init_unsupported_manager(self):
        """Test initialization with unsupported package manager."""
        with self.assertRaises(UnsupportedPackageManagerError):
            PackageManager(package_manager="pacman")
    
    @patch('cortex.packages.subprocess.run')
    def test_auto_detect_apt(self, mock_run):
        """Test auto-detection of apt package manager."""
        mock_run.return_value = MagicMock(returncode=0)
        pm = PackageManager()
        # Should default to apt if detection works
        self.assertIn(pm.pm_type, [PackageManagerType.APT, PackageManagerType.YUM, 
                                    PackageManagerType.DNF])
    
    def test_parse_python_development(self):
        """Test parsing 'install python development tools'."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install python development tools")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        self.assertTrue(any("python3" in cmd for cmd in commands))
        self.assertTrue(any("python3-dev" in cmd or "python3-devel" in cmd 
                          for cmd in commands))
    
    def test_parse_python_data_science(self):
        """Test parsing 'install python with data science libraries'."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install python with data science libraries")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        # Should include numpy, pandas, or scipy
        commands_str = " ".join(commands)
        self.assertTrue(
            any(pkg in commands_str for pkg in ["numpy", "pandas", "scipy", "matplotlib"])
        )
    
    def test_parse_docker(self):
        """Test parsing docker installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install docker")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("docker" in commands_str)
    
    def test_parse_git(self):
        """Test parsing git installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install git")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("git" in commands_str)
    
    def test_parse_build_tools(self):
        """Test parsing build tools installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install build tools")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue(
            any(tool in commands_str for tool in ["build-essential", "gcc", "make"])
        )
    
    def test_parse_nodejs(self):
        """Test parsing nodejs installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install nodejs")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("nodejs" in commands_str)
    
    def test_parse_nginx(self):
        """Test parsing nginx installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install nginx")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("nginx" in commands_str)
    
    def test_parse_mysql(self):
        """Test parsing mysql installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install mysql")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("mysql" in commands_str)
    
    def test_parse_postgresql(self):
        """Test parsing postgresql installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install postgresql")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("postgresql" in commands_str)
    
    def test_parse_redis(self):
        """Test parsing redis installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install redis")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("redis" in commands_str)
    
    def test_parse_java(self):
        """Test parsing java installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install java")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("java" in commands_str or "jdk" in commands_str)
    
    def test_parse_go(self):
        """Test parsing go installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install go")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("golang" in commands_str or "go" in commands_str)
    
    def test_parse_rust(self):
        """Test parsing rust installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install rust")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("rust" in commands_str or "rustc" in commands_str)
    
    def test_parse_php(self):
        """Test parsing php installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install php")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("php" in commands_str)
    
    def test_parse_ruby(self):
        """Test parsing ruby installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install ruby")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("ruby" in commands_str)
    
    def test_parse_machine_learning(self):
        """Test parsing machine learning libraries."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install machine learning libraries")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue(
            any(lib in commands_str for lib in ["numpy", "scipy", "scikit"])
        )
    
    def test_parse_kubernetes(self):
        """Test parsing kubernetes installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install kubernetes")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("kubectl" in commands_str)
    
    def test_parse_ansible(self):
        """Test parsing ansible installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install ansible")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("ansible" in commands_str)
    
    def test_parse_terraform(self):
        """Test parsing terraform installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install terraform")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("terraform" in commands_str)
    
    def test_parse_ffmpeg(self):
        """Test parsing ffmpeg installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install ffmpeg")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("ffmpeg" in commands_str)
    
    def test_parse_libreoffice(self):
        """Test parsing libreoffice installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install libreoffice")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("libreoffice" in commands_str)
    
    def test_parse_firefox(self):
        """Test parsing firefox installation."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install firefox")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("firefox" in commands_str)
    
    def test_parse_multiple_categories(self):
        """Test parsing request that matches multiple categories."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install python with git and docker")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("python" in commands_str)
        self.assertTrue("git" in commands_str)
        self.assertTrue("docker" in commands_str)
    
    def test_parse_empty_input(self):
        """Test parsing empty input."""
        pm = PackageManager(package_manager="apt")
        with self.assertRaises(PackageManagerError):
            pm.parse("")
    
    def test_parse_whitespace_only(self):
        """Test parsing whitespace-only input."""
        pm = PackageManager(package_manager="apt")
        with self.assertRaises(PackageManagerError):
            pm.parse("   ")
    
    def test_parse_unknown_package(self):
        """Test parsing unknown package (should raise error or use fallback)."""
        pm = PackageManager(package_manager="apt")
        # This might raise an error or use fallback parsing
        try:
            commands = pm.parse("install xyz123unknownpackage")
            # If it doesn't raise, should return some command
            self.assertIsInstance(commands, list)
        except PackageManagerError:
            # This is acceptable behavior
            pass
    
    def test_parse_remove_action(self):
        """Test parsing remove action."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("remove python")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("remove" in commands_str)
        self.assertTrue("python" in commands_str)
    
    def test_parse_update_action(self):
        """Test parsing update action."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("update packages")
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0)
        commands_str = " ".join(commands)
        self.assertTrue("update" in commands_str)
    
    def test_yum_package_names(self):
        """Test that yum uses correct package names."""
        pm = PackageManager(package_manager="yum")
        commands = pm.parse("install apache")
        self.assertIsInstance(commands, list)
        commands_str = " ".join(commands)
        # Yum uses httpd, not apache2
        self.assertTrue("httpd" in commands_str)
    
    def test_dnf_package_names(self):
        """Test that dnf uses correct package names."""
        pm = PackageManager(package_manager="dnf")
        commands = pm.parse("install apache")
        self.assertIsInstance(commands, list)
        commands_str = " ".join(commands)
        # DNF uses httpd, not apache2
        self.assertTrue("httpd" in commands_str)
    
    def test_get_supported_software(self):
        """Test getting list of supported software."""
        pm = PackageManager(package_manager="apt")
        supported = pm.get_supported_software()
        self.assertIsInstance(supported, list)
        self.assertGreater(len(supported), 20)  # Should have 20+ categories
        self.assertIn("python_dev", supported)
        self.assertIn("docker", supported)
        self.assertIn("git", supported)
    
    def test_search_packages(self):
        """Test searching for packages."""
        pm = PackageManager(package_manager="apt")
        results = pm.search_packages("python")
        self.assertIsInstance(results, dict)
        self.assertGreater(len(results), 0)
    
    def test_apt_command_format(self):
        """Test that apt commands are formatted correctly."""
        pm = PackageManager(package_manager="apt")
        commands = pm.parse("install git")
        self.assertIsInstance(commands, list)
        # Should include update command
        self.assertTrue(any("apt update" in cmd for cmd in commands))
        # Should include install command
        self.assertTrue(any("apt install" in cmd for cmd in commands))
        # Should include -y flag
        install_cmd = [cmd for cmd in commands if "install" in cmd][0]
        self.assertTrue("-y" in install_cmd)
    
    def test_yum_command_format(self):
        """Test that yum commands are formatted correctly."""
        pm = PackageManager(package_manager="yum")
        commands = pm.parse("install git")
        self.assertIsInstance(commands, list)
        # Should include update command
        self.assertTrue(any("yum update" in cmd for cmd in commands))
        # Should include install command
        self.assertTrue(any("yum install" in cmd for cmd in commands))
        # Should include -y flag
        install_cmd = [cmd for cmd in commands if "install" in cmd][0]
        self.assertTrue("-y" in install_cmd)
    
    def test_dnf_command_format(self):
        """Test that dnf commands are formatted correctly."""
        pm = PackageManager(package_manager="dnf")
        commands = pm.parse("install git")
        self.assertIsInstance(commands, list)
        # Should include update command
        self.assertTrue(any("dnf update" in cmd for cmd in commands))
        # Should include install command
        self.assertTrue(any("dnf install" in cmd for cmd in commands))
        # Should include -y flag
        install_cmd = [cmd for cmd in commands if "install" in cmd][0]
        self.assertTrue("-y" in install_cmd)
    
    def test_case_insensitive_matching(self):
        """Test that matching is case insensitive."""
        pm = PackageManager(package_manager="apt")
        commands1 = pm.parse("INSTALL PYTHON")
        commands2 = pm.parse("install python")
        commands3 = pm.parse("Install Python")
        
        # All should produce similar results
        self.assertIsInstance(commands1, list)
        self.assertIsInstance(commands2, list)
        self.assertIsInstance(commands3, list)
        self.assertGreater(len(commands1), 0)
        self.assertGreater(len(commands2), 0)
        self.assertGreater(len(commands3), 0)


class TestPackageManagerEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""
    
    def test_variations_python_dev(self):
        """Test various ways to request python development tools."""
        pm = PackageManager(package_manager="apt")
        variations = [
            "install python development tools",
            "install python dev",
            "install python development",
            "install python programming tools"
        ]
        
        for variation in variations:
            commands = pm.parse(variation)
            self.assertIsInstance(commands, list)
            self.assertGreater(len(commands), 0)
            commands_str = " ".join(commands)
            self.assertTrue("python" in commands_str)
    
    def test_variations_data_science(self):
        """Test various ways to request data science libraries."""
        pm = PackageManager(package_manager="apt")
        variations = [
            "install python with data science libraries",
            "install data science libraries",
            "install numpy pandas",
            "install jupyter"
        ]
        
        for variation in variations:
            commands = pm.parse(variation)
            self.assertIsInstance(commands, list)
            self.assertGreater(len(commands), 0)


if __name__ == '__main__':
    unittest.main()
