import argparse
import json
import logging
import os
import select
import sys
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from cortex.api_key_detector import auto_detect_api_key, setup_api_key
from cortex.ask import AskHandler
from cortex.branding import VERSION, console, cx_header, cx_print, show_banner
from cortex.coordinator import InstallationCoordinator, InstallationStep, StepStatus
from cortex.demo import run_demo
from cortex.dependency_importer import DependencyImporter, PackageEcosystem, ParseResult
from cortex.env_manager import EnvironmentManager, get_env_manager
from cortex.i18n import SUPPORTED_LANGUAGES, LanguageConfig, get_language, set_language, t
from cortex.installation_history import InstallationHistory, InstallationStatus, InstallationType
from cortex.llm.interpreter import CommandInterpreter
from cortex.network_config import NetworkConfig
from cortex.notification_manager import NotificationManager
from cortex.predictive_prevention import FailurePrediction, PredictiveErrorManager, RiskLevel
from cortex.role_manager import RoleManager
from cortex.stack_manager import StackManager
from cortex.stdin_handler import StdinHandler
from cortex.uninstall_impact import (
    ImpactResult,
    ImpactSeverity,
    ServiceStatus,
    UninstallImpactAnalyzer,
)
from cortex.update_checker import UpdateChannel, should_notify_update
from cortex.updater import Updater, UpdateStatus
from cortex.validators import validate_api_key, validate_install_request
from cortex.version_manager import get_version_string

# CLI Help Constants
HELP_SKIP_CONFIRM = "Skip confirmation prompt"

if TYPE_CHECKING:
    from cortex.daemon_client import DaemonClient, DaemonResponse
    from cortex.shell_env_analyzer import ShellEnvironmentAnalyzer

# Suppress noisy log messages in normal operation
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cortex.installation_history").setLevel(logging.ERROR)


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class CortexCLI:
    RISK_COLORS = {
        RiskLevel.NONE: "green",
        RiskLevel.LOW: "green",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.HIGH: "orange1",
        RiskLevel.CRITICAL: "red",
    }
    # Installation messages
    INSTALL_FAIL_MSG = "Installation failed"

    def __init__(self, verbose: bool = False):
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.verbose = verbose
        self.predict_manager = None

    @property
    def risk_labels(self) -> dict[RiskLevel, str]:
        """
        Localized mapping from RiskLevel enum values to human-readable strings.

        Returns a dictionary mapping each tier (RiskLevel.NONE to CRITICAL)
        to its corresponding localized label via the t() translation helper.
        """
        return {
            RiskLevel.NONE: t("predictive.no_risk"),
            RiskLevel.LOW: t("predictive.low_risk"),
            RiskLevel.MEDIUM: t("predictive.medium_risk"),
            RiskLevel.HIGH: t("predictive.high_risk"),
            RiskLevel.CRITICAL: t("predictive.critical_risk"),
        }

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
                        console.print(
                            "[bold cyan]Reclaim ownership using sudo? (y/n): [/bold cyan]", end=""
                        )
                        response = StdinHandler.get_input()
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
        self._print_error(t("api_key.not_found"))
        cx_print(t("api_key.configure_prompt"), "info")
        cx_print(t("api_key.ollama_hint"), "info")
        return None

    def _get_provider(self) -> str:
        # 1. Check explicit provider override FIRST (highest priority)
        explicit_provider = os.environ.get("CORTEX_PROVIDER", "").lower()
        if explicit_provider in ["ollama", "openai", "claude", "fake"]:
            self._debug(f"Using explicit CORTEX_PROVIDER={explicit_provider}")
            return explicit_provider

        # 2. Use provider from auto-detection (set by _get_api_key)
        detected = getattr(self, "_detected_provider", None)
        if detected == "anthropic":
            return "claude"
        elif detected == "openai":
            return "openai"

        # 3. Check env vars (may have been set by auto-detect)
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "claude"
        elif os.environ.get("OPENAI_API_KEY"):
            return "openai"

        # 4. Fallback to Ollama for offline mode
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
        cx_print(f"{t('ui.error_prefix')}: {message}", "error")

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

    def _ask_ai_and_render(self, question: str) -> int:
        """Invoke AI with question and render response as Markdown."""
        api_key = self._get_api_key()
        if not api_key:
            self._print_error("No API key found. Please configure an API provider.")
            return 1

        provider = self._get_provider()
        try:
            handler = AskHandler(api_key=api_key, provider=provider)
            answer = handler.ask(question)
            console.print(Markdown(answer))
            return 0
        except ImportError as e:
            self._print_error(str(e))
            cx_print("Install required SDK or use CORTEX_PROVIDER=ollama", "info")
            return 1
        except (ValueError, RuntimeError) as e:
            self._print_error(str(e))
            return 1

    def role(self, args: argparse.Namespace) -> int:
        """
        Handles system role detection and manual configuration via AI context sensing.

        This method supports two subcommands:
        - 'detect': Analyzes the system and suggests appropriate roles based on
                    installed binaries, hardware, and activity patterns.
        - 'set': Manually assigns a role slug and provides tailored package recommendations.

        Args:
            args: The parsed command-line arguments containing the role_action
                 and optional role_slug.

        Returns:
            int: Exit code - 0 on success, 1 on error.
        """
        manager = RoleManager()
        action = getattr(args, "role_action", None)

        # Step 1: Ensure a subcommand is provided to maintain a valid return state.
        if not action:
            self._print_error("Please specify a subcommand (detect/set)")
            return 1

        if action == "detect":
            # Retrieve environmental facts including active persona and installation history.
            context = manager.get_system_context()

            # Step 2: Extract the most recent patterns for AI analysis.
            # Python handles list slicing gracefully even if the list has fewer than 10 items.
            patterns = context.get("patterns", [])
            limited_patterns = patterns[-10:]
            patterns_str = (
                "\n".join([f"  • {p}" for p in limited_patterns]) or "  • No patterns sensed"
            )

            signals_str = ", ".join(context.get("binaries", [])) or "none detected"
            gpu_status = (
                "GPU Acceleration available" if context.get("has_gpu") else "Standard CPU only"
            )

            # Generate a unique timestamp for cache-busting and session tracking.
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

            # Construct the architectural analysis prompt for the LLM.
            question = (
                f"### SYSTEM ARCHITECT ANALYSIS [TIME: {timestamp}] ###\n"
                f"ENVIRONMENTAL CONTEXT:\n"
                f"- CURRENTLY SET ROLE: {context.get('active_role')}\n"
                f"- Detected Binaries: [{signals_str}]\n"
                f"- Hardware Acceleration: {gpu_status}\n"
                f"- Installation History: {'Present' if context.get('has_install_history') else 'None'}\n\n"
                f"OPERATIONAL_HISTORY (Technical Intents & Installed Packages):\n{patterns_str}\n\n"
                f"TASK: Acting as a Senior Systems Architect, analyze the existing role and signals. "
                f"Suggest 3-5 professional roles that complement the system.\n\n"
                f"--- STRICT RESPONSE FORMAT ---\n"
                f"YOUR RESPONSE MUST START WITH THE NUMBER '1.' AND CONTAIN ONLY THE LIST. "
                f"DO NOT PROVIDE INTRODUCTIONS. DO NOT PROVIDE REASONING. DO NOT PROVIDE A SUMMARY. "
                f"FAILURE TO COMPLY WILL BREAK THE CLI PARSER.\n\n"
                f"Detected roles:\n"
                f"1."
            )

            cx_print("🧠 AI is sensing system context and activity patterns...", "thinking")
            if self._ask_ai_and_render(question) != 0:
                return 1
            console.print()

            # Record the detection event in the installation history database for audit purposes.
            history = InstallationHistory()
            history.record_installation(
                InstallationType.CONFIG,
                ["system-detection"],
                ["cortex role detect"],
                datetime.now(timezone.utc),
            )

            console.print(
                "\n[dim italic]💡 To install any recommended packages, simply run:[/dim italic]"
            )
            console.print("[bold cyan]    cortex install <package_name>[/bold cyan]\n")
            return 0

        elif action == "set":
            if not args.role_slug:
                self._print_error("Role slug is required for 'set' command.")
                return 1

            role_slug = args.role_slug

            # Step 3: Persist the role and handle both validation and persistence errors.
            try:
                manager.save_role(role_slug)
                history = InstallationHistory()
                history.record_installation(
                    InstallationType.CONFIG,
                    [role_slug],
                    [f"cortex role set {role_slug}"],
                    datetime.now(timezone.utc),
                )
            except ValueError as e:
                self._print_error(f"Invalid role slug: {e}")
                return 1
            except RuntimeError as e:
                self._print_error(f"Failed to persist role: {e}")
                return 1

            cx_print(f"✓ Role set to: [bold cyan]{role_slug}[/bold cyan]", "success")

            context = manager.get_system_context()
            # Generate a unique request ID for cache-busting and tracking purposes.
            req_id = f"{datetime.now().strftime('%H:%M:%S.%f')}-{uuid.uuid4().hex[:4]}"

            cx_print(f"🔍 Fetching tailored AI recommendations for {role_slug}...", "info")

            # Construct the recommendation prompt for the LLM.
            rec_question = (
                f"### ARCHITECTURAL ADVISORY [ID: {req_id}] ###\n"
                f"NEW_TARGET_PERSONA: {role_slug}\n"
                f"OS: {sys.platform} | GPU: {'Enabled' if context.get('has_gpu') else 'None'}\n\n"
                f"TASK: Generate 3-5 unique packages for '{role_slug}' ONLY.\n"
                f"--- PREFERRED RESPONSE FORMAT ---\n"
                f"Please start with '1.' and provide only the list of roles. "
                f"Omit introductions, reasoning, and summaries.\n\n"
                f"💡 Recommended packages for {role_slug}:\n"
                f"  - "
            )

            if self._ask_ai_and_render(rec_question) != 0:
                return 1

            console.print(
                "\n[dim italic]💡 Ready to upgrade? Install any of these using:[/dim italic]"
            )
            console.print("[bold cyan]    cortex install <package_name>[/bold cyan]\n")
            return 0

        else:
            self._print_error("Unknown role command")
        return 1

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
        cx_print(f"\n📦 {t('stack.available')}:\n", "info")
        for stack in stacks:
            pkg_count = len(stack.get("packages", []))
            console.print(f"  [green]{stack.get('id', 'unknown')}[/green]")
            console.print(f"    {stack.get('name', t('stack.unnamed'))}")
            console.print(f"    {stack.get('description', t('stack.no_description'))}")
            console.print(f"    [dim]({pkg_count} packages)[/dim]\n")
        cx_print(t("stack.use_command"), "info")
        return 0

    def _handle_stack_describe(self, manager: StackManager, stack_id: str) -> int:
        """Describe a specific stack."""
        stack = manager.find_stack(stack_id)
        if not stack:
            self._print_error(t("stack.not_found", name=stack_id))
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
                f"💡 {t('stack.gpu_fallback', original=original_name, suggested=suggested_name)}",
                "info",
            )

        stack = manager.find_stack(suggested_name)
        if not stack:
            self._print_error(t("stack.not_found", name=suggested_name))
            return 1

        packages = stack.get("packages", [])
        if not packages:
            self._print_error(t("stack.no_packages", name=suggested_name))
            return 1

        if args.dry_run:
            return self._handle_stack_dry_run(stack, packages)

        return self._handle_stack_real_install(stack, packages)

    def _handle_stack_dry_run(self, stack: dict[str, Any], packages: list[str]) -> int:
        """Preview packages that would be installed without executing."""
        cx_print(f"\n📋 {t('stack.installing', name=stack['name'])}", "info")
        console.print(f"\n{t('stack.dry_run_preview')}:")
        for pkg in packages:
            console.print(f"  • {pkg}")
        console.print(f"\n{t('stack.packages_total', count=len(packages))}")
        cx_print(f"\n{t('stack.dry_run_note')}", "warning")
        return 0

    def _handle_stack_real_install(self, stack: dict[str, Any], packages: list[str]) -> int:
        """Install all packages in the stack."""
        cx_print(f"\n🚀 {t('stack.installing', name=stack['name'])}\n", "success")

        # Batch into a single LLM request
        packages_str = " ".join(packages)
        result = self.install(software=packages_str, execute=True, dry_run=False)

        if result != 0:
            self._print_error(t("stack.failed", name=stack["name"]))
            return 1

        self._print_success(f"\n✅ {t('stack.installed', name=stack['name'])}")
        console.print(t("stack.packages_installed", count=len(packages)))
        return 0

    # --- Sandbox Commands (Docker-based package testing) ---
    def sandbox(self, args: argparse.Namespace) -> int:
        """Handle `cortex sandbox` commands for Docker-based package testing."""
        from cortex.sandbox import (
            DockerNotFoundError,
            DockerSandbox,
            SandboxAlreadyExistsError,
            SandboxNotFoundError,
        )

        action = getattr(args, "sandbox_action", None)

        if not action:
            cx_print(f"\n🐳 {t('sandbox.header')}\n", "info")
            console.print(t("sandbox.usage"))
            console.print(f"\n{t('sandbox.commands_header')}:")
            console.print(f"  create <name>              {t('sandbox.cmd_create')}")
            console.print(f"  install <name> <package>   {t('sandbox.cmd_install')}")
            console.print(f"  test <name> [package]      {t('sandbox.cmd_test')}")
            console.print(f"  promote <name> <package>   {t('sandbox.cmd_promote')}")
            console.print(f"  cleanup <name>             {t('sandbox.cmd_cleanup')}")
            console.print(f"  list                       {t('sandbox.cmd_list')}")
            console.print(f"  exec <name> <cmd...>       {t('sandbox.cmd_exec')}")
            console.print(f"\n{t('sandbox.example_workflow')}:")
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
                response = StdinHandler.get_input()
                if response and response.lower() not in ("y", "yes"):
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

    def _display_prediction_warning(self, prediction: FailurePrediction) -> None:
        """Display formatted prediction warning."""
        color = self.RISK_COLORS.get(prediction.risk_level, "white")
        label = self.risk_labels.get(prediction.risk_level, "Unknown")

        console.print()
        if prediction.risk_level >= RiskLevel.HIGH:
            console.print(f"⚠️  [bold red]{t('predictive.risks_detected')}:[/bold red]")
        else:
            console.print(f"ℹ️  [bold {color}]{t('predictive.risks_detected')}:[/bold {color}]")

        if prediction.reasons:
            console.print(f"\n[bold]{label}:[/bold]")
            for reason in prediction.reasons:
                console.print(f"   - {reason}")

        if prediction.recommendations:
            console.print(f"\n[bold]{t('predictive.recommendation')}:[/bold]")
            for i, rec in enumerate(prediction.recommendations, 1):
                console.print(f"   {i}. {rec}")

        if prediction.predicted_errors:
            console.print(f"\n[bold]{t('predictive.predicted_errors')}:[/bold]")
            for err in prediction.predicted_errors:
                msg = f"{err[:100]}..." if len(err) > 100 else err
                console.print(f"   ! [dim]{msg}[/dim]")

    def _confirm_risky_operation(self, prediction: FailurePrediction) -> bool:
        """Prompt user for confirmation of a risky operation."""
        if prediction.risk_level == RiskLevel.HIGH or prediction.risk_level == RiskLevel.CRITICAL:
            cx_print(f"\n{t('predictive.high_risk_warning')}", "warning")

        console.print(f"\n{t('predictive.continue_anyway')} [y/N]: ", end="", markup=False)
        try:
            response = StdinHandler.get_input().lower()
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return False

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
            # Render as markdown for proper formatting in terminal
            console.print(Markdown(answer))
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

    def _ask_with_session_key(self, question: str, api_key: str, provider: str) -> int:
        """Answer a question using provided session API key without re-prompting.

        This wrapper is used by continuous voice mode to avoid re-calling _get_api_key().
        """
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

    def _install_with_session_key(
        self,
        software: str,
        api_key: str,
        provider: str,
        execute: bool = False,
        dry_run: bool = False,
    ) -> int:
        """Install software using provided session API key without re-prompting.

        This wrapper is used by continuous voice mode to avoid re-calling _get_api_key().
        """
        history = InstallationHistory()
        install_id = None
        start_time = datetime.now()

        # Validate input first
        is_valid, error = validate_install_request(software)
        if not is_valid:
            self._print_error(error)
            return 1

        software = self._normalize_software_name(software)
        self._debug(f"Using provider: {provider}")
        self._debug("Using session API key: <REDACTED>")

        try:
            self._print_status("🧠", "Understanding request...")
            interpreter = CommandInterpreter(api_key=api_key, provider=provider)
            self._print_status("📦", "Planning installation...")

            for _ in range(10):
                self._animate_spinner("Analyzing system requirements...")
            self._clear_line()

            commands = interpreter.parse(f"install {software}")

            if not commands:
                self._print_error(t("install.no_commands"))
                return 1

            packages = history._extract_packages_from_commands(commands)

            if execute or dry_run:
                install_id = history.record_installation(
                    InstallationType.INSTALL, packages, commands, start_time
                )

            self._print_status("⚙️", f"Installing {software}...")
            print("\nGenerated commands:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. {cmd}")

            if dry_run:
                print(f"\n({t('install.dry_run_message')})")
                if install_id:
                    history.update_installation(install_id, InstallationStatus.SUCCESS)
                return 0

            if execute:
                print(f"\n{t('install.executing')}")
                coordinator = InstallationCoordinator(commands=commands)
                result = coordinator.execute()

                if result.success:
                    if install_id:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                    return 0
                else:
                    error_msg = result.message or "Installation failed"
                    if install_id:
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                    self._print_error(error_msg)
                    return 1
            else:
                # Neither dry_run nor execute - just show commands
                return 0

        except Exception as e:
            error_msg = str(e)
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, error_msg)
            self._print_error(error_msg)
            return 1

    def voice(self, continuous: bool = False, model: str | None = None) -> int:
        """Handle voice input mode.

        Args:
            continuous: If True, stay in voice mode until Ctrl+C.
                       If False, record single input and exit.
            model: Whisper model name (e.g., 'base.en', 'small.en').
                  If None, uses CORTEX_WHISPER_MODEL env var or 'base.en'.
        """
        import queue
        import threading

        try:
            from cortex.voice import (
                MicrophoneNotFoundError,
                ModelNotFoundError,
                VoiceInputError,
                VoiceInputHandler,
            )
        except ImportError:
            self._print_error("Voice dependencies not installed.")
            cx_print("Install with: pip install cortex-linux[voice]", "info")
            return 1

        api_key = self._get_api_key()
        if not api_key:
            return 1

        # Capture provider once for session
        provider = self._get_provider()
        self._debug(f"Session using provider: {provider}")

        # Display model information if specified
        if model:
            model_info = {
                "tiny.en": "(39 MB, fastest, good for clear speech)",
                "base.en": "(140 MB, balanced speed/accuracy)",
                "small.en": "(466 MB, better accuracy)",
                "medium.en": "(1.5 GB, high accuracy)",
                "tiny": "(39 MB, multilingual)",
                "base": "(290 MB, multilingual)",
                "small": "(968 MB, multilingual)",
                "medium": "(3 GB, multilingual)",
                "large": "(6 GB, best accuracy, multilingual)",
            }
            cx_print(f"Using Whisper model: {model} {model_info.get(model, '')}", "info")

        # Queue for thread-safe communication between worker and main thread
        input_queue = queue.Queue()
        response_queue = queue.Queue()

        def process_voice_command(text: str) -> None:
            """Process transcribed voice command."""
            if not text:
                return

            # Determine if this is an install command or a question
            text_lower = text.lower().strip()
            is_install = any(
                text_lower.startswith(word) for word in ["install", "setup", "add", "get", "put"]
            )

            if is_install:
                # Remove the command verb for install
                software = text
                for verb in ["install", "setup", "add", "get", "put"]:
                    if text_lower.startswith(verb):
                        software = text[len(verb) :].strip()
                        break

                # Validate software name
                if not software or len(software) > 200:
                    cx_print("Invalid software name", "error")
                    return

                # Check for dangerous characters that shouldn't be in package names
                dangerous_chars = [";", "&", "|", "`", "$", "(", ")"]
                if any(char in software for char in dangerous_chars):
                    cx_print("Invalid characters detected in software name", "error")
                    return

                cx_print(f"Installing: {software}", "info")

                # Handle prompt based on mode
                def _drain_queues() -> None:
                    """Clear any stale prompt/response messages from previous interactions."""

                    try:
                        while not response_queue.empty():
                            response_queue.get_nowait()
                    except Exception:
                        pass

                    try:
                        while not input_queue.empty():
                            input_queue.get_nowait()
                    except Exception:
                        pass

                def _flush_stdin() -> None:
                    """Flush any pending input from stdin."""
                    try:
                        # Use select to check for pending input without blocking
                        while select.select([sys.stdin], [], [], 0.0)[0]:
                            sys.stdin.read(1)
                    except (OSError, ValueError, TypeError):
                        # OSError: fd not valid, ValueError: fd negative, TypeError: not selectable
                        pass

                def _resolve_choice() -> str:
                    """Prompt user until a valid choice is provided."""

                    def _prompt_inline() -> str:
                        console.print()
                        console.print("[bold cyan]Choose an action:[/bold cyan]")
                        console.print("  [1] Dry run (preview commands)")
                        console.print("  [2] Execute (run commands)")
                        console.print("  [3] Cancel")
                        console.print("  [dim](Ctrl+C to cancel)[/dim]")
                        console.print()

                        try:
                            _flush_stdin()  # Clear any buffered input
                            choice = input("Enter choice [1/2/3]: ").strip()
                            # Blank input defaults to dry-run (1)
                            return choice or "1"
                        except (KeyboardInterrupt, EOFError):
                            return "3"

                    if input_handler_thread is None:
                        # Single-shot mode: inline prompt handling (no input handler thread running)
                        _flush_stdin()  # Clear any buffered input before prompting
                        choice_local = _prompt_inline()
                        while choice_local not in {"1", "2", "3"}:
                            cx_print("Invalid choice. Please enter 1, 2, or 3.", "warning")
                            choice_local = _prompt_inline()
                        return choice_local

                    # Continuous mode: use queue-based communication with input handler thread
                    _drain_queues()
                    while True:
                        input_queue.put({"type": "prompt", "software": software})

                        try:
                            response = response_queue.get(timeout=60)
                            choice_local = response.get("choice")
                        except queue.Empty:
                            cx_print("\nInput timeout - cancelled.", "warning")
                            return "3"

                        if choice_local in {"1", "2", "3"}:
                            return choice_local

                        # Invalid or malformed response — re-prompt
                        cx_print("Invalid choice. Please enter 1, 2, or 3.", "warning")

                def _prompt_execute_after_dry_run() -> str:
                    """Prompt user to execute or cancel after dry-run preview."""
                    console.print()
                    console.print("[bold cyan]Dry-run complete. What next?[/bold cyan]")
                    console.print("  [1] Execute (run commands)")
                    console.print("  [2] Cancel")
                    console.print("  [dim](Ctrl+C to cancel)[/dim]")
                    console.print()

                    try:
                        _flush_stdin()  # Clear any buffered input
                        choice_input = input("Enter choice [1/2]: ").strip()
                        return choice_input or "2"  # Default to cancel
                    except (KeyboardInterrupt, EOFError):
                        return "2"

                choice = _resolve_choice()

                # Process choice (unified for both modes)
                if choice == "1":
                    self._install_with_session_key(
                        software, api_key, provider, execute=False, dry_run=True
                    )
                    # After dry-run, ask if user wants to execute
                    follow_up = _prompt_execute_after_dry_run()
                    while follow_up not in {"1", "2"}:
                        cx_print("Invalid choice. Please enter 1 or 2.", "warning")
                        follow_up = _prompt_execute_after_dry_run()
                    if follow_up == "1":
                        cx_print("Executing installation...", "info")
                        self._install_with_session_key(
                            software, api_key, provider, execute=True, dry_run=False
                        )
                    else:
                        cx_print("Cancelled.", "info")
                elif choice == "2":
                    cx_print("Executing installation...", "info")
                    self._install_with_session_key(
                        software, api_key, provider, execute=True, dry_run=False
                    )
                else:
                    cx_print("Cancelled.", "info")
            else:
                # Treat as a question
                cx_print(f"Question: {text}", "info")
                self._ask_with_session_key(text, api_key, provider)

        handler = None
        input_handler_thread = None
        stop_input_handler = threading.Event()

        def input_handler_loop():
            """Main thread loop to handle user input requests from worker thread."""
            while not stop_input_handler.is_set():
                try:
                    request = input_queue.get(timeout=0.5)
                    if request.get("type") == "prompt":
                        console.print()
                        console.print("[bold cyan]Choose an action:[/bold cyan]")
                        console.print("  [1] Dry run (preview commands)")
                        console.print("  [2] Execute (run commands)")
                        console.print("  [3] Cancel")
                        console.print()

                        while True:
                            try:
                                choice = input("Enter choice [1/2/3]: ").strip()
                                # Blank input defaults to dry-run (1)
                                choice = choice or "1"
                            except (KeyboardInterrupt, EOFError):
                                response_queue.put({"choice": "3"})
                                cx_print("\nCancelled.", "info")
                                break

                            if choice in {"1", "2", "3"}:
                                response_queue.put({"choice": choice})
                                break

                            cx_print("Invalid choice. Please enter 1, 2, or 3.", "warning")
                except queue.Empty:
                    continue
                except Exception as e:
                    logging.debug(f"Input handler error: {e}")
                    continue

        try:
            handler = VoiceInputHandler(model_name=model)

            if continuous:
                # Start input handler thread
                input_handler_thread = threading.Thread(target=input_handler_loop, daemon=True)
                input_handler_thread.start()

                # Continuous voice mode
                handler.start_voice_mode(process_voice_command)
            else:
                # Single recording mode
                text = handler.record_single()
                if text:
                    process_voice_command(text)
                else:
                    cx_print("No speech detected.", "warning")

            return 0

        except (VoiceInputError, MicrophoneNotFoundError, ModelNotFoundError) as e:
            self._print_error(str(e))
            return 1
        except KeyboardInterrupt:
            cx_print("\nVoice mode exited.", "info")
            return 0
        finally:
            # Stop input handler thread
            stop_input_handler.set()
            if input_handler_thread is not None and input_handler_thread.is_alive():
                input_handler_thread.join(timeout=1.0)

            # Ensure cleanup even if exceptions occur
            if handler is not None:
                try:
                    handler.stop()
                except Exception as e:
                    # Log cleanup errors but don't raise
                    logging.debug("Error during voice handler cleanup: %s", e)

    def _normalize_software_name(self, software: str) -> str:
        """Normalize software name by cleaning whitespace.

        Returns a natural-language description suitable for LLM interpretation.
        Does NOT return shell commands - all command generation must go through
        the LLM and validation pipeline.
        """
        # Just normalize whitespace - return natural language description
        return " ".join(software.split())

    def _record_history_error(
        self,
        history: InstallationHistory,
        install_id: str | None,
        error: str,
    ) -> None:
        """Record installation error to history."""
        if install_id:
            history.update_installation(install_id, InstallationStatus.FAILED, error)

    def _handle_parallel_execution(
        self,
        commands: list[str],
        software: str,
        install_id: str | None,
        history: InstallationHistory,
    ) -> int:
        """Handle parallel installation execution."""
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

            if success:
                total_duration = self._calculate_duration(parallel_tasks)
                self._print_success(f"{software} installed successfully!")
                print(f"\nCompleted in {total_duration:.2f} seconds (parallel mode)")
                if install_id:
                    history.update_installation(install_id, InstallationStatus.SUCCESS)
                    print(f"\n📝 Installation recorded (ID: {install_id})")
                    print(f"   To rollback: cortex rollback {install_id}")
                return 0

            error_msg = self._get_parallel_error_msg(parallel_tasks)
            self._record_history_error(history, install_id, error_msg)
            self._print_error(self.INSTALL_FAIL_MSG)
            if error_msg:
                print(f"  Error: {error_msg}", file=sys.stderr)
            if install_id:
                print(f"\n📝 Installation recorded (ID: {install_id})")
                print(f"   View details: cortex history {install_id}")
            return 1

        except (ValueError, OSError) as e:
            self._record_history_error(history, install_id, str(e))
            self._print_error(f"Parallel execution failed: {str(e)}")
            return 1
        except Exception as e:
            self._record_history_error(history, install_id, str(e))
            self._print_error(f"Unexpected parallel execution error: {str(e)}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def _calculate_duration(self, parallel_tasks: list) -> float:
        """Calculate total duration from parallel tasks."""
        if not parallel_tasks:
            return 0.0

        max_end = max(
            (t.end_time for t in parallel_tasks if t.end_time is not None),
            default=None,
        )
        min_start = min(
            (t.start_time for t in parallel_tasks if t.start_time is not None),
            default=None,
        )
        if max_end is not None and min_start is not None:
            return max_end - min_start
        return 0.0

    def _get_parallel_error_msg(self, parallel_tasks: list) -> str:
        """Extract error message from failed parallel tasks."""
        failed_tasks = [t for t in parallel_tasks if getattr(t.status, "value", "") == "failed"]
        return failed_tasks[0].error if failed_tasks else self.INSTALL_FAIL_MSG

    def _handle_sequential_execution(
        self,
        commands: list[str],
        software: str,
        install_id: str | None,
        history: InstallationHistory,
    ) -> int:
        """Handle sequential installation execution."""

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
            descriptions=[f"Step {i + 1}" for i in range(len(commands))],
            timeout=300,
            stop_on_error=True,
            progress_callback=progress_callback,
        )

        result = coordinator.execute()

        if result.success:
            self._print_success(f"{software} installed successfully!")
            print(f"\nCompleted in {result.total_duration:.2f} seconds")
            if install_id:
                history.update_installation(install_id, InstallationStatus.SUCCESS)
                print(f"\n📝 Installation recorded (ID: {install_id})")
                print(f"   To rollback: cortex rollback {install_id}")
            return 0

        # Handle failure
        self._record_history_error(
            history, install_id, result.error_message or self.INSTALL_FAIL_MSG
        )
        if result.failed_step is not None:
            self._print_error(f"{self.INSTALL_FAIL_MSG} at step {result.failed_step + 1}")
        else:
            self._print_error(self.INSTALL_FAIL_MSG)
        if result.error_message:
            print(f"  Error: {result.error_message}", file=sys.stderr)
        if install_id:
            print(f"\n📝 Installation recorded (ID: {install_id})")
            print(f"   View details: cortex history {install_id}")
        return 1

    def install(
        self,
        software: str,
        execute: bool = False,
        dry_run: bool = False,
        parallel: bool = False,
        json_output: bool = False,
    ) -> int:
        """Install software using the LLM-powered package manager."""
        # Initialize installation history
        history = InstallationHistory()
        install_id = None
        start_time = datetime.now()
        # Validate input first
        is_valid, error = validate_install_request(software)
        if not is_valid:
            if json_output:
                print(json.dumps({"success": False, "error": error, "error_type": "ValueError"}))
            else:
                self._print_error(error)
            return 1

        software = self._normalize_software_name(software)

        api_key = self._get_api_key()
        if not api_key:
            error_msg = "No API key found. Please configure an API provider."
            # Record installation attempt before failing if we have packages
            try:
                packages = [software.split()[0]]  # Basic package extraction
                install_id = history.record_installation(
                    InstallationType.INSTALL, packages, [], start_time
                )
            except Exception:
                pass  # If recording fails, continue with error reporting

            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, error_msg)

            if json_output:
                print(
                    json.dumps({"success": False, "error": error_msg, "error_type": "RuntimeError"})
                )
            else:
                self._print_error(error_msg)
            return 1

        provider = self._get_provider()
        self._debug(f"Using provider: {provider}")
        self._debug(f"API key: {api_key[:10]}...{api_key[-4:]}")

        try:
            if not json_output:
                self._print_status("🧠", "Understanding request...")

            interpreter = CommandInterpreter(api_key=api_key, provider=provider)

            if not json_output:
                self._print_status("📦", "Planning installation...")
                for _ in range(10):
                    self._animate_spinner("Analyzing system requirements...")
                self._clear_line()

            commands = interpreter.parse(f"install {software}")

            if not commands:
                self._print_error(t("install.no_commands"))
                return 1

            # Predictive Analysis
            if not json_output:
                self._print_status("🔮", t("predictive.analyzing"))
            if not self.predict_manager:
                self.predict_manager = PredictiveErrorManager(api_key=api_key, provider=provider)
            prediction = self.predict_manager.analyze_installation(software, commands)
            if not json_output:
                self._clear_line()

            if not json_output:
                if prediction.risk_level != RiskLevel.NONE:
                    self._display_prediction_warning(prediction)
                    if execute and not self._confirm_risky_operation(prediction):
                        cx_print(f"\n{t('ui.operation_cancelled')}", "warning")
                        return 0
                else:
                    cx_print(t("predictive.no_issues_detected"), "success")

            # Extract packages from commands for tracking
            packages = history._extract_packages_from_commands(commands)

            # Record installation start
            if execute or dry_run:
                install_id = history.record_installation(
                    InstallationType.INSTALL, packages, commands, start_time
                )

            # If JSON output requested, return structured data and exit early
            if json_output:
                output = {
                    "success": True,
                    "commands": commands,
                    "packages": packages,
                    "install_id": install_id,
                    "prediction": {
                        "risk_level": prediction.risk_level.name,
                        "reasons": prediction.reasons,
                        "recommendations": prediction.recommendations,
                        "predicted_errors": prediction.predicted_errors,
                    },
                }
                print(json.dumps(output, indent=2))
                return 0

            self._print_status("⚙️", f"Installing {software}...")
            print("\nGenerated commands:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. {cmd}")

            if dry_run:
                print(f"\n({t('install.dry_run_message')})")
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

                print(f"\n{t('install.executing')}")

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
                            self._print_success(t("install.package_installed", package=software))
                            print(
                                f"\n{t('progress.completed_in', seconds=f'{total_duration:.2f}')}"
                            )

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

                        self._print_error(t("install.failed"))
                        if error_msg:
                            print(f"  {t('common.error')}: {error_msg}", file=sys.stderr)
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
                    self._print_success(t("install.package_installed", package=software))
                    print(f"\n{t('progress.completed_in', seconds=f'{result.total_duration:.2f}')}")

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

            print("\nExecuting commands...")
            if parallel:
                return self._handle_parallel_execution(commands, software, install_id, history)

            return self._handle_sequential_execution(commands, software, install_id, history)

        except ValueError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            if json_output:

                print(json.dumps({"success": False, "error": str(e), "error_type": "ValueError"}))
            else:
                self._print_error(str(e))
            return 1
        except RuntimeError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            if json_output:

                print(json.dumps({"success": False, "error": str(e), "error_type": "RuntimeError"}))
            else:
                self._print_error(f"API call failed: {str(e)}")
            return 1
        except OSError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            if json_output:

                print(json.dumps({"success": False, "error": str(e), "error_type": "OSError"}))
            else:
                self._print_error(f"System error: {str(e)}")
            return 1
        except Exception as e:
            self._record_history_error(history, install_id, str(e))
            self._print_error(f"Unexpected error: {str(e)}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def remove(self, args: argparse.Namespace) -> int:
        """Handle package removal with impact analysis"""
        package = args.package
        dry_run = getattr(args, "dry_run", True)  # Default to dry-run for safety
        purge = getattr(args, "purge", False)
        force = getattr(args, "force", False)
        json_output = getattr(args, "json", False)

        # Initialize and analyze
        result = self._analyze_package_removal(package)
        if result is None:
            return 1

        # Check if package doesn't exist at all (not in repos)
        if self._check_package_not_found(result):
            return 1

        # Output results
        self._output_impact_result(result, json_output)

        # Dry-run mode - stop here
        if dry_run:
            console.print()
            cx_print("Dry run mode - no changes made", "info")
            cx_print(f"To proceed with removal: cortex remove {package} --execute", "info")
            return 0

        # Safety check and confirmation
        if not self._can_proceed_with_removal(result, force, args, package, purge):
            return self._removal_blocked_or_cancelled(result, force)

        return self._execute_removal(package, purge)

    def _analyze_package_removal(self, package: str):
        """Initialize analyzer and perform impact analysis. Returns None on failure."""
        try:
            analyzer = UninstallImpactAnalyzer()
        except Exception as e:
            self._print_error(f"Failed to initialize impact analyzer: {e}")
            return None

        cx_print(f"Analyzing impact of removing '{package}'...", "info")
        try:
            return analyzer.analyze(package)
        except Exception as e:
            self._print_error(f"Impact analysis failed: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return None

    def _check_package_not_found(self, result) -> bool:
        """Check if package doesn't exist in repos and print warnings."""
        if result.warnings and "not found in repositories" in str(result.warnings):
            for warning in result.warnings:
                cx_print(warning, "warning")
            for rec in result.recommendations:
                cx_print(rec, "info")
            return True
        return False

    def _output_impact_result(self, result, json_output: bool) -> None:
        """Output the impact result in JSON or rich format."""
        if json_output:
            import json as json_module

            data = {
                "target_package": result.target_package,
                "direct_dependents": result.direct_dependents,
                "transitive_dependents": result.transitive_dependents,
                "affected_services": [
                    {
                        "name": s.name,
                        "status": s.status.value,
                        "package": s.package,
                        "is_critical": s.is_critical,
                    }
                    for s in result.affected_services
                ],
                "orphaned_packages": result.orphaned_packages,
                "cascade_packages": result.cascade_packages,
                "severity": result.severity.value,
                "total_affected": result.total_affected,
                "cascade_depth": result.cascade_depth,
                "recommendations": result.recommendations,
                "warnings": result.warnings,
                "safe_to_remove": result.safe_to_remove,
            }
            console.print(json_module.dumps(data, indent=2))
        else:
            self._display_impact_report(result)

    def _can_proceed_with_removal(
        self, result, force: bool, args, package: str, purge: bool
    ) -> bool:
        """Check safety and get user confirmation. Returns True if can proceed."""
        if not result.safe_to_remove and not force:
            return False

        skip_confirm = getattr(args, "yes", False)
        if skip_confirm:
            return True

        return self._confirm_removal(package, purge)

    def _confirm_removal(self, package: str, purge: bool) -> bool:
        """Prompt user for removal confirmation."""
        console.print()
        confirm_msg = f"Remove '{package}'"
        if purge:
            confirm_msg += " and purge configuration"
        confirm_msg += "? [y/N]: "
        try:
            response = StdinHandler.get_input(confirm_msg).lower()
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return False

    def _removal_blocked_or_cancelled(self, result, force: bool) -> int:
        """Handle blocked or cancelled removal."""
        if not result.safe_to_remove and not force:
            console.print()
            self._print_error(
                "Package removal has high impact. Use --force to proceed anyway, "
                "or address the recommendations first."
            )
            return 1
        cx_print("Removal cancelled", "info")
        return 0

    def _display_impact_report(self, result: ImpactResult) -> None:
        """Display formatted impact analysis report"""

        # Severity styling
        severity_styles = {
            ImpactSeverity.SAFE: ("green", "✅"),
            ImpactSeverity.LOW: ("green", "💚"),
            ImpactSeverity.MEDIUM: ("yellow", "🟡"),
            ImpactSeverity.HIGH: ("orange1", "🟠"),
            ImpactSeverity.CRITICAL: ("red", "🔴"),
        }
        style, icon = severity_styles.get(result.severity, ("white", "❓"))

        # Header
        console.print()
        console.print(
            Panel(f"[bold]{icon} Impact Analysis: {result.target_package}[/bold]", style=style)
        )

        # Display sections
        self._display_warnings(result.warnings)
        self._display_package_list(result.direct_dependents, "cyan", "📦 Direct dependents", 10)
        self._display_services(result.affected_services)
        self._display_summary_table(result, style, Table)
        self._display_package_list(result.cascade_packages, "yellow", "🗑️  Cascade removal", 5)
        self._display_package_list(result.orphaned_packages, "white", "👻 Would become orphaned", 5)
        self._display_recommendations(result.recommendations)

        # Final verdict
        console.print()
        if result.safe_to_remove:
            console.print("[bold green]✅ Safe to remove[/bold green]")
        else:
            console.print("[bold yellow]⚠️  Review recommendations before proceeding[/bold yellow]")

    def _display_warnings(self, warnings: list) -> None:
        """Display warnings with appropriate styling."""
        for warning in warnings:
            if "not currently installed" in warning:
                console.print(f"\n[bold yellow]ℹ️  {warning}[/bold yellow]")
                console.print("[dim]   Showing potential impact analysis for this package.[/dim]")
            else:
                console.print(f"\n[bold red]⚠️  {warning}[/bold red]")

    def _display_package_list(self, packages: list, color: str, title: str, limit: int) -> None:
        """Display a list of packages with truncation."""
        if packages:
            console.print(f"\n[bold {color}]{title} ({len(packages)}):[/bold {color}]")
            for pkg in packages[:limit]:
                console.print(f"   • {pkg}")
            if len(packages) > limit:
                console.print(f"   [dim]... and {len(packages) - limit} more[/dim]")
        elif "dependents" in title:
            console.print(f"\n[bold {color}]{title}:[/bold {color}] None")

    def _display_services(self, services: list) -> None:
        """Display affected services."""
        if services:
            console.print(f"\n[bold magenta]🔧 Affected services ({len(services)}):[/bold magenta]")
            for service in services:
                status_icon = "🟢" if service.status == ServiceStatus.RUNNING else "⚪"
                critical_marker = " [red][CRITICAL][/red]" if service.is_critical else ""
                console.print(f"   {status_icon} {service.name}{critical_marker}")
        else:
            console.print("\n[bold magenta]🔧 Affected services:[/bold magenta] None")

    def _display_summary_table(self, result, style: str, table_class) -> None:
        """Display the impact summary table."""
        summary_table = table_class(show_header=False, box=None, padding=(0, 2))
        summary_table.add_column("Metric", style="dim")
        summary_table.add_column("Value")
        summary_table.add_row("Total packages affected", str(result.total_affected))
        summary_table.add_row("Cascade depth", str(result.cascade_depth))
        summary_table.add_row("Services at risk", str(len(result.affected_services)))
        summary_table.add_row("Severity", f"[{style}]{result.severity.value.upper()}[/{style}]")
        console.print("\n[bold]📊 Impact Summary:[/bold]")
        console.print(summary_table)

    def _display_recommendations(self, recommendations: list) -> None:
        """Display recommendations."""
        if recommendations:
            console.print("\n[bold green]💡 Recommendations:[/bold green]")
            for rec in recommendations:
                console.print(f"   • {rec}")

    def _execute_removal(self, package: str, purge: bool = False) -> int:
        """Execute the actual package removal with audit logging"""
        import datetime
        import subprocess

        cx_print(f"Removing '{package}'...", "info")

        # Initialize history for audit logging
        history = InstallationHistory()
        start_time = datetime.datetime.now()
        operation_type = InstallationType.PURGE if purge else InstallationType.REMOVE

        # Build removal command (with -y since user already confirmed)
        if purge:
            cmd = ["sudo", "apt-get", "purge", "-y", package]
        else:
            cmd = ["sudo", "apt-get", "remove", "-y", package]

        # Record the operation start
        try:
            install_id = history.record_installation(
                operation_type=operation_type,
                packages=[package],
                commands=[" ".join(cmd)],
                start_time=start_time,
            )
        except Exception as e:
            self._debug(f"Failed to record installation start: {e}")
            install_id = None

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                self._print_success(f"'{package}' removed successfully")

                # Record successful removal
                if install_id:
                    try:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                    except Exception as e:
                        self._debug(f"Failed to update installation record: {e}")

                # Run autoremove to clean up orphaned packages
                console.print()
                cx_print("Running autoremove to clean up orphaned packages...", "info")
                autoremove_cmd = ["sudo", "apt-get", "autoremove", "-y"]
                autoremove_start = datetime.datetime.now()

                # Record autoremove operation start
                autoremove_id = None
                try:
                    autoremove_id = history.record_installation(
                        operation_type=InstallationType.REMOVE,
                        packages=[f"{package}-autoremove"],
                        commands=[" ".join(autoremove_cmd)],
                        start_time=autoremove_start,
                    )
                except Exception as e:
                    self._debug(f"Failed to record autoremove start: {e}")

                try:
                    autoremove_result = subprocess.run(
                        autoremove_cmd,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )

                    if autoremove_result.returncode == 0:
                        cx_print("Cleanup complete", "success")
                        if autoremove_id:
                            try:
                                history.update_installation(
                                    autoremove_id, InstallationStatus.SUCCESS
                                )
                            except Exception as e:
                                self._debug(f"Failed to update autoremove record: {e}")
                    else:
                        cx_print("Autoremove completed with warnings", "warning")
                        if autoremove_id:
                            try:
                                history.update_installation(
                                    autoremove_id,
                                    InstallationStatus.FAILED,
                                    error_message=(
                                        autoremove_result.stderr[:500]
                                        if autoremove_result.stderr
                                        else "Autoremove returned non-zero exit code"
                                    ),
                                )
                            except Exception as e:
                                self._debug(f"Failed to update autoremove record: {e}")
                except subprocess.TimeoutExpired:
                    cx_print("Autoremove timed out", "warning")
                    if autoremove_id:
                        try:
                            history.update_installation(
                                autoremove_id,
                                InstallationStatus.FAILED,
                                error_message="Autoremove timed out after 300 seconds",
                            )
                        except Exception:
                            pass
                except Exception as e:
                    cx_print(f"Autoremove failed: {e}", "warning")
                    if autoremove_id:
                        try:
                            history.update_installation(
                                autoremove_id,
                                InstallationStatus.FAILED,
                                error_message=str(e)[:500],
                            )
                        except Exception:
                            pass

                return 0
            else:
                self._print_error(f"Removal failed: {result.stderr}")
                # Record failed removal
                if install_id:
                    try:
                        history.update_installation(
                            install_id,
                            InstallationStatus.FAILED,
                            error_message=result.stderr[:500],
                        )
                    except Exception as e:
                        self._debug(f"Failed to update installation record: {e}")
                return 1

        except subprocess.TimeoutExpired:
            self._print_error("Removal timed out")
            # Record timeout failure
            if install_id:
                try:
                    history.update_installation(
                        install_id,
                        InstallationStatus.FAILED,
                        error_message="Operation timed out after 300 seconds",
                    )
                except Exception:
                    pass
            return 1
        except Exception as e:
            self._print_error(f"Removal failed: {e}")
            # Record exception failure
            if install_id:
                try:
                    history.update_installation(
                        install_id,
                        InstallationStatus.FAILED,
                        error_message=str(e)[:500],
                    )
                except Exception:
                    pass
            return 1

    def cache_stats(self) -> int:
        try:
            from cortex.semantic_cache import SemanticCache

            cache = SemanticCache()
            stats = cache.stats()
            hit_rate_value = f"{stats.hit_rate * 100:.1f}" if stats.total else "0.0"

            cx_header(t("cache.stats_header"))
            cx_print(f"{t('cache.hits')}: {stats.hits}", "info")
            cx_print(f"{t('cache.misses')}: {stats.misses}", "info")
            cx_print(t("cache.hit_rate", rate=hit_rate_value), "info")
            cx_print(f"{t('cache.saved_calls')}: {stats.saved_calls}", "info")
            return 0
        except (ImportError, OSError) as e:
            self._print_error(t("cache.read_error", error=str(e)))
            return 1
        except Exception as e:
            self._print_error(t("cache.unexpected_error", error=str(e)))
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def config(self, args: argparse.Namespace) -> int:
        """Handle configuration commands including language settings."""
        action = getattr(args, "config_action", None)

        if not action:
            cx_print(t("config.missing_subcommand"), "error")
            return 1

        if action == "language":
            return self._config_language(args)
        elif action == "show":
            return self._config_show()
        else:
            self._print_error(t("config.unknown_action", action=action))
            return 1

    def _config_language(self, args: argparse.Namespace) -> int:
        """Handle language configuration."""
        lang_config = LanguageConfig()

        # List available languages
        if getattr(args, "list", False):
            cx_header(t("language.available"))
            for code, info in SUPPORTED_LANGUAGES.items():
                current_marker = " ✓" if code == get_language() else ""
                console.print(
                    f"  [green]{code}[/green] - {info['name']} ({info['native']}){current_marker}"
                )
            return 0

        # Show language info
        if getattr(args, "info", False):
            info = lang_config.get_language_info()
            cx_header(t("language.current"))
            console.print(f"  [bold]{info['name']}[/bold] ({info['native_name']})")
            console.print(f"  [dim]{t('config.code_label')}: {info['language']}[/dim]")
            # Translate the source value using proper key mapping
            source_translation_keys = {
                "environment": "language.set_from_env",
                "config": "language.set_from_config",
                "auto-detected": "language.auto_detected",
                "default": "language.default",
            }
            source = info.get("source", "")
            source_key = source_translation_keys.get(source)
            source_display = t(source_key) if source_key else source
            console.print(f"  [dim]{t('config.source_label')}: {source_display}[/dim]")

            if info.get("env_override"):
                console.print(f"  [dim]{t('language.set_from_env')}: {info['env_override']}[/dim]")
            if info.get("detected_language"):
                console.print(
                    f"  [dim]{t('language.auto_detected')}: {info['detected_language']}[/dim]"
                )
            return 0

        # Set language
        code = getattr(args, "code", None)
        if not code:
            # No code provided, show current language and list
            current = get_language()
            current_info = SUPPORTED_LANGUAGES.get(current, {})
            cx_print(
                f"{t('language.current')}: {current_info.get('name', current)} "
                f"({current_info.get('native', '')})",
                "info",
            )
            console.print()
            console.print(
                f"[dim]{t('language.supported_codes')}: {', '.join(SUPPORTED_LANGUAGES.keys())}[/dim]"
            )
            console.print(f"[dim]{t('config.use_command_hint')}[/dim]")
            console.print(f"[dim]{t('config.list_hint')}[/dim]")
            return 0

        # Handle 'auto' to clear saved preference
        if code.lower() == "auto":
            lang_config.clear_language()
            from cortex.i18n.translator import reset_translator

            reset_translator()
            new_lang = get_language()
            new_info = SUPPORTED_LANGUAGES.get(new_lang, {})
            cx_print(t("language.changed", language=new_info.get("native", new_lang)), "success")
            console.print(f"[dim]({t('language.auto_detected')})[/dim]")
            return 0

        # Validate and set language
        code = code.lower()
        if code not in SUPPORTED_LANGUAGES:
            self._print_error(t("language.invalid_code", code=code))
            console.print(
                f"[dim]{t('language.supported_codes')}: {', '.join(SUPPORTED_LANGUAGES.keys())}[/dim]"
            )
            return 1

        try:
            lang_config.set_language(code)
            # Reset the global translator to pick up the new language
            from cortex.i18n.translator import reset_translator

            reset_translator()
            set_language(code)

            lang_info = SUPPORTED_LANGUAGES[code]
            cx_print(t("language.changed", language=lang_info["native"]), "success")
            return 0
        except (ValueError, RuntimeError) as e:
            self._print_error(t("language.set_failed", error=str(e)))
            return 1

    def _config_show(self) -> int:
        """Show all current configuration."""
        cx_header(t("config.header"))

        # Language
        lang_config = LanguageConfig()
        lang_info = lang_config.get_language_info()
        console.print(f"[bold]{t('config.language_label')}:[/bold]")
        console.print(
            f"  {lang_info['name']} ({lang_info['native_name']}) "
            f"[dim][{lang_info['language']}][/dim]"
        )
        # Translate the source identifier to user-friendly text
        source_translations = {
            "environment": t("language.set_from_env"),
            "config": t("language.set_from_config"),
            "auto-detected": t("language.auto_detected"),
            "default": t("language.default"),
        }
        source_display = source_translations.get(lang_info["source"], lang_info["source"])
        console.print(f"  [dim]{t('config.source_label')}: {source_display}[/dim]")
        console.print()

        # API Provider
        provider = self._get_provider()
        console.print(f"[bold]{t('config.llm_provider_label')}:[/bold]")
        console.print(f"  {provider}")
        console.print()

        # Config paths
        console.print(f"[bold]{t('config.config_paths_label')}:[/bold]")
        console.print(f"  {t('config.preferences_path')}: ~/.cortex/preferences.yaml")
        console.print(f"  {t('config.history_path')}: ~/.cortex/history.db")
        console.print()

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

    def update(self, args: argparse.Namespace) -> int:
        """Handle the update command for self-updating Cortex."""
        from rich.progress import Progress, SpinnerColumn, TextColumn

        # Parse channel
        channel_str = getattr(args, "channel", "stable")
        try:
            channel = UpdateChannel(channel_str)
        except ValueError:
            channel = UpdateChannel.STABLE

        updater = Updater(channel=channel)

        # Handle subcommands
        action = getattr(args, "update_action", None)

        if action == "check" or (not action and getattr(args, "check", False)):
            # Check for updates only
            cx_print("Checking for updates...", "thinking")
            result = updater.check_update_available(force=True)

            if result.error:
                self._print_error(f"Update check failed: {result.error}")
                return 1

            console.print()
            cx_print(f"Current version: [cyan]{result.current_version}[/cyan]", "info")

            if result.update_available and result.latest_release:
                cx_print(
                    f"Update available: [green]{result.latest_version}[/green]",
                    "success",
                )
                console.print()
                console.print("[bold]Release notes:[/bold]")
                console.print(result.latest_release.release_notes_summary)
                console.print()
                cx_print(
                    "Run [bold]cortex update install[/bold] to upgrade",
                    "info",
                )
            else:
                cx_print("Cortex is up to date!", "success")

            return 0

        elif action == "install":
            # Install update
            target = getattr(args, "version", None)
            dry_run = getattr(args, "dry_run", False)

            if dry_run:
                cx_print("Dry run mode - no changes will be made", "warning")

            cx_header("Cortex Self-Update")

            def progress_callback(message: str, percent: float) -> None:
                if percent >= 0:
                    cx_print(f"{message} ({percent:.0f}%)", "info")
                else:
                    cx_print(message, "info")

            updater.progress_callback = progress_callback

            result = updater.update(target_version=target, dry_run=dry_run)

            console.print()

            if result.success:
                if result.status == UpdateStatus.SUCCESS:
                    if result.new_version == result.previous_version:
                        cx_print("Already up to date!", "success")
                    else:
                        cx_print(
                            f"Updated: {result.previous_version} → {result.new_version}",
                            "success",
                        )
                        if result.duration_seconds:
                            console.print(f"[dim]Completed in {result.duration_seconds:.1f}s[/dim]")
                elif result.status == UpdateStatus.PENDING:
                    # Dry run
                    cx_print(
                        f"Would update: {result.previous_version} → {result.new_version}",
                        "info",
                    )
                return 0
            else:
                if result.status == UpdateStatus.ROLLED_BACK:
                    cx_print("Update failed - rolled back to previous version", "warning")
                else:
                    self._print_error(f"Update failed: {result.error}")
                return 1

        elif action == "rollback":
            # Rollback to previous version
            backup_id = getattr(args, "backup_id", None)

            backups = updater.list_backups()

            if not backups:
                self._print_error("No backups available for rollback")
                return 1

            if backup_id:
                # Find specific backup
                target_backup = None
                for b in backups:
                    if b.version == backup_id or str(b.path).endswith(backup_id):
                        target_backup = b
                        break

                if not target_backup:
                    self._print_error(f"Backup '{backup_id}' not found")
                    return 1

                backup_path = target_backup.path
            else:
                # Use most recent backup
                backup_path = backups[0].path

            cx_print(f"Rolling back to backup: {backup_path.name}", "info")
            result = updater.rollback_to_backup(backup_path)

            if result.success:
                cx_print(
                    f"Rolled back: {result.previous_version} → {result.new_version}",
                    "success",
                )
                return 0
            else:
                self._print_error(f"Rollback failed: {result.error}")
                return 1

        elif action == "list" or getattr(args, "list_releases", False):
            # List available versions
            from cortex.update_checker import UpdateChecker

            checker = UpdateChecker(channel=channel)
            releases = checker.get_all_releases(limit=10)

            if not releases:
                cx_print("No releases found", "warning")
                return 1

            cx_header(f"Available Releases ({channel.value} channel)")

            table = Table(show_header=True, header_style="bold cyan", box=None)
            table.add_column("Version", style="green")
            table.add_column("Date")
            table.add_column("Channel")
            table.add_column("Notes")

            current = get_version_string()

            for release in releases:
                version_str = str(release.version)
                if version_str == current:
                    version_str = f"{version_str} [dim](current)[/dim]"

                # Truncate notes
                notes = release.name or release.body[:50] if release.body else ""
                if len(notes) > 50:
                    notes = notes[:47] + "..."

                table.add_row(
                    version_str,
                    release.formatted_date,
                    release.version.channel.value,
                    notes,
                )

            console.print(table)
            return 0

        elif action == "backups":
            # List backups
            backups = updater.list_backups()

            if not backups:
                cx_print("No backups available", "info")
                return 0

            cx_header("Available Backups")

            table = Table(show_header=True, header_style="bold cyan", box=None)
            table.add_column("Version", style="green")
            table.add_column("Date")
            table.add_column("Size")
            table.add_column("Path")

            for backup in backups:
                # Format size
                size_mb = backup.size_bytes / (1024 * 1024)
                size_str = f"{size_mb:.1f} MB"

                # Format date
                try:
                    dt = datetime.fromisoformat(backup.timestamp)
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    date_str = backup.timestamp[:16]

                table.add_row(
                    backup.version,
                    date_str,
                    size_str,
                    str(backup.path.name),
                )

            console.print(table)
            console.print()
            cx_print(
                "Use [bold]cortex update rollback <version>[/bold] to restore",
                "info",
            )
            return 0

        else:
            # Default: show current version and check for updates
            cx_print(f"Current version: [cyan]{get_version_string()}[/cyan]", "info")
            cx_print("Checking for updates...", "thinking")

            result = updater.check_update_available()

            if result.update_available and result.latest_release:
                console.print()
                cx_print(
                    f"Update available: [green]{result.latest_version}[/green]",
                    "success",
                )
                console.print()
                console.print("[bold]What's new:[/bold]")
                console.print(result.latest_release.release_notes_summary)
                console.print()
                cx_print(
                    "Run [bold]cortex update install[/bold] to upgrade",
                    "info",
                )
            else:
                cx_print("Cortex is up to date!", "success")

            return 0

    # Daemon Commands
    # --------------------------

    def daemon(self, args: argparse.Namespace) -> int:
        """Handle daemon commands: install, uninstall, config, reload-config, version, ping, shutdown.

        Available commands:
        - install/uninstall: Manage systemd service files (Python-side)
        - config: Get daemon configuration via IPC
        - reload-config: Reload daemon configuration via IPC
        - version: Get daemon version via IPC
        - ping: Test daemon connectivity via IPC
        - shutdown: Request daemon shutdown via IPC
        - run-tests: Run daemon test suite
        """
        action = getattr(args, "daemon_action", None)

        if action == "install":
            return self._daemon_install(args)
        elif action == "uninstall":
            return self._daemon_uninstall(args)
        elif action == "config":
            return self._daemon_config()
        elif action == "reload-config":
            return self._daemon_reload_config()
        elif action == "version":
            return self._daemon_version()
        elif action == "ping":
            return self._daemon_ping()
        elif action == "shutdown":
            return self._daemon_shutdown()
        elif action == "run-tests":
            return self._daemon_run_tests(args)
        else:
            cx_print("Usage: cortex daemon <command>", "info")
            cx_print("", "info")
            cx_print("Available commands:", "info")
            cx_print("  install        Install and enable the daemon service", "info")
            cx_print("  uninstall      Remove the daemon service", "info")
            cx_print("  config         Show daemon configuration", "info")
            cx_print("  reload-config  Reload daemon configuration", "info")
            cx_print("  version        Show daemon version", "info")
            cx_print("  ping           Test daemon connectivity", "info")
            cx_print("  shutdown       Request daemon shutdown", "info")
            cx_print("  run-tests      Run daemon test suite", "info")
            return 0

    def _update_history_on_failure(
        self, history: InstallationHistory, install_id: str | None, error_msg: str
    ) -> None:
        """
        Helper method to update installation history on failure.

        Args:
            history: InstallationHistory instance.
            install_id: Installation ID to update, or None if not available.
            error_msg: Error message to record.
        """
        if install_id:
            try:
                history.update_installation(install_id, InstallationStatus.FAILED, error_msg)
            except Exception:
                # Continue even if audit logging fails - don't break the main flow
                pass

    def _daemon_ipc_call(
        self,
        operation_name: str,
        ipc_func: "Callable[[DaemonClient], DaemonResponse]",
    ) -> tuple[bool, "DaemonResponse | None"]:
        """
        Helper method for daemon IPC calls with centralized error handling.

        Args:
            operation_name: Human-readable name of the operation for error messages.
            ipc_func: A callable that takes a DaemonClient and returns a DaemonResponse.

        Returns:
            Tuple of (success: bool, response: DaemonResponse | None)
            On error, response is None and an error message is printed.
        """
        # Initialize audit logging
        history = InstallationHistory()
        start_time = datetime.now(timezone.utc)
        install_id = None

        try:
            # Record operation start
            install_id = history.record_installation(
                InstallationType.CONFIG,
                ["cortexd"],
                [f"daemon.{operation_name}"],
                start_time,
            )
        except Exception:
            # Continue even if audit logging fails - don't break the main flow
            pass

        try:
            from cortex.daemon_client import (
                DaemonClient,
                DaemonConnectionError,
                DaemonNotInstalledError,
                DaemonResponse,
            )

            client = DaemonClient()
            response = ipc_func(client)

            # Update history with success/failure
            if install_id:
                try:
                    if response and response.success:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                    else:
                        error_msg = (
                            response.error if response and response.error else "IPC call failed"
                        )
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                except Exception:
                    # Continue even if audit logging fails - don't break the main flow
                    pass

            return True, response

        except DaemonNotInstalledError as e:
            error_msg = str(e)
            cx_print(f"{error_msg}", "error")
            self._update_history_on_failure(history, install_id, error_msg)
            return False, None
        except DaemonConnectionError as e:
            error_msg = str(e)
            cx_print(f"{error_msg}", "error")
            self._update_history_on_failure(history, install_id, error_msg)
            return False, None
        except ImportError:
            error_msg = "Daemon client not available."
            cx_print(error_msg, "error")
            self._update_history_on_failure(history, install_id, error_msg)
            return False, None
        except Exception as e:
            error_msg = f"Unexpected error during {operation_name}: {e}"
            cx_print(error_msg, "error")
            self._update_history_on_failure(history, install_id, error_msg)
            return False, None

    def _daemon_install(self, args: argparse.Namespace) -> int:
        """Install the cortexd daemon using setup_daemon.py."""
        import subprocess
        from pathlib import Path

        cx_header("Installing Cortex Daemon")

        # Find setup_daemon.py
        daemon_dir = Path(__file__).parent.parent / "daemon"
        setup_script = daemon_dir / "scripts" / "setup_daemon.py"

        if not setup_script.exists():
            error_msg = f"Setup script not found at {setup_script}"
            cx_print(error_msg, "error")
            cx_print("Please ensure the daemon directory is present.", "error")
            return 1

        execute = getattr(args, "execute", False)

        if not execute:
            cx_print("This will build and install the cortexd daemon.", "info")
            cx_print("", "info")
            cx_print("The setup wizard will:", "info")
            cx_print("  1. Check and install build dependencies", "info")
            cx_print("  2. Build the daemon from source", "info")
            cx_print("  3. Install systemd service files", "info")
            cx_print("  4. Enable and start the service", "info")
            cx_print("", "info")
            cx_print("Run with --execute to proceed:", "info")
            cx_print("  cortex daemon install --execute", "dim")
            # Don't record dry-runs in audit history
            return 0

        # Initialize audit logging only when execution will actually run
        history = InstallationHistory()
        start_time = datetime.now(timezone.utc)
        install_id = None

        try:
            # Record operation start
            install_id = history.record_installation(
                InstallationType.CONFIG,
                ["cortexd"],
                ["cortex daemon install"],
                start_time,
            )
        except Exception as e:
            cx_print(f"Warning: Could not initialize audit logging: {e}", "warning")

        # Run setup_daemon.py
        cx_print("Running daemon setup wizard...", "info")
        try:
            result = subprocess.run(
                [sys.executable, str(setup_script)],
                check=False,
            )

            # Record completion
            if install_id:
                try:
                    if result.returncode == 0:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                    else:
                        error_msg = f"Setup script returned exit code {result.returncode}"
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                except Exception:
                    # Continue even if audit logging fails - don't break the main flow
                    pass

            return result.returncode
        except subprocess.SubprocessError as e:
            error_msg = f"Subprocess error during daemon install: {str(e)}"
            cx_print(error_msg, "error")
            if install_id:
                try:
                    history.update_installation(install_id, InstallationStatus.FAILED, error_msg)
                except Exception:
                    # Continue even if audit logging fails - don't break the main flow
                    pass
            return 1
        except Exception as e:
            error_msg = f"Unexpected error during daemon install: {str(e)}"
            cx_print(error_msg, "error")
            if install_id:
                try:
                    history.update_installation(install_id, InstallationStatus.FAILED, error_msg)
                except Exception:
                    # Continue even if audit logging fails - don't break the main flow
                    pass
            return 1

    def _daemon_uninstall(self, args: argparse.Namespace) -> int:
        """Uninstall the cortexd daemon."""
        import subprocess
        from pathlib import Path

        cx_header("Uninstalling Cortex Daemon")

        execute = getattr(args, "execute", False)

        if not execute:
            cx_print("This will stop and remove the cortexd daemon.", "warning")
            cx_print("", "info")
            cx_print("This will:", "info")
            cx_print("  1. Stop the cortexd service", "info")
            cx_print("  2. Disable the service", "info")
            cx_print("  3. Remove systemd unit files", "info")
            cx_print("  4. Remove the daemon binary", "info")
            cx_print("", "info")
            cx_print("Run with --execute to proceed:", "info")
            cx_print("  cortex daemon uninstall --execute", "dim")
            # Don't record dry-runs in audit history
            return 0

        # Initialize audit logging only when execution will actually run
        history = InstallationHistory()
        start_time = datetime.now(timezone.utc)
        install_id = None

        try:
            # Record operation start
            install_id = history.record_installation(
                InstallationType.CONFIG,
                ["cortexd"],
                ["cortex daemon uninstall"],
                start_time,
            )
        except Exception as e:
            cx_print(f"Warning: Could not initialize audit logging: {e}", "warning")

        # Find uninstall script
        daemon_dir = Path(__file__).parent.parent / "daemon"
        uninstall_script = daemon_dir / "scripts" / "uninstall.sh"

        if uninstall_script.exists():
            cx_print("Running uninstall script...", "info")
            try:
                # Security: Lock down script permissions before execution
                # Set read-only permissions for non-root users to prevent tampering
                import stat

                script_stat = uninstall_script.stat()
                # Remove write permissions for group and others, keep owner read/execute
                uninstall_script.chmod(stat.S_IRUSR | stat.S_IXUSR)

                result = subprocess.run(
                    ["sudo", "bash", str(uninstall_script)],
                    check=False,
                    capture_output=True,
                    text=True,
                )

                # Record completion
                if install_id:
                    try:
                        if result.returncode == 0:
                            history.update_installation(install_id, InstallationStatus.SUCCESS)
                        else:
                            error_msg = f"Uninstall script returned exit code {result.returncode}"
                            if result.stderr:
                                error_msg += f": {result.stderr[:500]}"
                            history.update_installation(
                                install_id, InstallationStatus.FAILED, error_msg
                            )
                    except Exception:
                        # Continue even if audit logging fails - don't break the main flow
                        pass

                return result.returncode
            except subprocess.SubprocessError as e:
                error_msg = f"Subprocess error during daemon uninstall: {str(e)}"
                cx_print(error_msg, "error")
                if install_id:
                    try:
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                    except Exception:
                        # Continue even if audit logging fails - don't break the main flow
                        pass
                return 1
            except Exception as e:
                error_msg = f"Unexpected error during daemon uninstall: {str(e)}"
                cx_print(error_msg, "error")
                if install_id:
                    try:
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                    except Exception:
                        # Continue even if audit logging fails - don't break the main flow
                        pass
                return 1
        else:
            # Manual uninstall
            cx_print("Running manual uninstall...", "info")
            commands = [
                ["sudo", "systemctl", "stop", "cortexd"],
                ["sudo", "systemctl", "disable", "cortexd"],
                ["sudo", "rm", "-f", "/etc/systemd/system/cortexd.service"],
                ["sudo", "rm", "-f", "/etc/systemd/system/cortexd.socket"],
                ["sudo", "rm", "-f", "/usr/local/bin/cortexd"],
                ["sudo", "systemctl", "daemon-reload"],
            ]

            try:
                any_failed = False
                error_messages = []

                for cmd in commands:
                    cmd_str = " ".join(cmd)
                    cx_print(f"  Running: {cmd_str}", "dim")

                    # Update installation history with command info (append to existing record)
                    if install_id:
                        try:
                            # Append command info to existing installation record
                            # instead of creating orphan records
                            history.update_installation(
                                install_id,
                                InstallationStatus.IN_PROGRESS,
                                f"Executing: {cmd_str}",
                            )
                        except Exception:
                            # Continue even if audit logging fails - don't break the main flow
                            pass

                    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

                    # Track failures
                    if result.returncode != 0:
                        any_failed = True
                        error_msg = (
                            f"Command '{cmd_str}' failed with return code {result.returncode}"
                        )
                        if result.stderr:
                            error_msg += f": {result.stderr[:500]}"
                        error_messages.append(error_msg)
                        cx_print(f"  Failed: {error_msg}", "error")

                # Update history and return based on overall success
                if any_failed:
                    combined_error = "; ".join(error_messages)
                    cx_print("Daemon uninstall failed.", "error")
                    if install_id:
                        try:
                            history.update_installation(
                                install_id, InstallationStatus.FAILED, combined_error
                            )
                        except Exception:
                            # Continue even if audit logging fails - don't break the main flow
                            pass
                    return 1
                else:
                    cx_print("Daemon uninstalled.", "success")
                    # Record success
                    if install_id:
                        try:
                            history.update_installation(install_id, InstallationStatus.SUCCESS)
                        except Exception:
                            # Continue even if audit logging fails - don't break the main flow
                            pass
                    return 0
            except subprocess.SubprocessError as e:
                error_msg = f"Subprocess error during manual uninstall: {str(e)}"
                cx_print(error_msg, "error")
                if install_id:
                    try:
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                    except Exception:
                        # Continue even if audit logging fails - don't break the main flow
                        pass
                return 1
            except Exception as e:
                error_msg = f"Unexpected error during manual uninstall: {str(e)}"
                cx_print(error_msg, "error")
                if install_id:
                    try:
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                    except Exception:
                        # Continue even if audit logging fails - don't break the main flow
                        pass
                return 1

    def _daemon_config(self) -> int:
        """Get daemon configuration via IPC."""
        from rich.table import Table

        cx_header("Daemon Configuration")

        success, response = self._daemon_ipc_call("config.get", lambda c: c.config_get())
        if not success:
            return 1

        if response.success and response.result:
            table = Table(title="Current Configuration", show_header=True)
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")

            for key, value in response.result.items():
                table.add_row(key, str(value))

            console.print(table)
            return 0
        else:
            cx_print(f"Failed to get config: {response.error}", "error")
            return 1

    def _daemon_reload_config(self) -> int:
        """Reload daemon configuration via IPC."""
        cx_header("Reloading Daemon Configuration")

        success, response = self._daemon_ipc_call("config.reload", lambda c: c.config_reload())
        if not success:
            return 1

        if response.success:
            cx_print("Configuration reloaded successfully!", "success")
            return 0
        else:
            cx_print(f"Failed to reload config: {response.error}", "error")
            return 1

    def _daemon_version(self) -> int:
        """Get daemon version via IPC."""
        cx_header("Daemon Version")

        success, response = self._daemon_ipc_call("version", lambda c: c.version())
        if not success:
            return 1

        if response.success and response.result:
            name = response.result.get("name", "cortexd")
            version = response.result.get("version", "unknown")
            cx_print(f"{name} version {version}", "success")
            return 0
        else:
            cx_print(f"Failed to get version: {response.error}", "error")
            return 1

    def _daemon_ping(self) -> int:
        """Test daemon connectivity via IPC."""
        import time

        cx_header("Daemon Ping")

        start = time.time()
        success, response = self._daemon_ipc_call("ping", lambda c: c.ping())
        elapsed = (time.time() - start) * 1000  # ms

        if not success:
            return 1

        if response.success:
            cx_print(f"Pong! Response time: {elapsed:.1f}ms", "success")
            return 0
        else:
            cx_print(f"Ping failed: {response.error}", "error")
            return 1

    def _daemon_shutdown(self) -> int:
        """Request daemon shutdown via IPC."""
        cx_header("Requesting Daemon Shutdown")

        success, response = self._daemon_ipc_call("shutdown", lambda c: c.shutdown())
        if not success:
            return 1

        if response.success:
            cx_print("Daemon shutdown requested successfully!", "success")
            return 0
        cx_print(f"Failed to request shutdown: {response.error}", "error")
        return 1

    def _daemon_run_tests(self, args: argparse.Namespace) -> int:
        """Run the daemon test suite."""
        import subprocess

        cx_header("Daemon Tests")

        # Initialize audit logging
        history = InstallationHistory()
        start_time = datetime.now(timezone.utc)
        install_id = None

        try:
            # Record operation start
            install_id = history.record_installation(
                InstallationType.CONFIG,
                ["cortexd"],
                ["daemon.run-tests"],
                start_time,
            )
        except Exception:
            # Continue even if audit logging fails
            pass

        # Find daemon directory
        daemon_dir = Path(__file__).parent.parent / "daemon"
        build_dir = daemon_dir / "build"
        tests_dir = build_dir / "tests"  # Test binaries are in build/tests/

        # Define test binaries
        unit_tests = [
            "test_config",
            "test_protocol",
            "test_rate_limiter",
            "test_logger",
            "test_common",
        ]
        integration_tests = ["test_ipc_server", "test_handlers", "test_daemon"]
        all_tests = unit_tests + integration_tests

        # Check if tests are built
        def check_tests_built() -> tuple[bool, list[str]]:
            """Check which test binaries exist."""
            existing = []
            for test in all_tests:
                if (tests_dir / test).exists():
                    existing.append(test)
            return len(existing) > 0, existing

        tests_built, existing_tests = check_tests_built()

        if not tests_built:
            error_msg = "Tests are not built."
            cx_print(error_msg, "warning")
            cx_print("", "info")
            cx_print("To build tests, run the setup wizard with test building enabled:", "info")
            cx_print("", "info")
            cx_print("  [bold]python daemon/scripts/setup_daemon.py[/bold]", "info")
            cx_print("", "info")
            cx_print("When prompted, answer 'yes' to build the test suite.", "info")
            cx_print("", "info")
            cx_print("Or build manually:", "info")
            cx_print("  cd daemon && ./scripts/build.sh Release --with-tests", "dim")
            if install_id:
                try:
                    history.update_installation(install_id, InstallationStatus.FAILED, error_msg)
                except Exception:
                    # Continue even if audit logging fails - don't break the main flow
                    pass
            return 1

        # Determine which tests to run
        test_filter = getattr(args, "test", None)
        run_unit = getattr(args, "unit", False)
        run_integration = getattr(args, "integration", False)
        verbose = getattr(args, "verbose", False)

        tests_to_run = []

        if test_filter:
            # Run a specific test
            # Allow partial matching (e.g., "config" matches "test_config")
            test_name = test_filter if test_filter.startswith("test_") else f"test_{test_filter}"
            if test_name in existing_tests:
                tests_to_run = [test_name]
            else:
                error_msg = f"Test '{test_filter}' not found or not built."
                cx_print(error_msg, "error")
                cx_print("", "info")
                cx_print("Available tests:", "info")
                for t in existing_tests:
                    cx_print(f"  • {t}", "info")
                if install_id:
                    try:
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                    except Exception:
                        # Continue even if audit logging fails - don't break the main flow
                        pass
                return 1
        elif run_unit and not run_integration:
            tests_to_run = [t for t in unit_tests if t in existing_tests]
            if not tests_to_run:
                error_msg = "No unit tests built."
                cx_print(error_msg, "warning")
                if install_id:
                    try:
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                    except Exception:
                        # Continue even if audit logging fails - don't break the main flow
                        pass
                return 1
        elif run_integration and not run_unit:
            tests_to_run = [t for t in integration_tests if t in existing_tests]
            if not tests_to_run:
                error_msg = "No integration tests built."
                cx_print(error_msg, "warning")
                if install_id:
                    try:
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                    except Exception:
                        # Continue even if audit logging fails - don't break the main flow
                        pass
                return 1
        else:
            # Run all available tests
            tests_to_run = existing_tests

        # Show what we're running
        cx_print(f"Running {len(tests_to_run)} test(s)...", "info")
        cx_print("", "info")

        # Use ctest for running tests
        ctest_args = ["ctest", "--output-on-failure"]

        if verbose:
            ctest_args.append("-V")

        # Filter specific tests if not running all
        if test_filter or run_unit or run_integration:
            # ctest uses -R for regex filtering
            test_regex = "|".join(tests_to_run)
            ctest_args.extend(["-R", test_regex])

        try:
            result = subprocess.run(
                ctest_args,
                cwd=str(build_dir),
                check=False,
            )

            if result.returncode == 0:
                cx_print("", "info")
                cx_print("All tests passed!", "success")
                if install_id:
                    try:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                    except Exception:
                        # Continue even if audit logging fails - don't break the main flow
                        pass
                return 0
            else:
                error_msg = f"Test execution failed with return code {result.returncode}"
                cx_print("", "info")
                cx_print("Some tests failed.", "error")
                if install_id:
                    try:
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                    except Exception:
                        # Continue even if audit logging fails - don't break the main flow
                        pass
                return 1
        except subprocess.SubprocessError as e:
            error_msg = f"Subprocess error during test execution: {str(e)}"
            cx_print(error_msg, "error")
            self._update_history_on_failure(history, install_id, error_msg)
            return 1
        except Exception as e:
            error_msg = f"Unexpected error during test execution: {str(e)}"
            cx_print(error_msg, "error")
            self._update_history_on_failure(history, install_id, error_msg)
            return 1

    def benchmark(self, verbose: bool = False):
        """Run AI performance benchmark and display scores"""
        from cortex.benchmark import run_benchmark

        return run_benchmark(verbose=verbose)

    def systemd(self, service: str, action: str = "status", verbose: bool = False):
        """Systemd service helper with plain English explanations"""
        from cortex.systemd_helper import run_systemd_helper

        return run_systemd_helper(service, action, verbose)

    def gpu(self, action: str = "status", mode: str = None, verbose: bool = False):
        """Hybrid GPU (Optimus) manager"""
        from cortex.gpu_manager import run_gpu_manager

        return run_gpu_manager(action, mode, verbose)

    def printer(self, action: str = "status", verbose: bool = False):
        """Printer/Scanner auto-setup"""
        from cortex.printer_setup import run_printer_setup

        return run_printer_setup(action, verbose)

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
            confirm = StdinHandler.get_input(
                f"⚠️  Clear ALL environment variables for '{app}'? (y/n): "
            )
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
        confirm = StdinHandler.get_input(f"\nInstall all {total} packages? [Y/n]: ")
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
            self._print_error(self.INSTALL_FAIL_MSG)
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
                self._print_error(f"\n{self.INSTALL_FAIL_MSG} at step {result.failed_step + 1}")
            else:
                self._print_error(f"\n{self.INSTALL_FAIL_MSG}")
            if result.error_message:
                console.print(f"Error: {result.error_message}", style="red")
            return 1

    def doctor(self) -> int:
        """Run system health checks."""
        from cortex.doctor import SystemDoctor

        doc = SystemDoctor()
        return doc.run_checks()

    def troubleshoot(self, no_execute: bool = False) -> int:
        """Run interactive troubleshooter."""
        from cortex.troubleshoot import Troubleshooter

        troubleshooter = Troubleshooter(no_execute=no_execute)
        return troubleshooter.start()

    # --------------------------


def _is_ascii(s: str) -> bool:
    """Check if a string contains only ASCII characters."""
    try:
        s.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _normalize_for_lookup(s: str) -> str:
    """
    Normalize a string for lookup, handling Latin and non-Latin scripts differently.

    For ASCII/Latin text: casefold for case-insensitive matching (handles accented chars)
    For non-Latin text (e.g., 中文): keep unchanged to preserve meaning

    Uses casefold() instead of lower() because:
    - casefold() handles accented Latin characters better (e.g., "Español", "Français")
    - casefold() is more aggressive and handles edge cases like German ß -> ss

    This prevents issues like:
    - "中文".lower() producing the same string but creating duplicate keys
    - Meaningless normalization of non-Latin scripts
    """
    if _is_ascii(s):
        return s.casefold()
    # For non-ASCII Latin scripts (accented chars like é, ñ, ü), use casefold
    # Only keep unchanged for truly non-Latin scripts (CJK, Arabic, etc.)
    try:
        # Check if string contains any Latin characters (a-z, A-Z, or accented)
        # If it does, it's likely a Latin-based language name
        import unicodedata

        has_latin = any(unicodedata.category(c).startswith("L") and ord(c) < 0x3000 for c in s)
        if has_latin:
            return s.casefold()
    except Exception:
        pass
    return s


def _resolve_language_name(name: str) -> str | None:
    """
    Resolve a language name or code to a supported language code.

    Accepts:
    - Language codes: en, es, fr, de, zh
    - English names: English, Spanish, French, German, Chinese
    - Native names: Español, Français, Deutsch, 中文

    Args:
        name: Language name or code (case-insensitive for Latin scripts)

    Returns:
        Language code if found, None otherwise

    Note:
        Non-Latin scripts (e.g., Chinese 中文) are matched exactly without
        case normalization, since .lower() is meaningless for these scripts
        and could create key collisions.
    """
    name = name.strip()
    name_normalized = _normalize_for_lookup(name)

    # Direct code match (codes are always ASCII/lowercase)
    if name_normalized in SUPPORTED_LANGUAGES:
        return name_normalized

    # Build lookup tables for names
    # Using a list of tuples to handle potential key collisions properly
    name_to_code: dict[str, str] = {}

    for code, info in SUPPORTED_LANGUAGES.items():
        english_name = info["name"]
        native_name = info["native"]

        # English names are always ASCII, use casefold for case-insensitive matching
        name_to_code[english_name.casefold()] = code

        # Native names: normalize using _normalize_for_lookup
        # - Latin scripts (Español, Français): casefold for case-insensitive matching
        # - Non-Latin scripts (中文): store as-is only
        native_normalized = _normalize_for_lookup(native_name)
        name_to_code[native_normalized] = code

        # Also store original native name for exact match
        # (handles case where user types exactly "Español" with correct accent)
        if native_name != native_normalized:
            name_to_code[native_name] = code

    # Try to find a match using normalized input
    if name_normalized in name_to_code:
        return name_to_code[name_normalized]

    # Try exact match for non-ASCII input
    if name in name_to_code:
        return name_to_code[name]

    return None


def _handle_set_language(language_input: str) -> int:
    """
    Handle the --set-language global flag.

    Args:
        language_input: Language name or code from user

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Resolve the language name to a code
    lang_code = _resolve_language_name(language_input)

    if not lang_code:
        # Show error with available options
        cx_print(t("language.invalid_code", code=language_input), "error")
        console.print()
        console.print(f"[bold]{t('language.supported_languages_header')}[/bold]")
        for code, info in SUPPORTED_LANGUAGES.items():
            console.print(f"  • {info['name']} ({info['native']}) - code: [green]{code}[/green]")
        return 1

    # Set the language
    try:
        lang_config = LanguageConfig()
        lang_config.set_language(lang_code)

        # Reset and update global translator
        from cortex.i18n.translator import reset_translator

        reset_translator()
        set_language(lang_code)

        lang_info = SUPPORTED_LANGUAGES[lang_code]
        cx_print(t("language.changed", language=lang_info["native"]), "success")
        return 0
    except Exception as e:
        cx_print(t("language.set_failed", error=str(e)), "error")
        return 1

    def dashboard(self) -> int:
        """Launch the real-time system monitoring dashboard"""
        try:
            from cortex.dashboard import DashboardApp

            app = DashboardApp()
            rc = app.run()
            return rc if isinstance(rc, int) else 0
        except ImportError as e:
            self._print_error(f"Dashboard dependencies not available: {e}")
            cx_print("Install required packages with:", "info")
            cx_print("  pip install psutil>=5.9.0 nvidia-ml-py>=12.0.0", "info")
            return 1
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            self._print_error(f"Dashboard error: {e}")
            return 1


def show_rich_help():
    """Display a beautifully formatted help table using the Rich library.

    This function outputs the primary command menu, providing descriptions
    for all core Cortex utilities including installation, environment
    management, and container tools.
    """

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
    table.add_row("voice", "Voice input mode (F9 to speak)")
    table.add_row("demo", "See Cortex in action")
    table.add_row("wizard", "Configure API key")
    table.add_row("status", "System status")
    table.add_row("install <pkg>", "Install software")
    table.add_row("remove <pkg>", "Remove packages with impact analysis")
    table.add_row("install --mic", "Install via voice input")
    table.add_row("import <file>", "Import deps from package files")
    table.add_row("history", "View history")
    table.add_row("rollback <id>", "Undo installation")
    table.add_row("role", "AI-driven system role detection")
    table.add_row("stack <name>", "Install the stack")
    table.add_row("dashboard", "Real-time system monitoring dashboard")
    table.add_row("notify", "Manage desktop notifications")
    table.add_row("env", "Manage environment variables")
    table.add_row("cache stats", "Show LLM cache statistics")
    table.add_row("docker permissions", "Fix Docker bind-mount permissions")
    table.add_row("sandbox <cmd>", "Test packages in Docker sandbox")
    table.add_row("update", "Check for and install updates")
    table.add_row("daemon <cmd>", "Manage the cortexd background daemon")
    table.add_row("doctor", "System health check")
    table.add_row("troubleshoot", "Interactive system troubleshooter")

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

    # Check for updates on startup (cached, non-blocking)
    # Only show notification for commands that aren't 'update' itself
    try:
        if temp_args.command not in ["update", None] and "--json" not in sys.argv:
            update_release = should_notify_update()
            if update_release:
                console.print(
                    f"[cyan]🔔 Cortex update available:[/cyan] "
                    f"[green]{update_release.version}[/green]"
                )
                console.print("   [dim]Run 'cortex update' to upgrade[/dim]")
                console.print()
    except Exception:
        pass  # Don't block CLI on update check failures

    parser = argparse.ArgumentParser(
        prog="cortex",
        description="AI-powered Linux command interpreter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global flags
    parser.add_argument("--version", "-V", action="version", version=f"cortex {VERSION}")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument(
        "--set-language",
        "--language",
        dest="set_language",
        metavar="LANG",
        help="Set display language (e.g., English, Spanish, Español, es, zh)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Define the docker command and its associated sub-actions
    docker_parser = subparsers.add_parser("docker", help="Docker and container utilities")
    docker_subs = docker_parser.add_subparsers(dest="docker_action", help="Docker actions")

    # Add the permissions action to allow fixing file ownership issues
    perm_parser = docker_subs.add_parser(
        "permissions", help="Fix file permissions from bind mounts"
    )

    # Provide an option to skip the manual confirmation prompt
    perm_parser.add_argument("--yes", "-y", action="store_true", help=HELP_SKIP_CONFIRM)

    perm_parser.add_argument(
        "--execute", "-e", action="store_true", help="Apply ownership changes (default: dry-run)"
    )

    # Demo command
    subparsers.add_parser("demo", help="See Cortex in action")

    # Dashboard command
    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Real-time system monitoring dashboard"
    )

    # Wizard command
    subparsers.add_parser("wizard", help="Configure API key interactively")

    # Status command (includes comprehensive health checks)
    subparsers.add_parser("status", help="Show comprehensive system status and health checks")

    # Benchmark command
    benchmark_parser = subparsers.add_parser("benchmark", help="Run AI performance benchmark")
    benchmark_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # Systemd helper command
    systemd_parser = subparsers.add_parser("systemd", help="Systemd service helper (plain English)")
    systemd_parser.add_argument("service", help="Service name")
    systemd_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "diagnose", "deps"],
        help="Action: status (default), diagnose, deps",
    )
    systemd_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # GPU manager command
    gpu_parser = subparsers.add_parser("gpu", help="Hybrid GPU (Optimus) manager")
    gpu_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "modes", "switch", "apps"],
        help="Action: status (default), modes, switch, apps",
    )
    gpu_parser.add_argument(
        "mode", nargs="?", help="Mode for switch action (integrated/hybrid/nvidia)"
    )
    gpu_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # Printer/Scanner setup command
    printer_parser = subparsers.add_parser("printer", help="Printer/Scanner auto-setup")
    printer_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "detect"],
        help="Action: status (default), detect",
    )
    printer_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # Ask command
    ask_parser = subparsers.add_parser("ask", help="Ask a question about your system")
    ask_parser.add_argument("question", nargs="?", type=str, help="Natural language question")
    ask_parser.add_argument(
        "--mic",
        action="store_true",
        help="Use voice input (press F9 to record)",
    )

    # Voice command - continuous voice mode
    voice_parser = subparsers.add_parser(
        "voice", help="Voice input mode (F9 to speak, Ctrl+C to exit)"
    )
    voice_parser.add_argument(
        "--single",
        "-s",
        action="store_true",
        help="Record single input and exit (default: continuous mode)",
    )
    voice_parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        metavar="MODEL",
        choices=[
            "tiny.en",
            "base.en",
            "small.en",
            "medium.en",
            "tiny",
            "base",
            "small",
            "medium",
            "large",
        ],
        help="Whisper model to use (default: base.en or CORTEX_WHISPER_MODEL env var). "
        "Available models: tiny.en (39MB), base.en (140MB), small.en (466MB), "
        "medium.en (1.5GB), tiny/base/small/medium (multilingual), large (6GB).",
    )

    # Install command
    install_parser = subparsers.add_parser("install", help="Install software")
    install_parser.add_argument("software", nargs="?", type=str, help="Software to install")
    install_parser.add_argument("--execute", action="store_true", help="Execute commands")
    install_parser.add_argument("--dry-run", action="store_true", help="Show commands only")
    install_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel execution for multi-step installs",
    )
    install_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    install_parser.add_argument(
        "--mic",
        action="store_true",
        help="Use voice input for software name (press F9 to record)",
    )

    # Remove command - uninstall with impact analysis
    remove_parser = subparsers.add_parser(
        "remove",
        help="Remove packages with impact analysis",
        description="Analyze and remove packages safely with dependency impact analysis.",
    )
    remove_parser.add_argument("package", type=str, help="Package to remove")
    remove_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show impact analysis without removing (default)",
    )
    remove_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually remove the package after analysis",
    )
    remove_parser.add_argument(
        "--purge",
        action="store_true",
        help="Also remove configuration files",
    )
    remove_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force removal even if impact is high",
    )
    remove_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help=HELP_SKIP_CONFIRM,
    )
    remove_parser.add_argument(
        "--json",
        action="store_true",
        help="Output impact analysis as JSON",
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

    # Role Management Commands
    # This parser defines the primary interface for system personality and contextual sensing.
    role_parser = subparsers.add_parser(
        "role", help="AI-driven system personality and context management"
    )
    role_subs = role_parser.add_subparsers(dest="role_action", help="Role actions")

    # Subcommand: role detect
    # Dynamically triggers the sensing layer to analyze system context and suggest roles.
    role_subs.add_parser(
        "detect", help="Dynamically sense system context and shell patterns to suggest an AI role"
    )

    # Subcommand: role set <slug>
    # Allows manual override for role persistence and provides tailored recommendations.
    role_set_parser = role_subs.add_parser(
        "set", help="Manually override the system role and receive tailored recommendations"
    )
    role_set_parser.add_argument(
        "role_slug",
        help="The role identifier (e.g., 'data-scientist', 'web-server', 'ml-workstation')",
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

    # --- Config commands (including language settings) ---
    config_parser = subparsers.add_parser("config", help="Configure Cortex settings")
    config_subs = config_parser.add_subparsers(dest="config_action", help="Configuration actions")

    # config language <code> - set language
    config_lang_parser = config_subs.add_parser("language", help="Set display language")
    config_lang_parser.add_argument(
        "code",
        nargs="?",
        help="Language code (en, es, fr, de, zh) or 'auto' for auto-detection",
    )
    config_lang_parser.add_argument(
        "--list", "-l", action="store_true", help="List available languages"
    )
    config_lang_parser.add_argument(
        "--info", "-i", action="store_true", help="Show current language configuration"
    )

    # config show - show all configuration
    config_subs.add_parser("show", help="Show all current configuration")

    # --- Daemon Commands ---
    daemon_parser = subparsers.add_parser("daemon", help="Manage the cortexd background daemon")
    daemon_subs = daemon_parser.add_subparsers(dest="daemon_action", help="Daemon actions")

    # daemon install [--execute]
    daemon_install_parser = daemon_subs.add_parser(
        "install", help="Install and enable the daemon service"
    )
    daemon_install_parser.add_argument(
        "--execute", action="store_true", help="Actually run the installation"
    )

    # daemon uninstall [--execute]
    daemon_uninstall_parser = daemon_subs.add_parser(
        "uninstall", help="Stop and remove the daemon service"
    )
    daemon_uninstall_parser.add_argument(
        "--execute", action="store_true", help="Actually run the uninstallation"
    )

    # daemon config - uses config.get IPC handler
    daemon_subs.add_parser("config", help="Show current daemon configuration")

    # daemon reload-config - uses config.reload IPC handler
    daemon_subs.add_parser("reload-config", help="Reload daemon configuration from disk")

    # daemon version - uses version IPC handler
    daemon_subs.add_parser("version", help="Show daemon version")

    # daemon ping - uses ping IPC handler
    daemon_subs.add_parser("ping", help="Test daemon connectivity")

    # daemon shutdown - uses shutdown IPC handler
    daemon_subs.add_parser("shutdown", help="Request daemon shutdown")

    # daemon run-tests - run daemon test suite
    daemon_run_tests_parser = daemon_subs.add_parser(
        "run-tests",
        help="Run daemon test suite (runs all tests by default when no filters are provided)",
    )
    daemon_run_tests_parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    daemon_run_tests_parser.add_argument(
        "--integration", action="store_true", help="Run only integration tests"
    )
    daemon_run_tests_parser.add_argument(
        "--test",
        "-t",
        type=str,
        metavar="NAME",
        help="Run a specific test (e.g., test_config, test_daemon)",
    )
    daemon_run_tests_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show verbose test output"
    )
    # --------------------------

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
    sandbox_promote_parser.add_argument("-y", "--yes", action="store_true", help=HELP_SKIP_CONFIRM)

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

    # Doctor command
    doctor_parser = subparsers.add_parser("doctor", help="System health check")

    # Troubleshoot command
    troubleshoot_parser = subparsers.add_parser(
        "troubleshoot", help="Interactive system troubleshooter"
    )
    troubleshoot_parser.add_argument(
        "--no-execute",
        action="store_true",
        help="Disable automatic command execution (read-only mode)",
    )
    # License and upgrade commands
    subparsers.add_parser("upgrade", help="Upgrade to Cortex Pro")
    subparsers.add_parser("license", help="Show license status")

    activate_parser = subparsers.add_parser("activate", help="Activate a license key")
    activate_parser.add_argument("license_key", help="Your license key")

    # --- Update Command ---
    update_parser = subparsers.add_parser("update", help="Check for and install Cortex updates")
    update_parser.add_argument(
        "--channel",
        "-c",
        choices=["stable", "beta", "dev"],
        default="stable",
        help="Update channel (default: stable)",
    )
    update_subs = update_parser.add_subparsers(dest="update_action", help="Update actions")

    # update check
    update_check_parser = update_subs.add_parser("check", help="Check for available updates")

    # update install [version] [--dry-run]
    update_install_parser = update_subs.add_parser("install", help="Install available update")
    update_install_parser.add_argument(
        "version", nargs="?", help="Specific version to install (default: latest)"
    )
    update_install_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be updated without installing"
    )

    # update rollback [backup_id]
    update_rollback_parser = update_subs.add_parser("rollback", help="Rollback to previous version")
    update_rollback_parser.add_argument(
        "backup_id", nargs="?", help="Backup ID or version to restore (default: most recent)"
    )

    # update list
    update_subs.add_parser("list", help="List available versions")

    # update backups
    update_subs.add_parser("backups", help="List available backups for rollback")
    # --------------------------

    # WiFi/Bluetooth Driver Matcher
    wifi_parser = subparsers.add_parser("wifi", help="WiFi/Bluetooth driver auto-matcher")
    wifi_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "detect", "recommend", "install", "connectivity"],
        help="Action to perform (default: status)",
    )
    wifi_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    # Stdin Piping Support
    stdin_parser = subparsers.add_parser("stdin", help="Process piped stdin data")
    stdin_parser.add_argument(
        "action",
        nargs="?",
        default="info",
        choices=["info", "analyze", "passthrough", "stats"],
        help="Action to perform (default: info)",
    )
    stdin_parser.add_argument(
        "--max-lines",
        type=int,
        default=1000,
        help="Maximum lines to process (default: 1000)",
    )
    stdin_parser.add_argument(
        "--truncation",
        choices=["head", "tail", "middle", "sample"],
        default="middle",
        help="Truncation mode for large input (default: middle)",
    )
    stdin_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    # Semantic Version Resolver
    deps_parser = subparsers.add_parser("deps", help="Dependency version resolver")
    deps_parser.add_argument(
        "action",
        nargs="?",
        default="analyze",
        choices=["analyze", "parse", "check", "compare"],
        help="Action to perform (default: analyze)",
    )
    deps_parser.add_argument(
        "packages",
        nargs="*",
        help="Package constraints (format: pkg:constraint:source)",
    )
    deps_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    # System Health Score
    health_parser = subparsers.add_parser("health", help="System health score and recommendations")
    health_parser.add_argument(
        "action",
        nargs="?",
        default="check",
        choices=["check", "history", "factors", "quick"],
        help="Action to perform (default: check)",
    )
    health_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Configure logging based on parsed arguments
    if getattr(args, "json", False):
        logging.getLogger("cortex").setLevel(logging.ERROR)
        # Also suppress common SDK loggers
        logging.getLogger("anthropic").setLevel(logging.ERROR)
        logging.getLogger("openai").setLevel(logging.ERROR)
        logging.getLogger("httpcore").setLevel(logging.ERROR)

    # Handle --set-language global flag first (before any command)
    if getattr(args, "set_language", None):
        result = _handle_set_language(args.set_language)
        # Only return early if no command is specified
        # This allows: cortex --set-language es install nginx
        if not args.command:
            return result
        # If language setting failed, still return the error
        if result != 0:
            return result
        # Otherwise continue with the command execution

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
        elif args.command == "dashboard":
            return cli.dashboard()
        elif args.command == "wizard":
            return cli.wizard()
        elif args.command == "status":
            return cli.status()
        elif args.command == "benchmark":
            return cli.benchmark(verbose=getattr(args, "verbose", False))
        elif args.command == "systemd":
            return cli.systemd(
                args.service,
                action=getattr(args, "action", "status"),
                verbose=getattr(args, "verbose", False),
            )
        elif args.command == "gpu":
            return cli.gpu(
                action=getattr(args, "action", "status"),
                mode=getattr(args, "mode", None),
                verbose=getattr(args, "verbose", False),
            )
        elif args.command == "printer":
            return cli.printer(
                action=getattr(args, "action", "status"), verbose=getattr(args, "verbose", False)
            )
        elif args.command == "voice":
            model = getattr(args, "model", None)
            return cli.voice(continuous=not getattr(args, "single", False), model=model)
        elif args.command == "ask":
            # Handle --mic flag for voice input
            if getattr(args, "mic", False):
                try:
                    from cortex.voice import VoiceInputError, VoiceInputHandler

                    handler = VoiceInputHandler()
                    cx_print("Press F9 to speak your question...", "info")
                    transcript = handler.record_single()

                    if not transcript:
                        cli._print_error("No speech detected")
                        return 1

                    cx_print(f"Question: {transcript}", "info")
                    return cli.ask(transcript)
                except ImportError:
                    cli._print_error("Voice dependencies not installed.")
                    cx_print("Install with: pip install cortex-linux[voice]", "info")
                    return 1
                except VoiceInputError as e:
                    cli._print_error(f"Voice input error: {e}")
                    return 1
            if not args.question:
                cli._print_error("Please provide a question or use --mic for voice input")
                return 1
            return cli.ask(args.question)
        elif args.command == "install":
            # Handle --mic flag for voice input
            if getattr(args, "mic", False):
                handler = None
                try:
                    from cortex.voice import VoiceInputError, VoiceInputHandler

                    handler = VoiceInputHandler()
                    cx_print("Press F9 to speak what you want to install...", "info")
                    software = handler.record_single()
                    if not software:
                        cx_print("No speech detected.", "warning")
                        return 1
                    cx_print(f"Installing: {software}", "info")
                except ImportError:
                    cli._print_error("Voice dependencies not installed.")
                    cx_print("Install with: pip install cortex-linux[voice]", "info")
                    return 1
                except VoiceInputError as e:
                    cli._print_error(f"Voice input error: {e}")
                    return 1
                finally:
                    # Always clean up resources
                    if handler is not None:
                        try:
                            handler.stop()
                        except Exception as e:
                            # Log cleanup errors but don't raise
                            logging.debug("Error during voice handler cleanup: %s", e)
            else:
                software = args.software
                if not software:
                    cli._print_error("Please provide software name or use --mic for voice input")
                    return 1
            return cli.install(
                software,
                execute=args.execute,
                dry_run=args.dry_run,
                parallel=args.parallel,
                json_output=args.json,
            )
        elif args.command == "remove":
            # Handle --execute flag to override default dry-run
            if args.execute:
                args.dry_run = False
            return cli.remove(args)
        elif args.command == "import":
            return cli.import_deps(args)
        elif args.command == "history":
            return cli.history(limit=args.limit, status=args.status, show_id=args.show_id)
        elif args.command == "rollback":
            return cli.rollback(args.id, dry_run=args.dry_run)
        elif args.command == "role":
            return cli.role(args)
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
        elif args.command == "doctor":
            return cli.doctor()
        elif args.command == "troubleshoot":
            return cli.troubleshoot(
                no_execute=getattr(args, "no_execute", False),
            )
        elif args.command == "config":
            return cli.config(args)
        elif args.command == "upgrade":
            from cortex.licensing import open_upgrade_page

            open_upgrade_page()
            return 0
        elif args.command == "license":
            from cortex.licensing import show_license_status

            show_license_status()
            return 0
        elif args.command == "activate":
            from cortex.licensing import activate_license

            return 0 if activate_license(args.license_key) else 1
        elif args.command == "update":
            return cli.update(args)
        elif args.command == "daemon":
            return cli.daemon(args)
        elif args.command == "wifi":
            from cortex.wifi_driver import run_wifi_driver

            return run_wifi_driver(
                action=getattr(args, "action", "status"),
                verbose=getattr(args, "verbose", False),
            )
        elif args.command == "stdin":
            from cortex.stdin_handler import run_stdin_handler

            return run_stdin_handler(
                action=getattr(args, "action", "info"),
                max_lines=getattr(args, "max_lines", 1000),
                truncation=getattr(args, "truncation", "middle"),
                verbose=getattr(args, "verbose", False),
            )
        elif args.command == "deps":
            from cortex.semver_resolver import run_semver_resolver

            return run_semver_resolver(
                action=getattr(args, "action", "analyze"),
                packages=getattr(args, "packages", None),
                verbose=getattr(args, "verbose", False),
            )
        elif args.command == "health":
            from cortex.health_score import run_health_check

            return run_health_check(
                action=getattr(args, "action", "check"),
                verbose=getattr(args, "verbose", False),
            )
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
