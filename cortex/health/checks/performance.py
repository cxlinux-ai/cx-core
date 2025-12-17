import multiprocessing
import os

from ..monitor import CheckResult, HealthCheck


class PerformanceCheck(HealthCheck):
    """Check system performance metrics including CPU load and memory usage."""

    def run(self) -> CheckResult:
        """Check system load and memory usage.

        Returns:
            CheckResult with performance score.
        """
        score = 100
        issues = []
        rec = None

        # 1. Load Average (1min)
        try:
            load1, _, _ = os.getloadavg()
            cores = multiprocessing.cpu_count()
            # Load ratio against core count
            load_ratio = load1 / cores

            if load_ratio > 1.0:
                score -= 50
                issues.append(f"High Load ({load1:.2f})")
                rec = "Check top processes"
        except OSError:
            pass  # Skip on Windows etc.

        # 2. Memory Usage (Linux /proc/meminfo)
        try:
            with open('/proc/meminfo') as f:
                meminfo = {}
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = int(parts[1].strip().split()[0])

                if 'MemTotal' in meminfo and 'MemAvailable' in meminfo:
                    total = meminfo['MemTotal']
                    avail = meminfo['MemAvailable']
                    used_percent = ((total - avail) / total) * 100

                    if used_percent > 80:
                        penalty = int(used_percent - 80)
                        score -= penalty
                        issues.append(f"High Memory ({used_percent:.0f}%)")
        except FileNotFoundError:
            pass  # Non-Linux systems

        # Summary of results
        status = "OK"
        if score < 50:
            status = "CRITICAL"
        elif score < 90:
            status = "WARNING"

        details = ", ".join(issues) if issues else "Optimal"

        return CheckResult(
            name="System Load",
            category="performance",
            score=max(0, score),
            status=status,
            details=details,
            recommendation=rec,
            weight=0.20  # 20%
        )
