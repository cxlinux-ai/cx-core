#!/usr/bin/env python3
"""
Batch Operations & Parallel Execution Module

Handles installation of multiple packages with:
- Parallel downloads and installations
- Dependency graph optimization
- Progress tracking
- Error handling and rollback
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from cortex.coordinator import InstallationCoordinator, InstallationResult, StepStatus
from cortex.dependency_resolver import DependencyGraph, DependencyResolver

logger = logging.getLogger(__name__)


class PackageStatus(Enum):
    """Status of a package in batch installation"""

    PENDING = "pending"
    ANALYZING = "analyzing"
    RESOLVING = "resolving"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PackageInstallation:
    """Represents a single package installation in a batch"""

    name: str
    status: PackageStatus = PackageStatus.PENDING
    dependency_graph: DependencyGraph | None = None
    commands: list[str] = field(default_factory=list)
    result: InstallationResult | None = None
    start_time: float | None = None
    end_time: float | None = None
    error_message: str | None = None
    rollback_commands: list[str] = field(default_factory=list)

    def duration(self) -> float | None:
        """Get installation duration in seconds"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


@dataclass
class BatchInstallationResult:
    """Result of a batch installation operation"""

    packages: list[PackageInstallation]
    total_duration: float
    successful: list[str]
    failed: list[str]
    skipped: list[str]
    total_dependencies: int
    optimized_dependencies: int
    time_saved: float | None = None  # vs sequential execution

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        total = len(self.packages)
        if total == 0:
            return 0.0
        return (len(self.successful) / total) * 100


class BatchInstaller:
    """Handles batch installation of multiple packages with parallel execution"""

    def __init__(
        self,
        max_workers: int = 4,
        progress_callback: Callable[[int, int, PackageInstallation], None] | None = None,
        enable_rollback: bool = True,
    ):
        """
        Initialize batch installer.

        Args:
            max_workers: Maximum number of parallel workers for downloads/installations
            progress_callback: Optional callback for progress updates
            enable_rollback: Whether to enable rollback on failures
        """
        self.max_workers = max_workers
        self.progress_callback = progress_callback
        self.enable_rollback = enable_rollback
        self.dependency_resolver = DependencyResolver()
        self._install_lock = threading.Lock()

    def analyze_packages(self, package_names: list[str]) -> dict[str, PackageInstallation]:
        """
        Analyze all packages and resolve their dependencies.

        Args:
            package_names: List of package names to analyze

        Returns:
            Dictionary mapping package names to PackageInstallation objects
        """
        logger.info(f"Analyzing {len(package_names)} packages...")
        packages: dict[str, PackageInstallation] = {}

        # Resolve dependencies for all packages
        for name in package_names:
            packages[name] = PackageInstallation(name=name, status=PackageStatus.ANALYZING)
            if self.progress_callback:
                self.progress_callback(0, len(package_names), packages[name])

        # Resolve dependencies (can be done in parallel)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_package = {
                executor.submit(self.dependency_resolver.resolve_dependencies, name): name
                for name in package_names
            }

            for future in as_completed(future_to_package):
                package_name = future_to_package[future]
                try:
                    graph = future.result()
                    packages[package_name].dependency_graph = graph
                    packages[package_name].status = PackageStatus.RESOLVING
                except Exception as e:
                    logger.error(f"Failed to resolve dependencies for {package_name}: {e}")
                    packages[package_name].status = PackageStatus.FAILED
                    packages[package_name].error_message = str(e)

        return packages

    def optimize_dependency_graph(
        self, packages: dict[str, PackageInstallation]
    ) -> dict[str, list[str]]:
        """
        Optimize dependency resolution across multiple packages.

        Merges dependency graphs, removes duplicates, and calculates optimal installation order.

        Args:
            packages: Dictionary of packages to optimize

        Returns:
            Dictionary mapping package names to optimized command lists
        """
        logger.info("Optimizing dependency graph...")

        # Collect all unique dependencies that need to be installed
        all_missing_deps: set[str] = set()
        package_deps: dict[str, list[str]] = {}

        for name, pkg in packages.items():
            if pkg.dependency_graph:
                missing_deps = []
                # Get installation order from dependency graph
                for dep_name in pkg.dependency_graph.installation_order:
                    if not self.dependency_resolver.is_package_installed(dep_name):
                        all_missing_deps.add(dep_name)
                        missing_deps.append(dep_name)
                package_deps[name] = missing_deps

        # Create unified installation order: shared deps first, then package-specific deps + package
        optimized_commands: dict[str, list[str]] = {}
        update_added = False

        # First, install shared dependencies (dependencies needed by multiple packages)
        shared_deps = []
        dep_counts: dict[str, int] = {}
        for deps in package_deps.values():
            for dep in deps:
                dep_counts[dep] = dep_counts.get(dep, 0) + 1

        # Dependencies needed by 2+ packages are "shared"
        for dep, count in dep_counts.items():
            if count > 1:
                shared_deps.append(dep)

        # Install shared dependencies first
        if shared_deps:
            commands = []
            if not update_added:
                commands.append("sudo apt-get update")
                update_added = True
            # Install all shared deps in one command for efficiency
            shared_deps_str = " ".join(shared_deps)
            commands.append(f"sudo apt-get install -y {shared_deps_str}")
            optimized_commands["_shared_deps"] = commands

        # Then install each package with its remaining dependencies
        for package_name, deps in package_deps.items():
            # Filter out already-installed shared deps
            remaining_deps = [d for d in deps if d not in shared_deps]
            commands = []

            if remaining_deps:
                # Install remaining dependencies
                for dep in remaining_deps:
                    if not self.dependency_resolver.is_package_installed(dep):
                        if not update_added:
                            commands.append("sudo apt-get update")
                            update_added = True
                        commands.append(f"sudo apt-get install -y {dep}")

            # Install the main package itself
            if not self.dependency_resolver.is_package_installed(package_name):
                if not update_added:
                    commands.append("sudo apt-get update")
                    update_added = True
                commands.append(f"sudo apt-get install -y {package_name}")

            if commands:
                optimized_commands[package_name] = commands

        return optimized_commands

    def _topological_sort(
        self, package_dependencies: dict[str, set[str]], all_dependencies: set[str]
    ) -> list[str]:
        """
        Perform topological sort to determine installation order.

        Args:
            package_dependencies: Map of package to its dependencies
            all_dependencies: Set of all dependency names

        Returns:
            List of package names in installation order
        """
        # Simple topological sort implementation
        # Dependencies come first, then packages
        result = []
        visited = set()

        # Add all dependencies first (they have no dependencies themselves in this context)
        for dep in all_dependencies:
            if dep not in visited:
                result.append(dep)
                visited.add(dep)

        # Add packages
        for package_name in package_dependencies.keys():
            if package_name not in visited:
                result.append(package_name)
                visited.add(package_name)

        return result

    def install_batch(
        self,
        package_names: list[str],
        execute: bool = False,
        dry_run: bool = False,
    ) -> BatchInstallationResult:
        """
        Install multiple packages in batch with parallel execution.

        Args:
            package_names: List of package names to install
            execute: Whether to actually execute commands
            dry_run: If True, only show what would be executed

        Returns:
            BatchInstallationResult with installation results
        """
        start_time = time.time()
        logger.info(f"Starting batch installation of {len(package_names)} packages")

        # Step 1: Analyze packages and resolve dependencies
        packages = self.analyze_packages(package_names)

        # Step 2: Optimize dependency graph
        optimized_commands = self.optimize_dependency_graph(packages)

        # Calculate statistics
        total_deps = sum(
            len(pkg.dependency_graph.all_dependencies) if pkg.dependency_graph else 0
            for pkg in packages.values()
        )
        # Count unique dependencies across all packages
        all_unique_deps = set()
        for pkg in packages.values():
            if pkg.dependency_graph:
                for dep in pkg.dependency_graph.all_dependencies:
                    all_unique_deps.add(dep.name)
        optimized_deps = len(all_unique_deps)

        # Step 3: Execute installations
        if dry_run:
            logger.info("Dry run mode - commands not executed")
            for name, pkg in packages.items():
                # Combine shared deps and package-specific commands
                pkg.commands = []
                if "_shared_deps" in optimized_commands:
                    pkg.commands.extend(optimized_commands["_shared_deps"])
                pkg.commands.extend(optimized_commands.get(name, []))
                pkg.status = PackageStatus.SKIPPED
        elif execute:
            # Execute in parallel where possible
            self._execute_installations(packages, optimized_commands)
        else:
            # Just prepare commands
            for name, pkg in packages.items():
                # Combine shared deps and package-specific commands
                pkg.commands = []
                if "_shared_deps" in optimized_commands:
                    pkg.commands.extend(optimized_commands["_shared_deps"])
                pkg.commands.extend(optimized_commands.get(name, []))

        # Calculate results
        total_duration = time.time() - start_time
        successful = [name for name, pkg in packages.items() if pkg.status == PackageStatus.SUCCESS]
        failed = [name for name, pkg in packages.items() if pkg.status == PackageStatus.FAILED]
        skipped = [name for name, pkg in packages.items() if pkg.status == PackageStatus.SKIPPED]

        # Estimate sequential time (sum of individual package durations)
        sequential_time = sum(pkg.duration() if pkg.duration() else 0 for pkg in packages.values())
        time_saved = sequential_time - total_duration if sequential_time > total_duration else None

        result = BatchInstallationResult(
            packages=list(packages.values()),
            total_duration=total_duration,
            successful=successful,
            failed=failed,
            skipped=skipped,
            total_dependencies=total_deps,
            optimized_dependencies=optimized_deps,
            time_saved=time_saved,
        )

        logger.info(
            f"Batch installation completed: {len(successful)} successful, "
            f"{len(failed)} failed, {len(skipped)} skipped"
        )

        return result

    def _execute_installations(
        self,
        packages: dict[str, PackageInstallation],
        optimized_commands: dict[str, list[str]],
    ):
        """Execute installations with parallel execution where possible."""
        logger.info(f"Executing installations with {self.max_workers} workers...")

        # First, install shared dependencies if any
        shared_deps_installed = False
        if "_shared_deps" in optimized_commands:
            logger.info("Installing shared dependencies...")
            shared_commands = optimized_commands["_shared_deps"]
            try:
                coordinator = InstallationCoordinator(
                    commands=shared_commands,
                    descriptions=[
                        f"Shared dependencies - step {i+1}" for i in range(len(shared_commands))
                    ],
                    timeout=300,
                    stop_on_error=True,
                )
                result = coordinator.execute()
                if result.success:
                    shared_deps_installed = True
                    logger.info("✅ Shared dependencies installed")
                else:
                    logger.error("❌ Shared dependencies failed")
            except Exception as e:
                logger.error(f"Error installing shared dependencies: {e}")

        def install_package(package_name: str) -> tuple[str, bool, str | None]:
            """Install a single package and return (name, success, error)"""
            pkg = packages[package_name]
            pkg.start_time = time.time()
            pkg.status = PackageStatus.INSTALLING

            # Combine shared deps (already installed) and package-specific commands
            commands = []
            if "_shared_deps" in optimized_commands and not shared_deps_installed:
                # If shared deps failed, include them in each package's commands
                commands.extend(optimized_commands["_shared_deps"])
            commands.extend(optimized_commands.get(package_name, []))
            pkg.commands = commands

            if not commands:
                pkg.status = PackageStatus.SKIPPED
                pkg.end_time = time.time()
                return (package_name, True, None)

            try:
                # Use a lock to ensure only one apt-get process runs at a time
                # but allows parallel analysis and UI updates
                with self._install_lock:
                    coordinator = InstallationCoordinator(
                        commands=commands,
                        descriptions=[
                            f"Installing {package_name} - step {i+1}" for i in range(len(commands))
                        ],
                        timeout=300,
                        stop_on_error=True,
                        enable_rollback=self.enable_rollback,
                    )

                    result = coordinator.execute()
                
                pkg.result = result
                pkg.end_time = time.time()

                if result.success:
                    pkg.status = PackageStatus.SUCCESS
                    return (package_name, True, None)
                else:
                    pkg.status = PackageStatus.FAILED
                    error_msg = result.error_message or "Installation failed"
                    pkg.error_message = error_msg
                    return (package_name, False, error_msg)

            except Exception as e:
                pkg.status = PackageStatus.FAILED
                pkg.error_message = str(e)
                pkg.end_time = time.time()
                return (package_name, False, str(e))

        # Execute installations in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all installation tasks
            future_to_package = {
                executor.submit(install_package, name): name for name in packages.keys()
            }

            # Process completed tasks and update progress
            completed = 0
            total = len(packages)

            for future in as_completed(future_to_package):
                package_name = future_to_package[future]
                completed += 1

                try:
                    name, success, error = future.result()
                    pkg = packages[name]

                    if self.progress_callback:
                        self.progress_callback(completed, total, pkg)

                    if success:
                        logger.info(f"✅ {name} installed successfully")
                    else:
                        logger.error(f"❌ {name} failed: {error}")

                except Exception as e:
                    logger.error(f"Error installing {package_name}: {e}")
                    packages[package_name].status = PackageStatus.FAILED
                    packages[package_name].error_message = str(e)

    def rollback_batch(self, result: BatchInstallationResult) -> bool:
        """
        Rollback a batch installation.

        Args:
            result: BatchInstallationResult from a previous installation

        Returns:
            True if rollback was successful
        """
        if not self.enable_rollback:
            logger.warning("Rollback is disabled")
            return False

        logger.info("Starting batch rollback...")
        success_count = 0

        # Rollback in reverse order
        for pkg in reversed(result.packages):
            if pkg.status == PackageStatus.SUCCESS and pkg.rollback_commands:
                try:
                    for cmd in reversed(pkg.rollback_commands):
                        logger.info(f"Rolling back {pkg.name}: {cmd}")
                        # Execute rollback command
                        import subprocess

                        subprocess.run(cmd, shell=True, capture_output=True, timeout=60)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Rollback failed for {pkg.name}: {e}")

        logger.info(f"Rollback completed: {success_count}/{len(result.successful)} packages")
        return success_count == len(result.successful)
