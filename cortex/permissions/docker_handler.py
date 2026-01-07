"""
Docker UID/GID mapping handler for Permission Auditor.
Handles container-specific permission issues and UID mapping.
"""

import grp
import os
import pwd
import re
from pathlib import Path
from typing import Optional


class DockerPermissionHandler:
    """Handle Docker-specific permission mapping and adjustments."""

    def __init__(self, verbose: bool = False, dry_run: bool = True):
        self.verbose = verbose
        self.dry_run = dry_run
        self.container_info = self._detect_container_environment()

    def _detect_container_environment(self) -> dict:
        """Detect if running in Docker/container environment."""
        info = {
            "is_container": False,
            "container_runtime": None,
            "host_uid": os.getuid(),
            "host_gid": os.getgid(),
            "uid_mapping": {},
            "gid_mapping": {},
        }

        # Check common container indicators
        try:
            # Check /proc/self/cgroup for container info
            cgroup_path = "/proc/self/cgroup"
            if os.path.exists(cgroup_path):
                with open(cgroup_path) as f:
                    content = f.read()

                    if "docker" in content.lower():
                        info["is_container"] = True
                        info["container_runtime"] = "docker"
                    elif "kubepods" in content or "containerd" in content:
                        info["is_container"] = True
                        info["container_runtime"] = "kubernetes"

            # Check /.dockerenv file (Docker specific)
            if os.path.exists("/.dockerenv"):
                info["is_container"] = True
                info["container_runtime"] = "docker"

            # Check for Podman
            if "container" in os.environ and os.environ.get("container") == "podman":
                info["is_container"] = True
                info["container_runtime"] = "podman"

        except (OSError, PermissionError) as e:
            if self.verbose:
                print(f"Container detection warning: {e}")

        # Discover UID/GID mappings
        if info["is_container"]:
            info["uid_mapping"] = self._discover_uid_mapping()
            info["gid_mapping"] = self._discover_gid_mapping()

        return info

    def _discover_uid_mapping(self) -> dict[int, str]:
        """Discover UID to username mapping in container."""
        mapping = {}

        try:
            # Common container UIDs and their typical usernames
            common_uids = {
                0: "root",
                1: "daemon",
                2: "bin",
                3: "sys",
                4: "sync",
                5: "games",
                6: "man",
                7: "lp",
                8: "mail",
                9: "news",
                10: "uucp",
                13: "proxy",
                33: "www-data",
                100: "users",
                999: "postgres",
                101: "nginx",
                102: "redis",
                103: "mysql",
                104: "mongodb",
            }

            # Add current user's UID
            current_uid = os.getuid()
            try:
                current_user = pwd.getpwuid(current_uid).pw_name
                common_uids[current_uid] = current_user
            except (KeyError, AttributeError):
                common_uids[current_uid] = f"user{current_uid}"

            # Check which UIDs actually exist in the container
            for uid, default_name in common_uids.items():
                try:
                    user_info = pwd.getpwuid(uid)
                    mapping[uid] = user_info.pw_name
                except KeyError:
                    # UID doesn't exist in this container
                    continue

        except Exception as e:
            if self.verbose:
                print(f"UID mapping discovery error: {e}")
            # Fallback to minimal mapping
            mapping = {0: "root", os.getuid(): f"user{os.getuid()}"}

        return mapping

    def _discover_gid_mapping(self) -> dict[int, str]:
        """Discover GID to groupname mapping in container."""
        mapping = {}

        try:
            # Common container GIDs
            common_gids = {
                0: "root",
                1: "daemon",
                2: "bin",
                3: "sys",
                4: "adm",
                5: "tty",
                6: "disk",
                7: "lp",
                8: "mail",
                9: "news",
                10: "uucp",
                12: "man",
                13: "proxy",
                33: "www-data",
                100: "users",
                999: "postgres",
                101: "nginx",
            }

            current_gid = os.getgid()
            try:
                group_info = grp.getgrgid(current_gid)
                common_gids[current_gid] = group_info.gr_name
            except (KeyError, AttributeError):
                common_gids[current_gid] = f"group{current_gid}"

            for gid, default_name in common_gids.items():
                try:
                    group_info = grp.getgrgid(gid)
                    mapping[gid] = group_info.gr_name
                except KeyError:
                    continue

        except Exception as e:
            if self.verbose:
                print(f"GID mapping discovery error: {e}")
            mapping = {0: "root", os.getgid(): f"group{os.getgid()}"}

        return mapping

    def adjust_issue_for_container(self, issue: dict) -> dict:
        """Adjust permission issue description for container context."""
        if not self.container_info["is_container"]:
            return issue

        adjusted_issue = issue.copy()
        path = issue.get("path", "")

        # Add container-specific context
        if "docker" in path.lower() or "/var/lib/docker" in path:
            adjusted_issue["container_context"] = {
                "type": "docker_volume",
                "suggestion": "Consider using named volumes with proper ownership",
            }

        # Adjust UID/GID in descriptions
        if "stat" in issue:
            uid = issue["stat"].get("uid")
            gid = issue["stat"].get("gid")

            if uid is not None:
                username = self.container_info["uid_mapping"].get(uid, f"UID{uid}")
                adjusted_issue["uid_info"] = f"{uid} ({username})"

            if gid is not None:
                groupname = self.container_info["gid_mapping"].get(gid, f"GID{gid}")
                adjusted_issue["gid_info"] = f"{gid} ({groupname})"

        return adjusted_issue

    def get_container_specific_fix(self, issue: dict, base_fix: dict) -> dict:
        """Get container-specific fix recommendation."""
        if not self.container_info["is_container"]:
            return base_fix

        path = issue.get("path", "")
        fix = base_fix.copy()

        # Special handling for Docker bind mounts
        if any(pattern in path for pattern in ["/var/lib/docker", "/docker/", "docker.sock"]):
            fix["container_advice"] = (
                "For Docker bind mounts, consider:\n"
                "1. Use Docker volumes instead of bind mounts\n"
                "2. Set correct UID/GID in Dockerfile with USER directive\n"
                "3. Use docker run --user flag to match host UID\n"
                "4. For existing containers, use: docker exec -u root container chown ..."
            )

        # Adjust for common container paths
        if "/var/www/" in path or "/app/" in path:
            fix["recommended"] = 0o755 if issue.get("is_directory") else 0o644
            fix["reason"] = "Web application files in container"

        return fix

    def fix_docker_bind_mount_permissions(
        self, path: str, host_uid: int = None, host_gid: int = None, dry_run: bool = True
    ) -> dict:
        """Specialized fix for Docker bind mount permission issues."""
        result = {
            "success": False,
            "actions": [],
            "warnings": [],
            "dry_run": dry_run,
        }

        try:
            path_obj = Path(path).resolve()

            if not path_obj.exists():
                result["warnings"].append(f"Path does not exist: {path}")
                return result

            # Determine target UID/GID
            target_uid = host_uid if host_uid is not None else os.getuid()
            target_gid = host_gid if host_gid is not None else os.getgid()

            # Check current ownership
            stat_info = path_obj.stat()
            current_uid = stat_info.st_uid
            current_gid = stat_info.st_gid

            result["current"] = {
                "path": str(path_obj),
                "uid": current_uid,
                "gid": current_gid,
                "username": self._uid_to_name(current_uid),
                "groupname": self._gid_to_name(current_gid),
            }

            result["target"] = {
                "uid": target_uid,
                "gid": target_gid,
                "username": self._uid_to_name(target_uid),
                "groupname": self._gid_to_name(target_gid),
            }

            # Plan actions
            actions_needed = []

            if current_uid != target_uid or current_gid != target_gid:
                actions_needed.append(
                    {
                        "type": "chown",
                        "command": f"chown {target_uid}:{target_gid} '{path_obj}'",
                        "description": f"Change ownership from {current_uid}:{current_gid} to {target_uid}:{target_gid}",
                    }
                )

            # Check permissions
            current_mode = stat_info.st_mode & 0o777
            if current_mode == 0o777 or current_mode == 0o666:
                recommended = 0o755 if path_obj.is_dir() else 0o644
                actions_needed.append(
                    {
                        "type": "chmod",
                        "command": f"chmod {oct(recommended)[2:]} '{path_obj}'",
                        "description": f"Fix dangerous permissions {oct(current_mode)} -> {oct(recommended)}",
                    }
                )

            result["actions"] = actions_needed

            # Execute if not dry-run
            if not dry_run and actions_needed:
                all_succeeded = True
                for action in actions_needed:
                    try:
                        if action["type"] == "chown":
                            os.chown(path_obj, target_uid, target_gid)
                        elif action["type"] == "chmod":
                            recommended = int(action["command"].split()[1], 8)
                            os.chmod(path_obj, recommended)

                    except (PermissionError, OSError) as e:
                        result["warnings"].append(f"Failed {action['type']}: {e}")
                        all_succeeded = False

                result["success"] = all_succeeded

            elif dry_run and actions_needed:
                result["success"] = True  # Dry-run considered successful

            else:
                result["success"] = True  # No actions needed

        except Exception as e:
            result["warnings"].append(f"Unexpected error: {e}")

        return result

    def _uid_to_name(self, uid: int) -> str:
        """Convert UID to username."""
        try:
            return pwd.getpwuid(uid).pw_name
        except (KeyError, AttributeError):
            return f"UID{uid}"

    def _gid_to_name(self, gid: int) -> str:
        """Convert GID to groupname."""
        try:
            return grp.getgrgid(gid).gr_name
        except (KeyError, AttributeError):
            return f"GID{gid}"

    def generate_docker_permission_report(self, path: str = ".") -> str:
        """Generate detailed Docker permission report."""
        report_lines = ["🐳 DOCKER PERMISSION AUDIT REPORT", "=" * 50]

        # Container info
        if self.container_info["is_container"]:
            report_lines.append(f"Container Runtime: {self.container_info['container_runtime']}")
            report_lines.append(
                f"Host UID/GID: {self.container_info['host_uid']}/{self.container_info['host_gid']}"
            )
        else:
            report_lines.append("Environment: Native (not in container)")

        report_lines.append("")

        # UID Mapping
        report_lines.append("UID Mapping:")
        for uid, name in sorted(self.container_info["uid_mapping"].items()):
            report_lines.append(f"  {uid:>6} → {name}")

        report_lines.append("")

        # GID Mapping
        report_lines.append("GID Mapping:")
        for gid, name in sorted(self.container_info["gid_mapping"].items()):
            report_lines.append(f"  {gid:>6} → {name}")

        report_lines.append("")
        report_lines.append("Common Docker Permission Issues:")
        report_lines.append("  1. Bind mounts with wrong UID/GID")
        report_lines.append("  2. Container running as root when not needed")
        report_lines.append("  3. World-writable files in volumes")
        report_lines.append("  4. /var/run/docker.sock with wrong permissions")

        return "\n".join(report_lines)


# Convenience function
def detect_docker_uid_mapping() -> dict:
    """Detect Docker UID mapping for current environment."""
    handler = DockerPermissionHandler()
    return handler.container_info


# Update auditor_fixer.py to use Docker handler
# Add this import and integration
