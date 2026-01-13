# LLM Setup Guide for Cortex Daemon

## Overview

Cortex Daemon supports running any GGUF-format language model via llama.cpp. The daemon automatically loads a configured model on startup and provides inference capabilities through the IPC protocol.

## Quick Start

### Automated Setup (Recommended)

```bash
cd /path/to/cortex
./daemon/scripts/setup-llm.sh
```

This script will:
1. Create `~/.cortex/models` directory
2. Download TinyLlama 1.1B model (~600MB)
3. Create `/etc/cortex/daemon.conf` with model configuration
4. Restart the daemon to load the model
5. Verify the model loaded successfully

### Manual Setup

#### Step 1: Download a Model

```bash
mkdir -p ~/.cortex/models
cd ~/.cortex/models

# Example: Download TinyLlama (recommended for testing)
wget https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

# Or another model - see COMPATIBLE_MODELS.md for options
```

#### Step 2: Create Configuration

```bash
sudo mkdir -p /etc/cortex
sudo nano /etc/cortex/daemon.conf
```

Add or update the `model_path` line:

```yaml
socket_path: /run/cortex/cortex.sock
model_path: /home/username/.cortex/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
monitoring_interval_seconds: 300
enable_cve_scanning: true
enable_journald_logging: true
log_level: 1
max_inference_queue_size: 100
memory_limit_mb: 150
```

**Important:** Replace `/home/username` with your actual home directory.

#### Step 3: Restart Daemon

```bash
sudo systemctl restart cortexd
sleep 3
```

#### Step 4: Verify

```bash
# Check daemon status
sudo systemctl status cortexd

# Check if model loaded
cortex daemon health
# Should show: "LLM Loaded: Yes"

# View loading logs
sudo journalctl -u cortexd -n 50 | grep -i "model\|llm"
```

## Supported Models

### Quick Reference

| Model | Size | Memory | Speed | Quality | Best For |
|-------|------|--------|-------|---------|----------|
| TinyLlama 1.1B | 600MB | <1GB | ⚡⚡⚡⚡⚡ | ⭐⭐ | Testing |
| Phi 2.7B | 1.6GB | 2-3GB | ⚡⚡⚡⚡ | ⭐⭐⭐ | Development |
| Mistral 7B | 4GB | 5-6GB | ⚡⚡⚡ | ⭐⭐⭐⭐ | Production |
| Llama 2 13B | 8GB | 9-10GB | ⚡⚡ | ⭐⭐⭐⭐⭐ | High Quality |

### All Compatible Models

All models in GGUF format from [TheBloke's HuggingFace](https://huggingface.co/TheBloke) are compatible. This includes:

- **Base Models**: Llama, Llama 2, Mistral, Qwen, Phi, Falcon, MPT
- **Specialized**: Code Llama, WizardCoder, Orca, Neural Chat
- **Instruct Models**: Chat-tuned versions for conversation
- **Quantizations**: Q3, Q4, Q5, Q6, Q8 (lower = faster, higher = more accurate)

See [COMPATIBLE_MODELS.md](../COMPATIBLE_MODELS.md) for a comprehensive list with download links.

## Switching Models

To switch to a different model:

```bash
# 1. Download new model
cd ~/.cortex/models
wget https://huggingface.co/TheBloke/[MODEL]/resolve/main/[MODEL].gguf

# 2. Update config
sudo nano /etc/cortex/daemon.conf
# Change model_path line

# 3. Restart daemon
sudo systemctl restart cortexd

# 4. Verify
cortex daemon health
```

## Troubleshooting

### Model Not Loading

```bash
# Check error messages
sudo journalctl -u cortexd -n 100 | grep -i "error\|model\|failed"

# Verify file exists and is readable
ls -lh ~/.cortex/models/model.gguf
file ~/.cortex/models/model.gguf  # Should say "data"

# Try running daemon in foreground for debugging
sudo /usr/local/bin/cortexd
```

### Out of Memory

If daemon crashes or uses too much memory:

1. Use a smaller model (TinyLlama or Phi instead of Mistral)
2. Use higher quantization (Q3_K_M instead of Q5)
3. Reduce `memory_limit_mb` in config
4. Reduce `max_inference_queue_size` in config

```yaml
# For limited memory systems:
memory_limit_mb: 100
max_inference_queue_size: 50
```

### Model File Corrupted

If you see errors about invalid file format:

```bash
# Verify download completed
ls -lh ~/.cortex/models/model.gguf

# Re-download if incomplete
cd ~/.cortex/models
rm model.gguf
wget https://huggingface.co/.../model.gguf
```

### Permission Denied

If you see permission errors:

```bash
# Ensure file is world-readable
chmod 644 ~/.cortex/models/*.gguf

# Ensure directory is accessible
chmod 755 ~/.cortex/models
```

## Performance Tips

### For Maximum Speed

```yaml
model_path: ~/.cortex/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
memory_limit_mb: 50
max_inference_queue_size: 50
```

### For Balanced Performance

```yaml
model_path: ~/.cortex/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf
memory_limit_mb: 150
max_inference_queue_size: 100
```

### For Maximum Quality

```yaml
model_path: ~/.cortex/models/llama-2-13b-chat.Q4_K_M.gguf
memory_limit_mb: 256
max_inference_queue_size: 50
```

## Understanding Configuration

### model_path

Absolute path to the GGUF model file. Supports:
- Absolute paths: `/home/user/.cortex/models/model.gguf`
- Relative paths (from config file location)
- Home expansion: `~/.cortex/models/model.gguf`

### memory_limit_mb

Maximum memory the daemon is allowed to use (in MB):
- Minimum: 50 MB
- Default: 150 MB
- For 13B models: 250+ MB recommended

### max_inference_queue_size

Maximum number of concurrent inference requests:
- Minimum: 10
- Default: 100
- Higher = more concurrency but more memory

## API Usage

Once the model is loaded, use it through the Python client:

```python
from cortex.daemon_client import DaemonClient

client = DaemonClient()

# Check health
health = client.get_health()
print(f"LLM Loaded: {health.get('llm_loaded')}")
print(f"Inference Queue: {health.get('inference_queue_size')}")

# Run inference (when implemented in inference API)
# result = client.infer("What is 2+2?")
```

## Resource Requirements

### Minimum (Testing)
- CPU: 2 cores
- RAM: 2GB (1GB free for model)
- Storage: 1GB for models
- Model: TinyLlama (600MB)

### Recommended (Production)
- CPU: 4+ cores
- RAM: 8GB (6GB free for model)
- Storage: 10GB for multiple models
- Model: Mistral 7B (4GB)

### High Performance (Large Models)
- CPU: 8+ cores
- RAM: 16GB+ (12GB free for model)
- Storage: 30GB+ for multiple large models
- Model: Llama 2 13B (8GB) or Mistral 8x7B (26GB)

## Monitoring

Check current model status:

```bash
# Get full health snapshot
cortex daemon health

# Get just LLM status
cortex daemon health | grep "LLM Loaded"

# Monitor in real-time
watch -n 1 'cortex daemon health'
```

## Advanced Configuration

### Loading Models at Specific Times

Set cron job to load model during off-peak hours:

```bash
# Edit crontab
sudo crontab -e

# Load model at 2 AM daily
0 2 * * * /usr/bin/systemctl restart cortexd
```

### Using Different Models for Different Tasks

```bash
# Create multiple config files
sudo nano /etc/cortex/daemon-fast.conf    # TinyLlama
sudo nano /etc/cortex/daemon-quality.conf # Mistral

# Switch by restarting with different config
# (Requires modification to systemd service)
```

### Custom Model Paths

If storing models elsewhere:

```yaml
# Network-mounted models
model_path: /mnt/nfs/models/mistral-7b.gguf

# External storage
model_path: /media/usb/models/model.gguf
```

## Frequently Asked Questions

**Q: Can I use models not from TheBloke?**
A: Yes, any GGUF-format model works. Make sure it's converted to GGUF format first.

**Q: Can I switch models without restarting?**
A: Not currently - daemon restart is required to load a new model.

**Q: How much disk space do I need?**
A: Models are stored in `~/.cortex/models`. Budget 1-10GB depending on models used.

**Q: Can I run multiple models simultaneously?**
A: Not currently - only one model loads per daemon instance. You can run multiple daemon instances on different ports.

**Q: What if my model doesn't load?**
A: Check logs with `journalctl -u cortexd -n 100`. Most common issues:
- File doesn't exist
- Wrong file format (not GGUF)
- Corrupted download
- Insufficient memory

## See Also

- [COMPATIBLE_MODELS.md](../COMPATIBLE_MODELS.md) - Complete model list
- [DAEMON_SETUP.md](DAEMON_SETUP.md) - General daemon setup
- [DAEMON_ARCHITECTURE.md](DAEMON_ARCHITECTURE.md) - LLM integration details
- [DAEMON_API.md](DAEMON_API.md) - IPC protocol reference
