"""Verification and conflict detection for the Do Runner module."""

import os
import re
import subprocess
import time
from typing import Any

from rich.console import Console

from .models import CommandLog

console = Console()


class ConflictDetector:
    """Detects conflicts with existing configurations."""

    def _execute_command(
        self, cmd: str, needs_sudo: bool = False, timeout: int = 120
    ) -> tuple[bool, str, str]:
        """Execute a single command."""
        try:
            if needs_sudo and not cmd.strip().startswith("sudo"):
                cmd = f"sudo {cmd}"

            result = subprocess.run(
                ["sudo", "bash", "-c", cmd] if needs_sudo else cmd,
                shell=not needs_sudo,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", str(e)

    def check_for_conflicts(
        self,
        cmd: str,
        purpose: str,
    ) -> dict[str, Any]:
        """
        Check if the command might conflict with existing resources.

        This is a GENERAL conflict detector that works for:
        - Docker containers
        - Services (systemd)
        - Files/directories
        - Packages
        - Databases
        - Users/groups
        - Ports
        - Virtual environments
        - And more...

        Returns:
            Dict with conflict info, alternatives, and cleanup commands.
        """
        # Check all resource types
        checkers = [
            self._check_docker_conflict,
            self._check_service_conflict,
            self._check_file_conflict,
            self._check_package_conflict,
            self._check_port_conflict,
            self._check_user_conflict,
            self._check_venv_conflict,
            self._check_database_conflict,
            self._check_cron_conflict,
        ]

        for checker in checkers:
            result = checker(cmd, purpose)
            if result["has_conflict"]:
                return result

        # Default: no conflict
        return {
            "has_conflict": False,
            "conflict_type": None,
            "resource_type": None,
            "resource_name": None,
            "suggestion": None,
            "cleanup_commands": [],
            "alternative_actions": [],
        }

    def _create_conflict_result(
        self,
        resource_type: str,
        resource_name: str,
        conflict_type: str,
        suggestion: str,
        is_active: bool = True,
        alternative_actions: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Create a standardized conflict result with alternatives."""

        # Generate standard alternative actions based on resource type and state
        if alternative_actions is None:
            if is_active:
                alternative_actions = [
                    {
                        "action": "use_existing",
                        "description": f"Use existing {resource_type} '{resource_name}'",
                        "commands": [],
                    },
                    {
                        "action": "restart",
                        "description": f"Restart {resource_type} '{resource_name}'",
                        "commands": self._get_restart_commands(resource_type, resource_name),
                    },
                    {
                        "action": "recreate",
                        "description": f"Remove and recreate {resource_type} '{resource_name}'",
                        "commands": self._get_remove_commands(resource_type, resource_name),
                    },
                ]
            else:
                alternative_actions = [
                    {
                        "action": "start_existing",
                        "description": f"Start existing {resource_type} '{resource_name}'",
                        "commands": self._get_start_commands(resource_type, resource_name),
                    },
                    {
                        "action": "recreate",
                        "description": f"Remove and recreate {resource_type} '{resource_name}'",
                        "commands": self._get_remove_commands(resource_type, resource_name),
                    },
                ]

        return {
            "has_conflict": True,
            "conflict_type": conflict_type,
            "resource_type": resource_type,
            "resource_name": resource_name,
            "suggestion": suggestion,
            "is_active": is_active,
            "alternative_actions": alternative_actions,
            "cleanup_commands": [],
            "use_existing": is_active,
        }

    def _get_restart_commands(self, resource_type: str, name: str) -> list[str]:
        """Get restart commands for a resource type."""
        commands = {
            "container": [f"docker restart {name}"],
            "service": [f"sudo systemctl restart {name}"],
            "database": [f"sudo systemctl restart {name}"],
            "webserver": [f"sudo systemctl restart {name}"],
        }
        return commands.get(resource_type, [])

    def _get_start_commands(self, resource_type: str, name: str) -> list[str]:
        """Get start commands for a resource type."""
        commands = {
            "container": [f"docker start {name}"],
            "service": [f"sudo systemctl start {name}"],
            "database": [f"sudo systemctl start {name}"],
            "webserver": [f"sudo systemctl start {name}"],
        }
        return commands.get(resource_type, [])

    def _get_remove_commands(self, resource_type: str, name: str) -> list[str]:
        """Get remove/cleanup commands for a resource type."""
        commands = {
            "container": [f"docker rm -f {name}"],
            "service": [f"sudo systemctl stop {name}"],
            "file": [f"sudo rm -f {name}"],
            "directory": [f"sudo rm -rf {name}"],
            "package": [],  # Don't auto-remove packages
            "user": [],  # Don't auto-remove users
            "venv": [f"rm -rf {name}"],
            "database": [],  # Don't auto-remove databases
        }
        return commands.get(resource_type, [])

    def _check_docker_conflict(self, cmd: str, purpose: str) -> dict[str, Any]:
        """Check for Docker container/compose conflicts."""
        result = {"has_conflict": False}

        # Docker run with --name
        if "docker run" in cmd.lower():
            name_match = re.search(r"--name\s+([^\s]+)", cmd)
            if name_match:
                container_name = name_match.group(1)

                # Check if container exists
                success, container_id, _ = self._execute_command(
                    f"docker ps -aq --filter name=^{container_name}$", needs_sudo=False
                )

                if success and container_id.strip():
                    # Check if running
                    running_success, running_id, _ = self._execute_command(
                        f"docker ps -q --filter name=^{container_name}$", needs_sudo=False
                    )
                    is_running = running_success and running_id.strip()

                    # Get image info
                    _, image_info, _ = self._execute_command(
                        f"docker inspect --format '{{{{.Config.Image}}}}' {container_name}",
                        needs_sudo=False,
                    )
                    image = image_info.strip() if image_info else "unknown"

                    status = "running" if is_running else "stopped"
                    return self._create_conflict_result(
                        resource_type="container",
                        resource_name=container_name,
                        conflict_type=f"container_{status}",
                        suggestion=f"Container '{container_name}' already exists ({status}, image: {image})",
                        is_active=is_running,
                    )

        # Docker compose
        if "docker-compose" in cmd.lower() or "docker compose" in cmd.lower():
            if "up" in cmd:
                success, services, _ = self._execute_command(
                    "docker compose ps -q 2>/dev/null", needs_sudo=False
                )
                if success and services.strip():
                    return self._create_conflict_result(
                        resource_type="compose",
                        resource_name="docker-compose",
                        conflict_type="compose_running",
                        suggestion="Docker Compose services are already running",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": "Keep existing services",
                                "commands": [],
                            },
                            {
                                "action": "restart",
                                "description": "Restart services",
                                "commands": ["docker compose restart"],
                            },
                            {
                                "action": "recreate",
                                "description": "Recreate services",
                                "commands": ["docker compose down", "docker compose up -d"],
                            },
                        ],
                    )

        return result

    def _check_service_conflict(self, cmd: str, purpose: str) -> dict[str, Any]:
        """Check for systemd service conflicts."""
        result = {"has_conflict": False}

        # systemctl start/enable
        if "systemctl" in cmd:
            service_match = re.search(r"systemctl\s+(start|enable|restart)\s+([^\s]+)", cmd)
            if service_match:
                action = service_match.group(1)
                service = service_match.group(2).replace(".service", "")

                success, status, _ = self._execute_command(
                    f"systemctl is-active {service} 2>/dev/null", needs_sudo=False
                )

                if action in ["start", "enable"] and status.strip() == "active":
                    return self._create_conflict_result(
                        resource_type="service",
                        resource_name=service,
                        conflict_type="service_running",
                        suggestion=f"Service '{service}' is already running",
                        is_active=True,
                    )

        # service command
        if cmd.startswith("service ") or " service " in cmd:
            service_match = re.search(r"service\s+(\S+)\s+(start|restart)", cmd)
            if service_match:
                service = service_match.group(1)
                success, status, _ = self._execute_command(
                    f"systemctl is-active {service} 2>/dev/null", needs_sudo=False
                )
                if status.strip() == "active":
                    return self._create_conflict_result(
                        resource_type="service",
                        resource_name=service,
                        conflict_type="service_running",
                        suggestion=f"Service '{service}' is already running",
                        is_active=True,
                    )

        return result

    def _check_file_conflict(self, cmd: str, purpose: str) -> dict[str, Any]:
        """Check for file/directory conflicts."""
        result = {"has_conflict": False}
        paths_in_cmd = re.findall(r"(/[^\s>|]+)", cmd)

        for path in paths_in_cmd:
            # Skip common read paths
            if path in ["/dev/null", "/etc/os-release", "/proc/", "/sys/"]:
                continue

            # Check for file creation/modification commands
            is_write_cmd = any(
                p in cmd for p in [">", "tee ", "cp ", "mv ", "touch ", "mkdir ", "echo "]
            )

            if is_write_cmd and os.path.exists(path):
                is_dir = os.path.isdir(path)
                resource_type = "directory" if is_dir else "file"

                return self._create_conflict_result(
                    resource_type=resource_type,
                    resource_name=path,
                    conflict_type=f"{resource_type}_exists",
                    suggestion=f"{resource_type.title()} '{path}' already exists",
                    is_active=True,
                    alternative_actions=[
                        {
                            "action": "use_existing",
                            "description": f"Keep existing {resource_type}",
                            "commands": [],
                        },
                        {
                            "action": "backup",
                            "description": "Backup and overwrite",
                            "commands": [f"sudo cp -r {path} {path}.cortex.bak"],
                        },
                        {
                            "action": "recreate",
                            "description": "Remove and recreate",
                            "commands": [f"sudo rm -rf {path}" if is_dir else f"sudo rm -f {path}"],
                        },
                    ],
                )

        return result

    def _check_package_conflict(self, cmd: str, purpose: str) -> dict[str, Any]:
        """Check for package installation conflicts."""
        result = {"has_conflict": False}

        # apt install
        if "apt install" in cmd or "apt-get install" in cmd:
            pkg_match = re.search(r"(?:apt|apt-get)\s+install\s+(?:-y\s+)?(\S+)", cmd)
            if pkg_match:
                package = pkg_match.group(1)
                success, _, _ = self._execute_command(
                    f"dpkg -l {package} 2>/dev/null | grep -q '^ii'", needs_sudo=False
                )
                if success:
                    # Get version
                    _, version_out, _ = self._execute_command(
                        f"dpkg -l {package} | grep '^ii' | awk '{{print $3}}'", needs_sudo=False
                    )
                    version = version_out.strip() if version_out else "unknown"

                    return self._create_conflict_result(
                        resource_type="package",
                        resource_name=package,
                        conflict_type="package_installed",
                        suggestion=f"Package '{package}' is already installed (version: {version})",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": f"Keep current version ({version})",
                                "commands": [],
                            },
                            {
                                "action": "upgrade",
                                "description": "Upgrade to latest version",
                                "commands": [f"sudo apt install --only-upgrade -y {package}"],
                            },
                            {
                                "action": "reinstall",
                                "description": "Reinstall package",
                                "commands": [f"sudo apt install --reinstall -y {package}"],
                            },
                        ],
                    )

        # pip install
        if "pip install" in cmd or "pip3 install" in cmd:
            pkg_match = re.search(r"pip3?\s+install\s+(?:-[^\s]+\s+)*(\S+)", cmd)
            if pkg_match:
                package = pkg_match.group(1)
                success, version_out, _ = self._execute_command(
                    f"pip3 show {package} 2>/dev/null | grep Version", needs_sudo=False
                )
                if success and version_out:
                    version = version_out.replace("Version:", "").strip()
                    return self._create_conflict_result(
                        resource_type="pip_package",
                        resource_name=package,
                        conflict_type="pip_package_installed",
                        suggestion=f"Python package '{package}' is already installed (version: {version})",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": f"Keep current version ({version})",
                                "commands": [],
                            },
                            {
                                "action": "upgrade",
                                "description": "Upgrade to latest",
                                "commands": [f"pip3 install --upgrade {package}"],
                            },
                            {
                                "action": "reinstall",
                                "description": "Reinstall package",
                                "commands": [f"pip3 install --force-reinstall {package}"],
                            },
                        ],
                    )

        # npm install -g
        if "npm install -g" in cmd or "npm i -g" in cmd:
            pkg_match = re.search(r"npm\s+(?:install|i)\s+-g\s+(\S+)", cmd)
            if pkg_match:
                package = pkg_match.group(1)
                success, version_out, _ = self._execute_command(
                    f"npm list -g {package} 2>/dev/null | grep {package}", needs_sudo=False
                )
                if success and version_out:
                    return self._create_conflict_result(
                        resource_type="npm_package",
                        resource_name=package,
                        conflict_type="npm_package_installed",
                        suggestion=f"npm package '{package}' is already installed globally",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": "Keep current version",
                                "commands": [],
                            },
                            {
                                "action": "upgrade",
                                "description": "Update to latest",
                                "commands": [f"npm update -g {package}"],
                            },
                        ],
                    )

        # snap install - check if snap is available and package is installed
        if "snap install" in cmd:
            # First check if snap is available
            snap_available = self._check_tool_available("snap")
            if not snap_available:
                return self._create_conflict_result(
                    resource_type="tool",
                    resource_name="snap",
                    conflict_type="tool_not_available",
                    suggestion="Snap package manager is not installed. Installing snap first.",
                    is_active=False,
                    alternative_actions=[
                        {
                            "action": "install_first",
                            "description": "Install snapd first",
                            "commands": ["sudo apt update", "sudo apt install -y snapd"],
                        },
                        {
                            "action": "use_apt",
                            "description": "Use apt instead of snap",
                            "commands": [],
                        },
                    ],
                )

            pkg_match = re.search(r"snap\s+install\s+(\S+)", cmd)
            if pkg_match:
                package = pkg_match.group(1)
                success, version_out, _ = self._execute_command(
                    f"snap list {package} 2>/dev/null | grep {package}", needs_sudo=False
                )
                if success and version_out:
                    return self._create_conflict_result(
                        resource_type="snap_package",
                        resource_name=package,
                        conflict_type="snap_package_installed",
                        suggestion=f"Snap package '{package}' is already installed",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": "Keep current version",
                                "commands": [],
                            },
                            {
                                "action": "refresh",
                                "description": "Refresh to latest",
                                "commands": [f"sudo snap refresh {package}"],
                            },
                        ],
                    )

        # flatpak install - check if flatpak is available and package is installed
        if "flatpak install" in cmd:
            # First check if flatpak is available
            flatpak_available = self._check_tool_available("flatpak")
            if not flatpak_available:
                return self._create_conflict_result(
                    resource_type="tool",
                    resource_name="flatpak",
                    conflict_type="tool_not_available",
                    suggestion="Flatpak is not installed. Installing flatpak first.",
                    is_active=False,
                    alternative_actions=[
                        {
                            "action": "install_first",
                            "description": "Install flatpak first",
                            "commands": ["sudo apt update", "sudo apt install -y flatpak"],
                        },
                        {
                            "action": "use_apt",
                            "description": "Use apt instead of flatpak",
                            "commands": [],
                        },
                    ],
                )

            pkg_match = re.search(r"flatpak\s+install\s+(?:-y\s+)?(\S+)", cmd)
            if pkg_match:
                package = pkg_match.group(1)
                success, version_out, _ = self._execute_command(
                    f"flatpak list | grep -i {package}", needs_sudo=False
                )
                if success and version_out:
                    return self._create_conflict_result(
                        resource_type="flatpak_package",
                        resource_name=package,
                        conflict_type="flatpak_package_installed",
                        suggestion=f"Flatpak application '{package}' is already installed",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": "Keep current version",
                                "commands": [],
                            },
                            {
                                "action": "upgrade",
                                "description": "Update to latest",
                                "commands": [f"flatpak update -y {package}"],
                            },
                        ],
                    )

        return result

    def _check_tool_available(self, tool: str) -> bool:
        """Check if a command-line tool is available."""
        success, output, _ = self._execute_command(f"which {tool} 2>/dev/null", needs_sudo=False)
        return success and bool(output.strip())

    def _check_port_conflict(self, cmd: str, purpose: str) -> dict[str, Any]:
        """Check for port binding conflicts."""
        result = {"has_conflict": False}

        # Look for port mappings
        port_patterns = [
            r"-p\s+(\d+):\d+",  # docker -p 8080:80
            r"--port[=\s]+(\d+)",  # --port 8080
            r":(\d+)\s",  # :8080
            r"listen\s+(\d+)",  # nginx listen 80
        ]

        for pattern in port_patterns:
            match = re.search(pattern, cmd)
            if match:
                port = match.group(1)

                # Check if port is in use
                success, output, _ = self._execute_command(
                    f"ss -tlnp | grep ':{port} '", needs_sudo=True
                )
                if success and output:
                    # Get process using the port
                    process = "unknown"
                    proc_match = re.search(r'users:\(\("([^"]+)"', output)
                    if proc_match:
                        process = proc_match.group(1)

                    return self._create_conflict_result(
                        resource_type="port",
                        resource_name=port,
                        conflict_type="port_in_use",
                        suggestion=f"Port {port} is already in use by '{process}'",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_different",
                                "description": "Use a different port",
                                "commands": [],
                            },
                            {
                                "action": "stop_existing",
                                "description": f"Stop process using port {port}",
                                "commands": [f"sudo fuser -k {port}/tcp"],
                            },
                        ],
                    )

        return result

    def _check_user_conflict(self, cmd: str, purpose: str) -> dict[str, Any]:
        """Check for user/group creation conflicts."""
        result = {"has_conflict": False}

        # useradd / adduser
        if "useradd" in cmd or "adduser" in cmd:
            user_match = re.search(r"(?:useradd|adduser)\s+(?:[^\s]+\s+)*(\S+)$", cmd)
            if user_match:
                username = user_match.group(1)
                success, _, _ = self._execute_command(
                    f"id {username} 2>/dev/null", needs_sudo=False
                )
                if success:
                    return self._create_conflict_result(
                        resource_type="user",
                        resource_name=username,
                        conflict_type="user_exists",
                        suggestion=f"User '{username}' already exists",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": f"Use existing user '{username}'",
                                "commands": [],
                            },
                            {
                                "action": "modify",
                                "description": "Modify existing user",
                                "commands": [],
                            },
                        ],
                    )

        # groupadd / addgroup
        if "groupadd" in cmd or "addgroup" in cmd:
            group_match = re.search(r"(?:groupadd|addgroup)\s+(\S+)$", cmd)
            if group_match:
                groupname = group_match.group(1)
                success, _, _ = self._execute_command(
                    f"getent group {groupname} 2>/dev/null", needs_sudo=False
                )
                if success:
                    return self._create_conflict_result(
                        resource_type="group",
                        resource_name=groupname,
                        conflict_type="group_exists",
                        suggestion=f"Group '{groupname}' already exists",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": f"Use existing group '{groupname}'",
                                "commands": [],
                            },
                        ],
                    )

        return result

    def _check_venv_conflict(self, cmd: str, purpose: str) -> dict[str, Any]:
        """Check for virtual environment conflicts."""
        result = {"has_conflict": False}

        # python -m venv / virtualenv
        if "python" in cmd and "venv" in cmd:
            venv_match = re.search(r"(?:venv|virtualenv)\s+(\S+)", cmd)
            if venv_match:
                venv_path = venv_match.group(1)
                if os.path.exists(venv_path) and os.path.exists(
                    os.path.join(venv_path, "bin", "python")
                ):
                    return self._create_conflict_result(
                        resource_type="venv",
                        resource_name=venv_path,
                        conflict_type="venv_exists",
                        suggestion=f"Virtual environment '{venv_path}' already exists",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": "Use existing venv",
                                "commands": [],
                            },
                            {
                                "action": "recreate",
                                "description": "Delete and recreate",
                                "commands": [f"rm -rf {venv_path}"],
                            },
                        ],
                    )

        return result

    def _check_database_conflict(self, cmd: str, purpose: str) -> dict[str, Any]:
        """Check for database creation conflicts."""
        result = {"has_conflict": False}

        # MySQL/MariaDB create database
        if "mysql" in cmd.lower() and "create database" in cmd.lower():
            db_match = re.search(
                r"create\s+database\s+(?:if\s+not\s+exists\s+)?(\S+)", cmd, re.IGNORECASE
            )
            if db_match:
                dbname = db_match.group(1).strip("`\"'")
                success, output, _ = self._execute_command(
                    f"mysql -e \"SHOW DATABASES LIKE '{dbname}'\" 2>/dev/null", needs_sudo=False
                )
                if success and dbname in output:
                    return self._create_conflict_result(
                        resource_type="mysql_database",
                        resource_name=dbname,
                        conflict_type="database_exists",
                        suggestion=f"MySQL database '{dbname}' already exists",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": "Use existing database",
                                "commands": [],
                            },
                            {
                                "action": "recreate",
                                "description": "Drop and recreate",
                                "commands": [f"mysql -e 'DROP DATABASE {dbname}'"],
                            },
                        ],
                    )

        # PostgreSQL create database
        if "createdb" in cmd or ("psql" in cmd and "create database" in cmd.lower()):
            db_match = re.search(r"(?:createdb|create\s+database)\s+(\S+)", cmd, re.IGNORECASE)
            if db_match:
                dbname = db_match.group(1).strip("\"'")
                success, _, _ = self._execute_command(
                    f"psql -lqt 2>/dev/null | cut -d \\| -f 1 | grep -qw {dbname}", needs_sudo=False
                )
                if success:
                    return self._create_conflict_result(
                        resource_type="postgres_database",
                        resource_name=dbname,
                        conflict_type="database_exists",
                        suggestion=f"PostgreSQL database '{dbname}' already exists",
                        is_active=True,
                        alternative_actions=[
                            {
                                "action": "use_existing",
                                "description": "Use existing database",
                                "commands": [],
                            },
                            {
                                "action": "recreate",
                                "description": "Drop and recreate",
                                "commands": [f"dropdb {dbname}"],
                            },
                        ],
                    )

        return result

    def _check_cron_conflict(self, cmd: str, purpose: str) -> dict[str, Any]:
        """Check for cron job conflicts."""
        result = {"has_conflict": False}

        # crontab entries
        if "crontab" in cmd or "/etc/cron" in cmd:
            # Check if similar cron job exists
            if "echo" in cmd and ">>" in cmd:
                # Extract the command being added
                job_match = re.search(r"echo\s+['\"]([^'\"]+)['\"]", cmd)
                if job_match:
                    job_content = job_match.group(1)
                    # Check existing crontab
                    success, crontab, _ = self._execute_command(
                        "crontab -l 2>/dev/null", needs_sudo=False
                    )
                    if success and crontab:
                        # Check if similar job exists
                        job_cmd = job_content.split()[-1] if job_content else ""
                        if job_cmd and job_cmd in crontab:
                            return self._create_conflict_result(
                                resource_type="cron_job",
                                resource_name=job_cmd,
                                conflict_type="cron_exists",
                                suggestion=f"Similar cron job for '{job_cmd}' already exists",
                                is_active=True,
                                alternative_actions=[
                                    {
                                        "action": "use_existing",
                                        "description": "Keep existing cron job",
                                        "commands": [],
                                    },
                                    {
                                        "action": "replace",
                                        "description": "Replace existing job",
                                        "commands": [],
                                    },
                                ],
                            )

        return result


class VerificationRunner:
    """Runs verification tests after command execution."""

    def _execute_command(
        self, cmd: str, needs_sudo: bool = False, timeout: int = 120
    ) -> tuple[bool, str, str]:
        """Execute a single command."""
        try:
            if needs_sudo and not cmd.strip().startswith("sudo"):
                cmd = f"sudo {cmd}"

            result = subprocess.run(
                ["sudo", "bash", "-c", cmd] if needs_sudo else cmd,
                shell=not needs_sudo,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", str(e)

    def run_verification_tests(
        self,
        commands_executed: list[CommandLog],
        user_query: str,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """
        Run verification tests after all commands have been executed.

        Returns:
            Tuple of (all_passed, test_results)
        """
        console.print()
        console.print("[bold cyan]🧪 Running verification tests...[/bold cyan]")

        test_results = []
        services_to_check = set()
        configs_to_check = set()
        files_to_check = set()

        for cmd_log in commands_executed:
            cmd = cmd_log.command.lower()

            if "systemctl" in cmd or "service " in cmd:
                svc_match = re.search(r"(?:systemctl|service)\s+\w+\s+([^\s]+)", cmd)
                if svc_match:
                    services_to_check.add(svc_match.group(1).replace(".service", ""))

            if "nginx" in cmd:
                configs_to_check.add("nginx")
            if "apache" in cmd or "a2ensite" in cmd:
                configs_to_check.add("apache")

            paths = re.findall(r"(/[^\s>|&]+)", cmd_log.command)
            for path in paths:
                if any(x in path for x in ["/etc/", "/var/", "/opt/"]):
                    files_to_check.add(path)

        all_passed = True

        # Config tests
        if "nginx" in configs_to_check:
            console.print("[dim]   Testing nginx configuration...[/dim]")
            success, stdout, stderr = self._execute_command("nginx -t", needs_sudo=True)
            test_results.append(
                {
                    "test": "nginx -t",
                    "passed": success,
                    "output": stdout if success else stderr,
                }
            )
            if success:
                console.print("[green]   ✓ Nginx configuration is valid[/green]")
            else:
                console.print(f"[red]   ✗ Nginx config test failed: {stderr[:100]}[/red]")
                all_passed = False

        if "apache" in configs_to_check:
            console.print("[dim]   Testing Apache configuration...[/dim]")
            success, stdout, stderr = self._execute_command(
                "apache2ctl configtest", needs_sudo=True
            )
            test_results.append(
                {
                    "test": "apache2ctl configtest",
                    "passed": success,
                    "output": stdout if success else stderr,
                }
            )
            if success:
                console.print("[green]   ✓ Apache configuration is valid[/green]")
            else:
                console.print(f"[red]   ✗ Apache config test failed: {stderr[:100]}[/red]")
                all_passed = False

        # Service status tests
        for service in services_to_check:
            console.print(f"[dim]   Checking service {service}...[/dim]")
            success, stdout, stderr = self._execute_command(
                f"systemctl is-active {service}", needs_sudo=False
            )
            is_active = stdout.strip() == "active"
            test_results.append(
                {
                    "test": f"systemctl is-active {service}",
                    "passed": is_active,
                    "output": stdout,
                }
            )
            if is_active:
                console.print(f"[green]   ✓ Service {service} is running[/green]")
            else:
                console.print(f"[yellow]   ⚠ Service {service} status: {stdout.strip()}[/yellow]")

        # File existence tests
        for file_path in list(files_to_check)[:5]:
            if os.path.exists(file_path):
                success, _, _ = self._execute_command(f"test -r {file_path}", needs_sudo=True)
                test_results.append(
                    {
                        "test": f"file exists: {file_path}",
                        "passed": True,
                        "output": "File exists and is readable",
                    }
                )
            else:
                test_results.append(
                    {
                        "test": f"file exists: {file_path}",
                        "passed": False,
                        "output": "File does not exist",
                    }
                )
                console.print(f"[yellow]   ⚠ File not found: {file_path}[/yellow]")

        # Connectivity tests
        query_lower = user_query.lower()
        if any(x in query_lower for x in ["proxy", "forward", "port", "listen"]):
            port_match = re.search(r"port\s*(\d+)|:(\d+)", user_query)
            if port_match:
                port = port_match.group(1) or port_match.group(2)
                console.print(f"[dim]   Testing connectivity on port {port}...[/dim]")
                success, stdout, stderr = self._execute_command(
                    f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}/ 2>/dev/null || echo 'failed'",
                    needs_sudo=False,
                )
                if stdout.strip() not in ["failed", "000", ""]:
                    console.print(
                        f"[green]   ✓ Port {port} responding (HTTP {stdout.strip()})[/green]"
                    )
                    test_results.append(
                        {
                            "test": f"curl localhost:{port}",
                            "passed": True,
                            "output": f"HTTP {stdout.strip()}",
                        }
                    )
                else:
                    console.print(
                        f"[yellow]   ⚠ Port {port} not responding (may be expected)[/yellow]"
                    )

        # Summary
        passed = sum(1 for t in test_results if t["passed"])
        total = len(test_results)

        console.print()
        if all_passed:
            console.print(f"[bold green]✓ All tests passed ({passed}/{total})[/bold green]")
        else:
            console.print(
                f"[bold yellow]⚠ Some tests failed ({passed}/{total} passed)[/bold yellow]"
            )

        return all_passed, test_results


class FileUsefulnessAnalyzer:
    """Analyzes file content usefulness for modifications."""

    def _execute_command(
        self, cmd: str, needs_sudo: bool = False, timeout: int = 120
    ) -> tuple[bool, str, str]:
        """Execute a single command."""
        try:
            if needs_sudo and not cmd.strip().startswith("sudo"):
                cmd = f"sudo {cmd}"

            result = subprocess.run(
                ["sudo", "bash", "-c", cmd] if needs_sudo else cmd,
                shell=not needs_sudo,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", str(e)

    def check_file_exists_and_usefulness(
        self,
        cmd: str,
        purpose: str,
        user_query: str,
    ) -> dict[str, Any]:
        """Check if files the command creates already exist and analyze their usefulness."""
        result = {
            "files_checked": [],
            "existing_files": [],
            "useful_content": {},
            "recommendations": [],
            "modified_command": cmd,
        }

        file_creation_patterns = [
            (r"(?:echo|printf)\s+.*?>\s*([^\s;|&]+)", "write"),
            (r"(?:echo|printf)\s+.*?>>\s*([^\s;|&]+)", "append"),
            (r"tee\s+(?:-a\s+)?([^\s;|&]+)", "write"),
            (r"cp\s+[^\s]+\s+([^\s;|&]+)", "copy"),
            (r"touch\s+([^\s;|&]+)", "create"),
            (r"cat\s+.*?>\s*([^\s;|&]+)", "write"),
            (r"sed\s+-i[^\s]*\s+.*?\s+([^\s;|&]+)$", "modify"),
            (r"mv\s+[^\s]+\s+([^\s;|&]+)", "move"),
        ]

        target_files = []
        operation_type = None

        for pattern, op_type in file_creation_patterns:
            matches = re.findall(pattern, cmd)
            for match in matches:
                if match.startswith("/") or match.startswith("~"):
                    target_files.append(match)
                    operation_type = op_type

        result["files_checked"] = target_files

        for file_path in target_files:
            if file_path.startswith("~"):
                file_path = os.path.expanduser(file_path)

            if os.path.exists(file_path):
                result["existing_files"].append(file_path)
                console.print(f"[yellow]📁 File exists: {file_path}[/yellow]")

                success, content, _ = self._execute_command(
                    f"cat '{file_path}' 2>/dev/null", needs_sudo=True
                )

                if success and content:
                    useful_parts = self.analyze_file_usefulness(content, purpose, user_query)

                    if useful_parts["is_useful"]:
                        result["useful_content"][file_path] = useful_parts
                        console.print(
                            f"[cyan]   ✓ Contains useful content: {useful_parts['summary']}[/cyan]"
                        )

                        if useful_parts["action"] == "merge":
                            result["recommendations"].append(
                                {
                                    "file": file_path,
                                    "action": "merge",
                                    "reason": useful_parts["reason"],
                                    "keep_sections": useful_parts.get("keep_sections", []),
                                }
                            )
                        elif useful_parts["action"] == "modify":
                            result["recommendations"].append(
                                {
                                    "file": file_path,
                                    "action": "modify",
                                    "reason": useful_parts["reason"],
                                }
                            )
                    else:
                        result["recommendations"].append(
                            {
                                "file": file_path,
                                "action": "backup_and_replace",
                                "reason": "Existing content not relevant",
                            }
                        )
            elif operation_type in ["write", "copy", "create"]:
                parent_dir = os.path.dirname(file_path)
                if parent_dir and not os.path.exists(parent_dir):
                    console.print(
                        f"[yellow]📁 Parent directory doesn't exist: {parent_dir}[/yellow]"
                    )
                    result["recommendations"].append(
                        {
                            "file": file_path,
                            "action": "create_parent",
                            "reason": f"Need to create {parent_dir} first",
                        }
                    )

        return result

    def analyze_file_usefulness(
        self,
        content: str,
        purpose: str,
        user_query: str,
    ) -> dict[str, Any]:
        """Analyze if file content is useful for the current purpose."""
        result = {
            "is_useful": False,
            "summary": "",
            "action": "replace",
            "reason": "",
            "keep_sections": [],
        }

        content_lower = content.lower()
        purpose_lower = purpose.lower()
        query_lower = user_query.lower()

        # Nginx configuration
        if any(
            x in content_lower for x in ["server {", "location", "nginx", "proxy_pass", "listen"]
        ):
            result["is_useful"] = True

            has_server_block = "server {" in content_lower or "server{" in content_lower
            has_location = "location" in content_lower
            has_proxy = "proxy_pass" in content_lower
            has_ssl = "ssl" in content_lower or "443" in content

            summary_parts = []
            if has_server_block:
                summary_parts.append("server block")
            if has_location:
                summary_parts.append("location rules")
            if has_proxy:
                summary_parts.append("proxy settings")
            if has_ssl:
                summary_parts.append("SSL config")

            result["summary"] = "Has " + ", ".join(summary_parts)

            if "proxy" in query_lower or "forward" in query_lower:
                if has_proxy:
                    existing_proxy = re.search(r"proxy_pass\s+([^;]+)", content)
                    if existing_proxy:
                        result["action"] = "modify"
                        result["reason"] = f"Existing proxy to {existing_proxy.group(1).strip()}"
                else:
                    result["action"] = "merge"
                    result["reason"] = "Add proxy to existing server block"
                    result["keep_sections"] = ["server", "ssl", "location"]
            elif "ssl" in query_lower or "https" in query_lower:
                if has_ssl:
                    result["action"] = "modify"
                    result["reason"] = "SSL already configured, modify as needed"
                else:
                    result["action"] = "merge"
                    result["reason"] = "Add SSL to existing config"
            else:
                result["action"] = "merge"
                result["reason"] = "Preserve existing configuration"

        # Apache configuration
        elif any(
            x in content_lower for x in ["<virtualhost", "documentroot", "apache", "servername"]
        ):
            result["is_useful"] = True
            result["summary"] = "Apache VirtualHost config"
            result["action"] = "merge"
            result["reason"] = "Preserve existing VirtualHost settings"

        # Systemd service file
        elif any(x in content_lower for x in ["[unit]", "[service]", "[install]", "execstart"]):
            result["is_useful"] = True
            result["summary"] = "Systemd service file"
            result["action"] = "modify"
            result["reason"] = "Update existing service configuration"

        # Shell script
        elif content.strip().startswith("#!/"):
            result["is_useful"] = True
            result["summary"] = "Shell script"
            result["action"] = "backup_and_replace"
            result["reason"] = "Replace script with new version"

        # Environment/config file
        elif "=" in content and "<" not in content:
            keys = re.findall(r"^([A-Z_][A-Z0-9_]*)\s*=", content, re.MULTILINE)
            if keys:
                result["is_useful"] = True
                result["summary"] = f"Config file with {len(keys)} settings"
                result["action"] = "merge"
                result["reason"] = "Merge environment variables"
                result["keep_sections"] = keys

        # Cron job
        elif any(x in content for x in ["* *", "*/", "@reboot", "@daily", "@hourly"]):
            result["is_useful"] = True
            result["summary"] = "Cron jobs"
            result["action"] = "merge"
            result["reason"] = "Preserve existing cron jobs"

        # Generic - check for keyword overlap
        else:
            purpose_words = set(purpose_lower.split())
            content_words = set(content_lower.split())
            overlap = purpose_words & content_words

            if len(overlap) > 2:
                result["is_useful"] = True
                result["summary"] = f"Related content ({len(overlap)} keyword matches)"
                result["action"] = "backup_and_replace"
                result["reason"] = "Content partially relevant, backing up"

        return result

    def apply_file_recommendations(
        self,
        recommendations: list[dict[str, Any]],
    ) -> list[str]:
        """Apply recommendations for existing files."""
        commands_executed = []

        for rec in recommendations:
            file_path = rec["file"]
            action = rec["action"]

            if action == "backup_and_replace":
                backup_path = f"{file_path}.cortex.bak.{int(time.time())}"
                backup_cmd = f"sudo cp '{file_path}' '{backup_path}'"
                success, _, _ = self._execute_command(backup_cmd, needs_sudo=True)
                if success:
                    console.print(f"[dim]   ✓ Backed up to {backup_path}[/dim]")
                    commands_executed.append(backup_cmd)

            elif action == "create_parent":
                parent = os.path.dirname(file_path)
                mkdir_cmd = f"sudo mkdir -p '{parent}'"
                success, _, _ = self._execute_command(mkdir_cmd, needs_sudo=True)
                if success:
                    console.print(f"[dim]   ✓ Created directory {parent}[/dim]")
                    commands_executed.append(mkdir_cmd)

        return commands_executed
