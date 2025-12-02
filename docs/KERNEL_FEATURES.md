# Cortex Kernel Features

User-space implementations of kernel-level AI concepts. These demonstrate kernel-level thinking while running on standard Ubuntu 24.04.

## Components

### 1. Model Lifecycle Manager
Systemd-based LLM service management.

```bash
cortex model register llama-70b --path meta-llama/Llama-2-70b-hf --backend vllm
cortex model start llama-70b
cortex model status
```

### 2. KV-Cache Manager
Shared memory cache pools for LLM inference.

```bash
cortex cache create llama-cache --size 16G
cortex cache status
cortex cache destroy llama-cache
```

### 3. Accelerator Limits
cgroups v2 wrapper for AI workloads.

```bash
cortex limits create inference-job --preset inference --gpus 2
cortex limits status
```

### 4. /dev/llm Virtual Device
FUSE-based file interface to LLMs.

```bash
cortex-llm-device mount /mnt/llm
echo "Hello" > /mnt/llm/claude/prompt
cat /mnt/llm/claude/response
```

## Architecture

These are Tier 1 features from our kernel enhancement roadmap - user-space implementations that can ship now while we work on upstream kernel contributions.

## Patents

The KV-Cache Manager implements concepts from our provisional patent applications for kernel-managed KV-cache memory regions.
