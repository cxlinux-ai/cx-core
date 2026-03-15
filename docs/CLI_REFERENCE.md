# CX CLI Command Reference

Complete reference for CX Terminal's AI-powered CLI commands.

## AI Commands

### `cx ask`

AI-powered command interface. Asks questions, generates commands, and optionally executes them.

```bash
cx ask "how do I install docker"          # Get AI answer
cx ask --do "install nginx"               # Generate and execute commands
cx ask --local "explain this error"       # Use local AI model only
cx ask --format json "list open ports"    # JSON output
echo "error log" | cx ask --do "fix this" # Pipe input
```

**Flags:**
| Flag | Short | Description |
|------|-------|-------------|
| `--do` | `-d` | Execute suggested commands (with confirmation) |
| `--yes` | `-y` | Skip confirmation prompts |
| `--local` | | Use local AI model only (Mistral 7B) |
| `--format` | `-f` | Output format: `text` (default) or `json` |
| `--verbose` | `-v` | Verbose output |

**Smart routing:** `cx ask` detects intent and routes to CX primitives when possible:
- `cx ask "create a python project"` → `cx new python <name>`
- `cx ask "save my work"` → `cx save <smart-name>`

---

### `cx install`

Install packages or software using natural language. Shortcut for `cx ask --do "install ..."`.

```bash
cx install docker
cx install "python 3.12 with pip"
cx install -y nodejs           # Skip confirmation
```

**Flags:** `--yes (-y)`, `--local`, `--verbose (-v)`

---

### `cx setup`

Setup or configure systems using natural language. Shortcut for `cx ask --do "setup ..."`.

```bash
cx setup "ssh key for github"
cx setup "firewall with ufw"
cx setup -y "postgresql database"
```

**Flags:** `--yes (-y)`, `--local`, `--verbose (-v)`

---

### `cx fix`

Fix errors or problems using AI. Reads the last error automatically if no argument provided.

```bash
cx fix                              # Fix last command's error
cx fix "permission denied on /var"
cx fix -y "broken apt packages"     # Auto-confirm fix
```

**Flags:** `--yes (-y)`, `--local`, `--verbose (-v)`

**Error capture:** Uses `~/.cx/last_error` file from shell integration to automatically capture the last failed command's output.

---

### `cx explain`

Explain a command, file, or concept.

```bash
cx explain "what does chmod 755 do"
cx explain iptables
cx explain --format json "systemd services"
```

**Flags:** `--format (-f)`, `--local`, `--verbose (-v)`

---

### `cx what`

Ask questions about the system. Shortcut for `cx ask` without execution.

```bash
cx what "is my disk usage"
cx what "ports are open"
cx what "version of python is installed"
```

**Flags:** `--format (-f)`, `--local`, `--verbose (-v)`

---

## Workspace Commands

### `cx new`

Scaffold a new project from a template.

```bash
cx new python my-project
cx new react my-app
cx new rust my-cli
```

**Available templates:** `python`, `node`, `react`, `nextjs`, `go`, `rust`, `api` (FastAPI), `docker`, `db` (SQLite)

Templates are stored in `~/.cx/templates/` or `/usr/share/cx-terminal/templates/`.

---

### `cx save`

Save a workspace snapshot.

```bash
cx save my-feature        # Save current workspace state
cx save                   # Auto-generated name
```

---

### `cx restore`

Restore a previously saved workspace snapshot.

```bash
cx restore my-feature
```

---

### `cx snapshots`

List and manage saved workspace snapshots.

```bash
cx snapshots              # List all snapshots
```

---

## Quick Blocks

Type these shortcuts directly in the terminal to quickly scaffold environments:

| Command | Description |
|---------|-------------|
| `/python` | Python environment setup |
| `/node` | Node.js project scaffold |
| `/react` | React app boilerplate |
| `/nextjs` | Next.js app setup |
| `/api` | FastAPI starter |
| `/docker` | Dockerfile + compose template |
| `/go` | Go project setup |
| `/rust` | Rust project setup |
| `/db` | SQLite setup |
| `/help` | List available quick blocks |

---

## Keyboard Shortcuts

### macOS

| Shortcut | Action |
|----------|--------|
| `Cmd+K` | Quick AI Ask |
| `Cmd+Shift+N` | New project from template |
| `Cmd+Shift+S` | Show snapshots |
| `Cmd+O` | Show snapshots for restore |
| `Cmd+Shift+F` | Find files |
| `Cmd+Shift+H` | Show CX help |

### Linux

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` | Quick AI Ask |
| `Ctrl+Shift+N` | New project from template |
| `Ctrl+Shift+S` | Show snapshots |
| `Ctrl+O` | Show snapshots for restore |
| `Ctrl+Shift+F` | Find files |
| `Ctrl+Shift+H` | Show CX help |

---

## AI Provider Configuration

CX Terminal connects to AI via the CX daemon. Supported providers:

- **Cloud:** OpenAI, Anthropic (via CX daemon)
- **Local:** Mistral 7B (via `--local` flag)

The daemon socket is located at `~/.cx/daemon.sock`.

---

## Tool System

When using `cx ask`, the AI can call built-in tools:

| Tool | Description |
|------|-------------|
| `kb_lookup(app, query)` | Look up application documentation |
| `troubleshoot(service, error?, symptoms?)` | Diagnose system issues |
| `search_packages(query, source?)` | Search apt/snap/pip packages |
| `get_system_info(type, target?)` | Get system status info |
| `read_logs(source, service?, path?, lines?)` | Read log files |

---

*CX Linux v0.3.2 · [cxlinux.com](https://cxlinux.com) · [GitHub](https://github.com/cxlinux-ai/cx-core)*
