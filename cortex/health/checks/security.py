import subprocess
import os
from ..monitor import HealthCheck, CheckResult

class SecurityCheck(HealthCheck):
    """
    Checks system security posture including firewall status and SSH configuration.
    
    Evaluates UFW firewall activity and SSH root login permissions,
    returning a weighted score and actionable recommendations.
    """

    def run(self) -> CheckResult:
        """
        Execute security checks and return aggregated results.
        
        Returns:
            CheckResult: Security assessment with score (0-100), status,
                        detected issues, and recommendations.
        """
        score = 100
        issues = []
        recommendations = []
        
        # 1. Firewall (UFW) Check
        # Returns: score_delta (negative for penalty), issues, recommendations
        fw_score_delta, fw_issues, fw_recs = self._check_firewall()
        
        # If firewall is inactive, score becomes 0 immediately per requirements
        if fw_score_delta == -100:
             score = 0
        
        issues.extend(fw_issues)
        recommendations.extend(fw_recs)

        # 2. SSH Root Login Check
        ssh_score_delta, ssh_issues, ssh_recs = self._check_ssh_root_login()
        score += ssh_score_delta
        issues.extend(ssh_issues)
        recommendations.extend(ssh_recs)

        status = "OK"
        if score < 50: status = "CRITICAL"
        elif score < 100: status = "WARNING"

        return CheckResult(
            name="Security Posture",
            category="security",
            score=max(0, score),
            status=status,
            details=", ".join(issues) if issues else "Secure",
            recommendation=", ".join(recommendations) if recommendations else None,
            weight=0.35
        )

    def _check_firewall(self) -> tuple[int, list[str], list[str]]:
        """
        Check if UFW is active.
        
        Returns:
            tuple: (score_delta, issues_list, recommendations_list)
        """
        try:
            res = subprocess.run(
                ["systemctl", "is-active", "ufw"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if res.returncode == 0 and res.stdout.strip() == "active":
                return 0, [], []
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
        
        # Return -100 to signal immediate failure condition
        return -100, ["Firewall Inactive"], ["Enable UFW Firewall"]

    def _check_ssh_root_login(self) -> tuple[int, list[str], list[str]]:
        """
        Check for PermitRootLogin yes in sshd_config.
        
        Returns:
            tuple: (score_delta, issues_list, recommendations_list)
        """
        try:
            ssh_config = "/etc/ssh/sshd_config"
            if os.path.exists(ssh_config):
                with open(ssh_config, 'r') as f:
                    for line in f:
                        parts = line.split()
                        # Precise check: PermitRootLogin must be the first word, yes the second
                        # This avoids matching commented lines or "no" followed by comments
                        if len(parts) >= 2 and parts[0] == "PermitRootLogin" and parts[1] == "yes":
                            return -50, ["Root SSH Allowed"], ["Disable SSH Root Login in sshd_config"]
        except (PermissionError, Exception):
            pass
        
        return 0, [], []