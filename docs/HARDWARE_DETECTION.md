# Hardware Detection Module

**Issue:** #253  
**Status:** Ready for Review  
**Bounty:** As specified in issue (+ bonus after funding)

## Overview

Instant, comprehensive hardware detection on first run. Automatically identifies CPU, GPU, RAM, storage, and provides optimization recommendations for package installation.

## Features

| Feature | Description |
|---------|-------------|
| Instant Detection | Sub-second hardware scan |
| GPU Support | NVIDIA, AMD, Intel detection with driver info |
| CUDA Detection | Version and compute capability |
| Smart Recommendations | Hardware-aware package suggestions |
| JSON Export | Machine-readable output |

## Quick Start

```python
from cortex.hardware_detection import detect_hardware, get_recommendations

# Detect all hardware
info = detect_hardware()
print(f"CPU: {info.cpu.model}")
print(f"GPU: {info.gpu.model if info.gpu.detected else 'None'}")
print(f"RAM: {info.memory.total_gb:.1f} GB")

# Get recommendations
recs = get_recommendations(info)
for rec in recs:
    print(f"• {rec}")
```

## CLI Usage

```bash
# Show hardware info
cortex hardware

# JSON output
cortex hardware --json

# Check GPU only
cortex hardware --gpu

# Get recommendations
cortex hardware --recommend
```

## API Reference

### detect_hardware()

Detects all system hardware and returns `HardwareInfo` object.

```python
info = detect_hardware()

# CPU info
info.cpu.model          # "AMD Ryzen 9 5900X"
info.cpu.cores          # 12
info.cpu.threads        # 24
info.cpu.architecture   # "x86_64"

# GPU info
info.gpu.detected       # True
info.gpu.model          # "NVIDIA GeForce RTX 4090"
info.gpu.vendor         # "nvidia"
info.gpu.driver         # "535.154.05"
info.gpu.cuda_version   # "12.3"
info.gpu.vram_gb        # 24.0

# Memory info
info.memory.total_gb    # 64.0
info.memory.available_gb # 48.5

# Storage info
info.storage.devices    # [StorageDevice(...), ...]
info.storage.total_gb   # 2000.0
```

### get_recommendations()

Returns hardware-aware package recommendations.

```python
recs = get_recommendations(info)
# Returns: [
#   "nvidia-driver-535 (GPU detected)",
#   "cuda-toolkit-12-3 (CUDA available)",
#   "python3-venv (development)",
# ]
```

## Detection Methods

### CPU Detection

```python
# Sources:
# 1. /proc/cpuinfo
# 2. lscpu command
# 3. platform module fallback
```

### GPU Detection

```python
# NVIDIA: nvidia-smi
# AMD: rocm-smi, lspci
# Intel: lspci
```

### Memory Detection

```python
# Sources:
# 1. /proc/meminfo
# 2. free command fallback
```

## Data Classes

### HardwareInfo

```python
@dataclass
class HardwareInfo:
    cpu: CPUInfo
    gpu: GPUInfo
    memory: MemoryInfo
    storage: StorageInfo
    network: NetworkInfo
    detected_at: datetime
```

### CPUInfo

```python
@dataclass
class CPUInfo:
    model: str
    vendor: str
    cores: int
    threads: int
    architecture: str
    frequency_mhz: float
    cache_mb: float
    flags: List[str]  # CPU features
```

### GPUInfo

```python
@dataclass
class GPUInfo:
    detected: bool
    model: str
    vendor: str  # nvidia, amd, intel
    driver: str
    vram_gb: float
    cuda_version: str
    compute_capability: str
```

## Integration

### With Package Manager

```python
from cortex.hardware_detection import detect_hardware
from cortex.package_manager import install

info = detect_hardware()

if info.gpu.detected and info.gpu.vendor == "nvidia":
    # Install with GPU optimizations
    install("tensorflow", gpu=True)
else:
    # CPU-only installation
    install("tensorflow")
```

### With First-Run Wizard

```python
# Automatically called during setup
from cortex.first_run_wizard import FirstRunWizard

wizard = FirstRunWizard()
wizard._detect_system()  # Uses hardware_detection internally
```

## Output Formats

### Human-Readable

```
System Hardware
===============
CPU: AMD Ryzen 9 5900X 12-Core @ 3.70 GHz
     Architecture: x86_64, Threads: 24

GPU: NVIDIA GeForce RTX 4090
     Driver: 535.154.05, CUDA: 12.3
     VRAM: 24 GB

Memory: 64.0 GB total, 48.5 GB available

Storage:
  /dev/nvme0n1: 1000 GB (NVMe SSD)
  /dev/sda: 2000 GB (HDD)
```

### JSON

```json
{
  "cpu": {
    "model": "AMD Ryzen 9 5900X",
    "cores": 12,
    "threads": 24
  },
  "gpu": {
    "detected": true,
    "model": "NVIDIA GeForce RTX 4090",
    "cuda_version": "12.3"
  },
  "memory": {
    "total_gb": 64.0,
    "available_gb": 48.5
  }
}
```

## Performance

| Operation | Time |
|-----------|------|
| CPU detection | <50ms |
| GPU detection | <200ms |
| Full scan | <500ms |

## Testing

```bash
pytest tests/test_hardware_detection.py -v
pytest tests/test_hardware_detection.py --cov=cortex.hardware_detection
```

---

**Closes:** #253
