try:
    from pathlib import Path

    from dotenv import load_dotenv
except ImportError:
    pass
"""
First-Run Wizard Module for Cortex Linux

Provides a seamless onboarding experience for new users, guiding them
through initial setup, configuration, and feature discovery.

"""

import json
import logging
import os
import random
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Import API key test utilities
from cortex.utils.api_key_test import test_anthropic_api_key, test_openai_api_key

# Examples for dry run prompts
DRY_RUN_EXAMPLES = [
    "Machine learning module",
    "libraries for video compression tool",
    "web development framework",
    "data analysis tools",
    "image processing library",
    "database management system",
    "text editor with plugins",
    "networking utilities",
    "game development engine",
    "scientific computing tools",
]


def detect_available_providers() -> list[str]:
    """Detect available providers based on API keys and installations."""
    providers = []
    if os.environ.get("ANTHROPIC_API_KEY") and os.environ.get(
        "ANTHROPIC_API_KEY"
    ).strip().startswith("sk-ant-"):
        providers.append("anthropic")
    if os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_API_KEY").strip().startswith(
        "sk-"
    ):
        providers.append("openai")
    if shutil.which("ollama"):
        providers.append("ollama")
    return providers


logger = logging.getLogger(__name__)


class WizardStep(Enum):
    """Steps in the first-run wizard."""

    WELCOME = "welcome"
    API_SETUP = "api_setup"
    HARDWARE_DETECTION = "hardware_detection"
    PREFERENCES = "preferences"
    SHELL_INTEGRATION = "shell_integration"
    TEST_COMMAND = "test_command"
    COMPLETE = "complete"


@dataclass
class WizardState:
    """Tracks the current state of the wizard."""

    current_step: WizardStep = WizardStep.WELCOME
    completed_steps: list[WizardStep] = field(default_factory=list)
    skipped_steps: list[WizardStep] = field(default_factory=list)
    collected_data: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    def mark_completed(self, step: WizardStep):
        """Mark a step as completed."""
        if step not in self.completed_steps:
            self.completed_steps.append(step)

    def mark_skipped(self, step: WizardStep):
        """Mark a step as skipped."""
        if step not in self.skipped_steps:
            self.skipped_steps.append(step)

    def is_completed(self, step: WizardStep) -> bool:
        """Check if a step is completed."""
        return step in self.completed_steps

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "current_step": self.current_step.value,
            "completed_steps": [s.value for s in self.completed_steps],
            "skipped_steps": [s.value for s in self.skipped_steps],
            "collected_data": self.collected_data,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WizardState":
        """Deserialize from dict."""
        return cls(
            current_step=WizardStep(data.get("current_step", "welcome")),
            completed_steps=[WizardStep(s) for s in data.get("completed_steps", [])],
            skipped_steps=[WizardStep(s) for s in data.get("skipped_steps", [])],
            collected_data=data.get("collected_data", {}),
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if data.get("started_at")
                else datetime.now()
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
        )


@dataclass
class StepResult:
    """Result of a wizard step."""

    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    next_step: WizardStep | None = None
    skip_to: WizardStep | None = None


class FirstRunWizard:
    def _install_suggested_packages(self):
        """Offer to install suggested packages and run the install if user agrees."""
        suggestions = ["python", "numpy", "requests"]
        print("\nTry installing a package to verify Cortex is ready:")
        for pkg in suggestions:
            print(f"  cortex install {pkg}")
        resp = self._prompt("Would you like to install these packages now? [Y/n]: ", default="y")
        if resp.strip().lower() in ("", "y", "yes"):
            env = os.environ.copy()
            for pkg in suggestions:
                print(f"\nInstalling {pkg}...")
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "cortex.cli", "install", pkg],
                        capture_output=True,
                        text=True,
                        env=env,
                    )
                    print(result.stdout)
                    if result.stderr:
                        print(result.stderr)
                except Exception as e:
                    print(f"Error installing {pkg}: {e}")

    def _setup_claude_api(self) -> StepResult:
        print("\nTo get a Claude API key:")
        print("  1. Go to https://console.anthropic.com")
        print("  2. Sign up or log in")
        print("  3. Create an API key\n")
        api_key = self._prompt("Enter your Claude API key: ")
        if not api_key or not api_key.startswith("sk-"):
            print("\n⚠ Invalid API key format")
            return StepResult(success=True, data={"api_provider": "none"})
        self._save_env_var("ANTHROPIC_API_KEY", api_key)
        self.config["api_provider"] = "anthropic"
        self.config["api_key_configured"] = True
        print("\n✓ Claude API key saved!")
        if self.interactive:
            do_test = self._prompt(
                "Would you like to test your Claude API key now? [Y/n]: ", default="y"
            )
            if do_test.strip().lower() in ("", "y", "yes"):
                print("\nTesting Claude API key...")
                if test_anthropic_api_key(api_key):
                    print("\n✅ Claude API key is valid and working!")
                    resp = self._prompt(
                        "Would you like some package suggestions to try? [Y/n]: ", default="y"
                    )
                    if resp.strip().lower() in ("", "y", "yes"):
                        self._install_suggested_packages()
                else:
                    print("\n❌ Claude API key test failed. Please check your key or network.")
        return StepResult(success=True, data={"api_provider": "anthropic"})

    def _setup_openai_api(self) -> StepResult:
        print("\nTo get an OpenAI API key:")
        print("  1. Go to https://platform.openai.com")
        print("  2. Sign up or log in")
        print("  3. Create an API key\n")
        api_key = self._prompt("Enter your OpenAI API key: ")
        if not api_key or not api_key.startswith("sk-"):
            print("\n⚠ Invalid API key format")
            return StepResult(success=True, data={"api_provider": "none"})
        self._save_env_var("OPENAI_API_KEY", api_key)
        self.config["api_provider"] = "openai"
        self.config["api_key_configured"] = True
        print("\n✓ OpenAI API key saved!")
        if self.interactive:
            do_test = self._prompt(
                "Would you like to test your OpenAI API key now? [Y/n]: ", default="y"
            )
            if do_test.strip().lower() in ("", "y", "yes"):
                print("\nTesting OpenAI API key...")
                if test_openai_api_key(api_key):
                    print("\n✅ OpenAI API key is valid and working!")
                    resp = self._prompt(
                        "Would you like some package suggestions to try? [Y/n]: ", default="y"
                    )
                    if resp.strip().lower() in ("", "y", "yes"):
                        self._install_suggested_packages()
                else:
                    print("\n❌ OpenAI API key test failed. Please check your key or network.")
        return StepResult(success=True, data={"api_provider": "openai"})

    def _setup_ollama(self) -> StepResult:
        print("\nOllama selected. No API key required.")
        self.config["api_provider"] = "ollama"
        return StepResult(success=True, data={"api_provider": "ollama"})

    """
    Interactive first-run wizard for Cortex Linux.

    Guides users through:
    1. Welcome and introduction
    2. API key setup
    3. Hardware detection
    4. User preferences
    5. Shell integration
    6. Test command
    """

    CONFIG_DIR = Path.home() / ".cortex"
    STATE_FILE = CONFIG_DIR / "wizard_state.json"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    SETUP_COMPLETE_FILE = CONFIG_DIR / ".setup_complete"

    def __init__(self, interactive: bool = True):
        self.interactive = interactive
        self.state = WizardState()
        self.config: dict[str, Any] = {}
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """Ensure config directory exists."""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def needs_setup(self) -> bool:
        """Check if first-run setup is needed."""
        return not self.SETUP_COMPLETE_FILE.exists()

    def load_state(self) -> bool:
        """Load wizard state from file."""
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE) as f:
                    data = json.load(f)
                    self.state = WizardState.from_dict(data)
                    return True
            except Exception as e:
                logger.warning(f"Could not load wizard state: {e}")
        return False

    def save_state(self):
        """Save wizard state to file."""
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(self.state.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save wizard state: {e}")

    def save_config(self):
        """Save configuration to file."""
        try:
            with open(self.CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save config: {e}")

    def mark_setup_complete(self):
        """Mark setup as complete."""
        self.SETUP_COMPLETE_FILE.touch()
        self.state.completed_at = datetime.now()
        self.save_state()

    def run(self) -> bool:
        """
        Refactored onboarding: detect available providers, auto-select if one, show menu if multiple, validate lazily, save provider.
        """
        self._clear_screen()
        self._print_banner()

        # Load current config to get existing provider
        current_config = get_config()
        current_provider = current_config.get("api_provider")

        # Detect available providers
        available_providers = detect_available_providers()

        if not available_providers:
            print("\nNo API keys or local AI found.")
            print("Please export your API key in your shell profile:")
            print("  For OpenAI: export OPENAI_API_KEY=sk-...")
            print("  For Anthropic: export ANTHROPIC_API_KEY=sk-ant-...")
            print("  Or install Ollama: https://ollama.ai")
            return False

        if len(available_providers) == 1:
            provider = available_providers[0]
            provider_names = {
                "anthropic": "Anthropic (Claude)",
                "openai": "OpenAI",
                "ollama": "Ollama (local)",
            }
            print(f"\nAuto-selected provider: {provider_names.get(provider, provider)}")
        else:
            # Show menu with available marked
            print("\nSelect your preferred LLM provider:")
            if current_provider:
                provider_names = {
                    "anthropic": "Anthropic (Claude)",
                    "openai": "OpenAI",
                    "ollama": "Ollama (local)",
                }
                print(f"Current provider: {provider_names.get(current_provider, current_provider)}")
            if current_provider:
                options = [
                    ("1. Keep current provider (skip setup)", "skip"),
                    ("2. Anthropic (Claude)", "anthropic"),
                    ("3. OpenAI", "openai"),
                    ("4. Ollama (local)", "ollama"),
                ]
            else:
                options = [
                    ("1. Anthropic (Claude)", "anthropic"),
                    ("2. OpenAI", "openai"),
                    ("3. Ollama (local)", "ollama"),
                ]
            for opt, prov in options:
                status = " ✓" if prov in available_providers else ""
                if prov == current_provider:
                    status += " (current)"
                print(f"{opt}{status}")
            default_choice = "1"
            choice_prompt = (
                "Choose a provider [1-3]: " if not current_provider else "Choose a provider [1-4]: "
            )
            choice = self._prompt(
                choice_prompt,
                default=default_choice,
            )
            if current_provider:
                provider_map = {"1": "skip", "2": "anthropic", "3": "openai", "4": "ollama"}
            else:
                provider_map = {"1": "anthropic", "2": "openai", "3": "ollama"}
            provider = provider_map.get(choice)
            if provider == "skip":
                print("Setup skipped. Your current configuration is unchanged.")
                return True
            if not provider or provider not in available_providers:
                print("Invalid choice or provider not available.")
                return False

        # Validate and prompt for key lazily
        if provider == "anthropic":
            key = os.environ.get("ANTHROPIC_API_KEY")
            if key:
                key = key.strip()
            while not key or not key.startswith("sk-ant-"):
                print("\nNo valid Anthropic API key found.")
                key = self._prompt("Enter your Claude (Anthropic) API key: ")
                if key and key.startswith("sk-ant-"):
                    self._save_env_var("ANTHROPIC_API_KEY", key)
                    os.environ["ANTHROPIC_API_KEY"] = key
            random_example = random.choice(DRY_RUN_EXAMPLES)
            do_test = self._prompt(
                f'Would you like to perform a real dry run (install "{random_example}") to test your Claude setup? [Y/n]: ',
                default="y",
            )
            if do_test.strip().lower() in ("", "y", "yes"):
                print(f'\nRunning: cortex install "{random_example}" (dry run)...')
                try:
                    # Import cli here to avoid circular import
                    from cortex.cli import CortexCLI

                    cli = CortexCLI()
                    result = cli.install(
                        random_example, execute=False, dry_run=True, forced_provider="claude"
                    )
                    if result != 0:
                        print(
                            "\n❌ Dry run failed for Anthropic provider. Please check your API key and network."
                        )
                        return False
                except Exception as e:
                    print(f"Error during dry run: {e}")
                    return False
        elif provider == "openai":
            key = os.environ.get("OPENAI_API_KEY")
            if key:
                key = key.strip()
                if key.startswith("sk-") and test_openai_api_key(key):
                    # Valid existing key, proceed
                    pass
                else:
                    key = None
            while not key or not key.startswith("sk-"):
                print("\nNo valid OpenAI API key found.")
                key = self._prompt("Enter your OpenAI API key: ")
                if key and key.startswith("sk-") and test_openai_api_key(key):
                    self._save_env_var("OPENAI_API_KEY", key)
                    os.environ["OPENAI_API_KEY"] = key
                else:
                    print("Invalid API key. Please try again.")
                    key = None
            random_example = random.choice(DRY_RUN_EXAMPLES)
            do_test = self._prompt(
                f'Would you like to perform a real dry run (install "{random_example}") to test your OpenAI setup? [Y/n]: ',
                default="y",
            )
            if do_test.strip().lower() in ("", "y", "yes"):
                print(f'\nRunning: cortex install "{random_example}" (dry run)...')
                try:
                    # Import cli here to avoid circular import
                    from cortex.cli import CortexCLI

                    cli = CortexCLI()
                    result = cli.install(
                        random_example, execute=False, dry_run=True, forced_provider="openai"
                    )
                    if result != 0:
                        print(
                            "\n❌ Dry run failed for OpenAI provider. Please check your API key and network."
                        )
                        return False
                except Exception as e:
                    print(f"Error during dry run: {e}")
                    return False
        elif provider == "ollama":
            print("Ollama detected and ready.")

        # Save provider
        self.config["api_provider"] = provider
        self.save_config()
        self.mark_setup_complete()

        # Success message
        print(f"\n[✔] Setup complete! Provider '{provider}' is ready for AI workloads.")
        print("You can rerun this wizard anytime to change your provider.")
        return True

    def _step_welcome(self) -> StepResult:
        """Welcome step with introduction."""
        self._clear_screen()
        self._print_banner()

        print(
            """
Welcome to Cortex Linux! 🚀

Cortex is an AI-powered package manager that understands natural language.
Instead of memorizing apt commands, just tell Cortex what you want:

  $ cortex install a web server
  $ cortex setup python for machine learning
  $ cortex remove unused packages

This wizard will help you set up Cortex in just a few minutes.
"""
        )

        if self.interactive:
            response = self._prompt("Press Enter to continue (or 'q' to quit): ")
            if response.lower() == "q":
                return StepResult(success=False, message="User cancelled")

        return StepResult(success=True)

    def _step_api_setup(self) -> StepResult:
        """API key configuration step."""
        self._clear_screen()
        self._print_header("Step 1: API Configuration")

        # Check for existing API keys
        existing_claude = os.environ.get("ANTHROPIC_API_KEY")
        existing_openai = os.environ.get("OPENAI_API_KEY")

        # Build menu with indicators for existing keys
        claude_status = " ✓ (key found)" if existing_claude else ""
        openai_status = " ✓ (key found)" if existing_openai else ""

        print(
            f"""
Cortex uses AI to understand your commands. You can use:

  1. Claude API (Anthropic){claude_status} - Recommended
  2. OpenAI API{openai_status}
  3. Local LLM (Ollama) - Free, runs on your machine
  4. Skip for now (limited functionality)
"""
        )

        if not self.interactive:
            # In non-interactive mode, auto-select if key exists
            if existing_claude:
                self.config["api_provider"] = "anthropic"
                self.config["api_key_configured"] = True
                return StepResult(success=True, data={"api_provider": "anthropic"})
            if existing_openai:
                self.config["api_provider"] = "openai"
                self.config["api_key_configured"] = True
                return StepResult(success=True, data={"api_provider": "openai"})
            return StepResult(
                success=True,
                message="Non-interactive mode - skipping API setup",
                data={"api_provider": "none"},
            )

        # Always let user choose
        choice = self._prompt("Choose an option [1-4]: ", default="1")

        if choice == "1":
            if existing_claude:
                print("\n✓ Using existing Claude API key!")
                # Prompt for dry run even if key exists
                if self.interactive:
                    do_test = self._prompt(
                        "Would you like to test your Claude API key now? [Y/n]: ", default="y"
                    )
                    if do_test.strip().lower() in ("", "y", "yes"):
                        print("\nTesting Claude API key...")
                        from cortex.utils.api_key_test import test_anthropic_api_key

                        if test_anthropic_api_key(existing_claude):
                            print("\n✅ Claude API key is valid and working!")
                            resp = self._prompt(
                                "Would you like some package suggestions to try? [Y/n]: ",
                                default="y",
                            )
                            if resp.strip().lower() in ("", "y", "yes"):
                                self._install_suggested_packages()
                        else:
                            print(
                                "\n❌ Claude API key test failed. Please check your key or network."
                            )
                self.config["api_provider"] = "anthropic"
                self.config["api_key_configured"] = True
                return StepResult(success=True, data={"api_provider": "anthropic"})
            return self._setup_claude_api()
        elif choice == "2":
            if existing_openai:
                print("\n✓ Using existing OpenAI API key!")
                # Prompt for dry run even if key exists
                if self.interactive:
                    do_test = self._prompt(
                        "Would you like to test your OpenAI API key now? [Y/n]: ", default="y"
                    )
                    if do_test.strip().lower() in ("", "y", "yes"):
                        print("\nTesting OpenAI API key...")
                        from cortex.utils.api_key_test import test_openai_api_key

                        if test_openai_api_key(existing_openai):
                            print("\n✅ OpenAI API key is valid and working!")
                            resp = self._prompt(
                                "Would you like some package suggestions to try? [Y/n]: ",
                                default="y",
                            )
                            if resp.strip().lower() in ("", "y", "yes"):
                                self._install_suggested_packages()
                        else:
                            print(
                                "\n❌ OpenAI API key test failed. Please check your key or network."
                            )
                self.config["api_provider"] = "openai"
                self.config["api_key_configured"] = True
                return StepResult(success=True, data={"api_provider": "openai"})
            return self._setup_openai_api()
        elif choice == "3":
            return self._setup_ollama()
        else:
            print("\n⚠ Running without AI - you'll only have basic apt functionality")
            return StepResult(success=True, data={"api_provider": "none"})

    def _detect_hardware(self) -> dict[str, Any]:
        """Detect system hardware."""
        from cortex.hardware_detection import detect_hardware

        try:
            info = detect_hardware()
            return asdict(info)
        except Exception as e:
            logger.warning(f"Hardware detection failed: {e}")
            return {
                "cpu": {"vendor": "unknown", "model": "unknown"},
                "gpu": {"vendor": "unknown", "model": "unknown"},
            }

    def _step_hardware_detection(self) -> StepResult:
        """Detect and configure hardware settings."""
        self._clear_screen()
        self._print_header("Step 2: Hardware Detection")

        print("\nDetecting your hardware for optimal performance...\n")

        hardware_info = self._detect_hardware()

        # Save hardware info
        self.config["hardware"] = hardware_info

        # Display results
        cpu = hardware_info.get("cpu", {})
        gpu_list = hardware_info.get("gpu", [])
        memory = hardware_info.get("memory", {})

        print("  • CPU:", cpu.get("model", "Unknown"))
        if gpu_list:
            gpu = gpu_list[0]  # Take first GPU
            gpu_vendor = gpu.get("vendor", "unknown")
            gpu_model = gpu.get("model", "Detected")
            if gpu_vendor != "unknown":
                print(f"  • GPU: {gpu_model} ({gpu_vendor})")
            else:
                print("  • GPU: Detected")
        else:
            print("  • GPU: Not detected")

        if memory:
            print(f"  • Memory: {memory.get('total_gb', 0)} GB")

        print("\n✓ Hardware detection complete!")

        return StepResult(success=True, data={"hardware": hardware_info})

    def _step_preferences(self) -> StepResult:
        """Configure user preferences."""
        self._clear_screen()
        self._print_header("Step 3: Preferences")

        print("\nLet's customize Cortex for you.\n")

        preferences = {}

        if self.interactive:
            # Confirmation mode
            print("By default, Cortex will ask for confirmation before installing packages.")
            auto_confirm = self._prompt("Enable auto-confirm for installs? [y/N]: ", default="n")
            preferences["auto_confirm"] = auto_confirm.lower() == "y"

            # Verbosity
            print("\nVerbosity level:")
            print("  1. Quiet (minimal output)")
            print("  2. Normal (recommended)")
            print("  3. Verbose (detailed output)")
            verbosity = self._prompt("Choose [1-3]: ", default="2")
            preferences["verbosity"] = (
                ["quiet", "normal", "verbose"][int(verbosity) - 1]
                if verbosity.isdigit()
                else "normal"
            )

            # Offline mode
            print("\nEnable offline caching? (stores AI responses for offline use)")
            offline = self._prompt("Enable caching? [Y/n]: ", default="y")
            preferences["enable_cache"] = offline.lower() != "n"
        else:
            preferences = {"auto_confirm": False, "verbosity": "normal", "enable_cache": True}

        self.config["preferences"] = preferences

        print("\n✓ Preferences saved!")
        return StepResult(success=True, data={"preferences": preferences})

    def _step_shell_integration(self) -> StepResult:
        """Set up shell integration."""
        self._clear_screen()
        self._print_header("Step 4: Shell Integration")

        print("\nCortex can integrate with your shell for a better experience:\n")
        print("  • Tab completion for commands")
        print("  • Keyboard shortcuts (optional)")
        print("  • Automatic suggestions\n")

        if not self.interactive:
            return StepResult(success=True, data={"shell_integration": False})

        setup = self._prompt("Set up shell integration? [Y/n]: ", default="y")

        if setup.lower() == "n":
            return StepResult(success=True, data={"shell_integration": False})

        # Detect shell
        shell = os.environ.get("SHELL", "/bin/bash")
        shell_name = os.path.basename(shell)

        print(f"\nDetected shell: {shell_name}")

        # Create completion script
        completion_script = self._generate_completion_script(shell_name)
        completion_file = self.CONFIG_DIR / f"completion.{shell_name}"

        with open(completion_file, "w") as f:
            f.write(completion_script)

        # Add to shell config
        shell_config = self._get_shell_config(shell_name)
        source_line = (
            f'\n# Cortex completion\n[ -f "{completion_file}" ] && source "{completion_file}"\n'
        )

        if shell_config.exists():
            with open(shell_config, "a") as f:
                f.write(source_line)
            print(f"\n✓ Added completion to {shell_config}")

        print("\nRestart your shell or run:")
        print(f"  source {completion_file}")

        if self.interactive:
            self._prompt("\nPress Enter to continue: ")

        return StepResult(success=True, data={"shell_integration": True})

    def _generate_completion_script(self, shell: str) -> str:
        """Generate shell completion script."""
        if shell in ["bash", "sh"]:
            return """
# Cortex bash completion
_cortex_completion() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local commands="install remove update search info undo history help"

    if [ $COMP_CWORD -eq 1 ]; then
        COMPREPLY=($(compgen -W "$commands" -- "$cur"))
    fi
}
complete -F _cortex_completion cortex
"""
        elif shell == "zsh":
            return """
# Cortex zsh completion
_cortex() {
    local commands=(
        'install:Install packages'
        'remove:Remove packages'
        'update:Update system'
        'search:Search for packages'
        'info:Show package info'
        'undo:Undo last operation'
        'history:Show history'
        'help:Show help'
    )
    _describe 'command' commands
}
compdef _cortex cortex
"""
        elif shell == "fish":
            return """
# Cortex fish completion
complete -c cortex -f
complete -c cortex -n "__fish_use_subcommand" -a "install" -d "Install packages"
complete -c cortex -n "__fish_use_subcommand" -a "remove" -d "Remove packages"
complete -c cortex -n "__fish_use_subcommand" -a "update" -d "Update system"
complete -c cortex -n "__fish_use_subcommand" -a "search" -d "Search packages"
complete -c cortex -n "__fish_use_subcommand" -a "undo" -d "Undo last operation"
complete -c cortex -n "__fish_use_subcommand" -a "history" -d "Show history"
"""
        return "# No completion available for this shell"

    def _get_shell_config(self, shell: str) -> Path:
        """Get the shell config file path."""
        home = Path.home()
        configs = {
            "bash": home / ".bashrc",
            "zsh": home / ".zshrc",
            "fish": home / ".config" / "fish" / "config.fish",
        }
        return configs.get(shell, home / ".profile")

    def _step_test_command(self) -> StepResult:
        """Run a test command."""
        self._clear_screen()
        self._print_header("Step 5: Test Cortex")

        print("\nLet's make sure everything works!\n")
        print("Try running a simple command:\n")
        print("  $ cortex search text editors\n")

        if not self.interactive:
            return StepResult(success=True, data={"test_completed": False})

        run_test = self._prompt("Run test now? [Y/n]: ", default="y")

        if run_test.lower() == "n":
            return StepResult(success=True, data={"test_completed": False})

        print("\n" + "=" * 50)

        # Simulate or run actual test
        try:
            # Check if cortex command exists
            cortex_path = shutil.which("cortex")
            if cortex_path:
                result = subprocess.run(
                    ["cortex", "search", "text", "editors"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                print(result.stdout)
                if result.returncode == 0:
                    print("\n✓ Test successful!")
                else:
                    print(f"\n⚠ Test completed with warnings: {result.stderr}")
            else:
                # Fallback to apt search
                print("Running: apt search text-editor")
                subprocess.run(["apt", "search", "text-editor"], timeout=30)
                print("\n✓ Basic functionality working!")
        except subprocess.TimeoutExpired:
            print("\n⚠ Test timed out - this is OK, Cortex is still usable")
        except Exception as e:
            print(f"\n⚠ Test failed: {e}")

        print("=" * 50)

        if self.interactive:
            self._prompt("\nPress Enter to continue: ")

        return StepResult(success=True, data={"test_completed": True})

    def _step_complete(self) -> StepResult:
        """Completion step."""
        self._clear_screen()
        self._print_header("Setup Complete! 🎉")

        # Save all config
        self.save_config()

        print(
            """
Cortex is ready to use! Here are some things to try:

  📦 Install packages:
     cortex install docker
     cortex install a web server

  🔍 Search packages:
     cortex search image editors
     cortex search something for pdf

  🔄 Update system:
     cortex update everything

  ⏪ Undo mistakes:
     cortex undo

  📖 Get help:
     cortex help

"""
        )

        # Show configuration summary
        print("Configuration Summary:")
        print(f"  • API Provider: {self.config.get('api_provider', 'none')}")

        hardware = self.config.get("hardware", {})
        if hardware.get("gpu_vendor"):
            print(f"  • GPU: {hardware.get('gpu', 'Detected')}")

        prefs = self.config.get("preferences", {})
        print(f"  • Verbosity: {prefs.get('verbosity', 'normal')}")
        print(f"  • Caching: {'enabled' if prefs.get('enable_cache') else 'disabled'}")

        print("\n" + "=" * 50)
        print("Happy computing! 🐧")
        print("=" * 50 + "\n")

        return StepResult(success=True)

    # Helper methods
    def _clear_screen(self):
        """Clear the terminal screen."""
        if self.interactive:
            os.system("clear" if os.name == "posix" else "cls")

    def _print_banner(self):
        """Print the Cortex banner."""
        banner = """
   ____           _
  / ___|___  _ __| |_ _____  __
 | |   / _ \\| '__| __/ _ \\ \\/ /
 | |__| (_) | |  | ||  __/>  <
  \\____\\___/|_|   \\__\\___/_/\\_\\


"""
        print(banner)

    def _print_header(self, title: str):
        """Print a section header."""
        print("\n" + "=" * 50)
        print(f"  {title}")
        print("=" * 50 + "\n")

    def _print_error(self, message: str):
        """Print an error message."""
        print(f"\n❌ {message}\n")

    def _prompt(self, message: str, default: str = "") -> str:
        """Prompt for user input."""
        if not self.interactive:
            return default

        try:
            response = input(message).strip()
            return response if response else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _save_env_var(self, name: str, value: str):
        """Save environment variable to shell config."""
        shell = os.environ.get("SHELL", "/bin/bash")
        shell_name = os.path.basename(shell)
        config_file = self._get_shell_config(shell_name)

        export_line = f'\nexport {name}="{value}"\n'  # nosec - intentional user config storage

        try:
            with open(config_file, "a") as f:
                f.write(export_line)

            # Also set for current session
            os.environ[name] = value
        except Exception as e:
            logger.warning(f"Could not save env var: {e}")


# Convenience functions
def needs_first_run() -> bool:
    """Check if first-run wizard is needed."""
    return FirstRunWizard(interactive=False).needs_setup()


def run_wizard(interactive: bool = True) -> bool:
    """Run the first-run wizard."""
    wizard = FirstRunWizard(interactive=interactive)
    return wizard.run()


def get_config() -> dict[str, Any]:
    """Get the saved configuration."""
    config_file = FirstRunWizard.CONFIG_FILE
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    # Run wizard if needed
    if needs_first_run() or "--force" in sys.argv:
        success = run_wizard()
        sys.exit(0 if success else 1)
    else:
        print("Setup already complete. Use --force to run again.")
