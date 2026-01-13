import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()

DAEMON_DIR = Path(__file__).parent.parent
BUILD_SCRIPT = DAEMON_DIR / "scripts" / "build.sh"
INSTALL_SCRIPT = DAEMON_DIR / "scripts" / "install.sh"
INSTALL_LLM_SCRIPT = DAEMON_DIR / "scripts" / "install-llm.sh"
MODEL_DIR = Path.home() / ".cortex" / "models"
CONFIG_FILE = "/etc/cortex/daemon.yaml"
CONFIG_EXAMPLE = DAEMON_DIR / "config" / "cortexd.yaml.example"
LLM_ENV_FILE = "/etc/cortex/llm.env"
CORTEX_ENV_FILE = Path.home() / ".cortex" / ".env"

# Recommended models for local llama.cpp
RECOMMENDED_MODELS = {
    "1": {
        "name": "TinyLlama 1.1B (Fast & Lightweight)",
        "url": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "size": "600MB",
        "ram": "2GB",
        "description": "Best for testing and low-resource systems",
    },
    "2": {
        "name": "Phi 2.7B (Fast & Capable)",
        "url": "https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf",
        "size": "1.6GB",
        "ram": "3GB",
        "description": "Good balance of speed and capability",
    },
    "3": {
        "name": "Mistral 7B (Balanced)",
        "url": "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "size": "4GB",
        "ram": "8GB",
        "description": "Best for production with good balance of speed and quality",
    },
    "4": {
        "name": "Llama 2 13B (High Quality)",
        "url": "https://huggingface.co/TheBloke/Llama-2-13B-Chat-GGUF/resolve/main/llama-2-13b-chat.Q4_K_M.gguf",
        "size": "8GB",
        "ram": "16GB",
        "description": "Best for high-quality responses",
    },
}

# Cloud API providers
CLOUD_PROVIDERS = {
    "1": {
        "name": "Claude (Anthropic)",
        "provider": "claude",
        "env_var": "ANTHROPIC_API_KEY",
        "description": "Recommended - Best reasoning and safety",
    },
    "2": {
        "name": "OpenAI (GPT-4)",
        "provider": "openai",
        "env_var": "OPENAI_API_KEY",
        "description": "Popular choice with broad capabilities",
    },
}


def choose_llm_backend() -> str:
    """
    Let user choose between Cloud APIs or Local llama.cpp.

    Displays a table with options and prompts user to select.

    Returns:
        str: "cloud", "local", or "none"
    """
    console.print("\n[bold cyan]LLM Backend Configuration[/bold cyan]\n")
    console.print("Choose how Cortex will handle AI/LLM requests:\n")

    table = Table(title="LLM Backend Options")
    table.add_column("Option", style="cyan", width=8)
    table.add_column("Backend", style="green", width=20)
    table.add_column("Requirements", width=25)
    table.add_column("Best For", width=35)

    table.add_row(
        "1",
        "Cloud APIs",
        "API key (internet required)",
        "Best quality, no local resources needed",
    )
    table.add_row(
        "2",
        "Local llama.cpp",
        "2-16GB RAM, GGUF model",
        "Free, private, works offline",
    )
    table.add_row(
        "3",
        "None (skip)",
        "None",
        "Configure LLM later",
    )

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "Select LLM backend",
        choices=["1", "2", "3"],
        default="1",
    )

    if choice == "1":
        return "cloud"
    elif choice == "2":
        return "local"
    else:
        return "none"


def setup_cloud_api() -> dict | None:
    """
    Configure cloud API provider and get API key.

    Returns:
        dict | None: Configuration dict with provider and api_key, or None if cancelled.
    """
    console.print("\n[bold cyan]Cloud API Setup[/bold cyan]\n")

    table = Table(title="Available Cloud Providers")
    table.add_column("Option", style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("Description")

    for key, provider in CLOUD_PROVIDERS.items():
        table.add_row(key, provider["name"], provider["description"])

    console.print(table)
    console.print()

    choice = Prompt.ask("Select provider", choices=["1", "2"], default="1")
    provider_info = CLOUD_PROVIDERS[choice]

    console.print(f"\n[cyan]Selected: {provider_info['name']}[/cyan]")
    console.print(f"[dim]Environment variable: {provider_info['env_var']}[/dim]\n")

    # Check if API key already exists in environment
    existing_key = os.environ.get(provider_info["env_var"])
    if existing_key:
        console.print(f"[green]✓ Found existing {provider_info['env_var']} in environment[/green]")
        if not Confirm.ask("Do you want to use a different key?", default=False):
            return {
                "provider": provider_info["provider"],
                "api_key": existing_key,
                "env_var": provider_info["env_var"],
            }

    api_key = Prompt.ask(f"Enter your {provider_info['name']} API key", password=True)

    if not api_key:
        console.print("[yellow]No API key provided. Skipping cloud setup.[/yellow]")
        return None

    return {
        "provider": provider_info["provider"],
        "api_key": api_key,
        "env_var": provider_info["env_var"],
    }


def save_cloud_api_config(config: dict) -> None:
    """
    Save cloud API configuration to ~/.cortex/.env file.

    Args:
        config: Dict with provider, api_key, and env_var keys.
    """
    console.print("[cyan]Saving API configuration...[/cyan]")

    # Create ~/.cortex directory
    cortex_dir = Path.home() / ".cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)

    env_file = cortex_dir / ".env"

    # Read existing env file if it exists
    existing_lines = []
    if env_file.exists():
        with open(env_file) as f:
            existing_lines = f.readlines()

    # Update or add the API key
    env_var = config["env_var"]
    api_key = config["api_key"]
    provider = config["provider"]

    # Filter out existing entries for this env var and CORTEX_PROVIDER
    new_lines = [
        line
        for line in existing_lines
        if not line.startswith(f"{env_var}=") and not line.startswith("CORTEX_PROVIDER=")
    ]

    # Add new entries
    new_lines.append(f"CORTEX_PROVIDER={provider}\n")
    new_lines.append(f"{env_var}={api_key}\n")

    # Write back
    with open(env_file, "w") as f:
        f.writelines(new_lines)

    # Set restrictive permissions
    os.chmod(env_file, 0o600)

    console.print(f"[green]✓ API key saved to {env_file}[/green]")
    console.print(f"[green]✓ Provider set to: {provider}[/green]")


def check_llama_server() -> bool:
    """
    Check if llama-server is installed.

    Returns:
        bool: True if llama-server is available, False otherwise.
    """
    result = subprocess.run(
        ["which", "llama-server"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        console.print(f"[green]✓ llama-server found: {result.stdout.strip()}[/green]")
        return True

    # Check common locations
    common_paths = [
        "/usr/local/bin/llama-server",
        "/usr/bin/llama-server",
        str(Path.home() / ".local" / "bin" / "llama-server"),
    ]
    for path in common_paths:
        if Path(path).exists():
            console.print(f"[green]✓ llama-server found: {path}[/green]")
            return True

    console.print("[yellow]⚠ llama-server not found[/yellow]")
    console.print("[dim]Install from: https://github.com/ggerganov/llama.cpp[/dim]")
    return False


def install_llm_service(model_path: Path, threads: int = 4, ctx_size: int = 2048) -> bool:
    """
    Install and configure cortex-llm.service.

    Args:
        model_path: Path to the GGUF model file.
        threads: Number of CPU threads for inference.
        ctx_size: Context size in tokens.

    Returns:
        bool: True if installation succeeded, False otherwise.
    """
    console.print("\n[cyan]Installing cortex-llm service...[/cyan]")

    if not INSTALL_LLM_SCRIPT.exists():
        console.print(f"[red]Install script not found: {INSTALL_LLM_SCRIPT}[/red]")
        return False

    result = subprocess.run(
        [
            "sudo",
            str(INSTALL_LLM_SCRIPT),
            "install",
            str(model_path),
            str(threads),
            str(ctx_size),
        ],
        check=False,
    )

    return result.returncode == 0


def setup_local_llm() -> Path | None:
    """
    Set up local llama.cpp with GGUF model.

    Downloads model and installs cortex-llm.service.

    Returns:
        Path | None: Path to the model file, or None if setup failed.
    """
    console.print("\n[bold cyan]Local llama.cpp Setup[/bold cyan]\n")

    # Check for llama-server
    if not check_llama_server():
        console.print("\n[yellow]llama-server is required for local LLM.[/yellow]")
        console.print("[cyan]Install it first, then run this setup again.[/cyan]")
        console.print("\n[dim]Installation options:[/dim]")
        console.print("[dim]  1. Build from source: https://github.com/ggerganov/llama.cpp[/dim]")
        console.print("[dim]  2. Package manager (if available)[/dim]")

        if not Confirm.ask("\nContinue anyway (you can install llama-server later)?", default=False):
            return None

    # Download or select model
    model_path = download_model()
    if not model_path:
        return None

    # Configure threads
    import multiprocessing

    cpu_count = multiprocessing.cpu_count()
    default_threads = min(4, cpu_count)

    console.print(f"\n[cyan]CPU cores available: {cpu_count}[/cyan]")
    threads_str = Prompt.ask(
        "Number of threads for inference",
        default=str(default_threads),
    )
    threads = int(threads_str) if threads_str.isdigit() else default_threads

    # Install cortex-llm service
    if not install_llm_service(model_path, threads):
        console.print("[red]Failed to install cortex-llm service.[/red]")
        console.print("[yellow]You can install it manually later:[/yellow]")
        console.print(f"[dim]  sudo {INSTALL_LLM_SCRIPT} install {model_path} {threads}[/dim]")
        return model_path  # Still return model path for config

    # Save provider config
    cortex_dir = Path.home() / ".cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    env_file = cortex_dir / ".env"

    # Update .env file
    existing_lines = []
    if env_file.exists():
        with open(env_file) as f:
            existing_lines = f.readlines()

    new_lines = [
        line
        for line in existing_lines
        if not line.startswith("CORTEX_PROVIDER=") and not line.startswith("LLAMA_CPP_BASE_URL=")
    ]
    new_lines.append("CORTEX_PROVIDER=llama_cpp\n")
    new_lines.append("LLAMA_CPP_BASE_URL=http://127.0.0.1:8085\n")

    with open(env_file, "w") as f:
        f.writelines(new_lines)

    console.print(f"[green]✓ Provider set to: llama_cpp[/green]")
    console.print(f"[green]✓ LLM service URL: http://127.0.0.1:8085[/green]")

    return model_path


def check_daemon_built() -> bool:
    """
    Check if the cortexd daemon binary has been built.

    Checks for the existence of the cortexd binary at DAEMON_DIR / "build" / "cortexd".

    Returns:
        bool: True if the daemon binary exists, False otherwise.
    """
    return (DAEMON_DIR / "build" / "cortexd").exists()


def clean_build() -> None:
    """
    Remove the previous build directory to ensure a clean build.

    Removes DAEMON_DIR / "build" using sudo rm -rf. Prints status messages
    to console. On failure, logs an error and calls sys.exit(1) to terminate.

    Returns:
        None
    """
    build_dir = DAEMON_DIR / "build"
    if build_dir.exists():
        console.print(f"[cyan]Removing previous build directory: {build_dir}[/cyan]")
        result = subprocess.run(["sudo", "rm", "-rf", str(build_dir)], check=False)
        if result.returncode != 0:
            console.print("[red]Failed to remove previous build directory.[/red]")
            sys.exit(1)


def build_daemon() -> bool:
    """
    Build the cortexd daemon from source.

    Runs the BUILD_SCRIPT (daemon/scripts/build.sh) with "Release" argument
    using subprocess.run.

    Returns:
        bool: True if the build completed successfully (exit code 0), False otherwise.
    """
    console.print("[cyan]Building the daemon...[/cyan]")
    result = subprocess.run(["bash", str(BUILD_SCRIPT), "Release"], check=False)
    return result.returncode == 0


def install_daemon() -> bool:
    """
    Install the cortexd daemon system-wide.

    Runs the INSTALL_SCRIPT (daemon/scripts/install.sh) with sudo using
    subprocess.run.

    Returns:
        bool: True if the installation completed successfully (exit code 0),
              False otherwise.
    """
    console.print("[cyan]Installing the daemon...[/cyan]")
    result = subprocess.run(["sudo", str(INSTALL_SCRIPT)], check=False)
    return result.returncode == 0


def download_model() -> Path | None:
    """
    Download or select an LLM model for the cortex daemon.

    Presents options to use an existing model or download a new one from
    recommended sources or a custom URL. Validates and sanitizes URLs to
    prevent security issues.

    Returns:
        Path | None: Path to the downloaded/selected model file, or None if
                     download failed or was cancelled.
    """
    console.print("[cyan]Setting up LLM model...[/cyan]\n")

    # Check for existing models
    existing_models = []
    if MODEL_DIR.exists():
        existing_models = list(MODEL_DIR.glob("*.gguf"))

    if existing_models:
        console.print("[green]Found existing models in ~/.cortex/models:[/green]")
        for idx, model in enumerate(existing_models, 1):
            console.print(f"  {idx}. {model.name}")

        use_existing = Confirm.ask("\nDo you want to use an existing model?")
        if use_existing:
            if len(existing_models) == 1:
                return existing_models[0]
            else:
                choice = Prompt.ask(
                    "Select a model", choices=[str(i) for i in range(1, len(existing_models) + 1)]
                )
                return existing_models[int(choice) - 1]

        console.print("\n[cyan]Proceeding to download a new model...[/cyan]\n")

    # Display recommended models
    table = Table(title="Recommended Models")
    table.add_column("Option", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Size")
    table.add_column("Description")

    for key, model in RECOMMENDED_MODELS.items():
        table.add_row(key, model["name"], model["size"], model["description"])

    console.print(table)
    console.print("\n[cyan]Option 4:[/cyan] Custom model URL")

    choice = Prompt.ask("Select an option (1-4)", choices=["1", "2", "3", "4"])

    if choice in RECOMMENDED_MODELS:
        model_url = RECOMMENDED_MODELS[choice]["url"]
        console.print(f"[green]Selected: {RECOMMENDED_MODELS[choice]['name']}[/green]")
    else:
        model_url = Prompt.ask("Enter the model URL")

    # Validate and sanitize the URL
    parsed_url = urlparse(model_url)
    if parsed_url.scheme not in ("http", "https"):
        console.print("[red]Invalid URL scheme. Only http and https are allowed.[/red]")
        return None
    if not parsed_url.netloc:
        console.print("[red]Invalid URL: missing host/domain.[/red]")
        return None

    # Derive a safe filename from the URL path
    url_path = Path(parsed_url.path)
    raw_filename = url_path.name if url_path.name else ""

    # Reject filenames with path traversal or empty names
    if not raw_filename or ".." in raw_filename or raw_filename.startswith("/"):
        console.print("[red]Invalid or unsafe filename in URL. Using generated name.[/red]")
        # Generate a safe fallback name based on URL hash
        import hashlib

        url_hash = hashlib.sha256(model_url.encode()).hexdigest()[:12]
        raw_filename = f"model_{url_hash}.gguf"

    # Clean the filename: only allow alphanumerics, dots, hyphens, underscores
    safe_filename = re.sub(r"[^\w.\-]", "_", raw_filename)
    if not safe_filename:
        safe_filename = "downloaded_model.gguf"

    os.makedirs(MODEL_DIR, exist_ok=True)

    # Construct model_path safely and verify it stays within MODEL_DIR
    model_path = (MODEL_DIR / safe_filename).resolve()
    if not str(model_path).startswith(str(MODEL_DIR.resolve())):
        console.print("[red]Security error: model path escapes designated directory.[/red]")
        return None

    console.print(f"[cyan]Downloading to {model_path}...[/cyan]")
    # Use subprocess with list arguments (no shell) after URL validation
    result = subprocess.run(["wget", model_url, "-O", str(model_path)], check=False)
    return model_path if result.returncode == 0 else None


def configure_auto_load(model_path: Path | str) -> None:
    """
    Configure the cortex daemon to auto-load the specified model on startup.

    Updates the daemon configuration file (/etc/cortex/daemon.yaml) to set the
    model_path and disable lazy_load, then restarts the daemon service.

    Args:
        model_path: Path (or string path) to the GGUF model file to configure
                    for auto-loading. Accepts either a Path object or a string.

    Returns:
        None. Exits the program with code 1 on failure.
    """
    console.print("[cyan]Configuring auto-load for the model...[/cyan]")
    # Create /etc/cortex directory if it doesn't exist
    subprocess.run(["sudo", "mkdir", "-p", "/etc/cortex"], check=False)

    # Check if config already exists
    config_exists = Path(CONFIG_FILE).exists()

    if not config_exists:
        # Copy example config and modify it
        console.print("[cyan]Creating daemon configuration file...[/cyan]")
        subprocess.run(["sudo", "cp", str(CONFIG_EXAMPLE), CONFIG_FILE], check=False)

    # Use YAML library to safely update the configuration instead of sed
    # This avoids shell injection risks from special characters in model_path
    try:
        # Read the current config file
        result = subprocess.run(
            ["sudo", "cat", CONFIG_FILE], capture_output=True, text=True, check=True
        )
        config = yaml.safe_load(result.stdout) or {}

        # Ensure the llm section exists
        if "llm" not in config:
            config["llm"] = {}

        # Update the configuration values under the llm section
        # The daemon reads from llm.model_path and llm.lazy_load
        config["llm"]["model_path"] = str(model_path)
        config["llm"]["lazy_load"] = False

        # Write the updated config back via sudo tee
        updated_yaml = yaml.dump(config, default_flow_style=False, sort_keys=False)
        write_result = subprocess.run(
            ["sudo", "tee", CONFIG_FILE],
            input=updated_yaml,
            text=True,
            capture_output=True,
            check=False,
        )

        if write_result.returncode != 0:
            console.print(
                f"[red]Failed to write config file (exit code {write_result.returncode})[/red]"
            )
            sys.exit(1)

        console.print(
            f"[green]Model configured to auto-load on daemon startup: {model_path}[/green]"
        )
        console.print("[cyan]Restarting daemon to apply configuration...[/cyan]")
        subprocess.run(["sudo", "systemctl", "restart", "cortexd"], check=False)
        console.print("[green]Daemon restarted with model loaded![/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to read config file: {e}[/red]")
        sys.exit(1)
    except yaml.YAMLError as e:
        console.print(f"[red]Failed to parse config file: {e}[/red]")
        sys.exit(1)


def configure_daemon_llm_backend(backend: str, config: dict | None = None) -> None:
    """
    Update daemon configuration with the chosen LLM backend.

    Args:
        backend: "cloud", "local", or "none"
        config: Optional configuration dict (provider info for cloud, model path for local)
    """
    console.print("[cyan]Updating daemon configuration...[/cyan]")

    # Create /etc/cortex directory if it doesn't exist
    subprocess.run(["sudo", "mkdir", "-p", "/etc/cortex"], check=False)

    # Check if config already exists
    config_exists = Path(CONFIG_FILE).exists()

    if not config_exists:
        console.print("[cyan]Creating daemon configuration file...[/cyan]")
        subprocess.run(["sudo", "cp", str(CONFIG_EXAMPLE), CONFIG_FILE], check=False)

    try:
        # Read the current config file
        result = subprocess.run(
            ["sudo", "cat", CONFIG_FILE], capture_output=True, text=True, check=True
        )
        daemon_config = yaml.safe_load(result.stdout) or {}

        # Ensure the llm section exists
        if "llm" not in daemon_config:
            daemon_config["llm"] = {}

        # Update the backend
        daemon_config["llm"]["backend"] = backend

        if backend == "cloud" and config:
            if "cloud" not in daemon_config["llm"]:
                daemon_config["llm"]["cloud"] = {}
            daemon_config["llm"]["cloud"]["provider"] = config.get("provider", "claude")
            daemon_config["llm"]["cloud"]["api_key_env"] = config.get("env_var", "ANTHROPIC_API_KEY")

        elif backend == "local":
            if "local" not in daemon_config["llm"]:
                daemon_config["llm"]["local"] = {}
            daemon_config["llm"]["local"]["base_url"] = "http://127.0.0.1:8085"
            if config and "model_name" in config:
                daemon_config["llm"]["local"]["model_name"] = config["model_name"]

        # Clear legacy embedded model settings when using new backend
        if backend in ("cloud", "local"):
            daemon_config["llm"]["model_path"] = ""
            daemon_config["llm"]["lazy_load"] = True

        # Write the updated config back via sudo tee
        updated_yaml = yaml.dump(daemon_config, default_flow_style=False, sort_keys=False)
        write_result = subprocess.run(
            ["sudo", "tee", CONFIG_FILE],
            input=updated_yaml,
            text=True,
            capture_output=True,
            check=False,
        )

        if write_result.returncode != 0:
            console.print(f"[red]Failed to write config file[/red]")
            return

        console.print(f"[green]✓ Daemon configured with LLM backend: {backend}[/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to read config file: {e}[/red]")
    except yaml.YAMLError as e:
        console.print(f"[red]Failed to parse config file: {e}[/red]")


def main() -> int:
    """
    Interactive setup wizard for the Cortex daemon.

    Guides the user through building, installing, and configuring the cortexd daemon,
    including LLM backend setup (Cloud APIs or Local llama.cpp).

    Returns:
        int: Exit code (0 for success, 1 for failure). The function calls sys.exit()
             directly on failures, so the return value is primarily for documentation
             and potential future refactoring.
    """
    console.print(
        "\n[bold cyan]╔══════════════════════════════════════════════════════════════╗[/bold cyan]"
    )
    console.print(
        "[bold cyan]║           Cortex Daemon Interactive Setup                    ║[/bold cyan]"
    )
    console.print(
        "[bold cyan]╚══════════════════════════════════════════════════════════════╝[/bold cyan]\n"
    )

    # Step 1: Build daemon
    if not check_daemon_built():
        if Confirm.ask("Daemon not built. Do you want to build it now?"):
            if not build_daemon():
                console.print("[red]Failed to build the daemon.[/red]")
                sys.exit(1)
        else:
            console.print("[yellow]Cannot proceed without building the daemon.[/yellow]")
            sys.exit(1)
    else:
        if Confirm.ask("Daemon already built. Do you want to rebuild it?"):
            clean_build()
            if not build_daemon():
                console.print("[red]Failed to build the daemon.[/red]")
                sys.exit(1)

    # Step 2: Install daemon
    if not install_daemon():
        console.print("[red]Failed to install the daemon.[/red]")
        sys.exit(1)

    # Step 3: Choose LLM backend
    console.print("")
    if not Confirm.ask("Do you want to configure an LLM backend now?", default=True):
        console.print("\n[green]✓ Daemon installed successfully![/green]")
        console.print("[cyan]You can configure LLM later by running this setup again.[/cyan]\n")
        return 0

    backend = choose_llm_backend()

    if backend == "none":
        console.print("\n[green]✓ Daemon installed successfully![/green]")
        console.print("[cyan]LLM backend not configured. You can set it up later.[/cyan]\n")
        return 0

    elif backend == "cloud":
        # Setup cloud API
        cloud_config = setup_cloud_api()
        if cloud_config:
            save_cloud_api_config(cloud_config)
            configure_daemon_llm_backend("cloud", cloud_config)

        console.print(
            "\n[bold green]╔══════════════════════════════════════════════════════════════╗[/bold green]"
        )
        console.print(
            "[bold green]║              Setup Completed Successfully!                   ║[/bold green]"
        )
        console.print(
            "[bold green]╚══════════════════════════════════════════════════════════════╝[/bold green]"
        )
        console.print(f"\n[cyan]LLM Backend: Cloud API ({cloud_config['provider']})[/cyan]")
        console.print("[cyan]Try it out:[/cyan] cortex ask 'What packages do I have installed?'\n")
        return 0
    elif backend == "local":
        # Setup local llama.cpp
        model_path = setup_local_llm()
        if model_path:
            # Get model name from path for config
            model_name = model_path.stem if hasattr(model_path, "stem") else str(model_path)
            configure_daemon_llm_backend("local", {"model_name": model_name})

            console.print(
                "\n[bold green]╔══════════════════════════════════════════════════════════════╗[/bold green]"
            )
            console.print(
                "[bold green]║              Setup Completed Successfully!                   ║[/bold green]"
            )
            console.print(
                "[bold green]╚══════════════════════════════════════════════════════════════╝[/bold green]"
            )
            console.print("\n[cyan]LLM Backend: Local llama.cpp[/cyan]")
            console.print(f"[cyan]Model: {model_path}[/cyan]")
            console.print("[cyan]Service: cortex-llm.service[/cyan]")
            console.print("\n[dim]Useful commands:[/dim]")
            console.print("[dim]  sudo systemctl status cortex-llm   # Check LLM service[/dim]")
            console.print("[dim]  journalctl -u cortex-llm -f        # View LLM logs[/dim]")
            console.print("\n[cyan]Try it out:[/cyan] cortex ask 'What packages do I have installed?'\n")
            return 0
        else:
            console.print("[red]Failed to set up local LLM.[/red]")
            console.print("[yellow]Daemon is installed but LLM is not configured.[/yellow]")
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
