#!/usr/bin/env python3
"""
Cortex Linux Hardware Detection Module

Detects AI accelerators (GPUs, NPUs) and provides hardware-aware recommendations
for model selection and optimization.

Usage:
    from cortex.kernel_features.hardware_detect import detect_accelerators
    
    hardware = detect_accelerators()
    print(hardware.to_json())
"""

import json
import subprocess
import re
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum


class AcceleratorType(Enum):
    NVIDIA_GPU = "nvidia"
    AMD_GPU = "amd"
    INTEL_GPU = "intel"
    INTEL_NPU = "intel_npu"
    AMD_NPU = "amd_npu"
    QUALCOMM_NPU = "qualcomm_npu"
    APPLE_SILICON = "apple"
    UNKNOWN = "unknown"


@dataclass
class Accelerator:
    """Represents a single AI accelerator (GPU/NPU)."""
    type: AcceleratorType
    name: str
    vendor: str
    vram_gb: float = 0.0
    compute_units: int = 0
    compute_capability: str = ""
    driver_version: str = ""
    pci_bus_id: str = ""
    index: int = 0
    features: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['type'] = self.type.value
        return d


@dataclass 
class HardwareProfile:
    """Complete hardware profile for AI workloads."""
    accelerators: List[Accelerator] = field(default_factory=list)
    total_vram_gb: float = 0.0
    total_system_ram_gb: float = 0.0
    cpu_cores: int = 0
    cpu_model: str = ""
    recommended_models: List[str] = field(default_factory=list)
    max_model_size_gb: float = 0.0
    max_context_length: int = 0
    optimization_hints: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['accelerators'] = [a.to_dict() if isinstance(a, Accelerator) else a for a in self.accelerators]
        return d
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def run_command(cmd: List[str], timeout: int = 10) -> Optional[str]:
    """Run a shell command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        pass
    return None


def detect_nvidia_gpus() -> List[Accelerator]:
    """Detect NVIDIA GPUs using nvidia-smi."""
    gpus = []
    
    # Check if nvidia-smi exists
    output = run_command([
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,driver_version,pci.bus_id,compute_cap",
        "--format=csv,noheader,nounits"
    ])
    
    if not output:
        return gpus
    
    for line in output.strip().split('\n'):
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 6:
            try:
                vram_mb = float(parts[2])
                gpu = Accelerator(
                    type=AcceleratorType.NVIDIA_GPU,
                    name=parts[1],
                    vendor="NVIDIA",
                    vram_gb=round(vram_mb / 1024, 1),
                    compute_capability=parts[5],
                    driver_version=parts[3],
                    pci_bus_id=parts[4],
                    index=int(parts[0]),
                    features=["cuda", "tensor_cores"] if float(parts[5]) >= 7.0 else ["cuda"]
                )
                gpus.append(gpu)
            except (ValueError, IndexError):
                continue
    
    return gpus


def detect_amd_gpus() -> List[Accelerator]:
    """Detect AMD GPUs using rocm-smi."""
    gpus = []
    
    # Try rocm-smi first
    output = run_command(["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"])
    
    if output:
        try:
            data = json.loads(output)
            for card_id, card_info in data.items():
                if card_id.startswith("card"):
                    gpu = Accelerator(
                        type=AcceleratorType.AMD_GPU,
                        name=card_info.get("Card series", "AMD GPU"),
                        vendor="AMD",
                        vram_gb=round(card_info.get("VRAM Total Memory (B)", 0) / (1024**3), 1),
                        index=int(card_id.replace("card", "")),
                        features=["rocm", "hip"]
                    )
                    gpus.append(gpu)
        except (json.JSONDecodeError, KeyError):
            pass
    
    # Fallback to lspci
    if not gpus:
        output = run_command(["lspci", "-nn"])
        if output:
            for line in output.split('\n'):
                if "VGA" in line and ("AMD" in line or "ATI" in line):
                    # Extract device name
                    match = re.search(r'\[AMD[^\]]*\]\s*([^[]+)', line)
                    name = match.group(1).strip() if match else "AMD GPU"
                    gpu = Accelerator(
                        type=AcceleratorType.AMD_GPU,
                        name=name,
                        vendor="AMD",
                        features=["rocm"]
                    )
                    gpus.append(gpu)
    
    return gpus


def detect_intel_gpus() -> List[Accelerator]:
    """Detect Intel GPUs (Arc, integrated)."""
    gpus = []
    
    # Try intel_gpu_top
    output = run_command(["lspci", "-nn"])
    
    if output:
        for line in output.split('\n'):
            if "VGA" in line and "Intel" in line:
                # Check if Arc GPU
                is_arc = "Arc" in line or "DG2" in line or "Alchemist" in line
                
                # Extract device name
                match = re.search(r'Intel Corporation\s*([^[]+)', line)
                name = match.group(1).strip() if match else "Intel GPU"
                
                gpu = Accelerator(
                    type=AcceleratorType.INTEL_GPU,
                    name=name,
                    vendor="Intel",
                    features=["oneapi", "level_zero"] if is_arc else ["vaapi"],
                    vram_gb=16.0 if is_arc else 0.0  # Arc A770 has 16GB
                )
                gpus.append(gpu)
    
    return gpus


def detect_intel_npu() -> List[Accelerator]:
    """Detect Intel NPU (Meteor Lake+)."""
    npus = []
    
    # Check for Intel NPU device
    output = run_command(["lspci", "-nn"])
    
    if output and "Intel" in output and ("NPU" in output or "Neural" in output or "AI Boost" in output):
        npu = Accelerator(
            type=AcceleratorType.INTEL_NPU,
            name="Intel NPU",
            vendor="Intel",
            compute_units=10,  # Typical TOPS for Meteor Lake
            features=["openvino", "int8", "int4"]
        )
        npus.append(npu)
    
    # Also check sysfs
    if os.path.exists("/sys/class/accel"):
        for device in os.listdir("/sys/class/accel"):
            if "intel" in device.lower():
                npu = Accelerator(
                    type=AcceleratorType.INTEL_NPU,
                    name="Intel NPU",
                    vendor="Intel",
                    features=["openvino"]
                )
                npus.append(npu)
                break
    
    return npus


def detect_amd_npu() -> List[Accelerator]:
    """Detect AMD NPU (Ryzen AI)."""
    npus = []
    
    # Check for AMD XDNA device
    if os.path.exists("/dev/accel/accel0"):
        # Check if it's AMD XDNA
        output = run_command(["lspci", "-nn"])
        if output and "AMD" in output and ("XDNA" in output or "Ryzen AI" in output or "IPU" in output):
            npu = Accelerator(
                type=AcceleratorType.AMD_NPU,
                name="AMD Ryzen AI NPU",
                vendor="AMD",
                compute_units=16,  # TOPS
                features=["xdna", "int8", "int4"]
            )
            npus.append(npu)
    
    return npus


def detect_apple_silicon() -> List[Accelerator]:
    """Detect Apple Silicon (M1/M2/M3)."""
    accelerators = []
    
    # Check if running on macOS
    output = run_command(["sysctl", "-n", "machdep.cpu.brand_string"])
    
    if output and "Apple" in output:
        # Get chip info
        chip_name = output.strip()
        
        # Determine GPU cores and memory based on chip
        gpu_cores = 8  # Default
        unified_memory = 8  # Default
        
        if "M1" in chip_name:
            gpu_cores = 8 if "Pro" not in chip_name else 16
            unified_memory = 16 if "Pro" in chip_name else 8
        elif "M2" in chip_name:
            gpu_cores = 10 if "Pro" not in chip_name else 19
            unified_memory = 24 if "Pro" in chip_name else 8
        elif "M3" in chip_name:
            gpu_cores = 10 if "Pro" not in chip_name else 18
            unified_memory = 36 if "Pro" in chip_name else 8
        elif "M4" in chip_name:
            gpu_cores = 10 if "Pro" not in chip_name else 20
            unified_memory = 48 if "Pro" in chip_name else 16
        
        accelerator = Accelerator(
            type=AcceleratorType.APPLE_SILICON,
            name=chip_name,
            vendor="Apple",
            vram_gb=unified_memory,  # Unified memory
            compute_units=gpu_cores,
            features=["metal", "coreml", "neural_engine", "unified_memory"]
        )
        accelerators.append(accelerator)
    
    return accelerators


def get_system_ram_gb() -> float:
    """Get total system RAM in GB."""
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 1)
    except (FileNotFoundError, ValueError):
        pass
    
    # macOS fallback
    output = run_command(["sysctl", "-n", "hw.memsize"])
    if output:
        try:
            return round(int(output) / (1024**3), 1)
        except ValueError:
            pass
    
    return 0.0


def get_cpu_info() -> tuple:
    """Get CPU model and core count."""
    cores = os.cpu_count() or 0
    model = ""
    
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("model name"):
                    model = line.split(":")[1].strip()
                    break
    except FileNotFoundError:
        # macOS fallback
        output = run_command(["sysctl", "-n", "machdep.cpu.brand_string"])
        if output:
            model = output.strip()
    
    return model, cores


def recommend_models(total_vram_gb: float, system_ram_gb: float, has_npu: bool) -> List[str]:
    """Recommend LLM models based on available hardware."""
    recommendations = []
    
    # Available memory for inference (use GPU VRAM if available, else system RAM)
    available_gb = total_vram_gb if total_vram_gb > 0 else system_ram_gb * 0.7
    
    if available_gb >= 48:
        recommendations.extend([
            "llama3.1-70b-q4",
            "qwen2.5-72b-q4",
            "deepseek-coder-33b",
            "mixtral-8x22b-q4"
        ])
    
    if available_gb >= 24:
        recommendations.extend([
            "llama3.1-70b-q2",
            "qwen2.5-32b",
            "codellama-34b-q4",
            "deepseek-coder-33b-q4"
        ])
    
    if available_gb >= 16:
        recommendations.extend([
            "llama3.1-8b",
            "mistral-7b",
            "qwen2.5-14b",
            "codellama-13b"
        ])
    
    if available_gb >= 8:
        recommendations.extend([
            "llama3.2-3b",
            "phi-3-mini",
            "gemma-2b",
            "qwen2.5-7b-q4"
        ])
    
    if available_gb >= 4:
        recommendations.extend([
            "tinyllama-1.1b",
            "phi-2",
            "qwen2.5-1.5b"
        ])
    
    if has_npu:
        recommendations.append("phi-3-mini-npu")
        recommendations.append("qwen2.5-1.5b-npu")
    
    return recommendations[:10]  # Return top 10


def calculate_max_context(total_vram_gb: float, model_size_gb: float = 4.0) -> int:
    """Estimate maximum context length based on available memory."""
    # KV cache memory = 2 * num_layers * hidden_size * context_length * bytes_per_param
    # Rough estimate: 1GB VRAM ≈ 8K context for 7B model
    
    available_for_kv = total_vram_gb - model_size_gb
    if available_for_kv <= 0:
        return 2048  # Minimum
    
    # Rough scaling: 8K context per GB of KV cache space
    max_context = int(available_for_kv * 8192)
    
    # Cap at reasonable limits
    return min(max_context, 131072)  # 128K max


def generate_optimization_hints(profile: HardwareProfile) -> List[str]:
    """Generate optimization hints based on detected hardware."""
    hints = []
    
    # Memory hints
    if profile.total_system_ram_gb < 16:
        hints.append("Consider upgrading to 16GB+ RAM for better model loading")
    
    if profile.total_vram_gb == 0 and profile.total_system_ram_gb >= 16:
        hints.append("No GPU detected - models will run on CPU (slower but functional)")
        hints.append("Consider quantized models (Q4, Q2) for better CPU performance")
    
    # GPU hints
    for acc in profile.accelerators:
        if acc.type == AcceleratorType.NVIDIA_GPU:
            if acc.compute_capability and float(acc.compute_capability) >= 8.0:
                hints.append(f"{acc.name}: Enable Flash Attention 2 for best performance")
            if acc.vram_gb >= 24:
                hints.append(f"{acc.name}: Can run 70B models with 4-bit quantization")
        
        if acc.type == AcceleratorType.AMD_GPU:
            hints.append(f"{acc.name}: Use ROCm backend for optimal performance")
        
        if acc.type == AcceleratorType.APPLE_SILICON:
            hints.append(f"{acc.name}: Use Metal backend via llama.cpp or MLX")
            hints.append("Unified memory allows larger models than VRAM alone suggests")
    
    # NPU hints
    has_npu = any(acc.type in [AcceleratorType.INTEL_NPU, AcceleratorType.AMD_NPU] 
                  for acc in profile.accelerators)
    if has_npu:
        hints.append("NPU detected - use INT4/INT8 quantized models for best NPU performance")
        hints.append("Hybrid CPU+NPU inference available for larger models")
    
    # Huge pages hint
    hints.append("Run 'cortex optimize-system' to apply sysctl tuning for LLM workloads")
    
    return hints


def detect_accelerators() -> HardwareProfile:
    """
    Main detection function - detects all AI accelerators and builds hardware profile.
    
    Returns:
        HardwareProfile with detected hardware and recommendations
    """
    profile = HardwareProfile()
    
    # Detect all accelerator types
    profile.accelerators.extend(detect_nvidia_gpus())
    profile.accelerators.extend(detect_amd_gpus())
    profile.accelerators.extend(detect_intel_gpus())
    profile.accelerators.extend(detect_intel_npu())
    profile.accelerators.extend(detect_amd_npu())
    profile.accelerators.extend(detect_apple_silicon())
    
    # Calculate totals
    profile.total_vram_gb = sum(acc.vram_gb for acc in profile.accelerators)
    profile.total_system_ram_gb = get_system_ram_gb()
    profile.cpu_model, profile.cpu_cores = get_cpu_info()
    
    # Check for NPU
    has_npu = any(acc.type in [AcceleratorType.INTEL_NPU, AcceleratorType.AMD_NPU] 
                  for acc in profile.accelerators)
    
    # Generate recommendations
    profile.recommended_models = recommend_models(
        profile.total_vram_gb, 
        profile.total_system_ram_gb,
        has_npu
    )
    
    # Calculate limits
    profile.max_model_size_gb = max(profile.total_vram_gb, profile.total_system_ram_gb * 0.7)
    profile.max_context_length = calculate_max_context(profile.total_vram_gb)
    
    # Generate hints
    profile.optimization_hints = generate_optimization_hints(profile)
    
    return profile


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Cortex Hardware Detection")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", action="store_true", help="Only output recommendations")
    args = parser.parse_args()
    
    profile = detect_accelerators()
    
    if args.json:
        print(profile.to_json())
    elif args.quiet:
        print("Recommended models:")
        for model in profile.recommended_models:
            print(f"  - {model}")
    else:
        print("=" * 60)
        print("CORTEX LINUX HARDWARE DETECTION")
        print("=" * 60)
        print()
        
        print(f"CPU: {profile.cpu_model} ({profile.cpu_cores} cores)")
        print(f"System RAM: {profile.total_system_ram_gb} GB")
        print()
        
        if profile.accelerators:
            print("ACCELERATORS:")
            for acc in profile.accelerators:
                print(f"  [{acc.index}] {acc.name}")
                print(f"      Type: {acc.type.value}")
                print(f"      VRAM: {acc.vram_gb} GB")
                if acc.compute_capability:
                    print(f"      Compute: {acc.compute_capability}")
                if acc.features:
                    print(f"      Features: {', '.join(acc.features)}")
                print()
        else:
            print("No GPU/NPU accelerators detected")
            print("Models will run on CPU")
            print()
        
        print(f"Total VRAM: {profile.total_vram_gb} GB")
        print(f"Max model size: {profile.max_model_size_gb:.1f} GB")
        print(f"Max context length: {profile.max_context_length:,}")
        print()
        
        print("RECOMMENDED MODELS:")
        for model in profile.recommended_models[:5]:
            print(f"  ✓ {model}")
        print()
        
        print("OPTIMIZATION HINTS:")
        for hint in profile.optimization_hints:
            print(f"  → {hint}")
