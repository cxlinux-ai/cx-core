"""
JIT Compiler Benchmarking for Cortex Operations

Issue: #275 - JIT Compiler Benchmarking

Benchmarks Cortex operations with/without Python JIT enabled.
Supports Python 3.13+ experimental JIT features.
"""

import gc
import json
import os
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


class BenchmarkCategory(Enum):
    """Categories of benchmarks."""

    STARTUP = "startup"
    PARSING = "parsing"
    CACHE = "cache"
    STREAMING = "streaming"
    COMPUTATION = "computation"


@dataclass
class BenchmarkResult:
    """Result from a single benchmark run."""

    name: str
    category: BenchmarkCategory
    times: list = field(default_factory=list)
    memory_mb: float = 0.0
    jit_enabled: bool = False

    @property
    def mean(self) -> float:
        """Mean execution time."""
        return statistics.mean(self.times) if self.times else 0.0

    @property
    def median(self) -> float:
        """Median execution time."""
        return statistics.median(self.times) if self.times else 0.0

    @property
    def stdev(self) -> float:
        """Standard deviation of execution times."""
        return statistics.stdev(self.times) if len(self.times) > 1 else 0.0

    @property
    def min_time(self) -> float:
        """Minimum execution time."""
        return min(self.times) if self.times else 0.0

    @property
    def max_time(self) -> float:
        """Maximum execution time."""
        return max(self.times) if self.times else 0.0


@dataclass
class BenchmarkComparison:
    """Comparison between JIT and non-JIT results."""

    name: str
    category: BenchmarkCategory
    jit_mean: float
    no_jit_mean: float

    @property
    def speedup(self) -> float:
        """Speedup factor (>1 means JIT is faster)."""
        if self.jit_mean == 0:
            return 0.0
        return self.no_jit_mean / self.jit_mean

    @property
    def percent_improvement(self) -> float:
        """Percentage improvement with JIT."""
        if self.no_jit_mean == 0:
            return 0.0
        return ((self.no_jit_mean - self.jit_mean) / self.no_jit_mean) * 100


class JITBenchmark:
    """JIT Compiler Benchmarking Suite."""

    def __init__(
        self,
        iterations: int = 10,
        warmup: int = 3,
        verbose: bool = False,
    ):
        """Initialize the benchmark suite.

        Args:
            iterations: Number of benchmark iterations
            warmup: Number of warmup iterations
            verbose: Enable verbose output
        """
        self.iterations = iterations
        self.warmup = warmup
        self.verbose = verbose
        self.results: list[BenchmarkResult] = []

    def _get_python_info(self) -> dict:
        """Get Python version and JIT information."""
        info = {
            "version": sys.version,
            "version_info": list(sys.version_info[:3]),
            "implementation": sys.implementation.name,
            "jit_available": False,
            "jit_enabled": False,
        }

        # Check for Python 3.13+ JIT
        if sys.version_info >= (3, 13):
            info["jit_available"] = True
            # Check if JIT is enabled via environment or flags
            jit_env = os.environ.get("PYTHON_JIT", "0")
            info["jit_enabled"] = jit_env == "1"

        return info

    def _timer(self, func: Callable, *args, **kwargs) -> float:
        """Time a function execution.

        Args:
            func: Function to time
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Execution time in seconds
        """
        gc.disable()
        start = time.perf_counter()
        func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        gc.enable()
        return elapsed

    def _run_benchmark(
        self,
        name: str,
        category: BenchmarkCategory,
        func: Callable,
        *args,
        **kwargs,
    ) -> BenchmarkResult:
        """Run a benchmark with warmup and iterations.

        Args:
            name: Benchmark name
            category: Benchmark category
            func: Function to benchmark
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            BenchmarkResult with timing data
        """
        python_info = self._get_python_info()
        result = BenchmarkResult(
            name=name,
            category=category,
            jit_enabled=python_info["jit_enabled"],
        )

        # Warmup runs
        for _ in range(self.warmup):
            func(*args, **kwargs)

        # Timed runs
        for _ in range(self.iterations):
            elapsed = self._timer(func, *args, **kwargs)
            result.times.append(elapsed)

        return result

    # === Benchmark Functions ===

    def _bench_cli_startup(self) -> None:
        """Benchmark CLI import and initialization."""

        def run():
            # Simulate CLI startup by importing modules
            import argparse

            import importlib

            # Force reimport
            if "cortex.cli" in sys.modules:
                importlib.reload(sys.modules["cortex.cli"])

        return run()

    def _bench_command_parsing(self) -> None:
        """Benchmark command parsing."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("command", nargs="?")
        parser.add_argument("args", nargs="*")
        parser.add_argument("--verbose", "-v", action="store_true")
        parser.add_argument("--output", "-o", type=str)
        parser.add_argument("--execute", action="store_true")

        commands = [
            ["install", "package"],
            ["status", "--verbose"],
            ["benchmark", "--output", "results.json"],
            ["ask", "how", "do", "I", "update"],
            ["install", "package", "--execute"],
            [],
        ]

        for cmd in commands:
            parser.parse_args(cmd)

    def _bench_cache_operations(self) -> None:
        """Benchmark cache read/write operations."""
        cache = {}

        # Write operations
        for i in range(1000):
            cache[f"key_{i}"] = {"value": i, "data": "x" * 100}

        # Read operations
        for i in range(1000):
            _ = cache.get(f"key_{i}")

        # Update operations
        for i in range(500):
            if f"key_{i}" in cache:
                cache[f"key_{i}"]["value"] = i * 2

    def _bench_json_operations(self) -> None:
        """Benchmark JSON serialization/deserialization."""
        data = {
            "packages": [
                {"name": f"pkg_{i}", "version": f"1.{i}.0", "deps": list(range(10))}
                for i in range(100)
            ],
            "metadata": {"timestamp": time.time(), "source": "benchmark"},
        }

        # Serialize
        for _ in range(100):
            json_str = json.dumps(data)

        # Deserialize
        for _ in range(100):
            _ = json.loads(json_str)

    def _bench_string_processing(self) -> None:
        """Benchmark string processing operations."""
        text = "Lorem ipsum dolor sit amet " * 100

        # Split and join
        for _ in range(100):
            words = text.split()
            _ = " ".join(words)

        # Search and replace
        for _ in range(100):
            _ = text.replace("ipsum", "IPSUM")
            _ = text.lower()
            _ = text.upper()

    def _bench_list_operations(self) -> None:
        """Benchmark list operations."""
        # Create and populate
        data = list(range(10000))

        # Sort operations
        for _ in range(10):
            sorted_data = sorted(data, reverse=True)

        # Filter operations
        for _ in range(10):
            filtered = [x for x in data if x % 2 == 0]

        # Map operations
        for _ in range(10):
            mapped = [x * 2 for x in data]

    def _bench_dict_operations(self) -> None:
        """Benchmark dictionary operations."""
        # Create large dict
        data = {f"key_{i}": i for i in range(10000)}

        # Lookup operations
        for _ in range(100):
            for key in list(data.keys())[:1000]:
                _ = data.get(key)

        # Update operations
        for _ in range(10):
            data.update({f"new_key_{i}": i for i in range(1000)})

    def _bench_computation(self) -> None:
        """Benchmark numerical computation."""
        # Fibonacci-like computation
        def fib_iterative(n: int) -> int:
            if n < 2:
                return n
            a, b = 0, 1
            for _ in range(n - 1):
                a, b = b, a + b
            return b

        for _ in range(100):
            fib_iterative(100)

        # Prime checking
        def is_prime(n: int) -> bool:
            if n < 2:
                return False
            for i in range(2, int(n**0.5) + 1):
                if n % i == 0:
                    return False
            return True

        for _ in range(10):
            primes = [n for n in range(2, 1000) if is_prime(n)]

    def run_all_benchmarks(self) -> list[BenchmarkResult]:
        """Run all benchmarks.

        Returns:
            List of benchmark results
        """
        benchmarks = [
            ("CLI Startup", BenchmarkCategory.STARTUP, self._bench_cli_startup),
            ("Command Parsing", BenchmarkCategory.PARSING, self._bench_command_parsing),
            ("Cache Operations", BenchmarkCategory.CACHE, self._bench_cache_operations),
            ("JSON Operations", BenchmarkCategory.CACHE, self._bench_json_operations),
            (
                "String Processing",
                BenchmarkCategory.STREAMING,
                self._bench_string_processing,
            ),
            ("List Operations", BenchmarkCategory.COMPUTATION, self._bench_list_operations),
            ("Dict Operations", BenchmarkCategory.COMPUTATION, self._bench_dict_operations),
            ("Numerical Computation", BenchmarkCategory.COMPUTATION, self._bench_computation),
        ]

        self.results = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running benchmarks...", total=len(benchmarks))

            for name, category, func in benchmarks:
                progress.update(task, description=f"Running {name}...")
                result = self._run_benchmark(name, category, func)
                self.results.append(result)
                progress.advance(task)

        return self.results

    def run_single_benchmark(self, name: str) -> Optional[BenchmarkResult]:
        """Run a single benchmark by name.

        Args:
            name: Benchmark name to run

        Returns:
            BenchmarkResult or None if not found
        """
        benchmarks = {
            "startup": ("CLI Startup", BenchmarkCategory.STARTUP, self._bench_cli_startup),
            "parsing": (
                "Command Parsing",
                BenchmarkCategory.PARSING,
                self._bench_command_parsing,
            ),
            "cache": ("Cache Operations", BenchmarkCategory.CACHE, self._bench_cache_operations),
            "json": ("JSON Operations", BenchmarkCategory.CACHE, self._bench_json_operations),
            "string": (
                "String Processing",
                BenchmarkCategory.STREAMING,
                self._bench_string_processing,
            ),
            "list": ("List Operations", BenchmarkCategory.COMPUTATION, self._bench_list_operations),
            "dict": ("Dict Operations", BenchmarkCategory.COMPUTATION, self._bench_dict_operations),
            "compute": (
                "Numerical Computation",
                BenchmarkCategory.COMPUTATION,
                self._bench_computation,
            ),
        }

        if name.lower() not in benchmarks:
            return None

        bench_name, category, func = benchmarks[name.lower()]
        return self._run_benchmark(bench_name, category, func)

    def compare_jit(
        self, jit_results: list[BenchmarkResult], no_jit_results: list[BenchmarkResult]
    ) -> list[BenchmarkComparison]:
        """Compare JIT and non-JIT benchmark results.

        Args:
            jit_results: Results with JIT enabled
            no_jit_results: Results without JIT

        Returns:
            List of comparisons
        """
        comparisons = []

        # Match results by name
        jit_by_name = {r.name: r for r in jit_results}
        no_jit_by_name = {r.name: r for r in no_jit_results}

        for name in jit_by_name:
            if name in no_jit_by_name:
                jit_r = jit_by_name[name]
                no_jit_r = no_jit_by_name[name]
                comparisons.append(
                    BenchmarkComparison(
                        name=name,
                        category=jit_r.category,
                        jit_mean=jit_r.mean,
                        no_jit_mean=no_jit_r.mean,
                    )
                )

        return comparisons

    def display_results(self):
        """Display benchmark results in a formatted table."""
        python_info = self._get_python_info()

        # Python info panel
        info_text = f"""Version: {'.'.join(map(str, python_info['version_info']))}
Implementation: {python_info['implementation']}
JIT Available: {'Yes' if python_info['jit_available'] else 'No'}
JIT Enabled: {'Yes' if python_info['jit_enabled'] else 'No'}"""

        console.print(
            Panel(info_text, title="[bold cyan]Python Environment[/bold cyan]")
        )
        console.print()

        # Results table
        table = Table(title="Benchmark Results")
        table.add_column("Benchmark", style="cyan")
        table.add_column("Category", style="blue")
        table.add_column("Mean (ms)", justify="right", style="green")
        table.add_column("Median (ms)", justify="right")
        table.add_column("Std Dev", justify="right")
        table.add_column("Min (ms)", justify="right")
        table.add_column("Max (ms)", justify="right")

        for result in self.results:
            table.add_row(
                result.name,
                result.category.value,
                f"{result.mean * 1000:.3f}",
                f"{result.median * 1000:.3f}",
                f"{result.stdev * 1000:.4f}",
                f"{result.min_time * 1000:.3f}",
                f"{result.max_time * 1000:.3f}",
            )

        console.print(table)

    def display_comparison(self, comparisons: list[BenchmarkComparison]):
        """Display JIT comparison results.

        Args:
            comparisons: List of benchmark comparisons
        """
        table = Table(title="JIT vs Non-JIT Comparison")
        table.add_column("Benchmark", style="cyan")
        table.add_column("Category", style="blue")
        table.add_column("No JIT (ms)", justify="right")
        table.add_column("JIT (ms)", justify="right")
        table.add_column("Speedup", justify="right", style="green")
        table.add_column("Improvement", justify="right", style="yellow")

        for comp in comparisons:
            speedup_color = "green" if comp.speedup > 1 else "red"
            improvement_color = "green" if comp.percent_improvement > 0 else "red"

            table.add_row(
                comp.name,
                comp.category.value,
                f"{comp.no_jit_mean * 1000:.3f}",
                f"{comp.jit_mean * 1000:.3f}",
                f"[{speedup_color}]{comp.speedup:.2f}x[/{speedup_color}]",
                f"[{improvement_color}]{comp.percent_improvement:+.1f}%[/{improvement_color}]",
            )

        console.print(table)

        # Summary
        avg_improvement = statistics.mean([c.percent_improvement for c in comparisons])
        console.print()
        console.print(
            Panel(
                f"Average improvement with JIT: [bold]{avg_improvement:+.1f}%[/bold]",
                title="Summary",
                style="cyan",
            )
        )

    def export_results(self, filepath: str) -> bool:
        """Export results to JSON file.

        Args:
            filepath: Output file path

        Returns:
            True if successful
        """
        python_info = self._get_python_info()

        data = {
            "python": python_info,
            "config": {
                "iterations": self.iterations,
                "warmup": self.warmup,
            },
            "results": [
                {
                    "name": r.name,
                    "category": r.category.value,
                    "mean_ms": r.mean * 1000,
                    "median_ms": r.median * 1000,
                    "stdev_ms": r.stdev * 1000,
                    "min_ms": r.min_time * 1000,
                    "max_ms": r.max_time * 1000,
                    "jit_enabled": r.jit_enabled,
                    "times_ms": [t * 1000 for t in r.times],
                }
                for r in self.results
            ],
        }

        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except (OSError, IOError):
            return False

    def get_recommendations(self) -> list[str]:
        """Get recommendations based on benchmark results.

        Returns:
            List of recommendation strings
        """
        recommendations = []
        python_info = self._get_python_info()

        # Python version recommendation
        if python_info["version_info"] < [3, 13, 0]:
            recommendations.append(
                "Upgrade to Python 3.13+ to access experimental JIT compiler"
            )

        # JIT recommendation
        if python_info["jit_available"] and not python_info["jit_enabled"]:
            recommendations.append(
                "Enable JIT with: PYTHON_JIT=1 python -X jit your_script.py"
            )

        # Performance recommendations based on results
        if self.results:
            # Find slowest benchmarks
            sorted_results = sorted(self.results, key=lambda r: r.mean, reverse=True)
            slowest = sorted_results[0] if sorted_results else None

            if slowest and slowest.mean > 0.1:  # > 100ms
                recommendations.append(
                    f"Consider optimizing '{slowest.name}' - taking {slowest.mean*1000:.1f}ms"
                )

            # Check for high variance
            high_variance = [r for r in self.results if r.stdev > r.mean * 0.5]
            if high_variance:
                names = ", ".join(r.name for r in high_variance[:3])
                recommendations.append(
                    f"High variance detected in: {names}. Consider investigating."
                )

        return recommendations


def run_jit_benchmark(
    action: str = "run",
    benchmark: Optional[str] = None,
    iterations: int = 10,
    output: Optional[str] = None,
    verbose: bool = False,
) -> int:
    """Run JIT benchmarking suite.

    Args:
        action: Action to perform (run, compare, info)
        benchmark: Specific benchmark to run
        iterations: Number of iterations
        output: Output file path for results
        verbose: Enable verbose output

    Returns:
        Exit code (0 for success)
    """
    suite = JITBenchmark(iterations=iterations, verbose=verbose)

    if action == "info":
        python_info = suite._get_python_info()
        console.print(
            Panel(
                f"""Python Version: {'.'.join(map(str, python_info['version_info']))}
Implementation: {python_info['implementation']}
JIT Available: {'[green]Yes[/green]' if python_info['jit_available'] else '[red]No[/red]'}
JIT Enabled: {'[green]Yes[/green]' if python_info['jit_enabled'] else '[red]No[/red]'}

To enable JIT (Python 3.13+):
  PYTHON_JIT=1 python -X jit your_script.py""",
                title="[bold cyan]JIT Information[/bold cyan]",
            )
        )
        return 0

    elif action == "run":
        if benchmark:
            result = suite.run_single_benchmark(benchmark)
            if result:
                suite.results = [result]
            else:
                console.print(f"[red]Unknown benchmark: {benchmark}[/red]")
                console.print("Available: startup, parsing, cache, json, string, list, dict, compute")
                return 1
        else:
            suite.run_all_benchmarks()

        suite.display_results()

        # Show recommendations
        recommendations = suite.get_recommendations()
        if recommendations:
            console.print()
            console.print(
                Panel(
                    "\n".join(f"• {r}" for r in recommendations),
                    title="[bold yellow]Recommendations[/bold yellow]",
                )
            )

        # Export if requested
        if output:
            if suite.export_results(output):
                console.print(f"\n[green]Results exported to {output}[/green]")
            else:
                console.print(f"\n[red]Failed to export results to {output}[/red]")

        return 0

    elif action == "list":
        console.print("[bold cyan]Available Benchmarks:[/bold cyan]")
        benchmarks = [
            ("startup", "CLI Startup - Import and initialization time"),
            ("parsing", "Command Parsing - Argument parsing performance"),
            ("cache", "Cache Operations - Read/write cache operations"),
            ("json", "JSON Operations - Serialization/deserialization"),
            ("string", "String Processing - String manipulation"),
            ("list", "List Operations - List sorting/filtering/mapping"),
            ("dict", "Dict Operations - Dictionary operations"),
            ("compute", "Numerical Computation - CPU-bound calculations"),
        ]
        for name, desc in benchmarks:
            console.print(f"  [cyan]{name}[/cyan] - {desc}")
        return 0

    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Available actions: run, list, info")
        return 1
