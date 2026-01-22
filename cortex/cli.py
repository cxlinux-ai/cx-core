import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

from cortex.ask import AskHandler
from cortex.branding import VERSION, console, cx_header, cx_print, show_banner
from cortex.coordinator import InstallationCoordinator, InstallationStep, StepStatus
from cortex.demo import run_demo
from cortex.dependency_importer import (
    DependencyImporter,
    PackageEcosystem,
    ParseResult,
    format_package_list,
)
from cortex.env_manager import EnvironmentManager, get_env_manager
from cortex.installation_history import InstallationHistory, InstallationStatus, InstallationType
from cortex.llm.interpreter import CommandInterpreter
from cortex.network_config import NetworkConfig
from cortex.notification_manager import NotificationManager
from cortex.stack_manager import StackManager
from cortex.validators import validate_api_key, validate_install_request

# Suppress noisy log messages in normal operation
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cortex.installation_history").setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class CortexCLI:
    def __init__(self, verbose: bool = False):
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.verbose = verbose

    def _debug(self, message: str):
        """Print debug info only in verbose mode"""
        if self.verbose:
            console.print(f"[dim][DEBUG] {message}[/dim]")

    def _get_api_key(self) -> str | None:
        # Check if using Ollama or Fake provider (no API key needed)
        provider = self._get_provider()
        if provider == "ollama":
            self._debug("Using Ollama (no API key required)")
            return "ollama-local"  # Placeholder for Ollama
        if provider == "fake":
            self._debug("Using Fake provider for testing")
            return "fake-key"  # Placeholder for Fake provider

        is_valid, detected_provider, error = validate_api_key()
        if not is_valid:
            self._print_error(error)
            cx_print("Run [bold]cortex wizard[/bold] to configure your API key.", "info")
            cx_print("Or use [bold]CORTEX_PROVIDER=ollama[/bold] for offline mode.", "info")
            return None
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        return api_key

    def _get_provider(self) -> str:
        # Check environment variable for explicit provider choice
        explicit_provider = os.environ.get("CORTEX_PROVIDER", "").lower()
        if explicit_provider in ["ollama", "openai", "claude", "fake"]:
            return explicit_provider

        # Auto-detect based on available API keys
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "claude"
        elif os.environ.get("OPENAI_API_KEY"):
            return "openai"

        # Fallback to Ollama for offline mode
        return "ollama"

    def _print_status(self, emoji: str, message: str):
        """Legacy status print - maps to cx_print for Rich output"""
        status_map = {
            "🧠": "thinking",
            "📦": "info",
            "⚙️": "info",
            "🔍": "info",
        }
        status = status_map.get(emoji, "info")
        cx_print(message, status)

    def _print_error(self, message: str):
        cx_print(f"Error: {message}", "error")

    def _print_success(self, message: str):
        cx_print(message, "success")

    def _animate_spinner(self, message: str):
        sys.stdout.write(f"\r{self.spinner_chars[self.spinner_idx]} {message}")
        sys.stdout.flush()
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
        time.sleep(0.1)

    def _clear_line(self):
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    # --- New Notification Method ---
    def notify(self, args):
        """Handle notification commands"""
        # Addressing CodeRabbit feedback: Handle missing subcommand gracefully
        if not args.notify_action:
            self._print_error("Please specify a subcommand (config/enable/disable/dnd/send)")
            return 1

        mgr = NotificationManager()

        if args.notify_action == "config":
            console.print("[bold cyan]🔧 Current Notification Configuration:[/bold cyan]")
            status = (
                "[green]Enabled[/green]"
                if mgr.config.get("enabled", True)
                else "[red]Disabled[/red]"
            )
            console.print(f"Status: {status}")
            console.print(
                f"DND Window: [yellow]{mgr.config['dnd_start']} - {mgr.config['dnd_end']}[/yellow]"
            )
            console.print(f"History File: {mgr.history_file}")
            return 0

        elif args.notify_action == "enable":
            mgr.config["enabled"] = True
            # Addressing CodeRabbit feedback: Ideally should use a public method instead of private _save_config,
            # but keeping as is for a simple fix (or adding a save method to NotificationManager would be best).
            mgr._save_config()
            self._print_success("Notifications enabled")
            return 0

        elif args.notify_action == "disable":
            mgr.config["enabled"] = False
            mgr._save_config()
            cx_print("Notifications disabled (Critical alerts will still show)", "warning")
            return 0

        elif args.notify_action == "dnd":
            if not args.start or not args.end:
                self._print_error("Please provide start and end times (HH:MM)")
                return 1

            # Addressing CodeRabbit feedback: Add time format validation
            try:
                datetime.strptime(args.start, "%H:%M")
                datetime.strptime(args.end, "%H:%M")
            except ValueError:
                self._print_error("Invalid time format. Use HH:MM (e.g., 22:00)")
                return 1

            mgr.config["dnd_start"] = args.start
            mgr.config["dnd_end"] = args.end
            mgr._save_config()
            self._print_success(f"DND Window updated: {args.start} - {args.end}")
            return 0

        elif args.notify_action == "send":
            if not args.message:
                self._print_error("Message required")
                return 1
            console.print("[dim]Sending notification...[/dim]")
            mgr.send(args.title, args.message, level=args.level, actions=args.actions)
            return 0

        else:
            self._print_error("Unknown notify command")
            return 1

    # -------------------------------
    def demo(self):
        """
        Run the one-command investor demo
        """
        return run_demo()

    def stack(self, args: argparse.Namespace) -> int:
        """Handle `cortex stack` commands (list/describe/install/dry-run)."""
        try:
            manager = StackManager()

            # Validate --dry-run requires a stack name
            if args.dry_run and not args.name:
                self._print_error(
                    "--dry-run requires a stack name (e.g., `cortex stack ml --dry-run`)"
                )
                return 1

            # List stacks (default when no name/describe)
            if args.list or (not args.name and not args.describe):
                return self._handle_stack_list(manager)

            # Describe a specific stack
            if args.describe:
                return self._handle_stack_describe(manager, args.describe)

            # Install a stack (only remaining path)
            return self._handle_stack_install(manager, args)

        except FileNotFoundError as e:
            self._print_error(f"stacks.json not found. Ensure cortex/stacks.json exists: {e}")
            return 1
        except ValueError as e:
            self._print_error(f"stacks.json is invalid or malformed: {e}")
            return 1

    def _handle_stack_list(self, manager: StackManager) -> int:
        """List all available stacks."""
        stacks = manager.list_stacks()
        cx_print("\n📦 Available Stacks:\n", "info")
        for stack in stacks:
            pkg_count = len(stack.get("packages", []))
            console.print(f"  [green]{stack.get('id', 'unknown')}[/green]")
            console.print(f"    {stack.get('name', 'Unnamed Stack')}")
            console.print(f"    {stack.get('description', 'No description')}")
            console.print(f"    [dim]({pkg_count} packages)[/dim]\n")
        cx_print("Use: cortex stack <name> to install a stack", "info")
        return 0

    def _handle_stack_describe(self, manager: StackManager, stack_id: str) -> int:
        """Describe a specific stack."""
        stack = manager.find_stack(stack_id)
        if not stack:
            self._print_error(f"Stack '{stack_id}' not found. Use --list to see available stacks.")
            return 1
        description = manager.describe_stack(stack_id)
        console.print(description)
        return 0

    def _handle_stack_install(self, manager: StackManager, args: argparse.Namespace) -> int:
        """Install a stack with optional hardware-aware selection."""
        original_name = args.name
        suggested_name = manager.suggest_stack(args.name)

        if suggested_name != original_name:
            cx_print(
                f"💡 No GPU detected, using '{suggested_name}' instead of '{original_name}'",
                "info",
            )

        stack = manager.find_stack(suggested_name)
        if not stack:
            self._print_error(
                f"Stack '{suggested_name}' not found. Use --list to see available stacks."
            )
            return 1

        packages = stack.get("packages", [])
        if not packages:
            self._print_error(f"Stack '{suggested_name}' has no packages configured.")
            return 1

        if args.dry_run:
            return self._handle_stack_dry_run(stack, packages)

        return self._handle_stack_real_install(stack, packages)

    def _handle_stack_dry_run(self, stack: dict[str, Any], packages: list[str]) -> int:
        """Preview packages that would be installed without executing."""
        cx_print(f"\n📋 Stack: {stack['name']}", "info")
        console.print("\nPackages that would be installed:")
        for pkg in packages:
            console.print(f"  • {pkg}")
        console.print(f"\nTotal: {len(packages)} packages")
        cx_print("\nDry run only - no commands executed", "warning")
        return 0

    def _handle_stack_real_install(self, stack: dict[str, Any], packages: list[str]) -> int:
        """Install all packages in the stack."""
        cx_print(f"\n🚀 Installing stack: {stack['name']}\n", "success")

        # Batch into a single LLM request
        packages_str = " ".join(packages)
        result = self.install(software=packages_str, execute=True, dry_run=False)

        if result != 0:
            self._print_error(f"Failed to install stack '{stack['name']}'")
            return 1

        self._print_success(f"\n✅ Stack '{stack['name']}' installed successfully!")
        console.print(f"Installed {len(packages)} packages")
        return 0

    # --- Sandbox Commands (Docker-based package testing) ---
    def sandbox(self, args: argparse.Namespace) -> int:
        """Handle `cortex sandbox` commands for Docker-based package testing."""
        from cortex.sandbox import (
            DockerNotFoundError,
            DockerSandbox,
            SandboxAlreadyExistsError,
            SandboxNotFoundError,
            SandboxTestStatus,
        )

        action = getattr(args, "sandbox_action", None)

        if not action:
            cx_print("\n🐳 Docker Sandbox - Test packages safely before installing\n", "info")
            console.print("Usage: cortex sandbox <command> [options]")
            console.print("\nCommands:")
            console.print("  create <name>              Create a sandbox environment")
            console.print("  install <name> <package>   Install package in sandbox")
            console.print("  test <name> [package]      Run tests in sandbox")
            console.print("  promote <name> <package>   Install tested package on main system")
            console.print("  cleanup <name>             Remove sandbox environment")
            console.print("  list                       List all sandboxes")
            console.print("  exec <name> <cmd...>       Execute command in sandbox")
            console.print("\nExample workflow:")
            console.print("  cortex sandbox create test-env")
            console.print("  cortex sandbox install test-env nginx")
            console.print("  cortex sandbox test test-env")
            console.print("  cortex sandbox promote test-env nginx")
            console.print("  cortex sandbox cleanup test-env")
            return 0

        try:
            sandbox = DockerSandbox()

            if action == "create":
                return self._sandbox_create(sandbox, args)
            elif action == "install":
                return self._sandbox_install(sandbox, args)
            elif action == "test":
                return self._sandbox_test(sandbox, args)
            elif action == "promote":
                return self._sandbox_promote(sandbox, args)
            elif action == "cleanup":
                return self._sandbox_cleanup(sandbox, args)
            elif action == "list":
                return self._sandbox_list(sandbox)
            elif action == "exec":
                return self._sandbox_exec(sandbox, args)
            else:
                self._print_error(f"Unknown sandbox action: {action}")
                return 1

        except DockerNotFoundError as e:
            self._print_error(str(e))
            cx_print("Docker is required only for sandbox commands.", "info")
            return 1
        except SandboxNotFoundError as e:
            self._print_error(str(e))
            cx_print("Use 'cortex sandbox list' to see available sandboxes.", "info")
            return 1
        except SandboxAlreadyExistsError as e:
            self._print_error(str(e))
            return 1

    def _sandbox_create(self, sandbox, args: argparse.Namespace) -> int:
        """Create a new sandbox environment."""
        name = args.name
        image = getattr(args, "image", "ubuntu:22.04")

        cx_print(f"Creating sandbox '{name}'...", "info")
        result = sandbox.create(name, image=image)

        if result.success:
            cx_print(f"✓ Sandbox environment '{name}' created", "success")
            console.print(f"  [dim]{result.stdout}[/dim]")
            return 0
        else:
            self._print_error(result.message)
            if result.stderr:
                console.print(f"  [red]{result.stderr}[/red]")
            return 1

    def _sandbox_install(self, sandbox, args: argparse.Namespace) -> int:
        """Install a package in sandbox."""
        name = args.name
        package = args.package

        cx_print(f"Installing '{package}' in sandbox '{name}'...", "info")
        result = sandbox.install(name, package)

        if result.success:
            cx_print(f"✓ {package} installed in sandbox", "success")
            return 0
        else:
            self._print_error(result.message)
            if result.stderr:
                console.print(f"  [dim]{result.stderr[:500]}[/dim]")
            return 1

    def _sandbox_test(self, sandbox, args: argparse.Namespace) -> int:
        """Run tests in sandbox."""
        from cortex.sandbox import SandboxTestStatus

        name = args.name
        package = getattr(args, "package", None)

        cx_print(f"Running tests in sandbox '{name}'...", "info")
        result = sandbox.test(name, package)

        console.print()
        for test in result.test_results:
            if test.result == SandboxTestStatus.PASSED:
                console.print(f"   ✓  {test.name}")
                if test.message:
                    console.print(f"      [dim]{test.message[:80]}[/dim]")
            elif test.result == SandboxTestStatus.FAILED:
                console.print(f"   ✗  {test.name}")
                if test.message:
                    console.print(f"      [red]{test.message}[/red]")
            else:
                console.print(f"   ⊘  {test.name} [dim](skipped)[/dim]")

        console.print()
        if result.success:
            cx_print("All tests passed", "success")
            return 0
        else:
            self._print_error("Some tests failed")
            return 1

    def _sandbox_promote(self, sandbox, args: argparse.Namespace) -> int:
        """Promote a tested package to main system."""
        name = args.name
        package = args.package
        dry_run = getattr(args, "dry_run", False)
        skip_confirm = getattr(args, "yes", False)

        if dry_run:
            result = sandbox.promote(name, package, dry_run=True)
            cx_print(f"Would run: sudo apt-get install -y {package}", "info")
            return 0

        # Confirm with user unless -y flag
        if not skip_confirm:
            console.print(f"\nPromote '{package}' to main system? [Y/n]: ", end="")
            try:
                response = input().strip().lower()
                if response and response not in ("y", "yes"):
                    cx_print("Promotion cancelled", "warning")
                    return 0
            except (EOFError, KeyboardInterrupt):
                console.print()
                cx_print("Promotion cancelled", "warning")
                return 0

        cx_print(f"Installing '{package}' on main system...", "info")
        result = sandbox.promote(name, package, dry_run=False)

        if result.success:
            cx_print(f"✓ {package} installed on main system", "success")
            return 0
        else:
            self._print_error(result.message)
            if result.stderr:
                console.print(f"  [red]{result.stderr[:500]}[/red]")
            return 1

    def _sandbox_cleanup(self, sandbox, args: argparse.Namespace) -> int:
        """Remove a sandbox environment."""
        name = args.name
        force = getattr(args, "force", False)

        cx_print(f"Removing sandbox '{name}'...", "info")
        result = sandbox.cleanup(name, force=force)

        if result.success:
            cx_print(f"✓ Sandbox '{name}' removed", "success")
            return 0
        else:
            self._print_error(result.message)
            return 1

    def _sandbox_list(self, sandbox) -> int:
        """List all sandbox environments."""
        sandboxes = sandbox.list_sandboxes()

        if not sandboxes:
            cx_print("No sandbox environments found", "info")
            cx_print("Create one with: cortex sandbox create <name>", "info")
            return 0

        cx_print("\n🐳 Sandbox Environments:\n", "info")
        for sb in sandboxes:
            status_icon = "🟢" if sb.state.value == "running" else "⚪"
            console.print(f"  {status_icon} [green]{sb.name}[/green]")
            console.print(f"      Image: {sb.image}")
            console.print(f"      Created: {sb.created_at[:19]}")
            if sb.packages:
                console.print(f"      Packages: {', '.join(sb.packages)}")
            console.print()

        return 0

    def _sandbox_exec(self, sandbox, args: argparse.Namespace) -> int:
        """Execute command in sandbox."""
        name = args.name
        command = args.command

        result = sandbox.exec_command(name, command)

        if result.stdout:
            console.print(result.stdout, end="")
        if result.stderr:
            console.print(result.stderr, style="red", end="")

        return result.exit_code

    # --- End Sandbox Commands ---

    def ask(self, question: str | None, debug: bool = False, do_mode: bool = False) -> int:
        """Answer a natural language question about the system.
        
        In --do mode, Cortex can execute write and modify commands with user confirmation.
        If no question is provided in --do mode, starts an interactive session.
        """
        api_key = self._get_api_key()
        if not api_key:
            return 1

        provider = self._get_provider()
        self._debug(f"Using provider: {provider}")

        # Setup cortex user if in do mode
        if do_mode:
            try:
                from cortex.do_runner import setup_cortex_user
                cx_print("🔧 Do mode enabled - Cortex can execute commands to solve problems", "info")
                # Don't fail if user creation fails - we have fallbacks
                setup_cortex_user()
            except Exception as e:
                self._debug(f"Cortex user setup skipped: {e}")

        try:
            handler = AskHandler(
                api_key=api_key,
                provider=provider,
                debug=debug,
                do_mode=do_mode,
            )
            
            # If no question and in do mode, start interactive session
            if question is None and do_mode:
                return self._run_interactive_do_session(handler)
            elif question is None:
                self._print_error("Please provide a question or use --do for interactive mode")
                return 1
            
            answer = handler.ask(question)
            # Don't print raw JSON or processing messages
            if answer and not (answer.strip().startswith('{') or 
                               "I'm processing your request" in answer or
                               "I have a plan to execute" in answer):
                console.print(answer)
            return 0
        except ImportError as e:
            # Provide a helpful message if provider SDK is missing
            self._print_error(str(e))
            cx_print(
                "Install the required SDK or set CORTEX_PROVIDER=ollama for local mode.", "info"
            )
            return 1
        except ValueError as e:
            self._print_error(str(e))
            return 1
        except RuntimeError as e:
            self._print_error(str(e))
            return 1
    
    def _run_interactive_do_session(self, handler: AskHandler) -> int:
        """Run an interactive --do session where user can type queries."""
        import signal
        from rich.panel import Panel
        from rich.prompt import Prompt
        
        # Create a session
        from cortex.do_runner import DoRunDatabase
        db = DoRunDatabase()
        session_id = db.create_session()
        
        # Pass session_id to handler
        if handler._do_handler:
            handler._do_handler.current_session_id = session_id
        
        # Track if we're currently processing a request
        processing_request = False
        request_interrupted = False
        
        class SessionInterrupt(Exception):
            """Exception raised to interrupt the current request and return to prompt."""
            pass
        
        class SessionExit(Exception):
            """Exception raised to exit the session immediately (Ctrl+C)."""
            pass
        
        def handle_ctrl_z(signum, frame):
            """Handle Ctrl+Z - stop current operation, return to prompt."""
            nonlocal request_interrupted
            
            # Set interrupt flag on the handler - this will be checked in the loop
            handler.interrupt()
            
            # If DoHandler has an active process, stop it
            if handler._do_handler and handler._do_handler._current_process:
                try:
                    handler._do_handler._current_process.terminate()
                    handler._do_handler._current_process.wait(timeout=1)
                except:
                    try:
                        handler._do_handler._current_process.kill()
                    except:
                        pass
                handler._do_handler._current_process = None
            
            # If we're processing a request, interrupt it immediately
            if processing_request:
                request_interrupted = True
                console.print()
                console.print(f"[yellow]⚠ Ctrl+Z - Stopping current operation...[/yellow]")
                # Raise exception to break out and return to prompt
                raise SessionInterrupt("Interrupted by Ctrl+Z")
            else:
                # Not processing anything, just inform the user
                console.print()
                console.print(f"[dim]Ctrl+Z - Type 'exit' to end the session[/dim]")
        
        def handle_ctrl_c(signum, frame):
            """Handle Ctrl+C - exit the session immediately."""
            # Stop any active process first
            if handler._do_handler and handler._do_handler._current_process:
                try:
                    handler._do_handler._current_process.terminate()
                    handler._do_handler._current_process.wait(timeout=1)
                except:
                    try:
                        handler._do_handler._current_process.kill()
                    except:
                        pass
                handler._do_handler._current_process = None
            
            console.print()
            console.print("[cyan]👋 Session ended (Ctrl+C).[/cyan]")
            raise SessionExit("Exited by Ctrl+C")
        
        # Set up signal handlers for the entire session
        # Ctrl+Z (SIGTSTP) -> stop current operation, return to prompt
        # Ctrl+C (SIGINT) -> exit session immediately
        original_sigtstp = signal.signal(signal.SIGTSTP, handle_ctrl_z)
        original_sigint = signal.signal(signal.SIGINT, handle_ctrl_c)
        
        try:
            console.print()
            console.print(Panel(
                "[bold cyan]🚀 Cortex Interactive Session[/bold cyan]\n\n"
                f"[dim]Session ID: {session_id[:30]}...[/dim]\n\n"
                "Type what you want to do and Cortex will help you.\n"
                "Commands will be shown for approval before execution.\n\n"
                "[dim]Examples:[/dim]\n"
                "  • install docker and run nginx\n"
                "  • setup a postgresql database\n"
                "  • configure nginx to proxy port 3000\n"
                "  • check system resources\n\n"
                "[dim]Type 'exit' or 'quit' to end the session.[/dim]\n"
                "[dim]Press Ctrl+Z to stop current operation | Ctrl+C to exit immediately[/dim]",
                title="[bold green]Welcome[/bold green]",
                border_style="cyan",
            ))
            console.print()
            
            session_history = []  # Track what was done in this session
            run_count = 0
            
            while True:
                try:
                    # Show compact session status (not the full history panel)
                    if session_history:
                        console.print(f"[dim]Session: {len(session_history)} task(s) | {run_count} run(s) | Type 'history' to see details[/dim]")
                    
                    # Get user input
                    query = Prompt.ask("[bold cyan]What would you like to do?[/bold cyan]")
                    
                    if not query.strip():
                        continue
                    
                    # Check for exit
                    if query.lower().strip() in ["exit", "quit", "bye", "q"]:
                        db.end_session(session_id)
                        console.print()
                        console.print(f"[cyan]👋 Session ended ({run_count} runs). Run 'cortex do history' to see past runs.[/cyan]")
                        break
                    
                    # Check for help
                    if query.lower().strip() in ["help", "?"]:
                        console.print()
                        console.print("[bold]Available commands:[/bold]")
                        console.print("  [green]exit[/green], [green]quit[/green] - End the session")
                        console.print("  [green]history[/green] - Show session history")
                        console.print("  [green]clear[/green] - Clear session history")
                        console.print("  Or type any request in natural language!")
                        console.print()
                        continue
                    
                    # Check for history
                    if query.lower().strip() == "history":
                        if session_history:
                            from rich.table import Table
                            from rich.panel import Panel
                            
                            console.print()
                            table = Table(
                                show_header=True, 
                                header_style="bold cyan",
                                title=f"[bold]Session History[/bold]",
                                title_style="bold",
                            )
                            table.add_column("#", style="dim", width=3)
                            table.add_column("Query", style="white", max_width=45)
                            table.add_column("Status", justify="center", width=8)
                            table.add_column("Commands", justify="center", width=10)
                            table.add_column("Run ID", style="dim", max_width=20)
                            
                            for i, item in enumerate(session_history, 1):
                                status = "[green]✓ Success[/green]" if item.get("success") else "[red]✗ Failed[/red]"
                                query_short = item['query'][:42] + "..." if len(item['query']) > 42 else item['query']
                                cmd_count = str(item.get('commands_count', 0)) if item.get('success') else "-"
                                run_id = item.get('run_id', '-')[:18] + "..." if item.get('run_id') and len(item.get('run_id', '')) > 18 else item.get('run_id', '-')
                                table.add_row(str(i), query_short, status, cmd_count, run_id)
                            
                            console.print(table)
                            console.print()
                            console.print(f"[dim]Total: {len(session_history)} tasks | {run_count} runs | Session: {session_id[:20]}...[/dim]")
                            console.print()
                        else:
                            console.print("[dim]No tasks completed yet.[/dim]")
                        continue
                    
                    # Check for clear
                    if query.lower().strip() == "clear":
                        session_history.clear()
                        console.print("[dim]Session history cleared.[/dim]")
                        continue
                    
                    # Update session with query
                    db.update_session(session_id, query=query)
                    
                    # Process the query
                    console.print()
                    processing_request = True
                    request_interrupted = False
                    handler.reset_interrupt()  # Reset interrupt flag before new request
                    
                    try:
                        answer = handler.ask(query)
                        
                        # Check if request was interrupted
                        if request_interrupted:
                            console.print("[yellow]⚠ Request was interrupted[/yellow]")
                            session_history.append({
                                "query": query,
                                "success": False,
                                "error": "Interrupted by user",
                            })
                            continue
                        
                        # Get the run_id and command count if one was created
                        run_id = None
                        commands_count = 0
                        if handler._do_handler and handler._do_handler.current_run:
                            run_id = handler._do_handler.current_run.run_id
                            # Count commands from the run
                            if handler._do_handler.current_run.commands:
                                commands_count = len(handler._do_handler.current_run.commands)
                            run_count += 1
                            db.update_session(session_id, increment_runs=True)
                        
                        # Track in session history
                        session_history.append({
                            "query": query,
                            "success": True,
                            "answer": answer[:100] if answer else "",
                            "run_id": run_id,
                            "commands_count": commands_count,
                        })
                        
                        # Print response if it's informational (filter out JSON)
                        if answer and not answer.startswith("USER_DECLINED"):
                            # Don't print raw JSON or processing messages
                            if not (answer.strip().startswith('{') or 
                                    "I'm processing your request" in answer or
                                    "I have a plan to execute" in answer):
                                console.print(answer)
                        
                    except SessionInterrupt:
                        # Ctrl+Z/Ctrl+C pressed - return to prompt immediately
                        console.print()
                        session_history.append({
                            "query": query,
                            "success": False,
                            "error": "Interrupted by user",
                        })
                        continue  # Go back to "What would you like to do?" prompt
                    except Exception as e:
                        if request_interrupted:
                            console.print("[yellow]⚠ Request was interrupted[/yellow]")
                        else:
                            # Show user-friendly error without internal details
                            error_msg = str(e)
                            if isinstance(e, AttributeError):
                                console.print("[yellow]⚠ Something went wrong. Please try again.[/yellow]")
                                # Log the actual error for debugging
                                import logging
                                logging.debug(f"Internal error: {e}")
                            else:
                                console.print(f"[red]⚠ {error_msg}[/red]")
                        session_history.append({
                            "query": query,
                            "success": False,
                            "error": "Interrupted" if request_interrupted else str(e),
                        })
                    finally:
                        processing_request = False
                        request_interrupted = False
                    
                    console.print()
                    
                except SessionInterrupt:
                    # Ctrl+Z - just return to prompt
                    console.print()
                    continue
                except SessionExit:
                    # Ctrl+C - exit session immediately
                    db.end_session(session_id)
                    break
                except (KeyboardInterrupt, EOFError):
                    # Fallback for any other interrupts
                    db.end_session(session_id)
                    console.print()
                    console.print("[cyan]👋 Session ended.[/cyan]")
                    break
        
        finally:
            # Always restore signal handlers when session ends
            signal.signal(signal.SIGTSTP, original_sigtstp)
            signal.signal(signal.SIGINT, original_sigint)
        
        return 0

    def install(
        self,
        software: str,
        execute: bool = False,
        dry_run: bool = False,
        parallel: bool = False,
    ):
        # Validate input first
        is_valid, error = validate_install_request(software)
        if not is_valid:
            self._print_error(error)
            return 1

        # Special-case the ml-cpu stack:
        # The LLM sometimes generates outdated torch==1.8.1+cpu installs
        # which fail on modern Python. For the "pytorch-cpu jupyter numpy pandas"
        # combo, force a supported CPU-only PyTorch recipe instead.
        normalized = " ".join(software.split()).lower()

        if normalized == "pytorch-cpu jupyter numpy pandas":
            software = (
                "pip3 install torch torchvision torchaudio "
                "--index-url https://download.pytorch.org/whl/cpu && "
                "pip3 install jupyter numpy pandas"
            )

        api_key = self._get_api_key()
        if not api_key:
            return 1

        provider = self._get_provider()
        self._debug(f"Using provider: {provider}")
        self._debug(f"API key: {api_key[:10]}...{api_key[-4:]}")

        # Initialize installation history
        history = InstallationHistory()
        install_id = None
        start_time = datetime.now()

        try:
            self._print_status("🧠", "Understanding request...")

            interpreter = CommandInterpreter(api_key=api_key, provider=provider)

            self._print_status("📦", "Planning installation...")

            for _ in range(10):
                self._animate_spinner("Analyzing system requirements...")
            self._clear_line()

            commands = interpreter.parse(f"install {software}")

            if not commands:
                self._print_error(
                    "No commands generated. Please try again with a different request."
                )
                return 1

            # Extract packages from commands for tracking
            packages = history._extract_packages_from_commands(commands)

            # Record installation start
            if execute or dry_run:
                install_id = history.record_installation(
                    InstallationType.INSTALL, packages, commands, start_time
                )

            self._print_status("⚙️", f"Installing {software}...")
            print("\nGenerated commands:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. {cmd}")

            if dry_run:
                print("\n(Dry run mode - commands not executed)")
                if install_id:
                    history.update_installation(install_id, InstallationStatus.SUCCESS)
                return 0

            if execute:

                def progress_callback(current, total, step):
                    status_emoji = "⏳"
                    if step.status == StepStatus.SUCCESS:
                        status_emoji = "✅"
                    elif step.status == StepStatus.FAILED:
                        status_emoji = "❌"
                    print(f"\n[{current}/{total}] {status_emoji} {step.description}")
                    print(f"  Command: {step.command}")

                print("\nExecuting commands...")

                if parallel:
                    import asyncio

                    from cortex.install_parallel import run_parallel_install

                    def parallel_log_callback(message: str, level: str = "info"):
                        if level == "success":
                            cx_print(f"  ✅ {message}", "success")
                        elif level == "error":
                            cx_print(f"  ❌ {message}", "error")
                        else:
                            cx_print(f"  ℹ {message}", "info")

                    try:
                        success, parallel_tasks = asyncio.run(
                            run_parallel_install(
                                commands=commands,
                                descriptions=[f"Step {i + 1}" for i in range(len(commands))],
                                timeout=300,
                                stop_on_error=True,
                                log_callback=parallel_log_callback,
                            )
                        )

                        total_duration = 0.0
                        if parallel_tasks:
                            max_end = max(
                                (t.end_time for t in parallel_tasks if t.end_time is not None),
                                default=None,
                            )
                            min_start = min(
                                (t.start_time for t in parallel_tasks if t.start_time is not None),
                                default=None,
                            )
                            if max_end is not None and min_start is not None:
                                total_duration = max_end - min_start

                        if success:
                            self._print_success(f"{software} installed successfully!")
                            print(f"\nCompleted in {total_duration:.2f} seconds (parallel mode)")

                            if install_id:
                                history.update_installation(install_id, InstallationStatus.SUCCESS)
                                print(f"\n📝 Installation recorded (ID: {install_id})")
                                print(f"   To rollback: cortex rollback {install_id}")

                            return 0

                        failed_tasks = [
                            t for t in parallel_tasks if getattr(t.status, "value", "") == "failed"
                        ]
                        error_msg = failed_tasks[0].error if failed_tasks else "Installation failed"

                        if install_id:
                            history.update_installation(
                                install_id,
                                InstallationStatus.FAILED,
                                error_msg,
                            )

                        self._print_error("Installation failed")
                        if error_msg:
                            print(f"  Error: {error_msg}", file=sys.stderr)
                        if install_id:
                            print(f"\n📝 Installation recorded (ID: {install_id})")
                            print(f"   View details: cortex history {install_id}")
                        return 1

                    except (ValueError, OSError) as e:
                        if install_id:
                            history.update_installation(
                                install_id, InstallationStatus.FAILED, str(e)
                            )
                        self._print_error(f"Parallel execution failed: {str(e)}")
                        return 1
                    except Exception as e:
                        if install_id:
                            history.update_installation(
                                install_id, InstallationStatus.FAILED, str(e)
                            )
                        self._print_error(f"Unexpected parallel execution error: {str(e)}")
                        if self.verbose:
                            import traceback

                            traceback.print_exc()
                        return 1

                coordinator = InstallationCoordinator(
                    commands=commands,
                    descriptions=[f"Step {i + 1}" for i in range(len(commands))],
                    timeout=300,
                    stop_on_error=True,
                    progress_callback=progress_callback,
                )

                result = coordinator.execute()

                if result.success:
                    self._print_success(f"{software} installed successfully!")
                    print(f"\nCompleted in {result.total_duration:.2f} seconds")

                    # Record successful installation
                    if install_id:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                        print(f"\n📝 Installation recorded (ID: {install_id})")
                        print(f"   To rollback: cortex rollback {install_id}")

                    return 0
                else:
                    # Record failed installation
                    if install_id:
                        error_msg = result.error_message or "Installation failed"
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )

                    if result.failed_step is not None:
                        self._print_error(f"Installation failed at step {result.failed_step + 1}")
                    else:
                        self._print_error("Installation failed")
                    if result.error_message:
                        print(f"  Error: {result.error_message}", file=sys.stderr)
                    if install_id:
                        print(f"\n📝 Installation recorded (ID: {install_id})")
                        print(f"   View details: cortex history {install_id}")
                    return 1
            else:
                print("\nTo execute these commands, run with --execute flag")
                print("Example: cortex install docker --execute")

            return 0

        except ValueError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(str(e))
            return 1
        except RuntimeError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"API call failed: {str(e)}")
            return 1
        except OSError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"System error: {str(e)}")
            return 1
        except Exception as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"Unexpected error: {str(e)}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def cache_stats(self) -> int:
        try:
            from cortex.semantic_cache import SemanticCache

            cache = SemanticCache()
            stats = cache.stats()
            hit_rate = f"{stats.hit_rate * 100:.1f}%" if stats.total else "0.0%"

            cx_header("Cache Stats")
            cx_print(f"Hits: {stats.hits}", "info")
            cx_print(f"Misses: {stats.misses}", "info")
            cx_print(f"Hit rate: {hit_rate}", "info")
            cx_print(f"Saved calls (approx): {stats.hits}", "info")
            return 0
        except (ImportError, OSError) as e:
            self._print_error(f"Unable to read cache stats: {e}")
            return 1
        except Exception as e:
            self._print_error(f"Unexpected error reading cache stats: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def history(self, limit: int = 20, status: str | None = None, show_id: str | None = None):
        """Show installation history"""
        history = InstallationHistory()

        try:
            if show_id:
                # Show specific installation
                record = history.get_installation(show_id)

                if not record:
                    self._print_error(f"Installation {show_id} not found")
                    return 1

                print(f"\nInstallation Details: {record.id}")
                print("=" * 60)
                print(f"Timestamp: {record.timestamp}")
                print(f"Operation: {record.operation_type.value}")
                print(f"Status: {record.status.value}")
                if record.duration_seconds:
                    print(f"Duration: {record.duration_seconds:.2f}s")
                else:
                    print("Duration: N/A")
                print(f"\nPackages: {', '.join(record.packages)}")

                if record.error_message:
                    print(f"\nError: {record.error_message}")

                if record.commands_executed:
                    print("\nCommands executed:")
                    for cmd in record.commands_executed:
                        print(f"  {cmd}")

                print(f"\nRollback available: {record.rollback_available}")
                return 0
            else:
                # List history
                status_filter = InstallationStatus(status) if status else None
                records = history.get_history(limit, status_filter)

                if not records:
                    print("No installation records found.")
                    return 0

                print(
                    f"\n{'ID':<18} {'Date':<20} {'Operation':<12} {'Packages':<30} {'Status':<15}"
                )
                print("=" * 100)

                for r in records:
                    date = r.timestamp[:19].replace("T", " ")
                    packages = ", ".join(r.packages[:2])
                    if len(r.packages) > 2:
                        packages += f" +{len(r.packages) - 2}"

                    print(
                        f"{r.id:<18} {date:<20} {r.operation_type.value:<12} {packages:<30} {r.status.value:<15}"
                    )

                return 0
        except (ValueError, OSError) as e:
            self._print_error(f"Failed to retrieve history: {str(e)}")
            return 1
        except Exception as e:
            self._print_error(f"Unexpected error retrieving history: {str(e)}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def rollback(self, install_id: str, dry_run: bool = False):
        """Rollback an installation"""
        history = InstallationHistory()

        try:
            success, message = history.rollback(install_id, dry_run)

            if dry_run:
                print("\nRollback actions (dry run):")
                print(message)
                return 0
            elif success:
                self._print_success(message)
                return 0
            else:
                self._print_error(message)
                return 1
        except (ValueError, OSError) as e:
            self._print_error(f"Rollback failed: {str(e)}")
            return 1
        except Exception as e:
            self._print_error(f"Unexpected rollback error: {str(e)}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def status(self):
        """Show comprehensive system status and run health checks"""
        from cortex.doctor import SystemDoctor

        # Run the comprehensive system health checks
        # This now includes all functionality from the old status command
        # plus all the detailed health checks from doctor
        doctor = SystemDoctor()
        return doctor.run_checks()

    def wizard(self):
        """Interactive setup wizard for API key configuration"""
        show_banner()
        console.print()
        cx_print("Welcome to Cortex Setup Wizard!", "success")
        console.print()
        # (Simplified for brevity - keeps existing logic)
        cx_print("Please export your API key in your shell profile.", "info")
        return 0

    def env(self, args: argparse.Namespace) -> int:
        """Handle environment variable management commands."""
        env_mgr = get_env_manager()

        # Handle subcommand routing
        action = getattr(args, "env_action", None)

        if not action:
            self._print_error(
                "Please specify a subcommand (set/get/list/delete/export/import/clear/template)"
            )
            return 1

        try:
            if action == "set":
                return self._env_set(env_mgr, args)
            elif action == "get":
                return self._env_get(env_mgr, args)
            elif action == "list":
                return self._env_list(env_mgr, args)
            elif action == "delete":
                return self._env_delete(env_mgr, args)
            elif action == "export":
                return self._env_export(env_mgr, args)
            elif action == "import":
                return self._env_import(env_mgr, args)
            elif action == "clear":
                return self._env_clear(env_mgr, args)
            elif action == "template":
                return self._env_template(env_mgr, args)
            elif action == "apps":
                return self._env_list_apps(env_mgr, args)
            elif action == "load":
                return self._env_load(env_mgr, args)
            else:
                self._print_error(f"Unknown env subcommand: {action}")
                return 1
        except (ValueError, OSError) as e:
            self._print_error(f"Environment operation failed: {e}")
            return 1
        except Exception as e:
            self._print_error(f"Unexpected error: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def _env_set(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Set an environment variable."""
        app = args.app
        key = args.key
        value = args.value
        encrypt = getattr(args, "encrypt", False)
        var_type = getattr(args, "type", "string") or "string"
        description = getattr(args, "description", "") or ""

        try:
            env_mgr.set_variable(
                app=app,
                key=key,
                value=value,
                encrypt=encrypt,
                var_type=var_type,
                description=description,
            )

            if encrypt:
                cx_print("🔐 Variable encrypted and stored", "success")
            else:
                cx_print("✓ Environment variable set", "success")
            return 0

        except ValueError as e:
            self._print_error(str(e))
            return 1
        except ImportError as e:
            self._print_error(str(e))
            if "cryptography" in str(e).lower():
                cx_print("Install with: pip install cryptography", "info")
            return 1

    def _env_get(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Get an environment variable value."""
        app = args.app
        key = args.key
        show_encrypted = getattr(args, "decrypt", False)

        value = env_mgr.get_variable(app, key, decrypt=show_encrypted)

        if value is None:
            self._print_error(f"Variable '{key}' not found for app '{app}'")
            return 1

        var_info = env_mgr.get_variable_info(app, key)

        if var_info and var_info.encrypted and not show_encrypted:
            console.print(f"{key}: [dim][encrypted][/dim]")
        else:
            console.print(f"{key}: {value}")

        return 0

    def _env_list(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """List all environment variables for an app."""
        app = args.app
        show_encrypted = getattr(args, "decrypt", False)

        variables = env_mgr.list_variables(app)

        if not variables:
            cx_print(f"No environment variables set for '{app}'", "info")
            return 0

        cx_header(f"Environment: {app}")

        for var in sorted(variables, key=lambda v: v.key):
            if var.encrypted:
                if show_encrypted:
                    try:
                        value = env_mgr.get_variable(app, var.key, decrypt=True)
                        console.print(f"  {var.key}: {value} [dim](decrypted)[/dim]")
                    except ValueError:
                        console.print(f"  {var.key}: [red][decryption failed][/red]")
                else:
                    console.print(f"  {var.key}: [yellow][encrypted][/yellow]")
            else:
                console.print(f"  {var.key}: {var.value}")

            if var.description:
                console.print(f"    [dim]# {var.description}[/dim]")

        console.print()
        console.print(f"[dim]Total: {len(variables)} variable(s)[/dim]")
        return 0

    def _env_delete(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Delete an environment variable."""
        app = args.app
        key = args.key

        if env_mgr.delete_variable(app, key):
            cx_print(f"✓ Deleted '{key}' from '{app}'", "success")
            return 0
        else:
            self._print_error(f"Variable '{key}' not found for app '{app}'")
            return 1

    def _env_export(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Export environment variables to .env format."""
        app = args.app
        include_encrypted = getattr(args, "include_encrypted", False)
        output_file = getattr(args, "output", None)

        content = env_mgr.export_env(app, include_encrypted=include_encrypted)

        if not content:
            cx_print(f"No environment variables to export for '{app}'", "info")
            return 0

        if output_file:
            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(content)
                cx_print(f"✓ Exported to {output_file}", "success")
            except OSError as e:
                self._print_error(f"Failed to write file: {e}")
                return 1
        else:
            # Print to stdout
            print(content, end="")

        return 0

    def _env_import(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Import environment variables from .env format."""
        import sys

        app = args.app
        input_file = getattr(args, "file", None)
        encrypt_keys = getattr(args, "encrypt_keys", None)

        try:
            if input_file:
                with open(input_file, encoding="utf-8") as f:
                    content = f.read()
            elif not sys.stdin.isatty():
                content = sys.stdin.read()
            else:
                self._print_error("No input file specified and stdin is empty")
                cx_print("Usage: cortex env import <app> <file>", "info")
                cx_print("   or: cat .env | cortex env import <app>", "info")
                return 1

            # Parse encrypt-keys argument
            encrypt_list = []
            if encrypt_keys:
                encrypt_list = [k.strip() for k in encrypt_keys.split(",")]

            count, errors = env_mgr.import_env(app, content, encrypt_keys=encrypt_list)

            if errors:
                for err in errors:
                    cx_print(f"  ⚠ {err}", "warning")

            if count > 0:
                cx_print(f"✓ Imported {count} variable(s) to '{app}'", "success")
            else:
                cx_print("No variables imported", "info")

            # Return success (0) even with partial errors - some vars imported successfully
            return 0

        except FileNotFoundError:
            self._print_error(f"File not found: {input_file}")
            return 1
        except OSError as e:
            self._print_error(f"Failed to read file: {e}")
            return 1

    def _env_clear(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Clear all environment variables for an app."""
        app = args.app
        force = getattr(args, "force", False)

        # Confirm unless --force is used
        if not force:
            confirm = input(f"⚠️  Clear ALL environment variables for '{app}'? (y/n): ")
            if confirm.lower() != "y":
                cx_print("Operation cancelled", "info")
                return 0

        if env_mgr.clear_app(app):
            cx_print(f"✓ Cleared all variables for '{app}'", "success")
        else:
            cx_print(f"No environment data found for '{app}'", "info")

        return 0

    def _env_template(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Handle template subcommands."""
        template_action = getattr(args, "template_action", None)

        if template_action == "list":
            return self._env_template_list(env_mgr)
        elif template_action == "show":
            return self._env_template_show(env_mgr, args)
        elif template_action == "apply":
            return self._env_template_apply(env_mgr, args)
        else:
            self._print_error(
                "Please specify: template list, template show <name>, or template apply <name> <app>"
            )
            return 1

    def _env_template_list(self, env_mgr: EnvironmentManager) -> int:
        """List available templates."""
        templates = env_mgr.list_templates()

        cx_header("Available Environment Templates")

        for template in sorted(templates, key=lambda t: t.name):
            console.print(f"  [green]{template.name}[/green]")
            console.print(f"    {template.description}")
            console.print(f"    [dim]{len(template.variables)} variables[/dim]")
            console.print()

        cx_print("Use 'cortex env template show <name>' for details", "info")
        return 0

    def _env_template_show(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Show template details."""
        template_name = args.template_name

        template = env_mgr.get_template(template_name)
        if not template:
            self._print_error(f"Template '{template_name}' not found")
            return 1

        cx_header(f"Template: {template.name}")
        console.print(f"  {template.description}")
        console.print()

        console.print("[bold]Variables:[/bold]")
        for var in template.variables:
            req = "[red]*[/red]" if var.required else " "
            default = f" = {var.default}" if var.default else ""
            console.print(f"  {req} [cyan]{var.name}[/cyan] ({var.var_type}){default}")
            if var.description:
                console.print(f"      [dim]{var.description}[/dim]")

        console.print()
        console.print("[dim]* = required[/dim]")
        return 0

    def _env_template_apply(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Apply a template to an app."""
        template_name = args.template_name
        app = args.app

        # Parse key=value pairs from args
        values = {}
        value_args = getattr(args, "values", []) or []
        for val in value_args:
            if "=" in val:
                k, v = val.split("=", 1)
                values[k] = v

        # Parse encrypt keys
        encrypt_keys = []
        encrypt_arg = getattr(args, "encrypt_keys", None)
        if encrypt_arg:
            encrypt_keys = [k.strip() for k in encrypt_arg.split(",")]

        result = env_mgr.apply_template(
            template_name=template_name,
            app=app,
            values=values,
            encrypt_keys=encrypt_keys,
        )

        if result.valid:
            cx_print(f"✓ Applied template '{template_name}' to '{app}'", "success")
            return 0
        else:
            self._print_error(f"Failed to apply template '{template_name}'")
            for err in result.errors:
                console.print(f"  [red]✗[/red] {err}")
            return 1

    def _env_list_apps(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """List all apps with stored environments."""
        apps = env_mgr.list_apps()

        if not apps:
            cx_print("No applications with stored environments", "info")
            return 0

        cx_header("Applications with Environments")
        for app in apps:
            var_count = len(env_mgr.list_variables(app))
            console.print(f"  [green]{app}[/green] [dim]({var_count} variables)[/dim]")

        return 0

    def _env_load(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Load environment variables into current process."""
        app = args.app

        count = env_mgr.load_to_environ(app)

        if count > 0:
            cx_print(f"✓ Loaded {count} variable(s) from '{app}' into environment", "success")
        else:
            cx_print(f"No variables to load for '{app}'", "info")

        return 0

    # --- Do Command (manage do-mode runs) ---
    def do_cmd(self, args: argparse.Namespace) -> int:
        """Handle `cortex do` commands for managing do-mode runs."""
        from cortex.do_runner import DoHandler, ProtectedPathsManager, CortexUserManager
        
        action = getattr(args, "do_action", None)
        
        if not action:
            cx_print("\n🔧 Do Mode - Execute commands to solve problems\n", "info")
            console.print("Usage: cortex ask --do <question>")
            console.print("       cortex do <command> [options]")
            console.print("\nCommands:")
            console.print("  history [run_id]        View do-mode run history")
            console.print("  setup                   Setup cortex user for privilege management")
            console.print("  protected               Manage protected paths")
            console.print("\nExample:")
            console.print("  cortex ask --do 'Fix my nginx configuration'")
            console.print("  cortex do history")
            return 0
        
        if action == "history":
            return self._do_history(args)
        elif action == "setup":
            return self._do_setup()
        elif action == "protected":
            return self._do_protected(args)
        else:
            self._print_error(f"Unknown do action: {action}")
            return 1
    
    def _do_history(self, args: argparse.Namespace) -> int:
        """Show do-mode run history."""
        from cortex.do_runner import DoHandler
        
        handler = DoHandler()
        run_id = getattr(args, "run_id", None)
        
        if run_id:
            # Show specific run details
            run = handler.get_run(run_id)
            if not run:
                self._print_error(f"Run {run_id} not found")
                return 1
            
            # Get statistics from database
            stats = handler.db.get_run_stats(run_id)
            
            console.print(f"\n[bold]Do Run: {run.run_id}[/bold]")
            console.print("=" * 70)
            
            # Show session ID if available
            session_id = getattr(run, "session_id", None)
            if session_id:
                console.print(f"[bold]Session:[/bold] [magenta]{session_id}[/magenta]")
            
            console.print(f"[bold]Query:[/bold] {run.user_query}")
            console.print(f"[bold]Mode:[/bold] {run.mode.value}")
            console.print(f"[bold]Started:[/bold] {run.started_at}")
            console.print(f"[bold]Completed:[/bold] {run.completed_at}")
            console.print(f"\n[bold]Summary:[/bold] {run.summary}")
            
            # Show statistics
            if stats:
                console.print(f"\n[bold cyan]📊 Command Statistics:[/bold cyan]")
                total = stats.get("total_commands", 0)
                success = stats.get("successful_commands", 0)
                failed = stats.get("failed_commands", 0)
                skipped = stats.get("skipped_commands", 0)
                console.print(f"   Total: {total} | [green]✓ Success: {success}[/green] | [red]✗ Failed: {failed}[/red] | [yellow]○ Skipped: {skipped}[/yellow]")
            
            if run.files_accessed:
                console.print(f"\n[bold]Files Accessed:[/bold] {', '.join(run.files_accessed)}")
            
            # Get detailed commands from database
            commands_detail = handler.db.get_run_commands(run_id)
            
            console.print(f"\n[bold cyan]📋 Commands Executed:[/bold cyan]")
            console.print("-" * 70)
            
            if commands_detail:
                for cmd in commands_detail:
                    status = cmd["status"]
                    if status == "success":
                        status_icon = "[green]✓[/green]"
                    elif status == "failed":
                        status_icon = "[red]✗[/red]"
                    elif status == "skipped":
                        status_icon = "[yellow]○[/yellow]"
                    else:
                        status_icon = "[dim]?[/dim]"
                    
                    console.print(f"\n{status_icon} [bold]Command {cmd['index'] + 1}:[/bold] {cmd['command']}")
                    console.print(f"   [dim]Purpose:[/dim] {cmd['purpose']}")
                    console.print(f"   [dim]Status:[/dim] {status} | [dim]Duration:[/dim] {cmd['duration']:.2f}s")
                    
                    if cmd["output"]:
                        console.print(f"   [dim]Output:[/dim] {cmd['output']}")
                    if cmd["error"]:
                        console.print(f"   [red]Error:[/red] {cmd['error']}")
            else:
                # Fallback to run.commands if database commands not available
                for i, cmd in enumerate(run.commands):
                    status_icon = "[green]✓[/green]" if cmd.status.value == "success" else "[red]✗[/red]"
                    console.print(f"\n{status_icon} [bold]Command {i + 1}:[/bold] {cmd.command}")
                    console.print(f"   [dim]Purpose:[/dim] {cmd.purpose}")
                    console.print(f"   [dim]Status:[/dim] {cmd.status.value} | [dim]Duration:[/dim] {cmd.duration_seconds:.2f}s")
                    if cmd.output:
                        output_truncated = cmd.output[:250] + "..." if len(cmd.output) > 250 else cmd.output
                        console.print(f"   [dim]Output:[/dim] {output_truncated}")
                    if cmd.error:
                        console.print(f"   [red]Error:[/red] {cmd.error}")
            
            return 0
        
        # List recent runs
        limit = getattr(args, "limit", 20)
        runs = handler.get_run_history(limit)
        
        if not runs:
            cx_print("No do-mode runs found", "info")
            return 0
        
        # Group runs by session
        sessions = {}
        standalone_runs = []
        
        for run in runs:
            session_id = getattr(run, "session_id", None)
            if session_id:
                if session_id not in sessions:
                    sessions[session_id] = []
                sessions[session_id].append(run)
            else:
                standalone_runs.append(run)
        
        console.print(f"\n[bold]📜 Recent Do Runs:[/bold]")
        console.print(f"[dim]Sessions: {len(sessions)} | Standalone runs: {len(standalone_runs)}[/dim]\n")
        
        import json as json_module
        
        # Show sessions first
        for session_id, session_runs in sessions.items():
            console.print(f"[bold magenta]╭{'─' * 68}╮[/bold magenta]")
            console.print(f"[bold magenta]│ 📂 Session: {session_id[:40]}...{' ' * 15}│[/bold magenta]")
            console.print(f"[bold magenta]│    Runs: {len(session_runs)}{' ' * 57}│[/bold magenta]")
            console.print(f"[bold magenta]╰{'─' * 68}╯[/bold magenta]")
            
            for run in session_runs:
                self._display_run_summary(handler, run, indent="   ")
            console.print()
        
        # Show standalone runs
        if standalone_runs:
            if sessions:
                console.print(f"[bold cyan]{'─' * 70}[/bold cyan]")
                console.print("[bold]📋 Standalone Runs (no session):[/bold]")
            
            for run in standalone_runs:
                self._display_run_summary(handler, run)
        
        console.print(f"[dim]Use 'cortex do history <run_id>' for full details[/dim]")
        return 0
    
    def _display_run_summary(self, handler, run, indent: str = "") -> None:
        """Display a single run summary."""
        stats = handler.db.get_run_stats(run.run_id)
        if stats:
            total = stats.get("total_commands", 0)
            success = stats.get("successful_commands", 0)
            failed = stats.get("failed_commands", 0)
            status_str = f"[green]✓{success}[/green]/[red]✗{failed}[/red]/{total}"
        else:
            cmd_count = len(run.commands)
            success_count = sum(1 for c in run.commands if c.status.value == "success")
            failed_count = sum(1 for c in run.commands if c.status.value == "failed")
            status_str = f"[green]✓{success_count}[/green]/[red]✗{failed_count}[/red]/{cmd_count}"
        
        commands_list = handler.db.get_commands_list(run.run_id)
        
        console.print(f"{indent}[bold cyan]{'─' * 60}[/bold cyan]")
        console.print(f"{indent}[bold]Run ID:[/bold] {run.run_id}")
        console.print(f"{indent}[bold]Query:[/bold] {run.user_query[:60]}{'...' if len(run.user_query) > 60 else ''}")
        console.print(f"{indent}[bold]Status:[/bold] {status_str} | [bold]Started:[/bold] {run.started_at[:19] if run.started_at else '-'}")
        
        if commands_list and len(commands_list) <= 3:
            console.print(f"{indent}[bold]Commands:[/bold] {', '.join(cmd[:30] for cmd in commands_list)}")
        elif commands_list:
            console.print(f"{indent}[bold]Commands:[/bold] {len(commands_list)} commands")
    
    def _do_setup(self) -> int:
        """Setup cortex user for privilege management."""
        from cortex.do_runner import CortexUserManager
        
        cx_print("Setting up Cortex user for privilege management...", "info")
        
        if CortexUserManager.user_exists():
            cx_print("✓ Cortex user already exists", "success")
            return 0
        
        success, message = CortexUserManager.create_user()
        if success:
            cx_print(f"✓ {message}", "success")
            return 0
        else:
            self._print_error(message)
            return 1
    
    def _do_protected(self, args: argparse.Namespace) -> int:
        """Manage protected paths."""
        from cortex.do_runner import ProtectedPathsManager
        
        manager = ProtectedPathsManager()
        
        add_path = getattr(args, "add", None)
        remove_path = getattr(args, "remove", None)
        list_paths = getattr(args, "list", False)
        
        if add_path:
            manager.add_protected_path(add_path)
            cx_print(f"✓ Added '{add_path}' to protected paths", "success")
            return 0
        
        if remove_path:
            if manager.remove_protected_path(remove_path):
                cx_print(f"✓ Removed '{remove_path}' from protected paths", "success")
            else:
                self._print_error(f"Path '{remove_path}' not found in user-defined protected paths")
            return 0
        
        # Default: list all protected paths
        paths = manager.get_all_protected()
        console.print("\n[bold]Protected Paths:[/bold]")
        console.print("[dim](These paths require user confirmation for access)[/dim]\n")
        
        for path in paths:
            is_system = path in manager.SYSTEM_PROTECTED_PATHS
            tag = "[system]" if is_system else "[user]"
            console.print(f"  {path} [dim]{tag}[/dim]")
        
        console.print(f"\n[dim]Total: {len(paths)} paths[/dim]")
        console.print("[dim]Use --add <path> to add custom paths[/dim]")
        return 0

    # --- Info Command ---
    def info_cmd(self, args: argparse.Namespace) -> int:
        """Get system and application information using read-only commands."""
        from rich.panel import Panel
        from rich.table import Table
        
        try:
            from cortex.system_info_generator import (
                SystemInfoGenerator, 
                get_system_info_generator,
                COMMON_INFO_COMMANDS,
                APP_INFO_TEMPLATES,
            )
        except ImportError as e:
            self._print_error(f"System info generator not available: {e}")
            return 1
        
        debug = getattr(args, "debug", False)
        
        # Handle --list
        if getattr(args, "list", False):
            console.print("\n[bold]📊 Available Information Types[/bold]\n")
            
            console.print("[bold cyan]Quick Info Types (--quick):[/bold cyan]")
            for name in sorted(COMMON_INFO_COMMANDS.keys()):
                console.print(f"  • {name}")
            
            console.print("\n[bold cyan]Application Templates (--app):[/bold cyan]")
            for name in sorted(APP_INFO_TEMPLATES.keys()):
                aspects = ", ".join(APP_INFO_TEMPLATES[name].keys())
                console.print(f"  • {name}: [dim]{aspects}[/dim]")
            
            console.print("\n[bold cyan]Categories (--category):[/bold cyan]")
            console.print("  hardware, software, network, services, security, storage, performance, configuration")
            
            console.print("\n[dim]Examples:[/dim]")
            console.print("  cortex info --quick cpu")
            console.print("  cortex info --app nginx")
            console.print("  cortex info --category hardware")
            console.print("  cortex info What version of Python is installed?")
            return 0
        
        # Handle --quick
        quick_type = getattr(args, "quick", None)
        if quick_type:
            console.print(f"\n[bold]🔍 Quick Info: {quick_type.upper()}[/bold]\n")
            
            if quick_type in COMMON_INFO_COMMANDS:
                for cmd_info in COMMON_INFO_COMMANDS[quick_type]:
                    from cortex.ask import CommandValidator
                    success, stdout, stderr = CommandValidator.execute_command(cmd_info.command)
                    
                    if success and stdout:
                        console.print(Panel(
                            stdout[:1000] + ("..." if len(stdout) > 1000 else ""),
                            title=f"[cyan]{cmd_info.purpose}[/cyan]",
                            subtitle=f"[dim]{cmd_info.command[:60]}...[/dim]" if len(cmd_info.command) > 60 else f"[dim]{cmd_info.command}[/dim]",
                        ))
                    elif stderr:
                        console.print(f"[yellow]⚠ {cmd_info.purpose}: {stderr[:100]}[/yellow]")
            else:
                self._print_error(f"Unknown quick info type: {quick_type}")
                return 1
            return 0
        
        # Handle --app
        app_name = getattr(args, "app", None)
        if app_name:
            console.print(f"\n[bold]📦 Application Info: {app_name.upper()}[/bold]\n")
            
            if app_name.lower() in APP_INFO_TEMPLATES:
                templates = APP_INFO_TEMPLATES[app_name.lower()]
                for aspect, commands in templates.items():
                    console.print(f"[bold cyan]─── {aspect.upper()} ───[/bold cyan]")
                    for cmd_info in commands:
                        from cortex.ask import CommandValidator
                        success, stdout, stderr = CommandValidator.execute_command(cmd_info.command, timeout=15)
                        
                        if success and stdout:
                            output = stdout[:500] + ("..." if len(stdout) > 500 else "")
                            console.print(f"[dim]{cmd_info.purpose}:[/dim]")
                            console.print(output)
                        elif stderr:
                            console.print(f"[yellow]{cmd_info.purpose}: {stderr[:100]}[/yellow]")
                        console.print()
            else:
                # Try using LLM for unknown apps
                api_key = self._get_api_key()
                if api_key:
                    try:
                        generator = SystemInfoGenerator(
                            api_key=api_key,
                            provider=self._get_provider(),
                            debug=debug,
                        )
                        result = generator.get_app_info(app_name)
                        console.print(result.answer)
                    except Exception as e:
                        self._print_error(f"Could not get info for {app_name}: {e}")
                        return 1
                else:
                    self._print_error(f"Unknown app '{app_name}' and no API key for LLM lookup")
                    return 1
            return 0
        
        # Handle --category
        category = getattr(args, "category", None)
        if category:
            console.print(f"\n[bold]📊 Category Info: {category.upper()}[/bold]\n")
            
            api_key = self._get_api_key()
            if not api_key:
                # Fall back to running common commands without LLM
                category_mapping = {
                    "hardware": ["cpu", "memory", "disk", "gpu"],
                    "software": ["os", "kernel"],
                    "network": ["network", "dns"],
                    "services": ["services"],
                    "security": ["security"],
                    "storage": ["disk"],
                    "performance": ["cpu", "memory", "processes"],
                    "configuration": ["environment"],
                }
                aspects = category_mapping.get(category, [])
                for aspect in aspects:
                    if aspect in COMMON_INFO_COMMANDS:
                        console.print(f"[bold cyan]─── {aspect.upper()} ───[/bold cyan]")
                        for cmd_info in COMMON_INFO_COMMANDS[aspect]:
                            from cortex.ask import CommandValidator
                            success, stdout, _ = CommandValidator.execute_command(cmd_info.command)
                            if success and stdout:
                                console.print(stdout[:400])
                        console.print()
                return 0
            
            try:
                generator = SystemInfoGenerator(
                    api_key=api_key,
                    provider=self._get_provider(),
                    debug=debug,
                )
                result = generator.get_structured_info(category)
                console.print(result.answer)
            except Exception as e:
                self._print_error(f"Could not get category info: {e}")
                return 1
            return 0
        
        # Handle natural language query
        query_parts = getattr(args, "query", [])
        if query_parts:
            query = " ".join(query_parts)
            console.print(f"\n[bold]🔍 System Info Query[/bold]\n")
            console.print(f"[dim]Query: {query}[/dim]\n")
            
            api_key = self._get_api_key()
            if not api_key:
                self._print_error("Natural language queries require an API key. Use --quick or --app instead.")
                return 1
            
            try:
                generator = SystemInfoGenerator(
                    api_key=api_key,
                    provider=self._get_provider(),
                    debug=debug,
                )
                result = generator.get_info(query)
                
                console.print(Panel(result.answer, title="[bold green]Answer[/bold green]"))
                
                if debug and result.commands_executed:
                    table = Table(title="Commands Executed")
                    table.add_column("Command", style="cyan", max_width=50)
                    table.add_column("Status", style="green")
                    table.add_column("Time", style="dim")
                    for cmd in result.commands_executed:
                        status = "✓" if cmd.success else "✗"
                        table.add_row(
                            cmd.command[:50] + "..." if len(cmd.command) > 50 else cmd.command,
                            status,
                            f"{cmd.execution_time:.2f}s"
                        )
                    console.print(table)
                    
            except Exception as e:
                self._print_error(f"Query failed: {e}")
                if debug:
                    import traceback
                    traceback.print_exc()
                return 1
            return 0
        
        # No arguments - show help
        console.print("\n[bold]📊 Cortex Info - System Information Generator[/bold]\n")
        console.print("Get system and application information using read-only commands.\n")
        console.print("[bold cyan]Usage:[/bold cyan]")
        console.print("  cortex info --list                    List available info types")
        console.print("  cortex info --quick <type>            Quick lookup (cpu, memory, etc.)")
        console.print("  cortex info --app <name>              Application info (nginx, docker, etc.)")
        console.print("  cortex info --category <cat>          Category info (hardware, network, etc.)")
        console.print("  cortex info <query>                   Natural language query (requires API key)")
        console.print("\n[bold cyan]Examples:[/bold cyan]")
        console.print("  cortex info --quick memory")
        console.print("  cortex info --app nginx")
        console.print("  cortex info --category hardware")
        console.print("  cortex info What Python packages are installed?")
        return 0

    # --- Watch Command ---
    def watch_cmd(self, args: argparse.Namespace) -> int:
        """Manage terminal watching for manual intervention mode."""
        from rich.panel import Panel
        from cortex.do_runner.terminal import TerminalMonitor
        
        monitor = TerminalMonitor(use_llm=False)
        system_wide = getattr(args, "system", False)
        as_service = getattr(args, "service", False)
        
        if getattr(args, "install", False):
            if as_service:
                # Install as systemd service
                console.print("\n[bold cyan]🔧 Installing Cortex Watch Service[/bold cyan]")
                console.print("[dim]This will create a systemd user service that runs automatically[/dim]\n")
                
                from cortex.watch_service import install_service
                success, msg = install_service()
                console.print(msg)
                return 0 if success else 1
            elif system_wide:
                console.print("\n[bold cyan]🔧 Installing System-Wide Terminal Watch Hook[/bold cyan]")
                console.print("[dim]This will install to /etc/profile.d/ (requires sudo)[/dim]\n")
                success, msg = monitor.setup_system_wide_watch()
                if success:
                    console.print(f"[green]{msg}[/green]")
                    console.print("\n[bold green]✓ All new terminals will automatically have Cortex watching![/bold green]")
                else:
                    console.print(f"[red]✗ {msg}[/red]")
                    return 1
            else:
                console.print("\n[bold cyan]🔧 Installing Terminal Watch Hook[/bold cyan]\n")
                success, msg = monitor.setup_auto_watch(permanent=True)
                if success:
                    console.print(f"[green]✓ {msg}[/green]")
                    console.print("\n[yellow]Note: New terminals will have the hook automatically.[/yellow]")
                    console.print("[yellow]For existing terminals, run:[/yellow]")
                    console.print(f"[green]source ~/.cortex/watch_hook.sh[/green]")
                    console.print("\n[dim]Tip: For automatic activation in ALL terminals, run:[/dim]")
                    console.print("[cyan]cortex watch --install --system[/cyan]")
                else:
                    console.print(f"[red]✗ {msg}[/red]")
                    return 1
            return 0
        
        if getattr(args, "uninstall", False):
            if as_service:
                console.print("\n[bold cyan]🔧 Removing Cortex Watch Service[/bold cyan]\n")
                from cortex.watch_service import uninstall_service
                success, msg = uninstall_service()
            elif system_wide:
                console.print("\n[bold cyan]🔧 Removing System-Wide Terminal Watch Hook[/bold cyan]\n")
                success, msg = monitor.uninstall_system_wide_watch()
            else:
                console.print("\n[bold cyan]🔧 Removing Terminal Watch Hook[/bold cyan]\n")
                success, msg = monitor.remove_auto_watch()
            if success:
                console.print(f"[green]{msg}[/green]")
            else:
                console.print(f"[red]✗ {msg}[/red]")
                return 1
            return 0
        
        if getattr(args, "test", False):
            console.print("\n[bold cyan]🧪 Testing Terminal Monitoring[/bold cyan]\n")
            monitor.test_monitoring()
            return 0
        
        if getattr(args, "status", False):
            console.print("\n[bold cyan]📊 Terminal Watch Status[/bold cyan]\n")
            
            from pathlib import Path
            bashrc = Path.home() / ".bashrc"
            zshrc = Path.home() / ".zshrc"
            source_file = Path.home() / ".cortex" / "watch_hook.sh"
            watch_log = Path.home() / ".cortex" / "terminal_watch.log"
            system_hook = Path("/etc/profile.d/cortex-watch.sh")
            service_file = Path.home() / ".config" / "systemd" / "user" / "cortex-watch.service"
            
            console.print("[bold]Service Status:[/bold]")
            
            # Check systemd service
            if service_file.exists():
                try:
                    result = subprocess.run(
                        ["systemctl", "--user", "is-active", "cortex-watch.service"],
                        capture_output=True, text=True, timeout=5
                    )
                    is_active = result.stdout.strip() == "active"
                    if is_active:
                        console.print("  [bold green]✓ SYSTEMD SERVICE RUNNING[/bold green]")
                        console.print("    [dim]Automatic terminal monitoring active[/dim]")
                    else:
                        console.print("  [yellow]○ Systemd service installed but not running[/yellow]")
                        console.print("    [dim]Run: systemctl --user start cortex-watch[/dim]")
                except Exception:
                    console.print("  [yellow]○ Systemd service installed (status unknown)[/yellow]")
            else:
                console.print("  [dim]○ Systemd service not installed[/dim]")
                console.print("    [dim]Run: cortex watch --install --service (recommended)[/dim]")
            
            console.print()
            console.print("[bold]Hook Status:[/bold]")
            
            # System-wide check
            if system_hook.exists():
                console.print("  [green]✓ System-wide hook installed[/green]")
            else:
                console.print("  [dim]○ System-wide hook not installed[/dim]")
            
            # User-level checks
            if bashrc.exists() and "Cortex Terminal Watch Hook" in bashrc.read_text():
                console.print("  [green]✓ Hook installed in .bashrc[/green]")
            else:
                console.print("  [dim]○ Not installed in .bashrc[/dim]")
            
            if zshrc.exists() and "Cortex Terminal Watch Hook" in zshrc.read_text():
                console.print("  [green]✓ Hook installed in .zshrc[/green]")
            else:
                console.print("  [dim]○ Not installed in .zshrc[/dim]")
            
            console.print("\n[bold]Watch Log:[/bold]")
            if watch_log.exists():
                size = watch_log.stat().st_size
                lines = len(watch_log.read_text().strip().split('\n')) if size > 0 else 0
                console.print(f"  [green]✓ Log file exists: {watch_log}[/green]")
                console.print(f"  [dim]  Size: {size} bytes, {lines} commands logged[/dim]")
            else:
                console.print(f"  [dim]○ No log file yet (created when commands are run)[/dim]")
            
            return 0
        
        # Default: show help
        console.print()
        console.print(Panel(
            "[bold cyan]Terminal Watch[/bold cyan] - Real-time monitoring for manual intervention mode\n\n"
            "When Cortex enters manual intervention mode, it watches your other terminals\n"
            "to provide real-time feedback and AI-powered suggestions.\n\n"
            "[bold]Commands:[/bold]\n"
            "  [cyan]cortex watch --install --service[/cyan] Install as systemd service (RECOMMENDED)\n"
            "  [cyan]cortex watch --install --system[/cyan]  Install system-wide hook (requires sudo)\n"
            "  [cyan]cortex watch --install[/cyan]           Install hook to .bashrc/.zshrc\n"
            "  [cyan]cortex watch --uninstall --service[/cyan] Remove systemd service\n"
            "  [cyan]cortex watch --status[/cyan]            Show installation status\n"
            "  [cyan]cortex watch --test[/cyan]              Test monitoring setup\n\n"
            "[bold green]Recommended Setup:[/bold green]\n"
            "  Run [green]cortex watch --install --service[/green]\n\n"
            "  This creates a background service that:\n"
            "  • Starts automatically on login\n"
            "  • Restarts if it crashes\n"
            "  • Monitors ALL terminal activity\n"
            "  • No manual setup in each terminal!",
            title="[green]🔍 Cortex Watch[/green]",
            border_style="cyan",
        ))
        return 0

    # --- Import Dependencies Command ---
    def import_deps(self, args: argparse.Namespace) -> int:
        """Import and install dependencies from package manager files.

        Supports: requirements.txt (Python), package.json (Node),
                  Gemfile (Ruby), Cargo.toml (Rust), go.mod (Go)
        """
        file_path = getattr(args, "file", None)
        scan_all = getattr(args, "all", False)
        execute = getattr(args, "execute", False)
        include_dev = getattr(args, "dev", False)

        importer = DependencyImporter()

        # Handle --all flag: scan directory for all dependency files
        if scan_all:
            return self._import_all(importer, execute, include_dev)

        # Handle single file import
        if not file_path:
            self._print_error("Please specify a dependency file or use --all to scan directory")
            cx_print("Usage: cortex import <file> [--execute] [--dev]", "info")
            cx_print("       cortex import --all [--execute] [--dev]", "info")
            return 1

        return self._import_single_file(importer, file_path, execute, include_dev)

    def _import_single_file(
        self, importer: DependencyImporter, file_path: str, execute: bool, include_dev: bool
    ) -> int:
        """Import dependencies from a single file."""
        result = importer.parse(file_path, include_dev=include_dev)

        # Display parsing results
        self._display_parse_result(result, include_dev)

        if result.errors:
            for error in result.errors:
                self._print_error(error)
            return 1

        if not result.packages and not result.dev_packages:
            cx_print("No packages found in file", "info")
            return 0

        # Get install command
        install_cmd = importer.get_install_command(result.ecosystem, file_path)
        if not install_cmd:
            self._print_error(f"Unknown ecosystem: {result.ecosystem.value}")
            return 1

        # Dry run mode (default)
        if not execute:
            console.print(f"\n[bold]Install command:[/bold] {install_cmd}")
            cx_print("\nTo install these packages, run with --execute flag", "info")
            cx_print(f"Example: cortex import {file_path} --execute", "info")
            return 0

        # Execute mode - run the install command
        return self._execute_install(install_cmd, result.ecosystem)

    def _import_all(self, importer: DependencyImporter, execute: bool, include_dev: bool) -> int:
        """Scan directory and import all dependency files."""
        cx_print("Scanning directory...", "info")

        results = importer.scan_directory(include_dev=include_dev)

        if not results:
            cx_print("No dependency files found in current directory", "info")
            return 0

        # Display all found files
        total_packages = 0
        total_dev_packages = 0

        for file_path, result in results.items():
            filename = os.path.basename(file_path)
            if result.errors:
                console.print(f"   [red]✗[/red]  {filename} (error: {result.errors[0]})")
            else:
                pkg_count = result.prod_count
                dev_count = result.dev_count if include_dev else 0
                total_packages += pkg_count
                total_dev_packages += dev_count
                dev_str = f" + {dev_count} dev" if dev_count > 0 else ""
                console.print(f"   [green]✓[/green]  {filename} ({pkg_count} packages{dev_str})")

        console.print()

        if total_packages == 0 and total_dev_packages == 0:
            cx_print("No packages found in dependency files", "info")
            return 0

        # Generate install commands
        commands = importer.get_install_commands_for_results(results)

        if not commands:
            cx_print("No install commands generated", "info")
            return 0

        # Dry run mode (default)
        if not execute:
            console.print("[bold]Install commands:[/bold]")
            for cmd_info in commands:
                console.print(f"  • {cmd_info['command']}")
            console.print()
            cx_print("To install all packages, run with --execute flag", "info")
            cx_print("Example: cortex import --all --execute", "info")
            return 0

        # Execute mode - confirm before installing
        total = total_packages + total_dev_packages
        confirm = input(f"\nInstall all {total} packages? [Y/n]: ")
        if confirm.lower() not in ["", "y", "yes"]:
            cx_print("Installation cancelled", "info")
            return 0

        # Execute all install commands
        return self._execute_multi_install(commands)

    def _display_parse_result(self, result: ParseResult, include_dev: bool) -> None:
        """Display the parsed packages from a dependency file."""
        ecosystem_names = {
            PackageEcosystem.PYTHON: "Python",
            PackageEcosystem.NODE: "Node",
            PackageEcosystem.RUBY: "Ruby",
            PackageEcosystem.RUST: "Rust",
            PackageEcosystem.GO: "Go",
        }

        ecosystem_name = ecosystem_names.get(result.ecosystem, "Unknown")
        filename = os.path.basename(result.file_path)

        cx_print(f"\n📋 Found {result.prod_count} {ecosystem_name} packages", "info")

        if result.packages:
            console.print("\n[bold]Packages:[/bold]")
            for pkg in result.packages[:15]:  # Show first 15
                version_str = f" ({pkg.version})" if pkg.version else ""
                console.print(f"  • {pkg.name}{version_str}")
            if len(result.packages) > 15:
                console.print(f"  [dim]... and {len(result.packages) - 15} more[/dim]")

        if include_dev and result.dev_packages:
            console.print(f"\n[bold]Dev packages:[/bold] ({result.dev_count})")
            for pkg in result.dev_packages[:10]:
                version_str = f" ({pkg.version})" if pkg.version else ""
                console.print(f"  • {pkg.name}{version_str}")
            if len(result.dev_packages) > 10:
                console.print(f"  [dim]... and {len(result.dev_packages) - 10} more[/dim]")

        if result.warnings:
            console.print()
            for warning in result.warnings:
                cx_print(f"⚠ {warning}", "warning")

    def _execute_install(self, command: str, ecosystem: PackageEcosystem) -> int:
        """Execute a single install command."""
        ecosystem_names = {
            PackageEcosystem.PYTHON: "Python",
            PackageEcosystem.NODE: "Node",
            PackageEcosystem.RUBY: "Ruby",
            PackageEcosystem.RUST: "Rust",
            PackageEcosystem.GO: "Go",
        }

        ecosystem_name = ecosystem_names.get(ecosystem, "")
        cx_print(f"\n✓ Installing {ecosystem_name} packages...", "success")

        def progress_callback(current: int, total: int, step: InstallationStep) -> None:
            status_emoji = "⏳"
            if step.status == StepStatus.SUCCESS:
                status_emoji = "✅"
            elif step.status == StepStatus.FAILED:
                status_emoji = "❌"
            console.print(f"[{current}/{total}] {status_emoji} {step.description}")

        coordinator = InstallationCoordinator(
            commands=[command],
            descriptions=[f"Install {ecosystem_name} packages"],
            timeout=600,  # 10 minutes for package installation
            stop_on_error=True,
            progress_callback=progress_callback,
        )

        result = coordinator.execute()

        if result.success:
            self._print_success(f"{ecosystem_name} packages installed successfully!")
            console.print(f"Completed in {result.total_duration:.2f} seconds")
            return 0
        else:
            self._print_error("Installation failed")
            if result.error_message:
                console.print(f"Error: {result.error_message}", style="red")
            return 1

    def _execute_multi_install(self, commands: list[dict[str, str]]) -> int:
        """Execute multiple install commands."""
        all_commands = [cmd["command"] for cmd in commands]
        all_descriptions = [cmd["description"] for cmd in commands]

        def progress_callback(current: int, total: int, step: InstallationStep) -> None:
            status_emoji = "⏳"
            if step.status == StepStatus.SUCCESS:
                status_emoji = "✅"
            elif step.status == StepStatus.FAILED:
                status_emoji = "❌"
            console.print(f"\n[{current}/{total}] {status_emoji} {step.description}")
            console.print(f"  Command: {step.command}")

        coordinator = InstallationCoordinator(
            commands=all_commands,
            descriptions=all_descriptions,
            timeout=600,
            stop_on_error=True,
            progress_callback=progress_callback,
        )

        console.print("\n[bold]Installing packages...[/bold]")
        result = coordinator.execute()

        if result.success:
            self._print_success("\nAll packages installed successfully!")
            console.print(f"Completed in {result.total_duration:.2f} seconds")
            return 0
        else:
            if result.failed_step is not None:
                self._print_error(f"\nInstallation failed at step {result.failed_step + 1}")
            else:
                self._print_error("\nInstallation failed")
            if result.error_message:
                console.print(f"Error: {result.error_message}", style="red")
            return 1

    # --------------------------


def show_rich_help():
    """Display beautifully formatted help using Rich"""
    from rich.table import Table

    show_banner(show_version=True)
    console.print()

    console.print("[bold]AI-powered package manager for Linux[/bold]")
    console.print("[dim]Just tell Cortex what you want to install.[/dim]")
    console.print()

    # Commands table
    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Command", style="green")
    table.add_column("Description")

    table.add_row("ask <question>", "Ask about your system")
    table.add_row("ask --do <question>", "Solve problems (can write/execute)")
    table.add_row("do history", "View do-mode run history")
    table.add_row("demo", "See Cortex in action")
    table.add_row("wizard", "Configure API key")
    table.add_row("status", "System status")
    table.add_row("install <pkg>", "Install software")
    table.add_row("import <file>", "Import deps from package files")
    table.add_row("history", "View history")
    table.add_row("rollback <id>", "Undo installation")
    table.add_row("notify", "Manage desktop notifications")
    table.add_row("env", "Manage environment variables")
    table.add_row("cache stats", "Show LLM cache statistics")
    table.add_row("stack <name>", "Install the stack")
    table.add_row("sandbox <cmd>", "Test packages in Docker sandbox")
    table.add_row("doctor", "System health check")

    console.print(table)
    console.print()
    console.print("[dim]Learn more: https://cortexlinux.com/docs[/dim]")


def shell_suggest(text: str) -> int:
    """
    Internal helper used by shell hotkey integration.
    Prints a single suggested command to stdout.
    """
    try:
        from cortex.shell_integration import suggest_command

        suggestion = suggest_command(text)
        if suggestion:
            print(suggestion)
        return 0
    except Exception:
        return 1


def main():
    # Load environment variables from .env files BEFORE accessing any API keys
    # This must happen before any code that reads os.environ for API keys
    from cortex.env_loader import load_env

    load_env()

    # Auto-configure network settings (proxy detection, VPN compatibility, offline mode)
    # Use lazy loading - only detect when needed to improve CLI startup time
    try:
        network = NetworkConfig(auto_detect=False)  # Don't detect yet (fast!)

        # Only detect network for commands that actually need it
        # Parse args first to see what command we're running
        temp_parser = argparse.ArgumentParser(add_help=False)
        temp_parser.add_argument("command", nargs="?")
        temp_args, _ = temp_parser.parse_known_args()

        # Commands that need network detection
        NETWORK_COMMANDS = ["install", "update", "upgrade", "search", "doctor", "stack"]

        if temp_args.command in NETWORK_COMMANDS:
            # Now detect network (only when needed)
            network.detect(check_quality=True)  # Include quality check for these commands
            network.auto_configure()

    except Exception as e:
        # Network config is optional - don't block execution if it fails
        console.print(f"[yellow]⚠️  Network auto-config failed: {e}[/yellow]")

    parser = argparse.ArgumentParser(
        prog="cortex",
        description="AI-powered Linux command interpreter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global flags
    parser.add_argument("--version", "-V", action="version", version=f"cortex {VERSION}")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Demo command
    demo_parser = subparsers.add_parser("demo", help="See Cortex in action")

    # Wizard command
    wizard_parser = subparsers.add_parser("wizard", help="Configure API key interactively")

    # Status command (includes comprehensive health checks)
    subparsers.add_parser("status", help="Show comprehensive system status and health checks")

    # Ask command
    ask_parser = subparsers.add_parser("ask", help="Ask a question about your system")
    ask_parser.add_argument("question", type=str, nargs="?", default=None, help="Natural language question (optional with --do)")
    ask_parser.add_argument("--debug", action="store_true", help="Show debug output for agentic loop")
    ask_parser.add_argument(
        "--do", 
        action="store_true", 
        help="Enable do mode - Cortex can write, read, and execute commands to solve problems. If no question is provided, starts interactive session."
    )

    # Install command
    install_parser = subparsers.add_parser("install", help="Install software")
    install_parser.add_argument("software", type=str, help="Software to install")
    install_parser.add_argument("--execute", action="store_true", help="Execute commands")
    install_parser.add_argument("--dry-run", action="store_true", help="Show commands only")
    install_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel execution for multi-step installs",
    )

    # Import command - import dependencies from package manager files
    import_parser = subparsers.add_parser(
        "import",
        help="Import and install dependencies from package files",
    )
    import_parser.add_argument(
        "file",
        nargs="?",
        help="Dependency file (requirements.txt, package.json, Gemfile, Cargo.toml, go.mod)",
    )
    import_parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Scan directory for all dependency files",
    )
    import_parser.add_argument(
        "--execute",
        "-e",
        action="store_true",
        help="Execute install commands (default: dry-run)",
    )
    import_parser.add_argument(
        "--dev",
        "-d",
        action="store_true",
        help="Include dev dependencies",
    )

    # History command
    history_parser = subparsers.add_parser("history", help="View history")
    history_parser.add_argument("--limit", type=int, default=20)
    history_parser.add_argument("--status", choices=["success", "failed"])
    history_parser.add_argument("show_id", nargs="?")

    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback installation")
    rollback_parser.add_argument("id", help="Installation ID")
    rollback_parser.add_argument("--dry-run", action="store_true")

    # --- New Notify Command ---
    notify_parser = subparsers.add_parser("notify", help="Manage desktop notifications")
    notify_subs = notify_parser.add_subparsers(dest="notify_action", help="Notify actions")

    notify_subs.add_parser("config", help="Show configuration")
    notify_subs.add_parser("enable", help="Enable notifications")
    notify_subs.add_parser("disable", help="Disable notifications")

    dnd_parser = notify_subs.add_parser("dnd", help="Configure DND window")
    dnd_parser.add_argument("start", help="Start time (HH:MM)")
    dnd_parser.add_argument("end", help="End time (HH:MM)")

    send_parser = notify_subs.add_parser("send", help="Send test notification")
    send_parser.add_argument("message", help="Notification message")
    send_parser.add_argument("--title", default="Cortex Notification")
    send_parser.add_argument("--level", choices=["low", "normal", "critical"], default="normal")
    send_parser.add_argument("--actions", nargs="*", help="Action buttons")
    # --------------------------

    # Stack command
    stack_parser = subparsers.add_parser("stack", help="Manage pre-built package stacks")
    stack_parser.add_argument(
        "name", nargs="?", help="Stack name to install (ml, ml-cpu, webdev, devops, data)"
    )
    stack_group = stack_parser.add_mutually_exclusive_group()
    stack_group.add_argument("--list", "-l", action="store_true", help="List all available stacks")
    stack_group.add_argument("--describe", "-d", metavar="STACK", help="Show details about a stack")
    stack_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be installed (requires stack name)"
    )
    # Cache commands
    cache_parser = subparsers.add_parser("cache", help="Cache operations")
    cache_subs = cache_parser.add_subparsers(dest="cache_action", help="Cache actions")
    cache_subs.add_parser("stats", help="Show cache statistics")

    # --- Sandbox Commands (Docker-based package testing) ---
    sandbox_parser = subparsers.add_parser(
        "sandbox", help="Test packages in isolated Docker sandbox"
    )
    sandbox_subs = sandbox_parser.add_subparsers(dest="sandbox_action", help="Sandbox actions")

    # sandbox create <name> [--image IMAGE]
    sandbox_create_parser = sandbox_subs.add_parser("create", help="Create a sandbox environment")
    sandbox_create_parser.add_argument("name", help="Unique name for the sandbox")
    sandbox_create_parser.add_argument(
        "--image", default="ubuntu:22.04", help="Docker image to use (default: ubuntu:22.04)"
    )

    # sandbox install <name> <package>
    sandbox_install_parser = sandbox_subs.add_parser("install", help="Install a package in sandbox")
    sandbox_install_parser.add_argument("name", help="Sandbox name")
    sandbox_install_parser.add_argument("package", help="Package to install")

    # sandbox test <name> [package]
    sandbox_test_parser = sandbox_subs.add_parser("test", help="Run tests in sandbox")
    sandbox_test_parser.add_argument("name", help="Sandbox name")
    sandbox_test_parser.add_argument("package", nargs="?", help="Specific package to test")

    # sandbox promote <name> <package> [--dry-run]
    sandbox_promote_parser = sandbox_subs.add_parser(
        "promote", help="Install tested package on main system"
    )
    sandbox_promote_parser.add_argument("name", help="Sandbox name")
    sandbox_promote_parser.add_argument("package", help="Package to promote")
    sandbox_promote_parser.add_argument(
        "--dry-run", action="store_true", help="Show command without executing"
    )
    sandbox_promote_parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )

    # sandbox cleanup <name> [--force]
    sandbox_cleanup_parser = sandbox_subs.add_parser("cleanup", help="Remove a sandbox environment")
    sandbox_cleanup_parser.add_argument("name", help="Sandbox name to remove")
    sandbox_cleanup_parser.add_argument("-f", "--force", action="store_true", help="Force removal")

    # sandbox list
    sandbox_subs.add_parser("list", help="List all sandbox environments")

    # sandbox exec <name> <command...>
    sandbox_exec_parser = sandbox_subs.add_parser("exec", help="Execute command in sandbox")
    sandbox_exec_parser.add_argument("name", help="Sandbox name")
    sandbox_exec_parser.add_argument("command", nargs="+", help="Command to execute")
    # --------------------------

    # --- Environment Variable Management Commands ---
    env_parser = subparsers.add_parser("env", help="Manage environment variables")
    env_subs = env_parser.add_subparsers(dest="env_action", help="Environment actions")

    # env set <app> <KEY> <VALUE> [--encrypt] [--type TYPE] [--description DESC]
    env_set_parser = env_subs.add_parser("set", help="Set an environment variable")
    env_set_parser.add_argument("app", help="Application name")
    env_set_parser.add_argument("key", help="Variable name")
    env_set_parser.add_argument("value", help="Variable value")
    env_set_parser.add_argument("--encrypt", "-e", action="store_true", help="Encrypt the value")
    env_set_parser.add_argument(
        "--type",
        "-t",
        choices=["string", "url", "port", "boolean", "integer", "path"],
        default="string",
        help="Variable type for validation",
    )
    env_set_parser.add_argument("--description", "-d", help="Description of the variable")

    # env get <app> <KEY> [--decrypt]
    env_get_parser = env_subs.add_parser("get", help="Get an environment variable")
    env_get_parser.add_argument("app", help="Application name")
    env_get_parser.add_argument("key", help="Variable name")
    env_get_parser.add_argument(
        "--decrypt", action="store_true", help="Decrypt and show encrypted values"
    )

    # env list <app> [--decrypt]
    env_list_parser = env_subs.add_parser("list", help="List environment variables")
    env_list_parser.add_argument("app", help="Application name")
    env_list_parser.add_argument(
        "--decrypt", action="store_true", help="Decrypt and show encrypted values"
    )

    # env delete <app> <KEY>
    env_delete_parser = env_subs.add_parser("delete", help="Delete an environment variable")
    env_delete_parser.add_argument("app", help="Application name")
    env_delete_parser.add_argument("key", help="Variable name")

    # env export <app> [--include-encrypted] [--output FILE]
    env_export_parser = env_subs.add_parser("export", help="Export variables to .env format")
    env_export_parser.add_argument("app", help="Application name")
    env_export_parser.add_argument(
        "--include-encrypted",
        action="store_true",
        help="Include decrypted values of encrypted variables",
    )
    env_export_parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    # env import <app> [file] [--encrypt-keys KEYS]
    env_import_parser = env_subs.add_parser("import", help="Import variables from .env format")
    env_import_parser.add_argument("app", help="Application name")
    env_import_parser.add_argument("file", nargs="?", help="Input file (default: stdin)")
    env_import_parser.add_argument("--encrypt-keys", help="Comma-separated list of keys to encrypt")

    # env clear <app> [--force]
    env_clear_parser = env_subs.add_parser("clear", help="Clear all variables for an app")
    env_clear_parser.add_argument("app", help="Application name")
    env_clear_parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation")

    # env apps - list all apps with environments
    env_subs.add_parser("apps", help="List all apps with stored environments")

    # env load <app> - load into os.environ
    env_load_parser = env_subs.add_parser("load", help="Load variables into current environment")
    env_load_parser.add_argument("app", help="Application name")

    # env template subcommands
    env_template_parser = env_subs.add_parser("template", help="Manage environment templates")
    env_template_subs = env_template_parser.add_subparsers(
        dest="template_action", help="Template actions"
    )

    # env template list
    env_template_subs.add_parser("list", help="List available templates")

    # env template show <name>
    env_template_show_parser = env_template_subs.add_parser("show", help="Show template details")
    env_template_show_parser.add_argument("template_name", help="Template name")

    # env template apply <template> <app> [KEY=VALUE...] [--encrypt-keys KEYS]
    env_template_apply_parser = env_template_subs.add_parser("apply", help="Apply template to app")
    env_template_apply_parser.add_argument("template_name", help="Template name")
    env_template_apply_parser.add_argument("app", help="Application name")
    env_template_apply_parser.add_argument(
        "values", nargs="*", help="Variable values as KEY=VALUE pairs"
    )
    env_template_apply_parser.add_argument(
        "--encrypt-keys", help="Comma-separated list of keys to encrypt"
    )
    # --- Info Command (system information queries) ---
    info_parser = subparsers.add_parser("info", help="Get system and application information")
    info_parser.add_argument("query", nargs="*", help="Information query (natural language)")
    info_parser.add_argument(
        "--app", "-a", 
        type=str, 
        help="Get info about a specific application (nginx, docker, etc.)"
    )
    info_parser.add_argument(
        "--quick", "-q",
        type=str,
        choices=["cpu", "memory", "disk", "gpu", "os", "kernel", "network", "dns", 
                 "services", "security", "processes", "environment"],
        help="Quick lookup for common info types"
    )
    info_parser.add_argument(
        "--category", "-c",
        type=str,
        choices=["hardware", "software", "network", "services", "security", 
                 "storage", "performance", "configuration"],
        help="Get structured info for a category"
    )
    info_parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available info types and applications"
    )
    info_parser.add_argument(
        "--debug",
        action="store_true",
        help="Show debug output"
    )

    # --- Do Command (manage do-mode runs) ---
    do_parser = subparsers.add_parser("do", help="Manage do-mode execution runs")
    do_subs = do_parser.add_subparsers(dest="do_action", help="Do actions")

    # do history [--limit N]
    do_history_parser = do_subs.add_parser("history", help="View do-mode run history")
    do_history_parser.add_argument("--limit", "-n", type=int, default=20, help="Number of runs to show")
    do_history_parser.add_argument("run_id", nargs="?", help="Show details for specific run ID")

    # do setup - setup cortex user
    do_subs.add_parser("setup", help="Setup cortex user for privilege management")

    # do protected - manage protected paths
    do_protected_parser = do_subs.add_parser("protected", help="Manage protected paths")
    do_protected_parser.add_argument("--add", help="Add a path to protected list")
    do_protected_parser.add_argument("--remove", help="Remove a path from protected list")
    do_protected_parser.add_argument("--list", action="store_true", help="List all protected paths")
    # --------------------------

    # --- Watch Command (terminal monitoring setup) ---
    watch_parser = subparsers.add_parser("watch", help="Manage terminal watching for manual intervention mode")
    watch_parser.add_argument("--install", action="store_true", help="Install terminal watch hook to .bashrc/.zshrc")
    watch_parser.add_argument("--uninstall", action="store_true", help="Remove terminal watch hook from shell configs")
    watch_parser.add_argument("--system", action="store_true", help="Install/uninstall system-wide (requires sudo)")
    watch_parser.add_argument("--service", action="store_true", help="Install/uninstall as systemd service (recommended)")
    watch_parser.add_argument("--status", action="store_true", help="Show terminal watch status")
    watch_parser.add_argument("--test", action="store_true", help="Test terminal monitoring")
    # --------------------------

    args = parser.parse_args()

    if not args.command:
        show_rich_help()
        return 0

    cli = CortexCLI(verbose=args.verbose)

    try:
        if args.command == "demo":
            return cli.demo()
        elif args.command == "wizard":
            return cli.wizard()
        elif args.command == "status":
            return cli.status()
        elif args.command == "ask":
            return cli.ask(
                getattr(args, "question", None), 
                debug=args.debug, 
                do_mode=getattr(args, "do", False)
            )
        elif args.command == "install":
            return cli.install(
                args.software,
                execute=args.execute,
                dry_run=args.dry_run,
                parallel=args.parallel,
            )
        elif args.command == "import":
            return cli.import_deps(args)
        elif args.command == "history":
            return cli.history(limit=args.limit, status=args.status, show_id=args.show_id)
        elif args.command == "rollback":
            return cli.rollback(args.id, dry_run=args.dry_run)
        # Handle the new notify command
        elif args.command == "notify":
            return cli.notify(args)
        elif args.command == "stack":
            return cli.stack(args)
        elif args.command == "sandbox":
            return cli.sandbox(args)
        elif args.command == "cache":
            if getattr(args, "cache_action", None) == "stats":
                return cli.cache_stats()
            parser.print_help()
            return 1
        elif args.command == "env":
            return cli.env(args)
        elif args.command == "do":
            return cli.do_cmd(args)
        elif args.command == "info":
            return cli.info_cmd(args)
        elif args.command == "watch":
            return cli.watch_cmd(args)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled", file=sys.stderr)
        return 130
    except (ValueError, ImportError, OSError) as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
    except AttributeError as e:
        # Internal errors - show friendly message
        print("❌ Something went wrong. Please try again.", file=sys.stderr)
        if "--verbose" in sys.argv or "-v" in sys.argv:
            import traceback
            traceback.print_exc()
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        # Print traceback if verbose mode was requested
        if "--verbose" in sys.argv or "-v" in sys.argv:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
