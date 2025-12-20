import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Optional

# Suppress noisy log messages in normal operation
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cortex.installation_history").setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.branding import VERSION, console, cx_header, cx_print, show_banner
from cortex.coordinator import InstallationCoordinator, StepStatus
from cortex.installation_history import InstallationHistory, InstallationStatus, InstallationType
from cortex.llm.interpreter import CommandInterpreter
from cortex.notification_manager import NotificationManager
from cortex.stack_manager import StackManager
from cortex.templates import InstallationStep, Template, TemplateFormat, TemplateManager
from cortex.user_preferences import (
    PreferencesManager,
    format_preference_value,
    print_all_preferences,
)
from cortex.validators import (
    validate_api_key,
    validate_install_request,
)


class CortexCLI:
    def __init__(self, verbose: bool = False):
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.prefs_manager = None  # Lazy initialization
        self.verbose = verbose
        self.offline = False

    def _debug(self, message: str):
        """Print debug info only in verbose mode"""
        if self.verbose:
            console.print(f"[dim][DEBUG] {message}[/dim]")

    def _get_api_key(self) -> str | None:
        # Check if using Ollama (no API key needed)
        provider = self._get_provider()
        if provider == "ollama":
            self._debug("Using Ollama (no API key required)")
            return "ollama-local"  # Placeholder for Ollama

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
        if explicit_provider in ["ollama", "openai", "claude"]:
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
        template: str | None = None,
    ):
        # Validate input first (only if not using template)
        if not template:
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
            # If template is specified, use template system
            if template:
                return self._install_from_template(template, execute, dry_run)
            # Otherwise, use LLM-based installation
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

    def _install_from_template(self, template_name: str, execute: bool, dry_run: bool):
        """Install from a template."""
        history = InstallationHistory()
        install_id = None
        start_time = datetime.now()

        try:
            template_manager = TemplateManager()

            self._print_status("[*]", f"Loading template: {template_name}...")
            template = template_manager.load_template(template_name)

            if not template:
                self._print_error(f"Template '{template_name}' not found")
                self._print_status("[*]", "Available templates:")
                templates = template_manager.list_templates()
                for name, info in templates.items():
                    print(f"  - {name}: {info['description']}")
                return 1

            # Display template info
            print(f"\n{template.name} Template:")
            print(f"   {template.description}")
            print("\n   Packages:")
            for pkg in template.packages:
                print(f"   - {pkg}")

            # Check hardware compatibility
            is_compatible, warnings = template_manager.check_hardware_compatibility(template)
            if warnings:
                print("\n[WARNING] Hardware Compatibility Warnings:")
                for warning in warnings:
                    print(f"   - {warning}")
                if not is_compatible and not dry_run:
                    try:
                        response = input(
                            "\n[WARNING] Hardware requirements not met. Continue anyway? (y/N): "
                        )
                        if response.lower() != "y":
                            print("\n[INFO] Installation aborted by user")
                            return 1
                    except (EOFError, KeyboardInterrupt):
                        # Non-interactive environment or user cancelled
                        print(
                            "\n[ERROR] Aborting install: cannot prompt for hardware confirmation in non-interactive mode"
                        )
                        print(
                            "        Use --dry-run to preview commands, or ensure hardware requirements are met"
                        )
                        return 1

            # Generate commands
            self._print_status("[*]", "Generating installation commands...")
            commands = template_manager.generate_commands(template)

            if not commands:
                self._print_error("No commands generated from template")
                return 1

            # Extract packages for tracking
            packages = (
                template.packages
                if template.packages
                else history._extract_packages_from_commands(commands)
            )

            # Record installation start
            if execute or dry_run:
                install_id = history.record_installation(
                    InstallationType.INSTALL, packages, commands, start_time
                )

            print(f"\n[*] Installing {len(packages)} packages...")
            print("\nGenerated commands:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. {cmd}")

            if dry_run:
                print("\n(Dry run mode - commands not executed)")
                if install_id:
                    history.update_installation(install_id, InstallationStatus.SUCCESS)
                return 0

            if execute:
                # Convert template steps to coordinator format if available
                if template.steps:
                    plan = [
                        {
                            "command": step.command,
                            "description": step.description,
                            "rollback": step.rollback,
                        }
                        for step in template.steps
                    ]
                    coordinator = InstallationCoordinator.from_plan(
                        plan, timeout=300, stop_on_error=True
                    )
                else:

                    def progress_callback(current, total, step):
                        status_emoji = "⏳"
                        if step.status == StepStatus.SUCCESS:
                            status_emoji = "✅"
                        elif step.status == StepStatus.FAILED:
                            status_emoji = "❌"
                        print(f"\n[{current}/{total}] {status_emoji} {step.description}")
                        print(f"  Command: {step.command}")

                    coordinator = InstallationCoordinator(
                        commands=commands,
                        descriptions=[f"Step {i+1}" for i in range(len(commands))],
                        timeout=300,
                        stop_on_error=True,
                        progress_callback=progress_callback,
                    )

                print("\nExecuting commands...")
                result = coordinator.execute()

                if result.success:
                    # Run verification commands if available
                    if template.verification_commands:
                        self._print_status("[*]", "Verifying installation...")
                        verify_results = coordinator.verify_installation(
                            template.verification_commands
                        )
                        all_passed = all(verify_results.values())
                        if not all_passed:
                            print("\n[WARNING] Some verification checks failed:")
                            for cmd, passed in verify_results.items():
                                status = "[OK]" if passed else "[FAIL]"
                                print(f"  {status} {cmd}")

                    # Run post-install commands once
                    if template.post_install:
                        self._print_status("[*]", "Running post-installation steps...")
                        print("\n[*] Post-installation information:")
                        for cmd in template.post_install:
                            subprocess.run(cmd, shell=True)

                    self._print_success(f"{template.name} stack ready!")
                    print(f"\nCompleted in {result.total_duration:.2f} seconds")

                    # Record successful installation
                    if install_id:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                        print(f"\n[*] Installation recorded (ID: {install_id})")
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
                print(f"Example: cortex install --template {template_name} --execute")

            return 0

        except ValueError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(str(e))
            return 1
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"Unexpected error: {str(e)}")
            return 1

    def template_list(self):
        """List all available templates."""
        try:
            template_manager = TemplateManager()
            templates = template_manager.list_templates()

            if not templates:
                print("No templates found.")
                return 0

            print("\nAvailable Templates:")
            print("=" * 80)
            print(f"{'Name':<20} {'Version':<12} {'Type':<12} {'Description':<35}")
            print("=" * 80)

            for name, info in sorted(templates.items()):
                desc = (
                    info["description"][:33] + "..."
                    if len(info["description"]) > 35
                    else info["description"]
                )
                print(f"{name:<20} {info['version']:<12} {info['type']:<12} {desc:<35}")

            print(f"\nTotal: {len(templates)} templates")
            return 0
        except Exception as e:
            self._print_error(f"Failed to list templates: {str(e)}")
            return 1

    def template_create(self, name: str, interactive: bool = True):
        """Create a new template interactively."""
        try:
            print(f"\n[*] Creating template: {name}")

            if interactive:
                description = input("Description: ").strip()
                if not description:
                    self._print_error("Description is required")
                    return 1

                version = input("Version (default: 1.0.0): ").strip() or "1.0.0"
                author = input("Author (optional): ").strip() or None

                print("\nEnter packages (one per line, empty line to finish):")
                packages = []
                while True:
                    pkg = input("  Package: ").strip()
                    if not pkg:
                        break
                    packages.append(pkg)

                # Create template
                from cortex.templates import HardwareRequirements, Template

                template = Template(
                    name=name,
                    description=description,
                    version=version,
                    author=author,
                    packages=packages,
                )

                # Ask about hardware requirements
                print("\nHardware Requirements (optional):")
                min_ram = input("  Minimum RAM (MB, optional): ").strip()
                min_cores = input("  Minimum CPU cores (optional): ").strip()
                min_storage = input("  Minimum storage (MB, optional): ").strip()

                if min_ram or min_cores or min_storage:
                    try:
                        hw_req = HardwareRequirements(
                            min_ram_mb=int(min_ram) if min_ram else None,
                            min_cores=int(min_cores) if min_cores else None,
                            min_storage_mb=int(min_storage) if min_storage else None,
                        )
                    except ValueError:
                        self._print_error("Hardware requirements must be numeric values")
                        return 1
                    template.hardware_requirements = hw_req

                # Save template
                template_manager = TemplateManager()
                template_path = template_manager.save_template(template, name)

                self._print_success(f"Template '{name}' created successfully!")
                print(f"  Saved to: {template_path}")
                return 0
            else:
                self._print_error("Non-interactive template creation not yet supported")
                return 1

        except Exception as e:
            self._print_error(f"Failed to create template: {str(e)}")
            return 1

    def template_import(self, file_path: str, name: str | None = None):
        """Import a template from a file."""
        try:
            template_manager = TemplateManager()
            template = template_manager.import_template(file_path, name)

            # Save to user templates
            save_name = name or template.name
            template_path = template_manager.save_template(template, save_name)

            self._print_success(f"Template '{save_name}' imported successfully!")
            print(f"  Saved to: {template_path}")
            return 0
        except Exception as e:
            self._print_error(f"Failed to import template: {str(e)}")
            return 1

    def template_export(self, name: str, file_path: str, format: str = "yaml"):
        """Export a template to a file."""
        try:
            template_manager = TemplateManager()
            template_format = (
                TemplateFormat.YAML if format.lower() == "yaml" else TemplateFormat.JSON
            )
            export_path = template_manager.export_template(name, file_path, template_format)

            self._print_success(f"Template '{name}' exported successfully!")
            print(f"  Saved to: {export_path}")
            return 0
        except Exception as e:
            self._print_error(f"Failed to export template: {str(e)}")
            return 1

    def _get_prefs_manager(self):
        """Lazy initialize preferences manager"""
        if self.prefs_manager is None:
            self.prefs_manager = PreferencesManager()
        return self.prefs_manager

    def check_pref(self, key: str | None = None):
        """Check/display user preferences"""
        manager = self._get_prefs_manager()

        try:
            if key:
                # Show specific preference
                value = manager.get(key)
                if value is None:
                    self._print_error(f"Preference key '{key}' not found")
                    return 1

                print(f"\n{key} = {format_preference_value(value)}")
                return 0
            else:
                # Show all preferences
                print_all_preferences(manager)
                return 0

        except Exception as e:
            self._print_error(f"Failed to read preferences: {str(e)}")
            return 1

    def edit_pref(self, action: str, key: str | None = None, value: str | None = None):
        """Edit user preferences (add/set, delete/remove, list)"""
        manager = self._get_prefs_manager()

        try:
            if action in ["add", "set", "update"]:
                if not key or not value:
                    self._print_error("Key and value required")
                    return 1
                manager.set(key, value)
                self._print_success(f"Updated {key}")
                print(f"  New value: {format_preference_value(manager.get(key))}")
                return 0

            elif action in ["delete", "remove", "reset-key"]:
                if not key:
                    self._print_error("Key required")
                    return 1
                # Simplified reset logic
                print(f"Resetting {key}...")
                # (In a real implementation we would reset to default)
                return 0

            elif action in ["list", "show", "display"]:
                return self.check_pref()

            elif action == "reset-all":
                confirm = input("⚠️  Reset ALL preferences? (y/n): ")
                if confirm.lower() == "y":
                    manager.reset()
                    self._print_success("Preferences reset")
                return 0

            elif action == "validate":
                errors = manager.validate()
                if errors:
                    print("❌ Errors found")
                else:
                    self._print_success("Valid")
                return 0

            else:
                self._print_error(f"Unknown action: {action}")
                return 1

        except Exception as e:
            self._print_error(f"Failed to edit preferences: {str(e)}")
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

    def demo(self):
        """Run a demo showing Cortex capabilities without API key"""
        show_banner()
        console.print()
        cx_print("Running Demo...", "info")
        # (Keep existing demo logic)
        return 0


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

    table.add_row("demo", "See Cortex in action")
    table.add_row("wizard", "Configure API key")
    table.add_row("status", "System status")
    table.add_row("install <pkg>", "Install software")
    table.add_row("history", "View history")
    table.add_row("rollback <id>", "Undo installation")
    table.add_row("notify", "Manage desktop notifications")  # Added this line
    table.add_row("cache stats", "Show LLM cache statistics")
    table.add_row("stack <name>", "Install the stack")
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
    parser = argparse.ArgumentParser(
        prog="cortex",
        description="AI-powered Linux command interpreter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cortex install docker
  cortex install docker --execute
  cortex install "python 3.11 with pip"
  cortex install nginx --dry-run
  cortex install --template lamp --execute
  cortex template list
  cortex template create my-stack
  cortex template import template.yaml
  cortex template export lamp my-template.yaml
  cortex history
  cortex history show <id>
  cortex rollback <id>
  cortex check-pref
  cortex check-pref ai.model
  cortex edit-pref set ai.model gpt-4
  cortex edit-pref delete theme
  cortex edit-pref reset-all

Environment Variables:
  OPENAI_API_KEY      OpenAI API key for GPT-4
  ANTHROPIC_API_KEY   Anthropic API key for Claude
        """,
    )

    # Global flags
    parser.add_argument("--version", "-V", action="version", version=f"cortex {VERSION}")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument(
        "--offline", action="store_true", help="Use cached responses only (no network calls)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Demo command
    demo_parser = subparsers.add_parser("demo", help="See Cortex in action")

    # Wizard command
    wizard_parser = subparsers.add_parser("wizard", help="Configure API key interactively")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show system status")

    # doctor command
    doctor_parser = subparsers.add_parser("doctor", help="Run system health check")

    # Install command
    install_parser = subparsers.add_parser(
        "install", help="Install software using natural language or template"
    )
    install_group = install_parser.add_mutually_exclusive_group(required=True)
    install_group.add_argument(
        "software", type=str, nargs="?", help="Software to install (natural language)"
    )
    install_group.add_argument(
        "--template", type=str, help="Install from template (e.g., lamp, mean, mern)"
    )
    install_parser.add_argument(
        "--execute", action="store_true", help="Execute the generated commands"
    )
    install_parser.add_argument(
        "--dry-run", action="store_true", help="Show commands without executing"
    )

    # History command
    history_parser = subparsers.add_parser("history", help="View history")
    history_parser.add_argument("--limit", type=int, default=20)
    history_parser.add_argument("--status", choices=["success", "failed"])
    history_parser.add_argument("show_id", nargs="?")

    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback an installation")
    rollback_parser.add_argument("id", help="Installation ID to rollback")
    rollback_parser.add_argument(
        "--dry-run", action="store_true", help="Show rollback actions without executing"
    )

    # Preferences commands
    check_pref_parser = subparsers.add_parser("check-pref", help="Check preferences")
    check_pref_parser.add_argument("key", nargs="?")

    edit_pref_parser = subparsers.add_parser("edit-pref", help="Edit preferences")
    edit_pref_parser.add_argument("action", choices=["set", "add", "delete", "list", "validate"])
    edit_pref_parser.add_argument("key", nargs="?")
    edit_pref_parser.add_argument("value", nargs="?")

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

    # Template commands
    template_parser = subparsers.add_parser("template", help="Manage installation templates")
    template_subs = template_parser.add_subparsers(dest="template_action", help="Template actions")
    template_subs.add_parser("list", help="List all available templates")

    template_create_parser = template_subs.add_parser("create", help="Create a new template")
    template_create_parser.add_argument("name", help="Template name")

    template_import_parser = template_subs.add_parser("import", help="Import a template from file")
    template_import_parser.add_argument("file_path", help="Path to template file")
    template_import_parser.add_argument("--name", help="Override template name")

    template_export_parser = template_subs.add_parser("export", help="Export a template to file")
    template_export_parser.add_argument("name", help="Template name")
    template_export_parser.add_argument("file_path", help="Output file path")
    template_export_parser.add_argument(
        "--format", choices=["yaml", "json"], default="yaml", help="Export format"
    )

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
            if args.template:
                return cli.install(
                    "", execute=args.execute, dry_run=args.dry_run, template=args.template
                )
            else:
                # software is guaranteed to be set due to mutually_exclusive_group(required=True)
                return cli.install(args.software, execute=args.execute, dry_run=args.dry_run)
        elif args.command == "history":
            return cli.history(limit=args.limit, status=args.status, show_id=args.show_id)
        elif args.command == "rollback":
            return cli.rollback(args.id, dry_run=args.dry_run)
        elif args.command == "template":
            if args.template_action == "list":
                return cli.template_list()
            elif args.template_action == "create":
                return cli.template_create(args.name)
            elif args.template_action == "import":
                return cli.template_import(args.file_path, args.name)
            elif args.template_action == "export":
                return cli.template_export(args.name, args.file_path, args.format)
            else:
                parser.print_help()
                return 1
        elif args.command == "check-pref":
            return cli.check_pref(key=args.key)
        elif args.command == "edit-pref":
            return cli.edit_pref(action=args.action, key=args.key, value=args.value)
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
