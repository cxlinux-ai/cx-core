"""
Cortex Input Validators

Validates user input and provides helpful error messages.
"""

import os
import re
from typing import Optional, Tuple


class ValidationError(Exception):
    """Custom exception for validation errors with user-friendly messages"""

    def __init__(self, message: str, suggestion: Optional[str] = None):
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


def validate_api_key() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate that an API key is configured.

    Returns:
        Tuple of (is_valid, provider, error_message)
    """
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
    openai_key = os.environ.get('OPENAI_API_KEY')

    if anthropic_key:
        if not anthropic_key.startswith('sk-ant-'):
            return (False, None, "ANTHROPIC_API_KEY doesn't look valid (should start with 'sk-ant-')")
        return (True, 'claude', None)

    if openai_key:
        if not openai_key.startswith('sk-'):
            return (False, None, "OPENAI_API_KEY doesn't look valid (should start with 'sk-')")
        return (True, 'openai', None)

    return (False, None, "No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.")


def validate_package_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a package name for safety.

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check for shell injection attempts
    dangerous_chars = [';', '|', '&', '$', '`', '(', ')', '{', '}', '<', '>', '\n', '\r']

    for char in dangerous_chars:
        if char in name:
            return (False, f"Package name contains invalid character: '{char}'")

    # Check for path traversal
    if '..' in name or name.startswith('/'):
        return (False, "Package name cannot contain path components")

    # Check reasonable length
    if len(name) > 200:
        return (False, "Package name is too long (max 200 characters)")

    if len(name) < 1:
        return (False, "Package name cannot be empty")

    return (True, None)


def validate_install_request(request: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a natural language install request.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not request or not request.strip():
        return (False, "Install request cannot be empty")

    # Check for excessively long requests
    if len(request) > 1000:
        return (False, "Install request is too long (max 1000 characters)")

    # Check for obvious shell injection in natural language
    shell_patterns = [
        r';\s*rm\s',
        r';\s*sudo\s',
        r'\|\s*bash',
        r'\$\(',
        r'`[^`]+`',
    ]

    for pattern in shell_patterns:
        if re.search(pattern, request, re.IGNORECASE):
            return (False, "Install request contains potentially unsafe patterns")

    return (True, None)


def validate_installation_id(install_id: str) -> Tuple[bool, Optional[str]]:
    """
    Validate an installation ID format.

    Returns:
        Tuple of (is_valid, error_message)
    """
    # IDs should be alphanumeric with dashes (UUID-like)
    if not re.match(r'^[a-zA-Z0-9\-_]+$', install_id):
        return (False, "Invalid installation ID format")

    if len(install_id) > 100:
        return (False, "Installation ID is too long")

    return (True, None)


def sanitize_command(command: str) -> str:
    """
    Sanitize a command for safe display (not execution).
    Masks sensitive information like API keys.

    Args:
        command: The command string to sanitize

    Returns:
        Sanitized command string
    """
    # Mask API keys in output
    sanitized = re.sub(
        r'(ANTHROPIC_API_KEY|OPENAI_API_KEY)=\S+',
        r'\1=***',
        command
    )

    # Mask bearer tokens
    sanitized = re.sub(
        r'Bearer\s+\S+',
        'Bearer ***',
        sanitized
    )

    return sanitized
