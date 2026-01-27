# CX AI Terminal - Component Architecture

## Core Components (This Repository)

| Component | Path | Description |
|-----------|------|-------------|
| Terminal GUI | `wezterm-gui/` | Main AI-native terminal (WezTerm fork) |
| AI Integration | `wezterm-gui/src/ai/` | Claude/Ollama providers |
| Agents | `wezterm-gui/src/agents/` | File, system, code agents |
| Voice | `wezterm-gui/src/voice/` | Voice input with cpal |
| Blocks | `wezterm-gui/src/blocks/` | Command blocks system |

## Satellite Components (Separate Repositories)

These components are maintained in separate repositories for build isolation:

| Component | Repository | Stack | Purpose |
|-----------|------------|-------|---------|
| CLI | `cx-cli` | Python | Natural language shell commands |
| LLM Engine | `cx-llm` | Python | Local Ollama/llama.cpp integration |
| Network | `cx-network` | Python | WiFi/VPN/DNS management |
| Lightweight Terminal | `cx-terminal` | Rust | Simple terminal for embedded use |

## Installation

```bash
# Core terminal
cargo build --release -p cx-terminal-gui

# Python components
pip install cx-cli cx-llm cx-network
```

## License

All components are licensed under BSL 1.1 with 6-year Apache 2.0 conversion.
See LICENSE for details.
