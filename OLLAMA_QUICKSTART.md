# Ollama Quick Start Guide

## 🚀 Setup in 3 Steps

### 1. Install Dependencies
```bash
cd cortex
source venv/bin/activate
pip install -e .
```

### 2. Set Up Ollama
```bash
# Interactive setup (recommended)
python scripts/setup_ollama.py

# Or non-interactive
python scripts/setup_ollama.py --model llama3.2 --non-interactive
```

### 3. Test
```bash
# Run test suite
python tests/test_ollama_integration.py

# Test with Cortex
export CORTEX_PROVIDER=ollama
cortex install nginx --dry-run
```

## 📝 Configuration

### Environment Variables (.env)
```bash
CORTEX_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

### Config File (~/.cortex/config.json)
```json
{
  "api_provider": "ollama",
  "ollama_model": "llama3.2",
  "ollama_base_url": "http://localhost:11434"
}
```

## 🔧 Common Commands

```bash
# Setup
python scripts/setup_ollama.py

# Manage Ollama
ollama serve                     # Start service
ollama list                      # List models
ollama pull llama3.2             # Download model
ollama rm old-model              # Remove model
ollama run llama3.2 "test"       # Test model

# Use with Cortex
export CORTEX_PROVIDER=ollama
cortex install nginx --dry-run
cortex ask "how do I update Ubuntu?"

# Switch providers
export CORTEX_PROVIDER=claude    # Use Claude
export CORTEX_PROVIDER=ollama    # Use Ollama
```

## 🎯 Recommended Models

| Use Case | Model | Size | RAM |
|----------|-------|------|-----|
| **General (default)** | llama3.2 | 2GB | 4GB |
| **Fast/Low RAM** | llama3.2:1b | 1.3GB | 2GB |
| **Better Quality** | llama3.1:8b | 4.7GB | 8GB |
| **Code Tasks** | codellama:7b | 3.8GB | 8GB |

## 🐛 Troubleshooting

### Ollama Not Running
```bash
# Check status
ollama list

# Start service
ollama serve &
# Or with systemd
sudo systemctl start ollama
```

### Connection Issues
```bash
# Test connection
curl http://localhost:11434/api/tags

# Check if port is in use
sudo lsof -i :11434
```

### Out of Memory
```bash
# Use smaller model
ollama pull llama3.2:1b
export OLLAMA_MODEL=llama3.2:1b
```

## 📚 Full Documentation

- [Complete Setup Guide](docs/OLLAMA_SETUP.md)
- [LLM Integration](docs/LLM_INTEGRATION.md)
- [Main README](README.md)

## 💡 Tips

1. **Start small**: Use `llama3.2` (2GB) for testing
2. **GPU helps**: Ollama auto-detects NVIDIA/AMD GPUs
3. **Free forever**: No API costs, everything runs locally
4. **Works offline**: Perfect for air-gapped systems
5. **Mix providers**: Use Ollama for simple tasks, Claude for complex ones

## 🎉 Quick Win

```bash
# Complete setup in one go
python scripts/setup_ollama.py && \
export CORTEX_PROVIDER=ollama && \
cortex install nginx --dry-run && \
echo "✅ Ollama is working!"
```

---

**Need help?** Check [OLLAMA_SETUP.md](docs/OLLAMA_SETUP.md) or join [Discord](https://discord.gg/uCqHvxjU83)
