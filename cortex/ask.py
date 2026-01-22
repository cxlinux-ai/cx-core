"""Natural language query interface for Cortex.

Handles user questions about installed packages, configurations,
and system state using an agentic LLM loop with command execution.

The --do mode enables write and execute capabilities with user confirmation
and privilege management.
"""

import json
import os
import re
import shlex
import sqlite3
import subprocess
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class LLMResponseType(str, Enum):
    """Type of response from the LLM."""
    COMMAND = "command"
    ANSWER = "answer"
    DO_COMMANDS = "do_commands"  # For --do mode: commands that modify the system


class DoCommand(BaseModel):
    """A single command for --do mode with explanation."""
    command: str = Field(description="The shell command to execute")
    purpose: str = Field(description="Brief explanation of what this command does")
    requires_sudo: bool = Field(default=False, description="Whether this command requires sudo")


class SystemCommand(BaseModel):
    """Pydantic model for a system command to be executed.
    
    The LLM must return either a command to execute for data gathering,
    or a final answer to the user's question.
    In --do mode, it can also return a list of commands to execute.
    """
    response_type: LLMResponseType = Field(
        description="Whether this is a command to execute, a final answer, or do commands"
    )
    command: str | None = Field(
        default=None,
        description="The shell command to execute (only for response_type='command')"
    )
    answer: str | None = Field(
        default=None,
        description="The final answer to the user (only for response_type='answer')"
    )
    do_commands: list[DoCommand] | None = Field(
        default=None,
        description="List of commands to execute (only for response_type='do_commands')"
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of why this command/answer was chosen"
    )

    @field_validator("command")
    @classmethod
    def validate_command_not_empty(cls, v: str | None, info) -> str | None:
        if info.data.get("response_type") == LLMResponseType.COMMAND:
            if not v or not v.strip():
                raise ValueError("Command cannot be empty when response_type is 'command'")
        return v

    @field_validator("answer")
    @classmethod
    def validate_answer_not_empty(cls, v: str | None, info) -> str | None:
        if info.data.get("response_type") == LLMResponseType.ANSWER:
            if not v or not v.strip():
                raise ValueError("Answer cannot be empty when response_type is 'answer'")
        return v
    
    @field_validator("do_commands")
    @classmethod
    def validate_do_commands_not_empty(cls, v: list[DoCommand] | None, info) -> list[DoCommand] | None:
        if info.data.get("response_type") == LLMResponseType.DO_COMMANDS:
            if not v or len(v) == 0:
                raise ValueError("do_commands cannot be empty when response_type is 'do_commands'")
        return v


class CommandValidator:
    """Validates and filters commands to ensure they are read-only.
    
    Only allows commands that fetch data, blocks any that modify the system.
    """
    
    # Commands that are purely read-only and safe
    ALLOWED_COMMANDS: set[str] = {
        # System info
        "uname", "hostname", "uptime", "whoami", "id", "groups", "w", "who", "last",
        "date", "cal", "timedatectl",
        # File/directory listing (read-only)
        "ls", "pwd", "tree", "file", "stat", "readlink", "realpath", "dirname", "basename",
        "find", "locate", "which", "whereis", "type", "command",
        # Text viewing (read-only)
        "cat", "head", "tail", "less", "more", "wc", "nl", "strings",
        # Text processing (non-modifying)
        "grep", "egrep", "fgrep", "awk", "sed", "cut", "sort", "uniq", "tr", "column",
        "diff", "comm", "join", "paste", "expand", "unexpand", "fold", "fmt",
        # Package queries (read-only)
        "dpkg-query", "dpkg", "apt-cache", "apt-mark", "apt-config", "aptitude", "apt",
        "pip3", "pip", "python3", "python", "gem", "npm", "cargo", "go",
        # System info commands
        "lsb_release", "hostnamectl", "lscpu", "lsmem", "lsblk", "lspci", "lsusb",
        "lshw", "dmidecode", "hwinfo", "inxi",
        # Process/resource info
        "ps", "top", "htop", "pgrep", "pidof", "pstree", "free", "vmstat", "iostat",
        "mpstat", "sar", "nproc", "getconf",
        # Disk/filesystem info
        "df", "du", "mount", "findmnt", "blkid", "lsof", "fuser", "fdisk",
        # Network info (read-only)
        "ip", "ifconfig", "netstat", "ss", "route", "arp", "ping", "traceroute",
        "tracepath", "nslookup", "dig", "host", "getent", "hostname",
        # GPU info
        "nvidia-smi", "nvcc", "rocm-smi", "clinfo",
        # Environment
        "env", "printenv", "echo", "printf",
        # Systemd info (read-only)
        "systemctl", "journalctl", "loginctl", "timedatectl", "localectl",
        # Kernel/modules
        "uname", "lsmod", "modinfo", "sysctl",
        # Misc info
        "getconf", "locale", "xdpyinfo", "xrandr",
        # Container/virtualization info
        "docker", "podman", "kubectl", "crictl", "nerdctl",
        "lxc-ls", "virsh", "vboxmanage",
        # Development tools (version checks)
        "git", "node", "nodejs", "deno", "bun", "ruby", "perl", "php", "java", "javac",
        "rustc", "gcc", "g++", "clang", "clang++", "make", "cmake", "ninja", "meson",
        "dotnet", "mono", "swift", "kotlin", "scala", "groovy", "gradle", "mvn", "ant",
        # Database clients (info/version)
        "mysql", "psql", "sqlite3", "mongosh", "redis-cli",
        # Web/network tools
        "curl", "wget", "httpie", "openssl", "ssh", "scp", "rsync",
        # Cloud CLIs
        "aws", "gcloud", "az", "doctl", "linode-cli", "vultr-cli",
        "terraform", "ansible", "vagrant", "packer",
        # Other common tools
        "jq", "yq", "xmllint", "ffmpeg", "ffprobe", "imagemagick", "convert",
        "gh", "hub", "lab",  # GitHub/GitLab CLIs
        "snap", "flatpak",  # For version/list only
        "systemd-analyze", "bootctl",
    }
    
    # Version check flags - these make ANY command safe (read-only)
    VERSION_FLAGS: set[str] = {
        "--version", "-v", "-V", "--help", "-h", "-help",
        "version", "help", "--info", "-version",
    }
    
    # Subcommands that are blocked for otherwise allowed commands
    BLOCKED_SUBCOMMANDS: dict[str, set[str]] = {
        "dpkg": {"--configure", "-i", "--install", "--remove", "-r", "--purge", "-P", 
                 "--unpack", "--clear-avail", "--forget-old-unavail", "--update-avail",
                 "--merge-avail", "--set-selections", "--clear-selections"},
        "apt-mark": {"auto", "manual", "hold", "unhold", "showauto", "showmanual"},  # only show* are safe
        "pip3": {"install", "uninstall", "download", "wheel", "cache"},
        "pip": {"install", "uninstall", "download", "wheel", "cache"},
        "python3": {"-c"},  # Block arbitrary code execution
        "python": {"-c"},
        "npm": {"install", "uninstall", "update", "ci", "run", "exec", "init", "publish"},
        "gem": {"install", "uninstall", "update", "cleanup", "pristine"},
        "cargo": {"install", "uninstall", "build", "run", "clean", "publish"},
        "go": {"install", "get", "build", "run", "clean", "mod"},
        "systemctl": {"start", "stop", "restart", "reload", "enable", "disable", 
                      "mask", "unmask", "edit", "set-property", "reset-failed",
                      "daemon-reload", "daemon-reexec", "kill", "isolate",
                      "set-default", "set-environment", "unset-environment"},
        "mount": {"--bind", "-o", "--move"},  # Block actual mounting
        "fdisk": {"-l"},  # Only allow listing (-l), block everything else (inverted logic handled below)
        "sysctl": {"-w", "--write", "-p", "--load"},  # Block writes
        # Container tools - block modifying commands
        "docker": {"run", "exec", "build", "push", "pull", "rm", "rmi", "kill", "stop", "start",
                   "restart", "pause", "unpause", "create", "commit", "tag", "load", "save",
                   "import", "export", "login", "logout", "network", "volume", "system", "prune"},
        "podman": {"run", "exec", "build", "push", "pull", "rm", "rmi", "kill", "stop", "start",
                   "restart", "pause", "unpause", "create", "commit", "tag", "load", "save",
                   "import", "export", "login", "logout", "network", "volume", "system", "prune"},
        "kubectl": {"apply", "create", "delete", "edit", "patch", "replace", "scale", "exec",
                    "run", "expose", "set", "rollout", "drain", "cordon", "uncordon", "taint"},
        # Git - block modifying commands
        "git": {"push", "commit", "add", "rm", "mv", "reset", "revert", "merge", "rebase",
                "checkout", "switch", "restore", "stash", "clean", "init", "clone", "pull",
                "fetch", "cherry-pick", "am", "apply"},
        # Cloud CLIs - block modifying commands
        "aws": {"s3", "ec2", "iam", "lambda", "rds", "ecs", "eks"},  # Block service commands (allow sts, configure list)
        "gcloud": {"compute", "container", "functions", "run", "sql", "storage"},
        # Snap/Flatpak - block modifying commands  
        "snap": {"install", "remove", "refresh", "revert", "enable", "disable", "set", "unset"},
        "flatpak": {"install", "uninstall", "update", "repair"},
    }
    
    # Commands that are completely blocked (never allowed, even with --version)
    BLOCKED_COMMANDS: set[str] = {
        # Dangerous/destructive
        "rm", "rmdir", "unlink", "shred",
        "mv", "cp", "install", "mkdir", "touch",
        # Editors (sed is allowed for text processing, redirections are blocked separately)
        "nano", "vim", "vi", "emacs", "ed",
        # Package modification (apt-get is dangerous, apt is allowed with restrictions)
        "apt-get", "dpkg-reconfigure", "update-alternatives",
        # System modification
        "shutdown", "reboot", "poweroff", "halt", "init", "telinit",
        "useradd", "userdel", "usermod", "groupadd", "groupdel", "groupmod",
        "passwd", "chpasswd", "chage",
        "chmod", "chown", "chgrp", "chattr", "setfacl",
        "ln", "mkfifo", "mknod",
        # Dangerous utilities
        "dd", "mkfs", "fsck", "parted", "gdisk", "cfdisk", "sfdisk",
        "kill", "killall", "pkill",
        "nohup", "disown", "bg", "fg",
        "crontab", "at", "batch",
        "su", "sudo", "doas", "pkexec",
        # Network modification
        "iptables", "ip6tables", "nft", "ufw", "firewall-cmd",
        "ifup", "ifdown", "dhclient",
        # Shell/code execution
        "bash", "sh", "zsh", "fish", "dash", "csh", "tcsh", "ksh",
        "eval", "exec", "source",
        "xargs",  # Can be used to execute arbitrary commands
        "tee",  # Writes to files
    }
    
    # Patterns that indicate dangerous operations (NOT including safe chaining)
    DANGEROUS_PATTERNS: list[str] = [
        r">\s*[^|]",           # Output redirection (except pipes)
        r">>\s*",              # Append redirection
        r"<\s*",               # Input redirection  
        r"\$\(",               # Command substitution
        r"`[^`]+`",            # Backtick command substitution
        r"\|.*(?:sh|bash|zsh|exec|eval|xargs)",  # Piping to shell
    ]
    
    # Chaining patterns that we'll split instead of block
    CHAINING_PATTERNS: list[str] = [
        r";\s*",               # Command chaining
        r"\s*&&\s*",           # AND chaining
        r"\s*\|\|\s*",         # OR chaining
    ]
    
    @classmethod
    def split_chained_commands(cls, command: str) -> list[str]:
        """Split a chained command into individual commands."""
        # Split by ;, &&, or ||
        parts = re.split(r'\s*(?:;|&&|\|\|)\s*', command)
        return [p.strip() for p in parts if p.strip()]
    
    @classmethod
    def validate_command(cls, command: str) -> tuple[bool, str]:
        """Validate a command for safety.
        
        Args:
            command: The shell command to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not command or not command.strip():
            return False, "Empty command"
        
        command = command.strip()
        
        # Check for dangerous patterns (NOT chaining - we handle that separately)
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return False, f"Command contains blocked pattern (redirections or subshells)"
        
        # Check if command has chaining - if so, validate each part
        has_chaining = any(re.search(p, command) for p in cls.CHAINING_PATTERNS)
        if has_chaining:
            subcommands = cls.split_chained_commands(command)
            for subcmd in subcommands:
                is_valid, error = cls._validate_single_command(subcmd)
                if not is_valid:
                    return False, f"In chained command '{subcmd}': {error}"
            return True, ""
        
        return cls._validate_single_command(command)
    
    @classmethod
    def _validate_single_command(cls, command: str) -> tuple[bool, str]:
        """Validate a single (non-chained) command."""
        if not command or not command.strip():
            return False, "Empty command"
        
        command = command.strip()
        
        # Parse the command
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return False, f"Invalid command syntax: {e}"
        
        if not parts:
            return False, "Empty command"
        
        # Get base command (handle sudo prefix)
        base_cmd = parts[0]
        cmd_args = parts[1:]
        
        if base_cmd == "sudo":
            return False, "sudo is not allowed - only read-only commands permitted"
        
        # Check if this is a version/help check - these are always safe
        # Allow ANY command if it only has version/help flags
        if cmd_args and all(arg in cls.VERSION_FLAGS for arg in cmd_args):
            return True, ""  # Safe: just checking version/help
        
        # Also allow if first arg is a version flag (e.g., "docker --version" or "git version")
        if cmd_args and cmd_args[0] in cls.VERSION_FLAGS:
            return True, ""  # Safe: version/help check
        
        # Check if command is completely blocked (unless it's a version check)
        if base_cmd in cls.BLOCKED_COMMANDS:
            return False, f"Command '{base_cmd}' is not allowed - it can modify the system"
        
        # Check if command is in allowed list
        if base_cmd not in cls.ALLOWED_COMMANDS:
            return False, f"Command '{base_cmd}' is not in the allowed list of read-only commands"
        
        # Check for blocked subcommands
        if base_cmd in cls.BLOCKED_SUBCOMMANDS:
            blocked = cls.BLOCKED_SUBCOMMANDS[base_cmd]
            for arg in cmd_args:
                # Handle fdisk specially - only -l is allowed
                if base_cmd == "fdisk":
                    if arg not in ["-l", "--list"]:
                        return False, f"fdisk only allows -l/--list for listing partitions"
                elif arg in blocked:
                    return False, f"Subcommand '{arg}' is not allowed for '{base_cmd}' - it can modify the system"
        
        # Special handling for pip/pip3 - only allow show, list, freeze, check, config
        if base_cmd in ["pip", "pip3"]:
            if cmd_args:
                allowed_pip_cmds = {"show", "list", "freeze", "check", "config", "--version", "-V", "help", "--help"}
                if cmd_args[0] not in allowed_pip_cmds:
                    return False, f"pip command '{cmd_args[0]}' is not allowed - only read-only commands like 'show', 'list', 'freeze' are permitted"
        
        # Special handling for apt-mark - only showhold, showauto, showmanual
        if base_cmd == "apt-mark":
            if cmd_args:
                allowed_apt_mark = {"showhold", "showauto", "showmanual"}
                if cmd_args[0] not in allowed_apt_mark:
                    return False, f"apt-mark command '{cmd_args[0]}' is not allowed - only showhold, showauto, showmanual are permitted"
        
        # Special handling for docker/podman - allow info and list commands
        if base_cmd in ["docker", "podman"]:
            if cmd_args:
                allowed_docker_cmds = {
                    "ps", "images", "info", "version", "inspect", "logs", "top", "stats",
                    "port", "diff", "history", "search", "events", "container", "image",
                    "--version", "-v", "help", "--help",
                }
                # Also allow "container ls", "image ls", etc.
                if cmd_args[0] not in allowed_docker_cmds:
                    return False, f"docker command '{cmd_args[0]}' is not allowed - only read-only commands like 'ps', 'images', 'info', 'inspect', 'logs' are permitted"
                # Check container/image subcommands
                if cmd_args[0] in ["container", "image"] and len(cmd_args) > 1:
                    allowed_sub = {"ls", "list", "inspect", "history", "prune"}  # prune for info only
                    if cmd_args[1] not in allowed_sub and cmd_args[1] not in cls.VERSION_FLAGS:
                        return False, f"docker {cmd_args[0]} '{cmd_args[1]}' is not allowed - only ls, list, inspect are permitted"
        
        # Special handling for kubectl - allow get, describe, logs
        if base_cmd == "kubectl":
            if cmd_args:
                allowed_kubectl_cmds = {
                    "get", "describe", "logs", "top", "cluster-info", "config", "version",
                    "api-resources", "api-versions", "explain", "auth",
                    "--version", "-v", "help", "--help",
                }
                if cmd_args[0] not in allowed_kubectl_cmds:
                    return False, f"kubectl command '{cmd_args[0]}' is not allowed - only read-only commands like 'get', 'describe', 'logs' are permitted"
        
        # Special handling for git - allow status, log, show, diff, branch, remote, config (get)
        if base_cmd == "git":
            if cmd_args:
                allowed_git_cmds = {
                    "status", "log", "show", "diff", "branch", "remote", "tag", "describe",
                    "ls-files", "ls-tree", "ls-remote", "rev-parse", "rev-list", "cat-file",
                    "config", "shortlog", "blame", "annotate", "grep", "reflog",
                    "version", "--version", "-v", "help", "--help",
                }
                if cmd_args[0] not in allowed_git_cmds:
                    return False, f"git command '{cmd_args[0]}' is not allowed - only read-only commands like 'status', 'log', 'diff', 'branch' are permitted"
                # Block git config --set/--add
                if cmd_args[0] == "config" and any(a in cmd_args for a in ["--add", "--unset", "--remove-section", "--rename-section"]):
                    return False, "git config modifications are not allowed"
        
        # Special handling for snap/flatpak - allow list and info commands
        if base_cmd == "snap":
            if cmd_args:
                allowed_snap = {"list", "info", "find", "version", "connections", "services", "logs", "--version", "help", "--help"}
                if cmd_args[0] not in allowed_snap:
                    return False, f"snap command '{cmd_args[0]}' is not allowed - only list, info, find are permitted"
        
        if base_cmd == "flatpak":
            if cmd_args:
                allowed_flatpak = {"list", "info", "search", "remote-ls", "remotes", "history", "--version", "help", "--help"}
                if cmd_args[0] not in allowed_flatpak:
                    return False, f"flatpak command '{cmd_args[0]}' is not allowed - only list, info, search are permitted"
        
        # Special handling for AWS CLI - allow read-only commands
        if base_cmd == "aws":
            if cmd_args:
                allowed_aws = {"--version", "help", "--help", "sts", "configure"}
                # sts get-caller-identity is safe, configure list is safe
                if cmd_args[0] not in allowed_aws:
                    return False, f"aws command '{cmd_args[0]}' is not allowed - use 'sts get-caller-identity' or 'configure list' for read-only queries"
        
        # Special handling for apt - only allow list, show, search, policy, depends
        if base_cmd == "apt":
            if cmd_args:
                allowed_apt = {"list", "show", "search", "policy", "depends", "rdepends", "madison", "--version", "help", "--help"}
                if cmd_args[0] not in allowed_apt:
                    return False, f"apt command '{cmd_args[0]}' is not allowed - only list, show, search, policy are permitted for read-only queries"
            else:
                return False, "apt requires a subcommand like 'list', 'show', or 'search'"
        
        return True, ""
    
    @classmethod
    def execute_command(cls, command: str, timeout: int = 10) -> tuple[bool, str, str]:
        """Execute a validated command and return the result.
        
        For chained commands (&&, ||, ;), executes each command separately
        and combines the output.
        
        Args:
            command: The shell command to execute
            timeout: Maximum execution time in seconds
            
        Returns:
            Tuple of (success, stdout, stderr)
        """
        # Validate first
        is_valid, error = cls.validate_command(command)
        if not is_valid:
            return False, "", f"Command blocked: {error}"
        
        # Check if this is a chained command
        has_chaining = any(re.search(p, command) for p in cls.CHAINING_PATTERNS)
        
        if has_chaining:
            # Split and execute each command separately
            subcommands = cls.split_chained_commands(command)
            all_stdout = []
            all_stderr = []
            overall_success = True
            
            for subcmd in subcommands:
                try:
                    result = subprocess.run(
                        subcmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                    
                    if result.stdout.strip():
                        all_stdout.append(f"# {subcmd}\n{result.stdout.strip()}")
                    if result.stderr.strip():
                        all_stderr.append(f"# {subcmd}\n{result.stderr.strip()}")
                    
                    if result.returncode != 0:
                        overall_success = False
                        # For && chaining, stop on first failure
                        if "&&" in command:
                            break
                            
                except subprocess.TimeoutExpired:
                    all_stderr.append(f"# {subcmd}\nCommand timed out after {timeout} seconds")
                    overall_success = False
                    break
                except Exception as e:
                    all_stderr.append(f"# {subcmd}\nExecution failed: {e}")
                    overall_success = False
                    break
            
            return (
                overall_success,
                "\n\n".join(all_stdout),
                "\n\n".join(all_stderr),
            )
        
        # Single command
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return (
                result.returncode == 0,
                result.stdout.strip(),
                result.stderr.strip(),
            )
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", f"Command execution failed: {e}"


class AskHandler:
    """Handles natural language questions about the system using an agentic loop.
    
    The handler uses an iterative approach:
    1. LLM generates a read-only command to gather information
    2. Command is validated and executed
    3. Output is sent back to LLM
    4. LLM either generates another command or provides final answer
    5. Max 5 iterations before giving up
    
    In --do mode, the handler can execute write and modify commands with
    user confirmation and privilege management.
    """

    MAX_ITERATIONS = 5
    MAX_DO_ITERATIONS = 15  # More iterations for --do mode since it's solving problems

    def __init__(
        self,
        api_key: str,
        provider: str = "claude",
        model: str | None = None,
        debug: bool = False,
        do_mode: bool = False,
    ):
        """Initialize the ask handler.

        Args:
            api_key: API key for the LLM provider
            provider: Provider name ("openai", "claude", or "ollama")
            model: Optional model name override
            debug: Enable debug output to shell
            do_mode: Enable write/execute mode with user confirmation
        """
        self.api_key = api_key
        self.provider = provider.lower()
        self.model = model or self._default_model()
        self.debug = debug
        self.do_mode = do_mode
        
        # Import rich console for debug output
        if self.debug:
            from rich.console import Console
            from rich.panel import Panel
            self._console = Console()
        else:
            self._console = None
        
        # For expandable output storage
        self._last_output: str | None = None
        self._last_output_command: str | None = None
        
        # Interrupt flag - can be set externally to stop execution
        self._interrupted = False
        
        # Initialize DoHandler for --do mode
        self._do_handler = None
        if self.do_mode:
            try:
                from cortex.do_runner import DoHandler
                # Pass LLM callback so DoHandler can make LLM calls for interactive session
                self._do_handler = DoHandler(llm_callback=self._call_llm_for_do)
            except (ImportError, OSError, Exception) as e:
                # Log error but don't fail - do mode just won't work
                if self.debug and self._console:
                    self._console.print(f"[yellow]Warning: Could not initialize DoHandler: {e}[/yellow]")
                pass

        # Initialize cache
        try:
            from cortex.semantic_cache import SemanticCache

            self.cache: SemanticCache | None = SemanticCache()
        except (ImportError, OSError, sqlite3.OperationalError, Exception):
            self.cache = None

        self._initialize_client()

    def interrupt(self):
        """Interrupt the current operation. Call this from signal handlers."""
        self._interrupted = True
        # Also interrupt the DoHandler if it exists
        if self._do_handler:
            self._do_handler._interrupted = True
    
    def reset_interrupt(self):
        """Reset the interrupt flag before starting a new operation."""
        self._interrupted = False
        if self._do_handler:
            self._do_handler._interrupted = False

    def _default_model(self) -> str:
        if self.provider == "openai":
            return "gpt-4o"  # Use gpt-4o for 128K context
        elif self.provider == "claude":
            return "claude-sonnet-4-20250514"
        elif self.provider == "ollama":
            return "llama3.2"
        elif self.provider == "fake":
            return "fake"
        return "gpt-4o"
    
    def _debug_print(self, title: str, content: str, style: str = "dim") -> None:
        """Print debug output if debug mode is enabled."""
        if self.debug and self._console:
            from rich.panel import Panel
            self._console.print(Panel(content, title=f"[bold]{title}[/bold]", style=style))
    
    def _print_query_summary(self, question: str, commands_run: list[str], answer: str) -> None:
        """Print a condensed summary for question queries with improved visual design."""
        if not self._console:
            return
        
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        from rich import box
        
        # Clean the answer - remove any JSON/shell script that might have leaked
        clean_answer = answer
        import re
        
        # Check if answer looks like JSON or contains shell script fragments
        if clean_answer.startswith('{') or '{"' in clean_answer[:100]:
            # Try to extract just the answer field if present
            answer_match = re.search(r'"answer"\s*:\s*"([^"]*)"', clean_answer, re.DOTALL)
            if answer_match:
                clean_answer = answer_match.group(1)
                # Unescape common JSON escapes
                clean_answer = clean_answer.replace('\\n', '\n').replace('\\"', '"')
        
        # Remove shell script-like content that shouldn't be in the answer
        if re.search(r'^(if \[|while |for |echo \$|sed |awk |grep -)', clean_answer, re.MULTILINE):
            # This looks like shell script leaked - try to extract readable parts
            readable_lines = []
            for line in clean_answer.split('\n'):
                # Keep lines that look like actual content, not script
                if not re.match(r'^(if \[|fi$|done$|else$|then$|do$|while |for |echo \$|sed |awk )', line.strip()):
                    if line.strip() and not line.strip().startswith('#!'):
                        readable_lines.append(line)
            if readable_lines:
                clean_answer = '\n'.join(readable_lines[:20])  # Limit to 20 lines
        
        self._console.print()
        
        # Query section
        q_display = question[:80] + "..." if len(question) > 80 else question
        self._console.print(Panel(
            f"[bold]{q_display}[/bold]",
            title="[bold white on blue] 🔍 Query [/bold white on blue]",
            title_align="left",
            border_style="blue",
            padding=(0, 1),
            expand=False,
        ))
        
        # Info gathered section
        if commands_run:
            info_table = Table(
                show_header=False,
                box=box.SIMPLE,
                padding=(0, 1),
                expand=True,
            )
            info_table.add_column("", style="dim")
            
            for cmd in commands_run[:4]:
                cmd_display = cmd[:60] + "..." if len(cmd) > 60 else cmd
                info_table.add_row(f"$ {cmd_display}")
            if len(commands_run) > 4:
                info_table.add_row(f"[dim]... and {len(commands_run) - 4} more commands[/dim]")
            
            self._console.print(Panel(
                info_table,
                title=f"[bold] 📊 Info Gathered ({len(commands_run)} commands) [/bold]",
                title_align="left",
                border_style="dim",
                padding=(0, 0),
            ))
        
        # Answer section - make it prominent
        if clean_answer.strip():
            # Truncate very long answers
            if len(clean_answer) > 800:
                display_answer = clean_answer[:800] + "\n\n[dim]... (answer truncated)[/dim]"
            else:
                display_answer = clean_answer
            
            self._console.print(Panel(
                display_answer,
                title="[bold white on green] 💡 Answer [/bold white on green]",
                title_align="left",
                border_style="green",
                padding=(1, 2),
            ))
    
    def _show_expandable_output(self, console, output: str, command: str) -> None:
        """Show output with expand/collapse capability."""
        from rich.panel import Panel
        from rich.text import Text
        
        lines = output.split('\n')
        total_lines = len(lines)
        
        # Always show first 3 lines as preview
        preview_count = 3
        
        if total_lines <= preview_count + 2:
            # Small output - just show it all
            console.print(Panel(
                output,
                title=f"[dim]Output[/dim]",
                title_align="left",
                border_style="dim",
                padding=(0, 1),
            ))
            return
        
        # Show collapsed preview with expand option
        preview = '\n'.join(lines[:preview_count])
        remaining = total_lines - preview_count
        
        # Build the panel content
        content = Text()
        content.append(preview)
        content.append(f"\n\n[dim]─── {remaining} more lines hidden ───[/dim]", style="dim")
        
        console.print(Panel(
            content,
            title=f"[dim]Output ({total_lines} lines)[/dim]",
            subtitle="[dim italic]Type 'e' to expand[/dim italic]",
            subtitle_align="right",
            title_align="left",
            border_style="dim",
            padding=(0, 1),
        ))
        
        # Store for potential expansion
        self._last_output = output
        self._last_output_command = command

    def _initialize_client(self):
        if self.provider == "openai":
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("OpenAI package not installed. Run: pip install openai")
        elif self.provider == "claude":
            try:
                from anthropic import Anthropic
                import logging
                # Suppress noisy retry logging from anthropic client
                logging.getLogger("anthropic").setLevel(logging.WARNING)
                logging.getLogger("anthropic._base_client").setLevel(logging.WARNING)
                
                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("Anthropic package not installed. Run: pip install anthropic")
        elif self.provider == "ollama":
            self.ollama_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            self.client = None
        elif self.provider == "fake":
            self.client = None
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _get_system_prompt(self) -> str:
        if self.do_mode:
            return self._get_do_mode_system_prompt()
        return self._get_read_only_system_prompt()
    
    def _get_read_only_system_prompt(self) -> str:
        return """You are a Linux system assistant that answers questions by executing read-only shell commands.

SCOPE RESTRICTION - VERY IMPORTANT:
You are ONLY a Linux/system administration assistant. You can ONLY help with:
- Linux system administration, configuration, and troubleshooting
- Package management (apt, snap, flatpak, pip, npm, etc.)
- Service management (systemctl, docker, etc.)
- File system operations and permissions
- Networking and security
- Development environment setup
- Server configuration

If the user asks about anything unrelated to Linux/technical topics (social chat, personal advice, 
creative writing, general knowledge questions not related to their system, etc.), you MUST respond with:
{
    "response_type": "answer",
    "answer": "I'm Cortex, a Linux system assistant. I can only help with Linux system administration, package management, and technical tasks on your machine. I can't help with non-technical topics. Is there something I can help you with on your system?",
    "reasoning": "User query is outside my scope as a Linux system assistant"
}

Your task is to help answer the user's question about their system by:
1. Generating shell commands to gather the needed information
2. Analyzing the command output
3. Either generating another command if more info is needed, or providing the final answer

IMPORTANT RULES:
- You can ONLY use READ-ONLY commands that fetch data (no modifications allowed)
- Allowed commands include: cat, ls, grep, find, dpkg-query, apt-cache, pip3 show/list, ps, df, free, uname, lscpu, etc.
- NEVER use commands that modify the system (rm, mv, cp, apt install, pip install, etc.)
- NEVER use sudo
- NEVER use output redirection (>, >>), command chaining (;, &&, ||), or command substitution ($(), ``)

CRITICAL: You must respond with ONLY a JSON object - no other text before or after.
Do NOT include explanations outside the JSON. Put all reasoning inside the "reasoning" field.

JSON format:
{
    "response_type": "command" | "answer",
    "command": "<shell command to execute>" (only if response_type is "command"),
    "answer": "<your answer to the user>" (only if response_type is "answer"),
    "reasoning": "<brief explanation of your choice>"
}

Examples of ALLOWED commands:
- cat /etc/os-release
- dpkg-query -W -f='${Version}' python3
- pip3 show numpy
- pip3 list
- ls -la /usr/bin/python*
- uname -a
- lscpu
- free -h
- df -h
- ps aux | grep python
- apt-cache show nginx
- systemctl status nginx (read-only status check)

Examples of BLOCKED commands (NEVER use these):
- sudo anything
- apt install/remove
- pip install/uninstall
- rm, mv, cp, mkdir, touch
- echo "text" > file
- command1 && command2"""
    
    def _get_do_mode_system_prompt(self) -> str:
        return """You are a Linux system assistant that can READ, WRITE, and EXECUTE commands to solve problems.

SCOPE RESTRICTION - VERY IMPORTANT:
You are ONLY a Linux/system administration assistant. You can ONLY help with:
- Linux system administration, configuration, and troubleshooting
- Package management (apt, snap, flatpak, pip, npm, etc.)
- Service management (systemctl, docker, etc.)
- File system operations and permissions
- Networking and security
- Development environment setup
- Server configuration

If the user asks about anything unrelated to Linux/technical topics (social chat, personal advice, 
creative writing, general knowledge questions not related to their system, etc.), you MUST respond with:
{
    "response_type": "answer",
    "answer": "I'm Cortex, a Linux system assistant. I can only help with Linux system administration, package management, and technical tasks on your machine. I can't help with non-technical topics. What would you like me to do on your system?",
    "reasoning": "User query is outside my scope as a Linux system assistant"
}

You are in DO MODE - you have the ability to make changes to the system to solve the user's problem.

Your task is to:
1. Understand the user's problem or request
2. Quickly gather essential information (1-3 read commands MAX)
3. Plan and propose a solution with specific commands using "do_commands"
4. Execute the solution with the user's permission
5. Handle failures gracefully with repair attempts

CRITICAL WORKFLOW RULES:
- DO NOT spend more than 3-4 iterations gathering information
- After gathering basic system info (OS, existing packages), IMMEDIATELY propose do_commands
- If you know how to install/configure something, propose do_commands right away
- Be action-oriented: the user wants you to DO something, not just analyze
- You can always gather more info AFTER the user approves the commands if needed

WORKFLOW:
1. Quickly gather essential info (OS version, if package exists) - MAX 2-3 commands
2. IMMEDIATELY propose "do_commands" with your installation/setup plan
3. The do_commands will be shown to the user for approval before execution
4. Commands are executed using a TASK TREE system with auto-repair capabilities:
   - If a command fails, Cortex will automatically diagnose the error
   - Repair sub-tasks may be spawned and executed with additional permission requests
   - Terminal monitoring is available during manual intervention
5. After execution, verify the changes worked and provide a final "answer"
6. If execution_failures appear in history, propose alternative solutions

CRITICAL: You must respond with ONLY a JSON object - no other text before or after.
Do NOT include explanations outside the JSON. Put all reasoning inside the "reasoning" field.

For gathering information (read-only):
{
    "response_type": "command",
    "command": "<shell command to execute>",
    "reasoning": "<why you need this information>"
}

For proposing changes (write/execute):
{
    "response_type": "do_commands",
    "do_commands": [
        {
            "command": "<shell command>",
            "purpose": "<what this command does and why>",
            "requires_sudo": true/false
        }
    ],
    "reasoning": "<overall explanation of the solution>"
}

For final answer:
{
    "response_type": "answer",
    "answer": "<final response to user, summarizing what was done>",
    "reasoning": "<explanation>"
}

For proposing repair commands after failures:
{
    "response_type": "do_commands",
    "do_commands": [
        {
            "command": "<diagnostic or repair command>",
            "purpose": "<why this will help fix the previous failure>",
            "requires_sudo": true/false
        }
    ],
    "reasoning": "<analysis of what went wrong and how this will fix it>"
}

HANDLING FAILURES:
- When you see "execution_failures" in history, analyze the error messages carefully
- Common errors and their fixes:
  * "Permission denied" → Add sudo, check ownership, or run with elevated privileges
  * "No such file or directory" → Create parent directories first (mkdir -p)
  * "Command not found" → Install the package (apt install)
  * "Service not running" → Start the service first (systemctl start)
  * "Configuration syntax error" → Read config file, find and fix the error
- Always provide detailed reasoning when proposing repairs
- If the original approach won't work, suggest an alternative approach
- You may request multiple rounds of commands to diagnose and fix issues

IMPORTANT RULES:
- BE ACTION-ORIENTED: After 2-3 info commands, propose do_commands immediately
- DO NOT over-analyze: You have enough info once you know the OS and if basic packages exist
- For installation tasks: Propose the installation commands right away
- For do_commands, each command should be atomic and specific
- Always include a clear purpose for each command
- Mark requires_sudo: true if the command needs root privileges
- Be careful with destructive commands - always explain what they do
- After making changes, verify they worked before giving final answer
- If something fails, diagnose and try alternative approaches
- Multiple permission requests may be made during a single session for repair commands

ANTI-PATTERNS TO AVOID:
- Don't keep gathering info for more than 3 iterations
- Don't check every possible thing before proposing a solution
- Don't be overly cautious - the user wants action
- If you know how to solve the problem, propose do_commands NOW

PROTECTED PATHS (will require user authentication):
- /etc/* - System configuration
- /boot/* - Boot configuration  
- /usr/bin, /usr/sbin, /sbin, /bin - System binaries
- /root - Root home directory
- /var/log, /var/lib/apt - System data

COMMAND RESTRICTIONS:
- Use SINGLE commands only - no chaining with &&, ||, or ;
- Use pipes (|) sparingly and only for filtering
- No output redirection (>, >>) in read commands
- If you need multiple commands, return them separately in sequence

Examples of READ commands:
- cat /etc/nginx/nginx.conf
- ls -la /var/log/
- systemctl status nginx
- grep -r "error" /var/log/syslog
- dpkg -l | grep nginx
- apt list --installed | grep docker (use apt list, not apt install)

Examples of WRITE/EXECUTE commands (use with do_commands):
- echo 'server_name example.com;' >> /etc/nginx/sites-available/default
- systemctl restart nginx
- apt install -y nginx
- chmod 755 /var/www/html
- mkdir -p /etc/myapp
- cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.backup

Examples of REPAIR commands after failures:
- sudo chown -R $USER:$USER /path/to/file  # Fix ownership issues
- sudo mkdir -p /path/to/directory  # Create missing directories
- sudo apt install -y missing-package  # Install missing dependencies
- journalctl -u service-name -n 50 --no-pager  # Diagnose service issues"""

    # Maximum characters of command output to include in history
    MAX_OUTPUT_CHARS = 2000
    
    def _truncate_output(self, output: str) -> str:
        """Truncate command output to avoid context length issues."""
        if len(output) <= self.MAX_OUTPUT_CHARS:
            return output
        # Keep first and last portions
        half = self.MAX_OUTPUT_CHARS // 2
        return f"{output[:half]}\n\n... [truncated {len(output) - self.MAX_OUTPUT_CHARS} chars] ...\n\n{output[-half:]}"
    
    def _build_iteration_prompt(
        self, 
        question: str, 
        history: list[dict[str, str]]
    ) -> str:
        """Build the prompt for the current iteration."""
        prompt = f"User Question: {question}\n\n"
        
        if history:
            prompt += "Previous commands and results:\n"
            for i, entry in enumerate(history, 1):
                # Handle execution_failures context from do_commands
                if entry.get("type") == "execution_failures":
                    prompt += f"\n--- EXECUTION FAILURES (Need Repair) ---\n"
                    prompt += f"Message: {entry.get('message', 'Commands failed')}\n"
                    for fail in entry.get("failures", []):
                        prompt += f"\nFailed Command: {fail.get('command', 'unknown')}\n"
                        prompt += f"Purpose: {fail.get('purpose', 'unknown')}\n"
                        prompt += f"Error: {fail.get('error', 'unknown')}\n"
                    prompt += "\nPlease analyze these failures and propose repair commands or alternative approaches.\n"
                    continue
                
                # Handle regular commands
                prompt += f"\n--- Attempt {i} ---\n"
                
                # Check if this is a do_command execution result
                if "executed_by" in entry:
                    prompt += f"Command (executed by {entry['executed_by']}): {entry.get('command', 'unknown')}\n"
                    prompt += f"Purpose: {entry.get('purpose', 'unknown')}\n"
                    if entry.get('success'):
                        truncated_output = self._truncate_output(entry.get('output', ''))
                        prompt += f"Status: SUCCESS\nOutput:\n{truncated_output}\n"
                    else:
                        prompt += f"Status: FAILED\nError: {entry.get('error', 'unknown')}\n"
                else:
                    prompt += f"Command: {entry.get('command', 'unknown')}\n"
                    if entry.get('success'):
                        truncated_output = self._truncate_output(entry.get('output', ''))
                        prompt += f"Output:\n{truncated_output}\n"
                    else:
                        prompt += f"Error: {entry.get('error', 'unknown')}\n"
            
            prompt += "\n"
            
            # Check if there were recent failures
            has_failures = any(
                e.get("type") == "execution_failures" or 
                (e.get("executed_by") and not e.get("success"))
                for e in history[-5:]  # Check last 5 entries
            )
            
            if has_failures:
                prompt += "IMPORTANT: There were command failures. Please:\n"
                prompt += "1. Analyze the error messages to understand what went wrong\n"
                prompt += "2. Propose repair commands using 'do_commands' response type\n"
                prompt += "3. Or suggest an alternative approach if the original won't work\n"
            else:
                prompt += "Based on the above results, either provide another command to gather more information, or provide the final answer.\n"
        else:
            prompt += "Generate a shell command to gather the information needed to answer this question.\n"
        
        prompt += "\nRespond with a JSON object as specified in the system prompt."
        return prompt

    def _clean_llm_response(self, text: str) -> str:
        """Clean raw LLM response to prevent JSON from being displayed to user.
        
        Extracts meaningful content like reasoning or answer from raw JSON,
        or returns a generic error message if the response is pure JSON.
        
        NOTE: This is only called as a fallback when JSON parsing fails.
        We should NOT return placeholder messages for valid response types.
        """
        import re
        
        # If it looks like pure JSON, don't show it to user
        text = text.strip()
        
        # Check for partial JSON (starts with ], }, or other JSON fragments)
        if text.startswith((']', '},', ',"', '"response_type"', '"do_commands"', '"command"', '"reasoning"')):
            return ""  # Return empty so loop continues
        
        if text.startswith('{') and text.endswith('}'):
            # Try to extract useful fields
            try:
                data = json.loads(text)
                # Try to get meaningful content in order of preference
                if data.get("answer"):
                    return data["answer"]
                if data.get("reasoning") and data.get("response_type") == "answer":
                    # Only use reasoning if it's an answer type
                    reasoning = data["reasoning"]
                    if not any(p in reasoning for p in ['"command":', '"do_commands":', '"requires_sudo":']):
                        return f"Analysis: {reasoning}"
                # For do_commands or command types, return empty to let parsing retry
                if data.get("do_commands") or data.get("command"):
                    return ""  # Return empty so the proper parsing can happen
                # Pure JSON with no useful fields
                return ""
            except json.JSONDecodeError:
                pass
        
        # Check for JSON-like patterns in the text
        json_patterns = [
            r'"response_type"\s*:\s*"',
            r'"do_commands"\s*:\s*\[',
            r'"command"\s*:\s*"',
            r'"requires_sudo"\s*:\s*',
            r'\[\s*\{',  # Start of array of objects
            r'\}\s*,\s*\{',  # Object separator
            r'\]\s*,\s*"',  # End of array followed by key
        ]
        
        # If text contains raw JSON patterns, try to extract non-JSON parts
        has_json_patterns = any(re.search(p, text) for p in json_patterns)
        if has_json_patterns:
            # Try to find text before or after JSON
            parts = re.split(r'\{[\s\S]*"response_type"[\s\S]*\}', text)
            clean_parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 20]
            if clean_parts:
                # Filter out parts that still look like JSON
                clean_parts = [p for p in clean_parts if not any(j in p for j in ['":', '",', '{}', '[]'])]
                if clean_parts:
                    return " ".join(clean_parts)
            
            # No good text found, return generic message
            return "I'm processing your request. Please wait for the proper output."
        
        # Text doesn't look like JSON, return as-is
        return text

    def _parse_llm_response(self, response_text: str) -> SystemCommand:
        """Parse the LLM response into a SystemCommand object."""
        # Try to extract JSON from the response
        original_text = response_text.strip()
        response_text = original_text
        
        # Handle markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            parts = response_text.split("```")
            if len(parts) >= 2:
                response_text = parts[1].split("```")[0].strip()
        
        # Try direct JSON parsing first
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text (LLM sometimes adds prose before/after)
            json_match = re.search(r'\{[\s\S]*"response_type"[\s\S]*\}', original_text)
            if json_match:
                try:
                    # Find the complete JSON object by matching braces
                    json_str = json_match.group()
                    # Balance braces to get complete JSON
                    brace_count = 0
                    json_end = 0
                    for i, char in enumerate(json_str):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                json_end = i + 1
                                break
                    
                    if json_end > 0:
                        json_str = json_str[:json_end]
                    
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    # If still fails, don't show raw JSON to user
                    clean_answer = self._clean_llm_response(original_text)
                    return SystemCommand(
                        response_type=LLMResponseType.ANSWER,
                        answer=clean_answer,
                        reasoning="Could not parse structured response, treating as direct answer"
                    )
            else:
                # No JSON found, clean up before treating as direct answer
                clean_answer = self._clean_llm_response(original_text)
                return SystemCommand(
                    response_type=LLMResponseType.ANSWER,
                    answer=clean_answer,
                    reasoning="No JSON structure found, treating as direct answer"
                )
        
        try:
            # Handle do_commands - convert dict list to DoCommand objects
            if data.get("response_type") == "do_commands" and "do_commands" in data:
                data["do_commands"] = [
                    DoCommand(**cmd) if isinstance(cmd, dict) else cmd 
                    for cmd in data["do_commands"]
                ]
            
            return SystemCommand(**data)
        except Exception as e:
            # If SystemCommand creation fails, don't show raw JSON to user
            clean_answer = self._clean_llm_response(original_text)
            return SystemCommand(
                response_type=LLMResponseType.ANSWER,
                answer=clean_answer,
                reasoning=f"Failed to create SystemCommand: {e}"
            )

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM and return the response text."""
        # Check for interrupt before making API call
        if self._interrupted:
            raise InterruptedError("Operation interrupted by user")
        
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )
            try:
                content = response.choices[0].message.content or ""
            except (IndexError, AttributeError):
                content = ""
            return content.strip()
            
        elif self.provider == "claude":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            try:
                text = getattr(response.content[0], "text", None) or ""
            except (IndexError, AttributeError):
                text = ""
            return text.strip()
            
        elif self.provider == "ollama":
            import urllib.request

            url = f"{self.ollama_url}/api/generate"
            prompt = f"{system_prompt}\n\n{user_prompt}"

            data = json.dumps({
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3},
            }).encode("utf-8")

            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result.get("response", "").strip()
                
        elif self.provider == "fake":
            # For testing - return a simple answer
            fake_response = os.environ.get("CORTEX_FAKE_RESPONSE", "")
            if fake_response:
                return fake_response
            return json.dumps({
                "response_type": "answer",
                "answer": "Test mode response",
                "reasoning": "Fake provider for testing"
            })
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _call_llm_for_do(self, user_request: str, context: dict | None = None) -> dict:
        """Call LLM to process a natural language request for the interactive session.
        
        This is passed to DoHandler as a callback so it can make LLM calls
        during the interactive session.
        
        Args:
            user_request: The user's natural language request
            context: Optional context dict with executed_commands, session_actions, etc.
        
        Returns:
            Dict with either:
            - {"response_type": "do_commands", "do_commands": [...], "reasoning": "..."}
            - {"response_type": "answer", "answer": "...", "reasoning": "..."}
            - {"response_type": "command", "command": "...", "reasoning": "..."}
        """
        context = context or {}
        
        system_prompt = """You are a Linux system assistant in an interactive session.
The user has just completed some tasks and now wants to do something else.

SCOPE RESTRICTION:
You can ONLY help with Linux/technical topics. If the user asks about anything unrelated 
(social chat, personal advice, general knowledge, etc.), respond with:
{
    "response_type": "answer",
    "answer": "I'm Cortex, a Linux system assistant. I can only help with Linux system administration and technical tasks. What would you like me to do on your system?",
    "reasoning": "User query is outside my scope"
}

Based on their request, decide what to do:
1. If they want to EXECUTE commands (install, configure, start, etc.), respond with do_commands
2. If they want INFORMATION (show, explain, how to), respond with an answer
3. If they want to RUN a single read-only command, respond with command

CRITICAL: Respond with ONLY a JSON object - no other text.

For executing commands:
{
    "response_type": "do_commands",
    "do_commands": [
        {"command": "...", "purpose": "...", "requires_sudo": true/false}
    ],
    "reasoning": "..."
}

For providing information:
{
    "response_type": "answer", 
    "answer": "...",
    "reasoning": "..."
}

For running a read-only command:
{
    "response_type": "command",
    "command": "...",
    "reasoning": "..."
}
"""
        
        # Build context-aware prompt
        user_prompt = f"Context:\n"
        if context.get("original_query"):
            user_prompt += f"- Original task: {context['original_query']}\n"
        if context.get("executed_commands"):
            user_prompt += f"- Commands already executed: {', '.join(context['executed_commands'][:5])}\n"
        if context.get("session_actions"):
            user_prompt += f"- Actions in this session: {', '.join(context['session_actions'][:3])}\n"
        
        user_prompt += f"\nUser request: {user_request}\n"
        user_prompt += "\nRespond with a JSON object."
        
        try:
            response_text = self._call_llm(system_prompt, user_prompt)
            
            # Parse the response
            parsed = self._parse_llm_response(response_text)
            
            # Convert to dict
            result = {
                "response_type": parsed.response_type.value,
                "reasoning": parsed.reasoning,
            }
            
            if parsed.response_type == LLMResponseType.DO_COMMANDS and parsed.do_commands:
                result["do_commands"] = [
                    {"command": cmd.command, "purpose": cmd.purpose, "requires_sudo": cmd.requires_sudo}
                    for cmd in parsed.do_commands
                ]
            elif parsed.response_type == LLMResponseType.COMMAND and parsed.command:
                result["command"] = parsed.command
            elif parsed.response_type == LLMResponseType.ANSWER and parsed.answer:
                result["answer"] = parsed.answer
            
            return result
            
        except Exception as e:
            return {
                "response_type": "error",
                "error": str(e),
            }

    def ask(self, question: str) -> str:
        """Ask a natural language question about the system.

        Uses an agentic loop to execute read-only commands and gather information
        to answer the user's question.
        
        In --do mode, can also execute write/modify commands with user confirmation.

        Args:
            question: Natural language question

        Returns:
            Human-readable answer string

        Raises:
            ValueError: If question is empty
            RuntimeError: If LLM API call fails
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        question = question.strip()
        system_prompt = self._get_system_prompt()
        
        # Don't cache in do_mode (each run is unique)
        cache_key = f"ask:v2:{question}"
        if self.cache is not None and not self.do_mode:
            cached = self.cache.get_commands(
                prompt=cache_key,
                provider=self.provider,
                model=self.model,
                system_prompt=system_prompt,
            )
            if cached is not None and len(cached) > 0:
                return cached[0]

        # Agentic loop
        history: list[dict[str, Any]] = []
        tried_commands: list[str] = []
        max_iterations = self.MAX_DO_ITERATIONS if self.do_mode else self.MAX_ITERATIONS
        
        if self.debug:
            mode_str = "[DO MODE]" if self.do_mode else ""
            self._debug_print("Ask Query", f"{mode_str} Question: {question}", style="cyan")
        
        # Import console for progress output
        from rich.console import Console
        loop_console = Console()
        
        for iteration in range(max_iterations):
            # Check for interrupt at start of each iteration
            if self._interrupted:
                self._interrupted = False  # Reset for next request
                return "Operation interrupted by user."
            
            if self.debug:
                self._debug_print(
                    f"Iteration {iteration + 1}/{max_iterations}",
                    f"Calling LLM ({self.provider}/{self.model})...",
                    style="blue"
                )
            
            # Show progress to user (even without --debug)
            if self.do_mode and iteration > 0:
                from rich.panel import Panel
                loop_console.print()
                loop_console.print(Panel(
                    f"[bold cyan]Analyzing results...[/bold cyan]  [dim]Step {iteration + 1}[/dim]",
                    border_style="dim cyan",
                    padding=(0, 1),
                    expand=False,
                ))
            
            # Build prompt with history
            user_prompt = self._build_iteration_prompt(question, history)
            
            # Call LLM
            try:
                response_text = self._call_llm(system_prompt, user_prompt)
                # Check for interrupt after LLM call
                if self._interrupted:
                    self._interrupted = False
                    return "Operation interrupted by user."
            except InterruptedError:
                # Explicitly interrupted
                self._interrupted = False
                return "Operation interrupted by user."
            except Exception as e:
                if self._interrupted:
                    self._interrupted = False
                    return "Operation interrupted by user."
                raise RuntimeError(f"LLM API call failed: {str(e)}")
            
            if self.debug:
                self._debug_print("LLM Raw Response", response_text[:500] + ("..." if len(response_text) > 500 else ""), style="dim")
            
            # Parse response
            parsed = self._parse_llm_response(response_text)
            
            if self.debug:
                self._debug_print(
                    "LLM Parsed Response",
                    f"Type: {parsed.response_type.value}\n"
                    f"Reasoning: {parsed.reasoning}\n"
                    f"Command: {parsed.command or 'N/A'}\n"
                    f"Do Commands: {len(parsed.do_commands) if parsed.do_commands else 0}\n"
                    f"Answer: {(parsed.answer[:100] + '...') if parsed.answer and len(parsed.answer) > 100 else parsed.answer or 'N/A'}",
                    style="yellow"
                )
            
            # Show what the LLM decided to do
            if self.do_mode and not self.debug:
                from rich.panel import Panel
                if parsed.response_type == LLMResponseType.COMMAND and parsed.command:
                    loop_console.print(Panel(
                        f"[bold]🔍 Gathering info[/bold]\n[cyan]{parsed.command}[/cyan]",
                        border_style="blue",
                        padding=(0, 1),
                        expand=False,
                    ))
                elif parsed.response_type == LLMResponseType.DO_COMMANDS and parsed.do_commands:
                    loop_console.print(Panel(
                        f"[bold green]📋 Ready to execute[/bold green] [white]{len(parsed.do_commands)} command(s)[/white]",
                        border_style="green",
                        padding=(0, 1),
                        expand=False,
                    ))
                elif parsed.response_type == LLMResponseType.ANSWER and parsed.answer:
                    pass  # Will be handled below
                else:
                    # LLM returned an unexpected or empty response
                    loop_console.print(f"[dim yellow]⏳ Waiting for LLM to propose commands...[/dim yellow]")
            
            # If LLM provides a final answer, return it
            if parsed.response_type == LLMResponseType.ANSWER:
                answer = parsed.answer or ""
                
                # Skip empty answers (parsing fallback that should continue loop)
                if not answer.strip():
                    if self.do_mode:
                        loop_console.print(f"[dim]   (waiting for LLM to propose commands...)[/dim]")
                    continue
                
                if self.debug:
                    self._debug_print("Final Answer", answer, style="green")
                
                # Cache the response (not in do_mode)
                if self.cache is not None and answer and not self.do_mode:
                    try:
                        self.cache.put_commands(
                            prompt=cache_key,
                            provider=self.provider,
                            model=self.model,
                            system_prompt=system_prompt,
                            commands=[answer],
                        )
                    except (OSError, sqlite3.Error):
                        pass
                
                # Print condensed summary for questions
                self._print_query_summary(question, tried_commands, answer)
                
                return answer
            
            # Handle do_commands in --do mode
            if parsed.response_type == LLMResponseType.DO_COMMANDS and self.do_mode:
                if not parsed.do_commands:
                    # LLM said do_commands but provided none - ask it to try again
                    loop_console.print(f"[yellow]⚠ LLM response incomplete, retrying...[/yellow]")
                    history.append({
                        "type": "error",
                        "message": "Response contained no commands. Please provide specific commands to execute.",
                    })
                    continue
                    
                result = self._handle_do_commands(parsed, question, history)
                if result is not None:
                    # Result is either a completion message or None (continue loop)
                    return result
            
            # LLM wants to execute a read-only command
            if parsed.command:
                command = parsed.command
                tried_commands.append(command)
                
                if self.debug:
                    self._debug_print("Executing Command", f"$ {command}", style="magenta")
                
                # Validate and execute the command
                success, stdout, stderr = CommandValidator.execute_command(command)
                
                # Show execution result to user with expandable output
                if self.do_mode and not self.debug:
                    if success:
                        output_lines = len(stdout.split('\n')) if stdout else 0
                        loop_console.print(f"[green]   ✓ Got {output_lines} lines of output[/green]")
                        
                        # Show expandable output
                        if stdout and output_lines > 0:
                            self._show_expandable_output(loop_console, stdout, command)
                    else:
                        loop_console.print(f"[yellow]   ⚠ Command failed: {stderr[:100]}[/yellow]")
                
                if self.debug:
                    if success:
                        output_preview = stdout[:1000] + ("..." if len(stdout) > 1000 else "") if stdout else "(empty output)"
                        self._debug_print("Command Output (SUCCESS)", output_preview, style="green")
                    else:
                        self._debug_print("Command Output (FAILED)", f"Error: {stderr}", style="red")
                
                history.append({
                    "command": command,
                    "success": success,
                    "output": stdout if success else "",
                    "error": stderr if not success else "",
                })
                continue  # Continue to next iteration with new info
            
            # If we get here, no valid action was taken
            # This means LLM returned something we couldn't use
            if self.do_mode and not self.debug:
                if parsed.reasoning:
                    # Show reasoning if available
                    loop_console.print(f"[dim]   LLM: {parsed.reasoning[:100]}{'...' if len(parsed.reasoning) > 100 else ''}[/dim]")
        
        # Max iterations reached
        if self.do_mode:
            if tried_commands:
                commands_list = "\n".join(f"  - {cmd}" for cmd in tried_commands)
                result = f"The LLM gathered information but didn't propose any commands to execute.\n\nInfo gathered with:\n{commands_list}\n\nTry being more specific about what you want to do."
            else:
                result = "The LLM couldn't determine what commands to run. Try rephrasing your request with more specific details."
            
            loop_console.print(f"[yellow]⚠ {result}[/yellow]")
        else:
            commands_list = "\n".join(f"  - {cmd}" for cmd in tried_commands)
            result = f"Could not find an answer after {max_iterations} attempts.\n\nTried commands:\n{commands_list}"
        
        if self.debug:
            self._debug_print("Max Iterations Reached", result, style="red")
        
        return result
    
    def _handle_do_commands(
        self, 
        parsed: SystemCommand, 
        question: str,
        history: list[dict[str, Any]]
    ) -> str | None:
        """Handle do_commands response type - execute with user confirmation.
        
        Uses task tree execution for advanced auto-repair capabilities:
        - Spawns repair sub-tasks when commands fail
        - Requests additional permissions during execution
        - Monitors terminals during manual intervention
        - Provides detailed failure reasoning
        
        Returns:
            Result string if completed, None if should continue loop,
            or "USER_DECLINED:..." if user declined.
        """
        if not self._do_handler or not parsed.do_commands:
            return None
        
        from rich.console import Console
        console = Console()
        
        # Prepare commands for analysis
        commands = [
            (cmd.command, cmd.purpose) for cmd in parsed.do_commands
        ]
        
        # Analyze for protected paths
        analyzed = self._do_handler.analyze_commands_for_protected_paths(commands)
        
        # Show reasoning
        console.print()
        console.print(f"[bold cyan]🤖 Cortex Analysis:[/bold cyan] {parsed.reasoning}")
        console.print()
        
        # Show task tree preview
        console.print("[dim]📋 Planned tasks:[/dim]")
        for i, (cmd, purpose, protected) in enumerate(analyzed, 1):
            protected_note = f" [yellow](protected: {', '.join(protected)})[/yellow]" if protected else ""
            console.print(f"[dim]   {i}. {cmd[:60]}...{protected_note}[/dim]")
        console.print()
        
        # Request user confirmation
        if self._do_handler.request_user_confirmation(analyzed):
            # User approved - execute using task tree for better error handling
            run = self._do_handler.execute_with_task_tree(analyzed, question)
            
            # Add execution results to history
            for cmd_log in run.commands:
                history.append({
                    "command": cmd_log.command,
                    "success": cmd_log.status.value == "success",
                    "output": cmd_log.output,
                    "error": cmd_log.error,
                    "purpose": cmd_log.purpose,
                    "executed_by": "cortex" if "Manual execution" not in (cmd_log.purpose or "") else "user_manual",
                })
            
            # Check if any commands were completed manually during execution
            manual_completed = self._do_handler.get_completed_manual_commands()
            if manual_completed:
                history.append({
                    "type": "commands_completed_manually",
                    "commands": manual_completed,
                    "message": f"User manually executed these commands successfully: {', '.join(manual_completed)}. Do NOT re-propose them.",
                })
            
            # Check if there were failures that need LLM input
            failures = [c for c in run.commands if c.status.value == "failed"]
            if failures:
                # Add failure context to history for LLM to help with
                failure_summary = []
                for f in failures:
                    failure_summary.append({
                        "command": f.command,
                        "error": f.error[:500] if f.error else "Unknown error",
                        "purpose": f.purpose,
                    })
                
                history.append({
                    "type": "execution_failures",
                    "failures": failure_summary,
                    "message": f"{len(failures)} command(s) failed during execution. Please analyze and suggest fixes.",
                })
                
                # Continue loop so LLM can suggest next steps
                return None
            
            # All commands succeeded (automatically or manually)
            successes = [c for c in run.commands if c.status.value == "success"]
            if successes and not failures:
                # Everything worked - return success message
                summary = run.summary or f"Successfully executed {len(successes)} command(s)"
                return f"✅ {summary}"
            
            # Return summary for now - LLM will provide final answer in next iteration
            return None
        else:
            # User declined automatic execution - provide manual instructions with monitoring
            run = self._do_handler.provide_manual_instructions(analyzed, question)
            
            # Check if any commands were completed manually
            manual_completed = self._do_handler.get_completed_manual_commands()
            
            # Check success/failure status from the run
            from cortex.do_runner.models import CommandStatus
            successful_count = sum(1 for c in run.commands if c.status == CommandStatus.SUCCESS)
            failed_count = sum(1 for c in run.commands if c.status == CommandStatus.FAILED)
            total_expected = len(analyzed)
            
            if manual_completed and successful_count > 0:
                # Commands were completed successfully - go to end
                history.append({
                    "type": "commands_completed_manually",
                    "commands": manual_completed,
                    "message": f"User manually executed {successful_count} commands successfully.",
                })
                return f"✅ Commands completed manually. {successful_count} succeeded."
            
            # Commands were NOT all successful - ask user what they want to do
            console.print()
            from rich.panel import Panel
            from rich.prompt import Prompt
            
            status_msg = []
            if successful_count > 0:
                status_msg.append(f"[green]✓ {successful_count} succeeded[/green]")
            if failed_count > 0:
                status_msg.append(f"[red]✗ {failed_count} failed[/red]")
            remaining = total_expected - successful_count - failed_count
            if remaining > 0:
                status_msg.append(f"[yellow]○ {remaining} not executed[/yellow]")
            
            console.print(Panel(
                " | ".join(status_msg) if status_msg else "[yellow]No commands were executed[/yellow]",
                title="[bold] Manual Intervention Result [/bold]",
                border_style="yellow",
                padding=(0, 1),
            ))
            
            console.print()
            console.print("[bold]What would you like to do?[/bold]")
            console.print("[dim]  • Type your request to retry or modify the approach[/dim]")
            console.print("[dim]  • Say 'done', 'no', or 'skip' to finish without retrying[/dim]")
            console.print()
            
            try:
                user_response = Prompt.ask("[cyan]Your response[/cyan]").strip()
            except (EOFError, KeyboardInterrupt):
                user_response = "done"
            
            # Check if user wants to end
            end_keywords = ["done", "no", "skip", "exit", "quit", "stop", "cancel", "n", "finish", "end"]
            if user_response.lower() in end_keywords or not user_response:
                # User doesn't want to retry - go to end
                history.append({
                    "type": "manual_intervention_ended",
                    "message": f"User ended manual intervention. {successful_count} commands succeeded.",
                })
                if successful_count > 0:
                    return f"✅ Session ended. {successful_count} command(s) completed successfully."
                else:
                    return f"Session ended. No commands were executed."
            
            # User wants to retry or modify - add their input to history
            history.append({
                "type": "manual_intervention_feedback",
                "user_input": user_response,
                "previous_commands": [(cmd, purpose, []) for cmd, purpose, _ in analyzed],
                "successful_count": successful_count,
                "failed_count": failed_count,
                "message": f"User requested: {user_response}. Previous attempt had {successful_count} successes and {failed_count} failures.",
            })
            
            console.print()
            console.print(f"[cyan]🔄 Processing your request: {user_response[:50]}{'...' if len(user_response) > 50 else ''}[/cyan]")
            
            # Continue the loop with user's new input as additional context
            # The LLM will see the history and the user's feedback
            return None
