import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

console = Console()


@dataclass
class CheckResult:
    """Data class to hold the result of each check."""

    name: str               # Item name (e.g. "Disk Space")
    category: str           # Category (security, updates, performance, disk)
    score: int              # Score 0-100
    status: str             # "OK", "WARNING", "CRITICAL"
    details: str            # Detailed message
    recommendation: str | None = None  # Recommended action (if any)
    weight: float = 1.0     # Weight for weighted average


class HealthCheck(ABC):
    """Base class inherited by all health check modules."""

    @abstractmethod
    def run(self) -> CheckResult:
        """Execute the check and return a result."""
        pass


class HealthMonitor:
    """Main engine for system health monitoring.

    Manages registration of health checks, execution, score aggregation,
    and history persistence.
    """

    def __init__(self) -> None:
        """Initialize the health monitor and register default checks."""
        self.history_file = Path.home() / ".cortex" / "health_history.json"
        self.history_file.parent.mkdir(exist_ok=True)
        self.checks: list[HealthCheck] = []

        # Register each check here
        # (Import here to prevent circular references)
        from .checks.disk import DiskCheck
        from .checks.performance import PerformanceCheck
        from .checks.security import SecurityCheck
        from .checks.updates import UpdateCheck

        self.register_check(SecurityCheck())
        self.register_check(UpdateCheck())
        self.register_check(PerformanceCheck())
        self.register_check(DiskCheck())

    def register_check(self, check: HealthCheck) -> None:
        """Register a health check instance to be run as part of the monitor.

        Args:
            check (HealthCheck): The check instance to register.
        """
        self.checks.append(check)

    def run_all(self) -> dict:
        """Run all registered checks and return an aggregated health report.

        Returns:
            dict: A report containing the timestamp, total weighted score,
                  and a list of individual check results.
        """
        results = []
        total_weighted_score = 0
        total_weight = 0

        for check in self.checks:
            try:
                result = check.run()
                results.append(result)
                total_weighted_score += result.score * result.weight
                total_weight += result.weight
            except Exception as e:
                console.print(
                    f"[red]Error running check {check.__class__.__name__}: {e}[/red]"
                )

        final_score = 0
        if total_weight > 0:
            final_score = int(total_weighted_score / total_weight)

        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_score": final_score,
            "results": [
                {
                    "name": r.name,
                    "category": r.category,
                    "score": r.score,
                    "status": r.status,
                    "details": r.details,
                    "recommendation": r.recommendation
                }
                for r in results
            ]
        }

        self._save_history(report)
        return report

    def _save_history(self, report: dict) -> None:
        """Save the current health report to the history JSON file.

        Args:
            report (dict): The health report to save.
        """
        history = []
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    history = json.load(f)
            except json.JSONDecodeError:
                pass

        history.append(report)
        # Keep only the last 100 records
        history = history[-100:]

        try:
            with open(self.history_file, 'w') as f:
                json.dump(history, f, indent=4)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not save health history: {e}[/yellow]")