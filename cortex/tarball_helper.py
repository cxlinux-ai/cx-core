"""
Tarball/Manual Build Helper for Cortex Linux.
Analyzes build files, installs missing dependencies, and tracks manual builds.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.tree import Tree

from cortex.branding import console, cx_header


class BuildSystem(Enum):
    """Detected build system types."""

    AUTOTOOLS = "autotools"  # configure.ac, configure
    CMAKE = "cmake"  # CMakeLists.txt
    MESON = "meson"  # meson.build
    MAKE = "make"  # Makefile only
    PYTHON = "python"  # setup.py, pyproject.toml
    UNKNOWN = "unknown"


@dataclass
class Dependency:
    """A detected build dependency.

    Attributes:
        name: The dependency name as found in build files.
        dep_type: Type of dependency (library, header, tool, pkg-config).
        apt_package: Suggested apt package to install.
        required: Whether this dependency is required or optional.
        found: Whether the dependency is already installed.
    """

    name: str
    dep_type: str  # library, header, tool, pkg-config
    apt_package: str | None = None
    required: bool = True
    found: bool = False


@dataclass
class BuildAnalysis:
    """Results of analyzing a source directory.

    Attributes:
        build_system: Detected build system type.
        source_dir: Path to the source directory.
        dependencies: List of detected dependencies.
        missing_packages: List of apt packages to install.
        build_commands: Suggested build commands.
    """

    build_system: BuildSystem
    source_dir: Path
    dependencies: list[Dependency] = field(default_factory=list)
    missing_packages: list[str] = field(default_factory=list)
    build_commands: list[str] = field(default_factory=list)


@dataclass
class ManualInstall:
    """Record of a manual installation.

    Attributes:
        name: Name of the installed software.
        source_dir: Original source directory.
        installed_at: When the installation occurred.
        packages_installed: Apt packages installed for this build.
        files_installed: Files installed to the system.
        prefix: Installation prefix used.
    """

    name: str
    source_dir: str
    installed_at: str
    packages_installed: list[str] = field(default_factory=list)
    files_installed: list[str] = field(default_factory=list)
    prefix: str = "/usr/local"


class TarballHelper:
    """
    Helper for building software from tarballs and source code.

    Analyzes build files to detect dependencies, installs required
    -dev packages, tracks manual installations, and suggests
    packaged alternatives when available.
    """

    # Common header to apt package mappings
    HEADER_PACKAGES: dict[str, str] = {
        "zlib.h": "zlib1g-dev",
        "openssl/ssl.h": "libssl-dev",
        "curl/curl.h": "libcurl4-openssl-dev",
        "pthread.h": "libc6-dev",
        "ncurses.h": "libncurses-dev",
        "readline/readline.h": "libreadline-dev",
        "sqlite3.h": "libsqlite3-dev",
        "png.h": "libpng-dev",
        "jpeglib.h": "libjpeg-dev",
        "expat.h": "libexpat1-dev",
        "libxml/parser.h": "libxml2-dev",
        "glib.h": "libglib2.0-dev",
        "gtk/gtk.h": "libgtk-3-dev",
        "X11/Xlib.h": "libx11-dev",
        "pcre.h": "libpcre3-dev",
        "ffi.h": "libffi-dev",
        "uuid/uuid.h": "uuid-dev",
        "bz2.h": "libbz2-dev",
        "lzma.h": "liblzma-dev",
    }

    # Common pkg-config names to apt packages
    PKGCONFIG_PACKAGES: dict[str, str] = {
        "openssl": "libssl-dev",
        "libcurl": "libcurl4-openssl-dev",
        "zlib": "zlib1g-dev",
        "libpng": "libpng-dev",
        "libjpeg": "libjpeg-dev",
        "libxml-2.0": "libxml2-dev",
        "glib-2.0": "libglib2.0-dev",
        "gtk+-3.0": "libgtk-3-dev",
        "x11": "libx11-dev",
        "sqlite3": "libsqlite3-dev",
        "ncurses": "libncurses-dev",
        "readline": "libreadline-dev",
        "libffi": "libffi-dev",
        "uuid": "uuid-dev",
        "libpcre": "libpcre3-dev",
        "python3": "python3-dev",
        "dbus-1": "libdbus-1-dev",
        "libsystemd": "libsystemd-dev",
    }

    # Build tools
    BUILD_TOOLS: dict[str, str] = {
        "gcc": "build-essential",
        "g++": "build-essential",
        "make": "build-essential",
        "cmake": "cmake",
        "meson": "meson",
        "ninja": "ninja-build",
        "autoconf": "autoconf",
        "automake": "automake",
        "libtool": "libtool",
        "pkg-config": "pkg-config",
        "bison": "bison",
        "flex": "flex",
        "gettext": "gettext",
    }

    def __init__(self) -> None:
        """Initialize the TarballHelper."""
        self.history_file = Path.home() / ".cortex" / "manual_builds.json"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def detect_build_system(self, source_dir: Path) -> BuildSystem:
        """Detect the build system used in a source directory.

        Args:
            source_dir: Path to the source directory.

        Returns:
            The detected BuildSystem type.
        """
        if not source_dir.is_dir():
            raise ValueError(f"Not a directory: {source_dir}")

        # Check for various build system files
        if (source_dir / "CMakeLists.txt").exists():
            return BuildSystem.CMAKE
        elif (source_dir / "meson.build").exists():
            return BuildSystem.MESON
        elif (source_dir / "configure.ac").exists() or (source_dir / "configure.in").exists():
            return BuildSystem.AUTOTOOLS
        elif (source_dir / "configure").exists():
            return BuildSystem.AUTOTOOLS
        elif (source_dir / "setup.py").exists() or (source_dir / "pyproject.toml").exists():
            return BuildSystem.PYTHON
        elif (source_dir / "Makefile").exists():
            return BuildSystem.MAKE
        else:
            return BuildSystem.UNKNOWN

    def analyze(self, source_dir: Path) -> BuildAnalysis:
        """Analyze a source directory for build requirements.

        Args:
            source_dir: Path to the source directory to analyze.

        Returns:
            BuildAnalysis with detected dependencies and suggestions.
        """
        source_dir = Path(source_dir).resolve()
        build_system = self.detect_build_system(source_dir)

        analysis = BuildAnalysis(
            build_system=build_system,
            source_dir=source_dir,
        )

        # Detect dependencies based on build system
        if build_system == BuildSystem.CMAKE:
            self._analyze_cmake(source_dir, analysis)
        elif build_system == BuildSystem.AUTOTOOLS:
            self._analyze_autotools(source_dir, analysis)
        elif build_system == BuildSystem.MESON:
            self._analyze_meson(source_dir, analysis)
        elif build_system == BuildSystem.PYTHON:
            self._analyze_python(source_dir, analysis)

        # Check what's already installed
        self._check_installed(analysis)

        # Generate missing packages list
        for dep in analysis.dependencies:
            if (
                not dep.found
                and dep.apt_package
                and dep.apt_package not in analysis.missing_packages
            ):
                analysis.missing_packages.append(dep.apt_package)

        # Generate build commands
        analysis.build_commands = self._generate_build_commands(build_system, source_dir)

        return analysis

    def _analyze_cmake(self, source_dir: Path, analysis: BuildAnalysis) -> None:
        """Analyze CMakeLists.txt for dependencies."""
        cmake_file = source_dir / "CMakeLists.txt"
        if not cmake_file.exists():
            return

        content = cmake_file.read_text(encoding="utf-8", errors="ignore")

        # Find find_package() calls
        for match in re.finditer(r"find_package\s*\(\s*(\w+)", content, re.IGNORECASE):
            pkg_name = match.group(1).lower()
            apt_pkg = self.PKGCONFIG_PACKAGES.get(pkg_name)
            analysis.dependencies.append(
                Dependency(name=pkg_name, dep_type="package", apt_package=apt_pkg)
            )

        # Find pkg_check_modules() calls
        for match in re.finditer(
            r"pkg_check_modules\s*\([^)]*\s+([^\s)]+)", content, re.IGNORECASE
        ):
            pkg_name = match.group(1).lower()
            apt_pkg = self.PKGCONFIG_PACKAGES.get(pkg_name)
            analysis.dependencies.append(
                Dependency(name=pkg_name, dep_type="pkg-config", apt_package=apt_pkg)
            )

        # Find CHECK_INCLUDE_FILE calls
        for match in re.finditer(
            r"CHECK_INCLUDE_FILE\s*\(\s*[\"']?([^\"'\s\)]+)", content, re.IGNORECASE
        ):
            header = match.group(1)
            apt_pkg = self.HEADER_PACKAGES.get(header)
            analysis.dependencies.append(
                Dependency(name=header, dep_type="header", apt_package=apt_pkg)
            )

        # Add cmake as build tool
        analysis.dependencies.append(Dependency(name="cmake", dep_type="tool", apt_package="cmake"))

    def _analyze_autotools(self, source_dir: Path, analysis: BuildAnalysis) -> None:
        """Analyze configure.ac/configure for dependencies."""
        # Try configure.ac first, then configure
        config_file = source_dir / "configure.ac"
        if not config_file.exists():
            config_file = source_dir / "configure.in"
        if not config_file.exists():
            config_file = source_dir / "configure"

        if not config_file.exists():
            return

        content = config_file.read_text(encoding="utf-8", errors="ignore")

        # Find AC_CHECK_HEADERS
        for match in re.finditer(r"AC_CHECK_HEADER[S]?\s*\(\s*\[?([^\],\)]+)", content):
            headers = match.group(1).strip("[]").split()
            for header in headers:
                header = header.strip()
                apt_pkg = self.HEADER_PACKAGES.get(header)
                analysis.dependencies.append(
                    Dependency(name=header, dep_type="header", apt_package=apt_pkg)
                )

        # Find PKG_CHECK_MODULES
        for match in re.finditer(r"PKG_CHECK_MODULES\s*\([^,]+,\s*\[?([^\],\)]+)", content):
            pkg_spec = match.group(1).strip("[]")
            # Extract package name (before any version specifier)
            pkg_name = re.split(r"[<>=\s]", pkg_spec)[0].strip()
            apt_pkg = self.PKGCONFIG_PACKAGES.get(pkg_name.lower())
            analysis.dependencies.append(
                Dependency(name=pkg_name, dep_type="pkg-config", apt_package=apt_pkg)
            )

        # Find AC_CHECK_LIB
        for match in re.finditer(r"AC_CHECK_LIB\s*\(\s*\[?(\w+)", content):
            lib_name = match.group(1)
            # Try to find apt package
            apt_pkg = self.PKGCONFIG_PACKAGES.get(f"lib{lib_name}".lower())
            analysis.dependencies.append(
                Dependency(name=lib_name, dep_type="library", apt_package=apt_pkg)
            )

        # Add autotools as build tools
        analysis.dependencies.append(
            Dependency(name="autoconf", dep_type="tool", apt_package="autoconf")
        )
        analysis.dependencies.append(
            Dependency(name="automake", dep_type="tool", apt_package="automake")
        )

    def _analyze_meson(self, source_dir: Path, analysis: BuildAnalysis) -> None:
        """Analyze meson.build for dependencies."""
        meson_file = source_dir / "meson.build"
        if not meson_file.exists():
            return

        content = meson_file.read_text(encoding="utf-8", errors="ignore")

        # Find dependency() calls
        for match in re.finditer(r"dependency\s*\(\s*['\"]([^'\"]+)['\"]", content):
            pkg_name = match.group(1).lower()
            apt_pkg = self.PKGCONFIG_PACKAGES.get(pkg_name)
            analysis.dependencies.append(
                Dependency(name=pkg_name, dep_type="dependency", apt_package=apt_pkg)
            )

        # Add meson and ninja as build tools
        analysis.dependencies.append(Dependency(name="meson", dep_type="tool", apt_package="meson"))
        analysis.dependencies.append(
            Dependency(name="ninja", dep_type="tool", apt_package="ninja-build")
        )

    def _analyze_python(self, source_dir: Path, analysis: BuildAnalysis) -> None:
        """Analyze Python build files for dependencies."""
        # Add python dev package
        analysis.dependencies.append(
            Dependency(name="python3-dev", dep_type="tool", apt_package="python3-dev")
        )
        analysis.dependencies.append(
            Dependency(name="pip", dep_type="tool", apt_package="python3-pip")
        )

    def _check_installed(self, analysis: BuildAnalysis) -> None:
        """Check which dependencies are already installed."""
        for dep in analysis.dependencies:
            if dep.dep_type == "tool":
                # Check if tool is in PATH
                dep.found = shutil.which(dep.name) is not None
            elif dep.dep_type == "pkg-config" and dep.apt_package:
                # Check via pkg-config
                try:
                    result = subprocess.run(
                        ["pkg-config", "--exists", dep.name],
                        capture_output=True,
                        timeout=5,
                    )
                    dep.found = result.returncode == 0
                except subprocess.TimeoutExpired:
                    dep.found = False
            elif dep.apt_package:
                # Check if apt package is installed
                try:
                    result = subprocess.run(
                        ["dpkg-query", "-W", "-f=${Status}", dep.apt_package],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    dep.found = "install ok installed" in result.stdout
                except subprocess.TimeoutExpired:
                    dep.found = False

    def _generate_build_commands(self, build_system: BuildSystem, source_dir: Path) -> list[str]:
        """Generate suggested build commands for the build system."""
        if build_system == BuildSystem.CMAKE:
            return [
                "mkdir -p build && cd build",
                "cmake ..",
                "make -j$(nproc)",
                "sudo make install",
            ]
        elif build_system == BuildSystem.AUTOTOOLS:
            commands = []
            if not (source_dir / "configure").exists():
                commands.append("autoreconf -fi")
            commands.extend(
                [
                    "./configure",
                    "make -j$(nproc)",
                    "sudo make install",
                ]
            )
            return commands
        elif build_system == BuildSystem.MESON:
            return [
                "meson setup build",
                "ninja -C build",
                "sudo ninja -C build install",
            ]
        elif build_system == BuildSystem.PYTHON:
            return [
                "pip install .",
            ]
        elif build_system == BuildSystem.MAKE:
            return [
                "make -j$(nproc)",
                "sudo make install",
            ]
        else:
            return ["# Unable to determine build commands"]

    def install_dependencies(self, packages: list[str], dry_run: bool = False) -> bool:
        """Install missing apt packages.

        Args:
            packages: List of apt packages to install.
            dry_run: If True, just show what would be installed.

        Returns:
            True if installation succeeded (or dry_run), False otherwise.
        """
        if not packages:
            console.print("[green]No packages to install.[/green]")
            return True

        if dry_run:
            console.print("[bold]Would install:[/bold]")
            for pkg in packages:
                console.print(f"  - {pkg}")
            return True

        console.print(f"[bold]Installing {len(packages)} packages...[/bold]")
        cmd = ["sudo", "apt-get", "install", "-y"] + packages

        result = subprocess.run(cmd)
        if result.returncode != 0:
            console.print(
                "[red]Package installation failed. Check the output above for details.[/red]"
            )
            return False
        return True

    def find_alternative(self, name: str) -> str | None:
        """Check if there's a packaged alternative to building from source.

        Args:
            name: Name of the software to check.

        Returns:
            Package name if available, None otherwise.
        """
        # Search apt cache
        result = subprocess.run(
            ["apt-cache", "search", f"^{name}$"],
            capture_output=True,
            text=True,
        )

        if result.stdout.strip():
            return result.stdout.strip().split()[0]

        # Try with lib prefix
        result = subprocess.run(
            ["apt-cache", "search", f"^lib{name}"],
            capture_output=True,
            text=True,
        )

        if result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            # Prefer -dev packages
            for line in lines:
                if "-dev" in line:
                    return line.split()[0]
            return lines[0].split()[0]

        return None

    def track_installation(self, install: ManualInstall) -> None:
        """Track a manual installation.

        Args:
            install: ManualInstall record to save.
        """
        history = self._load_history()
        history[install.name] = {
            "source_dir": install.source_dir,
            "installed_at": install.installed_at,
            "packages_installed": install.packages_installed,
            "files_installed": install.files_installed,
            "prefix": install.prefix,
        }
        self._save_history(history)

    def list_installations(self) -> list[ManualInstall]:
        """List all tracked manual installations.

        Returns:
            List of ManualInstall records.
        """
        history = self._load_history()
        installations = []
        for name, data in history.items():
            installations.append(
                ManualInstall(
                    name=name,
                    source_dir=data.get("source_dir", ""),
                    installed_at=data.get("installed_at", ""),
                    packages_installed=data.get("packages_installed", []),
                    files_installed=data.get("files_installed", []),
                    prefix=data.get("prefix", "/usr/local"),
                )
            )
        return installations

    def cleanup_installation(self, name: str, dry_run: bool = False) -> bool:
        """Remove a tracked manual installation.

        Args:
            name: Name of the installation to remove.
            dry_run: If True, just show what would be removed.

        Returns:
            True if cleanup succeeded, False otherwise.
        """
        history = self._load_history()
        if name not in history:
            console.print(f"[red]Installation '{name}' not found in history.[/red]")
            return False

        data = history[name]
        packages = data.get("packages_installed", [])

        if dry_run:
            console.print(f"[bold]Would remove installation: {name}[/bold]")
            if packages:
                console.print("Packages that were installed:")
                for pkg in packages:
                    console.print(f"  - {pkg}")
            return True

        # Handle package removal first (before removing from history)
        if packages:
            remove_pkgs = Confirm.ask(
                f"Remove {len(packages)} packages that were installed for this build?"
            )
            if remove_pkgs:
                cmd = ["sudo", "apt-get", "remove", "-y"] + packages
                subprocess.run(cmd)

        # Remove from history after all user interactions
        del history[name]
        self._save_history(history)

        console.print(f"[green]Removed '{name}' from tracking.[/green]")

        return True

    def _load_history(self) -> dict:
        """Load installation history from file."""
        if not self.history_file.exists():
            return {}
        try:
            return json.loads(self.history_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_history(self, history: dict) -> None:
        """Save installation history to file."""
        self.history_file.write_text(json.dumps(history, indent=2), encoding="utf-8")


def run_analyze_command(source_dir: str) -> None:
    """Analyze a source directory and show results.

    Args:
        source_dir: Path to the source directory.
    """
    helper = TarballHelper()
    path = Path(source_dir).resolve()

    if not path.exists():
        console.print(f"[red]Directory not found: {path}[/red]")
        return

    console.print(f"\n[bold]Analyzing: {path}[/bold]\n")

    analysis = helper.analyze(path)

    # Show build system
    console.print(f"[cyan]Build System:[/cyan] {analysis.build_system.value}")
    console.print()

    # Check for packaged alternative
    dir_name = path.name.split("-")[0]  # Get name without version
    alternative = helper.find_alternative(dir_name)
    if alternative:
        console.print(
            Panel(
                f"[yellow]Packaged alternative available:[/yellow] [bold]{alternative}[/bold]\n"
                f"Consider: [cyan]sudo apt install {alternative}[/cyan]",
                title="Suggestion",
                border_style="yellow",
            )
        )
        console.print()

    # Show dependencies
    if analysis.dependencies:
        table = Table(title="Dependencies", box=box.SIMPLE)
        table.add_column("Name", style="cyan")
        table.add_column("Type")
        table.add_column("Apt Package")
        table.add_column("Status")

        for dep in analysis.dependencies:
            status = "[green]✓ Found[/green]" if dep.found else "[red]✗ Missing[/red]"
            table.add_row(
                dep.name,
                dep.dep_type,
                dep.apt_package or "[dim]unknown[/dim]",
                status,
            )

        console.print(table)
        console.print()

    # Show missing packages
    if analysis.missing_packages:
        console.print("[bold]Missing packages to install:[/bold]")
        console.print(f"  sudo apt install {' '.join(analysis.missing_packages)}")
        console.print()

    # Show build commands
    if analysis.build_commands:
        console.print("[bold]Build commands:[/bold]")
        for cmd in analysis.build_commands:
            console.print(f"  [cyan]{cmd}[/cyan]")


def run_install_deps_command(source_dir: str, dry_run: bool = False) -> None:
    """Install dependencies for a source directory.

    Args:
        source_dir: Path to the source directory.
        dry_run: If True, just show what would be installed.
    """
    helper = TarballHelper()
    path = Path(source_dir).resolve()

    if not path.exists():
        console.print(f"[red]Directory not found: {path}[/red]")
        return

    analysis = helper.analyze(path)

    if not analysis.missing_packages:
        console.print("[green]All dependencies are already installed![/green]")
        return

    helper.install_dependencies(analysis.missing_packages, dry_run=dry_run)


def run_list_command() -> None:
    """List all tracked manual installations."""
    helper = TarballHelper()
    installations = helper.list_installations()

    if not installations:
        console.print("[dim]No manual installations tracked.[/dim]")
        return

    table = Table(title="Manual Installations", box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Installed At")
    table.add_column("Packages")
    table.add_column("Prefix")

    for install in installations:
        table.add_row(
            install.name,
            install.installed_at,
            str(len(install.packages_installed)),
            install.prefix,
        )

    console.print(table)


def run_cleanup_command(name: str, dry_run: bool = False) -> None:
    """Clean up a tracked manual installation.

    Args:
        name: Name of the installation to clean up.
        dry_run: If True, just show what would be removed.
    """
    helper = TarballHelper()
    helper.cleanup_installation(name, dry_run=dry_run)


def run_track_command(name: str, source_dir: str, packages: list[str]) -> None:
    """Track a manual installation.

    Args:
        name: Name of the software.
        source_dir: Path to the source directory.
        packages: List of packages that were installed.
    """
    helper = TarballHelper()
    install = ManualInstall(
        name=name,
        source_dir=source_dir,
        installed_at=datetime.now().isoformat(),
        packages_installed=packages,
    )
    helper.track_installation(install)
    console.print(f"[green]Tracked installation: {name}[/green]")
