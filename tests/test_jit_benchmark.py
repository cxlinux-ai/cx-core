"""
Tests for JIT Compiler Benchmarking

Issue: #275 - JIT Compiler Benchmarking
"""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from cortex.jit_benchmark import (
    BenchmarkCategory,
    BenchmarkComparison,
    BenchmarkResult,
    JITBenchmark,
    run_jit_benchmark,
)


class TestBenchmarkCategory:
    """Tests for BenchmarkCategory enum."""

    def test_categories_defined(self):
        """Test all categories are defined."""
        assert BenchmarkCategory.STARTUP.value == "startup"
        assert BenchmarkCategory.PARSING.value == "parsing"
        assert BenchmarkCategory.CACHE.value == "cache"
        assert BenchmarkCategory.STREAMING.value == "streaming"
        assert BenchmarkCategory.COMPUTATION.value == "computation"


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_default_values(self):
        """Test default result values."""
        result = BenchmarkResult(
            name="Test",
            category=BenchmarkCategory.STARTUP,
        )
        assert result.times == []
        assert result.memory_mb == 0.0
        assert result.jit_enabled is False

    def test_statistics(self):
        """Test statistical properties."""
        result = BenchmarkResult(
            name="Test",
            category=BenchmarkCategory.STARTUP,
            times=[0.1, 0.2, 0.3, 0.4, 0.5],
        )
        assert result.mean == 0.3
        assert result.median == 0.3
        assert result.min_time == 0.1
        assert result.max_time == 0.5
        assert result.stdev > 0

    def test_empty_times(self):
        """Test with empty times list."""
        result = BenchmarkResult(
            name="Test",
            category=BenchmarkCategory.STARTUP,
        )
        assert result.mean == 0.0
        assert result.median == 0.0
        assert result.min_time == 0.0
        assert result.max_time == 0.0
        assert result.stdev == 0.0

    def test_single_time(self):
        """Test with single time value."""
        result = BenchmarkResult(
            name="Test",
            category=BenchmarkCategory.STARTUP,
            times=[0.5],
        )
        assert result.mean == 0.5
        assert result.stdev == 0.0


class TestBenchmarkComparison:
    """Tests for BenchmarkComparison dataclass."""

    def test_speedup_calculation(self):
        """Test speedup calculation."""
        comp = BenchmarkComparison(
            name="Test",
            category=BenchmarkCategory.STARTUP,
            jit_mean=0.1,
            no_jit_mean=0.2,
        )
        assert comp.speedup == 2.0

    def test_percent_improvement(self):
        """Test percent improvement calculation."""
        comp = BenchmarkComparison(
            name="Test",
            category=BenchmarkCategory.STARTUP,
            jit_mean=0.1,
            no_jit_mean=0.2,
        )
        assert comp.percent_improvement == 50.0

    def test_zero_jit_mean(self):
        """Test with zero JIT mean."""
        comp = BenchmarkComparison(
            name="Test",
            category=BenchmarkCategory.STARTUP,
            jit_mean=0.0,
            no_jit_mean=0.2,
        )
        assert comp.speedup == 0.0

    def test_zero_no_jit_mean(self):
        """Test with zero no-JIT mean."""
        comp = BenchmarkComparison(
            name="Test",
            category=BenchmarkCategory.STARTUP,
            jit_mean=0.1,
            no_jit_mean=0.0,
        )
        assert comp.percent_improvement == 0.0


class TestJITBenchmark:
    """Tests for JITBenchmark class."""

    @pytest.fixture
    def benchmark(self):
        """Create a benchmark instance with minimal iterations."""
        return JITBenchmark(iterations=2, warmup=1, verbose=False)

    def test_initialization(self, benchmark):
        """Test benchmark initialization."""
        assert benchmark.iterations == 2
        assert benchmark.warmup == 1
        assert benchmark.verbose is False
        assert benchmark.results == []

    def test_get_python_info(self, benchmark):
        """Test Python info retrieval."""
        info = benchmark._get_python_info()
        assert "version" in info
        assert "version_info" in info
        assert "implementation" in info
        assert "jit_available" in info
        assert "jit_enabled" in info

    def test_timer(self, benchmark):
        """Test timing function."""
        def slow_func():
            total = sum(range(10000))
            return total

        elapsed = benchmark._timer(slow_func)
        assert elapsed > 0
        assert elapsed < 1  # Should be fast

    def test_run_benchmark(self, benchmark):
        """Test running a single benchmark."""
        def test_func():
            return sum(range(100))

        result = benchmark._run_benchmark(
            "Test",
            BenchmarkCategory.COMPUTATION,
            test_func,
        )

        assert result.name == "Test"
        assert result.category == BenchmarkCategory.COMPUTATION
        assert len(result.times) == 2  # iterations=2

    def test_run_all_benchmarks(self, benchmark):
        """Test running all benchmarks."""
        results = benchmark.run_all_benchmarks()

        assert len(results) > 0
        assert all(isinstance(r, BenchmarkResult) for r in results)

    def test_run_single_benchmark_valid(self, benchmark):
        """Test running a single named benchmark."""
        result = benchmark.run_single_benchmark("compute")

        assert result is not None
        assert "Computation" in result.name

    def test_run_single_benchmark_invalid(self, benchmark):
        """Test running an invalid benchmark name."""
        result = benchmark.run_single_benchmark("invalid")
        assert result is None

    def test_compare_jit(self, benchmark):
        """Test JIT comparison."""
        jit_results = [
            BenchmarkResult(
                name="Test1",
                category=BenchmarkCategory.STARTUP,
                times=[0.1, 0.1],
                jit_enabled=True,
            ),
            BenchmarkResult(
                name="Test2",
                category=BenchmarkCategory.PARSING,
                times=[0.2, 0.2],
                jit_enabled=True,
            ),
        ]

        no_jit_results = [
            BenchmarkResult(
                name="Test1",
                category=BenchmarkCategory.STARTUP,
                times=[0.2, 0.2],
                jit_enabled=False,
            ),
            BenchmarkResult(
                name="Test2",
                category=BenchmarkCategory.PARSING,
                times=[0.3, 0.3],
                jit_enabled=False,
            ),
        ]

        comparisons = benchmark.compare_jit(jit_results, no_jit_results)

        assert len(comparisons) == 2
        assert comparisons[0].speedup == 2.0
        assert comparisons[1].percent_improvement > 0

    def test_export_results(self, benchmark):
        """Test exporting results to JSON."""
        benchmark.results = [
            BenchmarkResult(
                name="Test",
                category=BenchmarkCategory.STARTUP,
                times=[0.1, 0.2],
            ),
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            success = benchmark.export_results(filepath)
            assert success is True

            with open(filepath) as f:
                data = json.load(f)

            assert "python" in data
            assert "results" in data
            assert len(data["results"]) == 1
        finally:
            os.unlink(filepath)

    def test_export_results_failure(self, benchmark):
        """Test export failure handling."""
        benchmark.results = []
        success = benchmark.export_results("/nonexistent/path/file.json")
        assert success is False

    def test_get_recommendations_old_python(self, benchmark):
        """Test recommendations for old Python version."""
        with patch.object(benchmark, "_get_python_info") as mock_info:
            mock_info.return_value = {
                "version_info": [3, 11, 0],
                "jit_available": False,
                "jit_enabled": False,
            }

            recommendations = benchmark.get_recommendations()
            assert any("Python 3.13" in r for r in recommendations)

    def test_get_recommendations_jit_available(self, benchmark):
        """Test recommendations when JIT available but not enabled."""
        with patch.object(benchmark, "_get_python_info") as mock_info:
            mock_info.return_value = {
                "version_info": [3, 13, 0],
                "jit_available": True,
                "jit_enabled": False,
            }

            recommendations = benchmark.get_recommendations()
            assert any("Enable JIT" in r for r in recommendations)


class TestBenchmarkFunctions:
    """Tests for individual benchmark functions."""

    @pytest.fixture
    def benchmark(self):
        return JITBenchmark(iterations=1, warmup=0)

    def test_bench_cli_startup(self, benchmark):
        """Test CLI startup benchmark runs."""
        benchmark._bench_cli_startup()

    def test_bench_command_parsing(self, benchmark):
        """Test command parsing benchmark runs."""
        benchmark._bench_command_parsing()

    def test_bench_cache_operations(self, benchmark):
        """Test cache operations benchmark runs."""
        benchmark._bench_cache_operations()

    def test_bench_json_operations(self, benchmark):
        """Test JSON operations benchmark runs."""
        benchmark._bench_json_operations()

    def test_bench_string_processing(self, benchmark):
        """Test string processing benchmark runs."""
        benchmark._bench_string_processing()

    def test_bench_list_operations(self, benchmark):
        """Test list operations benchmark runs."""
        benchmark._bench_list_operations()

    def test_bench_dict_operations(self, benchmark):
        """Test dict operations benchmark runs."""
        benchmark._bench_dict_operations()

    def test_bench_computation(self, benchmark):
        """Test computation benchmark runs."""
        benchmark._bench_computation()


class TestDisplayMethods:
    """Tests for display methods."""

    @pytest.fixture
    def benchmark(self):
        return JITBenchmark(iterations=1, warmup=0)

    def test_display_results(self, benchmark, capsys):
        """Test display_results runs without error."""
        benchmark.results = [
            BenchmarkResult(
                name="Test",
                category=BenchmarkCategory.STARTUP,
                times=[0.1],
            ),
        ]

        benchmark.display_results()
        captured = capsys.readouterr()
        assert "test" in captured.out.lower() or "benchmark" in captured.out.lower()

    def test_display_comparison(self, benchmark, capsys):
        """Test display_comparison runs without error."""
        comparisons = [
            BenchmarkComparison(
                name="Test",
                category=BenchmarkCategory.STARTUP,
                jit_mean=0.1,
                no_jit_mean=0.2,
            ),
        ]

        benchmark.display_comparison(comparisons)
        captured = capsys.readouterr()
        assert "jit" in captured.out.lower() or "comparison" in captured.out.lower()


class TestRunJitBenchmark:
    """Tests for run_jit_benchmark entry point."""

    def test_run_info(self, capsys):
        """Test info action."""
        result = run_jit_benchmark("info")
        assert result == 0
        captured = capsys.readouterr()
        assert "python" in captured.out.lower()

    def test_run_list(self, capsys):
        """Test list action."""
        result = run_jit_benchmark("list")
        assert result == 0
        captured = capsys.readouterr()
        assert "benchmark" in captured.out.lower()

    def test_run_benchmark_all(self, capsys):
        """Test running all benchmarks."""
        result = run_jit_benchmark("run", iterations=1)
        assert result == 0

    def test_run_benchmark_single(self, capsys):
        """Test running single benchmark."""
        result = run_jit_benchmark("run", benchmark="compute", iterations=1)
        assert result == 0

    def test_run_benchmark_invalid(self, capsys):
        """Test running invalid benchmark."""
        result = run_jit_benchmark("run", benchmark="invalid")
        assert result == 1
        captured = capsys.readouterr()
        assert "unknown" in captured.out.lower()

    def test_run_unknown_action(self, capsys):
        """Test unknown action."""
        result = run_jit_benchmark("unknown")
        assert result == 1
        captured = capsys.readouterr()
        assert "unknown" in captured.out.lower()

    def test_run_with_output(self, capsys):
        """Test running with output file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            result = run_jit_benchmark("run", iterations=1, output=filepath)
            assert result == 0

            with open(filepath) as f:
                data = json.load(f)
            assert "results" in data
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
