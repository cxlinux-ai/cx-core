"""
Cortex Linux Branding Module

Provides consistent visual branding across all Cortex CLI output.
Uses Rich library for cross-platform terminal styling.
"""

from rich.console import Console
from rich.panel import Panel

console = Console()

# Brand colors
CORTEX_CYAN = "cyan"
CORTEX_DARK = "dark_cyan"

# ASCII Logo - matches the CX circular logo
LOGO_LARGE = """
[bold cyan]   ██████╗██╗  ██╗[/bold cyan]
[bold cyan]  ██╔════╝╚██╗██╔╝[/bold cyan]
[bold cyan]  ██║      ╚███╔╝ [/bold cyan]
[bold cyan]  ██║      ██╔██╗ [/bold cyan]
[bold cyan]  ╚██████╗██╔╝ ██╗[/bold cyan]
[bold cyan]   ╚═════╝╚═╝  ╚═╝[/bold cyan]
"""

LOGO_SMALL = """[bold cyan]╔═╗─┐ ┬[/bold cyan]
[bold cyan]║  ┌┴┬┘[/bold cyan]
[bold cyan]╚═╝┴ └─[/bold cyan]"""

# Version info
VERSION = "0.1.0"


def show_banner(show_version: bool = True):
    """
    Display the full Cortex banner.
    Called on first run or with --version flag.
    """
    content = LOGO_LARGE + "\n"
    content += "[dim]CortexLinux[/dim] [white]• AI-Powered Package Manager[/white]"

    if show_version:
        content += f"\n[dim]v{VERSION}[/dim]"

    console.print(Panel(content, border_style="cyan", padding=(0, 2)))


def cx_print(message: str, status: str = "info"):
    """
    Print a message with the CX badge prefix.
    Like Claude's orange icon, but for Cortex.

    Args:
        message: The message to display
        status: One of "info", "success", "warning", "error", "thinking"
    """
    badge = "[bold white on dark_cyan] CX [/bold white on dark_cyan]"

    status_icons = {
        "info": "[dim]│[/dim]",
        "success": "[green]✓[/green]",
        "warning": "[yellow]⚠[/yellow]",
        "error": "[red]✗[/red]",
        "thinking": "[cyan]⠋[/cyan]",  # Spinner frame
    }

    icon = status_icons.get(status, status_icons["info"])
    console.print(f"{badge} {icon} {message}")


def cx_step(step_num: int, total: int, message: str):
    """
    Print a numbered step with the CX badge.

    Example: CX │ [1/4] Updating package lists...
    """
    badge = "[bold white on dark_cyan] CX [/bold white on dark_cyan]"
    console.print(f"{badge} [dim]│[/dim] [{step_num}/{total}] {message}")


def cx_header(title: str):
    """
    Print a section header.
    """
    console.print()
    console.print(f"[bold cyan]━━━ {title} ━━━[/bold cyan]")
    console.print()


def cx_table_header():
    """
    Returns styled header for package tables.
    """
    return (
        "[bold cyan]Package[/bold cyan]",
        "[bold cyan]Version[/bold cyan]",
        "[bold cyan]Action[/bold cyan]",
    )


def show_welcome():
    """
    First-run welcome message.
    """
    show_banner()
    console.print()
    cx_print("Welcome to Cortex! Let's get you set up.", "success")
    cx_print("Run [bold]cortex wizard[/bold] to configure your API key.", "info")
    console.print()


def show_goodbye():
    """
    Exit message.
    """
    console.print()
    cx_print("Done! Run [bold]cortex --help[/bold] for more commands.", "info")
    console.print()


# Demo
if __name__ == "__main__":
    # Full banner
    show_banner()
    print()

    # Simulated operation flow
    cx_print("Understanding request...", "thinking")
    cx_print("Planning installation...", "info")
    cx_header("Installation Plan")

    cx_print("docker.io (24.0.5) — Container runtime", "info")
    cx_print("docker-compose (2.20.2) — Multi-container orchestration", "info")

    print()
    cx_step(1, 4, "Updating package lists...")
    cx_step(2, 4, "Installing docker.io...")
    cx_step(3, 4, "Installing docker-compose...")
    cx_step(4, 4, "Configuring services...")

    print()
    cx_print("Installation complete!", "success")
    cx_print("Docker is ready to use.", "info")
