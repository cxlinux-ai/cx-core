"""
Package Manager Wrapper for Cortex Linux

This module provides a natural language interface to package managers (apt, yum),
translating user-friendly descriptions into correct package installation commands.
"""

import re
import subprocess
import platform
from typing import List, Dict, Set, Optional, Tuple
from enum import Enum


class PackageManagerType(Enum):
    """Supported package manager types."""
    APT = "apt"  # Debian/Ubuntu
    YUM = "yum"  # RHEL/CentOS/Fedora (older versions)
    DNF = "dnf"  # RHEL/CentOS/Fedora (newer versions)


class PackageManagerError(Exception):
    """Base exception for package manager operations."""
    pass


class UnsupportedPackageManagerError(PackageManagerError):
    """Raised when the system's package manager is not supported."""
    pass


class PackageManager:
    """
    Intelligent package manager wrapper that translates natural language
    into package installation commands.
    
    Example:
        pm = PackageManager()
        commands = pm.parse("install python with data science libraries")
        # Returns: ["apt install -y python3 python3-pip python3-numpy python3-pandas"]
    """
    
    def __init__(self, package_manager: Optional[str] = None):
        """
        Initialize the PackageManager.
        
        Args:
            package_manager: Optional package manager type ('apt', 'yum', 'dnf').
                           If None, auto-detects based on system.
        """
        if package_manager:
            try:
                self.pm_type = PackageManagerType(package_manager.lower())
            except ValueError:
                raise UnsupportedPackageManagerError(
                    f"Unsupported package manager: {package_manager}. "
                    f"Supported: {[pm.value for pm in PackageManagerType]}"
                )
        else:
            self.pm_type = self._detect_package_manager()
        
        self._knowledge_base = self._build_knowledge_base()
    
    def _detect_package_manager(self) -> PackageManagerType:
        """Detect the system's package manager."""
        try:
            # Check for apt (Debian/Ubuntu)
            result = subprocess.run(
                ['which', 'apt'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return PackageManagerType.APT
            
            # Check for dnf (Fedora/RHEL 8+)
            result = subprocess.run(
                ['which', 'dnf'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return PackageManagerType.DNF
            
            # Check for yum (RHEL/CentOS 7 and older)
            result = subprocess.run(
                ['which', 'yum'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return PackageManagerType.YUM
            
            # Default to apt if detection fails (most common case)
            return PackageManagerType.APT
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            # Default to apt
            return PackageManagerType.APT
    
    def _build_knowledge_base(self) -> Dict[str, Dict[str, List[str]]]:
        """
        Build knowledge base of common software requests.
        
        Structure:
        {
            "category": {
                "keywords": ["package1", "package2", ...],
                "packages": {
                    "apt": ["package1", "package2", ...],
                    "yum": ["package1", "package2", ...],
                    "dnf": ["package1", "package2", ...]
                }
            }
        }
        """
        return {
            "python_dev": {
                "keywords": ["python", "development", "dev", "programming", "scripting"],
                "packages": {
                    "apt": ["python3", "python3-pip", "python3-dev", "python3-venv"],
                    "yum": ["python3", "python3-pip", "python3-devel"],
                    "dnf": ["python3", "python3-pip", "python3-devel"]
                }
            },
            "python_data_science": {
                "keywords": ["data science", "data science libraries", "numpy", "pandas", 
                           "scipy", "matplotlib", "jupyter", "data analysis"],
                "packages": {
                    "apt": ["python3", "python3-pip", "python3-numpy", "python3-pandas",
                           "python3-scipy", "python3-matplotlib", "jupyter", "ipython3"],
                    "yum": ["python3", "python3-pip", "python3-numpy", "python3-pandas",
                           "python3-scipy", "python3-matplotlib", "jupyter"],
                    "dnf": ["python3", "python3-pip", "python3-numpy", "python3-pandas",
                           "python3-scipy", "python3-matplotlib", "jupyter"]
                }
            },
            "python_ml": {
                "keywords": ["machine learning", "ml", "tensorflow", "pytorch", 
                           "scikit-learn", "keras"],
                "packages": {
                    "apt": ["python3", "python3-pip", "python3-numpy", "python3-scipy",
                           "python3-matplotlib", "python3-scikit-learn"],
                    "yum": ["python3", "python3-pip", "python3-numpy", "python3-scipy",
                           "python3-matplotlib", "python3-scikit-learn"],
                    "dnf": ["python3", "python3-pip", "python3-numpy", "python3-scipy",
                           "python3-matplotlib", "python3-scikit-learn"]
                }
            },
            "nodejs": {
                "keywords": ["node", "nodejs", "node.js", "npm", "javascript runtime"],
                "packages": {
                    "apt": ["nodejs", "npm"],
                    "yum": ["nodejs", "npm"],
                    "dnf": ["nodejs", "npm"]
                }
            },
            "docker": {
                "keywords": ["docker", "container", "containers"],
                "packages": {
                    "apt": ["docker.io", "docker-compose"],
                    "yum": ["docker", "docker-compose"],
                    "dnf": ["docker", "docker-compose"]
                }
            },
            "git": {
                "keywords": ["git", "version control", "vcs"],
                "packages": {
                    "apt": ["git"],
                    "yum": ["git"],
                    "dnf": ["git"]
                }
            },
            "build_tools": {
                "keywords": ["build tools", "build-essential", "compiler", "gcc", "g++", 
                           "make", "cmake", "development tools"],
                "packages": {
                    "apt": ["build-essential", "gcc", "g++", "make", "cmake"],
                    "yum": ["gcc", "gcc-c++", "make", "cmake"],
                    "dnf": ["gcc", "gcc-c++", "make", "cmake", "cmake-data"]
                }
            },
            "curl_wget": {
                "keywords": ["curl", "wget", "download", "http client"],
                "packages": {
                    "apt": ["curl", "wget"],
                    "yum": ["curl", "wget"],
                    "dnf": ["curl", "wget"]
                }
            },
            "vim": {
                "keywords": ["vim", "vi", "text editor", "editor"],
                "packages": {
                    "apt": ["vim"],
                    "yum": ["vim"],
                    "dnf": ["vim"]
                }
            },
            "nginx": {
                "keywords": ["nginx", "web server", "http server"],
                "packages": {
                    "apt": ["nginx"],
                    "yum": ["nginx"],
                    "dnf": ["nginx"]
                }
            },
            "apache": {
                "keywords": ["apache", "apache2", "httpd", "web server"],
                "packages": {
                    "apt": ["apache2"],
                    "yum": ["httpd"],
                    "dnf": ["httpd"]
                }
            },
            "mysql": {
                "keywords": ["mysql", "database", "sql database"],
                "packages": {
                    "apt": ["mysql-server", "mysql-client"],
                    "yum": ["mysql-server", "mysql"],
                    "dnf": ["mysql-server", "mysql"]
                }
            },
            "postgresql": {
                "keywords": ["postgresql", "postgres", "postgresql database"],
                "packages": {
                    "apt": ["postgresql", "postgresql-contrib"],
                    "yum": ["postgresql-server", "postgresql"],
                    "dnf": ["postgresql-server", "postgresql"]
                }
            },
            "redis": {
                "keywords": ["redis", "cache", "redis cache"],
                "packages": {
                    "apt": ["redis-server"],
                    "yum": ["redis"],
                    "dnf": ["redis"]
                }
            },
            "mongodb": {
                "keywords": ["mongodb", "mongo", "nosql database"],
                "packages": {
                    "apt": ["mongodb"],
                    "yum": ["mongodb-server"],
                    "dnf": ["mongodb-server"]
                }
            },
            "java": {
                "keywords": ["java", "jdk", "java development kit", "openjdk"],
                "packages": {
                    "apt": ["default-jdk", "openjdk-11-jdk"],
                    "yum": ["java-11-openjdk-devel"],
                    "dnf": ["java-11-openjdk-devel"]
                }
            },
            "go": {
                "keywords": ["go", "golang", "go programming"],
                "packages": {
                    "apt": ["golang-go"],
                    "yum": ["golang"],
                    "dnf": ["golang"]
                }
            },
            "rust": {
                "keywords": ["rust", "rustc", "cargo", "rust programming"],
                "packages": {
                    "apt": ["rustc", "cargo"],
                    "yum": ["rust", "cargo"],
                    "dnf": ["rust", "cargo"]
                }
            },
            "ruby": {
                "keywords": ["ruby", "ruby programming"],
                "packages": {
                    "apt": ["ruby", "ruby-dev"],
                    "yum": ["ruby", "ruby-devel"],
                    "dnf": ["ruby", "ruby-devel"]
                }
            },
            "php": {
                "keywords": ["php", "php programming"],
                "packages": {
                    "apt": ["php", "php-cli", "php-fpm"],
                    "yum": ["php", "php-cli", "php-fpm"],
                    "dnf": ["php", "php-cli", "php-fpm"]
                }
            },
            "python_web": {
                "keywords": ["django", "flask", "python web", "web framework"],
                "packages": {
                    "apt": ["python3", "python3-pip", "python3-venv"],
                    "yum": ["python3", "python3-pip"],
                    "dnf": ["python3", "python3-pip"]
                }
            },
            "kubernetes": {
                "keywords": ["kubernetes", "k8s", "kubectl"],
                "packages": {
                    "apt": ["kubectl"],
                    "yum": ["kubectl"],
                    "dnf": ["kubectl"]
                }
            },
            "ansible": {
                "keywords": ["ansible", "configuration management"],
                "packages": {
                    "apt": ["ansible"],
                    "yum": ["ansible"],
                    "dnf": ["ansible"]
                }
            },
            "terraform": {
                "keywords": ["terraform", "infrastructure as code"],
                "packages": {
                    "apt": ["terraform"],
                    "yum": ["terraform"],
                    "dnf": ["terraform"]
                }
            },
            "vim_plugins": {
                "keywords": ["vim plugins", "vim configuration"],
                "packages": {
                    "apt": ["vim", "vim-addon-manager"],
                    "yum": ["vim", "vim-enhanced"],
                    "dnf": ["vim", "vim-enhanced"]
                }
            },
            "media_tools": {
                "keywords": ["ffmpeg", "media", "video", "audio", "multimedia"],
                "packages": {
                    "apt": ["ffmpeg", "libavcodec-extra"],
                    "yum": ["ffmpeg", "ffmpeg-devel"],
                    "dnf": ["ffmpeg", "ffmpeg-devel"]
                }
            },
            "graphics": {
                "keywords": ["graphics", "gimp", "image editing"],
                "packages": {
                    "apt": ["gimp"],
                    "yum": ["gimp"],
                    "dnf": ["gimp"]
                }
            },
            "office": {
                "keywords": ["libreoffice", "office", "word processor", "spreadsheet"],
                "packages": {
                    "apt": ["libreoffice"],
                    "yum": ["libreoffice"],
                    "dnf": ["libreoffice"]
                }
            },
            "browser": {
                "keywords": ["firefox", "chrome", "browser", "web browser"],
                "packages": {
                    "apt": ["firefox"],
                    "yum": ["firefox"],
                    "dnf": ["firefox"]
                }
            },
            "network_tools": {
                "keywords": ["netcat", "nmap", "network", "networking tools"],
                "packages": {
                    "apt": ["netcat", "nmap"],
                    "yum": ["nc", "nmap"],
                    "dnf": ["nc", "nmap"]
                }
            },
            "ssh": {
                "keywords": ["ssh", "openssh", "remote access"],
                "packages": {
                    "apt": ["openssh-client", "openssh-server"],
                    "yum": ["openssh-clients", "openssh-server"],
                    "dnf": ["openssh-clients", "openssh-server"]
                }
            },
            "security_tools": {
                "keywords": ["security", "fail2ban", "ufw", "firewall"],
                "packages": {
                    "apt": ["fail2ban", "ufw"],
                    "yum": ["fail2ban", "firewalld"],
                    "dnf": ["fail2ban", "firewalld"]
                }
            }
        }
    
    def _normalize_input(self, text: str) -> str:
        """Normalize input text for matching."""
        return text.lower().strip()
    
    def _find_matching_categories(self, text: str) -> List[Tuple[str, float]]:
        """
        Find matching categories based on keywords.
        Returns list of (category, score) tuples sorted by score.
        """
        normalized_text = self._normalize_input(text)
        matches = []
        
        for category, data in self._knowledge_base.items():
            keywords = data["keywords"]
            score = 0.0
            
            # Count keyword matches
            for keyword in keywords:
                if keyword in normalized_text:
                    # Longer keywords get higher weight
                    score += len(keyword) * 0.1
                    
                    # Exact match gets bonus
                    if normalized_text == keyword or f" {keyword} " in f" {normalized_text} ":
                        score += 1.0
            
            if score > 0:
                matches.append((category, score))
        
        # Sort by score (descending)
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
    
    def _merge_packages(self, categories: List[str]) -> Set[str]:
        """Merge packages from multiple categories, removing duplicates."""
        packages = set()
        
        for category in categories:
            if category in self._knowledge_base:
                pm_key = self.pm_type.value
                category_packages = self._knowledge_base[category]["packages"].get(
                    pm_key, []
                )
                packages.update(category_packages)
        
        return packages
    
    def _get_package_command(self, packages: Set[str], action: str = "install") -> str:
        """
        Generate the package manager command.
        
        Args:
            packages: Set of package names
            action: Action to perform (install, remove, update)
        
        Returns:
            Command string
        """
        # Update action doesn't require packages
        if action == "update":
            if self.pm_type == PackageManagerType.APT:
                return "apt update"
            elif self.pm_type == PackageManagerType.YUM:
                return "yum update"
            elif self.pm_type == PackageManagerType.DNF:
                return "dnf update"
            else:
                raise UnsupportedPackageManagerError(
                    f"Unsupported package manager: {self.pm_type}"
                )
        
        # Install and remove actions require packages
        if not packages:
            raise PackageManagerError(f"No packages to {action}")
        
        package_list = " ".join(sorted(packages))
        
        if self.pm_type == PackageManagerType.APT:
            if action == "install":
                return f"apt install -y {package_list}"
            elif action == "remove":
                return f"apt remove -y {package_list}"
            else:
                raise PackageManagerError(f"Unsupported action: {action}")
        
        elif self.pm_type == PackageManagerType.YUM:
            if action == "install":
                return f"yum install -y {package_list}"
            elif action == "remove":
                return f"yum remove -y {package_list}"
            else:
                raise PackageManagerError(f"Unsupported action: {action}")
        
        elif self.pm_type == PackageManagerType.DNF:
            if action == "install":
                return f"dnf install -y {package_list}"
            elif action == "remove":
                return f"dnf remove -y {package_list}"
            else:
                raise PackageManagerError(f"Unsupported action: {action}")
        
        else:
            raise UnsupportedPackageManagerError(
                f"Unsupported package manager: {self.pm_type}"
            )
    
    def parse(self, user_input: str) -> List[str]:
        """
        Parse natural language input and return package manager commands.
        
        Args:
            user_input: Natural language description of what to install
        
        Returns:
            List of commands to execute
        
        Raises:
            PackageManagerError: If parsing fails or no packages found
        """
        if not user_input or not user_input.strip():
            raise PackageManagerError("Input cannot be empty")
        
        normalized_input = self._normalize_input(user_input)
        
        # Detect action
        action = "install"
        if any(word in normalized_input for word in ["remove", "uninstall", "delete"]):
            action = "remove"
        elif any(word in normalized_input for word in ["update", "upgrade"]):
            action = "update"
        
        # Find matching categories
        matches = self._find_matching_categories(normalized_input)
        
        # Handle update command (no packages needed)
        # If it's just an update/upgrade request, return update command
        if action == "update":
            # Check if user wants to update specific packages or just update package list
            has_package_keywords = any(
                word in normalized_input for word in ["package", "packages", "software"]
            )
            # If no specific package is mentioned, just update package lists
            if not has_package_keywords:
                return [self._get_package_command(set(), action="update")]
            # If packages are mentioned but we can't match them, still just update
            # This handles cases like "update packages" or "upgrade system"
            if not matches:
                return [self._get_package_command(set(), action="update")]
        
        if not matches:
            # Try to extract package names directly from input
            # This is a fallback for unknown packages
            words = normalized_input.split()
            # Filter out common stop words
            stop_words = {"install", "with", "and", "or", "the", "a", "an", 
                         "for", "to", "of", "in", "on", "at", "by", "from"}
            potential_packages = [w for w in words if w not in stop_words and len(w) > 2]
            
            if potential_packages:
                # Assume these are package names
                packages = set(potential_packages)
                return [self._get_package_command(packages, action)]
            else:
                raise PackageManagerError(
                    f"Could not parse request: '{user_input}'. "
                    "No matching packages found."
                )
        
        # Get top matching categories (threshold: score > 0.5)
        top_categories = [
            cat for cat, score in matches if score > 0.5
        ]
        
        # If no high-scoring matches, use the top match anyway
        if not top_categories:
            top_categories = [matches[0][0]]
        
        # Merge packages from matching categories
        packages = self._merge_packages(top_categories)
        
        # Generate commands
        commands = []
        
        # Add update command before install for apt/yum/dnf
        if action == "install" and self.pm_type in [
            PackageManagerType.APT, PackageManagerType.YUM, PackageManagerType.DNF
        ]:
            commands.append(self._get_package_command(set(), action="update"))
        
        # Add install/remove command
        commands.append(self._get_package_command(packages, action))
        
        return commands
    
    def get_supported_software(self) -> List[str]:
        """
        Get list of supported software categories.
        
        Returns:
            List of software category names
        """
        return list(self._knowledge_base.keys())
    
    def search_packages(self, query: str) -> Dict[str, List[str]]:
        """
        Search for packages matching a query.
        
        Args:
            query: Search query
        
        Returns:
            Dictionary mapping categories to package lists
        """
        matches = self._find_matching_categories(query)
        result = {}
        
        pm_key = self.pm_type.value
        for category, score in matches:
            if score > 0.5:
                result[category] = self._knowledge_base[category]["packages"].get(
                    pm_key, []
                )
        
        return result
