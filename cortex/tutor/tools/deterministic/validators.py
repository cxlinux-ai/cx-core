"""
Validators - Deterministic input validation for Intelligent Tutor.

Provides security-focused validation functions following Cortex patterns.
No LLM calls - pure rule-based validation.
"""

import re

# Maximum input length to prevent abuse
MAX_INPUT_LENGTH = 1000
MAX_PACKAGE_NAME_LENGTH = 100
MAX_QUESTION_LENGTH = 2000

# Blocked patterns for security (following Cortex TESTING.md)
BLOCKED_PATTERNS = [
    r"rm\s+-rf",  # Destructive file operations
    r"rm\s+-r\s+/",  # Root deletion
    r"mkfs\.",  # Filesystem formatting
    r"dd\s+if=",  # Disk operations
    r":\s*\(\)\s*\{",  # Fork bomb
    r">\s*/dev/sd",  # Direct disk writes
    r"chmod\s+-R\s+777",  # Unsafe permissions
    r"curl.*\|\s*sh",  # Pipe to shell
    r"wget.*\|\s*sh",  # Pipe to shell
    r"eval\s*\(",  # Eval injection
    r"exec\s*\(",  # Exec injection
    r"__import__",  # Python import injection
    r"subprocess",  # Subprocess calls
    r"os\.system",  # System calls
    r";\s*rm\s+",  # Command injection with rm
    r"&&\s*rm\s+",  # Command injection with rm
    r"\|\s*rm\s+",  # Pipe to rm
]

# Valid package name pattern (alphanumeric, hyphens, underscores, dots)
VALID_PACKAGE_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")

# Common package categories for validation hints
KNOWN_PACKAGE_CATEGORIES = [
    "system",  # apt, systemctl, journalctl
    "development",  # git, docker, npm, pip
    "database",  # postgresql, mysql, redis, mongodb
    "web",  # nginx, apache, curl, wget
    "security",  # ufw, fail2ban, openssl
    "networking",  # ssh, netstat, iptables
    "utilities",  # vim, tmux, htop, grep
]


def validate_package_name(package_name: str) -> tuple[bool, str | None]:
    """
    Validate a package name for safety and format.

    Args:
        package_name: The package name to validate.

    Returns:
        Tuple of (is_valid, error_message).
        If valid, error_message is None.

    Examples:
        >>> validate_package_name("docker")
        (True, None)
        >>> validate_package_name("rm -rf /")
        (False, "Package name contains blocked pattern")
        >>> validate_package_name("")
        (False, "Package name cannot be empty")
    """
    # Check for empty input
    if not package_name or not package_name.strip():
        return False, "Package name cannot be empty"

    package_name = package_name.strip()

    # Check length
    if len(package_name) > MAX_PACKAGE_NAME_LENGTH:
        return False, f"Package name too long (max {MAX_PACKAGE_NAME_LENGTH} characters)"

    # Check for blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, package_name, re.IGNORECASE):
            return False, "Package name contains blocked pattern"

    # Check valid format
    if not VALID_PACKAGE_PATTERN.match(package_name):
        return (
            False,
            "Package name must start with alphanumeric and contain only letters, "
            "numbers, dots, hyphens, and underscores",
        )

    return True, None


def validate_input(
    input_text: str,
    max_length: int = MAX_INPUT_LENGTH,
    allow_empty: bool = False,
) -> tuple[bool, str | None]:
    """
    Validate general user input for safety.

    Args:
        input_text: The input text to validate.
        max_length: Maximum allowed length.
        allow_empty: Whether empty input is allowed.

    Returns:
        Tuple of (is_valid, error_message).

    Examples:
        >>> validate_input("What is Docker?")
        (True, None)
        >>> validate_input("rm -rf / && steal_data")
        (False, "Input contains blocked pattern")
    """
    # Check for empty
    if not input_text or not input_text.strip():
        if allow_empty:
            return True, None
        return False, "Input cannot be empty"

    input_text = input_text.strip()

    # Check length
    if len(input_text) > max_length:
        return False, f"Input too long (max {max_length} characters)"

    # Check for blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, input_text, re.IGNORECASE):
            return False, "Input contains blocked pattern"

    return True, None


def validate_question(question: str) -> tuple[bool, str | None]:
    """
    Validate a user question for the Q&A system.

    Args:
        question: The question to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    return validate_input(question, max_length=MAX_QUESTION_LENGTH, allow_empty=False)


def validate_topic(topic: str) -> tuple[bool, str | None]:
    """
    Validate a topic name.

    Args:
        topic: The topic name to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not topic or not topic.strip():
        return False, "Topic cannot be empty"

    topic = topic.strip()

    if len(topic) > 200:
        return False, "Topic name too long (max 200 characters)"

    # Topics can have more characters than package names
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\s._-]*$", topic):
        return False, "Topic contains invalid characters"

    return True, None


def validate_score(score: float) -> tuple[bool, str | None]:
    """
    Validate a score value.

    Args:
        score: The score to validate (should be 0.0 to 1.0).

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not isinstance(score, (int, float)):
        return False, "Score must be a number"

    if score < 0.0 or score > 1.0:
        return False, "Score must be between 0.0 and 1.0"

    return True, None


def validate_learning_style(style: str) -> tuple[bool, str | None]:
    """
    Validate a learning style preference.

    Args:
        style: The learning style to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    valid_styles = ["visual", "reading", "hands-on"]

    if not style or style.lower() not in valid_styles:
        return False, f"Learning style must be one of: {', '.join(valid_styles)}"

    return True, None


def sanitize_input(input_text: str | None) -> str:
    """
    Sanitize user input by removing potentially dangerous content.

    Args:
        input_text: The input to sanitize (can be None).

    Returns:
        Sanitized input string.
    """
    if not input_text:
        return ""

    # Strip whitespace
    sanitized = input_text.strip()

    # Remove null bytes
    sanitized = sanitized.replace("\x00", "")

    # Limit length
    if len(sanitized) > MAX_INPUT_LENGTH:
        sanitized = sanitized[:MAX_INPUT_LENGTH]

    return sanitized


def extract_package_name(input_text: str | None) -> str | None:
    """
    Extract a potential package name from user input.

    Args:
        input_text: User input that may contain a package name (can be None).

    Returns:
        Extracted package name or None.

    Examples:
        >>> extract_package_name("Tell me about docker")
        'docker'
        >>> extract_package_name("How do I use nginx?")
        'nginx'
    """
    if not input_text:
        return None

    # Common patterns for package references
    patterns = [
        r"about\s+(\w[\w.-]*)",  # "about docker"
        r"learn\s+(\w[\w.-]*)",  # "learn git"
        r"teach\s+(?:me\s+)?(\w[\w.-]*)",  # "teach me python"
        r"explain\s+(\w[\w.-]*)",  # "explain nginx"
        r"how\s+(?:to\s+)?use\s+(\w[\w.-]*)",  # "how to use curl"
        r"what\s+is\s+(\w[\w.-]*)",  # "what is redis"
        r"^(\w[\w.-]*)$",  # Just the package name
    ]

    for pattern in patterns:
        match = re.search(pattern, input_text, re.IGNORECASE)
        if match:
            candidate = match.group(1)
            is_valid, _ = validate_package_name(candidate)
            if is_valid:
                return candidate.lower()

    return None


def get_validation_errors(
    package_name: str | None = None,
    topic: str | None = None,
    question: str | None = None,
    score: float | None = None,
) -> list[str]:
    """
    Validate multiple inputs and return all errors.

    Args:
        package_name: Optional package name to validate.
        topic: Optional topic to validate.
        question: Optional question to validate.
        score: Optional score to validate.

    Returns:
        List of error messages (empty if all valid).
    """
    errors = []

    if package_name is not None:
        is_valid, error = validate_package_name(package_name)
        if not is_valid:
            errors.append(f"Package name: {error}")

    if topic is not None:
        is_valid, error = validate_topic(topic)
        if not is_valid:
            errors.append(f"Topic: {error}")

    if question is not None:
        is_valid, error = validate_question(question)
        if not is_valid:
            errors.append(f"Question: {error}")

    if score is not None:
        is_valid, error = validate_score(score)
        if not is_valid:
            errors.append(f"Score: {error}")

    return errors


class ValidationResult:
    """Result of a validation operation."""

    def __init__(self, is_valid: bool, errors: list[str] | None = None) -> None:
        """
        Initialize validation result.

        Args:
            is_valid: Whether validation passed.
            errors: List of error messages if validation failed.
        """
        self.is_valid = is_valid
        self.errors = errors or []

    def __bool__(self) -> bool:
        """Return True if validation passed."""
        return self.is_valid

    def __str__(self) -> str:
        """Return string representation."""
        if self.is_valid:
            return "Validation passed"
        return f"Validation failed: {'; '.join(self.errors)}"


def validate_all(
    package_name: str | None = None,
    topic: str | None = None,
    question: str | None = None,
    score: float | None = None,
) -> ValidationResult:
    """
    Validate all provided inputs and return a ValidationResult.

    Args:
        package_name: Optional package name to validate.
        topic: Optional topic to validate.
        question: Optional question to validate.
        score: Optional score to validate.

    Returns:
        ValidationResult with is_valid and errors.
    """
    errors = get_validation_errors(package_name, topic, question, score)
    return ValidationResult(is_valid=len(errors) == 0, errors=errors)
