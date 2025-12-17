import shutil

from ..monitor import CheckResult, HealthCheck


class DiskCheck(HealthCheck):
    """Check root filesystem disk usage."""

    def run(self) -> CheckResult:
        """Calculate disk usage percentage.

        Returns:
            CheckResult based on usage thresholds.
        """
        try:
            # Use _ for unused variable (free space)
            total, used, _ = shutil.disk_usage("/")
            usage_percent = (used / total) * 100
        except Exception as e:
            return CheckResult(
                name="Disk Usage",
                category="disk",
                score=0,
                status="CRITICAL",
                details=f"Check failed: {e}",
                recommendation="Check disk mounts and permissions",
                weight=0.20
            )

        # Explicit early returns to avoid static analysis confusion
        if usage_percent > 90:
            return CheckResult(
                name="Disk Usage",
                category="disk",
                score=0,
                status="CRITICAL",
                details=f"{usage_percent:.1f}% used",
                recommendation="Clean up disk space immediately",
                weight=0.20
            )

        if usage_percent > 80:
            return CheckResult(
                name="Disk Usage",
                category="disk",
                score=50,
                status="WARNING",
                details=f"{usage_percent:.1f}% used",
                recommendation="Consider cleaning up disk space",
                weight=0.20
            )

        return CheckResult(
            name="Disk Usage",
            category="disk",
            score=100,
            status="OK",
            details=f"{usage_percent:.1f}% used",
            recommendation=None,
            weight=0.20
        )
