"""
Permission Auditor & Fixer module.
"""

from typing import Any


class PermissionAuditor:
    """Proxy class for PermissionAuditor with lazy loading."""

    def __new__(cls, *args, **kwargs):
        from .auditor_fixer import PermissionAuditor as RealPermissionAuditor

        return RealPermissionAuditor(*args, **kwargs)


class DockerPermissionHandler:
    """Proxy class for DockerPermissionHandler with lazy loading."""

    def __new__(cls, *args, **kwargs):
        from .docker_handler import DockerPermissionHandler as RealDockerPermissionHandler

        return RealDockerPermissionHandler(*args, **kwargs)


PermissionManager = PermissionAuditor
PermissionFixer = PermissionAuditor


def scan_path(path: str) -> Any:
    """
    Simplified interface to scan a path for permission issues.

    Args:
        path: Directory path to scan

    Returns:
        Scan results from PermissionAuditor.scan_directory()
    """
    auditor = PermissionAuditor()
    return auditor.scan_directory(path)


def analyze_permissions(path: str) -> dict[str, Any]:
    """
    Analyze permissions and return detailed report.

    Args:
        path: Directory path to analyze

    Returns:
        Dictionary with scan results and analysis
    """
    auditor = PermissionAuditor()
    scan = auditor.scan_directory(path)
    return {
        "path": path,
        "auditor": auditor,
        "scan": scan,
        "issues_count": len(scan.get("world_writable", [])) + len(scan.get("dangerous", [])),
    }


__all__ = [
    "PermissionAuditor",
    "DockerPermissionHandler",
    "PermissionManager",
    "PermissionFixer",
    "scan_path",
    "analyze_permissions",
]
