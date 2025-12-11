# Cortex Linux

An AI-powered package manager for Debian/Ubuntu that understands natural language.

```
$ cortex install nginx --dry-run

🧠 Understanding request: nginx
📦 Mode: DRY RUN

╭───────────────────────────── Installation Plan ──────────────────────────────╮
│ Packages to install:                                                         │
│   - nginx (1.24.0)                                                           │
│   - nginx-common                                                             │
│   - libnginx-mod-http-geoip                                                  │
│                                                                              │
│ Commands that will be executed:                                              │
│   sudo apt update                                                            │
│   sudo apt install -y nginx                                                  │
╰──────────────────────────────────────────────────────────────────────────────╯

Run with --execute to install, or edit the plan above.
```

## Requirements

- **OS:** Ubuntu 22.04+ / Debian 12+
- **Python:** 3.10 or higher
- **API Key:** Anthropic API key (get one at [console.anthropic.com](https://console.anthropic.com))

Check your Python version:
```bash
python3 --version  # Must be 3.10+
```

## Quick Start

### 1. Clone and enter the repository
```bash
git clone https://github.com/cortexlinux/cortex.git
cd cortex
```

### 2. Create and activate virtual environment
```bash
python3 -m venv venv

# Linux/macOS (bash/zsh):
source venv/bin/activate

# Linux/macOS (sh/dash):
. venv/bin/activate

# Windows:
venv\Scripts\activate
```

### 3. Install Cortex
```bash
pip install -e .
```

### 4. Configure your API key
```bash
echo 'ANTHROPIC_API_KEY=your-key-here' > .env
```

Replace `your-key-here` with your actual Anthropic API key.

### 5. Verify installation
```bash
cortex --version
# Output: cortex, version 0.1.0

cortex install nginx --dry-run
# Should show installation plan
```

## Usage

### Preview installations (safe, default)
```bash
cortex install nginx --dry-run
cortex install "something to edit PDFs" --dry-run
```

### Actually install
```bash
cortex install nginx --execute
```

### View history and rollback
```bash
cortex history
cortex rollback <id>
```

### Check preferences
```bash
cortex check-pref
```

## Troubleshooting

### "ANTHROPIC_API_KEY not set"
```bash
# Make sure .env file exists and contains your key
cat .env
# Should show: ANTHROPIC_API_KEY=sk-ant-...

# If missing, create it:
echo 'ANTHROPIC_API_KEY=your-actual-key' > .env
```

### "command not found: cortex"
```bash
# Make sure virtual environment is activated
source venv/bin/activate  # or: . venv/bin/activate

# Reinstall if needed
pip install -e .
```

### "Python version too old"
```bash
# Check version
python3 --version

# Ubuntu/Debian - install newer Python:
sudo apt update
sudo apt install python3.11 python3.11-venv

# Use specific version:
python3.11 -m venv venv
```

### pip install fails
```bash
# Update pip first
pip install --upgrade pip

# Try again
pip install -e .

# If still failing, install build tools:
sudo apt install python3-dev build-essential
```

## Safety Features

| Feature | Description |
|---------|-------------|
| **Dry-run default** | Shows planned commands without executing |
| **Firejail sandbox** | Commands run in isolated environment |
| **Rollback support** | Undo any installation with `cortex rollback` |
| **Audit logging** | All actions logged to `~/.cortex/history.db` |
| **No root by default** | Only uses sudo when explicitly needed |

## Project Status

### Completed
- ✅ CLI with dry-run and execute modes
- ✅ Claude and OpenAI integration
- ✅ Installation history and rollback
- ✅ User preferences (YAML-backed)
- ✅ Hardware detection
- ✅ Firejail sandboxing

### In Progress
- 🔄 Conflict resolution UI
- 🔄 Multi-step orchestration
- 🔄 Ollama local model support
- 🔄 MCP server integration

## Contributing

We need:
- Python developers (package manager features)
- Linux kernel developers (kernel optimizations)
- Technical writers (documentation)
- Beta testers (bug reports)

Bounties available for merged PRs. See issues labeled `bounty`.

## Community

- Discord: [discord.gg/uCqHvxjU83](https://discord.gg/uCqHvxjU83)
- Email: mike@cortexlinux.com

## License

Apache 2.0
