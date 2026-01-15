"""
System Health Score and Recommendations

Issue: #128 - System Health Score and Recommendations

Calculates overall system health score with actionable recommendations.
"""

import json
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


class HealthStatus(Enum):
    """Health status levels."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class HealthCategory(Enum):
    """Categories of health checks."""

    SECURITY = "security"
    UPDATES = "updates"
    PERFORMANCE = "performance"
    DISK = "disk"
    MEMORY = "memory"
    SERVICES = "services"


@dataclass
class HealthFactor:
    """A single health factor measurement."""

    name: str
    category: HealthCategory
    score: int  # 0-100
    weight: float = 1.0
    details: str = ""
    recommendation: str = ""
    fix_command: str = ""
    fix_points: int = 0

    @property
    def status(self) -> HealthStatus:
        """Get status based on score."""
        if self.score >= 90:
            return HealthStatus.EXCELLENT
        if self.score >= 75:
            return HealthStatus.GOOD
        if self.score >= 50:
            return HealthStatus.FAIR
        if self.score >= 25:
            return HealthStatus.POOR
        return HealthStatus.CRITICAL

    @property
    def status_icon(self) -> str:
        """Get status icon."""
        return {
            HealthStatus.EXCELLENT: "[green]✓[/green]",
            HealthStatus.GOOD: "[green]✓[/green]",
            HealthStatus.FAIR: "[yellow]⚠[/yellow]",
            HealthStatus.POOR: "[red]✗[/red]",
            HealthStatus.CRITICAL: "[red]✗[/red]",
        }.get(self.status, "?")


@dataclass
class HealthReport:
    """Complete health report."""

    timestamp: datetime = field(default_factory=datetime.now)
    factors: list[HealthFactor] = field(default_factory=list)

    @property
    def overall_score(self) -> int:
        """Calculate weighted overall score."""
        if not self.factors:
            return 0

        total_weight = sum(f.weight for f in self.factors)
        if total_weight == 0:
            return 0

        weighted_sum = sum(f.score * f.weight for f in self.factors)
        return int(weighted_sum / total_weight)

    @property
    def status(self) -> HealthStatus:
        """Get overall status."""
        score = self.overall_score
        if score >= 90:
            return HealthStatus.EXCELLENT
        if score >= 75:
            return HealthStatus.GOOD
        if score >= 50:
            return HealthStatus.FAIR
        if score >= 25:
            return HealthStatus.POOR
        return HealthStatus.CRITICAL

    @property
    def status_icon(self) -> str:
        """Get overall status icon."""
        return {
            HealthStatus.EXCELLENT: "[green]✓[/green]",
            HealthStatus.GOOD: "[green]✓[/green]",
            HealthStatus.FAIR: "[yellow]⚠[/yellow]",
            HealthStatus.POOR: "[red]✗[/red]",
            HealthStatus.CRITICAL: "[red]✗[/red]",
        }.get(self.status, "?")

    def get_recommendations(self) -> list[HealthFactor]:
        """Get factors with recommendations, sorted by impact."""
        factors_with_recs = [f for f in self.factors if f.recommendation]
        return sorted(factors_with_recs, key=lambda f: f.fix_points, reverse=True)


class HealthChecker:
    """System health checker."""

    def __init__(self, verbose: bool = False):
        """Initialize the health checker."""
        self.verbose = verbose
        self.history_path = Path.home() / ".cortex" / "health_history.json"

    def _run_command(self, cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
        """Run a command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"
        except FileNotFoundError:
            return 1, "", f"Command not found: {cmd[0]}"
        except Exception as e:
            return 1, "", str(e)

    def check_disk_space(self) -> HealthFactor:
        """Check disk space usage."""
        code, output, _ = self._run_command(["df", "-h", "/"])

        usage_percent = 50  # Default
        if code == 0:
            lines = output.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                for part in parts:
                    if part.endswith("%"):
                        try:
                            usage_percent = int(part.rstrip("%"))
                        except ValueError:
                            pass
                        break

        # Score: 100 at 0% used, 0 at 100% used
        score = max(0, 100 - usage_percent)

        recommendation = ""
        fix_command = ""
        fix_points = 0

        if usage_percent > 80:
            recommendation = "Clean up disk space"
            fix_command = "sudo apt autoremove && sudo apt clean"
            fix_points = min(20, usage_percent - 70)

        return HealthFactor(
            name="Disk Space",
            category=HealthCategory.DISK,
            score=score,
            weight=1.0,
            details=f"{usage_percent}% used",
            recommendation=recommendation,
            fix_command=fix_command,
            fix_points=fix_points,
        )

    def check_memory(self) -> HealthFactor:
        """Check memory usage."""
        code, output, _ = self._run_command(["free", "-m"])

        usage_percent = 50  # Default
        if code == 0:
            lines = output.strip().split("\n")
            for line in lines:
                if line.startswith("Mem:"):
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            total = int(parts[1])
                            used = int(parts[2])
                            if total > 0:
                                usage_percent = int((used / total) * 100)
                        except ValueError:
                            pass
                    break

        score = max(0, 100 - usage_percent)

        recommendation = ""
        if usage_percent > 85:
            recommendation = "High memory usage - consider closing unused applications"

        return HealthFactor(
            name="Memory",
            category=HealthCategory.MEMORY,
            score=score,
            weight=0.8,
            details=f"{usage_percent}% used",
            recommendation=recommendation,
        )

    def check_updates(self) -> HealthFactor:
        """Check for available system updates."""
        # Try apt
        code, output, _ = self._run_command(
            ["apt", "list", "--upgradable"],
            timeout=60,
        )

        update_count = 0
        if code == 0:
            lines = output.strip().split("\n")
            # Skip header line
            update_count = max(0, len(lines) - 1)

        # Score based on update count
        if update_count == 0:
            score = 100
        elif update_count < 5:
            score = 85
        elif update_count < 10:
            score = 70
        elif update_count < 20:
            score = 50
        else:
            score = 30

        recommendation = ""
        fix_command = ""
        fix_points = 0

        if update_count > 0:
            recommendation = f"Update {update_count} package(s)"
            fix_command = "sudo apt update && sudo apt upgrade -y"
            fix_points = min(20, update_count * 2)

        return HealthFactor(
            name="System Updates",
            category=HealthCategory.UPDATES,
            score=score,
            weight=1.2,
            details=f"{update_count} updates available",
            recommendation=recommendation,
            fix_command=fix_command,
            fix_points=fix_points,
        )

    def check_security(self) -> HealthFactor:
        """Check security-related settings."""
        issues = []
        score = 100

        # Check firewall
        code, output, _ = self._run_command(["ufw", "status"])
        if code != 0 or "inactive" in output.lower():
            issues.append("Firewall inactive")
            score -= 20

        # Check SSH config
        ssh_config = Path("/etc/ssh/sshd_config")
        if ssh_config.exists():
            try:
                content = ssh_config.read_text()
                if "PermitRootLogin yes" in content:
                    issues.append("Root SSH login enabled")
                    score -= 15
                if "PasswordAuthentication yes" in content:
                    issues.append("Password SSH enabled")
                    score -= 10
            except PermissionError:
                pass

        # Check for unattended upgrades
        code, _, _ = self._run_command(["dpkg", "-l", "unattended-upgrades"])
        if code != 0:
            issues.append("Automatic updates not configured")
            score -= 10

        score = max(0, score)

        recommendation = ""
        fix_command = ""
        fix_points = 0

        if issues:
            recommendation = f"Security issues: {', '.join(issues[:2])}"
            if "Firewall inactive" in issues:
                fix_command = "sudo ufw enable"
                fix_points = 15

        return HealthFactor(
            name="Security",
            category=HealthCategory.SECURITY,
            score=score,
            weight=1.5,
            details=f"{len(issues)} issue(s)" if issues else "No issues",
            recommendation=recommendation,
            fix_command=fix_command,
            fix_points=fix_points,
        )

    def check_services(self) -> HealthFactor:
        """Check critical system services."""
        failed_services = []

        # Check systemd
        code, output, _ = self._run_command(
            ["systemctl", "list-units", "--state=failed", "--no-pager"]
        )

        if code == 0:
            lines = output.strip().split("\n")
            for line in lines:
                if "failed" in line.lower() and ".service" in line:
                    parts = line.split()
                    if parts:
                        failed_services.append(parts[0])

        if not failed_services:
            score = 100
        elif len(failed_services) < 3:
            score = 75
        elif len(failed_services) < 5:
            score = 50
        else:
            score = 25

        recommendation = ""
        if failed_services:
            recommendation = f"Fix failed services: {', '.join(failed_services[:3])}"

        return HealthFactor(
            name="System Services",
            category=HealthCategory.SERVICES,
            score=score,
            weight=1.0,
            details=f"{len(failed_services)} failed" if failed_services else "All running",
            recommendation=recommendation,
        )

    def check_performance(self) -> HealthFactor:
        """Check system performance indicators."""
        score = 100
        issues = []

        # Check load average
        code, output, _ = self._run_command(["cat", "/proc/loadavg"])
        if code == 0:
            parts = output.split()
            if parts:
                try:
                    load_1m = float(parts[0])
                    # Get CPU count
                    cpu_code, cpu_out, _ = self._run_command(["nproc"])
                    cpu_count = int(cpu_out.strip()) if cpu_code == 0 else 1

                    if load_1m > cpu_count * 2:
                        issues.append("High load average")
                        score -= 30
                    elif load_1m > cpu_count:
                        issues.append("Elevated load")
                        score -= 15
                except (ValueError, IndexError):
                    pass

        # Check swap usage
        code, output, _ = self._run_command(["swapon", "--show"])
        if code == 0 and "partition" in output.lower():
            # Swap is being used - check how much
            code2, mem_out, _ = self._run_command(["free", "-m"])
            if code2 == 0:
                for line in mem_out.split("\n"):
                    if line.startswith("Swap:"):
                        parts = line.split()
                        if len(parts) >= 3:
                            try:
                                total = int(parts[1])
                                used = int(parts[2])
                                if total > 0 and (used / total) > 0.5:
                                    issues.append("High swap usage")
                                    score -= 15
                            except ValueError:
                                pass

        score = max(0, score)

        return HealthFactor(
            name="Performance",
            category=HealthCategory.PERFORMANCE,
            score=score,
            weight=1.0,
            details=", ".join(issues) if issues else "Normal",
            recommendation="High system load detected" if issues else "",
        )

    def run_all_checks(self) -> HealthReport:
        """Run all health checks.

        Returns:
            HealthReport with all factors
        """
        report = HealthReport()

        checks = [
            ("Disk Space", self.check_disk_space),
            ("Memory", self.check_memory),
            ("Updates", self.check_updates),
            ("Security", self.check_security),
            ("Services", self.check_services),
            ("Performance", self.check_performance),
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Checking health...", total=len(checks))

            for name, check_func in checks:
                progress.update(task, description=f"Checking {name}...")
                try:
                    factor = check_func()
                    report.factors.append(factor)
                except Exception as e:
                    if self.verbose:
                        console.print(f"[yellow]Warning: {name} check failed: {e}[/yellow]")
                progress.advance(task)

        return report

    def save_history(self, report: HealthReport):
        """Save health report to history."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

        history = []
        if self.history_path.exists():
            try:
                with open(self.history_path) as f:
                    history = json.load(f)
            except (OSError, json.JSONDecodeError):
                history = []

        entry = {
            "timestamp": report.timestamp.isoformat(),
            "overall_score": report.overall_score,
            "factors": {f.name: {"score": f.score, "details": f.details} for f in report.factors},
        }

        history.append(entry)

        # Keep last 30 entries
        history = history[-30:]

        try:
            with open(self.history_path, "w") as f:
                json.dump(history, f, indent=2)
        except OSError:
            pass

    def load_history(self) -> list[dict]:
        """Load health history."""
        if not self.history_path.exists():
            return []

        try:
            with open(self.history_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return []

    def display_report(self, report: HealthReport):
        """Display health report."""
        # Overall score
        score = report.overall_score
        status = report.status.value
        icon = report.status_icon

        score_color = "green" if score >= 75 else "yellow" if score >= 50 else "red"

        console.print()
        console.print(
            Panel(
                f"[bold]System Health Score:[/bold] [{score_color}]{score}/100[/{score_color}] {icon}",
                title="[bold cyan]Health Report[/bold cyan]",
            )
        )
        console.print()

        # Factors table
        table = Table(title="Health Factors")
        table.add_column("Factor", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Status")
        table.add_column("Details")

        for factor in report.factors:
            score_color = (
                "green" if factor.score >= 75 else "yellow" if factor.score >= 50 else "red"
            )
            table.add_row(
                factor.name,
                f"[{score_color}]{factor.score}[/{score_color}]",
                f"{factor.status_icon} {factor.status.value}",
                factor.details,
            )

        console.print(table)

        # Recommendations
        recommendations = report.get_recommendations()
        if recommendations:
            console.print()
            console.print("[bold yellow]Recommendations:[/bold yellow]")

            for i, factor in enumerate(recommendations, 1):
                points = f"(+{factor.fix_points} points)" if factor.fix_points else ""
                console.print(f"  {i}. {factor.recommendation} {points}")

    def display_history(self):
        """Display health history."""
        history = self.load_history()

        if not history:
            console.print("[yellow]No health history available[/yellow]")
            return

        table = Table(title="Health Score History")
        table.add_column("Date", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Trend")

        prev_score = None
        for entry in history[-10:]:  # Last 10 entries
            try:
                ts = datetime.fromisoformat(entry["timestamp"])
                score = entry["overall_score"]

                trend = ""
                if prev_score is not None:
                    if score > prev_score:
                        trend = "[green]↑[/green]"
                    elif score < prev_score:
                        trend = "[red]↓[/red]"
                    else:
                        trend = "→"

                score_color = "green" if score >= 75 else "yellow" if score >= 50 else "red"

                table.add_row(
                    ts.strftime("%Y-%m-%d %H:%M"),
                    f"[{score_color}]{score}[/{score_color}]",
                    trend,
                )

                prev_score = score
            except (KeyError, ValueError):
                continue

        console.print(table)


def run_health_check(
    action: str = "check",
    verbose: bool = False,
) -> int:
    """Run system health check.

    Args:
        action: Action to perform (check, history, fix)
        verbose: Enable verbose output

    Returns:
        Exit code (0 for success)
    """
    checker = HealthChecker(verbose=verbose)

    if action == "check":
        report = checker.run_all_checks()
        checker.display_report(report)
        checker.save_history(report)

        # Return 1 if health is poor
        return 0 if report.overall_score >= 50 else 1

    elif action == "history":
        checker.display_history()
        return 0

    elif action == "factors":
        console.print("[bold cyan]Health Factors:[/bold cyan]")
        factors = [
            ("Disk Space", "Monitors disk usage percentage", "1.0"),
            ("Memory", "Monitors RAM usage", "0.8"),
            ("System Updates", "Checks for available package updates", "1.2"),
            ("Security", "Checks firewall, SSH config, auto-updates", "1.5"),
            ("System Services", "Monitors failed systemd services", "1.0"),
            ("Performance", "Checks load average and swap usage", "1.0"),
        ]
        for name, desc, weight in factors:
            console.print(f"  [cyan]{name}[/cyan] (weight: {weight})")
            console.print(f"    {desc}")
        return 0

    elif action == "quick":
        # Quick check without saving history
        report = checker.run_all_checks()
        score = report.overall_score
        status = report.status.value

        score_color = "green" if score >= 75 else "yellow" if score >= 50 else "red"
        console.print(f"Health: [{score_color}]{score}/100[/{score_color}] ({status})")

        return 0 if score >= 50 else 1

    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Available actions: check, history, factors, quick")
        return 1
