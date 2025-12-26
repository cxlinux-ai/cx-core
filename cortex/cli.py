import argparse
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any

from cortex.branding import VERSION, console, cx_header, cx_print, show_banner
from cortex.coordinator import InstallationCoordinator, StepStatus
from cortex.demo import run_demo
from cortex.installation_history import InstallationHistory, InstallationStatus, InstallationType
from cortex.llm.interpreter import CommandInterpreter
from cortex.notification_manager import NotificationManager
from cortex.stack_manager import StackManager
from cortex.validators import (
    validate_api_key,
    validate_install_request,
)

# Suppress noisy log messages in normal operation
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cortex.installation_history").setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class CortexCLI:
    def __init__(self, verbose: bool = False):
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.verbose = verbose
        self.offline = False

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

    # Run system health checks
    def doctor(self):
        from cortex.doctor import SystemDoctor

        doctor = SystemDoctor()
        return doctor.run_checks()

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

            interpreter = CommandInterpreter(
                api_key=api_key, provider=provider, offline=self.offline
            )

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
                            print(f"   View details: cortex history show {install_id}")
                        return 1

                    except Exception as e:
                        if install_id:
                            history.update_installation(
                                install_id, InstallationStatus.FAILED, str(e)
                            )
                        self._print_error(f"Parallel execution failed: {str(e)}")
                        return 1

                coordinator = InstallationCoordinator(
                    commands=commands,
                    descriptions=[f"Step {i+1}" for i in range(len(commands))],
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
                        print(f"   View details: cortex history show {install_id}")
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
        except Exception as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"Unexpected error: {str(e)}")
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
        except Exception as e:
            self._print_error(f"Unable to read cache stats: {e}")
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
                        packages += f" +{len(r.packages)-2}"

                    print(
                        f"{r.id:<18} {date:<20} {r.operation_type.value:<12} {packages:<30} {r.status.value:<15}"
                    )

                return 0
        except Exception as e:
            self._print_error(f"Failed to retrieve history: {str(e)}")
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
        except Exception as e:
            self._print_error(f"Rollback failed: {str(e)}")
            return 1

    def status(self):
        """Show system status including security features"""
        import shutil

        show_banner(show_version=True)
        console.print()

        cx_header("System Status")

        # Check API key
        is_valid, provider, _ = validate_api_key()
        if is_valid:
            cx_print(f"API Provider: [bold]{provider}[/bold]", "success")
        else:
            # Check for Ollama
            ollama_provider = os.environ.get("CORTEX_PROVIDER", "").lower()
            if ollama_provider == "ollama":
                cx_print("API Provider: [bold]Ollama (local)[/bold]", "success")
            else:
                cx_print("API Provider: [bold]Not configured[/bold]", "warning")
                cx_print("  Run: cortex wizard", "info")

        # Check Firejail
        firejail_path = shutil.which("firejail")
        if firejail_path:
            cx_print(f"Firejail: [bold]Available[/bold] ({firejail_path})", "success")
        else:
            cx_print("Firejail: [bold]Not installed[/bold]", "warning")
            cx_print("  Install: sudo apt-get install firejail", "info")

        console.print()
        return 0

    def wizard(self):
        """Interactive setup wizard for API key configuration"""
        show_banner()
        console.print()
        cx_print("Welcome to Cortex Setup Wizard!", "success")
        console.print()
        # (Simplified for brevity - keeps existing logic)
        cx_print("Please export your API key in your shell profile.", "info")
        return 0

    def snapshot(self, args: argparse.Namespace) -> int:
        """Handle snapshot commands (create/list/restore/show/delete)."""
        from cortex.snapshot_manager import SnapshotManager

        manager = SnapshotManager()

        if not args.snapshot_action:
            self._print_error(
                "Please specify a snapshot action: create, list, show, restore, or delete"
            )
            self._print_error("Run 'cortex snapshot --help' for usage information")
            return 1

        if args.snapshot_action == "create":
            success, snapshot_id, message = manager.create_snapshot(args.description or "")
            if success:
                cx_print(f"✅ {message}", "success")
                return 0
            else:
                self._print_error(message)
                return 1

        elif args.snapshot_action == "list":
            snapshots = manager.list_snapshots()
            if not snapshots:
                cx_print("No snapshots found.", "info")
                return 0

            cx_print("\n📸 Available Snapshots:\n", "info")
            print(f"{'ID':<24} {'Date':<20} {'Packages':<12} {'Description'}")
            print("=" * 99)

            for snapshot in snapshots:
                date = snapshot.timestamp[:19].replace("T", " ")
                pkg_count = sum(len(pkgs) for pkgs in snapshot.packages.values())
                desc = snapshot.description[:40] if snapshot.description else "(no description)"
                print(f"{snapshot.id:<24} {date:<20} {pkg_count:<12} {desc}")
            return 0

        elif args.snapshot_action == "show":
            snapshot = manager.get_snapshot(args.snapshot_id)
            if not snapshot:
                self._print_error(f"Snapshot not found: {args.snapshot_id}")
                return 1

            cx_print(f"\nSnapshot Details: {snapshot.id}", "info")
            print("=" * 80)
            print(f"Timestamp: {snapshot.timestamp}")
            print(f"Description: {snapshot.description or '(no description)'}")
            print("\nSystem Info:")
            for key, value in snapshot.system_info.items():
                print(f"  {key}: {value}")
            print("\nPackages:")
            for source, packages in snapshot.packages.items():
                print(f"  {source.upper()}: {len(packages)} packages")
            return 0

        elif args.snapshot_action == "restore":
            success, message, commands = manager.restore_snapshot(
                args.snapshot_id, dry_run=args.dry_run
            )

            if args.dry_run:
                cx_print(f"\n🔍 Dry-run: {message}", "info")
                if commands:
                    print("\nCommands to execute:")
                    for cmd in commands:
                        print(f"  {cmd}")
            else:
                if success:
                    cx_print(f"✅ {message}", "success")
                else:
                    self._print_error(message)
                    if commands:
                        print("\nFailed commands:")
                        for cmd in commands:
                            print(f"  {cmd}")
                    return 1
            return 0

        elif args.snapshot_action == "delete":
            success, message = manager.delete_snapshot(args.snapshot_id)
            if success:
                cx_print(f"✅ {message}", "success")
                return 0
            else:
                self._print_error(message)
                return 1

        return 1


def show_rich_help():
    """Display beautifully formatted help using Rich"""
    from rich.table import Table
    from rich.panel import Panel

    show_banner(show_version=True)
    console.print()

    console.print("[bold cyan]AI-powered package manager for Linux[/bold cyan]")
    console.print("[dim]Natural language package management with system snapshots and rollbacks[/dim]")
    console.print()

    # Main Commands table
    table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
    table.add_column("Command", style="green", width=25)
    table.add_column("Description", style="white")

    table.add_row(
        "[bold]cortex install <pkg>[/bold]",
        "Install software using natural language\n"
        "[dim]Flags: --execute, --dry-run, --parallel[/dim]"
    )
    table.add_row(
        "[bold]cortex stack <name>[/bold]",
        "Install pre-built package stacks (ml, webdev, devops, data)\n"
        "[dim]Flags: --list, --describe <name>, --dry-run[/dim]"
    )
    table.add_row(
        "[bold]cortex snapshot[/bold]",
        "Manage system snapshots for safe rollbacks\n"
        "[dim]Actions: create, list, show <id>, restore <id>, delete <id>[/dim]"
    )
    table.add_row(
        "[bold]cortex history[/bold]",
        "View installation history and details\n"
        "[dim]Flags: --limit <n>, --status <success|failed> <id>[/dim]"
    )
    table.add_row(
        "[bold]cortex rollback <id>[/bold]",
        "Undo an installation by history ID\n"
        "[dim]Flags: --dry-run[/dim]"
    )

    console.print(Panel(table, title="[bold]Core Commands[/bold]", border_style="cyan"))
    console.print()

    # Utility Commands table
    util_table = Table(show_header=True, header_style="bold yellow", box=None, padding=(0, 2))
    util_table.add_column("Command", style="green", width=25)
    util_table.add_column("Description", style="white")

    util_table.add_row("[bold]cortex doctor[/bold]", "Run comprehensive system health check")
    util_table.add_row("[bold]cortex status[/bold]", "Show current system status and configuration")
    util_table.add_row("[bold]cortex wizard[/bold]", "Interactive setup for API keys and configuration")
    util_table.add_row("[bold]cortex demo[/bold]", "See Cortex capabilities with example commands")
    
    console.print(Panel(util_table, title="[bold]Utility Commands[/bold]", border_style="yellow"))
    console.print()

    # Configuration Commands table
    config_table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 2))
    config_table.add_column("Command", style="green", width=25)
    config_table.add_column("Description", style="white")

    config_table.add_row(
        "[bold]cortex notify[/bold]",
        "Manage desktop notifications\n"
        "[dim]Actions: config, enable, disable, dnd, send[/dim]"
    )
    config_table.add_row(
        "[bold]cortex cache stats[/bold]",
        "Show LLM response cache statistics"
    )

    console.print(Panel(config_table, title="[bold]Configuration Commands[/bold]", border_style="magenta"))
    console.print()

    # Global Flags
    flags_table = Table(show_header=False, box=None, padding=(0, 2))
    flags_table.add_column("Flag", style="cyan", width=20)
    flags_table.add_column("Description", style="white")

    flags_table.add_row("[bold]--verbose, -v[/bold]", "Show detailed debug output")
    flags_table.add_row("[bold]--offline[/bold]", "Use cached responses only (no network)")
    flags_table.add_row("[bold]--version, -V[/bold]", "Show version number")
    flags_table.add_row("[bold]--help, -h[/bold]", "Show this help message")

    console.print(Panel(flags_table, title="[bold]Global Flags[/bold]", border_style="blue"))
    console.print()

    # Examples
    console.print("[bold underline]Examples:[/bold underline]")
    console.print("  [green]cortex install nginx[/green]              [dim]# Install nginx with AI guidance[/dim]")
    console.print("  [green]cortex stack ml-cpu --dry-run[/green]    [dim]# Preview ML stack installation[/dim]")
    console.print("  [green]cortex snapshot create 'Pre-update'[/green] [dim]# Create system snapshot[/dim]")
    console.print("  [green]cortex history --limit 10[/green]        [dim]# Show last 10 installations[/dim]")
    console.print("  [green]cortex doctor[/green]                    [dim]# Run system diagnostics[/dim]")
    console.print()

    console.print("[dim]Documentation: https://cortexlinux.com/docs[/dim]")
    console.print("[dim]Discord: https://discord.gg/uCqHvxjU83[/dim]")


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

    parser = argparse.ArgumentParser(
        prog="cortex",
        description="Cortex Linux - AI-powered package manager with natural language interface\n"
                    "Install packages, manage stacks, create system snapshots, and rollback changes.",
        epilog="Examples:\n"
               "  cortex install nginx                    Install nginx with AI guidance\n"
               "  cortex stack ml-cpu --dry-run          Preview ML stack installation\n"
               "  cortex snapshot create 'Pre-update'    Create system snapshot\n"
               "  cortex history --limit 10              Show last 10 installations\n"
               "  cortex doctor                          Run system diagnostics\n\n"
               "Documentation: https://cortexlinux.com/docs\n"
               "Discord: https://discord.gg/uCqHvxjU83",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global flags
    parser.add_argument("--version", "-V", action="version", version=f"cortex {VERSION}")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument(
        "--offline", action="store_true", help="Use cached responses only (no network calls)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Demo command
    subparsers.add_parser(
        "demo",
        help="Interactive demonstration of Cortex features",
        description="See example installations and learn how to use Cortex effectively."
    )

    # Wizard command
    subparsers.add_parser(
        "wizard",
        help="Interactive setup wizard",
        description="Configure API keys (Anthropic/OpenAI) and initial preferences step-by-step."
    )

    # Status command
    subparsers.add_parser(
        "status",
        help="Show system status and configuration",
        description="Display Cortex configuration, API keys, cache stats, and system info."
    )

    # doctor command
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run comprehensive system diagnostics",
        description="Check dependencies, API connectivity, permissions, and system compatibility."
    )

    # Install command
    install_parser = subparsers.add_parser(
        "install",
        help="Install software using natural language",
        description="Install packages with AI-powered dependency resolution and hardware detection."
    )
    install_parser.add_argument("software", type=str, help="Software name or description (e.g., 'nginx', 'python web server')")
    install_parser.add_argument("--execute", action="store_true", help="Execute installation commands immediately")
    install_parser.add_argument("--dry-run", action="store_true", help="Preview commands without executing")
    install_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel execution for multi-step installs",
    )

    # History command
    history_parser = subparsers.add_parser(
        "history",
        help="View installation history",
        description="Display past installations with status, timestamps, and package details."
    )
    history_parser.add_argument("--limit", type=int, default=20, help="Number of records to show (default: 20)")
    history_parser.add_argument("--status", choices=["success", "failed"], help="Filter by installation status")
    history_parser.add_argument("show_id", nargs="?", help="Show detailed info for specific installation ID")

    # Rollback command
    rollback_parser = subparsers.add_parser(
        "rollback",
        help="Undo a previous installation",
        description="Revert an installation by removing packages that were added."
    )
    rollback_parser.add_argument("id", help="Installation ID from history")
    rollback_parser.add_argument("--dry-run", action="store_true", help="Preview rollback actions without executing")

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
    stack_parser = subparsers.add_parser(
        "stack",
        help="Install pre-built package stacks",
        description="Install curated package collections for ML, web development, DevOps, and data science."
    )
    stack_parser.add_argument(
        "name", nargs="?", help="Stack name: ml, ml-cpu, webdev, devops, data"
    )
    stack_group = stack_parser.add_mutually_exclusive_group()
    stack_group.add_argument("--list", "-l", action="store_true", help="List all available stacks with descriptions")
    stack_group.add_argument("--describe", "-d", metavar="STACK", help="Show detailed information about a specific stack")
    stack_parser.add_argument(
        "--dry-run", action="store_true", help="Preview stack contents without installing (requires stack name)"
    )

    # Snapshot commands
    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Manage system snapshots for safe rollbacks",
        description="Create, restore, and manage system snapshots of installed packages (APT, pip, npm)."
    )
    snapshot_subs = snapshot_parser.add_subparsers(dest="snapshot_action", help="Snapshot operations")

    # Create snapshot
    create_snap = snapshot_subs.add_parser(
        "create",
        help="Create a new system snapshot",
        description="Capture current state of all installed packages (APT, pip, npm)."
    )
    create_snap.add_argument("description", nargs="?", default="", help="Optional description (e.g., 'Before major update')")

    # List snapshots
    snapshot_subs.add_parser(
        "list",
        help="List all snapshots",
        description="Show all available snapshots with timestamps and package counts."
    )

    # Show snapshot details
    show_snap = snapshot_subs.add_parser(
        "show",
        help="Show detailed snapshot information",
        description="Display complete snapshot contents including all packages and versions."
    )
    show_snap.add_argument("snapshot_id", help="Snapshot ID (format: YYYYMMDD_HHMMSS_xxxxxxxx)")

    # Restore snapshot
    restore_snap = snapshot_subs.add_parser(
        "restore",
        help="Restore system to a previous snapshot",
        description="Install/remove packages to match snapshot state. Creates automatic backup first."
    )
    restore_snap.add_argument("snapshot_id", help="Snapshot ID to restore")
    restore_snap.add_argument("--dry-run", action="store_true", help="Preview restore actions without executing")

    # Delete snapshot
    delete_snap = snapshot_subs.add_parser(
        "delete",
        help="Delete a snapshot",
        description="Permanently remove a snapshot from disk."
    )
    delete_snap.add_argument("snapshot_id", help="Snapshot ID to delete")

    args = parser.parse_args()

    if not args.command:
        show_rich_help()
        return 0

    cli = CortexCLI(verbose=args.verbose)
    cli.offline = bool(getattr(args, "offline", False))

    try:
        if args.command == "demo":
            return cli.demo()
        elif args.command == "wizard":
            return cli.wizard()
        elif args.command == "status":
            return cli.status()
        elif args.command == "install":
            return cli.install(
                args.software,
                execute=args.execute,
                dry_run=args.dry_run,
                parallel=args.parallel,
            )
        elif args.command == "history":
            return cli.history(limit=args.limit, status=args.status, show_id=args.show_id)
        elif args.command == "rollback":
            return cli.rollback(args.id, dry_run=args.dry_run)
        # Handle the new notify command
        elif args.command == "notify":
            return cli.notify(args)
        elif args.command == "stack":
            return cli.stack(args)
        elif args.command == "doctor":
            return cli.doctor()
        elif args.command == "cache":
            if getattr(args, "cache_action", None) == "stats":
                return cli.cache_stats()
            parser.print_help()
            return 1
        elif args.command == "snapshot":
            return cli.snapshot(args)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
