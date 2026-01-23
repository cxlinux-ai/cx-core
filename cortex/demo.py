"""Interactive demo for Cortex Linux."""

import subprocess
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from cortex.branding import show_banner

console = Console()


def _run_cortex_command(args: list[str], capture: bool = False) -> tuple[int, str]:
    """Run a cortex command and return exit code and output."""
    cmd = ["cortex"] + args
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr
    else:
        result = subprocess.run(cmd)
        return result.returncode, ""


def _wait_for_enter():
    """Wait for user to press enter."""
    console.print("\n[dim]Press Enter to continue...[/dim]")
    input()


def _section(title: str, problem: str):
    """Display a compact section header."""
    console.print(f"\n[bold cyan]{'─' * 50}[/bold cyan]")
    console.print(f"[bold white]{title}[/bold white]")
    console.print(f"[dim]{problem}[/dim]\n")


def run_demo() -> int:
    """Run the interactive Cortex demo."""
    console.clear()
    show_banner()

    # ─────────────────────────────────────────────────────────────────
    # INTRODUCTION
    # ─────────────────────────────────────────────────────────────────

    intro = """
**Cortex** - The AI-native package manager for Linux.

In this demo you'll try:
• **Ask** - Query your system in natural language
• **Install** - Install packages with AI interpretation
• **Rollback** - Undo installations safely
"""
    console.print(Panel(Markdown(intro), title="[cyan]Demo[/cyan]", border_style="cyan"))
    _wait_for_enter()

    # ─────────────────────────────────────────────────────────────────
    # ASK COMMAND
    # ─────────────────────────────────────────────────────────────────

    _section("🔍 Ask Command", "Query your system without memorizing Linux commands.")

    console.print("[dim]Examples: 'What Python version?', 'How much disk space?'[/dim]\n")

    user_question = Prompt.ask(
        "[cyan]What would you like to ask?[/cyan]", default="What version of Python is installed?"
    )

    console.print(f'\n[yellow]$[/yellow] cortex ask "{user_question}"\n')
    _run_cortex_command(["ask", user_question])

    _wait_for_enter()

    # ─────────────────────────────────────────────────────────────────
    # INSTALL COMMAND
    # ─────────────────────────────────────────────────────────────────

    _section("📦 Install Command", "Describe what you want - Cortex finds the right packages.")

    console.print("[dim]Examples: 'a web server', 'python dev tools', 'docker'[/dim]\n")

    user_install = Prompt.ask(
        "[cyan]What would you like to install?[/cyan]", default="a lightweight text editor"
    )

    console.print(f'\n[yellow]$[/yellow] cortex install "{user_install}" --dry-run\n')
    _run_cortex_command(["install", user_install, "--dry-run"])

    console.print()
    if Confirm.ask("Actually install this?", default=False):
        console.print(f'\n[yellow]$[/yellow] cortex install "{user_install}" --execute\n')
        _run_cortex_command(["install", user_install, "--execute"])

    _wait_for_enter()

    # ─────────────────────────────────────────────────────────────────
    # ROLLBACK COMMAND
    # ─────────────────────────────────────────────────────────────────

    _section("⏪ Rollback Command", "Undo any installation by reverting to the previous state.")

    console.print("[dim]First, let's see your installation history with IDs:[/dim]\n")
    console.print("[yellow]$[/yellow] cortex history --limit 5\n")
    _run_cortex_command(["history", "--limit", "5"])

    _wait_for_enter()

    if Confirm.ask("Preview a rollback?", default=False):
        console.print("\n[cyan]Copy an installation ID from the history above:[/cyan]")
        console.print("[dim]$ cortex rollback [/dim]", end="")
        rollback_id = input().strip()

        if rollback_id:
            console.print(f"\n[yellow]$[/yellow] cortex rollback {rollback_id} --dry-run\n")
            _run_cortex_command(["rollback", rollback_id, "--dry-run"])

            if Confirm.ask("Actually rollback?", default=False):
                console.print(f"\n[yellow]$[/yellow] cortex rollback {rollback_id}\n")
                _run_cortex_command(["rollback", rollback_id])

    # ─────────────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────────────

    console.print(f"\n[bold cyan]{'─' * 50}[/bold cyan]")
    console.print("[bold green]✓ Demo Complete![/bold green]\n")
    console.print("[dim]Commands: ask, install, history, rollback, stack, status[/dim]")
    console.print("[dim]Run 'cortex --help' for more.[/dim]\n")

    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
