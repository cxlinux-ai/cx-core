"""JIT Compiler Benchmarking for Cortex Operations.

This module provides comprehensive performance benchmarking for Python 3.13+
experimental JIT compilation. It measures CLI startup, command parsing,
cache operations, and response streaming performance.

"""

import json
import os
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rich.console import Console
from rich.table import Table

console = Console()


class BenchmarkCategory(Enum):
    """Categories of benchmarks."""

    STARTUP = "startup"
    PARSING = "parsing"
    CACHE = "cache"
    STREAMING = "streaming"


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""

    name: str
    category: BenchmarkCategory
    mean: float
    median: float
    stdev: float
    min_time: float
    max_time: float
    iterations: int
    jit_enabled: bool

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "name": self.name,
            "category": self.category.value,
            "mean": self.mean,
            "median": self.median,
            "stdev": self.stdev,
            "min": self.min_time,
            "max": self.max_time,
            "iterations": self.iterations,
            "jit_enabled": self.jit_enabled,
        }


@dataclass
class BenchmarkComparison:
    """Comparison between two benchmark results."""

    name: str
    baseline_time: float
    jit_time: float
    speedup: float
    percent_improvement: float

    @property
    def is_faster(self) -> bool:
        """Check if JIT version is faster."""
        return self.speedup > 1.0


class JITBenchmark:
    """Main benchmarking class for Cortex operations."""

    def __init__(self, iterations: int = 100):
        """Initialize benchmarker.

        Args:
            iterations: Number of times to run each benchmark.
        """
        self.iterations = iterations
        self.jit_enabled = self._detect_jit()
        self.results: list[BenchmarkResult] = []

    def _detect_jit(self) -> bool:
        """Detect if Python JIT is enabled.

        Returns:
            True if JIT is enabled, False otherwise.
        """
        # Python 3.13+ has PYTHON_JIT environment variable
        return os.environ.get("PYTHON_JIT", "0") == "1"

    def _format_time(self, seconds: float) -> str:
        """Format time in appropriate unit.

        Args:
            seconds: Time in seconds.

        Returns:
            Formatted time string.
        """
        if seconds >= 1.0:
            return f"{seconds:.4f}s"
        elif seconds >= 0.001:
            return f"{seconds * 1000:.2f}ms"
        else:
            return f"{seconds * 1_000_000:.2f}μs"

    def _run_benchmark(
        self, func: Callable, name: str, category: BenchmarkCategory
    ) -> BenchmarkResult:
        """Run a single benchmark.

        Args:
            func: Function to benchmark.
            name: Name of the benchmark.
            category: Category of the benchmark.

        Returns:
            BenchmarkResult with timing statistics.
        """
        times = []

        # Warmup run
        func()

        # Actual benchmark runs
        for _ in range(self.iterations):
            start = time.perf_counter()
            func()
            end = time.perf_counter()
            times.append(end - start)

        return BenchmarkResult(
            name=name,
            category=category,
            mean=statistics.mean(times),
            median=statistics.median(times),
            stdev=statistics.stdev(times) if len(times) > 1 else 0.0,
            min_time=min(times),
            max_time=max(times),
            iterations=self.iterations,
            jit_enabled=self.jit_enabled,
        )

    def _bench_cli_startup(self) -> None:
        """Benchmark CLI startup time."""
        # Simulate CLI initialization overhead
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("command")
        parser.add_argument("--execute", action="store_true")
        _ = parser.parse_args(["install", "--execute"])

    def _bench_command_parsing(self) -> None:
        """Benchmark command parsing."""
        # Simulate command parsing logic
        commands = [
            "install nginx",
            "update system",
            "search python3-pip",
            "remove old-package",
        ]

        for cmd in commands:
            parts = cmd.split()
            action = parts[0] if parts else ""
            args = parts[1:] if len(parts) > 1 else []
            # Simulate parsing logic
            _ = {"action": action, "args": args}

    def _bench_cache_operations(self) -> None:
        """Benchmark cache read/write operations."""
        # Simulate cache operations
        cache_data = {f"key_{i}": f"value_{i}" * 10 for i in range(100)}

        # Write
        for key, value in cache_data.items():
            _ = json.dumps({key: value})

        # Read
        for key in cache_data:
            _ = cache_data.get(key)

    def _bench_response_streaming(self) -> None:
        """Benchmark response streaming."""
        # Simulate streaming response processing
        response = "This is a test response " * 100
        chunk_size = 50
        chunks = [response[i : i + chunk_size] for i in range(0, len(response), chunk_size)]

        for chunk in chunks:
            # Simulate chunk processing
            _ = chunk.upper().lower()

    def run_all_benchmarks(self) -> list[BenchmarkResult]:
        """Run all benchmarks.

        Returns:
            List of BenchmarkResult objects.
        """
        benchmarks = [
            ("CLI Startup", BenchmarkCategory.STARTUP, self._bench_cli_startup),
            ("Command Parsing", BenchmarkCategory.PARSING, self._bench_command_parsing),
            ("Cache Operations", BenchmarkCategory.CACHE, self._bench_cache_operations),
            ("Response Streaming", BenchmarkCategory.STREAMING, self._bench_response_streaming),
        ]

        self.results = []

        for name, category, func in benchmarks:
            console.print(f"[cyan]Benchmarking {name}...[/cyan]")
            result = self._run_benchmark(func, name, category)
            self.results.append(result)

        return self.results

    def run_benchmark(self, benchmark_name: str) -> BenchmarkResult | None:
        """Run a specific benchmark.

        Args:
            benchmark_name: Name of benchmark to run.

        Returns:
            BenchmarkResult or None if not found.
        """
        benchmark_map = {
            "cli": ("CLI Startup", BenchmarkCategory.STARTUP, self._bench_cli_startup),
            "parse": ("Command Parsing", BenchmarkCategory.PARSING, self._bench_command_parsing),
            "cache": ("Cache Operations", BenchmarkCategory.CACHE, self._bench_cache_operations),
            "stream": (
                "Response Streaming",
                BenchmarkCategory.STREAMING,
                self._bench_response_streaming,
            ),
        }

        if benchmark_name not in benchmark_map:
            return None

        name, category, func = benchmark_map[benchmark_name]
        console.print(f"[cyan]Benchmarking {name}...[/cyan]")
        result = self._run_benchmark(func, name, category)
        self.results.append(result)
        return result

    def list_benchmarks(self) -> list[str]:
        """List available benchmarks.

        Returns:
            List of benchmark names.
        """
        return ["cli", "parse", "cache", "stream"]

    def display_results(self) -> None:
        """Display benchmark results in a formatted table."""
        if not self.results:
            console.print("[yellow]No benchmark results to display[/yellow]")
            return

        table = Table(
            title="Cortex JIT Benchmark Results", show_header=True, header_style="bold cyan"
        )
        table.add_column("Benchmark", style="green", width=20)
        table.add_column("Mean", justify="right")
        table.add_column("Median", justify="right")
        table.add_column("Std Dev", justify="right")
        table.add_column("Min", justify="right")
        table.add_column("Max", justify="right")

        for result in self.results:
            table.add_row(
                result.name,
                self._format_time(result.mean),
                self._format_time(result.median),
                self._format_time(result.stdev),
                self._format_time(result.min_time),
                self._format_time(result.max_time),
            )

        console.print()
        console.print(table)
        console.print()
        console.print(f"[dim]Python {sys.version_info.major}.{sys.version_info.minor}[/dim]")
        console.print(f"[dim]JIT: {'Enabled' if self.jit_enabled else 'Disabled'}[/dim]")

    def export_json(self, filepath: str) -> None:
        """Export results to JSON file.

        Args:
            filepath: Path to output JSON file.
        """
        data = {
            "metadata": {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "jit_enabled": self.jit_enabled,
                "iterations": self.iterations,
                "timestamp": time.time(),
            },
            "results": [r.to_dict() for r in self.results],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        console.print(f"[green]✓[/green] Results exported to {filepath}")

    def generate_recommendations(self) -> None:
        """Generate performance recommendations based on results."""
        if not self.results:
            return

        console.print("\n[bold]Recommendations:[/bold]")

        if self.jit_enabled:
            console.print("[green]✓[/green] JIT compilation is enabled - performance gains active")
        else:
            if sys.version_info >= (3, 13):
                console.print(
                    "[yellow]ℹ[/yellow] Enable JIT for potential speedups: export PYTHON_JIT=1"
                )
            else:
                console.print(
                    "[yellow]ℹ[/yellow] Upgrade to Python 3.13+ for JIT compilation support"
                )

        # Analyze results
        slow_benchmarks = [r for r in self.results if r.mean > 0.01]  # > 10ms
        if slow_benchmarks:
            console.print(
                f"\n[yellow]Performance hotspots detected in {len(slow_benchmarks)} operation(s):[/yellow]"
            )
            for bench in slow_benchmarks:
                console.print(f"  • {bench.name}: {self._format_time(bench.mean)}")


def compare_results(baseline_file: str, jit_file: str) -> None:
    """Compare benchmark results between baseline and JIT.

    Args:
        baseline_file: Path to baseline JSON results.
        jit_file: Path to JIT-enabled JSON results.
    """
    with open(baseline_file, encoding="utf-8") as f:
        baseline_data = json.load(f)

    with open(jit_file, encoding="utf-8") as f:
        jit_data = json.load(f)

    # Create comparison table
    table = Table(title="JIT Performance Comparison", show_header=True, header_style="bold cyan")
    table.add_column("Benchmark", style="green")
    table.add_column("Baseline", justify="right")
    table.add_column("With JIT", justify="right")
    table.add_column("Speedup", justify="right")
    table.add_column("Improvement", justify="right")

    comparisons: list[BenchmarkComparison] = []

    baseline_results = {r["name"]: r for r in baseline_data["results"]}
    jit_results = {r["name"]: r for r in jit_data["results"]}

    for name in baseline_results:
        if name not in jit_results:
            continue

        baseline_time = baseline_results[name]["mean"]
        jit_time = jit_results[name]["mean"]

        speedup = baseline_time / jit_time if jit_time > 0 else 0
        improvement = ((baseline_time - jit_time) / baseline_time * 100) if baseline_time > 0 else 0

        comp = BenchmarkComparison(
            name=name,
            baseline_time=baseline_time,
            jit_time=jit_time,
            speedup=speedup,
            percent_improvement=improvement,
        )
        comparisons.append(comp)

        # Format times
        def fmt(t):
            if t >= 1.0:
                return f"{t:.4f}s"
            elif t >= 0.001:
                return f"{t * 1000:.2f}ms"
            else:
                return f"{t * 1_000_000:.2f}μs"

        speedup_str = f"{speedup:.2f}x" if speedup > 0 else "N/A"

        improvement_color = "green" if improvement > 0 else "red"
        improvement_str = f"[{improvement_color}]{improvement:+.1f}%[/{improvement_color}]"

        table.add_row(name, fmt(baseline_time), fmt(jit_time), speedup_str, improvement_str)

    console.print()
    console.print(table)

    # Summary
    if comparisons:
        avg_improvement = statistics.mean([c.percent_improvement for c in comparisons])
        console.print()
        console.print(f"[bold]Average Performance Change:[/bold] {avg_improvement:+.1f}%")

        if avg_improvement > 5:
            console.print("[green]✓ JIT provides significant performance benefit[/green]")
        elif avg_improvement > 0:
            console.print("[yellow]ℹ JIT provides modest performance benefit[/yellow]")
        else:
            console.print("[red]⚠ JIT does not improve performance[/red]")


def show_jit_info() -> None:
    """Display JIT availability and status information."""
    console.print("\n[bold cyan]Python JIT Information[/bold cyan]")
    console.print(
        f"Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    jit_available = sys.version_info >= (3, 13)
    jit_enabled = os.environ.get("PYTHON_JIT", "0") == "1"

    if jit_available:
        console.print("[green]✓[/green] JIT compilation available (Python 3.13+)")
    else:
        console.print("[yellow]✗[/yellow] JIT compilation not available (requires Python 3.13+)")

    if jit_enabled:
        console.print("[green]✓[/green] JIT compilation is ENABLED")
    else:
        console.print("[yellow]✗[/yellow] JIT compilation is DISABLED")

    if jit_available and not jit_enabled:
        console.print("\n[dim]To enable JIT: export PYTHON_JIT=1[/dim]")
        console.print("[dim]Then run benchmarks again to compare[/dim]")


def run_jit_benchmark(
    action: str = "run",
    benchmark_name: str | None = None,
    iterations: int = 100,
    output: str | None = None,
    compare_baseline: str | None = None,
    compare_jit: str | None = None,
) -> int:
    """Run JIT benchmarking suite.

    Args:
        action: Action to perform (run, list, info).
        benchmark_name: Specific benchmark to run (None for all).
        iterations: Number of iterations per benchmark.
        output: Output file for JSON export.
        compare_baseline: Baseline results file for comparison.
        compare_jit: JIT results file for comparison.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    if action == "info":
        show_jit_info()
        return 0

    if action == "compare":
        if not compare_baseline or not compare_jit:
            console.print("[red]Error: --compare requires both --baseline and --jit files[/red]")
            return 1

        try:
            compare_results(compare_baseline, compare_jit)
            return 0
        except FileNotFoundError as e:
            console.print(f"[red]Error: {e}[/red]")
            return 1
        except json.JSONDecodeError as e:
            console.print(f"[red]Error parsing JSON: {e}[/red]")
            return 1

    benchmarker = JITBenchmark(iterations=iterations)

    if action == "list":
        console.print("\n[bold cyan]Available Benchmarks:[/bold cyan]")
        for bench in benchmarker.list_benchmarks():
            console.print(f"  • {bench}")
        console.print("\n[dim]Run: cortex jit-benchmark -b <name>[/dim]")
        return 0

    # Run benchmarks
    console.print(
        f"\n[bold cyan]Running Cortex JIT Benchmarks[/bold cyan] ({iterations} iterations)"
    )
    console.print(f"Python {sys.version_info.major}.{sys.version_info.minor} | ", end="")
    console.print(f"JIT: {'Enabled' if benchmarker.jit_enabled else 'Disabled'}")
    console.print()

    if benchmark_name:
        result = benchmarker.run_benchmark(benchmark_name)
        if not result:
            console.print(f"[red]Error: Unknown benchmark '{benchmark_name}'[/red]")
            console.print("Run 'cortex jit-benchmark list' to see available benchmarks")
            return 1
    else:
        benchmarker.run_all_benchmarks()

    # Display results
    benchmarker.display_results()

    # Generate recommendations
    benchmarker.generate_recommendations()

    # Export if requested
    if output:
        benchmarker.export_json(output)

    return 0
