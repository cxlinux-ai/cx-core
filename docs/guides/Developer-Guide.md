# Developer Guide

## Development Setup
```bash
# Clone repository
git clone https://github.com/cortexlinux/cortex.git
cd cortex

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run with coverage
pytest --cov=cortex tests/
```

## Project Structure
```
cortex/
├── cortex/
│   ├── __init__.py
│   ├── packages.py          # Package manager wrapper
│   ├── llm_integration.py   # Claude API integration
│   ├── sandbox.py           # Safe command execution
│   ├── hardware.py          # Hardware detection
│   ├── dependencies.py      # Dependency resolution
│   ├── verification.py      # Installation verification
│   ├── rollback.py          # Rollback system
│   ├── config_templates.py  # Config generation
│   ├── logging_system.py    # Logging & diagnostics
│   ├── context_memory.py    # AI memory system
│   └── predictive_prevention.py # Pre-install risk analysis
├── tests/
│   └── test_*.py            # Unit tests
├── docs/
│   └── *.md                 # Documentation
└── .github/
    └── workflows/           # CI/CD
```

## Architecture

### Core Flow
```
User Input (Natural Language)
    ↓
LLM Integration Layer (Claude API)
    ↓
Package Manager Wrapper (apt/yum/dnf)
    ↓
Dependency Resolver
    ↓
Predictive Error Prevention (Risk Analysis)
    ↓
Sandbox Executor (Firejail)
    ↓
Installation Verifier
    ↓
Context Memory (learns patterns)
```

### Key Components

**LLM Integration (`llm_integration.py`)**
- Interfaces with Claude API
- Parses natural language
- Generates installation plans

**Package Manager (`packages.py`)**
- Translates intent to commands
- Supports apt, yum, dnf
- 32+ software categories

**Sandbox (`sandbox.py`)**
- Firejail isolation
- AppArmor policies
- Safe command execution

**Hardware Detection (`hardware.py`)**
- GPU/CPU detection
- Optimization recommendations
- Driver compatibility

## Contributing

### Claiming Issues

1. Browse [open issues](https://github.com/cortexlinux/cortex/issues)
2. Comment "I'd like to work on this"
3. Get assigned
4. Submit PR

### PR Requirements

- Tests with >80% coverage
- Documentation included
- Follows code style
- Passes CI checks

### Bounty Program

Cash bounties on merge:
- Critical features: $150-200
- Standard features: $75-150
- Testing/integration: $50-75
- 2x bonus at funding (Feb 2025)

Payment: Bitcoin, USDC, or PayPal

See [Bounty Program](Bounties) for details.

## Testing
```bash
# Run all tests
pytest

# Specific test file
pytest tests/test_packages.py

# With coverage
pytest --cov=cortex tests/

# Watch mode
pytest-watch
```

## Code Style
```bash
# Format code
black cortex/

# Lint
pylint cortex/

# Type checking
mypy cortex/
```

## Questions?

- Discord: https://discord.gg/uCqHvxjU83
- GitHub Discussions: https://github.com/cortexlinux/cortex/discussions
