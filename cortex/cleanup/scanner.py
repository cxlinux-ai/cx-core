import time
import re
from dataclasses import dataclass, field
from typing import List, Tuple
from pathlib import Path
from cortex.utils.commands import run_command

# Unit multipliers for size parsing
UNIT_MULTIPLIERS = {
    'KB': 1024,
    'MB': 1024 * 1024,
    'GB': 1024 * 1024 * 1024,
}

@dataclass
class ScanResult:
    """
    Result of a cleanup scan operation.
    
    Args:
        category (str): The category of items scanned (e.g., "Package Cache").
        size_bytes (int): Total size of items in bytes.
        count (int): Number of items found.
        items (List[str]): List of file paths or item names found.
    """
    category: str
    size_bytes: int
    count: int
    items: List[str] = field(default_factory=list)

class CleanupScanner:
    """
    Scanner for identifying cleanup opportunities on the system.
    """
    def __init__(self):
        self.apt_cache_dir = Path("/var/cache/apt/archives")
        self.log_dir = Path("/var/log")
        self.temp_dirs = [Path("/tmp"), Path.home() / ".cache"]
        
    def scan_all(self) -> List[ScanResult]:
        """
        Run all scan methods and return combined results.
        
        Returns:
            List[ScanResult]: List of results from all scan categories.
        """
        results = []
        results.append(self.scan_package_cache())
        results.append(self.scan_orphaned_packages())
        results.append(self.scan_temp_files())
        results.append(self.scan_logs())
        return results

    def scan_package_cache(self) -> ScanResult:
        """
        Scan apt package cache size.
        
        Returns:
            ScanResult: Result containing size and count of cached packages.
        """
        total_size = 0
        files = []
        
        if self.apt_cache_dir.exists():
            for f in self.apt_cache_dir.glob("*.deb"):
                try:
                    size = f.stat().st_size
                    total_size += size
                    files.append(str(f))
                except OSError:
                    pass
                    
        return ScanResult(
            category="Package Cache",
            size_bytes=total_size,
            count=len(files),
            items=files
        )

    def scan_orphaned_packages(self) -> ScanResult:
        """
        Scan for orphaned packages using apt-get autoremove --simulate.
        
        Returns:
            ScanResult: Result containing estimated size and count of orphaned packages.
        """
        # Note: This requires apt-get to be installed
        cmd = "apt-get autoremove --simulate"
        # We use strict=False because apt-get might output to stderr which run_command captures
        result = run_command(cmd, validate=True)
        
        packages = []
        size_bytes = 0
        
        if result.success:
            packages, size_bytes = self._parse_autoremove_output(result.stdout)

        return ScanResult(
            category="Orphaned Packages",
            size_bytes=size_bytes,
            count=len(packages),
            items=packages
        )

    def _parse_autoremove_output(self, stdout: str) -> Tuple[List[str], int]:
        """
        Helper to parse apt-get autoremove output.
        
        Args:
            stdout (str): Output from apt-get command.
            
        Returns:
            Tuple[List[str], int]: List of packages and estimated size in bytes.
        """
        packages = self._extract_packages(stdout)
        size_bytes = self._extract_size(stdout)
        return packages, size_bytes
    
    def _extract_packages(self, stdout: str) -> List[str]:
        """
        Extract package names from autoremove output.
        
        Args:
            stdout (str): Output from apt-get command.
            
        Returns:
            List[str]: List of package names.
        """
        packages = []
        capture = False
        
        for line in stdout.splitlines():
            if "The following packages will be REMOVED" in line:
                capture = True
                continue
            if capture:
                if not line.startswith(" "):
                    capture = False
                    continue
                packages.extend(line.strip().split())
        
        return packages
    
    def _extract_size(self, stdout: str) -> int:
        """
        Extract size in bytes from apt output.
        
        Args:
            stdout (str): Output from apt-get command.
            
        Returns:
            int: Size in bytes.
        """
        for line in stdout.splitlines():
            if "disk space will be freed" in line:
                match = re.search(r'([\d.]+)\s*(KB|MB|GB)', line, re.IGNORECASE)
                if match:
                    value = float(match.group(1))
                    unit = match.group(2).upper()
                    return int(value * UNIT_MULTIPLIERS.get(unit, 1))
        return 0

    def scan_temp_files(self, days_old: int = 7) -> ScanResult:
        """
        Scan for temporary files older than X days.
        
        Args:
            days_old (int): Minimum age of files in days to include.
            
        Returns:
            ScanResult: Result containing size and count of old temp files.
        """
        total_size = 0
        files = []
        now = time.time()
        cutoff = now - (days_old * 86400)
        
        for temp_dir in self.temp_dirs:
            if not temp_dir.exists():
                continue
                
            for filepath in temp_dir.rglob("*"):
                if filepath.is_file():
                    try:
                        stat = filepath.stat()
                        # Check if file is older than cutoff
                        if stat.st_mtime < cutoff:
                            total_size += stat.st_size
                            files.append(str(filepath))
                    except OSError:
                        pass
                        
        return ScanResult(
            category="Temporary Files",
            size_bytes=total_size,
            count=len(files),
            items=files
        )

    def scan_logs(self, min_size_mb: int = 100, days_old: int = 7) -> ScanResult:
        """
        Scan for large, old log files.
        
        Args:
            min_size_mb (int): Minimum size in MB to include.
            days_old (int): Minimum age in days to include.
            
        Returns:
            ScanResult: Result containing size and count of old log files.
        """
        total_size = 0
        files = []
        now = time.time()
        cutoff = now - (days_old * 86400)
        min_size = min_size_mb * 1024 * 1024
        
        if self.log_dir.exists():
            for filepath in self.log_dir.rglob("*.log"):
                if filepath.is_file():
                    try:
                        stat = filepath.stat()
                        if stat.st_size > min_size and stat.st_mtime < cutoff:
                            total_size += stat.st_size
                            files.append(str(filepath))
                    except OSError:
                        pass
                        
        return ScanResult(
            category="Old Logs",
            size_bytes=total_size,
            count=len(files),
            items=files
        )
