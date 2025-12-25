try:
    from pathlib import Path
    from dotenv import load_dotenv
    # Load from parent directory .env as well
    load_dotenv(dotenv_path=Path.cwd().parent / ".env", override=True)
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=True)
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

from dataclasses import dataclass, field
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
    "scientific computing tools"
]


def get_env_file_path() -> Path:
    """Get the path to the .env file."""
    # Check multiple locations for .env file in priority order
    possible_paths = [
        Path.cwd() / ".env",  # Current working directory (project folder)
        Path(__file__).parent.parent / ".env",  # cortex package parent
        Path(__file__).parent.parent.parent / ".env",  # project root
        Path.home() / ".cortex" / ".env",  # Home directory fallback
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Default to current directory .env
    return Path.cwd() / ".env"


def read_key_from_env_file(key_name: str) -> str | None:
    """
    Read an API key directly from the .env file.
    Returns the key value or None if not found/blank.
    """
    env_path = get_env_file_path()
    
    if not env_path.exists():
        return None
    
    try:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Parse KEY=VALUE format
                if '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    if key == key_name:
                        # Return None if value is empty or blank
                        value = value.strip()
                        if value and len(value) > 0:
                            return value
                        return None
    except Exception as e:
        logger.warning(f"Error reading .env file: {e}")
    
    return None


def save_key_to_env_file(key_name: str, key_value: str) -> bool:
    """
    Save an API key to the .env file.
    Updates existing key or adds new one.
    """
    env_path = get_env_file_path()
    
    lines = []
    key_found = False
    
    # Read existing content if file exists
    if env_path.exists():
        try:
            with open(env_path, 'r') as f:
                lines = f.readlines()
        except Exception:
            pass
    
    # Update or add the key
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            existing_key = stripped.split('=')[0].strip()
            if existing_key == key_name:
                new_lines.append(f'{key_name}="{key_value}"\n')
                key_found = True
                continue
        new_lines.append(line)
    
    # Add key if not found
    if not key_found:
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines.append('\n')
        new_lines.append(f'{key_name}="{key_value}"\n')
    
    # Write back to file
    try:
        with open(env_path, 'w') as f:
            f.writelines(new_lines)
        return True
    except Exception:
        return False


def is_valid_api_key(key: str | None, key_type: str = "generic") -> bool:
    """
    Check if an API key is valid (non-blank and properly formatted).
    """
    if key is None:
        return False
    
    key = key.strip()
    if not key:
        return False
    
    if key_type == "anthropic":
        return key.startswith("sk-ant-")
    elif key_type == "openai":
        return key.startswith("sk-")
    else:
        return True


def get_valid_api_key(env_var: str, key_type: str = "generic") -> str | None:
    """
    Get a valid API key from .env file first, then environment variable.
    Treats blank keys as missing.
    .env file is the source of truth - if blank there, key is considered missing.
    """
    # First check .env file (this is the source of truth)
    key_from_file = read_key_from_env_file(env_var)
    
    # Debug: print what we found
    env_path = get_env_file_path()
    logger.debug(f"Checking {env_var} in {env_path}: '{key_from_file}'")
    
    # If key in .env file exists, validate it
    if key_from_file is not None and len(key_from_file) > 0:
        if is_valid_api_key(key_from_file, key_type):
            # Update environment variable with the .env value
            os.environ[env_var] = key_from_file
            return key_from_file
        else:
            # Key exists but invalid format
            return None
    
    # Key is blank or missing in .env file
    # Clear any stale environment variable
    if env_var in os.environ:
        del os.environ[env_var]
    
    return None


def detect_available_providers() -> list[str]:
    """Detect available providers based on valid (non-blank) API keys in .env file."""
    providers = []
    
    if get_valid_api_key("ANTHROPIC_API_KEY", "anthropic"):
        providers.append("anthropic")
    if get_valid_api_key("OPENAI_API_KEY", "openai"):
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
        if step not in self.completed_steps:
            self.completed_steps.append(step)

    def mark_skipped(self, step: WizardStep):
        if step not in self.skipped_steps:
            self.skipped_steps.append(step)

    def is_completed(self, step: WizardStep) -> bool:
        return step in self.completed_steps

    def to_dict(self) -> dict[str, Any]:
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
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def needs_setup(self) -> bool:
        return not self.SETUP_COMPLETE_FILE.exists()

    def _get_current_provider(self) -> str | None:
        """Get the currently configured provider from config file."""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE) as f:
                    config = json.load(f)
                    return config.get("api_provider")
            except Exception:
                pass
        return None

    def load_state(self) -> bool:
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
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(self.state.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save wizard state: {e}")

    def save_config(self):
        try:
            with open(self.CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save config: {e}")

    def mark_setup_complete(self):
        self.SETUP_COMPLETE_FILE.touch()
        self.state.completed_at = datetime.now()
        self.save_state()

    def _prompt_for_api_key(self, key_type: str) -> str | None:
        """
        Prompt user for a valid API key, rejecting blank inputs.
        """
        if key_type == "anthropic":
            prefix = "sk-ant-"
            provider_name = "Claude (Anthropic)"
            print("\nTo get a Claude API key:")
            print("  1. Go to https://console.anthropic.com")
            print("  2. Sign up or log in")
            print("  3. Create an API key\n")
        else:
            prefix = "sk-"
            provider_name = "OpenAI"
            print("\nTo get an OpenAI API key:")
            print("  1. Go to https://platform.openai.com")
            print("  2. Sign up or log in")
            print("  3. Create an API key\n")
        
        while True:
            key = self._prompt(f"Enter your {provider_name} API key (or 'q' to cancel): ")
            
            if key.lower() == 'q':
                return None
            
            # Check if blank
            if not key or not key.strip():
                print("\n⚠ API key cannot be blank. Please enter a valid key.")
                continue
            
            key = key.strip()
            
            # Check format
            if not key.startswith(prefix):
                print(f"\n⚠ Invalid key format. {provider_name} keys should start with '{prefix}'")
                continue
            
            return key

    def _install_suggested_packages(self):
        """Offer to install suggested packages."""
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
                    result = subprocess.run([
                        sys.executable, "-m", "cortex.cli", "install", pkg
                    ], capture_output=True, text=True, env=env)
                    print(result.stdout)
                    if result.stderr:
                        print(result.stderr)
                except Exception as e:
                    print(f"Error installing {pkg}: {e}")

    def run(self) -> bool:
        """
        Main wizard flow:
        1. Reload and check .env file for API keys
        2. Always show provider selection menu (with all options)
        3. Show "Skip reconfiguration" only on second run onwards
        4. If selected provider's key is blank in .env, prompt for key
        5. Save key to .env file
        6. Run dry run to verify
        """
        self._clear_screen()
        self._print_banner()

        # Reload .env file to get fresh values
        env_path = get_env_file_path()
        try:
            from dotenv import load_dotenv
            # Force reload - override any existing environment variables
            load_dotenv(dotenv_path=env_path, override=True)
        except ImportError:
            pass

        # Clear any stale API keys from environment if they're blank in .env
        for key_name in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
            file_value = read_key_from_env_file(key_name)
            if file_value is None or len(file_value.strip()) == 0:
                # Key is blank in .env, remove from environment
                if key_name in os.environ:
                    del os.environ[key_name]

        # Detect which providers have valid keys (checks .env file)
        available_providers = detect_available_providers()
        has_ollama = shutil.which("ollama") is not None
        
        # Check if there's already a configured provider (for second run)
        current_provider = self._get_current_provider()
        is_first_run = current_provider is None

        # Provider display names
        provider_names = {
            "anthropic": "Anthropic (Claude)",
            "openai": "OpenAI",
            "ollama": "Ollama (local)",
            "none": "None"
        }

        # Show .env file location
        # print(f"\n[Checking API keys in: {env_path}]")

        print("\nSelect your preferred LLM provider:\n")

        # Build the menu dynamically
        option_num = 1
        provider_map = {}

        # Show "Skip reconfiguration" only on second run onwards
        if not is_first_run and current_provider and current_provider != "none":
            current_name = provider_names.get(current_provider, current_provider)
            print(f"  {option_num}. Skip reconfiguration (current: {current_name})")
            provider_map[str(option_num)] = "skip_reconfig"
            option_num += 1

        # Always show Anthropic option
        anthropic_status = " ✓ (key found)" if "anthropic" in available_providers else " (needs key)"
        print(f"  {option_num}. Anthropic (Claude){anthropic_status} - Recommended")
        provider_map[str(option_num)] = "anthropic"
        option_num += 1

        # Always show OpenAI option
        openai_status = " ✓ (key found)" if "openai" in available_providers else " (needs key)"
        print(f"  {option_num}. OpenAI{openai_status}")
        provider_map[str(option_num)] = "openai"
        option_num += 1

        # Always show Ollama option
        ollama_status = " ✓ (installed)" if has_ollama else " (not installed)"
        print(f"  {option_num}. Ollama (local){ollama_status}")
        provider_map[str(option_num)] = "ollama"

        # Get valid choices range
        valid_choices = list(provider_map.keys())
        default_choice = "1"
        
        choice = self._prompt(f"\nChoose a provider [{'-'.join([valid_choices[0], valid_choices[-1]])}]: ", default=default_choice)
        
        provider = provider_map.get(choice)
        
        if not provider:
            print(f"Invalid choice. Please enter a number between {valid_choices[0]} and {valid_choices[-1]}.")
            return False
        
        # Handle "skip reconfiguration"
        if provider == "skip_reconfig":
            print(f"\n✓ Keeping current provider: {provider_names.get(current_provider, current_provider)}")
            self.mark_setup_complete()
            return True

        # Handle Anthropic
        if provider == "anthropic":
            existing_key = get_valid_api_key("ANTHROPIC_API_KEY", "anthropic")
            
            if not existing_key:
                print("\nNo valid Anthropic API key found in .env file (blank or missing).")
                key = self._prompt_for_api_key("anthropic")
                if key is None:
                    print("\nSetup cancelled.")
                    return False
                # Save to .env file
                if save_key_to_env_file("ANTHROPIC_API_KEY", key):
                    print(f"✓ API key saved to {get_env_file_path()}")
                else:
                    print("⚠ Could not save to .env file, saving to shell config instead.")
                    self._save_env_var("ANTHROPIC_API_KEY", key)
                os.environ["ANTHROPIC_API_KEY"] = key
            else:
                print(f"\n✓ Valid Anthropic API key found in .env file!")
            
            self.config["api_provider"] = "anthropic"
            self.config["api_key_configured"] = True
            
            # Run dry run to verify
            random_example = random.choice(DRY_RUN_EXAMPLES)
            print(f'\nVerifying setup with dry run: cortex install "{random_example}"...')
            try:
                from cortex.cli import CortexCLI
                cli = CortexCLI()
                result = cli.install(random_example, execute=False, dry_run=True, forced_provider="claude")
                if result != 0:
                    print("\n❌ Dry run failed. Please check your API key and network.")
                    return False
                print("\n✅ API key verified successfully!")
            except Exception as e:
                print(f"\n❌ Error during verification: {e}")
                return False

        # Handle OpenAI
        elif provider == "openai":
            existing_key = get_valid_api_key("OPENAI_API_KEY", "openai")
            
            if not existing_key:
                print("\nNo valid OpenAI API key found in .env file (blank or missing).")
                key = self._prompt_for_api_key("openai")
                if key is None:
                    print("\nSetup cancelled.")
                    return False
                # Save to .env file
                if save_key_to_env_file("OPENAI_API_KEY", key):
                    print(f"✓ API key saved to {get_env_file_path()}")
                else:
                    print("⚠ Could not save to .env file, saving to shell config instead.")
                    self._save_env_var("OPENAI_API_KEY", key)
                os.environ["OPENAI_API_KEY"] = key
            else:
                print(f"\n✓ Valid OpenAI API key found in .env file!")
            
            self.config["api_provider"] = "openai"
            self.config["api_key_configured"] = True
            
            # Run dry run to verify
            random_example = random.choice(DRY_RUN_EXAMPLES)
            print(f'\nVerifying setup with dry run: cortex install "{random_example}"...')
            try:
                from cortex.cli import CortexCLI
                cli = CortexCLI()
                result = cli.install(random_example, execute=False, dry_run=True, forced_provider="openai")
                if result != 0:
                    print("\n❌ Dry run failed. Please check your API key and network.")
                    return False
                print("\n✅ API key verified successfully!")
            except Exception as e:
                print(f"\n❌ Error during verification: {e}")
                return False

        # Handle Ollama
        elif provider == "ollama":
            if not has_ollama:
                print("\n⚠ Ollama is not installed.")
                print("Install it from: https://ollama.ai")
                return False
            print("\n✓ Ollama detected and ready. No API key required.")
            self.config["api_provider"] = "ollama"
            self.config["api_key_configured"] = True

        # Save and complete
        self.save_config()
        self.mark_setup_complete()

        print(f"\n[✔] Setup complete! Provider '{provider}' is ready for AI workloads.")
        print("You can rerun this wizard anytime with: cortex wizard")
        return True

    # Helper methods
    def _clear_screen(self):
        if self.interactive:
            os.system("clear" if os.name == "posix" else "cls")

    def _print_banner(self):
        banner = """
   ____           _
  / ___|___  _ __| |_ _____  __
 | |   / _ \\| '__| __/ _ \\ \\/ /
 | |__| (_) | |  | ||  __/>  <
  \\____\\___/|_|   \\__\\___/_/\\_\\

"""
        print(banner)

    def _print_header(self, title: str):
        print("\n" + "=" * 50)
        print(f"  {title}")
        print("=" * 50 + "\n")

    def _print_error(self, message: str):
        print(f"\n❌ {message}\n")

    def _prompt(self, message: str, default: str = "") -> str:
        if not self.interactive:
            return default
        try:
            response = input(message).strip()
            return response if response else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _save_env_var(self, name: str, value: str):
        """Save environment variable to shell config (fallback)."""
        shell = os.environ.get("SHELL", "/bin/bash")
        shell_name = os.path.basename(shell)
        config_file = self._get_shell_config(shell_name)
        export_line = f'\nexport {name}="{value}"\n'
        try:
            with open(config_file, "a") as f:
                f.write(export_line)
            os.environ[name] = value
            print(f"✓ API key saved to {config_file}")
        except Exception as e:
            logger.warning(f"Could not save env var: {e}")

    def _get_shell_config(self, shell: str) -> Path:
        home = Path.home()
        configs = {
            "bash": home / ".bashrc",
            "zsh": home / ".zshrc",
            "fish": home / ".config" / "fish" / "config.fish",
        }
        return configs.get(shell, home / ".profile")

    def _generate_completion_script(self, shell: str) -> str:
        if shell in ["bash", "sh"]:
            return '''
# Cortex bash completion
_cortex_completion() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local commands="install remove update search info undo history help"
    if [ $COMP_CWORD -eq 1 ]; then
        COMPREPLY=($(compgen -W "$commands" -- "$cur"))
    fi
}
complete -F _cortex_completion cortex
'''
        elif shell == "zsh":
            return '''
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
'''
        elif shell == "fish":
            return '''
# Cortex fish completion
complete -c cortex -f
complete -c cortex -n "__fish_use_subcommand" -a "install" -d "Install packages"
complete -c cortex -n "__fish_use_subcommand" -a "remove" -d "Remove packages"
complete -c cortex -n "__fish_use_subcommand" -a "update" -d "Update system"
complete -c cortex -n "__fish_use_subcommand" -a "search" -d "Search packages"
complete -c cortex -n "__fish_use_subcommand" -a "undo" -d "Undo last operation"
complete -c cortex -n "__fish_use_subcommand" -a "history" -d "Show history"
'''
        return "# No completion available for this shell"


# Convenience functions
def needs_first_run() -> bool:
    return FirstRunWizard(interactive=False).needs_setup()


def run_wizard(interactive: bool = True) -> bool:
    wizard = FirstRunWizard(interactive=interactive)
    return wizard.run()


def get_config() -> dict[str, Any]:
    config_file = FirstRunWizard.CONFIG_FILE
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    if needs_first_run() or "--force" in sys.argv:
        success = run_wizard()
        sys.exit(0 if success else 1)
    else:
        print("Setup already complete. Use --force to run again.")