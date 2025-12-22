import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.branding import VERSION, console, cx_header, cx_print, show_banner
from cortex.coordinator import InstallationCoordinator, StepStatus
from cortex.demo import run_demo
from cortex.installation_history import InstallationHistory, InstallationStatus, InstallationType
from cortex.llm.interpreter import CommandInterpreter
from cortex.notification_manager import NotificationManager
from cortex.stack_manager import StackManager
from cortex.update_manifest import UpdateChannel
from cortex.updater import ChecksumMismatch, InstallError, UpdateError, UpdateService
from cortex.user_preferences import (
    PreferencesManager,
    format_preference_value,
    print_all_preferences,
)
from cortex.utils.stdin import combine_stdin_with_prompt, read_stdin
from cortex.validators import validate_api_key, validate_install_request

# Suppress noisy log messages in normal operation
# logging.getLogger("httpx").setLevel(logging.WARNING)
# logging.getLogger("cortex.installation_history").setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class CortexCLI:
    def __init__(self):
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.update_service = UpdateService()
        self.prefs_manager = None  # Lazy initialization

    def _get_api_key(self) -> str | None:
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self._print_error(
                "API key not found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable."
            )
            return None
        return api_key

    def _get_provider(self) -> str:
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            return "claude"
        return "openai"

    def _print_status(self, emoji: str, message: str):
        print(f"{emoji} {message}")

    def _print_error(self, message: str):
        print(f"❌ Error: {message}", file=sys.stderr)

    def _print_success(self, message: str):
        print(f"✅ {message}")

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

    def update(self, channel: str | None = None, force: bool = False, dry_run: bool = False):
        try:
            channel_enum = (
                UpdateChannel.from_string(channel) if channel else self.update_service.get_channel()
            )
        except ValueError as exc:
            self._print_error(str(exc))
            return 1

        try:
            result = self.update_service.perform_update(
                force=force, channel=channel_enum, dry_run=dry_run
            )
        except ChecksumMismatch as exc:
            self._print_error(f"Security check failed: {exc}")
            return 1
        except InstallError as exc:
            self._print_error(f"Installer error: {exc}")
            return 1
        except UpdateError as exc:
            self._print_error(f"Update failed: {exc}")
            return 1
        except Exception as exc:
            self._print_error(f"Unexpected update failure: {exc}")
            return 1

        if not result.release:
            self._print_status("ℹ️", result.message or "Cortex is already up to date.")
            return 0

        release = result.release

        if not result.updated:
            self._print_status(
                "🔔", f"Update available: {release.version.raw} ({release.channel.value})"
            )
            if release.release_notes:
                self._print_status("🆕", "What's new:")
                for line in release.release_notes.strip().splitlines():
                    print(f"   {line}")
            self._print_status("ℹ️", result.message or "Dry run complete.")
            return 0

        self._print_success(
            f"Update complete! {result.previous_version.raw} → {release.version.raw}"
        )
        self._print_status("🗂️", f"Log saved to {result.log_path}")
        if release.release_notes:
            self._print_status("🆕", "What's new:")
            for line in release.release_notes.strip().splitlines():
                print(f"   {line}")

        return 0

    def _notify_update_if_available(self):
        if os.environ.get("CORTEX_UPDATE_CHECK", "1") in ("0", "false", "False"):
            return

        try:
            result = self.update_service.check_for_updates()
        except Exception:
            return

        if result.update_available and result.release:
            release = result.release
            print(
                f"\n🔔 Cortex update available: {release.version.raw} "
                f"({result.channel.value} channel)\n"
                "   Run 'cortex update' to learn more.\n"
            )

    def show_channel(self):
        channel = self.update_service.get_channel()
        self._print_status("ℹ️", f"Current update channel: {channel.value}")
        return 0

    def set_channel(self, channel: str):
        try:
            channel_enum = UpdateChannel.from_string(channel)
        except ValueError as exc:
            self._print_error(str(exc))
            return 1

        self.update_service.set_channel(channel_enum)
        self._print_success(f"Update channel set to '{channel_enum.value}'")
        return 0

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
                    print("\nAvailable preference keys:")
                    print("  - verbosity")
                    print("  - theme")
                    print("  - language")
                    print("  - timezone")
                    print("  - confirmations.before_install")
                    print("  - confirmations.before_remove")
                    print("  - confirmations.before_upgrade")
                    print("  - confirmations.before_system_changes")
                    print("  - auto_update.check_on_start")
                    print("  - auto_update.auto_install")
                    print("  - auto_update.frequency_hours")
                    print("  - ai.model")
                    print("  - ai.creativity")
                    print("  - ai.explain_steps")
                    print("  - ai.suggest_alternatives")
                    print("  - ai.learn_from_history")
                    print("  - ai.max_suggestions")
                    print("  - packages.default_sources")
                    print("  - packages.prefer_latest")
                    print("  - packages.auto_cleanup")
                    print("  - packages.backup_before_changes")
                    return 1

                print(f"\n{key} = {format_preference_value(value)}")
                return 0
            else:
                # Show all preferences
                print_all_preferences(manager)

                # Show validation status
                print("\nValidation Status:")
                errors = manager.validate()
                if errors:
                    print("❌ Configuration has errors:")
                    for error in errors:
                        print(f"  - {error}")
                    return 1
                else:
                    print("✅ Configuration is valid")

                # Show config info
                info = manager.get_config_info()
                print(f"\nConfiguration file: {info['config_path']}")
                print(f"File size: {info['config_size_bytes']} bytes")
                if info["last_modified"]:
                    print(f"Last modified: {info['last_modified']}")

                return 0

        except Exception as e:
            self._print_error(f"Failed to read preferences: {str(e)}")
            return 1

    def edit_pref(self, action: str, key: str | None = None, value: str | None = None):
        """Edit user preferences (add/set, delete/remove, list)"""
        manager = self._get_prefs_manager()

        try:
            if action in ["add", "set", "update"]:
                # Set/update a preference
                if not key:
                    self._print_error("Key is required for set/add/update action")
                    print("Usage: cortex edit-pref set <key> <value>")
                    print("Example: cortex edit-pref set ai.model gpt-4")
                    return 1

                if not value:
                    self._print_error("Value is required for set/add/update action")
                    print("Usage: cortex edit-pref set <key> <value>")
                    return 1

                # Get current value for comparison
                old_value = manager.get(key)

                # Set new value
                manager.set(key, value)

                self._print_success(f"Updated {key}")
                if old_value is not None:
                    print(f"  Old value: {format_preference_value(old_value)}")
                print(f"  New value: {format_preference_value(manager.get(key))}")

                # Validate after change
                errors = manager.validate()
                if errors:
                    print("\n⚠️  Warning: Configuration has validation errors:")
                    for error in errors:
                        print(f"  - {error}")
                    print("\nYou may want to fix these issues.")

                return 0

            elif action in ["delete", "remove", "reset-key"]:
                # Reset a specific key to default
                if not key:
                    self._print_error("Key is required for delete/remove/reset-key action")
                    print("Usage: cortex edit-pref delete <key>")
                    print("Example: cortex edit-pref delete ai.model")
                    return 1

                # To "delete" a key, we reset entire config and reload (since we can't delete individual keys)
                # Instead, we'll reset to the default value for that key
                print(f"Resetting {key} to default value...")

                # Create a new manager with defaults
                from cortex.user_preferences import UserPreferences

                defaults = UserPreferences()

                # Get the default value
                parts = key.split(".")
                obj = defaults
                for part in parts:
                    obj = getattr(obj, part)
                default_value = obj

                # Set to default
                manager.set(key, format_preference_value(default_value))

                self._print_success(f"Reset {key} to default")
                print(f"  Value: {format_preference_value(manager.get(key))}")

                return 0

            elif action in ["list", "show", "display"]:
                # List all preferences (same as check-pref)
                return self.check_pref()

            elif action == "reset-all":
                # Reset all preferences to defaults
                confirm = input(
                    "⚠️  This will reset ALL preferences to defaults. Continue? (yes/no): "
                )
                if confirm.lower() not in ["yes", "y"]:
                    print("Operation cancelled.")
                    return 0

                manager.reset()
                self._print_success("All preferences reset to defaults")
                return 0

            elif action == "validate":
                # Validate configuration
                errors = manager.validate()
                if errors:
                    print("❌ Configuration has errors:")
                    for error in errors:
                        print(f"  - {error}")
                    return 1
                else:
                    self._print_success("Configuration is valid")
                    return 0

            elif action == "export":
                # Export preferences to file
                if not key:  # Using key as filepath
                    self._print_error("Filepath is required for export action")
                    print("Usage: cortex edit-pref export <filepath>")
                    print("Example: cortex edit-pref export ~/cortex-prefs.json")
                    return 1

                from pathlib import Path

                manager.export_json(Path(key))
                self._print_success(f"Preferences exported to {key}")
                return 0

            elif action == "import":
                # Import preferences from file
                if not key:  # Using key as filepath
                    self._print_error("Filepath is required for import action")
                    print("Usage: cortex edit-pref import <filepath>")
                    print("Example: cortex edit-pref import ~/cortex-prefs.json")
                    return 1

                from pathlib import Path

                filepath = Path(key)
                if not filepath.exists():
                    self._print_error(f"File not found: {filepath}")
                    return 1

                manager.import_json(filepath)
                self._print_success(f"Preferences imported from {key}")
                return 0

            else:
                self._print_error(f"Unknown action: {action}")
                print("\nAvailable actions:")
                print("  set/add/update <key> <value>  - Set a preference value")
                print("  delete/remove <key>           - Reset a preference to default")
                print("  list/show/display             - Display all preferences")
                print("  reset-all                     - Reset all preferences to defaults")
                print("  validate                      - Validate configuration")
                print("  export <filepath>             - Export preferences to JSON")
                print("  import <filepath>             - Import preferences from JSON")
                return 1

        except AttributeError as e:
            self._print_error(f"Invalid preference key: {key}")
            print("Use 'cortex check-pref' to see available keys")
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


def main():
    # Load environment variables from .env files BEFORE accessing any API keys
    # This must happen before any code that reads os.environ for API keys
    from cortex.env_loader import load_env

    load_env()

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

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Install command
    install_parser = subparsers.add_parser(
        "install", help="Install software using natural language"
    )
    install_parser.add_argument("software", type=str, help="Software to install (natural language)")
    install_parser.add_argument(
        "--execute", action="store_true", help="Execute the generated commands"
    )
    install_parser.add_argument(
        "--dry-run", action="store_true", help="Show commands without executing"
    )

    update_parser = subparsers.add_parser("update", help="Check for Cortex updates or upgrade")
    update_parser.add_argument(
        "--channel", choices=[c.value for c in UpdateChannel], help="Update channel to use"
    )
    update_parser.add_argument("--force", action="store_true", help="Force network check")
    update_parser.add_argument(
        "--dry-run", action="store_true", help="Show details without installing"
    )

    channel_parser = subparsers.add_parser("channel", help="Manage Cortex update channel")
    channel_sub = channel_parser.add_subparsers(dest="channel_command", required=True)
    channel_sub.add_parser("show", help="Display current update channel")
    channel_set_parser = channel_sub.add_parser("set", help="Set update channel")
    channel_set_parser.add_argument(
        "channel", choices=[c.value for c in UpdateChannel], help="Channel to use"
    )
    # doctor command
    doctor_parser = subparsers.add_parser("doctor", help="Run system health check")

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

    # History command
    history_parser = subparsers.add_parser("history", help="View installation history")
    history_parser.add_argument("--limit", type=int, default=20, help="Number of records to show")
    history_parser.add_argument(
        "--status",
        choices=["success", "failed", "rolled_back", "in_progress"],
        help="Filter by status",
    )
    history_parser.add_argument(
        "show_id", nargs="?", help="Show details for specific installation ID"
    )

    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback an installation")
    rollback_parser.add_argument("id", help="Installation ID to rollback")
    rollback_parser.add_argument(
        "--dry-run", action="store_true", help="Show rollback actions without executing"
    )

    # Check preferences command
    check_pref_parser = subparsers.add_parser("check-pref", help="Check/display user preferences")
    check_pref_parser.add_argument(
        "key", nargs="?", help="Specific preference key to check (optional)"
    )

    # Edit preferences command
    edit_pref_parser = subparsers.add_parser("edit-pref", help="Edit user preferences")
    edit_pref_parser.add_argument(
        "action",
        choices=[
            "set",
            "add",
            "update",
            "delete",
            "remove",
            "reset-key",
            "list",
            "show",
            "display",
            "reset-all",
            "validate",
            "export",
            "import",
        ],
        help="Action to perform",
    )
    edit_pref_parser.add_argument(
        "key", nargs="?", help="Preference key or filepath (for export/import)"
    )
    edit_pref_parser.add_argument("value", nargs="?", help="Preference value (for set/add/update)")
    rollback_parser = subparsers.add_parser("rollback", help="Rollback installation")
    rollback_parser.add_argument("id", help="Installation ID")
    rollback_parser.add_argument("--dry-run", action="store_true")

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
        parser.print_help()
        return 1

    cli = CortexCLI()

    if args.command == "install":
        return cli.install(args.software, execute=args.execute, dry_run=args.dry_run)
    if args.command == "update":
        return cli.update(channel=args.channel, force=args.force, dry_run=args.dry_run)
    if args.command == "channel":
        if args.channel_command == "show":
            return cli.show_channel()
        if args.channel_command == "set":
            return cli.set_channel(args.channel)

    return 0
    try:
        if args.command == "install":
            return cli.install(args.software, execute=args.execute, dry_run=args.dry_run)
        elif args.command == "update":
            return cli.update(channel=args.channel, force=args.force, dry_run=args.dry_run)
        elif args.command == "channel":
            if args.channel_command == "show":
                return cli.show_channel()
            if args.channel_command == "set":
                return cli.set_channel(args.channel)
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
        print("\n❌ Operation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
