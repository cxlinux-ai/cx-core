# Automatic Ollama Setup During Installation

## Overview

Cortex Linux now automatically sets up Ollama during the `pip install` process, making it easier to get started with local LLM support without manual configuration.

## How It Works

When you run `pip install -e .` (development mode) or `pip install cortex-linux` (production), the installation process automatically:

1. **Downloads and installs Ollama** - The official Ollama binary is downloaded and installed system-wide
2. **Starts the Ollama service** - The Ollama daemon is started in the background
3. **Prompts for model selection** - Interactive prompt to choose and download an LLM model (e.g., codellama:7b, phi3:mini)

## Installation Behavior

### Normal Installation
```bash
pip install -e .
```

This will:
- Install all Python dependencies
- Run the Ollama setup script automatically
- Prompt you to select a model to download
- Complete the setup with no additional steps needed

### CI/Automated Environments

The setup automatically detects and skips Ollama installation in:
- CI environments (checks `CI` or `GITHUB_ACTIONS` environment variables)
- Non-interactive terminals (skips model download prompt)

### Manual Skip

To skip Ollama setup during installation:
```bash
CORTEX_SKIP_OLLAMA_SETUP=1 pip install -e .
```

## Architecture

### Flow Diagram

```
pip install -e .
    ├─> setuptools installs dependencies
    ├─> setuptools installs entry points (cortex, cortex-setup-ollama)
    └─> PostDevelopCommand.run() is triggered
        └─> imports scripts.setup_ollama
            └─> setup_ollama() executes
                ├─> Check skip flags (CORTEX_SKIP_OLLAMA_SETUP, CI)
                ├─> install_ollama()
                │   ├─> Check if already installed
                │   └─> Download and run install.sh
                ├─> start_ollama_service()
                │   └─> Start 'ollama serve' in background
                └─> prompt_model_selection() (if interactive)
                    └─> pull_selected_model()
```

## Testing

### Run Integration Tests
```bash
python3 tests/test_ollama_setup_integration.py
```

This validates:
- Package structure is correct
- MANIFEST.in includes scripts directory
- setup_ollama can be imported
- setup_ollama executes without errors

### Manual Testing
```bash
# Test with skip flag
CORTEX_SKIP_OLLAMA_SETUP=1 pip install -e .

# Test normal installation (requires interactive terminal)
pip install -e .

# Verify Ollama was installed
which ollama
ollama --version

# Verify cortex works with Ollama
cortex install nginx --dry-run
```

## Troubleshooting

### Ollama Setup Fails During Installation

If Ollama setup fails, the installation will still succeed with a warning:
```
⚠️  Ollama setup encountered an issue: [error message]
ℹ️  You can run it manually later with: cortex-setup-ollama
```

You can then manually run:
```bash
cortex-setup-ollama
```

### Permission Issues

Ollama installation requires sudo access. If you get permission errors:
1. Run with sudo: `sudo pip install -e .` (not recommended)
2. Or skip Ollama during install and run manually:
   ```bash
   CORTEX_SKIP_OLLAMA_SETUP=1 pip install -e .
   sudo cortex-setup-ollama
   ```

### Ollama Already Installed

The setup script detects if Ollama is already installed and skips the installation step:
```
✅ Ollama already installed
```

## Configuration

### Environment Variables

- `CORTEX_SKIP_OLLAMA_SETUP=1` - Skip Ollama setup entirely
- `CI=1` or `GITHUB_ACTIONS=true` - Automatically detected, skips setup

### Available Models

During interactive installation, you can choose from:
1. **codellama:7b** (3.8 GB) - Default, good for code
2. **llama3:8b** (4.7 GB) - Balanced, general purpose
3. **phi3:mini** (1.9 GB) - Lightweight, quick responses
4. **deepseek-coder:6.7b** (3.8 GB) - Code-optimized
5. **mistral:7b** (4.1 GB) - Fast and efficient
6. **Skip** - Download later with `ollama pull <model>`

## Command Reference

### Installed Commands

After installation, these commands are available:

```bash
# Main Cortex CLI
cortex install nginx

# Manually run Ollama setup
cortex-setup-ollama
```

### Manual Ollama Commands

```bash
# Check Ollama status
ollama --version

# Start Ollama service
ollama serve

# Pull a specific model
ollama pull codellama:7b

# List downloaded models
ollama list

# Remove a model
ollama rm codellama:7b
```

## Development Notes

### Why This Approach?

1. **User Experience** - Zero-configuration setup for local LLM support
2. **Optional** - Can be skipped with environment variable
3. **Safe** - Detects CI environments automatically
4. **Robust** - Gracefully handles failures, doesn't break installation
5. **Standard** - Uses setuptools' cmdclass hooks (standard Python packaging)

### Alternative Approaches Considered

1. **Post-install script in entry_points** - Less reliable, harder to control execution context
2. **Separate install command** - Requires manual step, worse UX
3. **Check on first run** - Delays first use, interrupts workflow
4. **Docker-only** - Limits flexibility, requires container runtime

### Future Enhancements

- [ ] Add progress bar for Ollama download
- [ ] Support for custom model selection via environment variable
- [ ] Ollama version pinning/updates
- [ ] Automatic model updates on new Cortex releases
- [ ] Integration with `cortex doctor` for Ollama health checks

## Related Documentation

- [OLLAMA_INTEGRATION.md](OLLAMA_INTEGRATION.md) - Full Ollama integration guide
- [OLLAMA_QUICKSTART.md](OLLAMA_QUICKSTART.md) - Quick start for Ollama
- [FIRST_RUN_WIZARD.md](FIRST_RUN_WIZARD.md) - First-time user setup
- [docs/examples/ollama_demo.py](../examples/ollama_demo.py) - Example usage

## Support

If you encounter issues with automatic Ollama setup:

1. Check the error message - it should provide guidance
2. Try manual setup: `cortex-setup-ollama`
3. Check Ollama docs: https://ollama.com
4. Report issues: https://github.com/cortexlinux/cortex/issues
5. Discord: https://discord.gg/uCqHvxjU83
