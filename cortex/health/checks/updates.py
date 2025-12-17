import subprocess

from ..monitor import CheckResult, HealthCheck

# Command constants (full paths for security)
APT_CMD = "/usr/bin/apt"


class UpdateCheck(HealthCheck):
    """Check for pending system updates and security patches.

    This check evaluates the number of available package updates
    and applies score penalties accordingly:
    - Regular packages: -2 points each
    - Security updates: -10 points each

    Attributes:
        None
    """

    def run(self) -> CheckResult:
        """Check for available updates using apt.

        Returns:
            CheckResult with score based on pending updates.
        """
        score = 100
        pkg_count = 0
        sec_count = 0

        try:
            # Add timeout to prevent hangs
            res = subprocess.run(
                [APT_CMD, "list", "--upgradable"],
                capture_output=True,
                text=True,
                timeout=30
            )
            lines = res.stdout.splitlines()

            # apt list output header usually takes first line
            for line in lines[1:]:
                if line.strip():
                    if "security" in line.lower():
                        sec_count += 1
                    else:
                        pkg_count += 1

            # Scoring
            score -= (pkg_count * 2)
            score -= (sec_count * 10)

        except subprocess.TimeoutExpired as e:
            return CheckResult(
                name="System Updates",
                category="updates",
                score=0,
                status="CRITICAL",
                details=f"Check timed out: {e}",
                recommendation="Verify package manager configuration",
                weight=0.25
            )
        except FileNotFoundError:
            return CheckResult(
                name="System Updates",
                category="updates",
                score=0,
                status="CRITICAL",
                details="apt command not found",
                recommendation="This check requires apt package manager",
                weight=0.25
            )
        except OSError as e:
            return CheckResult(
                name="System Updates",
                category="updates",
                score=0,
                status="CRITICAL",
                details=f"Check failed: {e}",
                recommendation="Verify package manager configuration",
                weight=0.25
            )

        status = "OK"
        if score < 50:
            status = "CRITICAL"
        elif score < 90:
            status = "WARNING"

        details = f"{pkg_count} packages, {sec_count} security updates pending"
        if pkg_count == 0 and sec_count == 0:
            details = "System up to date"

        return CheckResult(
            name="System Updates",
            category="updates",
            score=max(0, score),
            status=status,
            details=details,
            recommendation="Run 'apt upgrade'" if score < 100 else None,
            weight=0.25
        )
