
import os
import shutil
import glob
import logging
import gzip
from typing import Dict, List, Tuple, Any
from pathlib import Path
from cortex.packages import PackageManager

class DiskOptimizer:
    """
    Smart Cleanup and Disk Space Optimizer.
    Handles scanning for cleanable items and performing safe cleanup.
    """
    
    def __init__(self):
        self.pm = PackageManager()
        self.logger = logging.getLogger("cortex.optimizer")
        
    def scan(self) -> Dict[str, Any]:
        """
        Scan system for cleanup opportunities.
        
        Returns:
            Dictionary containing cleanup stats
        """
        result = {
            "package_cache": 0,
            "orphaned_packages": [],
            "orphaned_size_est": 0,
            "logs": [],
            "logs_size": 0,
            "temp_files": [],
            "temp_size": 0,
            "total_reclaimable": 0
        }
        
        # 1. Check package cache size
        result["package_cache"] = self._get_package_cache_size()
        
        # 2. Find orphaned packages
        if hasattr(self.pm, 'get_orphaned_packages'):
            orphans = self.pm.get_orphaned_packages()
            result["orphaned_packages"] = orphans
            # Estimate 50MB per package as a rough heuristic if exact size unknown
            # Real implementation might query size per package
            result["orphaned_size_est"] = len(orphans) * 50 * 1024 * 1024
            
        # 3. Check for old logs (cortex logs and others)
        # For safety, we primarily target cortex logs and safe user logs
        log_patterns = [
            os.path.expanduser("~/.cortex/logs/*.log"),
            os.path.expanduser("~/*.log")
        ]
        
        for pattern in log_patterns:
            for log_file in glob.glob(pattern):
                if os.path.isfile(log_file) and not log_file.endswith('.gz'):
                    size = os.path.getsize(log_file)
                    # Consider cleanable if > 1MB
                    if size > 1024 * 1024:
                        result["logs"].append(log_file)
                        result["logs_size"] += size

        # 4. Temp files
        # Only safe temp locations
        temp_patterns = [
            os.path.expanduser("~/.cache/cortex/temp/*"),
            "/tmp/cortex-*"
        ]
        
        for pattern in temp_patterns:
            for temp_file in glob.glob(pattern):
                if os.path.isfile(temp_file):
                    size = os.path.getsize(temp_file)
                    result["temp_files"].append(temp_file)
                    result["temp_size"] += size

        # Calculate total
        result["total_reclaimable"] = (
            result["package_cache"] + 
            result["orphaned_size_est"] + 
            result["logs_size"] + 
            result["temp_size"]
        )
        
        return result

    def clean(self, safe_mode: bool = True) -> Dict[str, Any]:
        """
        Perform cleanup operations.
        
        Args:
            safe_mode: If True, skips undefined or potentially risky operations
                       (though this implementation tries to be safe by default)
        
        Returns:
            Dictionary with results of cleanup
        """
        stats = {
            "freed_bytes": 0,
            "actions": []
        }
        
        scan_results = self.scan()
        
        # 1. Clean package cache
        if scan_results["package_cache"] > 0:
            success, msg = self.pm.clean_cache(execute=True)
            if success:
                stats["freed_bytes"] += scan_results["package_cache"]
                stats["actions"].append(f"Cleaned package cache ({self._format_size(scan_results['package_cache'])})")
            else:
                stats["actions"].append(f"Failed to clean package cache: {msg}")

        # 2. Remove orphaned packages
        orphans = scan_results["orphaned_packages"]
        if orphans:
            success, msg = self.pm.remove_packages(orphans, execute=True)
            if success:
                stats["freed_bytes"] += scan_results["orphaned_size_est"]
                stats["actions"].append(f"Removed {len(orphans)} orphaned packages")
            else:
                stats["actions"].append(f"Failed to remove orphaned packages: {msg}")

        # 3. Compress logs
        for log_file in scan_results["logs"]:
            try:
                original_size = os.path.getsize(log_file)
                self._compress_file(log_file)
                new_size = os.path.getsize(log_file + ".gz")
                freed = original_size - new_size
                stats["freed_bytes"] += freed
                stats["actions"].append(f"Compressed {os.path.basename(log_file)}")
            except Exception as e:
                stats["actions"].append(f"Failed to compress {os.path.basename(log_file)}: {e}")

        # 4. Remove temp files
        for temp_file in scan_results["temp_files"]:
            try:
                size = os.path.getsize(temp_file)
                os.remove(temp_file)
                stats["freed_bytes"] += size
                stats["actions"].append(f"Removed temp file {os.path.basename(temp_file)}")
            except Exception as e:
                stats["actions"].append(f"Failed to remove {os.path.basename(temp_file)}: {e}")

        return stats

    def _get_package_cache_size(self) -> int:
        """Calculate size of package manager cache."""
        total_size = 0
        cache_dirs = []
        
        if self.pm.pm_type == "apt": # PackageManagerType enum handling simplified
            cache_dirs = ["/var/cache/apt/archives"]
        elif self.pm.pm_type in ["yum", "dnf"]:
            cache_dirs = ["/var/cache/yum", "/var/cache/dnf"]
            
        for d in cache_dirs:
            if os.path.exists(d):
                for dirpath, _, filenames in os.walk(d):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if os.path.isfile(fp):
                            total_size += os.path.getsize(fp)
                            
        return total_size

    def _compress_file(self, filepath: str):
        """Compress a file using gzip and remove original."""
        with open(filepath, 'rb') as f_in:
            with gzip.open(filepath + '.gz', 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(filepath)

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
