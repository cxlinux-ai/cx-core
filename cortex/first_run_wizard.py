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

from cortex.utils.api_key_validator import (
    validate_anthropic_api_key,
    validate_openai_api_key,
)

logger = logging.getLogger(__name__)

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


def get_env_file_path() -> Path:
    possible_paths = [
        Path.cwd() / ".env",
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent.parent / ".env",
        Path.home() / ".cortex" / ".env",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return Path.cwd() / ".env"


def read_key_from_env_file(key_name: str) -> str | None:
    env_path = get_env_file_path()
    if not env_path.exists():
        return None
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key == key_name:
                        return value or None
    except Exception as e:
        logger.warning(f"Error reading .env file: {e}")
    return None


def save_key_to_env_file(key_name: str, key_value: str) -> bool:
    env_path = get_env_file_path()
    lines: list[str] = []
    if env_path.exists():
        try:
            lines = env_path.read_text().splitlines(keepends=True)
        except Exception:
            pass

    updated = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key_name}="):
            new_lines.append(f'{key_name}="{key_value}"\n')
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f'{key_name}="{key_value}"\n')

    try:
        env_path.write_text("".join(new_lines))
        return True
    except Exception:
        return False


def is_valid_api_key(key: str | None, key_type: str) -> bool:
    if not key:
        return False
    if key_type == "anthropic":
        return key.startswith("sk-ant-")
    if key_type == "openai":
        return key.startswith("sk-")
    return True


def get_valid_api_key(env_var: str, key_type: str) -> str | None:
    key = read_key_from_env_file(env_var)
    if key and is_valid_api_key(key, key_type):
        os.environ[env_var] = key
        return key
    os.environ.pop(env_var, None)
    return None


def detect_available_providers() -> list[str]:
    providers = []
    if get_valid_api_key("ANTHROPIC_API_KEY", "anthropic"):
        providers.append("anthropic")
    if get_valid_api_key("OPENAI_API_KEY", "openai"):
        providers.append("openai")
    if shutil.which("ollama"):
        providers.append("ollama")
    return providers


class WizardStep(Enum):
    WELCOME = "welcome"
    API_SETUP = "api_setup"
    HARDWARE_DETECTION = "hardware_detection"
    PREFERENCES = "preferences"
    SHELL_INTEGRATION = "shell_integration"
    TEST_COMMAND = "test_command"
    COMPLETE = "complete"


@dataclass
class WizardState:
    current_step: WizardStep = WizardStep.WELCOME
    completed_steps: list[WizardStep] = field(default_factory=list)
    skipped_steps: list[WizardStep] = field(default_factory=list)
    collected_data: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None


@dataclass
class StepResult:
    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    next_step: WizardStep | None = None
    skip_to: WizardStep | None = None


class FirstRunWizard:
    CONFIG_DIR = Path.home() / ".cortex"
    STATE_FILE = CONFIG_DIR / "wizard_state.json"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    SETUP_COMPLETE_FILE = CONFIG_DIR / ".setup_complete"

    def __init__(self, interactive: bool = True) -> None:
        self.interactive = interactive
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def needs_setup(self) -> bool:
        return not self.SETUP_COMPLETE_FILE.exists()

    def run(self) -> bool:
        return True


def needs_first_run() -> bool:
    return FirstRunWizard(interactive=False).needs_setup()


def run_wizard(interactive: bool = True) -> bool:
    return FirstRunWizard(interactive=interactive).run()


def get_config() -> dict[str, Any]:
    config_file = FirstRunWizard.CONFIG_FILE
    if config_file.exists():
        return json.loads(config_file.read_text())
    return {}


__all__ = [
    "FirstRunWizard",
    "WizardState",
    "WizardStep",
    "StepResult",
    "needs_first_run",
    "run_wizard",
    "get_config",
]


if __name__ == "__main__":
    if needs_first_run() or "--force" in sys.argv:
        sys.exit(0 if run_wizard() else 1)
    print("Setup already complete. Use --force to run again.")
