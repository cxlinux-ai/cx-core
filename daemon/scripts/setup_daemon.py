import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

console = Console()

# Audit logging database path
AUDIT_DB_PATH = Path.home() / ".cortex" / "history.db"


def init_audit_db() -> bool:
    """
    Initialize the audit database for installer actions.

    Creates ~/.cortex directory if needed and sets up a SQLite database
    with an events table for logging installer actions.

    Returns:
        bool: True if initialization succeeded, False otherwise.
    """
    try:
        # Create ~/.cortex directory
        audit_dir = AUDIT_DB_PATH.parent
        audit_dir.mkdir(parents=True, exist_ok=True)

        # Create/connect to database
        conn = sqlite3.connect(str(AUDIT_DB_PATH))
        cursor = conn.cursor()

        # Create events table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT,
                success INTEGER DEFAULT 1
            )
        """)

        conn.commit()
        conn.close()
        return True
    except (sqlite3.Error, OSError) as e:
        console.print(f"[dim]Warning: Could not initialize audit database: {e}[/dim]")
        return False


def log_audit_event(event_type: str, details: str, success: bool = True) -> None:
    """
    Log an audit event to the history database.

    Inserts a timestamped row into the events table. Handles errors gracefully
    without crashing the installer.

    Args:
        event_type: Type of event (e.g., "install_dependencies", "build_daemon").
        details: Human-readable description of the event.
        success: Whether the action succeeded (default True).
    """
    try:
        # Ensure the database exists
        if not AUDIT_DB_PATH.exists():
            if not init_audit_db():
                return

        conn = sqlite3.connect(str(AUDIT_DB_PATH))
        cursor = conn.cursor()

        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        cursor.execute(
            "INSERT INTO events (timestamp, event_type, details, success) VALUES (?, ?, ?, ?)",
            (timestamp, event_type, details, 1 if success else 0),
        )

        conn.commit()
        conn.close()
    except (sqlite3.Error, OSError) as e:
        # Log to console but don't crash the installer
        console.print(f"[dim]Warning: Could not log audit event: {e}[/dim]")


DAEMON_DIR = Path(__file__).parent.parent
BUILD_SCRIPT = DAEMON_DIR / "scripts" / "build.sh"
INSTALL_SCRIPT = DAEMON_DIR / "scripts" / "install.sh"
CONFIG_FILE = "/etc/cortex/daemon.yaml"
CONFIG_EXAMPLE = DAEMON_DIR / "config" / "cortexd.yaml.example"
CORTEX_ENV_FILE = Path.home() / ".cortex" / ".env"

# System dependencies required to build the daemon (apt packages)
DAEMON_SYSTEM_DEPENDENCIES = [
    "cmake",
    "build-essential",
    "libsystemd-dev",
    "libssl-dev",
    "uuid-dev",
    "pkg-config",
    "libcap-dev",
]


def check_package_installed(package: str) -> bool:
    """
    Check if a system package is installed via dpkg.

    Args:
        package: Name of the apt package to check.

    Returns:
        bool: True if the package is installed, False otherwise.
    """
    result = subprocess.run(
        ["dpkg", "-s", package],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def check_system_dependencies() -> tuple[list[str], list[str]]:
    """
    Check which system dependencies are installed and which are missing.

    Returns:
        tuple: (installed_packages, missing_packages)
    """
    installed = []
    missing = []

    for package in DAEMON_SYSTEM_DEPENDENCIES:
        if check_package_installed(package):
            installed.append(package)
        else:
            missing.append(package)

    return installed, missing


def install_system_dependencies(packages: list[str]) -> bool:
    """
    Install system dependencies using apt-get.

    Args:
        packages: List of package names to install.

    Returns:
        bool: True if installation succeeded, False otherwise.
    """
    if not packages:
        return True

    console.print(f"\n[cyan]Installing {len(packages)} system package(s)...[/cyan]")
    console.print(f"[dim]Packages: {', '.join(packages)}[/dim]\n")

    # Update package list first
    console.print("[cyan]Updating package list...[/cyan]")
    update_result = subprocess.run(
        ["sudo", "apt-get", "update"],
        check=False,
    )
    if update_result.returncode != 0:
        console.print("[yellow]Warning: apt-get update failed, continuing anyway...[/yellow]")

    # Install packages
    install_cmd = ["sudo", "apt-get", "install", "-y"] + packages
    result = subprocess.run(install_cmd, check=False)

    if result.returncode == 0:
        console.print(f"[green]✓ Successfully installed {len(packages)} package(s)[/green]")
        log_audit_event(
            "install_system_dependencies",
            f"Installed {len(packages)} package(s): {', '.join(packages)}",
            success=True,
        )
        return True
    else:
        console.print("[red]✗ Failed to install some packages[/red]")
        log_audit_event(
            "install_system_dependencies",
            f"Failed to install package(s): {', '.join(packages)}",
            success=False,
        )
        return False


def setup_system_dependencies() -> bool:
    """
    Check and install required system dependencies for building the daemon.

    Displays a table of dependencies with their status and prompts the user
    to install missing ones.

    Returns:
        bool: True if all dependencies are satisfied, False otherwise.
    """
    console.print("\n[bold cyan]Checking System Dependencies[/bold cyan]\n")

    installed, missing = check_system_dependencies()

    # Display dependency status table
    table = Table(title="Build Dependencies")
    table.add_column("Package", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Description")

    package_descriptions = {
        "cmake": "Build system generator",
        "build-essential": "GCC, G++, make, and other build tools",
        "libsystemd-dev": "systemd integration headers",
        "libssl-dev": "OpenSSL development libraries",
        "uuid-dev": "UUID generation libraries",
        "pkg-config": "Package configuration tool",
        "libcap-dev": "Linux capabilities library",
    }

    for package in DAEMON_SYSTEM_DEPENDENCIES:
        status = "[green]✓ Installed[/green]" if package in installed else "[red]✗ Missing[/red]"
        description = package_descriptions.get(package, "")
        table.add_row(package, status, description)

    console.print(table)

    if not missing:
        console.print("\n[green]✓ All system dependencies are installed![/green]")
        return True

    console.print(
        f"\n[yellow]⚠ Missing {len(missing)} required package(s): {', '.join(missing)}[/yellow]"
    )

    if Confirm.ask("\nDo you want to install the missing dependencies now?", default=True):
        if install_system_dependencies(missing):
            # Verify installation
            _, still_missing = check_system_dependencies()
            if still_missing:
                console.print(f"[red]Some packages still missing: {', '.join(still_missing)}[/red]")
                return False
            return True
        else:
            return False
    else:
        console.print("[yellow]Cannot build daemon without required dependencies.[/yellow]")
        console.print("\n[cyan]You can install them manually with:[/cyan]")
        console.print(f"[dim]  sudo apt-get install -y {' '.join(missing)}[/dim]\n")
        return False


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
    if not build_dir.exists():
        # Log cancelled operation
        log_audit_event(
            "clean_build",
            f"Build directory does not exist: {build_dir}",
            success=True,
        )
        return

    console.print(f"[cyan]Removing previous build directory: {build_dir}[/cyan]")
    result = subprocess.run(
        ["sudo", "rm", "-rf", str(build_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        # Log successful removal
        log_audit_event(
            "clean_build",
            f"Successfully removed build directory: {build_dir}",
            success=True,
        )
    else:
        # Log failure before exiting
        error_details = f"returncode={result.returncode}"
        if result.stderr:
            error_details += f", stderr={result.stderr[:500]}"
        log_audit_event(
            "clean_build",
            f"Failed to remove build directory: {build_dir}, {error_details}",
            success=False,
        )
        console.print("[red]Failed to remove previous build directory.[/red]")
        if result.stderr:
            console.print(f"[dim]Error: {result.stderr.strip()}[/dim]")
        sys.exit(1)


def build_daemon(with_tests: bool = False) -> bool:
    """
    Build the cortexd daemon from source.

    Runs the BUILD_SCRIPT (daemon/scripts/build.sh) with "Release" argument
    using subprocess.run. Optionally builds tests.

    Args:
        with_tests: If True, also build the test suite.

    Returns:
        bool: True if the build completed successfully (exit code 0), False otherwise.
    """
    if with_tests:
        console.print("[cyan]Building the daemon with tests...[/cyan]")
        cmd = ["bash", str(BUILD_SCRIPT), "Release", "--with-tests"]
    else:
        console.print("[cyan]Building the daemon...[/cyan]")
        cmd = ["bash", str(BUILD_SCRIPT), "Release"]

    result = subprocess.run(cmd, check=False)
    success = result.returncode == 0
    log_audit_event(
        "build_daemon",
        f"Build daemon {'with tests ' if with_tests else ''}{'succeeded' if success else 'failed'}",
        success=success,
    )
    return success


def run_tests() -> bool:
    """
    Run the daemon test suite using ctest.

    Returns:
        bool: True if all tests passed, False otherwise.
    """
    build_dir = DAEMON_DIR / "build"
    tests_dir = build_dir / "tests"

    if not (tests_dir / "test_config").exists():
        console.print("[yellow]Tests not built. Please rebuild with tests enabled.[/yellow]")
        return False

    console.print("\n[cyan]Running daemon tests...[/cyan]\n")
    result = subprocess.run(
        ["ctest", "--output-on-failure"],
        cwd=str(build_dir),
        check=False,
    )

    success = result.returncode == 0
    log_audit_event(
        "run_tests",
        f"Test suite {'passed' if success else 'failed'}",
        success=success,
    )

    if success:
        console.print("\n[green]✓ All tests passed![/green]")
    else:
        console.print("\n[red]✗ Some tests failed.[/red]")

    return success


def check_tests_built() -> bool:
    """
    Check if the test binaries have been built.

    Returns:
        bool: True if test binaries exist, False otherwise.
    """
    # Test binaries are in daemon/build/tests/
    return (DAEMON_DIR / "build" / "tests" / "test_config").exists()


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
    success = result.returncode == 0
    log_audit_event(
        "install_daemon",
        f"Install daemon {'succeeded' if success else 'failed'}",
        success=success,
    )
    return success


def main() -> int:
    """
    Interactive setup wizard for the Cortex daemon.

    Guides the user through building and installing the cortexd daemon.

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

    # Initialize audit database
    init_audit_db()
    log_audit_event("setup_started", "Cortex daemon interactive setup started")

    # Step 0: Check and install system dependencies
    if not setup_system_dependencies():
        console.print("[red]Cannot proceed without required system dependencies.[/red]")
        sys.exit(1)

    # Step 1: Build daemon
    build_tests = False

    if not check_daemon_built():
        if Confirm.ask("Daemon not built. Do you want to build it now?"):
            build_tests = Confirm.ask("Do you also want to build the test suite?", default=False)
            if not build_daemon(with_tests=build_tests):
                console.print("[red]Failed to build the daemon.[/red]")
                sys.exit(1)
        else:
            console.print("[yellow]Cannot proceed without building the daemon.[/yellow]")
            sys.exit(1)
    else:
        if Confirm.ask("Daemon already built. Do you want to rebuild it?"):
            build_tests = Confirm.ask("Do you also want to build the test suite?", default=False)
            clean_build()
            if not build_daemon(with_tests=build_tests):
                console.print("[red]Failed to build the daemon.[/red]")
                sys.exit(1)

    # Step 1.5: Run tests if they were built or user wants to build them
    if Confirm.ask("\nDo you want to run the test suite?", default=False):
        if not check_tests_built():
            console.print("\n[yellow]Tests are not built.[/yellow]")
            if Confirm.ask(
                "Would you like to rebuild the daemon with tests enabled?", default=True
            ):
                clean_build()
                if not build_daemon(with_tests=True):
                    console.print("[red]Failed to build the daemon with tests.[/red]")
                    sys.exit(1)

                # Verify tests were built successfully
                if not check_tests_built():
                    console.print(
                        "[red]Tests were not built successfully. Check the build output above.[/red]"
                    )
                    sys.exit(1)

                # Run the tests now that they're built
                console.print("\n[green]✓ Tests built successfully![/green]")
                if not run_tests():
                    if not Confirm.ask(
                        "[yellow]Some tests failed. Continue with installation anyway?[/yellow]",
                        default=False,
                    ):
                        console.print("[yellow]Installation cancelled.[/yellow]")
                        sys.exit(1)
            else:
                console.print("[dim]Skipping tests.[/dim]")
        else:
            # Tests are already built, just run them
            if not run_tests():
                if not Confirm.ask(
                    "[yellow]Some tests failed. Continue with installation anyway?[/yellow]",
                    default=False,
                ):
                    console.print("[yellow]Installation cancelled.[/yellow]")
                    sys.exit(1)

    # Step 2: Install daemon
    if not install_daemon():
        console.print("[red]Failed to install the daemon.[/red]")
        sys.exit(1)

    console.print(
        "\n[bold green]╔══════════════════════════════════════════════════════════════╗[/bold green]"
    )
    console.print(
        "[bold green]║              Setup Completed Successfully!                   ║[/bold green]"
    )
    console.print(
        "[bold green]╚══════════════════════════════════════════════════════════════╝[/bold green]"
    )
    console.print("\n[green]✓ Daemon installed successfully![/green]")
    console.print("\n[cyan]Useful commands:[/cyan]")
    console.print("[cyan]  systemctl status cortexd       # Check daemon status[/cyan]")
    console.print("[cyan]  journalctl -u cortexd -f       # View daemon logs[/cyan]")
    console.print("[cyan]  cortex daemon ping             # Test daemon connection[/cyan]")
    console.print("[cyan]  cortex daemon version          # Get daemon version[/cyan]")

    if check_tests_built():
        console.print("\n[cyan]Test commands:[/cyan]")
        console.print("[cyan]  cortex daemon run-tests        # Run all tests[/cyan]")
        console.print("[cyan]  cortex daemon run-tests --unit # Run unit tests only[/cyan]")
        console.print(
            "[cyan]  cortex daemon run-tests --integration  # Run integration tests[/cyan]"
        )
        console.print("[cyan]  cortex daemon run-tests -t config      # Run specific test[/cyan]")

    console.print("")

    log_audit_event("setup_completed", "Setup completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
