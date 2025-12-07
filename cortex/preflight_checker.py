"""
Preflight System Checker for Cortex Installation

Performs real system checks before installation to identify issues,
verify requirements, and predict what will be installed.
"""

import os
import sys
import shutil
import socket
import platform
import subprocess
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path


@dataclass
class DiskInfo:
    """Disk usage information for a path"""
    path: str
    free_mb: int
    total_mb: int
    filesystem: str
    exists: bool
    writable: bool


@dataclass
class PackageInfo:
    """Information about a package/binary"""
    name: str
    installed: bool
    version: Optional[str] = None
    path: Optional[str] = None


@dataclass
class ServiceInfo:
    """Information about a system service"""
    name: str
    exists: bool
    active: bool
    enabled: bool = False


@dataclass
class PreflightReport:
    """Complete preflight check report"""
    os_info: Dict[str, str] = field(default_factory=dict)
    kernel_info: Dict[str, str] = field(default_factory=dict)
    cpu_arch: str = ""
    cgroup_info: Dict[str, str] = field(default_factory=dict)
    disk_usage: List[DiskInfo] = field(default_factory=list)
    package_status: List[PackageInfo] = field(default_factory=list)
    service_status: List[ServiceInfo] = field(default_factory=list)
    permissions_status: Dict[str, bool] = field(default_factory=dict)
    network_status: Dict[str, bool] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    
    # Installation estimates based on real checks
    packages_to_install: List[Dict[str, str]] = field(default_factory=list)
    total_download_mb: int = 0
    total_disk_required_mb: int = 0
    config_changes: List[str] = field(default_factory=list)


class PreflightChecker:
    """
    Real system checker for Cortex installation preflight checks.
    
    All checks are performed against the actual system - no simulation.
    """
    
    # Paths to check for disk space
    DISK_CHECK_PATHS = ['/', '/var/lib/docker', '/opt']
    MIN_DISK_SPACE_MB = 500
    
    def __init__(self, api_key: Optional[str] = None, provider: str = 'openai'):
        self.report = PreflightReport()
        self._is_linux = sys.platform.startswith('linux')
        self._is_windows = sys.platform == 'win32'
        self._is_mac = sys.platform == 'darwin'
        self.api_key = api_key
        self.provider = provider
        self._llm_client = None
    
    def _run_command(self, cmd: List[str], timeout: int = 10) -> Tuple[bool, str]:
        """Run a shell command and return success status and output"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode == 0, result.stdout.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except FileNotFoundError:
            return False, "Command not found"
        except Exception as e:
            return False, str(e)
    
    def _run_shell_command(self, cmd: str, timeout: int = 10) -> Tuple[bool, str]:
        """Run a shell command string and return success status and output"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode == 0, result.stdout.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)
    
    def check_os_info(self) -> Dict[str, str]:
        """Detect OS and distribution information"""
        info = {
            'platform': platform.system(),
            'platform_release': platform.release(),
            'platform_version': platform.version(),
            'machine': platform.machine(),
        }
        
        if self._is_linux:
            # Try to get distro info
            distro_info = self._get_linux_distro()
            info.update(distro_info)
        elif self._is_windows:
            info['distro'] = 'Windows'
            info['distro_version'] = platform.version()
        elif self._is_mac:
            info['distro'] = 'macOS'
            success, version = self._run_command(['sw_vers', '-productVersion'])
            info['distro_version'] = version if success else platform.mac_ver()[0]
        
        self.report.os_info = info
        return info
    
    def _get_linux_distro(self) -> Dict[str, str]:
        """Get Linux distribution information from /etc/os-release"""
        info = {'distro': 'Unknown', 'distro_version': '', 'distro_id': ''}
        
        os_release_path = Path('/etc/os-release')
        if os_release_path.exists():
            try:
                with open(os_release_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if '=' in line:
                            key, value = line.split('=', 1)
                            value = value.strip('"\'')
                            if key == 'NAME':
                                info['distro'] = value
                            elif key == 'VERSION_ID':
                                info['distro_version'] = value
                            elif key == 'ID':
                                info['distro_id'] = value
            except Exception:
                pass
        
        return info
    
    def check_basic_system_info(self) -> Dict[str, str]:
        """Get basic system information for display"""
        info = {
            'kernel': platform.release(),
            'architecture': platform.machine()
        }
        
        self.report.kernel_info = {'version': info['kernel']}
        self.report.cpu_arch = info['architecture']
        
        return info
    
    def check_disk_space(self, additional_paths: Optional[List[str]] = None) -> List[DiskInfo]:
        """Check disk space on critical paths"""
        paths_to_check = list(self.DISK_CHECK_PATHS)
        
        # Add current working directory
        paths_to_check.append(os.getcwd())
        
        if additional_paths:
            paths_to_check.extend(additional_paths)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_paths = []
        for p in paths_to_check:
            if p not in seen:
                seen.add(p)
                unique_paths.append(p)
        
        disk_info_list = []
        
        for path in unique_paths:
            disk_info = self._get_disk_info(path)
            disk_info_list.append(disk_info)
            
            # Check if path has enough space
            if disk_info.exists and disk_info.free_mb < self.MIN_DISK_SPACE_MB:
                self.report.warnings.append(
                    f"Low disk space on {path}: {disk_info.free_mb} MB free"
                )
        
        self.report.disk_usage = disk_info_list
        return disk_info_list
    
    def _get_disk_info(self, path: str) -> DiskInfo:
        """Get disk usage information for a specific path"""
        exists = os.path.exists(path)
        writable = os.access(path, os.W_OK) if exists else False
        
        if not exists:
            # Try to find the nearest existing parent
            check_path = Path(path)
            while not check_path.exists() and check_path.parent != check_path:
                check_path = check_path.parent
            path = str(check_path)
            exists = check_path.exists()
        
        free_mb = 0
        total_mb = 0
        filesystem = 'unknown'
        
        if exists:
            try:
                stat = shutil.disk_usage(path)
                free_mb = stat.free // (1024 * 1024)
                total_mb = stat.total // (1024 * 1024)
            except Exception:
                pass
            
            # Get filesystem type on Linux
            if self._is_linux:
                filesystem = self._get_filesystem_type(path)
        
        return DiskInfo(
            path=path,
            free_mb=free_mb,
            total_mb=total_mb,
            filesystem=filesystem,
            exists=exists,
            writable=writable
        )
    
    def _get_filesystem_type(self, path: str) -> str:
        """Get filesystem type for a path on Linux"""
        success, output = self._run_shell_command(f"df -T '{path}' | tail -1 | awk '{{print $2}}'")
        if success and output:
            return output
        return 'unknown'
    

    
    def check_package(self, name: str, version_cmd: Optional[List[str]] = None) -> PackageInfo:
        """Check if a package/binary is installed"""
        # First check if binary exists in PATH
        path = shutil.which(name)
        installed = path is not None
        version = None
        
        if installed and version_cmd:
            success, output = self._run_command(version_cmd)
            if success:
                version = output.split('\n')[0]
        
        return PackageInfo(
            name=name,
            installed=installed,
            version=version,
            path=path
        )
    
    def _get_llm_client(self):
        """Lazy initialize LLM client with fallback"""
        if self._llm_client is not None:
            return self._llm_client
        
        if not self.api_key:
            return None
        
        # Try to initialize with primary provider
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from LLM.interpreter import CommandInterpreter
            self._llm_client = CommandInterpreter(api_key=self.api_key, provider=self.provider)
            return self._llm_client
        except Exception:
            # Fallback to other provider
            try:
                fallback_provider = 'claude' if self.provider == 'openai' else 'openai'
                # Get fallback API key
                fallback_key = os.environ.get('ANTHROPIC_API_KEY' if fallback_provider == 'claude' else 'OPENAI_API_KEY')
                if fallback_key:
                    from LLM.interpreter import CommandInterpreter
                    self._llm_client = CommandInterpreter(api_key=fallback_key, provider=fallback_provider)
                    return self._llm_client
            except Exception:
                pass
        
        return None
    
    def _get_package_info_from_llm(self, software: str, os_info: Dict[str, str]) -> Dict[str, any]:
        """Query LLM for real package information including sizes"""
        client = self._get_llm_client()
        if not client:
            return {'packages': [], 'total_size_mb': 0, 'config_changes': []}
        
        try:
            # Create a specific prompt for package information
            distro_id = os_info.get('distro_id', 'ubuntu')
            
            prompt = f"""Get {software} package information for Linux {distro_id}. 

RESPOND WITH ONLY JSON - NO EXPLANATIONS OR TEXT BEFORE/AFTER:
{{
  "packages": [
    {{"name": "exact-package-name", "version": "latest", "size_mb": 25}}
  ],
  "total_size_mb": 25,
  "config_changes": ["/etc/nginx/nginx.conf"]
}}

Provide real package sizes in MB (integers only). Use standard repository package names for {distro_id}.
If unsure, estimate typical sizes. ONLY OUTPUT THE JSON OBJECT."""
            
            # Use the LLM's API directly for a simpler query
            if hasattr(client, 'client'):
                if client.provider.value == 'openai':
                    response = client.client.chat.completions.create(
                        model=client.model,
                        messages=[
                            {"role": "system", "content": "You are a Linux package expert. Provide accurate package information in JSON format only."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.1,
                        max_tokens=1000
                    )
                    content = response.choices[0].message.content.strip()
                else:  # claude
                    response = client.client.messages.create(
                        model=client.model,
                        max_tokens=1000,
                        temperature=0.1,
                        system="You are a Linux package expert. Provide accurate package information in JSON format only.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    content = response.content[0].text.strip()
                
                # Parse JSON response
                if content.startswith("```json"):
                    content = content.split("```json")[1].split("```")[0].strip()
                elif content.startswith("```"):
                    content = content.split("```")[1].split("```")[0].strip()
                
                data = json.loads(content)
                return data
        except Exception:
            # LLM response parsing failed, fall back to estimates
            pass
        
        return {'packages': [], 'total_size_mb': 0, 'config_changes': []}
    
    def check_docker(self) -> PackageInfo:
        """Check Docker installation and version"""
        pkg = self.check_package('docker', ['docker', '--version'])
        self.report.package_status.append(pkg)
        
        if not pkg.installed:
            # Try to get real package info from LLM
            if self.api_key:
                pkg_info = self._get_package_info_from_llm('docker', self.report.os_info)
                if pkg_info['packages']:
                    self.report.packages_to_install.extend(pkg_info['packages'])
                    self.report.config_changes.extend(pkg_info.get('config_changes', []))
                else:
                    # Fallback to defaults if LLM fails
                    self.report.packages_to_install.append({
                        'name': 'docker-ce',
                        'version': 'latest',
                        'size_mb': '~85 (estimate)'
                    })
                    self.report.config_changes.append('/etc/docker/daemon.json (new file)')
                    self.report.config_changes.append('/etc/group (add docker group)')
            else:
                # No API key - show estimate with disclaimer
                self.report.packages_to_install.append({
                    'name': 'docker-ce',
                    'version': 'latest',
                    'size_mb': '~85 (estimate)'
                })
                self.report.config_changes.append('/etc/docker/daemon.json (new file)')
                self.report.config_changes.append('/etc/group (add docker group)')
                self.report.warnings.append('Package sizes are estimates - provide API key for accurate sizes')
        
        return pkg
    
    def check_containerd(self) -> PackageInfo:
        """Check containerd installation"""
        pkg = self.check_package('containerd', ['containerd', '--version'])
        self.report.package_status.append(pkg)
        
        if not pkg.installed:
            # Try to get real package info from LLM
            if self.api_key:
                pkg_info = self._get_package_info_from_llm('containerd', self.report.os_info)
                if pkg_info['packages']:
                    self.report.packages_to_install.extend(pkg_info['packages'])
                else:
                    self.report.packages_to_install.append({
                        'name': 'containerd.io',
                        'version': 'latest',
                        'size_mb': '~45 (estimate)'
                    })
            else:
                self.report.packages_to_install.append({
                    'name': 'containerd.io',
                    'version': 'latest',
                    'size_mb': '~45 (estimate)'
                })
        
        return pkg
    
    def check_software(self, software_name: str) -> PackageInfo:
        """Check any software installation dynamically"""
        # Try common binary names
        pkg = self.check_package(software_name.lower(), [software_name.lower(), '--version'])
        self.report.package_status.append(pkg)
        
        if not pkg.installed:
            # Try to get real package info from LLM
            if self.api_key:
                pkg_info = self._get_package_info_from_llm(software_name, self.report.os_info)
                if pkg_info.get('packages'):
                    self.report.packages_to_install.extend(pkg_info['packages'])
                    if pkg_info.get('config_changes'):
                        self.report.config_changes.extend(pkg_info['config_changes'])
                else:
                    # LLM didn't return data, use estimate
                    self.report.packages_to_install.append({
                        'name': software_name,
                        'version': 'latest',
                        'size_mb': '~50 (estimate)'
                    })
                    self.report.warnings.append(f'Could not fetch real package size for {software_name}')
            else:
                # No API key, use estimate
                self.report.packages_to_install.append({
                    'name': software_name,
                    'version': 'latest',
                    'size_mb': '~50 (estimate)'
                })
        
        return pkg
    
    def calculate_requirements(self, software: str) -> None:
        """Calculate installation requirements based on software to install"""
        
        # Calculate total download and disk requirements
        total_download = 0
        total_disk = 0
        
        for pkg in self.report.packages_to_install:
            try:
                size_str = str(pkg.get('size_mb', '0'))
                # Remove estimate markers and parse
                size_str = size_str.replace('~', '').replace('(estimate)', '').strip()
                size = int(float(size_str))
                total_download += size
                total_disk += size * 3  # Rough estimate: downloaded + extracted + working space
            except (ValueError, AttributeError):
                pass
        
        self.report.total_download_mb = total_download
        self.report.total_disk_required_mb = total_disk
        
        # Check if we have enough disk space
        root_disk = next(
            (d for d in self.report.disk_usage if d.path == '/'),
            None
        )
        
        if root_disk and root_disk.free_mb < total_disk:
            self.report.errors.append(
                f"Insufficient disk space: {root_disk.free_mb} MB available, {total_disk} MB required"
            )
    
    def run_all_checks(self, software: str = "docker") -> PreflightReport:
        """Run all preflight checks and return complete report"""
        
        # OS and system detection
        self.check_os_info()
        self.check_basic_system_info()
        
        # Disk checks
        self.check_disk_space()
        
        # Package checks - check the requested software
        software_lower = software.lower()
        
        if 'docker' in software_lower:
            self.check_docker()
            self.check_containerd()
        else:
            # Generic software check with LLM
            self.check_software(software)
        
        # Calculate requirements
        self.calculate_requirements(software)
        
        return self.report


def format_report(report: PreflightReport, software: str) -> str:
    """Format the preflight report for display"""
    lines = []
    lines.append("\n🔍 Simulation mode: No changes will be made\n")
    
    # Check if using estimates
    using_estimates = any('estimate' in str(pkg.get('size_mb', '')) for pkg in report.packages_to_install)
    
    # System info
    lines.append("System Information:")
    lines.append(f"  OS: {report.os_info.get('distro', 'Unknown')} {report.os_info.get('distro_version', '')}")
    if report.kernel_info.get('version'):
        lines.append(f"  Kernel: {report.kernel_info.get('version')}")
    if report.cpu_arch:
        lines.append(f"  Architecture: {report.cpu_arch}")
    
    # What would be installed
    if report.packages_to_install:
        lines.append("\nWould install:")
        for pkg in report.packages_to_install:
            lines.append(f"  - {pkg['name']} {pkg.get('version', '')} ({pkg.get('size_mb', '?')} MB)")
        
        if using_estimates:
            lines.append(f"\nTotal download: ~{report.total_download_mb} MB (estimate)")
            lines.append(f"Disk space required: ~{report.total_disk_required_mb} MB (estimate)")
            lines.append("\n💡 Tip: Set OPENAI_API_KEY or ANTHROPIC_API_KEY for real-time package sizes")
        else:
            lines.append(f"\nTotal download: {report.total_download_mb} MB")
            lines.append(f"Disk space required: {report.total_disk_required_mb} MB")
    else:
        lines.append(f"\n✓ {software} is already installed")
    
    # Disk space available
    root_disk = next((d for d in report.disk_usage if d.path == '/'), None)
    if root_disk:
        status = '✓' if root_disk.free_mb > report.total_disk_required_mb else '✗'
        lines.append(f"Disk space available: {root_disk.free_mb // 1024} GB {status}")
    
    # Configuration changes
    if report.config_changes:
        lines.append("\nWould modify:")
        for change in report.config_changes:
            lines.append(f"  - {change}")
    
    # Potential issues
    if report.errors:
        lines.append("\n❌ Blocking issues:")
        for error in report.errors:
            lines.append(f"  - {error}")
    elif report.warnings:
        lines.append("\n⚠️  Warnings:")
        for warning in report.warnings[:5]:  # Show first 5 warnings
            lines.append(f"  - {warning}")
    else:
        lines.append("\nPotential issues: None detected")
    
    # Suggestions
    if report.suggestions:
        lines.append("\n💡 Suggestions:")
        for suggestion in report.suggestions[:3]:
            lines.append(f"  - {suggestion}")
    
    return '\n'.join(lines)


def export_report(report: PreflightReport, filepath: str) -> None:
    """Export preflight report to a JSON file"""
    import json
    from dataclasses import asdict
    
    # Convert dataclass to dict
    report_dict = asdict(report)

    # `asdict` already converts nested dataclasses recursively, so we can
    # directly write the result to JSON.
    with open(filepath, 'w') as f:
        json.dump(report_dict, f, indent=2)
