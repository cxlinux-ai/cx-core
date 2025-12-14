import shutil
import gzip
import logging
from typing import List, Dict
from pathlib import Path
from cortex.utils.commands import run_command
from cortex.cleanup.scanner import CleanupScanner, ScanResult
from cortex.cleanup.manager import CleanupManager

logger = logging.getLogger(__name__)

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
        freed_bytes = 0
        for line in stdout.splitlines():
            if "disk space will be freed" in line:
                parts = line.split()
                try:
                    for i, part in enumerate(parts):
                        if part.isdigit() or part.replace('.', '', 1).isdigit():
                            val = float(part)
                            unit = parts[i+1]
                            if unit.upper().startswith('KB'):
                                freed_bytes = int(val * 1024)
                            elif unit.upper().startswith('MB'):
                                freed_bytes = int(val * 1024 * 1024)
                            elif unit.upper().startswith('GB'):
                                freed_bytes = int(val * 1024 * 1024 * 1024)
                            break
                except Exception:
                    pass
        return freed_bytes

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
            "Package Cache": 0,
            "Orphaned Packages": 0,
            "Temporary Files": 0,
            "Old Logs": 0
        }
        
        for result in scan_results:
            if result.category == "Package Cache":
                summary["Package Cache"] = self.clean_package_cache()
                
            elif result.category == "Orphaned Packages":
                # Only remove orphaned packages in non-safe mode
                if not safe:
                    summary["Orphaned Packages"] = self.remove_orphaned_packages(result.items)
                
            elif result.category == "Temporary Files":
                summary["Temporary Files"] = self.clean_temp_files(result.items)
                
            elif result.category == "Old Logs":
                summary["Old Logs"] = self.compress_logs(result.items)
                
        return summary
