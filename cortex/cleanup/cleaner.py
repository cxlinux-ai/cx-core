import shutil
import gzip
import logging
import re
from typing import List, Dict, Optional
from pathlib import Path
from cortex.utils.commands import run_command
from cortex.cleanup.scanner import CleanupScanner, ScanResult
from cortex.cleanup.manager import CleanupManager

logger = logging.getLogger(__name__)

# Category constants to avoid duplication
CATEGORY_PACKAGE_CACHE = "Package Cache"
CATEGORY_ORPHANED_PACKAGES = "Orphaned Packages"
CATEGORY_TEMP_FILES = "Temporary Files"
CATEGORY_OLD_LOGS = "Old Logs"

# Unit multipliers for parsing
UNIT_MULTIPLIERS = {
    'KB': 1024,
    'MB': 1024 * 1024,
    'GB': 1024 * 1024 * 1024,
}

class DiskCleaner:
    """
    Handles the actual cleanup operations including package cleaning,
    orphaned package removal, temp file deletion, and log compression.
    """
    def __init__(self, dry_run: bool = False):
        """
        Initialize the DiskCleaner.
        
        Args:
            dry_run (bool): If True, simulate actions without modifying the filesystem.
        """
        self.dry_run = dry_run
        self.scanner = CleanupScanner()
        self.manager = CleanupManager()

    def clean_package_cache(self) -> int:
        """
        Clean apt package cache using 'apt-get clean'.
        
        Returns:
            int: Number of bytes freed (estimated).
        """
        # Get size before cleaning for reporting
        scan_result = self.scanner.scan_package_cache()
        size_freed = scan_result.size_bytes
        
        if self.dry_run:
            return size_freed
            
        # Run apt-get clean (use -n for non-interactive mode)
        cmd = "sudo -n apt-get clean"
        result = run_command(cmd, validate=True)
        
        if result.success:
            return size_freed
        else:
            logger.error(f"Failed to clean package cache: {result.stderr}")
            return 0

    def remove_orphaned_packages(self, packages: List[str]) -> int:
        """
        Remove orphaned packages using 'apt-get autoremove'.
        
        Args:
            packages (List[str]): List of package names to remove.
            
        Returns:
            int: Number of bytes freed (estimated).
        """
        if not packages:
            return 0
            
        if self.dry_run:
            return 0 # Size is estimated in scanner
            
        # Use -n for non-interactive mode
        cmd = "sudo -n apt-get autoremove -y"
        result = run_command(cmd, validate=True)
        
        freed_bytes = 0
        if result.success:
            freed_bytes = self._parse_freed_space(result.stdout)
            return freed_bytes
        else:
            logger.error(f"Failed to remove orphaned packages: {result.stderr}")
            return 0

    def _parse_freed_space(self, stdout: str) -> int:
        """
        Helper to parse freed space from apt output.
        
        Args:
            stdout (str): Output from apt command.
            
        Returns:
            int: Bytes freed.
        """
        for line in stdout.splitlines():
            if "disk space will be freed" in line:
                return self._extract_size_from_line(line)
        return 0
    
    def _extract_size_from_line(self, line: str) -> int:
        """
        Extract size in bytes from a line containing size information.
        
        Args:
            line (str): Line containing size info like "50.5 MB".
            
        Returns:
            int: Size in bytes.
        """
        # Match patterns like "50.5 MB" or "512 KB"
        match = re.search(r'([\d.]+)\s*(KB|MB|GB)', line, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            unit = match.group(2).upper()
            return int(value * UNIT_MULTIPLIERS.get(unit, 1))
        return 0

    def clean_temp_files(self, files: List[str]) -> int:
        """
        Remove temporary files by moving them to quarantine.
        
        Args:
            files (List[str]): List of file paths to remove.
            
        Returns:
            int: Number of bytes freed (estimated).
        """
        freed_bytes = 0
        
        for filepath_str in files:
            filepath = Path(filepath_str)
            if not filepath.exists():
                continue
            
            # Get size before any operation
            try:
                size = filepath.stat().st_size
            except OSError:
                size = 0
                
            if self.dry_run:
                freed_bytes += size
                continue
                
            # Move to quarantine
            item_id = self.manager.quarantine_file(str(filepath))
            if item_id:
                freed_bytes += size
            else:
                logger.warning(f"Failed to quarantine temp file: {filepath}")
                
        return freed_bytes

    def compress_logs(self, files: List[str]) -> int:
        """
        Compress log files using gzip.
        
        Args:
            files (List[str]): List of log file paths to compress.
            
        Returns:
            int: Number of bytes freed.
        """
        freed_bytes = 0
        
        for filepath_str in files:
            filepath = Path(filepath_str)
            if not filepath.exists():
                continue
                
            try:
                original_size = filepath.stat().st_size
                
                if self.dry_run:
                    # Estimate compression ratio (e.g. 90% reduction)
                    freed_bytes += int(original_size * 0.9)
                    continue
                
                # Compress
                gz_path = filepath.with_suffix(filepath.suffix + '.gz')
                with open(filepath, 'rb') as f_in:
                    with gzip.open(gz_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Verify compressed file exists and has size
                if gz_path.exists():
                    compressed_size = gz_path.stat().st_size
                    # Remove original
                    filepath.unlink()
                    freed_bytes += (original_size - compressed_size)
                    
            except Exception as e:
                logger.error(f"Failed to compress {filepath}: {e}")
                
        return freed_bytes

    def run_cleanup(self, scan_results: List[ScanResult], safe: bool = True) -> Dict[str, int]:
        """
        Run cleanup based on scan results.
        
        Args:
            scan_results (List[ScanResult]): Results from scanner.
            safe (bool): If True, perform safe cleanup (default).
            
        Returns:
            Dict[str, int]: Summary of bytes freed per category.
        """
        summary = {
            CATEGORY_PACKAGE_CACHE: 0,
            CATEGORY_ORPHANED_PACKAGES: 0,
            CATEGORY_TEMP_FILES: 0,
            CATEGORY_OLD_LOGS: 0
        }
        
        for result in scan_results:
            freed = self._process_category(result, safe)
            if result.category in summary:
                summary[result.category] = freed
                
        return summary
    
    def _process_category(self, result: ScanResult, safe: bool) -> int:
        """
        Process a single cleanup category.
        
        Args:
            result (ScanResult): Scan result for the category.
            safe (bool): Whether to use safe mode.
            
        Returns:
            int: Bytes freed.
        """
        if result.category == CATEGORY_PACKAGE_CACHE:
            return self.clean_package_cache()
        elif result.category == CATEGORY_ORPHANED_PACKAGES:
            # Only remove orphaned packages in non-safe mode
            return self.remove_orphaned_packages(result.items) if not safe else 0
        elif result.category == CATEGORY_TEMP_FILES:
            return self.clean_temp_files(result.items)
        elif result.category == CATEGORY_OLD_LOGS:
            return self.compress_logs(result.items)
        return 0
