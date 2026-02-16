# CX Terminal - Project Scope

## What is CX Terminal?

CX Terminal is an **AI-native terminal emulator** built on WezTerm, specifically designed as the primary interface for CX Linux. It is written in Rust and focuses on providing an enhanced terminal experience with AI integration.

## Architecture

- **Language**: Rust (2018 edition)
- **Base**: Fork of WezTerm terminal emulator
- **License**: BSL 1.1 for CX additions, MIT for WezTerm base
- **AI Integration**: Side-panel for LLM interaction
- **Voice Support**: Native voice capture via cpal
- **IPC**: Secure Unix socket communication with cx-daemon

## What CX Terminal Is NOT

CX Terminal is **not** the "Cortex" system administration CLI tool. The following components are **not part of this repository**:

- `cx` command-line tool
- `cx wizard`, `cx config`, `cx install` commands
- Python-based system administration scripts
- Docker sandbox management
- Package installation automation
- Network configuration validation

## Repository Contents

### Core Components
- `wezterm-gui/src/` - Terminal emulator GUI (Rust)
- `wezterm-gui/src/ai/` - AI panel integration
- `wezterm-gui/src/agents/` - CX agent system
- `wezterm-gui/src/blocks/` - Command blocks system
- `wezterm-gui/src/voice/` - Voice input support
- `shell-integration/` - Shell integration scripts
- `config/src/` - Configuration and Lua bindings

### Build System
- `Cargo.toml` - Rust package configuration
- `.github/workflows/` - CI/CD pipelines
- `ci/` - Build and deployment scripts

### Documentation
- `docs/` - Project documentation
- `README.md` - Project overview
- `CONTRIBUTING.md` - Contribution guidelines
- `LICENSE.md` - License information

## Issue Management

GitHub issues should relate to:
- Terminal emulator functionality
- AI panel features
- Voice input capabilities
- Build system problems
- Documentation updates
- WezTerm integration bugs

Issues referencing "cx" CLI commands, Python files, or system administration features likely belong to a different repository or are outdated from a previous project iteration.

## Related Projects

If you're looking for CX Linux system administration tools, they may be located in:
- A separate `cx` repository
- The main CX Linux distribution repository
- Integrated into the `cx-daemon` service

For questions about project scope, please check this document or open a discussion.