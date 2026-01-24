<p align="center">
  <img src="images/logo.png" alt="Cortex Linux" width="200" />
</p>

<h1 align="center">Cortex Linux</h1>

<p align="center">
  <strong>AI-Powered Package Manager for Debian/Ubuntu</strong><br>
  Install software using natural language. No more memorizing package names.
</p>

<p align="center">
  <a href="https://github.com/cortexlinux/cortex/actions/workflows/ci.yml">
    <img src="https://github.com/cortexlinux/cortex/actions/workflows/ci.yml/badge.svg" alt="CI Status" />
  </a>
  <a href="https://github.com/cortexlinux/cortex/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License" />
  </a>
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+" />
  </a>
  <a href="https://github.com/cortexlinux/cortex/releases">
    <img src="https://img.shields.io/badge/version-0.1.0--alpha-orange.svg" alt="Version" />
  </a>
  <a href="https://discord.gg/uCqHvxjU83">
    <img src="https://img.shields.io/discord/1234567890?color=7289da&label=Discord&logo=discord&logoColor=white" alt="Discord" />
  </a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#features">Features</a> •
  <a href="#usage">Usage</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#contributing">Contributing</a> •
  <a href="#community">Community</a>
</p>

---

## What is Cortex?

Cortex is an AI-native package manager that understands what you want to install, even when you don't know the exact package name.

```bash
# Instead of googling "what's the package name for PDF editing on Ubuntu?"
cortex install "something to edit PDFs"

# Instead of remembering exact package names
cortex install "a lightweight code editor with syntax highlighting"

# Natural language just works
cortex install "tools for video compression"
```

<p align="center">
  <img src="images/cortex_demo.gif" alt="Cortex Demo" width="700" />
</p>

---

## Features

| Feature | Description |
|---------|-------------|
| **Natural Language** | Describe what you need in plain English |
| **Dry-Run Default** | Preview all commands before execution |
| **Sandboxed Execution** | Commands run in Firejail isolation |
| **Full Rollback** | Undo any installation with `cortex rollback` |
| **Audit Trail** | Complete history in `~/.cortex/history.db` |
| **Hardware-Aware** | Detects GPU, CPU, memory for optimized packages |
| **Smart Update Recommendations** | AI-powered update recommendations and risk assessment |
| **Predictive Error Prevention** | AI-driven checks for potential installation failures |
| **Multi-LLM Support** | Works with Claude, GPT-4, or local Ollama models |

---

## Quick Start

### Prerequisites

- **OS:** Ubuntu 22.04+ / Debian 12+
- **Python:** 3.10 or higher
- **API Key:** [Anthropic](https://console.anthropic.com) or [OpenAI](https://platform.openai.com) *(optional - use Ollama for free local inference)*

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/cortexlinux/cortex.git
cd cortex

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Cortex
pip install -e .

# 4. Configure AI Provider (choose one):

## Option A: Ollama (FREE - Local LLM, no API key needed)
python scripts/setup_ollama.py

## Option B: Claude (Cloud API - Best quality)
echo 'ANTHROPIC_API_KEY=your-key-here' > .env

## Option C: OpenAI (Cloud API - Alternative)
echo 'OPENAI_API_KEY=your-key-here' > .env

# 5. Verify installation
cortex --version
```

### First Run

```bash
# Preview what would be installed (safe, no changes made)
cortex install nginx --dry-run

# Actually install
cortex install nginx --execute
```

### AI Command Execution Setup (`ask --do`)

For the full AI-powered command execution experience, run the setup script:

```bash
# Full setup (Ollama + Watch Service + Shell Hooks)
./scripts/setup_ask_do.sh

# Or use Python directly
python scripts/setup_ask_do.py

# Options:
#   --no-docker     Skip Docker/Ollama setup (use cloud LLM only)
#   --model phi     Use a smaller model (2GB instead of 4GB)
#   --skip-watch    Skip watch service installation
#   --uninstall     Remove all components
```

This script will:
1. **Set up Ollama** with a local LLM (Mistral by default) in Docker
2. **Install the Watch Service** for terminal monitoring
3. **Configure Shell Hooks** for command logging
4. **Verify everything works**

#### Quick Start After Setup

```bash
# Start an interactive AI session
cortex ask --do

# Or with a specific task
cortex ask --do "install nginx and configure it for reverse proxy"

# Check watch service status
cortex watch --status
```

#### Manual Setup (Alternative)

If you prefer manual setup:

```bash
# Install the Cortex Watch service (runs automatically on login)
cortex watch --install --service

# Check status
cortex watch --status

# For Ollama (optional - for local LLM)
docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama
docker exec ollama ollama pull mistral
```

This enables Cortex to monitor your terminal activity during manual intervention mode, providing real-time AI feedback and error detection.

---

## Usage

### Basic Commands

```bash
# Install with natural language
cortex install "web server for static sites" --dry-run
cortex install "image editing software like photoshop" --execute

# View installation history
cortex history

# Rollback an installation
cortex rollback <installation-id>

# Get smart update recommendations
cortex update recommend
```

### Command Reference

| Command | Description |
|---------|-------------|
| `cortex install <query>` | Install packages matching natural language query |
| `cortex install <query> --dry-run` | Preview installation plan (default) |
| `cortex install <query> --execute` | Execute the installation |
| `cortex ask <question>` | Ask questions about your system |
| `cortex ask --do` | Interactive AI command execution mode |
| `cortex sandbox <cmd>` | Test packages in Docker sandbox |
| `cortex history` | View all past installations |
| `cortex rollback <id>` | Undo a specific installation |
| `cortex update recommend` | Get AI-powered update recommendations |
| `cortex watch --install --service` | Install terminal monitoring service |
| `cortex watch --status` | Check terminal monitoring status |
| `cortex --version` | Show version information |
| `cortex --help` | Display help message |

### Configuration

Cortex stores configuration in `~/.cortex/`:

```
~/.cortex/
├── config.yaml           # User preferences
├── history.db            # Installation history (SQLite)
├── audit.log             # Detailed audit trail
├── terminal_watch.log    # Terminal monitoring log
└── watch_service.log     # Watch service logs
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Input                              │
│                    "install video editor"                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Interface                            │
│                         (cli.py)                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LLM Router                                 │
│              Claude / GPT-4 / Ollama                            │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Anthropic  │  │   OpenAI    │  │   Ollama    │             │
│  │   Claude    │  │    GPT-4    │  │   Local     │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Coordinator                                 │
│            (Plan Generation & Validation)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│    Hardware     │ │    Package      │ │    Sandbox      │
│    Detection    │ │    Manager      │ │    Executor     │
│                 │ │  (apt/yum/dnf)  │ │   (Firejail)    │
└─────────────────┘ └─────────────────┘ └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Installation History                          │
│                 (SQLite + Audit Logging)                        │
└─────────────────────────────────────────────────────────────────┘
```

### Project Structure

```
cortex/
├── cortex/                 # Main package
│   ├── cli.py              # Command-line interface
│   ├── ask.py              # AI Q&A and command execution
│   ├── coordinator.py      # Installation orchestration
│   ├── llm_router.py       # Multi-LLM routing
│   ├── packages.py         # Package manager wrapper
│   ├── hardware_detection.py
│   ├── installation_history.py
│   ├── watch_service.py    # Terminal monitoring service
│   ├── do_runner/          # AI command execution
│   │   ├── handler.py      # Main execution handler
│   │   ├── terminal.py     # Terminal monitoring
│   │   ├── diagnosis.py    # Error diagnosis & auto-fix
│   │   └── verification.py # Conflict detection
│   └── utils/              # Utility modules
├── tests/                  # Test suite
├── docs/                   # Documentation
│   └── ASK_DO_ARCHITECTURE.md  # ask --do deep dive
├── examples/               # Example scripts
└── scripts/                # Utility scripts
    ├── setup_ask_do.py     # Full ask --do setup
    ├── setup_ask_do.sh     # Bash setup alternative
    └── setup_ollama.py     # Ollama-only setup
```

---

## Safety & Security

Cortex is designed with security as a priority:

| Protection | Implementation |
|------------|----------------|
| **Dry-run by default** | No execution without `--execute` flag |
| **Sandboxed execution** | All commands run in Firejail containers |
| **Command validation** | Dangerous patterns blocked before execution |
| **Audit logging** | Every action recorded with timestamps |
| **Rollback capability** | Full undo support for all installations |
| **No root by default** | Sudo only when explicitly required |

### Security Policy

Found a vulnerability? Please report it responsibly:
- Email: security@cortexlinux.com
- See [SECURITY.md](SECURITY.md) for our disclosure policy

---

## Troubleshooting

<details>
<summary><strong>"ANTHROPIC_API_KEY not set"</strong></summary>

```bash
# Verify .env file exists
cat .env
# Should show: ANTHROPIC_API_KEY=sk-ant-...

# If missing, create it:
echo 'ANTHROPIC_API_KEY=your-actual-key' > .env
```
</details>

<details>
<summary><strong>"command not found: cortex"</strong></summary>

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall
pip install -e .
```
</details>

<details>
<summary><strong>"Python version too old"</strong></summary>

```bash
# Check version
python3 --version

# Install Python 3.11 on Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3.11-venv

# Create venv with specific version
python3.11 -m venv venv
```
</details>

<details>
<summary><strong>pip install fails</strong></summary>

```bash
# Update pip
pip install --upgrade pip

# Install build dependencies
sudo apt install python3-dev build-essential

# Retry installation
pip install -e .
```
</details>

---

## Project Status

> **Alpha Release** - Cortex is under active development. APIs may change.

### Completed
- [x] Natural language to package resolution
- [x] Claude and OpenAI integration
- [x] Installation history and rollback
- [x] User preferences (YAML-backed)
- [x] Hardware detection (GPU/CPU/Memory)
- [x] Firejail sandboxing
- [x] Dry-run preview mode

### In Progress
- [ ] Conflict resolution UI
- [ ] Multi-step orchestration
- [ ] Ollama local model support
- [ ] MCP server integration
- [ ] Snap/Flatpak support

### Planned
- [ ] Fedora/RHEL support
- [ ] Arch Linux support
- [ ] Web UI dashboard
- [ ] VS Code extension

See [ROADMAP.md](docs/ROADMAP.md) for the full development roadmap.

---

## Contributing

We welcome contributions of all kinds!

### Ways to Contribute

- **Code**: Python, Linux kernel optimizations
- **Documentation**: Guides, tutorials, API docs
- **Testing**: Bug reports, test coverage
- **Design**: UI/UX improvements

### Bounty Program

We offer bounties for merged PRs:

| Tier | Reward | Examples |
|------|--------|----------|
| Small | $25 | Bug fixes, typos, minor features |
| Medium | $50-100 | New features, significant improvements |
| Large | $150-200 | Major features, security fixes |

See issues labeled [`bounty`](https://github.com/cortexlinux/cortex/labels/bounty) for available tasks.

### Getting Started

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/cortex.git
cd cortex

# Setup development environment
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/ -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## Community

- **Discord**: [discord.gg/uCqHvxjU83](https://discord.gg/uCqHvxjU83)
- **Discussions**: [GitHub Discussions](https://github.com/cortexlinux/cortex/discussions)
- **Email**: mike@cortexlinux.com
- **Twitter**: [@cortexlinux](https://twitter.com/cortexlinux)

### Support

- **Bug Reports**: [GitHub Issues](https://github.com/cortexlinux/cortex/issues)
- **Feature Requests**: [GitHub Discussions](https://github.com/cortexlinux/cortex/discussions/categories/ideas)
- **Security Issues**: security@cortexlinux.com

---

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

---

<p align="center">
  <sub>Built with love by the Cortex team and contributors worldwide.</sub>
</p>
