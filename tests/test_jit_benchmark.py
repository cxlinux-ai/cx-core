"""Tests for JIT benchmark module."""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from cortex.jit_benchmark import (
    BenchmarkCategory,
    BenchmarkComparison,
    BenchmarkResult,
    JITBenchmark,
    compare_results,
    run_jit_benchmark,
    show_jit_info,
)


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = BenchmarkResult(
            name="Test Benchmark",
            category=BenchmarkCategory.STARTUP,
            mean=0.001,
            median=0.0009,
            stdev=0.0001,
            min_time=0.0008,
            max_time=0.0012,
            iterations=100,
            jit_enabled=True,
        )

        data = result.to_dict()

        assert data["name"] == "Test Benchmark"
        assert data["category"] == "startup"
        assert data["mean"] == 0.001
        assert data["jit_enabled"] is True


class TestBenchmarkComparison:
    """Tests for BenchmarkComparison dataclass."""

    def test_is_faster_true(self):
        """Test is_faster when JIT is faster."""
        comp = BenchmarkComparison(
            name="Test",
            baseline_time=0.002,
            jit_time=0.001,
            speedup=2.0,
            percent_improvement=50.0,
        )
        assert comp.is_faster is True

    def test_is_faster_false(self):
        """Test is_faster when JIT is slower."""
        comp = BenchmarkComparison(
            name="Test",
            baseline_time=0.001,
            jit_time=0.002,
            speedup=0.5,
            percent_improvement=-50.0,
        )
        assert comp.is_faster is False


class TestJITBenchmark:
    """Tests for JITBenchmark class."""

    def test_init(self):
        """Test initialization."""
        bench = JITBenchmark(iterations=50)
        assert bench.iterations == 50
        assert isinstance(bench.jit_enabled, bool)
        assert bench.results == []

    @patch.dict(os.environ, {"PYTHON_JIT": "1"})
    def test_detect_jit_enabled(self):
        """Test JIT detection when enabled."""
        bench = JITBenchmark()
        assert bench.jit_enabled is True

    @patch.dict(os.environ, {"PYTHON_JIT": "0"})
    def test_detect_jit_disabled(self):
        """Test JIT detection when disabled."""
        bench = JITBenchmark()
        assert bench.jit_enabled is False

    def test_format_time_seconds(self):
        """Test time formatting for seconds."""
        bench = JITBenchmark()
        assert "s" in bench._format_time(1.5)

    def test_format_time_milliseconds(self):
        """Test time formatting for milliseconds."""
        bench = JITBenchmark()
        assert "ms" in bench._format_time(0.005)

    def test_format_time_microseconds(self):
        """Test time formatting for microseconds."""
        bench = JITBenchmark()
        assert "μs" in bench._format_time(0.0000005)

    def test_bench_cli_startup(self):
        """Test CLI startup benchmark runs without error."""
        bench = JITBenchmark(iterations=5)
        bench._bench_cli_startup()  # Should not raise

    def test_bench_command_parsing(self):
        """Test command parsing benchmark runs without error."""
        bench = JITBenchmark(iterations=5)
        bench._bench_command_parsing()  # Should not raise

    def test_bench_cache_operations(self):
        """Test cache operations benchmark runs without error."""
        bench = JITBenchmark(iterations=5)
        bench._bench_cache_operations()  # Should not raise

    def test_bench_response_streaming(self):
        """Test response streaming benchmark runs without error."""
        bench = JITBenchmark(iterations=5)
        bench._bench_response_streaming()  # Should not raise

    def test_run_benchmark(self):
        """Test running a single benchmark."""
        bench = JITBenchmark(iterations=5)
        result = bench.run_benchmark("cli")

        assert result is not None
        assert result.name == "CLI Startup"
        assert result.category == BenchmarkCategory.STARTUP
        assert result.iterations == 5
        assert result.mean > 0

    def test_run_benchmark_invalid(self):
        """Test running an invalid benchmark."""
        bench = JITBenchmark()
        result = bench.run_benchmark("nonexistent")
        assert result is None

    def test_run_all_benchmarks(self):
        """Test running all benchmarks."""
        bench = JITBenchmark(iterations=5)
        results = bench.run_all_benchmarks()

        assert len(results) == 4
        assert all(isinstance(r, BenchmarkResult) for r in results)
        assert all(r.iterations == 5 for r in results)

    def test_list_benchmarks(self):
        """Test listing available benchmarks."""
        bench = JITBenchmark()
        benchmarks = bench.list_benchmarks()

        assert "cli" in benchmarks
        assert "parse" in benchmarks
        assert "cache" in benchmarks
        assert "stream" in benchmarks

    def test_export_json(self):
        """Test exporting results to JSON."""
        bench = JITBenchmark(iterations=5)
        bench.run_all_benchmarks()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            filepath = f.name

        try:
            bench.export_json(filepath)

            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            assert "metadata" in data
            assert "results" in data
            assert data["metadata"]["iterations"] == 5
            assert len(data["results"]) == 4
        finally:
            os.unlink(filepath)

    def test_display_results_empty(self):
        """Test displaying results when no benchmarks run."""
        bench = JITBenchmark()
        bench.display_results()  # Should not raise

    def test_display_results_with_data(self):
        """Test displaying results with benchmark data."""
        bench = JITBenchmark(iterations=5)
        bench.run_all_benchmarks()
        bench.display_results()  # Should not raise

    def test_generate_recommendations(self):
        """Test generating recommendations."""
        bench = JITBenchmark(iterations=5)
        bench.run_all_benchmarks()
        bench.generate_recommendations()  # Should not raise


def test_compare_results():
    """Test comparing baseline and JIT results."""
    # Create temporary JSON files
    baseline_data = {
        "metadata": {"python_version": "3.13.0", "jit_enabled": False},
        "results": [
            {
                "name": "CLI Startup",
                "category": "startup",
                "mean": 0.002,
                "median": 0.0019,
                "stdev": 0.0001,
                "min": 0.0018,
                "max": 0.0022,
                "iterations": 100,
                "jit_enabled": False,
            }
        ],
    }

    jit_data = {
        "metadata": {"python_version": "3.13.0", "jit_enabled": True},
        "results": [
            {
                "name": "CLI Startup",
                "category": "startup",
                "mean": 0.001,
                "median": 0.0009,
                "stdev": 0.00005,
                "min": 0.0009,
                "max": 0.0011,
                "iterations": 100,
                "jit_enabled": True,
            }
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix="_baseline.json") as baseline_f:
        json.dump(baseline_data, baseline_f)
        baseline_path = baseline_f.name

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix="_jit.json") as jit_f:
        json.dump(jit_data, jit_f)
        jit_path = jit_f.name

    try:
        compare_results(baseline_path, jit_path)  # Should not raise
    finally:
        os.unlink(baseline_path)
        os.unlink(jit_path)


def test_show_jit_info():
    """Test displaying JIT information."""
    show_jit_info()  # Should not raise


class TestRunJITBenchmark:
    """Tests for run_jit_benchmark function."""

    def test_run_info_action(self):
        """Test info action."""
        result = run_jit_benchmark(action="info")
        assert result == 0

    def test_run_list_action(self):
        """Test list action."""
        result = run_jit_benchmark(action="list")
        assert result == 0

    def test_run_all_benchmarks(self):
        """Test running all benchmarks."""
        result = run_jit_benchmark(action="run", iterations=5)
        assert result == 0

    def test_run_specific_benchmark(self):
        """Test running a specific benchmark."""
        result = run_jit_benchmark(action="run", benchmark_name="cli", iterations=5)
        assert result == 0

    def test_run_invalid_benchmark(self):
        """Test running an invalid benchmark."""
        result = run_jit_benchmark(action="run", benchmark_name="nonexistent", iterations=5)
        assert result == 1

    def test_run_with_export(self):
        """Test running benchmarks with JSON export."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            output_path = f.name

        try:
            result = run_jit_benchmark(action="run", iterations=5, output=output_path)
            assert result == 0
            assert os.path.exists(output_path)

            with open(output_path, encoding="utf-8") as f:
                data = json.load(f)

            assert "metadata" in data
            assert "results" in data
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_compare_missing_files(self):
        """Test compare action with missing files."""
        result = run_jit_benchmark(
            action="compare",
            compare_baseline="nonexistent_baseline.json",
            compare_jit="nonexistent_jit.json",
        )
        assert result == 1

    def test_compare_without_files(self):
        """Test compare action without file arguments."""
        result = run_jit_benchmark(action="compare")
        assert result == 1
