"""
Cortex Interactive Demo
Interactive 5-minute tutorial showcasing all major Cortex features
"""

import secrets
import sys
import time
from datetime import datetime, timedelta

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cortex.branding import show_banner
from cortex.hardware_detection import SystemInfo, detect_hardware


class CortexDemo:
    """Interactive Cortex demonstration"""

    def __init__(self) -> None:
        self.console = Console()
        self.hw: SystemInfo | None = None
        self.is_interactive = sys.stdin.isatty()
        self.installation_id = self._generate_id()

    def clear_screen(self) -> None:
        """Clears the terminal screen"""
        self.console.clear()

    def _generate_id(self) -> str:
        """Generate a fake installation ID for demo"""
        return secrets.token_hex(8)

    def _generate_past_date(self, days_ago: int, hours: int = 13, minutes: int = 11) -> str:
        """Generate a date string for N days ago"""
        past = datetime.now() - timedelta(days=days_ago)
        past = past.replace(hour=hours, minute=minutes, second=51)
        return past.strftime("%Y-%m-%d %H:%M:%S")

    def _is_gpu_vendor(self, model: str, keywords: list[str]) -> bool:
        """Check if GPU model matches any vendor keywords."""
        model_upper = str(model).upper()
        return any(kw in model_upper for kw in keywords)

    def run(self) -> int:
        """Main demo entry point"""
        try:
            self.clear_screen()
            show_banner()

            self.console.print("\n[bold cyan]🎬 Cortex Interactive Demo[/bold cyan]")
            self.console.print("[dim]Learn Cortex by typing real commands (~5 minutes)[/dim]\n")

            intro_text = """
Cortex is an AI-powered universal package manager that:

  • 🧠 [cyan]Understands natural language[/cyan] - No exact syntax needed
  • 🔍 [cyan]Plans before installing[/cyan] - Shows you what it will do first
  • 🔒 [cyan]Checks hardware compatibility[/cyan] - Prevents bad installs
  • 📦 [cyan]Works with all package managers[/cyan] - apt, brew, npm, pip...
  • 🎯 [cyan]Smart stacks[/cyan] - Pre-configured tool bundles
  • 🔄 [cyan]Safe rollback[/cyan] - Undo any installation

[bold]This is interactive - you'll type real commands![/bold]
[dim](Just type commands as shown - any input works for learning!)[/dim]
            """

            self.console.print(Panel(intro_text, border_style="cyan"))

            if not self._wait_for_user("\nPress Enter to start..."):
                return 0

            # Detect hardware for smart demos
            self.hw = detect_hardware()

            # Run all sections (now consolidated to 3)
            sections = [
                ("AI Intelligence & Understanding", self._section_ai_intelligence),
                ("Smart Stacks & Workflows", self._section_smart_stacks),
                ("History & Safety Features", self._section_history_safety),
            ]

            for i, (name, section_func) in enumerate(sections, 1):
                self.clear_screen()
                self.console.print(f"\n[dim]━━━ Section {i} of {len(sections)}: {name} ━━━[/dim]\n")

                if not section_func():
                    self.console.print(
                        "\n[yellow]Demo interrupted. Thanks for trying Cortex![/yellow]"
                    )
                    return 1

            # Show finale
            self.clear_screen()
            self._show_finale()

            return 0

        except (KeyboardInterrupt, EOFError):
            self.console.print(
                "\n\n[yellow]Demo interrupted. Thank you for trying Cortex![/yellow]"
            )
            return 1

    def _wait_for_user(self, message: str = "\nPress Enter to continue...") -> bool:
        """Wait for user input"""
        try:
            if self.is_interactive:
                self.console.print(f"[dim]{message}[/dim]")
                input()
            else:
                time.sleep(2)  # Auto-advance in non-interactive mode
            return True
        except (KeyboardInterrupt, EOFError):
            return False

    def _prompt_command(self, command: str) -> bool:
        """
        Prompt user to type a command.
        Re-prompts on empty input to ensure user provides something.
        """
        try:
            if self.is_interactive:
                while True:
                    self.console.print(f"\n[yellow]Try:[/yellow] [bold]{command}[/bold]")
                    self.console.print("\n[bold green]$[/bold green] ", end="")
                    user_input = input()

                    # If empty, re-prompt and give hint
                    if not user_input.strip():
                        self.console.print(
                            "[dim]Type the command above or anything else to continue[/dim]"
                        )
                        continue

                    break

                self.console.print("[green]✓[/green] [dim]Let's see what Cortex does...[/dim]\n")
            else:
                self.console.print(f"\n[yellow]Command:[/yellow] [bold]{command}[/bold]\n")
                time.sleep(1)

            return True
        except (KeyboardInterrupt, EOFError):
            return False

    def _simulate_cortex_output(self, packages: list[str], show_execution: bool = False) -> None:
        """Simulate real Cortex output with CX branding"""

        # Understanding phase
        with self.console.status("[cyan]CX[/cyan] Understanding request...", spinner="dots"):
            time.sleep(0.8)

        # Planning phase
        with self.console.status("[cyan]CX[/cyan] Planning installation...", spinner="dots"):
            time.sleep(1.0)

        pkg_str = " ".join(packages)
        self.console.print(f" [cyan]CX[/cyan]  │ Installing {pkg_str}...\n")
        time.sleep(0.5)

        # Show generated commands
        self.console.print("[bold]Generated commands:[/bold]")
        self.console.print("  1. [dim]sudo apt update[/dim]")

        for i, pkg in enumerate(packages, 2):
            self.console.print(f"  {i}. [dim]sudo apt install -y {pkg}[/dim]")

        if not show_execution:
            self.console.print(
                "\n[yellow]To execute these commands, run with --execute flag[/yellow]"
            )
            self.console.print("[dim]Example: cortex install docker --execute[/dim]\n")
        else:
            # Simulate execution
            self.console.print("\n[cyan]Executing commands...[/cyan]\n")
            time.sleep(0.5)

            total_steps = len(packages) + 1
            for step in range(1, total_steps + 1):
                self.console.print(f"[{step}/{total_steps}] ⏳ Step {step}")
                if step == 1:
                    self.console.print("  Command: [dim]sudo apt update[/dim]")
                else:
                    self.console.print(
                        f"  Command: [dim]sudo apt install -y {packages[step - 2]}[/dim]"
                    )
                time.sleep(0.8)
                self.console.print()

            self.console.print(
                f" [cyan]CX[/cyan]  [green]✓[/green] {pkg_str} installed successfully!\n"
            )

            # Show installation ID
            self.console.print(f"📝 Installation recorded (ID: {self.installation_id})")
            self.console.print(
                f"   To rollback: [cyan]cortex rollback {self.installation_id}[/cyan]\n"
            )

    def _section_ai_intelligence(self) -> bool:
        """Section 1: AI Intelligence - NLP, Planning, and Hardware Awareness"""
        self.console.print("[bold cyan]🧠 AI Intelligence & Understanding[/bold cyan]\n")

        # Part 1: Natural Language Understanding
        self.console.print("[bold]Part 1: Natural Language Understanding[/bold]")
        self.console.print(
            "Cortex understands what you [italic]mean[/italic], not just exact syntax."
        )
        self.console.print("Ask questions in plain English:\n")

        if not self._prompt_command('cortex ask "I need tools for Python web development"'):
            return False

        # Simulate AI response
        with self.console.status("[cyan]CX[/cyan] Understanding your request...", spinner="dots"):
            time.sleep(1.0)
        with self.console.status("[cyan]CX[/cyan] Analyzing requirements...", spinner="dots"):
            time.sleep(1.2)

        self.console.print(" [cyan]CX[/cyan]  [green]✓[/green] [dim]Recommendations ready[/dim]\n")
        time.sleep(0.5)

        # Show AI response
        response = """For Python web development on your system, here are the essential tools:

[bold]Web Frameworks:[/bold]
  • [cyan]FastAPI[/cyan] - Modern, fast framework with automatic API documentation
  • [cyan]Flask[/cyan] - Lightweight, flexible microframework
  • [cyan]Django[/cyan] - Full-featured framework with ORM and admin interface

[bold]Development Tools:[/bold]
  • [cyan]uvicorn[/cyan] - ASGI server for FastAPI
  • [cyan]gunicorn[/cyan] - WSGI server for production
  • [cyan]python3-venv[/cyan] - Virtual environments

Install a complete stack with: [cyan]cortex stack webdev[/cyan]
        """

        self.console.print(Panel(response, border_style="cyan", title="AI Response"))
        self.console.print()

        self.console.print("[bold green]💡 Key Feature:[/bold green]")
        self.console.print(
            "Cortex's AI [bold]understands intent[/bold] and provides smart recommendations.\n"
        )

        if not self._wait_for_user():
            return False

        # Part 2: Smart Planning
        self.console.print("\n[bold]Part 2: Transparent Planning[/bold]")
        self.console.print("Let's install Docker and Node.js together.")
        self.console.print("[dim]Cortex will show you the plan before executing anything.[/dim]")

        if not self._prompt_command('cortex install "docker nodejs"'):
            return False

        # Simulate the actual output
        self._simulate_cortex_output(["docker.io", "nodejs"], show_execution=False)

        self.console.print("[bold green]🔒 Transparency & Safety:[/bold green]")
        self.console.print(
            "Cortex [bold]shows you exactly what it will do[/bold] before making any changes."
        )
        self.console.print("[dim]No surprises, no unwanted modifications to your system.[/dim]\n")

        if not self._wait_for_user():
            return False

        # Part 3: Hardware-Aware Intelligence
        self.console.print("\n[bold]Part 3: Hardware-Aware Intelligence[/bold]")
        self.console.print(
            "Cortex detects your hardware and prevents incompatible installations.\n"
        )

        # Detect GPU (check both dedicated and integrated)
        gpu = getattr(self.hw, "gpu", None) if self.hw else None
        gpu_info = gpu[0] if (gpu and len(gpu) > 0) else None

        # Check for NVIDIA
        nvidia_keywords = ["NVIDIA", "GTX", "RTX", "GEFORCE", "QUADRO", "TESLA"]
        has_nvidia = gpu_info and self._is_gpu_vendor(gpu_info.model, nvidia_keywords)

        # Check for AMD (dedicated or integrated Radeon)
        amd_keywords = ["AMD", "RADEON", "RENOIR", "VEGA", "NAVI", "RX "]
        has_amd = gpu_info and self._is_gpu_vendor(gpu_info.model, amd_keywords)

        if has_nvidia:
            # NVIDIA GPU - show successful CUDA install
            self.console.print(f"[cyan]Detected GPU:[/cyan] {gpu_info.model}")
            self.console.print("Let's install CUDA for GPU acceleration:")

            if not self._prompt_command("cortex install cuda"):
                return False

            with self.console.status("[cyan]CX[/cyan] Understanding request...", spinner="dots"):
                time.sleep(0.8)
            with self.console.status(
                "[cyan]CX[/cyan] Checking hardware compatibility...", spinner="dots"
            ):
                time.sleep(1.0)

            self.console.print(
                " [cyan]CX[/cyan]  [green]✓[/green] NVIDIA GPU detected - CUDA compatible!\n"
            )
            time.sleep(0.5)

            self.console.print("[bold]Generated commands:[/bold]")
            self.console.print("  1. [dim]sudo apt update[/dim]")
            self.console.print("  2. [dim]sudo apt install -y nvidia-cuda-toolkit[/dim]\n")

            self.console.print(
                "[green]✅ Perfect! CUDA will work great on your NVIDIA GPU.[/green]\n"
            )

        elif has_amd:
            # AMD GPU - show Cortex catching the mistake
            self.console.print(f"[cyan]Detected GPU:[/cyan] {gpu_info.model}")
            self.console.print("Let's try to install CUDA...")

            if not self._prompt_command("cortex install cuda"):
                return False

            with self.console.status("[cyan]CX[/cyan] Understanding request...", spinner="dots"):
                time.sleep(0.8)
            with self.console.status(
                "[cyan]CX[/cyan] Checking hardware compatibility...", spinner="dots"
            ):
                time.sleep(1.2)

            self.console.print("\n[yellow]⚠️  Hardware Compatibility Warning:[/yellow]")
            time.sleep(0.8)
            self.console.print(f"[cyan]Your GPU:[/cyan] {gpu_info.model}")
            self.console.print("[red]NVIDIA CUDA will not work on AMD hardware![/red]\n")
            time.sleep(1.0)

            self.console.print(
                "[cyan]🤖 Cortex suggests:[/cyan] Install ROCm instead (AMD's GPU framework)"
            )
            time.sleep(0.8)
            self.console.print("\n[bold]Recommended alternative:[/bold]")
            self.console.print("  [cyan]cortex install rocm[/cyan]\n")

            self.console.print("[green]✅ Cortex prevented an incompatible installation![/green]\n")

        else:
            # No GPU - show Python dev tools
            self.console.print("[cyan]No dedicated GPU detected - CPU mode[/cyan]")
            self.console.print("Let's install Python development tools:")

            if not self._prompt_command("cortex install python-dev"):
                return False

            with self.console.status("[cyan]CX[/cyan] Understanding request...", spinner="dots"):
                time.sleep(0.8)
            with self.console.status("[cyan]CX[/cyan] Planning installation...", spinner="dots"):
                time.sleep(1.0)

            self.console.print("[bold]Generated commands:[/bold]")
            self.console.print("  1. [dim]sudo apt update[/dim]")
            self.console.print("  2. [dim]sudo apt install -y python3-dev[/dim]")
            self.console.print("  3. [dim]sudo apt install -y python3-pip[/dim]")
            self.console.print("  4. [dim]sudo apt install -y python3-venv[/dim]\n")

        self.console.print("[bold green]💡 The Difference:[/bold green]")
        self.console.print("Traditional package managers install whatever you ask for.")
        self.console.print(
            "Cortex [bold]checks compatibility FIRST[/bold] and prevents problems!\n"
        )

        return self._wait_for_user()

    def _section_smart_stacks(self) -> bool:
        """Section 2: Smart Stacks & Complete Workflows"""
        self.console.print("[bold cyan]📚 Smart Stacks - Complete Workflows[/bold cyan]\n")

        self.console.print("Stacks are pre-configured bundles of tools for common workflows.")
        self.console.print("Install everything you need with one command.\n")

        # List stacks
        if not self._prompt_command("cortex stack --list"):
            return False

        self.console.print()  # Visual spacing before stacks table

        # Show stacks table
        stacks_table = Table(title="📦 Available Stacks", show_header=True)
        stacks_table.add_column("Stack", style="cyan", width=12)
        stacks_table.add_column("Description", style="white", width=22)
        stacks_table.add_column("Packages", style="dim", width=35)

        stacks_table.add_row("ml", "Machine Learning (GPU)", "PyTorch, CUDA, Jupyter, pandas...")
        stacks_table.add_row("ml-cpu", "Machine Learning (CPU)", "PyTorch CPU-only version")
        stacks_table.add_row("webdev", "Web Development", "Node, npm, nginx, postgres")
        stacks_table.add_row("devops", "DevOps Tools", "Docker, kubectl, terraform, ansible")
        stacks_table.add_row("data", "Data Science", "Python, pandas, jupyter, postgres")

        self.console.print(stacks_table)
        self.console.print(
            "\n [cyan]CX[/cyan]  │ Use: [cyan]cortex stack <name>[/cyan] to install a stack\n"
        )

        if not self._wait_for_user():
            return False

        # Install webdev stack
        self.console.print("\nLet's install the Web Development stack:")

        if not self._prompt_command("cortex stack webdev"):
            return False

        self.console.print(" [cyan]CX[/cyan]  [green]✓[/green] ")
        self.console.print("🚀 Installing stack: [bold]Web Development[/bold]\n")

        # Simulate full stack installation
        self._simulate_cortex_output(["nodejs", "npm", "nginx", "postgresql"], show_execution=True)

        self.console.print(" [cyan]CX[/cyan]  [green]✓[/green] ")
        self.console.print("[green]✅ Stack 'Web Development' installed successfully![/green]")
        self.console.print("[green]Installed 4 packages[/green]\n")

        self.console.print("[bold green]💡 Benefit:[/bold green]")
        self.console.print(
            "One command sets up your [bold]entire development environment[/bold].\n"
        )

        self.console.print("\n[cyan]💡 Tip:[/cyan] Create custom stacks for your team's workflow!")
        self.console.print('   [dim]cortex stack create "mystack" package1 package2...[/dim]\n')

        return self._wait_for_user()

    def _section_history_safety(self) -> bool:
        """Section 3: History Tracking & Safety Features"""
        self.console.print("[bold cyan]🔒 History & Safety Features[/bold cyan]\n")

        # Part 1: Installation History
        self.console.print("[bold]Part 1: Installation History[/bold]")
        self.console.print("Cortex keeps a complete record of all installations.")
        self.console.print("Review what you've installed anytime:\n")

        if not self._prompt_command("cortex history"):
            return False

        self.console.print()

        # Show history table
        history_table = Table(show_header=True)
        history_table.add_column("ID", style="dim", width=18)
        history_table.add_column("Date", style="cyan", width=20)
        history_table.add_column("Operation", style="white", width=12)
        history_table.add_column("Packages", style="yellow", width=25)
        history_table.add_column("Status", style="green", width=10)

        history_table.add_row(
            self.installation_id,
            self._generate_past_date(0),
            "install",
            "nginx, nodejs +2",
            "success",
        )
        history_table.add_row(
            self._generate_id(),
            self._generate_past_date(1, 13, 13),
            "install",
            "docker",
            "success",
        )
        history_table.add_row(
            self._generate_id(),
            self._generate_past_date(1, 14, 25),
            "install",
            "python3-dev",
            "success",
        )
        history_table.add_row(
            self._generate_id(),
            self._generate_past_date(2, 18, 29),
            "install",
            "postgresql",
            "success",
        )

        self.console.print(history_table)
        self.console.print()

        self.console.print("[bold green]💡 Tracking Feature:[/bold green]")
        self.console.print(
            "Every installation is tracked. You can [bold]review or undo[/bold] any operation.\n"
        )

        if not self._wait_for_user():
            return False

        # Part 2: Rollback Functionality
        self.console.print("\n[bold]Part 2: Safe Rollback[/bold]")
        self.console.print("Made a mistake? Installed something wrong?")
        self.console.print("Cortex can [bold]roll back any installation[/bold].\n")

        self.console.print(
            f"Let's undo our webdev stack installation (ID: {self.installation_id}):"
        )

        if not self._prompt_command(f"cortex rollback {self.installation_id}"):
            return False

        self.console.print()
        with self.console.status("[cyan]CX[/cyan] Loading installation record...", spinner="dots"):
            time.sleep(0.8)
        with self.console.status("[cyan]CX[/cyan] Planning rollback...", spinner="dots"):
            time.sleep(1.0)
        with self.console.status("[cyan]CX[/cyan] Removing packages...", spinner="dots"):
            time.sleep(1.2)

        rollback_id = self._generate_id()
        self.console.print(
            f" [cyan]CX[/cyan]  [green]✓[/green] Rollback successful (ID: {rollback_id})\n"
        )

        self.console.print(
            "[green]✅ All packages from that installation have been removed.[/green]\n"
        )

        self.console.print("[bold green]💡 Peace of Mind:[/bold green]")
        self.console.print(
            "Try anything fearlessly - you can always [bold]roll back[/bold] to a clean state.\n"
        )

        return self._wait_for_user()

    def _show_finale(self) -> None:
        """Show finale with comparison table and next steps"""
        self.console.print("\n" + "=" * 70)
        self.console.print(
            "[bold green]🎉 Demo Complete - You've Mastered Cortex Basics![/bold green]"
        )
        self.console.print("=" * 70 + "\n")

        # Show comparison table (THE WOW FACTOR)
        self.console.print("\n[bold]Why Cortex is Different:[/bold]\n")

        comparison_table = Table(
            title="Cortex vs Traditional Package Managers", show_header=True, border_style="cyan"
        )
        comparison_table.add_column("Feature", style="cyan", width=20)
        comparison_table.add_column("Traditional (apt/brew)", style="yellow", width=25)
        comparison_table.add_column("Cortex", style="green", width=25)

        comparison_table.add_row("Planning", "Installs immediately", "Shows plan first")
        comparison_table.add_row("Search", "Exact string match", "Semantic/Intent based")
        comparison_table.add_row(
            "Hardware Aware", "Installs anything", "Checks compatibility first"
        )
        comparison_table.add_row("Natural Language", "Strict syntax only", "AI understands intent")
        comparison_table.add_row("Stacks", "Manual script creation", "One-command workflows")
        comparison_table.add_row("Safety", "Manual backups", "Automatic rollback")
        comparison_table.add_row("Multi-Manager", "Choose apt/brew/npm", "One tool, all managers")

        self.console.print(comparison_table)
        self.console.print()

        # Key takeaways
        summary = """
[bold]What You've Learned:[/bold]

  ✓ [cyan]AI-Powered Understanding[/cyan] - Natural language queries
  ✓ [cyan]Transparent Planning[/cyan] - See commands before execution
  ✓ [cyan]Hardware-Aware[/cyan] - Prevents incompatible installations
  ✓ [cyan]Smart Stacks[/cyan] - Complete workflows in one command
  ✓ [cyan]Full History[/cyan] - Track every installation
  ✓ [cyan]Safe Rollback[/cyan] - Undo anything, anytime

[bold cyan]Ready to use Cortex?[/bold cyan]

Essential commands:
  $ [cyan]cortex wizard[/cyan]                   # Configure your API key (recommended first step!)
  $ [cyan]cortex install "package"[/cyan]        # Install packages
  $ [cyan]cortex ask "question"[/cyan]           # Get AI recommendations
  $ [cyan]cortex stack --list[/cyan]             # See available stacks
  $ [cyan]cortex stack <name>[/cyan]             # Install a complete stack
  $ [cyan]cortex history[/cyan]                  # View installation history
  $ [cyan]cortex rollback <id>[/cyan]            # Undo an installation
  $ [cyan]cortex doctor[/cyan]                   # Check system health
  $ [cyan]cortex --help[/cyan]                   # See all commands

[dim]GitHub: github.com/cortexlinux/cortex[/dim]
        """

        self.console.print(Panel(summary, border_style="green", title="🚀 Next Steps"))
        self.console.print("\n[bold]Thank you for trying Cortex! Happy installing! 🎉[/bold]\n")


def run_demo() -> int:
    """
    Entry point for the interactive Cortex demo.
    Teaches users Cortex through hands-on practice.
    """
    demo = CortexDemo()
    return demo.run()
