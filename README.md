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
  <a href="https://github.com/cxlinux-ai/cx-core/stargazers">
    <img src="https://img.shields.io/github/stars/cxlinux-ai/cx-core?style=social" alt="GitHub stars" />
  </a>
  <a href="https://github.com/cxlinux-ai/cx-core/network/members">
    <img src="https://img.shields.io/github/forks/cxlinux-ai/cx-core?style=social" alt="GitHub forks" />
  </a>
  <a href="https://github.com/cxlinux-ai/cx-core/graphs/contributors">
    <img src="https://img.shields.io/github/contributors/cxlinux-ai/cx-core?color=1f6feb" alt="Contributors" />
  </a>
  <a href="https://github.com/cxlinux-ai/cx-core/discussions">
    <img src="https://img.shields.io/github/discussions/cxlinux-ai/cx-core?color=3fb950&label=discussions" alt="Discussions" />
  </a>
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#supported-platforms">Platforms</a> •
  <a href="#contributing">Contribute</a> •
  <a href="#license">License</a>
</p>

<p align="center">
  <img src="demo/cx-30s.gif" alt="cx ask: natural language in, a previewed command out, runs only after you confirm" width="800" />
  <br><sub>Real recording, local model, no mocks. Ask in plain English, review the command, confirm, and it runs.</sub>
</p>

<p align="center">
  <b>If CX saves you a trip to Stack Overflow, <a href="https://github.com/cxlinux-ai/cx-core/stargazers">⭐ star the repo</a></b>. It's how other Linux users find it.
</p>

---

## What is CX Linux?

CX Linux is an AI-native operating system that simplifies system administration through natural language. It provides an intelligent terminal interface that understands your intent, automates complex tasks, and learns from your workflow.

---

<a name="installation"></a>

## 🚀 Installation

### APT Repository (Recommended)

```bash
# Add CX Linux repository
curl -fsSL https://repo.cxlinux.com/key.gpg | sudo gpg --dearmor -o /etc/apt/keyrings/cxlinux.gpg
echo "deb [signed-by=/etc/apt/keyrings/cxlinux.gpg] https://repo.cxlinux.com/apt stable main" | sudo tee /etc/apt/sources.list.d/cxlinux.list

# Install CX Terminal
sudo apt update && sudo apt install cx-terminal
```

### Build from Source

```bash
# Clone the repository
git clone https://github.com/cxlinux-ai/cx-core.git
cd cx-core

# Build the CLI (the binary is cx-terminal; `cx` is the command name)
cargo build --release -p cx-terminal

# Install the CLI (cx ask, install, what, fix, explain)
sudo cp target/release/cx-terminal /usr/local/bin/
sudo ln -sf /usr/local/bin/cx-terminal /usr/local/bin/cx

# Optional: the GPU terminal and AI side panel. Running `cx` with no
# subcommand launches the GUI binary, which it looks for as `wezterm-gui`
# in the same directory.
cargo build --release -p cx-terminal-gui
sudo cp target/release/cx-terminal-gui /usr/local/bin/wezterm-gui
```

---

<a name="features"></a>

## ✨ Features

| Command | Description |
|---------|-------------|
| `cx ask` | Ask in natural language; shows the suggested commands (add `-d` to run AI suggestions after a `[y/N]` confirmation) |
| `cx install` | Install packages using natural language (e.g. `cx install cuda drivers`) |
| `cx what` | Ask about your system (e.g. `cx what packages use the most disk space`) |
| `cx fix` | Fix errors using AI assistance |
| `cx explain` | Explain a command or concept |
| `cx ai download` | Download the local CX model (~5 GB) for offline answers |

### Core Capabilities

- **Natural Language Interface**: Execute complex tasks with simple commands
- **AI Side-Panel**: Integrated LLM panel (Ctrl+Space) with full terminal context
- **Voice Support**: Hands-free operations via native audio capture
- **Workflow Learning**: Local models that learn your command patterns
- **Command Blocks**: Visual output grouping with interactive AI diagnosis

---

<a name="supported-platforms"></a>

## 🖥️ Supported Platforms

| Install method | Platforms |
|--------------|----------|
| **APT package** | Ubuntu 24.04 LTS or newer, amd64 (the package needs glibc 2.39) — verified |
| **Build from source** | Other Linux distributions and macOS — not yet verified |

---

<a name="quick-start"></a>

## 🏁 Quick Start

```bash
# Enable AI (pick one): local model, Claude API, or your Ollama server
cx ai download
# export ANTHROPIC_API_KEY=...
# export OLLAMA_HOST=http://...

# Ask a question (shows commands, runs nothing)
cx ask "how do I check disk usage"

# Ask and run, after confirming
cx ask -d "show memory usage"
```

---

## 🏗️ Architecture

- **Frontend**: GPU-accelerated terminal (based on [WezTerm](https://github.com/wez/wezterm))
- **AI Engine**: Custom Rust-based LLM orchestration
- **Daemon**: Background service for privileged OS tasks
- **IPC Layer**: Length-prefixed JSON-RPC over Unix sockets

---

## 🛡️ Safety & Security

- **AI suggestions are previews**: commands suggested by the AI are shown, not run, unless you add `-d`; then `cx` asks `[y/N]` first (`-y` skips the prompt)
- **Built-in CX actions ask first**: requests that match a built-in CX action (for example "save my work" → `cx save`) are offered with `Run this? [Y/n]`, where Enter means yes
- **No input is never consent**: at a `[y/N]` prompt, empty input or EOF means No. Two caveats: `-y` skips the prompt entirely, and piped input such as `echo y |` counts as an answer
- **Local-first AI**: with the downloaded model, questions are answered on your machine. Add `--local` to guarantee it: without `--local`, if the local model fails to load or answer, `cx` falls back to Claude (`ANTHROPIC_API_KEY`) or Ollama (`OLLAMA_HOST`) when you've configured them

---

## 📦 Related Repositories

| Repository | Description |
|------------|-------------|
| [cx-commercial](https://github.com/cxlinux-ai/cx-commercial) | Enterprise features and licensing |
| [cx-infrastructure](https://github.com/cxlinux-ai/cx-infrastructure) | System diagnostics and repair tools |
| [cx-web](https://github.com/cxlinux-ai/cx-web) | Official website |
| [cx-docs](https://github.com/cxlinux-ai/cx-docs) | Documentation |

---

<a name="contributing"></a>

## 🤝 Contributing

CX is built in the open, and first-time contributors are welcome.

1. **Find a task.** Browse [`good first issue`](https://github.com/cxlinux-ai/cx-core/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) or [`help wanted`](https://github.com/cxlinux-ai/cx-core/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22).
2. **Fork and build.** `cargo build --release -p cx-terminal`. The full setup is in [CONTRIBUTING.md](CONTRIBUTING.md).
3. **Open a PR.** Sign the CLA once, the first time you contribute. The bot walks you through it.

Ideas, questions, and show-and-tell go in [Discussions](https://github.com/cxlinux-ai/cx-core/discussions).

<a href="https://github.com/cxlinux-ai/cx-core/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=cxlinux-ai/cx-core&max=60" alt="Contributors" />
</a>

### Star history

<a href="https://star-history.com/#cxlinux-ai/cx-core&Date">
  <img src="https://api.star-history.com/svg?repos=cxlinux-ai/cx-core&type=Date" alt="Star history" width="600" />
</a>

---

<a name="license"></a>

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
