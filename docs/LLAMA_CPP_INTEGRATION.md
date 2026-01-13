# Cortexd - llama.cpp Integration Guide

## Overview

Cortex supports **llama.cpp** for local LLM inference using GGUF quantized models. This enables free, private, offline AI capabilities on your machine.

**Status**: ✅ **FULLY IMPLEMENTED**

---

## Architecture

Cortex uses a **separate service architecture** for llama.cpp to keep the main daemon lightweight:

```
┌──────────────────────────┐      ┌──────────────────────────┐
│   cortexd (C++ Daemon)   │      │  cortex-llm Service      │
│  ┌────────────────────┐  │      │  ┌────────────────────┐  │
│  │  Core Services     │  │ HTTP │  │  llama-server      │  │
│  │  - IPC Server      │◄─┼──────┼─►│  - GGUF Models     │  │
│  │  - System Monitor  │  │      │  │  - OpenAI API      │  │
│  │  - Alerts          │  │      │  │                    │  │
│  │  MemoryMax=256M    │  │      │  │  MemoryMax=16G     │  │
│  └────────────────────┘  │      │  └────────────────────┘  │
└──────────────────────────┘      └──────────────────────────┘
     cortexd.service                  cortex-llm.service
```

### Why Separate Services?

| Benefit | Description |
|---------|-------------|
| **Lightweight daemon** | cortexd stays under 256MB for system monitoring |
| **Memory isolation** | LLM models (2-16GB) don't affect daemon stability |
| **Failure isolation** | LLM crashes don't kill the daemon |
| **Flexible scaling** | Upgrade LLM service independently |

---

## Quick Start

The easiest way to set up llama.cpp is using the daemon setup wizard:

```bash
cd cortex/daemon
python scripts/setup_daemon.py
```

Select **"Local llama.cpp"** when prompted for LLM backend.

---

## Manual Setup

### 1. Install llama.cpp Server

**Option A: Build from Source (Recommended)**
```bash
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
```

**Option B: Package Manager**
```bash
sudo apt install libllama-dev  # If available
```

### 2. Download a Model

Get GGUF quantized models from Hugging Face:

```bash
mkdir -p ~/.cortex/models

# TinyLlama 1.1B (600MB, fast)
wget https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
  -O ~/.cortex/models/tinyllama-1.1b.gguf

# OR Phi 2.7B (1.6GB, balanced)
wget https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf \
  -O ~/.cortex/models/phi-2.7b.gguf

# OR Mistral 7B (4GB, high quality)
wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf \
  -O ~/.cortex/models/mistral-7b.gguf
```

### 3. Install cortex-llm Service

```bash
cd cortex/daemon
sudo ./scripts/install-llm.sh install ~/.cortex/models/model_name tot_threads tot_context_size
```

This will:
- Create `/etc/cortex/llm.env` with model configuration
- Install `cortex-llm.service` systemd unit
- Start the llama-server on port 8085

### 4. Configure Cortex to Use llama.cpp

```bash
# Set environment variables
export CORTEX_PROVIDER=llama_cpp
export LLAMA_CPP_BASE_URL=http://127.0.0.1:8085

# Or add to ~/.cortex/.env
echo "CORTEX_PROVIDER=llama_cpp" >> ~/.cortex/.env
echo "LLAMA_CPP_BASE_URL=http://127.0.0.1:8085" >> ~/.cortex/.env
```

### 5. Test

```bash
# Check service status
sudo systemctl status cortex-llm

# Test with Cortex
cortex ask "What is nginx?"
cortex install nginx --dry-run
```

---

## Service Management

### cortex-llm.service Commands

```bash
# Start/stop/restart
sudo systemctl start cortex-llm
sudo systemctl stop cortex-llm
sudo systemctl restart cortex-llm

# View status
sudo systemctl status cortex-llm

# View logs
journalctl -u cortex-llm -f

# Enable at boot
sudo systemctl enable cortex-llm

# Disable at boot
sudo systemctl disable cortex-llm
```

### Configuration

Edit `/etc/cortex/llm.env` to change model or settings:

```bash
# Path to the GGUF model file
CORTEX_LLM_MODEL_PATH=/home/user/.cortex/models/phi-2.7b.gguf

# Number of CPU threads for inference
CORTEX_LLM_THREADS=4

# Context size in tokens
CORTEX_LLM_CTX_SIZE=2048
```

After changing configuration:
```bash
sudo systemctl restart cortex-llm
```

### Switching Models

```bash
# Download new model
wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf \
  -O ~/.cortex/models/mistral-7b.gguf

# Update configuration
sudo ./scripts/install-llm.sh configure ~/.cortex/models/mistral-7b.gguf 4 2048
```

---

## Recommended Models

| Model | Size | RAM | Speed | Quality | Best For |
|-------|------|-----|-------|---------|----------|
| **TinyLlama 1.1B** | 600MB | 2GB | ⚡ Very Fast | Fair | Testing, low-resource |
| **Phi 2.7B** | 1.6GB | 3GB | ⚡ Fast | Good | Daily use, balanced |
| **Mistral 7B** | 4GB | 8GB | Medium | Very Good | Production |
| **Llama 2 13B** | 8GB | 16GB | Slow | Excellent | High quality |

---

## Python Integration

Cortex CLI automatically uses the `llama_cpp` provider when configured:

```python
from cortex.llm.interpreter import CommandInterpreter, APIProvider

# Create interpreter with llama.cpp
interpreter = CommandInterpreter(
    api_key="",  # Not needed for local
    provider="llama_cpp",
)

# Parse commands
commands = interpreter.parse("install nginx and configure it")
print(commands)
```

Environment variables:
- `CORTEX_PROVIDER=llama_cpp` - Use llama.cpp backend
- `LLAMA_CPP_BASE_URL=http://127.0.0.1:8085` - Server URL
- `LLAMA_CPP_MODEL=local-model` - Model name (display only)

---

## Legacy: Embedded LLM (Deprecated)

The previous approach embedded llama.cpp directly into the daemon. This is now **deprecated** in favor of the separate service architecture.

### Why Deprecated?

The embedded approach conflicted with the daemon's 256MB memory limit:
- Daemon MemoryMax: 256MB
- Smallest model (TinyLlama): 2GB RAM required

With embedded LLM, systemd would kill the daemon when loading any model.

### Migration

If you were using embedded LLM, migrate to the new architecture:

```bash
# Re-run setup wizard
cd cortex/daemon
python scripts/setup_daemon.py

# Select "Local llama.cpp" when prompted
```

---

## What's Implemented

### ✅ Separate Service (`cortex-llm.service`)

- Runs llama-server as a systemd service
- OpenAI-compatible API on port 8085
- Configurable via `/etc/cortex/llm.env`
- Memory limit: 16GB (configurable)

### ✅ Python Provider (`llama_cpp`)

- `cortex/llm/interpreter.py` - LLAMA_CPP provider
- OpenAI-compatible client (same as Ollama)
- Automatic error handling and retry

### ✅ Setup Wizard

- `daemon/scripts/setup_daemon.py` - Interactive setup
- Model download from Hugging Face
- Service installation and configuration

### ✅ Install Script

- `daemon/scripts/install-llm.sh` - Service management
- Install, uninstall, configure commands
- Environment file management

**Option B: Build from Source**
```bash
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
```

### 2. Download a Model

Get GGUF quantized models from Hugging Face:

```bash
mkdir -p ~/.cortex/models

# Phi 2.7B (fast, 1.6GB)
wget https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf \
  -O ~/.cortex/models/phi-2.7b.gguf

# OR Mistral 7B (balanced, 6.5GB)
wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/main/Mistral-7B-Instruct-v0.1.Q4_K_M.gguf \
  -O ~/.cortex/models/mistral-7b.gguf
```

**Model Sources**:
- TheBloke on Hugging Face: https://huggingface.co/TheBloke
- Ollama models: https://ollama.ai/library
- LM Studio: https://lmstudio.ai

### 3. Build Cortexd

```bash
cd /path/to/cortex/daemon
./scripts/build.sh Release
```

CMake will auto-detect llama.cpp and link it.

### 4. Configure Model Path

Edit `~/.cortex/daemon.conf`:

```yaml
[llm]
model_path: ~/.cortex/models/mistral-7b.gguf
n_threads: 4
n_ctx: 512
```

### 5. Install & Test

```bash
sudo ./daemon/scripts/install.sh
cortex daemon status

# Test inference
echo '{"command":"inference","params":{"prompt":"Hello"}}' | \
  socat - UNIX-CONNECT:/run/cortex/cortex.sock | jq .
```

---

## Performance Characteristics

### Latency

| Phase | Time | Notes |
|-------|------|-------|
| Model Load | 5-30s | One-time at daemon startup |
| Warm Inference | 50-200ms | Typical response time |
| Cold Inference | 200-500ms | First request after idle |
| Per Token | 5-50ms | Depends on model size |

### Memory Usage

| State | Memory | Notes |
|-------|--------|-------|
| Daemon Idle | 30-40 MB | Without model |
| Model Loaded | Model Size | e.g., 3.8GB for Mistral 7B |
| During Inference | +100-200 MB | Context buffers |

### Throughput

- **Single Request**: 10-50 tokens/second
- **Queue Depth**: Default 100 requests
- **Concurrent**: Requests are queued, one at a time

### Recommended Models

| Model | Size | Speed | RAM | Quality | Recommended For |
|-------|------|-------|-----|---------|-----------------|
| **Phi 2.7B** | 1.6GB | Very Fast | 2-3GB | Fair | Servers, Raspberry Pi |
| **Mistral 7B** | 6.5GB | Medium | 8-12GB | Good | Production |
| **Llama 2 7B** | 3.8GB | Medium | 5-8GB | Good | Systems with 8GB+ RAM |
| **Orca Mini** | 1.3GB | Very Fast | 2GB | Fair | Low-end hardware |

---

## API Usage

### Via Python Client

```python
from cortex.daemon_client import CortexDaemonClient

client = CortexDaemonClient()

# Run inference
result = client._send_command({
    "command": "inference",
    "params": {
        "prompt": "List Linux package managers",
        "max_tokens": 256,
        "temperature": 0.7
    }
})

print(result["data"]["output"])
print(f"Inference time: {result['data']['inference_time_ms']}ms")
```

### Via Unix Socket (Direct)

```bash
# Test inference
echo '{"command":"inference","params":{"prompt":"What is Python?","max_tokens":100}}' | \
  socat - UNIX-CONNECT:/run/cortex/cortex.sock

# Pretty print
echo '{"command":"inference","params":{"prompt":"Hello","max_tokens":50}}' | \
  socat - UNIX-CONNECT:/run/cortex/cortex.sock | jq .
```

### Via CLI

```bash
# Status (shows if model is loaded)
cortex daemon status

# Health (shows memory and inference queue)
cortex daemon health

# View logs
journalctl -u cortexd -f
```

---

## Troubleshooting

### Model Not Loading

**Error**: `Failed to load model: No such file or directory`

**Solution**:
```bash
# Check path
ls -la ~/.cortex/models/

# Update config
nano ~/.cortex/daemon.conf
# Set correct model_path

# Reload
cortex daemon reload-config
```

### libllama.so Not Found

**Error**: `libllama.so: cannot open shared object file`

**Solution**:
```bash
# Install llama.cpp
sudo apt install libllama-dev

# OR set library path
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

# Rebuild
cd daemon && ./scripts/build.sh Release
```

### Out of Memory

**Error**: `Cannot allocate memory during inference`

**Solution**:
1. Use a smaller model (e.g., Phi instead of Mistral)
2. Reduce context size in config:
   ```yaml
   n_ctx: 256  # Instead of 512
   ```
3. Reduce max_tokens per request

### Slow Inference

**Problem**: Inference taking >1 second per token

**Solution**:
1. Increase thread count:
   ```yaml
   n_threads: 8  # Instead of 4
   ```
2. Use quantized model (Q4, Q5 instead of FP16)
3. Check CPU usage: `top` or `htop`
4. Check for disk I/O bottleneck

### Model Already Loaded Error

**Problem**: Trying to load model twice

**Solution**:
```bash
# Reload daemon to unload old model
systemctl restart cortexd

# Or use API to unload first
cortex daemon shutdown
```

---

## Configuration Reference

### Full LLM Section

```yaml
[llm]
# Path to GGUF model file (required)
model_path: ~/.cortex/models/mistral-7b.gguf

# Number of CPU threads for inference (default: 4)
n_threads: 4

# Context window size in tokens (default: 512)
n_ctx: 512

# Use memory mapping for faster model loading (default: true)
use_mmap: true

# Maximum tokens per inference request (default: 256)
max_tokens_per_request: 256

# Temperature for sampling (0.0-2.0, default: 0.7)
temperature: 0.7
```

### Environment Variables

```bash
# Override model path
export CORTEXD_MODEL_PATH="$HOME/.cortex/models/custom.gguf"

# Set thread count
export CORTEXD_N_THREADS=8

# Enable verbose logging
export CORTEXD_LOG_LEVEL=0
```

---

## Development

### Extending the LLM Wrapper

To add features like streaming or batching:

```cpp
// In llama_wrapper.h
class LlamaWrapper : public LLMWrapper {
    // Add streaming inference
    std::vector<std::string> infer_streaming(const InferenceRequest& req);
    
    // Add token probabilities
    InferenceResult infer_with_probs(const InferenceRequest& req);
};
```

### Testing

```cpp
// In tests/unit/llm_wrapper_test.cpp
TEST(LlamaWrapperTest, LoadModel) {
    LlamaWrapper wrapper;
    EXPECT_TRUE(wrapper.load_model("model.gguf"));
    EXPECT_TRUE(wrapper.is_loaded());
}

TEST(LlamaWrapperTest, Inference) {
    LlamaWrapper wrapper;
    wrapper.load_model("model.gguf");
    
    InferenceRequest req;
    req.prompt = "Hello";
    req.max_tokens = 10;
    
    InferenceResult result = wrapper.infer(req);
    EXPECT_TRUE(result.success);
    EXPECT_FALSE(result.output.empty());
}
```

---

## Performance Tuning

### For Maximum Speed

```yaml
[llm]
n_threads: 8                    # Use all cores
n_ctx: 256                      # Smaller context
use_mmap: true                  # Faster loading
model_path: phi-2.gguf          # Fast model
```

### For Maximum Quality

```yaml
[llm]
n_threads: 4                    # Balanced
n_ctx: 2048                     # Larger context
use_mmap: true
model_path: mistral-7b.gguf     # Better quality
```

### For Low Memory

```yaml
[llm]
n_threads: 2                    # Fewer threads
n_ctx: 128                      # Minimal context
use_mmap: true
model_path: phi-2.gguf          # Small model (1.6GB)
```

---

## Future Enhancements

Potential additions in Phase 2:

- [ ] Token streaming (real-time output)
- [ ] Batched inference (multiple prompts)
- [ ] Model caching (keep multiple models)
- [ ] Quantization support (INT8, INT4)
- [ ] Custom system prompts
- [ ] Prompt templates (Jinja2, Handlebars)
- [ ] Metrics export (Prometheus)

---

## References

- **llama.cpp**: https://github.com/ggerganov/llama.cpp
- **GGUF Format**: https://github.com/ggerganov/ggml
- **Hugging Face Models**: https://huggingface.co/TheBloke
- **Ollama**: https://ollama.ai

---

## Support

### Getting Help

1. Check [DAEMON_TROUBLESHOOTING.md](DAEMON_TROUBLESHOOTING.md)
2. Review logs: `journalctl -u cortexd -f`
3. Test model: `cortex daemon health`
4. Open issue: https://github.com/cortexlinux/cortex/issues

### Common Issues

See troubleshooting section above for:
- Model loading failures
- Memory issues
- Slow inference
- Library not found errors

---

**Status**: ✅ Fully Implemented and Production Ready

