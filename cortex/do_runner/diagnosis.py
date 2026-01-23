"""
Comprehensive Error Diagnosis and Auto-Fix for Cortex Do Runner.

Handles all categories of Linux system errors:
1. Command & Shell Errors
2. File & Directory Errors
3. Permission & Ownership Errors
4. Process & Execution Errors
5. Memory & Resource Errors
6. Disk & Filesystem Errors
7. Networking Errors
8. Package Manager Errors
9. User & Authentication Errors
10. Device & Hardware Errors
11. Compilation & Build Errors
12. Archive & Compression Errors
13. Shell Script Errors
14. Environment & PATH Errors
15. Miscellaneous System Errors
"""

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

console = Console()


# ============================================================================
# Error Pattern Definitions by Category
# ============================================================================


@dataclass
class ErrorPattern:
    """Defines an error pattern and its fix strategy."""

    pattern: str
    error_type: str
    category: str
    description: str
    can_auto_fix: bool = False
    fix_strategy: str = ""
    severity: str = "error"  # error, warning, critical


# Category 1: Command & Shell Errors
COMMAND_SHELL_ERRORS = [
    # Timeout errors (check first for our specific message)
    ErrorPattern(
        r"[Cc]ommand timed out after \d+ seconds",
        "command_timeout",
        "timeout",
        "Command timed out - operation took too long",
        True,
        "retry_with_longer_timeout",
    ),
    ErrorPattern(
        r"[Tt]imed out",
        "timeout",
        "timeout",
        "Operation timed out",
        True,
        "retry_with_longer_timeout",
    ),
    ErrorPattern(
        r"[Tt]imeout",
        "timeout",
        "timeout",
        "Operation timed out",
        True,
        "retry_with_longer_timeout",
    ),
    # Standard command errors
    ErrorPattern(
        r"command not found",
        "command_not_found",
        "command_shell",
        "Command not installed",
        True,
        "install_package",
    ),
    ErrorPattern(
        r"No such file or directory",
        "not_found",
        "command_shell",
        "File or directory not found",
        True,
        "create_path",
    ),
    ErrorPattern(
        r"Permission denied",
        "permission_denied",
        "command_shell",
        "Permission denied",
        True,
        "use_sudo",
    ),
    ErrorPattern(
        r"Operation not permitted",
        "operation_not_permitted",
        "command_shell",
        "Operation not permitted (may need root)",
        True,
        "use_sudo",
    ),
    ErrorPattern(
        r"Not a directory",
        "not_a_directory",
        "command_shell",
        "Expected directory but found file",
        False,
        "check_path",
    ),
    ErrorPattern(
        r"Is a directory",
        "is_a_directory",
        "command_shell",
        "Expected file but found directory",
        False,
        "check_path",
    ),
    ErrorPattern(
        r"Invalid argument",
        "invalid_argument",
        "command_shell",
        "Invalid argument passed",
        False,
        "check_args",
    ),
    ErrorPattern(
        r"Too many arguments",
        "too_many_args",
        "command_shell",
        "Too many arguments provided",
        False,
        "check_args",
    ),
    ErrorPattern(
        r"[Mm]issing operand",
        "missing_operand",
        "command_shell",
        "Required argument missing",
        False,
        "check_args",
    ),
    ErrorPattern(
        r"[Aa]mbiguous redirect",
        "ambiguous_redirect",
        "command_shell",
        "Shell redirect is ambiguous",
        False,
        "fix_redirect",
    ),
    ErrorPattern(
        r"[Bb]ad substitution",
        "bad_substitution",
        "command_shell",
        "Shell variable substitution error",
        False,
        "fix_syntax",
    ),
    ErrorPattern(
        r"[Uu]nbound variable",
        "unbound_variable",
        "command_shell",
        "Variable not set",
        True,
        "set_variable",
    ),
    ErrorPattern(
        r"[Ss]yntax error near unexpected token",
        "syntax_error_token",
        "command_shell",
        "Shell syntax error",
        False,
        "fix_syntax",
    ),
    ErrorPattern(
        r"[Uu]nexpected EOF",
        "unexpected_eof",
        "command_shell",
        "Unclosed quote or bracket",
        False,
        "fix_syntax",
    ),
    ErrorPattern(
        r"[Cc]annot execute binary file",
        "cannot_execute_binary",
        "command_shell",
        "Binary incompatible with system",
        False,
        "check_architecture",
    ),
    ErrorPattern(
        r"[Ee]xec format error",
        "exec_format_error",
        "command_shell",
        "Invalid executable format",
        False,
        "check_architecture",
    ),
    ErrorPattern(
        r"[Ii]llegal option",
        "illegal_option",
        "command_shell",
        "Unrecognized command option",
        False,
        "check_help",
    ),
    ErrorPattern(
        r"[Ii]nvalid option",
        "invalid_option",
        "command_shell",
        "Invalid command option",
        False,
        "check_help",
    ),
    ErrorPattern(
        r"[Rr]ead-only file ?system",
        "readonly_fs",
        "command_shell",
        "Filesystem is read-only",
        True,
        "remount_rw",
    ),
    ErrorPattern(
        r"[Ii]nput/output error",
        "io_error",
        "command_shell",
        "I/O error (disk issue)",
        False,
        "check_disk",
        "critical",
    ),
    ErrorPattern(
        r"[Tt]ext file busy",
        "text_file_busy",
        "command_shell",
        "File is being executed",
        True,
        "wait_retry",
    ),
    ErrorPattern(
        r"[Aa]rgument list too long",
        "arg_list_too_long",
        "command_shell",
        "Too many arguments for command",
        True,
        "use_xargs",
    ),
    ErrorPattern(
        r"[Bb]roken pipe",
        "broken_pipe",
        "command_shell",
        "Pipe closed unexpectedly",
        False,
        "check_pipe",
    ),
]

# Category 2: File & Directory Errors
FILE_DIRECTORY_ERRORS = [
    ErrorPattern(
        r"[Ff]ile exists",
        "file_exists",
        "file_directory",
        "File already exists",
        True,
        "backup_overwrite",
    ),
    ErrorPattern(
        r"[Ff]ile name too long",
        "filename_too_long",
        "file_directory",
        "Filename exceeds limit",
        False,
        "shorten_name",
    ),
    ErrorPattern(
        r"[Tt]oo many.*symbolic links",
        "symlink_loop",
        "file_directory",
        "Symbolic link loop detected",
        True,
        "fix_symlink",
    ),
    ErrorPattern(
        r"[Ss]tale file handle",
        "stale_handle",
        "file_directory",
        "NFS file handle stale",
        True,
        "remount_nfs",
    ),
    ErrorPattern(
        r"[Dd]irectory not empty",
        "dir_not_empty",
        "file_directory",
        "Directory has contents",
        True,
        "rm_recursive",
    ),
    ErrorPattern(
        r"[Cc]ross-device link",
        "cross_device_link",
        "file_directory",
        "Cannot link across filesystems",
        True,
        "copy_instead",
    ),
    ErrorPattern(
        r"[Tt]oo many open files",
        "too_many_files",
        "file_directory",
        "File descriptor limit reached",
        True,
        "increase_ulimit",
    ),
    ErrorPattern(
        r"[Qq]uota exceeded",
        "quota_exceeded",
        "file_directory",
        "Disk quota exceeded",
        False,
        "check_quota",
    ),
    ErrorPattern(
        r"[Oo]peration timed out",
        "operation_timeout",
        "file_directory",
        "Operation timed out",
        True,
        "increase_timeout",
    ),
]

# Category 3: Permission & Ownership Errors
PERMISSION_ERRORS = [
    ErrorPattern(
        r"[Aa]ccess denied", "access_denied", "permission", "Access denied", True, "use_sudo"
    ),
    ErrorPattern(
        r"[Aa]uthentication fail",
        "auth_failure",
        "permission",
        "Authentication failed",
        False,
        "check_credentials",
    ),
    ErrorPattern(
        r"[Ii]nvalid user", "invalid_user", "permission", "User does not exist", True, "create_user"
    ),
    ErrorPattern(
        r"[Ii]nvalid group",
        "invalid_group",
        "permission",
        "Group does not exist",
        True,
        "create_group",
    ),
    ErrorPattern(
        r"[Nn]ot owner", "not_owner", "permission", "Not the owner of file", True, "use_sudo"
    ),
]

# Category 4: Process & Execution Errors
PROCESS_ERRORS = [
    ErrorPattern(
        r"[Nn]o such process",
        "no_such_process",
        "process",
        "Process does not exist",
        False,
        "check_pid",
    ),
    ErrorPattern(
        r"[Pp]rocess already running",
        "already_running",
        "process",
        "Process already running",
        True,
        "kill_existing",
    ),
    ErrorPattern(
        r"[Pp]rocess terminated",
        "process_terminated",
        "process",
        "Process was terminated",
        False,
        "check_logs",
    ),
    ErrorPattern(
        r"[Kk]illed",
        "killed",
        "process",
        "Process was killed (OOM?)",
        False,
        "check_memory",
        "critical",
    ),
    ErrorPattern(
        r"[Ss]egmentation fault",
        "segfault",
        "process",
        "Memory access violation",
        False,
        "debug_crash",
        "critical",
    ),
    ErrorPattern(
        r"[Bb]us error",
        "bus_error",
        "process",
        "Bus error (memory alignment)",
        False,
        "debug_crash",
        "critical",
    ),
    ErrorPattern(
        r"[Ff]loating point exception",
        "fpe",
        "process",
        "Floating point exception",
        False,
        "debug_crash",
    ),
    ErrorPattern(
        r"[Ii]llegal instruction",
        "illegal_instruction",
        "process",
        "CPU instruction error",
        False,
        "check_architecture",
        "critical",
    ),
    ErrorPattern(
        r"[Tt]race.*trap", "trace_trap", "process", "Debugger trap", False, "check_debugger"
    ),
    ErrorPattern(
        r"[Rr]esource temporarily unavailable",
        "resource_unavailable",
        "process",
        "Resource busy",
        True,
        "wait_retry",
    ),
    ErrorPattern(
        r"[Tt]oo many processes",
        "too_many_processes",
        "process",
        "Process limit reached",
        True,
        "increase_ulimit",
    ),
    ErrorPattern(
        r"[Oo]peration canceled",
        "operation_canceled",
        "process",
        "Operation was canceled",
        False,
        "check_timeout",
    ),
]

# Category 5: Memory & Resource Errors
MEMORY_ERRORS = [
    ErrorPattern(
        r"[Oo]ut of memory", "oom", "memory", "Out of memory", True, "free_memory", "critical"
    ),
    ErrorPattern(
        r"[Cc]annot allocate memory",
        "cannot_allocate",
        "memory",
        "Memory allocation failed",
        True,
        "free_memory",
        "critical",
    ),
    ErrorPattern(
        r"[Mm]emory exhausted",
        "memory_exhausted",
        "memory",
        "Memory exhausted",
        True,
        "free_memory",
        "critical",
    ),
    ErrorPattern(
        r"[Ss]tack overflow",
        "stack_overflow",
        "memory",
        "Stack overflow",
        False,
        "increase_stack",
        "critical",
    ),
    ErrorPattern(
        r"[Dd]evice or resource busy",
        "device_busy",
        "memory",
        "Device or resource busy",
        True,
        "wait_retry",
    ),
    ErrorPattern(
        r"[Nn]o space left on device",
        "no_space",
        "memory",
        "Disk full",
        True,
        "free_disk",
        "critical",
    ),
    ErrorPattern(
        r"[Dd]isk quota exceeded",
        "disk_quota",
        "memory",
        "Disk quota exceeded",
        False,
        "check_quota",
    ),
    ErrorPattern(
        r"[Ff]ile table overflow",
        "file_table_overflow",
        "memory",
        "System file table full",
        True,
        "increase_ulimit",
        "critical",
    ),
]

# Category 6: Disk & Filesystem Errors
FILESYSTEM_ERRORS = [
    ErrorPattern(
        r"[Ww]rong fs type",
        "wrong_fs_type",
        "filesystem",
        "Wrong filesystem type",
        False,
        "check_fstype",
    ),
    ErrorPattern(
        r"[Ff]ilesystem.*corrupt",
        "fs_corrupt",
        "filesystem",
        "Filesystem corrupted",
        False,
        "fsck",
        "critical",
    ),
    ErrorPattern(
        r"[Ss]uperblock invalid",
        "superblock_invalid",
        "filesystem",
        "Superblock invalid",
        False,
        "fsck",
        "critical",
    ),
    ErrorPattern(
        r"[Mm]ount point does not exist",
        "mount_point_missing",
        "filesystem",
        "Mount point missing",
        True,
        "create_mountpoint",
    ),
    ErrorPattern(
        r"[Dd]evice is busy",
        "device_busy_mount",
        "filesystem",
        "Device busy (in use)",
        True,
        "lazy_umount",
    ),
    ErrorPattern(
        r"[Nn]ot mounted", "not_mounted", "filesystem", "Filesystem not mounted", True, "mount_fs"
    ),
    ErrorPattern(
        r"[Aa]lready mounted",
        "already_mounted",
        "filesystem",
        "Already mounted",
        False,
        "check_mount",
    ),
    ErrorPattern(
        r"[Bb]ad magic number",
        "bad_magic",
        "filesystem",
        "Bad magic number in superblock",
        False,
        "fsck",
        "critical",
    ),
    ErrorPattern(
        r"[Ss]tructure needs cleaning",
        "needs_cleaning",
        "filesystem",
        "Filesystem needs fsck",
        False,
        "fsck",
    ),
    ErrorPattern(
        r"[Jj]ournal has aborted",
        "journal_aborted",
        "filesystem",
        "Journal aborted",
        False,
        "fsck",
        "critical",
    ),
]

# Category 7: Networking Errors
NETWORK_ERRORS = [
    ErrorPattern(
        r"[Nn]etwork is unreachable",
        "network_unreachable",
        "network",
        "Network unreachable",
        True,
        "check_network",
    ),
    ErrorPattern(
        r"[Nn]o route to host", "no_route", "network", "No route to host", True, "check_routing"
    ),
    ErrorPattern(
        r"[Cc]onnection refused",
        "connection_refused",
        "network",
        "Connection refused",
        True,
        "check_service",
    ),
    ErrorPattern(
        r"[Cc]onnection timed out",
        "connection_timeout",
        "network",
        "Connection timed out",
        True,
        "check_firewall",
    ),
    ErrorPattern(
        r"[Cc]onnection reset by peer",
        "connection_reset",
        "network",
        "Connection reset",
        False,
        "check_remote",
    ),
    ErrorPattern(
        r"[Hh]ost is down", "host_down", "network", "Remote host down", False, "check_host"
    ),
    ErrorPattern(
        r"[Tt]emporary failure in name resolution",
        "dns_temp_fail",
        "network",
        "DNS temporary failure",
        True,
        "retry_dns",
    ),
    ErrorPattern(
        r"[Nn]ame or service not known",
        "dns_unknown",
        "network",
        "DNS lookup failed",
        True,
        "check_dns",
    ),
    ErrorPattern(
        r"[Dd]NS lookup failed", "dns_failed", "network", "DNS lookup failed", True, "check_dns"
    ),
    ErrorPattern(
        r"[Aa]ddress already in use",
        "address_in_use",
        "network",
        "Port already in use",
        True,
        "find_port_user",
    ),
    ErrorPattern(
        r"[Cc]annot assign requested address",
        "cannot_assign_addr",
        "network",
        "Address not available",
        False,
        "check_interface",
    ),
    ErrorPattern(
        r"[Pp]rotocol not supported",
        "protocol_not_supported",
        "network",
        "Protocol not supported",
        False,
        "check_protocol",
    ),
    ErrorPattern(
        r"[Ss]ocket operation on non-socket",
        "not_socket",
        "network",
        "Invalid socket operation",
        False,
        "check_fd",
    ),
]

# Category 8: Package Manager Errors (Ubuntu/Debian apt)
PACKAGE_ERRORS = [
    ErrorPattern(
        r"[Uu]nable to locate package",
        "package_not_found",
        "package",
        "Package not found",
        True,
        "update_repos",
    ),
    ErrorPattern(
        r"[Pp]ackage.*not found",
        "package_not_found",
        "package",
        "Package not found",
        True,
        "update_repos",
    ),
    ErrorPattern(
        r"[Ff]ailed to fetch",
        "fetch_failed",
        "package",
        "Failed to download package",
        True,
        "change_mirror",
    ),
    ErrorPattern(
        r"[Hh]ash [Ss]um mismatch",
        "hash_mismatch",
        "package",
        "Package checksum mismatch",
        True,
        "clean_apt",
    ),
    ErrorPattern(
        r"[Rr]epository.*not signed",
        "repo_not_signed",
        "package",
        "Repository not signed",
        True,
        "add_key",
    ),
    ErrorPattern(
        r"[Gg][Pp][Gg] error", "gpg_error", "package", "GPG signature error", True, "fix_gpg"
    ),
    ErrorPattern(
        r"[Dd]ependency problems",
        "dependency_problems",
        "package",
        "Dependency issues",
        True,
        "fix_dependencies",
    ),
    ErrorPattern(
        r"[Uu]nmet dependencies",
        "unmet_dependencies",
        "package",
        "Unmet dependencies",
        True,
        "fix_dependencies",
    ),
    ErrorPattern(
        r"[Bb]roken packages", "broken_packages", "package", "Broken packages", True, "fix_broken"
    ),
    ErrorPattern(
        r"[Vv]ery bad inconsistent state",
        "inconsistent_state",
        "package",
        "Package in bad state",
        True,
        "force_reinstall",
    ),
    ErrorPattern(
        r"[Cc]onflicts with",
        "package_conflict",
        "package",
        "Package conflict",
        True,
        "resolve_conflict",
    ),
    ErrorPattern(
        r"dpkg.*lock", "dpkg_lock", "package", "Package manager locked", True, "clear_lock"
    ),
    ErrorPattern(r"apt.*lock", "apt_lock", "package", "APT locked", True, "clear_lock"),
    ErrorPattern(
        r"E: Could not get lock",
        "could_not_get_lock",
        "package",
        "Package manager locked",
        True,
        "clear_lock",
    ),
]

# Category 9: User & Authentication Errors
USER_AUTH_ERRORS = [
    ErrorPattern(
        r"[Uu]ser does not exist",
        "user_not_exist",
        "user_auth",
        "User does not exist",
        True,
        "create_user",
    ),
    ErrorPattern(
        r"[Gg]roup does not exist",
        "group_not_exist",
        "user_auth",
        "Group does not exist",
        True,
        "create_group",
    ),
    ErrorPattern(
        r"[Aa]ccount expired",
        "account_expired",
        "user_auth",
        "Account expired",
        False,
        "renew_account",
    ),
    ErrorPattern(
        r"[Pp]assword expired",
        "password_expired",
        "user_auth",
        "Password expired",
        False,
        "change_password",
    ),
    ErrorPattern(
        r"[Ii]ncorrect password",
        "wrong_password",
        "user_auth",
        "Wrong password",
        False,
        "check_password",
    ),
    ErrorPattern(
        r"[Aa]ccount locked",
        "account_locked",
        "user_auth",
        "Account locked",
        False,
        "unlock_account",
    ),
]

# Category 16: Docker/Container Errors
DOCKER_ERRORS = [
    # Container name conflicts
    ErrorPattern(
        r"[Cc]onflict.*container name.*already in use",
        "container_name_conflict",
        "docker",
        "Container name already in use",
        True,
        "remove_or_rename_container",
    ),
    ErrorPattern(
        r"is already in use by container",
        "container_name_conflict",
        "docker",
        "Container name already in use",
        True,
        "remove_or_rename_container",
    ),
    # Container not found
    ErrorPattern(
        r"[Nn]o such container",
        "container_not_found",
        "docker",
        "Container does not exist",
        True,
        "check_container_name",
    ),
    ErrorPattern(
        r"[Ee]rror: No such container",
        "container_not_found",
        "docker",
        "Container does not exist",
        True,
        "check_container_name",
    ),
    # Image not found
    ErrorPattern(
        r"[Uu]nable to find image",
        "image_not_found",
        "docker",
        "Docker image not found locally",
        True,
        "pull_image",
    ),
    ErrorPattern(
        r"[Rr]epository.*not found",
        "image_not_found",
        "docker",
        "Docker image repository not found",
        True,
        "check_image_name",
    ),
    ErrorPattern(
        r"manifest.*not found",
        "manifest_not_found",
        "docker",
        "Image manifest not found",
        True,
        "check_image_tag",
    ),
    # Container already running/stopped
    ErrorPattern(
        r"is already running",
        "container_already_running",
        "docker",
        "Container is already running",
        True,
        "stop_or_use_existing",
    ),
    ErrorPattern(
        r"is not running",
        "container_not_running",
        "docker",
        "Container is not running",
        True,
        "start_container",
    ),
    # Port conflicts
    ErrorPattern(
        r"[Pp]ort.*already allocated",
        "port_in_use",
        "docker",
        "Port is already in use",
        True,
        "free_port_or_use_different",
    ),
    ErrorPattern(
        r"[Bb]ind.*address already in use",
        "port_in_use",
        "docker",
        "Port is already in use",
        True,
        "free_port_or_use_different",
    ),
    # Volume errors
    ErrorPattern(
        r"[Vv]olume.*not found",
        "volume_not_found",
        "docker",
        "Docker volume not found",
        True,
        "create_volume",
    ),
    ErrorPattern(
        r"[Mm]ount.*denied",
        "mount_denied",
        "docker",
        "Mount point access denied",
        True,
        "check_mount_permissions",
    ),
    # Network errors
    ErrorPattern(
        r"[Nn]etwork.*not found",
        "network_not_found",
        "docker",
        "Docker network not found",
        True,
        "create_network",
    ),
    # Daemon errors
    ErrorPattern(
        r"[Cc]annot connect to the Docker daemon",
        "docker_daemon_not_running",
        "docker",
        "Docker daemon is not running",
        True,
        "start_docker_daemon",
    ),
    ErrorPattern(
        r"[Ii]s the docker daemon running",
        "docker_daemon_not_running",
        "docker",
        "Docker daemon is not running",
        True,
        "start_docker_daemon",
    ),
    # OOM errors
    ErrorPattern(
        r"[Oo]ut of memory",
        "container_oom",
        "docker",
        "Container ran out of memory",
        True,
        "increase_memory_limit",
    ),
    # Exec errors
    ErrorPattern(
        r"[Oo]CI runtime.*not found",
        "runtime_not_found",
        "docker",
        "Container runtime not found",
        False,
        "check_docker_installation",
    ),
]

# Category 17: Login/Credential Required Errors
LOGIN_REQUIRED_ERRORS = [
    # Docker/Container registry login errors
    ErrorPattern(
        r"[Uu]sername.*[Rr]equired",
        "docker_username_required",
        "login_required",
        "Docker username required",
        True,
        "prompt_docker_login",
    ),
    ErrorPattern(
        r"[Nn]on-null [Uu]sername",
        "docker_username_required",
        "login_required",
        "Docker username required",
        True,
        "prompt_docker_login",
    ),
    ErrorPattern(
        r"unauthorized.*authentication required",
        "docker_auth_required",
        "login_required",
        "Docker authentication required",
        True,
        "prompt_docker_login",
    ),
    ErrorPattern(
        r"denied.*requested access",
        "docker_access_denied",
        "login_required",
        "Docker registry access denied",
        True,
        "prompt_docker_login",
    ),
    ErrorPattern(
        r"denied:.*access",
        "docker_access_denied",
        "login_required",
        "Docker registry access denied",
        True,
        "prompt_docker_login",
    ),
    ErrorPattern(
        r"access.*denied",
        "docker_access_denied",
        "login_required",
        "Docker registry access denied",
        True,
        "prompt_docker_login",
    ),
    ErrorPattern(
        r"no basic auth credentials",
        "docker_no_credentials",
        "login_required",
        "Docker credentials not found",
        True,
        "prompt_docker_login",
    ),
    ErrorPattern(
        r"docker login",
        "docker_login_needed",
        "login_required",
        "Docker login required",
        True,
        "prompt_docker_login",
    ),
    # ghcr.io (GitHub Container Registry) specific errors
    ErrorPattern(
        r"ghcr\.io.*denied",
        "ghcr_access_denied",
        "login_required",
        "GitHub Container Registry access denied - login required",
        True,
        "prompt_docker_login",
    ),
    ErrorPattern(
        r"Head.*ghcr\.io.*denied",
        "ghcr_access_denied",
        "login_required",
        "GitHub Container Registry access denied - login required",
        True,
        "prompt_docker_login",
    ),
    # Generic registry denied patterns
    ErrorPattern(
        r"Error response from daemon.*denied",
        "registry_access_denied",
        "login_required",
        "Container registry access denied - login may be required",
        True,
        "prompt_docker_login",
    ),
    ErrorPattern(
        r"pull access denied",
        "pull_access_denied",
        "login_required",
        "Pull access denied - login required or image doesn't exist",
        True,
        "prompt_docker_login",
    ),
    ErrorPattern(
        r"requested resource.*denied",
        "resource_access_denied",
        "login_required",
        "Resource access denied - authentication required",
        True,
        "prompt_docker_login",
    ),
    # Git credential errors
    ErrorPattern(
        r"[Cc]ould not read.*[Uu]sername",
        "git_username_required",
        "login_required",
        "Git username required",
        True,
        "prompt_git_login",
    ),
    ErrorPattern(
        r"[Ff]atal:.*[Aa]uthentication failed",
        "git_auth_failed",
        "login_required",
        "Git authentication failed",
        True,
        "prompt_git_login",
    ),
    ErrorPattern(
        r"[Pp]assword.*authentication.*removed",
        "git_token_required",
        "login_required",
        "Git token required (password auth disabled)",
        True,
        "prompt_git_token",
    ),
    ErrorPattern(
        r"[Pp]ermission denied.*publickey",
        "git_ssh_required",
        "login_required",
        "Git SSH key required",
        True,
        "setup_git_ssh",
    ),
    # npm login errors
    ErrorPattern(
        r"npm ERR!.*E401",
        "npm_auth_required",
        "login_required",
        "npm authentication required",
        True,
        "prompt_npm_login",
    ),
    ErrorPattern(
        r"npm ERR!.*ENEEDAUTH",
        "npm_need_auth",
        "login_required",
        "npm authentication needed",
        True,
        "prompt_npm_login",
    ),
    ErrorPattern(
        r"You must be logged in",
        "npm_login_required",
        "login_required",
        "npm login required",
        True,
        "prompt_npm_login",
    ),
    # AWS credential errors
    ErrorPattern(
        r"[Uu]nable to locate credentials",
        "aws_no_credentials",
        "login_required",
        "AWS credentials not configured",
        True,
        "prompt_aws_configure",
    ),
    ErrorPattern(
        r"[Ii]nvalid[Aa]ccess[Kk]ey",
        "aws_invalid_key",
        "login_required",
        "AWS access key invalid",
        True,
        "prompt_aws_configure",
    ),
    ErrorPattern(
        r"[Ss]ignature.*[Dd]oes[Nn]ot[Mm]atch",
        "aws_secret_invalid",
        "login_required",
        "AWS secret key invalid",
        True,
        "prompt_aws_configure",
    ),
    ErrorPattern(
        r"[Ee]xpired[Tt]oken",
        "aws_token_expired",
        "login_required",
        "AWS token expired",
        True,
        "prompt_aws_configure",
    ),
    # PyPI/pip login errors
    ErrorPattern(
        r"HTTPError: 403.*upload",
        "pypi_auth_required",
        "login_required",
        "PyPI authentication required",
        True,
        "prompt_pypi_login",
    ),
    # Generic credential prompts
    ErrorPattern(
        r"[Ee]nter.*[Uu]sername",
        "username_prompt",
        "login_required",
        "Username required",
        True,
        "prompt_credentials",
    ),
    ErrorPattern(
        r"[Ee]nter.*[Pp]assword",
        "password_prompt",
        "login_required",
        "Password required",
        True,
        "prompt_credentials",
    ),
    ErrorPattern(
        r"[Aa]ccess [Tt]oken.*[Rr]equired",
        "token_required",
        "login_required",
        "Access token required",
        True,
        "prompt_token",
    ),
    ErrorPattern(
        r"[Aa][Pp][Ii].*[Kk]ey.*[Rr]equired",
        "api_key_required",
        "login_required",
        "API key required",
        True,
        "prompt_api_key",
    ),
]

# Category 10: Device & Hardware Errors
DEVICE_ERRORS = [
    ErrorPattern(
        r"[Nn]o such device", "no_device", "device", "Device not found", False, "check_device"
    ),
    ErrorPattern(
        r"[Dd]evice not configured",
        "device_not_configured",
        "device",
        "Device not configured",
        False,
        "configure_device",
    ),
    ErrorPattern(
        r"[Hh]ardware error",
        "hardware_error",
        "device",
        "Hardware error",
        False,
        "check_hardware",
        "critical",
    ),
    ErrorPattern(
        r"[Dd]evice offline", "device_offline", "device", "Device offline", False, "bring_online"
    ),
    ErrorPattern(
        r"[Mm]edia not present", "no_media", "device", "No media in device", False, "insert_media"
    ),
    ErrorPattern(
        r"[Rr]ead error",
        "read_error",
        "device",
        "Device read error",
        False,
        "check_disk",
        "critical",
    ),
    ErrorPattern(
        r"[Ww]rite error",
        "write_error",
        "device",
        "Device write error",
        False,
        "check_disk",
        "critical",
    ),
]

# Category 11: Compilation & Build Errors
BUILD_ERRORS = [
    ErrorPattern(
        r"[Nn]o rule to make target",
        "no_make_rule",
        "build",
        "Make target not found",
        False,
        "check_makefile",
    ),
    ErrorPattern(
        r"[Mm]issing separator",
        "missing_separator",
        "build",
        "Makefile syntax error",
        False,
        "fix_makefile",
    ),
    ErrorPattern(
        r"[Uu]ndefined reference",
        "undefined_reference",
        "build",
        "Undefined symbol",
        True,
        "add_library",
    ),
    ErrorPattern(
        r"[Ss]ymbol lookup error", "symbol_lookup", "build", "Symbol not found", True, "fix_ldpath"
    ),
    ErrorPattern(
        r"[Ll]ibrary not found",
        "library_not_found",
        "build",
        "Library not found",
        True,
        "install_lib",
    ),
    ErrorPattern(
        r"[Hh]eader.*not found",
        "header_not_found",
        "build",
        "Header file not found",
        True,
        "install_dev",
    ),
    ErrorPattern(
        r"[Rr]elocation error", "relocation_error", "build", "Relocation error", True, "fix_ldpath"
    ),
    ErrorPattern(
        r"[Cc]ompilation terminated",
        "compilation_failed",
        "build",
        "Compilation failed",
        False,
        "check_errors",
    ),
]

# Category 12: Archive & Compression Errors
ARCHIVE_ERRORS = [
    ErrorPattern(
        r"[Uu]nexpected end of file",
        "unexpected_eof_archive",
        "archive",
        "Archive truncated",
        False,
        "redownload",
    ),
    ErrorPattern(
        r"[Cc]orrupt archive",
        "corrupt_archive",
        "archive",
        "Archive corrupted",
        False,
        "redownload",
    ),
    ErrorPattern(
        r"[Ii]nvalid tar magic",
        "invalid_tar",
        "archive",
        "Invalid tar archive",
        False,
        "check_format",
    ),
    ErrorPattern(
        r"[Cc]hecksum error", "checksum_error", "archive", "Checksum mismatch", False, "redownload"
    ),
    ErrorPattern(
        r"[Nn]ot in gzip format", "not_gzip", "archive", "Not gzip format", False, "check_format"
    ),
    ErrorPattern(
        r"[Dd]ecompression failed",
        "decompress_failed",
        "archive",
        "Decompression failed",
        False,
        "check_format",
    ),
]

# Category 13: Shell Script Errors
SCRIPT_ERRORS = [
    ErrorPattern(
        r"[Bb]ad interpreter",
        "bad_interpreter",
        "script",
        "Interpreter not found",
        True,
        "fix_shebang",
    ),
    ErrorPattern(
        r"[Ll]ine \d+:.*command not found",
        "script_cmd_not_found",
        "script",
        "Command in script not found",
        True,
        "install_dependency",
    ),
    ErrorPattern(
        r"[Ii]nteger expression expected",
        "integer_expected",
        "script",
        "Expected integer",
        False,
        "fix_syntax",
    ),
    ErrorPattern(
        r"[Cc]onditional binary operator expected",
        "conditional_expected",
        "script",
        "Expected conditional",
        False,
        "fix_syntax",
    ),
]

# Category 14: Environment & PATH Errors
ENVIRONMENT_ERRORS = [
    ErrorPattern(
        r"[Vv]ariable not set",
        "var_not_set",
        "environment",
        "Environment variable not set",
        True,
        "set_variable",
    ),
    ErrorPattern(
        r"[Pp][Aa][Tt][Hh] not set",
        "path_not_set",
        "environment",
        "PATH not configured",
        True,
        "set_path",
    ),
    ErrorPattern(
        r"[Ee]nvironment corrupt",
        "env_corrupt",
        "environment",
        "Environment corrupted",
        True,
        "reset_env",
    ),
    ErrorPattern(
        r"[Ll]ibrary path not found",
        "lib_path_missing",
        "environment",
        "Library path missing",
        True,
        "set_ldpath",
    ),
    ErrorPattern(
        r"LD_LIBRARY_PATH", "ld_path_issue", "environment", "Library path issue", True, "set_ldpath"
    ),
]

# Category 15: Service & System Errors
# Category 16: Config File Errors (Nginx, Apache, etc.)
CONFIG_ERRORS = [
    # Nginx errors
    ErrorPattern(
        r"nginx:.*\[emerg\]",
        "nginx_config_error",
        "config",
        "Nginx configuration error",
        True,
        "fix_nginx_config",
    ),
    ErrorPattern(
        r"nginx.*syntax.*error",
        "nginx_syntax_error",
        "config",
        "Nginx syntax error",
        True,
        "fix_nginx_config",
    ),
    ErrorPattern(
        r"nginx.*unexpected",
        "nginx_unexpected",
        "config",
        "Nginx unexpected token",
        True,
        "fix_nginx_config",
    ),
    ErrorPattern(
        r"nginx.*unknown directive",
        "nginx_unknown_directive",
        "config",
        "Nginx unknown directive",
        True,
        "fix_nginx_config",
    ),
    ErrorPattern(
        r"nginx.*test failed",
        "nginx_test_failed",
        "config",
        "Nginx config test failed",
        True,
        "fix_nginx_config",
    ),
    ErrorPattern(
        r"nginx.*could not open",
        "nginx_file_error",
        "config",
        "Nginx could not open file",
        True,
        "fix_nginx_permissions",
    ),
    # Apache errors
    ErrorPattern(
        r"apache.*syntax error",
        "apache_syntax_error",
        "config",
        "Apache syntax error",
        True,
        "fix_apache_config",
    ),
    ErrorPattern(
        r"apache2?ctl.*configtest",
        "apache_config_error",
        "config",
        "Apache config test failed",
        True,
        "fix_apache_config",
    ),
    ErrorPattern(
        r"[Ss]yntax error on line \d+",
        "config_line_error",
        "config",
        "Config syntax error at line",
        True,
        "fix_config_line",
    ),
    # MySQL/MariaDB errors
    ErrorPattern(
        r"mysql.*error.*config",
        "mysql_config_error",
        "config",
        "MySQL configuration error",
        True,
        "fix_mysql_config",
    ),
    # PostgreSQL errors
    ErrorPattern(
        r"postgres.*error.*config",
        "postgres_config_error",
        "config",
        "PostgreSQL configuration error",
        True,
        "fix_postgres_config",
    ),
    # Generic config errors
    ErrorPattern(
        r"configuration.*syntax",
        "generic_config_syntax",
        "config",
        "Configuration syntax error",
        True,
        "fix_config_syntax",
    ),
    ErrorPattern(
        r"invalid.*configuration",
        "invalid_config",
        "config",
        "Invalid configuration",
        True,
        "fix_config_syntax",
    ),
    ErrorPattern(
        r"[Cc]onfig.*parse error",
        "config_parse_error",
        "config",
        "Config parse error",
        True,
        "fix_config_syntax",
    ),
]

SERVICE_ERRORS = [
    ErrorPattern(
        r"[Ss]ervice failed to start",
        "service_failed",
        "service",
        "Service failed to start",
        True,
        "check_service_logs",
    ),
    ErrorPattern(
        r"[Uu]nit.*failed",
        "unit_failed",
        "service",
        "Systemd unit failed",
        True,
        "check_service_logs",
    ),
    ErrorPattern(
        r"[Jj]ob for.*\.service failed",
        "job_failed",
        "service",
        "Service job failed",
        True,
        "check_service_logs",
    ),
    ErrorPattern(
        r"[Ff]ailed to start.*\.service",
        "start_failed",
        "service",
        "Failed to start service",
        True,
        "check_service_logs",
    ),
    ErrorPattern(
        r"[Dd]ependency failed",
        "dependency_failed",
        "service",
        "Service dependency failed",
        True,
        "start_dependency",
    ),
    ErrorPattern(
        r"[Ii]nactive.*dead",
        "service_inactive",
        "service",
        "Service not running",
        True,
        "start_service",
    ),
    ErrorPattern(
        r"[Mm]asked", "service_masked", "service", "Service is masked", True, "unmask_service"
    ),
    ErrorPattern(
        r"[Ee]nabled-runtime",
        "service_enabled_runtime",
        "service",
        "Service enabled at runtime",
        False,
        "check_service",
    ),
    ErrorPattern(
        r"[Cc]ontrol process exited with error",
        "control_process_error",
        "service",
        "Service control process failed",
        True,
        "check_service_logs",
    ),
    ErrorPattern(
        r"[Aa]ctivation.*timed out",
        "activation_timeout",
        "service",
        "Service activation timed out",
        True,
        "check_service_logs",
    ),
]

# Combine all error patterns
ALL_ERROR_PATTERNS = (
    DOCKER_ERRORS  # Check Docker errors first (common)
    + LOGIN_REQUIRED_ERRORS  # Check login errors (interactive)
    + CONFIG_ERRORS  # Check config errors (more specific)
    + COMMAND_SHELL_ERRORS
    + FILE_DIRECTORY_ERRORS
    + PERMISSION_ERRORS
    + PROCESS_ERRORS
    + MEMORY_ERRORS
    + FILESYSTEM_ERRORS
    + NETWORK_ERRORS
    + PACKAGE_ERRORS
    + USER_AUTH_ERRORS
    + DEVICE_ERRORS
    + BUILD_ERRORS
    + ARCHIVE_ERRORS
    + SCRIPT_ERRORS
    + ENVIRONMENT_ERRORS
    + SERVICE_ERRORS
)


# ============================================================================
# Login/Credential Requirements Configuration
# ============================================================================


@dataclass
class LoginRequirement:
    """Defines credentials required for a service login."""

    service: str
    display_name: str
    command_pattern: str  # Regex to match commands that need this login
    required_fields: list  # List of field names needed
    field_prompts: dict  # Field name -> prompt text
    field_secret: dict  # Field name -> whether to hide input
    login_command_template: str  # Template for login command
    env_vars: dict = field(default_factory=dict)  # Optional env var alternatives
    signup_url: str = ""
    docs_url: str = ""


# Login requirements for various services
LOGIN_REQUIREMENTS = {
    "docker": LoginRequirement(
        service="docker",
        display_name="Docker Registry",
        command_pattern=r"docker\s+(login|push|pull)",
        required_fields=["registry", "username", "password"],
        field_prompts={
            "registry": "Registry URL (press Enter for Docker Hub)",
            "username": "Username",
            "password": "Password or Access Token",
        },
        field_secret={"registry": False, "username": False, "password": True},
        login_command_template="docker login {registry} -u {username} -p {password}",
        env_vars={"username": "DOCKER_USERNAME", "password": "DOCKER_PASSWORD"},
        signup_url="https://hub.docker.com/signup",
        docs_url="https://docs.docker.com/docker-hub/access-tokens/",
    ),
    "ghcr": LoginRequirement(
        service="ghcr",
        display_name="GitHub Container Registry",
        command_pattern=r"docker.*ghcr\.io",
        required_fields=["username", "token"],
        field_prompts={
            "username": "GitHub Username",
            "token": "GitHub Personal Access Token (with packages scope)",
        },
        field_secret={"username": False, "token": True},
        login_command_template="echo {token} | docker login ghcr.io -u {username} --password-stdin",
        env_vars={"token": "GITHUB_TOKEN", "username": "GITHUB_USER"},
        signup_url="https://github.com/join",
        docs_url="https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry",
    ),
    "git_https": LoginRequirement(
        service="git_https",
        display_name="Git (HTTPS)",
        command_pattern=r"git\s+(clone|push|pull|fetch).*https://",
        required_fields=["username", "token"],
        field_prompts={
            "username": "Git Username",
            "token": "Personal Access Token",
        },
        field_secret={"username": False, "token": True},
        login_command_template="git config --global credential.helper store && echo 'https://{username}:{token}@github.com' >> ~/.git-credentials",
        env_vars={"token": "GIT_TOKEN", "username": "GIT_USER"},
        docs_url="https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token",
    ),
    "npm": LoginRequirement(
        service="npm",
        display_name="npm Registry",
        command_pattern=r"npm\s+(login|publish|adduser)",
        required_fields=["username", "password", "email"],
        field_prompts={
            "username": "npm Username",
            "password": "npm Password",
            "email": "Email Address",
        },
        field_secret={"username": False, "password": True, "email": False},
        login_command_template="npm login",  # npm login is interactive
        signup_url="https://www.npmjs.com/signup",
        docs_url="https://docs.npmjs.com/creating-and-viewing-access-tokens",
    ),
    "aws": LoginRequirement(
        service="aws",
        display_name="AWS",
        command_pattern=r"aws\s+",
        required_fields=["access_key_id", "secret_access_key", "region"],
        field_prompts={
            "access_key_id": "AWS Access Key ID",
            "secret_access_key": "AWS Secret Access Key",
            "region": "Default Region (e.g., us-east-1)",
        },
        field_secret={"access_key_id": False, "secret_access_key": True, "region": False},
        login_command_template="aws configure set aws_access_key_id {access_key_id} && aws configure set aws_secret_access_key {secret_access_key} && aws configure set region {region}",
        env_vars={
            "access_key_id": "AWS_ACCESS_KEY_ID",
            "secret_access_key": "AWS_SECRET_ACCESS_KEY",
            "region": "AWS_DEFAULT_REGION",
        },
        docs_url="https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html",
    ),
    "pypi": LoginRequirement(
        service="pypi",
        display_name="PyPI",
        command_pattern=r"(twine|pip).*upload",
        required_fields=["username", "token"],
        field_prompts={
            "username": "PyPI Username (use __token__ for API token)",
            "token": "PyPI Password or API Token",
        },
        field_secret={"username": False, "token": True},
        login_command_template="",  # Uses ~/.pypirc
        signup_url="https://pypi.org/account/register/",
        docs_url="https://pypi.org/help/#apitoken",
    ),
    "gcloud": LoginRequirement(
        service="gcloud",
        display_name="Google Cloud",
        command_pattern=r"gcloud\s+",
        required_fields=[],  # Interactive browser auth
        field_prompts={},
        field_secret={},
        login_command_template="gcloud auth login",
        docs_url="https://cloud.google.com/sdk/docs/authorizing",
    ),
    "kubectl": LoginRequirement(
        service="kubectl",
        display_name="Kubernetes",
        command_pattern=r"kubectl\s+",
        required_fields=["kubeconfig"],
        field_prompts={
            "kubeconfig": "Path to kubeconfig file (or press Enter for ~/.kube/config)",
        },
        field_secret={"kubeconfig": False},
        login_command_template="export KUBECONFIG={kubeconfig}",
        env_vars={"kubeconfig": "KUBECONFIG"},
        docs_url="https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/",
    ),
    "heroku": LoginRequirement(
        service="heroku",
        display_name="Heroku",
        command_pattern=r"heroku\s+",
        required_fields=["api_key"],
        field_prompts={
            "api_key": "Heroku API Key",
        },
        field_secret={"api_key": True},
        login_command_template="heroku auth:token",  # Interactive
        env_vars={"api_key": "HEROKU_API_KEY"},
        signup_url="https://signup.heroku.com/",
        docs_url="https://devcenter.heroku.com/articles/authentication",
    ),
}


# ============================================================================
# Ubuntu Package Mappings
# ============================================================================

UBUNTU_PACKAGE_MAP = {
    # Commands to packages
    "nginx": "nginx",
    "apache2": "apache2",
    "httpd": "apache2",
    "mysql": "mysql-server",
    "mysqld": "mysql-server",
    "postgres": "postgresql",
    "psql": "postgresql-client",
    "redis": "redis-server",
    "redis-server": "redis-server",
    "mongo": "mongodb",
    "mongod": "mongodb",
    "node": "nodejs",
    "npm": "npm",
    "yarn": "yarnpkg",
    "python": "python3",
    "python3": "python3",
    "pip": "python3-pip",
    "pip3": "python3-pip",
    "docker": "docker.io",
    "docker-compose": "docker-compose",
    "git": "git",
    "curl": "curl",
    "wget": "wget",
    "vim": "vim",
    "nano": "nano",
    "emacs": "emacs",
    "gcc": "gcc",
    "g++": "g++",
    "make": "make",
    "cmake": "cmake",
    "java": "default-jdk",
    "javac": "default-jdk",
    "ruby": "ruby",
    "gem": "ruby",
    "go": "golang-go",
    "cargo": "cargo",
    "rustc": "rustc",
    "php": "php",
    "composer": "composer",
    "ffmpeg": "ffmpeg",
    "imagemagick": "imagemagick",
    "convert": "imagemagick",
    "htop": "htop",
    "tree": "tree",
    "jq": "jq",
    "nc": "netcat-openbsd",
    "netcat": "netcat-openbsd",
    "ss": "iproute2",
    "ip": "iproute2",
    "dig": "dnsutils",
    "nslookup": "dnsutils",
    "zip": "zip",
    "unzip": "unzip",
    "tar": "tar",
    "gzip": "gzip",
    "rsync": "rsync",
    "ssh": "openssh-client",
    "sshd": "openssh-server",
    "screen": "screen",
    "tmux": "tmux",
    "awk": "gawk",
    "sed": "sed",
    "grep": "grep",
    "setfacl": "acl",
    "getfacl": "acl",
    "lsof": "lsof",
    "strace": "strace",
    # System monitoring tools
    "sensors": "lm-sensors",
    "sensors-detect": "lm-sensors",
    "iotop": "iotop",
    "iftop": "iftop",
    "nmap": "nmap",
    "netstat": "net-tools",
    "ifconfig": "net-tools",
    "smartctl": "smartmontools",
    "hdparm": "hdparm",
    # Optional tools (may not be in all repos)
    "snap": "snapd",
    "flatpak": "flatpak",
}

UBUNTU_SERVICE_MAP = {
    "nginx": "nginx",
    "apache": "apache2",
    "mysql": "mysql",
    "postgresql": "postgresql",
    "redis": "redis-server",
    "mongodb": "mongod",
    "docker": "docker",
    "ssh": "ssh",
    "cron": "cron",
    "ufw": "ufw",
}


# ============================================================================
# Error Diagnoser Class
# ============================================================================


class ErrorDiagnoser:
    """Comprehensive error diagnosis for all system error types."""

    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        self._compiled_patterns = []
        for ep in ALL_ERROR_PATTERNS:
            try:
                compiled = re.compile(ep.pattern, re.IGNORECASE | re.MULTILINE)
                self._compiled_patterns.append((compiled, ep))
            except re.error:
                console.print(f"[yellow]Warning: Invalid pattern: {ep.pattern}[/yellow]")

    def extract_path_from_error(self, stderr: str, cmd: str) -> str | None:
        """Extract the problematic file path from an error message."""
        patterns = [
            r"cannot (?:access|open|create|stat|read|write) ['\"]?([/\w\.\-_]+)['\"]?",
            r"['\"]([/\w\.\-_]+)['\"]?: (?:Permission denied|No such file)",
            r"open\(\) ['\"]([/\w\.\-_]+)['\"]? failed",
            r"failed to open ['\"]?([/\w\.\-_]+)['\"]?",
            r"couldn't open (?:temporary )?file ([/\w\.\-_]+)",
            r"([/\w\.\-_]+): Permission denied",
            r"([/\w\.\-_]+): No such file or directory",
            r"mkdir: cannot create directory ['\"]?([/\w\.\-_]+)['\"]?",
            r"touch: cannot touch ['\"]?([/\w\.\-_]+)['\"]?",
            r"cp: cannot (?:create|stat|access) ['\"]?([/\w\.\-_]+)['\"]?",
        ]

        for pattern in patterns:
            match = re.search(pattern, stderr, re.IGNORECASE)
            if match:
                path = match.group(1)
                if path.startswith("/"):
                    return path

        # Extract from command itself
        for part in cmd.split():
            if part.startswith("/") and any(
                c in part for c in ["/etc/", "/var/", "/usr/", "/home/", "/opt/", "/tmp/"]
            ):
                return part

        return None

    def extract_service_from_error(self, stderr: str, cmd: str) -> str | None:
        """Extract service name from error message or command."""
        cmd_parts = cmd.split()

        # From systemctl/service commands
        for i, part in enumerate(cmd_parts):
            if part in ["systemctl", "service"]:
                for j in range(i + 1, len(cmd_parts)):
                    candidate = cmd_parts[j]
                    if candidate not in [
                        "start",
                        "stop",
                        "restart",
                        "reload",
                        "status",
                        "enable",
                        "disable",
                        "is-active",
                        "is-enabled",
                        "-q",
                        "--quiet",
                        "--no-pager",
                    ]:
                        return candidate.replace(".service", "")

        # From error message
        patterns = [
            r"(?:Unit|Service) ([a-zA-Z0-9\-_]+)(?:\.service)? (?:not found|failed|could not)",
            r"Failed to (?:start|stop|restart|enable|disable) ([a-zA-Z0-9\-_]+)",
            r"([a-zA-Z0-9\-_]+)\.service",
        ]

        for pattern in patterns:
            match = re.search(pattern, stderr, re.IGNORECASE)
            if match:
                return match.group(1).replace(".service", "")

        return None

    def extract_package_from_error(self, stderr: str, cmd: str) -> str | None:
        """Extract package name from error."""
        patterns = [
            r"[Uu]nable to locate package ([a-zA-Z0-9\-_\.]+)",
            r"[Pp]ackage '?([a-zA-Z0-9\-_\.]+)'? (?:is )?not (?:found|installed)",
            r"[Nn]o package '?([a-zA-Z0-9\-_\.]+)'? (?:found|available)",
            r"apt.*install.*?([a-zA-Z0-9\-_\.]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, stderr + " " + cmd, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def extract_port_from_error(self, stderr: str) -> int | None:
        """Extract port number from error."""
        patterns = [
            r"[Pp]ort (\d+)",
            r"[Aa]ddress.*:(\d+)",
            r":(\d{2,5})\s",
        ]

        for pattern in patterns:
            match = re.search(pattern, stderr)
            if match:
                port = int(match.group(1))
                if 1 <= port <= 65535:
                    return port

        return None

    def _extract_container_name(self, stderr: str) -> str | None:
        """Extract Docker container name from error message."""
        patterns = [
            r'container name ["\'/]([a-zA-Z0-9_\-]+)["\'/]',
            r'["\'/]([a-zA-Z0-9_\-]+)["\'/] is already in use',
            r'container ["\']?([a-zA-Z0-9_\-]+)["\']?',
            r"No such container:?\s*([a-zA-Z0-9_\-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, stderr, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_image_name(self, stderr: str, cmd: str) -> str | None:
        """Extract Docker image name from error or command."""
        # From command
        if "docker" in cmd:
            parts = cmd.split()
            for i, part in enumerate(parts):
                if part in ["run", "pull", "push"]:
                    # Look for image name after flags
                    for j in range(i + 1, len(parts)):
                        candidate = parts[j]
                        if not candidate.startswith("-") and "/" in candidate or ":" in candidate:
                            return candidate
                        elif not candidate.startswith("-") and j == len(parts) - 1:
                            return candidate

        # From error
        patterns = [
            r'[Uu]nable to find image ["\']([^"\']+)["\']',
            r'repository ["\']?([^"\':\s]+(?::[^"\':\s]+)?)["\']? not found',
            r"manifest for ([^\s]+) not found",
        ]

        for pattern in patterns:
            match = re.search(pattern, stderr)
            if match:
                return match.group(1)

        return None

    def _extract_port(self, stderr: str) -> str | None:
        """Extract port from Docker error."""
        patterns = [
            r"[Pp]ort (\d+)",
            r":(\d+)->",
            r"address.*:(\d+)",
            r"-p\s*(\d+):",
        ]

        for pattern in patterns:
            match = re.search(pattern, stderr)
            if match:
                return match.group(1)

        return None

    def extract_config_file_and_line(self, stderr: str) -> tuple[str | None, int | None]:
        """Extract config file path and line number from error."""
        patterns = [
            r"in\s+(/[^\s:]+):(\d+)",  # "in /path:line"
            r"at\s+(/[^\s:]+):(\d+)",  # "at /path:line"
            r"(/[^\s:]+):(\d+):",  # "/path:line:"
            r"line\s+(\d+)\s+of\s+(/[^\s:]+)",  # "line X of /path"
            r"(/[^\s:]+)\s+line\s+(\d+)",  # "/path line X"
        ]

        for pattern in patterns:
            match = re.search(pattern, stderr, re.IGNORECASE)
            if match:
                groups = match.groups()
                if groups[0].startswith("/"):
                    return groups[0], int(groups[1])
                elif len(groups) > 1 and groups[1].startswith("/"):
                    return groups[1], int(groups[0])

        return None, None

    def extract_command_from_error(self, stderr: str) -> str | None:
        """Extract the failing command name from error."""
        patterns = [
            r"'([a-zA-Z0-9\-_]+)'.*command not found",
            r"([a-zA-Z0-9\-_]+): command not found",
            r"bash: ([a-zA-Z0-9\-_]+):",
            r"/usr/bin/env: '?([a-zA-Z0-9\-_]+)'?:",
        ]

        for pattern in patterns:
            match = re.search(pattern, stderr, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def diagnose_error(self, cmd: str, stderr: str) -> dict[str, Any]:
        """
        Comprehensive error diagnosis using pattern matching.

        Returns a detailed diagnosis dict with:
        - error_type: Specific error type
        - category: Error category (command_shell, network, etc.)
        - description: Human-readable description
        - fix_commands: Suggested fix commands
        - can_auto_fix: Whether we can auto-fix
        - fix_strategy: Strategy name for auto-fixer
        - extracted_info: Extracted paths, services, etc.
        - severity: error, warning, or critical
        """
        diagnosis = {
            "error_type": "unknown",
            "category": "unknown",
            "description": stderr[:300] if len(stderr) > 300 else stderr,
            "fix_commands": [],
            "can_auto_fix": False,
            "fix_strategy": "",
            "extracted_path": None,
            "extracted_info": {},
            "severity": "error",
        }

        stderr_lower = stderr.lower()

        # Extract common info
        diagnosis["extracted_path"] = self.extract_path_from_error(stderr, cmd)
        diagnosis["extracted_info"]["service"] = self.extract_service_from_error(stderr, cmd)
        diagnosis["extracted_info"]["package"] = self.extract_package_from_error(stderr, cmd)
        diagnosis["extracted_info"]["port"] = self.extract_port_from_error(stderr)

        config_file, line_num = self.extract_config_file_and_line(stderr)
        if config_file:
            diagnosis["extracted_info"]["config_file"] = config_file
            diagnosis["extracted_info"]["line_num"] = line_num

        # Match against compiled patterns
        for compiled, ep in self._compiled_patterns:
            if compiled.search(stderr):
                diagnosis["error_type"] = ep.error_type
                diagnosis["category"] = ep.category
                diagnosis["description"] = ep.description
                diagnosis["can_auto_fix"] = ep.can_auto_fix
                diagnosis["fix_strategy"] = ep.fix_strategy
                diagnosis["severity"] = ep.severity

                # Generate fix commands based on category and strategy
                self._generate_fix_commands(diagnosis, cmd, stderr)

                return diagnosis

        # Fallback: try generic patterns
        if "permission denied" in stderr_lower:
            diagnosis["error_type"] = "permission_denied"
            diagnosis["category"] = "permission"
            diagnosis["description"] = "Permission denied"
            diagnosis["can_auto_fix"] = True
            diagnosis["fix_strategy"] = "use_sudo"
            if not cmd.strip().startswith("sudo"):
                diagnosis["fix_commands"] = [f"sudo {cmd}"]

        elif "not found" in stderr_lower or "no such" in stderr_lower:
            diagnosis["error_type"] = "not_found"
            diagnosis["category"] = "file_directory"
            diagnosis["description"] = "File or directory not found"
            if diagnosis["extracted_path"]:
                diagnosis["can_auto_fix"] = True
                diagnosis["fix_strategy"] = "create_path"

        return diagnosis

    def _generate_fix_commands(self, diagnosis: dict, cmd: str, stderr: str) -> None:
        """Generate specific fix commands based on the error type and strategy."""
        strategy = diagnosis.get("fix_strategy", "")
        extracted = diagnosis.get("extracted_info", {})
        path = diagnosis.get("extracted_path")

        # Permission/Sudo strategies
        if strategy == "use_sudo":
            if not cmd.strip().startswith("sudo"):
                diagnosis["fix_commands"] = [f"sudo {cmd}"]

        # Path creation strategies
        elif strategy == "create_path":
            if path:
                parent = os.path.dirname(path)
                if parent:
                    diagnosis["fix_commands"] = [f"sudo mkdir -p {parent}"]

        # Package installation
        elif strategy == "install_package":
            missing_cmd = self.extract_command_from_error(stderr) or cmd.split()[0]
            pkg = UBUNTU_PACKAGE_MAP.get(missing_cmd, missing_cmd)
            diagnosis["fix_commands"] = ["sudo apt-get update", f"sudo apt-get install -y {pkg}"]
            diagnosis["extracted_info"]["missing_command"] = missing_cmd
            diagnosis["extracted_info"]["suggested_package"] = pkg

        # Service management
        elif strategy == "start_service" or strategy == "check_service":
            service = extracted.get("service")
            if service:
                diagnosis["fix_commands"] = [
                    f"sudo systemctl start {service}",
                    f"sudo systemctl status {service}",
                ]

        elif strategy == "check_service_logs":
            service = extracted.get("service")
            if service:
                # For web servers, check for port conflicts and common issues
                if service in ("apache2", "httpd", "nginx"):
                    diagnosis["fix_commands"] = [
                        # First check what's using port 80
                        "sudo lsof -i :80 -t | head -1",
                        # Stop conflicting services
                        "sudo systemctl stop nginx 2>/dev/null || true",
                        "sudo systemctl stop apache2 2>/dev/null || true",
                        # Test config
                        f"sudo {'apache2ctl' if service == 'apache2' else 'nginx'} -t 2>&1 || true",
                        # Now try starting
                        f"sudo systemctl start {service}",
                    ]
                elif service in ("mysql", "mariadb", "postgresql", "postgres"):
                    diagnosis["fix_commands"] = [
                        # Check disk space
                        "df -h /var/lib 2>/dev/null | tail -1",
                        # Check permissions
                        f"sudo chown -R {'mysql:mysql' if 'mysql' in service or 'mariadb' in service else 'postgres:postgres'} /var/lib/{'mysql' if 'mysql' in service or 'mariadb' in service else 'postgresql'} 2>/dev/null || true",
                        # Restart
                        f"sudo systemctl start {service}",
                    ]
                else:
                    # Generic service - check logs and try restart
                    diagnosis["fix_commands"] = [
                        f"sudo journalctl -u {service} -n 20 --no-pager 2>&1 | tail -10",
                        f"sudo systemctl reset-failed {service} 2>/dev/null || true",
                        f"sudo systemctl start {service}",
                    ]

        elif strategy == "unmask_service":
            service = extracted.get("service")
            if service:
                diagnosis["fix_commands"] = [
                    f"sudo systemctl unmask {service}",
                    f"sudo systemctl start {service}",
                ]

        # Config file fixes
        elif strategy in ["fix_nginx_config", "fix_nginx_permissions"]:
            config_file = extracted.get("config_file")
            line_num = extracted.get("line_num")
            if config_file:
                diagnosis["fix_commands"] = [
                    "sudo nginx -t 2>&1",
                    f"# Check config at: {config_file}" + (f":{line_num}" if line_num else ""),
                ]
            else:
                diagnosis["fix_commands"] = [
                    "sudo nginx -t 2>&1",
                    "# Check /etc/nginx/nginx.conf and sites-enabled/*",
                ]

        elif strategy == "fix_apache_config":
            config_file = extracted.get("config_file")
            diagnosis["fix_commands"] = [
                "sudo apache2ctl configtest",
                "sudo apache2ctl -S",  # Show virtual hosts
            ]
            if config_file:
                diagnosis["fix_commands"].append(f"# Check config at: {config_file}")

        elif strategy in ["fix_config_syntax", "fix_config_line"]:
            config_file = extracted.get("config_file")
            line_num = extracted.get("line_num")
            if config_file and line_num:
                diagnosis["fix_commands"] = [
                    f"sudo head -n {line_num + 5} {config_file} | tail -n 10",
                    f"# Edit: sudo nano +{line_num} {config_file}",
                ]
            elif config_file:
                diagnosis["fix_commands"] = [
                    f"sudo cat {config_file}",
                    f"# Edit: sudo nano {config_file}",
                ]

        elif strategy == "fix_mysql_config":
            diagnosis["fix_commands"] = [
                "sudo mysql --help --verbose 2>&1 | grep -A 1 'Default options'",
                "# Edit: sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf",
            ]

        elif strategy == "fix_postgres_config":
            diagnosis["fix_commands"] = [
                "sudo -u postgres psql -c 'SHOW config_file;'",
                "# Edit: sudo nano /etc/postgresql/*/main/postgresql.conf",
            ]

        # Package manager
        elif strategy == "clear_lock":
            diagnosis["fix_commands"] = [
                "sudo rm -f /var/lib/dpkg/lock-frontend",
                "sudo rm -f /var/lib/dpkg/lock",
                "sudo rm -f /var/cache/apt/archives/lock",
                "sudo dpkg --configure -a",
            ]

        elif strategy == "update_repos":
            pkg = extracted.get("package")
            diagnosis["fix_commands"] = ["sudo apt-get update"]
            if pkg:
                diagnosis["fix_commands"].append(f"apt-cache search {pkg}")

        elif strategy == "fix_dependencies":
            diagnosis["fix_commands"] = [
                "sudo apt-get install -f",
                "sudo dpkg --configure -a",
                "sudo apt-get update",
                "sudo apt-get upgrade",
            ]

        elif strategy == "fix_broken":
            diagnosis["fix_commands"] = [
                "sudo apt-get install -f",
                "sudo dpkg --configure -a",
                "sudo apt-get clean",
                "sudo apt-get update",
            ]

        elif strategy == "clean_apt":
            diagnosis["fix_commands"] = [
                "sudo apt-get clean",
                "sudo rm -rf /var/lib/apt/lists/*",
                "sudo apt-get update",
            ]

        elif strategy == "fix_gpg":
            diagnosis["fix_commands"] = [
                "sudo apt-key adv --refresh-keys --keyserver keyserver.ubuntu.com",
                "sudo apt-get update",
            ]

        # Docker strategies
        elif strategy == "remove_or_rename_container":
            container_name = self._extract_container_name(stderr)
            if container_name:
                diagnosis["fix_commands"] = [
                    f"docker rm -f {container_name}",
                    "# Or rename: docker rename {container_name} {container_name}_old",
                ]
                diagnosis["suggestion"] = (
                    f"Container '{container_name}' already exists. Removing it and retrying."
                )
            else:
                diagnosis["fix_commands"] = [
                    "docker ps -a",
                    "# Then: docker rm -f <container_name>",
                ]

        elif strategy == "stop_or_use_existing":
            container_name = self._extract_container_name(stderr)
            diagnosis["fix_commands"] = [
                f"docker stop {container_name}" if container_name else "docker stop <container>",
                "# Or connect to existing: docker exec -it <container> /bin/sh",
            ]

        elif strategy == "start_container":
            container_name = self._extract_container_name(stderr)
            diagnosis["fix_commands"] = [
                f"docker start {container_name}" if container_name else "docker start <container>"
            ]

        elif strategy == "pull_image":
            image_name = self._extract_image_name(stderr, cmd)
            diagnosis["fix_commands"] = [
                f"docker pull {image_name}" if image_name else "docker pull <image>"
            ]

        elif strategy == "free_port_or_use_different":
            port = self._extract_port(stderr)
            if port:
                diagnosis["fix_commands"] = [
                    f"sudo lsof -i :{port}",
                    f"# Kill process using port: sudo kill $(sudo lsof -t -i:{port})",
                    f"# Or use different port: -p {int(port)+1}:{port}",
                ]
            else:
                diagnosis["fix_commands"] = ["docker ps", "# Check which ports are in use"]

        elif strategy == "start_docker_daemon":
            diagnosis["fix_commands"] = [
                "sudo systemctl start docker",
                "sudo systemctl status docker",
            ]

        elif strategy == "create_volume":
            volume_name = extracted.get("volume")
            diagnosis["fix_commands"] = [
                (
                    f"docker volume create {volume_name}"
                    if volume_name
                    else "docker volume create <name>"
                )
            ]

        elif strategy == "create_network":
            network_name = extracted.get("network")
            diagnosis["fix_commands"] = [
                (
                    f"docker network create {network_name}"
                    if network_name
                    else "docker network create <name>"
                )
            ]

        elif strategy == "check_container_name":
            diagnosis["fix_commands"] = [
                "docker ps -a",
                "# Check container names and use correct one",
            ]

        # Timeout strategies
        elif strategy == "retry_with_longer_timeout":
            # Check if this is an interactive command that needs TTY
            interactive_patterns = [
                "docker exec -it",
                "docker run -it",
                "-ti ",
                "ollama run",
                "ollama chat",
            ]
            is_interactive = any(p in cmd.lower() for p in interactive_patterns)

            if is_interactive:
                diagnosis["fix_commands"] = [
                    "# This is an INTERACTIVE command that requires a terminal (TTY)",
                    "# Run it manually in a separate terminal window:",
                    f"# {cmd}",
                ]
                diagnosis["description"] = "Interactive command cannot run in background"
                diagnosis["suggestion"] = (
                    "This command needs interactive input. Please run it in a separate terminal."
                )
            else:
                diagnosis["fix_commands"] = [
                    "# This command timed out - it may still be running or need more time",
                    "# For docker pull: The image may be very large, try again with better network",
                    "# Check if the operation completed in background",
                ]
                diagnosis["suggestion"] = (
                    "The operation timed out. This often happens with large downloads. You can retry manually."
                )
            diagnosis["can_auto_fix"] = False  # Let user decide what to do

        # Network strategies
        elif strategy == "check_network":
            diagnosis["fix_commands"] = ["ping -c 2 8.8.8.8", "ip route", "cat /etc/resolv.conf"]

        elif strategy == "check_dns":
            diagnosis["fix_commands"] = [
                "cat /etc/resolv.conf",
                "systemd-resolve --status",
                "sudo systemctl restart systemd-resolved",
            ]

        elif strategy == "check_service":
            port = extracted.get("port")
            if port:
                diagnosis["fix_commands"] = [
                    f"sudo ss -tlnp sport = :{port}",
                    f"sudo lsof -i :{port}",
                ]

        elif strategy == "find_port_user":
            port = extracted.get("port")
            if port:
                diagnosis["fix_commands"] = [
                    f"sudo lsof -i :{port}",
                    f"sudo ss -tlnp sport = :{port}",
                    "# Kill process: sudo kill <PID>",
                ]

        elif strategy == "check_firewall":
            diagnosis["fix_commands"] = ["sudo ufw status", "sudo iptables -L -n"]

        # Disk/Memory strategies
        elif strategy == "free_disk":
            diagnosis["fix_commands"] = [
                "df -h",
                "sudo apt-get clean",
                "sudo apt-get autoremove -y",
                "sudo journalctl --vacuum-size=100M",
                "du -sh /var/log/*",
            ]

        elif strategy == "free_memory":
            diagnosis["fix_commands"] = [
                "free -h",
                "sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches",
                "top -b -n 1 | head -20",
            ]

        elif strategy == "increase_ulimit":
            diagnosis["fix_commands"] = [
                "ulimit -a",
                "# Add to /etc/security/limits.conf:",
                "# * soft nofile 65535",
                "# * hard nofile 65535",
            ]

        # Filesystem strategies
        elif strategy == "remount_rw":
            if path:
                mount_point = self._find_mount_point(path)
                if mount_point:
                    diagnosis["fix_commands"] = [f"sudo mount -o remount,rw {mount_point}"]

        elif strategy == "create_mountpoint":
            if path:
                diagnosis["fix_commands"] = [f"sudo mkdir -p {path}"]

        elif strategy == "mount_fs":
            diagnosis["fix_commands"] = ["mount", "cat /etc/fstab"]

        # User strategies
        elif strategy == "create_user":
            # Extract username from error if possible
            match = re.search(r"user '?([a-zA-Z0-9_-]+)'?", stderr, re.IGNORECASE)
            if match:
                user = match.group(1)
                diagnosis["fix_commands"] = [f"sudo useradd -m {user}", f"sudo passwd {user}"]

        elif strategy == "create_group":
            match = re.search(r"group '?([a-zA-Z0-9_-]+)'?", stderr, re.IGNORECASE)
            if match:
                group = match.group(1)
                diagnosis["fix_commands"] = [f"sudo groupadd {group}"]

        # Build strategies
        elif strategy == "install_lib":
            lib_match = re.search(r"library.*?([a-zA-Z0-9_-]+)", stderr, re.IGNORECASE)
            if lib_match:
                lib = lib_match.group(1)
                diagnosis["fix_commands"] = [
                    f"apt-cache search {lib}",
                    f"# Install with: sudo apt-get install lib{lib}-dev",
                ]

        elif strategy == "install_dev":
            header_match = re.search(r"([a-zA-Z0-9_/]+\.h)", stderr)
            if header_match:
                header = header_match.group(1)
                diagnosis["fix_commands"] = [
                    f"apt-file search {header}",
                    "# Install the -dev package that provides this header",
                ]

        elif strategy == "fix_ldpath":
            diagnosis["fix_commands"] = [
                "sudo ldconfig",
                "echo $LD_LIBRARY_PATH",
                "cat /etc/ld.so.conf.d/*.conf",
            ]

        # Wait/Retry strategies
        elif strategy == "wait_retry":
            diagnosis["fix_commands"] = ["sleep 2", f"# Then retry: {cmd}"]

        # Script strategies
        elif strategy == "fix_shebang":
            if path:
                diagnosis["fix_commands"] = [
                    f"head -1 {path}",
                    "# Fix shebang line to point to correct interpreter",
                    "# e.g., #!/usr/bin/env python3",
                ]

        # Environment strategies
        elif strategy == "set_variable":
            var_match = re.search(r"([A-Z_]+).*not set", stderr, re.IGNORECASE)
            if var_match:
                var = var_match.group(1)
                diagnosis["fix_commands"] = [
                    f"export {var}=<value>",
                    f"# Add to ~/.bashrc: export {var}=<value>",
                ]

        elif strategy == "set_path":
            diagnosis["fix_commands"] = [
                "echo $PATH",
                "export PATH=$PATH:/usr/local/bin",
                "# Add to ~/.bashrc",
            ]

        elif strategy == "set_ldpath":
            diagnosis["fix_commands"] = [
                "echo $LD_LIBRARY_PATH",
                "export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH",
                "sudo ldconfig",
            ]

        # Backup/Overwrite strategy
        elif strategy == "backup_overwrite":
            if path:
                diagnosis["fix_commands"] = [
                    f"sudo mv {path} {path}.backup",
                    f"# Then retry: {cmd}",
                ]

        # Symlink strategy
        elif strategy == "fix_symlink":
            if path:
                diagnosis["fix_commands"] = [
                    f"ls -la {path}",
                    f"readlink -f {path}",
                    f"# Remove broken symlink: sudo rm {path}",
                ]

        # Directory not empty
        elif strategy == "rm_recursive":
            if path:
                diagnosis["fix_commands"] = [
                    f"ls -la {path}",
                    f"# Remove recursively (CAUTION): sudo rm -rf {path}",
                ]

        # Copy instead of link
        elif strategy == "copy_instead":
            diagnosis["fix_commands"] = [
                "# Use cp instead of ln/mv for cross-device operations",
                "# cp -a <source> <dest>",
            ]

    def _find_mount_point(self, path: str) -> str | None:
        """Find the mount point for a given path."""
        try:
            path = os.path.abspath(path)
            while path != "/":
                if os.path.ismount(path):
                    return path
                path = os.path.dirname(path)
            return "/"
        except:
            return None


# ============================================================================
# Login Handler Class
# ============================================================================


class LoginHandler:
    """Handles interactive login/credential prompts for various services."""

    CREDENTIALS_FILE = os.path.expanduser("~/.cortex/credentials.json")

    def __init__(self):
        self.cached_credentials: dict[str, dict] = {}
        self._ensure_credentials_dir()
        self._load_saved_credentials()

    def _ensure_credentials_dir(self) -> None:
        """Ensure the credentials directory exists with proper permissions."""
        cred_dir = os.path.dirname(self.CREDENTIALS_FILE)
        if not os.path.exists(cred_dir):
            os.makedirs(cred_dir, mode=0o700, exist_ok=True)

    def _encode_credential(self, value: str) -> str:
        """Encode a credential value (basic obfuscation, not encryption)."""
        import base64

        return base64.b64encode(value.encode()).decode()

    def _decode_credential(self, encoded: str) -> str:
        """Decode a credential value."""
        import base64

        try:
            return base64.b64decode(encoded.encode()).decode()
        except Exception:
            return ""

    def _load_saved_credentials(self) -> None:
        """Load saved credentials from file."""
        import json

        if not os.path.exists(self.CREDENTIALS_FILE):
            return

        try:
            with open(self.CREDENTIALS_FILE) as f:
                saved = json.load(f)

            # Decode all saved credentials
            for service, creds in saved.items():
                decoded = {}
                for field, value in creds.items():
                    if field.startswith("_"):  # metadata fields
                        decoded[field] = value
                    else:
                        decoded[field] = self._decode_credential(value)
                self.cached_credentials[service] = decoded

        except (OSError, json.JSONDecodeError) as e:
            console.print(f"[dim]Note: Could not load saved credentials: {e}[/dim]")

    def _save_credentials(self, service: str, credentials: dict[str, str]) -> None:
        """Save credentials to file."""
        import json
        from datetime import datetime

        # Load existing credentials
        all_creds = {}
        if os.path.exists(self.CREDENTIALS_FILE):
            try:
                with open(self.CREDENTIALS_FILE) as f:
                    all_creds = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass

        # Encode new credentials
        encoded = {}
        for field_name, value in credentials.items():
            if value:  # Only save non-empty values
                encoded[field_name] = self._encode_credential(value)

        # Add metadata
        encoded["_saved_at"] = datetime.now().isoformat()

        all_creds[service] = encoded

        # Save to file with restricted permissions
        try:
            with open(self.CREDENTIALS_FILE, "w") as f:
                json.dump(all_creds, f, indent=2)
            os.chmod(self.CREDENTIALS_FILE, 0o600)  # Read/write only for owner
            console.print(f"[green]✓ Credentials saved to {self.CREDENTIALS_FILE}[/green]")
        except OSError as e:
            console.print(f"[yellow]Warning: Could not save credentials: {e}[/yellow]")

    def _delete_saved_credentials(self, service: str) -> None:
        """Delete saved credentials for a service."""
        import json

        if not os.path.exists(self.CREDENTIALS_FILE):
            return

        try:
            with open(self.CREDENTIALS_FILE) as f:
                all_creds = json.load(f)

            if service in all_creds:
                del all_creds[service]

                with open(self.CREDENTIALS_FILE, "w") as f:
                    json.dump(all_creds, f, indent=2)

                console.print(f"[dim]Removed saved credentials for {service}[/dim]")
        except (OSError, json.JSONDecodeError):
            pass

    def _has_saved_credentials(self, service: str) -> bool:
        """Check if we have saved credentials for a service."""
        return service in self.cached_credentials and bool(self.cached_credentials[service])

    def _ask_use_saved(self, service: str, requirement: LoginRequirement) -> bool:
        """Ask user if they want to use saved credentials."""
        saved = self.cached_credentials.get(service, {})

        # Show what we have saved (without showing secrets)
        saved_fields = []
        for field_name in requirement.required_fields:
            if field_name in saved and saved[field_name]:
                if requirement.field_secret.get(field_name, False):
                    saved_fields.append(f"{field_name}=****")
                else:
                    value = saved[field_name]
                    # Truncate long values
                    if len(value) > 20:
                        value = value[:17] + "..."
                    saved_fields.append(f"{field_name}={value}")

        if not saved_fields:
            return False

        console.print()
        console.print(f"[cyan]📁 Found saved credentials for {requirement.display_name}:[/cyan]")
        console.print(f"[dim]   {', '.join(saved_fields)}[/dim]")

        if "_saved_at" in saved:
            console.print(f"[dim]   Saved: {saved['_saved_at'][:19]}[/dim]")

        console.print()
        try:
            response = input("Use saved credentials? (y/n/delete): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False

        if response in ["d", "delete", "del", "remove"]:
            self._delete_saved_credentials(service)
            if service in self.cached_credentials:
                del self.cached_credentials[service]
            return False

        return response in ["y", "yes", ""]

    def _ask_save_credentials(self, service: str, credentials: dict[str, str]) -> None:
        """Ask user if they want to save credentials for next time."""
        console.print()
        console.print("[cyan]💾 Save these credentials for next time?[/cyan]")
        console.print(f"[dim]   Credentials will be stored in {self.CREDENTIALS_FILE}[/dim]")
        console.print("[dim]   (encoded, readable only by you)[/dim]")

        try:
            response = input("Save credentials? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return

        if response in ["y", "yes"]:
            self._save_credentials(service, credentials)
            # Also update cache
            self.cached_credentials[service] = credentials.copy()

    def detect_login_requirement(self, cmd: str, stderr: str) -> LoginRequirement | None:
        """Detect which service needs login based on command and error."""
        cmd_lower = cmd.lower()
        stderr_lower = stderr.lower()

        # Check for specific registries in docker commands
        if "docker" in cmd_lower:
            if "ghcr.io" in cmd_lower or "ghcr.io" in stderr_lower:
                return LOGIN_REQUIREMENTS.get("ghcr")
            if "gcr.io" in cmd_lower or "gcr.io" in stderr_lower:
                return LOGIN_REQUIREMENTS.get("gcloud")
            return LOGIN_REQUIREMENTS.get("docker")

        # Check other services
        for service, req in LOGIN_REQUIREMENTS.items():
            if re.search(req.command_pattern, cmd, re.IGNORECASE):
                return req

        return None

    def check_env_credentials(self, requirement: LoginRequirement) -> dict[str, str]:
        """Check if credentials are available in environment variables."""
        found = {}
        for field_name, env_var in requirement.env_vars.items():
            value = os.environ.get(env_var)
            if value:
                found[field_name] = value
        return found

    def prompt_for_credentials(
        self, requirement: LoginRequirement, pre_filled: dict[str, str] | None = None
    ) -> dict[str, str] | None:
        """Prompt user for required credentials."""
        import getpass

        console.print()
        console.print(
            f"[bold cyan]🔐 {requirement.display_name} Authentication Required[/bold cyan]"
        )
        console.print()

        if requirement.signup_url:
            console.print(f"[dim]Don't have an account? Sign up at: {requirement.signup_url}[/dim]")
        if requirement.docs_url:
            console.print(f"[dim]Documentation: {requirement.docs_url}[/dim]")
        console.print()

        # Check for existing env vars
        env_creds = self.check_env_credentials(requirement)
        if env_creds:
            console.print(
                f"[green]Found credentials in environment: {', '.join(env_creds.keys())}[/green]"
            )

        credentials = pre_filled.copy() if pre_filled else {}
        credentials.update(env_creds)

        try:
            for field in requirement.required_fields:
                if field in credentials and credentials[field]:
                    console.print(
                        f"[dim]{requirement.field_prompts[field]}: (using existing)[/dim]"
                    )
                    continue

                prompt_text = requirement.field_prompts.get(field, f"Enter {field}")
                is_secret = requirement.field_secret.get(field, False)

                # Handle special defaults
                default_value = ""
                if field == "registry":
                    default_value = "docker.io"
                elif field == "region":
                    default_value = "us-east-1"
                elif field == "kubeconfig":
                    default_value = os.path.expanduser("~/.kube/config")

                if default_value:
                    prompt_text = f"{prompt_text} [{default_value}]"

                console.print(f"[bold]{prompt_text}:[/bold] ", end="")

                if is_secret:
                    value = getpass.getpass("")
                else:
                    try:
                        value = input()
                    except (EOFError, KeyboardInterrupt):
                        console.print("\n[yellow]Authentication cancelled.[/yellow]")
                        return None

                # Use default if empty
                if not value and default_value:
                    value = default_value
                    console.print(f"[dim]Using default: {default_value}[/dim]")

                if not value and field != "registry":  # registry can be empty for Docker Hub
                    console.print(f"[red]Error: {field} is required.[/red]")
                    return None

                credentials[field] = value

            return credentials

        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Authentication cancelled.[/yellow]")
            return None

    def execute_login(
        self, requirement: LoginRequirement, credentials: dict[str, str]
    ) -> tuple[bool, str, str]:
        """Execute the login command with provided credentials."""

        # Build the login command
        if not requirement.login_command_template:
            return False, "", "No login command template defined"

        # Handle special cases
        if requirement.service == "docker" and credentials.get("registry") in ["", "docker.io"]:
            credentials["registry"] = ""  # Docker Hub doesn't need registry in command

        # Format the command
        try:
            login_cmd = requirement.login_command_template.format(**credentials)
        except KeyError as e:
            return False, "", f"Missing credential: {e}"

        # For Docker, use stdin for password to avoid it showing in ps
        if requirement.service in ["docker", "ghcr"]:
            password = credentials.get("password") or credentials.get("token", "")
            username = credentials.get("username", "")
            registry = credentials.get("registry", "")

            if requirement.service == "ghcr":
                registry = "ghcr.io"

            # Build safe command
            if registry:
                cmd_parts = ["docker", "login", registry, "-u", username, "--password-stdin"]
            else:
                cmd_parts = ["docker", "login", "-u", username, "--password-stdin"]

            console.print(
                f"[dim]Executing: docker login {registry or 'docker.io'} -u {username}[/dim]"
            )

            try:
                process = subprocess.Popen(
                    cmd_parts,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                stdout, stderr = process.communicate(input=password, timeout=60)
                return process.returncode == 0, stdout.strip(), stderr.strip()
            except subprocess.TimeoutExpired:
                process.kill()
                return False, "", "Login timed out"
            except Exception as e:
                return False, "", str(e)

        # For other services, execute directly
        console.print("[dim]Executing login...[/dim]")
        try:
            result = subprocess.run(
                login_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", "Login timed out"
        except Exception as e:
            return False, "", str(e)

    def handle_login(self, cmd: str, stderr: str) -> tuple[bool, str]:
        """
        Main entry point: detect login requirement, prompt, and execute.

        Returns:
            (success, message)
        """
        requirement = self.detect_login_requirement(cmd, stderr)

        if not requirement:
            return False, "Could not determine which service needs authentication"

        used_saved = False
        credentials = None

        # Check for saved credentials first
        if self._has_saved_credentials(requirement.service):
            if self._ask_use_saved(requirement.service, requirement):
                # Use saved credentials
                credentials = self.cached_credentials.get(requirement.service, {}).copy()
                # Remove metadata fields
                credentials = {k: v for k, v in credentials.items() if not k.startswith("_")}
                used_saved = True

                console.print("[cyan]Using saved credentials...[/cyan]")
                success, stdout, login_stderr = self.execute_login(requirement, credentials)

                if success:
                    console.print(
                        f"[green]✓ Successfully logged in to {requirement.display_name} using saved credentials[/green]"
                    )
                    return True, f"Logged in to {requirement.display_name} using saved credentials"
                else:
                    console.print(
                        f"[yellow]Saved credentials didn't work: {login_stderr[:100] if login_stderr else 'Unknown error'}[/yellow]"
                    )
                    console.print("[dim]Let's enter new credentials...[/dim]")
                    credentials = None
                    used_saved = False

        # Prompt for new credentials if we don't have valid ones
        if not credentials:
            # Pre-fill with any partial saved credentials (like username)
            pre_filled = {}
            if requirement.service in self.cached_credentials:
                saved = self.cached_credentials[requirement.service]
                for field in requirement.required_fields:
                    if (
                        field in saved
                        and saved[field]
                        and not requirement.field_secret.get(field, False)
                    ):
                        pre_filled[field] = saved[field]

            credentials = self.prompt_for_credentials(
                requirement, pre_filled if pre_filled else None
            )

        if not credentials:
            return False, "Authentication cancelled by user"

        # Execute login
        success, stdout, login_stderr = self.execute_login(requirement, credentials)

        if success:
            console.print(f"[green]✓ Successfully logged in to {requirement.display_name}[/green]")

            # Ask to save credentials if they weren't from saved file
            if not used_saved:
                self._ask_save_credentials(requirement.service, credentials)

            # Update session cache
            self.cached_credentials[requirement.service] = credentials.copy()

            return True, f"Successfully authenticated with {requirement.display_name}"
        else:
            error_msg = login_stderr or "Login failed"
            console.print(f"[red]✗ Login failed: {error_msg}[/red]")

            # Offer to retry
            console.print()
            try:
                retry = input("Would you like to try again? (y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                retry = "n"

            if retry in ["y", "yes"]:
                # Clear cached credentials for this service since they failed
                if requirement.service in self.cached_credentials:
                    del self.cached_credentials[requirement.service]
                return self.handle_login(cmd, stderr)  # Recursive retry

            return False, f"Login failed: {error_msg}"


# Auto-Fixer Class
# ============================================================================


class AutoFixer:
    """Auto-fixes errors based on diagnosis."""

    def __init__(self, llm_callback: Callable[[str, dict], dict] | None = None):
        self.diagnoser = ErrorDiagnoser()
        self.llm_callback = llm_callback
        # Track all attempted fixes across multiple calls to avoid repeating
        self._attempted_fixes: dict[str, set[str]] = {}  # cmd -> set of fix commands tried
        self._attempted_strategies: dict[str, set[str]] = {}  # cmd -> set of strategies tried

    def _get_fix_key(self, cmd: str) -> str:
        """Generate a key for tracking fixes for a command."""
        # Normalize the command (strip sudo, whitespace)
        normalized = cmd.strip()
        if normalized.startswith("sudo "):
            normalized = normalized[5:].strip()
        return normalized

    def _is_fix_attempted(self, original_cmd: str, fix_cmd: str) -> bool:
        """Check if a fix command has already been attempted for this command."""
        key = self._get_fix_key(original_cmd)
        fix_normalized = fix_cmd.strip()

        if key not in self._attempted_fixes:
            return False

        return fix_normalized in self._attempted_fixes[key]

    def _mark_fix_attempted(self, original_cmd: str, fix_cmd: str) -> None:
        """Mark a fix command as attempted."""
        key = self._get_fix_key(original_cmd)

        if key not in self._attempted_fixes:
            self._attempted_fixes[key] = set()

        self._attempted_fixes[key].add(fix_cmd.strip())

    def _is_strategy_attempted(self, original_cmd: str, strategy: str, error_type: str) -> bool:
        """Check if a strategy has been attempted for this command/error combination."""
        key = f"{self._get_fix_key(original_cmd)}:{error_type}"

        if key not in self._attempted_strategies:
            return False

        return strategy in self._attempted_strategies[key]

    def _mark_strategy_attempted(self, original_cmd: str, strategy: str, error_type: str) -> None:
        """Mark a strategy as attempted for this command/error combination."""
        key = f"{self._get_fix_key(original_cmd)}:{error_type}"

        if key not in self._attempted_strategies:
            self._attempted_strategies[key] = set()

        self._attempted_strategies[key].add(strategy)

    def reset_attempts(self, cmd: str | None = None) -> None:
        """Reset attempted fixes tracking. If cmd is None, reset all."""
        if cmd is None:
            self._attempted_fixes.clear()
            self._attempted_strategies.clear()
        else:
            key = self._get_fix_key(cmd)
            if key in self._attempted_fixes:
                del self._attempted_fixes[key]
            # Clear all strategies for this command
            to_delete = [k for k in self._attempted_strategies if k.startswith(key)]
            for k in to_delete:
                del self._attempted_strategies[k]

    def _get_llm_fix(self, cmd: str, stderr: str, diagnosis: dict) -> dict | None:
        """Use LLM to diagnose error and suggest fix commands.

        This is called when pattern matching fails to identify the error.
        """
        if not self.llm_callback:
            return None

        context = {
            "error_command": cmd,
            "error_output": stderr[:1000],  # Truncate for LLM context
            "current_diagnosis": diagnosis,
        }

        # Create a targeted prompt for error diagnosis
        prompt = f"""Analyze this Linux command error and provide fix commands.

FAILED COMMAND: {cmd}

ERROR OUTPUT:
{stderr[:800]}

Provide a JSON response with:
1. "fix_commands": list of shell commands to fix this error (in order)
2. "reasoning": brief explanation of the error and fix

Focus on common issues:
- Docker: container already exists (docker rm -f <name>), port conflicts, daemon not running
- Permissions: use sudo, create directories
- Services: systemctl start/restart
- Files: mkdir -p, touch, chown

Example response:
{{"fix_commands": ["docker rm -f ollama", "docker run ..."], "reasoning": "Container 'ollama' already exists, removing it first"}}"""

        try:
            response = self.llm_callback(prompt, context)

            if response and response.get("response_type") != "error":
                # Check if the response contains fix commands directly
                if response.get("fix_commands"):
                    return {
                        "fix_commands": response["fix_commands"],
                        "reasoning": response.get("reasoning", "AI-suggested fix"),
                    }

                # Check if it's a do_commands response
                if response.get("do_commands"):
                    return {
                        "fix_commands": [cmd["command"] for cmd in response["do_commands"]],
                        "reasoning": response.get("reasoning", "AI-suggested fix"),
                    }

                # Try to parse answer as fix suggestion
                if response.get("answer"):
                    # Extract commands from natural language response
                    answer = response["answer"]
                    commands = []
                    for line in answer.split("\n"):
                        line = line.strip()
                        if (
                            line.startswith("$")
                            or line.startswith("sudo ")
                            or line.startswith("docker ")
                        ):
                            commands.append(line.lstrip("$ "))
                    if commands:
                        return {"fix_commands": commands, "reasoning": "Extracted from AI response"}

            return None

        except Exception as e:
            console.print(f"[dim]   LLM fix generation failed: {e}[/dim]")
            return None

    def _execute_command(
        self, cmd: str, needs_sudo: bool = False, timeout: int = 120
    ) -> tuple[bool, str, str]:
        """Execute a single command."""
        import sys

        try:
            if needs_sudo and not cmd.strip().startswith("sudo"):
                cmd = f"sudo {cmd}"

            # Handle comments
            if cmd.strip().startswith("#"):
                return True, "", ""

            # For sudo commands, we need to handle the password prompt specially
            is_sudo = cmd.strip().startswith("sudo")

            if is_sudo:
                # Flush output before sudo to ensure clean state
                sys.stdout.flush()
                sys.stderr.flush()

            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if is_sudo:
                # After sudo, ensure console is in clean state
                # Print empty line to reset cursor position after potential password prompt
                sys.stdout.write("\n")
                sys.stdout.flush()

            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", str(e)

    def auto_fix_error(
        self,
        cmd: str,
        stderr: str,
        diagnosis: dict[str, Any],
        max_attempts: int = 5,
    ) -> tuple[bool, str, list[str]]:
        """
        General-purpose auto-fix system with retry logic.

        Tracks attempted fixes to avoid repeating the same fixes.

        Returns:
            Tuple of (fixed, message, commands_executed)
        """
        all_commands_executed = []
        current_stderr = stderr
        current_diagnosis = diagnosis
        attempt = 0
        skipped_attempts = 0
        max_skips = 3  # Max attempts to skip before giving up

        while attempt < max_attempts and skipped_attempts < max_skips:
            attempt += 1
            error_type = current_diagnosis.get("error_type", "unknown")
            strategy = current_diagnosis.get("fix_strategy", "")
            category = current_diagnosis.get("category", "unknown")

            # Check if this strategy was already attempted for this error
            if self._is_strategy_attempted(cmd, strategy, error_type):
                console.print(
                    f"[dim]   Skipping already-tried strategy: {strategy} for {error_type}[/dim]"
                )
                skipped_attempts += 1

                # Try to get a different diagnosis by re-analyzing
                if current_stderr:
                    # Force a different approach by marking current strategy as exhausted
                    current_diagnosis["fix_strategy"] = ""
                    current_diagnosis["can_auto_fix"] = False
                continue

            # Mark this strategy as attempted
            self._mark_strategy_attempted(cmd, strategy, error_type)

            # Check fix commands that would be generated
            fix_commands = current_diagnosis.get("fix_commands", [])

            # Filter out already-attempted fix commands
            new_fix_commands = []
            for fix_cmd in fix_commands:
                if fix_cmd.startswith("#"):  # Comments are always allowed
                    new_fix_commands.append(fix_cmd)
                elif self._is_fix_attempted(cmd, fix_cmd):
                    console.print(f"[dim]   Skipping already-executed: {fix_cmd[:50]}...[/dim]")
                else:
                    new_fix_commands.append(fix_cmd)

            # If all fix commands were already tried, skip this attempt
            if fix_commands and not new_fix_commands:
                console.print(f"[dim]   All fix commands already tried for {error_type}[/dim]")
                skipped_attempts += 1
                continue

            # Update diagnosis with filtered commands
            current_diagnosis["fix_commands"] = new_fix_commands

            # Reset skip counter since we found something new to try
            skipped_attempts = 0

            severity = current_diagnosis.get("severity", "error")

            # Visual grouping for auto-fix attempts
            from rich.panel import Panel
            from rich.text import Text

            fix_title = Text()
            fix_title.append("🔧 AUTO-FIX ", style="bold yellow")
            fix_title.append(f"Attempt {attempt}/{max_attempts}", style="dim")

            severity_color = "red" if severity == "critical" else "yellow"
            fix_content = Text()
            if severity == "critical":
                fix_content.append("⚠️  CRITICAL: ", style="bold red")
            fix_content.append(f"[{category}] ", style="dim")
            fix_content.append(error_type, style=f"bold {severity_color}")

            console.print()
            console.print(
                Panel(
                    fix_content,
                    title=fix_title,
                    title_align="left",
                    border_style=severity_color,
                    padding=(0, 1),
                )
            )

            # Ensure output is flushed before executing fixes
            import sys

            sys.stdout.flush()

            fixed, message, commands = self.apply_single_fix(cmd, current_stderr, current_diagnosis)

            # Mark all executed commands as attempted
            for exec_cmd in commands:
                self._mark_fix_attempted(cmd, exec_cmd)
            all_commands_executed.extend(commands)

            if fixed:
                # Check if it's just a "use sudo" suggestion
                if message == "Will retry with sudo":
                    sudo_cmd = f"sudo {cmd}" if not cmd.startswith("sudo") else cmd

                    # Check if we already tried sudo
                    if self._is_fix_attempted(cmd, sudo_cmd):
                        console.print("[dim]   Already tried sudo, skipping...[/dim]")
                        skipped_attempts += 1
                        continue

                    self._mark_fix_attempted(cmd, sudo_cmd)
                    success, stdout, new_stderr = self._execute_command(sudo_cmd)
                    all_commands_executed.append(sudo_cmd)

                    if success:
                        console.print(
                            Panel(
                                "[bold green]✓ Fixed with sudo[/bold green]",
                                border_style="green",
                                padding=(0, 1),
                                expand=False,
                            )
                        )
                        return (
                            True,
                            f"Fixed with sudo after {attempt} attempt(s)",
                            all_commands_executed,
                        )
                    else:
                        current_stderr = new_stderr
                        current_diagnosis = self.diagnoser.diagnose_error(cmd, new_stderr)
                        continue

                # Verify the original command now works
                console.print(
                    Panel(
                        f"[bold cyan]✓ Fix applied:[/bold cyan] {message}\n[dim]Verifying original command...[/dim]",
                        border_style="cyan",
                        padding=(0, 1),
                        expand=False,
                    )
                )

                verify_cmd = f"sudo {cmd}" if not cmd.startswith("sudo") else cmd
                success, stdout, new_stderr = self._execute_command(verify_cmd)
                all_commands_executed.append(verify_cmd)

                if success:
                    console.print(
                        Panel(
                            "[bold green]✓ Verified![/bold green] Command now succeeds",
                            border_style="green",
                            padding=(0, 1),
                            expand=False,
                        )
                    )
                    return (
                        True,
                        f"Fixed after {attempt} attempt(s): {message}",
                        all_commands_executed,
                    )
                else:
                    new_diagnosis = self.diagnoser.diagnose_error(cmd, new_stderr)

                    if new_diagnosis["error_type"] == error_type:
                        console.print(
                            "   [dim yellow]Same error persists, trying different approach...[/dim yellow]"
                        )
                    else:
                        console.print(
                            f"   [yellow]New error: {new_diagnosis['error_type']}[/yellow]"
                        )

                    current_stderr = new_stderr
                    current_diagnosis = new_diagnosis
            else:
                console.print(f"   [dim red]Fix attempt failed: {message}[/dim red]")
                console.print("   [dim]Trying fallback...[/dim]")

                # Try with sudo as fallback
                sudo_fallback = f"sudo {cmd}"
                if not cmd.strip().startswith("sudo") and not self._is_fix_attempted(
                    cmd, sudo_fallback
                ):
                    self._mark_fix_attempted(cmd, sudo_fallback)
                    success, _, new_stderr = self._execute_command(sudo_fallback)
                    all_commands_executed.append(sudo_fallback)

                    if success:
                        return True, "Fixed with sudo fallback", all_commands_executed

                    current_stderr = new_stderr
                    current_diagnosis = self.diagnoser.diagnose_error(cmd, new_stderr)
                else:
                    if cmd.strip().startswith("sudo"):
                        console.print("[dim]   Already running with sudo, no more fallbacks[/dim]")
                    else:
                        console.print("[dim]   Sudo fallback already tried[/dim]")
                    break

        # Final summary of what was attempted
        unique_attempts = len(self._attempted_fixes.get(self._get_fix_key(cmd), set()))
        if unique_attempts > 0:
            console.print(f"[dim]   Total unique fixes attempted: {unique_attempts}[/dim]")

        return (
            False,
            f"Could not fix after {attempt} attempts ({skipped_attempts} skipped as duplicates)",
            all_commands_executed,
        )

    def apply_single_fix(
        self,
        cmd: str,
        stderr: str,
        diagnosis: dict[str, Any],
    ) -> tuple[bool, str, list[str]]:
        """Apply a single fix attempt based on the error diagnosis."""
        error_type = diagnosis.get("error_type", "unknown")
        category = diagnosis.get("category", "unknown")
        strategy = diagnosis.get("fix_strategy", "")
        fix_commands = diagnosis.get("fix_commands", [])
        extracted = diagnosis.get("extracted_info", {})
        path = diagnosis.get("extracted_path")

        commands_executed = []

        # Strategy-based fixes

        # === Use Sudo ===
        if strategy == "use_sudo" or error_type in [
            "permission_denied",
            "operation_not_permitted",
            "access_denied",
        ]:
            if not cmd.strip().startswith("sudo"):
                console.print("[dim]   Adding sudo...[/dim]")
                return True, "Will retry with sudo", []

        # === Create Path ===
        if strategy == "create_path" or error_type == "not_found":
            missing_path = path or extracted.get("missing_path")

            if missing_path:
                parent_dir = os.path.dirname(missing_path)

                if parent_dir and not os.path.exists(parent_dir):
                    console.print(f"[dim]   Creating directory: {parent_dir}[/dim]")
                    mkdir_cmd = f"sudo mkdir -p {parent_dir}"
                    success, _, mkdir_err = self._execute_command(mkdir_cmd)
                    commands_executed.append(mkdir_cmd)

                    if success:
                        return True, f"Created directory {parent_dir}", commands_executed
                    else:
                        return False, f"Failed to create directory: {mkdir_err}", commands_executed

        # === Install Package ===
        if strategy == "install_package" or error_type == "command_not_found":
            missing_cmd = extracted.get(
                "missing_command"
            ) or self.diagnoser.extract_command_from_error(stderr)
            if not missing_cmd:
                missing_cmd = cmd.split()[0] if cmd.split() else ""

            suggested_pkg = UBUNTU_PACKAGE_MAP.get(missing_cmd, missing_cmd)

            if missing_cmd:
                console.print(f"[dim]   Installing package: {suggested_pkg}[/dim]")

                # Update repos first
                update_cmd = "sudo apt-get update"
                self._execute_command(update_cmd)
                commands_executed.append(update_cmd)

                # Install package
                install_cmd = f"sudo apt-get install -y {suggested_pkg}"
                success, _, install_err = self._execute_command(install_cmd)
                commands_executed.append(install_cmd)

                if success:
                    return True, f"Installed {suggested_pkg}", commands_executed
                else:
                    # Try without suggested package mapping
                    if suggested_pkg != missing_cmd:
                        install_cmd2 = f"sudo apt-get install -y {missing_cmd}"
                        success, _, _ = self._execute_command(install_cmd2)
                        commands_executed.append(install_cmd2)
                        if success:
                            return True, f"Installed {missing_cmd}", commands_executed

                    return False, f"Failed to install: {install_err[:100]}", commands_executed

        # === Clear Package Lock ===
        if strategy == "clear_lock" or error_type in [
            "dpkg_lock",
            "apt_lock",
            "could_not_get_lock",
        ]:
            console.print("[dim]   Clearing package locks...[/dim]")

            lock_cmds = [
                "sudo rm -f /var/lib/dpkg/lock-frontend",
                "sudo rm -f /var/lib/dpkg/lock",
                "sudo rm -f /var/cache/apt/archives/lock",
                "sudo dpkg --configure -a",
            ]

            for lock_cmd in lock_cmds:
                self._execute_command(lock_cmd)
                commands_executed.append(lock_cmd)

            return True, "Cleared package locks", commands_executed

        # === Fix Dependencies ===
        if strategy in ["fix_dependencies", "fix_broken"]:
            console.print("[dim]   Fixing package dependencies...[/dim]")

            fix_cmds = [
                "sudo apt-get install -f -y",
                "sudo dpkg --configure -a",
            ]

            for fix_cmd in fix_cmds:
                success, _, _ = self._execute_command(fix_cmd)
                commands_executed.append(fix_cmd)

            return True, "Attempted dependency fix", commands_executed

        # === Start Service ===
        if strategy in ["start_service", "check_service"] or error_type in [
            "service_inactive",
            "service_not_running",
        ]:
            service = extracted.get("service")

            if service:
                console.print(f"[dim]   Starting service: {service}[/dim]")
                start_cmd = f"sudo systemctl start {service}"
                success, _, start_err = self._execute_command(start_cmd)
                commands_executed.append(start_cmd)

                if success:
                    return True, f"Started service {service}", commands_executed
                else:
                    # Try enable --now
                    enable_cmd = f"sudo systemctl enable --now {service}"
                    success, _, _ = self._execute_command(enable_cmd)
                    commands_executed.append(enable_cmd)
                    if success:
                        return True, f"Enabled and started {service}", commands_executed
                    return False, f"Failed to start {service}: {start_err[:100]}", commands_executed

        # === Unmask Service ===
        if strategy == "unmask_service" or error_type == "service_masked":
            service = extracted.get("service")

            if service:
                console.print(f"[dim]   Unmasking service: {service}[/dim]")
                unmask_cmd = f"sudo systemctl unmask {service}"
                success, _, _ = self._execute_command(unmask_cmd)
                commands_executed.append(unmask_cmd)

                if success:
                    start_cmd = f"sudo systemctl start {service}"
                    self._execute_command(start_cmd)
                    commands_executed.append(start_cmd)
                    return True, f"Unmasked and started {service}", commands_executed

        # === Free Disk Space ===
        if strategy == "free_disk" or error_type == "no_space":
            console.print("[dim]   Cleaning up disk space...[/dim]")

            cleanup_cmds = [
                "sudo apt-get clean",
                "sudo apt-get autoremove -y",
                "sudo journalctl --vacuum-size=100M",
            ]

            for cleanup_cmd in cleanup_cmds:
                self._execute_command(cleanup_cmd)
                commands_executed.append(cleanup_cmd)

            return True, "Freed disk space", commands_executed

        # === Free Memory ===
        if strategy == "free_memory" or error_type in [
            "oom",
            "cannot_allocate",
            "memory_exhausted",
        ]:
            console.print("[dim]   Freeing memory...[/dim]")

            mem_cmds = [
                "sudo sync",
                "echo 3 | sudo tee /proc/sys/vm/drop_caches",
            ]

            for mem_cmd in mem_cmds:
                self._execute_command(mem_cmd)
                commands_executed.append(mem_cmd)

            return True, "Freed memory caches", commands_executed

        # === Fix Config Syntax (all config error types) ===
        config_error_types = [
            "config_syntax_error",
            "nginx_config_error",
            "nginx_syntax_error",
            "nginx_unexpected",
            "nginx_unknown_directive",
            "nginx_test_failed",
            "apache_syntax_error",
            "apache_config_error",
            "config_line_error",
            "mysql_config_error",
            "postgres_config_error",
            "generic_config_syntax",
            "invalid_config",
            "config_parse_error",
            "syntax_error",
        ]

        if error_type in config_error_types or category == "config":
            config_file = extracted.get("config_file")
            line_num = extracted.get("line_num")

            # Try to extract config file/line from error if not already done
            if not config_file:
                config_file, line_num = self.diagnoser.extract_config_file_and_line(stderr)

            if config_file and line_num:
                console.print(f"[dim]   Config error at {config_file}:{line_num}[/dim]")
                fixed, msg = self.fix_config_syntax(config_file, line_num, stderr, cmd)
                if fixed:
                    # Verify the fix (e.g., nginx -t)
                    if "nginx" in error_type or "nginx" in cmd.lower():
                        verify_cmd = "sudo nginx -t"
                        v_success, _, v_stderr = self._execute_command(verify_cmd)
                        commands_executed.append(verify_cmd)
                        if v_success:
                            return True, f"{msg} - nginx config now valid", commands_executed
                        else:
                            console.print("[yellow]   Config still has errors[/yellow]")
                            # Re-diagnose for next iteration
                            return False, f"{msg} but still has errors", commands_executed
                    return True, msg, commands_executed
                else:
                    return False, msg, commands_executed
            else:
                # Can't find specific line, provide general guidance
                if "nginx" in error_type or "nginx" in cmd.lower():
                    console.print("[dim]   Testing nginx config...[/dim]")
                    test_cmd = "sudo nginx -t 2>&1"
                    success, stdout, test_err = self._execute_command(test_cmd)
                    commands_executed.append(test_cmd)
                    if not success:
                        # Try to extract file/line from test output
                        cf, ln = self.diagnoser.extract_config_file_and_line(test_err)
                        if cf and ln:
                            fixed, msg = self.fix_config_syntax(cf, ln, test_err, cmd)
                            if fixed:
                                return True, msg, commands_executed
                return False, "Could not identify config file/line to fix", commands_executed

        # === Network Fixes ===
        if category == "network":
            if strategy == "check_dns" or error_type in [
                "dns_temp_fail",
                "dns_unknown",
                "dns_failed",
            ]:
                console.print("[dim]   Restarting DNS resolver...[/dim]")
                dns_cmd = "sudo systemctl restart systemd-resolved"
                success, _, _ = self._execute_command(dns_cmd)
                commands_executed.append(dns_cmd)
                if success:
                    return True, "Restarted DNS resolver", commands_executed

            if strategy == "find_port_user" or error_type == "address_in_use":
                port = extracted.get("port")
                if port:
                    console.print(f"[dim]   Port {port} in use, checking...[/dim]")
                    lsof_cmd = f"sudo lsof -i :{port}"
                    success, stdout, _ = self._execute_command(lsof_cmd)
                    commands_executed.append(lsof_cmd)
                    if stdout:
                        console.print(f"[dim]   Process using port: {stdout[:100]}[/dim]")
                    return (
                        False,
                        f"Port {port} is in use - kill the process first",
                        commands_executed,
                    )

        # === Remount Read-Write ===
        if strategy == "remount_rw" or error_type == "readonly_fs":
            if path:
                console.print("[dim]   Remounting filesystem read-write...[/dim]")
                # Find mount point
                mount_point = "/"
                check_path = os.path.abspath(path) if path else "/"
                while check_path != "/":
                    if os.path.ismount(check_path):
                        mount_point = check_path
                        break
                    check_path = os.path.dirname(check_path)

                remount_cmd = f"sudo mount -o remount,rw {mount_point}"
                success, _, remount_err = self._execute_command(remount_cmd)
                commands_executed.append(remount_cmd)
                if success:
                    return True, f"Remounted {mount_point} read-write", commands_executed

        # === Fix Symlink Loop ===
        if strategy == "fix_symlink" or error_type == "symlink_loop":
            if path:
                console.print(f"[dim]   Fixing symlink: {path}[/dim]")
                # Check if it's a broken symlink
                if os.path.islink(path):
                    rm_cmd = f"sudo rm {path}"
                    success, _, _ = self._execute_command(rm_cmd)
                    commands_executed.append(rm_cmd)
                    if success:
                        return True, f"Removed broken symlink {path}", commands_executed

        # === Wait and Retry ===
        if strategy == "wait_retry" or error_type in [
            "resource_unavailable",
            "text_file_busy",
            "device_busy",
        ]:
            import time

            console.print("[dim]   Waiting for resource...[/dim]")
            time.sleep(2)
            return True, "Waited 2 seconds", commands_executed

        # === Use xargs for long argument lists ===
        if strategy == "use_xargs" or error_type == "arg_list_too_long":
            console.print("[dim]   Argument list too long - need to use xargs or loop[/dim]")
            return False, "Use xargs or a loop to process files in batches", commands_executed

        # === Execute provided fix commands ===
        if fix_commands:
            console.print("[dim]   Executing fix commands...[/dim]")
            for fix_cmd in fix_commands:
                if fix_cmd.startswith("#"):
                    continue  # Skip comments
                success, stdout, err = self._execute_command(fix_cmd)
                commands_executed.append(fix_cmd)
                if not success and err:
                    console.print(f"[dim]   Warning: {fix_cmd} failed: {err[:50]}[/dim]")

            if commands_executed:
                return True, f"Executed {len(commands_executed)} fix commands", commands_executed

        # === Try LLM-based fix if available ===
        if self.llm_callback and error_type == "unknown":
            console.print("[dim]   Using AI to diagnose error...[/dim]")
            llm_fix = self._get_llm_fix(cmd, stderr, diagnosis)
            if llm_fix:
                fix_commands = llm_fix.get("fix_commands", [])
                reasoning = llm_fix.get("reasoning", "AI-suggested fix")

                if fix_commands:
                    console.print(f"[cyan]   🤖 AI diagnosis: {reasoning}[/cyan]")
                    for fix_cmd in fix_commands:
                        if self._is_fix_attempted(cmd, fix_cmd):
                            console.print(f"[dim]   Skipping (already tried): {fix_cmd}[/dim]")
                            continue

                        console.print(f"[dim]   Executing: {fix_cmd}[/dim]")
                        self._mark_fix_attempted(cmd, fix_cmd)

                        needs_sudo = fix_cmd.strip().startswith("sudo") or "docker" in fix_cmd
                        success, stdout, stderr = self._execute_command(
                            fix_cmd, needs_sudo=needs_sudo
                        )
                        commands_executed.append(fix_cmd)

                        if success:
                            console.print(f"[green]   ✓ Fixed: {fix_cmd}[/green]")
                            return True, reasoning, commands_executed

                    if commands_executed:
                        return True, "Executed AI-suggested fixes", commands_executed

        # === Fallback: try with sudo ===
        if not cmd.strip().startswith("sudo"):
            console.print("[dim]   Fallback: will try with sudo...[/dim]")
            return True, "Will retry with sudo", []

        return False, f"No fix strategy for {error_type}", commands_executed

    def fix_config_syntax(
        self,
        config_file: str,
        line_num: int,
        stderr: str,
        original_cmd: str,
    ) -> tuple[bool, str]:
        """Fix configuration file syntax errors."""
        console.print(f"[dim]   Analyzing config: {config_file}:{line_num}[/dim]")

        # Read the config file
        success, config_content, read_err = self._execute_command(f"sudo cat {config_file}")
        if not success or not config_content:
            return False, f"Could not read {config_file}: {read_err}"

        lines = config_content.split("\n")
        if line_num > len(lines) or line_num < 1:
            return False, f"Invalid line number {line_num}"

        problem_line = lines[line_num - 1]
        console.print(f"[dim]   Line {line_num}: {problem_line.strip()[:60]}...[/dim]")

        stderr_lower = stderr.lower()

        # Duplicate entry
        if "duplicate" in stderr_lower:
            console.print("[cyan]   Commenting out duplicate entry...[/cyan]")
            fix_cmd = f"sudo sed -i '{line_num}s/^/# DUPLICATE: /' {config_file}"
            success, _, _ = self._execute_command(fix_cmd)
            if success:
                return True, f"Commented out duplicate at line {line_num}"

        # Missing semicolon (for nginx, etc.)
        if "unexpected" in stderr_lower or "expecting" in stderr_lower:
            stripped = problem_line.strip()
            if stripped and not stripped.endswith((";", "{", "}", ":", ",", "#", ")")):
                console.print("[cyan]   Adding missing semicolon...[/cyan]")
                escaped_line = stripped.replace("/", "\\/").replace("&", "\\&")
                fix_cmd = f"sudo sed -i '{line_num}s/.*/    {escaped_line};/' {config_file}"
                success, _, _ = self._execute_command(fix_cmd)
                if success:
                    return True, f"Added semicolon at line {line_num}"

        # Unknown directive
        if "unknown" in stderr_lower and ("directive" in stderr_lower or "option" in stderr_lower):
            console.print("[cyan]   Commenting out unknown directive...[/cyan]")
            fix_cmd = f"sudo sed -i '{line_num}s/^/# UNKNOWN: /' {config_file}"
            success, _, _ = self._execute_command(fix_cmd)
            if success:
                return True, f"Commented out unknown directive at line {line_num}"

        # Invalid value/argument
        if "invalid" in stderr_lower:
            console.print("[cyan]   Commenting out line with invalid value...[/cyan]")
            fix_cmd = f"sudo sed -i '{line_num}s/^/# INVALID: /' {config_file}"
            success, _, _ = self._execute_command(fix_cmd)
            if success:
                return True, f"Commented out invalid line at line {line_num}"

        # Unterminated string
        if "unterminated" in stderr_lower or ("string" in stderr_lower and "quote" in stderr_lower):
            if problem_line.count('"') % 2 == 1:
                console.print("[cyan]   Adding missing double quote...[/cyan]")
                fix_cmd = f"sudo sed -i '{line_num}s/$/\"/' {config_file}"
                success, _, _ = self._execute_command(fix_cmd)
                if success:
                    return True, f"Added missing quote at line {line_num}"
            elif problem_line.count("'") % 2 == 1:
                console.print("[cyan]   Adding missing single quote...[/cyan]")
                fix_cmd = f'sudo sed -i "{line_num}s/$/\'/" {config_file}'
                success, _, _ = self._execute_command(fix_cmd)
                if success:
                    return True, f"Added missing quote at line {line_num}"

        # Fallback: comment out problematic line
        console.print("[cyan]   Fallback: commenting out problematic line...[/cyan]")
        fix_cmd = f"sudo sed -i '{line_num}s/^/# ERROR: /' {config_file}"
        success, _, _ = self._execute_command(fix_cmd)
        if success:
            return True, f"Commented out problematic line {line_num}"

        return False, "Could not identify a fix for this config error"


# ============================================================================
# Utility Functions
# ============================================================================


def get_error_category(error_type: str) -> str:
    """Get the category for an error type."""
    for pattern in ALL_ERROR_PATTERNS:
        if pattern.error_type == error_type:
            return pattern.category
    return "unknown"


def get_severity(error_type: str) -> str:
    """Get the severity for an error type."""
    for pattern in ALL_ERROR_PATTERNS:
        if pattern.error_type == error_type:
            return pattern.severity
    return "error"


def is_critical_error(error_type: str) -> bool:
    """Check if an error type is critical."""
    return get_severity(error_type) == "critical"
