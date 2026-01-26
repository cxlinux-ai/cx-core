# Contributing to CX Terminal

Thanks for considering contributing to CX Terminal! We value any contribution, even if it is just to highlight a typo.

## Quick Start for Contributors

```bash
# Clone the repository
git clone https://github.com/cxlinux-ai/cx.git
cd cx

# Install Rust (if not already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Check the code compiles
cargo check

# Run tests
cargo test

# Build release
cargo build --release

# Run the terminal
./target/release/cx-terminal-gui
```

## Project Structure

| Directory | Description |
|-----------|-------------|
| `wezterm-gui/src/ai/` | AI panel and LLM providers |
| `wezterm-gui/src/blocks/` | Command blocks system |
| `wezterm-gui/src/agents/` | CX Linux agent system |
| `wezterm-gui/src/voice/` | Voice capture and transcription |
| `wezterm-gui/src/learning/` | ML workflow learning |
| `wezterm/src/cli/` | CLI commands (ask, install, setup, etc.) |
| `term/` | Core terminal model (escape sequences, etc.) |
| `config/` | Configuration and Lua bindings |
| `shell-integration/` | Shell scripts for CX features |

## Development Workflow

### Check your code compiles
```bash
cargo check
```

### Run in debug mode
```bash
cargo run --bin cx-terminal-gui
```

### Run tests
```bash
cargo test --all
```

### Format code (required before PR)
```bash
cargo fmt --all
```

## CX Terminal Additions

When adding CX-specific features:

1. Add `// CX Terminal:` comments to mark our additions
2. Use the `cx` prefix for new modules/functions
3. Follow existing patterns in the codebase
4. Add tests for new functionality

### AI Commands

The AI CLI commands are in `wezterm/src/cli/`:
- `ask.rs` - Main AI query command
- `shortcuts.rs` - Convenience commands (install, setup, what, fix, explain)

### Command Blocks

The blocks system is in `wezterm-gui/src/blocks/`:
- `block.rs` - Block data structure
- `manager.rs` - Block lifecycle management
- `parser.rs` - OSC sequence parsing
- `renderer.rs` - Block rendering

## Submitting a Pull Request

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests: `cargo test --all`
5. Format code: `cargo fmt --all`
6. Commit with clear message: `git commit -m "feat: Add my feature"`
7. Push and create PR

### Commit Message Format

```
type: Short description

Longer description if needed.

Co-Authored-By: Your Name <your@email.com>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## Code of Conduct

Be respectful and constructive. We're all here to build something great.

## Questions?

- Discord: https://discord.gg/cxlinux
- GitHub Issues: https://github.com/cxlinux-ai/cx/issues
