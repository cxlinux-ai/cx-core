"""Main DoHandler class for the --do functionality."""

import datetime
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

# Dracula-Inspired Theme Colors
PURPLE = "#bd93f9"  # Dracula purple
PURPLE_LIGHT = "#ff79c6"  # Dracula pink
PURPLE_DARK = "#6272a4"  # Dracula comment
WHITE = "#f8f8f2"  # Dracula foreground
GRAY = "#6272a4"  # Dracula comment
GREEN = "#50fa7b"  # Dracula green
RED = "#ff5555"  # Dracula red
YELLOW = "#f1fa8c"  # Dracula yellow
CYAN = "#8be9fd"  # Dracula cyan
ORANGE = "#ffb86c"  # Dracula orange

# Round Icons
ICON_SUCCESS = "●"
ICON_ERROR = "●"
ICON_INFO = "○"
ICON_PENDING = "◐"
ICON_ARROW = "→"
ICON_CMD = "❯"

from .database import DoRunDatabase
from .diagnosis import AutoFixer, ErrorDiagnoser, LoginHandler
from .managers import CortexUserManager, ProtectedPathsManager
from .models import (
    CommandLog,
    CommandStatus,
    DoRun,
    RunMode,
    TaskNode,
    TaskTree,
)
from .terminal import TerminalMonitor
from .verification import (
    ConflictDetector,
    FileUsefulnessAnalyzer,
    VerificationRunner,
)

console = Console()


class DoHandler:
    """Main handler for the --do functionality."""

    def __init__(self, llm_callback: Callable[[str], dict] | None = None):
        self.db = DoRunDatabase()
        self.paths_manager = ProtectedPathsManager()
        self.user_manager = CortexUserManager
        self.current_run: DoRun | None = None
        self._granted_privileges: list[str] = []
        self.llm_callback = llm_callback

        self._task_tree: TaskTree | None = None
        self._permission_requests_count = 0

        self._terminal_monitor: TerminalMonitor | None = None

        # Manual intervention tracking
        self._expected_manual_commands: list[str] = []
        self._completed_manual_commands: list[str] = []

        # Session tracking
        self.current_session_id: str | None = None

        # Initialize helper classes
        self._diagnoser = ErrorDiagnoser()
        self._auto_fixer = AutoFixer(llm_callback=llm_callback)
        self._login_handler = LoginHandler()
        self._conflict_detector = ConflictDetector()
        self._verification_runner = VerificationRunner()
        self._file_analyzer = FileUsefulnessAnalyzer()

        # Execution state tracking for interruption handling
        self._current_process: subprocess.Popen | None = None
        self._current_command: str | None = None
        self._executed_commands: list[dict] = []
        self._interrupted = False
        self._interrupted_command: str | None = (
            None  # Track which command was interrupted for retry
        )
        self._remaining_commands: list[tuple[str, str, list[str]]] = (
            []
        )  # Commands that weren't executed
        self._original_sigtstp = None
        self._original_sigint = None

    def cleanup(self) -> None:
        """Clean up any running threads or resources."""
        if self._terminal_monitor:
            self._terminal_monitor.stop()
            self._terminal_monitor = None

    def _is_json_like(self, text: str) -> bool:
        """Check if text looks like raw JSON that shouldn't be displayed."""
        if not text:
            return False
        text = text.strip()
        # Check for obvious JSON patterns
        json_indicators = [
            text.startswith(("{", "[", "]", "}")),
            '"response_type"' in text,
            '"do_commands"' in text,
            '"command":' in text,
            '"requires_sudo"' in text,
            '{"' in text and '":' in text,
            text.count('"') > 6 and ":" in text,  # Multiple quoted keys
        ]
        return any(json_indicators)

    def _setup_signal_handlers(self):
        """Set up signal handlers for Ctrl+Z and Ctrl+C."""
        self._original_sigtstp = signal.signal(signal.SIGTSTP, self._handle_interrupt)
        self._original_sigint = signal.signal(signal.SIGINT, self._handle_interrupt)

    def _restore_signal_handlers(self):
        """Restore original signal handlers."""
        if self._original_sigtstp is not None:
            signal.signal(signal.SIGTSTP, self._original_sigtstp)
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)

    def _handle_interrupt(self, signum, frame):
        """Handle Ctrl+Z (SIGTSTP) or Ctrl+C (SIGINT) to stop current command only.

        This does NOT exit the session - it only stops the currently executing command.
        The session continues so the user can decide what to do next.
        """
        self._interrupted = True
        # Store the interrupted command for potential retry
        self._interrupted_command = self._current_command
        signal_name = "Ctrl+Z" if signum == signal.SIGTSTP else "Ctrl+C"

        console.print()
        console.print(
            f"[{YELLOW}]⚠ {signal_name} detected - Stopping current command...[/{YELLOW}]"
        )

        # Kill current subprocess if running
        if self._current_process and self._current_process.poll() is None:
            try:
                self._current_process.terminate()
                # Give it a moment to terminate gracefully
                try:
                    self._current_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._current_process.kill()
                console.print(f"[{YELLOW}]   Stopped: {self._current_command}[/{YELLOW}]")
            except Exception as e:
                console.print(f"[{GRAY}]   Error stopping process: {e}[/{GRAY}]")

        # Note: We do NOT raise KeyboardInterrupt here
        # The session continues - only the current command is stopped

    def _track_command_start(self, command: str, process: subprocess.Popen | None = None):
        """Track when a command starts executing."""
        self._current_command = command
        self._current_process = process

    def _track_command_complete(
        self, command: str, success: bool, output: str = "", error: str = ""
    ):
        """Track when a command completes."""
        self._executed_commands.append(
            {
                "command": command,
                "success": success,
                "output": output[:500] if output else "",
                "error": error[:200] if error else "",
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )
        self._current_command = None
        self._current_process = None

    def _reset_execution_state(self):
        """Reset execution tracking state for a new run."""
        self._current_process = None
        self._current_command = None
        self._executed_commands = []
        self._interrupted = False
        self._interrupted_command = None
        self._remaining_commands = []

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()

    def _show_expandable_output(self, output: str, command: str) -> None:
        """Show output with expand/collapse capability."""
        from rich.panel import Panel
        from rich.prompt import Prompt
        from rich.text import Text

        lines = output.split("\n")
        total_lines = len(lines)

        # Always show first 3 lines as preview
        preview_count = 3

        if total_lines <= preview_count + 2:
            # Small output - just show it all
            console.print(
                Panel(
                    output,
                    title=f"[{GRAY}]Output[/{GRAY}]",
                    title_align="left",
                    border_style=GRAY,
                    padding=(0, 1),
                )
            )
            return

        # Show collapsed preview
        preview = "\n".join(lines[:preview_count])
        remaining = total_lines - preview_count

        content = Text()
        content.append(preview)
        content.append(f"\n\n[{GRAY}]─── {remaining} more lines hidden ───[/{GRAY}]", style=GRAY)

        console.print(
            Panel(
                content,
                title=f"[{GRAY}]Output ({total_lines} lines)[/{GRAY}]",
                subtitle=f"[italic {GRAY}]Press Enter to continue, 'e' to expand[/italic {GRAY}]",
                subtitle_align="right",
                title_align="left",
                border_style=GRAY,
                padding=(0, 1),
            )
        )

        # Quick check if user wants to expand
        try:
            response = input().strip().lower()
            if response == "e":
                # Show full output
                console.print(
                    Panel(
                        output,
                        title=f"[{GRAY}]Full Output ({total_lines} lines)[/{GRAY}]",
                        title_align="left",
                        border_style=PURPLE,
                        padding=(0, 1),
                    )
                )
        except (EOFError, KeyboardInterrupt):
            pass

        # Initialize notification manager
        try:
            from cortex.notification_manager import NotificationManager

            self.notifier = NotificationManager()
        except ImportError:
            self.notifier = None

    def _send_notification(self, title: str, message: str, level: str = "normal"):
        """Send a desktop notification."""
        if self.notifier:
            self.notifier.send(title, message, level=level)
        else:
            console.print(
                f"[bold {YELLOW}]🔔 {title}:[/bold {YELLOW}] [{WHITE}]{message}[/{WHITE}]"
            )

    def setup_cortex_user(self) -> bool:
        """Ensure the cortex user exists."""
        if not self.user_manager.user_exists():
            console.print(f"[{YELLOW}]Setting up cortex user...[/{YELLOW}]")
            success, message = self.user_manager.create_user()
            if success:
                console.print(f"[{GREEN}]{ICON_SUCCESS} {message}[/{GREEN}]")
            else:
                console.print(f"[{RED}]{ICON_ERROR} {message}[/{RED}]")
            return success
        return True

    def analyze_commands_for_protected_paths(
        self, commands: list[tuple[str, str]]
    ) -> list[tuple[str, str, list[str]]]:
        """Analyze commands and identify protected paths they access."""
        results = []

        for command, purpose in commands:
            protected = []
            parts = command.split()
            for part in parts:
                if part.startswith("/") or part.startswith("~"):
                    path = os.path.expanduser(part)
                    if self.paths_manager.is_protected(path):
                        protected.append(path)

            results.append((command, purpose, protected))

        return results

    def request_user_confirmation(
        self,
        commands: list[tuple[str, str, list[str]]],
    ) -> bool:
        """Show commands to user and request confirmation with improved visual UI."""
        from rich import box
        from rich.columns import Columns
        from rich.panel import Panel
        from rich.text import Text

        console.print()

        # Create a table for commands
        cmd_table = Table(
            show_header=True,
            header_style=f"bold {PURPLE_LIGHT}",
            box=box.ROUNDED,
            border_style=PURPLE,
            expand=True,
            padding=(0, 1),
        )
        cmd_table.add_column("#", style=f"bold {PURPLE_LIGHT}", width=3, justify="right")
        cmd_table.add_column("Command", style=f"bold {WHITE}")
        cmd_table.add_column("Purpose", style=GRAY)

        all_protected = []
        for i, (cmd, purpose, protected) in enumerate(commands, 1):
            # Truncate long commands for display
            cmd_display = cmd if len(cmd) <= 60 else cmd[:57] + "..."
            purpose_display = purpose if len(purpose) <= 50 else purpose[:47] + "..."

            # Add protected path indicator
            if protected:
                cmd_display = f"{cmd_display} [{YELLOW}]⚠[/{YELLOW}]"
                all_protected.extend(protected)

            cmd_table.add_row(str(i), cmd_display, purpose_display)

        # Create header
        header_text = Text()
        header_text.append("🔐 ", style="bold")
        header_text.append("Permission Required", style=f"bold {WHITE}")
        header_text.append(
            f"  ({len(commands)} command{'s' if len(commands) > 1 else ''})", style=GRAY
        )

        console.print(
            Panel(
                cmd_table,
                title=header_text,
                title_align="left",
                border_style=PURPLE,
                padding=(1, 1),
            )
        )

        # Show protected paths if any
        if all_protected:
            protected_set = set(all_protected)
            protected_text = Text()
            protected_text.append("⚠ Protected paths: ", style=f"bold {YELLOW}")
            protected_text.append(", ".join(protected_set), style=GRAY)
            console.print(
                Panel(
                    protected_text,
                    border_style=PURPLE,
                    padding=(0, 1),
                    expand=False,
                )
            )

        console.print()
        return Confirm.ask("[bold]Proceed?[/bold]", default=False)

    def _needs_sudo(self, cmd: str, protected_paths: list[str]) -> bool:
        """Determine if a command needs sudo to execute."""
        sudo_commands = [
            "systemctl",
            "service",
            "apt",
            "apt-get",
            "dpkg",
            "mount",
            "umount",
            "fdisk",
            "mkfs",
            "chown",
            "chmod",
            "useradd",
            "userdel",
            "usermod",
            "groupadd",
            "groupdel",
        ]

        cmd_parts = cmd.split()
        if not cmd_parts:
            return False

        base_cmd = cmd_parts[0]

        if base_cmd in sudo_commands:
            return True

        if protected_paths:
            return True

        if any(p in cmd for p in ["/etc/", "/var/lib/", "/usr/", "/opt/", "/root/"]):
            return True

        return False

    # Commands that benefit from streaming output (long-running with progress)
    STREAMING_COMMANDS = [
        "docker pull",
        "docker push",
        "docker build",
        "apt install",
        "apt-get install",
        "apt update",
        "apt-get update",
        "apt upgrade",
        "apt-get upgrade",
        "pip install",
        "pip3 install",
        "pip download",
        "pip3 download",
        "npm install",
        "npm ci",
        "yarn install",
        "yarn add",
        "cargo build",
        "cargo install",
        "go build",
        "go install",
        "go get",
        "gem install",
        "bundle install",
        "wget",
        "curl -o",
        "curl -O",
        "git clone",
        "git pull",
        "git fetch",
        "make",
        "cmake",
        "ninja",
        "rsync",
        "scp",
    ]

    # Interactive commands that need a TTY - cannot be run in background/automated
    INTERACTIVE_COMMANDS = [
        "docker exec -it",
        "docker exec -ti",
        "docker run -it",
        "docker run -ti",
        "docker attach",
        "ollama run",
        "ollama chat",
        "ssh ",
        "bash -i",
        "sh -i",
        "zsh -i",
        "vi ",
        "vim ",
        "nano ",
        "emacs ",
        "python -i",
        "python3 -i",
        "ipython",
        "node -i",
        "mysql -u",
        "psql -U",
        "mongo ",
        "redis-cli",
        "htop",
        "top -i",
        "less ",
        "more ",
    ]

    def _should_stream_output(self, cmd: str) -> bool:
        """Check if command should use streaming output."""
        cmd_lower = cmd.lower()
        return any(streaming_cmd in cmd_lower for streaming_cmd in self.STREAMING_COMMANDS)

    def _is_interactive_command(self, cmd: str) -> bool:
        """Check if command requires interactive TTY and cannot be automated."""
        cmd_lower = cmd.lower()
        # Check explicit patterns
        if any(interactive in cmd_lower for interactive in self.INTERACTIVE_COMMANDS):
            return True
        # Check for -it or -ti flags in docker commands
        if "docker" in cmd_lower and (
            " -it " in cmd_lower
            or " -ti " in cmd_lower
            or cmd_lower.endswith(" -it")
            or cmd_lower.endswith(" -ti")
        ):
            return True
        return False

    # Timeout settings by command type (in seconds)
    COMMAND_TIMEOUTS = {
        "docker pull": 1800,  # 30 minutes for large images
        "docker push": 1800,  # 30 minutes for large images
        "docker build": 3600,  # 1 hour for complex builds
        "apt install": 900,  # 15 minutes
        "apt-get install": 900,
        "apt update": 300,  # 5 minutes
        "apt-get update": 300,
        "apt upgrade": 1800,  # 30 minutes
        "apt-get upgrade": 1800,
        "pip install": 600,  # 10 minutes
        "pip3 install": 600,
        "npm install": 900,  # 15 minutes
        "yarn install": 900,
        "git clone": 600,  # 10 minutes
        "make": 1800,  # 30 minutes
        "cargo build": 1800,
    }

    def _get_command_timeout(self, cmd: str) -> int:
        """Get appropriate timeout for a command."""
        cmd_lower = cmd.lower()
        for cmd_pattern, timeout in self.COMMAND_TIMEOUTS.items():
            if cmd_pattern in cmd_lower:
                return timeout
        return 600  # Default 10 minutes for streaming commands

    def _execute_with_streaming(
        self,
        cmd: str,
        needs_sudo: bool,
        timeout: int | None = None,  # None = auto-detect
    ) -> tuple[bool, str, str]:
        """Execute a command with real-time output streaming."""
        import select
        import sys

        # Auto-detect timeout if not specified
        if timeout is None:
            timeout = self._get_command_timeout(cmd)

        # Show timeout info for long operations
        if timeout > 300:
            console.print(
                f"[dim]      ⏱️  Timeout: {timeout // 60} minutes (large operation)[/dim]"
            )

        stdout_lines = []
        stderr_lines = []

        try:
            if needs_sudo:
                process = subprocess.Popen(
                    ["sudo", "bash", "-c", cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                )
            else:
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )

            # Use select for non-blocking reads on both stdout and stderr
            import time

            start_time = time.time()

            while True:
                # Check timeout
                if time.time() - start_time > timeout:
                    process.kill()
                    return (
                        False,
                        "\n".join(stdout_lines),
                        f"Command timed out after {timeout} seconds",
                    )

                # Check if process has finished
                if process.poll() is not None:
                    # Read any remaining output
                    remaining_stdout, remaining_stderr = process.communicate()
                    if remaining_stdout:
                        for line in remaining_stdout.splitlines():
                            stdout_lines.append(line)
                            self._print_progress_line(line, is_stderr=False)
                    if remaining_stderr:
                        for line in remaining_stderr.splitlines():
                            stderr_lines.append(line)
                            self._print_progress_line(line, is_stderr=True)
                    break

                # Try to read from stdout/stderr without blocking
                try:
                    readable, _, _ = select.select([process.stdout, process.stderr], [], [], 0.1)

                    for stream in readable:
                        line = stream.readline()
                        if line:
                            line = line.rstrip()
                            if stream == process.stdout:
                                stdout_lines.append(line)
                                self._print_progress_line(line, is_stderr=False)
                            else:
                                stderr_lines.append(line)
                                self._print_progress_line(line, is_stderr=True)
                except (ValueError, OSError):
                    # Stream closed
                    break

            return (
                process.returncode == 0,
                "\n".join(stdout_lines).strip(),
                "\n".join(stderr_lines).strip(),
            )

        except Exception as e:
            return False, "\n".join(stdout_lines), str(e)

    def _print_progress_line(self, line: str, is_stderr: bool = False) -> None:
        """Print a progress line with appropriate formatting."""
        if not line.strip():
            return

        line = line.strip()

        # Docker pull progress patterns
        if any(
            p in line
            for p in [
                "Pulling from",
                "Digest:",
                "Status:",
                "Pull complete",
                "Downloading",
                "Extracting",
            ]
        ):
            console.print(f"[dim]      📦 {line}[/dim]")
        # Docker build progress
        elif line.startswith("Step ") or line.startswith("---> "):
            console.print(f"[dim]      🔨 {line}[/dim]")
        # apt progress patterns
        elif any(
            p in line
            for p in [
                "Get:",
                "Hit:",
                "Fetched",
                "Reading",
                "Building",
                "Setting up",
                "Processing",
                "Unpacking",
            ]
        ):
            console.print(f"[dim]      📦 {line}[/dim]")
        # pip progress patterns
        elif any(p in line for p in ["Collecting", "Downloading", "Installing", "Successfully"]):
            console.print(f"[dim]      📦 {line}[/dim]")
        # npm progress patterns
        elif any(p in line for p in ["npm", "added", "packages", "audited"]):
            console.print(f"[dim]      📦 {line}[/dim]")
        # git progress patterns
        elif any(
            p in line for p in ["Cloning", "remote:", "Receiving", "Resolving", "Checking out"]
        ):
            console.print(f"[dim]      📦 {line}[/dim]")
        # wget/curl progress
        elif "%" in line and any(c.isdigit() for c in line):
            # Progress percentage - update in place
            console.print(f"[dim]      ⬇️  {line[:80]}[/dim]", end="\r")
        # Error lines
        elif is_stderr and any(
            p in line.lower() for p in ["error", "fail", "denied", "cannot", "unable"]
        ):
            console.print(f"[{YELLOW}]      ⚠ {line}[/{YELLOW}]")
        # Truncate very long lines
        elif len(line) > 100:
            console.print(f"[dim]      {line[:100]}...[/dim]")

    def _execute_single_command(
        self, cmd: str, needs_sudo: bool, timeout: int = 120
    ) -> tuple[bool, str, str]:
        """Execute a single command with proper privilege handling and interruption support."""
        # Check for interactive commands that need a TTY
        if self._is_interactive_command(cmd):
            return self._handle_interactive_command(cmd, needs_sudo)

        # Use streaming for long-running commands
        if self._should_stream_output(cmd):
            return self._execute_with_streaming(cmd, needs_sudo, timeout=300)

        # Track command start
        self._track_command_start(cmd)

        try:
            # Flush output before sudo to handle password prompts cleanly
            if needs_sudo:
                sys.stdout.flush()
                sys.stderr.flush()

            # Use Popen for interruptibility
            if needs_sudo:
                process = subprocess.Popen(
                    ["sudo", "bash", "-c", cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            else:
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

            # Store process for interruption handling
            self._current_process = process

            try:
                stdout, stderr = process.communicate(timeout=timeout)

                # Check if interrupted during execution
                if self._interrupted:
                    self._track_command_complete(
                        cmd, False, stdout or "", "Command interrupted by user"
                    )
                    return False, stdout.strip() if stdout else "", "Command interrupted by user"

                success = process.returncode == 0

                # Track completion
                self._track_command_complete(cmd, success, stdout, stderr)

                # After sudo, reset console state
                if needs_sudo:
                    sys.stdout.write("")  # Force flush
                    sys.stdout.flush()

                return (success, stdout.strip(), stderr.strip())

            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                self._track_command_complete(
                    cmd, False, stdout, f"Command timed out after {timeout} seconds"
                )
                return (
                    False,
                    stdout.strip() if stdout else "",
                    f"Command timed out after {timeout} seconds",
                )
        except Exception as e:
            self._track_command_complete(cmd, False, "", str(e))
            return False, "", str(e)

    def _handle_interactive_command(self, cmd: str, needs_sudo: bool) -> tuple[bool, str, str]:
        """Handle interactive commands that need a TTY.

        These commands cannot be run in the background - they need user interaction.
        We'll either:
        1. Try to open in a new terminal window
        2. Or inform the user to run it manually
        """
        console.print()
        console.print(f"[{YELLOW}]⚡ Interactive command detected[/{YELLOW}]")
        console.print(f"[{GRAY}]   This command requires a terminal for interaction.[/{GRAY}]")
        console.print()

        full_cmd = f"sudo {cmd}" if needs_sudo else cmd

        # Try to detect if we can open a new terminal
        terminal_cmds = [
            (
                "gnome-terminal",
                f'gnome-terminal -- bash -c "{full_cmd}; echo; echo Press Enter to close...; read"',
            ),
            (
                "konsole",
                f'konsole -e bash -c "{full_cmd}; echo; echo Press Enter to close...; read"',
            ),
            ("xterm", f'xterm -e bash -c "{full_cmd}; echo; echo Press Enter to close...; read"'),
            (
                "x-terminal-emulator",
                f'x-terminal-emulator -e bash -c "{full_cmd}; echo; echo Press Enter to close...; read"',
            ),
        ]

        # Check which terminal is available
        for term_name, term_cmd in terminal_cmds:
            if shutil.which(term_name):
                console.print(
                    f"[{PURPLE_LIGHT}]🖥️  Opening in new terminal window ({term_name})...[/{PURPLE_LIGHT}]"
                )
                console.print(f"[{GRAY}]   Command: {full_cmd}[/{GRAY}]")
                console.print()

                try:
                    # Start the terminal in background
                    subprocess.Popen(
                        term_cmd,
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True, f"Command opened in new {term_name} window", ""
                except Exception as e:
                    console.print(f"[{YELLOW}]   ⚠ Could not open terminal: {e}[/{YELLOW}]")
                    break

        # Fallback: ask user to run manually
        console.print(
            f"[bold {PURPLE_LIGHT}]📋 Please run this command manually in another terminal:[/bold {PURPLE_LIGHT}]"
        )
        console.print()
        console.print(f"   [{GREEN}]{full_cmd}[/{GREEN}]")
        console.print()
        console.print(f"[{GRAY}]   This command needs interactive input (TTY).[/{GRAY}]")
        console.print(f"[{GRAY}]   Cortex cannot capture its output automatically.[/{GRAY}]")
        console.print()

        # Return special status indicating manual run needed
        return True, "INTERACTIVE_COMMAND_MANUAL", f"Interactive command - run manually: {full_cmd}"

    def execute_commands_as_cortex(
        self,
        commands: list[tuple[str, str, list[str]]],
        user_query: str,
    ) -> DoRun:
        """Execute commands with granular error handling and auto-recovery."""
        run = DoRun(
            run_id=self.db._generate_run_id(),
            summary="",
            mode=RunMode.CORTEX_EXEC,
            user_query=user_query,
            started_at=datetime.datetime.now().isoformat(),
            session_id=self.current_session_id or "",
        )
        self.current_run = run

        console.print()
        console.print(
            f"[bold {PURPLE_LIGHT}]🚀 Executing commands with conflict detection...[/bold {PURPLE_LIGHT}]"
        )
        console.print()

        # Phase 1: Conflict Detection
        console.print(f"[{GRAY}]Checking for conflicts...[/{GRAY}]")

        cleanup_commands = []
        for cmd, purpose, protected in commands:
            conflict = self._conflict_detector.check_for_conflicts(cmd, purpose)
            if conflict["has_conflict"]:
                console.print(
                    f"[{YELLOW}]   ⚠ {conflict['conflict_type']}: {conflict['suggestion']}[/{YELLOW}]"
                )
                if conflict["cleanup_commands"]:
                    cleanup_commands.extend(conflict["cleanup_commands"])

        if cleanup_commands:
            console.print("[dim]Running cleanup commands...[/dim]")
            for cleanup_cmd in cleanup_commands:
                self._execute_single_command(cleanup_cmd, needs_sudo=True)

        console.print()

        all_protected = set()
        for _, _, protected in commands:
            all_protected.update(protected)

        if all_protected:
            console.print(f"[dim]📁 Protected paths involved: {', '.join(all_protected)}[/dim]")
            console.print()

        # Phase 2: Execute Commands
        from rich.panel import Panel
        from rich.text import Text

        for i, (cmd, purpose, protected) in enumerate(commands, 1):
            # Create a visually distinct panel for each command
            cmd_header = Text()
            cmd_header.append(f"[{i}/{len(commands)}] ", style=f"bold {WHITE}")
            cmd_header.append(f" {cmd}", style=f"bold {PURPLE_LIGHT}")

            console.print()
            console.print(
                Panel(
                    f"[bold {PURPLE_LIGHT}]{cmd}[/bold {PURPLE_LIGHT}]\n[{GRAY}]└─ {purpose}[/{GRAY}]",
                    title=f"[bold {WHITE}] Command {i}/{len(commands)} [/bold {WHITE}]",
                    title_align="left",
                    border_style=PURPLE,
                    padding=(0, 1),
                )
            )

            file_check = self._file_analyzer.check_file_exists_and_usefulness(
                cmd, purpose, user_query
            )

            if file_check["recommendations"]:
                self._file_analyzer.apply_file_recommendations(file_check["recommendations"])

            cmd_log = CommandLog(
                command=cmd,
                purpose=purpose,
                timestamp=datetime.datetime.now().isoformat(),
                status=CommandStatus.RUNNING,
            )

            start_time = time.time()
            needs_sudo = self._needs_sudo(cmd, protected)

            success, stdout, stderr = self._execute_single_command(cmd, needs_sudo)

            if not success:
                diagnosis = self._diagnoser.diagnose_error(cmd, stderr)

                # Create error panel for visual grouping
                error_info = (
                    f"[bold {RED}]{ICON_ERROR} {diagnosis['description']}[/bold {RED}]\n"
                    f"[{GRAY}]Type: {diagnosis['error_type']} | Category: {diagnosis.get('category', 'unknown')}[/{GRAY}]"
                )
                console.print(
                    Panel(
                        error_info,
                        title=f"[bold {RED}] {ICON_ERROR} Error Detected [/bold {RED}]",
                        title_align="left",
                        border_style=RED,
                        padding=(0, 1),
                    )
                )

                # Check if this is a login/credential required error
                if diagnosis.get("category") == "login_required":
                    console.print(
                        Panel(
                            f"[bold {PURPLE_LIGHT}]🔐 Authentication required for this command[/bold {PURPLE_LIGHT}]",
                            border_style=PURPLE,
                            padding=(0, 1),
                            expand=False,
                        )
                    )

                    login_success, login_msg = self._login_handler.handle_login(cmd, stderr)

                    if login_success:
                        console.print(
                            Panel(
                                f"[bold {GREEN}]{ICON_SUCCESS} {login_msg}[/bold {GREEN}]\n[{GRAY}]Retrying command...[/{GRAY}]",
                                border_style=PURPLE,
                                padding=(0, 1),
                                expand=False,
                            )
                        )

                        # Retry the command after successful login
                        success, stdout, stderr = self._execute_single_command(cmd, needs_sudo)

                        if success:
                            console.print(
                                Panel(
                                    f"[bold {GREEN}]{ICON_SUCCESS} Command succeeded after authentication![/bold {GREEN}]",
                                    border_style=PURPLE,
                                    padding=(0, 1),
                                    expand=False,
                                )
                            )
                        else:
                            console.print(
                                Panel(
                                    f"[bold {YELLOW}]Command still failed after login[/bold {YELLOW}]\n[{GRAY}]{stderr[:100]}[/{GRAY}]",
                                    border_style=PURPLE,
                                    padding=(0, 1),
                                )
                            )
                    else:
                        console.print(f"[{YELLOW}]{login_msg}[/{YELLOW}]")
                else:
                    # Not a login error, proceed with regular error handling
                    extra_info = []
                    if diagnosis.get("extracted_path"):
                        extra_info.append(f"[{GRAY}]Path:[/{GRAY}] {diagnosis['extracted_path']}")
                    if diagnosis.get("extracted_info"):
                        for key, value in diagnosis["extracted_info"].items():
                            if value:
                                extra_info.append(f"[{GRAY}]{key}:[/{GRAY}] {value}")

                    if extra_info:
                        console.print(
                            Panel(
                                "\n".join(extra_info),
                                title=f"[{GRAY}] Error Details [{GRAY}]",
                                title_align="left",
                                border_style=GRAY,
                                padding=(0, 1),
                                expand=False,
                            )
                        )

                    fixed, fix_message, fix_commands = self._auto_fixer.auto_fix_error(
                        cmd, stderr, diagnosis, max_attempts=3
                    )

                    if fixed:
                        success = True
                        console.print(
                            Panel(
                                f"[bold {GREEN}]{ICON_SUCCESS} Auto-fixed:[/bold {GREEN}] [{WHITE}]{fix_message}[/{WHITE}]",
                                title=f"[bold {GREEN}] Fix Successful [/bold {GREEN}]",
                                title_align="left",
                                border_style=PURPLE,
                                padding=(0, 1),
                                expand=False,
                            )
                        )
                        _, stdout, stderr = self._execute_single_command(cmd, needs_sudo=True)
                    else:
                        fix_info = []
                        if fix_commands:
                            fix_info.append(
                                f"[{GRAY}]Attempted:[/{GRAY}] {len(fix_commands)} fix command(s)"
                            )
                        fix_info.append(
                            f"[bold {YELLOW}]Result:[/bold {YELLOW}] [{WHITE}]{fix_message}[/{WHITE}]"
                        )
                        console.print(
                            Panel(
                                "\n".join(fix_info),
                                title=f"[bold {YELLOW}] Fix Incomplete [/bold {YELLOW}]",
                                title_align="left",
                                border_style=PURPLE,
                                padding=(0, 1),
                            )
                        )

            cmd_log.duration_seconds = time.time() - start_time
            cmd_log.output = stdout
            cmd_log.error = stderr
            cmd_log.status = CommandStatus.SUCCESS if success else CommandStatus.FAILED

            run.commands.append(cmd_log)
            run.files_accessed.extend(protected)

            if success:
                console.print(
                    Panel(
                        f"[bold {GREEN}]{ICON_SUCCESS} Success[/bold {GREEN}]  [{GRAY}]({cmd_log.duration_seconds:.2f}s)[/{GRAY}]",
                        border_style=PURPLE,
                        padding=(0, 1),
                        expand=False,
                    )
                )
                if stdout:
                    self._show_expandable_output(stdout, cmd)
            else:
                console.print(
                    Panel(
                        f"[bold {RED}]{ICON_ERROR} Failed[/bold {RED}]\n[{GRAY}]{stderr[:200]}[/{GRAY}]",
                        border_style=RED,
                        padding=(0, 1),
                    )
                )

                final_diagnosis = self._diagnoser.diagnose_error(cmd, stderr)
                if final_diagnosis["fix_commands"] and not final_diagnosis["can_auto_fix"]:
                    # Create a manual intervention panel
                    manual_content = [
                        f"[bold {YELLOW}]Issue:[/bold {YELLOW}] [{WHITE}]{final_diagnosis['description']}[/{WHITE}]",
                        "",
                    ]
                    manual_content.append(f"[bold {WHITE}]Suggested commands:[/bold {WHITE}]")
                    for fix_cmd in final_diagnosis["fix_commands"]:
                        if not fix_cmd.startswith("#"):
                            manual_content.append(f"  [{PURPLE_LIGHT}]$ {fix_cmd}[/{PURPLE_LIGHT}]")
                        else:
                            manual_content.append(f"  [{GRAY}]{fix_cmd}[/{GRAY}]")

                    console.print(
                        Panel(
                            "\n".join(manual_content),
                            title=f"[bold {YELLOW}] 💡 Manual Intervention Required [/bold {YELLOW}]",
                            title_align="left",
                            border_style=PURPLE,
                            padding=(0, 1),
                        )
                    )

            console.print()

        self._granted_privileges = []

        # Phase 3: Verification Tests
        console.print()
        console.print(
            Panel(
                f"[bold {WHITE}]Running verification tests...[/bold {WHITE}]",
                title=f"[bold {PURPLE_LIGHT}] 🧪 Verification Phase [/bold {PURPLE_LIGHT}]",
                title_align="left",
                border_style=PURPLE,
                padding=(0, 1),
                expand=False,
            )
        )
        all_tests_passed, test_results = self._verification_runner.run_verification_tests(
            run.commands, user_query
        )

        # Phase 4: Auto-repair if tests failed
        if not all_tests_passed:
            console.print()
            console.print(
                Panel(
                    f"[bold {YELLOW}]Attempting to repair test failures...[/bold {YELLOW}]",
                    title=f"[bold {YELLOW}] 🔧 Auto-Repair Phase [/bold {YELLOW}]",
                    title_align="left",
                    border_style=PURPLE,
                    padding=(0, 1),
                    expand=False,
                )
            )

            repair_success = self._handle_test_failures(test_results, run)

            if repair_success:
                console.print(f"[{GRAY}]Re-running verification tests...[/{GRAY}]")
                all_tests_passed, test_results = self._verification_runner.run_verification_tests(
                    run.commands, user_query
                )

        run.completed_at = datetime.datetime.now().isoformat()
        run.summary = self._generate_summary(run)

        if test_results:
            passed = sum(1 for t in test_results if t["passed"])
            run.summary += f" | Tests: {passed}/{len(test_results)} passed"

        self.db.save_run(run)

        # Generate LLM summary/answer
        llm_answer = self._generate_llm_answer(run, user_query)

        # Print condensed execution summary with answer
        self._print_execution_summary(run, answer=llm_answer)

        console.print()
        console.print(f"[dim]Run ID: {run.run_id}[/dim]")

        return run

    def _handle_resource_conflict(
        self,
        idx: int,
        cmd: str,
        conflict: dict,
        commands_to_skip: set,
        cleanup_commands: list,
    ) -> bool:
        """Handle any resource conflict with user options.

        This is a GENERAL handler for all resource types:
        - Docker containers
        - Services
        - Files/directories
        - Packages
        - Ports
        - Users/groups
        - Virtual environments
        - Databases
        - Cron jobs
        """
        resource_type = conflict.get("resource_type", "resource")
        resource_name = conflict.get("resource_name", "unknown")
        conflict_type = conflict.get("conflict_type", "unknown")
        suggestion = conflict.get("suggestion", "")
        is_active = conflict.get("is_active", True)
        alternatives = conflict.get("alternative_actions", [])

        # Resource type icons
        icons = {
            "container": "🐳",
            "compose": "🐳",
            "service": "⚙️",
            "file": "📄",
            "directory": "📁",
            "package": "📦",
            "pip_package": "🐍",
            "npm_package": "📦",
            "port": "🔌",
            "user": "👤",
            "group": "👥",
            "venv": "🐍",
            "mysql_database": "🗄️",
            "postgres_database": "🗄️",
            "cron_job": "⏰",
        }
        icon = icons.get(resource_type, "📌")

        # Display the conflict with visual grouping
        from rich.panel import Panel

        status_text = (
            f"[bold {PURPLE_LIGHT}]Active[/bold {PURPLE_LIGHT}]"
            if is_active
            else f"[{GRAY}]Inactive[/{GRAY}]"
        )
        conflict_content = (
            f"{icon} [bold {WHITE}]{resource_type.replace('_', ' ').title()}:[/bold {WHITE}] '{resource_name}'\n"
            f"[{GRAY}]Status:[/{GRAY}] {status_text}\n"
            f"[{GRAY}]{suggestion}[/{GRAY}]"
        )

        console.print()
        console.print(
            Panel(
                conflict_content,
                title=f"[bold {YELLOW}] ⚠️ Resource Conflict [/bold {YELLOW}]",
                title_align="left",
                border_style=PURPLE,
                padding=(0, 1),
            )
        )

        # If there are alternatives, show them
        if alternatives:
            options_content = [f"[bold {WHITE}]What would you like to do?[/bold {WHITE}]", ""]
            for j, alt in enumerate(alternatives, 1):
                options_content.append(f"  [{WHITE}]{j}. {alt['description']}[/{WHITE}]")

            console.print(
                Panel(
                    "\n".join(options_content),
                    border_style=GRAY,
                    padding=(0, 1),
                )
            )

            from rich.prompt import Prompt

            choice = Prompt.ask(
                "   Choose an option",
                choices=[str(k) for k in range(1, len(alternatives) + 1)],
                default="1",
            )

            selected = alternatives[int(choice) - 1]
            action = selected["action"]
            action_commands = selected.get("commands", [])

            # Handle different actions
            if action in ["use_existing", "use_different"]:
                console.print(
                    f"[{GREEN}]   {ICON_SUCCESS} Using existing {resource_type} '{resource_name}'[/{GREEN}]"
                )
                commands_to_skip.add(idx)
                return True

            elif action == "start_existing":
                console.print(
                    f"[{PURPLE_LIGHT}]   Starting existing {resource_type}...[/{PURPLE_LIGHT}]"
                )
                for start_cmd in action_commands:
                    needs_sudo = start_cmd.startswith("sudo")
                    success, _, stderr = self._execute_single_command(
                        start_cmd, needs_sudo=needs_sudo
                    )
                    if success:
                        console.print(f"[{GREEN}]   {ICON_SUCCESS} {start_cmd}[/{GREEN}]")
                    else:
                        console.print(f"[{RED}]   {ICON_ERROR} {start_cmd}: {stderr[:50]}[/{RED}]")
                commands_to_skip.add(idx)
                return True

            elif action in ["restart", "upgrade", "reinstall"]:
                console.print(
                    f"[{PURPLE_LIGHT}]   {action.title()}ing {resource_type}...[/{PURPLE_LIGHT}]"
                )
                for action_cmd in action_commands:
                    needs_sudo = action_cmd.startswith("sudo")
                    success, _, stderr = self._execute_single_command(
                        action_cmd, needs_sudo=needs_sudo
                    )
                    if success:
                        console.print(f"[{GREEN}]   {ICON_SUCCESS} {action_cmd}[/{GREEN}]")
                    else:
                        console.print(f"[{RED}]   {ICON_ERROR} {action_cmd}: {stderr[:50]}[/{RED}]")
                commands_to_skip.add(idx)
                return True

            elif action in ["recreate", "backup", "replace", "stop_existing"]:
                console.print(
                    f"[{PURPLE_LIGHT}]   Preparing to {action.replace('_', ' ')}...[/{PURPLE_LIGHT}]"
                )
                for action_cmd in action_commands:
                    needs_sudo = action_cmd.startswith("sudo")
                    success, _, stderr = self._execute_single_command(
                        action_cmd, needs_sudo=needs_sudo
                    )
                    if success:
                        console.print(f"[{GREEN}]   {ICON_SUCCESS} {action_cmd}[/{GREEN}]")
                    else:
                        console.print(f"[{RED}]   {ICON_ERROR} {action_cmd}: {stderr[:50]}[/{RED}]")
                # Don't skip - let the original command run after cleanup
                return True

            elif action == "modify":
                console.print(
                    f"[{PURPLE_LIGHT}]   Will modify existing {resource_type}[/{PURPLE_LIGHT}]"
                )
                # Don't skip - let the original command run to modify
                return True

            elif action == "install_first":
                # Install a missing tool/dependency first
                console.print(
                    f"[{PURPLE_LIGHT}]   Installing required dependency '{resource_name}'...[/{PURPLE_LIGHT}]"
                )
                all_success = True
                for action_cmd in action_commands:
                    needs_sudo = action_cmd.startswith("sudo")
                    success, stdout, stderr = self._execute_single_command(
                        action_cmd, needs_sudo=needs_sudo
                    )
                    if success:
                        console.print(f"[{GREEN}]   {ICON_SUCCESS} {action_cmd}[/{GREEN}]")
                    else:
                        console.print(f"[{RED}]   {ICON_ERROR} {action_cmd}: {stderr[:50]}[/{RED}]")
                        all_success = False

                if all_success:
                    console.print(
                        f"[{GREEN}]   {ICON_SUCCESS} '{resource_name}' installed. Continuing with original command...[/{GREEN}]"
                    )
                    # Don't skip - run the original command now that the tool is installed
                    return True
                else:
                    console.print(
                        f"[{RED}]   {ICON_ERROR} Failed to install '{resource_name}'[/{RED}]"
                    )
                    commands_to_skip.add(idx)
                    return True

            elif action == "use_apt":
                # User chose to use apt instead of snap
                console.print(
                    f"[{PURPLE_LIGHT}]   Skipping snap command - use apt instead[/{PURPLE_LIGHT}]"
                )
                commands_to_skip.add(idx)
                return True

            elif action == "refresh":
                # Refresh snap package
                console.print(f"[{PURPLE_LIGHT}]   Refreshing snap package...[/{PURPLE_LIGHT}]")
                for action_cmd in action_commands:
                    needs_sudo = action_cmd.startswith("sudo")
                    success, _, stderr = self._execute_single_command(
                        action_cmd, needs_sudo=needs_sudo
                    )
                    if success:
                        console.print(f"[{GREEN}]   {ICON_SUCCESS} {action_cmd}[/{GREEN}]")
                    else:
                        console.print(f"[{RED}]   {ICON_ERROR} {action_cmd}: {stderr[:50]}[/{RED}]")
                commands_to_skip.add(idx)
                return True

        # No alternatives - use default behavior (add to cleanup if available)
        if conflict.get("cleanup_commands"):
            cleanup_commands.extend(conflict["cleanup_commands"])

        return False

    def _handle_test_failures(
        self,
        test_results: list[dict[str, Any]],
        run: DoRun,
    ) -> bool:
        """Handle failed verification tests by attempting auto-repair."""
        failed_tests = [t for t in test_results if not t["passed"]]

        if not failed_tests:
            return True

        console.print()
        console.print(f"[bold {YELLOW}]🔧 Attempting to fix test failures...[/bold {YELLOW}]")

        all_fixed = True

        for test in failed_tests:
            test_name = test["test"]
            output = test["output"]

            console.print(f"[{GRAY}]   Fixing: {test_name}[/{GRAY}]")

            if "nginx -t" in test_name:
                diagnosis = self._diagnoser.diagnose_error("nginx -t", output)
                fixed, msg, _ = self._auto_fixer.auto_fix_error(
                    "nginx -t", output, diagnosis, max_attempts=3
                )
                if fixed:
                    console.print(f"[{GREEN}]   {ICON_SUCCESS} Fixed: {msg}[/{GREEN}]")
                else:
                    console.print(f"[{RED}]   {ICON_ERROR} Could not fix: {msg}[/{RED}]")
                    all_fixed = False

            elif "apache2ctl" in test_name:
                diagnosis = self._diagnoser.diagnose_error("apache2ctl configtest", output)
                fixed, msg, _ = self._auto_fixer.auto_fix_error(
                    "apache2ctl configtest", output, diagnosis, max_attempts=3
                )
                if fixed:
                    console.print(f"[{GREEN}]   {ICON_SUCCESS} Fixed: {msg}[/{GREEN}]")
                else:
                    all_fixed = False

            elif "systemctl is-active" in test_name:
                import re

                svc_match = re.search(r"is-active\s+(\S+)", test_name)
                if svc_match:
                    service = svc_match.group(1)
                    success, _, err = self._execute_single_command(
                        f"sudo systemctl start {service}", needs_sudo=True
                    )
                    if success:
                        console.print(
                            f"[{GREEN}]   {ICON_SUCCESS} Started service {service}[/{GREEN}]"
                        )
                    else:
                        console.print(
                            f"[{YELLOW}]   ⚠ Could not start {service}: {err[:50]}[/{YELLOW}]"
                        )

            elif "file exists" in test_name:
                import re

                path_match = re.search(r"file exists: (.+)", test_name)
                if path_match:
                    path = path_match.group(1)
                    parent = os.path.dirname(path)
                    if parent and not os.path.exists(parent):
                        self._execute_single_command(f"sudo mkdir -p {parent}", needs_sudo=True)
                        console.print(
                            f"[{GREEN}]   {ICON_SUCCESS} Created directory {parent}[/{GREEN}]"
                        )

        return all_fixed

    def execute_with_task_tree(
        self,
        commands: list[tuple[str, str, list[str]]],
        user_query: str,
    ) -> DoRun:
        """Execute commands using the task tree system with advanced auto-repair."""
        # Reset execution state for new run
        self._reset_execution_state()

        run = DoRun(
            run_id=self.db._generate_run_id(),
            summary="",
            mode=RunMode.CORTEX_EXEC,
            user_query=user_query,
            started_at=datetime.datetime.now().isoformat(),
            session_id=self.current_session_id or "",
        )
        self.current_run = run
        self._permission_requests_count = 0

        self._task_tree = TaskTree()
        for cmd, purpose, protected in commands:
            task = self._task_tree.add_root_task(cmd, purpose)
            task.reasoning = f"Protected paths: {', '.join(protected)}" if protected else ""

        console.print()
        console.print(
            Panel(
                f"[bold {PURPLE_LIGHT}]🌳 Task Tree Execution Mode[/bold {PURPLE_LIGHT}]\n"
                f"[{GRAY}]Commands will be executed with auto-repair capabilities.[/{GRAY}]\n"
                f"[{GRAY}]Conflict detection and verification tests enabled.[/{GRAY}]\n"
                f"[{YELLOW}]Press Ctrl+Z or Ctrl+C to stop execution at any time.[/{YELLOW}]",
                expand=False,
                border_style=PURPLE,
            )
        )
        console.print()

        # Set up signal handlers for Ctrl+Z and Ctrl+C
        self._setup_signal_handlers()

        # Phase 1: Conflict Detection - Claude-like header
        console.print(
            f"[bold {PURPLE}]━━━[/bold {PURPLE}] [bold {WHITE}]Checking for Conflicts[/bold {WHITE}]"
        )

        conflicts_found = []
        cleanup_commands = []
        commands_to_skip = set()  # Track commands that should be skipped (use existing)
        commands_to_replace = {}  # Track commands that should be replaced
        resource_decisions = {}  # Track user decisions for each resource to avoid duplicate prompts

        for i, (cmd, purpose, protected) in enumerate(commands):
            conflict = self._conflict_detector.check_for_conflicts(cmd, purpose)
            if conflict["has_conflict"]:
                conflicts_found.append((i, cmd, conflict))

        if conflicts_found:
            # Deduplicate conflicts by resource name
            unique_resources = {}
            for idx, cmd, conflict in conflicts_found:
                resource_name = conflict.get("resource_name", cmd)
                if resource_name not in unique_resources:
                    unique_resources[resource_name] = []
                unique_resources[resource_name].append((idx, cmd, conflict))

            console.print(
                f"  [{YELLOW}]{ICON_PENDING}[/{YELLOW}] Found [bold {WHITE}]{len(unique_resources)}[/bold {WHITE}] unique conflict(s)"
            )

            for resource_name, resource_conflicts in unique_resources.items():
                # Only ask once per unique resource
                first_idx, first_cmd, first_conflict = resource_conflicts[0]

                # Handle the first conflict to get user's decision
                decision = self._handle_resource_conflict(
                    first_idx, first_cmd, first_conflict, commands_to_skip, cleanup_commands
                )
                resource_decisions[resource_name] = decision

                # Apply the same decision to all other commands affecting this resource
                if len(resource_conflicts) > 1:
                    for idx, cmd, conflict in resource_conflicts[1:]:
                        if first_idx in commands_to_skip:
                            commands_to_skip.add(idx)

            # Run cleanup commands for non-Docker conflicts
            if cleanup_commands:
                console.print("[dim]   Running cleanup commands...[/dim]")
                for cleanup_cmd in cleanup_commands:
                    self._execute_single_command(cleanup_cmd, needs_sudo=True)
                    console.print(f"[dim]   ✓ {cleanup_cmd}[/dim]")

            # Filter out skipped commands
            if commands_to_skip:
                filtered_commands = [
                    (cmd, purpose, protected)
                    for i, (cmd, purpose, protected) in enumerate(commands)
                    if i not in commands_to_skip
                ]
                # Update task tree to skip these tasks
                for task in self._task_tree.root_tasks:
                    task_idx = next(
                        (i for i, (c, p, pr) in enumerate(commands) if c == task.command), None
                    )
                    if task_idx in commands_to_skip:
                        task.status = CommandStatus.SKIPPED
                        task.output = "Using existing resource"
                commands = filtered_commands
        else:
            console.print(f"  [{GREEN}]{ICON_SUCCESS}[/{GREEN}] No conflicts detected")

        console.print()

        all_protected = set()
        for _, _, protected in commands:
            all_protected.update(protected)

        if all_protected:
            console.print(f"[{GRAY}]📁 Protected paths: {', '.join(all_protected)}[/{GRAY}]")
            console.print()

        try:
            # Phase 2: Execute Commands - Claude-like header
            console.print()
            console.print(
                f"[bold {PURPLE}]━━━[/bold {PURPLE}] [bold {WHITE}]Executing Commands[/bold {WHITE}]"
            )
            console.print()

            # Track remaining commands for resume functionality
            executed_tasks = set()
            for i, root_task in enumerate(self._task_tree.root_tasks):
                if self._interrupted:
                    # Store remaining tasks for potential continuation
                    remaining_tasks = self._task_tree.root_tasks[i:]
                    self._remaining_commands = [
                        (t.command, t.purpose, [])
                        for t in remaining_tasks
                        if t.status not in (CommandStatus.SUCCESS, CommandStatus.SKIPPED)
                    ]
                    break
                self._execute_task_node(root_task, run, commands)
                executed_tasks.add(root_task.id)

            if not self._interrupted:
                # Phase 3: Verification Tests - Claude-like header
                console.print()
                console.print(
                    f"[bold {PURPLE}]━━━[/bold {PURPLE}] [bold {WHITE}]Verification[/bold {WHITE}]"
                )

                all_tests_passed, test_results = self._verification_runner.run_verification_tests(
                    run.commands, user_query
                )

                # Phase 4: Auto-repair if tests failed
                if not all_tests_passed:
                    console.print()
                    console.print(
                        f"[bold {PURPLE}]━━━[/bold {PURPLE}] [bold {WHITE}]Auto-Repair[/bold {WHITE}]"
                    )

                    repair_success = self._handle_test_failures(test_results, run)

                    if repair_success:
                        console.print()
                        console.print(f"[{GRAY}]   Re-running verification tests...[/{GRAY}]")
                        all_tests_passed, test_results = (
                            self._verification_runner.run_verification_tests(
                                run.commands, user_query
                            )
                        )
            else:
                all_tests_passed = False
                test_results = []

            run.completed_at = datetime.datetime.now().isoformat()

            if self._interrupted:
                run.summary = f"INTERRUPTED after {len(self._executed_commands)} command(s)"
            else:
                run.summary = self._generate_tree_summary(run)
                if test_results:
                    passed = sum(1 for t in test_results if t["passed"])
                    run.summary += f" | Tests: {passed}/{len(test_results)} passed"

            self.db.save_run(run)

            console.print()
            console.print("[bold]Task Execution Tree:[/bold]")
            self._task_tree.print_tree()

            # Generate LLM summary/answer if available
            llm_answer = None
            if not self._interrupted:
                llm_answer = self._generate_llm_answer(run, user_query)

            # Print condensed execution summary with answer
            self._print_execution_summary(run, answer=llm_answer)

            console.print()
            if self._interrupted:
                console.print(f"[dim]Run ID: {run.run_id} (interrupted)[/dim]")
            elif all_tests_passed:
                console.print(f"[dim]Run ID: {run.run_id}[/dim]")

            if self._permission_requests_count > 1:
                console.print(
                    f"[dim]Permission requests made: {self._permission_requests_count}[/dim]"
                )

            # Reset interrupted flag before interactive session
            # This allows the user to continue the session even after stopping a command
            was_interrupted = self._interrupted
            self._interrupted = False

            # Always go to interactive session - even after interruption
            # User can decide what to do next (retry, skip, exit)
            self._interactive_session(run, commands, user_query, was_interrupted=was_interrupted)

            return run

        finally:
            # Always restore signal handlers
            self._restore_signal_handlers()

    def _interactive_session(
        self,
        run: DoRun,
        commands: list[tuple[str, str, list[str]]],
        user_query: str,
        was_interrupted: bool = False,
    ) -> None:
        """Interactive session after task completion - suggest next steps.

        If was_interrupted is True, the previous command execution was stopped
        by Ctrl+Z/Ctrl+C. We still continue the session so the user can decide
        what to do next (retry, skip remaining, run different command, etc).
        """
        import sys

        from rich.prompt import Prompt

        # Flush any pending output to ensure clean display
        sys.stdout.flush()
        sys.stderr.flush()

        # Generate context-aware suggestions based on what was done
        suggestions = self._generate_suggestions(run, commands, user_query)

        # If interrupted, add special suggestions at the beginning
        if was_interrupted:
            interrupted_suggestions = [
                {
                    "label": "🔄 Retry interrupted command",
                    "description": "Try running the interrupted command again",
                    "type": "retry_interrupted",
                },
                {
                    "label": "⏭️ Skip and continue",
                    "description": "Skip the interrupted command and continue with remaining tasks",
                    "type": "skip_and_continue",
                },
            ]
            suggestions = interrupted_suggestions + suggestions

        # Track context for natural language processing
        context = {
            "original_query": user_query,
            "executed_commands": [cmd for cmd, _, _ in commands],
            "session_actions": [],
            "was_interrupted": was_interrupted,
        }

        console.print()
        if was_interrupted:
            console.print(
                f"[bold {YELLOW}]━━━[/bold {YELLOW}] [bold {WHITE}]Execution Interrupted - What would you like to do?[/bold {WHITE}]"
            )
        else:
            console.print(
                f"[bold {PURPLE}]━━━[/bold {PURPLE}] [bold {WHITE}]Next Steps[/bold {WHITE}]"
            )
        console.print()

        # Display suggestions
        self._display_suggestions(suggestions)

        console.print()
        console.print(f"[{GRAY}]You can type any request in natural language[/{GRAY}]")
        console.print()

        # Ensure prompt is visible
        sys.stdout.flush()

        while True:
            try:
                response = Prompt.ask(
                    f"[bold {PURPLE_LIGHT}]{ICON_CMD}[/bold {PURPLE_LIGHT}]", default="exit"
                )

                response_stripped = response.strip()
                response_lower = response_stripped.lower()

                # Check for exit keywords
                if response_lower in [
                    "exit",
                    "quit",
                    "done",
                    "no",
                    "n",
                    "bye",
                    "thanks",
                    "nothing",
                    "",
                ]:
                    console.print(
                        "[dim]👋 Session ended. Run 'cortex do history' to see past runs.[/dim]"
                    )
                    break

                # Try to parse as number (for suggestion selection)
                try:
                    choice = int(response_stripped)
                    if suggestions and 1 <= choice <= len(suggestions):
                        suggestion = suggestions[choice - 1]
                        self._execute_suggestion(suggestion, run, user_query)
                        context["session_actions"].append(suggestion.get("label", ""))

                        # Update last query to the suggestion for context-aware follow-ups
                        suggestion_label = suggestion.get("label", "")
                        context["last_query"] = suggestion_label

                        # Continue the session with suggestions based on what was just done
                        console.print()
                        suggestions = self._generate_suggestions_for_query(
                            suggestion_label, context
                        )
                        self._display_suggestions(suggestions)
                        console.print()
                        continue
                    elif suggestions and choice == len(suggestions) + 1:
                        console.print("[dim]👋 Session ended.[/dim]")
                        break
                except ValueError:
                    pass

                # Handle natural language request
                handled = self._handle_natural_language_request(
                    response_stripped, suggestions, context, run, commands
                )

                if handled:
                    context["session_actions"].append(response_stripped)
                    # Update context with the new query for better suggestions
                    context["last_query"] = response_stripped

                    # Refresh suggestions based on NEW query (not combined)
                    # This ensures suggestions are relevant to what user just asked
                    console.print()
                    suggestions = self._generate_suggestions_for_query(response_stripped, context)
                    self._display_suggestions(suggestions)
                    console.print()

            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]👋 Session ended.[/dim]")
                break

        # Cleanup: ensure any terminal monitors are stopped
        if self._terminal_monitor:
            self._terminal_monitor.stop()
            self._terminal_monitor = None

    def _generate_suggestions_for_query(self, query: str, context: dict) -> list[dict]:
        """Generate suggestions based on the current query and context.

        This generates follow-up suggestions relevant to what the user just asked/did,
        not tied to the original task.
        """
        suggestions = []
        query_lower = query.lower()

        # User management related queries
        if any(w in query_lower for w in ["user", "locked", "password", "account", "login"]):
            suggestions.append(
                {
                    "type": "info",
                    "icon": "👥",
                    "label": "List all users",
                    "description": "Show all system users",
                    "command": "cat /etc/passwd | cut -d: -f1",
                    "purpose": "List all users",
                }
            )
            suggestions.append(
                {
                    "type": "info",
                    "icon": "🔐",
                    "label": "Check sudo users",
                    "description": "Show users with sudo access",
                    "command": "getent group sudo",
                    "purpose": "List sudo group members",
                }
            )
            suggestions.append(
                {
                    "type": "action",
                    "icon": "🔓",
                    "label": "Unlock a user",
                    "description": "Unlock a locked user account",
                    "demo_type": "unlock_user",
                }
            )

        # Service/process related queries
        elif any(
            w in query_lower for w in ["service", "systemctl", "running", "process", "status"]
        ):
            suggestions.append(
                {
                    "type": "info",
                    "icon": "📊",
                    "label": "List running services",
                    "description": "Show all active services",
                    "command": "systemctl list-units --type=service --state=running",
                    "purpose": "List running services",
                }
            )
            suggestions.append(
                {
                    "type": "info",
                    "icon": "🔍",
                    "label": "Check failed services",
                    "description": "Show services that failed to start",
                    "command": "systemctl list-units --type=service --state=failed",
                    "purpose": "List failed services",
                }
            )

        # Disk/storage related queries
        elif any(w in query_lower for w in ["disk", "storage", "space", "mount", "partition"]):
            suggestions.append(
                {
                    "type": "info",
                    "icon": "💾",
                    "label": "Check disk usage",
                    "description": "Show disk space by partition",
                    "command": "df -h",
                    "purpose": "Check disk usage",
                }
            )
            suggestions.append(
                {
                    "type": "info",
                    "icon": "📁",
                    "label": "Find large files",
                    "description": "Show largest files on disk",
                    "command": "sudo du -ah / 2>/dev/null | sort -rh | head -20",
                    "purpose": "Find large files",
                }
            )

        # Network related queries
        elif any(w in query_lower for w in ["network", "ip", "port", "connection", "firewall"]):
            suggestions.append(
                {
                    "type": "info",
                    "icon": "🌐",
                    "label": "Show network interfaces",
                    "description": "Display IP addresses and interfaces",
                    "command": "ip addr show",
                    "purpose": "Show network interfaces",
                }
            )
            suggestions.append(
                {
                    "type": "info",
                    "icon": "🔌",
                    "label": "List open ports",
                    "description": "Show listening ports",
                    "command": "sudo ss -tlnp",
                    "purpose": "List open ports",
                }
            )

        # Security related queries
        elif any(w in query_lower for w in ["security", "audit", "log", "auth", "fail"]):
            suggestions.append(
                {
                    "type": "info",
                    "icon": "🔒",
                    "label": "Check auth logs",
                    "description": "Show recent authentication attempts",
                    "command": "sudo tail -50 /var/log/auth.log",
                    "purpose": "Check auth logs",
                }
            )
            suggestions.append(
                {
                    "type": "info",
                    "icon": "⚠️",
                    "label": "Check failed logins",
                    "description": "Show failed login attempts",
                    "command": "sudo lastb | head -20",
                    "purpose": "Check failed logins",
                }
            )

        # Package/installation related queries
        elif any(w in query_lower for w in ["install", "package", "apt", "update"]):
            suggestions.append(
                {
                    "type": "action",
                    "icon": "📦",
                    "label": "Update system",
                    "description": "Update package lists and upgrade",
                    "command": "sudo apt update && sudo apt upgrade -y",
                    "purpose": "Update system packages",
                }
            )
            suggestions.append(
                {
                    "type": "info",
                    "icon": "📋",
                    "label": "List installed packages",
                    "description": "Show recently installed packages",
                    "command": "apt list --installed 2>/dev/null | tail -20",
                    "purpose": "List installed packages",
                }
            )

        # Default: generic helpful suggestions
        if not suggestions:
            suggestions.append(
                {
                    "type": "info",
                    "icon": "📊",
                    "label": "System overview",
                    "description": "Show system info and resource usage",
                    "command": "uname -a && uptime && free -h",
                    "purpose": "System overview",
                }
            )
            suggestions.append(
                {
                    "type": "info",
                    "icon": "🔍",
                    "label": "Check system logs",
                    "description": "View recent system messages",
                    "command": "sudo journalctl -n 20 --no-pager",
                    "purpose": "Check system logs",
                }
            )

        return suggestions

    def _display_suggestions(self, suggestions: list[dict]) -> None:
        """Display numbered suggestions."""
        if not suggestions:
            console.print(f"[{GRAY}]No specific suggestions available.[/{GRAY}]")
            return

        for i, suggestion in enumerate(suggestions, 1):
            icon = suggestion.get("icon", "💡")
            label = suggestion.get("label", "")
            desc = suggestion.get("description", "")
            console.print(
                f"  [{PURPLE_LIGHT}]{i}.[/{PURPLE_LIGHT}] {icon} [{WHITE}]{label}[/{WHITE}]"
            )
            if desc:
                console.print(f"      [{GRAY}]{desc}[/{GRAY}]")

        console.print(f"  [{PURPLE_LIGHT}]{len(suggestions) + 1}.[/{PURPLE_LIGHT}] 🚪 Exit session")

    def _handle_natural_language_request(
        self,
        request: str,
        suggestions: list[dict],
        context: dict,
        run: DoRun,
        commands: list[tuple[str, str, list[str]]],
    ) -> bool:
        """Handle a natural language request from the user.

        Uses LLM if available for full understanding, falls back to pattern matching.
        Returns True if the request was handled, False otherwise.
        """
        request_lower = request.lower()

        # Quick keyword matching for common actions (fast path)
        keyword_handlers = [
            (["start", "run", "begin", "launch", "execute"], "start"),
            (["setup", "configure", "config", "set up"], "setup"),
            (["demo", "example", "sample", "code"], "demo"),
            (["test", "verify", "check", "validate"], "test"),
        ]

        # Check if request is a simple match to existing suggestions
        for keywords, action_type in keyword_handlers:
            if any(kw in request_lower for kw in keywords):
                # Only use quick match if it's a very simple request
                if len(request.split()) <= 4:
                    for suggestion in suggestions:
                        if suggestion.get("type") == action_type:
                            self._execute_suggestion(suggestion, run, context["original_query"])
                            return True

        # Use LLM for full understanding if available
        console.print()
        console.print(f"[{PURPLE_LIGHT}]🤔 Understanding your request...[/{PURPLE_LIGHT}]")

        if self.llm_callback:
            return self._handle_request_with_llm(request, context, run, commands)
        else:
            # Fall back to pattern matching
            return self._handle_request_with_patterns(request, context, run)

    def _handle_request_with_llm(
        self,
        request: str,
        context: dict,
        run: DoRun,
        commands: list[tuple[str, str, list[str]]],
    ) -> bool:
        """Handle request using LLM for full understanding."""
        try:
            # Call LLM to understand the request
            llm_response = self.llm_callback(request, context)

            if not llm_response or llm_response.get("response_type") == "error":
                console.print(
                    f"[{YELLOW}]⚠ Could not process request: {llm_response.get('error', 'Unknown error')}[/{YELLOW}]"
                )
                return False

            response_type = llm_response.get("response_type")

            # HARD CHECK: Filter out any raw JSON from reasoning field
            reasoning = llm_response.get("reasoning", "")
            if reasoning:
                # Remove any JSON-like content from reasoning
                import re

                # If reasoning looks like JSON or contains JSON patterns, clean it
                if (
                    reasoning.strip().startswith(("{", "[", "]", '"response_type"'))
                    or re.search(r'"do_commands"\s*:', reasoning)
                    or re.search(r'"command"\s*:', reasoning)
                    or re.search(r'"requires_sudo"\s*:', reasoning)
                ):
                    # Extract just the text explanation if possible
                    text_match = re.search(r'"reasoning"\s*:\s*"([^"]+)"', reasoning)
                    if text_match:
                        reasoning = text_match.group(1)
                    else:
                        reasoning = "Processing your request..."
                llm_response["reasoning"] = reasoning

            # Handle do_commands - execute with confirmation
            if response_type == "do_commands" and llm_response.get("do_commands"):
                do_commands = llm_response["do_commands"]
                reasoning = llm_response.get("reasoning", "")

                # Final safety check: don't print JSON-looking reasoning
                if reasoning and not self._is_json_like(reasoning):
                    console.print()
                    console.print(f"[{PURPLE_LIGHT}]🤖 {reasoning}[/{PURPLE_LIGHT}]")
                console.print()

                # Show commands and ask for confirmation
                console.print(f"[bold {WHITE}]📋 Commands to execute:[/bold {WHITE}]")
                for i, cmd_info in enumerate(do_commands, 1):
                    cmd = cmd_info.get("command", "")
                    purpose = cmd_info.get("purpose", "")
                    sudo = "🔐 " if cmd_info.get("requires_sudo") else ""
                    console.print(f"  {i}. {sudo}[{GREEN}]{cmd}[/{GREEN}]")
                    if purpose:
                        console.print(f"     [{GRAY}]{purpose}[/{GRAY}]")
                console.print()

                if not Confirm.ask("Execute these commands?", default=True):
                    console.print(f"[{GRAY}]Skipped.[/{GRAY}]")
                    return False

                # Execute the commands
                console.print()
                from rich.panel import Panel

                executed_in_session = []
                for idx, cmd_info in enumerate(do_commands, 1):
                    cmd = cmd_info.get("command", "")
                    purpose = cmd_info.get("purpose", "Execute command")
                    needs_sudo = cmd_info.get("requires_sudo", False) or self._needs_sudo(cmd, [])

                    # Create visual grouping for each command
                    console.print()
                    console.print(
                        Panel(
                            f"[bold {PURPLE_LIGHT}]{cmd}[/bold {PURPLE_LIGHT}]\n[{GRAY}]└─ {purpose}[/{GRAY}]",
                            title=f"[bold {WHITE}] Command {idx}/{len(do_commands)} [/bold {WHITE}]",
                            title_align="left",
                            border_style=PURPLE,
                            padding=(0, 1),
                        )
                    )

                    success, stdout, stderr = self._execute_single_command(cmd, needs_sudo)

                    if success:
                        console.print(
                            Panel(
                                f"[bold {GREEN}]{ICON_SUCCESS} Success[/bold {GREEN}]",
                                border_style=PURPLE,
                                padding=(0, 1),
                                expand=False,
                            )
                        )
                        if stdout:
                            output_preview = stdout[:300] + ("..." if len(stdout) > 300 else "")
                            console.print(f"[{GRAY}]{output_preview}[/{GRAY}]")
                        executed_in_session.append(cmd)
                    else:
                        console.print(
                            Panel(
                                f"[bold {RED}]{ICON_ERROR} Failed[/bold {RED}]\n[{GRAY}]{stderr[:150]}[/{GRAY}]",
                                border_style=RED,
                                padding=(0, 1),
                            )
                        )

                        # Offer to diagnose and fix
                        if Confirm.ask("Try to auto-fix?", default=True):
                            diagnosis = self._diagnoser.diagnose_error(cmd, stderr)
                            fixed, msg, _ = self._auto_fixer.auto_fix_error(cmd, stderr, diagnosis)
                            if fixed:
                                console.print(
                                    Panel(
                                        f"[bold {GREEN}]{ICON_SUCCESS} Fixed:[/bold {GREEN}] [{WHITE}]{msg}[/{WHITE}]",
                                        border_style=PURPLE,
                                        padding=(0, 1),
                                        expand=False,
                                    )
                                )
                                executed_in_session.append(cmd)

                # Track executed commands in context for suggestion generation
                if "executed_commands" not in context:
                    context["executed_commands"] = []
                context["executed_commands"].extend(executed_in_session)

                return True

            # Handle single command - execute directly
            elif response_type == "command" and llm_response.get("command"):
                cmd = llm_response["command"]
                reasoning = llm_response.get("reasoning", "")

                console.print()
                console.print(
                    f"[{PURPLE_LIGHT}]📋 Running:[/{PURPLE_LIGHT}] [{GREEN}]{cmd}[/{GREEN}]"
                )
                if reasoning:
                    console.print(f"   [{GRAY}]{reasoning}[/{GRAY}]")

                needs_sudo = self._needs_sudo(cmd, [])
                success, stdout, stderr = self._execute_single_command(cmd, needs_sudo)

                if success:
                    console.print(f"[{GREEN}]{ICON_SUCCESS} Success[/{GREEN}]")
                    if stdout:
                        console.print(
                            f"[{GRAY}]{stdout[:500]}{'...' if len(stdout) > 500 else ''}[/{GRAY}]"
                        )
                else:
                    console.print(f"[{RED}]{ICON_ERROR} Failed: {stderr[:200]}[/{RED}]")

                return True

            # Handle answer - just display it (filter raw JSON)
            elif response_type == "answer" and llm_response.get("answer"):
                answer = llm_response["answer"]
                # Don't print raw JSON or internal processing messages
                if not (
                    self._is_json_like(answer)
                    or "I'm processing your request" in answer
                    or "I have a plan to execute" in answer
                ):
                    console.print()
                    console.print(answer)
                return True

            else:
                console.print(f"[{YELLOW}]I didn't understand that. Could you rephrase?[/{YELLOW}]")
                return False

        except Exception as e:
            console.print(f"[{YELLOW}]⚠ Error processing request: {e}[/{YELLOW}]")
            # Fall back to pattern matching
            return self._handle_request_with_patterns(request, context, run)

    def _handle_request_with_patterns(
        self,
        request: str,
        context: dict,
        run: DoRun,
    ) -> bool:
        """Handle request using pattern matching (fallback when LLM not available)."""
        # Try to generate a command from the natural language request
        generated = self._generate_command_from_request(request, context)

        if generated:
            cmd = generated.get("command")
            purpose = generated.get("purpose", "Execute user request")
            needs_confirm = generated.get("needs_confirmation", True)

            console.print()
            console.print(f"[{PURPLE_LIGHT}]📋 I'll run this command:[/{PURPLE_LIGHT}]")
            console.print(f"   [{GREEN}]{cmd}[/{GREEN}]")
            console.print(f"   [{GRAY}]{purpose}[/{GRAY}]")
            console.print()

            if needs_confirm:
                if not Confirm.ask("Proceed?", default=True):
                    console.print(f"[{GRAY}]Skipped.[/{GRAY}]")
                    return False

            # Execute the command
            needs_sudo = self._needs_sudo(cmd, [])
            success, stdout, stderr = self._execute_single_command(cmd, needs_sudo)

            if success:
                console.print(f"[{GREEN}]{ICON_SUCCESS} Success[/{GREEN}]")
                if stdout:
                    output_preview = stdout[:500] + ("..." if len(stdout) > 500 else "")
                    console.print(f"[{GRAY}]{output_preview}[/{GRAY}]")
            else:
                console.print(f"[{RED}]{ICON_ERROR} Failed: {stderr[:200]}[/{RED}]")

                # Offer to diagnose the error
                if Confirm.ask("Would you like me to try to fix this?", default=True):
                    diagnosis = self._diagnoser.diagnose_error(cmd, stderr)
                    fixed, msg, _ = self._auto_fixer.auto_fix_error(cmd, stderr, diagnosis)
                    if fixed:
                        console.print(f"[{GREEN}]{ICON_SUCCESS} Fixed: {msg}[/{GREEN}]")

            return True

        # Couldn't understand the request
        console.print(
            f"[{YELLOW}]I'm not sure how to do that. Could you be more specific?[/{YELLOW}]"
        )
        console.print(
            "[dim]Try something like: 'run the container', 'show me the config', or select a number.[/dim]"
        )
        return False

    def _generate_command_from_request(
        self,
        request: str,
        context: dict,
    ) -> dict | None:
        """Generate a command from a natural language request."""
        request_lower = request.lower()
        executed_cmds = context.get("executed_commands", [])
        cmd_context = " ".join(executed_cmds).lower()

        # Pattern matching for common requests
        patterns = [
            # Docker patterns
            (r"run.*(?:container|image|docker)(?:.*port\s*(\d+))?", self._gen_docker_run),
            (r"stop.*(?:container|docker)", self._gen_docker_stop),
            (r"remove.*(?:container|docker)", self._gen_docker_remove),
            (r"(?:show|list).*(?:containers?|images?)", self._gen_docker_list),
            (r"logs?(?:\s+of)?(?:\s+the)?(?:\s+container)?", self._gen_docker_logs),
            (r"exec.*(?:container|docker)|shell.*(?:container|docker)", self._gen_docker_exec),
            # Service patterns
            (
                r"(?:start|restart).*(?:service|nginx|apache|postgres|mysql|redis)",
                self._gen_service_start,
            ),
            (r"stop.*(?:service|nginx|apache|postgres|mysql|redis)", self._gen_service_stop),
            (r"status.*(?:service|nginx|apache|postgres|mysql|redis)", self._gen_service_status),
            # Package patterns
            (r"install\s+(.+)", self._gen_install_package),
            (r"update\s+(?:packages?|system)", self._gen_update_packages),
            # File patterns
            (
                r"(?:show|cat|view|read).*(?:config|file|log)(?:.*?([/\w\.\-]+))?",
                self._gen_show_file,
            ),
            (r"edit.*(?:config|file)(?:.*?([/\w\.\-]+))?", self._gen_edit_file),
            # Info patterns
            (r"(?:check|show|what).*(?:version|status)", self._gen_check_version),
            (r"(?:how|where).*(?:connect|access|use)", self._gen_show_connection_info),
        ]

        import re

        for pattern, handler in patterns:
            match = re.search(pattern, request_lower)
            if match:
                return handler(request, match, context)

        # Use LLM if available to generate command
        if self.llm_callback:
            return self._llm_generate_command(request, context)

        return None

    # Command generators
    def _gen_docker_run(self, request: str, match, context: dict) -> dict:
        # Find the image from context
        executed = context.get("executed_commands", [])
        image = "your-image"
        for cmd in executed:
            if "docker pull" in cmd:
                image = cmd.split("docker pull")[-1].strip()
                break

        # Check for port in request
        port = match.group(1) if match.lastindex and match.group(1) else "8080"
        container_name = image.split("/")[-1].split(":")[0]

        return {
            "command": f"docker run -d --name {container_name} -p {port}:{port} {image}",
            "purpose": f"Run {image} container on port {port}",
            "needs_confirmation": True,
        }

    def _gen_docker_stop(self, request: str, match, context: dict) -> dict:
        return {
            "command": "docker ps -q | xargs -r docker stop",
            "purpose": "Stop all running containers",
            "needs_confirmation": True,
        }

    def _gen_docker_remove(self, request: str, match, context: dict) -> dict:
        return {
            "command": "docker ps -aq | xargs -r docker rm",
            "purpose": "Remove all containers",
            "needs_confirmation": True,
        }

    def _gen_docker_list(self, request: str, match, context: dict) -> dict:
        if "image" in request.lower():
            return {
                "command": "docker images",
                "purpose": "List Docker images",
                "needs_confirmation": False,
            }
        return {
            "command": "docker ps -a",
            "purpose": "List all containers",
            "needs_confirmation": False,
        }

    def _gen_docker_logs(self, request: str, match, context: dict) -> dict:
        return {
            "command": "docker logs $(docker ps -lq) --tail 50",
            "purpose": "Show logs of the most recent container",
            "needs_confirmation": False,
        }

    def _gen_docker_exec(self, request: str, match, context: dict) -> dict:
        return {
            "command": "docker exec -it $(docker ps -lq) /bin/sh",
            "purpose": "Open shell in the most recent container",
            "needs_confirmation": True,
        }

    def _gen_service_start(self, request: str, match, context: dict) -> dict:
        # Extract service name
        services = ["nginx", "apache2", "postgresql", "mysql", "redis", "docker"]
        service = "nginx"  # default
        for svc in services:
            if svc in request.lower():
                service = svc
                break

        if "restart" in request.lower():
            return {
                "command": f"sudo systemctl restart {service}",
                "purpose": f"Restart {service}",
                "needs_confirmation": True,
            }
        return {
            "command": f"sudo systemctl start {service}",
            "purpose": f"Start {service}",
            "needs_confirmation": True,
        }

    def _gen_service_stop(self, request: str, match, context: dict) -> dict:
        services = ["nginx", "apache2", "postgresql", "mysql", "redis", "docker"]
        service = "nginx"
        for svc in services:
            if svc in request.lower():
                service = svc
                break
        return {
            "command": f"sudo systemctl stop {service}",
            "purpose": f"Stop {service}",
            "needs_confirmation": True,
        }

    def _gen_service_status(self, request: str, match, context: dict) -> dict:
        services = ["nginx", "apache2", "postgresql", "mysql", "redis", "docker"]
        service = "nginx"
        for svc in services:
            if svc in request.lower():
                service = svc
                break
        return {
            "command": f"systemctl status {service}",
            "purpose": f"Check {service} status",
            "needs_confirmation": False,
        }

    def _gen_install_package(self, request: str, match, context: dict) -> dict:
        package = match.group(1).strip() if match.group(1) else "package-name"
        # Clean up common words
        package = package.replace("please", "").replace("the", "").replace("package", "").strip()
        return {
            "command": f"sudo apt install -y {package}",
            "purpose": f"Install {package}",
            "needs_confirmation": True,
        }

    def _gen_update_packages(self, request: str, match, context: dict) -> dict:
        return {
            "command": "sudo apt update && sudo apt upgrade -y",
            "purpose": "Update all packages",
            "needs_confirmation": True,
        }

    def _gen_show_file(self, request: str, match, context: dict) -> dict:
        # Try to extract file path or use common config locations
        file_path = match.group(1) if match.lastindex and match.group(1) else None

        if not file_path:
            if "nginx" in request.lower():
                file_path = "/etc/nginx/nginx.conf"
            elif "apache" in request.lower():
                file_path = "/etc/apache2/apache2.conf"
            elif "postgres" in request.lower():
                file_path = "/etc/postgresql/*/main/postgresql.conf"
            else:
                file_path = "/etc/hosts"

        return {
            "command": f"cat {file_path}",
            "purpose": f"Show {file_path}",
            "needs_confirmation": False,
        }

    def _gen_edit_file(self, request: str, match, context: dict) -> dict:
        file_path = match.group(1) if match.lastindex and match.group(1) else "/etc/hosts"
        return {
            "command": f"sudo nano {file_path}",
            "purpose": f"Edit {file_path}",
            "needs_confirmation": True,
        }

    def _gen_check_version(self, request: str, match, context: dict) -> dict:
        # Try to determine what to check version of
        tools = {
            "docker": "docker --version",
            "node": "node --version && npm --version",
            "python": "python3 --version && pip3 --version",
            "nginx": "nginx -v",
            "postgres": "psql --version",
        }

        for tool, cmd in tools.items():
            if tool in request.lower():
                return {
                    "command": cmd,
                    "purpose": f"Check {tool} version",
                    "needs_confirmation": False,
                }

        # Default: show multiple versions
        return {
            "command": "docker --version; node --version 2>/dev/null; python3 --version",
            "purpose": "Check installed tool versions",
            "needs_confirmation": False,
        }

    def _gen_show_connection_info(self, request: str, match, context: dict) -> dict:
        executed = context.get("executed_commands", [])

        # Check what was installed to provide relevant connection info
        if any("ollama" in cmd for cmd in executed):
            return {
                "command": "echo 'Ollama API: http://localhost:11434' && curl -s http://localhost:11434/api/tags 2>/dev/null | head -5",
                "purpose": "Show Ollama connection info",
                "needs_confirmation": False,
            }
        elif any("postgres" in cmd for cmd in executed):
            return {
                "command": "echo 'PostgreSQL: psql -U postgres -h localhost' && sudo -u postgres psql -c '\\conninfo'",
                "purpose": "Show PostgreSQL connection info",
                "needs_confirmation": False,
            }
        elif any("nginx" in cmd for cmd in executed):
            return {
                "command": "echo 'Nginx: http://localhost:80' && curl -I http://localhost 2>/dev/null | head -3",
                "purpose": "Show Nginx connection info",
                "needs_confirmation": False,
            }

        return {
            "command": "ss -tlnp | head -20",
            "purpose": "Show listening ports and services",
            "needs_confirmation": False,
        }

    def _llm_generate_command(self, request: str, context: dict) -> dict | None:
        """Use LLM to generate a command from the request."""
        if not self.llm_callback:
            return None

        try:
            prompt = f"""Given this context:
- User originally asked: {context.get('original_query', 'N/A')}
- Commands executed: {', '.join(context.get('executed_commands', [])[:5])}
- Previous session actions: {', '.join(context.get('session_actions', [])[:3])}

The user now asks: "{request}"

Generate a single Linux command to fulfill this request.
Respond with JSON: {{"command": "...", "purpose": "..."}}
If you cannot generate a safe command, respond with: {{"error": "reason"}}"""

            result = self.llm_callback(prompt)
            if result and isinstance(result, dict):
                if "command" in result:
                    return {
                        "command": result["command"],
                        "purpose": result.get("purpose", "Execute user request"),
                        "needs_confirmation": True,
                    }
        except Exception:
            pass

        return None

    def _generate_suggestions(
        self,
        run: DoRun,
        commands: list[tuple[str, str, list[str]]],
        user_query: str,
    ) -> list[dict]:
        """Generate context-aware suggestions based on what was installed/configured."""
        suggestions = []

        # Analyze what was done
        executed_cmds = [cmd for cmd, _, _ in commands]
        cmd_str = " ".join(executed_cmds).lower()
        query_lower = user_query.lower()

        # Docker-related suggestions
        if "docker" in cmd_str or "docker" in query_lower:
            if "pull" in cmd_str:
                # Suggest running the container
                for cmd, _, _ in commands:
                    if "docker pull" in cmd:
                        image = cmd.split("docker pull")[-1].strip()
                        suggestions.append(
                            {
                                "type": "start",
                                "icon": "🚀",
                                "label": "Start the container",
                                "description": f"Run {image} in a container",
                                "command": f"docker run -d --name {image.split('/')[-1].split(':')[0]} {image}",
                                "purpose": f"Start {image} container",
                            }
                        )
                        suggestions.append(
                            {
                                "type": "demo",
                                "icon": "📝",
                                "label": "Show demo usage",
                                "description": "Example docker-compose and run commands",
                                "demo_type": "docker",
                                "image": image,
                            }
                        )
                        break

        # Ollama/Model runner suggestions
        if "ollama" in cmd_str or "ollama" in query_lower or "model" in query_lower:
            suggestions.append(
                {
                    "type": "start",
                    "icon": "🚀",
                    "label": "Start Ollama server",
                    "description": "Run Ollama in the background",
                    "command": "docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama",
                    "purpose": "Start Ollama server container",
                }
            )
            suggestions.append(
                {
                    "type": "setup",
                    "icon": "⚙️",
                    "label": "Pull a model",
                    "description": "Download a model like llama2, mistral, or codellama",
                    "command": "docker exec ollama ollama pull llama2",
                    "purpose": "Download llama2 model",
                }
            )
            suggestions.append(
                {
                    "type": "demo",
                    "icon": "📝",
                    "label": "Show API demo",
                    "description": "Example curl commands and Python code",
                    "demo_type": "ollama",
                }
            )
            suggestions.append(
                {
                    "type": "test",
                    "icon": "🧪",
                    "label": "Test the installation",
                    "description": "Verify Ollama is running correctly",
                    "command": "curl http://localhost:11434/api/tags",
                    "purpose": "Check Ollama API",
                }
            )

        # Nginx suggestions
        if "nginx" in cmd_str or "nginx" in query_lower:
            suggestions.append(
                {
                    "type": "start",
                    "icon": "🚀",
                    "label": "Start Nginx",
                    "description": "Start the Nginx web server",
                    "command": "sudo systemctl start nginx",
                    "purpose": "Start Nginx service",
                }
            )
            suggestions.append(
                {
                    "type": "setup",
                    "icon": "⚙️",
                    "label": "Configure a site",
                    "description": "Set up a new virtual host",
                    "demo_type": "nginx_config",
                }
            )
            suggestions.append(
                {
                    "type": "test",
                    "icon": "🧪",
                    "label": "Test configuration",
                    "description": "Verify Nginx config is valid",
                    "command": "sudo nginx -t",
                    "purpose": "Test Nginx configuration",
                }
            )

        # PostgreSQL suggestions
        if "postgres" in cmd_str or "postgresql" in query_lower:
            suggestions.append(
                {
                    "type": "start",
                    "icon": "🚀",
                    "label": "Start PostgreSQL",
                    "description": "Start the database server",
                    "command": "sudo systemctl start postgresql",
                    "purpose": "Start PostgreSQL service",
                }
            )
            suggestions.append(
                {
                    "type": "setup",
                    "icon": "⚙️",
                    "label": "Create a database",
                    "description": "Create a new database and user",
                    "demo_type": "postgres_setup",
                }
            )
            suggestions.append(
                {
                    "type": "test",
                    "icon": "🧪",
                    "label": "Test connection",
                    "description": "Verify PostgreSQL is accessible",
                    "command": "sudo -u postgres psql -c '\\l'",
                    "purpose": "List PostgreSQL databases",
                }
            )

        # Node.js/npm suggestions
        if "node" in cmd_str or "npm" in cmd_str or "nodejs" in query_lower:
            suggestions.append(
                {
                    "type": "demo",
                    "icon": "📝",
                    "label": "Show starter code",
                    "description": "Example Express.js server",
                    "demo_type": "nodejs",
                }
            )
            suggestions.append(
                {
                    "type": "test",
                    "icon": "🧪",
                    "label": "Verify installation",
                    "description": "Check Node.js and npm versions",
                    "command": "node --version && npm --version",
                    "purpose": "Check Node.js installation",
                }
            )

        # Python/pip suggestions
        if "python" in cmd_str or "pip" in cmd_str:
            suggestions.append(
                {
                    "type": "demo",
                    "icon": "📝",
                    "label": "Show example code",
                    "description": "Example Python usage",
                    "demo_type": "python",
                }
            )
            suggestions.append(
                {
                    "type": "test",
                    "icon": "🧪",
                    "label": "Test import",
                    "description": "Verify packages are importable",
                    "demo_type": "python_test",
                }
            )

        # Generic suggestions if nothing specific matched
        if not suggestions:
            # Add a generic test suggestion
            suggestions.append(
                {
                    "type": "test",
                    "icon": "🧪",
                    "label": "Run a quick test",
                    "description": "Verify the installation works",
                    "demo_type": "generic_test",
                }
            )

        return suggestions[:5]  # Limit to 5 suggestions

    def _execute_suggestion(
        self,
        suggestion: dict,
        run: DoRun,
        user_query: str,
    ) -> None:
        """Execute a suggestion."""
        suggestion_type = suggestion.get("type")

        if suggestion_type == "retry_interrupted":
            # Retry the command that was interrupted
            if self._interrupted_command:
                console.print()
                console.print(
                    f"[{PURPLE_LIGHT}]🔄 Retrying:[/{PURPLE_LIGHT}] [{WHITE}]{self._interrupted_command}[/{WHITE}]"
                )
                console.print()

                needs_sudo = "sudo" in self._interrupted_command or self._needs_sudo(
                    self._interrupted_command, []
                )
                success, stdout, stderr = self._execute_single_command(
                    self._interrupted_command, needs_sudo=needs_sudo
                )

                if success:
                    console.print(f"[{GREEN}]{ICON_SUCCESS} Success[/{GREEN}]")
                    if stdout:
                        console.print(
                            f"[{GRAY}]{stdout[:500]}{'...' if len(stdout) > 500 else ''}[/{GRAY}]"
                        )
                    self._interrupted_command = None  # Clear after successful retry
                else:
                    console.print(f"[{RED}]{ICON_ERROR} Failed: {stderr[:200]}[/{RED}]")
            else:
                console.print(f"[{YELLOW}]No interrupted command to retry.[/{YELLOW}]")
        elif suggestion_type == "skip_and_continue":
            # Skip the interrupted command and continue with remaining
            console.print()
            console.print(
                f"[{PURPLE_LIGHT}]⏭️ Skipping interrupted command and continuing...[/{PURPLE_LIGHT}]"
            )
            self._interrupted_command = None

            if self._remaining_commands:
                console.print(f"[dim]Remaining commands: {len(self._remaining_commands)}[/dim]")
                for cmd, purpose, protected in self._remaining_commands:
                    console.print(f"[dim]  • {cmd[:60]}{'...' if len(cmd) > 60 else ''}[/dim]")
                console.print()
                console.print(
                    "[dim]Use 'continue all' to execute remaining commands, or type a new request.[/dim]"
                )
            else:
                console.print("[dim]No remaining commands to execute.[/dim]")
        elif suggestion_type == "demo":
            self._show_demo(suggestion.get("demo_type", "generic"), suggestion)
        elif suggestion_type == "test":
            # Show test commands based on what was installed
            self._show_test_commands(run, user_query)
        elif "command" in suggestion:
            console.print()
            console.print(
                f"[{PURPLE_LIGHT}]Executing:[/{PURPLE_LIGHT}] [{WHITE}]{suggestion['command']}[/{WHITE}]"
            )
            console.print()

            needs_sudo = "sudo" in suggestion["command"]
            success, stdout, stderr = self._execute_single_command(
                suggestion["command"], needs_sudo=needs_sudo
            )

            if success:
                console.print(f"[{GREEN}]{ICON_SUCCESS} Success[/{GREEN}]")
                if stdout:
                    console.print(
                        f"[{GRAY}]{stdout[:500]}{'...' if len(stdout) > 500 else ''}[/{GRAY}]"
                    )
            else:
                console.print(f"[{RED}]{ICON_ERROR} Failed: {stderr[:200]}[/{RED}]")
        elif "manual_commands" in suggestion:
            # Show manual commands
            console.print()
            console.print(f"[bold {PURPLE_LIGHT}]📋 Manual Commands:[/bold {PURPLE_LIGHT}]")
            for cmd in suggestion["manual_commands"]:
                console.print(f"  [{GREEN}]$ {cmd}[/{GREEN}]")
            console.print()
            console.print(f"[{GRAY}]Copy and run these commands in your terminal.[/{GRAY}]")
        else:
            console.print(f"[{YELLOW}]No specific action available for this suggestion.[/{YELLOW}]")

    def _show_test_commands(self, run: DoRun, user_query: str) -> None:
        """Show test commands based on what was installed/configured."""
        from rich.panel import Panel

        console.print()
        console.print("[bold cyan]🧪 Quick Test Commands[/bold cyan]")
        console.print()

        test_commands = []
        query_lower = user_query.lower()

        # Detect what was installed and suggest appropriate tests
        executed_cmds = [c.command.lower() for c in run.commands if c.status.value == "success"]
        all_cmds_str = " ".join(executed_cmds)

        # Web server tests
        if "apache" in all_cmds_str or "apache2" in query_lower:
            test_commands.extend(
                [
                    ("Check Apache status", "systemctl status apache2"),
                    ("Test Apache config", "sudo apache2ctl -t"),
                    ("View in browser", "curl -I http://localhost"),
                ]
            )

        if "nginx" in all_cmds_str or "nginx" in query_lower:
            test_commands.extend(
                [
                    ("Check Nginx status", "systemctl status nginx"),
                    ("Test Nginx config", "sudo nginx -t"),
                    ("View in browser", "curl -I http://localhost"),
                ]
            )

        # Database tests
        if "mysql" in all_cmds_str or "mysql" in query_lower:
            test_commands.extend(
                [
                    ("Check MySQL status", "systemctl status mysql"),
                    ("Test MySQL connection", "sudo mysql -e 'SELECT VERSION();'"),
                ]
            )

        if "postgresql" in all_cmds_str or "postgres" in query_lower:
            test_commands.extend(
                [
                    ("Check PostgreSQL status", "systemctl status postgresql"),
                    ("Test PostgreSQL", "sudo -u postgres psql -c 'SELECT version();'"),
                ]
            )

        # Docker tests
        if "docker" in all_cmds_str or "docker" in query_lower:
            test_commands.extend(
                [
                    ("Check Docker status", "systemctl status docker"),
                    ("List containers", "docker ps -a"),
                    ("Test Docker", "docker run hello-world"),
                ]
            )

        # PHP tests
        if "php" in all_cmds_str or "php" in query_lower or "lamp" in query_lower:
            test_commands.extend(
                [
                    ("Check PHP version", "php -v"),
                    ("Test PHP info", "php -i | head -20"),
                ]
            )

        # Node.js tests
        if "node" in all_cmds_str or "nodejs" in query_lower:
            test_commands.extend(
                [
                    ("Check Node version", "node -v"),
                    ("Check npm version", "npm -v"),
                ]
            )

        # Python tests
        if "python" in all_cmds_str or "python" in query_lower:
            test_commands.extend(
                [
                    ("Check Python version", "python3 --version"),
                    ("Check pip version", "pip3 --version"),
                ]
            )

        # Generic service tests
        if not test_commands:
            # Try to extract service names from commands
            for cmd_log in run.commands:
                if "systemctl" in cmd_log.command and cmd_log.status.value == "success":
                    import re

                    match = re.search(
                        r"systemctl\s+(?:start|enable|restart)\s+(\S+)", cmd_log.command
                    )
                    if match:
                        service = match.group(1)
                        test_commands.append(
                            (f"Check {service} status", f"systemctl status {service}")
                        )

        if not test_commands:
            test_commands = [
                ("Check system status", "systemctl --failed"),
                ("View recent logs", "journalctl -n 20 --no-pager"),
            ]

        # Display test commands
        for i, (desc, cmd) in enumerate(test_commands[:6], 1):  # Limit to 6
            console.print(f"  [bold {WHITE}]{i}.[/bold {WHITE}] {desc}")
            console.print(f"     [{GREEN}]$ {cmd}[/{GREEN}]")
            console.print()

        console.print(f"[{GRAY}]Copy and run these commands to verify your installation.[/{GRAY}]")
        console.print()

        # Offer to run the first test
        try:
            response = input(f"[{GRAY}]Run first test? [y/N]: [/{GRAY}]").strip().lower()
            if response in ["y", "yes"]:
                if test_commands:
                    desc, cmd = test_commands[0]
                    console.print()
                    console.print(
                        f"[{PURPLE_LIGHT}]Running:[/{PURPLE_LIGHT}] [{WHITE}]{cmd}[/{WHITE}]"
                    )
                    needs_sudo = cmd.strip().startswith("sudo")
                    success, stdout, stderr = self._execute_single_command(
                        cmd, needs_sudo=needs_sudo
                    )
                    if success:
                        console.print(f"[{GREEN}]{ICON_SUCCESS} {desc} - Passed[/{GREEN}]")
                        if stdout:
                            console.print(
                                Panel(
                                    stdout[:500],
                                    title=f"[{GRAY}]Output[/{GRAY}]",
                                    border_style=GRAY,
                                )
                            )
                    else:
                        console.print(f"[{RED}]{ICON_ERROR} {desc} - Failed[/{RED}]")
                        if stderr:
                            console.print(f"[{GRAY}]{stderr[:200]}[/{GRAY}]")
        except (EOFError, KeyboardInterrupt):
            pass

    def _show_demo(self, demo_type: str, suggestion: dict) -> None:
        """Show demo code/commands for a specific type."""
        console.print()

        if demo_type == "docker":
            image = suggestion.get("image", "your-image")
            console.print(f"[bold {PURPLE_LIGHT}]📝 Docker Usage Examples[/bold {PURPLE_LIGHT}]")
            console.print()
            console.print(f"[{GRAY}]# Run container in foreground:[/{GRAY}]")
            console.print(f"[{GREEN}]docker run -it {image}[/{GREEN}]")
            console.print()
            console.print(f"[{GRAY}]# Run container in background:[/{GRAY}]")
            console.print(f"[{GREEN}]docker run -d --name myapp {image}[/{GREEN}]")
            console.print()
            console.print(f"[{GRAY}]# Run with port mapping:[/{GRAY}]")
            console.print(f"[{GREEN}]docker run -d -p 8080:8080 {image}[/{GREEN}]")
            console.print()
            console.print(f"[{GRAY}]# Run with volume mount:[/{GRAY}]")
            console.print(f"[{GREEN}]docker run -d -v /host/path:/container/path {image}[/{GREEN}]")

        elif demo_type == "ollama":
            console.print(f"[bold {PURPLE_LIGHT}]📝 Ollama API Examples[/bold {PURPLE_LIGHT}]")
            console.print()
            console.print(f"[{GRAY}]# List available models:[/{GRAY}]")
            console.print(f"[{GREEN}]curl http://localhost:11434/api/tags[/{GREEN}]")
            console.print()
            console.print(f"[{GRAY}]# Generate text:[/{GRAY}]")
            console.print(f"""[{GREEN}]curl http://localhost:11434/api/generate -d '{{
  "model": "llama2",
  "prompt": "Hello, how are you?"
}}'[/{GREEN}]""")
            console.print()
            console.print(f"[{GRAY}]# Python example:[/{GRAY}]")
            console.print(f"""[{GREEN}]import requests

response = requests.post('http://localhost:11434/api/generate',
    json={{
        'model': 'llama2',
        'prompt': 'Explain quantum computing in simple terms',
        'stream': False
    }})
print(response.json()['response'])[/{GREEN}]""")

        elif demo_type == "nginx_config":
            console.print(
                f"[bold {PURPLE_LIGHT}]📝 Nginx Configuration Example[/bold {PURPLE_LIGHT}]"
            )
            console.print()
            console.print(f"[{GRAY}]# Create a new site config:[/{GRAY}]")
            console.print(f"[{GREEN}]sudo nano /etc/nginx/sites-available/mysite[/{GREEN}]")
            console.print()
            console.print(f"[{GRAY}]# Example config:[/{GRAY}]")
            console.print(f"""[{GREEN}]server {{
    listen 80;
    server_name example.com;

    location / {{
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }}
}}[/{GREEN}]""")
            console.print()
            console.print(f"[{GRAY}]# Enable the site:[/{GRAY}]")
            console.print(
                f"[{GREEN}]sudo ln -s /etc/nginx/sites-available/mysite /etc/nginx/sites-enabled/[/{GREEN}]"
            )
            console.print(f"[{GREEN}]sudo nginx -t && sudo systemctl reload nginx[/{GREEN}]")

        elif demo_type == "postgres_setup":
            console.print(f"[bold {PURPLE_LIGHT}]📝 PostgreSQL Setup Example[/bold {PURPLE_LIGHT}]")
            console.print()
            console.print("[dim]# Create a new user and database:[/dim]")
            console.print("[{GREEN}]sudo -u postgres createuser --interactive myuser[/{GREEN}]")
            console.print(f"[{GREEN}]sudo -u postgres createdb mydb -O myuser[/{GREEN}]")
            console.print()
            console.print("[dim]# Connect to the database:[/dim]")
            console.print(f"[{GREEN}]psql -U myuser -d mydb[/{GREEN}]")
            console.print()
            console.print("[dim]# Python connection example:[/dim]")
            console.print(f"""[{GREEN}]import psycopg2

conn = psycopg2.connect(
    dbname="mydb",
    user="myuser",
    password="mypassword",
    host="localhost"
)
cursor = conn.cursor()
cursor.execute("SELECT version();")
print(cursor.fetchone())[/{GREEN}]""")

        elif demo_type == "nodejs":
            console.print(f"[bold {PURPLE_LIGHT}]📝 Node.js Example[/bold {PURPLE_LIGHT}]")
            console.print()
            console.print("[dim]# Create a simple Express server:[/dim]")
            console.print(f"""[{GREEN}]// server.js
const express = require('express');
const app = express();

app.get('/', (req, res) => {{
    res.json({{ message: 'Hello from Node.js!' }});
}});

app.listen(3000, () => {{
    console.log('Server running on http://localhost:3000');
}});[/{GREEN}]""")
            console.print()
            console.print("[dim]# Run it:[/dim]")
            console.print(
                f"[{GREEN}]npm init -y && npm install express && node server.js[/{GREEN}]"
            )

        elif demo_type == "python":
            console.print(f"[bold {PURPLE_LIGHT}]📝 Python Example[/bold {PURPLE_LIGHT}]")
            console.print()
            console.print("[dim]# Simple HTTP server:[/dim]")
            console.print(f"[{GREEN}]python3 -m http.server 8000[/{GREEN}]")
            console.print()
            console.print("[dim]# Flask web app:[/dim]")
            console.print(f"""[{GREEN}]from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return {{'message': 'Hello from Python!'}}

if __name__ == '__main__':
    app.run(debug=True)[/{GREEN}]""")

        else:
            console.print(
                "[dim]No specific demo available. Check the documentation for usage examples.[/dim]"
            )

        console.print()

    def _execute_task_node(
        self,
        task: TaskNode,
        run: DoRun,
        original_commands: list[tuple[str, str, list[str]]],
        depth: int = 0,
    ):
        """Execute a single task node with auto-repair capabilities."""
        indent = "  " * depth
        task_num = f"[{task.task_type.value.upper()}]"

        # Check if task was marked as skipped (e.g., using existing resource)
        if task.status == CommandStatus.SKIPPED:
            # Claude-like skipped output
            console.print(
                f"{indent}[{GRAY}]{ICON_INFO}[/{GRAY}] [{PURPLE_LIGHT}]{task.command[:65]}{'...' if len(task.command) > 65 else ''}[/{PURPLE_LIGHT}]"
            )
            console.print(
                f"{indent}  [{GRAY}]↳ Skipped: {task.output or 'Using existing resource'}[/{GRAY}]"
            )

            # Log the skipped command
            cmd_log = CommandLog(
                command=task.command,
                purpose=task.purpose,
                timestamp=datetime.datetime.now().isoformat(),
                status=CommandStatus.SKIPPED,
                output=task.output or "Using existing resource",
            )
            run.commands.append(cmd_log)
            return

        # Claude-like command output
        console.print(
            f"{indent}[bold {PURPLE_LIGHT}]{ICON_SUCCESS}[/bold {PURPLE_LIGHT}] [bold {WHITE}]{task.command[:65]}{'...' if len(task.command) > 65 else ''}[/bold {WHITE}]"
        )
        console.print(f"{indent}  [{GRAY}]↳ {task.purpose}[/{GRAY}]")

        protected_paths = []
        user_query = run.user_query if run else ""
        for cmd, _, protected in original_commands:
            if cmd == task.command:
                protected_paths = protected
                break

        file_check = self._file_analyzer.check_file_exists_and_usefulness(
            task.command, task.purpose, user_query
        )

        if file_check["recommendations"]:
            self._file_analyzer.apply_file_recommendations(file_check["recommendations"])

        task.status = CommandStatus.RUNNING
        start_time = time.time()

        needs_sudo = self._needs_sudo(task.command, protected_paths)
        success, stdout, stderr = self._execute_single_command(task.command, needs_sudo)

        task.output = stdout
        task.error = stderr
        task.duration_seconds = time.time() - start_time

        # Check if command was interrupted by Ctrl+Z/Ctrl+C
        if self._interrupted:
            task.status = CommandStatus.INTERRUPTED
            cmd_log = CommandLog(
                command=task.command,
                purpose=task.purpose,
                timestamp=datetime.datetime.now().isoformat(),
                status=CommandStatus.INTERRUPTED,
                output=stdout,
                error="Command interrupted by user (Ctrl+Z/Ctrl+C)",
                duration_seconds=task.duration_seconds,
            )
            console.print(
                f"{indent}  [{YELLOW}]⚠[/{YELLOW}] [{GRAY}]Interrupted ({task.duration_seconds:.2f}s)[/{GRAY}]"
            )
            run.commands.append(cmd_log)
            return

        cmd_log = CommandLog(
            command=task.command,
            purpose=task.purpose,
            timestamp=datetime.datetime.now().isoformat(),
            status=CommandStatus.SUCCESS if success else CommandStatus.FAILED,
            output=stdout,
            error=stderr,
            duration_seconds=task.duration_seconds,
        )

        if success:
            task.status = CommandStatus.SUCCESS
            # Claude-like success output
            console.print(
                f"{indent}  [{GREEN}]{ICON_SUCCESS}[/{GREEN}] [{GRAY}]Done ({task.duration_seconds:.2f}s)[/{GRAY}]"
            )
            if stdout:
                output_preview = stdout[:100] + ("..." if len(stdout) > 100 else "")
                console.print(f"{indent}  [{GRAY}]{output_preview}[/{GRAY}]")
            console.print()
            run.commands.append(cmd_log)
            return

        task.status = CommandStatus.NEEDS_REPAIR
        diagnosis = self._diagnoser.diagnose_error(task.command, stderr)
        task.failure_reason = diagnosis.get("description", "Unknown error")

        # Claude-like error output
        console.print(
            f"{indent}  [{RED}]{ICON_ERROR}[/{RED}] [bold {RED}]{diagnosis['error_type']}[/bold {RED}]"
        )
        console.print(
            f"{indent}  [{GRAY}]{diagnosis['description'][:80]}{'...' if len(diagnosis['description']) > 80 else ''}[/{GRAY}]"
        )

        # Check if this is a login/credential required error
        if diagnosis.get("category") == "login_required":
            console.print(f"{indent}[{PURPLE_LIGHT}]   🔐 Authentication required[/{PURPLE_LIGHT}]")

            login_success, login_msg = self._login_handler.handle_login(task.command, stderr)

            if login_success:
                console.print(f"{indent}[{GREEN}]   {ICON_SUCCESS} {login_msg}[/{GREEN}]")
                console.print(f"{indent}[{PURPLE_LIGHT}]   Retrying command...[/{PURPLE_LIGHT}]")

                # Retry the command
                needs_sudo = self._needs_sudo(task.command, [])
                success, new_stdout, new_stderr = self._execute_single_command(
                    task.command, needs_sudo
                )

                if success:
                    task.status = CommandStatus.SUCCESS
                    task.reasoning = "Succeeded after authentication"
                    cmd_log.status = CommandStatus.SUCCESS
                    cmd_log.stdout = new_stdout[:500] if new_stdout else ""
                    console.print(
                        f"{indent}[{GREEN}]   {ICON_SUCCESS} Command succeeded after authentication![/{GREEN}]"
                    )
                    run.commands.append(cmd_log)
                    return
                else:
                    # Still failed after login
                    stderr = new_stderr
                    diagnosis = self._diagnoser.diagnose_error(task.command, stderr)
                    console.print(
                        f"{indent}[{YELLOW}]   Command still failed: {stderr[:100]}[/{YELLOW}]"
                    )
            else:
                console.print(f"{indent}[{YELLOW}]   {login_msg}[/{YELLOW}]")

        if diagnosis.get("extracted_path"):
            console.print(f"{indent}[dim]   Path: {diagnosis['extracted_path']}[/dim]")

        # Handle timeout errors specially - don't blindly retry
        if diagnosis.get("category") == "timeout" or "timed out" in stderr.lower():
            console.print(f"{indent}[{YELLOW}]   ⏱️  This operation timed out[/{YELLOW}]")

            # Check if it's a docker pull - those might still be running
            if "docker pull" in task.command.lower():
                console.print(
                    f"{indent}[{PURPLE_LIGHT}]   {ICON_INFO}  Docker pull may still be downloading in background[/{PURPLE_LIGHT}]"
                )
                console.print(
                    f"{indent}[{GRAY}]   Check with: docker images | grep <image-name>[/{GRAY}]"
                )
                console.print(
                    f"{indent}[{GRAY}]   Or retry with: docker pull --timeout=0 <image>[/{GRAY}]"
                )
            elif "apt" in task.command.lower():
                console.print(
                    f"{indent}[{PURPLE_LIGHT}]   {ICON_INFO}  Package installation timed out[/{PURPLE_LIGHT}]"
                )
                console.print(
                    f"{indent}[{GRAY}]   Check apt status: sudo dpkg --configure -a[/{GRAY}]"
                )
                console.print(f"{indent}[{GRAY}]   Then retry the command[/{GRAY}]")
            else:
                console.print(
                    f"{indent}[{PURPLE_LIGHT}]   {ICON_INFO}  You can retry this command manually[/{PURPLE_LIGHT}]"
                )

            # Mark as needing manual intervention, not auto-fix
            task.status = CommandStatus.NEEDS_REPAIR
            task.failure_reason = "Operation timed out - may need manual retry"
            cmd_log.status = CommandStatus.FAILED
            cmd_log.error = stderr
            run.commands.append(cmd_log)
            return

        if task.repair_attempts < task.max_repair_attempts:
            import sys

            task.repair_attempts += 1
            console.print(
                f"{indent}[{PURPLE_LIGHT}]   🔧 Auto-fix attempt {task.repair_attempts}/{task.max_repair_attempts}[/{PURPLE_LIGHT}]"
            )

            # Flush output before auto-fix to ensure clean display after sudo prompts
            sys.stdout.flush()

            fixed, fix_message, fix_commands = self._auto_fixer.auto_fix_error(
                task.command, stderr, diagnosis, max_attempts=3
            )

            for fix_cmd in fix_commands:
                repair_task = self._task_tree.add_repair_task(
                    parent=task,
                    command=fix_cmd,
                    purpose=f"Auto-fix: {diagnosis['error_type']}",
                    reasoning=fix_message,
                )
                repair_task.status = CommandStatus.SUCCESS

            if fixed:
                task.status = CommandStatus.SUCCESS
                task.reasoning = f"Auto-fixed: {fix_message}"
                console.print(f"{indent}[{GREEN}]   {ICON_SUCCESS} {fix_message}[/{GREEN}]")
                cmd_log.status = CommandStatus.SUCCESS
                run.commands.append(cmd_log)
                return
            else:
                console.print(f"{indent}[{YELLOW}]   Auto-fix incomplete: {fix_message}[/{YELLOW}]")

        task.status = CommandStatus.FAILED
        task.reasoning = self._generate_task_failure_reasoning(task, diagnosis)

        error_type = diagnosis.get("error_type", "unknown")

        # Check if this is a "soft failure" that shouldn't warrant manual intervention
        # These are cases where a tool/command simply isn't available and that's OK
        soft_failure_types = {
            "command_not_found",  # Tool not installed
            "not_found",  # File/command doesn't exist
            "no_such_command",
            "unable_to_locate_package",  # Package doesn't exist in repos
        }

        # Also check for patterns in the error message that indicate optional tools
        optional_tool_patterns = [
            "sensors",  # lm-sensors - optional hardware monitoring
            "snap",  # snapd - optional package manager
            "flatpak",  # optional package manager
            "docker",  # optional if not needed
            "podman",  # optional container runtime
            "nmap",  # optional network scanner
            "htop",  # optional system monitor
            "iotop",  # optional I/O monitor
            "iftop",  # optional network monitor
        ]

        cmd_base = task.command.split()[0] if task.command else ""
        is_optional_tool = any(pattern in cmd_base.lower() for pattern in optional_tool_patterns)
        is_soft_failure = error_type in soft_failure_types and is_optional_tool

        if is_soft_failure:
            # Mark as skipped instead of failed - this is an optional tool that's not available
            task.status = CommandStatus.SKIPPED
            task.reasoning = f"Tool '{cmd_base}' not available (optional)"
            console.print(
                f"{indent}[yellow]   ○ Skipped: {cmd_base} not available (optional tool)[/yellow]"
            )
            console.print(
                f"{indent}[dim]   This tool provides additional info but isn't required[/dim]"
            )
            cmd_log.status = CommandStatus.SKIPPED
        else:
            console.print(f"{indent}[red]   ✗ Failed: {diagnosis['description'][:100]}[/red]")
            console.print(f"{indent}[dim]   Reasoning: {task.reasoning}[/dim]")

            # Only offer manual intervention for errors that could actually be fixed manually
            # Don't offer for missing commands/packages that auto-fix couldn't resolve
            should_offer_manual = (diagnosis.get("fix_commands") or stderr) and error_type not in {
                "command_not_found",
                "not_found",
                "unable_to_locate_package",
            }

            if should_offer_manual:
                console.print(f"\n{indent}[yellow]💡 Manual intervention available[/yellow]")

                suggested_cmds = diagnosis.get("fix_commands", [f"sudo {task.command}"])
                console.print(f"{indent}[dim]   Suggested commands:[/dim]")
                for cmd in suggested_cmds[:3]:
                    console.print(f"{indent}[cyan]   $ {cmd}[/cyan]")

                if Confirm.ask(f"{indent}Run manually while Cortex monitors?", default=False):
                    manual_success = self._supervise_manual_intervention_for_task(
                        task, suggested_cmds, run
                    )
                    if manual_success:
                        task.status = CommandStatus.SUCCESS
                        task.reasoning = "Completed via monitored manual intervention"
                        cmd_log.status = CommandStatus.SUCCESS

        cmd_log.status = task.status
        run.commands.append(cmd_log)

    def _supervise_manual_intervention_for_task(
        self,
        task: TaskNode,
        suggested_commands: list[str],
        run: DoRun,
    ) -> bool:
        """Supervise manual intervention for a specific task with terminal monitoring."""
        from rich.panel import Panel
        from rich.prompt import Prompt

        # If no suggested commands provided, use the task command with sudo
        if not suggested_commands:
            if task and task.command:
                # Add sudo if not already present
                cmd = task.command
                if not cmd.strip().startswith("sudo"):
                    cmd = f"sudo {cmd}"
                suggested_commands = [cmd]

        # Claude-like manual intervention UI
        console.print()
        console.print("[bold blue]━━━[/bold blue] [bold]Manual Intervention[/bold]")
        console.print()

        # Show the task context
        if task and task.purpose:
            console.print(f"[bold]Task:[/bold] {task.purpose}")
            console.print()

        console.print("[dim]Run these commands in another terminal:[/dim]")
        console.print()

        # Show commands in a clear box
        if suggested_commands:
            from rich.panel import Panel

            cmd_text = "\n".join(f"  {i}. {cmd}" for i, cmd in enumerate(suggested_commands, 1))
            console.print(
                Panel(
                    cmd_text,
                    title="[bold cyan]📋 Commands to Run[/bold cyan]",
                    border_style="cyan",
                    padding=(0, 1),
                )
            )
        else:
            console.print("  [yellow]⚠ No specific commands - check the task above[/yellow]")

        console.print()

        # Track expected commands for matching
        self._expected_manual_commands = suggested_commands.copy() if suggested_commands else []
        self._completed_manual_commands: list[str] = []

        # Start terminal monitoring with detailed output
        self._terminal_monitor = TerminalMonitor(
            notification_callback=lambda title, msg: self._send_notification(title, msg)
        )
        self._terminal_monitor.start(expected_commands=suggested_commands)

        console.print()
        console.print("[dim]Type 'done' when finished, 'help' for tips, or 'cancel' to abort[/dim]")
        console.print()

        try:
            while True:
                try:
                    user_input = Prompt.ask("[cyan]Status[/cyan]", default="done").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[yellow]Manual intervention cancelled[/yellow]")
                    return False

                # Handle natural language responses
                if user_input in [
                    "done",
                    "finished",
                    "complete",
                    "completed",
                    "success",
                    "worked",
                    "yes",
                    "y",
                ]:
                    # Show observed commands and check for matches
                    observed = self._terminal_monitor.get_observed_commands()
                    matched_commands = []
                    unmatched_commands = []

                    if observed:
                        console.print(f"\n[cyan]📊 Observed {len(observed)} command(s):[/cyan]")
                        for obs in observed[-5:]:
                            obs_cmd = obs["command"]
                            is_matched = False

                            # Check if this matches any expected command
                            for expected in self._expected_manual_commands:
                                if self._commands_match(obs_cmd, expected):
                                    matched_commands.append(obs_cmd)
                                    self._completed_manual_commands.append(expected)
                                    console.print(f"   • {obs_cmd[:60]}... [green]✓[/green]")
                                    is_matched = True
                                    break

                            if not is_matched:
                                unmatched_commands.append(obs_cmd)
                                console.print(f"   • {obs_cmd[:60]}... [yellow]?[/yellow]")

                    # Check if expected commands were actually run
                    if self._expected_manual_commands and not matched_commands:
                        console.print()
                        console.print(
                            "[yellow]⚠ None of the expected commands were detected.[/yellow]"
                        )
                        console.print("[dim]Expected:[/dim]")
                        for cmd in self._expected_manual_commands[:3]:
                            console.print(f"   [cyan]$ {cmd}[/cyan]")
                        console.print()

                        # Send notification with correct commands
                        self._send_notification(
                            "⚠️ Cortex: Expected Commands",
                            f"Run: {self._expected_manual_commands[0][:50]}...",
                        )

                        console.print(
                            "[dim]Type 'done' again to confirm, or run the expected commands first.[/dim]"
                        )
                        continue  # Don't mark as success yet - let user try again

                    # Check if any observed commands had errors (check last few)
                    has_errors = False
                    if observed:
                        for obs in observed[-3:]:
                            if obs.get("has_error") or obs.get("status") == "failed":
                                has_errors = True
                                console.print(
                                    "[yellow]⚠ Some commands may have failed. Please verify.[/yellow]"
                                )
                                break

                    if has_errors and user_input not in ["yes", "y", "worked", "success"]:
                        console.print("[dim]Type 'success' to confirm it worked anyway.[/dim]")
                        continue

                    console.print("[green]✓ Manual step completed successfully[/green]")

                    if self._task_tree:
                        verify_task = self._task_tree.add_verify_task(
                            parent=task,
                            command="# Manual verification",
                            purpose="User confirmed manual intervention success",
                        )
                        verify_task.status = CommandStatus.SUCCESS

                    # Mark matched commands as completed so they're not re-executed
                    if matched_commands:
                        task.manual_commands_completed = matched_commands

                    return True

                elif user_input in ["help", "?", "hint", "tips"]:
                    console.print()
                    console.print("[bold]💡 Manual Intervention Tips:[/bold]")
                    console.print("   • Use [cyan]sudo[/cyan] if you see 'Permission denied'")
                    console.print("   • Use [cyan]sudo su -[/cyan] to become root")
                    console.print("   • Check paths with [cyan]ls -la <path>[/cyan]")
                    console.print("   • Check services: [cyan]systemctl status <service>[/cyan]")
                    console.print("   • View logs: [cyan]journalctl -u <service> -n 50[/cyan]")
                    console.print()

                elif user_input in ["cancel", "abort", "quit", "exit", "no", "n"]:
                    console.print("[yellow]Manual intervention cancelled[/yellow]")
                    return False

                elif user_input in ["failed", "error", "problem", "issue"]:
                    console.print()
                    error_desc = Prompt.ask("[yellow]What error did you encounter?[/yellow]")
                    error_lower = error_desc.lower()

                    # Provide contextual help based on error description
                    if "permission" in error_lower or "denied" in error_lower:
                        console.print("\n[cyan]💡 Try running with sudo:[/cyan]")
                        for cmd in suggested_commands[:2]:
                            if not cmd.startswith("sudo"):
                                console.print(f"   [green]sudo {cmd}[/green]")
                    elif "not found" in error_lower or "no such" in error_lower:
                        console.print("\n[cyan]💡 Check if path/command exists:[/cyan]")
                        console.print("   [green]which <command>[/green]")
                        console.print("   [green]ls -la <path>[/green]")
                    elif "service" in error_lower or "systemctl" in error_lower:
                        console.print("\n[cyan]💡 Service troubleshooting:[/cyan]")
                        console.print("   [green]sudo systemctl status <service>[/green]")
                        console.print("   [green]sudo journalctl -u <service> -n 50[/green]")
                    else:
                        console.print("\n[cyan]💡 General debugging:[/cyan]")
                        console.print("   • Check the error message carefully")
                        console.print("   • Try running with sudo")
                        console.print("   • Check if all required packages are installed")

                    console.print()
                    console.print("[dim]Type 'done' when fixed, or 'cancel' to abort[/dim]")

                else:
                    # Any other input - show status
                    observed = self._terminal_monitor.get_observed_commands()
                    console.print(
                        f"[dim]Still monitoring... ({len(observed)} commands observed)[/dim]"
                    )
                    console.print("[dim]Type 'done' when finished, 'help' for tips[/dim]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Manual intervention cancelled[/yellow]")
            return False
        finally:
            if self._terminal_monitor:
                observed = self._terminal_monitor.stop()
                # Log observed commands to run
                for obs in observed:
                    run.commands.append(
                        CommandLog(
                            command=obs["command"],
                            purpose=f"Manual execution ({obs['source']})",
                            timestamp=obs["timestamp"],
                            status=CommandStatus.SUCCESS,
                        )
                    )
                self._terminal_monitor = None

            # Clear tracking
            self._expected_manual_commands = []

    def _commands_match(self, observed: str, expected: str) -> bool:
        """Check if an observed command matches an expected command.

        Handles variations like:
        - With/without sudo
        - Different whitespace
        - Same command with different args still counts
        """
        # Normalize commands
        obs_normalized = observed.strip().lower()
        exp_normalized = expected.strip().lower()

        # Remove sudo prefix for comparison
        if obs_normalized.startswith("sudo "):
            obs_normalized = obs_normalized[5:].strip()
        if exp_normalized.startswith("sudo "):
            exp_normalized = exp_normalized[5:].strip()

        # Exact match
        if obs_normalized == exp_normalized:
            return True

        obs_parts = obs_normalized.split()
        exp_parts = exp_normalized.split()

        # Check for service management commands first (need full match including service name)
        service_commands = ["systemctl", "service"]
        for svc_cmd in service_commands:
            if svc_cmd in obs_normalized and svc_cmd in exp_normalized:
                # Extract action and service name
                obs_action = None
                exp_action = None
                obs_service = None
                exp_service = None

                for i, part in enumerate(obs_parts):
                    if part in [
                        "restart",
                        "start",
                        "stop",
                        "reload",
                        "status",
                        "enable",
                        "disable",
                    ]:
                        obs_action = part
                        # Service name is usually the next word
                        if i + 1 < len(obs_parts):
                            obs_service = obs_parts[i + 1]
                        break

                for i, part in enumerate(exp_parts):
                    if part in [
                        "restart",
                        "start",
                        "stop",
                        "reload",
                        "status",
                        "enable",
                        "disable",
                    ]:
                        exp_action = part
                        if i + 1 < len(exp_parts):
                            exp_service = exp_parts[i + 1]
                        break

                if obs_action and exp_action and obs_service and exp_service:
                    if obs_action == exp_action and obs_service == exp_service:
                        return True
                    else:
                        return False  # Different action or service

        # For non-service commands, check if first 2-3 words match
        if len(obs_parts) >= 2 and len(exp_parts) >= 2:
            # Skip if either is a service command (handled above)
            if obs_parts[0] not in ["systemctl", "service"] and exp_parts[0] not in [
                "systemctl",
                "service",
            ]:
                # Compare first two words (command and subcommand)
                if obs_parts[:2] == exp_parts[:2]:
                    return True

        return False

    def get_completed_manual_commands(self) -> list[str]:
        """Get list of commands completed during manual intervention."""
        return getattr(self, "_completed_manual_commands", [])

    def _generate_task_failure_reasoning(
        self,
        task: TaskNode,
        diagnosis: dict,
    ) -> str:
        """Generate detailed reasoning for why a task failed."""
        parts = []

        parts.append(f"Error: {diagnosis.get('error_type', 'unknown')}")

        if task.repair_attempts > 0:
            parts.append(f"Repair attempts: {task.repair_attempts} (all failed)")

        if diagnosis.get("extracted_path"):
            parts.append(f"Problem path: {diagnosis['extracted_path']}")

        error_type = diagnosis.get("error_type", "")
        if "permission" in error_type.lower():
            parts.append("Root cause: Insufficient file system permissions")
        elif "not_found" in error_type.lower():
            parts.append("Root cause: Required file or directory does not exist")
        elif "service" in error_type.lower():
            parts.append("Root cause: System service issue")

        if diagnosis.get("fix_commands"):
            parts.append(f"Suggested fix: {diagnosis['fix_commands'][0][:50]}...")

        return " | ".join(parts)

    def _generate_tree_summary(self, run: DoRun) -> str:
        """Generate a summary from the task tree execution."""
        if not self._task_tree:
            return self._generate_summary(run)

        summary = self._task_tree.get_summary()

        total = sum(summary.values())
        success = summary.get("success", 0)
        failed = summary.get("failed", 0)
        repaired = summary.get("needs_repair", 0)

        parts = [
            f"Total tasks: {total}",
            f"Successful: {success}",
            f"Failed: {failed}",
        ]

        if repaired > 0:
            parts.append(f"Repair attempted: {repaired}")

        if self._permission_requests_count > 1:
            parts.append(f"Permission requests: {self._permission_requests_count}")

        return " | ".join(parts)

    def provide_manual_instructions(
        self,
        commands: list[tuple[str, str, list[str]]],
        user_query: str,
    ) -> DoRun:
        """Provide instructions for manual execution and monitor progress."""
        run = DoRun(
            run_id=self.db._generate_run_id(),
            summary="",
            mode=RunMode.USER_MANUAL,
            user_query=user_query,
            started_at=datetime.datetime.now().isoformat(),
            session_id=self.current_session_id or "",
        )
        self.current_run = run

        console.print()
        console.print(
            Panel(
                "[bold cyan]📋 Manual Execution Instructions[/bold cyan]",
                expand=False,
            )
        )
        console.print()

        cwd = os.getcwd()
        console.print("[bold]1. Open a new terminal and navigate to:[/bold]")
        console.print(f"   [cyan]cd {cwd}[/cyan]")
        console.print()

        console.print("[bold]2. Execute the following commands in order:[/bold]")
        console.print()

        for i, (cmd, purpose, protected) in enumerate(commands, 1):
            console.print(f"   [bold yellow]Step {i}:[/bold yellow] {purpose}")
            needs_sudo = self._needs_sudo(cmd, protected)

            if protected:
                console.print(f"   [red]⚠️  Accesses protected paths: {', '.join(protected)}[/red]")

            if needs_sudo and not cmd.strip().startswith("sudo"):
                console.print(f"   [cyan]sudo {cmd}[/cyan]")
            else:
                console.print(f"   [cyan]{cmd}[/cyan]")
            console.print()

            run.commands.append(
                CommandLog(
                    command=cmd,
                    purpose=purpose,
                    timestamp=datetime.datetime.now().isoformat(),
                    status=CommandStatus.PENDING,
                )
            )

        console.print("[bold]3. Once done, return to this terminal and press Enter.[/bold]")
        console.print()

        monitor = TerminalMonitor(
            notification_callback=lambda title, msg: self._send_notification(title, msg, "normal")
        )

        expected_commands = [cmd for cmd, _, _ in commands]
        monitor.start_monitoring(expected_commands)

        console.print("[dim]🔍 Monitoring terminal activity... (press Enter when done)[/dim]")

        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass

        observed = monitor.stop_monitoring()

        # Add observed commands to the run
        for obs in observed:
            run.commands.append(
                CommandLog(
                    command=obs["command"],
                    purpose="User-executed command",
                    timestamp=obs["timestamp"],
                    status=CommandStatus.SUCCESS,
                )
            )

        run.completed_at = datetime.datetime.now().isoformat()
        run.summary = self._generate_summary(run)

        self.db.save_run(run)

        # Generate LLM summary/answer
        llm_answer = self._generate_llm_answer(run, user_query)

        # Print condensed execution summary with answer
        self._print_execution_summary(run, answer=llm_answer)

        console.print()
        console.print(f"[dim]Run ID: {run.run_id}[/dim]")

        return run

    def _generate_summary(self, run: DoRun) -> str:
        """Generate a summary of what was done in the run."""
        successful = sum(1 for c in run.commands if c.status == CommandStatus.SUCCESS)
        failed = sum(1 for c in run.commands if c.status == CommandStatus.FAILED)

        mode_str = "automated" if run.mode == RunMode.CORTEX_EXEC else "manual"

        if failed == 0:
            return f"Successfully executed {successful} commands ({mode_str}) for: {run.user_query[:50]}"
        else:
            return f"Executed {successful} commands with {failed} failures ({mode_str}) for: {run.user_query[:50]}"

    def _generate_llm_answer(self, run: DoRun, user_query: str) -> str | None:
        """Generate an LLM-based answer/summary after command execution."""
        if not self.llm_callback:
            return None

        # Collect command outputs
        command_results = []
        for cmd in run.commands:
            status = (
                "✓"
                if cmd.status == CommandStatus.SUCCESS
                else "✗" if cmd.status == CommandStatus.FAILED else "○"
            )
            result = {
                "command": cmd.command,
                "purpose": cmd.purpose,
                "status": status,
                "output": (cmd.output[:500] if cmd.output else "")[:500],  # Limit output size
            }
            if cmd.error:
                result["error"] = cmd.error[:200]
            command_results.append(result)

        # Build prompt for LLM
        prompt = f"""The user asked: "{user_query}"

The following commands were executed:
"""
        for i, result in enumerate(command_results, 1):
            prompt += f"\n{i}. [{result['status']}] {result['command']}"
            prompt += f"\n   Purpose: {result['purpose']}"
            if result.get("output"):
                # Only include meaningful output, not empty or whitespace-only
                output_preview = result["output"].strip()[:200]
                if output_preview:
                    prompt += f"\n   Output: {output_preview}"
            if result.get("error"):
                prompt += f"\n   Error: {result['error']}"

        prompt += """

Based on the above execution results, provide a helpful summary/answer for the user.
Focus on:
1. What was accomplished
2. Any issues encountered and their impact
3. Key findings or results from the commands
4. Any recommendations for next steps

Keep the response concise (2-4 paragraphs max). Do NOT include JSON in your response.
Respond directly with the answer text only."""

        try:
            from rich.console import Console
            from rich.status import Status

            console = Console()
            with Status("[cyan]Generating summary...[/cyan]", spinner="dots"):
                result = self.llm_callback(prompt)

            if result:
                # Handle different response formats
                if isinstance(result, dict):
                    # Extract answer from various possible keys
                    answer = (
                        result.get("answer") or result.get("response") or result.get("text") or ""
                    )
                    if not answer and "reasoning" in result:
                        answer = result.get("reasoning", "")
                elif isinstance(result, str):
                    answer = result
                else:
                    return None

                # Clean the answer
                answer = answer.strip()

                # Filter out JSON-like responses
                if answer.startswith("{") or answer.startswith("["):
                    return None

                return answer if answer else None
        except Exception as e:
            # Silently fail - summary is optional
            import logging

            logging.debug(f"LLM summary generation failed: {e}")
            return None

        return None

    def _print_execution_summary(self, run: DoRun, answer: str | None = None):
        """Print a condensed execution summary with improved visual design."""
        from rich import box
        from rich.panel import Panel
        from rich.text import Text

        # Count statuses
        successful = [c for c in run.commands if c.status == CommandStatus.SUCCESS]
        failed = [c for c in run.commands if c.status == CommandStatus.FAILED]
        skipped = [c for c in run.commands if c.status == CommandStatus.SKIPPED]
        interrupted = [c for c in run.commands if c.status == CommandStatus.INTERRUPTED]

        total = len(run.commands)

        # Build status header
        console.print()

        # Create a status bar
        if total > 0:
            status_text = Text()
            status_text.append("  ")
            if successful:
                status_text.append(f"✓ {len(successful)} ", style="bold green")
            if failed:
                status_text.append(f"✗ {len(failed)} ", style="bold red")
            if skipped:
                status_text.append(f"○ {len(skipped)} ", style="bold yellow")
            if interrupted:
                status_text.append(f"⚠ {len(interrupted)} ", style="bold yellow")

            # Calculate success rate
            success_rate = (len(successful) / total * 100) if total > 0 else 0
            status_text.append(f"  ({success_rate:.0f}% success)", style="dim")

            console.print(
                Panel(
                    status_text,
                    title="[bold white on blue] 📊 Execution Status [/bold white on blue]",
                    title_align="left",
                    border_style="blue",
                    padding=(0, 1),
                    expand=False,
                )
            )

        # Create a table for detailed results
        if successful or failed or skipped:
            result_table = Table(
                show_header=True,
                header_style="bold",
                box=box.SIMPLE,
                padding=(0, 1),
                expand=True,
            )
            result_table.add_column("Status", width=8, justify="center")
            result_table.add_column("Action", style="white")

            # Add successful commands
            for cmd in successful[:4]:
                purpose = cmd.purpose[:60] + "..." if len(cmd.purpose) > 60 else cmd.purpose
                result_table.add_row("[green]✓ Done[/green]", purpose)
            if len(successful) > 4:
                result_table.add_row(
                    "[dim]...[/dim]", f"[dim]and {len(successful) - 4} more completed[/dim]"
                )

            # Add failed commands
            for cmd in failed[:2]:
                error_short = (
                    (cmd.error[:40] + "...")
                    if cmd.error and len(cmd.error) > 40
                    else (cmd.error or "Unknown")
                )
                result_table.add_row(
                    "[red]✗ Failed[/red]", f"{cmd.command[:30]}... - {error_short}"
                )

            # Add skipped commands
            for cmd in skipped[:2]:
                purpose = cmd.purpose[:50] + "..." if len(cmd.purpose) > 50 else cmd.purpose
                result_table.add_row("[yellow]○ Skip[/yellow]", purpose)

            console.print(
                Panel(
                    result_table,
                    title="[bold] 📋 Details [/bold]",
                    title_align="left",
                    border_style="dim",
                    padding=(0, 0),
                )
            )

        # Answer section (for questions) - make it prominent
        if answer:
            # Clean the answer - remove any JSON-like content that might have leaked
            clean_answer = answer
            if clean_answer.startswith("{") or '{"' in clean_answer[:50]:
                # Looks like JSON leaked through, try to extract readable parts
                import re

                # Try to extract just the answer field if present
                answer_match = re.search(r'"answer"\s*:\s*"([^"]*)"', clean_answer)
                if answer_match:
                    clean_answer = answer_match.group(1)

            # Truncate very long answers
            if len(clean_answer) > 500:
                display_answer = clean_answer[:500] + "\n\n[dim]... (truncated)[/dim]"
            else:
                display_answer = clean_answer

            console.print(
                Panel(
                    display_answer,
                    title="[bold white on green] 💡 Answer [/bold white on green]",
                    title_align="left",
                    border_style="green",
                    padding=(1, 2),
                )
            )

    def get_run_history(self, limit: int = 20) -> list[DoRun]:
        """Get recent do run history."""
        return self.db.get_recent_runs(limit)

    def get_run(self, run_id: str) -> DoRun | None:
        """Get a specific run by ID."""
        return self.db.get_run(run_id)

    # Expose diagnosis and auto-fix methods for external use
    def _diagnose_error(self, cmd: str, stderr: str) -> dict[str, Any]:
        """Diagnose a command failure."""
        return self._diagnoser.diagnose_error(cmd, stderr)

    def _auto_fix_error(
        self,
        cmd: str,
        stderr: str,
        diagnosis: dict[str, Any],
        max_attempts: int = 5,
    ) -> tuple[bool, str, list[str]]:
        """Auto-fix an error."""
        return self._auto_fixer.auto_fix_error(cmd, stderr, diagnosis, max_attempts)

    def _check_for_conflicts(self, cmd: str, purpose: str) -> dict[str, Any]:
        """Check for conflicts."""
        return self._conflict_detector.check_for_conflicts(cmd, purpose)

    def _run_verification_tests(
        self,
        commands_executed: list[CommandLog],
        user_query: str,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Run verification tests."""
        return self._verification_runner.run_verification_tests(commands_executed, user_query)

    def _check_file_exists_and_usefulness(
        self,
        cmd: str,
        purpose: str,
        user_query: str,
    ) -> dict[str, Any]:
        """Check file existence and usefulness."""
        return self._file_analyzer.check_file_exists_and_usefulness(cmd, purpose, user_query)

    def _analyze_file_usefulness(
        self,
        content: str,
        purpose: str,
        user_query: str,
    ) -> dict[str, Any]:
        """Analyze file usefulness."""
        return self._file_analyzer.analyze_file_usefulness(content, purpose, user_query)


def setup_cortex_user() -> bool:
    """Setup the cortex user if it doesn't exist."""
    handler = DoHandler()
    return handler.setup_cortex_user()


def get_do_handler() -> DoHandler:
    """Get a DoHandler instance."""
    return DoHandler()
