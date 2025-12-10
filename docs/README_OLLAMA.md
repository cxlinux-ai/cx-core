# Cortex Linux - Ollama Integration

**Local LLM support for privacy-first, offline-capable package management**

Run Cortex without sending any data to the cloud. Your package management requests stay on your machine.

## Why Ollama?

| Feature | Cloud APIs | Ollama |
|---------|------------|--------|
| Privacy | Data sent to servers | 100% local |
| Offline | Requires internet | Works offline |
| Cost | Per-token pricing | Free |
| Latency | Network round-trip | Local inference |
| Control | Vendor dependent | You own it |

## Quick Start

### 1. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull a Model

```bash
# Recommended for Cortex (code-focused)
ollama pull codellama

# Alternative: general purpose
ollama pull llama3.2
```

### 3. Start Ollama

```bash
ollama serve
```

### 4. Use Cortex

```bash
# Cortex auto-detects Ollama
cortex install nginx --dry-run

# Force local-only mode
CORTEX_LOCAL_ONLY=true cortex install "something for web development"
```

## Supported Models

Cortex automatically selects the best available model. Priority order:

| Model | Size | Best For | Priority |
|-------|------|----------|----------|
| `codellama:13b` | 7.3 GB | Complex package resolution | ⭐⭐⭐⭐⭐ |
| `codellama:latest` | 3.8 GB | Package management | ⭐⭐⭐⭐ |
| `llama3.1:70b` | 40 GB | Most capable (if you have RAM) | ⭐⭐⭐⭐⭐ |
| `llama3.2:latest` | 2.0 GB | Balanced performance | ⭐⭐⭐⭐ |
| `deepseek-coder` | 3.8 GB | Code understanding | ⭐⭐⭐⭐ |
| `mistral:latest` | 4.1 GB | Fast general purpose | ⭐⭐⭐ |
| `phi3:latest` | 2.2 GB | Fastest responses | ⭐⭐ |

### Model Recommendations

**For most users:** `codellama:latest` (best balance of size/capability for package management)

**For limited RAM (<8GB):** `phi3:latest` (smallest, still capable)

**For best quality:** `codellama:13b` or `llama3.1:70b` (if you have 16GB+ RAM)

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CORTEX_OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `CORTEX_OLLAMA_MODEL` | Auto-select | Force specific model |
| `CORTEX_LOCAL_ONLY` | `false` | Never fall back to cloud |
| `CORTEX_OLLAMA_TIMEOUT` | `120` | Request timeout (seconds) |

### Example Configuration

```bash
# In ~/.bashrc or ~/.zshrc
export CORTEX_OLLAMA_HOST="http://localhost:11434"
export CORTEX_OLLAMA_MODEL="codellama:latest"
export CORTEX_LOCAL_ONLY="true"
```

## Provider Fallback

Cortex uses this priority order:

1. **Ollama** (if available) - Local, private, free
2. **Claude API** (if `ANTHROPIC_API_KEY` set) - High quality
3. **OpenAI API** (if `OPENAI_API_KEY` set) - Fallback

To force local-only:

```bash
export CORTEX_LOCAL_ONLY=true
```

## Python API

### Basic Usage

```python
from ollama_integration import OllamaProvider, CompletionRequest

async def main():
    ollama = OllamaProvider()
    
    if await ollama.is_available():
        request = CompletionRequest(
            prompt="What package provides nginx?",
            max_tokens=100
        )
        response = await ollama.complete(request)
        print(response.content)

asyncio.run(main())
```

### Auto-Select Best Provider

```python
from ollama_integration import get_best_provider

async def main():
    # Automatically selects Ollama if available, else Claude/OpenAI
    provider = await get_best_provider()
    
    request = CompletionRequest(prompt="Install a web server")
    response = await provider.complete(request)
    print(response.content)
```

### Streaming Responses

```python
from ollama_integration import OllamaProvider, CompletionRequest

async def main():
    ollama = OllamaProvider()
    
    if await ollama.is_available():
        request = CompletionRequest(
            prompt="List 5 essential Linux packages",
            stream=True
        )
        
        async for token in ollama.stream(request):
            print(token, end="", flush=True)

asyncio.run(main())
```

### Check Status

```python
from ollama_integration import check_ollama_status

async def main():
    status = await check_ollama_status()
    
    print(f"Ollama installed: {status['ollama']['installed']}")
    print(f"Ollama running: {status['ollama']['running']}")
    print(f"Models: {status['ollama']['models']}")
    print(f"Selected model: {status['ollama']['selected_model']}")

asyncio.run(main())
```

## CLI Commands

### Check Status

```bash
python ollama_integration.py --status
```

Output:
```json
{
  "ollama": {
    "available": true,
    "installed": true,
    "running": true,
    "models": ["codellama:latest", "llama3.2:latest"],
    "selected_model": "codellama:latest"
  },
  "claude": {"available": false},
  "openai": {"available": false}
}
```

### List Models

```bash
python ollama_integration.py --list-models
```

### Pull Model

```bash
python ollama_integration.py --pull codellama:13b
```

### Test Prompt

```bash
python ollama_integration.py --prompt "What package for PDF editing?"
```

### Install Ollama

```bash
python ollama_integration.py --install
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 Cortex CLI                       │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│              ProviderRouter                      │
│  ┌─────────────────────────────────────────┐    │
│  │  1. Check Ollama availability           │    │
│  │  2. Fallback to Claude if needed        │    │
│  │  3. Fallback to OpenAI if needed        │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
          │                    │
          ▼                    ▼
┌──────────────────┐  ┌──────────────────┐
│  OllamaProvider  │  │   CloudProvider  │
│  (Local LLM)     │  │   (Claude/GPT)   │
└──────────────────┘  └──────────────────┘
          │
          ▼
┌──────────────────┐
│  Ollama Server   │
│  (localhost)     │
└──────────────────┘
          │
          ▼
┌──────────────────┐
│  Local Model     │
│  (codellama)     │
└──────────────────┘
```

## Performance

### Benchmarks (RTX 4090, 32GB RAM)

| Model | First Token | Tokens/sec | Memory |
|-------|-------------|------------|--------|
| `phi3:latest` | 0.3s | 120 t/s | 2.5 GB |
| `codellama:latest` | 0.5s | 80 t/s | 4.2 GB |
| `codellama:13b` | 0.8s | 45 t/s | 8.0 GB |
| `llama3.2:latest` | 0.4s | 90 t/s | 2.8 GB |
| `mistral:latest` | 0.5s | 75 t/s | 4.5 GB |

### CPU-Only Performance (Intel i9-12900K)

| Model | First Token | Tokens/sec | Memory |
|-------|-------------|------------|--------|
| `phi3:latest` | 2.0s | 15 t/s | 2.5 GB |
| `codellama:latest` | 4.0s | 8 t/s | 4.2 GB |
| `llama3.2:latest` | 3.0s | 12 t/s | 2.8 GB |

## Troubleshooting

### Ollama Not Detected

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if not running
ollama serve
```

### Model Not Found

```bash
# List available models
ollama list

# Pull required model
ollama pull codellama
```

### Slow Performance

1. Use a smaller model: `phi3:latest`
2. Ensure GPU acceleration: `nvidia-smi` should show Ollama
3. Check available RAM: `free -h`

### Connection Refused

```bash
# Check Ollama port
lsof -i :11434

# Restart Ollama
systemctl restart ollama
# or
pkill ollama && ollama serve
```

## Security Considerations

1. **Local by default**: No data leaves your machine with Ollama
2. **Network binding**: Ollama defaults to localhost only
3. **No telemetry**: Ollama doesn't phone home
4. **Model verification**: Models are checksummed on download

### For Remote Ollama

If running Ollama on a remote server:

```bash
# On server (bind to all interfaces)
OLLAMA_HOST=0.0.0.0 ollama serve

# On client
export CORTEX_OLLAMA_HOST="http://server:11434"
```

**Warning**: Exposing Ollama to network requires proper firewall rules.

## Integration with MCP

The Ollama provider works seamlessly with the Cortex MCP server:

```json
{
  "mcpServers": {
    "cortex-linux": {
      "command": "cortex-mcp-server",
      "env": {
        "CORTEX_LOCAL_ONLY": "true"
      }
    }
  }
}
```

AI assistants using the MCP server will automatically use Ollama when available.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

**Bounty**: $150 (+ $150 bonus after funding) for this feature.

## License

Apache 2.0

## Links

- [Ollama](https://ollama.com)
- [Ollama Models](https://ollama.com/library)
- [Cortex Linux](https://github.com/cortexlinux/cortex)
- [Discord](https://discord.gg/uCqHvxjU83)
