<<<<<<< HEAD
# Cortex Linux
<<<<<<< HEAD
=======
<!-- Improved compatibility of back to top link: See: https://github.com/othneildrew/Best-README-Template/pull/73 -->
<a name="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]
[![Discord][discord-shield]][discord-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/cortexlinux/cortex">
    <img src="images/logo.png" alt="Cortex Linux Logo" width="120" height="120">
  </a>

  <h3 align="center">Cortex Linux</h3>

  <p align="center">
    An AI-powered package manager that understands what you actually want to install.
    <br />
    <a href="https://cortexlinux.com/docs"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://cortexlinux.com/beta">View Demo</a>
    ·
    <a href="https://github.com/cortexlinux/cortex/issues">Report Bug</a>
    ·
    <a href="https://github.com/cortexlinux/cortex/issues">Request Feature</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#safety-features">Safety Features</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#bounties">Bounties</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgements">Acknowledgements</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
## About The Project

[![Cortex Screen Shot][product-screenshot]](https://cortexlinux.com)

Stop memorizing package names. Just tell Cortex what you want.
>>>>>>> 17831ac (feat: Add branding with CX badge + README overhaul (Alex template))

```bash
$ cortex install "full ML stack for my RTX 4090"

🔍 Detected: NVIDIA RTX 4090 (24GB VRAM)
📦 Installing: CUDA 12.3, cuDNN, PyTorch 2.1, TensorFlow...
⚡ Optimized for your GPU
✅ Done in 4m 23s
```

Here's why Cortex exists:

<<<<<<< HEAD
Cortex wraps `apt` with AI to:
- Parse natural language requests ("install something for web serving")
- Detect hardware and optimize installations for your GPU/CPU
- Resolve dependency conflicts interactively
- Track installation history with rollback support
- Run in dry-run mode by default (no surprises)
=======

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
>>>>>>> 1c5eeca (Code review: Security fixes, documentation overhaul, CI/CD repair (#208))
=======
* **Natural language** — Say "install docker" not `apt install docker.io docker-compose docker-buildx`
* **Hardware-aware** — Automatically detects your GPU, CPU, and RAM to optimize installations
* **Safe by default** — Every command shows a preview before execution. Nothing runs without your approval.
* **Undo mistakes** — Full transaction history with rollback capability
>>>>>>> 17831ac (feat: Add branding with CX badge + README overhaul (Alex template))

Cortex wraps apt/dpkg with an AI layer that translates intent into action, while keeping you in control.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

* [![Python][Python-badge]][Python-url]
* [![Ubuntu][Ubuntu-badge]][Ubuntu-url]
* [![Claude][Claude-badge]][Claude-url]
* [![LangChain][LangChain-badge]][LangChain-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

Get Cortex running on your Debian/Ubuntu system in under 2 minutes.

### Prerequisites

* Ubuntu 22.04+ or Debian 11+
* Python 3.11+
* An Anthropic API key ([get one here](https://console.anthropic.com))

### Installation

**One-liner install (coming soon):**
```bash
<<<<<<< HEAD
# Clone the repo
git clone https://github.com/cortexlinux/cortex.git
cd cortex

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

<<<<<<< HEAD
# Install
pip install -e .

# Set your API key
echo 'ANTHROPIC_API_KEY=your-key-here' > .env
=======
Cortex Linux embeds AI at the operating system level. Tell it what you need in plain English - it handles everything:

| Feature | Description |
|---------|-------------|
| **Natural Language Commands** | System understands intent, not syntax |
| **Hardware-Aware Optimization** | Automatically configures for your GPU/CPU |
| **Self-Healing Configuration** | Fixes broken dependencies automatically |
| **Enterprise-Grade Security** | AI actions are sandboxed and validated |
| **Installation History** | Track and rollback any installation |
>>>>>>> 1c5eeca (Code review: Security fixes, documentation overhaul, CI/CD repair (#208))

# Test it
cortex install nginx --dry-run
=======
curl -fsSL https://cortexlinux.com/install.sh | bash
>>>>>>> 17831ac (feat: Add branding with CX badge + README overhaul (Alex template))
```

**Manual install:**

1. Clone the repo
   ```bash
   git clone https://github.com/cortexlinux/cortex.git
   cd cortex
   ```

2. Create virtual environment
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies
   ```bash
   pip install -e .
   ```

4. Set your API key
   ```bash
   export ANTHROPIC_API_KEY='your-api-key-here'
   ```

5. Run Cortex
   ```bash
   cortex install docker
   ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE EXAMPLES -->
## Usage

### Basic Installation
```bash
# Natural language
cortex install "web development tools"

# Direct package
cortex install nginx

<<<<<<< HEAD
<<<<<<< HEAD
# Natural language works
cortex install "something to edit PDFs" --dry-run
=======
### Phase 1: Foundation (Weeks 1-2)
- ✅ LLM integration layer (PR #5 by @Sahilbhatane)
- ✅ Safe command execution sandbox (PR #6 by @dhvil)
- ✅ Hardware detection (PR #4 by @dhvil)
- ✅ Package manager AI wrapper
- ✅ Installation history & rollback
- [ ] Basic multi-step orchestration
>>>>>>> 1c5eeca (Code review: Security fixes, documentation overhaul, CI/CD repair (#208))
=======
# Multiple packages
cortex install "docker, nodejs, and postgresql"
```
>>>>>>> 17831ac (feat: Add branding with CX badge + README overhaul (Alex template))

### Dry Run (Preview Mode)
```bash
# See what would happen without executing
cortex install tensorflow --dry-run
```

### Search Packages
```bash
# Fuzzy search
cortex search "video editor"
```

### Transaction History
```bash
# View what Cortex has done
cortex history

# Undo last operation
cortex undo
```

### Hardware Detection
```bash
# See what Cortex knows about your system
cortex hardware
```

_For more examples, please refer to the [Documentation](https://cortexlinux.com/docs)_

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- SAFETY FEATURES -->
## Safety Features

| Feature | Description |
|---------|-------------|
| **Dry-run mode** | Preview all commands before execution |
| **Transaction log** | Every operation is recorded with undo capability |
| **Firejail sandbox** | Optional sandboxing for untrusted packages |
| **Confirmation prompts** | Nothing executes without explicit approval |
| **Rollback support** | Integration with Timeshift/Snapper snapshots |

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ROADMAP -->
## Roadmap

- [x] Natural language to apt translation
- [x] Hardware detection (GPU, CPU, RAM)
- [x] Dry-run mode
- [x] Firejail sandboxing
- [ ] Interactive fuzzy search (fzf integration)
- [ ] One-liner install script
- [ ] Offline mode with semantic caching
- [ ] Local LLM fallback (Ollama)
- [ ] System snapshot integration
- [ ] Web dashboard

See the [open issues](https://github.com/cortexlinux/cortex/issues) for a full list of proposed features and known issues.

<<<<<<< HEAD
## Tech Stack

- **Base OS**: Ubuntu 24.04 LTS (Debian packaging)
- **AI Layer**: Python 3.11+, LangChain, Claude API
- **Security**: Firejail sandboxing, AppArmor policies
- **Package Management**: apt wrapper with semantic understanding
- **Hardware Detection**: hwinfo, lspci, nvidia-smi integration

## Get Involved

**We need:**
- Linux Kernel Developers
- AI/ML Engineers
- DevOps Experts
- Technical Writers
- Beta Testers

Browse [Issues](../../issues) for contribution opportunities.

### Join the Community

- **Discord**: https://discord.gg/uCqHvxjU83
- **Email**: mike@cortexlinux.com

## Why This Matters

**Market Opportunity**: $50B+ (10x Cursor's $9B valuation)

- Cursor wraps VS Code → $9B valuation
- Cortex wraps entire OS → 10x larger market
- Every data scientist, ML engineer, DevOps team needs this

**Business Model**: Open source community edition + Enterprise subscriptions

## Founding Team

**Michael J. Morgan** - CEO/Founder  
AI Venture Holdings LLC | Patent holder in AI-accelerated systems

**You?** - Looking for technical co-founders from the contributor community.

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
=======
<p align="right">(<a href="#readme-top">back to top</a>)</p>
>>>>>>> 17831ac (feat: Add branding with CX badge + README overhaul (Alex template))

<!-- CONTRIBUTING -->
## Contributing

<<<<<<< HEAD
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
=======
Contributions make the open source community amazing. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request
>>>>>>> 17831ac (feat: Add branding with CX badge + README overhaul (Alex template))

See `CONTRIBUTING.md` for detailed guidelines.

<<<<<<< HEAD
### Get Help

-  **Discord:** [Join our server](https://discord.gg/uCqHvxjU83)
-  **GitHub Issues:** [Report bugs](https://github.com/cortexlinux/cortex/issues)
-  **Discussions:** [Ask questions](https://github.com/cortexlinux/cortex/discussions)

### Stay Updated

-  Star this repository
-  Follow [@cortexlinux](https://twitter.com/cortexlinux) on Twitter
-  Subscribe to our [newsletter](https://cortexlinux.com)

---
=======
<p align="right">(<a href="#readme-top">back to top</a>)</p>
>>>>>>> 17831ac (feat: Add branding with CX badge + README overhaul (Alex template))

<!-- BOUNTIES -->
## Bounties

We pay contributors for merged PRs. 💰

| Tier | Current | After Funding |
|------|---------|---------------|
| Quick fix | $25 | +$25 bonus |
| Small feature | $50 | +$50 bonus |
| Medium feature | $75-100 | +$75-100 bonus |
| Large feature | $150-175 | +$150-175 bonus |

**Early contributors get double** — when we close funding, all previous bounties receive a matching bonus.

See issues labeled [`bounty`](https://github.com/cortexlinux/cortex/labels/bounty) to get started.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- LICENSE -->
## License

<<<<<<< HEAD
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
=======
Distributed under the MIT License. See `LICENSE` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTACT -->
## Contact

Mike Morgan - [@mikejmorgan_ai](https://twitter.com/mikejmorgan_ai)

Project Link: [https://github.com/cortexlinux/cortex](https://github.com/cortexlinux/cortex)

Discord: [https://discord.gg/cortexlinux](https://discord.gg/uCqHvxjU83)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ACKNOWLEDGEMENTS -->
## Acknowledgements

* [Anthropic Claude](https://anthropic.com) - AI backbone
* [LangChain](https://langchain.com) - LLM orchestration
* [Rich](https://github.com/Textualize/rich) - Terminal formatting
* [Firejail](https://firejail.wordpress.com) - Sandboxing
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template) - This README structure

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/cortexlinux/cortex.svg?style=for-the-badge
[contributors-url]: https://github.com/cortexlinux/cortex/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/cortexlinux/cortex.svg?style=for-the-badge
[forks-url]: https://github.com/cortexlinux/cortex/network/members
[stars-shield]: https://img.shields.io/github/stars/cortexlinux/cortex.svg?style=for-the-badge
[stars-url]: https://github.com/cortexlinux/cortex/stargazers
[issues-shield]: https://img.shields.io/github/issues/cortexlinux/cortex.svg?style=for-the-badge
[issues-url]: https://github.com/cortexlinux/cortex/issues
[license-shield]: https://img.shields.io/github/license/cortexlinux/cortex.svg?style=for-the-badge
[license-url]: https://github.com/cortexlinux/cortex/blob/main/LICENSE
[discord-shield]: https://img.shields.io/discord/1234567890?style=for-the-badge&logo=discord&logoColor=white
[discord-url]: https://discord.gg/uCqHvxjU83
[product-screenshot]: images/screenshot.png
[Python-badge]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
[Python-url]: https://python.org
[Ubuntu-badge]: https://img.shields.io/badge/Ubuntu-E95420?style=for-the-badge&logo=ubuntu&logoColor=white
[Ubuntu-url]: https://ubuntu.com
[Claude-badge]: https://img.shields.io/badge/Claude-191919?style=for-the-badge&logo=anthropic&logoColor=white
[Claude-url]: https://anthropic.com
[LangChain-badge]: https://img.shields.io/badge/LangChain-121212?style=for-the-badge&logo=chainlink&logoColor=white
[LangChain-url]: https://langchain.com
>>>>>>> 17831ac (feat: Add branding with CX badge + README overhaul (Alex template))
