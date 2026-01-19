"""
Hardware Detection Module for Cortex Linux

Provides comprehensive, instant hardware detection for optimal package
recommendations and system configuration.

Issue: #253
"""

import builtins
import contextlib
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GPUVendor(Enum):
    """GPU vendors."""

    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    UNKNOWN = "unknown"


class CPUVendor(Enum):
    """CPU vendors."""

    INTEL = "intel"
    AMD = "amd"
    ARM = "arm"
    UNKNOWN = "unknown"


@dataclass
class CPUInfo:
    """CPU information."""

    vendor: CPUVendor = CPUVendor.UNKNOWN
    model: str = "Unknown"
    cores: int = 0
    threads: int = 0
    frequency_mhz: float = 0.0
    architecture: str = "x86_64"
    features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "vendor": self.vendor.value}


@dataclass
class GPUInfo:
    """GPU information."""

    vendor: GPUVendor = GPUVendor.UNKNOWN
    model: str = "Unknown"
    memory_mb: int = 0
    driver_version: str = ""
    cuda_version: str = ""
    compute_capability: str = ""
    pci_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "vendor": self.vendor.value}


@dataclass
class MemoryInfo:
    """Memory information."""

    total_mb: int = 0
    available_mb: int = 0
    swap_total_mb: int = 0
    swap_free_mb: int = 0

    @property
    def total_gb(self) -> float:
        return round(self.total_mb / 1024, 1)

    @property
    def available_gb(self) -> float:
        return round(self.available_mb / 1024, 1)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "total_gb": self.total_gb, "available_gb": self.available_gb}


@dataclass
class StorageInfo:
    """Storage information."""

    device: str = ""
    mount_point: str = ""
    filesystem: str = ""
    total_gb: float = 0.0
    used_gb: float = 0.0
    available_gb: float = 0.0

    @property
    def usage_percent(self) -> float:
        if self.total_gb > 0:
            return round((self.used_gb / self.total_gb) * 100, 1)
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "usage_percent": self.usage_percent}


@dataclass
class NetworkInfo:
    """Network interface information."""

    interface: str = ""
    ip_address: str = ""
    mac_address: str = ""
    speed_mbps: int = 0
    is_wireless: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SystemInfo:
    """Complete system information."""

    hostname: str = ""
    kernel_version: str = ""
    distro: str = ""
    distro_version: str = ""
    uptime_seconds: int = 0

    cpu: CPUInfo = field(default_factory=CPUInfo)
    gpu: list[GPUInfo] = field(default_factory=list)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    storage: list[StorageInfo] = field(default_factory=list)
    network: list[NetworkInfo] = field(default_factory=list)

    # Capabilities
    has_nvidia_gpu: bool = False
    has_amd_gpu: bool = False
    cuda_available: bool = False
    rocm_available: bool = False
    virtualization: str = ""  # kvm, vmware, docker, none

    def to_dict(self) -> dict[str, Any]:
        return {
            "hostname": self.hostname,
            "kernel_version": self.kernel_version,
            "distro": self.distro,
            "distro_version": self.distro_version,
            "uptime_seconds": self.uptime_seconds,
            "cpu": self.cpu.to_dict(),
            "gpu": [g.to_dict() for g in self.gpu],
            "memory": self.memory.to_dict(),
            "storage": [s.to_dict() for s in self.storage],
            "network": [n.to_dict() for n in self.network],
            "has_nvidia_gpu": self.has_nvidia_gpu,
            "has_amd_gpu": self.has_amd_gpu,
            "cuda_available": self.cuda_available,
            "rocm_available": self.rocm_available,
            "virtualization": self.virtualization,
        }


class HardwareDetector:
    """
    Fast, comprehensive hardware detection for Cortex Linux.

    Detects:
    - CPU (vendor, model, cores, features)
    - GPU (NVIDIA, AMD, Intel)
    - Memory (RAM, swap)
    - Storage (disks, partitions)
    - Network interfaces
    - System info (kernel, distro)
    """

    CACHE_FILE = Path.home() / ".cortex" / "hardware_cache.json"
    CACHE_MAX_AGE_SECONDS = 3600  # 1 hour

    def __init__(self, use_cache: bool = True):
        self.use_cache = use_cache
        self._info: SystemInfo | None = None
        self._cache_lock = threading.RLock()  # Reentrant lock for cache file access

    def _uname(self):
        """Return uname-like info with nodename/release/machine attributes."""
        uname_fn = getattr(os, "uname", None)
        if callable(uname_fn):
            return uname_fn()
        return platform.uname()

    def detect(self, force_refresh: bool = False) -> SystemInfo:
        """
        Detect all hardware information.

        Args:
            force_refresh: Bypass cache and re-detect

        Returns:
            SystemInfo with complete hardware details
        """
        # Check cache first
        if self.use_cache and not force_refresh:
            cached = self._load_cache()
            if cached:
                return cached

        info = SystemInfo()

        # Detect everything
        self._detect_system(info)
        self._detect_cpu(info)
        self._detect_gpu(info)
        self._detect_memory(info)
        self._detect_storage(info)
        self._detect_network(info)
        self._detect_virtualization(info)

        # Cache results
        if self.use_cache:
            self._save_cache(info)

        self._info = info
        return info

    def detect_quick(self) -> dict[str, Any]:
        """
        Quick detection of essential hardware info.

        Returns minimal info for fast startup.
        """
        return {
            "cpu_cores": self._get_cpu_cores(),
            "ram_gb": self._get_ram_gb(),
            "has_nvidia": self._has_nvidia_gpu(),
            "disk_free_gb": self._get_disk_free_gb(),
        }

    def _load_cache(self) -> SystemInfo | None:
        """Load cached hardware info if valid (thread-safe)."""
        if not self.use_cache:
            return None

        with self._cache_lock:
            try:
                if not self.CACHE_FILE.exists():
                    return None

                # Check age
                import time

                if time.time() - self.CACHE_FILE.stat().st_mtime > self.CACHE_MAX_AGE_SECONDS:
                    return None

                with open(self.CACHE_FILE) as f:
                    data = json.load(f)

                # Reconstruct SystemInfo
                info = SystemInfo()
                info.hostname = data.get("hostname", "")
                info.kernel_version = data.get("kernel_version", "")
                info.distro = data.get("distro", "")
                info.distro_version = data.get("distro_version", "")

                # CPU
                cpu_data = data.get("cpu", {})
                info.cpu = CPUInfo(
                    vendor=CPUVendor(cpu_data.get("vendor", "unknown")),
                    model=cpu_data.get("model", "Unknown"),
                    cores=cpu_data.get("cores", 0),
                    threads=cpu_data.get("threads", 0),
                )

                # Memory
                mem_data = data.get("memory", {})
                info.memory = MemoryInfo(
                    total_mb=mem_data.get("total_mb", 0),
                    available_mb=mem_data.get("available_mb", 0),
                )

                # Capabilities
                info.has_nvidia_gpu = data.get("has_nvidia_gpu", False)
                info.cuda_available = data.get("cuda_available", False)

                return info

            except Exception as e:
                logger.debug(f"Cache load failed: {e}")
                return None

    def _save_cache(self, info: SystemInfo) -> None:
        """Save hardware info to cache (thread-safe)."""
        if not self.use_cache:
            return

        with self._cache_lock:
            try:
                self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(self.CACHE_FILE, "w") as f:
                    json.dump(info.to_dict(), f, indent=2)
            except Exception as e:
                logger.debug(f"Cache save failed: {e}")

    def _detect_system(self, info: SystemInfo):
        """Detect basic system information."""
        # Hostname
        try:
            info.hostname = self._uname().nodename
        except Exception:
            info.hostname = "unknown"

        # Kernel
        with contextlib.suppress(Exception):
            info.kernel_version = self._uname().release

        # Distro
        try:
            if Path("/etc/os-release").exists():
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("NAME="):
                            info.distro = line.split("=")[1].strip().strip('"')
                        elif line.startswith("VERSION_ID="):
                            info.distro_version = line.split("=")[1].strip().strip('"')
        except Exception:
            pass

        # Uptime
        try:
            with open("/proc/uptime") as f:
                info.uptime_seconds = int(float(f.read().split()[0]))
        except Exception:
            pass

    def _detect_cpu(self, info: SystemInfo):
        """Detect CPU information."""
        try:
            uname = self._uname()
            with open("/proc/cpuinfo") as f:
                content = f.read()

            # Model name
            match = re.search(r"model name\s*:\s*(.+)", content)
            if match:
                info.cpu.model = match.group(1).strip()

            # Vendor
            if "Intel" in info.cpu.model:
                info.cpu.vendor = CPUVendor.INTEL
            elif "AMD" in info.cpu.model:
                info.cpu.vendor = CPUVendor.AMD
            elif "ARM" in info.cpu.model or "aarch" in uname.machine:
                info.cpu.vendor = CPUVendor.ARM

            # Cores (physical)
            cores = set()
            for match in re.finditer(r"core id\s*:\s*(\d+)", content):
                cores.add(match.group(1))
            info.cpu.cores = len(cores) if cores else os.cpu_count() or 1

            # Threads
            info.cpu.threads = content.count("processor\t:")
            if info.cpu.threads == 0:
                info.cpu.threads = os.cpu_count() or 1

            # Frequency
            match = re.search(r"cpu MHz\s*:\s*([\d.]+)", content)
            if match:
                info.cpu.frequency_mhz = float(match.group(1))

            # Architecture
            info.cpu.architecture = uname.machine

            # Features
            match = re.search(r"flags\s*:\s*(.+)", content)
            if match:
                flags = match.group(1).split()
                # Keep only interesting features
                interesting = {"avx", "avx2", "avx512f", "sse4_1", "sse4_2", "aes", "fma"}
                info.cpu.features = [f for f in flags if f in interesting]

        except Exception as e:
            logger.debug(f"CPU detection failed: {e}")

    def _detect_gpu(self, info: SystemInfo):
        """Detect GPU information."""
        # Try lspci for basic detection
        try:
            result = subprocess.run(["lspci", "-nn"], capture_output=True, text=True, timeout=5)

            for line in result.stdout.split("\n"):
                parsed = self._parse_lspci_gpu_line(line, info)
                if parsed is not None:
                    info.gpu.append(parsed)

        except Exception as e:
            logger.debug(f"lspci GPU detection failed: {e}")

        # NVIDIA-specific detection
        if info.has_nvidia_gpu:
            self._detect_nvidia_details(info)

        # AMD-specific detection
        if info.has_amd_gpu:
            self._detect_amd_details(info)

    def _parse_lspci_gpu_line(self, line: str, info: SystemInfo) -> "GPUInfo | None":
        """Parse a single `lspci -nn` line into a GPUInfo if it looks like a GPU entry."""
        if "VGA" not in line and "3D" not in line and "Display" not in line:
            return None

        gpu = GPUInfo()

        pci_match = re.search(r"\[([0-9a-fA-F]{4}:[0-9a-fA-F]{4})\]", line)
        if pci_match:
            gpu.pci_id = pci_match.group(1)

        upper = line.upper()
        if "NVIDIA" in upper:
            gpu.vendor = GPUVendor.NVIDIA
            info.has_nvidia_gpu = True
            gpu.model = self._extract_gpu_model(line, "NVIDIA")
        elif "AMD" in upper or "ATI" in upper:
            gpu.vendor = GPUVendor.AMD
            info.has_amd_gpu = True
            gpu.model = self._extract_gpu_model(line, "AMD")
        elif "INTEL" in upper:
            gpu.vendor = GPUVendor.INTEL
            gpu.model = self._extract_gpu_model(line, "INTEL")

        return gpu

    def _extract_gpu_model(self, line: str, vendor: str) -> str:
        """Extract GPU model name from lspci line."""
        # Try to get the part after the vendor name (case-insensitive)
        try:
            match = re.search(re.escape(vendor), line, flags=re.IGNORECASE)
            if match:
                model = line[match.end() :].split("[")[0].strip()
                model = model.replace("Corporation", "").strip()
                return f"{vendor} {model}"
        except Exception as e:
            logger.debug(f"GPU model extraction failed for {vendor}: {e}")
        return f"{vendor} GPU"

    def _detect_nvidia_details(self, info: SystemInfo):
        """Detect NVIDIA-specific GPU details."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version,compute_cap",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                info.cuda_available = True

                for i, line in enumerate(result.stdout.strip().split("\n")):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 4 and i < len(info.gpu):
                        if info.gpu[i].vendor == GPUVendor.NVIDIA:
                            info.gpu[i].model = parts[0]
                            info.gpu[i].memory_mb = int(parts[1])
                            info.gpu[i].driver_version = parts[2]
                            info.gpu[i].compute_capability = parts[3]

        except FileNotFoundError:
            logger.debug("nvidia-smi not found")
        except Exception as e:
            logger.debug(f"NVIDIA detection failed: {e}")

    def _detect_amd_details(self, info: SystemInfo):
        """Detect AMD-specific GPU details."""
        try:
            # Check for ROCm
            result = subprocess.run(
                ["rocm-smi", "--showid"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info.rocm_available = True
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"AMD detection failed: {e}")

    def _detect_memory(self, info: SystemInfo):
        """Detect memory information."""
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        info.memory.total_mb = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"):
                        info.memory.available_mb = int(line.split()[1]) // 1024
                    elif line.startswith("SwapTotal:"):
                        info.memory.swap_total_mb = int(line.split()[1]) // 1024
                    elif line.startswith("SwapFree:"):
                        info.memory.swap_free_mb = int(line.split()[1]) // 1024
        except Exception as e:
            logger.debug(f"Memory detection failed: {e}")

    def _detect_storage(self, info: SystemInfo):
        """Detect storage information."""
        try:
            result = subprocess.run(
                ["df", "-BM", "--output=source,target,fstype,size,used,avail"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            for line in result.stdout.strip().split("\n")[1:]:
                parts = line.split()
                if len(parts) >= 6:
                    device = parts[0]

                    # Skip pseudo filesystems
                    if device.startswith("/dev/") or device == "overlay":
                        storage = StorageInfo(
                            device=device,
                            mount_point=parts[1],
                            filesystem=parts[2],
                            total_gb=float(parts[3].rstrip("M")) / 1024,
                            used_gb=float(parts[4].rstrip("M")) / 1024,
                            available_gb=float(parts[5].rstrip("M")) / 1024,
                        )
                        info.storage.append(storage)

        except Exception as e:
            logger.debug(f"Storage detection failed: {e}")

    def _detect_network(self, info: SystemInfo):
        """Detect network interface information."""
        try:
            # Get interfaces from /sys/class/net
            net_path = Path("/sys/class/net")

            for iface_dir in net_path.iterdir():
                if iface_dir.name == "lo":
                    continue

                net = NetworkInfo(interface=iface_dir.name)

                # Check if wireless
                net.is_wireless = (iface_dir / "wireless").exists()

                # Get MAC address
                with contextlib.suppress(builtins.BaseException):
                    net.mac_address = (iface_dir / "address").read_text().strip()

                # Get IP address
                try:
                    result = subprocess.run(
                        ["ip", "-4", "addr", "show", iface_dir.name],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    match = re.search(r"inet\s+([\d.]+)", result.stdout)
                    if match:
                        net.ip_address = match.group(1)
                except Exception:
                    pass

                # Get speed
                try:
                    speed = (iface_dir / "speed").read_text().strip()
                    net.speed_mbps = int(speed)
                except Exception:
                    pass

                if net.ip_address:  # Only add if has IP
                    info.network.append(net)

        except Exception as e:
            logger.debug(f"Network detection failed: {e}")

    def _detect_virtualization(self, info: SystemInfo):
        """Detect if running in virtualized environment."""
        try:
            result = subprocess.run(
                ["systemd-detect-virt"], capture_output=True, text=True, timeout=2
            )
            virt = result.stdout.strip()
            if virt and virt != "none":
                info.virtualization = virt
        except Exception:
            pass

        # Docker detection
        if Path("/.dockerenv").exists():
            info.virtualization = "docker"

    # Quick detection methods
    def _get_cpu_cores(self) -> int:
        """Quick CPU core count."""
        return os.cpu_count() or 1

    def _get_ram_gb(self) -> float:
        """Quick RAM amount in GB."""
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / 1024 / 1024, 1)
        except Exception:
            pass
        return 0.0

    def _has_nvidia_gpu(self) -> bool:
        """Quick NVIDIA GPU check."""
        try:
            result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=2)
            return "NVIDIA" in result.stdout.upper()
        except Exception:
            return False

    def _get_disk_free_gb(self) -> float:
        """Quick disk free space on root."""
        try:
            statvfs_fn = getattr(os, "statvfs", None)
            if callable(statvfs_fn):
                statvfs = statvfs_fn("/")
                return round((statvfs.f_frsize * statvfs.f_bavail) / (1024**3), 1)

            root_path = os.path.abspath(os.sep)
            _total, _used, free = shutil.disk_usage(root_path)
            return round(free / (1024**3), 1)
        except Exception:
            return 0.0


# Convenience functions
_detector_instance = None


def get_detector() -> HardwareDetector:
    """Get the global hardware detector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = HardwareDetector()
    return _detector_instance


def detect_hardware(force_refresh: bool = False) -> SystemInfo:
    """Detect all hardware information."""
    return get_detector().detect(force_refresh=force_refresh)


def detect_quick() -> dict[str, Any]:
    """Quick hardware detection."""
    return get_detector().detect_quick()


def get_gpu_info() -> list[GPUInfo]:
    """Get GPU information only."""
    info = detect_hardware()
    return info.gpu


def has_nvidia_gpu() -> bool:
    """Check if system has NVIDIA GPU."""
    return detect_quick()["has_nvidia"]


def get_ram_gb() -> float:
    """Get RAM in GB."""
    return detect_quick()["ram_gb"]


def get_cpu_cores() -> int:
    """Get CPU core count."""
    return detect_quick()["cpu_cores"]


if __name__ == "__main__":
    import time

    print("Hardware Detection Demo")
    print("=" * 60)

    detector = HardwareDetector(use_cache=False)

    # Quick detection
    print("\n⚡ Quick Detection:")
    start = time.time()
    quick = detector.detect_quick()
    print(f"  Time: {(time.time() - start) * 1000:.0f}ms")
    print(f"  CPU Cores: {quick['cpu_cores']}")
    print(f"  RAM: {quick['ram_gb']} GB")
    print(f"  NVIDIA GPU: {quick['has_nvidia']}")
    print(f"  Disk Free: {quick['disk_free_gb']} GB")

    # Full detection
    print("\n🔍 Full Detection:")
    start = time.time()
    info = detector.detect()
    print(f"  Time: {(time.time() - start) * 1000:.0f}ms")

    print("\n📋 System:")
    print(f"  Hostname: {info.hostname}")
    print(f"  Distro: {info.distro} {info.distro_version}")
    print(f"  Kernel: {info.kernel_version}")

    print("\n🔧 CPU:")
    print(f"  Model: {info.cpu.model}")
    print(f"  Vendor: {info.cpu.vendor.value}")
    print(f"  Cores: {info.cpu.cores} ({info.cpu.threads} threads)")
    print(f"  Features: {', '.join(info.cpu.features[:5])}")

    print("\n🎮 GPU:")
    for gpu in info.gpu:
        print(f"  {gpu.model}")
        if gpu.memory_mb:
            print(f"    Memory: {gpu.memory_mb} MB")
        if gpu.driver_version:
            print(f"    Driver: {gpu.driver_version}")
    if not info.gpu:
        print("  No dedicated GPU detected")

    print("\n💾 Memory:")
    print(f"  RAM: {info.memory.total_gb} GB ({info.memory.available_gb} GB available)")
    print(f"  Swap: {info.memory.swap_total_mb} MB")

    print("\n💿 Storage:")
    for disk in info.storage[:3]:
        print(
            f"  {disk.mount_point}: {disk.available_gb:.1f} GB free / {disk.total_gb:.1f} GB ({disk.usage_percent}% used)"
        )

    print("\n🌐 Network:")
    for net in info.network:
        print(f"  {net.interface}: {net.ip_address} ({'wireless' if net.is_wireless else 'wired'})")

    print("\n✨ Capabilities:")
    print(f"  NVIDIA GPU: {info.has_nvidia_gpu}")
    print(f"  CUDA Available: {info.cuda_available}")
    print(f"  AMD GPU: {info.has_amd_gpu}")
    print(f"  ROCm Available: {info.rocm_available}")
    if info.virtualization:
        print(f"  Virtualization: {info.virtualization}")

    print("\n✅ Detection complete!")
