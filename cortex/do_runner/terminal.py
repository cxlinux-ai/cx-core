"""Terminal monitoring for the manual execution flow."""

import datetime
import json
import os
import re
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()

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
ICON_MONITOR = "◉"
ICON_SUCCESS = "●"
ICON_ERROR = "●"
ICON_INFO = "○"
ICON_PENDING = "◐"
ICON_ARROW = "→"


class ClaudeLLM:
    """Claude LLM client using the LLMRouter for intelligent error analysis."""

    def __init__(self):
        self._router = None
        self._available: bool | None = None

    def _get_router(self):
        """Lazy initialize the router."""
        if self._router is None:
            try:
                from cortex.llm_router import LLMRouter, TaskType

                self._router = LLMRouter()
                self._task_type = TaskType
            except Exception:
                self._router = False  # Mark as failed
        return self._router if self._router else None

    def is_available(self) -> bool:
        """Check if Claude API is available."""
        if self._available is not None:
            return self._available

        router = self._get_router()
        self._available = router is not None and router.claude_client is not None
        return self._available

    def analyze_error(self, command: str, error_output: str, max_tokens: int = 300) -> dict | None:
        """Analyze an error using Claude and return diagnosis with solution."""
        router = self._get_router()
        if not router:
            return None

        try:
            messages = [
                {
                    "role": "system",
                    "content": """You are a Linux system debugging expert. Analyze the command error and provide:
1. Root cause (1 sentence)
2. Solution (1-2 specific commands to fix it)

IMPORTANT: Do NOT suggest commands that require sudo/root privileges, as they cannot be auto-executed.
Only suggest commands that can run as a regular user, such as:
- Checking status (docker ps, systemctl status --user, etc.)
- User-level config fixes
- Environment variable exports
- File operations in user directories

If the ONLY fix requires sudo, explain what needs to be done but prefix the command with "# MANUAL: "

Be concise. Output format:
CAUSE: <one sentence explanation>
FIX: <command 1>
FIX: <command 2 if needed>""",
                },
                {"role": "user", "content": f"Command: {command}\n\nError:\n{error_output[:500]}"},
            ]

            response = router.complete(
                messages=messages,
                task_type=self._task_type.ERROR_DEBUGGING,
                max_tokens=max_tokens,
                temperature=0.3,
            )

            # Parse response
            content = response.content
            result = {"cause": "", "fixes": [], "raw": content}

            for line in content.split("\n"):
                line = line.strip()
                if line.upper().startswith("CAUSE:"):
                    result["cause"] = line[6:].strip()
                elif line.upper().startswith("FIX:"):
                    fix = line[4:].strip()
                    if fix and not fix.startswith("#"):
                        result["fixes"].append(fix)

            return result

        except Exception as e:
            console.print(f"[{GRAY}]Claude analysis error: {e}[/{GRAY}]")
            return None


class LocalLLM:
    """Local LLM client using Ollama with Mistral (fallback)."""

    def __init__(self, model: str = "mistral"):
        self.model = model
        self._available: bool | None = None

    def is_available(self) -> bool:
        """Check if Ollama with the model is available."""
        if self._available is not None:
            return self._available

        try:
            result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
            self._available = result.returncode == 0 and self.model in result.stdout
            if not self._available:
                # Try to check if ollama is running at least
                result = subprocess.run(
                    ["curl", "-s", "http://localhost:11434/api/tags"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self._available = self.model in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            self._available = False

        return self._available

    def analyze(self, prompt: str, max_tokens: int = 200, timeout: int = 10) -> str | None:
        """Call the local LLM for analysis."""
        if not self.is_available():
            return None

        try:
            import urllib.error
            import urllib.request

            # Use Ollama API directly via urllib (faster than curl subprocess)
            data = json.dumps(
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": 0.3,
                    },
                }
            ).encode("utf-8")

            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result.get("response", "").strip()

        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, Exception):
            pass

        return None


class TerminalMonitor:
    """
    Monitors terminal commands for the manual execution flow.

    Monitors ALL terminal sources by default:
    - Bash history file (~/.bash_history)
    - Zsh history file (~/.zsh_history)
    - Fish history file (~/.local/share/fish/fish_history)
    - ALL Cursor terminal files (all projects)
    - External terminal output files
    """

    def __init__(
        self, notification_callback: Callable[[str, str], None] | None = None, use_llm: bool = True
    ):
        self.notification_callback = notification_callback
        self._monitoring = False
        self._monitor_thread: threading.Thread | None = None
        self._commands_observed: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._cursor_terminals_dirs: list[Path] = []
        self._expected_commands: list[str] = []
        self._shell_history_files: list[Path] = []
        self._output_buffer: list[dict[str, Any]] = []  # Buffer for terminal output
        self._show_live_output = True  # Whether to print live output

        # Claude LLM for intelligent error analysis (primary)
        self._use_llm = use_llm
        self._claude: ClaudeLLM | None = None
        self._llm: LocalLLM | None = None  # Fallback
        if use_llm:
            self._claude = ClaudeLLM()
            self._llm = LocalLLM(model="mistral")  # Keep as fallback

        # Context for LLM
        self._session_context: list[str] = []  # Recent commands for context

        # Use existing auto-fix architecture
        from cortex.do_runner.diagnosis import AutoFixer, ErrorDiagnoser

        self._diagnoser = ErrorDiagnoser()
        self._auto_fixer = AutoFixer(llm_callback=self._llm_for_autofix if use_llm else None)

        # Notification manager for desktop notifications
        self.notifier = self._create_notifier()

        # Discover all terminal sources
        self._discover_terminal_sources()

    def _create_notifier(self):
        """Create notification manager for desktop notifications."""
        try:
            from cortex.notification_manager import NotificationManager

            return NotificationManager()
        except ImportError:
            return None

    def _llm_for_autofix(self, prompt: str) -> dict:
        """LLM callback for the AutoFixer."""
        if not self._llm or not self._llm.is_available():
            return {}

        result = self._llm.analyze(prompt, max_tokens=200, timeout=15)
        if result:
            return {"response": result, "fix_commands": []}
        return {}

    def _discover_terminal_sources(self, verbose: bool = False):
        """Discover all available terminal sources to monitor."""
        home = Path.home()

        # Reset lists
        self._shell_history_files = []
        self._cursor_terminals_dirs = []

        # Shell history files
        shell_histories = [
            home / ".bash_history",  # Bash
            home / ".zsh_history",  # Zsh
            home / ".history",  # Generic
            home / ".sh_history",  # Sh
            home / ".local" / "share" / "fish" / "fish_history",  # Fish
            home / ".ksh_history",  # Korn shell
            home / ".tcsh_history",  # Tcsh
        ]

        for hist_file in shell_histories:
            if hist_file.exists():
                self._shell_history_files.append(hist_file)
                if verbose:
                    console.print(f"[{GRAY}]{ICON_INFO} Monitoring: {hist_file}[/{GRAY}]")

        # Find ALL Cursor terminal directories (all projects)
        cursor_base = home / ".cursor" / "projects"
        if cursor_base.exists():
            for project_dir in cursor_base.iterdir():
                if project_dir.is_dir():
                    terminals_path = project_dir / "terminals"
                    if terminals_path.exists():
                        self._cursor_terminals_dirs.append(terminals_path)
                        if verbose:
                            console.print(
                                f"[{GRAY}]{ICON_INFO} Monitoring Cursor terminals: {terminals_path.parent.name}[/{GRAY}]"
                            )

        # Also check for tmux/screen panes
        self._tmux_available = self._check_command_exists("tmux")
        self._screen_available = self._check_command_exists("screen")

        if verbose:
            if self._tmux_available:
                console.print(
                    f"[{GRAY}]{ICON_INFO} Tmux detected - will monitor tmux panes[/{GRAY}]"
                )
            if self._screen_available:
                console.print(
                    f"[{GRAY}]{ICON_INFO} Screen detected - will monitor screen sessions[/{GRAY}]"
                )

    def _check_command_exists(self, cmd: str) -> bool:
        """Check if a command exists in PATH."""
        import shutil

        return shutil.which(cmd) is not None

    def start(
        self,
        verbose: bool = True,
        show_live: bool = True,
        expected_commands: list[str] | None = None,
    ):
        """Start monitoring terminal for commands."""
        self.start_monitoring(
            expected_commands=expected_commands, verbose=verbose, show_live=show_live
        )

    def _is_service_running(self) -> bool:
        """Check if the Cortex Watch systemd service is running."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", "cortex-watch.service"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return result.stdout.strip() == "active"
        except Exception:
            return False

    def start_monitoring(
        self,
        expected_commands: list[str] | None = None,
        verbose: bool = True,
        show_live: bool = True,
        clear_old_logs: bool = True,
    ):
        """Start monitoring ALL terminal sources for commands."""
        self._monitoring = True
        self._expected_commands = expected_commands or []
        self._show_live_output = show_live
        self._output_buffer = []
        self._session_context = []

        # Mark this terminal as the Cortex terminal so watch hook won't log its commands
        os.environ["CORTEX_TERMINAL"] = "1"

        # Record the monitoring start time to filter out old commands
        self._monitoring_start_time = datetime.datetime.now()

        # Always clear old watch log to start fresh - this prevents reading old session commands
        watch_file = self.get_watch_file_path()
        if watch_file.exists():
            # Truncate the file to clear old commands from previous sessions
            watch_file.write_text("")

        # Also record starting positions for bash/zsh history files
        self._history_start_positions: dict[str, int] = {}
        for hist_file in [Path.home() / ".bash_history", Path.home() / ".zsh_history"]:
            if hist_file.exists():
                self._history_start_positions[str(hist_file)] = hist_file.stat().st_size

        # Re-discover sources in case new terminals opened
        self._discover_terminal_sources(verbose=verbose)

        # Check LLM availability
        llm_status = ""
        if self._llm and self._use_llm:
            if self._llm.is_available():
                llm_status = (
                    f"\n[{GREEN}]{ICON_SUCCESS} AI Analysis: Mistral (local) - Active[/{GREEN}]"
                )
            else:
                llm_status = f"\n[{YELLOW}]{ICON_PENDING} AI Analysis: Mistral not available (install with: ollama pull mistral)[/{YELLOW}]"

        if verbose:
            from rich.panel import Panel

            watch_file = self.get_watch_file_path()
            source_file = Path.home() / ".cortex" / "watch_hook.sh"

            # Check if systemd service is running (best option)
            service_running = self._is_service_running()

            # Check if auto-watch is already set up
            bashrc = Path.home() / ".bashrc"
            hook_installed = False
            if bashrc.exists() and "Cortex Terminal Watch Hook" in bashrc.read_text():
                hook_installed = True

            # If service is running, we don't need the hook
            if service_running:
                setup_info = (
                    f"[{GREEN}]{ICON_SUCCESS} Cortex Watch Service is running[/{GREEN}]\n"
                    f"[{GRAY}]All terminal activity is being monitored automatically![/{GRAY}]"
                )
            else:
                # Not using the service, need to set up hooks
                if not hook_installed:
                    # Auto-install the hook to .bashrc
                    self.setup_auto_watch(permanent=True)
                    hook_installed = True  # Now installed

                # Ensure source file exists
                self.setup_auto_watch(permanent=False)

                # Create a super short activation command
                short_cmd = f"source {source_file}"

                # Try to copy to clipboard
                clipboard_copied = False
                try:
                    # Try xclip first, then xsel
                    for clip_cmd in [
                        ["xclip", "-selection", "clipboard"],
                        ["xsel", "--clipboard", "--input"],
                    ]:
                        try:
                            proc = subprocess.run(
                                clip_cmd, input=short_cmd.encode(), capture_output=True, timeout=2
                            )
                            if proc.returncode == 0:
                                clipboard_copied = True
                                break
                        except (FileNotFoundError, subprocess.TimeoutExpired):
                            continue
                except Exception:
                    pass

                if hook_installed:
                    clipboard_msg = (
                        f"[{GREEN}]📋 Copied to clipboard![/{GREEN}] " if clipboard_copied else ""
                    )
                    setup_info = (
                        f"[{GREEN}]{ICON_SUCCESS} Terminal watch hook is installed in .bashrc[/{GREEN}]\n"
                        f"[{GRAY}](New terminals will auto-activate)[/{GRAY}]\n\n"
                        f"[bold {YELLOW}]For EXISTING terminals, paste this:[/bold {YELLOW}]\n"
                        f"[bold {PURPLE_LIGHT}]{short_cmd}[/bold {PURPLE_LIGHT}]\n"
                        f"{clipboard_msg}\n"
                        f"[{GRAY}]Or type [/{GRAY}][{GREEN}]cortex watch --install --service[/{GREEN}][{GRAY}] for automatic monitoring![/{GRAY}]"
                    )

                    # Send desktop notification with the command
                    try:
                        msg = f"Paste in your OTHER terminal:\n\n{short_cmd}"
                        if clipboard_copied:
                            msg += "\n\n(Already copied to clipboard!)"
                        subprocess.run(
                            [
                                "notify-send",
                                "--urgency=critical",
                                "--icon=dialog-warning",
                                "--expire-time=15000",
                                "⚠️ Cortex: Activate Terminal Watching",
                                msg,
                            ],
                            capture_output=True,
                            timeout=2,
                        )
                    except Exception:
                        pass
                else:
                    setup_info = (
                        f"[bold {YELLOW}]⚠ For real-time monitoring in OTHER terminals:[/bold {YELLOW}]\n\n"
                        f"[bold {PURPLE_LIGHT}]{short_cmd}[/bold {PURPLE_LIGHT}]\n\n"
                        f"[{GRAY}]Or install the watch service: [/{GRAY}][{GREEN}]cortex watch --install --service[/{GREEN}]"
                    )

            console.print()
            console.print(
                Panel(
                    f"[bold {PURPLE_LIGHT}]{ICON_MONITOR} Terminal Monitoring Active[/bold {PURPLE_LIGHT}]\n\n"
                    f"[{WHITE}]Watching {len(self._shell_history_files)} shell history files\n"
                    f"Watching {len(self._cursor_terminals_dirs)} Cursor terminal directories\n"
                    + ("Watching Tmux panes\n" if self._tmux_available else "")
                    + llm_status
                    + "\n\n"
                    + setup_info
                    + f"[/{WHITE}]",
                    title=f"[bold {PURPLE}]Live Terminal Monitor[/bold {PURPLE}]",
                    border_style=PURPLE,
                )
            )
            console.print()
            console.print(f"[{GRAY}]─" * 60 + f"[/{GRAY}]")
            console.print(f"[bold {WHITE}]📡 Live Terminal Feed:[/bold {WHITE}]")
            console.print(f"[{GRAY}]─" * 60 + f"[/{GRAY}]")
            console.print(f"[{GRAY}]Waiting for commands from other terminals...[/{GRAY}]")
            console.print()

        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self) -> list[dict[str, Any]]:
        """Stop monitoring and return observed commands."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None

        with self._lock:
            result = list(self._commands_observed)
            return result

    def stop(self) -> list[dict[str, Any]]:
        """Stop monitoring terminal."""
        return self.stop_monitoring()

    def get_observed_commands(self) -> list[dict[str, Any]]:
        """Get all observed commands so far."""
        with self._lock:
            return list(self._commands_observed)

    def test_monitoring(self):
        """Test that monitoring is working by showing what files are being watched."""
        console.print(
            f"\n[bold {PURPLE_LIGHT}]{ICON_MONITOR} Terminal Monitoring Test[/bold {PURPLE_LIGHT}]\n"
        )

        # Check shell history files
        console.print(f"[bold {WHITE}]Shell History Files:[/bold {WHITE}]")
        for hist_file in self._shell_history_files:
            exists = hist_file.exists()
            size = hist_file.stat().st_size if exists else 0
            status = (
                f"[{GREEN}]{ICON_SUCCESS}[/{GREEN}]" if exists else f"[{RED}]{ICON_ERROR}[/{RED}]"
            )
            console.print(f"  {status} [{WHITE}]{hist_file} ({size} bytes)[/{WHITE}]")

        # Check Cursor terminal directories
        console.print(f"\n[bold {WHITE}]Cursor Terminal Directories:[/bold {WHITE}]")
        for terminals_dir in self._cursor_terminals_dirs:
            if terminals_dir.exists():
                files = list(terminals_dir.glob("*.txt"))
                console.print(
                    f"  [{GREEN}]{ICON_SUCCESS}[/{GREEN}] [{WHITE}]{terminals_dir} ({len(files)} files)[/{WHITE}]"
                )
                for f in files[:5]:  # Show first 5
                    size = f.stat().st_size
                    console.print(f"      [{GRAY}]- {f.name} ({size} bytes)[/{GRAY}]")
                if len(files) > 5:
                    console.print(f"      [{GRAY}]... and {len(files) - 5} more[/{GRAY}]")
            else:
                console.print(
                    f"  [{RED}]{ICON_ERROR}[/{RED}] [{WHITE}]{terminals_dir} (not found)[/{WHITE}]"
                )

        # Check tmux
        console.print(f"\n[bold {WHITE}]Other Sources:[/bold {WHITE}]")
        console.print(
            f"  [{WHITE}]Tmux: [/{WHITE}]{f'[{GREEN}]{ICON_SUCCESS} available[/{GREEN}]' if self._tmux_available else f'[{GRAY}]not available[/{GRAY}]'}"
        )
        console.print(
            f"  [{WHITE}]Screen: [/{WHITE}]{f'[{GREEN}]{ICON_SUCCESS} available[/{GREEN}]' if self._screen_available else f'[{GRAY}]not available[/{GRAY}]'}"
        )

        console.print(
            f"\n[{YELLOW}]Tip: For bash history to update in real-time, run in your terminal:[/{YELLOW}]"
        )
        console.print(f"[{GREEN}]export PROMPT_COMMAND='history -a'[/{GREEN}]")
        console.print()

    def inject_test_command(self, command: str, source: str = "test"):
        """Inject a test command to verify the display is working."""
        self._process_observed_command(command, source)

    def get_watch_file_path(self) -> Path:
        """Get the path to the cortex watch file."""
        return Path.home() / ".cortex" / "terminal_watch.log"

    def setup_terminal_hook(self) -> str:
        """Generate a bash command to set up real-time terminal watching.

        Returns the command the user should run in their terminal.
        """
        watch_file = self.get_watch_file_path()
        watch_file.parent.mkdir(parents=True, exist_ok=True)

        # Create a bash function that logs commands
        hook_command = f"""
# Cortex Terminal Hook - paste this in your terminal:
export CORTEX_WATCH_FILE="{watch_file}"
export PROMPT_COMMAND='history -a; echo "$(date +%H:%M:%S) $(history 1 | sed "s/^[ ]*[0-9]*[ ]*//")" >> "$CORTEX_WATCH_FILE"'
echo "✓ Cortex is now watching this terminal"
"""
        return hook_command.strip()

    def print_setup_instructions(self):
        """Print instructions for setting up real-time terminal watching."""
        from rich.panel import Panel

        watch_file = self.get_watch_file_path()

        console.print()
        console.print(
            Panel(
                f"[bold {YELLOW}]⚠ For real-time terminal monitoring, run this in your OTHER terminal:[/bold {YELLOW}]\n\n"
                f'[{GREEN}]export PROMPT_COMMAND=\'history -a; echo "$(date +%H:%M:%S) $(history 1 | sed "s/^[ ]*[0-9]*[ ]*//")" >> {watch_file}\'[/{GREEN}]\n\n'
                f"[{GRAY}]This makes bash write commands immediately so Cortex can see them.[/{GRAY}]",
                title=f"[{PURPLE_LIGHT}]Setup Required[/{PURPLE_LIGHT}]",
                border_style=PURPLE,
            )
        )
        console.print()

    def setup_system_wide_watch(self) -> tuple[bool, str]:
        """
        Install the terminal watch hook system-wide in /etc/profile.d/.

        This makes the hook active for ALL users and ALL new terminals automatically.
        Requires sudo.

        Returns:
            Tuple of (success, message)
        """
        import subprocess

        watch_file = self.get_watch_file_path()
        profile_script = "/etc/profile.d/cortex-watch.sh"

        # The system-wide hook script
        hook_content = """#!/bin/bash
# Cortex Terminal Watch Hook - System Wide
# Installed by: cortex do watch --system
# This enables real-time terminal command monitoring for Cortex AI

# Only run in interactive shells
[[ $- != *i* ]] && return

# Skip if already set up or if this is the Cortex terminal
[[ -n "$CORTEX_TERMINAL" ]] && return
[[ -n "$__CORTEX_WATCH_ACTIVE" ]] && return
export __CORTEX_WATCH_ACTIVE=1

# Watch file location (user-specific)
CORTEX_WATCH_FILE="$HOME/.cortex/terminal_watch.log"
mkdir -p "$HOME/.cortex" 2>/dev/null

__cortex_last_histnum=""
__cortex_log_cmd() {
    local histnum="$(history 1 2>/dev/null | awk '{print $1}')"
    [[ "$histnum" == "$__cortex_last_histnum" ]] && return
    __cortex_last_histnum="$histnum"

    local cmd="$(history 1 2>/dev/null | sed "s/^[ ]*[0-9]*[ ]*//")"
    [[ -z "${cmd// /}" ]] && return
    [[ "$cmd" == cortex* ]] && return
    [[ "$cmd" == *"watch_hook"* ]] && return

    echo "$cmd" >> "$CORTEX_WATCH_FILE" 2>/dev/null
}

# Add to PROMPT_COMMAND (preserve existing)
if [[ -z "$PROMPT_COMMAND" ]]; then
    export PROMPT_COMMAND='history -a; __cortex_log_cmd'
else
    export PROMPT_COMMAND="${PROMPT_COMMAND}; __cortex_log_cmd"
fi
"""

        try:
            # Write to a temp file first
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(hook_content)
                temp_file = f.name

            # Use sudo to copy to /etc/profile.d/
            result = subprocess.run(
                ["sudo", "cp", temp_file, profile_script],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False, f"Failed to install: {result.stderr}"

            # Make it executable
            subprocess.run(["sudo", "chmod", "+x", profile_script], capture_output=True, timeout=10)

            # Clean up temp file
            Path(temp_file).unlink(missing_ok=True)

            return (
                True,
                f"✓ Installed system-wide to {profile_script}\n"
                "All NEW terminals will automatically have Cortex watching enabled.\n"
                "For current terminals, run: source /etc/profile.d/cortex-watch.sh",
            )

        except subprocess.TimeoutExpired:
            return False, "Timeout waiting for sudo"
        except Exception as e:
            return False, f"Error: {e}"

    def uninstall_system_wide_watch(self) -> tuple[bool, str]:
        """Remove the system-wide terminal watch hook."""
        import subprocess

        profile_script = "/etc/profile.d/cortex-watch.sh"

        try:
            if not Path(profile_script).exists():
                return True, "System-wide hook not installed"

            result = subprocess.run(
                ["sudo", "rm", profile_script], capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                return False, f"Failed to remove: {result.stderr}"

            return True, f"✓ Removed {profile_script}"

        except Exception as e:
            return False, f"Error: {e}"

    def is_system_wide_installed(self) -> bool:
        """Check if system-wide hook is installed."""
        return Path("/etc/profile.d/cortex-watch.sh").exists()

    def setup_auto_watch(self, permanent: bool = True) -> tuple[bool, str]:
        """
        Set up automatic terminal watching for new and existing terminals.

        Args:
            permanent: If True, adds the hook to ~/.bashrc for future terminals

        Returns:
            Tuple of (success, message)
        """
        watch_file = self.get_watch_file_path()
        watch_file.parent.mkdir(parents=True, exist_ok=True)

        # The hook command - excludes cortex commands and source commands
        # Uses a function to filter out Cortex terminal commands
        # Added: tracks last logged command and history number to avoid duplicates
        hook_line = f"""
__cortex_last_histnum=""
__cortex_log_cmd() {{
    # Get current history number
    local histnum="$(history 1 | awk '{{print $1}}')"
    # Skip if same as last logged (prevents duplicate on terminal init)
    [[ "$histnum" == "$__cortex_last_histnum" ]] && return
    __cortex_last_histnum="$histnum"

    local cmd="$(history 1 | sed "s/^[ ]*[0-9]*[ ]*//")"
    # Skip empty or whitespace-only commands
    [[ -z "${{cmd// /}}" ]] && return
    # Skip if this is the cortex terminal or cortex-related commands
    [[ "$cmd" == cortex* ]] && return
    [[ "$cmd" == *"source"*".cortex"* ]] && return
    [[ "$cmd" == *"watch_hook"* ]] && return
    [[ -n "$CORTEX_TERMINAL" ]] && return
    # Include terminal ID (TTY) in the log - format: TTY|COMMAND
    local tty_name="$(tty 2>/dev/null | sed 's|/dev/||' | tr '/' '_')"
    echo "${{tty_name:-unknown}}|$cmd" >> {watch_file}
}}
export PROMPT_COMMAND='history -a; __cortex_log_cmd'
"""
        marker = "# Cortex Terminal Watch Hook"

        bashrc = Path.home() / ".bashrc"
        zshrc = Path.home() / ".zshrc"

        added_to = []

        if permanent:
            # Add to .bashrc if it exists and doesn't already have the hook
            if bashrc.exists():
                content = bashrc.read_text()
                if marker not in content:
                    # Add hook AND a short alias for easy activation
                    alias_line = f'\nalias cw="source {watch_file.parent}/watch_hook.sh"  # Quick Cortex watch activation\n'
                    with open(bashrc, "a") as f:
                        f.write(f"\n{marker}\n{hook_line}\n{alias_line}")
                    added_to.append(".bashrc")
                else:
                    added_to.append(".bashrc (already configured)")

            # Add to .zshrc if it exists
            if zshrc.exists():
                content = zshrc.read_text()
                if marker not in content:
                    # Zsh uses precmd instead of PROMPT_COMMAND
                    # Added tracking to avoid duplicates
                    zsh_hook = f"""
{marker}
typeset -g __cortex_last_cmd=""
cortex_watch_hook() {{
    local cmd="$(fc -ln -1 | sed 's/^[[:space:]]*//')"
    [[ -z "$cmd" ]] && return
    [[ "$cmd" == "$__cortex_last_cmd" ]] && return
    __cortex_last_cmd="$cmd"
    [[ "$cmd" == cortex* ]] && return
    [[ "$cmd" == *".cortex"* ]] && return
    [[ -n "$CORTEX_TERMINAL" ]] && return
    # Include terminal ID (TTY) in the log - format: TTY|COMMAND
    local tty_name="$(tty 2>/dev/null | sed 's|/dev/||' | tr '/' '_')"
    echo "${{tty_name:-unknown}}|$cmd" >> {watch_file}
}}
precmd_functions+=(cortex_watch_hook)
"""
                    with open(zshrc, "a") as f:
                        f.write(zsh_hook)
                    added_to.append(".zshrc")
                else:
                    added_to.append(".zshrc (already configured)")

        # Create a source file for existing terminals
        source_file = Path.home() / ".cortex" / "watch_hook.sh"
        source_file.write_text(f"""#!/bin/bash
{marker}
{hook_line}
echo "✓ Cortex is now watching this terminal"
""")
        source_file.chmod(0o755)
        source_file.chmod(0o755)

        if added_to:
            msg = f"Added to: {', '.join(added_to)}\n"
            msg += f"For existing terminals, run: source {source_file}"
            return True, msg
        else:
            return True, f"Source file created: {source_file}\nRun: source {source_file}"

    def remove_auto_watch(self) -> tuple[bool, str]:
        """Remove the automatic terminal watching hook from shell configs."""
        marker = "# Cortex Terminal Watch Hook"
        removed_from = []

        for rc_file in [Path.home() / ".bashrc", Path.home() / ".zshrc"]:
            if rc_file.exists():
                content = rc_file.read_text()
                if marker in content:
                    # Remove the hook section
                    lines = content.split("\n")
                    new_lines = []
                    skip_until_blank = False

                    for line in lines:
                        if marker in line:
                            skip_until_blank = True
                            continue
                        if skip_until_blank:
                            if (
                                line.strip() == ""
                                or line.startswith("export PROMPT")
                                or line.startswith("cortex_watch")
                                or line.startswith("precmd_functions")
                            ):
                                continue
                            if line.startswith("}"):
                                continue
                            skip_until_blank = False
                        new_lines.append(line)

                    rc_file.write_text("\n".join(new_lines))
                    removed_from.append(rc_file.name)

        # Remove source file
        source_file = Path.home() / ".cortex" / "watch_hook.sh"
        if source_file.exists():
            source_file.unlink()
            removed_from.append("watch_hook.sh")

        if removed_from:
            return True, f"Removed from: {', '.join(removed_from)}"
        return True, "No hooks found to remove"

    def broadcast_hook_to_terminals(self) -> int:
        """
        Attempt to set up the hook in all running bash terminals.
        Uses various methods to inject the hook.

        Returns the number of terminals that were set up.
        """
        watch_file = self.get_watch_file_path()
        hook_cmd = f'export PROMPT_COMMAND=\'history -a; echo "$(history 1 | sed "s/^[ ]*[0-9]*[ ]*//")" >> {watch_file}\''

        count = 0

        # Method 1: Write to all pts devices (requires proper permissions)
        try:
            pts_dir = Path("/dev/pts")
            if pts_dir.exists():
                for pts in pts_dir.iterdir():
                    if pts.name.isdigit():
                        try:
                            # This usually requires the same user
                            with open(pts, "w") as f:
                                f.write("\n# Cortex: Setting up terminal watch...\n")
                                f.write("source ~/.cortex/watch_hook.sh\n")
                            count += 1
                        except (PermissionError, OSError):
                            pass
        except Exception:
            pass

        return count

    def _monitor_loop(self):
        """Monitor loop that watches ALL terminal sources for activity."""
        file_positions: dict[str, int] = {}
        last_check_time: dict[str, float] = {}

        # Cortex watch file (real-time if user sets up the hook)
        watch_file = self.get_watch_file_path()

        # Ensure watch file directory exists
        watch_file.parent.mkdir(parents=True, exist_ok=True)

        # Initialize positions for all shell history files - start at END to only see NEW commands
        for hist_file in self._shell_history_files:
            if hist_file.exists():
                try:
                    file_positions[str(hist_file)] = hist_file.stat().st_size
                    last_check_time[str(hist_file)] = time.time()
                except OSError:
                    pass

        # Initialize watch file position - ALWAYS start from END of existing content
        # This ensures we only see commands written AFTER monitoring starts
        if watch_file.exists():
            try:
                # Start from current end position (skip ALL existing content)
                file_positions[str(watch_file)] = watch_file.stat().st_size
            except OSError:
                file_positions[str(watch_file)] = 0
        else:
            # File doesn't exist yet - will be created, start from 0
            file_positions[str(watch_file)] = 0

        # Initialize positions for all Cursor terminal files
        for terminals_dir in self._cursor_terminals_dirs:
            if terminals_dir.exists():
                for term_file in terminals_dir.glob("*.txt"):
                    try:
                        file_positions[str(term_file)] = term_file.stat().st_size
                    except OSError:
                        pass
                # Also check for ext-*.txt files (external terminals)
                for term_file in terminals_dir.glob("ext-*.txt"):
                    try:
                        file_positions[str(term_file)] = term_file.stat().st_size
                    except OSError:
                        pass

        check_count = 0
        while self._monitoring:
            time.sleep(0.2)  # Check very frequently (5 times per second)
            check_count += 1

            # Check Cortex watch file FIRST (this is the real-time one)
            if watch_file.exists():
                self._check_watch_file(watch_file, file_positions)

            # Check all shell history files
            for hist_file in self._shell_history_files:
                if hist_file.exists():
                    shell_name = hist_file.stem.replace("_history", "").replace(".", "")
                    self._check_file_for_new_commands(
                        hist_file, file_positions, source=f"{shell_name}_history"
                    )

            # Check ALL Cursor terminal directories (these update in real-time!)
            for terminals_dir in self._cursor_terminals_dirs:
                if terminals_dir.exists():
                    project_name = terminals_dir.parent.name

                    # IDE terminals - check ALL txt files
                    for term_file in terminals_dir.glob("*.txt"):
                        if not term_file.name.startswith("ext-"):
                            self._check_file_for_new_commands(
                                term_file,
                                file_positions,
                                source=f"cursor:{project_name}:{term_file.stem}",
                            )

                    # External terminals (iTerm, gnome-terminal, etc.)
                    for term_file in terminals_dir.glob("ext-*.txt"):
                        self._check_file_for_new_commands(
                            term_file,
                            file_positions,
                            source=f"external:{project_name}:{term_file.stem}",
                        )

            # Check tmux panes if available (every 5 checks = 1 second)
            if self._tmux_available and check_count % 5 == 0:
                self._check_tmux_panes()

            # Periodically show we're still monitoring (every 30 seconds)
            if check_count % 150 == 0 and self._show_live_output:
                console.print(
                    f"[{GRAY}]{ICON_PENDING} still monitoring ({len(self._commands_observed)} commands observed so far)[/{GRAY}]"
                )

    def _is_cortex_terminal_command(self, command: str) -> bool:
        """Check if a command is from the Cortex terminal itself (should be ignored).

        This should be very conservative - only filter out commands that are
        DEFINITELY from Cortex's own terminal, not user commands.
        """
        cmd_lower = command.lower().strip()

        # Only filter out commands that are clearly from Cortex terminal
        cortex_patterns = [
            "cortex ask",
            "cortex watch",
            "cortex do ",
            "cortex info",
            "source ~/.cortex/watch_hook",  # Setting up the watch hook
            ".cortex/watch_hook",
        ]

        for pattern in cortex_patterns:
            if pattern in cmd_lower:
                return True

        # Check if command starts with "cortex " (the CLI)
        if cmd_lower.startswith("cortex "):
            return True

        # Don't filter out general commands - let them through!
        return False

    def _check_watch_file(self, watch_file: Path, positions: dict[str, int]):
        """Check the Cortex watch file for new commands (real-time)."""
        try:
            current_size = watch_file.stat().st_size
            key = str(watch_file)

            # Initialize position if not set
            # Start from 0 because we clear the file when monitoring starts
            # This ensures we capture all commands written after monitoring begins
            if key not in positions:
                positions[key] = 0  # Start from beginning since file was cleared

            # If file is smaller than our position (was truncated), reset
            if current_size < positions[key]:
                positions[key] = 0

            if current_size > positions[key]:
                with open(watch_file) as f:
                    f.seek(positions[key])
                    new_content = f.read()

                    # Parse watch file - each line is a command
                    for line in new_content.split("\n"):
                        line = line.strip()
                        if not line:
                            continue

                        # Skip very short lines or common noise
                        if len(line) < 2:
                            continue

                        # Skip if we've already seen this exact command recently
                        if hasattr(self, "_recent_watch_commands"):
                            if line in self._recent_watch_commands:
                                continue
                        else:
                            self._recent_watch_commands = []

                        # Keep track of recent commands to avoid duplicates
                        self._recent_watch_commands.append(line)
                        if len(self._recent_watch_commands) > 20:
                            self._recent_watch_commands.pop(0)

                        # Handle format with timestamp: "HH:MM:SS command"
                        if re.match(r"^\d{2}:\d{2}:\d{2}\s+", line):
                            parts = line.split(" ", 1)
                            if len(parts) == 2 and parts[1].strip():
                                self._process_observed_command(parts[1].strip(), "live_terminal")
                        else:
                            # Plain command
                            self._process_observed_command(line, "live_terminal")

                positions[key] = current_size

        except OSError:
            pass

    def _check_tmux_panes(self):
        """Check tmux panes for recent commands."""
        import subprocess

        try:
            # Get list of tmux sessions
            result = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", "#{pane_id}:#{pane_current_command}"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if ":" in line:
                        pane_id, cmd = line.split(":", 1)
                        if cmd and cmd not in ["bash", "zsh", "fish", "sh"]:
                            self._process_observed_command(cmd, source=f"tmux:{pane_id}")
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass

    def _check_file_for_new_commands(
        self,
        file_path: Path,
        positions: dict[str, int],
        source: str,
    ):
        """Check a file for new commands and process them."""
        try:
            current_size = file_path.stat().st_size
            key = str(file_path)

            if key not in positions:
                positions[key] = current_size
                return

            if current_size > positions[key]:
                with open(file_path) as f:
                    f.seek(positions[key])
                    new_content = f.read()

                    # For Cursor terminals, also extract output
                    if "cursor" in source or "external" in source:
                        self._process_terminal_content(new_content, source)
                    else:
                        new_commands = self._extract_commands_from_content(new_content, source)
                        for cmd in new_commands:
                            self._process_observed_command(cmd, source)

                positions[key] = current_size

        except OSError:
            pass

    def _process_terminal_content(self, content: str, source: str):
        """Process terminal content including commands and their output."""
        lines = content.split("\n")
        current_command = None
        output_lines = []

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Check if this is a command line (has prompt)
            is_command = False
            for pattern in [
                r"^\$ (.+)$",
                r"^[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+:.+\$ (.+)$",
                r"^[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+:.+# (.+)$",
                r"^\(.*\)\s*\$ (.+)$",
            ]:
                match = re.match(pattern, line_stripped)
                if match:
                    # Save previous command with its output
                    if current_command:
                        self._process_observed_command_with_output(
                            current_command, "\n".join(output_lines), source
                        )

                    current_command = match.group(1).strip()
                    output_lines = []
                    is_command = True
                    break

            if not is_command and current_command:
                # This is output from the current command
                output_lines.append(line_stripped)

        # Process the last command
        if current_command:
            self._process_observed_command_with_output(
                current_command, "\n".join(output_lines), source
            )

    def _process_observed_command_with_output(self, command: str, output: str, source: str):
        """Process a command with its output for better feedback."""
        # First process the command normally
        self._process_observed_command(command, source)

        if not self._show_live_output:
            return

        # Then show relevant output if there is any
        if output and len(output) > 5:
            # Check for errors in output
            error_patterns = [
                (r"error:", "Error detected"),
                (r"Error:", "Error detected"),
                (r"ERROR", "Error detected"),
                (r"failed", "Operation failed"),
                (r"Failed", "Operation failed"),
                (r"permission denied", "Permission denied"),
                (r"Permission denied", "Permission denied"),
                (r"not found", "Not found"),
                (r"No such file", "File not found"),
                (r"command not found", "Command not found"),
                (r"Cannot connect", "Connection failed"),
                (r"Connection refused", "Connection refused"),
                (r"Unable to", "Operation failed"),
                (r"denied", "Access denied"),
                (r"Denied", "Access denied"),
                (r"timed out", "Timeout"),
                (r"timeout", "Timeout"),
                (r"fatal:", "Fatal error"),
                (r"FATAL", "Fatal error"),
                (r"panic", "Panic"),
                (r"segfault", "Crash"),
                (r"Segmentation fault", "Crash"),
                (r"killed", "Process killed"),
                (r"Killed", "Process killed"),
                (r"cannot", "Cannot complete"),
                (r"Could not", "Could not complete"),
                (r"Invalid", "Invalid input"),
                (r"Conflict", "Conflict detected"),
                (r"\[emerg\]", "Config error"),
                (r"\[error\]", "Error"),
                (r"\[crit\]", "Critical error"),
                (r"\[alert\]", "Alert"),
                (r"syntax error", "Syntax error"),
                (r"unknown directive", "Unknown directive"),
                (r"unexpected", "Unexpected error"),
            ]

            for pattern, msg in error_patterns:
                if re.search(pattern, output, re.IGNORECASE):
                    # Show error in bordered panel
                    from rich.panel import Panel
                    from rich.text import Text

                    output_preview = output[:200] + "..." if len(output) > 200 else output

                    error_text = Text()
                    error_text.append(f"{ICON_ERROR} {msg}\n\n", style=f"bold {RED}")
                    for line in output_preview.split("\n")[:3]:
                        if line.strip():
                            error_text.append(f"  {line.strip()[:80]}\n", style=GRAY)

                    console.print()
                    console.print(
                        Panel(
                            error_text,
                            title=f"[bold {RED}]Error[/bold {RED}]",
                            border_style=RED,
                            padding=(0, 1),
                        )
                    )

                    # Get AI-powered help
                    self._provide_error_help(command, output)
                    break
            else:
                # Show success indicator for commands that completed
                if "✓" in output or "success" in output.lower() or "complete" in output.lower():
                    console.print(
                        f"[{GREEN}]   {ICON_SUCCESS} Command completed successfully[/{GREEN}]"
                    )
                elif len(output.strip()) > 0:
                    # Show a preview of the output
                    output_lines = [l for l in output.split("\n") if l.strip()][:3]
                    if output_lines:
                        console.print(
                            f"[{GRAY}]   Output: {output_lines[0][:60]}{'...' if len(output_lines[0]) > 60 else ''}[/{GRAY}]"
                        )

    def _provide_error_help(self, command: str, output: str):
        """Provide contextual help for errors using Claude LLM and send solutions via notifications."""
        import subprocess

        from rich.panel import Panel
        from rich.table import Table

        console.print()

        # First, try Claude for intelligent analysis
        claude_analysis = None
        if self._claude and self._use_llm and self._claude.is_available():
            claude_analysis = self._claude.analyze_error(command, output)

        # Also use the existing ErrorDiagnoser for pattern-based analysis
        diagnosis = self._diagnoser.diagnose_error(command, output)

        error_type = diagnosis.get("error_type", "unknown")
        category = diagnosis.get("category", "unknown")
        description = diagnosis.get("description", output[:200])
        fix_commands = diagnosis.get("fix_commands", [])
        can_auto_fix = diagnosis.get("can_auto_fix", False)
        fix_strategy = diagnosis.get("fix_strategy", "")
        extracted_info = diagnosis.get("extracted_info", {})

        # If Claude provided analysis, use it to enhance diagnosis
        if claude_analysis:
            cause = claude_analysis.get("cause", "")
            claude_fixes = claude_analysis.get("fixes", [])

            # Show Claude's analysis in bordered panel
            if cause or claude_fixes:
                from rich.panel import Panel
                from rich.text import Text

                analysis_text = Text()
                if cause:
                    analysis_text.append("Cause: ", style="bold cyan")
                    analysis_text.append(f"{cause}\n\n", style="white")
                if claude_fixes:
                    analysis_text.append("Solution:\n", style=f"bold {GREEN}")
                    for fix in claude_fixes[:3]:
                        analysis_text.append(f"  $ {fix}\n", style=GREEN)

                console.print()
                console.print(
                    Panel(
                        analysis_text,
                        title=f"[bold {PURPLE_LIGHT}]{ICON_MONITOR} Claude Analysis[/bold {PURPLE_LIGHT}]",
                        border_style=PURPLE,
                        padding=(0, 1),
                    )
                )

            # Send notification with Claude's solution
            if cause or claude_fixes:
                notif_title = f"🔧 Cortex: {error_type if error_type != 'unknown' else 'Error'}"
                notif_body = cause[:100] if cause else description[:100]
                if claude_fixes:
                    notif_body += f"\n\nFix: {claude_fixes[0]}"
                self._send_solution_notification(notif_title, notif_body)

            # Use Claude's fixes if pattern-based analysis didn't find any
            if not fix_commands and claude_fixes:
                fix_commands = claude_fixes
                can_auto_fix = True

        # Show diagnosis in panel (only if no Claude analysis)
        if not claude_analysis:
            from rich.panel import Panel
            from rich.table import Table
            from rich.text import Text

            diag_table = Table(show_header=False, box=None, padding=(0, 1))
            diag_table.add_column("Key", style="dim")
            diag_table.add_column("Value", style="bold")

            diag_table.add_row("Type", error_type)
            diag_table.add_row("Category", category)
            if can_auto_fix:
                diag_table.add_row(
                    "Auto-Fix",
                    (
                        f"[{GREEN}]{ICON_SUCCESS} Yes[/{GREEN}] [{GRAY}]({fix_strategy})[/{GRAY}]"
                        if fix_strategy
                        else f"[{GREEN}]{ICON_SUCCESS} Yes[/{GREEN}]"
                    ),
                )
            else:
                diag_table.add_row("Auto-Fix", f"[{RED}]{ICON_INFO} No[/{RED}]")

            console.print()
            console.print(
                Panel(
                    diag_table,
                    title=f"[bold {PURPLE_LIGHT}]Diagnosis[/bold {PURPLE_LIGHT}]",
                    border_style=PURPLE,
                    padding=(0, 1),
                )
            )

        # If auto-fix is possible, attempt to run the fix commands
        if can_auto_fix and fix_commands:
            actionable_commands = [c for c in fix_commands if not c.startswith("#")]

            if actionable_commands:
                # Auto-fix with progress bar
                from rich.panel import Panel
                from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

                console.print()
                console.print(
                    Panel(
                        f"[bold {WHITE}]Running {len(actionable_commands)} fix command(s)...[/bold {WHITE}]",
                        title=f"[bold {PURPLE_LIGHT}]{ICON_SUCCESS} Auto-Fix[/bold {PURPLE_LIGHT}]",
                        border_style=PURPLE,
                        padding=(0, 1),
                    )
                )

                # Send notification that we're fixing the command
                self._notify_fixing_command(command, actionable_commands[0])

                # Run the fix commands
                fix_success = self._run_auto_fix_commands(actionable_commands, command, error_type)

                if fix_success:
                    # Success in bordered panel
                    from rich.panel import Panel

                    console.print()
                    console.print(
                        Panel(
                            f"[{GREEN}]{ICON_SUCCESS}[/{GREEN}] [{WHITE}]Auto-fix completed![/{WHITE}]\n\n[{GRAY}]Retry:[/{GRAY}] [{PURPLE_LIGHT}]{command}[/{PURPLE_LIGHT}]",
                            title=f"[bold {GREEN}]Success[/bold {GREEN}]",
                            border_style=PURPLE,
                            padding=(0, 1),
                        )
                    )

                    # Send success notification
                    self._send_fix_success_notification(command, error_type)
                else:
                    pass  # Sudo commands shown separately

                console.print()
                return

        # Show fix commands in bordered panel if we can't auto-fix
        if fix_commands and not claude_analysis:
            from rich.panel import Panel
            from rich.text import Text

            fix_text = Text()
            for cmd in fix_commands[:3]:
                if not cmd.startswith("#"):
                    fix_text.append(f"  $ {cmd}\n", style="green")

            console.print()
            console.print(
                Panel(
                    fix_text,
                    title="[bold]Manual Fix[/bold]",
                    border_style="blue",
                    padding=(0, 1),
                )
            )

        # If error is unknown and no Claude, use local LLM
        if (
            error_type == "unknown"
            and not claude_analysis
            and self._llm
            and self._use_llm
            and self._llm.is_available()
        ):
            llm_help = self._llm_analyze_error(command, output)
            if llm_help:
                console.print()
                console.print(f"[{GRAY}]{llm_help}[/{GRAY}]")

                # Try to extract fix command from LLM response
                llm_fix = self._extract_fix_from_llm(llm_help)
                if llm_fix:
                    console.print()
                    console.print(
                        f"[bold {GREEN}]{ICON_SUCCESS} AI Suggested Fix:[/bold {GREEN}] [{PURPLE_LIGHT}]{llm_fix}[/{PURPLE_LIGHT}]"
                    )

                    # Attempt to run the LLM suggested fix
                    if self._is_safe_fix_command(llm_fix):
                        console.print(f"[{GRAY}]Attempting AI-suggested fix...[/{GRAY}]")
                        self._run_auto_fix_commands([llm_fix], command, "ai_suggested")

        # Build notification message
        notification_msg = ""
        if fix_commands:
            actionable = [c for c in fix_commands if not c.startswith("#")]
            if actionable:
                notification_msg = f"Manual fix needed: {actionable[0][:50]}"
            else:
                notification_msg = description[:100]
        else:
            notification_msg = description[:100]

        # Send desktop notification
        self._send_error_notification(command, notification_msg, error_type, can_auto_fix)

        console.print()

    def _run_auto_fix_commands(
        self, commands: list[str], original_command: str, error_type: str
    ) -> bool:
        """Run auto-fix commands with progress bar and return True if successful."""
        import subprocess

        from rich.panel import Panel
        from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
        from rich.table import Table

        all_success = True
        sudo_commands_pending = []
        results = []

        # Break down && commands into individual commands
        expanded_commands = []
        for cmd in commands[:3]:
            if cmd.startswith("#"):
                continue
            # Split by && but preserve the individual commands
            if " && " in cmd:
                parts = [p.strip() for p in cmd.split(" && ") if p.strip()]
                expanded_commands.extend(parts)
            else:
                expanded_commands.append(cmd)

        actionable = expanded_commands

        # Show each command being run with Rich Status (no raw ANSI codes)
        from rich.status import Status

        for i, fix_cmd in enumerate(actionable, 1):
            # Check if this needs sudo
            needs_sudo = fix_cmd.strip().startswith("sudo ")

            if needs_sudo:
                try:
                    check_sudo = subprocess.run(
                        ["sudo", "-n", "true"], capture_output=True, timeout=5
                    )

                    if check_sudo.returncode != 0:
                        sudo_commands_pending.append(fix_cmd)
                        results.append((fix_cmd, "sudo", None))
                        console.print(
                            f"  [{GRAY}][{i}/{len(actionable)}][/{GRAY}] [{YELLOW}]![/{YELLOW}] [{WHITE}]{fix_cmd[:55]}...[/{WHITE}] [{GRAY}](needs sudo)[/{GRAY}]"
                        )
                        continue
                except Exception:
                    sudo_commands_pending.append(fix_cmd)
                    results.append((fix_cmd, "sudo", None))
                    console.print(
                        f"  [{GRAY}][{i}/{len(actionable)}][/{GRAY}] [{YELLOW}]![/{YELLOW}] [{WHITE}]{fix_cmd[:55]}...[/{WHITE}] [{GRAY}](needs sudo)[/{GRAY}]"
                    )
                    continue

            # Run command with status spinner
            cmd_display = fix_cmd[:55] + "..." if len(fix_cmd) > 55 else fix_cmd

            try:
                with Status(
                    f"[{PURPLE_LIGHT}]{cmd_display}[/{PURPLE_LIGHT}]",
                    console=console,
                    spinner="dots",
                ):
                    result = subprocess.run(
                        fix_cmd, shell=True, capture_output=True, text=True, timeout=60
                    )

                if result.returncode == 0:
                    results.append((fix_cmd, "success", None))
                    console.print(
                        f"  [{GRAY}][{i}/{len(actionable)}][/{GRAY}] [{GREEN}]{ICON_SUCCESS}[/{GREEN}] [{WHITE}]{cmd_display}[/{WHITE}]"
                    )
                else:
                    if (
                        "password" in (result.stderr or "").lower()
                        or "terminal is required" in (result.stderr or "").lower()
                    ):
                        sudo_commands_pending.append(fix_cmd)
                        results.append((fix_cmd, "sudo", None))
                        console.print(
                            f"  [{GRAY}][{i}/{len(actionable)}][/{GRAY}] [{YELLOW}]![/{YELLOW}] [{WHITE}]{cmd_display}[/{WHITE}] [{GRAY}](needs sudo)[/{GRAY}]"
                        )
                    else:
                        results.append(
                            (fix_cmd, "failed", result.stderr[:60] if result.stderr else "failed")
                        )
                        all_success = False
                        console.print(
                            f"  [{GRAY}][{i}/{len(actionable)}][/{GRAY}] [{RED}]{ICON_ERROR}[/{RED}] [{WHITE}]{cmd_display}[/{WHITE}]"
                        )
                        console.print(
                            f"      [{GRAY}]{result.stderr[:80] if result.stderr else 'Command failed'}[/{GRAY}]"
                        )
                        break

            except subprocess.TimeoutExpired:
                results.append((fix_cmd, "timeout", None))
                all_success = False
                console.print(
                    f"  [{GRAY}][{i}/{len(actionable)}][/{GRAY}] [{YELLOW}]{ICON_PENDING}[/{YELLOW}] [{WHITE}]{cmd_display}[/{WHITE}] [{GRAY}](timeout)[/{GRAY}]"
                )
                break
            except Exception as e:
                results.append((fix_cmd, "error", str(e)[:50]))
                all_success = False
                console.print(
                    f"  [{GRAY}][{i}/{len(actionable)}][/{GRAY}] [{RED}]{ICON_ERROR}[/{RED}] [{WHITE}]{cmd_display}[/{WHITE}]"
                )
                break

        # Show summary line
        success_count = sum(1 for _, s, _ in results if s == "success")
        if success_count > 0 and success_count == len([r for r in results if r[1] != "sudo"]):
            console.print(
                f"\n  [{GREEN}]{ICON_SUCCESS} All {success_count} command(s) completed[/{GREEN}]"
            )

        # Show sudo commands in bordered panel
        if sudo_commands_pending:
            from rich.panel import Panel
            from rich.text import Text

            sudo_text = Text()
            sudo_text.append("Run these commands manually:\n\n", style=GRAY)
            for cmd in sudo_commands_pending:
                sudo_text.append(f"  $ {cmd}\n", style=GREEN)

            console.print()
            console.print(
                Panel(
                    sudo_text,
                    title=f"[bold {YELLOW}]🔐 Sudo Required[/bold {YELLOW}]",
                    border_style=PURPLE,
                    padding=(0, 1),
                )
            )

            # Send notification about pending sudo commands
            self._send_sudo_pending_notification(sudo_commands_pending)

            # Still consider it a partial success if we need manual sudo
            return len(sudo_commands_pending) < len([c for c in commands if not c.startswith("#")])

        return all_success

    def _send_sudo_pending_notification(self, commands: list[str]):
        """Send notification about pending sudo commands."""
        try:
            import subprocess

            cmd_preview = commands[0][:40] + "..." if len(commands[0]) > 40 else commands[0]

            subprocess.run(
                [
                    "notify-send",
                    "--urgency=normal",
                    "--icon=dialog-password",
                    "🔐 Cortex: Sudo required",
                    f"Run in your terminal:\n{cmd_preview}",
                ],
                capture_output=True,
                timeout=2,
            )

        except Exception:
            pass

    def _extract_fix_from_llm(self, llm_response: str) -> str | None:
        """Extract a fix command from LLM response."""
        import re

        # Look for commands in common formats
        patterns = [
            r"`([^`]+)`",  # Backtick enclosed
            r"^\$ (.+)$",  # Shell prompt format
            r"^sudo (.+)$",  # Sudo commands
            r"run[:\s]+([^\n]+)",  # "run: command" format
            r"try[:\s]+([^\n]+)",  # "try: command" format
        ]

        for pattern in patterns:
            matches = re.findall(pattern, llm_response, re.MULTILINE | re.IGNORECASE)
            for match in matches:
                cmd = match.strip()
                if cmd and len(cmd) > 3 and self._is_safe_fix_command(cmd):
                    return cmd

        return None

    def _is_safe_fix_command(self, command: str) -> bool:
        """Check if a fix command is safe to run automatically."""
        cmd_lower = command.lower().strip()

        # Dangerous commands we should never auto-run
        dangerous_patterns = [
            "rm -rf /",
            "rm -rf ~",
            "rm -rf *",
            "> /dev/",
            "mkfs",
            "dd if=",
            "chmod -R 777 /",
            "chmod 777 /",
            ":(){:|:&};:",  # Fork bomb
            "wget|sh",
            "curl|sh",
            "curl|bash",
            "wget|bash",
        ]

        for pattern in dangerous_patterns:
            if pattern in cmd_lower:
                return False

        # Safe fix command patterns
        safe_patterns = [
            "sudo systemctl",
            "sudo service",
            "sudo apt",
            "sudo apt-get",
            "apt-cache",
            "systemctl status",
            "sudo nginx -t",
            "sudo nginx -s reload",
            "docker start",
            "docker restart",
            "pip install",
            "npm install",
            "sudo chmod",
            "sudo chown",
            "mkdir -p",
            "touch",
        ]

        for pattern in safe_patterns:
            if cmd_lower.startswith(pattern):
                return True

        # Allow sudo commands for common safe operations
        if cmd_lower.startswith("sudo "):
            rest = cmd_lower[5:].strip()
            safe_sudo = [
                "systemctl",
                "service",
                "apt",
                "apt-get",
                "nginx",
                "chmod",
                "chown",
                "mkdir",
            ]
            if any(rest.startswith(s) for s in safe_sudo):
                return True

        return False

    def _send_fix_success_notification(self, command: str, error_type: str):
        """Send a desktop notification that the fix was successful."""
        try:
            import subprocess

            cmd_short = command[:30] + "..." if len(command) > 30 else command

            subprocess.run(
                [
                    "notify-send",
                    "--urgency=normal",
                    "--icon=dialog-information",
                    f"✅ Cortex: Fixed {error_type}",
                    f"Auto-fix successful! You can now retry:\n{cmd_short}",
                ],
                capture_output=True,
                timeout=2,
            )

        except Exception:
            pass

    def _send_solution_notification(self, title: str, body: str):
        """Send a desktop notification with the solution from Claude."""
        try:
            import subprocess

            # Use notify-send with high priority
            subprocess.run(
                [
                    "notify-send",
                    "--urgency=critical",
                    "--icon=dialog-information",
                    "--expire-time=15000",  # 15 seconds
                    title,
                    body,
                ],
                capture_output=True,
                timeout=2,
            )

        except Exception:
            pass

    def _send_error_notification(
        self, command: str, solution: str, error_type: str = "", can_auto_fix: bool = False
    ):
        """Send a desktop notification with the error solution."""
        try:
            # Try to use notify-send (standard on Ubuntu)
            import subprocess

            # Truncate for notification
            cmd_short = command[:30] + "..." if len(command) > 30 else command
            solution_short = solution[:150] + "..." if len(solution) > 150 else solution

            # Build title with error type
            if error_type and error_type != "unknown":
                title = f"🔧 Cortex: {error_type}"
            else:
                title = "🔧 Cortex: Error detected"

            # Add auto-fix indicator
            if can_auto_fix:
                body = f"✓ Auto-fixable\n\n{solution_short}"
                icon = "dialog-information"
            else:
                body = solution_short
                icon = "dialog-warning"

            # Send notification
            subprocess.run(
                ["notify-send", "--urgency=normal", f"--icon={icon}", title, body],
                capture_output=True,
                timeout=2,
            )

        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            # notify-send not available or failed, try callback
            if self.notification_callback:
                self.notification_callback(f"Error in: {command[:30]}", solution[:100])

    def _llm_analyze_error(self, command: str, error_output: str) -> str | None:
        """Use local LLM to analyze an error and provide a fix."""
        if not self._llm:
            return None

        # Build context from recent commands
        context = ""
        if self._session_context:
            context = "Recent commands:\n" + "\n".join(self._session_context[-5:]) + "\n\n"

        prompt = f"""You are a Linux expert. A user ran a command and got an error.
Provide a brief, actionable fix (2-3 sentences max).

IMPORTANT: Do NOT suggest sudo commands - they cannot be auto-executed.
Only suggest non-sudo commands. If sudo is required, say "requires manual sudo" instead.

{context}Command: {command}

Error output:
{error_output[:500]}

Fix (be specific, give the exact non-sudo command to run):"""

        try:
            result = self._llm.analyze(prompt, max_tokens=150, timeout=10)
            if result:
                return result.strip()
        except Exception:
            pass

        return None

    def analyze_session_intent(self) -> str | None:
        """Use LLM to analyze what the user is trying to accomplish based on their commands."""
        if not self._llm or not self._llm.is_available():
            return None

        if len(self._session_context) < 2:
            return None

        prompt = f"""Based on these terminal commands, what is the user trying to accomplish?
Give a brief summary (1 sentence max).

Commands:
{chr(10).join(self._session_context[-5:])}

The user is trying to:"""

        try:
            result = self._llm.analyze(prompt, max_tokens=50, timeout=15)
            if result:
                result = result.strip()
                # Take only first sentence
                if ". " in result:
                    result = result.split(". ")[0] + "."
                return result
        except Exception:
            pass

        return None

    def get_next_step_suggestion(self) -> str | None:
        """Use LLM to suggest the next logical step based on recent commands."""
        if not self._llm or not self._llm.is_available():
            return None

        if len(self._session_context) < 1:
            return None

        prompt = f"""Based on these terminal commands, what single command should the user run next?
Respond with ONLY the command, nothing else.

Recent commands:
{chr(10).join(self._session_context[-5:])}

Next command:"""

        try:
            result = self._llm.analyze(prompt, max_tokens=30, timeout=15)
            if result:
                # Clean up - extract just the command
                result = result.strip()
                # Remove common prefixes
                for prefix in ["$", "Run:", "Try:", "Next:", "Command:", "`"]:
                    if result.lower().startswith(prefix.lower()):
                        result = result[len(prefix) :].strip()
                result = result.rstrip("`")
                return result.split("\n")[0].strip()
        except Exception:
            pass

        return None

    def get_collected_context(self) -> str:
        """Get a formatted summary of all collected terminal context."""
        with self._lock:
            if not self._commands_observed:
                return "No commands observed yet."

            lines = ["[bold]📋 Collected Terminal Context:[/bold]", ""]

            for i, obs in enumerate(self._commands_observed, 1):
                timestamp = obs.get("timestamp", "")[:19]
                source = obs.get("source", "unknown")
                command = obs.get("command", "")

                lines.append(f"{i}. [{timestamp}] ({source})")
                lines.append(f"   $ {command}")
                lines.append("")

            return "\n".join(lines)

    def print_collected_context(self):
        """Print a summary of all collected terminal context with AI analysis."""
        from rich.panel import Panel

        with self._lock:
            if not self._commands_observed:
                console.print(f"[{GRAY}]No commands observed yet.[/{GRAY}]")
                return

            console.print()
            console.print(
                Panel(
                    f"[bold {WHITE}]Collected {len(self._commands_observed)} command(s) from other terminals[/bold {WHITE}]",
                    title=f"[{PURPLE_LIGHT}]📋 Terminal Context Summary[/{PURPLE_LIGHT}]",
                    border_style=PURPLE,
                )
            )

            for i, obs in enumerate(self._commands_observed[-10:], 1):  # Show last 10
                timestamp = (
                    obs.get("timestamp", "")[:19].split("T")[-1]
                    if "T" in obs.get("timestamp", "")
                    else obs.get("timestamp", "")[:8]
                )
                source = obs.get("source", "unknown")
                command = obs.get("command", "")

                # Shorten source name
                if ":" in source:
                    source = source.split(":")[-1]

                console.print(
                    f"  [{GRAY}]{timestamp}[/{GRAY}] [{PURPLE_LIGHT}]{source:12}[/{PURPLE_LIGHT}] [{WHITE}]{command[:50]}{'...' if len(command) > 50 else ''}[/{WHITE}]"
                )

            if len(self._commands_observed) > 10:
                console.print(
                    f"  [{GRAY}]... and {len(self._commands_observed) - 10} more commands[/{GRAY}]"
                )

            # Add AI analysis if available
            if (
                self._llm
                and self._use_llm
                and self._llm.is_available()
                and len(self._session_context) >= 2
            ):
                console.print()
                console.print(
                    f"[bold {PURPLE_LIGHT}]{ICON_MONITOR} AI Analysis:[/bold {PURPLE_LIGHT}]"
                )

                # Analyze intent
                intent = self.analyze_session_intent()
                if intent:
                    console.print(f"[{WHITE}]   Intent: {intent}[/{WHITE}]")

                # Suggest next step
                next_step = self.get_next_step_suggestion()
                if next_step:
                    console.print(f"[{GREEN}]   Suggested next: {next_step}[/{GREEN}]")

            console.print()

    def _extract_commands_from_content(self, content: str, source: str) -> list[str]:
        """Extract commands from terminal content based on source type."""
        commands = []

        # Shell history files - each line is a command
        if "_history" in source or "history" in source:
            for line in content.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                # Skip timestamps in zsh extended history format
                if line.startswith(":"):
                    # Format: : timestamp:0;command
                    if ";" in line:
                        cmd = line.split(";", 1)[1]
                        if cmd:
                            commands.append(cmd)
                # Skip fish history format markers
                elif line.startswith("- cmd:"):
                    cmd = line[6:].strip()
                    if cmd:
                        commands.append(cmd)
                elif not line.startswith("when:"):
                    commands.append(line)
        else:
            # Terminal output - look for command prompts
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue

                # Various prompt patterns
                prompt_patterns = [
                    r"^\$ (.+)$",  # Simple $ prompt
                    r"^[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+:.+\$ (.+)$",  # user@host:path$ cmd
                    r"^[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+:.+# (.+)$",  # root prompt
                    r"^>>> (.+)$",  # Python REPL
                    r"^\(.*\)\s*\$ (.+)$",  # (venv) $ cmd
                    r"^➜\s+.+\s+(.+)$",  # Oh-my-zsh prompt
                    r"^❯ (.+)$",  # Starship prompt
                    r"^▶ (.+)$",  # Another prompt style
                    r"^\[.*\]\$ (.+)$",  # [dir]$ cmd
                    r"^% (.+)$",  # % prompt (zsh default)
                ]

                for pattern in prompt_patterns:
                    match = re.match(pattern, line)
                    if match:
                        cmd = match.group(1).strip()
                        if cmd:
                            commands.append(cmd)
                        break

        return commands

    def _process_observed_command(self, command: str, source: str = "unknown"):
        """Process an observed command and notify about issues with real-time feedback."""
        # Skip empty or very short commands
        if not command or len(command.strip()) < 2:
            return

        command = command.strip()

        # Skip commands from the Cortex terminal itself
        if self._is_cortex_terminal_command(command):
            return

        # Skip common shell built-ins that aren't interesting (only if standalone)
        skip_commands = ["cd", "ls", "pwd", "clear", "exit", "history", "fg", "bg", "jobs", "alias"]
        parts = command.split()
        cmd_base = parts[0] if parts else ""

        # Also handle sudo prefix
        if cmd_base == "sudo" and len(parts) > 1:
            cmd_base = parts[1]

        # Only skip if it's JUST the command with no args
        if cmd_base in skip_commands and len(parts) == 1:
            return

        # Skip if it looks like a partial command or just an argument
        if not any(c.isalpha() for c in cmd_base):
            return

        # Avoid duplicates within short time window
        with self._lock:
            recent = [
                c
                for c in self._commands_observed
                if c["command"] == command
                and (
                    datetime.datetime.now() - datetime.datetime.fromisoformat(c["timestamp"])
                ).seconds
                < 5
            ]
            if recent:
                return

            self._commands_observed.append(
                {
                    "command": command,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "source": source,
                    "has_error": False,  # Will be updated if error is detected
                    "status": "pending",  # pending, success, failed
                }
            )

            # Add to session context for LLM
            self._session_context.append(f"$ {command}")
            # Keep only last 10 commands for context
            if len(self._session_context) > 10:
                self._session_context = self._session_context[-10:]

        # Real-time feedback with visual emphasis
        self._show_realtime_feedback(command, source)

        # For live terminal commands, proactively check the result
        if source == "live_terminal":
            self._check_command_result(command)

        # Check for issues and provide help
        issues = self._check_command_issues(command)
        if issues:
            from rich.panel import Panel

            console.print(
                Panel(
                    f"[bold {YELLOW}]⚠ Issue:[/bold {YELLOW}] [{WHITE}]{issues}[/{WHITE}]",
                    border_style=PURPLE,
                    padding=(0, 1),
                    expand=False,
                )
            )
            if self.notification_callback:
                self.notification_callback("Cortex: Issue detected", issues)

        # Check if command matches expected commands
        if self._expected_commands:
            matched = self._check_command_match(command)
            from rich.panel import Panel

            if matched:
                console.print(
                    Panel(
                        f"[bold {GREEN}]{ICON_SUCCESS} Matches expected command[/bold {GREEN}]",
                        border_style=PURPLE,
                        padding=(0, 1),
                        expand=False,
                    )
                )
            else:
                # User ran a DIFFERENT command than expected
                console.print(
                    Panel(
                        f"[bold {YELLOW}]⚠ Not in expected commands[/bold {YELLOW}]",
                        border_style=PURPLE,
                        padding=(0, 1),
                        expand=False,
                    )
                )
                # Send notification with the correct command(s)
                self._notify_wrong_command(command)

    def _check_command_match(self, command: str) -> bool:
        """Check if a command matches any expected command."""
        if not self._expected_commands:
            return True  # No expected commands means anything goes

        cmd_normalized = command.strip().lower()
        # Remove sudo prefix for comparison
        if cmd_normalized.startswith("sudo "):
            cmd_normalized = cmd_normalized[5:].strip()

        for expected in self._expected_commands:
            exp_normalized = expected.strip().lower()
            if exp_normalized.startswith("sudo "):
                exp_normalized = exp_normalized[5:].strip()

            # Check for exact match or if command contains the expected command
            if cmd_normalized == exp_normalized:
                return True
            if exp_normalized in cmd_normalized:
                return True
            if cmd_normalized in exp_normalized:
                return True

            # Check if first words match (e.g., "systemctl restart nginx" vs "systemctl restart nginx.service")
            cmd_parts = cmd_normalized.split()
            exp_parts = exp_normalized.split()
            if len(cmd_parts) >= 2 and len(exp_parts) >= 2:
                if cmd_parts[0] == exp_parts[0] and cmd_parts[1] == exp_parts[1]:
                    return True

        return False

    def _notify_wrong_command(self, wrong_command: str):
        """Send desktop notification when user runs wrong command."""
        if not self._expected_commands:
            return

        # Find the most relevant expected command
        correct_cmd = self._expected_commands[0] if self._expected_commands else None

        if correct_cmd:
            title = "⚠️ Cortex: Wrong Command"
            body = f"You ran: {wrong_command[:40]}...\n\nExpected: {correct_cmd}"

            try:
                import subprocess

                subprocess.run(
                    [
                        "notify-send",
                        "--urgency=critical",
                        "--icon=dialog-warning",
                        "--expire-time=10000",
                        title,
                        body,
                    ],
                    capture_output=True,
                    timeout=2,
                )
            except Exception:
                pass

            # Also show in console
            console.print(
                f"         [bold {YELLOW}]📢 Expected command:[/bold {YELLOW}] [{PURPLE_LIGHT}]{correct_cmd}[/{PURPLE_LIGHT}]"
            )

    def _notify_fixing_command(self, original_cmd: str, fix_cmd: str):
        """Send notification that Cortex is fixing a command error."""
        title = "🔧 Cortex: Fixing Error"
        body = f"Command failed: {original_cmd[:30]}...\n\nFix: {fix_cmd}"

        try:
            import subprocess

            subprocess.run(
                [
                    "notify-send",
                    "--urgency=normal",
                    "--icon=dialog-information",
                    "--expire-time=8000",
                    title,
                    body,
                ],
                capture_output=True,
                timeout=2,
            )
        except Exception:
            pass

    def _check_command_result(self, command: str):
        """Proactively check if a command succeeded by running verification commands."""
        import subprocess
        import time

        # Wait a moment for the command to complete
        time.sleep(0.5)

        cmd_lower = command.lower().strip()
        check_cmd = None
        error_output = None

        # Determine what check to run based on the command
        if "systemctl" in cmd_lower:
            # Extract service name
            parts = command.split()
            service_name = None
            for i, p in enumerate(parts):
                if p in ["start", "stop", "restart", "reload", "enable", "disable"]:
                    if i + 1 < len(parts):
                        service_name = parts[i + 1]
                        break

            if service_name:
                check_cmd = f"systemctl status {service_name} 2>&1 | head -5"

        elif "service" in cmd_lower and "status" not in cmd_lower:
            # Extract service name for service command
            parts = command.split()
            if len(parts) >= 3:
                service_name = parts[1] if parts[0] != "sudo" else parts[2]
                check_cmd = f"service {service_name} status 2>&1 | head -5"

        elif "docker" in cmd_lower:
            if "run" in cmd_lower or "start" in cmd_lower:
                # Get container name if present
                parts = command.split()
                container_name = None
                for i, p in enumerate(parts):
                    if p == "--name" and i + 1 < len(parts):
                        container_name = parts[i + 1]
                        break

                if container_name:
                    check_cmd = (
                        f"docker ps -f name={container_name} --format '{{{{.Status}}}}' 2>&1"
                    )
                else:
                    check_cmd = "docker ps -l --format '{{.Status}} {{.Names}}' 2>&1"
            elif "stop" in cmd_lower or "rm" in cmd_lower:
                check_cmd = "docker ps -a -l --format '{{.Status}} {{.Names}}' 2>&1"

        elif "nginx" in cmd_lower and "-t" in cmd_lower:
            check_cmd = "nginx -t 2>&1"

        elif "apt" in cmd_lower or "apt-get" in cmd_lower:
            # Check for recent apt errors
            check_cmd = "tail -3 /var/log/apt/term.log 2>/dev/null || echo 'ok'"

        # Run the check command if we have one
        if check_cmd:
            try:
                result = subprocess.run(
                    check_cmd, shell=True, capture_output=True, text=True, timeout=5
                )

                output = result.stdout + result.stderr

                # Check for error indicators in the output
                error_indicators = [
                    "failed",
                    "error",
                    "not found",
                    "inactive",
                    "dead",
                    "could not",
                    "unable",
                    "denied",
                    "cannot",
                    "exited",
                    "not running",
                    "not loaded",
                ]

                has_error = any(ind in output.lower() for ind in error_indicators)

                if has_error or result.returncode != 0:
                    error_output = output

            except (subprocess.TimeoutExpired, Exception):
                pass

        # If we found an error, mark the command and process it with auto-fix
        if error_output:
            console.print("         [dim]checking...[/dim]")
            # Mark this command as having an error
            with self._lock:
                for obs in self._commands_observed:
                    if obs["command"] == command:
                        obs["has_error"] = True
                        obs["status"] = "failed"
                        break
            self._process_observed_command_with_output(command, error_output, "live_terminal_check")
        else:
            # Mark as success if check passed
            with self._lock:
                for obs in self._commands_observed:
                    if obs["command"] == command and obs["status"] == "pending":
                        obs["status"] = "success"
                        break

    def _show_realtime_feedback(self, command: str, source: str):
        """Show real-time visual feedback for detected commands."""
        if not self._show_live_output:
            return

        from rich.panel import Panel
        from rich.text import Text

        # Source icons and labels
        source_info = {
            "cursor": ("🖥️", "Cursor IDE", "cyan"),
            "external": ("🌐", "External Terminal", "blue"),
            "tmux": ("📺", "Tmux", "magenta"),
            "bash": ("📝", "Bash", "green"),
            "zsh": ("📝", "Zsh", "green"),
            "fish": ("🐟", "Fish", "yellow"),
        }

        # Determine source type
        icon, label, color = "📝", "Terminal", "white"
        for key, (i, l, c) in source_info.items():
            if key in source.lower():
                icon, label, color = i, l, c
                break

        # Categorize command
        cmd_category = self._categorize_command(command)
        category_icons = {
            "docker": "🐳",
            "git": "📦",
            "apt": "📦",
            "pip": "🐍",
            "npm": "📦",
            "systemctl": "⚙️",
            "service": "⚙️",
            "sudo": "🔐",
            "ssh": "🔗",
            "curl": "🌐",
            "wget": "⬇️",
            "mkdir": "📁",
            "rm": "🗑️",
            "cp": "📋",
            "mv": "📋",
            "cat": "📄",
            "vim": "📝",
            "nano": "📝",
            "nginx": "🌐",
            "python": "🐍",
            "node": "📗",
        }
        cmd_icon = category_icons.get(cmd_category, "▶")

        # Format timestamp
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        # Store in buffer for later reference
        self._output_buffer.append(
            {
                "timestamp": timestamp,
                "source": source,
                "label": label,
                "icon": icon,
                "color": color,
                "command": command,
                "cmd_icon": cmd_icon,
            }
        )

        # Print real-time feedback with bordered section
        analysis = self._analyze_command(command)

        # Build command display
        cmd_text = Text()
        cmd_text.append(f"{cmd_icon} ", style="bold")
        cmd_text.append(command, style="bold white")
        if analysis:
            cmd_text.append(f"\n   {analysis}", style="dim italic")

        console.print()
        console.print(
            Panel(
                cmd_text,
                title=f"[dim]{timestamp}[/dim]",
                title_align="right",
                border_style="blue",
                padding=(0, 1),
            )
        )

    def _categorize_command(self, command: str) -> str:
        """Categorize a command by its base command."""
        cmd_parts = command.split()
        if not cmd_parts:
            return "unknown"

        base = cmd_parts[0]
        if base == "sudo" and len(cmd_parts) > 1:
            base = cmd_parts[1]

        return base.lower()

    def _analyze_command(self, command: str) -> str | None:
        """Analyze a command and return a brief description using LLM or patterns."""
        cmd_lower = command.lower()

        # First try pattern matching for speed
        patterns = [
            (r"docker run", "Starting a Docker container"),
            (r"docker pull", "Pulling a Docker image"),
            (r"docker ps", "Listing Docker containers"),
            (r"docker exec", "Executing command in container"),
            (r"docker build", "Building Docker image"),
            (r"docker stop", "Stopping container"),
            (r"docker rm", "Removing container"),
            (r"git clone", "Cloning a repository"),
            (r"git pull", "Pulling latest changes"),
            (r"git push", "Pushing changes"),
            (r"git commit", "Committing changes"),
            (r"git status", "Checking repository status"),
            (r"apt install", "Installing package via apt"),
            (r"apt update", "Updating package list"),
            (r"pip install", "Installing Python package"),
            (r"npm install", "Installing Node.js package"),
            (r"systemctl start", "Starting a service"),
            (r"systemctl stop", "Stopping a service"),
            (r"systemctl restart", "Restarting a service"),
            (r"systemctl status", "Checking service status"),
            (r"nginx -t", "Testing Nginx configuration"),
            (r"curl", "Making HTTP request"),
            (r"wget", "Downloading file"),
            (r"ssh", "SSH connection"),
            (r"mkdir", "Creating directory"),
            (r"rm -rf", "Removing files/directories recursively"),
            (r"cp ", "Copying files"),
            (r"mv ", "Moving/renaming files"),
            (r"chmod", "Changing file permissions"),
            (r"chown", "Changing file ownership"),
        ]

        for pattern, description in patterns:
            if re.search(pattern, cmd_lower):
                return description

        # Use LLM for unknown commands
        if self._llm and self._use_llm and self._llm.is_available():
            return self._llm_analyze_command(command)

        return None

    def _llm_analyze_command(self, command: str) -> str | None:
        """Use local LLM to analyze a command."""
        if not self._llm:
            return None

        prompt = f"""Analyze this Linux command and respond with ONLY a brief description (max 10 words) of what it does:

Command: {command}

Brief description:"""

        try:
            result = self._llm.analyze(prompt, max_tokens=30, timeout=5)
            if result:
                # Clean up the response
                result = result.strip().strip('"').strip("'")
                # Take only first line
                result = result.split("\n")[0].strip()
                # Limit length
                if len(result) > 60:
                    result = result[:57] + "..."
                return result
        except Exception:
            pass

        return None

    def _check_command_issues(self, command: str) -> str | None:
        """Check if a command has potential issues and return a warning."""
        issues = []

        if any(p in command for p in ["/etc/", "/var/", "/usr/"]):
            if not command.startswith("sudo") and not command.startswith("cat"):
                issues.append("May need sudo for system files")

        if "rm -rf /" in command:
            issues.append("DANGER: Destructive command detected!")

        typo_checks = {
            "sudp": "sudo",
            "suod": "sudo",
            "cta": "cat",
            "mdir": "mkdir",
            "mkidr": "mkdir",
        }
        for typo, correct in typo_checks.items():
            if command.startswith(typo + " "):
                issues.append(f"Typo? Did you mean '{correct}'?")

        return "; ".join(issues) if issues else None
