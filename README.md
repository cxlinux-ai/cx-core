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
| **🤖 Natural Language** | Describe what you need in plain English |
| **🔒 Privacy-First** | Local LLM support via Ollama - no API keys required |
| **📴 Offline Capable** | Works completely offline with local models |
| **🆓 Zero Cost** | Free local inference, optional cloud fallback |
| **🛡️ Sandboxed Execution** | Commands run in Firejail isolation |
| **⏮️ Full Rollback** | Undo any installation with `cortex rollback` |
| **📋 Audit Trail** | Complete history in `~/.cortex/history.db` |
| **🔧 Hardware-Aware** | Detects GPU, CPU, memory for optimized packages |
| **☁️ Multi-LLM Support** | Ollama (local), Claude, GPT-4, or Kimi K2 |

---

## Quick Start

### Prerequisites

- **OS:** Ubuntu 22.04+ / Debian 12+
- **Python:** 3.10 or higher
- **API Key (Optional):** [Anthropic](https://console.anthropic.com) or [OpenAI](https://platform.openai.com) for cloud fallback

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

# The setup will run automatically when you first use cortex
# You'll be prompted to select which Ollama model to download

# 4. (Optional) Configure cloud API key for fallback
echo 'ANTHROPIC_API_KEY=your-key-here' > .env

# 5. Verify installation and trigger setup
cortex --version

# 6. Check Ollama status and installed models
ollama list
```

> **🎉 No API Keys Required!** Cortex automatically sets up Ollama on first use for local, privacy-first LLM inference. You'll be prompted to select which model to download (codellama:7b recommended). Cloud API keys are optional fallbacks.

### First Run

```bash
# Preview what would be installed (safe, no changes made)
# Uses local Ollama by default - no API calls!
cortex install nginx --dry-run

# Actually install
cortex install nginx --execute
```

---

## Usage

### Basic Commands

```bash
# Install with natural language (uses local LLM)
cortex install "web server for static sites" --dry-run
cortex install "image editing software like photoshop" --execute

# View installation history
cortex history

# Rollback an installation
cortex rollback <installation-id>

# Check system preferences
cortex check-pref

# Manage local LLM models
ollama list                    # Show available models
ollama pull llama3:8b         # Download a model
cortex-setup-ollama           # Re-run Ollama setup
```

### Command Reference

| Command | Description |
|---------|-------------|
| `cortex install <query>` | Install packages matching natural language query |
| `cortex install <query> --dry-run` | Preview installation plan (default) |
| `cortex install <query> --execute` | Execute the installation |
| `cortex history` | View all past installations |
| `cortex rollback <id>` | Undo a specific installation |
| `cortex check-pref` | Display current preferences |
| `cortex-setup-ollama` | Setup/reinstall Ollama integration |
| `cortex --version` | Show version information |
| `cortex --help` | Display help message |

### Configuration

Cortex stores configuration in `~/.cortex/`:

```
~/.cortex/
├── config.yaml      # User preferences
├── history.db       # Installation history (SQLite)
└── audit.log        # Detailed audit trail
```

### Local LLM Support (Ollama)

**Privacy-First by Default**: Cortex uses local LLMs via Ollama for zero-cost, offline-capable operation.

**Benefits:**
- ✅ **100% Private**: All processing happens locally
- ✅ **Completely Offline**: Works without internet after setup
- ✅ **Zero Cost**: No API fees or subscriptions
- ✅ **No API Keys**: Get started immediately

**Recommended Models:**
- `phi3:mini` (1.9GB) - Lightweight, default
- `llama3:8b` (4.7GB) - Balanced performance
- `codellama:13b` (9GB) - Code-optimized
- `deepseek-coder-v2:16b` (10GB+) - Best for system tasks

**Manage Models:**
```bash
ollama list                     # Show installed models
ollama pull llama3:8b          # Download a model
ollama rm phi3:mini            # Remove a model
```

**Cloud Fallback:**
If local models are unavailable, Cortex automatically falls back to cloud providers (if configured):
```bash
# Optional: Set cloud API keys for fallback
export ANTHROPIC_API_KEY=your-claude-key
export OPENAI_API_KEY=your-openai-key
```

📖 **[Full Ollama Documentation](docs/OLLAMA_INTEGRATION.md)**

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
│         Ollama (Local) → Claude → GPT-4 → Kimi K2              │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Ollama    │  │  Anthropic  │  │   OpenAI    │             │
│  │   (Local)   │  │   Claude    │  │    GPT-4    │             │
│  │  PRIORITY   │  │  Fallback 1 │  │  Fallback 2 │             │
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
│   ├── coordinator.py      # Installation orchestration
│   ├── llm_router.py       # Multi-LLM routing
│   ├── packages.py         # Package manager wrapper
│   ├── hardware_detection.py
│   ├── installation_history.py
│   └── utils/              # Utility modules
├── tests/                  # Test suite
├── docs/                   # Documentation
├── examples/               # Example scripts
└── scripts/                # Utility scripts
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
