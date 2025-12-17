#!/usr/bin/env python3
"""
Intelligent Package Manager Wrapper for Cortex Linux

Translates natural language requests into apt/yum package manager commands.
Supports common software installations, development tools, and libraries.
"""

import re
import subprocess
from enum import Enum


class PackageManagerType(Enum):
    """Supported package manager types."""

    APT = "apt"  # Ubuntu/Debian
    YUM = "yum"  # RHEL/CentOS/Fedora (older)
    DNF = "dnf"  # RHEL/CentOS/Fedora (newer)


class PackageManager:
    """
    Intelligent wrapper that translates natural language into package manager commands.

    Example:
        pm = PackageManager()
        commands = pm.parse("install python with data science libraries")
        # Returns: ["apt install python3 python3-pip python3-numpy python3-pandas python3-scipy"]
    """

    def __init__(self, pm_type: PackageManagerType | None = None):
        """
        Initialize the package manager.

        Args:
            pm_type: Package manager type (auto-detected if None)
        """
        self.pm_type = pm_type or self._detect_package_manager()
        self.package_mappings = self._build_package_mappings()
        self.action_patterns = self._build_action_patterns()

    def _detect_package_manager(self) -> PackageManagerType:
        """Detect the package manager based on the system."""
        try:
            # Check for apt
            result = subprocess.run(["which", "apt"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return PackageManagerType.APT

            # Check for dnf (preferred over yum on newer systems)
            result = subprocess.run(["which", "dnf"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return PackageManagerType.DNF

            # Check for yum
            result = subprocess.run(["which", "yum"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return PackageManagerType.YUM
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Default to apt (most common)
        return PackageManagerType.APT

    def _build_action_patterns(self) -> dict[str, list[str]]:
        """Build regex patterns for common actions."""
        return {
            "install": [
                r"\binstall\b",
                r"\bsetup\b",
                r"\bget\b",
                r"\badd\b",
                r"\bfetch\b",
                r"\bdownload\b",
            ],
            "remove": [
                r"\bremove\b",
                r"\buninstall\b",
                r"\bdelete\b",
                r"\bpurge\b",
            ],
            "update": [
                r"\bupdate\b",
                r"\bupgrade\b",
                r"\brefresh\b",
            ],
            "search": [
                r"\bsearch\b",
                r"\bfind\b",
                r"\blookup\b",
            ],
        }

    def _build_package_mappings(self) -> dict[str, dict[str, list[str]]]:
        """
        Build comprehensive package mappings for common software requests.
        Maps natural language terms to actual package names for apt/yum.
        """
        return {
            # Python and development tools
            "python": {
                "apt": ["python3", "python3-pip", "python3-venv"],
                "yum": ["python3", "python3-pip"],
            },
            "python development": {
                "apt": ["python3-dev", "python3-pip", "build-essential"],
                "yum": ["python3-devel", "python3-pip", "gcc", "gcc-c++", "make"],
            },
            "python data science": {
                "apt": [
                    "python3",
                    "python3-pip",
                    "python3-numpy",
                    "python3-pandas",
                    "python3-scipy",
                    "python3-matplotlib",
                    "python3-jupyter",
                ],
                "yum": [
                    "python3",
                    "python3-pip",
                    "python3-numpy",
                    "python3-pandas",
                    "python3-scipy",
                    "python3-matplotlib",
                ],
            },
            "python machine learning": {
                "apt": [
                    "python3",
                    "python3-pip",
                    "python3-numpy",
                    "python3-scipy",
                    "python3-scikit-learn",
                    "python3-tensorflow",
                    "python3-keras",
                ],
                "yum": ["python3", "python3-pip", "python3-numpy", "python3-scipy"],
            },
            # Web development
            "web development": {
                "apt": ["nodejs", "npm", "git", "curl", "wget"],
                "yum": ["nodejs", "npm", "git", "curl", "wget"],
            },
            "nodejs": {
                "apt": ["nodejs", "npm"],
                "yum": ["nodejs", "npm"],
            },
            "docker": {
                "apt": ["docker.io", "docker-compose"],
                "yum": ["docker", "docker-compose"],
            },
            "nginx": {
                "apt": ["nginx"],
                "yum": ["nginx"],
            },
            "apache": {
                "apt": ["apache2"],
                "yum": ["httpd"],
            },
            # Database
            "mysql": {
                "apt": ["mysql-server", "mysql-client"],
                "yum": ["mysql-server", "mysql"],
            },
            "postgresql": {
                "apt": ["postgresql", "postgresql-contrib"],
                "yum": ["postgresql-server", "postgresql"],
            },
            "mongodb": {
                "apt": ["mongodb"],
                "yum": ["mongodb-server", "mongodb"],
            },
            "redis": {
                "apt": ["redis-server"],
                "yum": ["redis"],
            },
            # Development tools
            "build tools": {
                "apt": ["build-essential", "gcc", "g++", "make", "cmake"],
                "yum": ["gcc", "gcc-c++", "make", "cmake"],
            },
            "git": {
                "apt": ["git"],
                "yum": ["git"],
            },
            "vim": {
                "apt": ["vim"],
                "yum": ["vim"],
            },
            "emacs": {
                "apt": ["emacs"],
                "yum": ["emacs"],
            },
            "curl": {
                "apt": ["curl"],
                "yum": ["curl"],
            },
            "wget": {
                "apt": ["wget"],
                "yum": ["wget"],
            },
            # System utilities
            "system monitoring": {
                "apt": ["htop", "iotop", "nethogs", "sysstat"],
                "yum": ["htop", "iotop", "nethogs", "sysstat"],
            },
            "network tools": {
                "apt": ["net-tools", "iputils-ping", "tcpdump", "wireshark"],
                "yum": ["net-tools", "iputils", "tcpdump", "wireshark"],
            },
            "compression tools": {
                "apt": ["zip", "unzip", "gzip", "bzip2", "xz-utils"],
                "yum": ["zip", "unzip", "gzip", "bzip2", "xz"],
            },
            # Media and graphics
            "image tools": {
                "apt": ["imagemagick", "ffmpeg", "libjpeg-dev", "libpng-dev"],
                "yum": ["ImageMagick", "ffmpeg", "libjpeg-turbo-devel", "libpng-devel"],
            },
            "video tools": {
                "apt": ["ffmpeg", "vlc"],
                "yum": ["ffmpeg", "vlc"],
            },
            # Security tools
            "security tools": {
                "apt": ["ufw", "fail2ban", "openssh-server", "ssl-cert"],
                "yum": ["firewalld", "fail2ban", "openssh-server"],
            },
            "firewall": {
                "apt": ["ufw"],
                "yum": ["firewalld"],
            },
            # Cloud and containers
            "kubernetes": {
                "apt": ["kubectl"],
                "yum": ["kubectl"],
            },
            "terraform": {
                "apt": ["terraform"],
                "yum": ["terraform"],
            },
            # Text processing
            "text editors": {
                "apt": ["vim", "nano", "emacs"],
                "yum": ["vim", "nano", "emacs"],
            },
            # Version control
            "version control": {
                "apt": ["git", "subversion"],
                "yum": ["git", "subversion"],
            },
        }

    def _normalize_text(self, text: str) -> str:
        """Normalize input text for matching."""
        # Convert to lowercase and remove extra whitespace
        text = text.lower().strip()
        # Remove common punctuation
        text = re.sub(r"[^\w\s]", " ", text)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        # Final strip to remove any leading/trailing whitespace
        return text.strip()

    def _extract_action(self, text: str) -> str:
        """Extract the action (install, remove, etc.) from the text."""
        normalized = self._normalize_text(text)

        for action, patterns in self.action_patterns.items():
            for pattern in patterns:
                if re.search(pattern, normalized):
                    return action

        # Default to install if no action specified
        return "install"

    def _find_matching_packages(self, text: str) -> list[str]:
        """
        Find matching packages based on natural language input.
        Returns list of package names.
        """
        normalized = self._normalize_text(text)
        matched_packages = set()

        # Get the appropriate package manager key
        pm_key = "apt" if self.pm_type == PackageManagerType.APT else "yum"

        # Handle Python with priority - check most specific first
        if "python" in normalized:
            if "machine learning" in normalized or "ml" in normalized:
                matched_packages.update(
                    self.package_mappings["python machine learning"].get(pm_key, [])
                )
            elif "data science" in normalized:
                matched_packages.update(
                    self.package_mappings["python data science"].get(pm_key, [])
                )
            elif "development" in normalized or "dev" in normalized:
                matched_packages.update(self.package_mappings["python development"].get(pm_key, []))
            else:
                # Basic python - only include basic packages
                matched_packages.update(self.package_mappings["python"].get(pm_key, []))

        # Handle other specific combinations
        if "web" in normalized and "development" in normalized:
            matched_packages.update(self.package_mappings["web development"].get(pm_key, []))

        if "build" in normalized and "tools" in normalized:
            matched_packages.update(self.package_mappings["build tools"].get(pm_key, []))

        if "system" in normalized and "monitoring" in normalized:
            matched_packages.update(self.package_mappings["system monitoring"].get(pm_key, []))

        if "network" in normalized and "tools" in normalized:
            matched_packages.update(self.package_mappings["network tools"].get(pm_key, []))

        if "security" in normalized and "tools" in normalized:
            matched_packages.update(self.package_mappings["security tools"].get(pm_key, []))

        if "text" in normalized and "editor" in normalized:
            matched_packages.update(self.package_mappings["text editors"].get(pm_key, []))

        if "version" in normalized and "control" in normalized:
            matched_packages.update(self.package_mappings["version control"].get(pm_key, []))

        if "compression" in normalized and "tools" in normalized:
            matched_packages.update(self.package_mappings["compression tools"].get(pm_key, []))

        if "image" in normalized and "tools" in normalized:
            matched_packages.update(self.package_mappings["image tools"].get(pm_key, []))

        # Handle exact key matches for multi-word categories
        for key, packages in self.package_mappings.items():
            # Skip single-word software (handled separately) and Python (handled above)
            if " " in key and key not in [
                "python",
                "python development",
                "python data science",
                "python machine learning",
            ]:
                if key in normalized:
                    matched_packages.update(packages.get(pm_key, []))

        # Handle individual software packages (only if not already matched above)
        # Check for exact key matches for single-word software
        single_software = {
            "docker",
            "nginx",
            "apache",
            "mysql",
            "postgresql",
            "mongodb",
            "redis",
            "git",
            "vim",
            "emacs",
            "curl",
            "wget",
            "nodejs",
            "kubernetes",
            "terraform",
        }

        for software in single_software:
            # Only match if it's a standalone word or exact match
            if software in normalized:
                # Check if it's part of a larger phrase (e.g., "docker-compose" contains "docker")
                # but we want to match "docker" as a standalone request
                words = normalized.split()
                if (
                    software in words
                    or normalized == software
                    or normalized.startswith(software + " ")
                    or normalized.endswith(" " + software)
                ):
                    if software in self.package_mappings:
                        matched_packages.update(self.package_mappings[software].get(pm_key, []))

        return sorted(matched_packages)

    def parse(self, request: str) -> list[str]:
        """
        Parse natural language request and return package manager commands.

        Args:
            request: Natural language request (e.g., "install python with data science libraries")

        Returns:
            List of package manager commands

        Raises:
            ValueError: If request cannot be parsed or no packages found
        """
        if not request or not request.strip():
            raise ValueError("Empty request provided")

        action = self._extract_action(request)
        packages = self._find_matching_packages(request)

        if not packages:
            raise ValueError(f"No matching packages found for: {request}")

        # Build command based on package manager type
        if self.pm_type == PackageManagerType.APT:
            if action == "install":
                return [f"apt install -y {' '.join(packages)}"]
            elif action == "remove":
                return [f"apt remove -y {' '.join(packages)}"]
            elif action == "update":
                return ["apt update", f"apt upgrade -y {' '.join(packages)}"]
            elif action == "search":
                return [f"apt search {' '.join(packages)}"]

        elif self.pm_type in (PackageManagerType.YUM, PackageManagerType.DNF):
            pm_cmd = "yum" if self.pm_type == PackageManagerType.YUM else "dnf"
            if action == "install":
                return [f"{pm_cmd} install -y {' '.join(packages)}"]
            elif action == "remove":
                return [f"{pm_cmd} remove -y {' '.join(packages)}"]
            elif action == "update":
                return [f"{pm_cmd} update -y {' '.join(packages)}"]
            elif action == "search":
                return [f"{pm_cmd} search {' '.join(packages)}"]

        return []

    def get_package_info(self, package_name: str) -> dict[str, str] | None:
        """
        Get information about a specific package.

        Args:
            package_name: Name of the package

        Returns:
            Dictionary with package information or None if not found
        """
        try:
            if self.pm_type == PackageManagerType.APT:
                result = subprocess.run(
                    ["apt-cache", "show", package_name], capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    info = {}
                    for line in result.stdout.split("\n"):
                        if ":" in line:
                            key, value = line.split(":", 1)
                            info[key.strip()] = value.strip()
                    return info

            elif self.pm_type in (PackageManagerType.YUM, PackageManagerType.DNF):
                pm_cmd = "yum" if self.pm_type == PackageManagerType.YUM else "dnf"
                result = subprocess.run(
                    [pm_cmd, "info", package_name], capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    info = {}
                    for line in result.stdout.split("\n"):
                        if ":" in line:
                            key, value = line.split(":", 1)
                            info[key.strip()] = value.strip()
                    return info
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None
