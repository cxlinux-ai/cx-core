"""
Stdin Piping Support for Log Analysis

Issue: #271 - Stdin Piping Support for Log Analysis

Enables Unix-style piping of data to Cortex commands.
Examples:
    docker logs | cortex analyze
    git diff | cortex summarize
    cat error.log | cortex find errors
"""

import select
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console()


class TruncationMode(Enum):
    """How to handle large stdin input."""

    HEAD = "head"  # Keep first N lines
    TAIL = "tail"  # Keep last N lines
    MIDDLE = "middle"  # Keep head and tail, truncate middle
    SAMPLE = "sample"  # Sample lines throughout


@dataclass
class StdinData:
    """Container for stdin data with metadata."""

    content: str
    line_count: int
    byte_count: int
    was_truncated: bool = False
    original_line_count: int = 0
    original_byte_count: int = 0

    @property
    def is_empty(self) -> bool:
        """Check if stdin was empty."""
        return self.byte_count == 0


class StdinHandler:
    """Handles reading and processing stdin data."""

    DEFAULT_MAX_LINES = 1000
    DEFAULT_MAX_BYTES = 100 * 1024  # 100KB
    TIMEOUT_SECONDS = 0.1

    def __init__(
        self,
        max_lines: int = DEFAULT_MAX_LINES,
        max_bytes: int = DEFAULT_MAX_BYTES,
        truncation_mode: TruncationMode = TruncationMode.MIDDLE,
    ):
        """Initialize the stdin handler.

        Args:
            max_lines: Maximum number of lines to keep
            max_bytes: Maximum bytes to keep
            truncation_mode: How to truncate large input
        """
        self.max_lines = max_lines
        self.max_bytes = max_bytes
        self.truncation_mode = truncation_mode

    def has_stdin_data(self) -> bool:
        """Check if stdin has data available.

        Returns:
            True if stdin has data or is a pipe/file, False if interactive terminal
        """
        # Check if stdin is a terminal (interactive)
        if sys.stdin.isatty():
            return False

        # On Unix, check if there's data available
        try:
            readable, _, _ = select.select([sys.stdin], [], [], self.TIMEOUT_SECONDS)
            return bool(readable)
        except (ValueError, OSError):
            # select not available or stdin closed
            # If not a tty, assume there might be data
            return True

    def read_stdin(self) -> StdinData:
        """Read all available stdin data.

        Returns:
            StdinData containing the input and metadata
        """
        if sys.stdin.isatty():
            return StdinData(content="", line_count=0, byte_count=0)

        try:
            content = sys.stdin.read()
        except OSError:
            return StdinData(content="", line_count=0, byte_count=0)

        lines = content.splitlines(keepends=True)
        byte_count = len(content.encode("utf-8", errors="replace"))

        return StdinData(
            content=content,
            line_count=len(lines),
            byte_count=byte_count,
            original_line_count=len(lines),
            original_byte_count=byte_count,
        )

    def truncate(self, data: StdinData) -> StdinData:
        """Truncate stdin data if it exceeds limits.

        Args:
            data: Original stdin data

        Returns:
            Truncated StdinData
        """
        if data.line_count <= self.max_lines and data.byte_count <= self.max_bytes:
            return data

        lines = data.content.splitlines(keepends=True)

        if self.truncation_mode == TruncationMode.HEAD:
            truncated_lines = lines[: self.max_lines]
        elif self.truncation_mode == TruncationMode.TAIL:
            truncated_lines = lines[-self.max_lines :]
        elif self.truncation_mode == TruncationMode.MIDDLE:
            half = self.max_lines // 2
            head = lines[:half]
            tail = lines[-half:]
            skipped = len(lines) - self.max_lines
            truncated_lines = head + [f"\n... [{skipped} lines truncated] ...\n\n"] + tail
        else:  # SAMPLE
            step = max(1, len(lines) // self.max_lines)
            truncated_lines = lines[::step][: self.max_lines]

        content = "".join(truncated_lines)

        # Check byte limit
        content_bytes = content.encode("utf-8", errors="replace")
        if len(content_bytes) > self.max_bytes:
            content = content_bytes[: self.max_bytes].decode("utf-8", errors="replace")
            content += "\n... [truncated due to size limit] ..."

        new_lines = content.splitlines(keepends=True)

        return StdinData(
            content=content,
            line_count=len(new_lines),
            byte_count=len(content.encode("utf-8", errors="replace")),
            was_truncated=True,
            original_line_count=data.original_line_count,
            original_byte_count=data.original_byte_count,
        )

    def read_and_truncate(self) -> StdinData:
        """Read stdin and apply truncation if needed.

        Returns:
            Processed StdinData
        """
        data = self.read_stdin()
        if data.is_empty:
            return data
        return self.truncate(data)

    @staticmethod
    def get_input(prompt: str = "") -> str:
        """Get interactive input from stdin safely.

        Args:
            prompt: Prompt text to display

        Returns:
            Input string or empty string on cancellation
        """
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return ""


def detect_content_type(content: str) -> str:
    """Detect the type of content from stdin.

    Args:
        content: The stdin content

    Returns:
        Detected content type string
    """
    if not content or not content.strip():
        return "empty"

    lines = content.strip().split("\n")
    if not lines:
        return "empty"

    first_line = lines[0].lower()

    # Log patterns
    log_patterns = [
        ("error", "error_log"),
        ("warn", "warning_log"),
        ("info", "info_log"),
        ("[error]", "error_log"),
        ("[warn]", "warning_log"),
        ("[info]", "info_log"),
        ("exception", "error_log"),
        ("traceback", "python_traceback"),
    ]

    for pattern, content_type in log_patterns:
        if pattern in first_line or any(pattern in line.lower() for line in lines[:10]):
            return content_type

    # Git patterns
    if first_line.startswith("diff --git"):
        return "git_diff"
    if first_line.startswith("commit ") and len(first_line.split()) == 2:
        return "git_log"
    if "@@" in content and ("+" in content or "-" in content):
        return "unified_diff"

    # JSON
    if first_line.startswith("{") or first_line.startswith("["):
        return "json"

    # CSV
    if (
        "," in first_line and lines[0].count(",") == lines[1].count(",")
        if len(lines) > 1
        else False
    ):
        return "csv"

    # Docker/container logs
    if any(pattern in content for pattern in ["container", "docker", "kubernetes", "pod"]):
        return "container_log"

    # System logs
    if any(pattern in content for pattern in ["systemd", "journald", "kernel", "syslog"]):
        return "system_log"

    return "text"


def analyze_stdin(
    data: StdinData,
    action: str = "analyze",
    verbose: bool = False,
) -> dict:
    """Analyze stdin content and return structured results.

    Args:
        data: Stdin data to analyze
        action: Type of analysis to perform
        verbose: Enable verbose output

    Returns:
        Analysis results dictionary
    """
    content = data.content
    lines = content.splitlines()

    result = {
        "line_count": data.line_count,
        "byte_count": data.byte_count,
        "was_truncated": data.was_truncated,
        "content_type": detect_content_type(content),
        "analysis": {},
    }

    # Content-specific analysis
    content_type = result["content_type"]

    if content_type == "error_log":
        errors = [l for l in lines if "error" in l.lower()]
        result["analysis"]["error_count"] = len(errors)
        result["analysis"]["sample_errors"] = errors[:5]

    elif content_type == "git_diff":
        additions = len([l for l in lines if l.startswith("+")])
        deletions = len([l for l in lines if l.startswith("-")])
        files = len([l for l in lines if l.startswith("diff --git")])
        result["analysis"]["files_changed"] = files
        result["analysis"]["additions"] = additions
        result["analysis"]["deletions"] = deletions

    elif content_type == "json":
        import json as json_lib

        try:
            parsed = json_lib.loads(content)
            if isinstance(parsed, list):
                result["analysis"]["type"] = "array"
                result["analysis"]["length"] = len(parsed)
            elif isinstance(parsed, dict):
                result["analysis"]["type"] = "object"
                result["analysis"]["keys"] = list(parsed.keys())[:10]
        except json_lib.JSONDecodeError:
            result["analysis"]["parse_error"] = True

    return result


def display_stdin_info(data: StdinData, analysis: dict | None = None):
    """Display information about stdin data.

    Args:
        data: Stdin data
        analysis: Optional analysis results
    """
    # Info table
    table = Table(show_header=False, box=None)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Lines", str(data.line_count))
    table.add_row("Bytes", f"{data.byte_count:,}")

    if data.was_truncated:
        table.add_row("Original Lines", str(data.original_line_count))
        table.add_row("Original Bytes", f"{data.original_byte_count:,}")
        table.add_row("Status", "[yellow]Truncated[/yellow]")

    if analysis:
        table.add_row("Content Type", analysis.get("content_type", "unknown"))

        if "analysis" in analysis:
            for key, value in analysis["analysis"].items():
                if isinstance(value, list):
                    value = f"{len(value)} items"
                table.add_row(key.replace("_", " ").title(), str(value))

    console.print(Panel(table, title="[bold cyan]Stdin Data[/bold cyan]"))

    # Preview
    if data.content:
        preview_lines = data.content.splitlines()[:20]
        preview = "\n".join(preview_lines)
        if len(data.content.splitlines()) > 20:
            preview += "\n..."

        console.print()
        console.print("[bold]Preview:[/bold]")
        console.print(Syntax(preview, "text", line_numbers=True, word_wrap=True))


def run_stdin_handler(
    action: str = "info",
    max_lines: int = StdinHandler.DEFAULT_MAX_LINES,
    truncation: str = "middle",
    verbose: bool = False,
) -> int:
    """Run the stdin handler.

    Args:
        action: Action to perform (info, analyze, passthrough)
        max_lines: Maximum lines to process
        truncation: Truncation mode (head, tail, middle, sample)
        verbose: Enable verbose output

    Returns:
        Exit code (0 for success)
    """
    # Map truncation string to enum
    truncation_map = {
        "head": TruncationMode.HEAD,
        "tail": TruncationMode.TAIL,
        "middle": TruncationMode.MIDDLE,
        "sample": TruncationMode.SAMPLE,
    }
    truncation_mode = truncation_map.get(truncation, TruncationMode.MIDDLE)

    handler = StdinHandler(
        max_lines=max_lines,
        truncation_mode=truncation_mode,
    )

    # Check for stdin data
    if not handler.has_stdin_data():
        console.print("[yellow]No stdin data detected[/yellow]")
        console.print("\nUsage examples:")
        console.print("  [dim]docker logs container | cortex stdin analyze[/dim]")
        console.print("  [dim]git diff | cortex stdin info[/dim]")
        console.print("  [dim]cat error.log | cortex stdin --max-lines 500[/dim]")
        return 0

    # Read and process stdin
    data = handler.read_and_truncate()

    if data.is_empty:
        console.print("[yellow]Stdin was empty[/yellow]")
        return 0

    if action == "info":
        analysis = analyze_stdin(data)
        display_stdin_info(data, analysis)
        return 0

    elif action == "analyze":
        analysis = analyze_stdin(data, verbose=verbose)
        display_stdin_info(data, analysis)

        # Detailed analysis
        if analysis["content_type"] != "text":
            console.print()
            console.print(
                Panel(
                    f"Content type: [bold]{analysis['content_type']}[/bold]",
                    title="Analysis",
                )
            )

        return 0

    elif action == "passthrough":
        # Just output the (possibly truncated) content
        console.print(data.content, end="")
        return 0

    elif action == "stats":
        # Machine-readable stats
        analysis = analyze_stdin(data)
        import json

        print(json.dumps(analysis, indent=2))
        return 0

    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Available actions: info, analyze, passthrough, stats")
        return 1
