import os
import subprocess

from ..monitor import CheckResult, HealthCheck

# Command constants (full paths for security - avoids PATH manipulation attacks)
SYSTEMCTL_CMD = "/usr/bin/systemctl"
UFW_SERVICE = "ufw"
SSH_CONFIG_PATH = "/etc/ssh/sshd_config"


class SecurityCheck(HealthCheck):
    """Check system security posture including firewall and SSH configuration.

    This check evaluates:
    - UFW firewall status (0 points if inactive)
    - SSH root login configuration (-50 points if enabled)

    Attributes:
        None

    Example:
        >>> check = SecurityCheck()
        >>> result = check.run()
        >>> print(result.score)
        100
    """

    def run(self) -> CheckResult:
        """Execute security checks and return aggregated result.

        Returns:
            CheckResult: Security posture score and recommendations.
        """
        score = 100
        issues = []
        recommendations = []

        # 1. Firewall (UFW) Check
        ufw_active = False
        try:
            # Add timeout to prevent hanging (Fixes Reliability Issue)
            res = subprocess.run(
                [SYSTEMCTL_CMD, "is-active", UFW_SERVICE],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Fix: Use exact match to avoid matching "inactive" which contains "active"
            if res.returncode == 0 and res.stdout.strip() == "active":
                ufw_active = True
        except subprocess.TimeoutExpired:
            pass  # Command timed out, treat as inactive or unavailable
        except FileNotFoundError:
            pass  # Environment without systemctl (e.g., Docker or non-systemd)
        except OSError:
            pass  # Other OS-level errors

        if not ufw_active:
            score = 0  # Spec: 0 points if Firewall is inactive
            issues.append("Firewall Inactive")
            recommendations.append("Enable UFW Firewall")

        # 2. SSH Root Login Check
        self._check_ssh_root_login(issues, recommendations)
        if "Root SSH Allowed" in issues:
            score -= 50

        status = "OK"
        if score < 50:
            status = "CRITICAL"
        elif score < 100:
            status = "WARNING"

        return CheckResult(
            name="Security Posture",
            category="security",
            score=max(0, score),
            status=status,
            details=", ".join(issues) if issues else "Secure",
            recommendation=", ".join(recommendations) if recommendations else None,
            weight=0.35
        )

    def _check_ssh_root_login(
        self, issues: list[str], recommendations: list[str]
    ) -> None:
        """Check if SSH root login is enabled.

        Args:
            issues: List to append issue descriptions to.
            recommendations: List to append recommendations to.
        """
        try:
            if not os.path.exists(SSH_CONFIG_PATH):
                return

            with open(SSH_CONFIG_PATH) as f:
                for line in f:
                    stripped = line.strip()
                    # Check for uncommented PermitRootLogin yes
                    if stripped.startswith("PermitRootLogin"):
                        parts = stripped.split()
                        if len(parts) >= 2 and parts[1] == "yes":
                            issues.append("Root SSH Allowed")
                            recommendations.append(
                                "Disable SSH Root Login in sshd_config"
                            )
                            return
        except PermissionError:
            pass  # Cannot read config, skip check
        except OSError:
            pass  # Other file system errors
