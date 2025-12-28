# Contributing to Cortex Linux

Thank you for your interest in contributing to Cortex Linux! We're building the AI-native operating system and need your help.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Code Style Guide](#code-style-guide)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)
- [Bounty Program](#bounty-program)
- [Community](#community)

---

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please:

- Be respectful and considerate
- Use welcoming and inclusive language
- Accept constructive criticism gracefully
- Focus on what's best for the community
- Show empathy towards other community members

---

## Getting Started

### Prerequisites

Before contributing, ensure you have:

- **Python 3.10+** installed
- **Git** for version control
- A **GitHub account**
- An API key (Anthropic or OpenAI) for testing

### Quick Start

1. **Fork the repository** on GitHub
2. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR-USERNAME/cortex.git
   cd cortex
   ```
3. **Set up development environment** (see below)
4. **Create a branch** for your changes
5. **Make your changes** and test them
6. **Submit a Pull Request**

---

## Development Setup

### Complete Setup

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/cortex.git
cd cortex

# Add upstream remote
git remote add upstream https://github.com/cortexlinux/cortex.git

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install in development mode
pip install -e .

# Run tests to verify setup
pytest tests/ -v
```

### Requirements Files

If `requirements-dev.txt` doesn't exist, install these manually:

```bash
pip install pytest pytest-cov pytest-mock black pylint mypy bandit
```

### IDE Setup

**VS Code (Recommended):**
```json
// .vscode/settings.json
{
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests/"]
}
```

---

## How to Contribute

### Types of Contributions

| Type | Description | Bounty Eligible |
|------|-------------|-----------------|
| Bug Fixes | Fix existing issues | Yes |
| Features | Add new functionality | Yes |
| Tests | Improve test coverage | Yes |
| Documentation | Update docs, comments | Yes |
| Code Review | Review PRs | No |
| Triage | Categorize issues | No |

### Finding Issues to Work On

1. Browse [open issues](https://github.com/cortexlinux/cortex/issues)
2. Look for labels:
   - `good first issue` - Great for newcomers
   - `help wanted` - Ready for contribution
   - `bounty` - Has cash reward
   - `priority:high` - Important issues
3. Comment "I'd like to work on this" to claim an issue
4. Wait for assignment before starting (prevents duplicate work)

---

## Pull Request Process

### Before Submitting

- [ ] Code follows style guide
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] New code has tests (aim for >80% coverage)
- [ ] Documentation is updated if needed
- [ ] Commit messages are clear
- [ ] Branch is up to date with `main`

### PR Template

```markdown
## Summary
Brief description of changes (2-3 sentences).

## Related Issue
Closes #123

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
How did you test these changes?

## Checklist
- [ ] Tests pass locally
- [ ] Code follows style guide
- [ ] Documentation updated
```

### Review Process

1. **Automated checks** run on PR creation
2. **Maintainer review** within 48-72 hours
3. **Address feedback** if changes requested
4. **Approval** from at least one maintainer
5. **Merge** by maintainer

---

## Code Style Guide

### Python Style

We follow **PEP 8** with some modifications:

```python
# Use 4 spaces for indentation (not tabs)
# Line length: 100 characters max

# Use snake_case for functions and variables
def calculate_dependencies(package_name: str) -> List[str]:
    pass

# Use PascalCase for classes
class InstallationCoordinator:
    pass

# Use UPPER_CASE for constants
MAX_RETRY_ATTEMPTS = 3
DEFAULT_TIMEOUT = 300
```

### Docstrings

Use Google-style docstrings:

```python
def install_package(
    package_name: str,
    dry_run: bool = False,
    timeout: int = 300
) -> InstallationResult:
    """Install a package using the appropriate package manager.

    Args:
        package_name: Name of the package to install.
        dry_run: If True, show commands without executing.
        timeout: Maximum time in seconds for installation.

    Returns:
        InstallationResult containing success status and details.

    Raises:
        ValueError: If package_name is empty.
        TimeoutError: If installation exceeds timeout.
    """
    pass
```

### Type Hints

Always use type hints:

```python
from typing import List, Dict, Optional

def parse_request(
    request: str,
    context: Optional[Dict[str, str]] = None
) -> List[str]:
    pass
```

### Formatting

Use **black** for formatting:

```bash
black cortex/ --check  # Check formatting
black cortex/          # Format all files
```

---

## Testing Guidelines

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=cortex --cov-report=html

# Run specific test file
pytest tests/test_cli.py -v
```

### Coverage Requirements

- **New code:** Must have >80% coverage
- **Overall project:** Target 70% minimum
- **Critical modules:** Target 90%+

---

## Bounty Program

### How It Works

1. **Find bounty issue** - Look for `bounty` label
2. **Claim the issue** - Comment to get assigned
3. **Complete the work** - Submit quality PR
4. **Get reviewed and merged**
5. **Receive payment** within 48 hours

### Bounty Tiers

| Tier | Amount | Description |
|------|--------|-------------|
| **Critical** | $150-200 | Security fixes, core features |
| **Important** | $100-150 | Significant features |
| **Standard** | $75-100 | Regular features |
| **Testing** | $50-75 | Test coverage improvements |
| **Docs** | $25-50 | Documentation updates |

### Payment Methods

- Bitcoin (preferred)
- USDC (Ethereum or Polygon)
- PayPal

---

## Community

### Communication Channels

| Channel | Purpose |
|---------|---------|
| **Discord** | Real-time chat, questions |
| **GitHub Issues** | Bug reports, features |
| **GitHub Discussions** | Long-form discussions |

### Discord Server

Join us: [https://discord.gg/uCqHvxjU83](https://discord.gg/uCqHvxjU83)

### Response Times

- **Issues:** 24-48 hours
- **PRs:** 48-72 hours
- **Discord:** Best effort (usually hours)

---

## Questions?

- **Discord:** [https://discord.gg/uCqHvxjU83](https://discord.gg/uCqHvxjU83)
- **Email:** mike@cortexlinux.com

---

**Thank you for contributing to Cortex Linux!**
