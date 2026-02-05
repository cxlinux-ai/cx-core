<p align="center">
  <img src="assets/icon/cx-terminal-icon.svg" alt="CX Linux Logo" width="200" />
</p>

<h1 align="center">CX Linux</h1>

<p align="center">
  <strong>AI Agents for Linux Administration</strong><br>
  Natural language system management. Works in any terminal.
</p>

<p align="center">
  <a href="#quick-start">
    <img src="https://img.shields.io/badge/pip%20install-cx--linux-blue.svg" alt="pip install cx-linux" />
  </a>
  <a href="https://github.com/cxlinux-ai/cx-core/releases">
    <img src="https://img.shields.io/badge/Download-ISO-green.svg" alt="Download ISO" />
  </a>
  <a href="https://github.com/cxlinux-ai/cx-core/blob/main/LICENSE.md">
    <img src="https://img.shields.io/badge/License-BSL%201.1-purple.svg" alt="License" />
  </a>
  <a href="https://discord.gg/cxlinux">
    <img src="https://img.shields.io/discord/1234567890?color=7289da&label=Discord&logo=discord&logoColor=white" alt="Discord" />
  </a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#what-can-cx-do">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#cx-terminal-pro">Pro Terminal</a> •
  <a href="#cx-linux-distro">Full Distro</a>
</p>

---

## What is CX Linux?

CX Linux is an **AI agent system for Linux administration**. Ask questions in plain English, hire autonomous agents to monitor your systems, and let AI handle the complexity.

```bash
# Install in seconds
pip install cx-linux

# Ask anything
cx ask "Why is my server running slow?"

# Get things done
cx ask --do "Install and configure nginx with SSL"

# Hire an agent to watch your system
cx hire monitoring-agent
```

**Works in any terminal.** No special app required.

---

## Quick Start

### Option 1: pip (Recommended)

```bash
pip install cx-linux
cx ask "Hello, what can you do?"
```

### Option 2: apt (Debian/Ubuntu)

```bash
curl -fsSL https://apt.cxlinux.com/install.sh | bash
apt install cx-linux
```

### Option 3: Full Distro

Download the [CX Linux ISO](https://github.com/cxlinux-ai/cx-distro/releases) for the complete AI-native experience.

---

## What Can CX Do?

### Ask Questions
```bash
cx ask "How do I check which ports are open?"
cx ask "Explain what this error means" < /var/log/syslog
cx ask "What's using all my disk space?"
```

### Execute Tasks
```bash
cx ask --do "Update all packages and reboot if needed"
cx ask --do "Create a new user called deploy with sudo access"
cx ask --do "Set up a firewall allowing only SSH and HTTPS"
```

### Hire Agents
```bash
cx hire security-agent      # Monitors for vulnerabilities
cx hire backup-agent        # Automated backups
cx hire monitoring-agent    # System health tracking
cx hire performance-agent   # Optimization recommendations

cx status                   # See all active agents
cx fire monitoring-agent    # Stop an agent
```

### Shortcuts
```bash
cx install docker           # Natural language package installation
cx fix "nginx won't start"  # AI-powered troubleshooting
cx explain systemctl        # Learn any command
cx setup "web server"       # Guided configuration
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                      Any Terminal                           │
│  $ cx ask "Why is my build failing?"                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     CX AI Engine                            │
│  • Understands context (cwd, history, environment)         │
│  • Connects to Claude, OpenAI, Ollama, or local models     │
│  • Sandboxed execution for safety                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Your Linux System                        │
│  • Commands executed with your approval                    │
│  • Full audit trail in ~/.cx/history.db                    │
│  • Agents run as background services                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Safety First

- **Dry-run by default:** See what will happen before it happens
- **Sandboxed execution:** Dangerous commands require explicit approval
- **Audit logging:** Full history of all AI actions
- **Local-first:** Your data never leaves your machine (with local models)
- **Rollback support:** Undo agent actions with `cx rollback`

---

## CX Terminal (Pro)

Want the full AI-native experience? **CX Terminal** adds:

| Feature | CLI (Free) | Terminal (Pro) |
|---------|------------|----------------|
| `cx ask` commands | ✅ | ✅ |
| AI agents | ✅ | ✅ |
| Natural language install | ✅ | ✅ |
| **AI Sidebar (Ctrl+Space)** | ❌ | ✅ |
| **Voice commands** | ❌ | ✅ |
| **Visual command blocks** | ❌ | ✅ |
| **Workflow learning** | Basic | Advanced |

```bash
# Download CX Terminal
# macOS
brew install --cask cx-terminal

# Linux
curl -fsSL https://cxlinux.com/install-terminal.sh | bash
```

[Learn more about CX Terminal Pro →](https://cxlinux.com/pro)

---

## CX Linux Distro

The complete AI-native Linux experience. CX Linux is a full operating system with AI built in from boot.

- **Pre-configured:** `cx` CLI ready out of the box
- **AI-optimized:** Tuned for LLM inference (NVIDIA/AMD GPU support)
- **Privacy-first:** Local Ollama models pre-installed
- **Beautiful:** Custom boot animation, themes, and branding

[Download CX Linux ISO →](https://github.com/cxlinux-ai/cx-distro/releases)

---

## Configuration

```bash
# Set your preferred AI provider
cx config set provider claude      # or openai, ollama, local

# Add API key
cx config set api_key sk-xxx

# Use local models (privacy mode)
cx config set provider ollama
cx config set model llama3.2
```

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Bounty Program

| Type | Reward |
|------|--------|
| Bug fix | $25-200 |
| Small feature | $50-100 |
| Medium feature | $200-500 |
| Large feature | $500-1000+ |

---

## License

- **CX Additions:** [BSL 1.1](LICENSE.md) (converts to Apache 2.0 in 2032)
- **Terminal Foundation:** MIT (WezTerm)

---

<p align="center">
  <strong>CX Linux - The AI Layer for Linux</strong><br>
  <a href="https://cxlinux.com">Website</a> •
  <a href="https://docs.cxlinux.com">Docs</a> •
  <a href="https://discord.gg/cxlinux">Discord</a> •
  <a href="https://twitter.com/cxlinux">Twitter</a>
</p>
