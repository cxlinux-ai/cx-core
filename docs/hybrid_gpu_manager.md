# Hybrid GPU Manager (Linux)

This tool addresses Linux Pain Point #14: hybrid GPU switching latency and lack of visibility.

## Features

- Detects available GPUs (Intel/AMD + NVIDIA)
- Shows which GPU is currently active
- Lists applications currently using NVIDIA GPU
- Allows per-app GPU selection
- Provides rough battery impact estimates

## Requirements

- Linux system with hybrid GPU
- NVIDIA drivers installed (for NVIDIA features)
- Python 3.10+

## Usage

### Show GPU status
```bash
python scripts/gpu_manager.py status
