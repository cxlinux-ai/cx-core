<p align="center">
  <img src="images/cx_linux_ai_logo.png" alt="CX Linux Logo" width="250" />
</p>

<h1 align="center">CX Terminal</h1>

<p align="center">
  <strong>The AI-Native Terminal for CX Linux</strong><br>
  Agentic system administration, real-time context awareness, and seamless AI orchestration.
</p>

<p align="center">
  <a href="https://github.com/cxlinux-ai/cx/actions">
    <img src="https://github.com/cxlinux-ai/cx/actions/workflows/ci.yml/badge.svg" alt="CI Status" />
  </a>
  <a href="https://github.com/cxlinux-ai/cx/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License" />
  </a>
  <a href="https://github.com/cxlinux-ai/cx/releases">
    <img src="https://img.shields.io/badge/version-0.1.0--alpha-orange.svg" alt="Version" />
  </a>
  <a href="https://discord.gg/uCqHvxjU83">
    <img src="https://img.shields.io/discord/1234567890?color=7289da&label=Discord&logo=discord&logoColor=white" alt="Discord" />
  </a>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#safety--security">Safety</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## What is CX Terminal?

CX Terminal is not just a terminal emulator; it is the primary interface for **CX Linux**. It integrates a specialized AI side-panel that shares a "nervous system" with your OS via a dedicated IPC daemon. It understands your intent, captures your voice, and learns from your unique workflow.

```bash
# Real-time AI intervention (Ctrl+Space)
cx ask "Why is my build failing?"

# Agentic command execution
cx ask --do "Optimize my NVIDIA drivers for training"

# Voice-to-Command
# [Capture Audio] -> "Create a new git branch for the audio feature"
```

---

## 🚀 Key Features

| Feature | Description |
|---------|-------------|
| **AI Side-Panel** | Integrated LLM panel (Ctrl+Space) with full terminal context. |
| **Audio Intelligence** | Native voice capture via `cpal` for hands-free operations. |
| **Daemon IPC** | Secure Unix socket communication for OS-level agentic tasks. |
| **ML Workflow Learning** | Local TF-IDF and N-gram models that learn your command patterns. |
| **Command Blocks** | Visual output grouping with interactive AI diagnosis for errors. |
| **Hardware-Aware** | Optimized for Mac Studio (M2/M3) and NVIDIA/AMD GPU environments. |

---

## 🛠️ Quick Start

### Prerequisites
- **OS:** CX Linux / Ubuntu 22.04+ / macOS (M-Series)
- **Rust:** 1.75+ (Stable)
- **Daemon:** `cx-daemon` must be running for agentic features.

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/cxlinux-ai/cx.git
cd cx

# 2. Build the terminal
cargo build --release

# 3. Launch the AI-Native experience
./target/release/cx-terminal-gui
```

---

## 🏗️ Architecture

CX Terminal uses a distributed architecture to ensure low latency and high security:

- **Frontend:** GPU-accelerated terminal core (based on WezTerm).
- **AI Panel:** Custom Rust-based UI for LLM orchestration.
- **Daemon (cx-daemon):** A background service handling privileged OS tasks.
- **IPC Layer:** 4-byte length-prefixed JSON-RPC over Unix sockets.

---

## 🛡️ Safety & Security

- **Sandboxed Execution:** AI-generated commands run in isolated environments.
- **Dry-Run Validation:** View AI plans before they touch your system.
- **Local-First ML:** Your command history and learning models never leave your machine.
- **Audit Logging:** Full SQLite-backed history in `~/.cx/history.db`.

---

## 🤝 Contributing

We offer a **Bounty Program** for merged PRs:
- **Small ():** Bug fixes, UI tweaks.
- **Medium ():** New AI tool integrations, performance gains.
- **Large (+):** Major architectural improvements.

---

<p align="center">
  <sub>Built with love by the CX Linux team.</sub>
</p>
