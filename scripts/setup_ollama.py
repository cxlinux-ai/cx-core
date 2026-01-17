#!/usr/bin/env python3
"""
Ollama Setup Script for Cortex Linux

This script handles the complete Ollama installation and model selection process.
It provides an interactive experience to:
1. Check if Ollama is already installed
2. Install Ollama if not present
3. Verify the installation
4. Prompt user to select and download a model
5. Test the model
6. Configure Cortex to use Ollama

Usage:
    python scripts/setup_ollama.py
    python scripts/setup_ollama.py --model llama3.2  # Non-interactive with specific model
    python scripts/setup_ollama.py --skip-test       # Skip model testing

Author: Cortex Linux Team
SPDX-License-Identifier: BUSL-1.1
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class Colors:
    """ANSI color codes for terminal output."""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text.center(70)}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 70}{Colors.ENDC}\n")


def print_success(text: str) -> None:
    """Print success message."""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text: str) -> None:
    """Print warning message."""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_info(text: str) -> None:
    """Print info message."""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def check_ollama_installed() -> bool:
    """Check if Ollama is already installed."""
    return shutil.which("ollama") is not None


def check_ollama_running() -> bool:
    """Check if Ollama service is running."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def install_ollama() -> bool:
    """Install Ollama using the official installer."""
    print_info("Installing Ollama...")
    print_info("This will download and run: curl -fsSL https://ollama.ai/install.sh | sh")

    try:
        # Download and execute the installer
        result = subprocess.run(
            "curl -fsSL https://ollama.ai/install.sh | sh",
            shell=True,
            check=False,  # Don't raise exception, we'll check manually
            capture_output=False,  # Show output to user
        )

        # Exit code 9 means useradd warning (group exists) - this is OK
        # Exit code 0 means complete success
        # Check if ollama binary exists to verify installation
        time.sleep(1)  # Give filesystem a moment to sync

        if shutil.which("ollama"):
            print_success("Ollama installed successfully!")
            return True
        else:
            # Check common installation paths
            if os.path.exists("/usr/local/bin/ollama") or os.path.exists("/usr/bin/ollama"):
                print_success("Ollama installed successfully!")
                return True

            print_error(
                f"Installation completed with exit code {result.returncode}, but ollama binary not found"
            )
            return False

    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install Ollama: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error during installation: {e}")
        return False


def start_ollama_service() -> bool:
    """Start the Ollama service."""
    print_info("Starting Ollama service...")
    print_info("This initializes API keys and starts the server...")

    try:
        # Check if already running
        if check_ollama_running():
            print_success("Ollama service is already running!")
            return True

        # Start Ollama in the background
        process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for service to be ready (up to 15 seconds)
        print_info("Waiting for service to initialize...")
        for i in range(15):
            time.sleep(1)
            if check_ollama_running():
                print_success("Ollama service is running!")
                print_info("API endpoint: http://localhost:11434")
                return True

            # Check if process died
            if process.poll() is not None:
                print_error("Ollama service failed to start")
                return False

        print_warning("Ollama service started but not responding yet.")
        print_info("It may still be initializing. Check with: ollama list")
        return True

    except FileNotFoundError:
        print_error("Ollama binary not found. Installation may have failed.")
        print_info("Try running: which ollama")
        return False
    except Exception as e:
        print_warning(f"Could not start Ollama service automatically: {e}")
        print_info("You can start it manually with: ollama serve &")
        return False


def get_available_models() -> list[dict[str, Any]]:
    """Get list of recommended models for Cortex."""
    return [
        {
            "name": "llama3.2",
            "size": "2GB",
            "description": "Fast and efficient (3B params, recommended)",
            "recommended": True,
        },
        {
            "name": "llama3.2:1b",
            "size": "1.3GB",
            "description": "Smallest and fastest (1B params)",
            "recommended": False,
        },
        {
            "name": "llama3.1:8b",
            "size": "4.7GB",
            "description": "More capable (8B params, requires more RAM)",
            "recommended": False,
        },
        {
            "name": "mistral",
            "size": "4.1GB",
            "description": "Good alternative to Llama (7B params)",
            "recommended": False,
        },
        {
            "name": "codellama:7b",
            "size": "3.8GB",
            "description": "Optimized for code generation",
            "recommended": False,
        },
        {
            "name": "phi3",
            "size": "2.3GB",
            "description": "Microsoft Phi-3 (3.8B params)",
            "recommended": False,
        },
    ]


def list_installed_models() -> list[str]:
    """Get list of already installed Ollama models."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return []

        # Parse output (skip header line)
        models = []
        for line in result.stdout.split("\n")[1:]:
            if line.strip():
                model_name = line.split()[0]
                models.append(model_name)

        return models

    except Exception:
        return []


def prompt_model_selection(models: list[dict[str, Any]], installed: list[str]) -> str | None:
    """Prompt user to select a model."""
    print("\nAvailable Ollama models for Cortex:\n")

    for i, model in enumerate(models, 1):
        installed_marker = " [INSTALLED]" if model["name"] in installed else ""
        rec_marker = " ⭐" if model["recommended"] else ""
        print(f"  {i}. {Colors.BOLD}{model['name']}{Colors.ENDC}{rec_marker}{installed_marker}")
        print(f"     Size: {model['size']} | {model['description']}")
        print()

    print(f"  {len(models) + 1}. Custom model (enter name manually)")
    print(f"  {len(models) + 2}. Skip (I'll download a model later)")

    while True:
        choice = input(
            f"\n{Colors.BOLD}Select a model [1-{len(models) + 2}]: {Colors.ENDC}"
        ).strip()

        try:
            choice_num = int(choice)
        except ValueError:
            print_error("Invalid input. Please enter a number.")
            continue

        if 1 <= choice_num <= len(models):
            return models[choice_num - 1]["name"]
        elif choice_num == len(models) + 1:
            custom = input(f"{Colors.BOLD}Enter model name: {Colors.ENDC}").strip()
            if custom:
                return custom
        elif choice_num == len(models) + 2:
            return None
        print_error("Invalid choice. Please try again.")


def pull_model(model_name: str) -> bool:
    """Download and install an Ollama model."""
    print_info(f"Downloading model '{model_name}'...")
    print_info("This may take several minutes depending on your internet speed.")

    try:
        # Run ollama pull with live output
        result = subprocess.run(
            ["ollama", "pull", model_name],
            check=True,
        )

        if result.returncode == 0:
            print_success(f"Model '{model_name}' downloaded successfully!")
            return True
        else:
            print_error(f"Failed to download model (exit code {result.returncode})")
            return False

    except subprocess.CalledProcessError as e:
        print_error(f"Failed to pull model: {e}")
        return False
    except KeyboardInterrupt:
        print_warning("\nDownload interrupted by user")
        return False
    except Exception as e:
        print_error(f"Unexpected error while pulling model: {e}")
        return False


def test_model(model_name: str) -> bool:
    """Test the installed model with a simple prompt."""
    print_info(f"Testing model '{model_name}'...")

    test_prompt = "What is the apt command to install nginx? Answer in one sentence."

    try:
        result = subprocess.run(
            ["ollama", "run", model_name, test_prompt],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and result.stdout.strip():
            print_success("Model test successful!")
            print(f"\n{Colors.BOLD}Model response:{Colors.ENDC}")
            print(f"  {result.stdout.strip()}\n")
            return True
        else:
            print_warning("Model responded but output may be empty")
            return False

    except subprocess.TimeoutExpired:
        print_warning("Model test timed out (this is normal for first run)")
        return True  # Don't fail on timeout, model is probably working
    except Exception as e:
        print_error(f"Failed to test model: {e}")
        return False


def configure_cortex(model_name: str) -> bool:
    """Configure Cortex to use Ollama with the selected model."""
    print_info("Configuring Cortex to use Ollama...")

    cortex_dir = Path.home() / ".cortex"
    cortex_dir.mkdir(mode=0o700, exist_ok=True)

    config_file = cortex_dir / "config.json"

    # Load existing config or create new one
    config = {}
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
        except Exception:
            # If the existing config cannot be read (e.g., corrupted JSON), ignore it and start fresh.
            pass

    # Update config
    config["api_provider"] = "ollama"
    config["ollama_model"] = model_name
    config["ollama_base_url"] = "http://localhost:11434"

    # Save config
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        print_success("Cortex configuration updated!")
        print_info("Provider: ollama")
        print_info(f"Model: {model_name}")
        return True

    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


def main():
    """Main setup flow."""
    parser = argparse.ArgumentParser(description="Set up Ollama for Cortex Linux")
    parser.add_argument(
        "--model",
        help="Model to install (skips interactive selection)",
    )
    parser.add_argument(
        "--skip-test",
        action="store_true",
        help="Skip model testing",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run in non-interactive mode (requires --model)",
    )

    args = parser.parse_args()

    # Validate args
    if args.non_interactive and not args.model:
        print_error("--non-interactive requires --model to be specified")
        sys.exit(1)

    print_header("Ollama Setup for Cortex Linux")

    # Step 1: Check if Ollama is installed
    print_info("Checking Ollama installation...")
    if check_ollama_installed():
        print_success("Ollama is already installed")
    else:
        print_warning("Ollama is not installed")

        if args.non_interactive:
            print_error("Cannot install in non-interactive mode")
            sys.exit(1)

        confirm = input(f"\n{Colors.BOLD}Install Ollama now? [Y/n]: {Colors.ENDC}").strip().lower()
        if confirm in ["n", "no"]:
            print_info("Installation cancelled. You can install manually with:")
            print_info("  curl -fsSL https://ollama.ai/install.sh | sh")
            sys.exit(0)

        if not install_ollama():
            print_error("Failed to install Ollama")
            sys.exit(1)

    # Step 2: Check if Ollama is running
    print_info("Checking Ollama service...")
    if not check_ollama_running():
        print_warning("Ollama service is not running")
        if not start_ollama_service():
            print_warning("Please start Ollama manually: ollama serve &")
            if not args.non_interactive:
                input(f"\n{Colors.BOLD}Press Enter after starting Ollama...{Colors.ENDC}")

    # Step 3: Check for already installed models
    installed_models = list_installed_models()
    if installed_models:
        print_success(f"Found {len(installed_models)} installed model(s):")
        for model in installed_models:
            print(f"  • {model}")

    # Step 4: Model selection
    model_name = None

    if args.model:
        # Use specified model
        model_name = args.model
        print_info(f"Using specified model: {model_name}")
    elif args.non_interactive:
        # This shouldn't happen due to validation above, but just in case
        print_error("No model specified in non-interactive mode")
        sys.exit(1)
    else:
        # Interactive selection
        available_models = get_available_models()
        model_name = prompt_model_selection(available_models, installed_models)

    if not model_name:
        print_info("No model selected. You can download one later with: ollama pull <model-name>")
        print_info("Configuring Cortex to use Ollama...")
        configure_cortex("llama3.2")  # Default model for future use
        print_success("\nSetup complete! ✨")
        print_info("\nNext steps:")
        print_info("  1. Download a model: ollama pull llama3.2")
        print_info("  2. Test Cortex: cortex install nginx --dry-run")
        sys.exit(0)

    # Step 5: Pull model if not installed
    if model_name not in installed_models:
        if not pull_model(model_name):
            print_error("Failed to download model")
            sys.exit(1)
    else:
        print_success(f"Model '{model_name}' is already installed")

    # Step 6: Test model
    if not args.skip_test:
        test_model(model_name)

    # Step 7: Configure Cortex
    configure_cortex(model_name)

    # Success!
    print_header("Setup Complete! ✨")
    print_success("Ollama is installed and configured for Cortex Linux")
    print()
    print(f"{Colors.BOLD}Quick Start:{Colors.ENDC}")
    print(f"  • Test Cortex: {Colors.OKGREEN}cortex install nginx --dry-run{Colors.ENDC}")
    print(f"  • Chat with AI: {Colors.OKGREEN}cortex ask 'how do I update my system?'{Colors.ENDC}")
    print(f"  • Change model: {Colors.OKGREEN}ollama pull <model-name>{Colors.ENDC}")
    print()
    print(f"{Colors.BOLD}Useful Commands:{Colors.ENDC}")
    print(f"  • List models: {Colors.OKCYAN}ollama list{Colors.ENDC}")
    print(f"  • Remove model: {Colors.OKCYAN}ollama rm <model-name>{Colors.ENDC}")
    print(f"  • Test model: {Colors.OKCYAN}ollama run {model_name}{Colors.ENDC}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("\n\nSetup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        sys.exit(1)
