#!/usr/bin/env python3
"""
Cortex Linux - Comprehensive Logging & Diagnostics System
Issue #29: Structured logging, log rotation, and diagnostic tools

This module provides enterprise-grade logging with multiple outputs,
automatic rotation, filtering, and diagnostic capabilities.
"""

import os
import sys
import json
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import threading


@dataclass
class LogEntry:
    """Structured log entry"""
    timestamp: str
    level: str
    logger: str
    message: str
    context: Dict[str, Any] = None
    exception: Optional[str] = None
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = ''.join(traceback.format_exception(*record.exc_info))
            
        # Add extra fields
        if hasattr(record, 'context'):
            log_data['context'] = record.context
            
        return json.dumps(log_data)


class ColoredConsoleFormatter(logging.Formatter):
    """Colored formatter for console output"""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m'    # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        # Add color
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
            
        # Format message
        formatted = super().format(record)
        
        # Reset levelname
        record.levelname = levelname
        
        return formatted


class CortexLogger:
    """
    Comprehensive Logging System for Cortex Linux
    
    Features:
    - Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - Multiple outputs (console, file, structured JSON)
    - Automatic log rotation
    - Context-aware logging
    - Performance metrics
    - Diagnostic tools
    """
    
    def __init__(
        self,
        name: str = "cortex",
        log_dir: str = "~/.cortex/logs",
        console_level: str = "INFO",
        file_level: str = "DEBUG",
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5
    ):
        """
        Initialize logging system
        
        Args:
            name: Logger name
            log_dir: Directory for log files
            console_level: Console log level
            file_level: File log level
            max_bytes: Max size per log file
            backup_count: Number of backup files to keep
        """
        self.name = name
        self.log_dir = Path(log_dir).expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Setup handlers
        self._setup_console_handler(console_level)
        self._setup_file_handler(file_level, max_bytes, backup_count)
        self._setup_structured_handler(max_bytes, backup_count)
        self._setup_error_handler()
        
        # Performance tracking
        self._operation_times = {}
        self._operation_lock = threading.Lock()
        
    def _setup_console_handler(self, level: str):
        """Setup colored console handler"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level))
        
        formatter = ColoredConsoleFormatter(
            '%(levelname)s [%(name)s] %(message)s'
        )
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(console_handler)
        
    def _setup_file_handler(self, level: str, max_bytes: int, backup_count: int):
        """Setup rotating file handler"""
        log_file = self.log_dir / f"{self.name}.log"
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setLevel(getattr(logging, level))
        
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        
    def _setup_structured_handler(self, max_bytes: int, backup_count: int):
        """Setup structured JSON log handler"""
        json_file = self.log_dir / f"{self.name}.json.log"
        
        json_handler = RotatingFileHandler(
            json_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        json_handler.setLevel(logging.DEBUG)
        json_handler.setFormatter(StructuredFormatter())
        
        self.logger.addHandler(json_handler)
        
    def _setup_error_handler(self):
        """Setup dedicated error log handler"""
        error_file = self.log_dir / f"{self.name}.error.log"
        
        error_handler = RotatingFileHandler(
            error_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3
        )
        error_handler.setLevel(logging.ERROR)
        
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s - %(message)s\n%(pathname)s:%(lineno)d\n',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(formatter)
        
        self.logger.addHandler(error_handler)
        
    def debug(self, message: str, context: Dict = None):
        """Log debug message"""
        self._log(logging.DEBUG, message, context)
        
    def info(self, message: str, context: Dict = None):
        """Log info message"""
        self._log(logging.INFO, message, context)
        
    def warning(self, message: str, context: Dict = None):
        """Log warning message"""
        self._log(logging.WARNING, message, context)
        
    def error(self, message: str, context: Dict = None, exc_info: bool = False):
        """Log error message"""
        self._log(logging.ERROR, message, context, exc_info)
        
    def critical(self, message: str, context: Dict = None, exc_info: bool = False):
        """Log critical message"""
        self._log(logging.CRITICAL, message, context, exc_info)
        
    def _log(self, level: int, message: str, context: Dict = None, exc_info: bool = False):
        """Internal logging method"""
        extra = {'context': context} if context else {}
        self.logger.log(level, message, extra=extra, exc_info=exc_info)
        
    def start_operation(self, operation_name: str):
        """Start timing an operation"""
        with self._operation_lock:
            self._operation_times[operation_name] = datetime.now()
            
    def end_operation(self, operation_name: str, log_level: str = "INFO"):
        """End timing an operation and log duration"""
        with self._operation_lock:
            if operation_name in self._operation_times:
                start_time = self._operation_times.pop(operation_name)
                duration = (datetime.now() - start_time).total_seconds()
                
                self._log(
                    getattr(logging, log_level),
                    f"Operation '{operation_name}' completed",
                    {'duration_seconds': duration}
                )
                
                return duration
                
        return None
        
    def log_function_call(self, func_name: str, args: tuple = None, kwargs: dict = None):
        """Log function call with arguments"""
        context = {
            'function': func_name,
            'args': str(args) if args else None,
            'kwargs': str(kwargs) if kwargs else None
        }
        self.debug(f"Calling function: {func_name}", context)
        
    def log_system_info(self):
        """Log system information"""
        import platform
        
        info = {
            'platform': platform.platform(),
            'python_version': platform.python_version(),
            'machine': platform.machine(),
            'processor': platform.processor()
        }
        
        self.info("System information", info)
        
    def get_log_stats(self) -> Dict[str, Any]:
        """Get logging statistics"""
        stats = {
            'log_directory': str(self.log_dir),
            'log_files': [],
            'total_size_bytes': 0
        }
        
        for log_file in self.log_dir.glob(f"{self.name}*.log*"):
            size = log_file.stat().st_size
            stats['log_files'].append({
                'name': log_file.name,
                'size_bytes': size,
                'size_mb': round(size / (1024 * 1024), 2),
                'modified': datetime.fromtimestamp(log_file.stat().st_mtime).isoformat()
            })
            stats['total_size_bytes'] += size
            
        stats['total_size_mb'] = round(stats['total_size_bytes'] / (1024 * 1024), 2)
        stats['file_count'] = len(stats['log_files'])
        
        return stats
        
    def search_logs(
        self,
        pattern: str,
        level: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Search through log files
        
        Args:
            pattern: Text pattern to search for
            level: Filter by log level
            since: Only return logs after this time
            limit: Maximum number of results
            
        Returns:
            List of matching log entries
        """
        results = []
        
        # Read JSON log file for structured search
        json_log = self.log_dir / f"{self.name}.json.log"
        
        if not json_log.exists():
            return results
            
        try:
            with open(json_log, 'r') as f:
                for line in f:
                    if len(results) >= limit:
                        break
                        
                    try:
                        entry = json.loads(line)
                        
                        # Filter by level
                        if level and entry.get('level') != level:
                            continue
                            
                        # Filter by time
                        if since:
                            entry_time = datetime.fromisoformat(entry['timestamp'])
                            if entry_time < since:
                                continue
                                
                        # Filter by pattern
                        if pattern.lower() in entry.get('message', '').lower():
                            results.append(entry)
                            
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            self.error(f"Error searching logs: {e}")
            
        return results
        
    def export_logs(
        self,
        output_path: str,
        format: str = "json",
        since: Optional[datetime] = None,
        level: Optional[str] = None
    ) -> str:
        """
        Export logs to file
        
        Args:
            output_path: Output file path
            format: Export format (json, csv, txt)
            since: Only export logs after this time
            level: Filter by log level
            
        Returns:
            Path to exported file
        """
        output_file = Path(output_path)
        
        # Get all matching logs
        logs = self.search_logs("", level=level, since=since, limit=10000)
        
        if format == "json":
            with open(output_file, 'w') as f:
                json.dump(logs, f, indent=2)
                
        elif format == "csv":
            import csv
            with open(output_file, 'w', newline='') as f:
                if logs:
                    writer = csv.DictWriter(f, fieldnames=logs[0].keys())
                    writer.writeheader()
                    writer.writerows(logs)
                    
        elif format == "txt":
            with open(output_file, 'w') as f:
                for log in logs:
                    f.write(f"[{log['timestamp']}] {log['level']} - {log['message']}\n")
                    
        return str(output_file)
        
    def clear_old_logs(self, days: int = 30) -> int:
        """
        Clear log files older than specified days
        
        Args:
            days: Delete logs older than this many days
            
        Returns:
            Number of files deleted
        """
        from datetime import timedelta
        
        cutoff_time = datetime.now() - timedelta(days=days)
        deleted = 0
        
        for log_file in self.log_dir.glob(f"{self.name}*.log*"):
            modified_time = datetime.fromtimestamp(log_file.stat().st_mtime)
            
            if modified_time < cutoff_time:
                try:
                    log_file.unlink()
                    deleted += 1
                    self.info(f"Deleted old log file: {log_file.name}")
                except Exception as e:
                    self.error(f"Could not delete {log_file.name}: {e}")
                    
        return deleted
        
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get summary of errors in recent time period
        
        Args:
            hours: Look back this many hours
            
        Returns:
            Error summary statistics
        """
        from datetime import timedelta
        from collections import Counter
        
        since = datetime.now() - timedelta(hours=hours)
        errors = self.search_logs("", level="ERROR", since=since, limit=1000)
        
        summary = {
            'total_errors': len(errors),
            'time_period_hours': hours,
            'error_messages': Counter([e['message'] for e in errors]),
            'error_modules': Counter([e.get('module', 'unknown') for e in errors]),
            'first_error': errors[0]['timestamp'] if errors else None,
            'last_error': errors[-1]['timestamp'] if errors else None
        }
        
        return summary


class LogContext:
    """Context manager for operation logging"""
    
    def __init__(self, logger: CortexLogger, operation: str):
        self.logger = logger
        self.operation = operation
        
    def __enter__(self):
        self.logger.start_operation(self.operation)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.logger.error(
                f"Operation '{self.operation}' failed",
                context={'exception_type': exc_type.__name__},
                exc_info=True
            )
        else:
            self.logger.end_operation(self.operation)


def main():
    """Example usage"""
    logger = CortexLogger("cortex")
    
    print("📝 Cortex Logging System Demo")
    print("=" * 60)
    
    # Basic logging
    logger.info("Cortex Linux starting up")
    logger.debug("Debug information", {'version': '0.1.0'})
    logger.warning("This is a warning")
    
    # Operation timing
    logger.start_operation("package_install")
    import time
    time.sleep(0.1)
    logger.end_operation("package_install")
    
    # Context manager
    with LogContext(logger, "database_query"):
        time.sleep(0.05)
        logger.info("Query completed")
        
    # Error logging
    try:
        raise ValueError("Example error")
    except Exception:
        logger.error("An error occurred", exc_info=True)
        
    # Log statistics
    print("\n📊 Log Statistics:")
    stats = logger.get_log_stats()
    print(f"  Files: {stats['file_count']}")
    print(f"  Total Size: {stats['total_size_mb']} MB")
    
    # Search logs
    print("\n🔍 Searching logs for 'Cortex':")
    results = logger.search_logs("Cortex", limit=3)
    for result in results:
        print(f"  [{result['level']}] {result['message']}")
        
    # Error summary
    print("\n❌ Error Summary (last 24h):")
    error_summary = logger.get_error_summary()
    print(f"  Total Errors: {error_summary['total_errors']}")
    
    print("\n✅ Logging demo complete!")
    print(f"   Logs stored in: {logger.log_dir}")


if __name__ == "__main__":
    main()
