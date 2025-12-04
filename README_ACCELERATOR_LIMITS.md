# Cortex Accelerator-Aware Resource Limits

A cgroups v2 wrapper for managing GPU, CPU, and memory resources for AI workloads with workload presets.

## Quick Start

```bash
# Create a profile with the inference preset and 2 GPUs
cortex limits create inference-job --preset inference --gpus 2

# Apply limits to a running process
cortex limits apply inference-job --pid 12345

# Get environment variables for new processes
eval $(cortex limits env inference-job)

# Check status
cortex limits status inference-job
```

## Workload Presets

| Preset | CPU | Memory | GPU | OOM Score | Use Case |
|--------|-----|--------|-----|-----------|----------|
| inference | 4 cores | 32G | 100% | -500 | Low-latency serving |
| training | 16 cores | 128G | 100% | -800 | Long training jobs |
| batch | 8 cores | 64G | 80% | 0 | Background processing |
| interactive | 2 cores | 16G | 50% | -200 | Development |

## Features

- **cgroups v2 unified hierarchy support**: Full integration with modern Linux cgroups
- **Workload presets**: Sensible defaults for common AI workload patterns
- **NVIDIA GPU isolation**: Set `CUDA_VISIBLE_DEVICES` automatically
- **OOM score adjustment**: Protect critical AI jobs from the OOM killer
- **CPU quota and weight**: Fine-grained CPU resource control
- **Memory limits**: Hard (max) and soft (high) limits with reclaim triggers
- **User mode delegation**: Works without root when cgroups delegation is enabled

## Commands

### Create Profile

```bash
cortex limits create <name> [options]

Options:
  --preset    Workload preset (inference, training, batch, interactive)
  --gpus      Number of GPUs to allocate
  --cpu       CPU quota percentage (100 = 1 core)
  --memory    Memory limit in GB
  --oom-adj   OOM score adjustment (-1000 to 1000)
```

### Apply to Process

```bash
cortex limits apply <name> --pid <pid>
```

### Environment Variables

```bash
# Print exports for shell
cortex limits env <name>

# Apply to current shell
eval $(cortex limits env <name>)
```

### Status

```bash
# List all profiles
cortex limits list

# Show specific profile
cortex limits status <name>

# Show available presets
cortex limits presets
```

### Delete Profile

```bash
cortex limits delete <name>
```

## Environment Variables Generated

When using `cortex limits env`, the following variables are set:

| Variable | Description |
|----------|-------------|
| `CUDA_VISIBLE_DEVICES` | NVIDIA GPU visibility |
| `HIP_VISIBLE_DEVICES` | AMD ROCm GPU visibility |
| `ONEAPI_DEVICE_SELECTOR` | Intel oneAPI device selection |
| `OMP_NUM_THREADS` | OpenMP thread count |
| `MKL_NUM_THREADS` | Intel MKL thread count |
| `OPENBLAS_NUM_THREADS` | OpenBLAS thread count |
| `TF_MEMORY_ALLOCATION` | TensorFlow memory hint |
| `PYTORCH_CUDA_ALLOC_CONF` | PyTorch CUDA allocator config |

## User Mode (Non-Root)

For non-root usage, enable cgroups delegation:

```bash
# Check if delegation is enabled
cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/cgroup.subtree_control

# Enable delegation (as root)
mkdir -p /etc/systemd/system/user@.service.d
cat > /etc/systemd/system/user@.service.d/delegate.conf << EOF
[Service]
Delegate=cpu cpuset io memory pids
EOF
systemctl daemon-reload
```

## Architecture

```
AcceleratorLimitsManager
├── LimitsDatabase (SQLite storage)
├── CgroupsV2Controller (cgroups interface)
└── OOMScoreManager (OOM score adjustment)

ResourceLimits (dataclass)
├── CPU: quota, weight, affinity
├── Memory: max, high limits
├── GPU: device IDs, percentage
└── OOM: score adjustment
```

## Testing

```bash
pytest tests/test_accelerator_limits.py -v
```

## Files

- `cortex/kernel_features/accelerator_limits.py` - Main implementation
- `tests/test_accelerator_limits.py` - Unit tests
- `README_ACCELERATOR_LIMITS.md` - This file

## Related Issues

- [#222 Accelerator-Aware Resource Limits](https://github.com/cortexlinux/cortex/issues/222)
