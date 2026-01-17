# Cortex Linux - AI Agent Guidelines

## Project Overview

Cortex Linux is an AI-native package manager for Debian/Ubuntu that understands natural language commands. It wraps `apt` with LLM intelligence to parse requests, detect hardware, resolve dependencies, and execute installations safely.

**Repository**: https://github.com/cortexlinux/cortex
**License**: BUSL-1.1 (Business Source License 1.1)
**Primary Language**: Python 3.10+

## Quick Start

```bash
# Clone and setup
git clone https://github.com/cortexlinux/cortex.git
cd cortex
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Configure API key
echo 'ANTHROPIC_API_KEY=your-key-here' > .env

# Verify installation
cortex install nginx --dry-run
```

## Development Environment

### Prerequisites
- Python 3.10 or higher
- Ubuntu 22.04+ or Debian 12+
- Virtual environment (required)
- Anthropic API key or OpenAI API key

### Setup Commands
```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Testing Instructions

```bash
# Run all tests
pytest tests/ -v

# Test dry-run (safe)
cortex install nginx --dry-run

# Test hardware detection
cortex-detect-hardware
```

## Code Standards

- Follow PEP 8
- Type hints required
- Docstrings for public APIs
- >80% test coverage for PRs

## Safety Requirements

1. Dry-run by default for all installations
2. No silent sudo
3. Firejail sandboxing required
4. Audit logging to ~/.cortex/history.db

## PR Guidelines

- Title format: [component] Description
- All tests must pass
- Documentation required for new features

## Contact

- Discord: https://discord.gg/uCqHvxjU83
- Email: mike@cortexlinux.com
