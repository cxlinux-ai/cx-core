import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()

DAEMON_DIR = Path(__file__).parent.parent
BUILD_SCRIPT = DAEMON_DIR / "scripts" / "build.sh"
INSTALL_SCRIPT = DAEMON_DIR / "scripts" / "install.sh"
MODEL_DIR = Path.home() / ".cortex" / "models"
CONFIG_FILE = "/etc/cortex/daemon.yaml"
CONFIG_EXAMPLE = DAEMON_DIR / "config" / "cortexd.yaml.example"

# Recommended models
RECOMMENDED_MODELS = {
    "1": {
        "name": "TinyLlama 1.1B (Fast & Lightweight)",
        "url": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "size": "600MB",
        "description": "Best for testing and low-resource systems",
    },
    "2": {
        "name": "Mistral 7B (Balanced)",
        "url": "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "size": "4GB",
        "description": "Best for production with good balance of speed and quality",
    },
    "3": {
        "name": "Llama 2 13B (High Quality)",
        "url": "https://huggingface.co/TheBloke/Llama-2-13B-Chat-GGUF/resolve/main/llama-2-13b-chat.Q4_K_M.gguf",
        "size": "8GB",
        "description": "Best for high-quality responses",
    },
}


def check_daemon_built():
    return (DAEMON_DIR / "build" / "cortexd").exists()


def clean_build():
    build_dir = DAEMON_DIR / "build"
    if build_dir.exists():
        console.print(f"[cyan]Removing previous build directory: {build_dir}[/cyan]")
        result = subprocess.run(["sudo", "rm", "-rf", str(build_dir)], check=False)
        if result.returncode != 0:
            console.print("[red]Failed to remove previous build directory.[/red]")
            sys.exit(1)


def build_daemon():
    console.print("[cyan]Building the daemon...[/cyan]")
    result = subprocess.run(["bash", str(BUILD_SCRIPT), "Release"], check=False)
    return result.returncode == 0


def install_daemon():
    console.print("[cyan]Installing the daemon...[/cyan]")
    result = subprocess.run(["sudo", str(INSTALL_SCRIPT)], check=False)
    return result.returncode == 0


def download_model():
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

    os.makedirs(MODEL_DIR, exist_ok=True)
    model_path = MODEL_DIR / model_url.split("/")[-1]

    console.print(f"[cyan]Downloading to {model_path}...[/cyan]")
    result = subprocess.run(["wget", model_url, "-O", str(model_path)], check=False)
    return model_path if result.returncode == 0 else None


def setup_model(model_path):
    console.print(f"[cyan]Loading model: {model_path} into the daemon...[/cyan]")
    result = subprocess.run(["cortex", "daemon", "llm", "load", str(model_path)], check=False)
    return result.returncode == 0


def configure_auto_load(model_path):
    console.print("[cyan]Configuring auto-load for the model...[/cyan]")
    # Create /etc/cortex directory if it doesn't exist
    subprocess.run(["sudo", "mkdir", "-p", "/etc/cortex"], check=False)

    # Check if config already exists
    config_exists = Path(CONFIG_FILE).exists()

    if not config_exists:
        # Copy example config and modify it
        console.print("[cyan]Creating daemon configuration file...[/cyan]")
        subprocess.run(["sudo", "cp", str(CONFIG_EXAMPLE), CONFIG_FILE], check=False)

    # Update model_path - set the path
    sed_cmd1 = f's|model_path: "".*|model_path: "{model_path}"|g'
    subprocess.run(["sudo", "sed", "-i", sed_cmd1, CONFIG_FILE], check=False)

    # Set lazy_load to false so model loads on startup
    sed_cmd2 = "s|lazy_load: true|lazy_load: false|g"
    result = subprocess.run(["sudo", "sed", "-i", sed_cmd2, CONFIG_FILE], check=False)

    if result.returncode == 0:
        console.print(
            f"[green]Model configured to auto-load on daemon startup: {model_path}[/green]"
        )
        console.print("[cyan]Restarting daemon to apply configuration...[/cyan]")
        subprocess.run(["sudo", "systemctl", "restart", "cortexd"], check=False)
        console.print("[green]Daemon restarted with model loaded![/green]")
    else:
        console.print("[red]Failed to configure auto-load.[/red]")
        sys.exit(1)


def main():
    if not check_daemon_built():
        if Confirm.ask("Daemon not built. Do you want to build it now?"):
            if not build_daemon():
                console.print("[red]Failed to build the daemon.[/red]")
                sys.exit(1)
    else:
        if Confirm.ask("Daemon already built. Do you want to build it again?"):
            clean_build()
            if not build_daemon():
                console.print("[red]Failed to build the daemon.[/red]")
                sys.exit(1)

    if not install_daemon():
        console.print("[red]Failed to install the daemon.[/red]")
        sys.exit(1)

    model_path = download_model()
    if model_path:
        if setup_model(model_path):
            configure_auto_load(model_path)
            console.print("[green]Setup completed successfully![/green]")
        else:
            console.print("[red]Failed to load the model into the daemon.[/red]")
    else:
        console.print("[red]Failed to download the model.[/red]")


if __name__ == "__main__":
    main()
