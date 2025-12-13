# Cortex Linux Kernel Configuration Guide

This document describes the recommended Linux kernel configuration flags for building an LLM-optimized kernel.

## Quick Start

If you just want to optimize an existing system without rebuilding the kernel:

```bash
# Apply sysctl optimizations
sudo cp sysctl.d/99-cortex-llm.conf /etc/sysctl.d/
sudo sysctl -p /etc/sysctl.d/99-cortex-llm.conf

# Install systemd templates
sudo cp systemd/*.service systemd/*.slice /usr/lib/systemd/system/
sudo systemctl daemon-reload
```

## Kernel Configuration Flags

### Memory Management (Critical for LLMs)

```kconfig
# Transparent Huge Pages - automatic huge page allocation
# Essential for large model weight memory mapping
CONFIG_TRANSPARENT_HUGEPAGE=y
CONFIG_TRANSPARENT_HUGEPAGE_ALWAYS=y

# Heterogeneous Memory Management - unified CPU/GPU memory
# Enables efficient memory sharing between CPU and accelerators
CONFIG_HMM_MIRROR=y
CONFIG_DEVICE_PRIVATE=y

# Memory tiers for CXL and tiered memory systems
# Allows using CXL memory expansion for larger models
CONFIG_MEMORY_TIER=y

# NUMA support for multi-socket systems
CONFIG_NUMA=y
CONFIG_NUMA_BALANCING=y

# Memory compaction for huge page allocation
CONFIG_COMPACTION=y

# KSM for weight deduplication across processes
CONFIG_KSM=y
```

### I/O Subsystem (Fast Model Loading)

```kconfig
# io_uring - high-performance async I/O
# Enables zero-copy model weight loading
CONFIG_IO_URING=y

# NVMe optimizations
CONFIG_BLK_DEV_NVME=y
CONFIG_NVME_MULTIPATH=y

# Direct I/O support
CONFIG_DIRECT_IO=y
```

### eBPF (Custom Scheduling)

```kconfig
# Core eBPF support
CONFIG_BPF=y
CONFIG_BPF_SYSCALL=y
CONFIG_BPF_JIT=y
CONFIG_BPF_JIT_ALWAYS_ON=y

# eBPF scheduler extensions
CONFIG_BPF_LSM=y
CONFIG_DEBUG_INFO_BTF=y
CONFIG_PAHOLE_HAS_SPLIT_BTF=y
CONFIG_DEBUG_INFO_BTF_MODULES=y

# Scheduler class extensions (for custom ML schedulers)
CONFIG_SCHED_CLASS_EXT=y
```

### GPU/Accelerator Support

```kconfig
# NVIDIA GPU support
CONFIG_DRM=y
CONFIG_DRM_NOUVEAU=m  # Open source driver
# Note: Proprietary NVIDIA driver installed separately

# AMD GPU support (includes ROCm compatibility)
CONFIG_DRM_AMDGPU=m
CONFIG_DRM_AMDGPU_SI=y
CONFIG_DRM_AMDGPU_CIK=y
CONFIG_HSA_AMD=y

# Intel GPU support (Arc, integrated)
CONFIG_DRM_I915=m
CONFIG_DRM_XE=m

# Intel NPU support (Meteor Lake+)
CONFIG_INTEL_NPU=m

# AMD NPU support (Ryzen AI)
CONFIG_ACCEL_AMDXDNA=m

# Generic accelerator framework
CONFIG_DRM_ACCEL=y
```

### CXL Memory Expansion

```kconfig
# CXL support for memory expansion
# Enables running models larger than system RAM
CONFIG_CXL_BUS=y
CONFIG_CXL_PCI=y
CONFIG_CXL_ACPI=y
CONFIG_CXL_PMEM=y
CONFIG_CXL_MEM=y
CONFIG_CXL_PORT=y
CONFIG_CXL_REGION=y
```

### Security Features

```kconfig
# Secure boot support
CONFIG_EFI=y
CONFIG_EFI_STUB=y
CONFIG_SECURITY_LOCKDOWN_LSM=y

# User namespace for container isolation
CONFIG_USER_NS=y

# Seccomp for syscall filtering
CONFIG_SECCOMP=y
CONFIG_SECCOMP_FILTER=y

# Firejail/sandbox support
CONFIG_NAMESPACES=y
CONFIG_NET_NS=y
CONFIG_PID_NS=y
CONFIG_IPC_NS=y
```

### Networking (Distributed Inference)

```kconfig
# High-performance networking
CONFIG_NET=y
CONFIG_INET=y
CONFIG_IPV6=y

# RDMA for tensor transfer
CONFIG_INFINIBAND=m
CONFIG_INFINIBAND_USER_ACCESS=m
CONFIG_MLX4_INFINIBAND=m
CONFIG_MLX5_INFINIBAND=m

# TCP optimizations
CONFIG_TCP_CONG_BBR=y
CONFIG_DEFAULT_TCP_CONG="bbr"
```

### Real-Time Scheduling (Optional)

```kconfig
# For latency-sensitive inference
CONFIG_PREEMPT=y
CONFIG_PREEMPT_VOLUNTARY=n
CONFIG_HZ_1000=y
CONFIG_NO_HZ_FULL=y
```

## Building the Kernel

### Ubuntu/Debian

```bash
# Install build dependencies
sudo apt install build-essential libncurses-dev bison flex libssl-dev \
    libelf-dev dwarves zstd

# Get kernel source
apt source linux-image-$(uname -r)
cd linux-*

# Copy current config as base
cp /boot/config-$(uname -r) .config

# Apply Cortex optimizations
cat >> .config << 'EOF'
CONFIG_TRANSPARENT_HUGEPAGE=y
CONFIG_TRANSPARENT_HUGEPAGE_ALWAYS=y
CONFIG_HMM_MIRROR=y
CONFIG_IO_URING=y
CONFIG_BPF_SYSCALL=y
CONFIG_BPF_JIT_ALWAYS_ON=y
CONFIG_DRM_AMDGPU=m
CONFIG_DRM_XE=m
EOF

# Update config
make olddefconfig

# Build
make -j$(nproc) bindeb-pkg

# Install
sudo dpkg -i ../linux-image-*.deb ../linux-headers-*.deb
```

### Fedora

```bash
# Install build dependencies
sudo dnf install fedpkg fedora-packager rpmdevtools ncurses-devel \
    pesign grubby bison flex openssl-devel elfutils-libelf-devel dwarves

# Get kernel source
koji download-build --arch=src kernel-$(uname -r | sed 's/.fc.*//')
rpm -ivh kernel-*.src.rpm

# Apply config changes and rebuild
cd ~/rpmbuild/SPECS
rpmbuild -bb kernel.spec
```

## Verifying Configuration

After booting with the new kernel:

```bash
# Check huge pages
cat /proc/meminfo | grep -i huge

# Check eBPF
cat /proc/config.gz | gunzip | grep CONFIG_BPF

# Check HMM
cat /proc/config.gz | gunzip | grep CONFIG_HMM

# Check accelerator support
lsmod | grep -E "(amdgpu|nvidia|i915|xe)"

# Check CXL
lspci | grep -i cxl
```

## Performance Validation

```bash
# Run Cortex benchmark
cortex benchmark --model llama3-8b

# Compare with stock kernel
# Expected improvements:
# - Model load time: 2-3x faster (huge pages)
# - Inference latency: 10-20% lower (scheduling)
# - Memory efficiency: 30% better (HMM)
```

## Troubleshooting

### Huge Pages Not Available

```bash
# Check current allocation
cat /proc/meminfo | grep HugePages

# Allocate at boot (add to /etc/default/grub)
GRUB_CMDLINE_LINUX="hugepages=4096"
sudo update-grub
```

### GPU Not Detected

```bash
# Check IOMMU
dmesg | grep -i iommu

# Disable IOMMU if causing issues (add to kernel cmdline)
iommu=soft
```

### eBPF Programs Fail to Load

```bash
# Check BTF availability
ls /sys/kernel/btf/vmlinux

# If missing, rebuild kernel with CONFIG_DEBUG_INFO_BTF=y
```

## Next Steps

1. Apply sysctl tuning: `sudo sysctl -p /etc/sysctl.d/99-cortex-llm.conf`
2. Install systemd templates: See `systemd/` directory
3. Run hardware detection: `cortex detect-hardware`
4. Start a model: `systemctl start cortex-model@llama3-8b`
