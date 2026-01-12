"""
Terminal UI branding and styling for Intelligent Tutor.

Provides Rich console utilities following Cortex Linux patterns.
"""

from typing import Literal, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

# Global Rich console instance
console = Console()

# Status type definitions
StatusType = Literal["success", "error", "info", "warning", "tutor", "question"]

# Status emoji and color mappings
STATUS_CONFIG = {
    "success": {"emoji": "[green]\u2713[/green]", "color": "green"},
    "error": {"emoji": "[red]\u2717[/red]", "color": "red"},
    "info": {"emoji": "[blue]\u2139[/blue]", "color": "blue"},
    "warning": {"emoji": "[yellow]\u26a0[/yellow]", "color": "yellow"},
    "tutor": {"emoji": "[cyan]\U0001f393[/cyan]", "color": "cyan"},
    "question": {"emoji": "[magenta]?[/magenta]", "color": "magenta"},
}


def tutor_print(message: str, status: StatusType = "info") -> None:
    """
    Print a formatted message with status indicator.

    Args:
        message: The message to display.
        status: Status type for styling (success, error, info, warning, tutor, question).

    Example:
        >>> tutor_print("Lesson completed!", "success")
        >>> tutor_print("An error occurred", "error")
    """
    config = STATUS_CONFIG.get(status, STATUS_CONFIG["info"])
    emoji = config["emoji"]
    color = config["color"]
    console.print(f"{emoji} [{color}]{message}[/{color}]")


def print_banner() -> None:
    """
    Print the Intelligent Tutor welcome banner.

    Displays a styled ASCII art banner with version info.
    """
    banner_text = """
[bold cyan]  ___       _       _ _ _                  _     _____      _
 |_ _|_ __ | |_ ___| | (_) __ _  ___ _ __ | |_  |_   _|   _| |_ ___  _ __
  | || '_ \\| __/ _ \\ | | |/ _` |/ _ \\ '_ \\| __|   | || | | | __/ _ \\| '__|
  | || | | | ||  __/ | | | (_| |  __/ | | | |_    | || |_| | || (_) | |
 |___|_| |_|\\__\\___|_|_|_|\\__, |\\___|_| |_|\\__|   |_| \\__,_|\\__\\___/|_|
                          |___/[/bold cyan]
    """
    console.print(banner_text)
    console.print("[dim]AI-Powered Package Tutor for Cortex Linux[/dim]")
    console.print()


def print_lesson_header(package_name: str) -> None:
    """
    Print a styled lesson header for a package.

    Args:
        package_name: Name of the package being taught.
    """
    header = Panel(
        f"[bold cyan]\U0001f393 {package_name} Tutorial[/bold cyan]",
        border_style="cyan",
        padding=(0, 2),
    )
    console.print(header)
    console.print()


def print_menu(options: list[str], title: str = "Select an option") -> None:
    """
    Print a numbered menu of options.

    Args:
        options: List of menu options to display.
        title: Title for the menu.
    """
    console.print(f"\n[bold]{title}[/bold]")
    for i, option in enumerate(options, 1):
        console.print(f"   [cyan]{i}.[/cyan] {option}")
    console.print()


def print_code_example(code: str, language: str = "python", title: str | None = None) -> None:
    """
    Print a syntax-highlighted code block.

    Args:
        code: The code to display.
        language: Programming language for syntax highlighting.
        title: Optional title for the code block.
    """
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    if title:
        console.print(f"\n[bold]{title}[/bold]")
    console.print(syntax)
    console.print()


def print_best_practice(practice: str, index: int) -> None:
    """
    Print a styled best practice item.

    Args:
        practice: The best practice text.
        index: Index number of the practice.
    """
    console.print(f"  [green]\u2713[/green] [bold]{index}.[/bold] {practice}")


def print_tutorial_step(step: str, step_number: int, total_steps: int) -> None:
    """
    Print a tutorial step with progress indicator.

    Args:
        step: The step description.
        step_number: Current step number.
        total_steps: Total number of steps.
    """
    progress_bar = "\u2588" * step_number + "\u2591" * (total_steps - step_number)
    console.print(f"\n[dim][{progress_bar}] Step {step_number}/{total_steps}[/dim]")
    console.print(f"[bold cyan]\u25b6[/bold cyan] {step}")


def print_progress_summary(completed: int, total: int, package_name: str) -> None:
    """
    Print a progress summary for a package.

    Args:
        completed: Number of completed topics.
        total: Total number of topics.
        package_name: Name of the package.
    """
    percentage = (completed / total * 100) if total > 0 else 0
    bar_filled = int(percentage / 5)
    bar_empty = 20 - bar_filled
    progress_bar = "[green]\u2588[/green]" * bar_filled + "[dim]\u2591[/dim]" * bar_empty

    console.print(f"\n[bold]{package_name} Progress[/bold]")
    console.print(f"  {progress_bar} {percentage:.0f}%")
    console.print(f"  [dim]{completed}/{total} topics completed[/dim]")


def print_table(headers: list[str], rows: list[list[str]], title: str = "") -> None:
    """
    Print a formatted table.

    Args:
        headers: Column headers.
        rows: Table rows (list of lists).
        title: Optional table title.
    """
    table = Table(title=title, show_header=True, header_style="bold cyan")

    for header in headers:
        table.add_column(header)

    for row in rows:
        table.add_row(*row)

    console.print(table)
    console.print()


def print_markdown(content: str) -> None:
    """
    Print markdown-formatted content.

    Args:
        content: Markdown text to render.
    """
    md = Markdown(content)
    console.print(md)


def get_user_input(prompt: str, default: str | None = None) -> str:
    """
    Get user input with optional default value.

    Args:
        prompt: The prompt to display.
        default: Optional default value.

    Returns:
        str: User input or default value.
    """
    if default:
        prompt_text = f"[bold cyan]{prompt}[/bold cyan] [dim]({default})[/dim]: "
    else:
        prompt_text = f"[bold cyan]{prompt}[/bold cyan]: "

    try:
        response = console.input(prompt_text)
        return response.strip() or default or ""
    except (EOFError, KeyboardInterrupt):
        console.print()
        tutor_print("Operation cancelled", "info")
        return ""


def create_progress_bar(_description: str = "Processing") -> Progress:
    """
    Create a Rich progress bar for long-running operations.

    Args:
        _description: Description text for the progress bar (reserved for future use).

    Returns:
        Progress: Configured Rich Progress instance.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def print_error_panel(error_message: str, title: str = "Error") -> None:
    """
    Print an error message in a styled panel.

    Args:
        error_message: The error message to display.
        title: Panel title.
    """
    panel = Panel(
        f"[red]{error_message}[/red]",
        title=f"[bold red]{title}[/bold red]",
        border_style="red",
    )
    console.print(panel)


def print_success_panel(message: str, title: str = "Success") -> None:
    """
    Print a success message in a styled panel.

    Args:
        message: The success message to display.
        title: Panel title.
    """
    panel = Panel(
        f"[green]{message}[/green]",
        title=f"[bold green]{title}[/bold green]",
        border_style="green",
    )
    console.print(panel)
