<p align="center">
  <img src="assets/icon/cx-terminal-icon.svg" alt="CX Linux Logo" width="200" />
</p>

<h1 align="center">CX Linux</h1>

<p align="center">
  <strong>The AI-Native Linux Distribution</strong><br>
  Agentic system administration, real-time context awareness, and seamless AI orchestration.
</p>

<p align="center">
  <a href="https://github.com/cxlinux-ai/cx-core/actions/workflows/cx-test.yml">
    <img src="https://github.com/cxlinux-ai/cx-core/actions/workflows/cx-test.yml/badge.svg" alt="Build Status" />
  </a>
  <a href="https://github.com/cxlinux-ai/cx-core/releases">
    <img src="https://img.shields.io/badge/version-v0.3.2-brightgreen.svg" alt="Version" />
  </a>
  <a href="https://github.com/cxlinux-ai/cx-core/blob/main/LICENSE.md">
    <img src="https://img.shields.io/badge/License-BSL%201.1-blue.svg" alt="License" />
  </a>
  <a href="https://discord.gg/7K6TR7qtS">
    <img src="https://img.shields.io/discord/1234567890?color=7289da&label=Discord&logo=discord&logoColor=white" alt="Discord" />
  </a>
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#supported-platforms">Platforms</a> •
  <a href="#license">License</a>
</p>

---

## What is CX Linux?

CX Linux is an AI-native operating system that simplifies system administration through natural language. It provides an intelligent terminal interface that understands your intent, automates complex tasks, and learns from your workflow.

---

## 🚀 Installation

### APT Repository (Recommended)

```bash
# Add CX Linux repository
curl -fsSL https://repo.cxlinux.com/key.gpg | sudo gpg --dearmor -o /etc/apt/keyrings/cxlinux.gpg
echo "deb [signed-by=/etc/apt/keyrings/cxlinux.gpg] https://repo.cxlinux.com/apt stable main" | sudo tee /etc/apt/sources.list.d/cxlinux.list

# Install CX Terminal (binary: cx-terminal; `cx` symlink added by the package postinst)
sudo apt update && sudo apt install cx-terminal
```

**APT repo requirements:** the published `cx-terminal` package is built on Ubuntu 24.04 and requires `libc6 >= 2.39`. Ubuntu 22.04/20.04 and Debian 12 (Bookworm) cannot install from this repo until a compatible build is published. See [docs/verification/INSTALL_VERIFICATION.md](docs/verification/INSTALL_VERIFICATION.md).

**License activation** (after Pro/Team checkout): **`cx activate <LICENSE_KEY>`** (aliases: `cx license activate …`, `cx-terminal activate …`). Keys appear on the [pricing success page](https://cxlinux.com/pricing/success) and in your account dashboard. See [docs/verification/LICENSE_ACTIVATION_FLOW.md](docs/verification/LICENSE_ACTIVATION_FLOW.md).

### Build from Source

```bash
# Clone the repository
git clone https://github.com/cxlinux-ai/cx-core.git
cd cx-core

# Build
cargo build --release -p cx-terminal

# Install
sudo cp target/release/cx-terminal /usr/local/bin/
sudo ln -sf /usr/local/bin/cx-terminal /usr/local/bin/cx
```

---

## ✨ Features

| Command | Description |
|---------|-------------|
| `cx ask` | Ask questions in natural language, get intelligent responses |
| `cx status` | System health check and status overview |
| `cx demo` | Interactive demo of CX Linux capabilities |

### Core Capabilities

- **Natural Language Interface**: Execute complex tasks with simple commands
- **AI Side-Panel**: Integrated LLM panel (Ctrl+Space) with full terminal context
- **Voice Support**: Hands-free operations via native audio capture
- **Workflow Learning**: Local models that learn your command patterns
- **Command Blocks**: Visual output grouping with interactive AI diagnosis

---

## 🖥️ Supported Platforms

| Distribution | Versions |
|--------------|----------|
| **Ubuntu** | 24.04 LTS (APT repo); older LTS via source build |
| **Debian** | 12 (Bookworm) — source build only; APT repo pending glibc-compatible package |
| **Fedora** | 39, 40, 41 |
| **CentOS** | Stream 9 |

---

## 🏁 Quick Start

```bash
# Ask a question
cx-terminal ask "How do I install Docker?"

# Activate a Pro license (after checkout)
cx-terminal activate CX-PRO-XXXX-XXXX-XXXX-XXXX

# Check license status
cx-terminal license
```

---

## 🏗️ Architecture

- **Frontend**: GPU-accelerated terminal (based on [WezTerm](https://github.com/wez/wezterm))
- **AI Engine**: Custom Rust-based LLM orchestration
- **Daemon**: Background service for privileged OS tasks
- **IPC Layer**: Length-prefixed JSON-RPC over Unix sockets

---

## 🛡️ Safety & Security

- **Sandboxed Execution**: AI-generated commands run in isolated environments
- **Dry-Run Mode**: Preview AI plans before execution
- **Local-First ML**: Command history and models stay on your machine
- **Audit Logging**: Full history in `~/.cx/history.db`

---

## 📦 Related Repositories

| Repository | Description |
|------------|-------------|
| [cx-commercial](https://github.com/cxlinux-ai/cx-commercial) | Enterprise features and licensing |
| [cx-infrastructure](https://github.com/cxlinux-ai/cx-infrastructure) | System diagnostics and repair tools |
| [cx-web](https://github.com/cxlinux-ai/cx-web) | Official website |
| [cx-docs](https://github.com/cxlinux-ai/cx-docs) | Documentation |

---

## 📄 License

**Business Source License 1.1 (BSL 1.1)**

- Free for personal and non-commercial use
- Commercial use requires a license
- Converts to **Apache 2.0** on **January 15, 2032**

See [LICENSE](LICENSE) for full terms.

---

<p align="center">
  <sub>Built by <a href="https://cxlinux.com">CX Linux</a> • AI Venture Holdings LLC</sub>
</p>
