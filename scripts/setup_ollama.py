#!/usr/bin/env python3
"""
Post-installation setup script for Cortex Linux.
Automatically installs and configures Ollama for local LLM support.

Author: Cortex Linux Team
License: Apache 2.0
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_ollama_installed() -> bool:
    """Check if Ollama is already installed."""
    return shutil.which("ollama") is not None


def install_ollama() -> bool:
    """
    Install Ollama using the official installation script with progress tracking.

    Returns:
        True if installation succeeded, False otherwise
    """
    if is_ollama_installed():
        logger.info("✅ Ollama already installed")
        return True

    print("\n📦 Installing Ollama for local LLM support...")
    print("   This enables privacy-first, offline package management")
    print("   ⏳ This may take 1-2 minutes and will prompt for sudo password...\n")

    try:
        # Run the official Ollama installer directly (it handles sudo internally)
        start_time = time.time()

        process = subprocess.Popen(
            ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        last_line = ""
        # Stream output and show progress
        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue

            # Show important messages
            if any(
                x in stripped.lower()
                for x in [
                    "installing",
                    "downloading",
                    "creating",
                    "starting",
                    "enabling",
                    "done",
                    "success",
                    "password",
                    ">>>",
                ]
            ):
                # Avoid duplicate lines
                if stripped != last_line:
                    print(f"   {stripped}")
                    sys.stdout.flush()
                    last_line = stripped

        process.wait(timeout=600)

        install_time = time.time() - start_time

        if process.returncode == 0 and is_ollama_installed():
            print(f"\n   ✅ Ollama installed successfully in {int(install_time)}s\n")
            return True
        else:
            print(
                f"\n   ⚠️  Ollama installation encountered issues (exit code: {process.returncode})"
            )
            print("   💡 Try running manually: curl -fsSL https://ollama.com/install.sh | sh")
            return False

    except subprocess.TimeoutExpired:
        print("\n   ⚠️  Ollama installation timed out (exceeded 10 minutes)")
        print("   💡 Try running manually: curl -fsSL https://ollama.com/install.sh | sh")
        return False
    except KeyboardInterrupt:
        print("\n\n   ⚠️  Installation cancelled by user")
        print("   💡 You can install Ollama later with: cortex-setup-ollama")
        return False
    except Exception as e:
        print(f"\n   ⚠️  Ollama installation failed: {e}")
        print("   💡 Try running manually: curl -fsSL https://ollama.com/install.sh | sh")
        return False


def start_ollama_service() -> bool:
    """
    Start the Ollama service.

    Returns:
        True if service started, False otherwise
    """
    if not is_ollama_installed():
        return False

    print("🚀 Starting Ollama service...")

    try:
        # Start Ollama in background
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Give it a moment to start
        time.sleep(2)
        print("✅ Ollama service started\n")
        return True

    except Exception as e:
        print(f"⚠️  Failed to start Ollama service: {e}\n")
        return False


def prompt_model_selection() -> str:
    """
    Prompt user to select which Ollama model to download.

    Returns:
        Model name selected by user
    """
    print("\n" + "=" * 60)
    print("📦 Select Ollama Model to Download")
    print("=" * 60)
    print("\nAvailable models (Quality vs Size trade-off):\n")

    models = [
        ("codellama:7b", "3.8 GB", "Good for code, fast (DEFAULT)", True),
        ("llama3:8b", "4.7 GB", "Balanced, general purpose"),
        ("phi3:mini", "1.9 GB", "Lightweight, quick responses"),
        ("deepseek-coder:6.7b", "3.8 GB", "Code-optimized"),
        ("mistral:7b", "4.1 GB", "Fast and efficient"),
    ]

    for i, (name, size, desc, *is_default) in enumerate(models, 1):
        default_marker = " ⭐" if is_default else ""
        print(f"  {i}. {name:<20} | {size:<8} | {desc}{default_marker}")

    print("\n  6. Skip (download later)")
    print("\n" + "=" * 60)

    try:
        choice = input("\nSelect option (1-6) [Press Enter for default]: ").strip()

        if not choice:
            # Default to codellama:7b
            return "codellama:7b"

        choice_num = int(choice)

        if choice_num == 6:
            return "skip"
        elif 1 <= choice_num <= 5:
            return models[choice_num - 1][0]
        else:
            print("⚠️  Invalid choice, using default (codellama:7b)")
            return "codellama:7b"

    except (ValueError, KeyboardInterrupt):
        print("\n⚠️  Using default model (codellama:7b)")
        return "codellama:7b"


def pull_selected_model(model_name: str) -> bool:
    """
    Pull the selected model for Cortex with progress tracking.

    Args:
        model_name: Name of the model to pull

    Returns:
        True if model pulled successfully, False otherwise
    """
    if not is_ollama_installed():
        return False

    if model_name == "skip":
        logger.info("⏭️  Skipping model download - you can pull one later with: ollama pull <model>")
        return True

    # Model size estimates for time calculation
    model_sizes = {
        "codellama:7b": 3.8,
        "llama3:8b": 4.7,
        "phi3:mini": 1.9,
        "deepseek-coder:6.7b": 3.8,
        "mistral:7b": 4.1,
    }

    model_size_gb = model_sizes.get(model_name, 4.0)

    print(f"\n📥 Pulling {model_name} ({model_size_gb} GB)...")
    print("⏳ Downloading model - showing progress with speed and time estimates\n")

    try:
        start_time = time.time()
        last_percent = -1
        last_update_time = start_time

        # Show real-time progress with enhanced tracking
        process = subprocess.Popen(
            ["ollama", "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Track which layer we're downloading (the big one)
        main_layer = None

        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue

            # Skip repetitive manifest lines
            if "pulling manifest" in stripped:
                if not main_layer:
                    print("   Preparing download...", end="\r", flush=True)
                continue

            # Handle completion messages
            if "verifying sha256" in stripped:
                print("\n   Verifying download integrity...")
                continue
            if "writing manifest" in stripped:
                print("   Finalizing installation...")
                continue
            if stripped == "success":
                print("   ✓ Installation complete!")
                continue

            # Look for actual download progress lines
            if (
                "pulling" in stripped
                and ":" in stripped
                and ("%" in stripped or "GB" in stripped or "MB" in stripped)
            ):
                # Extract layer ID
                layer_match = re.search(r"pulling ([a-f0-9]+):", stripped)
                if layer_match:
                    current_layer = layer_match.group(1)

                    # Identify the main (largest) layer - it will have percentage and size info
                    if "%" in stripped and ("GB" in stripped or "MB" in stripped):
                        if not main_layer:
                            main_layer = current_layer

                        # Only show progress for the main layer
                        if current_layer == main_layer:
                            # Extract percentage
                            percent_match = re.search(r"(\d+)%", stripped)
                            if percent_match:
                                percent = int(percent_match.group(1))
                                current_time = time.time()

                                # Only update every 1% or every second to reduce flicker
                                if percent != last_percent and (
                                    percent % 1 == 0 or current_time - last_update_time > 1
                                ):
                                    elapsed = current_time - start_time

                                    if percent > 0 and elapsed > 1:
                                        downloaded_gb = model_size_gb * (percent / 100.0)
                                        speed_mbps = (downloaded_gb * 1024) / elapsed

                                        # Calculate ETA
                                        if percent < 100 and speed_mbps > 0:
                                            remaining_gb = model_size_gb - downloaded_gb
                                            eta_seconds = (remaining_gb * 1024) / speed_mbps
                                            eta_str = str(timedelta(seconds=int(eta_seconds)))

                                            # Create progress bar
                                            bar_length = 40
                                            filled = int(bar_length * percent / 100)
                                            bar = "█" * filled + "░" * (bar_length - filled)

                                            # Single line progress update
                                            print(
                                                f"   [{bar}] {percent:3d}% | {downloaded_gb:.2f}/{model_size_gb} GB | {speed_mbps:.1f} MB/s | ETA: {eta_str}   ",
                                                end="\r",
                                                flush=True,
                                            )
                                        elif percent == 100:
                                            bar = "█" * 40
                                            print(
                                                f"   [{bar}] 100% | {model_size_gb}/{model_size_gb} GB | {speed_mbps:.1f} MB/s | Complete!   ",
                                                end="\r",
                                                flush=True,
                                            )
                                    else:
                                        # Early in download
                                        bar_length = 40
                                        filled = int(bar_length * percent / 100)
                                        bar = "█" * filled + "░" * (bar_length - filled)
                                        print(
                                            f"   [{bar}] {percent:3d}% | Calculating speed...                              ",
                                            end="\r",
                                            flush=True,
                                        )

                                    last_percent = percent
                                    last_update_time = current_time

        print("\n")  # Move to new line after progress completes
        process.wait(timeout=900)

        total_time = time.time() - start_time
        if process.returncode == 0:
            avg_speed = (model_size_gb * 1024) / total_time if total_time > 0 else 0
            print(f"✅ {model_name} downloaded successfully!")
            print(
                f"   Total time: {str(timedelta(seconds=int(total_time)))} | Average speed: {avg_speed:.1f} MB/s\n"
            )
            return True
        else:
            logger.warning(f"⚠️  Model pull failed, you can try: ollama pull {model_name}")
            return False

    except subprocess.TimeoutExpired:
        logger.warning(
            f"⚠️  Model download timed out (15 min limit) - try again with: ollama pull {model_name}"
        )
        return False
    except Exception as e:
        logger.warning(f"⚠️  Model pull failed: {e}")
        return False


def setup_ollama():
    """Main setup function for Ollama integration."""
    print("\n" + "=" * 70)
    print("🚀 Cortex Linux - Initial Setup")
    print("=" * 70 + "\n")

    # Check if we should skip Ollama setup
    if os.getenv("CORTEX_SKIP_OLLAMA_SETUP") == "1":
        print("⏭️  Skipping Ollama setup (CORTEX_SKIP_OLLAMA_SETUP=1)\n")
        return

    # Check if running in CI/automated environment
    if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
        print("⏭️  Skipping Ollama setup in CI environment\n")
        return

    # Prompt user if they want to install Ollama (only in interactive mode)
    if sys.stdin.isatty():
        print("Cortex can use local AI models via Ollama for privacy-first, offline operation.")
        print("This means:")
        print("  • No API keys needed")
        print("  • Works completely offline")
        print("  • Your data never leaves your machine")
        print("  • Free to use (no API costs)")
        print()
        print("Ollama will download a ~2-4 GB AI model to your system.")
        print()

        while True:
            response = input("Would you like to install Ollama now? (y/n) [y]: ").strip().lower()
            if response in ["", "y", "yes"]:
                print()
                break
            elif response in ["n", "no"]:
                print("\n✓ Skipping Ollama installation")
                print("ℹ️  You can install it later by running: cortex-setup-ollama")
                print("ℹ️  Or set up API keys for Claude/OpenAI instead\n")
                return
            else:
                print("Please enter 'y' or 'n'")
    else:
        print("ℹ️  Non-interactive mode - skipping Ollama setup")
        print("   Run 'cortex-setup-ollama' to set up Ollama manually\n")
        return

    # Install Ollama
    if not install_ollama():
        print("⚠️  Ollama installation skipped")
        print("ℹ️  You can install it later with: curl -fsSL https://ollama.com/install.sh | sh")
        print("ℹ️  Cortex will fall back to cloud providers (Claude/OpenAI) if configured\n")
        return

    # Start service
    if not start_ollama_service():
        print("ℹ️  Ollama service will start automatically on first use\n")

    # Interactive model selection
    selected_model = prompt_model_selection()
    pull_selected_model(selected_model)

    print("=" * 70)
    print("✅ Cortex Linux setup complete!")
    print("=" * 70)
    print("\nQuick Start:")
    print("  1. Run: cortex install nginx --dry-run")
    print("  2. No API keys needed - uses local Ollama by default")
    print("  3. Optional: Set ANTHROPIC_API_KEY or OPENAI_API_KEY for cloud fallback\n")


if __name__ == "__main__":
    setup_ollama()
