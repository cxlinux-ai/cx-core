"""Natural language query interface for Cortex.

Handles user questions about installed packages, configurations,
and system state using LLM with semantic caching. Also provides
educational content and tracks learning progress.
"""

import atexit
import json
import logging
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cortex.config_utils import get_ollama_model

# Module logger for debug diagnostics
logger = logging.getLogger(__name__)

# Maximum number of tokens to request from LLM
MAX_TOKENS = 2000

# Cortex Terminal Theme Colors - Dracula-Inspired
_CORTEX_BG = "#282a36"  # Dracula background
_CORTEX_FG = "#f8f8f2"  # Dracula foreground
_CORTEX_PURPLE = "#bd93f9"  # Dracula purple
_CORTEX_CURSOR = "#ff79c6"  # Dracula pink for cursor
_ORIGINAL_COLORS_SAVED = False

# Available Themes
THEMES = {
    "dracula": {
        "name": "Dracula",
        "bg": "#282a36",
        "fg": "#f8f8f2",
        "cursor": "#ff79c6",
        "primary": "#bd93f9",
        "secondary": "#ff79c6",
        "success": "#50fa7b",
        "warning": "#f1fa8c",
        "error": "#ff5555",
        "info": "#8be9fd",
        "muted": "#6272a4",
    },
    "nord": {
        "name": "Nord",
        "bg": "#2e3440",
        "fg": "#eceff4",
        "cursor": "#88c0d0",
        "primary": "#81a1c1",
        "secondary": "#88c0d0",
        "success": "#a3be8c",
        "warning": "#ebcb8b",
        "error": "#bf616a",
        "info": "#5e81ac",
        "muted": "#4c566a",
    },
    "monokai": {
        "name": "Monokai",
        "bg": "#272822",
        "fg": "#f8f8f2",
        "cursor": "#f92672",
        "primary": "#ae81ff",
        "secondary": "#f92672",
        "success": "#a6e22e",
        "warning": "#e6db74",
        "error": "#f92672",
        "info": "#66d9ef",
        "muted": "#75715e",
    },
    "gruvbox": {
        "name": "Gruvbox",
        "bg": "#282828",
        "fg": "#ebdbb2",
        "cursor": "#fe8019",
        "primary": "#b8bb26",
        "secondary": "#fe8019",
        "success": "#b8bb26",
        "warning": "#fabd2f",
        "error": "#fb4934",
        "info": "#83a598",
        "muted": "#928374",
    },
    "catppuccin": {
        "name": "Catppuccin Mocha",
        "bg": "#1e1e2e",
        "fg": "#cdd6f4",
        "cursor": "#f5c2e7",
        "primary": "#cba6f7",
        "secondary": "#f5c2e7",
        "success": "#a6e3a1",
        "warning": "#f9e2af",
        "error": "#f38ba8",
        "info": "#89b4fa",
        "muted": "#6c7086",
    },
    "tokyo-night": {
        "name": "Tokyo Night",
        "bg": "#1a1b26",
        "fg": "#c0caf5",
        "cursor": "#bb9af7",
        "primary": "#7aa2f7",
        "secondary": "#bb9af7",
        "success": "#9ece6a",
        "warning": "#e0af68",
        "error": "#f7768e",
        "info": "#7dcfff",
        "muted": "#565f89",
    },
}

# Current active theme
_CURRENT_THEME = "dracula"


def get_current_theme() -> dict:
    """Get the current active theme colors."""
    return THEMES.get(_CURRENT_THEME, THEMES["dracula"])


def set_theme(theme_name: str) -> bool:
    """Set the active theme by name."""
    global _CURRENT_THEME, _CORTEX_BG, _CORTEX_FG, _CORTEX_CURSOR

    if theme_name not in THEMES:
        return False

    _CURRENT_THEME = theme_name
    theme = THEMES[theme_name]
    _CORTEX_BG = theme["bg"]
    _CORTEX_FG = theme["fg"]
    _CORTEX_CURSOR = theme["cursor"]

    # Apply theme to terminal
    _set_terminal_theme()
    return True


def show_theme_selector() -> str | None:
    """Show interactive theme selector with arrow key navigation.

    Returns:
        Selected theme name or None if cancelled
    """
    import sys
    import termios
    import tty

    theme_list = list(THEMES.keys())
    current_idx = theme_list.index(_CURRENT_THEME) if _CURRENT_THEME in theme_list else 0
    num_themes = len(theme_list)

    # ANSI codes
    CLEAR_LINE = "\033[2K"
    MOVE_UP = "\033[A"
    HIDE_CURSOR = "\033[?25l"
    SHOW_CURSOR = "\033[?25h"

    # Colors (ANSI)
    PURPLE = "\033[38;2;189;147;249m"
    PINK = "\033[38;2;255;121;198m"
    GRAY = "\033[38;2;108;112;134m"
    WHITE = "\033[38;2;248;248;242m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def get_key():
        """Get a single keypress."""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":
                        return "up"
                    elif ch3 == "B":
                        return "down"
                return "esc"
            elif ch == "\r" or ch == "\n":
                return "enter"
            elif ch == "q" or ch == "\x03":
                return "quit"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def get_theme_color(theme, color_type):
        """Get ANSI color code for theme color."""
        hex_color = theme.get(color_type, "#ffffff")
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return f"\033[38;2;{r};{g};{b}m"

    def draw_menu():
        """Draw the menu."""
        # Header
        print(
            f"\r{CLEAR_LINE}   {PURPLE}{BOLD}◉{RESET} {PINK}{BOLD}Select Theme{RESET} {GRAY}(↑/↓ navigate, Enter select, q cancel){RESET}"
        )
        print(f"\r{CLEAR_LINE}")

        # Theme options
        for idx, theme_key in enumerate(theme_list):
            theme = THEMES[theme_key]
            primary = get_theme_color(theme, "primary")
            secondary = get_theme_color(theme, "secondary")
            success = get_theme_color(theme, "success")
            error = get_theme_color(theme, "error")

            if idx == current_idx:
                print(
                    f"\r{CLEAR_LINE}   {primary}→ {BOLD}{theme['name']}{RESET}  {primary}■{secondary}■{success}■{error}■{RESET}"
                )
            else:
                print(f"\r{CLEAR_LINE}     {GRAY}{theme['name']}{RESET}")

        print(f"\r{CLEAR_LINE}")

    def clear_menu():
        """Move cursor up and clear all menu lines."""
        total_lines = num_themes + 3  # header + blank + themes + blank
        for _ in range(total_lines):
            sys.stdout.write(f"{MOVE_UP}{CLEAR_LINE}")
        sys.stdout.flush()

    # Initial draw
    try:
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()
        print()  # Initial blank line
        draw_menu()

        while True:
            key = get_key()

            if key == "up":
                current_idx = (current_idx - 1) % num_themes
                clear_menu()
                draw_menu()
            elif key == "down":
                current_idx = (current_idx + 1) % num_themes
                clear_menu()
                draw_menu()
            elif key == "enter":
                clear_menu()
                sys.stdout.write(SHOW_CURSOR)
                sys.stdout.flush()
                return theme_list[current_idx]
            elif key == "quit" or key == "esc":
                clear_menu()
                sys.stdout.write(SHOW_CURSOR)
                sys.stdout.flush()
                return None
    except Exception:
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()
        return None
    finally:
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()


def _set_terminal_theme():
    """Set terminal colors to Dracula-inspired theme using OSC escape sequences."""
    global _ORIGINAL_COLORS_SAVED

    # Only works on terminals that support OSC sequences (most modern terminals)
    if not sys.stdout.isatty():
        return

    try:
        # Set background color (OSC 11) - Dracula dark
        sys.stdout.write(f"\033]11;{_CORTEX_BG}\007")
        # Set foreground color (OSC 10) - Dracula light
        sys.stdout.write(f"\033]10;{_CORTEX_FG}\007")
        # Set cursor color to pink (OSC 12)
        sys.stdout.write(f"\033]12;{_CORTEX_CURSOR}\007")
        sys.stdout.flush()

        _ORIGINAL_COLORS_SAVED = True

        # Register cleanup to restore colors on exit
        atexit.register(_restore_terminal_theme)
    except Exception:
        pass  # Silently fail if terminal doesn't support escape sequences


def _restore_terminal_theme():
    """Restore terminal to default colors."""
    global _ORIGINAL_COLORS_SAVED

    if not _ORIGINAL_COLORS_SAVED or not sys.stdout.isatty():
        return

    try:
        # Reset to terminal defaults
        sys.stdout.write("\033]110\007")  # Reset foreground to default
        sys.stdout.write("\033]111\007")  # Reset background to default
        sys.stdout.write("\033]112\007")  # Reset cursor to default
        sys.stdout.flush()

        _ORIGINAL_COLORS_SAVED = False
    except Exception:
        pass


def _print_cortex_banner():
    """Print a Cortex session banner with Dracula-inspired styling."""
    if not sys.stdout.isatty():
        return

    from rich.console import Console
    from rich.padding import Padding
    from rich.panel import Panel
    from rich.text import Text

    # Dracula colors
    PURPLE = "#bd93f9"
    PINK = "#ff79c6"
    CYAN = "#8be9fd"
    GRAY = "#6272a4"

    console = Console()

    # Build banner content
    banner_text = Text()
    banner_text.append("◉ CORTEX", style=f"bold {PINK}")
    banner_text.append(" AI-Powered Terminal Session\n", style=CYAN)
    banner_text.append("Type your request • ", style=GRAY)
    banner_text.append("Ctrl+C to exit", style=GRAY)

    # Create panel with fixed width
    panel = Panel(
        banner_text,
        border_style=PURPLE,
        padding=(0, 1),
        width=45,  # Fixed width
    )

    # Fixed left margin of 3
    padded_panel = Padding(panel, (0, 0, 0, 3))

    console.print()
    console.print(padded_panel)
    console.print()


class SystemInfoGatherer:
    """Gathers local system information for context-aware responses."""

    @staticmethod
    def get_python_version() -> str:
        """Get installed Python version."""
        return platform.python_version()

    @staticmethod
    def get_python_path() -> str:
        """Get Python executable path."""
        import sys

        return sys.executable

    @staticmethod
    def get_os_info() -> dict[str, str]:
        """Get OS information."""
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        }

    @staticmethod
    def get_installed_package(package: str) -> str | None:
        """Check if a package is installed via apt and return version."""
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f=${Version}", package],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            # If dpkg-query is unavailable or fails, return None silently.
            # We avoid user-visible logs to keep CLI output clean.
            pass
        return None

    @staticmethod
    def get_pip_package(package: str) -> str | None:
        """Check if a Python package is installed via pip."""
        try:
            result = subprocess.run(
                ["pip3", "show", package],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("Version:"):
                        return line.split(":", 1)[1].strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            # If pip is unavailable or the command fails, return None silently.
            pass
        return None

    @staticmethod
    def check_command_exists(cmd: str) -> bool:
        """Check if a command exists in PATH."""
        return shutil.which(cmd) is not None

    @staticmethod
    def get_gpu_info() -> dict[str, Any]:
        """Get GPU information if available."""
        gpu_info: dict[str, Any] = {"available": False, "nvidia": False, "cuda": None}

        # Check for nvidia-smi
        if shutil.which("nvidia-smi"):
            gpu_info["nvidia"] = True
            gpu_info["available"] = True
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    gpu_info["model"] = result.stdout.strip().split(",")[0]
            except (subprocess.SubprocessError, FileNotFoundError):
                # If nvidia-smi is unavailable or fails, keep defaults.
                pass

            # Check CUDA version
            try:
                result = subprocess.run(
                    ["nvcc", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if "release" in line.lower():
                            parts = line.split("release")
                            if len(parts) > 1:
                                gpu_info["cuda"] = parts[1].split(",")[0].strip()
            except (subprocess.SubprocessError, FileNotFoundError):
                # If nvcc is unavailable or fails, leave CUDA info unset.
                pass

        return gpu_info

    def gather_context(self) -> dict[str, Any]:
        """Gather relevant system context for LLM."""
        return {
            "python_version": self.get_python_version(),
            "python_path": self.get_python_path(),
            "os": self.get_os_info(),
            "gpu": self.get_gpu_info(),
        }


class LearningTracker:
    """Tracks educational topics the user has explored."""

    _progress_file: Path | None = None

    # Patterns that indicate educational questions
    EDUCATIONAL_PATTERNS = [
        r"^explain\b",
        r"^teach\s+me\b",
        r"^what\s+is\b",
        r"^what\s+are\b",
        r"^how\s+does\b",
        r"^how\s+do\b",
        r"^how\s+to\b",
        r"\bbest\s+practices?\b",
        r"^tutorial\b",
        r"^guide\s+to\b",
        r"^learn\s+about\b",
        r"^introduction\s+to\b",
        r"^basics\s+of\b",
    ]

    # Compiled patterns shared across all instances for efficiency
    _compiled_patterns: list[re.Pattern[str]] = [
        re.compile(p, re.IGNORECASE) for p in EDUCATIONAL_PATTERNS
    ]

    def __init__(self) -> None:
        """Initialize the learning tracker.

        Uses pre-compiled educational patterns for efficient matching
        across multiple queries. Patterns are shared as class variables
        to avoid recompilation overhead.
        """

    @property
    def progress_file(self) -> Path:
        """Lazily compute the progress file path to avoid import-time errors."""
        if self._progress_file is None:
            try:
                self._progress_file = Path.home() / ".cortex" / "learning_history.json"
            except RuntimeError:
                # Fallback for restricted environments where home is inaccessible
                import tempfile

                self._progress_file = (
                    Path(tempfile.gettempdir()) / ".cortex" / "learning_history.json"
                )
        return self._progress_file

    def is_educational_query(self, question: str) -> bool:
        """Determine if a question is educational in nature."""
        return any(pattern.search(question) for pattern in self._compiled_patterns)

    def extract_topic(self, question: str) -> str:
        """Extract the main topic from an educational question."""
        # Remove common prefixes
        topic = question.lower()
        prefixes_to_remove = [
            r"^explain\s+",
            r"^teach\s+me\s+about\s+",
            r"^teach\s+me\s+",
            r"^what\s+is\s+",
            r"^what\s+are\s+",
            r"^how\s+does\s+",
            r"^how\s+do\s+",
            r"^how\s+to\s+",
            r"^tutorial\s+on\s+",
            r"^guide\s+to\s+",
            r"^learn\s+about\s+",
            r"^introduction\s+to\s+",
            r"^basics\s+of\s+",
            r"^best\s+practices\s+for\s+",
        ]
        for prefix in prefixes_to_remove:
            topic = re.sub(prefix, "", topic, flags=re.IGNORECASE)

        # Clean up and truncate
        topic = topic.strip("? ").strip()

        # Truncate at word boundaries to keep topic identifier meaningful
        # If topic exceeds 50 chars, truncate at the last space within those 50 chars
        # to preserve whole words. If the first 50 chars contain no spaces,
        # keep the full 50-char prefix.
        if len(topic) > 50:
            truncated = topic[:50]
            # Try to split at word boundary; keep full 50 chars if no spaces found
            words = truncated.rsplit(" ", 1)
            # Handle case where topic starts with space after prefix removal
            topic = words[0] if words[0] else truncated

        return topic

    def record_topic(self, question: str) -> None:
        """Record that the user explored an educational topic.

        Note: This method performs a read-modify-write cycle on the history file
        without file locking. If multiple cortex ask processes run concurrently,
        concurrent updates could theoretically be lost. This is acceptable for a
        single-user CLI tool where concurrent invocations are rare and learning
        history is non-critical, but worth noting for future enhancements.
        """
        if not self.is_educational_query(question):
            return

        topic = self.extract_topic(question)
        if not topic:
            return

        history = self._load_history()
        if not isinstance(history, dict):
            history = {"topics": {}, "total_queries": 0}

        # Ensure history has expected structure (defensive defaults for malformed data)
        history.setdefault("topics", {})
        history.setdefault("total_queries", 0)
        if not isinstance(history.get("topics"), dict):
            history["topics"] = {}

        # Ensure total_queries is an integer
        if not isinstance(history.get("total_queries"), int):
            try:
                history["total_queries"] = int(history["total_queries"])
            except (ValueError, TypeError):
                history["total_queries"] = 0

        # Use UTC timestamps for consistency and accurate sorting
        utc_now = datetime.now(timezone.utc).isoformat()

        # Update or add topic
        if topic in history["topics"]:
            # Check if the topic data is actually a dict before accessing it
            if not isinstance(history["topics"][topic], dict):
                # If topic data is malformed, reinitialize it
                history["topics"][topic] = {
                    "count": 1,
                    "first_accessed": utc_now,
                    "last_accessed": utc_now,
                }
            else:
                try:
                    # Safely increment count, handle missing key
                    history["topics"][topic]["count"] = history["topics"][topic].get("count", 0) + 1
                    history["topics"][topic]["last_accessed"] = utc_now
                except (KeyError, TypeError, AttributeError):
                    # If topic data is malformed, reinitialize it
                    history["topics"][topic] = {
                        "count": 1,
                        "first_accessed": utc_now,
                        "last_accessed": utc_now,
                    }
        else:
            history["topics"][topic] = {
                "count": 1,
                "first_accessed": utc_now,
                "last_accessed": utc_now,
            }

        history["total_queries"] = history.get("total_queries", 0) + 1
        self._save_history(history)

    def get_history(self) -> dict[str, Any]:
        """Get the learning history."""
        return self._load_history()

    def get_recent_topics(self, limit: int = 5) -> list[str]:
        """Get recently explored topics."""
        history = self._load_history()
        topics = history.get("topics", {})

        # Filter out malformed entries and sort by last_accessed
        valid_topics = [
            (name, data)
            for name, data in topics.items()
            if isinstance(data, dict) and "last_accessed" in data
        ]
        sorted_topics = sorted(
            valid_topics,
            key=lambda x: x[1].get("last_accessed", ""),
            reverse=True,
        )
        return [t[0] for t in sorted_topics[:limit]]

    def _load_history(self) -> dict[str, Any]:
        """Load learning history from file."""
        if not self.progress_file.exists():
            return {"topics": {}, "total_queries": 0}

        try:
            with open(self.progress_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"topics": {}, "total_queries": 0}

    def _save_history(self, history: dict[str, Any]) -> None:
        """Save learning history to file.

        Silently handles save failures to keep CLI clean, but logs at debug level
        for diagnostics. Failures may occur due to permission issues or disk space.
        """
        try:
            self.progress_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.progress_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except OSError as e:
            # Log at debug level to help diagnose permission/disk issues
            # without breaking CLI output or crashing the application
            logger.debug(
                f"Failed to save learning history to {self.progress_file}: {e}",
                exc_info=False,
            )


class AskHandler:
    """Handles natural language questions about the system."""

    def __init__(
        self,
        api_key: str,
        provider: str = "claude",
        model: str | None = None,
        do_mode: bool = False,
    ):
        """Initialize the ask handler.

        Args:
            api_key: API key for the LLM provider
            provider: Provider name ("openai", "claude", or "ollama")
            model: Optional model name override
            do_mode: If True, enable execution mode with do_runner
        """
        self.api_key = api_key
        self.provider = provider.lower()
        self.model = model or self._default_model()
        self.info_gatherer = SystemInfoGatherer()
        self.learning_tracker = LearningTracker()
        self.do_mode = do_mode

        # Initialize do_handler if in do_mode
        self._do_handler = None
        if do_mode:
            try:
                from cortex.do_runner.handler import DoHandler

                # Create LLM callback for DoHandler
                self._do_handler = DoHandler(llm_callback=self._do_llm_callback)
            except ImportError:
                pass

        # Initialize cache
        try:
            from cortex.semantic_cache import SemanticCache

            self.cache: SemanticCache | None = SemanticCache()
        except (ImportError, OSError):
            self.cache = None

        self._initialize_client()

    def _default_model(self) -> str:
        if self.provider == "openai":
            return "gpt-4"
        elif self.provider == "claude":
            return "claude-sonnet-4-20250514"
        elif self.provider == "ollama":
            return self._get_ollama_model()
        elif self.provider == "fake":
            return "fake"
        return "gpt-4"

    def _get_ollama_model(self) -> str:
        """Determine which Ollama model to use.

        Delegates to the shared ``get_ollama_model()`` utility function.
        """
        return get_ollama_model()

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

    def _do_llm_callback(self, request: str, context: dict | None = None) -> dict:
        """LLM callback for DoHandler - generates structured do_commands responses."""
        system_prompt = self._get_do_system_prompt()

        # Build context string if provided
        context_str = ""
        if context:
            context_str = f"\n\nContext:\n{json.dumps(context, indent=2)}"

        full_prompt = f"{request}{context_str}"

        try:
            if self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": full_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=MAX_TOKENS,
                )
                content = response.choices[0].message.content or ""
            elif self.provider == "claude":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    temperature=0.3,
                    system=system_prompt,
                    messages=[{"role": "user", "content": full_prompt}],
                )
                content = response.content[0].text or ""
            elif self.provider == "ollama":
                import urllib.request

                url = f"{self.ollama_url}/api/generate"
                prompt = f"{system_prompt}\n\nRequest: {full_prompt}"
                data = json.dumps(
                    {
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": MAX_TOKENS},
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    content = result.get("response", "")
            else:
                return {"response_type": "error", "error": f"Unsupported provider: {self.provider}"}

            # Parse JSON from response
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                return json.loads(json_match.group())

            # If no JSON, return as answer
            return {"response_type": "answer", "answer": content.strip()}

        except Exception as e:
            return {"response_type": "error", "error": str(e)}

    def _get_do_system_prompt(self) -> str:
        """Get system prompt for do_mode - generates structured commands."""
        return """You are a Linux system automation assistant. Your job is to translate user requests into executable shell commands.

RESPONSE FORMAT - You MUST respond with valid JSON in one of these formats:

For actionable requests (install, configure, run, etc.):
{
    "response_type": "do_commands",
    "reasoning": "Brief explanation of what you're going to do",
    "do_commands": [
        {
            "command": "the actual shell command",
            "purpose": "what this command does",
            "requires_sudo": true/false
        }
    ]
}

For informational requests or when you cannot generate commands:
{
    "response_type": "answer",
    "answer": "Your response text here"
}

RULES:
1. Generate safe, well-tested commands
2. Set requires_sudo: true for commands that need root privileges
3. Break complex tasks into multiple commands
4. For package installation, use apt on Debian/Ubuntu
5. Include verification commands when appropriate
6. NEVER include dangerous commands (rm -rf /, etc.)
7. Always respond with valid JSON only - no extra text"""

    def _handle_do_request(self, question: str) -> str:
        """Handle a request in do_mode - generates and executes commands.

        Args:
            question: The user's request

        Returns:
            Summary of what was done or the answer
        """
        from rich.console import Console
        from rich.padding import Padding
        from rich.panel import Panel
        from rich.prompt import Confirm
        from rich.text import Text

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

        # Icons (round/circle based)
        ICON_THINKING = "◐"
        ICON_PLAN = "◉"
        ICON_CMD = "❯"
        ICON_SUCCESS = "●"
        ICON_ERROR = "●"
        ICON_ARROW = "→"
        ICON_LOCK = "◉"

        console = Console()

        # Fixed layout constants
        LEFT_MARGIN = 3
        INDENT = "   "
        BOX_WIDTH = 70  # Fixed box width

        def print_padded(text: str) -> None:
            """Print text with left margin."""
            console.print(f"{INDENT}{text}")

        def print_panel(content, **kwargs) -> None:
            """Print a panel with fixed width and left margin."""
            panel = Panel(content, width=BOX_WIDTH, **kwargs)
            padded = Padding(panel, (0, 0, 0, LEFT_MARGIN))
            console.print(padded)

        # Processing indicator
        console.print()
        print_padded(
            f"[{PURPLE}]{ICON_THINKING}[/{PURPLE}] [{PURPLE_LIGHT}]Analyzing results... Step 1[/{PURPLE_LIGHT}]"
        )
        console.print()

        llm_response = self._do_llm_callback(question)

        if not llm_response:
            print_panel(
                f"[{RED}]{ICON_ERROR} I couldn't process that request. Please try again.[/{RED}]",
                border_style=RED,
                padding=(0, 2),
            )
            return ""

        response_type = llm_response.get("response_type", "")

        # If it's just an answer (informational), return it in a panel
        if response_type == "answer":
            answer = llm_response.get("answer", "No response generated.")
            print_panel(
                f"[{WHITE}]{answer}[/{WHITE}]",
                border_style=PURPLE,
                title=f"[bold {PURPLE_LIGHT}]{ICON_SUCCESS} Answer[/bold {PURPLE_LIGHT}]",
                title_align="left",
                padding=(0, 2),
            )
            return ""

        # If it's an error, return the error message in a panel
        if response_type == "error":
            print_panel(
                f"[{RED}]{llm_response.get('error', 'Unknown error')}[/{RED}]",
                border_style=RED,
                title=f"[bold {RED}]{ICON_ERROR} Error[/bold {RED}]",
                title_align="left",
                padding=(0, 2),
            )
            return ""

        # Handle do_commands - execute with confirmation
        if response_type == "do_commands" and llm_response.get("do_commands"):
            do_commands = llm_response["do_commands"]
            reasoning = llm_response.get("reasoning", "")

            # Show reasoning
            if reasoning:
                print_panel(
                    f"[{WHITE}]{reasoning}[/{WHITE}]",
                    border_style=PURPLE,
                    title=f"[bold {PURPLE_LIGHT}]{ICON_PLAN} Gathering info[/bold {PURPLE_LIGHT}]",
                    title_align="left",
                    padding=(0, 2),
                )
                console.print()

            # Build commands list
            commands_text = Text()
            for i, cmd_info in enumerate(do_commands, 1):
                cmd = cmd_info.get("command", "")
                purpose = cmd_info.get("purpose", "")
                needs_sudo = cmd_info.get("requires_sudo", False)

                # Number and lock icon
                if needs_sudo:
                    commands_text.append(f"  {ICON_LOCK} ", style=YELLOW)
                else:
                    commands_text.append(f"  {ICON_CMD} ", style=PURPLE)

                commands_text.append(f"{i}. ", style=f"bold {WHITE}")
                commands_text.append(f"{cmd}\n", style=f"bold {PURPLE_LIGHT}")
                if purpose:
                    commands_text.append(f"     {ICON_ARROW} ", style=GRAY)
                    commands_text.append(f"{purpose}\n", style=GRAY)
                commands_text.append("\n")

            print_panel(
                commands_text,
                border_style=PURPLE,
                title=f"[bold {PURPLE_LIGHT}]Commands[/bold {PURPLE_LIGHT}]",
                title_align="left",
                padding=(0, 2),
            )
            console.print()

            if not Confirm.ask(
                f"{INDENT}[{PURPLE}]Execute these commands?[/{PURPLE}]", default=True
            ):
                console.print()
                print_padded(f"[{YELLOW}]{ICON_ERROR} Skipped by user[/{YELLOW}]")
                return ""

            # Execute header
            console.print()
            print_padded(f"[{PURPLE_LIGHT}]Executing...[/{PURPLE_LIGHT}]")

            results = []
            for idx, cmd_info in enumerate(do_commands, 1):
                cmd = cmd_info.get("command", "")
                purpose = cmd_info.get("purpose", "Execute command")
                needs_sudo = cmd_info.get("requires_sudo", False)

                # Show step indicator
                console.print()
                print_padded(
                    f"[{PURPLE_LIGHT}]Analyzing results... Step {idx + 1}[/{PURPLE_LIGHT}]"
                )
                console.print()

                # Build command display
                cmd_text = Text()
                cmd_text.append(f"  {ICON_CMD} ", style=PURPLE)
                cmd_text.append(f"{cmd}", style=f"bold {PURPLE_LIGHT}")

                # Show command panel
                print_panel(
                    cmd_text,
                    border_style=PURPLE_DARK,
                    title=f"[{GRAY}]{ICON_PLAN} Gathering info[/{GRAY}]",
                    title_align="left",
                    padding=(0, 2),
                )

                # Show spinner while executing
                with console.status(f"[{PURPLE}]Running...[/{PURPLE}]", spinner="dots") as status:
                    # Execute via DoHandler if available
                    if self._do_handler:
                        success, stdout, stderr = self._do_handler._execute_single_command(
                            cmd, needs_sudo
                        )
                    else:
                        # Fallback to direct subprocess
                        import subprocess

                        try:
                            exec_cmd = cmd
                            if needs_sudo and not cmd.startswith("sudo"):
                                exec_cmd = f"sudo {cmd}"
                            result = subprocess.run(
                                exec_cmd, shell=True, capture_output=True, text=True, timeout=120
                            )
                            success = result.returncode == 0
                            stdout = result.stdout.strip()
                            stderr = result.stderr.strip()
                        except Exception as e:
                            success = False
                            stdout = ""
                            stderr = str(e)

                if success:
                    if stdout:
                        output_lines = stdout.split("\n")
                        line_count = len(output_lines)
                        truncated_lines = output_lines[:8]  # Show up to 8 lines

                        # Build output text
                        output_text = Text()
                        for line in truncated_lines:
                            if line.strip():
                                # Truncate long lines at 80 chars
                                display_line = line[:80] + ("..." if len(line) > 80 else "")
                                output_text.append(f"{display_line}\n", style=WHITE)

                        console.print()
                        print_padded(
                            f"[{GREEN}]{ICON_SUCCESS} Got {line_count} lines of output[/{GREEN}]"
                        )
                        console.print()

                        print_panel(
                            output_text,
                            border_style=PURPLE_DARK,
                            title=f"[{GRAY}]Output[/{GRAY}]",
                            title_align="left",
                            padding=(0, 2),
                        )
                    else:
                        print_padded(f"[{GREEN}]{ICON_SUCCESS} Command succeeded[/{GREEN}]")

                    results.append(("success", cmd, stdout))
                else:
                    console.print()
                    print_padded(f"[{YELLOW}]⚠ Command failed:[/{YELLOW}]")
                    if stderr:
                        # Wrap error message
                        error_text = stderr[:200] + ("..." if len(stderr) > 200 else "")
                        print_padded(f"  [{GRAY}]{error_text}[/{GRAY}]")
                    results.append(("failed", cmd, stderr))

            # Generate LLM-based summary
            console.print()
            return self._generate_execution_summary(question, results, do_commands)

        # Default fallback
        return self._format_answer(llm_response.get("answer", "Request processed."))

    def _generate_execution_summary(
        self, question: str, results: list, commands: list[dict]
    ) -> str:
        """Generate a comprehensive summary after command execution.

        Args:
            question: The original user request
            results: List of (status, command, output/error) tuples
            commands: The original command list with purposes

        Returns:
            Formatted summary with answer
        """
        success_count = sum(1 for r in results if r[0] == "success")
        fail_count = len(results) - success_count

        # Build execution results for LLM - include actual outputs!
        execution_results = []
        for i, result in enumerate(results):
            cmd_info = commands[i] if i < len(commands) else {}
            status = "✓" if result[0] == "success" else "✗"
            entry = {
                "command": result[1],
                "purpose": cmd_info.get("purpose", ""),
                "status": status,
            }
            # Include command output (truncate to reasonable size)
            if len(result) > 2 and result[2]:
                if result[0] == "success":
                    entry["output"] = result[2][:1000]  # Include successful output
                else:
                    entry["error"] = result[2][:500]  # Include error message
            execution_results.append(entry)

        # Generate LLM summary with command outputs
        summary_prompt = f"""The user asked: "{question}"

The following commands were executed with their outputs:
"""
        for i, entry in enumerate(execution_results, 1):
            summary_prompt += f"\n{i}. [{entry['status']}] {entry['command']}"
            if entry.get("purpose"):
                summary_prompt += f"\n   Purpose: {entry['purpose']}"
            if entry.get("output"):
                summary_prompt += f"\n   Output:\n{entry['output']}"
            if entry.get("error"):
                summary_prompt += f"\n   Error: {entry['error']}"

        summary_prompt += f"""

Execution Summary: {success_count} succeeded, {fail_count} failed.

IMPORTANT: You MUST extract and report the ACTUAL DATA from the command outputs above.
DO NOT give a generic summary like "commands ran successfully" or "I checked your disk usage".

Instead, give the user the REAL ANSWER with SPECIFIC VALUES from the output. For example:
- If they asked about disk usage, tell them: "Your root partition is 45% full (67GB used of 150GB)"
- If they asked about memory, tell them: "You have 8.2GB RAM in use out of 16GB total"
- If they asked about a service status, tell them: "nginx is running (active) since 2 days ago"

Extract the key numbers, percentages, sizes, statuses from the command outputs and present them clearly.

Respond with just the answer containing the actual data, no JSON."""

        try:
            # Call LLM for summary
            if self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful assistant that summarizes command execution results concisely.",
                        },
                        {"role": "user", "content": summary_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=500,
                )
                summary = response.choices[0].message.content or ""
            elif self.provider == "claude":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=500,
                    temperature=0.3,
                    system="You are a helpful assistant that summarizes command execution results concisely.",
                    messages=[{"role": "user", "content": summary_prompt}],
                )
                summary = response.content[0].text or ""
            elif self.provider == "ollama":
                import urllib.request

                url = f"{self.ollama_url}/api/generate"
                data = json.dumps(
                    {
                        "model": self.model,
                        "prompt": f"Summarize concisely:\n{summary_prompt}",
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 500},
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    summary = result.get("response", "")
            else:
                summary = ""

            if summary.strip():
                return self._format_answer(summary.strip())
        except Exception:
            pass  # Fall back to basic summary

        # Fallback basic summary
        if fail_count == 0:
            return self._format_answer(
                f"✅ Successfully completed your request. All {success_count} command(s) executed successfully."
            )
        else:
            return self._format_answer(
                f"Completed with issues: {success_count} command(s) succeeded, {fail_count} failed. Check the output above for details."
            )

    def _format_answer(self, answer: str) -> str:
        """Format the final answer with a clear summary section in Dracula theme.

        Args:
            answer: The answer text

        Returns:
            Empty string (output is printed directly to console)
        """
        from rich.console import Console
        from rich.padding import Padding
        from rich.panel import Panel

        # Dracula Theme Colors
        PURPLE = "#bd93f9"
        WHITE = "#f8f8f2"
        GREEN = "#50fa7b"
        ICON_SUCCESS = "●"

        console = Console()

        if not answer:
            answer = "Request completed."

        # Create panel with fixed width
        panel = Panel(
            f"[{WHITE}]{answer}[/{WHITE}]",
            border_style=PURPLE,
            title=f"[bold {GREEN}]{ICON_SUCCESS} Summary[/bold {GREEN}]",
            title_align="left",
            padding=(0, 2),
            width=70,  # Fixed width
        )

        # Add left margin
        padded = Padding(panel, (0, 0, 0, 3))

        console.print()
        console.print(padded)
        console.print()

        return ""

    def _get_system_prompt(self, context: dict[str, Any]) -> str:
        return f"""You are a helpful Linux system assistant and tutor. You help users with both system-specific questions AND educational queries about Linux, packages, and best practices.

System Context:
{json.dumps(context, indent=2)}

**Query Type Detection**

Automatically detect the type of question and respond appropriately:

**Educational Questions (tutorials, explanations, learning)**

Triggered by questions like: "explain...", "teach me...", "how does X work", "what is...", "best practices for...", "tutorial on...", "learn about...", "guide to..."

For educational questions:
1. Provide structured, tutorial-style explanations
2. Include practical code examples with proper formatting
3. Highlight best practices and common pitfalls to avoid
4. Break complex topics into digestible sections
5. Use clear section labels and bullet points for readability
6. Mention related topics the user might want to explore next
7. Tailor examples to the user's system when relevant (e.g., use apt for Debian-based systems)

**Diagnostic Questions (system-specific, troubleshooting)**

Triggered by questions about: current system state, "why is my...", "what packages...", "check my...", specific errors, system status

For diagnostic questions:
1. Analyze the provided system context
2. Give specific, actionable answers
3. Be concise but informative
4. If you don't have enough information, say so clearly

**Output Formatting Rules (CRITICAL - Follow exactly)**

1. NEVER use markdown headings (# or ##) - they render poorly in terminals
2. For section titles, use **Bold Text** on its own line instead
3. Use bullet points (-) for lists
4. Use numbered lists (1. 2. 3.) for sequential steps
5. Use triple backticks with language name for code blocks (```bash)
6. Use *italic* sparingly for emphasis
7. Keep lines under 100 characters when possible
8. Add blank lines between sections for readability
9. For tables, use simple text formatting, not markdown tables

Example of good formatting:
**Installation Steps**

1. Update your package list:
```bash
sudo apt update
```

2. Install the package:
```bash
sudo apt install nginx
```

**Key Points**
- Point one here
- Point two here"""

    def _call_openai(self, question: str, system_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.3,
            max_tokens=MAX_TOKENS,
        )
        # Defensive: content may be None or choices could be empty in edge cases
        try:
            content = response.choices[0].message.content or ""
        except (IndexError, AttributeError):
            content = ""
        return content.strip()

    def _call_claude(self, question: str, system_prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            temperature=0.3,
            system=system_prompt,
            messages=[{"role": "user", "content": question}],
        )
        # Defensive: content list or text may be missing/None
        try:
            text = getattr(response.content[0], "text", None) or ""
        except (IndexError, AttributeError):
            text = ""
        return text.strip()

    def _call_ollama(self, question: str, system_prompt: str) -> str:
        import urllib.error
        import urllib.request

        url = f"{self.ollama_url}/api/generate"
        prompt = f"{system_prompt}\n\nQuestion: {question}"

        data = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": MAX_TOKENS},
            }
        ).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("response", "").strip()

    def _call_fake(self, question: str, system_prompt: str) -> str:
        """Return predefined fake response for testing."""
        fake_response = os.environ.get("CORTEX_FAKE_RESPONSE", "")
        if fake_response:
            return fake_response
        # Default fake responses for common questions
        q_lower = question.lower()
        if "python" in q_lower and "version" in q_lower:
            return f"You have Python {platform.python_version()} installed."
        return "I cannot answer that question in test mode."

    def ask(self, question: str, system_prompt: str | None = None) -> str:
        """Ask a natural language question about the system.

        Args:
            question: Natural language question
            system_prompt: Optional override for the system prompt

        Returns:
            Human-readable answer string

        Raises:
            ValueError: If question is empty
            RuntimeError: If offline and no cached response exists
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        question = question.strip()

        # In do_mode, use DoHandler for command execution
        if self.do_mode and self._do_handler:
            return self._handle_do_request(question)

        # Use provided system prompt or generate default
        if system_prompt is None:
            context = self.info_gatherer.gather_context()
            system_prompt = self._get_system_prompt(context)

        # Cache lookup uses both question and system context (via system_prompt) for system-specific answers
        cache_key = f"ask:{question}"

        # Try cache first
        if self.cache is not None:
            cached = self.cache.get_commands(
                prompt=cache_key,
                provider=self.provider,
                model=self.model,
                system_prompt=system_prompt,
            )
            if cached is not None and len(cached) > 0:
                # Track topic access even for cached responses
                self.learning_tracker.record_topic(question)
                return cached[0]

        # Call LLM
        try:
            if self.provider == "openai":
                answer = self._call_openai(question, system_prompt)
            elif self.provider == "claude":
                answer = self._call_claude(question, system_prompt)
            elif self.provider == "ollama":
                answer = self._call_ollama(question, system_prompt)
            elif self.provider == "fake":
                answer = self._call_fake(question, system_prompt)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
        except Exception as e:
            raise RuntimeError(f"LLM API call failed: {str(e)}")

        # Cache the response silently
        if self.cache is not None and answer:
            try:
                self.cache.put_commands(
                    prompt=cache_key,
                    provider=self.provider,
                    model=self.model,
                    system_prompt=system_prompt,
                    commands=[answer],
                )
            except (OSError, sqlite3.Error):
                pass  # Silently fail cache writes

        # Track educational topics for learning history
        self.learning_tracker.record_topic(question)

        return answer

    def get_learning_history(self) -> dict[str, Any]:
        """Get the user's learning history.

        Returns:
            Dictionary with topics explored and statistics
        """
        return self.learning_tracker.get_history()

    def get_recent_topics(self, limit: int = 5) -> list[str]:
        """Get recently explored educational topics.

        Args:
            limit: Maximum number of topics to return

        Returns:
            List of topic strings
        """
        return self.learning_tracker.get_recent_topics(limit)
