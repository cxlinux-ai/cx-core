#!/usr/bin/env python3
"""
Post-install hook for Cortex Linux.
Automatically runs after pip install to setup Ollama.
"""

import os
import sys


def run_setup():
    """Run Ollama setup after installation."""
    # Skip if in CI or if explicitly disabled
    if (
        os.getenv("CI")
        or os.getenv("GITHUB_ACTIONS")
        or os.getenv("CORTEX_SKIP_OLLAMA_SETUP") == "1"
    ):
        return

    # Check if already ran setup (marker file in user's home)
    marker_file = os.path.expanduser("~/.cortex/.setup_done")
    if os.path.exists(marker_file):
        return

    print("\n" + "=" * 70)
    print("🚀 Running Cortex post-installation setup...")
    print("=" * 70 + "\n")

    try:
        # Import and run the setup function
        from scripts.setup_ollama import setup_ollama

        setup_ollama()

        # Create marker file to prevent running again
        os.makedirs(os.path.dirname(marker_file), exist_ok=True)
        with open(marker_file, "w") as f:
            f.write("Setup completed\n")

    except Exception as e:
        print(f"⚠️  Ollama setup encountered an issue: {e}")
        print("ℹ️  You can run it manually later with: cortex-setup-ollama")
    finally:
        print("\n" + "=" * 70)
        print("💡 TIP: To re-run setup anytime, execute: cortex-setup-ollama")
        print("=" * 70)


if __name__ == "__main__":
    run_setup()
