"""
Tests for Benchmark Module

Issue: #246 - cortex benchmark: Performance Scoring
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.benchmark import (
    MODEL_REQUIREMENTS,
    BenchmarkReport,
    BenchmarkResult,
    CortexBenchmark,
    run_benchmark,
)


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_result_creation(self):
        """Test creating a benchmark result."""
        result = BenchmarkResult(
            name="Test", score=75, raw_value=100.5, unit="ms", description="Test benchmark"
        )
        assert result.name == "Test"
        assert result.score == 75
        assert result.raw_value == 100.5
        assert result.unit == "ms"

    def test_result_default_description(self):
        """Test default description is empty."""
        result = BenchmarkResult(name="Test", score=50, raw_value=10.0, unit="s")
        assert result.description == ""


class TestBenchmarkReport:
    """Tests for BenchmarkReport dataclass."""

    def test_report_defaults(self):
        """Test report default values."""
        report = BenchmarkReport()
        assert report.timestamp == ""
        assert report.system_info == {}
        assert report.results == []
        assert report.overall_score == 0
        assert report.can_run == []
        assert report.needs_upgrade == []

    def test_report_to_dict(self):
        """Test report serialization."""
        report = BenchmarkReport(timestamp="2025-01-01T00:00:00", overall_score=75, rating="Good")
        result = report.to_dict()
        assert result["timestamp"] == "2025-01-01T00:00:00"
        assert result["overall_score"] == 75
        assert result["rating"] == "Good"

    def test_report_with_results(self):
        """Test report with benchmark results."""
        report = BenchmarkReport()
        report.results.append(BenchmarkResult("CPU", 80, 50.0, "ms"))
        report.results.append(BenchmarkResult("GPU", 60, 4096, "MB"))

        data = report.to_dict()
        assert len(data["results"]) == 2
        assert data["results"][0]["name"] == "CPU"
        assert data["results"][1]["score"] == 60


class TestModelRequirements:
    """Tests for model requirements configuration."""

    def test_model_requirements_structure(self):
        """Test model requirements have correct structure."""
        for model, reqs in MODEL_REQUIREMENTS.items():
            assert len(reqs) == 3
            min_ram, min_vram, min_score = reqs
            assert isinstance(min_ram, int)
            assert isinstance(min_vram, int)
            assert isinstance(min_score, int)
            assert 0 <= min_score <= 100

    def test_small_models_have_lower_requirements(self):
        """Test that smaller models have lower requirements."""
        small_models = ["tinyllama", "phi-2", "qwen2.5-1.5b"]
        large_models = ["llama2-70b", "mixtral-8x7b"]

        for small in small_models:
            if small in MODEL_REQUIREMENTS:
                small_reqs = MODEL_REQUIREMENTS[small]
                for large in large_models:
                    if large in MODEL_REQUIREMENTS:
                        large_reqs = MODEL_REQUIREMENTS[large]
                        assert small_reqs[0] <= large_reqs[0]  # RAM


class TestCortexBenchmark:
    """Tests for CortexBenchmark class."""

    @pytest.fixture
    def benchmark(self):
        """Create a benchmark instance."""
        return CortexBenchmark(verbose=False)

    def test_benchmark_initialization(self, benchmark):
        """Test benchmark initialization."""
        assert benchmark.verbose is False
        assert benchmark._results == []

    def test_get_system_info(self, benchmark):
        """Test system info gathering."""
        info = benchmark._get_system_info()
        assert "platform" in info
        assert "architecture" in info
        assert "cpu_cores" in info
        assert info["cpu_cores"] >= 1

    def test_benchmark_cpu(self, benchmark):
        """Test CPU benchmark."""
        result = benchmark._benchmark_cpu()
        assert result.name == "CPU Performance"
        assert 0 <= result.score <= 100
        assert result.unit == "ms"

    def test_benchmark_memory(self, benchmark):
        """Test memory benchmark."""
        result = benchmark._benchmark_memory()
        assert result.name == "Memory Bandwidth"
        assert 0 <= result.score <= 100
        assert result.unit == "GB/s"

    def test_benchmark_gpu_no_gpu(self, benchmark):
        """Test GPU benchmark without GPU."""
        system_info = {
            "has_nvidia_gpu": False,
            "has_apple_silicon": False,
        }
        result = benchmark._benchmark_gpu(system_info)
        assert result.name == "GPU Memory"
        assert result.score <= 20  # Low score for no GPU

    def test_benchmark_gpu_apple_silicon(self, benchmark):
        """Test GPU benchmark on Apple Silicon."""
        system_info = {
            "has_nvidia_gpu": False,
            "has_apple_silicon": True,
            "ram_gb": 16,
        }
        result = benchmark._benchmark_gpu(system_info)
        assert result.name == "GPU Memory"
        assert result.score > 20  # Higher score for Apple Silicon

    def test_benchmark_gpu_nvidia(self, benchmark):
        """Test GPU benchmark with NVIDIA GPU."""
        system_info = {
            "has_nvidia_gpu": True,
            "nvidia_vram_mb": 8192,
        }
        result = benchmark._benchmark_gpu(system_info)
        assert result.name == "GPU Memory"
        assert result.score >= 50  # Good score for 8GB VRAM

    def test_benchmark_inference_simulation(self, benchmark):
        """Test inference simulation benchmark."""
        result = benchmark._benchmark_inference_simulation()
        assert result.name == "Inference Speed"
        assert 0 <= result.score <= 100
        assert "tok/s" in result.unit

    def test_benchmark_token_generation(self, benchmark):
        """Test token generation benchmark."""
        result = benchmark._benchmark_token_generation()
        assert result.name == "Token Rate"
        assert 0 <= result.score <= 100
        assert result.unit == "tok/s"

    def test_calculate_overall_score(self, benchmark):
        """Test overall score calculation."""
        results = [
            BenchmarkResult("GPU Memory", 80, 8192, "MB"),
            BenchmarkResult("Inference Speed", 70, 50.0, "K tok/s"),
            BenchmarkResult("Token Rate", 75, 100.0, "tok/s"),
            BenchmarkResult("CPU Performance", 60, 50.0, "ms"),
            BenchmarkResult("Memory Bandwidth", 65, 10.0, "GB/s"),
        ]
        score, rating = benchmark._calculate_overall_score(results)
        assert 0 <= score <= 100
        assert rating in ["Excellent", "Great", "Good", "Fair", "Basic", "Limited"]

    def test_rating_levels(self, benchmark):
        """Test different rating levels."""
        # High scores
        high_results = [BenchmarkResult("GPU Memory", 95, 24576, "MB")] * 5
        score, rating = benchmark._calculate_overall_score(high_results)
        assert rating in ["Excellent", "Great"]

        # Low scores
        low_results = [BenchmarkResult("GPU Memory", 20, 512, "MB")] * 5
        score, rating = benchmark._calculate_overall_score(low_results)
        assert rating in ["Basic", "Limited"]

    def test_get_model_recommendations(self, benchmark):
        """Test model recommendations."""
        system_info = {
            "ram_gb": 16,
            "nvidia_vram_mb": 4096,
            "has_apple_silicon": False,
        }
        can_run, needs_upgrade, suggestion = benchmark._get_model_recommendations(
            system_info, overall_score=65
        )
        assert isinstance(can_run, list)
        assert isinstance(needs_upgrade, list)
        # With 16GB RAM and 4GB VRAM, should be able to run small models
        assert len(can_run) > 0

    def test_get_model_recommendations_apple_silicon(self, benchmark):
        """Test model recommendations for Apple Silicon."""
        system_info = {
            "ram_gb": 32,
            "nvidia_vram_mb": 0,
            "has_apple_silicon": True,
        }
        can_run, _, _ = benchmark._get_model_recommendations(system_info, 75)
        # 32GB unified memory should run several models
        assert len(can_run) >= 3

    def test_save_to_history(self, benchmark):
        """Test saving benchmark to history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            benchmark.HISTORY_FILE = Path(tmpdir) / "benchmark_history.json"

            report = BenchmarkReport(
                timestamp="2025-01-01T00:00:00", overall_score=75, rating="Good"
            )
            benchmark._save_to_history(report)

            assert benchmark.HISTORY_FILE.exists()
            with open(benchmark.HISTORY_FILE) as f:
                history = json.load(f)
            assert len(history) == 1
            assert history[0]["overall_score"] == 75

    def test_history_limit(self, benchmark):
        """Test history is limited to 50 entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            benchmark.HISTORY_FILE = Path(tmpdir) / "benchmark_history.json"

            # Save 60 entries
            for i in range(60):
                report = BenchmarkReport(
                    timestamp=f"2025-01-{i:02d}T00:00:00",
                    overall_score=i,
                )
                benchmark._save_to_history(report)

            with open(benchmark.HISTORY_FILE) as f:
                history = json.load(f)
            # Should be limited to 50
            assert len(history) == 50
            # Should keep the most recent (last 50)
            assert history[-1]["overall_score"] == 59


class TestNvidiaDetection:
    """Tests for NVIDIA GPU detection."""

    @pytest.fixture
    def benchmark(self):
        return CortexBenchmark()

    def test_detect_nvidia_gpu_not_available(self, benchmark):
        """Test when nvidia-smi is not available."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            assert benchmark._detect_nvidia_gpu() is False

    def test_detect_nvidia_gpu_available(self, benchmark):
        """Test when NVIDIA GPU is detected."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="NVIDIA GeForce RTX 3080")
            assert benchmark._detect_nvidia_gpu() is True

    def test_get_nvidia_vram(self, benchmark):
        """Test getting NVIDIA VRAM."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="10240")
            assert benchmark._get_nvidia_vram() == 10240


class TestAppleSiliconDetection:
    """Tests for Apple Silicon detection."""

    @pytest.fixture
    def benchmark(self):
        return CortexBenchmark()

    def test_is_apple_silicon_mac_arm(self, benchmark):
        """Test Apple Silicon detection on M-series Mac."""
        with patch("platform.system", return_value="Darwin"):
            with patch("platform.machine", return_value="arm64"):
                assert benchmark._is_apple_silicon() is True

    def test_is_not_apple_silicon_mac_intel(self, benchmark):
        """Test Apple Silicon detection on Intel Mac."""
        with patch("platform.system", return_value="Darwin"):
            with patch("platform.machine", return_value="x86_64"):
                assert benchmark._is_apple_silicon() is False

    def test_is_not_apple_silicon_linux(self, benchmark):
        """Test Apple Silicon detection on Linux."""
        with patch("platform.system", return_value="Linux"):
            assert benchmark._is_apple_silicon() is False


class TestBenchmarkRun:
    """Tests for running the full benchmark."""

    def test_run_benchmark_returns_report(self):
        """Test that run() returns a BenchmarkReport."""
        benchmark = CortexBenchmark()
        with patch.object(benchmark, "_save_to_history"):
            report = benchmark.run(save_history=False)
        assert isinstance(report, BenchmarkReport)
        assert report.timestamp != ""
        assert len(report.results) == 5  # CPU, Memory, GPU, Inference, Token

    def test_run_benchmark_all_scores_valid(self):
        """Test all scores are in valid range."""
        benchmark = CortexBenchmark()
        with patch.object(benchmark, "_save_to_history"):
            report = benchmark.run(save_history=False)

        for result in report.results:
            assert 0 <= result.score <= 100

        assert 0 <= report.overall_score <= 100

    def test_run_benchmark_has_rating(self):
        """Test report has a rating."""
        benchmark = CortexBenchmark()
        with patch.object(benchmark, "_save_to_history"):
            report = benchmark.run(save_history=False)

        assert report.rating in ["Excellent", "Great", "Good", "Fair", "Basic", "Limited"]


class TestRunBenchmarkFunction:
    """Tests for the run_benchmark entry point."""

    def test_run_benchmark_returns_zero(self, capsys):
        """Test run_benchmark returns 0 on success."""
        with patch("cortex.benchmark.CortexBenchmark") as MockBenchmark:
            mock_instance = MagicMock()
            mock_instance.run.return_value = BenchmarkReport(
                overall_score=75,
                rating="Good",
                results=[],
            )
            MockBenchmark.return_value = mock_instance

            result = run_benchmark(verbose=False)
            assert result == 0


class TestDisplayReport:
    """Tests for report display."""

    @pytest.fixture
    def benchmark(self):
        return CortexBenchmark()

    def test_display_report_outputs(self, benchmark, capsys):
        """Test display_report produces output."""
        report = BenchmarkReport(
            overall_score=75,
            rating="Good",
            system_info={
                "cpu_model": "Test CPU",
                "ram_gb": 16,
                "has_nvidia_gpu": False,
                "has_apple_silicon": True,
            },
            results=[
                BenchmarkResult("CPU Performance", 80, 50.0, "ms"),
                BenchmarkResult("Memory Bandwidth", 70, 10.0, "GB/s"),
                BenchmarkResult("GPU Memory", 65, 8192, "MB"),
                BenchmarkResult("Inference Speed", 75, 50.0, "K tok/s"),
                BenchmarkResult("Token Rate", 72, 100.0, "tok/s"),
            ],
            can_run=["tinyllama", "phi-2"],
            upgrade_suggestion="Upgrade to 32GB RAM for: llama2-13b",
        )

        benchmark.display_report(report)
        captured = capsys.readouterr()

        assert "CORTEX BENCHMARK" in captured.out
        assert "75" in captured.out
        assert "Good" in captured.out
        assert "tinyllama" in captured.out or "phi-2" in captured.out
