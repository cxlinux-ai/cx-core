# Daemon LLM Health Status Implementation

## Overview

The daemon health system correctly reports the LLM loaded status through the `cortex daemon health` command. The implementation is generic and works with any GGUF model configured in the daemon.

## Architecture

### Components

1. **SystemMonitor Interface** (`daemon/include/system_monitor.h`)
   - `set_llm_loaded(bool loaded)` - Updates the LLM loaded status
   - `get_health_snapshot()` - Returns current health snapshot including LLM status

2. **Main Daemon** (`daemon/src/main.cpp`)
   - Loads model on startup from configured path
   - Notifies SystemMonitor when model loads successfully
   - Status automatically reflects load success/failure

3. **Configuration** (`/etc/cortex/daemon.conf`)
   - `model_path` - Path to any GGUF model file
   - No hardcoded model names - works with any model

### Implementation Flow

```
┌─────────────────┐
│  Daemon Starts  │
└────────┬────────┘
         │
         ▼
┌──────────────────────┐
│ Read model_path from │
│   daemon.conf        │
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│ g_llm_wrapper->      │
│   load_model(path)   │
└─────────┬────────────┘
          │
     ┌────┴────┐
     │         │
    Yes       No
     │         │
     ▼         ▼
┌─────────┐ ┌──────────────┐
│ Success │ │ Load Failed  │
└────┬────┘ └──────────────┘
     │
     ▼
┌──────────────────────────┐
│ g_system_monitor->       │
│   set_llm_loaded(true)   │
└──────────────────────────┘
```

## Usage

### Check LLM Status

```bash
cortex daemon health
```

Output shows:
```
  LLM Loaded:         Yes  # Model loaded successfully
  # or
  LLM Loaded:         No   # Model not loaded or load failed
```

### Configure Different Models

The implementation works with **any GGUF model**:

```bash
# Edit configuration
sudo nano /etc/cortex/daemon.conf

# Change model_path to any GGUF file
model_path: /path/to/your/model.gguf

# Restart daemon
sudo systemctl restart cortexd

# Verify new model loaded
cortex daemon health
```

### Examples

#### TinyLlama (Testing)
```yaml
model_path: /var/lib/cortex/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
```

#### Mistral 7B (Production)
```yaml
model_path: /var/lib/cortex/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf
```

#### Llama 2 13B (High Quality)
```yaml
model_path: /var/lib/cortex/models/llama-2-13b-chat.Q5_K_M.gguf
```

## Verification

### Check Model Loading in Logs

```bash
# View model loading process
sudo journalctl -u cortexd -n 50 | grep -i "model\|llm"

# Expected successful output:
# Attempting to load model from: /path/to/model.gguf
# Loading model with llama_model_load_from_file
# Model loaded successfully: /path/to/model.gguf (threads=4, ctx=512, mmap=true)
# LLM model loaded successfully
```

### Programmatic Health Check

```python
import socket
import json

def check_llm_status():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect('/run/cortex.sock')
    
    request = json.dumps({
        "method": "health.snapshot",
        "params": {}
    })
    
    sock.sendall(request.encode() + b'\n')
    response = json.loads(sock.recv(4096).decode())
    sock.close()
    
    return response['result']['llm_loaded']

if check_llm_status():
    print("✓ LLM is loaded")
else:
    print("✗ LLM is not loaded")
```

## Troubleshooting

### LLM Shows "No" But Logs Show Success

This was a previous bug (fixed January 2026). If you see this:

1. Verify you're running the latest daemon version:
   ```bash
   cortexd --version  # Should be 0.1.0 or later
   ```

2. Check that `set_llm_loaded()` is called in main.cpp:
   ```bash
   grep -A2 "LLM model loaded successfully" daemon/src/main.cpp
   # Should show: g_system_monitor->set_llm_loaded(true);
   ```

### Model Fails to Load

```bash
# Check daemon logs for errors
sudo journalctl -u cortexd -n 100 | grep -i error

# Common issues:
# - File not found: Check model_path in /etc/cortex/daemon.conf
# - Permission denied: Ensure model file is readable (chmod 644)
# - Out of memory: Try a smaller quantized model (Q3, Q4)
# - Corrupted model: Re-download the GGUF file
```

### Health Command Hangs

```bash
# Check daemon is running
sudo systemctl status cortexd

# Check socket exists
ls -la /run/cortex.sock

# Restart daemon if needed
sudo systemctl restart cortexd
```

## Implementation Details

### Thread Safety

The `set_llm_loaded()` method uses a mutex to ensure thread-safe updates:

```cpp
void SystemMonitorImpl::set_llm_loaded(bool loaded) {
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    last_snapshot_.llm_loaded = loaded;
}
```

### Why Not Use Extern?

An earlier implementation attempted to use `extern std::unique_ptr<LLMWrapper> g_llm_wrapper` in system_monitor.cpp to directly query the LLM status. This caused segfaults due to initialization order issues and symbol visibility problems.

The current callback-based approach is:
- ✅ Thread-safe
- ✅ No initialization order dependencies
- ✅ Clean separation of concerns
- ✅ Extensible for future status updates

## Related Documentation

- [LLM Setup Guide](LLM_SETUP.md) - How to download and configure models
- [Daemon Setup](DAEMON_SETUP.md) - Daemon installation and configuration
- [Daemon Troubleshooting](DAEMON_TROUBLESHOOTING.md) - Common issues and solutions
- [llama.cpp Integration](LLAMA_CPP_INTEGRATION.md) - Technical details on llama.cpp usage