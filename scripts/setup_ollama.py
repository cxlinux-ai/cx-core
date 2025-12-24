#!/usr/bin/env python3
"""
Post-installation setup script for Cortex Linux.
Automatically installs and configures Ollama for local LLM support.

Author: Cortex Linux Team
License: Apache 2.0
"""

import logging
import os
import shutil
import subprocess
import sys
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_ollama_installed() -> bool:
    """Check if Ollama is already installed."""
    return shutil.which("ollama") is not None


def install_ollama() -> bool:
    """
    Install Ollama using the official installation script.
    
    Returns:
        True if installation succeeded, False otherwise
    """
    if is_ollama_installed():
        logger.info("✅ Ollama already installed")
        return True

    logger.info("📦 Installing Ollama for local LLM support...")
    logger.info("   This enables privacy-first, offline package management")
    
    try:
        # Download installation script
        logger.info("   Downloading Ollama installer...")
        result = subprocess.run(
            ["curl", "-fsSL", "https://ollama.com/install.sh"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode != 0:
            logger.error(f"❌ Failed to download Ollama installer: {result.stderr}")
            return False

        # Execute installation script
        logger.info("   Running Ollama installer...")
        install_result = subprocess.run(
            ["sh", "-c", result.stdout],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if install_result.returncode == 0:
            logger.info("✅ Ollama installed successfully")
            return True
        else:
            logger.warning(f"⚠️  Ollama installation encountered issues: {install_result.stderr}")
            # Don't fail the entire setup if Ollama fails
            return False

    except subprocess.TimeoutExpired:
        logger.warning("⚠️  Ollama installation timed out")
        return False
    except Exception as e:
        logger.warning(f"⚠️  Ollama installation failed: {e}")
        return False


def start_ollama_service() -> bool:
    """
    Start the Ollama service.
    
    Returns:
        True if service started, False otherwise
    """
    if not is_ollama_installed():
        return False

    logger.info("🚀 Starting Ollama service...")
    
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
        logger.info("✅ Ollama service started")
        return True

    except Exception as e:
        logger.warning(f"⚠️  Failed to start Ollama service: {e}")
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
    
    print(f"\n  6. Skip (download later)")
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
    Pull the selected model for Cortex.
    
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

    logger.info(f"📥 Pulling {model_name} - this may take 5-10 minutes...")
    logger.info("   Downloading model from Ollama registry...")
    
    try:
        # Show real-time progress
        process = subprocess.Popen(
            ["ollama", "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        
        # Display progress in real-time
        for line in process.stdout:
            # Show progress lines
            if line.strip():
                print(f"   {line.strip()}")
        
        process.wait(timeout=600)  # 10 minutes timeout
        
        if process.returncode == 0:
            logger.info(f"✅ {model_name} downloaded successfully")
            return True
        else:
            logger.warning(f"⚠️  Model pull failed, you can try: ollama pull {model_name}")
            return False

    except subprocess.TimeoutExpired:
        logger.warning("⚠️  Model download timed out - try again with: ollama pull {model_name}")
        return False
    except Exception as e:
        logger.warning(f"⚠️  Model pull failed: {e}")
        return False


def setup_ollama():
    """Main setup function for Ollama integration."""
    logger.info("=" * 60)
    logger.info("Cortex Linux - Setting up local LLM support")
    logger.info("=" * 60)
    
    # Check if we should skip Ollama setup
    if os.getenv("CORTEX_SKIP_OLLAMA_SETUP") == "1":
        logger.info("⏭️  Skipping Ollama setup (CORTEX_SKIP_OLLAMA_SETUP=1)")
        return
    
    # Check if running in CI/automated environment
    if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
        logger.info("⏭️  Skipping Ollama setup in CI environment")
        return

    # Install Ollama
    if not install_ollama():
        logger.warning("⚠️  Ollama installation skipped")
        logger.info("ℹ️  You can install it later with: curl -fsSL https://ollama.com/install.sh | sh")
        logger.info("ℹ️  Cortex will fall back to cloud providers (Claude/OpenAI) if configured")
        return

    # Start service
    if not start_ollama_service():
        logger.info("ℹ️  Ollama service will start automatically on first use")
        return

    # Interactive model selection (skip in non-interactive environments)
    if sys.stdin.isatty():
        selected_model = prompt_model_selection()
        pull_selected_model(selected_model)
    else:
        logger.info("ℹ️  Non-interactive mode detected - skipping model download")
        logger.info("   You can pull a model later with: ollama pull <model>")
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ Cortex Linux setup complete!")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Quick Start:")
    logger.info("  1. Run: cortex install nginx --dry-run")
    logger.info("  2. No API keys needed - uses local Ollama by default")
    logger.info("  3. Optional: Set ANTHROPIC_API_KEY or OPENAI_API_KEY for cloud fallback")
    logger.info("")


if __name__ == "__main__":
    setup_ollama()
