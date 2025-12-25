# Quick Reference: Ollama Auto-Setup

## ✅ What Was Implemented

Ollama is now **automatically installed** when you run `pip install -e .`

## 🚀 Usage

### Normal Installation (Ollama Included)
```bash
pip install -e .
```
- Installs Cortex
- Downloads and installs Ollama binary
- Starts Ollama service
- Prompts for model selection (e.g., codellama:7b)
- Takes ~5-10 minutes (mostly model download)

### Skip Ollama During Installation
```bash
CORTEX_SKIP_OLLAMA_SETUP=1 pip install -e .
```
- Installs Cortex only
- Skips Ollama setup
- Faster installation
- Can set up Ollama manually later

### Manual Ollama Setup (After Installation)
```bash
cortex-setup-ollama
```
- Run this if you skipped Ollama during installation
- Or to re-run the setup/add models

## 🔍 Verification

### Check Installation
```bash
# Verify Ollama binary
which ollama
ollama --version

# List downloaded models
ollama list

# Test Cortex with Ollama
cortex install nginx --dry-run
```

### Run Tests
```bash
# Integration tests
python3 tests/test_ollama_setup_integration.py

# Full verification
./scripts/verify_ollama_setup.sh
```

## 🛠️ Environment Variables

| Variable | Effect |
|----------|--------|
| `CORTEX_SKIP_OLLAMA_SETUP=1` | Skip Ollama setup |
| `CI=1` | Auto-skips (CI detected) |
| `GITHUB_ACTIONS=true` | Auto-skips (CI detected) |

## 📁 Files Changed

- ✅ [scripts/__init__.py](../scripts/__init__.py) - NEW (makes scripts a package)
- ✅ [setup.py](../setup.py) - MODIFIED (calls setup_ollama directly)
- ✅ [MANIFEST.in](../MANIFEST.in) - MODIFIED (includes scripts/*.py)
- ✅ [pyproject.toml](../pyproject.toml) - MODIFIED (fix license format)
- ✅ [tests/test_ollama_setup_integration.py](../tests/test_ollama_setup_integration.py) - NEW
- ✅ [scripts/verify_ollama_setup.sh](../scripts/verify_ollama_setup.sh) - NEW
- ✅ [docs/AUTOMATIC_OLLAMA_SETUP.md](../docs/AUTOMATIC_OLLAMA_SETUP.md) - NEW (full docs)
- ✅ [docs/OLLAMA_AUTO_SETUP_IMPLEMENTATION.md](../docs/OLLAMA_AUTO_SETUP_IMPLEMENTATION.md) - NEW (impl summary)

## 📖 Documentation

- **Full Guide:** [docs/AUTOMATIC_OLLAMA_SETUP.md](../docs/AUTOMATIC_OLLAMA_SETUP.md)
- **Implementation Details:** [docs/OLLAMA_AUTO_SETUP_IMPLEMENTATION.md](../docs/OLLAMA_AUTO_SETUP_IMPLEMENTATION.md)
- **Ollama Integration:** [docs/OLLAMA_INTEGRATION.md](../docs/OLLAMA_INTEGRATION.md)

## 🎯 Key Benefits

1. ✅ **Zero manual steps** - One command gets everything
2. ✅ **Privacy-first** - Local LLM by default
3. ✅ **Optional** - Can skip with env var
4. ✅ **CI-friendly** - Auto-detects and skips in CI
5. ✅ **Graceful** - Installation succeeds even if Ollama fails

## 🔧 Troubleshooting

### Ollama Setup Failed During Installation
```bash
# Installation will still succeed with a warning
# Run setup manually:
cortex-setup-ollama
```

### Permission Issues
```bash
# Ollama needs sudo, so either:
sudo pip install -e .  # Not recommended

# OR skip during install, then:
CORTEX_SKIP_OLLAMA_SETUP=1 pip install -e .
sudo cortex-setup-ollama
```

### Check What Happened
```bash
# During install, you'll see:
# ✅ Ollama already installed (if already present)
# 📦 Installing Ollama... (if downloading)
# ⏭️  Skipping Ollama setup (if skipped)
# ⚠️  Ollama setup encountered an issue (if failed)
```

## 💬 Support

- **Issues:** https://github.com/cortexlinux/cortex/issues
- **Discord:** https://discord.gg/uCqHvxjU83
- **Email:** mike@cortexlinux.com

---

**Last Updated:** December 25, 2025  
**Status:** ✅ Complete and Tested
