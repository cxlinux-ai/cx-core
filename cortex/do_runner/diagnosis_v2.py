"""
Cortex Diagnosis System v2

A structured error diagnosis and resolution system with the following flow:
1. Categorize error type (file, login, package, syntax, input, etc.)
2. LLM generates fix commands with variable placeholders
3. Resolve variables from query, LLM, or system_info_generator
4. Execute fix commands and log output
5. If error, push to stack and repeat
6. Test original command, if still fails, repeat

Uses a stack-based approach for tracking command errors.
"""

import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

console = Console()


# =============================================================================
# ERROR CATEGORIES
# =============================================================================


class ErrorCategory(str, Enum):
    """Broad categories of errors that can occur during command execution."""

    # File & Directory Errors (LOCAL)
    FILE_NOT_FOUND = "file_not_found"
    FILE_EXISTS = "file_exists"
    DIRECTORY_NOT_FOUND = "directory_not_found"
    PERMISSION_DENIED_LOCAL = "permission_denied_local"  # Local file/dir permission
    READ_ONLY_FILESYSTEM = "read_only_filesystem"
    DISK_FULL = "disk_full"

    # URL/Link Permission Errors (REMOTE)
    PERMISSION_DENIED_URL = "permission_denied_url"  # URL/API permission
    ACCESS_DENIED_REGISTRY = "access_denied_registry"  # Container registry
    ACCESS_DENIED_REPO = "access_denied_repo"  # Git/package repo
    ACCESS_DENIED_API = "access_denied_api"  # API endpoint

    # Authentication & Login Errors
    LOGIN_REQUIRED = "login_required"
    AUTH_FAILED = "auth_failed"
    TOKEN_EXPIRED = "token_expired"
    INVALID_CREDENTIALS = "invalid_credentials"

    # Legacy - for backward compatibility
    PERMISSION_DENIED = "permission_denied"  # Will be resolved to LOCAL or URL

    # Package & Resource Errors
    PACKAGE_NOT_FOUND = "package_not_found"
    IMAGE_NOT_FOUND = "image_not_found"
    RESOURCE_NOT_FOUND = "resource_not_found"
    DEPENDENCY_MISSING = "dependency_missing"
    VERSION_CONFLICT = "version_conflict"

    # Command Errors
    COMMAND_NOT_FOUND = "command_not_found"
    SYNTAX_ERROR = "syntax_error"
    INVALID_ARGUMENT = "invalid_argument"
    MISSING_ARGUMENT = "missing_argument"
    DEPRECATED_SYNTAX = "deprecated_syntax"

    # Service & Process Errors
    SERVICE_NOT_RUNNING = "service_not_running"
    SERVICE_FAILED = "service_failed"
    PORT_IN_USE = "port_in_use"
    PROCESS_KILLED = "process_killed"
    TIMEOUT = "timeout"

    # Network Errors
    NETWORK_UNREACHABLE = "network_unreachable"
    CONNECTION_REFUSED = "connection_refused"
    DNS_FAILED = "dns_failed"
    SSL_ERROR = "ssl_error"

    # Configuration Errors
    CONFIG_SYNTAX_ERROR = "config_syntax_error"
    CONFIG_INVALID_VALUE = "config_invalid_value"
    CONFIG_MISSING_KEY = "config_missing_key"

    # Resource Errors
    OUT_OF_MEMORY = "out_of_memory"
    CPU_LIMIT = "cpu_limit"
    QUOTA_EXCEEDED = "quota_exceeded"

    # Unknown
    UNKNOWN = "unknown"


# Error pattern definitions for each category
ERROR_PATTERNS: dict[ErrorCategory, list[tuple[str, str]]] = {
    # File & Directory
    ErrorCategory.FILE_NOT_FOUND: [
        (r"No such file or directory", "file"),
        (r"cannot open '([^']+)'.*No such file", "file"),
        (r"stat\(\): cannot stat '([^']+)'", "file"),
        (r"File not found:? ([^\n]+)", "file"),
    ],
    ErrorCategory.FILE_EXISTS: [
        (r"File exists", "file"),
        (r"cannot create.*File exists", "file"),
    ],
    ErrorCategory.DIRECTORY_NOT_FOUND: [
        (r"No such file or directory:.*/$", "directory"),
        (r"cannot access '([^']+/)': No such file or directory", "directory"),
        (r"mkdir: cannot create directory '([^']+)'.*No such file", "parent_directory"),
    ],
    # Local file/directory permission denied
    ErrorCategory.PERMISSION_DENIED_LOCAL: [
        (r"Permission denied.*(/[^\s:]+)", "path"),
        (r"cannot open '([^']+)'.*Permission denied", "path"),
        (r"cannot create.*'([^']+)'.*Permission denied", "path"),
        (r"cannot access '([^']+)'.*Permission denied", "path"),
        (r"Operation not permitted.*(/[^\s:]+)", "path"),
        (r"EACCES.*(/[^\s]+)", "path"),
    ],
    # URL/Link permission denied (registries, APIs, repos)
    ErrorCategory.PERMISSION_DENIED_URL: [
        (r"403 Forbidden.*https?://([^\s/]+)", "host"),
        (r"401 Unauthorized.*https?://([^\s/]+)", "host"),
        (r"Access denied.*https?://([^\s/]+)", "host"),
    ],
    ErrorCategory.ACCESS_DENIED_REGISTRY: [
        (r"denied: requested access to the resource is denied", "registry"),
        (r"pull access denied", "registry"),  # Higher priority pattern
        (r"pull access denied for ([^\s,]+)", "image"),
        (r"unauthorized: authentication required.*registry", "registry"),
        (r"Error response from daemon.*denied", "registry"),
        (r"UNAUTHORIZED.*registry", "registry"),
        (r"unauthorized to access repository", "registry"),
    ],
    ErrorCategory.ACCESS_DENIED_REPO: [
        (r"Repository not found.*https?://([^\s]+)", "repo"),
        (r"fatal: could not read from remote repository", "repo"),
        (r"Permission denied \(publickey\)", "repo"),
        (r"Host key verification failed", "host"),
        (r"remote: Permission to ([^\s]+) denied", "repo"),
    ],
    ErrorCategory.ACCESS_DENIED_API: [
        (r"API.*access denied", "api"),
        (r"AccessDenied.*Access denied", "api"),  # AWS-style error
        (r"403.*API", "api"),
        (r"unauthorized.*api", "api"),
        (r"An error occurred \(AccessDenied\)", "api"),  # AWS CLI error
        (r"not authorized to perform", "api"),
    ],
    # Legacy pattern for generic permission denied
    ErrorCategory.PERMISSION_DENIED: [
        (r"Permission denied", "resource"),
        (r"Operation not permitted", "operation"),
        (r"Access denied", "resource"),
        (r"EACCES", "resource"),
    ],
    ErrorCategory.READ_ONLY_FILESYSTEM: [
        (r"Read-only file system", "filesystem"),
    ],
    ErrorCategory.DISK_FULL: [
        (r"No space left on device", "device"),
        (r"Disk quota exceeded", "quota"),
    ],
    # Authentication & Login
    ErrorCategory.LOGIN_REQUIRED: [
        (r"Login required", "service"),
        (r"Authentication required", "service"),
        (r"401 Unauthorized", "service"),
        (r"not logged in", "service"),
        (r"must be logged in", "service"),
        (r"Non-null Username Required", "service"),
    ],
    ErrorCategory.AUTH_FAILED: [
        (r"Authentication failed", "service"),
        (r"invalid username or password", "credentials"),
        (r"403 Forbidden", "access"),
        (r"access denied", "resource"),
    ],
    ErrorCategory.TOKEN_EXPIRED: [
        (r"token.*expired", "token"),
        (r"session expired", "session"),
        (r"credential.*expired", "credential"),
    ],
    ErrorCategory.INVALID_CREDENTIALS: [
        (r"invalid.*credentials?", "type"),
        (r"bad credentials", "type"),
        (r"incorrect password", "auth"),
    ],
    # Package & Resource
    ErrorCategory.PACKAGE_NOT_FOUND: [
        (r"Unable to locate package ([^\s]+)", "package"),
        (r"Package ([^\s]+) is not available", "package"),
        (r"No package ([^\s]+) available", "package"),
        (r"E: Package '([^']+)' has no installation candidate", "package"),
        (r"error: package '([^']+)' not found", "package"),
        (r"ModuleNotFoundError: No module named '([^']+)'", "module"),
    ],
    ErrorCategory.IMAGE_NOT_FOUND: [
        (r"manifest.*not found", "image"),
        (r"image.*not found", "image"),
        (r"repository does not exist", "repository"),
        (r"Error response from daemon: manifest for ([^\s]+) not found", "image"),
        # Note: "pull access denied" moved to ACCESS_DENIED_REGISTRY
    ],
    ErrorCategory.RESOURCE_NOT_FOUND: [
        (r"resource.*not found", "resource"),
        (r"404 Not Found", "url"),
        (r"could not find ([^\n]+)", "resource"),
        (r"No matching distribution found for ([^\s]+)", "package"),
        (r"Could not find a version that satisfies the requirement ([^\s]+)", "package"),
    ],
    ErrorCategory.DEPENDENCY_MISSING: [
        (r"Depends:.*but it is not going to be installed", "dependency"),
        (r"unmet dependencies", "packages"),
        (r"dependency.*not satisfied", "dependency"),
        (r"peer dep missing", "dependency"),
    ],
    ErrorCategory.VERSION_CONFLICT: [
        (r"version conflict", "packages"),
        (r"incompatible version", "version"),
        (r"requires.*but ([^\s]+) is installed", "conflict"),
    ],
    # Command Errors
    ErrorCategory.COMMAND_NOT_FOUND: [
        (r"command not found", "command"),
        (r"not found", "binary"),
        (r"is not recognized as", "command"),
        (r"Unknown command", "subcommand"),
    ],
    ErrorCategory.SYNTAX_ERROR: [
        (r"syntax error", "location"),
        (r"parse error", "location"),
        (r"unexpected token", "token"),
        (r"near unexpected", "token"),
    ],
    ErrorCategory.INVALID_ARGUMENT: [
        (r"invalid.*argument", "argument"),
        (r"unrecognized option", "option"),
        (r"unknown option", "option"),
        (r"illegal option", "option"),
        (r"bad argument", "argument"),
    ],
    ErrorCategory.MISSING_ARGUMENT: [
        (r"missing.*argument", "argument"),
        (r"requires.*argument", "argument"),
        (r"missing operand", "operand"),
        (r"option.*requires an argument", "option"),
    ],
    ErrorCategory.DEPRECATED_SYNTAX: [
        (r"deprecated", "feature"),
        (r"obsolete", "feature"),
        (r"use.*instead", "replacement"),
    ],
    # Service & Process
    ErrorCategory.SERVICE_NOT_RUNNING: [
        (r"is not running", "service"),
        (r"service.*stopped", "service"),
        (r"inactive \(dead\)", "service"),
        (r"Unit.*not found", "unit"),
        (r"Failed to connect to", "service"),
        (r"could not be found", "service"),
        (r"Unit ([^\s]+)\.service could not be found", "service"),
    ],
    ErrorCategory.SERVICE_FAILED: [
        (r"failed to start", "service"),
        (r"service.*failed", "service"),
        (r"Job.*failed", "job"),
        (r"Main process exited", "process"),
    ],
    ErrorCategory.PORT_IN_USE: [
        (r"Address already in use", "port"),
        (r"port.*already.*use", "port"),
        (r"bind\(\): Address already in use", "port"),
        (r"EADDRINUSE", "port"),
    ],
    ErrorCategory.PROCESS_KILLED: [
        (r"Killed", "signal"),
        (r"SIGKILL", "signal"),
        (r"Out of memory", "oom"),
    ],
    ErrorCategory.TIMEOUT: [
        (r"timed out", "operation"),
        (r"timeout", "operation"),
        (r"deadline exceeded", "operation"),
    ],
    # Network
    ErrorCategory.NETWORK_UNREACHABLE: [
        (r"Network is unreachable", "network"),
        (r"No route to host", "host"),
        (r"Could not resolve host", "host"),
    ],
    ErrorCategory.CONNECTION_REFUSED: [
        (r"Connection refused", "target"),
        (r"ECONNREFUSED", "target"),
        (r"couldn't connect to host", "host"),
    ],
    ErrorCategory.DNS_FAILED: [
        (r"Name or service not known", "hostname"),
        (r"Temporary failure in name resolution", "dns"),
        (r"DNS lookup failed", "hostname"),
    ],
    ErrorCategory.SSL_ERROR: [
        (r"SSL.*error", "ssl"),
        (r"certificate.*error", "certificate"),
        (r"CERT_", "certificate"),
    ],
    # Configuration
    ErrorCategory.CONFIG_SYNTAX_ERROR: [
        (r"configuration.*syntax.*error", "config"),
        (r"invalid configuration", "config"),
        (r"parse error in", "config"),
        (r"nginx:.*emerg.*", "nginx_config"),
        (r"Failed to parse", "config"),
    ],
    ErrorCategory.CONFIG_INVALID_VALUE: [
        (r"invalid value", "config"),
        (r"unknown directive", "directive"),
        (r"invalid parameter", "parameter"),
    ],
    ErrorCategory.CONFIG_MISSING_KEY: [
        (r"missing.*key", "key"),
        (r"required.*not set", "key"),
        (r"undefined variable", "variable"),
    ],
    # Resource
    ErrorCategory.OUT_OF_MEMORY: [
        (r"Out of memory", "memory"),
        (r"Cannot allocate memory", "memory"),
        (r"MemoryError", "memory"),
        (r"OOMKilled", "oom"),
    ],
    ErrorCategory.QUOTA_EXCEEDED: [
        (r"quota exceeded", "quota"),
        (r"limit reached", "limit"),
        (r"rate limit", "rate"),
    ],
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class DiagnosisResult:
    """Result of error diagnosis (Step 1)."""

    category: ErrorCategory
    error_message: str
    extracted_info: dict[str, str] = field(default_factory=dict)
    confidence: float = 1.0
    raw_stderr: str = ""


@dataclass
class FixCommand:
    """A single fix command with variable placeholders."""

    command_template: str  # Command with {variable} placeholders
    purpose: str
    variables: list[str] = field(default_factory=list)  # Variable names found
    requires_sudo: bool = False

    def __post_init__(self):
        # Extract variables from template
        self.variables = re.findall(r"\{(\w+)\}", self.command_template)


@dataclass
class FixPlan:
    """Plan for fixing an error (Step 2 output)."""

    category: ErrorCategory
    commands: list[FixCommand]
    reasoning: str
    all_variables: set[str] = field(default_factory=set)

    def __post_init__(self):
        # Collect all unique variables
        for cmd in self.commands:
            self.all_variables.update(cmd.variables)


@dataclass
class VariableResolution:
    """Resolution for a variable (Step 3)."""

    name: str
    value: str
    source: str  # "query", "llm", "system_info", "default"


@dataclass
class ExecutionResult:
    """Result of executing a fix command (Step 4)."""

    command: str
    success: bool
    stdout: str
    stderr: str
    execution_time: float


@dataclass
class ErrorStackEntry:
    """Entry in the error stack for tracking."""

    original_command: str
    intent: str
    error: str
    category: ErrorCategory
    fix_plan: FixPlan | None = None
    fix_attempts: int = 0
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# DIAGNOSIS ENGINE
# =============================================================================


class DiagnosisEngine:
    """
    Main diagnosis engine implementing the structured error resolution flow.

    Flow:
    1. Categorize error type
    2. LLM generates fix commands with variables
    3. Resolve variables
    4. Execute fix commands
    5. If error, push to stack and repeat
    6. Test original command
    """

    MAX_FIX_ATTEMPTS = 5
    MAX_STACK_DEPTH = 10

    # Known URL/remote service patterns in commands
    URL_COMMAND_PATTERNS = [
        r"docker\s+(pull|push|login)",
        r"git\s+(clone|push|pull|fetch|remote)",
        r"npm\s+(publish|login|install.*@)",
        r"pip\s+install.*--index-url",
        r"curl\s+",
        r"wget\s+",
        r"aws\s+",
        r"gcloud\s+",
        r"kubectl\s+",
        r"helm\s+",
        r"az\s+",  # Azure CLI
        r"gh\s+",  # GitHub CLI
    ]

    # Known registries and their authentication services
    KNOWN_SERVICES = {
        "ghcr.io": "ghcr",
        "docker.io": "docker",
        "registry.hub.docker.com": "docker",
        "github.com": "git_https",
        "gitlab.com": "git_https",
        "bitbucket.org": "git_https",
        "registry.npmjs.org": "npm",
        "pypi.org": "pypi",
        "amazonaws.com": "aws",
        "gcr.io": "gcloud",
    }

    def __init__(
        self,
        api_key: str | None = None,
        provider: str = "claude",
        model: str | None = None,
        debug: bool = False,
    ):
        self.api_key = (
            api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        )
        self.provider = provider.lower()
        self.model = model or self._default_model()
        self.debug = debug

        # Error stack for tracking command errors
        self.error_stack: list[ErrorStackEntry] = []

        # Resolution cache to avoid re-resolving same variables
        self.variable_cache: dict[str, str] = {}

        # Execution history for logging
        self.execution_history: list[dict[str, Any]] = []

        # Initialize LoginHandler for credential management
        self._login_handler = None
        try:
            from cortex.do_runner.diagnosis import LoginHandler

            self._login_handler = LoginHandler()
        except ImportError:
            pass

        self._initialize_client()

    def _default_model(self) -> str:
        if self.provider == "openai":
            return "gpt-4o"
        elif self.provider == "claude":
            return "claude-sonnet-4-20250514"
        return "gpt-4o"

    def _initialize_client(self):
        """Initialize the LLM client."""
        if not self.api_key:
            console.print("[yellow]⚠ No API key found - LLM features disabled[/yellow]")
            self.client = None
            return

        if self.provider == "openai":
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                self.client = None
        elif self.provider == "claude":
            try:
                from anthropic import Anthropic

                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                self.client = None
        else:
            self.client = None

    # =========================================================================
    # PERMISSION TYPE DETECTION
    # =========================================================================

    def _is_url_based_permission_error(
        self, command: str, stderr: str
    ) -> tuple[bool, str | None, str | None]:
        """
        Determine if permission denied is for a local file/dir or a URL/link.

        Returns:
            Tuple of (is_url_based, service_name, url_or_host)
        """
        # Check if command involves known remote operations
        is_remote_command = any(
            re.search(pattern, command, re.IGNORECASE) for pattern in self.URL_COMMAND_PATTERNS
        )

        # Check stderr for URL patterns
        url_patterns = [
            r"https?://([^\s/]+)",
            r"([a-zA-Z0-9.-]+\.(io|com|org|net))",
            r"registry[.\s]",
            r"(ghcr\.io|docker\.io|gcr\.io|quay\.io)",
        ]

        found_host = None
        for pattern in url_patterns:
            match = re.search(pattern, stderr, re.IGNORECASE)
            if match:
                found_host = match.group(1) if match.groups() else match.group(0)
                break

        # Also check command for URLs/hosts
        if not found_host:
            for pattern in url_patterns:
                match = re.search(pattern, command, re.IGNORECASE)
                if match:
                    found_host = match.group(1) if match.groups() else match.group(0)
                    break

        # Determine service
        service = None
        if found_host:
            for host_pattern, svc in self.KNOWN_SERVICES.items():
                if host_pattern in found_host.lower():
                    service = svc
                    break

        # Detect service from command if not found from host
        if not service:
            if "git " in command.lower():
                service = "git_https"
                if not found_host:
                    found_host = "git remote"
            elif "aws " in command.lower():
                service = "aws"
                if not found_host:
                    found_host = "aws"
            elif "docker " in command.lower():
                service = "docker"
            elif "npm " in command.lower():
                service = "npm"

        # Git-specific patterns
        git_remote_patterns = [
            "remote:" in stderr.lower(),
            "permission to" in stderr.lower() and ".git" in stderr.lower(),
            "denied to" in stderr.lower(),
            "could not read from remote repository" in stderr.lower(),
            "fatal: authentication failed" in stderr.lower(),
        ]

        # AWS-specific patterns
        aws_patterns = [
            "accessdenied" in stderr.lower().replace(" ", ""),
            "an error occurred" in stderr.lower() and "denied" in stderr.lower(),
            "not authorized" in stderr.lower(),
        ]

        # If it's a remote command with a host or URL-based error patterns
        is_url_based = (
            bool(is_remote_command and found_host)
            or any(
                [
                    "401" in stderr,
                    "403" in stderr,
                    "unauthorized" in stderr.lower(),
                    "authentication required" in stderr.lower(),
                    "login required" in stderr.lower(),
                    "access denied" in stderr.lower() and found_host,
                    "pull access denied" in stderr.lower(),
                    "denied: requested access" in stderr.lower(),
                ]
            )
            or any(git_remote_patterns)
            or any(aws_patterns)
        )

        if is_url_based:
            console.print("[cyan]   🌐 Detected URL-based permission error[/cyan]")
            console.print(f"[dim]      Host: {found_host or 'unknown'}[/dim]")
            console.print(f"[dim]      Service: {service or 'unknown'}[/dim]")

        return is_url_based, service, found_host

    def _is_local_file_permission_error(self, command: str, stderr: str) -> tuple[bool, str | None]:
        """
        Check if permission error is for a local file/directory.

        Returns:
            Tuple of (is_local_file, file_path)
        """
        # Check for local path patterns in stderr
        local_patterns = [
            r"Permission denied.*(/[^\s:]+)",
            r"cannot open '([^']+)'.*Permission denied",
            r"cannot create.*'([^']+)'.*Permission denied",
            r"cannot access '([^']+)'.*Permission denied",
            r"cannot read '([^']+)'",
            r"failed to open '([^']+)'",
            r"open\(\) \"([^\"]+)\" failed",
        ]

        for pattern in local_patterns:
            match = re.search(pattern, stderr, re.IGNORECASE)
            if match:
                path = match.group(1)
                # Verify it's a local path (starts with / or ./)
                if path.startswith("/") or path.startswith("./"):
                    console.print("[cyan]   📁 Detected local file permission error[/cyan]")
                    console.print(f"[dim]      Path: {path}[/dim]")
                    return True, path

        # Check command for local paths being accessed
        path_match = re.search(r"(/[^\s]+)", command)
        if path_match and "permission denied" in stderr.lower():
            path = path_match.group(1)
            console.print("[cyan]   📁 Detected local file permission error (from command)[/cyan]")
            console.print(f"[dim]      Path: {path}[/dim]")
            return True, path

        return False, None

    def _resolve_permission_error_type(
        self,
        command: str,
        stderr: str,
        current_category: ErrorCategory,
    ) -> tuple[ErrorCategory, dict[str, str]]:
        """
        Resolve generic PERMISSION_DENIED to specific LOCAL or URL category.

        Returns:
            Tuple of (refined_category, additional_info)
        """
        additional_info = {}

        # Only process if it's a generic permission error
        permission_categories = [
            ErrorCategory.PERMISSION_DENIED,
            ErrorCategory.PERMISSION_DENIED_LOCAL,
            ErrorCategory.PERMISSION_DENIED_URL,
            ErrorCategory.ACCESS_DENIED_REGISTRY,
            ErrorCategory.ACCESS_DENIED_REPO,
            ErrorCategory.ACCESS_DENIED_API,
            ErrorCategory.AUTH_FAILED,
        ]

        if current_category not in permission_categories:
            return current_category, additional_info

        # Check URL-based first (more specific)
        is_url, service, host = self._is_url_based_permission_error(command, stderr)
        if is_url:
            additional_info["service"] = service or "unknown"
            additional_info["host"] = host or "unknown"

            # Determine more specific category
            if "registry" in stderr.lower() or service in ["docker", "ghcr", "gcloud"]:
                return ErrorCategory.ACCESS_DENIED_REGISTRY, additional_info
            elif "git" in command.lower() or service in ["git_https"]:
                return ErrorCategory.ACCESS_DENIED_REPO, additional_info
            elif "api" in stderr.lower() or service in ["aws", "gcloud", "azure"]:
                # AWS, GCloud, Azure are API-based services
                return ErrorCategory.ACCESS_DENIED_API, additional_info
            elif (
                "aws " in command.lower()
                or "az " in command.lower()
                or "gcloud " in command.lower()
            ):
                # Cloud CLI commands are API-based
                return ErrorCategory.ACCESS_DENIED_API, additional_info
            else:
                return ErrorCategory.PERMISSION_DENIED_URL, additional_info

        # Check local file
        is_local, path = self._is_local_file_permission_error(command, stderr)
        if is_local:
            additional_info["path"] = path or ""
            return ErrorCategory.PERMISSION_DENIED_LOCAL, additional_info

        # Default to local for generic permission denied
        return ErrorCategory.PERMISSION_DENIED_LOCAL, additional_info

    # =========================================================================
    # STEP 1: Categorize Error
    # =========================================================================

    def categorize_error(self, command: str, stderr: str, stdout: str = "") -> DiagnosisResult:
        """
        Step 1: Categorize the error type.

        Examines stderr (and stdout) to determine the broad category of error.
        For permission errors, distinguishes between local file/dir and URL/link.
        """
        self._log_step(1, "Categorizing error type")

        combined_output = f"{stderr}\n{stdout}".lower()

        best_match: tuple[ErrorCategory, dict[str, str], float] | None = None

        for category, patterns in ERROR_PATTERNS.items():
            for pattern, info_key in patterns:
                match = re.search(pattern, stderr, re.IGNORECASE)
                if match:
                    extracted_info = {info_key: match.group(1) if match.groups() else ""}

                    # Calculate confidence based on pattern specificity
                    confidence = len(pattern) / 50.0  # Longer patterns = more specific
                    confidence = min(confidence, 1.0)

                    if best_match is None or confidence > best_match[2]:
                        best_match = (category, extracted_info, confidence)

        if best_match:
            category, extracted_info, confidence = best_match

            # Refine permission errors to LOCAL or URL
            refined_category, additional_info = self._resolve_permission_error_type(
                command, stderr, category
            )
            extracted_info.update(additional_info)

            result = DiagnosisResult(
                category=refined_category,
                error_message=stderr[:500],
                extracted_info=extracted_info,
                confidence=confidence,
                raw_stderr=stderr,
            )
        else:
            result = DiagnosisResult(
                category=ErrorCategory.UNKNOWN,
                error_message=stderr[:500],
                confidence=0.0,
                raw_stderr=stderr,
            )

        self._print_diagnosis(result, command)
        return result

    # =========================================================================
    # STEP 2: Generate Fix Plan via LLM
    # =========================================================================

    def generate_fix_plan(self, command: str, intent: str, diagnosis: DiagnosisResult) -> FixPlan:
        """
        Step 2: LLM generates fix commands with variable placeholders.

        Context given: command, intent, error, category
        Output: List of commands with {variable} placeholders
        """
        self._log_step(2, "Generating fix plan via LLM")

        if not self.client:
            # Fallback to rule-based fix generation
            return self._generate_fallback_fix_plan(command, intent, diagnosis)

        system_prompt = self._get_fix_generation_prompt()

        user_prompt = f"""Generate fix commands for this error:

**Command:** `{command}`
**Intent:** {intent}
**Error Category:** {diagnosis.category.value}
**Error Message:** {diagnosis.error_message}
**Extracted Info:** {json.dumps(diagnosis.extracted_info)}

Provide fix commands with variable placeholders in {{curly_braces}} for any values that need to be determined at runtime.

Respond with JSON:
{{
    "reasoning": "explanation of the fix approach",
    "commands": [
        {{
            "command": "command with {{variable}} placeholders",
            "purpose": "what this command does",
            "requires_sudo": true/false
        }}
    ]
}}"""

        try:
            response = self._call_llm(system_prompt, user_prompt)

            # Parse response
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                data = json.loads(json_match.group())

                commands = []
                for cmd_data in data.get("commands", []):
                    commands.append(
                        FixCommand(
                            command_template=cmd_data.get("command", ""),
                            purpose=cmd_data.get("purpose", ""),
                            requires_sudo=cmd_data.get("requires_sudo", False),
                        )
                    )

                plan = FixPlan(
                    category=diagnosis.category,
                    commands=commands,
                    reasoning=data.get("reasoning", ""),
                )

                self._print_fix_plan(plan)
                return plan

        except Exception as e:
            console.print(f"[yellow]⚠ LLM fix generation failed: {e}[/yellow]")

        # Fallback
        return self._generate_fallback_fix_plan(command, intent, diagnosis)

    def _get_fix_generation_prompt(self) -> str:
        return """You are a Linux system error diagnosis expert. Generate shell commands to fix errors.

RULES:
1. Use {variable} placeholders for values that need to be determined at runtime
2. Common variables: {file_path}, {package_name}, {service_name}, {user}, {port}, {config_file}
3. Commands should be atomic and specific
4. Include sudo only when necessary
5. Order commands logically (prerequisites first)

VARIABLE NAMING:
- {file_path} - path to a file
- {dir_path} - path to a directory
- {package} - package name to install
- {service} - systemd service name
- {user} - username
- {port} - port number
- {config_file} - configuration file path
- {config_line} - line number in config
- {image} - Docker/container image name
- {registry} - Container registry URL
- {username} - Login username
- {token} - Auth token or password

EXAMPLE OUTPUT:
{
    "reasoning": "Permission denied on /etc/nginx - need sudo to write, also backup first",
    "commands": [
        {
            "command": "sudo cp {config_file} {config_file}.backup",
            "purpose": "Backup the configuration file before modifying",
            "requires_sudo": true
        },
        {
            "command": "sudo sed -i 's/{old_value}/{new_value}/' {config_file}",
            "purpose": "Fix the configuration value",
            "requires_sudo": true
        }
    ]
}"""

    def _generate_fallback_fix_plan(
        self, command: str, intent: str, diagnosis: DiagnosisResult
    ) -> FixPlan:
        """Generate a fix plan using rules when LLM is unavailable."""
        commands: list[FixCommand] = []
        reasoning = f"Rule-based fix for {diagnosis.category.value}"

        category = diagnosis.category
        info = diagnosis.extracted_info

        # LOCAL permission denied - use sudo
        if category == ErrorCategory.PERMISSION_DENIED_LOCAL:
            path = info.get("path", "")
            reasoning = "Local file/directory permission denied - using elevated privileges"
            commands.append(
                FixCommand(
                    command_template=f"sudo {command}",
                    purpose=f"Retry with elevated privileges for local path{' ' + path if path else ''}",
                    requires_sudo=True,
                )
            )

        # URL-based permission - handle login
        elif category in [
            ErrorCategory.PERMISSION_DENIED_URL,
            ErrorCategory.ACCESS_DENIED_REGISTRY,
            ErrorCategory.ACCESS_DENIED_REPO,
            ErrorCategory.ACCESS_DENIED_API,
        ]:
            service = info.get("service", "unknown")
            host = info.get("host", "unknown")
            reasoning = f"URL/remote access denied - requires authentication to {service or host}"

            # Generate login command based on service
            if service == "docker" or service == "ghcr" or "registry" in category.value:
                registry = host if host != "unknown" else "{registry}"
                commands.extend(
                    [
                        FixCommand(
                            command_template=f"docker login {registry}",
                            purpose=f"Login to container registry {registry}",
                        ),
                        FixCommand(
                            command_template=command,
                            purpose="Retry original command after login",
                        ),
                    ]
                )
            elif service == "git_https" or "repo" in category.value:
                commands.extend(
                    [
                        FixCommand(
                            command_template="git config --global credential.helper store",
                            purpose="Enable credential storage for git",
                        ),
                        FixCommand(
                            command_template=command,
                            purpose="Retry original command (will prompt for credentials)",
                        ),
                    ]
                )
            elif service == "npm":
                commands.extend(
                    [
                        FixCommand(
                            command_template="npm login",
                            purpose="Login to npm registry",
                        ),
                        FixCommand(
                            command_template=command,
                            purpose="Retry original command after login",
                        ),
                    ]
                )
            elif service == "aws":
                commands.extend(
                    [
                        FixCommand(
                            command_template="aws configure",
                            purpose="Configure AWS credentials",
                        ),
                        FixCommand(
                            command_template=command,
                            purpose="Retry original command after configuration",
                        ),
                    ]
                )
            else:
                # Generic login placeholder
                commands.append(
                    FixCommand(
                        command_template="{login_command}",
                        purpose=f"Login to {service or host}",
                    )
                )
                commands.append(
                    FixCommand(
                        command_template=command,
                        purpose="Retry original command after login",
                    )
                )

        # Legacy generic permission denied - try to determine type
        elif category == ErrorCategory.PERMISSION_DENIED:
            commands.append(
                FixCommand(
                    command_template=f"sudo {command}",
                    purpose="Retry with elevated privileges",
                    requires_sudo=True,
                )
            )

        elif category == ErrorCategory.FILE_NOT_FOUND:
            file_path = info.get("file", "{file_path}")
            commands.append(
                FixCommand(
                    command_template=f"touch {file_path}",
                    purpose="Create missing file",
                )
            )

        elif category == ErrorCategory.DIRECTORY_NOT_FOUND:
            dir_path = info.get("directory", info.get("parent_directory", "{dir_path}"))
            commands.append(
                FixCommand(
                    command_template=f"mkdir -p {dir_path}",
                    purpose="Create missing directory",
                )
            )

        elif category == ErrorCategory.COMMAND_NOT_FOUND:
            # Try to guess package from command
            cmd_name = command.split()[0] if command else "{package}"
            commands.append(
                FixCommand(
                    command_template="sudo apt install -y {package}",
                    purpose="Install package providing the command",
                    requires_sudo=True,
                )
            )

        elif category == ErrorCategory.SERVICE_NOT_RUNNING:
            service = info.get("service", "{service}")
            commands.append(
                FixCommand(
                    command_template=f"sudo systemctl start {service}",
                    purpose="Start the service",
                    requires_sudo=True,
                )
            )

        elif category == ErrorCategory.LOGIN_REQUIRED:
            service = info.get("service", "{service}")
            commands.append(
                FixCommand(
                    command_template="{login_command}",
                    purpose=f"Login to {service}",
                )
            )

        elif category == ErrorCategory.PACKAGE_NOT_FOUND:
            package = info.get("package", "{package}")
            commands.extend(
                [
                    FixCommand(
                        command_template="sudo apt update",
                        purpose="Update package lists",
                        requires_sudo=True,
                    ),
                    FixCommand(
                        command_template=f"sudo apt install -y {package}",
                        purpose="Install the package",
                        requires_sudo=True,
                    ),
                ]
            )

        elif category == ErrorCategory.PORT_IN_USE:
            port = info.get("port", "{port}")
            commands.extend(
                [
                    FixCommand(
                        command_template=f"sudo lsof -i :{port}",
                        purpose="Find process using the port",
                        requires_sudo=True,
                    ),
                    FixCommand(
                        command_template="sudo kill -9 {pid}",
                        purpose="Kill the process using the port",
                        requires_sudo=True,
                    ),
                ]
            )

        elif category == ErrorCategory.CONFIG_SYNTAX_ERROR:
            config_file = info.get("config", info.get("nginx_config", "{config_file}"))
            commands.extend(
                [
                    FixCommand(
                        command_template=f"cat -n {config_file}",
                        purpose="Show config file with line numbers",
                    ),
                    FixCommand(
                        command_template=f"sudo nano {config_file}",
                        purpose="Edit config file to fix syntax",
                        requires_sudo=True,
                    ),
                ]
            )

        else:
            # Generic retry with sudo
            commands.append(
                FixCommand(
                    command_template=f"sudo {command}",
                    purpose="Retry with elevated privileges",
                    requires_sudo=True,
                )
            )

        plan = FixPlan(
            category=diagnosis.category,
            commands=commands,
            reasoning=reasoning,
        )

        self._print_fix_plan(plan)
        return plan

    # =========================================================================
    # STEP 3: Resolve Variables
    # =========================================================================

    def resolve_variables(
        self,
        fix_plan: FixPlan,
        original_query: str,
        command: str,
        diagnosis: DiagnosisResult,
    ) -> dict[str, str]:
        """
        Step 3: Resolve variable values using:
        1. Extract from original query
        2. LLM call with context
        3. system_info_command_generator
        """
        self._log_step(3, "Resolving variables")

        if not fix_plan.all_variables:
            console.print("[dim]   No variables to resolve[/dim]")
            return {}

        console.print(f"[cyan]   Variables to resolve: {', '.join(fix_plan.all_variables)}[/cyan]")

        resolved: dict[str, str] = {}

        for var_name in fix_plan.all_variables:
            # Check cache first
            if var_name in self.variable_cache:
                resolved[var_name] = self.variable_cache[var_name]
                console.print(f"[dim]   {var_name}: {resolved[var_name]} (cached)[/dim]")
                continue

            # Try extraction from diagnosis info
            value = self._try_extract_from_diagnosis(var_name, diagnosis)
            if value:
                resolved[var_name] = value
                console.print(f"[green]   ✓ {var_name}: {value} (from error)[/green]")
                continue

            # Try extraction from query
            value = self._try_extract_from_query(var_name, original_query)
            if value:
                resolved[var_name] = value
                console.print(f"[green]   ✓ {var_name}: {value} (from query)[/green]")
                continue

            # Try system_info_command_generator
            value = self._try_system_info(var_name, command, diagnosis)
            if value:
                resolved[var_name] = value
                console.print(f"[green]   ✓ {var_name}: {value} (from system)[/green]")
                continue

            # Fall back to LLM
            value = self._try_llm_resolution(var_name, original_query, command, diagnosis)
            if value:
                resolved[var_name] = value
                console.print(f"[green]   ✓ {var_name}: {value} (from LLM)[/green]")
                continue

            # Prompt user as last resort
            console.print(f"[yellow]   ⚠ Could not resolve {var_name}[/yellow]")
            try:
                from rich.prompt import Prompt

                value = Prompt.ask(f"   Enter value for {var_name}")
                if value:
                    resolved[var_name] = value
                    console.print(f"[green]   ✓ {var_name}: {value} (from user)[/green]")
            except Exception:
                pass

        # Update cache
        self.variable_cache.update(resolved)

        return resolved

    def _try_extract_from_diagnosis(self, var_name: str, diagnosis: DiagnosisResult) -> str | None:
        """Try to extract variable from diagnosis extracted_info."""
        # Map variable names to diagnosis info keys
        mappings = {
            "file_path": ["file", "path"],
            "dir_path": ["directory", "parent_directory", "dir"],
            "package": ["package", "module"],
            "service": ["service", "unit"],
            "port": ["port"],
            "config_file": ["config", "nginx_config", "config_file"],
            "user": ["user"],
            "image": ["image", "repository"],
        }

        keys_to_check = mappings.get(var_name, [var_name])
        for key in keys_to_check:
            if key in diagnosis.extracted_info and diagnosis.extracted_info[key]:
                return diagnosis.extracted_info[key]

        return None

    def _try_extract_from_query(self, var_name: str, query: str) -> str | None:
        """Try to extract variable from the original query."""
        # Pattern-based extraction from query
        patterns = {
            "file_path": [r"file\s+['\"]?([/\w.-]+)['\"]?", r"([/\w]+\.\w+)"],
            "dir_path": [r"directory\s+['\"]?([/\w.-]+)['\"]?", r"folder\s+['\"]?([/\w.-]+)['\"]?"],
            "package": [r"install\s+(\w[\w-]*)", r"package\s+(\w[\w-]*)"],
            "service": [r"service\s+(\w[\w-]*)", r"(\w+)\.service"],
            "port": [r"port\s+(\d+)", r":(\d{2,5})"],
            "image": [r"image\s+([^\s]+)", r"docker.*\s+([^\s]+:[^\s]*)"],
        }

        if var_name in patterns:
            for pattern in patterns[var_name]:
                match = re.search(pattern, query, re.IGNORECASE)
                if match:
                    return match.group(1)

        return None

    def _try_system_info(
        self, var_name: str, command: str, diagnosis: DiagnosisResult
    ) -> str | None:
        """Use system_info_command_generator to get variable value."""
        try:
            from cortex.system_info_generator import SystemInfoGenerator

            # System info commands for different variable types
            system_queries = {
                "user": "whoami",
                "home_dir": "echo $HOME",
                "current_dir": "pwd",
            }

            if var_name in system_queries:
                result = subprocess.run(
                    system_queries[var_name],
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()

            # For package commands, try to find the package
            if var_name == "package":
                cmd_name = command.split()[0] if command else ""
                # Common command-to-package mappings for Ubuntu
                package_map = {
                    "nginx": "nginx",
                    "docker": "docker.io",
                    "python": "python3",
                    "pip": "python3-pip",
                    "node": "nodejs",
                    "npm": "npm",
                    "git": "git",
                    "curl": "curl",
                    "wget": "wget",
                    "htop": "htop",
                    "vim": "vim",
                    "nano": "nano",
                }
                if cmd_name in package_map:
                    return package_map[cmd_name]

                # Try apt-file search if available
                result = subprocess.run(
                    f"apt-file search --regexp 'bin/{cmd_name}$' 2>/dev/null | head -1 | cut -d: -f1",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()

            # For service names, try systemctl
            if var_name == "service":
                # Extract service name from command if present
                service_match = re.search(r"systemctl\s+\w+\s+(\S+)", command)
                if service_match:
                    return service_match.group(1)

        except Exception as e:
            if self.debug:
                console.print(f"[dim]   System info failed for {var_name}: {e}[/dim]")

        return None

    def _try_llm_resolution(
        self,
        var_name: str,
        query: str,
        command: str,
        diagnosis: DiagnosisResult,
    ) -> str | None:
        """Use LLM to resolve variable value."""
        if not self.client:
            return None

        prompt = f"""Extract the value for variable '{var_name}' from this context:

Query: {query}
Command: {command}
Error Category: {diagnosis.category.value}
Error: {diagnosis.error_message[:200]}

Respond with ONLY the value, nothing else. If you cannot determine the value, respond with "UNKNOWN"."""

        try:
            response = self._call_llm("You extract specific values from context.", prompt)
            value = response.strip().strip("\"'")
            if value and value.upper() != "UNKNOWN":
                return value
        except Exception:
            pass

        return None

    # =========================================================================
    # URL AUTHENTICATION HANDLING
    # =========================================================================

    def handle_url_authentication(
        self,
        command: str,
        diagnosis: DiagnosisResult,
    ) -> tuple[bool, str]:
        """
        Handle URL-based permission errors by prompting for login.

        Uses LoginHandler to:
        1. Detect the service/website
        2. Prompt for credentials
        3. Store credentials for future use
        4. Execute login command

        Returns:
            Tuple of (success, message)
        """
        console.print("\n[bold cyan]🔐 URL Authentication Required[/bold cyan]")

        if not self._login_handler:
            console.print("[yellow]⚠ LoginHandler not available[/yellow]")
            return False, "LoginHandler not available"

        service = diagnosis.extracted_info.get("service", "unknown")
        host = diagnosis.extracted_info.get("host", "")

        console.print(f"[dim]   Service: {service}[/dim]")
        console.print(f"[dim]   Host: {host}[/dim]")

        try:
            # Use LoginHandler to manage authentication
            login_req = self._login_handler.detect_login_requirement(command, diagnosis.raw_stderr)

            if login_req:
                console.print(f"\n[cyan]📝 Login to {login_req.display_name}[/cyan]")

                # Handle login (will prompt, execute, and optionally save credentials)
                success, message = self._login_handler.handle_login(command, diagnosis.raw_stderr)

                if success:
                    console.print(f"[green]✓ {message}[/green]")
                    return True, message
                else:
                    console.print(f"[yellow]⚠ {message}[/yellow]")
                    return False, message
            else:
                # No matching login requirement, try generic approach
                console.print("[yellow]   Unknown service, trying generic login...[/yellow]")
                return self._handle_generic_login(command, diagnosis)

        except Exception as e:
            console.print(f"[red]✗ Authentication error: {e}[/red]")
            return False, str(e)

    def _handle_generic_login(
        self,
        command: str,
        diagnosis: DiagnosisResult,
    ) -> tuple[bool, str]:
        """Handle login for unknown services with interactive prompts."""
        from rich.prompt import Confirm, Prompt

        host = diagnosis.extracted_info.get("host", "unknown service")

        console.print(f"\n[cyan]Login required for: {host}[/cyan]")

        try:
            # Prompt for credentials
            username = Prompt.ask("Username")
            if not username:
                return False, "Username is required"

            password = Prompt.ask("Password", password=True)

            # Determine login command based on command context
            login_cmd = None

            if "docker" in command.lower():
                registry = diagnosis.extracted_info.get("host", "")
                login_cmd = f"docker login {registry}" if registry else "docker login"
            elif "git" in command.lower():
                # Store git credentials
                subprocess.run("git config --global credential.helper store", shell=True)
                login_cmd = None  # Git will prompt automatically
            elif "npm" in command.lower():
                login_cmd = "npm login"
            elif "pip" in command.lower() or "pypi" in host.lower():
                login_cmd = f"pip config set global.index-url https://{username}:{{password}}@pypi.org/simple/"

            if login_cmd:
                console.print(f"[dim]   Running: {login_cmd}[/dim]")

                # Execute login with password via stdin if needed
                if "{password}" in login_cmd:
                    login_cmd = login_cmd.replace("{password}", password)
                    result = subprocess.run(login_cmd, shell=True, capture_output=True, text=True)
                else:
                    # Interactive login
                    result = subprocess.run(
                        login_cmd,
                        shell=True,
                        input=f"{username}\n{password}\n",
                        capture_output=True,
                        text=True,
                    )

                if result.returncode == 0:
                    # Offer to save credentials
                    if self._login_handler and Confirm.ask(
                        "Save credentials for future use?", default=True
                    ):
                        self._login_handler._save_credentials(
                            host,
                            {
                                "username": username,
                                "password": password,
                            },
                        )
                        console.print("[green]✓ Credentials saved[/green]")

                    return True, f"Logged in to {host}"
                else:
                    return False, f"Login failed: {result.stderr[:200]}"

            return False, "Could not determine login command"

        except KeyboardInterrupt:
            return False, "Login cancelled"
        except Exception as e:
            return False, str(e)

    # =========================================================================
    # STEP 4: Execute Fix Commands
    # =========================================================================

    def execute_fix_commands(
        self, fix_plan: FixPlan, resolved_variables: dict[str, str]
    ) -> list[ExecutionResult]:
        """
        Step 4: Execute fix commands with resolved variables.
        """
        self._log_step(4, "Executing fix commands")

        results: list[ExecutionResult] = []

        for i, fix_cmd in enumerate(fix_plan.commands, 1):
            # Substitute variables
            command = fix_cmd.command_template
            for var_name, value in resolved_variables.items():
                command = command.replace(f"{{{var_name}}}", value)

            # Check for unresolved variables
            unresolved = re.findall(r"\{(\w+)\}", command)
            if unresolved:
                console.print(
                    f"[yellow]   ⚠ Skipping command with unresolved variables: {unresolved}[/yellow]"
                )
                results.append(
                    ExecutionResult(
                        command=command,
                        success=False,
                        stdout="",
                        stderr=f"Unresolved variables: {unresolved}",
                        execution_time=0,
                    )
                )
                continue

            console.print(f"\n[cyan]   [{i}/{len(fix_plan.commands)}] {command}[/cyan]")
            console.print(f"[dim]   └─ {fix_cmd.purpose}[/dim]")

            # Execute
            start_time = time.time()
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                execution_time = time.time() - start_time

                exec_result = ExecutionResult(
                    command=command,
                    success=result.returncode == 0,
                    stdout=result.stdout.strip(),
                    stderr=result.stderr.strip(),
                    execution_time=execution_time,
                )

                if exec_result.success:
                    console.print(f"[green]   ✓ Success ({execution_time:.2f}s)[/green]")
                    if exec_result.stdout and self.debug:
                        console.print(f"[dim]   Output: {exec_result.stdout[:200]}[/dim]")
                else:
                    console.print(f"[red]   ✗ Failed: {exec_result.stderr[:200]}[/red]")

                results.append(exec_result)

                # Log to history
                self.execution_history.append(
                    {
                        "command": command,
                        "success": exec_result.success,
                        "stderr": exec_result.stderr[:500],
                        "timestamp": time.time(),
                    }
                )

            except subprocess.TimeoutExpired:
                console.print("[red]   ✗ Timeout after 120s[/red]")
                results.append(
                    ExecutionResult(
                        command=command,
                        success=False,
                        stdout="",
                        stderr="Command timed out",
                        execution_time=120,
                    )
                )
            except Exception as e:
                console.print(f"[red]   ✗ Error: {e}[/red]")
                results.append(
                    ExecutionResult(
                        command=command,
                        success=False,
                        stdout="",
                        stderr=str(e),
                        execution_time=time.time() - start_time,
                    )
                )

        return results

    # =========================================================================
    # STEP 5 & 6: Error Stack Management and Retry Logic
    # =========================================================================

    def push_error(self, entry: ErrorStackEntry) -> None:
        """Push an error onto the stack."""
        if len(self.error_stack) >= self.MAX_STACK_DEPTH:
            console.print(f"[red]⚠ Error stack depth limit ({self.MAX_STACK_DEPTH}) reached[/red]")
            return

        self.error_stack.append(entry)
        self._print_error_stack()

    def pop_error(self) -> ErrorStackEntry | None:
        """Pop an error from the stack."""
        if self.error_stack:
            return self.error_stack.pop()
        return None

    def diagnose_and_fix(
        self,
        command: str,
        stderr: str,
        intent: str,
        original_query: str,
        stdout: str = "",
    ) -> tuple[bool, str]:
        """
        Main diagnosis and fix flow.

        Returns:
            Tuple of (success, message)
        """
        console.print(
            Panel(
                f"[bold]Starting Diagnosis[/bold]\n"
                f"Command: [cyan]{command}[/cyan]\n"
                f"Intent: {intent}",
                title="🔧 Cortex Diagnosis Engine",
                border_style="blue",
            )
        )

        # Push initial error to stack
        initial_entry = ErrorStackEntry(
            original_command=command,
            intent=intent,
            error=stderr,
            category=ErrorCategory.UNKNOWN,  # Will be set in Step 1
        )
        self.push_error(initial_entry)

        # Process error stack
        while self.error_stack:
            entry = self.error_stack[-1]  # Peek at top

            if entry.fix_attempts >= self.MAX_FIX_ATTEMPTS:
                console.print(
                    f"[red]✗ Max fix attempts ({self.MAX_FIX_ATTEMPTS}) reached for command[/red]"
                )
                self.pop_error()
                continue

            entry.fix_attempts += 1
            console.print(
                f"\n[bold]Fix Attempt {entry.fix_attempts}/{self.MAX_FIX_ATTEMPTS}[/bold]"
            )

            # Step 1: Categorize error
            diagnosis = self.categorize_error(entry.original_command, entry.error)
            entry.category = diagnosis.category

            # SPECIAL HANDLING: URL-based permission errors need authentication
            url_auth_categories = [
                ErrorCategory.PERMISSION_DENIED_URL,
                ErrorCategory.ACCESS_DENIED_REGISTRY,
                ErrorCategory.ACCESS_DENIED_REPO,
                ErrorCategory.ACCESS_DENIED_API,
                ErrorCategory.LOGIN_REQUIRED,
            ]

            if diagnosis.category in url_auth_categories:
                console.print(
                    "[cyan]🌐 URL-based access error detected - handling authentication[/cyan]"
                )

                auth_success, auth_message = self.handle_url_authentication(
                    entry.original_command, diagnosis
                )

                if auth_success:
                    # Re-test the original command after login
                    console.print("\n[cyan]📋 Testing original command after login...[/cyan]")

                    test_result = subprocess.run(
                        entry.original_command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                    if test_result.returncode == 0:
                        console.print("[green]✓ Command succeeded after authentication![/green]")
                        self.pop_error()
                        if not self.error_stack:
                            return True, f"Fixed via authentication: {auth_message}"
                        continue
                    else:
                        # Different error after login
                        entry.error = test_result.stderr.strip()
                        console.print(
                            "[yellow]⚠ New error after login, continuing diagnosis...[/yellow]"
                        )
                        continue
                else:
                    console.print(f"[yellow]⚠ Authentication failed: {auth_message}[/yellow]")
                    # Continue with normal fix flow

            # Step 2: Generate fix plan
            fix_plan = self.generate_fix_plan(entry.original_command, entry.intent, diagnosis)
            entry.fix_plan = fix_plan

            # Step 3: Resolve variables
            resolved_vars = self.resolve_variables(
                fix_plan,
                original_query,
                entry.original_command,
                diagnosis,
            )

            # Check if all variables resolved
            unresolved = fix_plan.all_variables - set(resolved_vars.keys())
            if unresolved:
                console.print(f"[yellow]⚠ Could not resolve all variables: {unresolved}[/yellow]")
                # Continue anyway with what we have

            # Step 4: Execute fix commands
            results = self.execute_fix_commands(fix_plan, resolved_vars)

            # Check for errors in fix commands (Step 5)
            fix_errors = [r for r in results if not r.success]
            if fix_errors:
                console.print(f"\n[yellow]⚠ {len(fix_errors)} fix command(s) failed[/yellow]")

                # Push the first error back to stack for diagnosis
                first_error = fix_errors[0]
                if first_error.stderr and "Unresolved variables" not in first_error.stderr:
                    new_entry = ErrorStackEntry(
                        original_command=first_error.command,
                        intent=f"Fix command for: {entry.intent}",
                        error=first_error.stderr,
                        category=ErrorCategory.UNKNOWN,
                    )
                    self.push_error(new_entry)
                continue

            # Step 6: Test original command
            console.print(f"\n[cyan]📋 Testing original command: {entry.original_command}[/cyan]")

            test_result = subprocess.run(
                entry.original_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if test_result.returncode == 0:
                console.print("[green]✓ Original command now succeeds![/green]")
                self.pop_error()

                # Check if stack is empty
                if not self.error_stack:
                    return True, "All errors resolved successfully"
            else:
                new_error = test_result.stderr.strip()
                console.print("[yellow]⚠ Original command still fails[/yellow]")

                if new_error != entry.error:
                    console.print("[cyan]   New error detected, updating...[/cyan]")
                    entry.error = new_error
                # Loop will continue with same entry

        # Stack empty but we didn't explicitly succeed
        return False, "Could not resolve all errors"

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM and return response text."""
        if self.provider == "claude":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        elif self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _log_step(self, step_num: int, description: str) -> None:
        """Log a diagnosis step."""
        console.print(f"\n[bold blue]Step {step_num}:[/bold blue] {description}")

    def _print_diagnosis(self, diagnosis: DiagnosisResult, command: str) -> None:
        """Print diagnosis result."""
        table = Table(title="Error Diagnosis", show_header=False, border_style="dim")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        table.add_row("Category", f"[cyan]{diagnosis.category.value}[/cyan]")
        table.add_row("Confidence", f"{diagnosis.confidence:.0%}")

        if diagnosis.extracted_info:
            info_str = ", ".join(f"{k}={v}" for k, v in diagnosis.extracted_info.items() if v)
            table.add_row("Extracted", info_str)

        table.add_row(
            "Error",
            (
                diagnosis.error_message[:100] + "..."
                if len(diagnosis.error_message) > 100
                else diagnosis.error_message
            ),
        )

        console.print(table)

    def _print_fix_plan(self, plan: FixPlan) -> None:
        """Print fix plan."""
        console.print(f"\n[bold]Fix Plan:[/bold] {plan.reasoning}")

        for i, cmd in enumerate(plan.commands, 1):
            sudo_tag = "[sudo]" if cmd.requires_sudo else ""
            vars_tag = f"[vars: {', '.join(cmd.variables)}]" if cmd.variables else ""
            console.print(f"   {i}. [cyan]{cmd.command_template}[/cyan] {sudo_tag} {vars_tag}")
            console.print(f"      [dim]{cmd.purpose}[/dim]")

    def _print_error_stack(self) -> None:
        """Print current error stack."""
        if not self.error_stack:
            console.print("[dim]   Error stack: empty[/dim]")
            return

        tree = Tree("[bold]Error Stack[/bold]")
        for i, entry in enumerate(reversed(self.error_stack)):
            branch = tree.add(f"[{'yellow' if i == 0 else 'dim'}]{entry.original_command[:50]}[/]")
            branch.add(f"[dim]Category: {entry.category.value}[/dim]")
            branch.add(f"[dim]Attempts: {entry.fix_attempts}[/dim]")

        console.print(tree)

    def get_execution_summary(self) -> dict[str, Any]:
        """Get summary of all executions."""
        return {
            "total_commands": len(self.execution_history),
            "successful": sum(1 for h in self.execution_history if h.get("success")),
            "failed": sum(1 for h in self.execution_history if not h.get("success")),
            "history": self.execution_history[-20:],  # Last 20
            "variables_cached": len(self.variable_cache),
        }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def get_diagnosis_engine(
    provider: str = "claude",
    debug: bool = False,
) -> DiagnosisEngine:
    """Factory function to create a DiagnosisEngine."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    return DiagnosisEngine(api_key=api_key, provider=provider, debug=debug)


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import sys

    console.print("[bold]Diagnosis Engine Test[/bold]\n")

    engine = get_diagnosis_engine(debug=True)

    # Test error categorization
    test_cases = [
        ("cat /nonexistent/file", "cat: /nonexistent/file: No such file or directory"),
        ("docker pull ghcr.io/test/image", "Error: Non-null Username Required"),
        ("apt install fakepackage", "E: Unable to locate package fakepackage"),
        ("nginx -t", 'nginx: [emerg] unknown directive "invalid" in /etc/nginx/nginx.conf:10'),
        (
            "systemctl start myservice",
            "Failed to start myservice.service: Unit myservice.service not found.",
        ),
    ]

    for cmd, error in test_cases:
        console.print(f"\n[bold]Test:[/bold] {cmd}")
        console.print(f"[dim]Error: {error}[/dim]")

        diagnosis = engine.categorize_error(cmd, error)
        console.print(f"[green]Category: {diagnosis.category.value}[/green]")
        console.print("")
