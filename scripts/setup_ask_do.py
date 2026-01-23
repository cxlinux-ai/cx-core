#!/usr/bin/env python3
"""
Setup script for Cortex `ask --do` command.

This script sets up everything needed for the AI-powered command execution:
1. Installs required Python dependencies
2. Sets up Ollama Docker container with a small model
3. Installs and starts the Cortex Watch service
4. Configures shell hooks for terminal monitoring

Usage:
    python scripts/setup_ask_do.py [--no-docker] [--model MODEL] [--skip-watch]

Options:
    --no-docker     Skip Docker/Ollama setup (use cloud LLM only)
    --model MODEL   Ollama model to install (default: mistral)
    --skip-watch    Skip watch service installation
    --uninstall     Remove all ask --do components
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


# ANSI colors
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


def print_header(text: str):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'═' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'═' * 60}{Colors.END}\n")


def print_step(text: str):
    """Print a step."""
    print(f"{Colors.BLUE}▶{Colors.END} {text}")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}✓{Colors.END} {text}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠{Colors.END} {text}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}✗{Colors.END} {text}")


def run_cmd(
    cmd: list[str], check: bool = True, capture: bool = False, timeout: int = 300
) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    try:
        result = subprocess.run(
            cmd, check=check, capture_output=capture, text=True, timeout=timeout
        )
        return result
    except subprocess.CalledProcessError as e:
        if capture:
            print_error(f"Command failed: {' '.join(cmd)}")
            if e.stderr:
                print(f"  {Colors.DIM}{e.stderr[:200]}{Colors.END}")
        raise
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out: {' '.join(cmd)}")
        raise


def check_docker() -> bool:
    """Check if Docker is installed and running."""
    try:
        result = run_cmd(["docker", "info"], capture=True, check=False)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_ollama_container() -> tuple[bool, bool]:
    """Check if Ollama container exists and is running.

    Returns: (exists, running)
    """
    try:
        result = run_cmd(
            ["docker", "ps", "-a", "--filter", "name=ollama", "--format", "{{.Status}}"],
            capture=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False, False

        status = result.stdout.strip().lower()
        running = "up" in status
        return True, running
    except Exception:
        return False, False


def setup_ollama(model: str = "mistral") -> bool:
    """Set up Ollama Docker container and pull a model."""
    print_header("Setting up Ollama (Local LLM)")

    # Check Docker
    print_step("Checking Docker...")
    if not check_docker():
        print_error("Docker is not installed or not running")
        print(f"  {Colors.DIM}Install Docker: https://docs.docker.com/get-docker/{Colors.END}")
        print(f"  {Colors.DIM}Then run: sudo systemctl start docker{Colors.END}")
        return False
    print_success("Docker is available")

    # Check existing container
    exists, running = check_ollama_container()

    if exists and running:
        print_success("Ollama container is already running")
    elif exists and not running:
        print_step("Starting existing Ollama container...")
        run_cmd(["docker", "start", "ollama"])
        print_success("Ollama container started")
    else:
        # Pull and run Ollama
        print_step("Pulling Ollama Docker image...")
        run_cmd(["docker", "pull", "ollama/ollama"])
        print_success("Ollama image pulled")

        print_step("Starting Ollama container...")
        run_cmd(
            [
                "docker",
                "run",
                "-d",
                "--name",
                "ollama",
                "-p",
                "11434:11434",
                "-v",
                "ollama:/root/.ollama",
                "--restart",
                "unless-stopped",
                "ollama/ollama",
            ]
        )
        print_success("Ollama container started")

        # Wait for container to be ready
        print_step("Waiting for Ollama to initialize...")
        time.sleep(5)

    # Check if model exists
    print_step(f"Checking for {model} model...")
    try:
        result = run_cmd(["docker", "exec", "ollama", "ollama", "list"], capture=True, check=False)
        if model in result.stdout:
            print_success(f"Model {model} is already installed")
            return True
    except Exception:
        pass

    # Pull model
    print_step(f"Pulling {model} model (this may take a few minutes)...")
    print(f"  {Colors.DIM}Model size: ~4GB for mistral, ~2GB for phi{Colors.END}")

    try:
        # Use subprocess directly for streaming output
        process = subprocess.Popen(
            ["docker", "exec", "ollama", "ollama", "pull", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        for line in process.stdout:
            line = line.strip()
            if line:
                # Show progress
                if "pulling" in line.lower() or "%" in line:
                    print(f"\r  {Colors.DIM}{line[:70]}{Colors.END}", end="", flush=True)

        process.wait()
        print()  # New line after progress

        if process.returncode == 0:
            print_success(f"Model {model} installed successfully")
            return True
        else:
            print_error(f"Failed to pull model {model}")
            return False

    except Exception as e:
        print_error(f"Error pulling model: {e}")
        return False


def setup_watch_service() -> bool:
    """Install and start the Cortex Watch service."""
    print_header("Setting up Cortex Watch Service")

    # Check if service is already installed
    service_file = Path.home() / ".config" / "systemd" / "user" / "cortex-watch.service"

    if service_file.exists():
        print_step("Watch service is already installed, checking status...")
        result = run_cmd(
            ["systemctl", "--user", "is-active", "cortex-watch.service"], capture=True, check=False
        )
        if result.stdout.strip() == "active":
            print_success("Cortex Watch service is running")
            return True
        else:
            print_step("Starting watch service...")
            run_cmd(["systemctl", "--user", "start", "cortex-watch.service"], check=False)
    else:
        # Install the service
        print_step("Installing Cortex Watch service...")

        try:
            # Import and run the installation
            from cortex.watch_service import install_service

            success, msg = install_service()

            if success:
                print_success("Watch service installed and started")
                print(
                    f"  {Colors.DIM}{msg[:200]}...{Colors.END}"
                    if len(msg) > 200
                    else f"  {Colors.DIM}{msg}{Colors.END}"
                )
            else:
                print_error(f"Failed to install watch service: {msg}")
                return False

        except ImportError:
            print_warning("Could not import watch_service module")
            print_step("Installing via CLI...")

            result = run_cmd(
                ["cortex", "watch", "--install", "--service"], capture=True, check=False
            )
            if result.returncode == 0:
                print_success("Watch service installed via CLI")
            else:
                print_error("Failed to install watch service")
                return False

    # Verify service is running
    result = run_cmd(
        ["systemctl", "--user", "is-active", "cortex-watch.service"], capture=True, check=False
    )
    if result.stdout.strip() == "active":
        print_success("Watch service is active and monitoring terminals")
        return True
    else:
        print_warning("Watch service installed but not running")
        return True  # Still return True as installation succeeded


def setup_shell_hooks() -> bool:
    """Set up shell hooks for terminal monitoring."""
    print_header("Setting up Shell Hooks")

    cortex_dir = Path.home() / ".cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)

    # Create watch hook script
    hook_file = cortex_dir / "watch_hook.sh"
    hook_content = """#!/bin/bash
# Cortex Terminal Watch Hook
# This hook logs commands for Cortex to monitor during manual intervention

__cortex_last_histnum=""
__cortex_log_cmd() {
    local histnum="$(history 1 | awk '{print $1}')"
    [[ "$histnum" == "$__cortex_last_histnum" ]] && return
    __cortex_last_histnum="$histnum"

    local cmd="$(history 1 | sed "s/^[ ]*[0-9]*[ ]*//")"
    [[ -z "${cmd// /}" ]] && return
    [[ "$cmd" == cortex* ]] && return
    [[ "$cmd" == *"source"*".cortex"* ]] && return
    [[ "$cmd" == *"watch_hook"* ]] && return
    [[ -n "$CORTEX_TERMINAL" ]] && return

    # Include terminal ID (TTY) in the log
    local tty_name="$(tty 2>/dev/null | sed 's|/dev/||' | tr '/' '_')"
    echo "${tty_name:-unknown}|$cmd" >> ~/.cortex/terminal_watch.log
}
export PROMPT_COMMAND='history -a; __cortex_log_cmd'
echo "✓ Cortex is now watching this terminal"
"""

    print_step("Creating watch hook script...")
    hook_file.write_text(hook_content)
    hook_file.chmod(0o755)
    print_success(f"Created {hook_file}")

    # Add to .bashrc if not already present
    bashrc = Path.home() / ".bashrc"
    marker = "# Cortex Terminal Watch Hook"

    if bashrc.exists():
        content = bashrc.read_text()
        if marker not in content:
            print_step("Adding hook to .bashrc...")

            bashrc_addition = f"""
{marker}
__cortex_last_histnum=""
__cortex_log_cmd() {{
    local histnum="$(history 1 | awk '{{print $1}}')"
    [[ "$histnum" == "$__cortex_last_histnum" ]] && return
    __cortex_last_histnum="$histnum"

    local cmd="$(history 1 | sed "s/^[ ]*[0-9]*[ ]*//")"
    [[ -z "${{cmd// /}}" ]] && return
    [[ "$cmd" == cortex* ]] && return
    [[ "$cmd" == *"source"*".cortex"* ]] && return
    [[ "$cmd" == *"watch_hook"* ]] && return
    [[ -n "$CORTEX_TERMINAL" ]] && return

    local tty_name="$(tty 2>/dev/null | sed 's|/dev/||' | tr '/' '_')"
    echo "${{tty_name:-unknown}}|$cmd" >> ~/.cortex/terminal_watch.log
}}
export PROMPT_COMMAND='history -a; __cortex_log_cmd'

alias cw="source ~/.cortex/watch_hook.sh"
"""
            with open(bashrc, "a") as f:
                f.write(bashrc_addition)
            print_success("Hook added to .bashrc")
        else:
            print_success("Hook already in .bashrc")

    # Add to .zshrc if it exists
    zshrc = Path.home() / ".zshrc"
    if zshrc.exists():
        content = zshrc.read_text()
        if marker not in content:
            print_step("Adding hook to .zshrc...")

            zshrc_addition = f"""
{marker}
typeset -g __cortex_last_cmd=""
cortex_watch_hook() {{
    local cmd="$(fc -ln -1 | sed 's/^[[:space:]]*//')"
    [[ -z "$cmd" ]] && return
    [[ "$cmd" == "$__cortex_last_cmd" ]] && return
    __cortex_last_cmd="$cmd"
    [[ "$cmd" == cortex* ]] && return
    [[ "$cmd" == *".cortex"* ]] && return
    [[ -n "$CORTEX_TERMINAL" ]] && return
    local tty_name="$(tty 2>/dev/null | sed 's|/dev/||' | tr '/' '_')"
    echo "${{tty_name:-unknown}}|$cmd" >> ~/.cortex/terminal_watch.log
}}
precmd_functions+=(cortex_watch_hook)
"""
            with open(zshrc, "a") as f:
                f.write(zshrc_addition)
            print_success("Hook added to .zshrc")
        else:
            print_success("Hook already in .zshrc")

    return True


def check_api_keys() -> dict[str, bool]:
    """Check for available API keys."""
    print_header("Checking API Keys")

    keys = {
        "ANTHROPIC_API_KEY": False,
        "OPENAI_API_KEY": False,
    }

    # Check environment variables
    for key in keys:
        if os.environ.get(key):
            keys[key] = True
            print_success(f"{key} found in environment")

    # Check .env file
    env_file = Path.cwd() / ".env"
    if env_file.exists():
        content = env_file.read_text()
        for key in keys:
            if key in content and not keys[key]:
                keys[key] = True
                print_success(f"{key} found in .env file")

    # Report missing keys
    if not any(keys.values()):
        print_warning("No API keys found")
        print(f"  {Colors.DIM}For cloud LLM, set ANTHROPIC_API_KEY or OPENAI_API_KEY{Colors.END}")
        print(f"  {Colors.DIM}Or use local Ollama (--no-docker to skip){Colors.END}")

    return keys


def verify_installation() -> bool:
    """Verify the installation is working."""
    print_header("Verifying Installation")

    all_good = True

    # Check cortex command
    print_step("Checking cortex command...")
    result = run_cmd(["cortex", "--version"], capture=True, check=False)
    if result.returncode == 0:
        print_success(f"Cortex installed: {result.stdout.strip()}")
    else:
        print_error("Cortex command not found")
        all_good = False

    # Check watch service
    print_step("Checking watch service...")
    result = run_cmd(
        ["systemctl", "--user", "is-active", "cortex-watch.service"], capture=True, check=False
    )
    if result.stdout.strip() == "active":
        print_success("Watch service is running")
    else:
        print_warning("Watch service is not running")

    # Check Ollama
    print_step("Checking Ollama...")
    exists, running = check_ollama_container()
    if running:
        print_success("Ollama container is running")

        # Check if model is available
        result = run_cmd(["docker", "exec", "ollama", "ollama", "list"], capture=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            models = [
                line.split()[0] for line in result.stdout.strip().split("\n")[1:] if line.strip()
            ]
            if models:
                print_success(f"Models available: {', '.join(models[:3])}")
    elif exists:
        print_warning("Ollama container exists but not running")
    else:
        print_warning("Ollama not installed (will use cloud LLM)")

    # Check API keys
    api_keys = check_api_keys()
    has_llm = any(api_keys.values()) or running

    if not has_llm:
        print_error("No LLM available (need API key or Ollama)")
        all_good = False

    return all_good


def uninstall() -> bool:
    """Remove all ask --do components."""
    print_header("Uninstalling Cortex ask --do Components")

    # Stop and remove watch service
    print_step("Removing watch service...")
    run_cmd(["systemctl", "--user", "stop", "cortex-watch.service"], check=False)
    run_cmd(["systemctl", "--user", "disable", "cortex-watch.service"], check=False)

    service_file = Path.home() / ".config" / "systemd" / "user" / "cortex-watch.service"
    if service_file.exists():
        service_file.unlink()
        print_success("Watch service removed")

    # Remove shell hooks from .bashrc and .zshrc
    marker = "# Cortex Terminal Watch Hook"
    for rc_file in [Path.home() / ".bashrc", Path.home() / ".zshrc"]:
        if rc_file.exists():
            content = rc_file.read_text()
            if marker in content:
                print_step(f"Removing hook from {rc_file.name}...")
                lines = content.split("\n")
                new_lines = []
                skip = False
                for line in lines:
                    if marker in line:
                        skip = True
                    elif skip and line.strip() == "":
                        skip = False
                        continue
                    elif not skip:
                        new_lines.append(line)
                rc_file.write_text("\n".join(new_lines))
                print_success(f"Hook removed from {rc_file.name}")

    # Remove cortex directory files (but keep config)
    cortex_dir = Path.home() / ".cortex"
    files_to_remove = [
        "watch_hook.sh",
        "terminal_watch.log",
        "terminal_commands.json",
        "watch_service.log",
        "watch_service.pid",
        "watch_state.json",
    ]
    for filename in files_to_remove:
        filepath = cortex_dir / filename
        if filepath.exists():
            filepath.unlink()
    print_success("Cortex watch files removed")

    # Optionally remove Ollama container
    exists, _ = check_ollama_container()
    if exists:
        print_step("Ollama container found")
        response = input("  Remove Ollama container and data? [y/N]: ").strip().lower()
        if response == "y":
            run_cmd(["docker", "stop", "ollama"], check=False)
            run_cmd(["docker", "rm", "ollama"], check=False)
            run_cmd(["docker", "volume", "rm", "ollama"], check=False)
            print_success("Ollama container and data removed")
        else:
            print(f"  {Colors.DIM}Keeping Ollama container{Colors.END}")

    print_success("Uninstallation complete")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Setup script for Cortex ask --do command",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/setup_ask_do.py                    # Full setup with Ollama
  python scripts/setup_ask_do.py --no-docker        # Skip Docker/Ollama setup
  python scripts/setup_ask_do.py --model phi        # Use smaller phi model
  python scripts/setup_ask_do.py --uninstall        # Remove all components
""",
    )
    parser.add_argument("--no-docker", action="store_true", help="Skip Docker/Ollama setup")
    parser.add_argument(
        "--model", default="mistral", help="Ollama model to install (default: mistral)"
    )
    parser.add_argument("--skip-watch", action="store_true", help="Skip watch service installation")
    parser.add_argument("--uninstall", action="store_true", help="Remove all ask --do components")

    args = parser.parse_args()

    print(f"\n{Colors.BOLD}{Colors.CYAN}")
    print("  ██████╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗")
    print(" ██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝")
    print(" ██║     ██║   ██║██████╔╝   ██║   █████╗   ╚███╔╝ ")
    print(" ██║     ██║   ██║██╔══██╗   ██║   ██╔══╝   ██╔██╗ ")
    print(" ╚██████╗╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗")
    print("  ╚═════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝")
    print(f"{Colors.END}")
    print(f"  {Colors.DIM}ask --do Setup Wizard{Colors.END}\n")

    if args.uninstall:
        return 0 if uninstall() else 1

    success = True

    # Step 1: Check API keys
    api_keys = check_api_keys()

    # Step 2: Setup Ollama (unless skipped)
    if not args.no_docker:
        if not setup_ollama(args.model):
            if not any(api_keys.values()):
                print_error("No LLM available - need either Ollama or API key")
                success = False
    else:
        print_warning("Skipping Docker/Ollama setup (--no-docker)")
        if not any(api_keys.values()):
            print_warning("No API keys found - you'll need to set one up")

    # Step 3: Setup watch service
    if not args.skip_watch:
        if not setup_watch_service():
            print_warning("Watch service setup had issues")
    else:
        print_warning("Skipping watch service (--skip-watch)")

    # Step 4: Setup shell hooks
    setup_shell_hooks()

    # Step 5: Verify installation
    if verify_installation():
        print_header("Setup Complete! 🎉")
        print(f"""
{Colors.GREEN}Everything is ready!{Colors.END}

{Colors.BOLD}To use Cortex ask --do:{Colors.END}
  cortex ask --do

{Colors.BOLD}To start an interactive session:{Colors.END}
  cortex ask --do "install nginx and configure it"

{Colors.BOLD}For terminal monitoring in existing terminals:{Colors.END}
  source ~/.cortex/watch_hook.sh
  {Colors.DIM}(or just type 'cw' after opening a new terminal){Colors.END}

{Colors.BOLD}To check status:{Colors.END}
  cortex watch --status
""")
        return 0
    else:
        print_header("Setup Completed with Warnings")
        print(f"""
{Colors.YELLOW}Some components may need attention.{Colors.END}

Run {Colors.CYAN}cortex watch --status{Colors.END} to check the current state.
""")
        return 1


if __name__ == "__main__":
    sys.exit(main())
