# Cortex CLI Commands Reference

This document provides a comprehensive reference for all commands available in the Cortex CLI, an AI-powered package manager for Debian/Ubuntu.

## Quick Reference

| Command | Description |
|---------|-------------|
| `cortex` | Show help and available commands |
| `cortex install <pkg>` | Install software |
| `cortex voice` | Voice input mode (hands-free with F9) |
| `cortex ask <question>` | Ask questions about your system or learn about Linux |
| `cortex demo` | See Cortex in action |
| `cortex wizard` | Configure API key |
| `cortex status` | Show comprehensive system status and health checks |
| `cortex doctor` | Run system health checks |
| `cortex troubleshoot` | Interactive AI troubleshooting assistant |
| `cortex history` | View installation history |
| `cortex rollback <id>` | Undo an installation |
| `cortex stack <name>` | Install a pre-built package stack |
| `cortex sandbox <cmd>` | Test packages in Docker sandbox |
| `cortex docker permissions` | Fix Docker bind-mount permissions |
| `cortex cache stats` | Show LLM cache statistics |
| `cortex notify` | Manage desktop notifications |

---

## Global Options

```bash
cortex --version, -V    # Show version
cortex --verbose, -v    # Show detailed output
cortex --help, -h       # Show help message
```

---

## Commands

### `cortex install`

Install software using natural language requests. Cortex uses AI to understand your request and generate the appropriate installation commands.

**Usage:**
```bash
cortex install <software> [options]
```

**Options:**
| Flag | Description |
|------|-------------|
| `--dry-run` | Show commands without executing (safe preview) |
| `--execute` | Actually run the installation commands |
| `--parallel` | Enable parallel execution for multi-step installs |

**Examples:**
```bash
# Preview what would be installed (default, safe)
cortex install nginx --dry-run

# Actually install the software
cortex install nginx --execute

# Install with parallel execution for faster installs
cortex install "nodejs npm" --execute --parallel

# Complex natural language requests
cortex install "latest stable docker with compose" --dry-run
cortex install "python3 with pip and virtualenv" --execute
```

**Notes:**
- Without `--execute`, Cortex only shows the commands it would run
- The `--dry-run` flag is recommended for first-time use to verify commands
- Installation is recorded in history for potential rollback
- **Smart Retry Logic**: Cortex automatically detects transient failures (like network timeouts) and retries commands with exponential backoff (up to 5 attempts). Permanent errors (like permission denied) fail immediately.

---

### `cortex ask`

Ask natural language questions about your system or learn about Linux, packages, and best practices. The AI automatically detects whether you're asking a diagnostic question about your system or an educational question to learn something new.

**Usage:**
```bash
cortex ask "<question>"
```

**Question Types:**

**Diagnostic Questions** - Questions about your specific system:
```bash
# System status queries
cortex ask "why is my disk full"
cortex ask "what packages need updating"
cortex ask "is my Python version compatible with TensorFlow"
cortex ask "check my GPU drivers"
```

**Educational Questions** - Learn about Linux, packages, and best practices:
```bash
# Explanations and tutorials
cortex ask "explain how Docker containers work"
cortex ask "what is systemd and how do I use it"
cortex ask "teach me about nginx configuration"
cortex ask "best practices for securing a Linux server"
cortex ask "how to set up a Python virtual environment"
```

**Features:**
- **Automatic Intent Detection**: The AI distinguishes between diagnostic and educational queries
- **System-Aware Responses**: Uses your actual system context (OS, Python version, GPU, etc.)
- **Structured Learning**: Educational responses include examples, best practices, and related topics
- **Learning Progress Tracking**: Educational topics you explore are tracked in `~/.cortex/learning_history.json`
- **Response Caching (best-effort)**: Repeated questions may return cached responses for faster performance; caching is disabled when `SemanticCache` is not available

**Examples:**
```bash
# Diagnostic: Get specific info about your system
cortex ask "what version of Python do I have"
cortex ask "can I run PyTorch on this system"

# Educational: Learn with structured tutorials
cortex ask "explain how apt package management works"
cortex ask "what are best practices for Docker security"
cortex ask "guide to setting up nginx as a reverse proxy"

# Mix of both
cortex ask "how do I install and configure Redis"
```

**Notes:**
- Educational responses are longer and include code examples with syntax highlighting
- Learning history helps track what topics you've explored over time

---

### `cortex demo`

Run an interactive demonstration of Cortex capabilities. Perfect for first-time users or presentations.

**Usage:**
```bash
cortex demo
```

---

### `cortex wizard`

Interactive setup wizard for configuring your API key and initial settings.

**Usage:**
```bash
cortex wizard
```

**Notes:**
- Guides you through API key configuration
- Supports Anthropic Claude, OpenAI, and Ollama (local) providers

---

### `cortex status`

Show comprehensive system status and run health checks to diagnose potential issues.

**Usage:**
```bash
cortex status
```

**Output includes:**

**System Configuration:**
- Configured API provider (Claude, OpenAI, or Ollama)
- Security features (Firejail availability)

**Python & Dependencies:**
- Python version compatibility
- Required package installation status

**GPU & Acceleration:**
- GPU driver detection (NVIDIA/AMD)
- CUDA/ROCm availability

**AI & Services:**
- Ollama installation and running status

**System Resources:**
- Available disk space
- System memory (RAM)

**Exit codes:**
- `0`: All checks passed, system is healthy
- `1`: Warnings found, system can operate but has recommendations
- `2`: Critical failures found, system may not work properly

---

### `cortex troubleshoot`

Interactive AI-powered troubleshooting assistant that can diagnose system issues and execute commands.

**Usage:**
```bash
cortex troubleshoot
```

**Features:**
- Conversational AI that understands your system issues
- Suggests shell commands to diagnose and fix problems
- Executes commands with your explicit confirmation
- Analyzes command output and suggests next steps
- Dangerous command protection (blocks `rm -rf`, `mkfs`, etc.)

**Flow:**
```text
┌─────────────────────────────────────────┐
│  User describes issue                   │
└─────────────────┬───────────────────────┘
                  ▼
┌─────────────────────────────────────────┐
│  AI suggests diagnostic command         │
└─────────────────┬───────────────────────┘
                  ▼
┌─────────────────────────────────────────┐
│  User confirms execution [y/n]          │
└─────────────────┬───────────────────────┘
                  ▼
┌─────────────────────────────────────────┐
│  Command runs, output displayed         │
└─────────────────┬───────────────────────┘
                  ▼
┌─────────────────────────────────────────┐
│  AI analyzes output, suggests next step │
└─────────────────────────────────────────┘
```

**Example Session:**
```text
$ cortex troubleshoot
🤖 Cortex Troubleshooter
Describe your issue, or type 'doctor' to run health checks.

You: docker won't start

AI: Let's check the Docker service status:

$ systemctl status docker

Suggested Command:
systemctl status docker
Execute this command? [y/n]: y

[Command Output displayed]

AI: The Docker daemon failed to start. Let's check the logs...
```

**Safety:**
- All commands require explicit user confirmation
- Dangerous commands are automatically blocked:
  - `rm -rf`, `rm -fr`
  - `mkfs` (filesystem format)
  - `dd` to devices
  - `shutdown`, `reboot`, `poweroff`
  - `chmod 777 /`
  - Fork bombs

**Special Commands:**
| Command | Action |
|---------|--------|
| `doctor` | Run health checks mid-session |
| `help` | Generate support log for escalation |
| `exit`, `quit`, `q` | Exit troubleshooter |

---

### `cortex history`

View the history of package installations and operations.

**Usage:**
```bash
cortex history [options] [show_id]
```

**Options:**
| Flag | Description |
|------|-------------|
| `--limit <n>` | Maximum number of records to show (default: 20) |
| `--status <status>` | Filter by status: `success` or `failed` |
| `show_id` | Show details for a specific installation ID |

**Examples:**
```bash
# List recent installations
cortex history

# Show only the last 5 installations
cortex history --limit 5

# Show only failed installations
cortex history --status failed

# Show details for a specific installation
cortex history abc123def456
```

---

### `cortex rollback`

Undo a previous installation by its ID.

**Usage:**
```bash
cortex rollback <id> [options]
```

**Options:**
| Flag | Description |
|------|-------------|
| `--dry-run` | Preview rollback actions without executing |

**Examples:**
```bash
# Preview what would be rolled back
cortex rollback abc123def456 --dry-run

# Actually perform the rollback
cortex rollback abc123def456
```

**Notes:**
- Installation IDs can be found using `cortex history`
- Not all installations support rollback

---

### `cortex stack`

Manage and install pre-built package stacks for common development environments.

**Usage:**
```bash
cortex stack [name] [options]
```

**Options:**
| Flag | Description |
|------|-------------|
| `--list, -l` | List all available stacks |
| `--describe, -d <stack>` | Show details about a specific stack |
| `--dry-run` | Preview what would be installed |

**Available Stacks:**
| Stack | Description |
|-------|-------------|
| `ml` | Machine learning stack (GPU) |
| `ml-cpu` | Machine learning stack (CPU only) |
| `webdev` | Web development tools |
| `devops` | DevOps and infrastructure tools |
| `data` | Data science and analysis tools |

**Examples:**
```bash
# List available stacks
cortex stack --list

# Describe a stack
cortex stack --describe ml

# Preview stack installation
cortex stack ml --dry-run

# Install a stack
cortex stack webdev

# Cortex auto-detects GPU and selects ml-cpu if no GPU found
cortex stack ml  # Will use ml-cpu on non-GPU systems
```

---

### `cortex cache`

Manage the LLM response cache for improved performance.

**Usage:**
```bash
cortex cache <action>
```

**Actions:**
| Action | Description |
|--------|-------------|
| `stats` | Show cache statistics (hits, misses, hit rate) |

**Examples:**
```bash
cortex cache stats
```

---

### `cortex sandbox`

Test packages in isolated Docker containers before installing to the main system. Requires Docker.

**Usage:**
```bash
cortex sandbox <action> [options]
```

**Actions:**
| Action | Description |
|--------|-------------|
| `create <name>` | Create a sandbox environment |
| `install <name> <pkg>` | Install package in sandbox |
| `test <name> [pkg]` | Run automated tests in sandbox |
| `promote <name> <pkg>` | Install tested package on main system |
| `cleanup <name>` | Remove sandbox environment |
| `list` | List all sandbox environments |
| `exec <name> <cmd...>` | Execute command in sandbox |

**Options:**
| Flag | Description |
|------|-------------|
| `--image <img>` | Docker image for create (default: ubuntu:22.04) |
| `--dry-run` | Preview promote without executing |
| `-y, --yes` | Skip confirmation for promote |
| `-f, --force` | Force cleanup even if running |

**Examples:**
```bash
# Create a sandbox
cortex sandbox create test-env

# Install package in sandbox
cortex sandbox install test-env nginx

# Run tests
cortex sandbox test test-env

# Promote to main system
cortex sandbox promote test-env nginx

# Cleanup
cortex sandbox cleanup test-env

# Use custom base image
cortex sandbox create debian-test --image debian:12
```

**Notes:**
- Docker must be installed and running
- Promotion runs fresh `apt install` on host (not container export)
- Some commands (`systemctl`, `service`) are blocked in sandbox
- See [SANDBOX.md](SANDBOX.md) for full documentation

---

### `cortex docker`

Manage Docker-related utilities and system configurations.

**Usage:**
```bash
cortex docker  [options]
```

**Actions:**

| Action | Description |
|--------|-------------|
| `permissions` | Fix ownership issues for files created by containers in bind-mounted directories. |

**Options:**

| Flag | Description |
|------|-------------|
| `-y, --yes` | Skip the confirmation prompt for permission repairs. |

**Examples:**
```bash
# Scan and fix permission issues interactively
cortex docker permissions

# Fix permissions without a prompt (non-interactive)
cortex docker permissions --yes
```

**Notes:**

- This command identifies files owned by `root` or other container UIDs and returns ownership to the host user.
- It automatically excludes standard environment directories like `.git`, `node_modules`, and `venv`.
- The tool also validates `docker-compose.yml` and suggests correct `user:` mapping if missing.

---

### `cortex notify`

Manage desktop notification settings for installation events.

**Usage:**
```bash
cortex notify <action> [options]
```

**Actions:**
| Action | Description |
|--------|-------------|
| `config` | Show current notification configuration |
| `enable` | Enable notifications |
| `disable` | Disable notifications (critical alerts still show) |
| `dnd <start> <end>` | Set Do Not Disturb window (HH:MM format) |
| `send <message>` | Send a test notification |

**Examples:**
```bash
# Show notification settings
cortex notify config

# Enable notifications
cortex notify enable

# Set DND from 10 PM to 8 AM
cortex notify dnd 22:00 08:00

# Send test notification
cortex notify send "Test message" --title "Test" --level normal
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for Anthropic Claude |
| `OPENAI_API_KEY` | API key for OpenAI |
| `CORTEX_PROVIDER` | Force provider: `claude`, `openai`, or `ollama` |

**Examples:**
```bash
# Use Claude
export ANTHROPIC_API_KEY="sk-ant-..."
cortex install nginx --dry-run

# Use OpenAI
export OPENAI_API_KEY="sk-..."
cortex install nginx --dry-run

# Use Ollama (local, no API key needed)
export CORTEX_PROVIDER=ollama
cortex install nginx --dry-run
```

---

## Common Workflows

### First-Time Setup
```bash
# 1. Run the setup wizard
cortex wizard

# 2. Check system status and run health checks
cortex status

# 3. Try a dry-run installation
cortex install nginx --dry-run
```

### Safe Installation Pattern
```bash
# 1. Preview the installation
cortex install docker --dry-run

# 2. If commands look correct, execute
cortex install docker --execute

# 3. Check history
cortex history --limit 1

# 4. If something went wrong, rollback
cortex rollback <installation-id>
```

### Using Stacks for Development
```bash
# 1. List available stacks
cortex stack --list

# 2. See what's in a stack
cortex stack --describe webdev

# 3. Preview installation
cortex stack webdev --dry-run

# 4. Install the stack
cortex stack webdev
```

### Learning with Cortex Ask
```bash
# 1. Ask diagnostic questions about your system
cortex ask "what version of Python do I have"
cortex ask "is Docker installed"

# 2. Learn about new topics with educational queries
cortex ask "explain how Docker containers work"
cortex ask "best practices for nginx configuration"

# 3. Get step-by-step tutorials
cortex ask "teach me how to set up a Python virtual environment"
cortex ask "guide to configuring SSH keys"

# 4. Your learning topics are automatically tracked
# View at ~/.cortex/learning_history.json
```

---

## Getting Help

```bash
# General help
cortex --help

# Command-specific help
cortex install --help
cortex stack --help
cortex history --help
```

## More Information

- **Documentation**: https://cortexlinux.com/docs
- **Discord**: https://discord.gg/uCqHvxjU83
- **GitHub**: https://github.com/cortexlinux/cortex
