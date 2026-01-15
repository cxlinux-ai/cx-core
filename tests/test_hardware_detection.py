"""
Tests for Hardware Detection Module

Issue: #253
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from cortex.hardware_detection import (
    CPUInfo,
    CPUVendor,
    GPUInfo,
    GPUVendor,
    HardwareDetector,
    MemoryInfo,
    NetworkInfo,
    StorageInfo,
    SystemInfo,
    detect_hardware,
    detect_quick,
    get_cpu_cores,
    get_detector,
    get_gpu_info,
    get_ram_gb,
    has_nvidia_gpu,
)


class TestCPUVendor:
    """Tests for CPUVendor enum."""

    def test_all_vendors_exist(self):
        """Test all expected vendors exist."""
        expected = ["INTEL", "AMD", "ARM", "UNKNOWN"]
        actual = [v.name for v in CPUVendor]

        for e in expected:
            assert e in actual


class TestGPUVendor:
    """Tests for GPUVendor enum."""

    def test_all_vendors_exist(self):
        """Test all expected vendors exist."""
        expected = ["NVIDIA", "AMD", "INTEL", "UNKNOWN"]
        actual = [v.name for v in GPUVendor]

        for e in expected:
            assert e in actual


class TestCPUInfo:
    """Tests for CPUInfo dataclass."""

    def test_default_values(self):
        """Test default values."""
        cpu = CPUInfo()

        assert cpu.vendor == CPUVendor.UNKNOWN
        assert cpu.model == "Unknown"
        assert cpu.cores == 0
        assert cpu.threads == 0

    def test_to_dict(self):
        """Test serialization."""
        cpu = CPUInfo(vendor=CPUVendor.INTEL, model="Intel Core i7-9700K", cores=8, threads=8)

        data = cpu.to_dict()

        assert data["vendor"] == "intel"
        assert data["model"] == "Intel Core i7-9700K"
        assert data["cores"] == 8


class TestGPUInfo:
    """Tests for GPUInfo dataclass."""

    def test_default_values(self):
        """Test default values."""
        gpu = GPUInfo()

        assert gpu.vendor == GPUVendor.UNKNOWN
        assert gpu.model == "Unknown"
        assert gpu.memory_mb == 0

    def test_to_dict(self):
        """Test serialization."""
        gpu = GPUInfo(
            vendor=GPUVendor.NVIDIA,
            model="GeForce RTX 4090",
            memory_mb=24576,
            driver_version="535.104.05",
        )

        data = gpu.to_dict()

        assert data["vendor"] == "nvidia"
        assert data["model"] == "GeForce RTX 4090"
        assert data["memory_mb"] == 24576


class TestMemoryInfo:
    """Tests for MemoryInfo dataclass."""

    def test_default_values(self):
        """Test default values."""
        mem = MemoryInfo()

        assert mem.total_mb == 0
        assert mem.available_mb == 0

    def test_total_gb_property(self):
        """Test total_gb calculation."""
        mem = MemoryInfo(total_mb=32768)

        assert mem.total_gb == 32.0

    def test_available_gb_property(self):
        """Test available_gb calculation."""
        mem = MemoryInfo(available_mb=16384)

        assert mem.available_gb == 16.0

    def test_to_dict(self):
        """Test serialization includes computed properties."""
        mem = MemoryInfo(total_mb=32768, available_mb=16384)

        data = mem.to_dict()

        assert "total_gb" in data
        assert "available_gb" in data


class TestStorageInfo:
    """Tests for StorageInfo dataclass."""

    def test_default_values(self):
        """Test default values."""
        storage = StorageInfo()

        assert storage.device == ""
        assert storage.total_gb == 0.0

    def test_usage_percent_property(self):
        """Test usage_percent calculation."""
        storage = StorageInfo(total_gb=500.0, used_gb=250.0)

        assert storage.usage_percent == 50.0

    def test_usage_percent_zero_total(self):
        """Test usage_percent with zero total."""
        storage = StorageInfo(total_gb=0.0, used_gb=0.0)

        assert storage.usage_percent == 0.0


class TestNetworkInfo:
    """Tests for NetworkInfo dataclass."""

    def test_default_values(self):
        """Test default values."""
        net = NetworkInfo()

        assert net.interface == ""
        assert net.is_wireless is False

    def test_to_dict(self):
        """Test serialization."""
        net = NetworkInfo(interface="eth0", ip_address="192.168.1.100", is_wireless=False)

        data = net.to_dict()

        assert data["interface"] == "eth0"
        assert data["ip_address"] == "192.168.1.100"


class TestSystemInfo:
    """Tests for SystemInfo dataclass."""

    def test_default_values(self):
        """Test default values."""
        info = SystemInfo()

        assert info.hostname == ""
        assert isinstance(info.cpu, CPUInfo)
        assert info.gpu == []
        assert isinstance(info.memory, MemoryInfo)

    def test_to_dict(self):
        """Test full serialization."""
        info = SystemInfo(
            hostname="testhost", kernel_version="5.15.0", distro="Ubuntu", distro_version="24.04"
        )
        info.cpu = CPUInfo(vendor=CPUVendor.INTEL, model="i7", cores=8)
        info.gpu = [GPUInfo(vendor=GPUVendor.NVIDIA, model="RTX 4090")]

        data = info.to_dict()

        assert data["hostname"] == "testhost"
        assert data["cpu"]["vendor"] == "intel"
        assert len(data["gpu"]) == 1
        assert data["gpu"][0]["vendor"] == "nvidia"


class TestHardwareDetector:
    """Tests for HardwareDetector class."""

    @pytest.fixture
    def detector(self, tmp_path):
        """Create detector with temp cache path."""
        detector = HardwareDetector(use_cache=False)
        detector.CACHE_FILE = tmp_path / "hardware_cache.json"
        return detector

    def test_init_no_cache(self):
        """Test initialization without cache."""
        detector = HardwareDetector(use_cache=False)
        assert detector.use_cache is False

    def test_init_with_cache(self):
        """Test initialization with cache."""
        detector = HardwareDetector(use_cache=True)
        assert detector.use_cache is True

    @patch("subprocess.run")
    @patch("builtins.open", mock_open(read_data="model name : Intel Core\nMemTotal: 32768 kB"))
    def test_detect_returns_system_info(self, mock_run, detector):
        """Test detect returns SystemInfo."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        info = detector.detect()

        assert isinstance(info, SystemInfo)

    @patch("os.cpu_count")
    def test_get_cpu_cores(self, mock_count, detector):
        """Test quick CPU core detection."""
        mock_count.return_value = 8

        cores = detector._get_cpu_cores()

        assert cores == 8

    @patch("os.cpu_count")
    def test_get_cpu_cores_none(self, mock_count, detector):
        """Test CPU cores when None returned."""
        mock_count.return_value = None

        cores = detector._get_cpu_cores()

        assert cores == 1

    @patch("builtins.open", mock_open(read_data="MemTotal: 33554432 kB\n"))
    def test_get_ram_gb(self, detector):
        """Test quick RAM detection."""
        ram = detector._get_ram_gb()

        assert ram == 32.0

    @patch("subprocess.run")
    def test_has_nvidia_gpu_true(self, mock_run, detector):
        """Test NVIDIA GPU detection when present."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="01:00.0 VGA: NVIDIA Corporation GeForce RTX 4090"
        )

        result = detector._has_nvidia_gpu()

        assert result is True

    @patch("subprocess.run")
    def test_has_nvidia_gpu_false(self, mock_run, detector):
        """Test NVIDIA GPU detection when absent."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="00:02.0 VGA: Intel Corporation UHD Graphics"
        )

        result = detector._has_nvidia_gpu()

        assert result is False

    @patch("os.statvfs", create=True)
    def test_get_disk_free_gb(self, mock_statvfs, detector):
        """Test disk free space detection."""
        mock_statvfs.return_value = MagicMock(
            f_frsize=4096, f_bavail=262144000, f_blocks=262144000
        )  # ~1TB free

        free_gb = detector._get_disk_free_gb()

        assert free_gb > 0

    @patch("subprocess.run")
    def test_detect_quick(self, mock_run, detector):
        """Test quick detection returns dict."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        with patch.object(detector, "_get_cpu_cores", return_value=8):
            with patch.object(detector, "_get_ram_gb", return_value=32.0):
                with patch.object(detector, "_has_nvidia_gpu", return_value=True):
                    with patch.object(detector, "_get_disk_free_gb", return_value=500.0):
                        quick = detector.detect_quick()

        assert quick["cpu_cores"] == 8
        assert quick["ram_gb"] == 32.0
        assert quick["has_nvidia"] is True
        assert quick["disk_free_gb"] == 500.0


class TestDetectionMethods:
    """Tests for individual detection methods."""

    @pytest.fixture
    def detector(self):
        return HardwareDetector(use_cache=False)

    @patch("os.uname", create=True)
    def test_detect_system(self, mock_uname, detector):
        """Test system info detection."""
        mock_uname.return_value = MagicMock(
            nodename="testhost", release="5.15.0-generic", version="5.15.0-generic"
        )

        info = SystemInfo()

        with patch("builtins.open", mock_open(read_data='NAME="Ubuntu"\nVERSION_ID="24.04"')):
            detector._detect_system(info)

        assert info.hostname == "testhost"
        assert info.kernel_version == "5.15.0-generic"

    def test_detect_cpu(self, detector):
        """Test CPU detection."""
        cpuinfo = """
processor   : 0
model name  : Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz
cpu MHz     : 3600.000
core id     : 0
flags       : avx avx2 sse4_1 sse4_2 aes
"""
        info = SystemInfo()

        with patch("builtins.open", mock_open(read_data=cpuinfo)):
            detector._detect_cpu(info)

        assert info.cpu.vendor == CPUVendor.INTEL
        assert "i7-9700K" in info.cpu.model

    @patch("subprocess.run")
    def test_detect_gpu_nvidia(self, mock_run, detector):
        """Test NVIDIA GPU detection."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GeForce RTX 4090 [10de:2684]",
        )

        info = SystemInfo()
        detector._detect_gpu(info)

        assert info.has_nvidia_gpu is True
        assert len(info.gpu) >= 1
        assert info.gpu[0].vendor == GPUVendor.NVIDIA

    @patch("subprocess.run")
    def test_detect_gpu_amd(self, mock_run, detector):
        """Test AMD GPU detection."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="01:00.0 VGA compatible controller: AMD/ATI Radeon RX 7900 XTX"
        )

        info = SystemInfo()
        detector._detect_gpu(info)

        assert info.has_amd_gpu is True

    def test_detect_memory(self, detector):
        """Test memory detection."""
        meminfo = """
MemTotal:       32768000 kB
MemAvailable:   16384000 kB
SwapTotal:       8192000 kB
SwapFree:        8192000 kB
"""
        info = SystemInfo()

        with patch("builtins.open", mock_open(read_data=meminfo)):
            detector._detect_memory(info)

        assert info.memory.total_mb == 32000
        assert info.memory.available_mb == 16000

    @patch("subprocess.run")
    def test_detect_storage(self, mock_run, detector):
        """Test storage detection."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""Filesystem     1M-blocks  Used Available Use% Mounted on
/dev/sda1       500000M  250000M  250000M  50% /""",
        )

        info = SystemInfo()
        detector._detect_storage(info)

        # Storage detection depends on parsing
        assert isinstance(info.storage, list)

    @patch("subprocess.run")
    def test_detect_virtualization_docker(self, mock_run, detector):
        """Test Docker detection."""
        mock_run.side_effect = Exception("Command not found")

        info = SystemInfo()

        with patch.object(Path, "exists", return_value=True):
            detector._detect_virtualization(info)

        assert info.virtualization == "docker"


class TestCaching:
    """Tests for caching functionality."""

    @pytest.fixture
    def detector(self, tmp_path):
        detector = HardwareDetector(use_cache=True)
        detector.CACHE_FILE = tmp_path / "test_cache.json"
        return detector

    def test_save_and_load_cache(self, detector):
        """Test cache save and load."""
        info = SystemInfo(hostname="testhost", distro="Ubuntu")
        info.cpu = CPUInfo(vendor=CPUVendor.INTEL, model="i7")
        info.memory = MemoryInfo(total_mb=32000)
        info.has_nvidia_gpu = True

        detector._save_cache(info)

        assert detector.CACHE_FILE.exists()

        loaded = detector._load_cache()

        assert loaded is not None
        assert loaded.hostname == "testhost"

    def test_load_cache_not_exists(self, detector):
        """Test loading non-existent cache."""
        result = detector._load_cache()
        assert result is None

    def test_load_cache_corrupted(self, detector):
        """Test loading corrupted cache."""
        detector.CACHE_FILE.write_text("invalid json")

        result = detector._load_cache()
        assert result is None


class TestGlobalFunctions:
    """Tests for module-level convenience functions."""

    def test_get_detector_singleton(self):
        """Test get_detector returns singleton."""
        d1 = get_detector()
        d2 = get_detector()

        assert d1 is d2

    @patch.object(HardwareDetector, "detect")
    def test_detect_hardware(self, mock_detect):
        """Test detect_hardware function."""
        mock_detect.return_value = SystemInfo()

        result = detect_hardware()

        assert isinstance(result, SystemInfo)

    @patch.object(HardwareDetector, "detect_quick")
    def test_detect_quick(self, mock_quick):
        """Test detect_quick function."""
        mock_quick.return_value = {"cpu_cores": 8}

        result = detect_quick()

        assert result["cpu_cores"] == 8

    @patch.object(HardwareDetector, "detect")
    def test_get_gpu_info(self, mock_detect):
        """Test get_gpu_info function."""
        info = SystemInfo()
        info.gpu = [GPUInfo(vendor=GPUVendor.NVIDIA)]
        mock_detect.return_value = info

        result = get_gpu_info()

        assert len(result) == 1

    @patch.object(HardwareDetector, "detect_quick")
    def test_has_nvidia_gpu(self, mock_quick):
        """Test has_nvidia_gpu function."""
        mock_quick.return_value = {"has_nvidia": True}

        result = has_nvidia_gpu()

        assert result is True

    @patch.object(HardwareDetector, "detect_quick")
    def test_get_ram_gb(self, mock_quick):
        """Test get_ram_gb function."""
        mock_quick.return_value = {"ram_gb": 32.0}

        result = get_ram_gb()

        assert result == 32.0

    @patch.object(HardwareDetector, "detect_quick")
    def test_get_cpu_cores(self, mock_quick):
        """Test get_cpu_cores function."""
        mock_quick.return_value = {"cpu_cores": 8}

        result = get_cpu_cores()

        assert result == 8


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def detector(self):
        return HardwareDetector(use_cache=False)

    @patch("subprocess.run")
    def test_lspci_timeout(self, mock_run, detector):
        """Test handling lspci timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("lspci", 5)

        info = SystemInfo()
        detector._detect_gpu(info)

        # Should not crash, just have empty GPU list
        assert info.gpu == []

    @patch("subprocess.run")
    def test_nvidia_smi_not_found(self, mock_run, detector):
        """Test handling missing nvidia-smi."""
        mock_run.side_effect = FileNotFoundError()  # nvidia-smi not found
        info = SystemInfo()
        info.has_nvidia_gpu = True
        detector._detect_nvidia_details(info)

        # Should not crash and cuda_available should remain False (default)
        assert info.cuda_available is False

    def test_detect_with_missing_proc_files(self, detector):
        """Test detection when /proc files are missing."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            info = SystemInfo()
            detector._detect_cpu(info)
            detector._detect_memory(info)

        # Should use defaults
        assert info.cpu.model == "Unknown"
        assert info.memory.total_mb == 0


class TestIntegration:
    """Integration tests."""

    def test_full_detection_cycle(self, tmp_path):
        """Test complete detection cycle with caching."""
        detector = HardwareDetector(use_cache=True)
        detector.CACHE_FILE = tmp_path / "cache.json"

        # First detection (populates cache)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            info1 = detector.detect()

        assert detector.CACHE_FILE.exists()

        # Second detection (from cache)
        info2 = detector.detect()

        # Should both be valid
        assert isinstance(info1, SystemInfo)
        assert isinstance(info2, SystemInfo)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
