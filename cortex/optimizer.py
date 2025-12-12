import os
import shutil
import subprocess
import glob
import gzip
import time
import logging
from typing import List, Dict, Optional
from pathlib import Path
from dataclasses import dataclass

from cortex.packages import PackageManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class CleanupOpportunity:
    type: str  # 'package_cache', 'orphans', 'logs', 'temp'
    size_bytes: int
    description: str
    items: List[str]  # List of files or packages

class LogManager:
    """Manages log file compression and cleanup."""
    def __init__(self, log_dir: str = "/var/log"):
        self.log_dir = log_dir

    def scan(self) -> Optional[CleanupOpportunity]:
        """Scan logs to identify old files that can be compressed."""
        candidates = []
        total_size = 0
        
        if not os.path.exists(self.log_dir):
            return None

        # Look for .1, .2, or .log.old files that aren't compressed
        # Also look for .log files older than 7 days
        patterns = ["**/*.1", "**/*.2", "**/*.log.old", "**/*.log"]
        cutoff = time.time() - (7 * 86400) # 7 days

        # We need to be careful with permissions here. 
        # Ideally this runs with permissions or handles errors gracefully.
        for pattern in patterns:
            for log_file in glob.glob(os.path.join(self.log_dir, pattern), recursive=True):
                try:
                    # Skip if already compressed
                    if log_file.endswith('.gz'):
                        continue
                        
                    stat = os.stat(log_file)
                    
                    # For .log files, check age
                    if log_file.endswith('.log'):
                        if stat.st_mtime > cutoff:
                            continue
                            
                    candidates.append(log_file)
                    total_size += stat.st_size
                except (OSError, PermissionError):
                    pass
        
        if candidates:
            return CleanupOpportunity(
                type="logs",
                size_bytes=total_size,
                description=f"Old log files ({len(candidates)})",
                items=candidates
            )
        return None

    def get_cleanup_commands(self) -> List[str]:
        """Generate commands to compress old logs."""
        # More robust find command
        return [
            f"find {self.log_dir} -name '*.log' -type f -mtime +7 -exec gzip {{}} \\+",
            f"find {self.log_dir} -name '*.1' -type f -exec gzip {{}} \\+",
            f"find {self.log_dir} -name '*.2' -type f -exec gzip {{}} \\+"
        ]

class TempCleaner:
    """Manages temporary file cleanup."""
    def __init__(self, temp_dirs: List[str] = None):
        if temp_dirs is None:
            self.temp_dirs = ["/tmp", "/var/tmp"]
        else:
            self.temp_dirs = temp_dirs

    def scan(self) -> Optional[CleanupOpportunity]:
        """Scan temp directories for old files."""
        candidates = []
        total_size = 0
        cutoff = time.time() - (7 * 86400) # 7 days
        
        for d in self.temp_dirs:
            if not os.path.exists(d):
                continue
            try:
                for root, _, files in os.walk(d):
                    for name in files:
                        fpath = os.path.join(root, name)
                        try:
                            stat = os.stat(fpath)
                            if stat.st_atime < cutoff and stat.st_mtime < cutoff:
                                candidates.append(fpath)
                                total_size += stat.st_size
                        except (OSError, PermissionError):
                            pass
            except (OSError, PermissionError):
                pass
                
        if candidates:
            return CleanupOpportunity(
                type="temp",
                size_bytes=total_size,
                description=f"Old temporary files ({len(candidates)})",
                items=candidates
            )
        return None

    def get_cleanup_commands(self) -> List[str]:
        """Generate commands to clean temp files."""
        commands = []
        for d in self.temp_dirs:
            # Delete files accessed more than 10 days ago
            commands.append(f"find {d} -type f -atime +10 -delete")
            # Delete empty directories
            commands.append(f"find {d} -type d -empty -delete")
        return commands

class CleanupOptimizer:
    """Orchestrator for system cleanup operations."""
    def __init__(self):
        self.pm = PackageManager()
        self.log_manager = LogManager()
        self.temp_cleaner = TempCleaner()
        self.backup_dir = Path("/var/lib/cortex/backups/cleanup")
        self._ensure_backup_dir()

    def _ensure_backup_dir(self):
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.backup_dir = Path.home() / ".cortex" / "backups" / "cleanup"
            self.backup_dir.mkdir(parents=True, exist_ok=True)

    def scan(self) -> List[CleanupOpportunity]:
        """Scan system for cleanup opportunities."""
        opportunities = []
        
        # 1. Package Manager
        pkg_info = self.pm.get_cleanable_items()
        if pkg_info.get("cache_size_bytes", 0) > 0:
            opportunities.append(CleanupOpportunity(
                type="package_cache",
                size_bytes=pkg_info["cache_size_bytes"],
                description="Package manager cache",
                items=["Package cache files"]
            ))
        
        if pkg_info.get("orphaned_packages"):
            opportunities.append(CleanupOpportunity(
                type="orphans",
                size_bytes=pkg_info.get("orphaned_size_bytes", 0),
                description=f"Orphaned packages ({len(pkg_info['orphaned_packages'])})",
                items=pkg_info["orphaned_packages"]
            ))
            
        # 2. Logs
        log_opp = self.log_manager.scan()
        if log_opp:
            opportunities.append(log_opp)
            
        # 3. Temp
        temp_opp = self.temp_cleaner.scan()
        if temp_opp:
            opportunities.append(temp_opp)
            
        return opportunities

    def get_cleanup_plan(self, safe_mode: bool = True) -> List[str]:
        """Generate a list of shell commands to execute the cleanup."""
        commands = []
        
        # 1. Package Cleanup
        commands.extend(self.pm.get_cleanup_commands('cache'))
        commands.extend(self.pm.get_cleanup_commands('orphans'))
        
        # 2. Log Cleanup
        commands.extend(self.log_manager.get_cleanup_commands())
        
        # 3. Temp Cleanup
        commands.extend(self.temp_cleaner.get_cleanup_commands())
        
        return commands

    def schedule_cleanup(self, frequency: str) -> bool:
        """Schedule cleanup job (daily, weekly, monthly)."""
        cron_cmd = "cortex cleanup run --safe > /var/log/cortex-cleanup.log 2>&1"
        cron_time = "@daily"
        if frequency == 'weekly': cron_time = "@weekly"
        elif frequency == 'monthly': cron_time = "@monthly"
        
        entry = f"{cron_time} {cron_cmd}"
        
        try:
            current_crontab = subprocess.run("crontab -l", shell=True, capture_output=True, text=True).stdout
            if cron_cmd in current_crontab:
                return True
            
            new_crontab = current_crontab + f"\n# Cortex Auto-Cleanup\n{entry}\n"
            proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
            return proc.returncode == 0
        except Exception:
            return False
