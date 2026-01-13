import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cortex.api_key_detector import setup_api_key
from cortex.ask import AskHandler
from cortex.branding import VERSION, console, show_banner
from cortex.coordinator import InstallationCoordinator, InstallationStep, StepStatus
from cortex.demo import run_demo
from cortex.dependency_importer import (
    DependencyImporter,
    PackageEcosystem,
    ParseResult,
)
from cortex.env_manager import EnvironmentManager, get_env_manager
from cortex.installation_history import InstallationHistory, InstallationStatus, InstallationType
from cortex.llm.interpreter import CommandInterpreter
from cortex.network_config import NetworkConfig
from cortex.notification_manager import NotificationManager
from cortex.stack_manager import StackManager
from cortex.ui import (
    data_table,
    error,
    info,
    progress_bar,
    section,
    spinner,
    status_box,
    success,
    summary_box,
    warning,
)
from cortex.validators import validate_install_request

if TYPE_CHECKING:
    from cortex.shell_env_analyzer import ShellEnvironmentAnalyzer

# Suppress noisy log messages in normal operation
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cortex.installation_history").setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class CortexCLI:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._detected_provider: str | None = None

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
            info(f"[dim]DEBUG[/dim] {message}", badge=True)

    def _get_api_key(self) -> str | None:
        # 1. Check explicit provider override first (fake/ollama need no key)
        explicit_provider = os.environ.get("CORTEX_PROVIDER", "").lower()
        if explicit_provider == "fake":
            self._debug("Using Fake provider for testing")
            return "fake-key"
        if explicit_provider == "ollama":
            self._debug("Using Ollama (no API key required)")
            return "ollama-local"

        with spinner("Detecting API provider and credentials"):
            success_flag, key, detected_provider = setup_api_key()

        if success_flag:
            self._detected_provider = detected_provider
            success("API key loaded", f"Provider: {detected_provider}")
            return key

        # Still no key
        error("No API key found or provided")
        info("Run [bold]cortex wizard[/bold] to configure your API key.", badge=True)
        info("Or use [bold]CORTEX_PROVIDER=ollama[/bold] for offline mode.", badge=True)
        return None

    def _animate_spinner(self, *_):
        """No-op animation placeholder (kept for backward compatibility)."""
        pass

    def _clear_line(self):
        """No-op; kept for compatibility with earlier console-clearing helpers."""
        pass

    def _get_provider(self) -> str:
        # Check environment variable for explicit provider choice
        explicit_provider = os.environ.get("CORTEX_PROVIDER", "").lower()
        if explicit_provider in {"ollama", "openai", "claude", "fake"}:
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
        """Legacy status mapper. Internally routes to ui.py for consistent formatting."""
        info(message, badge=True)

    def _print_error(self, message: str):
        error(message)

    def _print_success(self, message: str):
        success(message)

    def notify(self, args):
        """Handle notification commands"""
        # Addressing CodeRabbit feedback: Handle missing subcommand gracefully
        if not args.notify_action:
            error("Please specify a subcommand (config/enable/disable/dnd/send)")
            return 1

        mgr = NotificationManager()
        section("NOTIFICATIONS")

        if args.notify_action == "config":
            status_box(
                "NOTIFICATION SETTINGS",
                {
                    "Status": "Enabled" if mgr.config.get("enabled", True) else "Disabled",
                    "Do Not Disturb": f"{mgr.config.get('dnd_start','—')} → {mgr.config.get('dnd_end','—')}",
                    "History File": mgr.history_file,
                },
                border_color="green" if mgr.config.get("enabled", True) else "red",
            )
            return 0

        elif args.notify_action == "enable":
            mgr.config["enabled"] = True
            # Addressing CodeRabbit feedback: Ideally should use a public method instead of private _save_config,
            # but keeping as is for a simple fix (or adding a save method to NotificationManager would be best).
            mgr._save_config()
            success("Notifications enabled")
            return 0

        elif args.notify_action == "disable":
            mgr.config["enabled"] = False
            mgr._save_config()
            warning("Notifications disabled (critical alerts will still show)")
            return 0

        elif args.notify_action == "dnd":
            if not args.start or not args.end:
                error("Please provide start and end times (HH:MM)")
                return 1

            # Addressing CodeRabbit feedback: Add time format validation
            try:
                datetime.strptime(args.start, "%H:%M")
                datetime.strptime(args.end, "%H:%M")
            except ValueError:
                error("Invalid time format. Use HH:MM (e.g., 22:00)")
                return 1

            mgr.config["dnd_start"] = args.start
            mgr.config["dnd_end"] = args.end
            mgr._save_config()
            success(f"DND window updated: {args.start} → {args.end}")
            return 0

        elif args.notify_action == "send":
            if not args.message:
                error("Message is required")
                return 1

            with spinner("Sending notification"):
                mgr.send(
                    args.title,
                    args.message,
                    level=args.level,
                    actions=args.actions,
                )

            success("Notification sent")
            return 0

        else:
            error("Unknown notify command")
            return 1

    # -------------------------------
    def demo(self):
        """
        Run the one-command investor demo
        """
        return run_demo()
    def stack(self, args: argparse.Namespace) -> int:
        try:
            manager = StackManager()
        except FileNotFoundError as e:
            self._print_error(f"stacks.json not found. Ensure cortex/stacks.json exists: {e}")
            return 1
        except ValueError as e:
            self._print_error(f"stacks.json is invalid or malformed: {e}")
            return 1

        if args.dry_run and not args.name:
            error("--dry-run requires a stack name (e.g., cortex stack ml --dry-run)")
            return 1

        if args.list or (not args.name and not args.describe):
            return self._handle_stack_list(manager)

        if args.describe:
            return self._handle_stack_describe(manager, args.describe)

        return self._handle_stack_install(manager, args)

    def _handle_stack_describe(self, manager: StackManager, stack_id: str) -> int:
        """Describe a specific stack."""
        stack = manager.find_stack(stack_id)
        if not stack:
            self._print_error(
                f"Stack '{stack_id}' not found. Use --list to see available stacks."
            )
            return 1

        section(f"STACK DETAILS: {stack_id}")

        description = manager.describe_stack(stack_id)

        status_box(
            "STACK OVERVIEW",
            {
                "ID": stack.get("id", stack_id),
                "Name": stack.get("name", "Unnamed Stack"),
                "Packages": str(len(stack.get("packages", []))),
            },
        )

        from rich.panel import Panel
        console.print(
            Panel(
                description,
                title="[bold]Description[/bold]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

        return 0

    def _handle_stack_list(self, manager: StackManager) -> int:
        """List all available stacks."""
        stacks = manager.list_stacks()

        rows = []
        for stack in stacks:
            rows.append(
                [
                    stack.get("id", "unknown"),
                    stack.get("name", "Unnamed Stack"),
                    stack.get("description", "No description"),
                    len(stack.get("packages", [])),
                ]
            )

        section("AVAILABLE STACKS")

        data_table(
            columns=[
                {"name": "ID", "style": "cyan"},
                {"name": "Name"},
                {"name": "Description"},
                {"name": "Packages", "justify": "right"},
            ],
            rows=rows,
            title="Pre-built Software Stacks",
        )

        info("Use: cortex stack <name> to install a stack", badge=True)
        return 0

    def _handle_stack_install(self, manager: StackManager, args: argparse.Namespace) -> int:
        """Install a stack with optional hardware-aware selection."""
        original_name = args.name
        suggested_name = manager.suggest_stack(args.name)

        if suggested_name != original_name:
            info(
                f"No GPU detected. Using '{suggested_name}' instead of '{original_name}'",
                badge=True,
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
        status_box(
            f"DRY RUN: {stack['name']}",
            {
                "Packages": str(len(packages)),
                "Mode": "Preview only",
            },
        )

        data_table(
            columns=[{"name": "Package"}],
            rows=[[pkg] for pkg in packages],
            title="Packages to be Installed",
        )

        warning("Dry run only - no commands executed")
        return 0

    def _handle_stack_real_install(self, stack: dict[str, Any], packages: list[str]) -> int:
        """Install all packages in the stack."""
        section(f"INSTALLING STACK: {stack['name']}")

        # Batch into a single LLM request
        packages_str = " ".join(packages)
        result = self.install(software=packages_str, execute=True, dry_run=False)

        if result != 0:
            self._print_error(f"Failed to install stack '{stack['name']}'")
            return 1

        summary_box(
            "STACK INSTALLED",
            [
                f"Name: {stack['name']}",
                f"Packages installed: {len(packages)}",
            ],
            success=True,
        )
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
            section("DOCKER SANDBOX")

            status_box(
                "SANDBOX OVERVIEW",
                {
                    "Purpose": "Test packages safely before installing",
                    "Backend": "Docker",
                },
            )

            data_table(
                columns=[
                    {"name": "Command", "style": "cyan"},
                    {"name": "Description"},
                ],
                rows=[
                    ["create <name>", "Create a sandbox environment"],
                    ["install <name> <pkg>", "Install package in sandbox"],
                    ["test <name> [pkg]", "Run tests in sandbox"],
                    ["promote <name> <pkg>", "Install tested package on system"],
                    ["cleanup <name>", "Remove sandbox environment"],
                    ["list", "List all sandboxes"],
                    ["exec <name> <cmd>", "Execute command in sandbox"],
                ],
                title="Available Commands",
            )

            info("Example: cortex sandbox create test-env", badge=True)
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
            info("Docker is required only for sandbox commands", badge=True)
            return 1
        except SandboxNotFoundError as e:
            self._print_error(str(e))
            info("Use 'cortex sandbox list' to see available sandboxes", badge=True)
            return 1
        except SandboxAlreadyExistsError as e:
            self._print_error(str(e))
            return 1

    def _sandbox_create(self, sandbox, args: argparse.Namespace) -> int:
        """Create a new sandbox environment."""
        name = args.name
        image = getattr(args, "image", "ubuntu:22.04")

        section("CREATING SANDBOX")

        with spinner(f"Creating sandbox '{name}'"):
            result = sandbox.create(name, image=image)

        if result.success:
            summary_box(
                "SANDBOX CREATED",
                [
                    f"Name: {name}",
                    f"Image: {image}",
                ],
                success=True,
            )
            return 0

        error(result.message)
        if result.stderr:
            console.print("[red]Details:[/red]")
            console.print(result.stderr.strip(), style="red")
        return 1

    def _sandbox_install(self, sandbox, args: argparse.Namespace) -> int:
        """Install a package in sandbox."""
        name = args.name
        package = args.package

        section("SANDBOX INSTALL")

        with spinner(f"Installing '{package}' in sandbox '{name}'"):
            result = sandbox.install(name, package)

        if result.success:
            summary_box(
                "PACKAGE INSTALLED",
                [
                    f"Sandbox: {name}",
                    f"Package: {package}",
                ],
                success=True,
            )
            return 0

        error(result.message)
        if result.stderr:
            console.print("[red]Details:[/red]")
            console.print(result.stderr[:500].strip(), style="red")
        return 1

    def _sandbox_test(self, sandbox, args: argparse.Namespace) -> int:
        """Run tests in sandbox."""
        from cortex.sandbox import SandboxTestStatus

        name = args.name
        package = getattr(args, "package", None)

        section("SANDBOX TESTS")

        with spinner(f"Running tests in sandbox '{name}'"):
            result = sandbox.test(name, package)

        rows = []
        for test in result.test_results:
            if test.result == SandboxTestStatus.PASSED:
                status = "[green]PASSED[/green]"
            elif test.result == SandboxTestStatus.FAILED:
                status = "[red]FAILED[/red]"
            else:
                status = "[yellow]SKIPPED[/yellow]"

            rows.append([test.name, status])

        data_table(
            columns=[
                {"name": "Test"},
                {"name": "Result", "justify": "center"},
            ],
            rows=rows,
            title="Test Results",
        )

        if result.success:
            success("All tests passed")
            return 0

        error("Some tests failed")
        return 1

    def _sandbox_promote(self, sandbox, args: argparse.Namespace) -> int:
        """Promote a tested package to main system."""
        name = args.name
        package = args.package
        dry_run = getattr(args, "dry_run", False)
        skip_confirm = getattr(args, "yes", False)
        section("SANDBOX PROMOTION")

        if dry_run:
            info(f"Would run: sudo apt-get install -y {package}", badge=True)
            return 0

        if not skip_confirm:
            console.print(f"[yellow]Promote '{package}' to main system?[/yellow] [Y/n]: ", end="")
            try:
                response = input().strip().lower()
                if response and response not in ("y", "yes"):
                    warning("Promotion cancelled")
                    return 0
            except (EOFError, KeyboardInterrupt):
                console.print()
                warning("Promotion cancelled")
                return 0

        # sandbox.promote likely runs docker/remote operations; keep spinner for UX
        with spinner(f"Installing '{package}' on main system"):
            result = sandbox.promote(name, package, dry_run=False)

        if result.success:
            success(f"{package} installed on main system")
            return 0

        error(result.message)
        if result.stderr:
            console.print("[red]Details:[/red]")
            console.print(result.stderr[:500].strip(), style="red")
        return 1

    def _sandbox_cleanup(self, sandbox, args: argparse.Namespace) -> int:
        """Remove a sandbox environment."""
        name = args.name
        force = getattr(args, "force", False)

        section("SANDBOX CLEANUP")

        with spinner(f"Removing sandbox '{name}'"):
            result = sandbox.cleanup(name, force=force)

        if result.success:
            success(f"Sandbox '{name}' removed")
            return 0
        else:
            self._print_error(result.message)
            return 1

    def _sandbox_list(self, sandbox) -> int:
        """List all sandbox environments."""
        sandboxes = sandbox.list_sandboxes()

        if not sandboxes:
            info("No sandbox environments found", badge=True)
            info("Create one with: cortex sandbox create <name>", badge=True)
            return 0

        rows = []
        for sb in sandboxes:
            rows.append(
                [
                    sb.name,
                    sb.image,
                    sb.state.value,
                    ", ".join(sb.packages) if sb.packages else "—",
                ]
            )

        section("SANDBOX ENVIRONMENTS")

        data_table(
            columns=[
                {"name": "Name", "style": "cyan"},
                {"name": "Image"},
                {"name": "State"},
                {"name": "Packages"},
            ],
            rows=rows,
        )

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

        section("AI QUERY")

        status_box(
            "REQUEST",
            {
                "Question": question,
                "Provider": provider,
            },
        )

        try:
            with spinner("Thinking"):
                handler = AskHandler(
                    api_key=api_key,
                    provider=provider,
                )
                answer = handler.ask(question)

            section("ANSWER")
            from rich.panel import Panel

            console.print(
                Panel(
                    answer,
                    title="[bold]RESPONSE[/bold]",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )
            return 0
        except ImportError as e:
            # Provide a helpful message if provider SDK is missing
            self._print_error(str(e))
            info(
                "Install the required SDK or set CORTEX_PROVIDER=ollama for local mode.",
                badge=True,
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
        is_valid, error_msg = validate_install_request(software)
        if not is_valid:
            self._print_error(error_msg)
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

        # Initialize installation history
        history = InstallationHistory()
        install_id = None
        start_time = datetime.now()

        try:
            section("INSTALL REQUEST")

            status_box(
                "REQUEST DETAILS",
                {
                    "Software": software,
                    "Provider": provider,
                    "Mode": "Dry run" if dry_run else "Execute" if execute else "Plan only",
                },
            )

            with spinner("Understanding request and planning installation"):
                interpreter = CommandInterpreter(api_key=api_key, provider=provider)
                commands = interpreter.parse(f"install {software}")

            if not commands:
                self._print_error("No commands generated. Please try again.")
                return 1

            # Extract packages from commands for tracking
            packages = history._extract_packages_from_commands(commands)

            # Record installation start
            if execute or dry_run:
                install_id = history.record_installation(
                    InstallationType.INSTALL, packages, commands, start_time
                )


            section("INSTALLATION PLAN")

            data_table(
                columns=[
                    {"name": "#", "justify": "right"},
                    {"name": "Command"},
                ],
                rows=[[i + 1, cmd] for i, cmd in enumerate(commands)],
                title="Generated Commands",
            )

            if dry_run:
                summary_box(
                    "DRY RUN COMPLETE",
                    [
                        f"Commands generated: {len(commands)}",
                        "No commands were executed",
                    ],
                    success=True,
                )
                if install_id:
                    history.update_installation(install_id, InstallationStatus.SUCCESS)
                return 0

            if not execute:
                warning("Use --execute to run these commands")
                info(f"Example: cortex install {software} --execute", badge=True)
                return 0

            section("EXECUTION")

            if parallel:
                import asyncio
                from cortex.install_parallel import run_parallel_install

                def parallel_log_callback(message: str, level: str = "info"):
                    if level == "success":
                        success(message)
                    elif level == "error":
                        error(message)
                    else:
                        info(message)

                try:
                    with spinner("Executing installation in parallel"):
                        success_flag, _ = asyncio.run(
                            run_parallel_install(
                                commands=commands,
                                descriptions=[f"Step {i + 1}" for i in range(len(commands))],
                                timeout=300,
                                stop_on_error=True,
                                log_callback=parallel_log_callback,
                            )
                        )
                except Exception as e:
                    if install_id:
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, str(e)
                        )
                    self._print_error(f"Parallel execution failed: {e}")
                    return 1

                if not success_flag:
                    self._print_error("Installation failed")
                    return 1

                summary_box(
                    "INSTALLATION COMPLETE",
                    [
                        f"Software: {software}",
                        "Mode: Parallel",
                    ],
                    success=True,
                )

                if install_id:
                    history.update_installation(install_id, InstallationStatus.SUCCESS)
                return 0

            total_steps = len(commands)
            info("Installing packages", badge=True)

            if any(cmd.strip().startswith("sudo ") for cmd in commands):
                if os.system("sudo -v") != 0:
                    self._print_error("Sudo authentication failed or cancelled")
                    return 1

            for idx, cmd in enumerate(commands, 1):
                info(f"Step {idx}/{total_steps}", badge=True)
                console.print(f"    [dim]→ {cmd}[/dim]")

                coordinator = InstallationCoordinator(
                    commands=[cmd],
                    descriptions=[f"Step {idx}"],
                    timeout=300,
                    stop_on_error=True,
                )

                result = coordinator.execute()

                if not result.success:
                    self._print_error(f"Failed at step {idx}")
                    if result.error_message:
                        console.print(result.error_message, style="red")

                    if install_id:
                        history.update_installation(
                            install_id,
                            InstallationStatus.FAILED,
                            result.error_message or "Installation failed",
                        )
                    return 1

            duration = (datetime.now() - start_time).total_seconds()

            summary_box(
                "INSTALLATION COMPLETE",
                [
                    f"Software: {software}",
                    f"Duration: {duration:.2f}s",
                ],
                success=True,
            )

            if install_id:
                history.update_installation(install_id, InstallationStatus.SUCCESS)

            return 0

        except Exception as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"Unexpected error: {e}")
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

            section("CACHE STATISTICS")

            status_box(
                "SEMANTIC CACHE",
                {
                    "Hits": str(stats.hits),
                    "Misses": str(stats.misses),
                    "Hit rate": hit_rate,
                    "Saved calls (approx)": str(stats.hits),
                },
            )
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

                section("INSTALLATION DETAILS")

                status_value = record.status.value
                if status_value.lower() == "success":
                    status_display = "[green]SUCCESS[/green]"
                elif status_value.lower() == "failed":
                    status_display = "[red]FAILED[/red]"
                else:
                    status_display = status_value.upper()

                status_box(
                    f"INSTALL ID: {record.id}",
                    {
                        "Timestamp": record.timestamp,
                        "Operation": record.operation_type.value,
                        "Status": status_display,
                        "Duration": (
                            f"{record.duration_seconds:.2f}s"
                            if record.duration_seconds
                            else "N/A"
                        ),
                        "Rollback available": str(record.rollback_available),
                    },
                )

                if record.packages:
                    data_table(
                        columns=[{"name": "Packages"}],
                        rows=[[pkg] for pkg in record.packages],
                        title="Installed Packages",
                    )

                if record.commands_executed:
                    data_table(
                        columns=[{"name": "Commands Executed"}],
                        rows=[[cmd] for cmd in record.commands_executed],
                        title="Commands",
                    )

                if record.error_message:
                    warning(record.error_message)

                return 0
                # List history
            status_filter = InstallationStatus(status) if status else None
            records = history.get_history(limit, status_filter)

            if not records:
                info("No installation records found", badge=True)
                return 0

            rows = []
            for r in records:
                date = r.timestamp[:19].replace("T", " ")
                packages = ", ".join(r.packages[:2])
                if len(r.packages) > 2:
                    packages += f" +{len(r.packages) - 2}"

                status_value = r.status.value
                if status_value.lower() == "success":
                    status_display = "[green]SUCCESS[/green]"
                elif status_value.lower() == "failed":
                    status_display = "[red]FAILED[/red]"
                else:
                    status_display = status_value.upper()

                rows.append(
                    [
                        r.id,
                        date,
                        r.operation_type.value,
                        packages,
                        status_display,
                    ]
                )

            section("INSTALLATION HISTORY")

            data_table(
                columns=[
                    {"name": "ID", "style": "cyan"},
                    {"name": "Date"},
                    {"name": "Operation"},
                    {"name": "Packages"},
                    {"name": "Status", "justify": "center"},
                ],
                rows=rows,
                title=f"Last {len(rows)} Installations",
            )

            info("Use: cortex history <id> to view details", badge=True)
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
            success_flag, message = history.rollback(install_id, dry_run)

            section("ROLLBACK")

            if dry_run:
                status_box(
                    f"DRY RUN: {install_id}",
                    {
                        "Action": "Rollback preview",
                        "Details": message,
                    },
                )
                return 0

            if success_flag:
                success(message)
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

    def status(self) -> int:
        """Show comprehensive system status and run health checks"""
        from cortex.doctor import SystemDoctor

        section("SYSTEM STATUS")

        # Run health checks (spinner handled inside SystemDoctor)
        doctor = SystemDoctor()
        result = doctor.run_checks()

        if isinstance(result, int):
            return result
        if hasattr(result, "success"):
            return 0 if result.success else 1
        return 0

    def wizard(self):
        """Interactive setup wizard for API key configuration"""
        show_banner()
        console.print()
        section("SETUP WIZARD")
        success("Welcome to Cortex Setup Wizard!")
        console.print()
        info("Please export your API key in your shell profile.", badge=True)
        return 0

    def env(self, args: argparse.Namespace) -> int:
        """Handle environment variable management commands."""
        env_mgr = get_env_manager()

        # Handle subcommand routing
        action = getattr(args, "env_action", None)

        if not action:
            self._print_error(
                "Please specify a subcommand "
                "(set/get/list/delete/export/import/clear/template/audit/check/path)"
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
            with spinner(f"Setting variable '{key}' for app '{app}'"):
                env_mgr.set_variable(
                    app=app,
                    key=key,
                    value=value,
                    encrypt=encrypt,
                    var_type=var_type,
                    description=description,
                )

            status_box(
                "VARIABLE SAVED",
                {
                    "App": app,
                    "Key": key,
                    "Encrypted": "[yellow]yes[/yellow]" if encrypt else "[green]no[/green]",
                    "Type": var_type,
                },
                border_color="green",
            )
            return 0

        except ValueError as e:
            self._print_error(str(e))
            return 1
        except ImportError as e:
            self._print_error(str(e))
            if "cryptography" in str(e).lower():
                info("Install with: pip install cryptography", badge=True)
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

        encrypted = var_info.encrypted if var_info else False

        display_value = (
            "[dim][encrypted][/dim]"
            if encrypted and not show_encrypted
            else str(value)
        )

        section("ENV VARIABLE")

        status_box(
            f"{app} • {key}",
            {
                "Value": display_value,
                "Encrypted": "[yellow]yes[/yellow]" if encrypted else "[green]no[/green]",
            },
        )

        return 0

    def _env_list(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """List all environment variables for an app."""
        app = args.app
        show_encrypted = getattr(args, "decrypt", False)

        variables = env_mgr.list_variables(app)

        if not variables:
            info(f"No environment variables set for '{app}'", badge=True)
            return 0

        section(f"ENVIRONMENT: {app}")

        rows = []
        for var in sorted(variables, key=lambda v: v.key):
            if var.encrypted:
                if show_encrypted:
                    try:
                        value = env_mgr.get_variable(app, var.key, decrypt=True)
                    except ValueError:
                        value = "[red]decryption failed[/red]"
                else:
                    value = "[dim][encrypted][/dim]"
            else:
                value = var.value

            rows.append(
                [
                    var.key,
                    value,
                    "[yellow]yes[/yellow]" if var.encrypted else "[green]no[/green]",
                    var.description or "",
                ]
            )

        data_table(
            columns=[
                {"name": "Key", "style": "cyan"},
                {"name": "Value"},
                {"name": "Encrypted", "justify": "center"},
                {"name": "Description"},
            ],
            rows=rows,
            title=f"Variables ({len(rows)})",
            expand=True,
        )

        info(f"Total variables: {len(rows)}", badge=True)
        return 0

    def _env_delete(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Delete an environment variable."""
        app = args.app
        key = args.key

        with spinner(f"Deleting variable '{key}' from '{app}'"):
            deleted = env_mgr.delete_variable(app, key)

        if deleted:
            success(f"Deleted '{key}' from '{app}'")
            return 0

        self._print_error(f"Variable '{key}' not found for app '{app}'")
        return 1

    def _env_export(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Export environment variables to .env format."""
        app = args.app
        include_encrypted = getattr(args, "include_encrypted", False)
        output_file = getattr(args, "output", None)

        content = env_mgr.export_env(app, include_encrypted=include_encrypted)

        if not content:
            info(f"No environment variables to export for '{app}'", badge=True)
            return 0

        if output_file:
            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(content)
                success(f"Exported environment to {output_file}")
            except OSError as e:
                self._print_error(f"Failed to write file: {e}")
                return 1
        else:
            # Print to stdout
            print(content, end="")

        return 0

    def _env_import(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Import environment variables from .env format."""
        import sys as _sys

        app = args.app
        input_file = getattr(args, "file", None)
        encrypt_keys = getattr(args, "encrypt_keys", None)

        try:
            if input_file:
                with open(input_file, encoding="utf-8") as f:
                    content = f.read()
            elif not _sys.stdin.isatty():
                content = _sys.stdin.read()
            else:
                self._print_error("No input file specified and stdin is empty")
                info("Usage: cortex env import <app> <file>", badge=True)
                info("   or: cat .env | cortex env import <app>", badge=True)
                return 1

            # Parse encrypt-keys argument
            encrypt_list = []
            if encrypt_keys:
                encrypt_list = [k.strip() for k in encrypt_keys.split(",")]

            with spinner("Importing environment variables"):
                count, errors = env_mgr.import_env(app, content, encrypt_keys=encrypt_list)

            for err in errors:
                warning(err)

            if count > 0:
                success(f"Imported {count} variable(s) to '{app}'")
            else:
                info("No variables imported", badge=True)

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
                info("Operation cancelled", badge=True)
                return 0

        with spinner(f"Clearing environment for '{app}'"):
            cleared = env_mgr.clear_app(app)

        if cleared:
            success(f"Cleared all variables for '{app}'")
        else:
            info(f"No environment data found for '{app}'", badge=True)

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

        section("ENV TEMPLATES")

        rows = []
        for template in sorted(templates, key=lambda t: t.name):
            rows.append([template.name, template.description, len(template.variables)])

        data_table(
            columns=[
                {"name": "Name", "style": "cyan"},
                {"name": "Description"},
                {"name": "Variables", "justify": "right"},
            ],
            rows=rows,
            title="Available Environment Templates",
        )

        info("Use 'cortex env template show <name>' for details", badge=True)
        return 0

    def _env_template_show(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Show template details."""
        template_name = args.template_name

        template = env_mgr.get_template(template_name)
        if not template:
            self._print_error(f"Template '{template_name}' not found")
            return 1

        section(f"TEMPLATE: {template.name}")

        status_box(
            "TEMPLATE INFO",
            {
                "Description": template.description,
                "Variables": str(len(template.variables)),
            },
        )

        rows = []
        for var in template.variables:
            req = "[red]*[/red]" if var.required else ""
            default = f" = {var.default}" if var.default else ""
            rows.append([req, var.name, var.var_type, var.description or "", default])

        data_table(
            columns=[
                {"name": "Req"},
                {"name": "Name", "style": "cyan"},
                {"name": "Type"},
                {"name": "Description"},
                {"name": "Default"},
            ],
            rows=rows,
            title="Template Variables",
        )

        info("* = required", badge=False)
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

        with spinner(f"Applying template '{template_name}' to '{app}'"):
            result = env_mgr.apply_template(
                template_name=template_name,
                app=app,
                values=values,
                encrypt_keys=encrypt_keys,
            )

        if result.valid:
            success(f"Applied template '{template_name}' to '{app}'")
            return 0

        self._print_error(f"Failed to apply template '{template_name}'")
        for err in result.errors:
            warning(err)
        return 1

    def _env_list_apps(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """List all apps with stored environments."""
        apps = env_mgr.list_apps()

        if not apps:
            info("No applications with stored environments", badge=True)
            return 0

        section("APPLICATIONS WITH ENVIRONMENTS")

        rows = []
        for app in apps:
            var_count = len(env_mgr.list_variables(app))
            rows.append([app, var_count])

        data_table(
            columns=[
                {"name": "Application", "style": "cyan"},
                {"name": "Variables", "justify": "right"},
            ],
            rows=rows,
            title="Apps",
        )

        return 0

    def _env_load(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Load environment variables into current process."""
        app = args.app

        with spinner(f"Loading variables from '{app}' into environment"):
            count = env_mgr.load_to_environ(app)

        if count > 0:
            success(f"Loaded {count} variable(s) from '{app}' into environment")
        else:
            info(f"No variables to load for '{app}'", badge=True)

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

        if not file_path:
            self._print_error("Please specify a dependency file or use --all to scan directory")
            info("Usage: cortex import <file> [--execute] [--dev]", badge=True)
            info("       cortex import --all [--execute] [--dev]", badge=True)
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
            for err in result.errors:
                self._print_error(err)
            return 1

        if not result.packages and not result.dev_packages:
            info("No packages found in file", badge=True)
            return 0

        # Get install command
        install_cmd = importer.get_install_command(result.ecosystem, file_path)
        if not install_cmd:
            self._print_error(f"Unknown ecosystem: {result.ecosystem.value}")
            return 1

        # Dry run mode (default)
        if not execute:
            status_box(
                "INSTALL PREVIEW",
                {
                    "Ecosystem": result.ecosystem.value,
                    "Command": install_cmd,
                },
            )
            info("Run again with --execute to install", badge=True)
            return 0

        # Execute mode - run the install command
        return self._execute_install(install_cmd, result.ecosystem)

    def _import_all(self, importer: DependencyImporter, execute: bool, include_dev: bool) -> int:
        section("DEPENDENCY SCAN")

        with spinner("Scanning directory for dependency files"):
            results = importer.scan_directory(include_dev=include_dev)

        if not results:
            info("No dependency files found in current directory", badge=True)
            return 0

        rows = []
        # Display all found files
        total_packages = 0
        total_dev_packages = 0

        for file_path, result in results.items():
            filename = os.path.basename(file_path)
            if result.errors:
                rows.append([filename, "ERROR", result.errors[0]])
            else:
                pkg_count = result.prod_count
                dev_count = result.dev_count if include_dev else 0
                total_packages += pkg_count
                total_dev_packages += dev_count
                rows.append(
                    [
                        filename,
                        f"{pkg_count}",
                        f"+{dev_count}" if dev_count > 0 else "—",
                    ]
                )

        data_table(
            columns=[
                {"name": "File", "style": "cyan"},
                {"name": "Packages"},
                {"name": "Dev"},
            ],
            rows=rows,
            title="Detected Dependency Files",
        )

        if total_packages == 0 and total_dev_packages == 0:
            info("No packages found in dependency files", badge=True)
            return 0

        commands = importer.get_install_commands_for_results(results)
        if not commands:
            info("No install commands generated", badge=True)
            return 0

        if not execute:
            data_table(
                columns=[{"name": "Install Command"}],
                rows=[[c["command"]] for c in commands],
                title="Install Commands",
            )
            info("Run with --execute to install all packages", badge=True)
            return 0

        total = total_packages + total_dev_packages
        confirm = input(f"\nInstall all {total} packages? [Y/n]: ")
        if confirm.lower() not in ("", "y", "yes"):
            info("Installation cancelled", badge=True)
            return 0

        return self._execute_multi_install(commands)

    def _display_parse_result(self, result: ParseResult, include_dev: bool) -> None:
        ecosystem_names = {
            PackageEcosystem.PYTHON: "Python",
            PackageEcosystem.NODE: "Node",
            PackageEcosystem.RUBY: "Ruby",
            PackageEcosystem.RUST: "Rust",
            PackageEcosystem.GO: "Go",
        }

        ecosystem_name = ecosystem_names.get(result.ecosystem, "Unknown")

        section("DEPENDENCY PARSE")

        status_box(
            "SUMMARY",
            {
                "Ecosystem": ecosystem_name,
                "Packages": str(result.prod_count),
                "Dev packages": str(result.dev_count if include_dev else 0),
            },
        )

        if result.packages:
            data_table(
                columns=[{"name": "Package"}],
                rows=[
                    [f"{p.name}{f' ({p.version})' if p.version else ''}"]
                    for p in result.packages[:15]
                ],
                title="Packages",
            )

        if include_dev and result.dev_packages:
            data_table(
                columns=[{"name": "Dev Package"}],
                rows=[
                    [f"{p.name}{f' ({p.version})' if p.version else ''}"]
                    for p in result.dev_packages[:10]
                ],
                title="Dev Packages",
            )

        for w in result.warnings:
            warning(w)

    def _execute_install(self, command: str, ecosystem: PackageEcosystem) -> int:
        ecosystem_names = {
            PackageEcosystem.PYTHON: "Python",
            PackageEcosystem.NODE: "Node",
            PackageEcosystem.RUBY: "Ruby",
            PackageEcosystem.RUST: "Rust",
            PackageEcosystem.GO: "Go",
        }

        ecosystem_name = ecosystem_names.get(ecosystem, "")

        section("INSTALLING DEPENDENCIES")

        with progress_bar() as progress:
            task = progress.add_task("Installing", total=1)

            def progress_callback(current, total, step: InstallationStep):
                if step.status == StepStatus.RUNNING:
                    info(f"Step {current}/{total}", badge=True)
                elif step.status == StepStatus.FAILED:
                    error(f"Step {current}/{total} failed")

            coordinator = InstallationCoordinator(
                commands=[command],
                descriptions=[f"Install {ecosystem_name} packages"],
                timeout=600,
                stop_on_error=True,
                progress_callback=progress_callback,
            )

            result = coordinator.execute()
            # Explicitly show commands as they are about to run
            for idx, cmd in enumerate(commands, 1):
                info(f"Step {idx}/{len(commands)}", badge=True)
                console.print(f"    [dim]→ {cmd}[/dim]")


        if result.success:
            summary_box(
                "INSTALL COMPLETE",
                [
                    f"Ecosystem: {ecosystem_name}",
                    f"Duration: {result.total_duration:.2f}s",
                ],
                success=True,
            )
            return 0

        self._print_error("Installation failed")
        if result.error_message:
            console.print(result.error_message, style="red")
        return 1

    def _execute_multi_install(self, commands: list[dict[str, str]]) -> int:
        all_commands = [cmd["command"] for cmd in commands]
        all_descriptions = [cmd["description"] for cmd in commands]

        section("INSTALLING ALL DEPENDENCIES")

        with progress_bar() as progress:
            task = progress.add_task("Installing", total=len(all_commands))

            coordinator = InstallationCoordinator(
                commands=all_commands,
                descriptions=all_descriptions,
                timeout=600,
                stop_on_error=True,
                progress_callback=lambda c, t, s: progress.advance(task, 1),
            )

            result = coordinator.execute()

        if result.success:
            summary_box(
                "ALL DEPENDENCIES INSTALLED",
                [f"Steps executed: {len(all_commands)}"],
                success=True,
            )
            return 0

        if result.failed_step is not None:
            self._print_error(f"Installation failed at step {result.failed_step + 1}")
        else:
            self._print_error("Installation failed")

        if result.error_message:
            console.print(result.error_message, style="red")
        return 1

    # --------------------------
def show_rich_help():
    """Display a beautifully formatted help table using the Rich library.

    This function outputs the primary command menu, providing descriptions
    for all core Cortex utilities including installation, environment
    management, and container tools.
    """
    show_banner(show_version=True)
    console.print()

    section("CORTEX CLI")

    status_box(
        "OVERVIEW",
        {
            "Description": "AI-powered package manager for Linux",
            "Usage": "Tell Cortex what you want to install",
        },
    )

    data_table(
        columns=[
            {"name": "Command", "style": "green"},
            {"name": "Description"},
        ],
        rows=[
            ["ask <question>", "Ask questions about your system"],
            ["demo", "See Cortex in action"],
            ["wizard", "Configure API key"],
            ["status", "System status and health checks"],
            ["install <pkg>", "Install software"],
            ["import <file>", "Import dependencies from package files"],
            ["history", "View installation history"],
            ["rollback <id>", "Undo an installation"],
            ["notify", "Manage desktop notifications"],
            ["env", "Manage environment variables"],
            ["cache stats", "Show LLM cache statistics"],
            ["stack <name>", "Install a predefined stack"],
            ["sandbox <cmd>", "Test packages in a Docker sandbox"],

        ],
        title="AVAILABLE COMMANDS",
    )

    info("Learn more: https://cortexlinux.com/", badge=True)


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
        warning(f"Network auto-config failed: {e}")

    parser = argparse.ArgumentParser(
        prog="cortex",
        description="AI-powered Linux command interpreter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global flags
    parser.add_argument("--version", "-V", action="version", version=f"cortex {VERSION}")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("demo", help="See Cortex in action")
    subparsers.add_parser("wizard", help="Configure API key interactively")
    
    subparsers.add_parser("status", help="Show comprehensive system status and health checks")

    ask_parser = subparsers.add_parser("ask", help="Ask a question about your system")
    ask_parser.add_argument("question", type=str, help="Natural language question")

    # Install command
    install_parser = subparsers.add_parser("install", help="Install software")
    install_parser.add_argument("software", type=str, help="Software to install")
    install_parser.add_argument("--execute", action="store_true", help="Execute commands")
    install_parser.add_argument("--dry-run", action="store_true", help="Show commands only")
    install_parser.add_argument("--parallel", action="store_true", help="Enable parallel execution")

    # Import command - import dependencies from package manager files
    import_parser = subparsers.add_parser("import", help="Import dependencies from package files")
    import_parser.add_argument("file", nargs="?")
    import_parser.add_argument("--all", "-a", action="store_true")
    import_parser.add_argument("--execute", "-e", action="store_true")
    import_parser.add_argument("--dev", "-d", action="store_true")

    # History command
    history_parser = subparsers.add_parser("history", help="View history")
    history_parser.add_argument("--limit", type=int, default=20)
    history_parser.add_argument("--status", choices=["success", "failed"])
    history_parser.add_argument("show_id", nargs="?")

    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback installation")
    rollback_parser.add_argument("id")
    rollback_parser.add_argument("--dry-run", action="store_true")

    # --- New Notify Command ---
    notify_parser = subparsers.add_parser("notify", help="Manage desktop notifications")
    notify_subs = notify_parser.add_subparsers(dest="notify_action")

    notify_subs.add_parser("config")
    notify_subs.add_parser("enable")
    notify_subs.add_parser("disable")

    dnd_parser = notify_subs.add_parser("dnd")
    dnd_parser.add_argument("start")
    dnd_parser.add_argument("end")

    send_parser = notify_subs.add_parser("send")
    send_parser.add_argument("message")
    send_parser.add_argument("--title", default="Cortex Notification")
    send_parser.add_argument("--level", choices=["low", "normal", "critical"], default="normal")
    send_parser.add_argument("--actions", nargs="*")

    # Stack command
    stack_parser = subparsers.add_parser("stack", help="Manage pre-built package stacks")
    stack_parser.add_argument("name", nargs="?")
    stack_group = stack_parser.add_mutually_exclusive_group()
    stack_group.add_argument("--list", "-l", action="store_true")
    stack_group.add_argument("--describe", "-d")
    stack_parser.add_argument("--dry-run", action="store_true")

    # Cache commands
    cache_parser = subparsers.add_parser("cache", help="Cache operations")
    cache_subs = cache_parser.add_subparsers(dest="cache_action")
    cache_subs.add_parser("stats")


    # --- Sandbox Commands (Docker-based package testing) ---
    sandbox_parser = subparsers.add_parser("sandbox", help="Test packages in Docker sandbox")
    sandbox_subs = sandbox_parser.add_subparsers(dest="sandbox_action")

    sandbox_create_parser = sandbox_subs.add_parser("create")
    sandbox_create_parser.add_argument("name")
    sandbox_create_parser.add_argument("--image", default="ubuntu:22.04")

    # sandbox install <name> <package>
    sandbox_install_parser = sandbox_subs.add_parser("install")
    sandbox_install_parser.add_argument("name")
    sandbox_install_parser.add_argument("package")

    # sandbox test <name> [package]
    sandbox_test_parser = sandbox_subs.add_parser("test")
    sandbox_test_parser.add_argument("name")
    sandbox_test_parser.add_argument("package", nargs="?")

    # sandbox promote <name> <package> [--dry-run]
    sandbox_promote_parser = sandbox_subs.add_parser("promote")
    sandbox_promote_parser.add_argument("name")
    sandbox_promote_parser.add_argument("package")
    sandbox_promote_parser.add_argument("--dry-run", action="store_true")
    sandbox_promote_parser.add_argument("-y", "--yes", action="store_true")


    # sandbox cleanup <name> [--force]
    sandbox_cleanup_parser = sandbox_subs.add_parser("cleanup")
    sandbox_cleanup_parser.add_argument("name")
    sandbox_cleanup_parser.add_argument("-f", "--force", action="store_true")


    # sandbox list
    sandbox_subs.add_parser("list")


    # sandbox exec <name> <command...>
    sandbox_exec_parser = sandbox_subs.add_parser("exec")
    sandbox_exec_parser.add_argument("name")
    sandbox_exec_parser.add_argument("cmd",  nargs="+") #maybe needs update here


    # --- Environment Variable Management Commands ---
    env_parser = subparsers.add_parser("env", help="Manage environment variables")
    env_subs = env_parser.add_subparsers(dest="env_action")

    # env set <app> <KEY> <VALUE> [--encrypt] [--type TYPE] [--description DESC]
    env_set_parser = env_subs.add_parser("set")
    env_set_parser.add_argument("app")
    env_set_parser.add_argument("key")
    env_set_parser.add_argument("value")
    env_set_parser.add_argument("--encrypt", "-e", action="store_true")
    env_set_parser.add_argument(
        "--type",
        "-t",
        choices=["string", "url", "port", "boolean", "integer", "path"],
        default="string",
    )
    env_set_parser.add_argument("--description", "-d")

    # env get <app> <KEY> [--decrypt]
    env_get_parser = env_subs.add_parser("get")
    env_get_parser.add_argument("app")
    env_get_parser.add_argument("key")
    env_get_parser.add_argument("--decrypt", action="store_true")

    # env list <app> [--decrypt]
    env_list_parser = env_subs.add_parser("list")
    env_list_parser.add_argument("app")
    env_list_parser.add_argument("--decrypt", action="store_true")

    # env delete <app> <KEY>
    env_delete_parser = env_subs.add_parser("delete")
    env_delete_parser.add_argument("app")
    env_delete_parser.add_argument("key")

    # env export <app> [--include-encrypted] [--output FILE]
    env_export_parser = env_subs.add_parser("export")
    env_export_parser.add_argument("app")
    env_export_parser.add_argument("--include-encrypted", action="store_true")
    env_export_parser.add_argument("--output", "-o")

    # env import <app> [file] [--encrypt-keys KEYS]
    env_import_parser = env_subs.add_parser("import")
    env_import_parser.add_argument("app")
    env_import_parser.add_argument("file", nargs="?")
    env_import_parser.add_argument("--encrypt-keys")

    # env clear <app> [--force]
    env_clear_parser = env_subs.add_parser("clear")
    env_clear_parser.add_argument("app")
    env_clear_parser.add_argument("--force", "-f", action="store_true")

    # env apps - list all apps with environments
    env_subs.add_parser("apps")

    # env load <app> - load into os.environ
    env_load_parser = env_subs.add_parser("load")
    env_load_parser.add_argument("app")

    # env template subcommands
    env_template_parser = env_subs.add_parser("template")
    env_template_subs = env_template_parser.add_subparsers(dest="template_action")

    # env template list
    env_template_subs.add_parser("list")
    # env template show <name>
    env_template_show_parser = env_template_subs.add_parser("show")
    env_template_show_parser.add_argument("template_name")

    # env template apply <template> <app> [KEY=VALUE...] [--encrypt-keys KEYS]
    # need to update things here if needed 
    env_template_apply_parser = env_template_subs.add_parser("apply")
    env_template_apply_parser.add_argument("template_name")
    env_template_apply_parser.add_argument("app")
    env_template_apply_parser.add_argument("values", nargs="*")
    env_template_apply_parser.add_argument("--encrypt-keys") 

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
        console.print()
        error("Operation cancelled")
        return 130
    except (ValueError, ImportError, OSError) as e:
        console.print()
        error(f"Error: {e}")
        return 1
    except Exception as e:
        console.print()
        error(f"Unexpected error: {e}")
        if "--verbose" in sys.argv or "-v" in sys.argv:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
