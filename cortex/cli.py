import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cortex.api_key_detector import auto_detect_api_key, setup_api_key
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

if TYPE_CHECKING:
    from cortex.shell_env_analyzer import ShellEnvironmentAnalyzer

# Suppress noisy log messages in normal operation
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cortex.installation_history").setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class CortexCLI:
    def __init__(self, verbose: bool = False):
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.verbose = verbose

    # Define a method to handle Docker-specific permission repairs
    def docker_permissions(self, args: argparse.Namespace) -> int:
        """Handle the diagnosis and repair of Docker file permissions.

        This method coordinates the environment-aware scanning of the project
        directory and applies ownership reclamation logic. It ensures that
        administrative actions (sudo) are never performed without user
        acknowledgment unless the non-interactive flag is present.

        Args:
            args: The parsed command-line arguments containing the execution
                context and safety flags.

        Returns:
            int: 0 if successful or the operation was gracefully cancelled,
                1 if a system or logic error occurred.
        """
        from cortex.permission_manager import PermissionManager

        try:
            manager = PermissionManager(os.getcwd())
            cx_print("🔍 Scanning for Docker-related permission issues...", "info")

            # Validate Docker Compose configurations for missing user mappings
            # to help prevent future permission drift.
            manager.check_compose_config()

            # Retrieve execution context from argparse.
            execute_flag = getattr(args, "execute", False)
            yes_flag = getattr(args, "yes", False)

            # SAFETY GUARD: If executing repairs, prompt for confirmation unless
            # the --yes flag was provided. This follows the project safety
            # standard: 'No silent sudo execution'.
            if execute_flag and not yes_flag:
                mismatches = manager.diagnose()
                if mismatches:
                    cx_print(
                        f"⚠️ Found {len(mismatches)} paths requiring ownership reclamation.",
                        "warning",
                    )
                    try:
                        # Interactive confirmation prompt for administrative repair.
                        response = console.input(
                            "[bold cyan]Reclaim ownership using sudo? (y/n): [/bold cyan]"
                        )
                        if response.lower() not in ("y", "yes"):
                            cx_print("Operation cancelled", "info")
                            return 0
                    except (EOFError, KeyboardInterrupt):
                        # Graceful handling of terminal exit or manual interruption.
                        console.print()
                        cx_print("Operation cancelled", "info")
                        return 0

            # Delegate repair logic to PermissionManager. If execute is False,
            # a dry-run report is generated. If True, repairs are batched to
            # avoid system ARG_MAX shell limits.
            if manager.fix_permissions(execute=execute_flag):
                if execute_flag:
                    cx_print("✨ Permissions fixed successfully!", "success")
                return 0

            return 1

        except (PermissionError, FileNotFoundError, OSError) as e:
            # Handle system-level access issues or missing project files.
            cx_print(f"❌ Permission check failed: {e}", "error")
            return 1
        except NotImplementedError as e:
            # Report environment incompatibility (e.g., native Windows).
            cx_print(f"❌ {e}", "error")
            return 1
        except Exception as e:
            # Safety net for unexpected runtime exceptions to prevent CLI crashes.
            cx_print(f"❌ Unexpected error: {e}", "error")
            return 1

    def _debug(self, message: str):
        """Print debug info only in verbose mode"""
        if self.verbose:
            console.print(f"[dim][DEBUG] {message}[/dim]")

    def _get_api_key(self) -> str | None:
        # 1. Check explicit provider override first (fake/ollama need no key)
        explicit_provider = os.environ.get("CORTEX_PROVIDER", "").lower()
        if explicit_provider == "fake":
            self._debug("Using Fake provider for testing")
            return "fake-key"
        if explicit_provider == "ollama":
            self._debug("Using Ollama (no API key required)")
            return "ollama-local"

        # 2. Try auto-detection + prompt to save (setup_api_key handles both)
        success, key, detected_provider = setup_api_key()
        if success:
            self._debug(f"Using {detected_provider} API key")
            # Store detected provider so _get_provider can use it
            self._detected_provider = detected_provider
            return key

        # Still no key
        self._print_error("No API key found or provided")
        cx_print("Run [bold]cortex wizard[/bold] to configure your API key.", "info")
        cx_print("Or use [bold]CORTEX_PROVIDER=ollama[/bold] for offline mode.", "info")
        return None

    def _get_provider(self) -> str:
        # Check environment variable for explicit provider choice
        explicit_provider = os.environ.get("CORTEX_PROVIDER", "").lower()
        if explicit_provider in ["ollama", "openai", "claude", "fake"]:
            return explicit_provider

        # Use provider from auto-detection (set by _get_api_key)
        detected = getattr(self, "_detected_provider", None)
        if detected == "anthropic":
            return "claude"
        elif detected == "openai":
            return "openai"

        # Check env vars (may have been set by auto-detect)
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
        command = args.cmd

        result = sandbox.exec_command(name, command)

        if result.stdout:
            console.print(result.stdout, end="")
        if result.stderr:
            console.print(result.stderr, style="red", end="")

        return result.exit_code

    # --- End Sandbox Commands ---

    def ask(self, question: str) -> int:
        """Answer a natural language question about the system."""
        api_key = self._get_api_key()
        if not api_key:
            return 1

        provider = self._get_provider()
        self._debug(f"Using provider: {provider}")

        try:
            handler = AskHandler(
                api_key=api_key,
                provider=provider,
            )
            answer = handler.ask(question)
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
                "Please specify a subcommand (set/get/list/delete/export/import/clear/template/audit/check/path)"
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
            # Shell environment analyzer commands
            elif action == "audit":
                return self._env_audit(args)
            elif action == "check":
                return self._env_check(args)
            elif action == "path":
                return self._env_path(args)
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

    # --- Shell Environment Analyzer Commands ---
    def _env_audit(self, args: argparse.Namespace) -> int:
        """Audit shell environment variables and show their sources."""
        from cortex.shell_env_analyzer import Shell, ShellEnvironmentAnalyzer

        shell = None
        if hasattr(args, "shell") and args.shell:
            shell = Shell(args.shell)

        analyzer = ShellEnvironmentAnalyzer(shell=shell)
        include_system = not getattr(args, "no_system", False)
        as_json = getattr(args, "json", False)

        audit = analyzer.audit(include_system=include_system)

        if as_json:
            import json

            print(json.dumps(audit.to_dict(), indent=2))
            return 0

        # Display audit results
        cx_header(f"Environment Audit ({audit.shell.value} shell)")

        console.print("\n[bold]Config Files Scanned:[/bold]")
        for f in audit.config_files_scanned:
            console.print(f"  • {f}")

        if audit.variables:
            console.print("\n[bold]Variables with Definitions:[/bold]")
            # Sort by number of sources (most definitions first)
            sorted_vars = sorted(audit.variables.items(), key=lambda x: len(x[1]), reverse=True)
            for var_name, sources in sorted_vars[:20]:  # Limit to top 20
                console.print(f"\n  [cyan]{var_name}[/cyan] ({len(sources)} definition(s))")
                for src in sources:
                    console.print(f"    [dim]{src.file}:{src.line_number}[/dim]")
                    # Show truncated value
                    val_preview = src.value[:50] + "..." if len(src.value) > 50 else src.value
                    console.print(f"      → {val_preview}")

            if len(audit.variables) > 20:
                console.print(f"\n  [dim]... and {len(audit.variables) - 20} more variables[/dim]")

        if audit.conflicts:
            console.print("\n[bold]⚠️  Conflicts Detected:[/bold]")
            for conflict in audit.conflicts:
                severity_color = {
                    "info": "blue",
                    "warning": "yellow",
                    "error": "red",
                }.get(conflict.severity.value, "white")
                console.print(
                    f"  [{severity_color}]{conflict.severity.value.upper()}[/{severity_color}]: {conflict.description}"
                )

        console.print(f"\n[dim]Total: {len(audit.variables)} variable(s) found[/dim]")
        return 0

    def _env_check(self, args: argparse.Namespace) -> int:
        """Check for environment variable conflicts and issues."""
        from cortex.shell_env_analyzer import Shell, ShellEnvironmentAnalyzer

        shell = None
        if hasattr(args, "shell") and args.shell:
            shell = Shell(args.shell)

        analyzer = ShellEnvironmentAnalyzer(shell=shell)
        audit = analyzer.audit()

        cx_header(f"Environment Health Check ({audit.shell.value})")

        issues_found = 0

        # Check for conflicts
        if audit.conflicts:
            console.print("\n[bold]Variable Conflicts:[/bold]")
            for conflict in audit.conflicts:
                issues_found += 1
                severity_color = {
                    "info": "blue",
                    "warning": "yellow",
                    "error": "red",
                }.get(conflict.severity.value, "white")
                console.print(
                    f"  [{severity_color}]●[/{severity_color}] {conflict.variable_name}: {conflict.description}"
                )
                for src in conflict.sources:
                    console.print(f"      [dim]• {src.file}:{src.line_number}[/dim]")

        # Check PATH
        duplicates = analyzer.get_path_duplicates()
        missing = analyzer.get_missing_paths()

        if duplicates:
            console.print("\n[bold]PATH Duplicates:[/bold]")
            for dup in duplicates:
                issues_found += 1
                console.print(f"  [yellow]●[/yellow] {dup}")

        if missing:
            console.print("\n[bold]Missing PATH Entries:[/bold]")
            for m in missing:
                issues_found += 1
                console.print(f"  [red]●[/red] {m}")

        if issues_found == 0:
            cx_print("\n✓ No issues found! Environment looks healthy.", "success")
            return 0
        else:
            console.print(f"\n[yellow]Found {issues_found} issue(s)[/yellow]")
            cx_print("Run 'cortex env path dedupe' to fix PATH duplicates", "info")
            return 1

    def _env_path(self, args: argparse.Namespace) -> int:
        """Handle PATH management subcommands."""
        from cortex.shell_env_analyzer import Shell, ShellEnvironmentAnalyzer

        path_action = getattr(args, "path_action", None)

        if not path_action:
            self._print_error("Please specify a path action (list/add/remove/dedupe/clean)")
            return 1

        shell = None
        if hasattr(args, "shell") and args.shell:
            shell = Shell(args.shell)

        analyzer = ShellEnvironmentAnalyzer(shell=shell)

        if path_action == "list":
            return self._env_path_list(analyzer, args)
        elif path_action == "add":
            return self._env_path_add(analyzer, args)
        elif path_action == "remove":
            return self._env_path_remove(analyzer, args)
        elif path_action == "dedupe":
            return self._env_path_dedupe(analyzer, args)
        elif path_action == "clean":
            return self._env_path_clean(analyzer, args)
        else:
            self._print_error(f"Unknown path action: {path_action}")
            return 1

    def _env_path_list(self, analyzer: "ShellEnvironmentAnalyzer", args: argparse.Namespace) -> int:
        """List PATH entries with status."""
        as_json = getattr(args, "json", False)

        current_path = os.environ.get("PATH", "")
        entries = current_path.split(os.pathsep)

        # Get analysis
        audit = analyzer.audit()

        if as_json:
            import json

            print(json.dumps([e.to_dict() for e in audit.path_entries], indent=2))
            return 0

        cx_header("PATH Entries")

        seen: set = set()
        for i, entry in enumerate(entries, 1):
            if not entry:
                continue

            status_icons = []

            # Check if exists
            if not Path(entry).exists():
                status_icons.append("[red]✗ missing[/red]")

            # Check if duplicate
            if entry in seen:
                status_icons.append("[yellow]⚠ duplicate[/yellow]")
            seen.add(entry)

            status = " ".join(status_icons) if status_icons else "[green]✓[/green]"
            console.print(f"  {i:2d}. {entry}  {status}")

        duplicates = analyzer.get_path_duplicates()
        missing = analyzer.get_missing_paths()

        console.print()
        console.print(
            f"[dim]Total: {len(entries)} entries, {len(duplicates)} duplicates, {len(missing)} missing[/dim]"
        )

        return 0

    def _env_path_add(self, analyzer: "ShellEnvironmentAnalyzer", args: argparse.Namespace) -> int:
        """Add a path entry."""
        import os
        from pathlib import Path

        new_path = args.path
        prepend = not getattr(args, "append", False)
        persist = getattr(args, "persist", False)

        # Resolve to absolute path
        new_path = str(Path(new_path).expanduser().resolve())

        if persist:
            # When persisting, check the config file, not current PATH
            try:
                config_path = analyzer.get_shell_config_path()
                # Check if already in config
                config_content = ""
                if os.path.exists(config_path):
                    with open(config_path) as f:
                        config_content = f.read()

                # Check if path is in a cortex-managed block
                if (
                    f'export PATH="{new_path}:$PATH"' in config_content
                    or f'export PATH="$PATH:{new_path}"' in config_content
                ):
                    cx_print(f"'{new_path}' is already in {config_path}", "info")
                    return 0

                analyzer.add_path_to_config(new_path, prepend=prepend)
                cx_print(f"✓ Added '{new_path}' to {config_path}", "success")
                console.print(f"[dim]To use in current shell: source {config_path}[/dim]")
            except Exception as e:
                self._print_error(f"Failed to persist: {e}")
                return 1
        else:
            # Check if already in current PATH (for non-persist mode)
            current_path = os.environ.get("PATH", "")
            if new_path in current_path.split(os.pathsep):
                cx_print(f"'{new_path}' is already in PATH", "info")
                return 0

            # Only modify current process env (won't persist across commands)
            updated = analyzer.safe_add_path(new_path, prepend=prepend)
            os.environ["PATH"] = updated
            position = "prepended to" if prepend else "appended to"
            cx_print(f"✓ '{new_path}' {position} PATH (this process only)", "success")
            cx_print("Note: Add --persist to make this permanent", "info")

        return 0

    def _env_path_remove(
        self, analyzer: "ShellEnvironmentAnalyzer", args: argparse.Namespace
    ) -> int:
        """Remove a path entry."""
        import os

        target_path = args.path
        persist = getattr(args, "persist", False)

        if persist:
            # When persisting, remove from config file
            try:
                config_path = analyzer.get_shell_config_path()
                result = analyzer.remove_path_from_config(target_path)
                if result:
                    cx_print(f"✓ Removed '{target_path}' from {config_path}", "success")
                    console.print(f"[dim]To update current shell: source {config_path}[/dim]")
                else:
                    cx_print(f"'{target_path}' was not in cortex-managed config block", "info")
            except Exception as e:
                self._print_error(f"Failed to persist removal: {e}")
                return 1
        else:
            # Only modify current process env (won't persist across commands)
            current_path = os.environ.get("PATH", "")
            if target_path not in current_path.split(os.pathsep):
                cx_print(f"'{target_path}' is not in current PATH", "info")
                return 0

            updated = analyzer.safe_remove_path(target_path)
            os.environ["PATH"] = updated
            cx_print(f"✓ Removed '{target_path}' from PATH (this process only)", "success")
            cx_print("Note: Add --persist to make this permanent", "info")

        return 0

    def _env_path_dedupe(
        self, analyzer: "ShellEnvironmentAnalyzer", args: argparse.Namespace
    ) -> int:
        """Remove duplicate PATH entries."""
        import os

        dry_run = getattr(args, "dry_run", False)
        persist = getattr(args, "persist", False)

        duplicates = analyzer.get_path_duplicates()

        if not duplicates:
            cx_print("✓ No duplicate PATH entries found", "success")
            return 0

        cx_header("PATH Deduplication")
        console.print(f"[yellow]Found {len(duplicates)} duplicate(s):[/yellow]")
        for dup in duplicates:
            console.print(f"  • {dup}")

        if dry_run:
            console.print("\n[dim]Dry run - no changes made[/dim]")
            clean_path = analyzer.dedupe_path()
            console.print("\n[bold]Cleaned PATH would be:[/bold]")
            for entry in clean_path.split(os.pathsep)[:10]:
                console.print(f"  {entry}")
            if len(clean_path.split(os.pathsep)) > 10:
                console.print("  [dim]... and more[/dim]")
            return 0

        # Apply deduplication
        clean_path = analyzer.dedupe_path()
        os.environ["PATH"] = clean_path
        cx_print(f"✓ Removed {len(duplicates)} duplicate(s) from PATH (current session)", "success")

        if persist:
            script = analyzer.generate_path_fix_script()
            console.print("\n[bold]Add this to your shell config for persistence:[/bold]")
            console.print(f"[dim]{script}[/dim]")

        return 0

    def _env_path_clean(
        self, analyzer: "ShellEnvironmentAnalyzer", args: argparse.Namespace
    ) -> int:
        """Clean PATH by removing duplicates and optionally missing paths."""
        import os

        remove_missing = getattr(args, "remove_missing", False)
        dry_run = getattr(args, "dry_run", False)

        duplicates = analyzer.get_path_duplicates()
        missing = analyzer.get_missing_paths() if remove_missing else []

        total_issues = len(duplicates) + len(missing)

        if total_issues == 0:
            cx_print("✓ PATH is already clean", "success")
            return 0

        cx_header("PATH Cleanup")

        if duplicates:
            console.print(f"[yellow]Duplicates ({len(duplicates)}):[/yellow]")
            for d in duplicates[:5]:
                console.print(f"  • {d}")
            if len(duplicates) > 5:
                console.print(f"  [dim]... and {len(duplicates) - 5} more[/dim]")

        if missing:
            console.print(f"\n[red]Missing paths ({len(missing)}):[/red]")
            for m in missing[:5]:
                console.print(f"  • {m}")
            if len(missing) > 5:
                console.print(f"  [dim]... and {len(missing) - 5} more[/dim]")

        if dry_run:
            clean_path = analyzer.clean_path(remove_missing=remove_missing)
            console.print("\n[dim]Dry run - no changes made[/dim]")
            console.print(
                f"[bold]Would reduce PATH from {len(os.environ.get('PATH', '').split(os.pathsep))} to {len(clean_path.split(os.pathsep))} entries[/bold]"
            )
            return 0

        # Apply cleanup
        clean_path = analyzer.clean_path(remove_missing=remove_missing)
        old_count = len(os.environ.get("PATH", "").split(os.pathsep))
        new_count = len(clean_path.split(os.pathsep))
        os.environ["PATH"] = clean_path

        cx_print(f"✓ Cleaned PATH: {old_count} → {new_count} entries", "success")

        # Show fix script
        script = analyzer.generate_path_fix_script()
        if "no fixes needed" not in script:
            console.print("\n[bold]To make permanent, add to your shell config:[/bold]")
            console.print(f"[dim]{script}[/dim]")

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
    """Display a beautifully formatted help table using the Rich library.

    This function outputs the primary command menu, providing descriptions
    for all core Cortex utilities including installation, environment
    management, and container tools.
    """
    from rich.table import Table

    show_banner(show_version=True)
    console.print()

    console.print("[bold]AI-powered package manager for Linux[/bold]")
    console.print("[dim]Just tell Cortex what you want to install.[/dim]")
    console.print()

    # Initialize a table to display commands with specific column styling
    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Command", style="green")
    table.add_column("Description")

    # Command Rows
    table.add_row("ask <question>", "Ask about your system")
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
    table.add_row("docker permissions", "Fix Docker bind-mount permissions")
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

    # Define the docker command and its associated sub-actions
    docker_parser = subparsers.add_parser("docker", help="Docker and container utilities")
    docker_subs = docker_parser.add_subparsers(dest="docker_action", help="Docker actions")

    # Add the permissions action to allow fixing file ownership issues
    perm_parser = docker_subs.add_parser(
        "permissions", help="Fix file permissions from bind mounts"
    )

    # Provide an option to skip the manual confirmation prompt
    perm_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    perm_parser.add_argument(
        "--execute", "-e", action="store_true", help="Apply ownership changes (default: dry-run)"
    )

    # Demo command
    demo_parser = subparsers.add_parser("demo", help="See Cortex in action")

    # Wizard command
    wizard_parser = subparsers.add_parser("wizard", help="Configure API key interactively")

    # Status command (includes comprehensive health checks)
    subparsers.add_parser("status", help="Show comprehensive system status and health checks")

    # Ask command
    ask_parser = subparsers.add_parser("ask", help="Ask a question about your system")
    ask_parser.add_argument("question", type=str, help="Natural language question")

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
    sandbox_exec_parser.add_argument("cmd", nargs="+", help="Command to execute")
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

    # --- Shell Environment Analyzer Commands ---
    # env audit - show all shell variables with sources
    env_audit_parser = env_subs.add_parser(
        "audit", help="Audit shell environment variables and show their sources"
    )
    env_audit_parser.add_argument(
        "--shell",
        choices=["bash", "zsh", "fish"],
        help="Shell to analyze (default: auto-detect)",
    )
    env_audit_parser.add_argument(
        "--no-system",
        action="store_true",
        help="Exclude system-wide config files",
    )
    env_audit_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # env check - detect conflicts and issues
    env_check_parser = env_subs.add_parser(
        "check", help="Check for environment variable conflicts and issues"
    )
    env_check_parser.add_argument(
        "--shell",
        choices=["bash", "zsh", "fish"],
        help="Shell to check (default: auto-detect)",
    )

    # env path subcommands
    env_path_parser = env_subs.add_parser("path", help="Manage PATH entries")
    env_path_subs = env_path_parser.add_subparsers(dest="path_action", help="PATH actions")

    # env path list
    env_path_list_parser = env_path_subs.add_parser("list", help="List PATH entries with status")
    env_path_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # env path add <path> [--prepend|--append] [--persist]
    env_path_add_parser = env_path_subs.add_parser("add", help="Add a path entry (idempotent)")
    env_path_add_parser.add_argument("path", help="Path to add")
    env_path_add_parser.add_argument(
        "--append",
        action="store_true",
        help="Append to end of PATH (default: prepend)",
    )
    env_path_add_parser.add_argument(
        "--persist",
        action="store_true",
        help="Add to shell config file for persistence",
    )
    env_path_add_parser.add_argument(
        "--shell",
        choices=["bash", "zsh", "fish"],
        help="Shell config to modify (default: auto-detect)",
    )

    # env path remove <path> [--persist]
    env_path_remove_parser = env_path_subs.add_parser("remove", help="Remove a path entry")
    env_path_remove_parser.add_argument("path", help="Path to remove")
    env_path_remove_parser.add_argument(
        "--persist",
        action="store_true",
        help="Remove from shell config file",
    )
    env_path_remove_parser.add_argument(
        "--shell",
        choices=["bash", "zsh", "fish"],
        help="Shell config to modify (default: auto-detect)",
    )

    # env path dedupe [--dry-run] [--persist]
    env_path_dedupe_parser = env_path_subs.add_parser(
        "dedupe", help="Remove duplicate PATH entries"
    )
    env_path_dedupe_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without making changes",
    )
    env_path_dedupe_parser.add_argument(
        "--persist",
        action="store_true",
        help="Generate shell config to persist deduplication",
    )
    env_path_dedupe_parser.add_argument(
        "--shell",
        choices=["bash", "zsh", "fish"],
        help="Shell for generated config (default: auto-detect)",
    )

    # env path clean [--remove-missing] [--dry-run]
    env_path_clean_parser = env_path_subs.add_parser(
        "clean", help="Clean PATH (remove duplicates and optionally missing paths)"
    )
    env_path_clean_parser.add_argument(
        "--remove-missing",
        action="store_true",
        help="Also remove paths that don't exist",
    )
    env_path_clean_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be cleaned without making changes",
    )
    env_path_clean_parser.add_argument(
        "--shell",
        choices=["bash", "zsh", "fish"],
        help="Shell for generated fix script (default: auto-detect)",
    )
    # --------------------------

    args = parser.parse_args()

    # The Guard: Check for empty commands before starting the CLI
    if not args.command:
        show_rich_help()
        return 0

    # Initialize the CLI handler
    cli = CortexCLI(verbose=args.verbose)

    try:
        # Route the command to the appropriate method inside the cli object
        if args.command == "docker":
            if args.docker_action == "permissions":
                return cli.docker_permissions(args)
            parser.print_help()
            return 1

        if args.command == "demo":
            return cli.demo()
        elif args.command == "wizard":
            return cli.wizard()
        elif args.command == "status":
            return cli.status()
        elif args.command == "ask":
            return cli.ask(args.question)
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
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled", file=sys.stderr)
        return 130
    except (ValueError, ImportError, OSError) as e:
        print(f"❌ Error: {e}", file=sys.stderr)
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
