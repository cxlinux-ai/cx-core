"""
First-Run Wizard Module for Cortex Linux

Provides a seamless onboarding experience for new users, guiding them
through initial setup, configuration, and feature discovery.

Issue: #256
"""

import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from cortex.env_manager import get_env_manager

logger = logging.getLogger(__name__)

# Application name for storing cortex API keys
CORTEX_APP_NAME = "cortex"


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
        Run the complete wizard.

        Returns:
            True if wizard completed successfully
        """
        if not self.needs_setup():
            return True

        # Load any existing state
        self.load_state()

        # Define step handlers
        steps = [
            (WizardStep.WELCOME, self._step_welcome),
            (WizardStep.API_SETUP, self._step_api_setup),
            (WizardStep.HARDWARE_DETECTION, self._step_hardware_detection),
            (WizardStep.PREFERENCES, self._step_preferences),
            (WizardStep.SHELL_INTEGRATION, self._step_shell_integration),
            (WizardStep.TEST_COMMAND, self._step_test_command),
            (WizardStep.COMPLETE, self._step_complete),
        ]

        # Find starting point
        start_idx = 0
        for i, (step, _) in enumerate(steps):
            if step == self.state.current_step:
                start_idx = i
                break

        # Run steps
        for step, handler in steps[start_idx:]:
            self.state.current_step = step
            self.save_state()

            result = handler()

            if result.success:
                self.state.mark_completed(step)
                self.state.collected_data.update(result.data)

                if result.skip_to:
                    # Skip to a specific step
                    for s, _ in steps:
                        if s == result.skip_to:
                            break
                        if s not in self.state.completed_steps:
                            self.state.mark_skipped(s)
            else:
                if result.next_step:
                    # Allow retry or skip
                    continue
                else:
                    # Fatal error
                    self._print_error(f"Setup failed: {result.message}")
                    return False

        self.mark_setup_complete()
        return True

    def _step_welcome(self) -> StepResult:
        """Welcome step with introduction."""
        self._clear_screen()
        self._print_banner()

        print("""
Welcome to Cortex Linux! 🚀

Cortex is an AI-powered package manager that understands natural language.
Instead of memorizing apt commands, just tell Cortex what you want:

  $ cortex install a web server
  $ cortex setup python for machine learning
  $ cortex remove unused packages

This wizard will help you set up Cortex in just a few minutes.
""")

        if self.interactive:
            response = self._prompt("Press Enter to continue (or 'q' to quit): ")
            if response.lower() == "q":
                return StepResult(success=False, message="User cancelled")

        return StepResult(success=True)

    def _step_api_setup(self) -> StepResult:
        """API key configuration step."""
        self._clear_screen()
        self._print_header("Step 1: API Configuration")

        print("""
Cortex uses AI to understand your commands. You can use:

  1. Claude API (Anthropic) - Recommended
  2. OpenAI API
  3. Local LLM (Ollama) - Free, runs on your machine
  4. Skip for now (limited functionality)
""")

        # Check for existing API keys
        existing_claude = os.environ.get("ANTHROPIC_API_KEY")
        existing_openai = os.environ.get("OPENAI_API_KEY")

        if existing_claude:
            print("✓ Found existing Claude API key: ********...")
            self.config["api_provider"] = "anthropic"
            self.config["api_key_configured"] = True
            return StepResult(success=True, data={"api_provider": "anthropic"})

        if existing_openai:
            print("✓ Found existing OpenAI API key: ********...")
            self.config["api_provider"] = "openai"
            self.config["api_key_configured"] = True
            return StepResult(success=True, data={"api_provider": "openai"})

        if not self.interactive:
            return StepResult(
                success=True,
                message="Non-interactive mode - skipping API setup",
                data={"api_provider": "none"},
            )

        choice = self._prompt("Choose an option [1-4]: ", default="1")

        if choice == "1":
            return self._setup_claude_api()
        elif choice == "2":
            return self._setup_openai_api()
        elif choice == "3":
            return self._setup_ollama()
        else:
            print("\n⚠ Running without AI - you'll only have basic apt functionality")
            return StepResult(success=True, data={"api_provider": "none"})

    def _setup_claude_api(self) -> StepResult:
        """Set up Claude API."""
        print("\nTo get a Claude API key:")
        print("  1. Go to https://console.anthropic.com")
        print("  2. Sign up or log in")
        print("  3. Create an API key\n")

        api_key = self._prompt("Enter your Claude API key: ")

        if not api_key or not api_key.startswith("sk-"):
            print("\n⚠ Invalid API key format")
            return StepResult(success=True, data={"api_provider": "none"})

        # Save to shell profile
        self._save_env_var("ANTHROPIC_API_KEY", api_key)

        self.config["api_provider"] = "anthropic"
        self.config["api_key_configured"] = True

        print("\n✓ Claude API key saved!")
        return StepResult(success=True, data={"api_provider": "anthropic"})

    def _setup_openai_api(self) -> StepResult:
        """Set up OpenAI API."""
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
        return StepResult(success=True, data={"api_provider": "openai"})

    def _setup_ollama(self) -> StepResult:
        """Set up Ollama for local LLM."""
        print("\nChecking for Ollama...")

        # Check if Ollama is installed
        ollama_path = shutil.which("ollama")

        if not ollama_path:
            print("\nOllama is not installed. Install it with:")
            print("  curl -fsSL https://ollama.ai/install.sh | sh")

            install = self._prompt("\nInstall Ollama now? [y/N]: ", default="n")

            if install.lower() == "y":
                try:
                    subprocess.run(
                        "curl -fsSL https://ollama.ai/install.sh | sh", shell=True, check=True
                    )
                    print("\n✓ Ollama installed!")
                except subprocess.CalledProcessError:
                    print("\n✗ Failed to install Ollama")
                    return StepResult(success=True, data={"api_provider": "none"})

        # Let user choose model or use default
        print("\nWhich Ollama model would you like to use?")
        print("  1. llama3.2 (2GB) - Recommended for most users")
        print("  2. llama3.2:1b (1.3GB) - Faster, less RAM")
        print("  3. mistral (4GB) - Alternative quality model")
        print("  4. phi3 (2.3GB) - Microsoft's efficient model")
        print("  5. Custom (enter your own)")

        model_choices = {
            "1": "llama3.2",
            "2": "llama3.2:1b",
            "3": "mistral",
            "4": "phi3",
        }

        choice = self._prompt("\nEnter choice [1]: ", default="1")

        if choice == "5":
            model_name = self._prompt("Enter model name: ", default="llama3.2")
        elif choice in model_choices:
            model_name = model_choices[choice]
        else:
            print(f"Invalid choice '{choice}', using default model llama3.2")
            model_name = "llama3.2"

        # Pull the selected model
        print(f"\nPulling {model_name} model (this may take a few minutes)...")
        try:
            subprocess.run(["ollama", "pull", model_name], check=True)
            print("\n✓ Model ready!")
        except subprocess.CalledProcessError:
            print(
                f"\n⚠ Could not pull model - you can do this later with: ollama pull {model_name}"
            )

        self.config["api_provider"] = "ollama"
        self.config["ollama_model"] = model_name

        return StepResult(success=True, data={"api_provider": "ollama"})

    def _step_hardware_detection(self) -> StepResult:
        """Detect and configure hardware."""
        self._clear_screen()
        self._print_header("Step 2: Hardware Detection")

        print("\nDetecting your hardware...\n")

        hardware_info = self._detect_hardware()

        # Display results
        print(f"  CPU: {hardware_info.get('cpu', 'Unknown')}")
        print(f"  RAM: {hardware_info.get('ram_gb', 'Unknown')} GB")
        print(f"  GPU: {hardware_info.get('gpu', 'None detected')}")
        print(f"  Disk: {hardware_info.get('disk_gb', 'Unknown')} GB available")

        # GPU-specific setup
        if hardware_info.get("gpu_vendor") == "nvidia":
            print("\n🎮 NVIDIA GPU detected!")

            if self.interactive:
                setup_cuda = self._prompt("Set up CUDA support? [Y/n]: ", default="y")
                if setup_cuda.lower() != "n":
                    hardware_info["setup_cuda"] = True
                    print("  → CUDA will be configured when needed")

        self.config["hardware"] = hardware_info

        if self.interactive:
            self._prompt("\nPress Enter to continue: ")

        return StepResult(success=True, data={"hardware": hardware_info})

    def _detect_hardware(self) -> dict[str, Any]:
        """Detect system hardware."""
        info = {}

        # CPU
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        info["cpu"] = line.split(":")[1].strip()
                        break
        except:
            info["cpu"] = "Unknown"

        # RAM
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if "MemTotal" in line:
                        kb = int(line.split()[1])
                        info["ram_gb"] = round(kb / 1024 / 1024, 1)
                        break
        except:
            info["ram_gb"] = 0

        # GPU
        try:
            result = subprocess.run(["lspci"], capture_output=True, text=True)
            for line in result.stdout.split("\n"):
                if "VGA" in line or "3D" in line:
                    if "NVIDIA" in line.upper():
                        info["gpu"] = line.split(":")[-1].strip()
                        info["gpu_vendor"] = "nvidia"
                    elif "AMD" in line.upper():
                        info["gpu"] = line.split(":")[-1].strip()
                        info["gpu_vendor"] = "amd"
                    elif "Intel" in line.upper():
                        info["gpu"] = line.split(":")[-1].strip()
                        info["gpu_vendor"] = "intel"
                    break
        except:
            info["gpu"] = "None detected"

        # Disk
        try:
            result = subprocess.run(["df", "-BG", "/"], capture_output=True, text=True)
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                info["disk_gb"] = int(parts[3].rstrip("G"))
        except:
            info["disk_gb"] = 0

        return info

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

        print("""
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

""")

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

        Linux that understands you.
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
        """Save environment variable securely using encrypted storage.

        API keys are stored encrypted in ~/.cortex/environments/cortex.json
        using Fernet encryption. The encryption key is stored in
        ~/.cortex/.env_key with restricted permissions (chmod 600).
        """
        # Set for current session regardless of storage success
        os.environ[name] = value

        try:
            env_mgr = get_env_manager()

            # Handle brand names correctly (e.g., "OpenAI" not "Openai")
            provider_name_raw = name.replace("_API_KEY", "")
            if provider_name_raw == "OPENAI":
                provider_name_display = "OpenAI"
            elif provider_name_raw == "ANTHROPIC":
                provider_name_display = "Anthropic"
            else:
                provider_name_display = provider_name_raw.replace("_", " ").title()

            env_mgr.set_variable(
                app=CORTEX_APP_NAME,
                key=name,
                value=value,
                encrypt=True,
                description=f"API key for {provider_name_display}",
            )
            logger.info(f"Saved {name} to encrypted storage")
        except ImportError:
            logger.warning(
                f"cryptography package not installed. {name} set for current session only. "
                "Install cryptography for persistent encrypted storage: pip install cryptography"
            )
        except Exception as e:
            logger.warning(f"Could not save env var to encrypted storage: {e}")


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
