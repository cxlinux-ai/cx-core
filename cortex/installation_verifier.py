#!/usr/bin/env python3
"""
Installation Verification System
Validates that software installations completed successfully
"""

import datetime
import json
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from shutil import which


class VerificationStatus(Enum):
    """Verification result status"""

    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass
class VerificationTest:
    """Individual verification test"""

    name: str
    test_type: str  # command, file, service, version
    expected: str
    actual: str | None = None
    passed: bool = False
    error_message: str | None = None


@dataclass
class VerificationResult:
    """Complete verification result"""

    package_name: str
    status: VerificationStatus
    tests: list[VerificationTest]
    overall_message: str
    timestamp: str


class InstallationVerifier:
    """Verifies software installations"""

    # Common verification patterns for popular packages
    VERIFICATION_PATTERNS = {
        "nginx": {
            "command": "nginx -v",
            "file": "/usr/sbin/nginx",
            "service": "nginx",
            "version_regex": r"nginx/(\d+\.\d+\.\d+)",
        },
        "apache2": {
            "command": "apache2 -v",
            "file": "/usr/sbin/apache2",
            "service": "apache2",
            "version_regex": r"Apache/(\d+\.\d+\.\d+)",
        },
        "postgresql": {
            "command": "psql --version",
            "file": "/usr/bin/psql",
            "service": "postgresql",
            "version_regex": r"PostgreSQL[^\d]*([\d\.]+)",
        },
        "mysql-server": {
            "command": "mysql --version",
            "file": "/usr/bin/mysql",
            "service": "mysql",
            "version_regex": r"Ver (\d+\.\d+\.\d+)",
        },
        "docker": {
            "command": "docker --version",
            "file": "/usr/bin/docker",
            "service": "docker",
            "version_regex": r"Docker version (\d+\.\d+\.\d+)",
        },
        "python3": {
            "command": "python3 --version",
            "file": "/usr/bin/python3",
            "version_regex": r"Python (\d+\.\d+\.\d+)",
        },
        "nodejs": {
            "command": "node --version",
            "file": "/usr/bin/node",
            "version_regex": r"v(\d+\.\d+\.\d+)",
        },
        "redis-server": {
            "command": "redis-server --version",
            "file": "/usr/bin/redis-server",
            "service": "redis-server",
            "version_regex": r"v=(\d+\.\d+\.\d+)",
        },
        "git": {
            "command": "git --version",
            "file": "/usr/bin/git",
            "version_regex": r"git version (\d+\.\d+\.\d+)",
        },
        "curl": {
            "command": "curl --version",
            "file": "/usr/bin/curl",
            "version_regex": r"curl (\d+\.\d+\.\d+)",
        },
    }

    def __init__(self):
        self.results: list[VerificationResult] = []

    def _run_command(self, cmd: str, timeout: int = 5) -> tuple[bool, str, str]:
        """
        Execute command safely
        Returns: (success, stdout, stderr)
        """
        try:
            result = subprocess.run(
                shlex.split(cmd), capture_output=True, text=True, timeout=timeout
            )
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "", "Command timed out")
        except FileNotFoundError:
            return (False, "", "Command not found")
        except Exception as e:
            return (False, "", str(e))

    def _test_command_exists(self, cmd: str) -> VerificationTest:
        """Test if command can be executed"""
        success, stdout, stderr = self._run_command(cmd)

        return VerificationTest(
            name=f"Command execution: {cmd}",
            test_type="command",
            expected="Command executes successfully",
            actual=stdout[:100] if success else stderr[:100],
            passed=success,
            error_message=None if success else f"Command failed: {stderr}",
        )

    def _test_file_exists(self, filepath: str) -> VerificationTest:
        """Test if file/binary exists"""
        path = Path(filepath)
        exists = path.exists()
        actual_location: str | None = None

        if exists:
            actual_location = str(path)
        else:
            # Try to resolve via PATH when direct path lookup fails
            command_name = filepath if not path.is_absolute() else path.name
            resolved_path = which(command_name)
            if resolved_path:
                exists = True
                actual_location = resolved_path

        actual_message = f"Found at {actual_location}" if actual_location else "Not found"

        return VerificationTest(
            name=f"File exists: {filepath}",
            test_type="file",
            expected="File exists and is accessible",
            actual=actual_message,
            passed=exists,
            error_message=None if exists else f"File not found: {filepath}",
        )

    def _test_service_status(self, service_name: str) -> VerificationTest:
        """Test if systemd service is active"""
        success, stdout, stderr = self._run_command(f"systemctl is-active {service_name}")

        service_state = stdout.strip().lower()
        is_active = success and service_state == "active"
        actual = service_state or stderr.strip() or "unknown"

        error_message = None
        if not is_active:
            if service_state and service_state != "active":
                error_message = f"Service state: {service_state}"
            elif stderr:
                error_message = stderr.strip()
            else:
                error_message = "Service check failed"

        return VerificationTest(
            name=f"Service status: {service_name}",
            test_type="service",
            expected="Service is active/running",
            actual=actual,
            passed=is_active,
            error_message=error_message,
        )

    def _test_version_match(
        self, cmd: str, version_regex: str, expected_version: str | None = None
    ) -> VerificationTest:
        """Test version information"""
        success, stdout, stderr = self._run_command(cmd)

        if not success:
            return VerificationTest(
                name=f"Version check: {cmd}",
                test_type="version",
                expected=expected_version or "Any version",
                actual="Command failed",
                passed=False,
                error_message=stderr,
            )

        # Extract version
        match = re.search(version_regex, stdout + stderr)
        actual_version = match.group(1) if match else "Unknown"

        # Check if version matches if expected_version provided
        version_matches = True
        if expected_version:
            version_matches = actual_version == expected_version

        return VerificationTest(
            name=f"Version check: {cmd}",
            test_type="version",
            expected=expected_version or "Any version",
            actual=actual_version,
            passed=bool(match) and version_matches,
            error_message=None if match else "Could not parse version",
        )

    def verify_package(
        self,
        package_name: str,
        expected_version: str | None = None,
        custom_tests: list[dict] | None = None,
    ) -> VerificationResult:
        """
        Verify package installation

        Args:
            package_name: Name of package to verify
            expected_version: Optional version to check against
            custom_tests: Optional list of custom test definitions
        """

        tests: list[VerificationTest] = []

        # Use predefined patterns if available
        if package_name in self.VERIFICATION_PATTERNS:
            pattern = self.VERIFICATION_PATTERNS[package_name]

            # Test command
            if "command" in pattern:
                tests.append(self._test_command_exists(pattern["command"]))

            # Test file
            if "file" in pattern:
                tests.append(self._test_file_exists(pattern["file"]))

            # Test service
            if "service" in pattern:
                tests.append(self._test_service_status(pattern["service"]))

            # Test version
            if "version_regex" in pattern and "command" in pattern:
                tests.append(
                    self._test_version_match(
                        pattern["command"], pattern["version_regex"], expected_version
                    )
                )

        # Add custom tests
        if custom_tests:
            for test_def in custom_tests:
                if test_def.get("type") == "command":
                    tests.append(self._test_command_exists(test_def["command"]))
                elif test_def.get("type") == "file":
                    tests.append(self._test_file_exists(test_def["path"]))
                elif test_def.get("type") == "service":
                    tests.append(self._test_service_status(test_def["name"]))

        # If no patterns found, try basic checks
        if not tests:
            # Try dpkg query
            success, stdout, stderr = self._run_command(f"dpkg -l {package_name}")
            tests.append(
                VerificationTest(
                    name=f"Package installed: {package_name}",
                    test_type="dpkg",
                    expected="Package found in dpkg",
                    actual="Installed" if success else "Not found",
                    passed=success,
                    error_message=None if success else "Package not in dpkg database",
                )
            )

        # Determine overall status
        total_tests = len(tests)
        passed_tests = sum(1 for t in tests if t.passed)

        if passed_tests == total_tests:
            status = VerificationStatus.SUCCESS
            message = f"✅ {package_name} installed and verified successfully"
        elif passed_tests == 0:
            status = VerificationStatus.FAILED
            message = f"❌ {package_name} installation verification failed"
        elif passed_tests > 0:
            status = VerificationStatus.PARTIAL
            message = (
                f"⚠️ {package_name} partially verified ({passed_tests}/{total_tests} tests passed)"
            )
        else:
            status = VerificationStatus.UNKNOWN
            message = f"❓ Could not verify {package_name} installation"

        result = VerificationResult(
            package_name=package_name,
            status=status,
            tests=tests,
            overall_message=message,
            timestamp=datetime.datetime.now().isoformat(),
        )

        self.results.append(result)
        return result

    def verify_multiple_packages(self, packages: list[str]) -> list[VerificationResult]:
        """Verify multiple packages"""
        results = []

        print(f"\n🔍 Verifying {len(packages)} package(s)...")

        for package in packages:
            print(f"\n  Checking {package}...")
            result = self.verify_package(package)
            results.append(result)
            print(f"  {result.overall_message}")

        return results

    def print_detailed_results(self, result: VerificationResult) -> None:
        """Print detailed verification results"""
        print("\n" + "=" * 60)
        print(f"VERIFICATION REPORT: {result.package_name}")
        print("=" * 60)
        print(f"\nStatus: {result.status.value.upper()}")
        print(f"Time: {result.timestamp}")
        print(f"\n{result.overall_message}\n")

        print("Test Results:")
        print("-" * 60)

        for i, test in enumerate(result.tests, 1):
            status_icon = "✅" if test.passed else "❌"
            print(f"\n{i}. {status_icon} {test.name}")
            print(f"   Type: {test.test_type}")
            print(f"   Expected: {test.expected}")
            print(f"   Actual: {test.actual}")

            if test.error_message:
                print(f"   Error: {test.error_message}")

        print("\n" + "=" * 60)

    def export_results_json(self, filepath: str) -> None:
        """Export all verification results to JSON"""
        results_dict = []

        for result in self.results:
            result_dict = {
                "package_name": result.package_name,
                "status": result.status.value,
                "overall_message": result.overall_message,
                "timestamp": result.timestamp,
                "tests": [asdict(test) for test in result.tests],
            }
            results_dict.append(result_dict)

        with open(filepath, "w") as f:
            json.dump(results_dict, f, indent=2)

        print(f"\n✅ Results exported to {filepath}")

    def get_summary(self) -> dict[str, int]:
        """Get summary statistics"""
        summary = {
            "total": len(self.results),
            "success": 0,
            "failed": 0,
            "partial": 0,
            "unknown": 0,
        }

        for result in self.results:
            if result.status == VerificationStatus.SUCCESS:
                summary["success"] += 1
            elif result.status == VerificationStatus.FAILED:
                summary["failed"] += 1
            elif result.status == VerificationStatus.PARTIAL:
                summary["partial"] += 1
            else:
                summary["unknown"] += 1

        return summary


# CLI Interface
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Verify software package installations")
    parser.add_argument("packages", nargs="+", help="Package names to verify")
    parser.add_argument("--version", help="Expected version to verify against")
    parser.add_argument("--export", help="Export results to JSON file")
    parser.add_argument("--detailed", action="store_true", help="Show detailed test results")

    args = parser.parse_args()

    verifier = InstallationVerifier()

    # Verify packages
    results = verifier.verify_multiple_packages(args.packages)

    # Print detailed results if requested
    if args.detailed:
        for result in results:
            verifier.print_detailed_results(result)

    # Print summary
    summary = verifier.get_summary()
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Total packages: {summary['total']}")
    print(f"✅ Success: {summary['success']}")
    print(f"❌ Failed: {summary['failed']}")
    print(f"⚠️ Partial: {summary['partial']}")
    print(f"❓ Unknown: {summary['unknown']}")

    # Export if requested
    if args.export:
        verifier.export_results_json(args.export)

    # Exit with appropriate code
    sys.exit(0 if summary["failed"] == 0 else 1)
