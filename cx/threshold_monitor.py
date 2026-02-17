"""
Threshold-based alerting system for CX Linux.

This module monitors system metrics and triggers alerts when configurable
thresholds are exceeded. It integrates with the SystemAlertManager to provide
persistent alert management and works with existing monitoring components.

Features:
- CPU usage monitoring with configurable thresholds
- Memory usage monitoring
- Disk space monitoring
- System health integration with doctor.py
- Configurable alert rules and cooldown periods
- Integration with hardware profiler
- Automatic metric collection and persistence

Author: CX Linux Team
License: MIT
"""

import datetime
import json
import psutil
import shutil
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from rich.console import Console

from cx.system_alert_manager import get_alert_manager, AlertType, AlertSeverity, AlertStatus

console = Console()


@dataclass
class ThresholdRule:
    """Configuration for a threshold rule."""
    name: str
    metric_type: str  # cpu_usage, memory_usage, disk_free_gb, etc
    operator: str  # >, <, >=, <=, ==
    threshold: float
    severity: AlertSeverity
    cooldown_minutes: int = 5  # Prevent spam alerts
    enabled: bool = True
    description: str = ""


@dataclass
class SystemMetric:
    """System metric measurement."""
    metric_type: str
    value: float
    unit: str
    timestamp: datetime.datetime
    source: str = "threshold_monitor"


class ThresholdMonitor:
    """
    Monitors system metrics and triggers alerts based on configurable thresholds.
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize threshold monitor."""
        # Set up configuration directory
        if config_dir is None:
            self.config_dir = Path.home() / ".cx"
        else:
            self.config_dir = config_dir

        self.config_dir.mkdir(exist_ok=True)

        # Configuration files
        self.rules_file = self.config_dir / "threshold_rules.json"
        self.last_alert_file = self.config_dir / "last_alerts.json"

        # Initialize components
        self.alert_manager = get_alert_manager()
        self.rules: List[ThresholdRule] = []
        self.last_alert_times: Dict[str, datetime.datetime] = {}

        # Monitoring control
        self.monitoring_active = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

        # Load configuration
        self._load_rules()
        self._load_last_alert_times()

    def _load_rules(self):
        """Load threshold rules from configuration file."""
        if self.rules_file.exists():
            try:
                with open(self.rules_file, 'r') as f:
                    rules_data = json.load(f)

                self.rules = []
                for rule_dict in rules_data:
                    # Convert severity string to enum
                    rule_dict['severity'] = AlertSeverity(rule_dict['severity'])
                    self.rules.append(ThresholdRule(**rule_dict))

                console.print(f"[green]✓[/green] Loaded {len(self.rules)} threshold rules")

            except Exception as e:
                console.print(f"[yellow]⚠️[/yellow] Failed to load threshold rules: {e}")
                self._create_default_rules()
        else:
            self._create_default_rules()

    def _create_default_rules(self):
        """Create default threshold rules."""
        default_rules = [
            ThresholdRule(
                name="High CPU Usage",
                metric_type="cpu_usage",
                operator=">",
                threshold=80.0,
                severity=AlertSeverity.NORMAL,
                cooldown_minutes=5,
                description="CPU usage above 80% for sustained period"
            ),
            ThresholdRule(
                name="Critical CPU Usage",
                metric_type="cpu_usage",
                operator=">",
                threshold=95.0,
                severity=AlertSeverity.CRITICAL,
                cooldown_minutes=2,
                description="CPU usage above 95% - system may be unresponsive"
            ),
            ThresholdRule(
                name="High Memory Usage",
                metric_type="memory_usage",
                operator=">",
                threshold=85.0,
                severity=AlertSeverity.NORMAL,
                cooldown_minutes=5,
                description="Memory usage above 85%"
            ),
            ThresholdRule(
                name="Critical Memory Usage",
                metric_type="memory_usage",
                operator=">",
                threshold=95.0,
                severity=AlertSeverity.CRITICAL,
                cooldown_minutes=2,
                description="Memory usage above 95% - risk of OOM"
            ),
            ThresholdRule(
                name="Low Disk Space",
                metric_type="disk_free_gb",
                operator="<",
                threshold=5.0,
                severity=AlertSeverity.NORMAL,
                cooldown_minutes=30,
                description="Less than 5GB free disk space"
            ),
            ThresholdRule(
                name="Critical Disk Space",
                metric_type="disk_free_gb",
                operator="<",
                threshold=1.0,
                severity=AlertSeverity.CRITICAL,
                cooldown_minutes=15,
                description="Less than 1GB free disk space"
            ),
            ThresholdRule(
                name="High Load Average",
                metric_type="load_average_1m",
                operator=">",
                threshold=psutil.cpu_count() * 2,  # 2x CPU count
                severity=AlertSeverity.NORMAL,
                cooldown_minutes=10,
                description="High system load - may impact performance"
            ),
        ]

        self.rules = default_rules
        self._save_rules()
        console.print(f"[green]✓[/green] Created {len(self.rules)} default threshold rules")

    def _save_rules(self):
        """Save threshold rules to configuration file."""
        try:
            # Convert to serializable format
            rules_data = []
            for rule in self.rules:
                rule_dict = asdict(rule)
                rule_dict['severity'] = rule.severity.value  # Convert enum to string
                rules_data.append(rule_dict)

            with open(self.rules_file, 'w') as f:
                json.dump(rules_data, f, indent=2)

        except Exception as e:
            console.print(f"[red]✗[/red] Failed to save threshold rules: {e}")

    def _load_last_alert_times(self):
        """Load last alert times for cooldown management."""
        if self.last_alert_file.exists():
            try:
                with open(self.last_alert_file, 'r') as f:
                    data = json.load(f)

                # Convert ISO timestamps back to datetime objects
                self.last_alert_times = {}
                for rule_name, timestamp_str in data.items():
                    self.last_alert_times[rule_name] = datetime.datetime.fromisoformat(timestamp_str)

            except Exception as e:
                console.print(f"[yellow]⚠️[/yellow] Failed to load last alert times: {e}")
                self.last_alert_times = {}
        else:
            self.last_alert_times = {}

    def _save_last_alert_times(self):
        """Save last alert times."""
        try:
            # Convert datetime objects to ISO strings
            data = {}
            for rule_name, timestamp in self.last_alert_times.items():
                data[rule_name] = timestamp.isoformat()

            with open(self.last_alert_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            console.print(f"[red]✗[/red] Failed to save last alert times: {e}")

    def collect_system_metrics(self) -> List[SystemMetric]:
        """Collect current system metrics."""
        metrics = []
        now = datetime.datetime.now()

        try:
            # CPU usage (percentage)
            cpu_percent = psutil.cpu_percent(interval=1)
            metrics.append(SystemMetric("cpu_usage", cpu_percent, "%", now))

            # Memory usage (percentage)
            memory = psutil.virtual_memory()
            metrics.append(SystemMetric("memory_usage", memory.percent, "%", now))
            metrics.append(SystemMetric("memory_available_gb", memory.available / (1024**3), "GB", now))

            # Disk usage for root filesystem
            disk = psutil.disk_usage('/')
            disk_free_gb = disk.free / (1024**3)
            disk_used_percent = (disk.used / disk.total) * 100
            metrics.append(SystemMetric("disk_free_gb", disk_free_gb, "GB", now))
            metrics.append(SystemMetric("disk_used_percent", disk_used_percent, "%", now))

            # Load average (Unix-like systems)
            try:
                load_avg = psutil.getloadavg()
                metrics.append(SystemMetric("load_average_1m", load_avg[0], "load", now))
                metrics.append(SystemMetric("load_average_5m", load_avg[1], "load", now))
                metrics.append(SystemMetric("load_average_15m", load_avg[2], "load", now))
            except (AttributeError, OSError):
                # getloadavg not available on Windows
                pass

            # Network I/O
            net_io = psutil.net_io_counters()
            if net_io:
                metrics.append(SystemMetric("network_bytes_sent", net_io.bytes_sent, "bytes", now))
                metrics.append(SystemMetric("network_bytes_recv", net_io.bytes_recv, "bytes", now))

            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if disk_io:
                metrics.append(SystemMetric("disk_read_bytes", disk_io.read_bytes, "bytes", now))
                metrics.append(SystemMetric("disk_write_bytes", disk_io.write_bytes, "bytes", now))

        except Exception as e:
            console.print(f"[red]✗[/red] Failed to collect system metrics: {e}")

        return metrics

    def evaluate_thresholds(self, metrics: List[SystemMetric]) -> List[str]:
        """
        Evaluate metrics against threshold rules.

        Returns:
            List of rule names that triggered alerts
        """
        triggered_rules = []

        # Create metric lookup
        metric_values = {metric.metric_type: metric.value for metric in metrics}

        for rule in self.rules:
            if not rule.enabled:
                continue

            # Check if metric exists
            if rule.metric_type not in metric_values:
                continue

            value = metric_values[rule.metric_type]

            # Check cooldown period
            if rule.name in self.last_alert_times:
                time_since_last = datetime.datetime.now() - self.last_alert_times[rule.name]
                if time_since_last.total_seconds() < (rule.cooldown_minutes * 60):
                    continue

            # Evaluate threshold
            triggered = False
            if rule.operator == ">" and value > rule.threshold:
                triggered = True
            elif rule.operator == ">=" and value >= rule.threshold:
                triggered = True
            elif rule.operator == "<" and value < rule.threshold:
                triggered = True
            elif rule.operator == "<=" and value <= rule.threshold:
                triggered = True
            elif rule.operator == "==" and value == rule.threshold:
                triggered = True

            if triggered:
                # Create alert
                self._create_threshold_alert(rule, value, metric_values)
                triggered_rules.append(rule.name)

                # Update last alert time
                self.last_alert_times[rule.name] = datetime.datetime.now()

        # Save updated alert times
        if triggered_rules:
            self._save_last_alert_times()

        return triggered_rules

    def _create_threshold_alert(self, rule: ThresholdRule, current_value: float, all_metrics: Dict[str, float]):
        """Create an alert for a triggered threshold rule."""
        try:
            title = f"Threshold Alert: {rule.name}"
            message = (
                f"{rule.metric_type} is {current_value:.1f} "
                f"({rule.operator} {rule.threshold}). {rule.description}"
            )

            metadata = {
                "rule_name": rule.name,
                "metric_type": rule.metric_type,
                "current_value": current_value,
                "threshold": rule.threshold,
                "operator": rule.operator,
                "all_metrics": all_metrics
            }

            alert_id = self.alert_manager.create_alert(
                alert_type=AlertType.THRESHOLD,
                severity=rule.severity,
                source="threshold_monitor",
                title=title,
                message=message,
                metadata=metadata
            )

            console.print(f"[red]🚨[/red] Threshold alert #{alert_id}: {rule.name} ({current_value:.1f})")

        except Exception as e:
            console.print(f"[red]✗[/red] Failed to create threshold alert: {e}")

    def start_monitoring(self, interval_seconds: int = 60):
        """Start continuous monitoring."""
        if self.monitoring_active:
            console.print("[yellow]⚠️[/yellow] Monitoring already active")
            return

        self.monitoring_active = True
        self.stop_event.clear()

        def monitor_loop():
            console.print(f"[green]🔍[/green] Started threshold monitoring (interval: {interval_seconds}s)")

            while not self.stop_event.wait(interval_seconds):
                try:
                    # Collect metrics
                    metrics = self.collect_system_metrics()

                    # Store metrics in alert database
                    for metric in metrics:
                        self.alert_manager.record_metric(
                            metric.metric_type,
                            metric.value,
                            metric.unit,
                            metric.source
                        )

                    # Evaluate thresholds
                    triggered = self.evaluate_thresholds(metrics)

                    if triggered:
                        console.print(f"[yellow]⚠️[/yellow] {len(triggered)} threshold(s) triggered: {', '.join(triggered)}")

                except Exception as e:
                    console.print(f"[red]✗[/red] Error in monitoring loop: {e}")

            console.print("[dim]🛑 Threshold monitoring stopped[/dim]")

        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        """Stop continuous monitoring."""
        if not self.monitoring_active:
            return

        self.monitoring_active = False
        self.stop_event.set()

        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

        console.print("[green]✓[/green] Threshold monitoring stopped")

    def add_rule(self, rule: ThresholdRule):
        """Add a new threshold rule."""
        self.rules.append(rule)
        self._save_rules()
        console.print(f"[green]✓[/green] Added threshold rule: {rule.name}")

    def remove_rule(self, rule_name: str) -> bool:
        """Remove a threshold rule by name."""
        original_count = len(self.rules)
        self.rules = [rule for rule in self.rules if rule.name != rule_name]

        if len(self.rules) < original_count:
            self._save_rules()
            console.print(f"[green]✓[/green] Removed threshold rule: {rule_name}")
            return True
        else:
            console.print(f"[yellow]⚠️[/yellow] Rule not found: {rule_name}")
            return False

    def list_rules(self) -> List[Dict[str, Any]]:
        """List all threshold rules."""
        return [asdict(rule) for rule in self.rules]

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics as a dictionary."""
        metrics = self.collect_system_metrics()
        result = {}

        for metric in metrics:
            result[metric.metric_type] = {
                "value": metric.value,
                "unit": metric.unit,
                "timestamp": metric.timestamp.isoformat()
            }

        return result

    def manual_check(self) -> Dict[str, Any]:
        """Perform a manual threshold check and return results."""
        metrics = self.collect_system_metrics()
        triggered = self.evaluate_thresholds(metrics)

        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "metrics": self.get_current_metrics(),
            "triggered_rules": triggered,
            "total_rules": len(self.rules),
            "enabled_rules": len([r for r in self.rules if r.enabled])
        }


# Global instance
_threshold_monitor_instance = None


def get_threshold_monitor() -> ThresholdMonitor:
    """Get global threshold monitor instance (singleton pattern)."""
    global _threshold_monitor_instance
    if _threshold_monitor_instance is None:
        _threshold_monitor_instance = ThresholdMonitor()
    return _threshold_monitor_instance


if __name__ == "__main__":
    # Test the threshold monitor
    monitor = ThresholdMonitor()

    # Perform manual check
    result = monitor.manual_check()
    console.print(f"Manual check results: {result}")

    # Start monitoring for a short time
    console.print("Starting 30-second monitoring test...")
    monitor.start_monitoring(interval_seconds=5)
    time.sleep(30)
    monitor.stop_monitoring()