#!/usr/bin/env python3
"""
Source Package Builder for Cortex Linux

Builds and installs packages from source code when binaries are unavailable.
Supports common build systems: autotools, cmake, make, python setup.py, etc.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cortex.branding import cx_print
from cortex.dependency_resolver import DependencyResolver
from cortex.utils.commands import CommandResult, run_command, validate_command

logger = logging.getLogger(__name__)

# Build cache directory
CACHE_DIR = Path.home() / ".cortex" / "build_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Common build dependencies by category
BUILD_DEPENDENCIES = {
    "base": ["build-essential", "gcc", "g++", "make", "cmake", "pkg-config"],
    "autotools": ["autoconf", "automake", "libtool", "gettext"],
    "python": ["python3-dev", "python3-pip", "python3-setuptools", "python3-wheel"],
    "ssl": ["libssl-dev"],
    "zlib": ["zlib1g-dev"],
    "curl": ["libcurl4-openssl-dev"],
    "xml": ["libxml2-dev"],
    "sqlite": ["libsqlite3-dev"],
    "readline": ["libreadline-dev"],
}


@dataclass
class BuildConfig:
    """Configuration for a source build."""

    package_name: str
    version: str | None = None
    source_url: str | None = None
    source_type: str = "tarball"  # tarball, git, github
    build_system: str = "autotools"  # autotools, cmake, make, python, custom
    configure_args: list[str] | None = None
    make_args: list[str] | None = None
    install_prefix: str = "/usr/local"
    cache_key: str | None = None


@dataclass
class BuildResult:
    """Result of a build operation."""

    success: bool
    package_name: str
    version: str | None
    build_dir: str
    install_commands: list[str]
    error_message: str | None = None
    cached: bool = False


class SourceBuilder:
    """Builds packages from source code.

    Handles fetching source code, detecting build systems, managing build
    dependencies, configuring builds, compiling, and installing packages.
    Supports caching of build artifacts for faster subsequent builds.

    Attributes:
        dependency_resolver: DependencyResolver instance for checking installed packages.
        cache_dir: Path to build cache directory.
    """

    def __init__(self):
        self.dependency_resolver = DependencyResolver()
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, package_name: str, version: str | None, source_url: str) -> str:
        """Generate a cache key for a build."""
        key_data = f"{package_name}:{version}:{source_url}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def _check_cache(self, cache_key: str) -> Path | None:
        """Check if a build is cached."""
        cache_path = self.cache_dir / cache_key
        if cache_path.exists() and (cache_path / "installed").exists():
            return cache_path
        return None

    def _save_to_cache(self, cache_key: str, build_dir: Path, install_commands: list[str]) -> None:
        """Save build artifacts to cache."""
        cache_path = self.cache_dir / cache_key
        cache_path.mkdir(parents=True, exist_ok=True)

        # Save metadata
        metadata = {
            "build_dir": str(build_dir),
            "install_commands": install_commands,
            "timestamp": str(Path(build_dir).stat().st_mtime),
        }
        with open(cache_path / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        # Mark as installed
        (cache_path / "installed").touch()

    def detect_build_dependencies(self, package_name: str, build_system: str) -> list[str]:
        """Detect required build dependencies for a package.

        Args:
            package_name: Name of the package to build.
            build_system: Build system type (autotools, cmake, make, python).

        Returns:
            List of missing build dependency package names that need to be installed.
        """
        required_deps = set()

        # Base dependencies
        required_deps.update(BUILD_DEPENDENCIES["base"])

        # Build system specific
        if build_system == "autotools":
            required_deps.update(BUILD_DEPENDENCIES["autotools"])
        elif build_system == "cmake":
            required_deps.add("cmake")
        elif build_system == "python":
            required_deps.update(BUILD_DEPENDENCIES["python"])

        # Package-specific dependencies (common patterns)
        if "python" in package_name.lower():
            required_deps.update(BUILD_DEPENDENCIES["python"])

        # Check which are missing
        missing = []
        for dep in required_deps:
            if not self.dependency_resolver.is_package_installed(dep):
                missing.append(dep)

        return missing

    def fetch_source(
        self, package_name: str, source_url: str | None, version: str | None
    ) -> Path:
        """Fetch source code from URL or detect from package name.

        Args:
            package_name: Name of the package to fetch.
            source_url: URL to source code (optional, will auto-detect if not provided).
            version: Version to fetch (optional).

        Returns:
            Path to extracted source directory.

        Raises:
            RuntimeError: If source download or extraction fails.
            ValueError: If source location cannot be detected.
        """
        if source_url:
            return self._fetch_from_url(source_url, package_name, version)
        else:
            # Try to detect source location
            return self._detect_source_location(package_name, version)

    def _fetch_from_url(self, url: str, package_name: str, version: str | None) -> Path:
        """Fetch source from a URL."""
        temp_dir = Path(tempfile.mkdtemp(prefix=f"cortex-build-{package_name}-"))

        try:
            # Download
            cx_print(f"📥 Downloading {package_name} source...", "info")
            archive_path = temp_dir / "source.tar.gz"

            if url.startswith("https://github.com/"):
                # GitHub release or archive
                if not url.endswith((".tar.gz", ".zip")):
                    if version:
                        url = f"{url}/archive/refs/tags/v{version}.tar.gz"
                    else:
                        url = f"{url}/archive/refs/heads/main.tar.gz"

            urllib.request.urlretrieve(url, archive_path)

            # Extract
            cx_print(f"📦 Extracting source...", "info")
            extract_dir = temp_dir / "extracted"
            extract_dir.mkdir()

            if archive_path.suffix == ".gz" or archive_path.suffixes[-2:] == [".tar", ".gz"]:
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(extract_dir)
            elif archive_path.suffix == ".zip":
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    zip_ref.extractall(extract_dir)

            # Find the actual source directory (usually one level deep)
            extracted_items = list(extract_dir.iterdir())
            if len(extracted_items) == 1 and extracted_items[0].is_dir():
                return extracted_items[0]
            else:
                return extract_dir

        except Exception as e:
            logger.exception(f"Failed to fetch source from {url}")
            raise RuntimeError(f"Failed to fetch source: {e}")

    def _detect_source_location(self, package_name: str, version: str | None) -> Path:
        """Detect source location from package name."""
        # Try common patterns
        common_urls = {
            "python": f"https://www.python.org/ftp/python/{version or '3.12.0'}/Python-{version or '3.12.0'}.tgz",
            "nginx": "https://nginx.org/download/nginx-1.24.0.tar.gz",
            "redis": f"https://download.redis.io/releases/redis-{version or '7.0'}.tar.gz",
        }

        if package_name.lower() in common_urls:
            return self._fetch_from_url(common_urls[package_name.lower()], package_name, version)

        raise ValueError(
            f"Could not detect source location for {package_name}. "
            "Please provide --source-url or configure source location."
        )

    def detect_build_system(self, source_dir: Path) -> str:
        """
        Detect the build system used in source directory.

        Args:
            source_dir: Path to source code

        Returns:
            Build system type (autotools, cmake, make, python, custom)
        """
        # Check for configure script (autotools)
        if (source_dir / "configure").exists() or (source_dir / "configure.ac").exists():
            return "autotools"

        # Check for CMakeLists.txt
        if (source_dir / "CMakeLists.txt").exists():
            return "cmake"

        # Check for Makefile
        if (source_dir / "Makefile").exists():
            return "make"

        # Check for Python setup.py or pyproject.toml
        if (source_dir / "setup.py").exists() or (source_dir / "pyproject.toml").exists():
            return "python"

        # Default to autotools (most common)
        return "autotools"

    def configure_build(self, source_dir: Path, config: BuildConfig) -> list[str]:
        """Configure the build.

        Args:
            source_dir: Path to source code directory.
            config: Build configuration with options and settings.

        Returns:
            List of configure commands to execute.
        """
        commands = []

        if config.build_system == "autotools":
            configure_cmd = "./configure"
            if config.configure_args:
                configure_cmd += " " + " ".join(config.configure_args)
            else:
                # Default configure options
                configure_cmd += f" --prefix={config.install_prefix}"
                configure_cmd += " --enable-optimizations"
            commands.append(configure_cmd)

        elif config.build_system == "cmake":
            build_dir = source_dir / "build"
            build_dir.mkdir(exist_ok=True)
            cmake_cmd = "cmake"
            if config.configure_args:
                cmake_cmd += " " + " ".join(config.configure_args)
            else:
                cmake_cmd += f" -DCMAKE_INSTALL_PREFIX={config.install_prefix}"
            cmake_cmd += " .."
            commands.append(f"cd {build_dir} && {cmake_cmd}")

        elif config.build_system == "python":
            # Python packages usually don't need explicit configure
            pass

        return commands

    def build(self, source_dir: Path, config: BuildConfig) -> list[str]:
        """Build the package.

        Args:
            source_dir: Path to source code directory.
            config: Build configuration with options and settings.

        Returns:
            List of build commands to execute.
        """
        commands = []

        if config.build_system == "autotools" or config.build_system == "make":
            make_cmd = "make"
            if config.make_args:
                make_cmd += " " + " ".join(config.make_args)
            else:
                # Use parallel builds by default
                import multiprocessing

                jobs = multiprocessing.cpu_count()
                make_cmd += f" -j{jobs}"
            commands.append(make_cmd)

        elif config.build_system == "cmake":
            build_dir = source_dir / "build"
            make_cmd = "make"
            if config.make_args:
                make_cmd += " " + " ".join(config.make_args)
            else:
                import multiprocessing

                jobs = multiprocessing.cpu_count()
                make_cmd += f" -j{jobs}"
            commands.append(f"cd {build_dir} && {make_cmd}")

        elif config.build_system == "python":
            commands.append("python3 setup.py build")

        return commands

    def install_build(self, source_dir: Path, config: BuildConfig) -> list[str]:
        """Generate install commands for built package.

        Args:
            source_dir: Path to source code directory.
            config: Build configuration with options and settings.

        Returns:
            List of install commands to execute (requires sudo).
        """
        commands = []

        if config.build_system == "autotools" or config.build_system == "make":
            commands.append("sudo make install")

        elif config.build_system == "cmake":
            build_dir = source_dir / "build"
            commands.append(f"cd {build_dir} && sudo make install")

        elif config.build_system == "python":
            commands.append("sudo python3 setup.py install")

        return commands

    def build_from_source(
        self,
        package_name: str,
        version: str | None = None,
        source_url: str | None = None,
        build_system: str | None = None,
        configure_args: list[str] | None = None,
        make_args: list[str] | None = None,
        install_prefix: str = "/usr/local",
        use_cache: bool = True,
    ) -> BuildResult:
        """Build and install a package from source.

        Args:
            package_name: Name of the package to build.
            version: Version to build (optional, can be specified as package@version).
            source_url: URL to source code (optional, will auto-detect if not provided).
            build_system: Build system type (auto-detected if None).
            configure_args: Additional configure arguments for autotools/cmake.
            make_args: Additional make arguments for compilation.
            install_prefix: Installation prefix (default: /usr/local).
            use_cache: Whether to use build cache for faster rebuilds.

        Returns:
            BuildResult with build information, success status, and install commands.

        Raises:
            RuntimeError: If source download, configuration, or build fails.
        """
        try:
            # Check cache
            cache_key = None
            if use_cache and source_url:
                cache_key = self._get_cache_key(package_name, version, source_url)
                cached_path = self._check_cache(cache_key)
                if cached_path:
                    cx_print(f"📦 Using cached build for {package_name}", "info")
                    metadata_path = cached_path / "metadata.json"
                    if metadata_path.exists():
                        with open(metadata_path) as f:
                            metadata = json.load(f)
                            return BuildResult(
                                success=True,
                                package_name=package_name,
                                version=version,
                                build_dir=str(cached_path),
                                install_commands=metadata.get("install_commands", []),
                                cached=True,
                            )

            # Fetch source
            source_dir = self.fetch_source(package_name, source_url, version)

            # Detect build system if not provided
            if not build_system:
                build_system = self.detect_build_system(source_dir)

            # Create build config
            config = BuildConfig(
                package_name=package_name,
                version=version,
                source_url=source_url,
                build_system=build_system,
                configure_args=configure_args,
                make_args=make_args,
                install_prefix=install_prefix,
                cache_key=cache_key,
            )

            # Detect and install build dependencies
            cx_print(f"🔍 Checking build dependencies...", "info")
            missing_deps = self.detect_build_dependencies(package_name, build_system)

            if missing_deps:
                cx_print(f"   Installing: {', '.join(missing_deps)}", "info")
                install_cmd = f"sudo apt-get install -y {' '.join(missing_deps)}"
                result = run_command(install_cmd, timeout=600)
                if not result.success:
                    return BuildResult(
                        success=False,
                        package_name=package_name,
                        version=version,
                        build_dir=str(source_dir),
                        install_commands=[],
                        error_message=f"Failed to install build dependencies: {result.stderr}",
                    )
            else:
                cx_print(f"   ✓ All build dependencies satisfied", "success")

            # Configure
            cx_print(f"⚙️  Configuring build...", "info")
            configure_commands = self.configure_build(source_dir, config)
            for cmd in configure_commands:
                result = run_command(cmd, cwd=str(source_dir), timeout=300)
                if not result.success:
                    return BuildResult(
                        success=False,
                        package_name=package_name,
                        version=version,
                        build_dir=str(source_dir),
                        install_commands=[],
                        error_message=f"Configure failed: {result.stderr}",
                    )

            # Build
            cx_print(f"🔨 Compiling (this may take a while)...", "info")
            build_commands = self.build(source_dir, config)
            for cmd in build_commands:
                result = run_command(cmd, cwd=str(source_dir), timeout=3600)  # 1 hour timeout
                if not result.success:
                    return BuildResult(
                        success=False,
                        package_name=package_name,
                        version=version,
                        build_dir=str(source_dir),
                        install_commands=[],
                        error_message=f"Build failed: {result.stderr}",
                    )

            # Generate install commands
            install_commands = self.install_build(source_dir, config)

            # Save to cache
            if use_cache and cache_key:
                self._save_to_cache(cache_key, source_dir, install_commands)

            return BuildResult(
                success=True,
                package_name=package_name,
                version=version,
                build_dir=str(source_dir),
                install_commands=install_commands,
            )

        except Exception as e:
            logger.exception(f"Build failed for {package_name}")
            return BuildResult(
                success=False,
                package_name=package_name,
                version=version,
                build_dir="",
                install_commands=[],
                error_message=str(e),
            )

