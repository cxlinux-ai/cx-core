# CX Terminal - Claude Code Instructions

## Project Overview
CX Terminal is an AI-native terminal emulator forked from WezTerm. This is the primary interface for CX Linux.

## Branding Rules
- Use "CX" branding consistently
- Company: CX Linux
- Email: support@cxlinux.com
- License: BSL 1.1 for additions, MIT for WezTerm base

## Code Standards
- Language: Rust (2018 edition)
- Config: Lua
- Shell scripts: Bash/Zsh/Fish
- Follow existing WezTerm patterns
- Add `// CX Terminal:` comments for our additions

## Key Directories
```
wezterm-gui/src/blocks/    - Command blocks system
wezterm-gui/src/ai/        - AI panel and providers
wezterm-gui/src/agents/    - CX Linux agent system
shell-integration/         - Shell scripts for block detection
config/src/                - Configuration and Lua bindings
docs/                      - PRD, architecture, guides
```

## Current State
- WezTerm forked and rebranded ✅
- Module scaffolding complete ✅
- Shell integration scripts written ✅
- Needs: compilation verification, wiring into GUI

## Build Commands
```bash
# Check compilation
cargo check

# Build debug
cargo build

# Build release
cargo build --release

# Run
cargo run --bin cx-terminal-gui
```

## PR/Commit Rules
- Prefix commits with feat:, fix:, docs:, refactor:
- Reference PRD sections in commits when applicable
- Don't push to main without user approval

## AI Integration
- Default provider: Claude API
- Fallback: Ollama (local)
- Streaming responses preferred
- Privacy-first: local AI is default when available
