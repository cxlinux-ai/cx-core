#!/usr/bin/env python3
"""
Tarball Build Helper for Cortex Linux
Analyzes configure scripts and CMakeLists.txt to detect missing dependencies,
automatically installs -dev packages, tracks manual installations for cleanup,
and suggests package alternatives when available.
Pain Point #21 Solution: Prevents build failures from missing headers and dependencies.
"""

import logging
import os
import re
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from cortex.installation_history import InstallationHistory, InstallationType, InstallationStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BuildSystem(Enum):
    """Detected build system type"""

    AUTOTOOLS = "autotools"  # configure script
    CMAKE = "cmake"  # CMakeLists.txt
    MESON = "meson"  # meson.build
    UNKNOWN = "unknown"


@dataclass
class DependencyRequirement:
    """Represents a dependency requirement from build files"""

    name: str
    library_name: str  # e.g., "ssl" for libssl
    header_file: str | None = None  # e.g., "openssl/ssl.h"
    pkg_config: str | None = None  # e.g., "openssl"
    version: str | None = None
    required: bool = True
    found: bool = False
    suggested_package: str | None = None
    alternatives: list[str] = field(default_factory=list)


@dataclass
class TarballAnalysis:
    """Analysis results for a tarball"""

    tarball_path: str
    extracted_path: str | None = None
    build_system: BuildSystem = BuildSystem.UNKNOWN
    dependencies: list[DependencyRequirement] = field(default_factory=list)
    missing_dependencies: list[DependencyRequirement] = field(default_factory=list)
    build_commands: list[str] = field(default_factory=list)
    install_commands: list[str] = field(default_factory=list)


class TarballHelper:
    """
    Helper for building software from tarballs.
    Analyzes configure scripts and CMakeLists.txt to detect dependencies,
    installs missing -dev packages, and tracks installations for cleanup.
    """

    # Common library to -dev package mappings
    LIBRARY_TO_DEV_PACKAGE = {
        # SSL/TLS
        "ssl": "libssl-dev",
        "crypto": "libssl-dev",
        "openssl": "libssl-dev",
        # Compression
        "z": "zlib1g-dev",
        "zlib": "zlib1g-dev",
        "bz2": "libbz2-dev",
        "bzip2": "libbz2-dev",
        "lzma": "liblzma-dev",
        "xz": "liblzma-dev",
        # XML
        "xml2": "libxml2-dev",
        "xml": "libxml2-dev",
        "expat": "libexpat1-dev",
        # Image formats
        "jpeg": "libjpeg-dev",
        "png": "libpng-dev",
        "png16": "libpng-dev",
        "tiff": "libtiff-dev",
        "gif": "libgif-dev",
        "webp": "libwebp-dev",
        # Graphics
        "X11": "libx11-dev",
        "Xext": "libxext-dev",
        "Xrender": "libxrender-dev",
        "Xrandr": "libxrandr-dev",
        "Xinerama": "libxinerama-dev",
        "Xcursor": "libxcursor-dev",
        "Xfixes": "libxfixes-dev",
        "Xdamage": "libxdamage-dev",
        "Xcomposite": "libxcomposite-dev",
        "Xft": "libxft-dev",
        # Audio
        "asound": "libasound2-dev",
        "pulse": "libpulse-dev",
        "sndfile": "libsndfile1-dev",
        # Database
        "pq": "libpq-dev",
        "mysqlclient": "libmysqlclient-dev",
        "sqlite3": "libsqlite3-dev",
        # Networking
        "curl": "libcurl4-openssl-dev",
        "curl4": "libcurl4-openssl-dev",
        "idn": "libidn2-dev",
        "idn2": "libidn2-dev",
        # Crypto
        "crypto": "libssl-dev",
        "gcrypt": "libgcrypt20-dev",
        "gpg-error": "libgpg-error-dev",
        "nettle": "libnettle-dev",
        # Text processing
        "pcre": "libpcre3-dev",
        "pcre2": "libpcre2-dev",
        "pcre16": "libpcre3-dev",
        "pcre32": "libpcre3-dev",
        "icu": "libicu-dev",
        "readline": "libreadline-dev",
        "ncurses": "libncurses5-dev",
        "ncursesw": "libncursesw5-dev",
        # System
        "dl": None,  # Usually in libc
        "pthread": None,  # Usually in libc
        "m": None,  # Math library, usually in libc
        "rt": None,  # Real-time, usually in libc
        "util": None,  # Usually in libc
        # Python
        "python3": "python3-dev",
        "python3.11": "python3-dev",
        "python3.12": "python3-dev",
        # GTK/GLib
        "glib-2.0": "libglib2.0-dev",
        "gobject-2.0": "libglib2.0-dev",
        "gio-2.0": "libglib2.0-dev",
        "gtk-3": "libgtk-3-dev",
        "gtk+-3.0": "libgtk-3-dev",
        "gtk-4": "libgtk-4-dev",
        "gtk+-4.0": "libgtk-4-dev",
        # Qt
        "Qt5Core": "qtbase5-dev",
        "Qt5Gui": "qtbase5-dev",
        "Qt5Widgets": "qtbase5-dev",
        "Qt5Network": "qtbase5-dev",
        # Fonts
        "fontconfig": "libfontconfig1-dev",
        "freetype": "libfreetype6-dev",
        # Video
        "avcodec": "libavcodec-dev",
        "avformat": "libavformat-dev",
        "avutil": "libavutil-dev",
        "swscale": "libswscale-dev",
        # Other common libraries
        "ffi": "libffi-dev",
        "uuid": "uuid-dev",
        "uuid1": "uuid-dev",
        "yaml": "libyaml-dev",
        "yaml-0.1": "libyaml-dev",
        "event": "libevent-dev",
        "event-2.0": "libevent-dev",
        "event_pthreads": "libevent-dev",
        "systemd": "libsystemd-dev",
        "udev": "libudev-dev",
        "usb-1.0": "libusb-1.0-0-dev",
        "usb": "libusb-dev",
    }

    # Header file to package mappings (for cases where library name doesn't match)
    HEADER_TO_PACKAGE = {
        "openssl/ssl.h": "libssl-dev",
        "openssl/crypto.h": "libssl-dev",
        "zlib.h": "zlib1g-dev",
        "bzlib.h": "libbz2-dev",
        "lzma.h": "liblzma-dev",
        "xml2/libxml/parser.h": "libxml2-dev",
        "expat.h": "libexpat1-dev",
        "jpeglib.h": "libjpeg-dev",
        "png.h": "libpng-dev",
        "tiff.h": "libtiff-dev",
        "gif_lib.h": "libgif-dev",
        "webp/decode.h": "libwebp-dev",
        "X11/Xlib.h": "libx11-dev",
        "X11/extensions/Xext.h": "libxext-dev",
        "X11/extensions/Xrender.h": "libxrender-dev",
        "X11/extensions/Xrandr.h": "libxrandr-dev",
        "X11/extensions/Xinerama.h": "libxinerama-dev",
        "X11/Xcursor/Xcursor.h": "libxcursor-dev",
        "X11/extensions/Xfixes.h": "libxfixes-dev",
        "X11/extensions/Xdamage.h": "libxdamage-dev",
        "X11/extensions/Xcomposite.h": "libxcomposite-dev",
        "X11/Xft/Xft.h": "libxft-dev",
        "alsa/asoundlib.h": "libasound2-dev",
        "pulse/pulseaudio.h": "libpulse-dev",
        "sndfile.h": "libsndfile1-dev",
        "postgresql/libpq-fe.h": "libpq-dev",
        "mysql/mysql.h": "libmysqlclient-dev",
        "sqlite3.h": "libsqlite3-dev",
        "curl/curl.h": "libcurl4-openssl-dev",
        "idn2.h": "libidn2-dev",
        "gcrypt.h": "libgcrypt20-dev",
        "gpg-error.h": "libgpg-error-dev",
        "nettle/nettle-types.h": "libnettle-dev",
        "pcre.h": "libpcre3-dev",
        "pcre2.h": "libpcre2-dev",
        "unicode/ucnv.h": "libicu-dev",
        "readline/readline.h": "libreadline-dev",
        "ncurses.h": "libncurses5-dev",
        "ncursesw/ncurses.h": "libncursesw5-dev",
        "Python.h": "python3-dev",
        "glib.h": "libglib2.0-dev",
        "glib-object.h": "libglib2.0-dev",
        "gtk/gtk.h": "libgtk-3-dev",
        "QtCore/QtCore": "qtbase5-dev",
        "fontconfig/fontconfig.h": "libfontconfig1-dev",
        "ft2build.h": "libfreetype6-dev",
        "libavcodec/avcodec.h": "libavcodec-dev",
        "ffi.h": "libffi-dev",
        "uuid/uuid.h": "uuid-dev",
        "yaml.h": "libyaml-dev",
        "event2/event.h": "libevent-dev",
        "systemd/sd-daemon.h": "libsystemd-dev",
        "libudev.h": "libudev-dev",
        "libusb-1.0/libusb.h": "libusb-1.0-0-dev",
    }

    # Alternative package suggestions (when primary package not available)
    PACKAGE_ALTERNATIVES = {
        "libssl-dev": ["libssl1.1-dev", "libssl1.0-dev"],
        "libcurl4-openssl-dev": ["libcurl4-gnutls-dev", "libcurl4-nss-dev"],
        "libgtk-3-dev": ["libgtk2.0-dev"],
        "libgtk-4-dev": ["libgtk-3-dev"],
        "qtbase5-dev": ["qt4-dev-tools"],
        "libmysqlclient-dev": ["libmariadb-dev"],
        "libevent-dev": ["libev-dev"],
    }

    def __init__(self, track_installations: bool = True):
        """
        Initialize tarball helper.
        Args:
            track_installations: If True, track all installations for cleanup
        """
        self.track_installations = track_installations
        self.installation_history = InstallationHistory() if track_installations else None
        self.installed_packages: list[str] = []

    def _run_command(self, cmd: list[str], cwd: str | None = None) -> tuple[bool, str, str]:
        """Execute command and return success, stdout, stderr"""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, cwd=cwd
            )
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "", "Command timed out")
        except Exception as e:
            return (False, "", str(e))

    def _check_package_installed(self, package: str) -> bool:
        """Check if a package is installed"""
        success, _, _ = self._run_command(["dpkg", "-l", package])
        return success

    def _find_package_for_library(self, library_name: str) -> str | None:
        """Find apt package name for a library"""
        # Remove 'lib' prefix and common suffixes
        lib_clean = re.sub(r"^lib", "", library_name.lower())
        lib_clean = re.sub(r"\.(so|a)(\..*)?$", "", lib_clean)

        # Try direct mapping
        if lib_clean in self.LIBRARY_TO_DEV_PACKAGE:
            return self.LIBRARY_TO_DEV_PACKAGE[lib_clean]

        # Try with common prefixes
        for prefix in ["", "lib"]:
            test_name = f"{prefix}{lib_clean}"
            if test_name in self.LIBRARY_TO_DEV_PACKAGE:
                return self.LIBRARY_TO_DEV_PACKAGE[test_name]

        # Try apt-cache search
        success, stdout, _ = self._run_command(
            ["apt-cache", "search", f"^{lib_clean}-dev"]
        )
        if success and stdout.strip():
            # Get first matching package
            for line in stdout.split("\n"):
                if " - " in line:
                    pkg_name = line.split(" - ")[0].strip()
                    if "-dev" in pkg_name:
                        return pkg_name

        return None

    def _find_package_for_header(self, header_file: str) -> str | None:
        """Find apt package name for a header file"""
        # Try direct mapping
        if header_file in self.HEADER_TO_PACKAGE:
            return self.HEADER_TO_PACKAGE[header_file]

        # Try with common include paths
        for include_path in ["", "include/", "usr/include/"]:
            test_path = f"{include_path}{header_file}"
            if test_path in self.HEADER_TO_PACKAGE:
                return self.HEADER_TO_PACKAGE[test_path]

        # Try to find package using dpkg -S
        success, stdout, _ = self._run_command(["dpkg", "-S", header_file])
        if success:
            # Extract package name (format: package: path/to/file)
            for line in stdout.split("\n"):
                if ":" in line:
                    pkg_name = line.split(":")[0].strip()
                    # Check if it's a -dev package or find the -dev variant
                    if "-dev" in pkg_name:
                        return pkg_name
                    else:
                        # Try to find -dev variant
                        dev_pkg = pkg_name.replace("-common", "-dev").replace("-runtime", "-dev")
                        if self._check_package_installed(dev_pkg):
                            return dev_pkg

        return None

    def _get_package_alternatives(self, package: str) -> list[str]:
        """Get alternative packages if primary not available"""
        return self.PACKAGE_ALTERNATIVES.get(package, [])

    def _detect_build_system(self, source_dir: Path) -> BuildSystem:
        """Detect the build system used"""
        if (source_dir / "configure").exists() or (source_dir / "configure.ac").exists():
            return BuildSystem.AUTOTOOLS
        elif (source_dir / "CMakeLists.txt").exists():
            return BuildSystem.CMAKE
        elif (source_dir / "meson.build").exists():
            return BuildSystem.MESON
        return BuildSystem.UNKNOWN

    def _parse_configure_script(self, source_dir: Path) -> list[DependencyRequirement]:
        """Parse configure script for dependencies"""
        dependencies = []
        configure_path = source_dir / "configure"

        if not configure_path.exists():
            return dependencies

        try:
            content = configure_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Could not read configure script: {e}")
            return dependencies

        # Pattern: AC_CHECK_LIB(library, function, ...)
        ac_check_lib_pattern = r"AC_CHECK_LIB\s*\(\s*([^,)]+)\s*[,)]"
        for match in re.finditer(ac_check_lib_pattern, content):
            lib_name = match.group(1).strip().strip('"\'')
            if lib_name:
                dep = DependencyRequirement(
                    name=lib_name,
                    library_name=lib_name,
                    required=True,
                )
                dep.suggested_package = self._find_package_for_library(lib_name)
                dependencies.append(dep)

        # Pattern: PKG_CHECK_MODULES([VAR], [package])
        pkg_check_pattern = r"PKG_CHECK_MODULES\s*\(\s*[^,]+,\s*\[([^\]]+)\]"
        for match in re.finditer(pkg_check_pattern, content):
            pkg_name = match.group(1).strip().strip('"\'')
            if pkg_name:
                dep = DependencyRequirement(
                    name=pkg_name,
                    library_name=pkg_name,
                    pkg_config=pkg_name,
                    required=True,
                )
                dep.suggested_package = self._find_package_for_library(pkg_name)
                dependencies.append(dep)

        # Pattern: AC_CHECK_HEADER(header, ...)
        ac_check_header_pattern = r"AC_CHECK_HEADER\s*\(\s*([^,)]+)\s*[,)]"
        for match in re.finditer(ac_check_header_pattern, content):
            header = match.group(1).strip().strip('"\'')
            if header:
                dep = DependencyRequirement(
                    name=header,
                    library_name=header.split("/")[0],
                    header_file=header,
                    required=True,
                )
                dep.suggested_package = self._find_package_for_header(header)
                dependencies.append(dep)

        return dependencies

    def _parse_cmake_lists(self, source_dir: Path) -> list[DependencyRequirement]:
        """Parse CMakeLists.txt for dependencies"""
        dependencies = []
        cmake_path = source_dir / "CMakeLists.txt"

        if not cmake_path.exists():
            return dependencies

        try:
            content = cmake_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Could not read CMakeLists.txt: {e}")
            return dependencies

        # Pattern: find_package(PackageName [version] REQUIRED)
        find_package_pattern = r"find_package\s*\(\s*([^\s)]+)(?:\s+([^\s)]+))?(?:\s+REQUIRED)?"
        for match in re.finditer(find_package_pattern, content, re.IGNORECASE):
            pkg_name = match.group(1).strip()
            version = match.group(2) if match.group(2) else None
            required = "REQUIRED" in match.group(0).upper()

            if pkg_name:
                dep = DependencyRequirement(
                    name=pkg_name,
                    library_name=pkg_name,
                    version=version,
                    required=required,
                )
                dep.suggested_package = self._find_package_for_library(pkg_name)
                dependencies.append(dep)

        # Pattern: find_library(VAR ... NAMES libname ...)
        find_library_pattern = r"find_library\s*\([^)]+NAMES\s+([^\s)]+)"
        for match in re.finditer(find_library_pattern, content, re.IGNORECASE):
            lib_name = match.group(1).strip()
            if lib_name:
                # Remove lib prefix and .so suffix
                lib_clean = re.sub(r"^lib", "", lib_name)
                lib_clean = re.sub(r"\.(so|a)(\..*)?$", "", lib_clean)

                dep = DependencyRequirement(
                    name=lib_clean,
                    library_name=lib_clean,
                    required=True,
                )
                dep.suggested_package = self._find_package_for_library(lib_clean)
                dependencies.append(dep)

        # Pattern: pkg_check_modules(VAR ... package ...)
        pkg_check_pattern = r"pkg_check_modules\s*\([^)]+([^\s)]+)"
        for match in re.finditer(pkg_check_pattern, content, re.IGNORECASE):
            pkg_name = match.group(1).strip()
            if pkg_name:
                dep = DependencyRequirement(
                    name=pkg_name,
                    library_name=pkg_name,
                    pkg_config=pkg_name,
                    required=True,
                )
                dep.suggested_package = self._find_package_for_library(pkg_name)
                dependencies.append(dep)

        return dependencies

    def analyze_tarball(self, tarball_path: str, extract_to: str | None = None) -> TarballAnalysis:
        """
        Analyze a tarball to detect dependencies and build requirements.
        Args:
            tarball_path: Path to the tarball file
            extract_to: Directory to extract to (uses temp dir if None)
        Returns:
            TarballAnalysis with detected dependencies and build system
        """
        tarball_path = Path(tarball_path).resolve()

        if not tarball_path.exists():
            raise FileNotFoundError(f"Tarball not found: {tarball_path}")

        analysis = TarballAnalysis(tarball_path=str(tarball_path))

        # Extract tarball
        if extract_to:
            extract_dir = Path(extract_to)
            extract_dir.mkdir(parents=True, exist_ok=True)
        else:
            extract_dir = Path(tempfile.mkdtemp(prefix="cortex-tarball-"))

        try:
            logger.info(f"Extracting {tarball_path} to {extract_dir}")
            with tarfile.open(tarball_path, "r:*") as tar:
                # Get the root directory name
                members = tar.getmembers()
                if members:
                    root_dir = members[0].name.split("/")[0]
                    tar.extractall(extract_dir)

                source_dir = extract_dir / root_dir if members else extract_dir
                analysis.extracted_path = str(source_dir)

                # Detect build system
                analysis.build_system = self._detect_build_system(source_dir)

                # Parse dependencies based on build system
                if analysis.build_system == BuildSystem.AUTOTOOLS:
                    analysis.dependencies = self._parse_configure_script(source_dir)
                    analysis.build_commands = [
                        "./configure",
                        "make",
                    ]
                    analysis.install_commands = ["sudo make install"]
                elif analysis.build_system == BuildSystem.CMAKE:
                    analysis.dependencies = self._parse_cmake_lists(source_dir)
                    analysis.build_commands = [
                        "mkdir -p build",
                        "cd build",
                        "cmake ..",
                        "make",
                    ]
                    analysis.install_commands = ["sudo make install"]
                elif analysis.build_system == BuildSystem.MESON:
                    analysis.dependencies = []  # TODO: Parse meson.build
                    analysis.build_commands = [
                        "meson setup build",
                        "ninja -C build",
                    ]
                    analysis.install_commands = ["sudo ninja -C build install"]

                # Check which dependencies are missing
                for dep in analysis.dependencies:
                    if dep.suggested_package:
                        dep.found = self._check_package_installed(dep.suggested_package)
                        if not dep.found:
                            analysis.missing_dependencies.append(dep)
                            # Get alternatives
                            dep.alternatives = self.suggest_alternatives(dep.suggested_package)

        except Exception as e:
            logger.error(f"Error analyzing tarball: {e}")
            raise

        return analysis

    def install_missing_dependencies(
        self, analysis: TarballAnalysis, dry_run: bool = False
    ) -> tuple[bool, list[str]]:
        """
        Install missing -dev packages automatically.
        Args:
            analysis: TarballAnalysis with missing dependencies
            dry_run: If True, only show what would be installed
        Returns:
            (success, list of installed packages)
        """
        if not analysis.missing_dependencies:
            logger.info("No missing dependencies found")
            return (True, [])

        packages_to_install = []
        for dep in analysis.missing_dependencies:
            if dep.suggested_package:
                packages_to_install.append(dep.suggested_package)
            elif dep.alternatives:
                # Try first alternative
                packages_to_install.append(dep.alternatives[0])

        if not packages_to_install:
            logger.warning("No packages to install (missing suggestions)")
            return (False, [])

        # Remove duplicates
        packages_to_install = list(set(packages_to_install))

        if dry_run:
            logger.info(f"Would install: {', '.join(packages_to_install)}")
            return (True, packages_to_install)

        # Install packages
        logger.info(f"Installing missing dependencies: {', '.join(packages_to_install)}")
        success, stdout, stderr = self._run_command(
            ["sudo", "apt-get", "install", "-y"] + packages_to_install
        )

        if success:
            self.installed_packages.extend(packages_to_install)
            # Track installation if enabled
            if self.track_installations and self.installation_history:
                from datetime import datetime

                install_id = self.installation_history.record_installation(
                    InstallationType.INSTALL,
                    packages_to_install,
                    [f"sudo apt-get install -y {' '.join(packages_to_install)}"],
                    datetime.now(),
                )
                self.installation_history.update_installation(
                    install_id, InstallationStatus.SUCCESS
                )
            return (True, packages_to_install)
        else:
            logger.error(f"Failed to install packages: {stderr}")
            return (False, [])

    def get_cleanup_commands(self) -> list[str]:
        """
        Get commands to cleanup manually installed packages.
        Returns:
            List of apt-get remove commands
        """
        if not self.installed_packages:
            return []

        return [f"sudo apt-get remove -y {' '.join(self.installed_packages)}"]

    def suggest_alternatives(self, package: str) -> list[str]:
        """
        Suggest alternative packages when primary not available.
        Args:
            package: Package name that's not available
        Returns:
            List of alternative package names
        """
        return self.PACKAGE_ALTERNATIVES.get(package, [])


# CLI Interface
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Tarball build helper for Cortex Linux")
    parser.add_argument("tarball", help="Path to tarball file")
    parser.add_argument("--extract-to", help="Directory to extract tarball")
    parser.add_argument("--install-deps", action="store_true", help="Install missing dependencies")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--no-track", action="store_true", help="Don't track installations")

    args = parser.parse_args()

    helper = TarballHelper(track_installations=not args.no_track)

    try:
        print(f"Analyzing tarball: {args.tarball}")
        analysis = helper.analyze_tarball(args.tarball, args.extract_to)

        print(f"\nBuild System: {analysis.build_system.value}")
        print(f"Extracted to: {analysis.extracted_path}")

        if analysis.dependencies:
            print(f"\nDependencies found: {len(analysis.dependencies)}")
            for dep in analysis.dependencies:
                status = "✓" if dep.found else "✗"
                print(f"  {status} {dep.name}")
                if dep.suggested_package:
                    print(f"    → {dep.suggested_package}")

        if analysis.missing_dependencies:
            print(f"\nMissing dependencies: {len(analysis.missing_dependencies)}")
            for dep in analysis.missing_dependencies:
                print(f"  ✗ {dep.name}")
                if dep.suggested_package:
                    print(f"    → Install: {dep.suggested_package}")
                if dep.alternatives:
                    print(f"    → Alternatives: {', '.join(dep.alternatives)}")

        if args.install_deps:
            success, installed = helper.install_missing_dependencies(analysis, args.dry_run)
            if success:
                print(f"\n✓ Installed {len(installed)} packages")
            else:
                print("\n✗ Failed to install dependencies")
                sys.exit(1)

        if analysis.build_commands:
            print("\nBuild commands:")
            for cmd in analysis.build_commands:
                print(f"  {cmd}")

        if helper.installed_packages:
            print("\nCleanup commands:")
            for cmd in helper.get_cleanup_commands():
                print(f"  {cmd}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)