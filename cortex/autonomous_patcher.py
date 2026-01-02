#!/usr/bin/env python3
"""
Autonomous Security Patcher for Cortex Linux

Automatically patches security vulnerabilities with safety controls including:
- Dry-run mode by default
- Rollback capability
- Whitelist/blacklist support
- Severity-based filtering
- Integration with installation history
"""

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from cortex.installation_history import InstallationHistory, InstallationStatus, InstallationType
from cortex.vulnerability_scanner import Severity, Vulnerability, VulnerabilityScanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Module-level apt update tracking (shared across all instances)
_apt_update_lock = threading.Lock()
_apt_last_updated: datetime | None = None
_APT_UPDATE_INTERVAL_SECONDS = 300  # 5 minutes


class PatchStrategy(Enum):
    """Patching strategy"""

    AUTOMATIC = "automatic"  # Patch all vulnerabilities
    CRITICAL_ONLY = "critical_only"  # Only patch critical vulnerabilities
    HIGH_AND_ABOVE = "high_and_above"  # Patch high and critical
    MANUAL = "manual"  # Require manual approval for each patch


@dataclass
class PatchPlan:
    """Plan for patching vulnerabilities"""

    vulnerabilities: list[Vulnerability]
    packages_to_update: dict[str, str]  # package -> target_version
    estimated_duration_minutes: float
    requires_reboot: bool
    rollback_available: bool


@dataclass
class PatchResult:
    """Result of a patching operation"""

    patch_id: str
    timestamp: str
    vulnerabilities_patched: int
    packages_updated: list[str]
    success: bool
    errors: list[str]
    rollback_id: str | None = None
    duration_seconds: float | None = None


class AutonomousPatcher:
    """Autonomous security patching with safety controls"""

    def __init__(
        self,
        strategy: PatchStrategy = PatchStrategy.CRITICAL_ONLY,
        dry_run: bool = True,
        auto_approve: bool = False,
    ):
        """
        Initialize the autonomous patcher.

        Args:
            strategy: Patching strategy
            dry_run: If True, only show what would be patched
            auto_approve: If True, automatically approve patches (dangerous!)
        """
        self.strategy = strategy
        self.dry_run = dry_run
        self.auto_approve = auto_approve
        self.scanner = VulnerabilityScanner()
        self.history = InstallationHistory()

        # Safety controls
        self.whitelist: set[str] = set()  # Packages always allowed to patch
        self.blacklist: set[str] = set()  # Packages never patched automatically
        self.min_severity = Severity.MEDIUM  # Minimum severity to patch

        # Load configuration
        self._load_config()

    def _load_config(self):
        """Load patcher configuration from file"""
        config_path = Path.home() / ".cortex" / "patcher_config.json"

        if config_path.exists():
            try:
                import json

                with open(config_path) as f:
                    config = json.load(f)

                self.whitelist = set(config.get("whitelist", []))
                self.blacklist = set(config.get("blacklist", []))
                min_sev = config.get("min_severity", "medium")
                self.min_severity = Severity(min_sev.lower())

                logger.info(f"Loaded patcher config from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load patcher config: {e}")

    def _save_config(self):
        """Save patcher configuration to file"""
        config_path = Path.home() / ".cortex" / "patcher_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            import json

            config = {
                "whitelist": list(self.whitelist),
                "blacklist": list(self.blacklist),
                "min_severity": self.min_severity.value,
            }

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save patcher config: {e}")

    def _run_command(self, cmd: list[str]) -> tuple[bool, str, str]:
        """Execute command and return success, stdout, stderr"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "", "Command timed out")
        except Exception as e:
            return (False, "", str(e))

    def ensure_apt_updated(self, force: bool = False) -> bool:
        """
        Ensure apt package list is updated. Thread-safe and rate-limited.
        
        Args:
            force: If True, force update even if recently updated
            
        Returns:
            True if update succeeded or was recently done, False on failure
        """
        global _apt_last_updated
        
        with _apt_update_lock:
            now = datetime.now()
            
            # Check if we need to update
            if not force and _apt_last_updated is not None:
                elapsed = (now - _apt_last_updated).total_seconds()
                if elapsed < _APT_UPDATE_INTERVAL_SECONDS:
                    logger.debug(f"Apt cache still fresh ({elapsed:.0f}s old), skipping update")
                    return True
            
            # Run apt-get update
            logger.info("Updating apt package list...")
            success, stdout, stderr = self._run_command(["apt-get", "update", "-qq"])
            
            if success:
                _apt_last_updated = now
                logger.info("Apt package list updated successfully")
                return True
            else:
                logger.warning(f"Failed to update apt package list: {stderr}")
                # Still set timestamp to avoid hammering on repeated failures
                _apt_last_updated = now
                return False

    def _check_package_update_available(self, package_name: str) -> str | None:
        """
        Check if an update is available for a package.
        
        Note: Call ensure_apt_updated() before iterating over multiple packages
        to avoid repeated apt-get update calls.
        """
        try:
            # Check for available updates (apt-get update should be called beforehand)
            success, stdout, _ = self._run_command(
                ["apt-cache", "policy", package_name]
            )

            if success:
                # Parse output to find candidate version
                for line in stdout.split("\n"):
                    if "Candidate:" in line:
                        parts = line.split(":")
                        if len(parts) >= 2:
                            version = parts[1].strip()
                            if version and version != "(none)":
                                return version

        except Exception as e:
            logger.warning(f"Failed to check update for {package_name}: {e}")

        return None

    def _compare_versions(self, version1: str, operator: str, version2: str) -> bool:
        """
        Compare two Debian package versions using dpkg --compare-versions.
        
        Args:
            version1: First version string
            operator: Comparison operator (lt, le, eq, ne, ge, gt)
            version2: Second version string
            
        Returns:
            True if the comparison holds, False otherwise
        """
        try:
            success, _, _ = self._run_command(
                ["dpkg", "--compare-versions", version1, operator, version2]
            )
            return success
        except Exception as e:
            logger.warning(f"Version comparison failed: {e}")
            return False

    def _update_fixes_vulnerability(
        self, candidate_version: str, vulnerability: Vulnerability
    ) -> bool:
        """
        Check if the candidate version fixes the vulnerability.
        
        Args:
            candidate_version: The version available for update
            vulnerability: The vulnerability to check
            
        Returns:
            True if the update will fix the vulnerability
        """
        fixed_version = vulnerability.fixed_version
        
        # If no fixed version is specified, we can't verify - log warning but allow
        if not fixed_version:
            logger.debug(
                f"No fixed_version specified for {vulnerability.cve_id} on "
                f"{vulnerability.package_name}, cannot verify fix"
            )
            return True  # Allow update when fixed_version is unknown
        
        # Check if candidate version >= fixed version
        if self._compare_versions(candidate_version, "ge", fixed_version):
            logger.debug(
                f"Candidate {candidate_version} >= fixed {fixed_version} for "
                f"{vulnerability.package_name} ({vulnerability.cve_id})"
            )
            return True
        
        logger.warning(
            f"Update for {vulnerability.package_name} to {candidate_version} does NOT fix "
            f"{vulnerability.cve_id} (requires >= {fixed_version})"
        )
        return False

    def _should_patch(self, vulnerability: Vulnerability) -> bool:
        """
        Determine if a vulnerability should be patched based on strategy and filters.

        Args:
            vulnerability: Vulnerability to check

        Returns:
            True if should be patched
        """
        # Check blacklist
        if vulnerability.package_name in self.blacklist:
            logger.debug(f"Skipping {vulnerability.package_name} (blacklisted)")
            return False

        # Check whitelist (always patch if whitelisted)
        if vulnerability.package_name in self.whitelist:
            return True

        # Check minimum severity
        severity_order = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
            Severity.UNKNOWN: 0,
        }

        if severity_order.get(vulnerability.severity, 0) < severity_order.get(
            self.min_severity, 0
        ):
            return False

        # Check strategy
        if self.strategy == PatchStrategy.CRITICAL_ONLY:
            return vulnerability.severity == Severity.CRITICAL
        elif self.strategy == PatchStrategy.HIGH_AND_ABOVE:
            return vulnerability.severity in [Severity.CRITICAL, Severity.HIGH]
        elif self.strategy == PatchStrategy.AUTOMATIC:
            return True
        elif self.strategy == PatchStrategy.MANUAL:
            return False  # Manual approval required

        return False

    def create_patch_plan(
        self, vulnerabilities: list[Vulnerability] | None = None
    ) -> PatchPlan:
        """
        Create a plan for patching vulnerabilities.

        Args:
            vulnerabilities: List of vulnerabilities to patch (if None, scans all)

        Returns:
            PatchPlan with packages to update
        """
        if vulnerabilities is None:
            # Scan for vulnerabilities
            scan_result = self.scanner.scan_all_packages()
            vulnerabilities = scan_result.vulnerabilities

        # Filter vulnerabilities based on strategy
        to_patch = [v for v in vulnerabilities if self._should_patch(v)]

        if not to_patch:
            return PatchPlan(
                vulnerabilities=[],
                packages_to_update={},
                estimated_duration_minutes=0.0,
                requires_reboot=False,
                rollback_available=True,
            )

        # Group by package
        packages_to_update: dict[str, str] = {}
        package_vulns: dict[str, list[Vulnerability]] = {}

        for vuln in to_patch:
            if vuln.package_name not in package_vulns:
                package_vulns[vuln.package_name] = []
            package_vulns[vuln.package_name].append(vuln)

        # Update apt package list once before checking all packages
        self.ensure_apt_updated()

        # Check for available updates and verify they fix vulnerabilities
        requires_reboot = False
        verified_vulns: list[Vulnerability] = []
        skipped_vulns: list[tuple[Vulnerability, str]] = []  # (vuln, reason)

        for package_name, vulns in package_vulns.items():
            # Check if update is available
            update_version = self._check_package_update_available(package_name)

            if not update_version:
                for vuln in vulns:
                    skipped_vulns.append((vuln, "no update available"))
                continue

            # Verify the update fixes each vulnerability for this package
            fixes_any = False
            for vuln in vulns:
                if self._update_fixes_vulnerability(update_version, vuln):
                    verified_vulns.append(vuln)
                    fixes_any = True
                else:
                    skipped_vulns.append(
                        (vuln, f"update to {update_version} does not fix (requires >= {vuln.fixed_version})")
                    )

            # Only include the package if it fixes at least one vulnerability
            if fixes_any:
                packages_to_update[package_name] = update_version

                # Check if this is a kernel package (requires reboot)
                if "linux-image" in package_name or "linux-headers" in package_name:
                    requires_reboot = True

        # Log skipped vulnerabilities
        if skipped_vulns:
            logger.info(f"Skipped {len(skipped_vulns)} vulnerabilities that cannot be fixed by available updates:")
            for vuln, reason in skipped_vulns[:5]:  # Log first 5
                logger.info(f"  - {vuln.cve_id} ({vuln.package_name}): {reason}")
            if len(skipped_vulns) > 5:
                logger.info(f"  ... and {len(skipped_vulns) - 5} more")

        # Estimate duration (rough: 1 minute per package)
        estimated_duration = len(packages_to_update) * 1.0

        return PatchPlan(
            vulnerabilities=verified_vulns,
            packages_to_update=packages_to_update,
            estimated_duration_minutes=estimated_duration,
            requires_reboot=requires_reboot,
            rollback_available=True,
        )

    def apply_patch_plan(self, plan: PatchPlan) -> PatchResult:
        """
        Apply a patch plan.

        Args:
            plan: Patch plan to apply

        Returns:
            PatchResult with results
        """
        patch_id = f"patch_{int(time.time())}"
        start_time = datetime.now()

        if not plan.packages_to_update:
            return PatchResult(
                patch_id=patch_id,
                timestamp=start_time.isoformat(),
                vulnerabilities_patched=0,
                packages_updated=[],
                success=True,
                errors=[],
            )

        if self.dry_run:
            logger.info("DRY RUN MODE - No packages will be updated")
            logger.info(f"Would update {len(plan.packages_to_update)} packages:")
            for package, version in plan.packages_to_update.items():
                logger.info(f"  - {package} -> {version}")

            return PatchResult(
                patch_id=patch_id,
                timestamp=start_time.isoformat(),
                vulnerabilities_patched=len(plan.vulnerabilities),
                packages_updated=list(plan.packages_to_update.keys()),
                success=True,
                errors=[],
            )

        # Record installation start
        packages_list = list(plan.packages_to_update.keys())
        commands = ["apt-get update"]
        if packages_list:
            commands.append("apt-get install -y " + " ".join(packages_list))

        install_id = self.history.record_installation(
            InstallationType.UPGRADE,
            packages_list,
            commands,
            start_time,
        )

        # Execute patching
        errors = []
        updated_packages = []

        try:
            # Update package list
            logger.info("Updating package list...")
            success, stdout, stderr = self._run_command(["apt-get", "update", "-qq"])
            if not success:
                errors.append(f"Failed to update package list: {stderr}")

            # Install updates
            for package_name, target_version in plan.packages_to_update.items():
                logger.info(f"Updating {package_name} to {target_version}...")

                # Use apt-get install with specific version if available
                if target_version:
                    cmd = ["apt-get", "install", "-y", f"{package_name}={target_version}"]
                else:
                    cmd = ["apt-get", "install", "-y", package_name]

                success, stdout, stderr = self._run_command(cmd)

                if success:
                    updated_packages.append(package_name)
                    logger.info(f"✅ Updated {package_name}")
                else:
                    error_msg = f"Failed to update {package_name}: {stderr}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            # Update installation record
            if errors:
                self.history.update_installation(
                    install_id, InstallationStatus.FAILED, "\n".join(errors)
                )
                success = False
            else:
                self.history.update_installation(install_id, InstallationStatus.SUCCESS)
                success = True

            duration = (datetime.now() - start_time).total_seconds()

            result = PatchResult(
                patch_id=patch_id,
                timestamp=start_time.isoformat(),
                vulnerabilities_patched=len(plan.vulnerabilities),
                packages_updated=updated_packages,
                success=success,
                errors=errors,
                rollback_id=install_id,
                duration_seconds=duration,
            )

            if success:
                logger.info(
                    f"✅ Patch complete: {len(updated_packages)} packages updated in {duration:.2f}s"
                )
            else:
                logger.error(f"❌ Patch failed: {len(errors)} errors")

            return result

        except Exception as e:
            error_msg = f"Patch operation failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

            self.history.update_installation(
                install_id, InstallationStatus.FAILED, error_msg
            )

            return PatchResult(
                patch_id=patch_id,
                timestamp=start_time.isoformat(),
                vulnerabilities_patched=0,
                packages_updated=[],
                success=False,
                errors=errors,
                rollback_id=install_id,
            )

    def patch_vulnerabilities(
        self, vulnerabilities: list[Vulnerability] | None = None
    ) -> PatchResult:
        """
        Scan and patch vulnerabilities automatically.

        Args:
            vulnerabilities: Optional list of vulnerabilities to patch

        Returns:
            PatchResult with patching results
        """
        # Create patch plan
        plan = self.create_patch_plan(vulnerabilities)

        if not plan.packages_to_update:
            logger.info("No packages need patching")
            return PatchResult(
                patch_id=f"patch_{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                vulnerabilities_patched=0,
                packages_updated=[],
                success=True,
                errors=[],
            )

        # Show plan
        logger.info("📋 Patch Plan:")
        logger.info(f"  Vulnerabilities to patch: {len(plan.vulnerabilities)}")
        logger.info(f"  Packages to update: {len(plan.packages_to_update)}")
        logger.info(f"  Estimated duration: {plan.estimated_duration_minutes:.1f} minutes")
        if plan.requires_reboot:
            logger.warning("  ⚠️  System reboot required after patching")

        # Apply plan
        return self.apply_patch_plan(plan)

    def add_to_whitelist(self, package_name: str):
        """Add package to whitelist"""
        self.whitelist.add(package_name)
        self._save_config()
        logger.info(f"Added {package_name} to whitelist")

    def add_to_blacklist(self, package_name: str):
        """Add package to blacklist"""
        self.blacklist.add(package_name)
        self._save_config()
        logger.info(f"Added {package_name} to blacklist")

    def set_min_severity(self, severity: Severity):
        """Set minimum severity for patching"""
        self.min_severity = severity
        self._save_config()
        logger.info(f"Minimum severity set to {severity.value}")


# CLI Interface
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Autonomous security patcher")
    parser.add_argument("--scan-and-patch", action="store_true", help="Scan and patch vulnerabilities")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run mode (default)")
    parser.add_argument("--apply", action="store_true", help="Actually apply patches (disable dry-run)")
    parser.add_argument(
        "--strategy",
        choices=["automatic", "critical_only", "high_and_above", "manual"],
        default="critical_only",
        help="Patching strategy",
    )
    parser.add_argument("--whitelist", help="Add package to whitelist")
    parser.add_argument("--blacklist", help="Add package to blacklist")
    parser.add_argument(
        "--min-severity",
        choices=["critical", "high", "medium", "low"],
        help="Minimum severity to patch",
    )

    args = parser.parse_args()

    dry_run = args.dry_run and not args.apply
    strategy = PatchStrategy(args.strategy)

    patcher = AutonomousPatcher(strategy=strategy, dry_run=dry_run)

    if args.whitelist:
        patcher.add_to_whitelist(args.whitelist)
        print(f"✅ Added {args.whitelist} to whitelist")

    if args.blacklist:
        patcher.add_to_blacklist(args.blacklist)
        print(f"✅ Added {args.blacklist} to blacklist")

    if args.min_severity:
        patcher.set_min_severity(Severity(args.min_severity))
        print(f"✅ Minimum severity set to {args.min_severity}")

    if args.scan_and_patch:
        if dry_run:
            print("🔍 DRY RUN MODE - No packages will be updated\n")

        result = patcher.patch_vulnerabilities()

        if result.success:
            print("\n✅ Patch complete!")
            print(f"  Packages updated: {len(result.packages_updated)}")
            print(f"  Vulnerabilities patched: {result.vulnerabilities_patched}")
            if result.duration_seconds:
                print(f"  Duration: {result.duration_seconds:.2f}s")
        else:
            print("\n❌ Patch failed!")
            for error in result.errors:
                print(f"  - {error}")
            sys.exit(1)

    if not any([args.scan_and_patch, args.whitelist, args.blacklist, args.min_severity]):
        parser.print_help()

