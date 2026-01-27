# CX Terminal - Development Guide

## Mission Statement

**CX Terminal is the terminal emulator for the AI-Native Agentic OS.**

CX Linux reimagines the operating system for an era where AI agents are first-class citizens. CX Terminal serves as the primary interface between users and AI agents, providing:

- **Command Blocks**: AI-generated commands with context, explanations, and one-click execution
- **Voice-First Input**: Natural language command entry via local speech recognition
- **Learning System**: Privacy-preserving adaptation to user workflows
- **Agent Integration**: Native support for file, system, and code agents
- **Daemon Communication**: Real-time IPC with the CX system daemon

## Project Overview
CX Terminal is an AI-native terminal emulator for CX Linux, forked from WezTerm.

---

## CX Linux Terminal Family

This CLAUDE.md defines standards for **all 4 CX terminals**:

| Terminal | Repository | Purpose |
|----------|------------|---------|
| **CX Terminal** | `cxlinux-ai/cx` | Primary GUI terminal |
| **CX TTY** | `cxlinux-ai/cx-tty` | Virtual console terminal |
| **CX Remote** | `cxlinux-ai/cx-remote` | SSH/remote session terminal |
| **CX Embedded** | `cxlinux-ai/cx-embedded` | Lightweight embedded terminal |

All terminals MUST follow the code style, pricing constants, and branch protection rules defined here.

---

## Pricing Constants

**All 4 terminals MUST use these exact pricing values:**

```rust
// Subscription tier pricing - DO NOT MODIFY without business approval
pub const TIER_CORE_PRICE: u32 = 0;        // Free
pub const TIER_PRO_PRICE: u32 = 1900;      // $19.00 per system (one-time)
pub const TIER_TEAM_PRICE: u32 = 9900;     // $99.00 per month
pub const TIER_ENTERPRISE_PRICE: u32 = 19900; // $199.00 per month
```

### Subscription Tiers

| Tier | Price | Billing | Features |
|------|-------|---------|----------|
| **Core** | Free | - | Local AI only, basic terminal |
| **Pro** | $19/system | One-time | Cloud AI, all providers |
| **Team** | $99/month | Monthly | Team features, shared configs, analytics |
| **Enterprise** | $199/month | Monthly | Full suite, SSO, audit logs, SLA |

### Stripe Product IDs

```bash
# Environment variables for Stripe integration
STRIPE_PRICE_CORE=price_free
STRIPE_PRICE_PRO=price_1ABC...      # $19 one-time
STRIPE_PRICE_TEAM=price_1DEF...     # $99/month recurring
STRIPE_PRICE_ENTERPRISE=price_1GHI... # $199/month recurring
```

---

## Branch Protection Rules

### Ruleset Configuration (ID: 9679118)

All repositories in `@cxlinux-ai` organization use this ruleset:

```json
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          { "context": "Cargo Check" },
          { "context": "Rustfmt" },
          { "context": "Test Suite" },
          { "context": "Documentation Tests" }
        ]
      }
    }
  ],
  "bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "always"
    }
  ]
}
```

### Required CI Checks

All PRs must pass these checks before merge:

| Check | Command | Purpose |
|-------|---------|---------|
| Cargo Check | `cargo check --workspace` | Compilation verification |
| Rustfmt | `cargo fmt --all -- --check` | Code formatting |
| Test Suite | `cargo test --workspace` | Unit/integration tests |
| Documentation Tests | `cargo test --doc --workspace` | Doc example verification |

### Applying Rulesets

```bash
# Apply ruleset to a repository
gh api repos/cxlinux-ai/REPO_NAME/rulesets \
  --method POST \
  --input ruleset.json

# Update existing ruleset
gh api repos/cxlinux-ai/cx/rulesets/9679118 \
  --method PUT \
  --input ruleset.json

# List all rulesets
gh api repos/cxlinux-ai/cx/rulesets
```

---

## Code Style

### Rust Standards

- **Edition**: Rust 2021
- **Formatting**: `rustfmt` with default settings
- **Linting**: `clippy` with `-D warnings` (treat warnings as errors)
- **Comments**: Mark CX additions with `// CX Terminal:` prefix

```rust
// CX Terminal: AI panel integration
pub struct AiPanel {
    provider: Box<dyn AiProvider>,
    // ...
}
```

### Logging

Use the `log` crate consistently:

```rust
use log::{info, debug, warn, error, trace};

info!("Starting CX Terminal v{}", env!("CARGO_PKG_VERSION"));
debug!("Config loaded from {:?}", config_path);
warn!("Fallback to local AI - no API key");
error!("Failed to connect to daemon: {}", e);
trace!("Frame rendered in {}ms", duration);
```

### Error Handling

```rust
// Preferred: Use anyhow for application errors
use anyhow::{Context, Result};

fn load_config() -> Result<Config> {
    let path = config_path().context("Failed to determine config path")?;
    let content = fs::read_to_string(&path)
        .with_context(|| format!("Failed to read config from {:?}", path))?;
    Ok(toml::from_str(&content)?)
}
```

### Commit Messages

Follow Conventional Commits:

```
feat: Add voice input support
fix: Resolve memory leak in AI panel
docs: Update CLAUDE.md with pricing
refactor: Extract subscription validation
style: Apply rustfmt to all files
chore: Update dependencies
test: Add integration tests for daemon IPC
perf: Optimize command block rendering
```

---

## CI Dependencies

### Ubuntu/Debian Build Requirements

All CI workflows must install these packages:

```yaml
- name: Install dependencies
  run: |
    sudo apt-get update
    sudo apt-get install -y \
      cmake \
      libfontconfig1-dev \
      libfreetype6-dev \
      libx11-dev \
      libx11-xcb-dev \
      libxcb1-dev \
      libxcb-render0-dev \
      libxcb-shape0-dev \
      libxcb-xfixes0-dev \
      libxcb-keysyms1-dev \
      libxcb-icccm4-dev \
      libxcb-image0-dev \
      libxcb-util-dev \
      libxkbcommon-dev \
      libxkbcommon-x11-dev \
      libwayland-dev \
      libssl-dev \
      libegl1-mesa-dev \
      libasound2-dev
```

### macOS Build Requirements

macOS builds require the app bundle structure:

```
assets/macos/CX Terminal.app/
└── Contents/
    └── Info.plist
```

---

## Build Commands

```bash
# Quick check (fast, no binary)
cargo check

# Debug build
cargo build

# Release build (optimized)
cargo build --release

# Run debug binary
cargo run --bin cx-terminal-gui

# Run release binary
./target/release/cx-terminal-gui
```

## Test Commands

```bash
# Run all tests
cargo test

# Run specific package tests
cargo test -p cx-terminal-gui
cargo test -p config

# Run with output
cargo test -- --nocapture

# Run clippy
cargo clippy --workspace -- -D warnings
```

---

## Key Directories

| Path | Purpose |
|------|---------|
| `wezterm-gui/src/ai/` | AI panel, providers, streaming |
| `wezterm-gui/src/agents/` | Agent system (file, system, code) |
| `wezterm-gui/src/blocks/` | Command blocks system |
| `wezterm-gui/src/voice/` | Voice input with cpal |
| `wezterm-gui/src/learning/` | ML training, user model |
| `wezterm-gui/src/workflows/` | Workflow automation |
| `wezterm-gui/src/subscription/` | Licensing, Stripe integration |
| `wezterm-gui/src/cx_daemon/` | CX daemon IPC client |
| `shell-integration/` | Bash/Zsh/Fish integration |
| `config/src/` | Configuration, Lua bindings |
| `examples/` | Example configs (cx.lua) |

## Config Paths

- User config: `~/.cx.lua` or `~/.config/cx/cx.lua`
- Data dir: `~/.config/cx-terminal/`
- Daemon socket: `~/.cx/daemon.sock`

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude API access |
| `OLLAMA_HOST` | Local LLM endpoint |
| `CX_TERMINAL` | Set by terminal for shell detection |
| `TERM_PROGRAM` | Set to "CXTerminal" |

---

## Security Constraints

**Critical security measures implemented:**

1. **Webhook Verification**: Stripe webhooks use HMAC-SHA256 signature verification
2. **Learning Data Privacy**: User learning data stored with `0o700` permissions (owner-only)
3. **IPC Socket Security**: No `/tmp` fallback - sockets only in secure user directories
4. **Privacy Filters**: All privacy filters (IP, email, username anonymization) enabled by default

**Security audit checklist:**
```bash
# Verify learning data permissions
ls -la ~/.config/cx-terminal/

# Verify socket permissions
ls -la ~/.cx/daemon.sock

# Check no secrets in environment
env | grep -i "key\|secret\|token" | head -5
```

---

## Production Deployment

**Pre-deployment verification:**
```bash
# Full release build
cargo build --release

# Run test suite
cargo test

# Run clippy
cargo clippy --workspace -- -D warnings

# Verify branding (should return no results)
grep -r "wezterm/wezterm" . --include="*.toml" | grep -v target
grep -r "cortexlinux" . --include="*.rs" --include="*.md" | grep -v target
```

**Binary location:** `./target/release/cx-terminal-gui`

**Required runtime:**
- `~/.cx/` directory (auto-created)
- CX daemon running for full AI features
- API keys in environment or config for cloud AI

---

## Attribution

CX Terminal is built on the excellent [WezTerm](https://wezfurlong.org/wezterm/) by Wez Furlong, licensed under MIT.

## Important Notes

- Never use "cortex" or "cortexlinux" - use "cx" and "cxlinux-ai"
- GitHub: github.com/cxlinux-ai/cx
- Website: cxlinux.ai
- License server: license.cxlinux.ai

---

## Organization Repositories

All 20 repositories in `@cxlinux-ai` follow these standards:

| Repository | Description |
|------------|-------------|
| cx | Primary CX Terminal |
| cx-tty | Virtual console terminal |
| cx-remote | SSH/remote terminal |
| cx-embedded | Embedded terminal |
| cx-daemon | System daemon |
| cx-cli | Command-line interface |
| cx-llm | Local LLM inference |
| cx-network | Network management |
| cx-distro | ISO builder |
| cx-docs | Documentation |
| cx-apt-repo | Package repository |
| cx-website | Marketing site |
| cx-installer | Installation wizard |
| cx-themes | Theme packages |
| cx-plugins | Plugin system |
| cx-analytics | Usage analytics |
| cx-auth | Authentication service |
| cx-api | REST API |
| cx-sdk | Developer SDK |
| cx-examples | Example configurations |
