"""
System Health Check for Cortex Linux
Performs diagnostic checks and provides fix suggestions.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.status import Status
from rich.table import Table

from cortex.branding import console, cx_header
from cortex.validators import validate_api_key


class SystemDoctor:
    """
    Performs comprehensive system health checks and diagnostics.

    Checks for:
    - Python version compatibility
    - Required Python dependencies
    - GPU drivers (NVIDIA/AMD)
    - CUDA/ROCm availability
    - Ollama installation and status
    - API key configuration
    - Disk space availability
    - System memory

    Attributes:
        warnings: List of non-critical issues found
        failures: List of critical issues that may prevent operation
        suggestions: List of fix commands for issues
        passes: List of successful checks
    """

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.failures: list[str] = []
        self.suggestions: list[str] = []
        self.passes: list[str] = []

    def run_checks(self) -> int:
        """
        Run all health checks and return appropriate exit code.

        Exit codes:
            0: All checks passed, system is healthy
            1: Warnings found, system can operate but has recommendations
            2: Critical failures found, system may not work properly

        Returns:
        int: Exit code reflecting system health status (0, 1, or 2)
        """
        # Show banner once
        # show_banner()
        console.print()

        # Option 2: Stylized CX header with SYSTEM HEALTH CHECK
        console.print("[bold cyan]   ██████╗██╗  ██╗    SYSTEM HEALTH CHECK[/bold cyan]")
        console.print("[bold cyan]  ██╔════╝╚██╗██╔╝   ─────────────────────[/bold cyan]")
        console.print("[bold cyan]  ██║      ╚███╔╝          Running...[/bold cyan]")
        console.print("[bold cyan]  ██║      ██╔██╗ [/bold cyan]")
        console.print("[bold cyan]  ╚██████╗██╔╝ ██╗[/bold cyan]")
        console.print("[bold cyan]   ╚═════╝╚═╝  ╚═╝[/bold cyan]")
        console.print()

        # Run checks with spinner
        with console.status("[bold cyan][CX] Scanning system...[/bold cyan]", spinner="dots"):
            # System Info (includes API provider and security features)
            self._print_section("System Configuration")
            self._check_api_keys()
            self._check_security_tools()

            # Python & Dependencies
            self._print_section("Python & Dependencies")
            self._check_python()
            self._check_dependencies()

            self._print_section("GPU & Acceleration")
            self._check_gpu_driver()
            self._check_cuda()

            self._print_section("AI & Services")
            self._check_ollama()

            # System Resources
            self._print_section("System Resources")
            self._check_disk_space()
            self._check_memory()

        self._print_summary()

        if self.failures:
            return 2  # Critical failures
        elif self.warnings:
            return 1  # Warnings only
        return 0  # All good

    def _print_section(self, title: str) -> None:
        """Print a section header using CX branding."""
        cx_header(title)

    def _print_check(
        self,
        status: str,
        message: str,
        suggestion: str | None = None,
    ) -> None:
        """
        Print a check result with appropriate formatting and colors.

        Args:
            status: One of "PASS", "WARN", "FAIL", or "INFO"
            message: Description of the check result
            suggestion: Optional fix command or suggestion
        """
        # Define symbols and colors
        if status == "PASS":
            symbol = "✓"
            color = "bold green"
            prefix = "[PASS]"
            self.passes.append(message)
        elif status == "WARN":
            symbol = "⚠"
            color = "bold yellow"
            prefix = "[WARN]"
            self.warnings.append(message)
            if suggestion:
                self.suggestions.append(suggestion)
        elif status == "FAIL":
            symbol = "✗"
            color = "bold red"
            prefix = "[FAIL]"
            self.failures.append(message)
            if suggestion:
                self.suggestions.append(suggestion)
        else:
            symbol = "?"
            color = "dim"
            prefix = "[INFO]"

        # Print with icon prefix and coloring
        console.print(f" [cyan]CX[/cyan]  [{color}]{symbol} {prefix}[/{color}] {message}")

    def _check_python(self) -> None:
        """Check Python version compatibility."""
        version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        if sys.version_info >= (3, 10):  # noqa: UP036
            self._print_check("PASS", f"Python {version}")
        else:
            self._print_check(
                "FAIL",
                f"Python {version} (3.10+ required)",
                "Install Python 3.10+: sudo apt install python3.11",
            )

    def _check_dependencies(self) -> None:
        """Check packages from requirements.txt."""
        missing: list[str] = []
        requirements_path = Path("requirements.txt")

        if not requirements_path.exists():
            self._print_check("WARN", "No requirements.txt found")
            return

        # Map requirement names to importable module names
        name_overrides = {
            "pyyaml": "yaml",
            "typing-extensions": "typing_extensions",
            "python-dotenv": "dotenv",
        }

        try:
            with open(requirements_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        raw_name = line.split("==")[0].split(">")[0].split("<")[0].strip()
                        pkg_name = name_overrides.get(
                            raw_name.lower(), raw_name.lower().replace("-", "_")
                        )
                        try:
                            __import__(pkg_name)
                        except ImportError:
                            missing.append(raw_name)
        except Exception:
            self._print_check("WARN", "Could not read requirements.txt")
            return

        if not missing:
            self._print_check("PASS", "All requirements.txt packages installed")
        elif len(missing) < 3:
            self._print_check(
                "WARN",
                f"Missing from requirements.txt: {', '.join(missing)}",
                "Install dependencies: pip install -r requirements.txt",
            )
        else:
            self._print_check(
                "FAIL",
                f"Missing {len(missing)} packages from requirements.txt: {', '.join(missing[:3])}...",
                "Install dependencies: pip install -r requirements.txt",
            )

    def _check_gpu_driver(self) -> None:
        """Check for GPU drivers (NVIDIA or AMD ROCm)."""
        # Check NVIDIA
        if shutil.which("nvidia-smi"):
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    version = result.stdout.strip().split("\n")[0]
                    self._print_check("PASS", f"NVIDIA Driver {version}")
                    return
            except (subprocess.TimeoutExpired, Exception):
                pass

        # Check AMD ROCm
        if shutil.which("rocm-smi"):
            try:
                result = subprocess.run(
                    ["rocm-smi", "--showdriverversion"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    self._print_check("PASS", "AMD ROCm driver detected")
                    return
            except (subprocess.TimeoutExpired, Exception):
                pass

        # No GPU found - this is a warning, not a failure
        self._print_check(
            "WARN",
            "No GPU detected (CPU-only mode supported, local inference will be slower)",
            "Optional: Install NVIDIA/AMD drivers for acceleration",
        )

    def _check_cuda(self) -> None:
        """Check CUDA/ROCm availability for GPU acceleration."""
        # Check CUDA
        if shutil.which("nvcc"):
            try:
                result = subprocess.run(
                    ["nvcc", "--version"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and "release" in result.stdout:
                    version_line = result.stdout.split("release")[1].split(",")[0].strip()
                    self._print_check("PASS", f"CUDA {version_line}")
                    return
            except (subprocess.TimeoutExpired, Exception):
                pass

        # Check ROCm
        rocm_info_path = Path("/opt/rocm/.info/version")
        if rocm_info_path.exists():
            try:
                version = rocm_info_path.read_text(encoding="utf-8").strip()
                self._print_check("PASS", f"ROCm {version}")
                return
            except (OSError, UnicodeDecodeError):
                self._print_check("PASS", "ROCm installed")
                return
        elif Path("/opt/rocm").exists():
            self._print_check("PASS", "ROCm installed")
            return

        # Check if PyTorch has CUDA available (software level)
        try:
            import torch

            if torch.cuda.is_available():
                self._print_check("PASS", "CUDA available (PyTorch)")
                return
        except ImportError:
            pass

        self._print_check(
            "WARN",
            "CUDA/ROCm not found (GPU acceleration unavailable)",
            "Install CUDA: https://developer.nvidia.com/cuda-downloads",
        )

    def _check_ollama(self) -> None:
        """Check if Ollama is installed and running."""
        # Check if installed
        if not shutil.which("ollama"):
            self._print_check(
                "WARN",
                "Ollama not installed",
                "Install Ollama: curl https://ollama.ai/install.sh | sh",
            )
            return

        # Check if running by testing the API
        try:
            import requests

            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                self._print_check("PASS", "Ollama installed and running")
                return
        except Exception:
            pass

        # Ollama installed but not running
        self._print_check(
            "WARN", "Ollama installed but not running", "Start Ollama: ollama serve &"
        )

    def _check_api_keys(self) -> None:
        """Check if API keys are configured for cloud models."""
        is_valid, provider, error = validate_api_key()

        if is_valid:
            self._print_check("PASS", f"{provider} API key configured")
        else:
            # Check for Ollama
            ollama_provider = os.environ.get("CORTEX_PROVIDER", "").lower()
            if ollama_provider == "ollama":
                self._print_check("PASS", "API Provider: Ollama (local)")
            else:
                self._print_check(
                    "WARN",
                    "No API keys configured (required for cloud models)",
                    "Configure API key: export ANTHROPIC_API_KEY=sk-... or run 'cortex wizard'",
                )

    def _check_security_tools(self) -> None:
        """Check security features like Firejail availability."""
        firejail_path = shutil.which("firejail")
        if firejail_path:
            self._print_check("PASS", f"Firejail available at {firejail_path}")
        else:
            self._print_check(
                "WARN",
                "Firejail not installed (sandboxing unavailable)",
                "Install: sudo apt-get install firejail",
            )

    def _check_disk_space(self) -> None:
        """Check available disk space for model storage."""
        try:
            usage = shutil.disk_usage(os.path.expanduser("~"))
            free_gb = usage.free / (1024**3)
            total_gb = usage.total / (1024**3)

            if free_gb > 20:
                self._print_check(
                    "PASS", f"{free_gb:.1f}GB free disk space ({total_gb:.1f}GB total)"
                )
            elif free_gb > 10:
                self._print_check(
                    "WARN",
                    f"{free_gb:.1f}GB free (20GB+ recommended for models)",
                    "Free up disk space: sudo apt clean && docker system prune -a",
                )
            else:
                self._print_check(
                    "FAIL",
                    f"Only {free_gb:.1f}GB free (critically low)",
                    "Free up disk space: sudo apt autoremove && sudo apt clean",
                )
        except (OSError, Exception) as e:
            self._print_check("WARN", f"Could not check disk space: {type(e).__name__}")

    def _check_memory(self) -> None:
        """Check system RAM availability."""
        mem_gb = self._get_system_memory()

        if mem_gb is None:
            self._print_check("WARN", "Could not detect system RAM")
            return

        if mem_gb >= 16:
            self._print_check("PASS", f"{mem_gb:.1f}GB RAM")
        elif mem_gb >= 8:
            self._print_check(
                "WARN",
                f"{mem_gb:.1f}GB RAM (16GB recommended for larger models)",
                "Consider upgrading RAM or use smaller models",
            )
        else:
            self._print_check(
                "FAIL",
                f"Only {mem_gb:.1f}GB RAM (8GB minimum required)",
                "Upgrade RAM to at least 8GB",
            )

    def _get_system_memory(self) -> float | None:
        """
        Get system memory in GB.

        Returns:
            float: Total system memory in GB, or None if detection fails
        """
        # Try /proc/meminfo (Linux)
        try:
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_kb = int(line.split()[1])
                        return mem_kb / (1024**2)
        except (OSError, ValueError, IndexError):
            pass

        # Try psutil (macOS/BSD/Windows)
        try:
            import psutil

            return psutil.virtual_memory().total / (1024**3)
        except ImportError:
            pass

        return None

    def _print_summary(self) -> None:
        """Print summary table and overall health status with suggestions."""
        console.print()

        # Create summary table
        table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")

        if self.passes:
            table.add_row("[green]✓ Passed[/green]", f"[green]{len(self.passes)}[/green]")
        if self.warnings:
            table.add_row("[yellow]⚠ Warnings[/yellow]", f"[yellow]{len(self.warnings)}[/yellow]")
        if self.failures:
            table.add_row("[red]✗ Failures[/red]", f"[red]{len(self.failures)}[/red]")

        console.print(table)
        console.print()

        # Overall status panel
        if self.failures:
            console.print(
                Panel(
                    f"[bold red]❌ {len(self.failures)} critical failure(s) found[/bold red]",
                    border_style="red",
                    padding=(0, 2),
                )
            )
        elif self.warnings:
            console.print(
                Panel(
                    f"[bold yellow]⚠️  {len(self.warnings)} warning(s) found[/bold yellow]",
                    border_style="yellow",
                    padding=(0, 2),
                )
            )
        else:
            console.print(
                Panel(
                    "[bold green]✅ All checks passed! System is healthy.[/bold green]",
                    border_style="green",
                    padding=(0, 2),
                )
            )

        # Show fix suggestions if any
        if self.suggestions:
            console.print()
            console.print("[bold cyan]💡 Suggested fixes:[/bold cyan]")
            for i, suggestion in enumerate(self.suggestions, 1):
                console.print(f"   [dim]{i}.[/dim] {suggestion}")
            console.print()


def run_doctor() -> int:
    """
    Run the system doctor and return exit code.

    Returns:
        int: Exit code (0 = all good, 1 = warnings, 2 = failures)
    """
    doctor = SystemDoctor()
    return doctor.run_checks()


if __name__ == "__main__":
    sys.exit(run_doctor())
