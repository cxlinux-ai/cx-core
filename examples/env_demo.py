#!/usr/bin/env python3
"""
Environment Variable Manager Demo

This script demonstrates the environment variable management features
of Cortex, including:

- Setting and getting variables
- Encrypting sensitive values
- Using templates
- Importing and exporting
- Variable validation

Run this script to see the env manager in action:
    python examples/env_demo.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cortex.env_manager import (
    EnvironmentManager,
    EnvironmentStorage,
    EncryptionManager,
    get_env_manager,
)

console = Console()


def demo_header(title: str) -> None:
    """Print a demo section header."""
    console.print()
    console.print(Panel(f"[bold cyan]{title}[/bold cyan]", expand=False))
    console.print()


def demo_basic_operations(env_mgr: EnvironmentManager) -> None:
    """Demonstrate basic set/get/list/delete operations."""
    demo_header("1. Basic Operations")

    app = "demo-app"

    # Set variables
    console.print("[bold]Setting variables...[/bold]")
    env_mgr.set_variable(app, "DATABASE_URL", "postgres://localhost:5432/mydb")
    console.print("  ✓ Set DATABASE_URL")

    env_mgr.set_variable(app, "REDIS_URL", "redis://localhost:6379")
    console.print("  ✓ Set REDIS_URL")

    env_mgr.set_variable(app, "LOG_LEVEL", "debug", description="Application logging level")
    console.print("  ✓ Set LOG_LEVEL with description")

    console.print()

    # Get a variable
    console.print("[bold]Getting a variable...[/bold]")
    value = env_mgr.get_variable(app, "DATABASE_URL")
    console.print(f"  DATABASE_URL = {value}")

    console.print()

    # List all variables
    console.print("[bold]Listing all variables...[/bold]")
    variables = env_mgr.list_variables(app)

    table = Table(show_header=True, header_style="bold")
    table.add_column("Key")
    table.add_column("Value")
    table.add_column("Description")

    for var in sorted(variables, key=lambda v: v.key):
        table.add_row(
            var.key,
            var.value[:50] + "..." if len(var.value) > 50 else var.value,
            var.description or "-",
        )

    console.print(table)

    console.print()

    # Delete a variable
    console.print("[bold]Deleting REDIS_URL...[/bold]")
    env_mgr.delete_variable(app, "REDIS_URL")
    console.print("  ✓ Deleted REDIS_URL")

    # Verify deletion
    remaining = env_mgr.list_variables(app)
    console.print(f"  Remaining variables: {len(remaining)}")


def demo_encryption(env_mgr: EnvironmentManager) -> None:
    """Demonstrate encryption features."""
    demo_header("2. Encryption")

    app = "demo-app"

    # Set encrypted variables
    console.print("[bold]Setting encrypted variables...[/bold]")

    env_mgr.set_variable(
        app,
        "API_KEY",
        "sk-secret-api-key-12345",
        encrypt=True,
        description="External API key",
    )
    console.print("  🔐 Set API_KEY (encrypted)")

    env_mgr.set_variable(
        app,
        "JWT_SECRET",
        "super-secret-jwt-signing-key",
        encrypt=True,
    )
    console.print("  🔐 Set JWT_SECRET (encrypted)")

    console.print()

    # Show how encrypted values appear
    console.print("[bold]Viewing encrypted variables...[/bold]")

    api_key_info = env_mgr.get_variable_info(app, "API_KEY")
    console.print(f"  API_KEY encrypted: {api_key_info.encrypted}")
    console.print(f"  API_KEY stored value: {api_key_info.value[:40]}...")

    console.print()

    # Decrypt and show
    console.print("[bold]Decrypting variables...[/bold]")
    decrypted = env_mgr.get_variable(app, "API_KEY", decrypt=True)
    console.print(f"  API_KEY decrypted: {decrypted}")

    console.print()

    # Show in list (encrypted placeholder)
    console.print("[bold]Variables in list view:[/bold]")
    for var in env_mgr.list_variables(app):
        if var.encrypted:
            console.print(f"  {var.key}: [yellow][encrypted][/yellow]")
        else:
            console.print(f"  {var.key}: {var.value}")


def demo_validation(env_mgr: EnvironmentManager) -> None:
    """Demonstrate variable validation."""
    demo_header("3. Validation")

    app = "demo-validation"

    console.print("[bold]Setting validated variables...[/bold]")

    # Valid port
    try:
        env_mgr.set_variable(app, "PORT", "3000", var_type="port")
        console.print("  ✓ PORT=3000 (valid port)")
    except ValueError as e:
        console.print(f"  ✗ PORT: {e}")

    # Valid URL
    try:
        env_mgr.set_variable(app, "API_URL", "https://api.example.com", var_type="url")
        console.print("  ✓ API_URL=https://api.example.com (valid URL)")
    except ValueError as e:
        console.print(f"  ✗ API_URL: {e}")

    # Valid boolean
    try:
        env_mgr.set_variable(app, "DEBUG", "true", var_type="boolean")
        console.print("  ✓ DEBUG=true (valid boolean)")
    except ValueError as e:
        console.print(f"  ✗ DEBUG: {e}")

    console.print()
    console.print("[bold]Testing invalid values...[/bold]")

    # Invalid port
    try:
        env_mgr.set_variable(app, "BAD_PORT", "99999", var_type="port")
        console.print("  ✓ BAD_PORT accepted")
    except ValueError as e:
        console.print(f"  ✗ BAD_PORT=99999: [red]{e}[/red]")

    # Invalid URL
    try:
        env_mgr.set_variable(app, "BAD_URL", "not-a-url", var_type="url")
        console.print("  ✓ BAD_URL accepted")
    except ValueError as e:
        console.print(f"  ✗ BAD_URL=not-a-url: [red]{e}[/red]")

    # Invalid boolean
    try:
        env_mgr.set_variable(app, "BAD_BOOL", "maybe", var_type="boolean")
        console.print("  ✓ BAD_BOOL accepted")
    except ValueError as e:
        console.print(f"  ✗ BAD_BOOL=maybe: [red]{e}[/red]")


def demo_templates(env_mgr: EnvironmentManager) -> None:
    """Demonstrate template functionality."""
    demo_header("4. Templates")

    # List available templates
    console.print("[bold]Available templates:[/bold]")
    templates = env_mgr.list_templates()

    for template in sorted(templates, key=lambda t: t.name):
        console.print(f"  • [green]{template.name}[/green]: {template.description}")

    console.print()

    # Show template details
    console.print("[bold]Django template details:[/bold]")
    django = env_mgr.get_template("django")
    if django:
        for var in django.variables:
            req = "[red]*[/red]" if var.required else " "
            default = f" = {var.default}" if var.default else ""
            console.print(f"  {req} {var.name} ({var.var_type}){default}")

    console.print()

    # Apply a template
    console.print("[bold]Applying Node.js template to 'my-node-app'...[/bold]")
    result = env_mgr.apply_template(
        "nodejs",
        "my-node-app",
        values={
            "NODE_ENV": "production",
            "PORT": "8080",
        },
    )

    if result.valid:
        console.print("  ✓ Template applied successfully")
        console.print()
        console.print("  [bold]Variables set:[/bold]")
        for var in env_mgr.list_variables("my-node-app"):
            console.print(f"    {var.key} = {var.value}")
    else:
        console.print("  ✗ Template failed:")
        for error in result.errors:
            console.print(f"    - {error}")


def demo_export_import(env_mgr: EnvironmentManager) -> None:
    """Demonstrate export and import functionality."""
    demo_header("5. Export & Import")

    app = "export-demo"

    # Set up some variables
    env_mgr.set_variable(app, "DATABASE_URL", "postgres://localhost/db")
    env_mgr.set_variable(app, "CACHE_URL", "redis://localhost:6379")
    env_mgr.set_variable(app, "SECRET", "my-secret", encrypt=True)

    console.print("[bold]Exporting to .env format...[/bold]")

    # Export without encrypted
    content = env_mgr.export_env(app, include_encrypted=False)
    console.print()
    console.print("[dim]--- .env content (without secrets) ---[/dim]")
    console.print(content)
    console.print("[dim]--- end ---[/dim]")

    console.print()

    # Export with encrypted
    content_with_secrets = env_mgr.export_env(app, include_encrypted=True)
    console.print("[bold]Exporting with decrypted secrets...[/bold]")
    console.print()
    console.print("[dim]--- .env content (with secrets) ---[/dim]")
    console.print(content_with_secrets)
    console.print("[dim]--- end ---[/dim]")

    console.print()

    # Import demonstration
    console.print("[bold]Importing from .env format...[/bold]")

    import_content = """
# Production configuration
NODE_ENV=production
PORT=3000
DEBUG=false
API_ENDPOINT=https://api.example.com
"""

    count, errors = env_mgr.import_env("import-demo", import_content)
    console.print(f"  ✓ Imported {count} variables")

    if errors:
        console.print("  Warnings:")
        for error in errors:
            console.print(f"    - {error}")

    console.print()
    console.print("  Imported variables:")
    for var in env_mgr.list_variables("import-demo"):
        console.print(f"    {var.key} = {var.value}")


def demo_app_isolation(env_mgr: EnvironmentManager) -> None:
    """Demonstrate application isolation."""
    demo_header("6. Application Isolation")

    console.print("[bold]Setting same key in different apps...[/bold]")

    env_mgr.set_variable("app-1", "DATABASE_URL", "postgres://db1.example.com/app1")
    env_mgr.set_variable("app-2", "DATABASE_URL", "postgres://db2.example.com/app2")
    env_mgr.set_variable("app-3", "DATABASE_URL", "mysql://db3.example.com/app3")

    console.print()
    console.print("[bold]Values are isolated per app:[/bold]")

    for app in ["app-1", "app-2", "app-3"]:
        value = env_mgr.get_variable(app, "DATABASE_URL")
        console.print(f"  {app}: {value}")

    console.print()
    console.print("[bold]Listing all apps with environments:[/bold]")
    apps = env_mgr.list_apps()
    for app in apps:
        var_count = len(env_mgr.list_variables(app))
        console.print(f"  • {app} ({var_count} variables)")


def demo_load_to_environ(env_mgr: EnvironmentManager) -> None:
    """Demonstrate loading variables into os.environ."""
    demo_header("7. Loading into os.environ")

    app = "environ-demo"

    # Clean up any existing test vars
    test_keys = ["DEMO_VAR_1", "DEMO_VAR_2", "DEMO_SECRET"]
    for key in test_keys:
        if key in os.environ:
            del os.environ[key]

    # Set some variables
    env_mgr.set_variable(app, "DEMO_VAR_1", "value1")
    env_mgr.set_variable(app, "DEMO_VAR_2", "value2")
    env_mgr.set_variable(app, "DEMO_SECRET", "secret-value", encrypt=True)

    console.print("[bold]Before loading:[/bold]")
    for key in test_keys:
        console.print(f"  os.environ.get('{key}'): {os.environ.get(key)}")

    console.print()
    console.print("[bold]Loading environment...[/bold]")
    count = env_mgr.load_to_environ(app)
    console.print(f"  ✓ Loaded {count} variables into os.environ")

    console.print()
    console.print("[bold]After loading:[/bold]")
    for key in test_keys:
        value = os.environ.get(key)
        console.print(f"  os.environ.get('{key}'): {value}")

    # Clean up
    for key in test_keys:
        if key in os.environ:
            del os.environ[key]


def main() -> None:
    """Run all demos."""
    console.print()
    console.print(
        Panel(
            "[bold magenta]Cortex Environment Variable Manager Demo[/bold magenta]\n\n"
            "This demo showcases the environment management features.",
            expand=False,
        )
    )

    # Use a temporary directory for the demo
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create environment manager with temporary storage
        storage = EnvironmentStorage(base_path=tmppath / "environments")
        encryption = EncryptionManager(key_path=tmppath / ".env_key")
        env_mgr = EnvironmentManager(storage=storage, encryption=encryption)

        console.print()
        console.print(f"[dim]Using temporary storage: {tmpdir}[/dim]")

        # Run demos
        demo_basic_operations(env_mgr)
        demo_encryption(env_mgr)
        demo_validation(env_mgr)
        demo_templates(env_mgr)
        demo_export_import(env_mgr)
        demo_app_isolation(env_mgr)
        demo_load_to_environ(env_mgr)

        # Summary
        demo_header("Demo Complete!")

        console.print("[bold]To use in your own projects:[/bold]")
        console.print()
        console.print("  # CLI usage")
        console.print("  [green]cortex env set myapp DATABASE_URL postgres://localhost/db[/green]")
        console.print("  [green]cortex env set myapp API_KEY secret123 --encrypt[/green]")
        console.print("  [green]cortex env list myapp[/green]")
        console.print()
        console.print("  # Python usage")
        console.print("  [cyan]from cortex.env_manager import get_env_manager[/cyan]")
        console.print("  [cyan]env_mgr = get_env_manager()[/cyan]")
        console.print("  [cyan]env_mgr.set_variable('myapp', 'KEY', 'value')[/cyan]")
        console.print()
        console.print("See [bold]docs/ENV_MANAGEMENT.md[/bold] for full documentation.")
        console.print()


if __name__ == "__main__":
    main()
