# Getting Started with Cortex Linux

## Prerequisites

- Ubuntu 24.04 LTS (or compatible)
- Python 3.11+
- Internet connection

## Quick Install
```bash
# Clone repository
git clone https://github.com/cortexlinux/cortex.git
cd cortex

# Install Cortex
pip install -e .

# Configure API key
export ANTHROPIC_API_KEY="your-key-here"

# Run Cortex
python -m cortex install "nodejs"
```

## First Commands
```bash
# Install development environment
cortex install "web development environment"

# Install with GPU optimization
cortex install "tensorflow" --optimize-gpu

# Simulate before installing
cortex simulate "install oracle database"

# Check system health
cortex health
```

## Next Steps

- Read the [User Guide](User-Guide) for complete command reference
- Join [Discord](https://discord.gg/uCqHvxjU83) for support
- Check [FAQ](FAQ) for common questions
