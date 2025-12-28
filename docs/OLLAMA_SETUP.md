# Ollama Integration Guide

## Overview

Cortex Linux supports **Ollama** for free, local LLM inference. This means you can use Cortex without paying for API keys, and all AI processing happens on your machine.

## Why Use Ollama?

| Advantage | Description |
|-----------|-------------|
| **Free** | No API costs - runs entirely on your hardware |
| **Private** | Your data never leaves your machine |
| **Offline** | Works without internet connection |
| **Fast** | Low latency for local inference |
| **Flexible** | Choose from multiple open-source models |

## Quick Setup

The easiest way to set up Ollama is using our setup script:

```bash
cd cortex
python scripts/setup_ollama.py
```

This interactive script will:
1. Check if Ollama is installed (and install it if needed)
2. Start the Ollama service
3. Let you choose and download a model
4. Test the model
5. Configure Cortex to use Ollama

## Manual Setup

If you prefer manual setup:

### 1. Install Ollama

```bash
# Linux / macOS
curl -fsSL https://ollama.ai/install.sh | sh

# Or download from https://ollama.ai
```

### 2. Start Ollama Service

```bash
# Start in background
ollama serve &

# Or use systemd (Linux)
sudo systemctl start ollama
sudo systemctl enable ollama
```

### 3. Download a Model

```bash
# Recommended: Llama 3.2 (2GB, fast)
ollama pull llama3.2

# Alternative options:
ollama pull llama3.2:1b      # Smallest (1.3GB)
ollama pull llama3.1:8b      # More capable (4.7GB)
ollama pull mistral          # Good alternative (4.1GB)
ollama pull codellama:7b     # Optimized for code (3.8GB)
ollama pull phi3             # Microsoft Phi-3 (2.3GB)
```

### 4. Configure Cortex

Create or edit `.env` file:

```bash
# Set Ollama as the provider
CORTEX_PROVIDER=ollama

# Optional: Configure Ollama URL (default: http://localhost:11434)
OLLAMA_BASE_URL=http://localhost:11434

# Optional: Set specific model (default: llama3.2)
OLLAMA_MODEL=llama3.2
```

Or edit `~/.cortex/config.json`:

```json
{
  "api_provider": "ollama",
  "ollama_model": "llama3.2",
  "ollama_base_url": "http://localhost:11434"
}
```

### 5. Test

```bash
# Test Cortex with Ollama
cortex install nginx --dry-run

# Test Ollama directly
ollama run llama3.2 "What is nginx?"
```

## Model Recommendations

### For Cortex (Package Management)

| Model | Size | RAM | Speed | Recommended For |
|-------|------|-----|-------|-----------------|
| **llama3.2** | 2GB | 4GB | Fast | Default choice - good balance |
| llama3.2:1b | 1.3GB | 2GB | Fastest | Low-RAM systems, quick responses |
| llama3.1:8b | 4.7GB | 8GB | Slower | Better reasoning, more capable |
| mistral | 4.1GB | 8GB | Medium | Alternative to Llama |

### For Code Generation

| Model | Size | RAM | Speed | Recommended For |
|-------|------|-----|-------|-----------------|
| **codellama:7b** | 3.8GB | 8GB | Medium | Code-focused tasks |
| phi3 | 2.3GB | 4GB | Fast | Smaller code model |

### Hardware Requirements

| Model Size | Minimum RAM | Recommended RAM | Notes |
|------------|-------------|-----------------|-------|
| 1B params | 2GB | 4GB | Fastest, least capable |
| 3B params | 4GB | 8GB | Good balance |
| 7B params | 8GB | 16GB | More capable |
| 8B params | 8GB | 16GB | Best reasoning |

**Note:** These are minimums. More RAM = faster inference and better context handling.

## Switching Models

You can change models at any time:

```bash
# Download a new model
ollama pull mistral

# Update Cortex configuration
export OLLAMA_MODEL=mistral

# Or edit ~/.cortex/config.json
```

## Troubleshooting

### Ollama Service Not Running

```bash
# Check if Ollama is running
ollama list

# Start Ollama
ollama serve &

# Or use systemd
sudo systemctl start ollama
```

### Connection Refused

```bash
# Check Ollama is listening
curl http://localhost:11434/api/tags

# If using custom port, update .env:
OLLAMA_BASE_URL=http://localhost:YOUR_PORT
```

### Model Download Fails

```bash
# Check disk space
df -h

# Check internet connection
ping ollama.ai

# Try again with verbose output
ollama pull llama3.2 --verbose
```

### Slow Inference

1. **Use a smaller model**: Try `llama3.2:1b` instead of `llama3.1:8b`
2. **Check RAM usage**: `free -h` - if swapping, you need more RAM
3. **Close other apps**: Free up system resources
4. **Use GPU**: Install Ollama with GPU support (CUDA/ROCm)

### Out of Memory

```bash
# Switch to smaller model
ollama pull llama3.2:1b
export OLLAMA_MODEL=llama3.2:1b

# Or reduce context length in requests
```

## Performance Optimization

### GPU Acceleration

Ollama automatically uses GPU if available:

```bash
# Check GPU detection
ollama list

# For NVIDIA GPUs, install CUDA toolkit
sudo apt install nvidia-cuda-toolkit

# For AMD GPUs, install ROCm
# Follow: https://rocm.docs.amd.com/en/latest/deploy/linux/quick_start.html
```

### Memory Management

```bash
# Keep multiple models for different tasks
ollama pull llama3.2       # Fast, general
ollama pull codellama:7b   # Code-focused

# Remove unused models to save space
ollama rm old-model
```

## Comparing Ollama vs Cloud APIs

| Feature | Ollama (Local) | Claude API | OpenAI API |
|---------|---------------|------------|------------|
| **Cost** | Free | ~$0.02/request | ~$0.01/request |
| **Privacy** | 100% private | Data sent to cloud | Data sent to cloud |
| **Speed** | Fast (local) | Network latency | Network latency |
| **Quality** | Good (varies by model) | Excellent | Excellent |
| **Offline** | Yes | No | No |
| **GPU** | Optional (faster) | N/A | N/A |
| **RAM** | 2-16GB | N/A | N/A |

## Using Multiple Providers

You can switch between providers:

```bash
# Use Ollama for simple tasks
export CORTEX_PROVIDER=ollama
cortex install nginx --dry-run

# Use Claude for complex tasks
export CORTEX_PROVIDER=claude
cortex install "complex ML environment setup" --dry-run
```

## Advanced Configuration

### Custom Ollama Server

If running Ollama on another machine:

```bash
# .env file
OLLAMA_BASE_URL=http://192.168.1.100:11434
```

### Fine-tuned Models

```bash
# Create custom model (see Ollama docs)
ollama create my-cortex-model -f Modelfile

# Use in Cortex
export OLLAMA_MODEL=my-cortex-model
```

## API Compatibility

Ollama provides an OpenAI-compatible API, so Cortex's LLM router can use it seamlessly:

```python
from cortex.llm_router import LLMRouter, LLMProvider

router = LLMRouter(
    ollama_base_url="http://localhost:11434",
    ollama_model="llama3.2",
    default_provider=LLMProvider.OLLAMA
)
```

## Resources

- **Ollama Website**: https://ollama.ai
- **Model Library**: https://ollama.ai/library
- **GitHub**: https://github.com/ollama/ollama
- **Discord**: https://discord.gg/ollama

## Contributing

Found ways to improve Ollama integration? We welcome contributions:

- **Model benchmarks**: Test different models with Cortex
- **Performance optimizations**: Speed improvements
- **Documentation**: Better setup guides
- **Bug reports**: Issues with Ollama integration

See [Contributing.md](../Contributing.md) for details.

---

## Quick Reference

```bash
# Setup
python scripts/setup_ollama.py

# Common commands
ollama list                    # List installed models
ollama pull llama3.2           # Download model
ollama rm old-model            # Remove model
ollama run llama3.2 "test"     # Test model
ollama serve                   # Start service

# Cortex with Ollama
export CORTEX_PROVIDER=ollama
cortex install nginx --dry-run
```

---

**Need help?** Join our [Discord](https://discord.gg/uCqHvxjU83) or [open an issue](https://github.com/cortexlinux/cortex/issues).
