"""
Cortex Benchmark Module

Quick system benchmark for AI performance scoring.
Runs GPU, inference, and token generation tests.

Issue: #246
"""

import json
import os
import platform
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from cortex.branding import CORTEX_CYAN, console, cx_header, cx_print

# Model recommendations based on system capabilities
MODEL_REQUIREMENTS = {
    # Model: (min_ram_gb, min_vram_mb, min_score)
    "tinyllama": (4, 0, 20),
    "phi-2": (8, 0, 40),
    "qwen2.5-1.5b": (8, 0, 45),
    "gemma-2b": (8, 2048, 50),
    "llama2-7b": (16, 4096, 60),
    "mistral-7b": (16, 4096, 65),
    "llama2-13b": (32, 8192, 75),
    "mixtral-8x7b": (48, 16384, 85),
    "llama2-70b": (128, 40960, 95),
}


@dataclass
class BenchmarkResult:
    """Individual benchmark test result."""

    name: str
    score: int  # 0-100
    raw_value: float
    unit: str
    description: str = ""


@dataclass
class BenchmarkReport:
    """Complete benchmark report."""

    timestamp: str = ""
    system_info: dict = field(default_factory=dict)
    results: list[BenchmarkResult] = field(default_factory=list)
    overall_score: int = 0
    rating: str = ""
    can_run: list[str] = field(default_factory=list)
    needs_upgrade: list[str] = field(default_factory=list)
    upgrade_suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "system_info": self.system_info,
            "results": [asdict(r) for r in self.results],
            "overall_score": self.overall_score,
            "rating": self.rating,
            "can_run": self.can_run,
            "needs_upgrade": self.needs_upgrade,
            "upgrade_suggestion": self.upgrade_suggestion,
        }


class CortexBenchmark:
    """
    System benchmark for AI performance scoring.

    Runs quick tests to evaluate:
    - CPU performance (matrix operations)
    - Memory bandwidth
    - GPU availability and performance (if available)
    - Token generation simulation

    Produces a 0-100 score with model recommendations.
    """

    HISTORY_FILE = Path.home() / ".cortex" / "benchmark_history.json"

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._results: list[BenchmarkResult] = []

    def _get_system_info(self) -> dict:
        """Gather basic system information."""
        info = {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor() or "Unknown",
            "python_version": platform.python_version(),
        }

        # Try to get CPU info
        try:
            if platform.system() == "Linux":
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line:
                            info["cpu_model"] = line.split(":")[1].strip()
                            break
            elif platform.system() == "Darwin":
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    info["cpu_model"] = result.stdout.strip()
        except Exception:
            pass

        # CPU cores
        info["cpu_cores"] = os.cpu_count() or 1

        # Memory
        try:
            if platform.system() == "Linux":
                with open("/proc/meminfo") as f:
                    for line in f:
                        if "MemTotal" in line:
                            mem_kb = int(line.split()[1])
                            info["ram_gb"] = round(mem_kb / 1024 / 1024, 1)
                            break
            elif platform.system() == "Darwin":
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    mem_bytes = int(result.stdout.strip())
                    info["ram_gb"] = round(mem_bytes / 1024 / 1024 / 1024, 1)
        except Exception:
            info["ram_gb"] = 0

        # GPU detection
        info["has_nvidia_gpu"] = self._detect_nvidia_gpu()
        info["nvidia_vram_mb"] = self._get_nvidia_vram()
        info["has_apple_silicon"] = self._is_apple_silicon()

        return info

    def _detect_nvidia_gpu(self) -> bool:
        """Check if NVIDIA GPU is available."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0 and result.stdout.strip() != ""
        except Exception:
            return False

    def _get_nvidia_vram(self) -> int:
        """Get NVIDIA GPU VRAM in MB."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return int(result.stdout.strip().split("\n")[0])
        except Exception:
            pass
        return 0

    def _is_apple_silicon(self) -> bool:
        """Check if running on Apple Silicon."""
        return platform.system() == "Darwin" and platform.machine() == "arm64"

    def _benchmark_cpu(self) -> BenchmarkResult:
        """
        Benchmark CPU with matrix operations.
        Uses pure Python for portability.
        """
        size = 500
        iterations = 3

        # Matrix multiplication simulation
        times = []
        for _ in range(iterations):
            matrix_a = [[float(i * j) for j in range(size)] for i in range(size)]
            matrix_b = [[float(i + j) for j in range(size)] for i in range(size)]

            start = time.perf_counter()
            # Simplified matrix operation (sum of products)
            result = 0.0
            for i in range(min(100, size)):
                for j in range(min(100, size)):
                    result += matrix_a[i][j] * matrix_b[j][i]
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times)

        # Score: faster is better (normalize to 0-100)
        # Baseline: 0.1s = 50, 0.01s = 100, 1s = 10
        if avg_time <= 0.01:
            score = 100
        elif avg_time >= 1.0:
            score = 10
        else:
            score = int(100 - (avg_time * 90))
            score = max(10, min(100, score))

        return BenchmarkResult(
            name="CPU Performance",
            score=score,
            raw_value=round(avg_time * 1000, 2),
            unit="ms",
            description="Matrix computation speed",
        )

    def _benchmark_memory(self) -> BenchmarkResult:
        """
        Benchmark memory bandwidth with array operations.
        """
        size = 10_000_000  # 10M elements
        iterations = 3

        times = []
        for _ in range(iterations):
            # Allocate and fill array
            data = list(range(size))

            start = time.perf_counter()
            # Memory-intensive operations
            total = sum(data)
            data_reversed = data[::-1]
            _ = total + len(data_reversed)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times)

        # Calculate approximate bandwidth (bytes per second)
        bytes_processed = size * 8 * 2  # 8 bytes per int, 2 operations
        bandwidth_gbps = (bytes_processed / avg_time) / (1024**3)

        # Score based on bandwidth
        # Baseline: 10 GB/s = 50, 50 GB/s = 100, 1 GB/s = 10
        if bandwidth_gbps >= 50:
            score = 100
        elif bandwidth_gbps <= 1:
            score = 10
        else:
            score = int(10 + (bandwidth_gbps / 50) * 90)
            score = max(10, min(100, score))

        return BenchmarkResult(
            name="Memory Bandwidth",
            score=score,
            raw_value=round(bandwidth_gbps, 2),
            unit="GB/s",
            description="Memory throughput",
        )

    def _benchmark_gpu(self, system_info: dict) -> BenchmarkResult:
        """
        Benchmark GPU if available.
        Returns a simulated score based on detection.
        """
        if system_info.get("has_nvidia_gpu"):
            vram_mb = system_info.get("nvidia_vram_mb", 0)

            # Score based on VRAM
            # 4GB = 50, 8GB = 70, 16GB = 85, 24GB+ = 95
            if vram_mb >= 24576:
                score = 95
            elif vram_mb >= 16384:
                score = 85
            elif vram_mb >= 8192:
                score = 70
            elif vram_mb >= 4096:
                score = 50
            elif vram_mb >= 2048:
                score = 35
            else:
                score = 20

            return BenchmarkResult(
                name="GPU Memory",
                score=score,
                raw_value=vram_mb,
                unit="MB",
                description="NVIDIA GPU VRAM",
            )

        elif system_info.get("has_apple_silicon"):
            # Apple Silicon unified memory - estimate based on RAM
            ram_gb = system_info.get("ram_gb", 8)
            if ram_gb >= 64:
                score = 90
            elif ram_gb >= 32:
                score = 80
            elif ram_gb >= 16:
                score = 65
            elif ram_gb >= 8:
                score = 45
            else:
                score = 30

            return BenchmarkResult(
                name="GPU Memory",
                score=score,
                raw_value=int(ram_gb * 1024),
                unit="MB (unified)",
                description="Apple Silicon unified memory",
            )

        else:
            # No dedicated GPU
            return BenchmarkResult(
                name="GPU Memory",
                score=15,
                raw_value=0,
                unit="MB",
                description="No dedicated GPU detected",
            )

    def _benchmark_inference_simulation(self) -> BenchmarkResult:
        """
        Simulate inference workload with string operations and hashing.
        This approximates tokenization and model forward pass overhead.
        """
        iterations = 1000
        sample_text = "The quick brown fox jumps over the lazy dog. " * 10

        start = time.perf_counter()
        for _ in range(iterations):
            # Simulate tokenization
            tokens = sample_text.split()
            # Simulate embedding lookup (string hashing)
            embeddings = [hash(token) % 10000 for token in tokens]
            # Simulate attention (nested loops)
            attention = sum(
                embeddings[i] * embeddings[j]
                for i in range(min(50, len(embeddings)))
                for j in range(min(50, len(embeddings)))
            )
            _ = attention
        elapsed = time.perf_counter() - start

        # Tokens per second
        total_tokens = iterations * len(sample_text.split())
        tokens_per_sec = total_tokens / elapsed

        # Score: 10K tokens/s = 50, 100K = 100, 1K = 20
        if tokens_per_sec >= 100000:
            score = 100
        elif tokens_per_sec <= 1000:
            score = 20
        else:
            score = int(20 + ((tokens_per_sec - 1000) / 99000) * 80)
            score = max(20, min(100, score))

        return BenchmarkResult(
            name="Inference Speed",
            score=score,
            raw_value=round(tokens_per_sec / 1000, 2),
            unit="K tok/s",
            description="Simulated inference throughput",
        )

    def _benchmark_token_generation(self) -> BenchmarkResult:
        """
        Simulate token generation with sequential operations.
        """
        vocab_size = 32000
        sequence_length = 100
        iterations = 50

        start = time.perf_counter()
        for _ in range(iterations):
            # Simulate autoregressive generation
            generated = []
            context = [0] * 10
            for _ in range(sequence_length):
                # Simulate softmax over vocabulary
                logits = [
                    (hash((i, tuple(context[-10:]))) % 1000) / 1000
                    for i in range(min(1000, vocab_size))
                ]
                next_token = max(range(len(logits)), key=lambda i: logits[i])
                generated.append(next_token)
                context.append(next_token)
        elapsed = time.perf_counter() - start

        # Tokens per second
        total_tokens = iterations * sequence_length
        tokens_per_sec = total_tokens / elapsed

        # Score: 50 tok/s = 50, 500 tok/s = 100, 5 tok/s = 20
        if tokens_per_sec >= 500:
            score = 100
        elif tokens_per_sec <= 5:
            score = 20
        else:
            score = int(20 + ((tokens_per_sec - 5) / 495) * 80)
            score = max(20, min(100, score))

        return BenchmarkResult(
            name="Token Rate",
            score=score,
            raw_value=round(tokens_per_sec, 1),
            unit="tok/s",
            description="Simulated generation speed",
        )

    def _calculate_overall_score(self, results: list[BenchmarkResult]) -> tuple[int, str]:
        """
        Calculate overall score and rating.

        Weights:
        - GPU Memory: 35%
        - Inference: 25%
        - Token Rate: 25%
        - CPU: 10%
        - Memory: 5%
        """
        weights = {
            "GPU Memory": 0.35,
            "Inference Speed": 0.25,
            "Token Rate": 0.25,
            "CPU Performance": 0.10,
            "Memory Bandwidth": 0.05,
        }

        weighted_sum = 0
        total_weight = 0

        for result in results:
            weight = weights.get(result.name, 0.1)
            weighted_sum += result.score * weight
            total_weight += weight

        overall = int(weighted_sum / total_weight) if total_weight > 0 else 0

        # Rating
        if overall >= 90:
            rating = "Excellent"
        elif overall >= 75:
            rating = "Great"
        elif overall >= 60:
            rating = "Good"
        elif overall >= 40:
            rating = "Fair"
        elif overall >= 25:
            rating = "Basic"
        else:
            rating = "Limited"

        return overall, rating

    def _get_model_recommendations(
        self, system_info: dict, overall_score: int
    ) -> tuple[list[str], list[str], str]:
        """
        Get model recommendations based on system capabilities.

        Returns:
            Tuple of (can_run, needs_upgrade, upgrade_suggestion)
        """
        ram_gb = system_info.get("ram_gb", 0)
        vram_mb = system_info.get("nvidia_vram_mb", 0)

        # Apple Silicon uses unified memory
        if system_info.get("has_apple_silicon"):
            vram_mb = int(ram_gb * 1024 * 0.75)  # ~75% available for GPU

        can_run = []
        needs_upgrade = []

        for model, (min_ram, min_vram, min_score) in MODEL_REQUIREMENTS.items():
            if ram_gb >= min_ram and vram_mb >= min_vram and overall_score >= min_score:
                can_run.append(model)
            else:
                needs_upgrade.append(model)

        # Generate upgrade suggestion
        suggestion = ""
        if needs_upgrade and can_run:
            # Find the next achievable model
            for model in needs_upgrade:
                min_ram, min_vram, min_score = MODEL_REQUIREMENTS[model]
                if overall_score >= min_score:
                    if ram_gb < min_ram:
                        suggestion = f"Upgrade to {min_ram}GB RAM for: {model}"
                        break
                    if vram_mb < min_vram:
                        suggestion = f"Add GPU with {min_vram}MB VRAM for: {model}"
                        break
        elif not can_run:
            suggestion = "Consider upgrading RAM to at least 8GB for basic AI models"

        return can_run, needs_upgrade, suggestion

    def _save_to_history(self, report: BenchmarkReport):
        """Save benchmark result to history file."""
        try:
            self.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

            history = []
            if self.HISTORY_FILE.exists():
                with open(self.HISTORY_FILE) as f:
                    history = json.load(f)

            # Keep last 50 results
            history.append(report.to_dict())
            history = history[-50:]

            with open(self.HISTORY_FILE, "w") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            if self.verbose:
                cx_print(f"Could not save benchmark history: {e}", "warning")

    def run(self, save_history: bool = True) -> BenchmarkReport:
        """
        Run the complete benchmark suite.

        Returns:
            BenchmarkReport with scores and recommendations
        """
        report = BenchmarkReport()
        report.timestamp = datetime.now().isoformat()

        # Gather system info
        cx_print("Detecting system hardware...", "info")
        report.system_info = self._get_system_info()

        # Run benchmarks with progress display
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(bar_width=30, style="cyan", complete_style="green"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Running benchmarks...", total=5)

            # CPU benchmark
            progress.update(task, description="Testing CPU performance...")
            report.results.append(self._benchmark_cpu())
            progress.advance(task)

            # Memory benchmark
            progress.update(task, description="Testing memory bandwidth...")
            report.results.append(self._benchmark_memory())
            progress.advance(task)

            # GPU benchmark
            progress.update(task, description="Testing GPU capabilities...")
            report.results.append(self._benchmark_gpu(report.system_info))
            progress.advance(task)

            # Inference benchmark
            progress.update(task, description="Testing inference speed...")
            report.results.append(self._benchmark_inference_simulation())
            progress.advance(task)

            # Token generation benchmark
            progress.update(task, description="Testing token generation...")
            report.results.append(self._benchmark_token_generation())
            progress.advance(task)

        # Calculate overall score
        report.overall_score, report.rating = self._calculate_overall_score(report.results)

        # Get model recommendations
        report.can_run, report.needs_upgrade, report.upgrade_suggestion = (
            self._get_model_recommendations(report.system_info, report.overall_score)
        )

        # Save to history
        if save_history:
            self._save_to_history(report)

        return report

    def display_report(self, report: BenchmarkReport):
        """Display the benchmark report with rich formatting."""
        console.print()

        # Header
        cx_header("CORTEX BENCHMARK")

        # System info
        info = report.system_info
        cpu_model = info.get("cpu_model", info.get("processor", "Unknown"))
        ram_gb = info.get("ram_gb", 0)
        gpu_info = ""
        if info.get("has_nvidia_gpu"):
            vram = info.get("nvidia_vram_mb", 0)
            gpu_info = f"NVIDIA ({vram}MB)"
        elif info.get("has_apple_silicon"):
            gpu_info = "Apple Silicon"
        else:
            gpu_info = "Integrated"

        console.print(f"[dim]CPU:[/dim] {cpu_model}")
        console.print(f"[dim]RAM:[/dim] {ram_gb}GB")
        console.print(f"[dim]GPU:[/dim] {gpu_info}")
        console.print()

        # Results table
        table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style="cyan",
            box=box.ROUNDED,
        )
        table.add_column("Test", style="cyan", width=20)
        table.add_column("Score", justify="right", width=10)
        table.add_column("Value", justify="right", width=15)

        for result in report.results:
            # Color code score
            if result.score >= 75:
                score_str = f"[green]{result.score}/100[/green]"
            elif result.score >= 50:
                score_str = f"[yellow]{result.score}/100[/yellow]"
            else:
                score_str = f"[red]{result.score}/100[/red]"

            table.add_row(result.name, score_str, f"{result.raw_value} {result.unit}")

        console.print(table)
        console.print()

        # Overall score panel
        if report.overall_score >= 75:
            score_color = "green"
        elif report.overall_score >= 50:
            score_color = "yellow"
        else:
            score_color = "red"

        score_content = (
            f"[bold {score_color}]{report.overall_score}/100[/bold {score_color}] ({report.rating})"
        )
        console.print(
            Panel(
                f"[bold]OVERALL SCORE:[/bold]  {score_content}",
                border_style="cyan",
                box=box.ROUNDED,
            )
        )
        console.print()

        # Model recommendations
        if report.can_run:
            console.print("[bold green]✓[/bold green] Your system can run:")
            console.print(f"  [cyan]{', '.join(report.can_run)}[/cyan]")
            console.print()

        if report.upgrade_suggestion:
            console.print(f"[yellow]⚠[/yellow] {report.upgrade_suggestion}")
            console.print()


def run_benchmark(verbose: bool = False) -> int:
    """
    Main entry point for cortex benchmark command.

    Returns:
        Exit code (0 for success)
    """
    benchmark = CortexBenchmark(verbose=verbose)
    report = benchmark.run()
    benchmark.display_report(report)
    return 0
