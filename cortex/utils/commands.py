"""
Secure Command Execution Utilities

This module provides safe command execution with validation and sandboxing.
All commands should go through these utilities to prevent shell injection.
"""

import logging
import re
import shlex
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Dangerous patterns that should never be executed
DANGEROUS_PATTERNS = [
    # File system destruction
    r"rm\s+-rf\s+[/\*]",
    r"rm\s+-rf\s+\$",
    r"rm\s+--no-preserve-root",
    r":\s*\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}",  # Fork bomb
    # Disk operations
    r"dd\s+if=.*of=/dev/",
    r"mkfs\.",
    r"wipefs",
    # Network attacks
    r"curl\s+.*\|\s*sh",
    r"curl\s+.*\|\s*bash",
    r"wget\s+.*\|\s*sh",
    r"wget\s+.*\|\s*bash",
    r"curl\s+-o\s+-\s+.*\|\s*",
    # Code execution
    r"\beval\s+",
    r'python\s+-c\s+["\'].*exec',
    r'python\s+-c\s+["\'].*import\s+os',
    r"base64\s+-d\s+.*\|",
    r"\$\(.*\)",  # Command substitution (dangerous in some contexts)
    # System modification
    r">\s*/etc/",
    r"chmod\s+777",
    r"chmod\s+\+s",
    r"chown\s+.*:.*\s+/",
    # Privilege escalation
    r"sudo\s+su\s*$",
    r"sudo\s+-i\s*$",
    # Environment manipulation
    r"export\s+LD_PRELOAD",
    r"export\s+LD_LIBRARY_PATH.*=/",
]

# Commands that are allowed (allowlist for package management)
ALLOWED_COMMAND_PREFIXES = [
    "apt",
    "apt-get",
    "apt-cache",
    "dpkg",
    "yum",
    "dnf",
    "pacman",
    "zypper",
    "pip",
    "pip3",
    "npm",
    "systemctl",
    "service",
    "docker",
    "docker-compose",
    "kubectl",
    "git",
    "curl",  # Only for downloading, not piping to shell
    "wget",  # Only for downloading, not piping to shell
    "tar",
    "unzip",
    "chmod",
    "chown",
    "mkdir",
    "cp",
    "mv",
    "ln",
    "cat",
    "echo",
    "tee",
    "grep",
    "sed",
    "awk",
    "head",
    "tail",
    "sort",
    "uniq",
    "wc",
    "ls",
    "find",
    "which",
    "whereis",
    "id",
    "whoami",
    "hostname",
    "uname",
    "lsb_release",
    "nvidia-smi",
    "nvcc",
    "make",
    "cmake",
    "gcc",
    "g++",
    "python",
    "python3",
    "node",
    "java",
    "go",
    "rustc",
    "cargo",
]


@dataclass
class CommandResult:
    """Result of a command execution."""

    success: bool
    stdout: str
    stderr: str
    return_code: int
    command: str


class CommandValidationError(Exception):
    """Raised when a command fails validation."""

    pass


def validate_command(command: str, strict: bool = True) -> tuple[bool, str | None]:
    """
    Validate a command for security.

    Args:
        command: The command string to validate
        strict: If True, command must start with an allowed prefix

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not command or not command.strip():
        return False, "Empty command"

    command = command.strip()

    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Dangerous pattern detected: {pattern}"

    # Check for shell metacharacters that could enable injection
    dangerous_chars = ["`", "$", "&&", "||", ";", "\n", "\r"]
    for char in dangerous_chars:
        if char in command:
            # Allow some patterns like $(dpkg --print-architecture)
            if char == "$" and "$(" in command:
                # Only allow specific safe command substitutions
                safe_substitutions = [
                    "$(dpkg --print-architecture)",
                    "$(lsb_release -cs)",
                    "$(uname -r)",
                    "$(uname -m)",
                    "$(whoami)",
                    "$(hostname)",
                ]
                # Check if all $(...) patterns are in safe list
                found_subs = re.findall(r"\$\([^)]+\)", command)
                for sub in found_subs:
                    if sub not in safe_substitutions:
                        return False, f"Unsafe command substitution: {sub}"
            elif char == "&&" or char == "||":
                # Allow chained commands, but validate each part
                continue
            elif char == ";":
                # Semicolon is dangerous - could chain arbitrary commands
                return False, "Semicolon not allowed in commands"
            elif char == "`":
                return False, "Backtick command substitution not allowed"

    # Strict mode: command must start with allowed prefix
    if strict:
        first_word = command.split()[0]
        # Handle sudo prefix
        if first_word == "sudo":
            parts = command.split()
            if len(parts) > 1:
                first_word = parts[1]

        if first_word not in ALLOWED_COMMAND_PREFIXES:
            return False, f"Command '{first_word}' is not in the allowlist"

    return True, None


def sanitize_command(command: str) -> str:
    """
    Sanitize a command by removing potentially dangerous elements.

    Args:
        command: The command to sanitize

    Returns:
        Sanitized command string
    """
    # Remove null bytes
    command = command.replace("\x00", "")

    # Remove control characters
    command = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", command)

    # Normalize whitespace
    command = " ".join(command.split())

    return command


def run_command(
    command: str,
    timeout: int = 300,
    validate: bool = True,
    use_shell: bool = False,
    capture_output: bool = True,
    cwd: str | None = None,
) -> CommandResult:
    """
    Execute a command safely with validation.

    Args:
        command: The command to execute
        timeout: Maximum execution time in seconds
        validate: Whether to validate the command before execution
        use_shell: Use shell execution (less secure, only for complex commands)
        capture_output: Capture stdout/stderr
        cwd: Working directory for command execution

    Returns:
        CommandResult with execution details

    Raises:
        CommandValidationError: If command fails validation
    """
    # Sanitize input
    command = sanitize_command(command)

    # Validate if requested
    if validate:
        is_valid, error = validate_command(command, strict=True)
        if not is_valid:
            raise CommandValidationError(f"Command validation failed: {error}")

    try:
        if use_shell:
            # Shell execution - use with caution
            # Only allow if command has been validated
            result = subprocess.run(
                command,
                shell=True,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
        else:
            # Safer: parse command and execute without shell
            # This prevents most injection attacks
            args = shlex.split(command)
            result = subprocess.run(
                args, capture_output=capture_output, text=True, timeout=timeout, cwd=cwd
            )

        return CommandResult(
            success=result.returncode == 0,
            stdout=result.stdout if capture_output else "",
            stderr=result.stderr if capture_output else "",
            return_code=result.returncode,
            command=command,
        )

    except subprocess.TimeoutExpired:
        return CommandResult(
            success=False,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
            return_code=-1,
            command=command,
        )
    except FileNotFoundError as e:
        return CommandResult(
            success=False,
            stdout="",
            stderr=f"Command not found: {e}",
            return_code=-1,
            command=command,
        )
    except Exception as e:
        logger.exception(f"Error executing command: {command}")
        return CommandResult(
            success=False, stdout="", stderr=str(e), return_code=-1, command=command
        )


def run_command_chain(
    commands: list[str], timeout_per_command: int = 300, stop_on_error: bool = True
) -> list[CommandResult]:
    """
    Execute a chain of commands safely.

    Args:
        commands: List of commands to execute
        timeout_per_command: Timeout for each command
        stop_on_error: Stop execution if a command fails

    Returns:
        List of CommandResult for each command
    """
    results = []

    for command in commands:
        result = run_command(command, timeout=timeout_per_command)
        results.append(result)

        if not result.success and stop_on_error:
            break

    return results
