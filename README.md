# Cortex Linux

> **The AI-Native Operating System** - Linux that understands you. No documentation required.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Status](https://img.shields.io/badge/Status-Alpha-orange.svg)]()
[![Discord](https://img.shields.io/discord/1234567890?color=7289da&label=Discord)](https://discord.gg/uCqHvxjU83)

```bash
$ cortex install oracle-23-ai --optimize-gpu
  Analyzing system: NVIDIA RTX 4090 detected
  Installing CUDA 12.3 + dependencies
  Configuring Oracle for GPU acceleration
  Running validation tests
 Oracle 23 AI ready at localhost:1521 (4m 23s)
```

---

## Table of Contents

- [The Problem](#the-problem)
- [The Solution](#the-solution)
- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Development](#development)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [FAQ](#faq)
- [Community](#community)
- [License](#license)

---

## The Problem

Installing complex software on Linux is broken:

-  **47 Stack Overflow tabs** to install CUDA drivers
-  **Dependency hell** that wastes days
-  **Configuration files** written in ancient runes
-  **"Works on my machine"** syndrome

**Developers spend 30% of their time fighting the OS instead of building.**

## The Solution

Cortex Linux embeds AI at the operating system level. Tell it what you need in plain English - it handles everything:

| Feature | Description |
|---------|-------------|
| **Natural Language Commands** | System understands intent, not syntax |
| **Hardware-Aware Optimization** | Automatically configures for your GPU/CPU |
| **Self-Healing Configuration** | Fixes broken dependencies automatically |
| **Enterprise-Grade Security** | AI actions are sandboxed and validated |
| **Installation History** | Track and rollback any installation |

---

## Features

### Core Capabilities

- **Natural Language Parsing** - "Install Python for machine learning" just works
- **Multi-Provider LLM Support** - Claude (Anthropic) and OpenAI GPT-4
- **Intelligent Package Management** - Wraps apt/yum/dnf with semantic understanding
- **Hardware Detection** - Automatic GPU, CPU, RAM, storage profiling
- **Sandboxed Execution** - Firejail-based isolation for all commands
- **Installation Rollback** - Undo any installation with one command
- **Error Analysis** - AI-powered error diagnosis and fix suggestions

### Supported Software (32+ Categories)

| Category | Examples |
|----------|----------|
| Languages | Python, Node.js, Go, Rust |
| Databases | PostgreSQL, MySQL, MongoDB, Redis |
| Web Servers | Nginx, Apache |
| Containers | Docker, Kubernetes |
| DevOps | Terraform, Ansible |
| ML/AI | CUDA, TensorFlow, PyTorch |

---

## Quick Start

```bash
# Install cortex
pip install cortex-linux

# Set your API key (choose one)
export ANTHROPIC_API_KEY="your-key-here"
# or
export OPENAI_API_KEY="your-key-here"

# Install software with natural language
cortex install docker
cortex install "python for data science"
cortex install "web development environment"

# Execute the installation
cortex install docker --execute

# Preview without executing
cortex install nginx --dry-run
```

---

## Installation

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **OS** | Ubuntu 24.04 LTS | Other Debian-based coming soon |
| **Python** | 3.10+ | Required |
| **Firejail** | Latest | Recommended for sandboxing |
| **API Key** | - | Anthropic or OpenAI |

### Step-by-Step Installation

```bash
# 1. Install system dependencies
sudo apt update
sudo apt install -y python3 python3-pip python3-venv firejail

# 2. Create virtual environment (recommended)
python3 -m venv ~/.cortex-venv
source ~/.cortex-venv/bin/activate

# 3. Install Cortex
pip install cortex-linux

# 4. Configure API key
echo 'export ANTHROPIC_API_KEY="your-key"' >> ~/.bashrc
source ~/.bashrc

# 5. Verify installation
cortex --help
```

### From Source

```bash
git clone https://github.com/cortexlinux/cortex.git
cd cortex
pip install -e .
```

---

## Usage

### Basic Commands

```bash
# Install software
cortex install <software>           # Show commands only
cortex install <software> --execute # Execute installation
cortex install <software> --dry-run # Preview mode

# Installation history
cortex history                      # List recent installations
cortex history show <id>            # Show installation details

# Rollback
cortex rollback <id>                # Undo an installation
cortex rollback <id> --dry-run      # Preview rollback
```

### Examples

```bash
# Simple installations
cortex install docker --execute
cortex install postgresql --execute
cortex install nginx --execute

# Natural language requests
cortex install "python with machine learning libraries" --execute
cortex install "web development stack with nodejs and npm" --execute
cortex install "database tools for postgresql" --execute

# Complex requests
cortex install "cuda drivers for nvidia gpu" --execute
cortex install "complete devops toolchain" --execute
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | One of these |
| `OPENAI_API_KEY` | OpenAI GPT-4 API key | required |
| `MOONSHOT_API_KEY` | Kimi K2 API key | Optional |
| `CORTEX_LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING) | No |
| `CORTEX_DATA_DIR` | Data directory path | No |

---

## Configuration

### Configuration File

Create `~/.config/cortex/config.yaml`:

```yaml
# LLM Provider Settings
llm:
  default_provider: claude  # claude, openai, kimi
  temperature: 0.3
  max_tokens: 1000

# Security Settings
security:
  enable_sandbox: true
  require_confirmation: true
  allowed_directories:
    - /tmp
    - ~/.local

# Logging
logging:
  level: INFO
  file: ~/.local/share/cortex/cortex.log
```

---

## Architecture

```
                    User Input

               Natural Language

              Cortex CLI

          +--------+--------+
          |                 |
     LLM Router       Hardware
          |           Profiler
          |
  +-------+-------+
  |       |       |
Claude  GPT-4  Kimi K2
          |
    Command Generator
          |
   Security Validator
          |
   Sandbox Executor
          |
  +-------+-------+
  |               |
apt/yum/dnf   Verifier
                  |
           Installation
             History
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| CLI | `cortex/cli.py` | Command-line interface |
| Coordinator | `cortex/coordinator.py` | Installation orchestration |
| LLM Interpreter | `LLM/interpreter.py` | Natural language to commands |
| Package Manager | `cortex/packages.py` | Package manager abstraction |
| Sandbox | `src/sandbox_executor.py` | Secure command execution |
| Hardware Profiler | `src/hwprofiler.py` | System hardware detection |
| History | `installation_history.py` | Installation tracking |
| Error Parser | `error_parser.py` | Error analysis and fixes |

---

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/cortexlinux/cortex.git
cd cortex

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install in development mode
pip install -e .

# Run tests
pytest test/ -v

# Run with coverage
pytest test/ --cov=cortex --cov-report=html
```

### Code Style

```bash
# Format code
black cortex/

# Lint
pylint cortex/

# Type checking
mypy cortex/
```

### Project Structure

```
cortex/
 cortex/              # Core Python package
    __init__.py
    cli.py            # CLI entry point
    coordinator.py    # Installation coordinator
    packages.py       # Package manager wrapper
 LLM/                 # LLM integration
    interpreter.py    # Command interpreter
    requirements.txt
 src/                 # Additional modules
    sandbox_executor.py
    hwprofiler.py
    progress_tracker.py
 test/                # Unit tests
 docs/                # Documentation
 examples/            # Usage examples
 .github/             # CI/CD workflows
 requirements.txt     # Dependencies
 setup.py             # Package config
```

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Contribution Guide

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Bounty Program

Cash bounties on merge:

| Tier | Amount | Examples |
|------|--------|----------|
| Critical | $150-200 | Security fixes, core features |
| Standard | $75-150 | New features, integrations |
| Testing | $25-75 | Tests, documentation |

**Payment methods:** Bitcoin, USDC, PayPal

See [Bounties.md](Bounties.md) for available bounties.

---

## Roadmap

### Current Status: Alpha (Phase 1)

-  LLM integration layer
-  Safe command execution sandbox
-  Hardware detection
-  Installation history & rollback
-  Error parsing & suggestions
-  Multi-provider LLM support

### Coming Soon (Phase 2)

-  Advanced dependency resolution
-  Configuration file generation
-  Multi-step installation orchestration
-  Plugin architecture

### Future (Phase 3)

-  Enterprise deployment tools
-  Security hardening & audit logging
-  Role-based access control
-  Air-gapped deployment support

See [ROADMAP.md](ROADMAP.md) for detailed plans.

---

## FAQ

<details>
<summary><strong>What operating systems are supported?</strong></summary>

Currently Ubuntu 24.04 LTS. Other Debian-based distributions coming soon.
</details>

<details>
<summary><strong>Is it free?</strong></summary>

Yes! Community edition is free and open source (Apache 2.0). Enterprise subscriptions will be available for advanced features.
</details>

<details>
<summary><strong>Is it secure?</strong></summary>

Yes. All commands are validated and executed in a Firejail sandbox with AppArmor policies. AI-generated commands are checked against a security allowlist.
</details>

<details>
<summary><strong>Can I use my own LLM?</strong></summary>

Currently supports Claude (Anthropic) and OpenAI. Local LLM support is planned for future releases.
</details>

<details>
<summary><strong>What if something goes wrong?</strong></summary>

Every installation is tracked and can be rolled back with `cortex rollback <id>`.
</details>

See [FAQ.md](FAQ.md) for more questions.

---

## Community

### Get Help

-  **Discord:** [Join our server](https://discord.gg/uCqHvxjU83)
-  **GitHub Issues:** [Report bugs](https://github.com/cortexlinux/cortex/issues)
-  **Discussions:** [Ask questions](https://github.com/cortexlinux/cortex/discussions)

### Stay Updated

-  Star this repository
-  Follow [@cortexlinux](https://twitter.com/cortexlinux) on Twitter
-  Subscribe to our [newsletter](https://cortexlinux.com)

---

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Built with [Claude](https://anthropic.com) and [OpenAI](https://openai.com)
- Sandbox powered by [Firejail](https://firejail.wordpress.com/)
- Inspired by the pain of every developer who spent hours on Stack Overflow

---

<p align="center">
  <strong>Star this repo to follow development</strong>
  <br><br>
  Built with  by the Cortex Linux community
</p>
