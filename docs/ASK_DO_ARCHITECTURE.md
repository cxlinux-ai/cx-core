# Cortex `ask --do` Architecture

> AI-powered command execution with intelligent error handling, auto-repair, and real-time terminal monitoring.

## Table of Contents

- [Overview](#overview)
- [Architecture Diagram](#architecture-diagram)
- [Core Components](#core-components)
- [Execution Flow](#execution-flow)
- [Terminal Monitoring](#terminal-monitoring)
- [Error Handling & Auto-Fix](#error-handling--auto-fix)
- [Session Management](#session-management)
- [Key Files](#key-files)
- [Data Flow](#data-flow)

---

## Overview

`cortex ask --do` is an interactive AI assistant that can execute commands on your Linux system. Unlike simple command execution, it features:

- **Natural Language Understanding** - Describe what you want in plain English
- **Conflict Detection** - Detects existing resources (Docker containers, services, files) before execution
- **Task Tree Execution** - Structured command execution with dependencies
- **Auto-Repair** - Automatically diagnoses and fixes failed commands
- **Terminal Monitoring** - Watches your other terminals for real-time feedback
- **Session Persistence** - Tracks history across multiple interactions

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INPUT                                      │
│                    "install nginx and configure it"                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLI Layer                                       │
│                            (cli.py)                                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ Signal Handlers │  │ Session Manager │  │  Interactive    │             │
│  │  (Ctrl+Z/C)     │  │   (session_id)  │  │    Prompt       │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            AskHandler                                        │
│                            (ask.py)                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        LLM Integration                               │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │   │
│  │  │   Claude    │  │   Kimi K2   │  │   Ollama    │                  │   │
│  │  │  (Primary)  │  │ (Fallback)  │  │   (Local)   │                  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Response Types:                                                             │
│  ├── "command"      → Read-only info gathering                              │
│  ├── "do_commands"  → Commands to execute (requires approval)               │
│  └── "answer"       → Final response to user                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             DoHandler                                        │
│                         (do_runner/handler.py)                               │
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   Conflict   │  │  Task Tree   │  │    Auto      │  │   Terminal   │   │
│  │  Detection   │  │  Execution   │  │   Repair     │  │   Monitor    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                              │
│  Execution Modes:                                                            │
│  ├── Automatic   → Commands run with user approval                          │
│  └── Manual      → User runs commands, Cortex monitors                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌─────────────────────────────┐   ┌─────────────────────────────────────────┐
│     Automatic Execution      │   │         Manual Intervention              │
│                              │   │                                          │
│  ┌────────────────────────┐ │   │  ┌────────────────────────────────────┐ │
│  │   ConflictDetector     │ │   │  │      TerminalMonitor               │ │
│  │  (verification.py)     │ │   │  │      (terminal.py)                 │ │
│  │                        │ │   │  │                                    │ │
│  │  Checks for:           │ │   │  │  Monitors:                         │ │
│  │  • Docker containers   │ │   │  │  • ~/.bash_history                 │ │
│  │  • Running services    │ │   │  │  • ~/.zsh_history                  │ │
│  │  • Existing files      │ │   │  │  • terminal_watch.log              │ │
│  │  • Port conflicts      │ │   │  │  • Cursor IDE terminals            │ │
│  │  • Package conflicts   │ │   │  │                                    │ │
│  └────────────────────────┘ │   │  │  Features:                         │ │
│                              │   │  │  • Real-time command detection    │ │
│  ┌────────────────────────┐ │   │  │  • Error detection & auto-fix     │ │
│  │   CommandExecutor      │ │   │  │  • Desktop notifications          │ │
│  │   (executor.py)        │ │   │  │  • Terminal ID tracking           │ │
│  │                        │ │   │  └────────────────────────────────────┘ │
│  │  • Subprocess mgmt     │ │   │                                          │
│  │  • Timeout handling    │ │   │  ┌────────────────────────────────────┐ │
│  │  • Output capture      │ │   │  │      Watch Service (Daemon)        │ │
│  │  • Sudo handling       │ │   │  │      (watch_service.py)            │ │
│  └────────────────────────┘ │   │  │                                    │ │
│                              │   │  │  • Runs as systemd user service   │ │
│  ┌────────────────────────┐ │   │  │  • Auto-starts on login            │ │
│  │   ErrorDiagnoser       │ │   │  │  • Uses inotify for efficiency     │ │
│  │   (diagnosis.py)       │ │   │  │  • Logs to terminal_commands.json │ │
│  │                        │ │   │  └────────────────────────────────────┘ │
│  │  • Pattern matching    │ │   │                                          │
│  │  • LLM-powered diag    │ │   └─────────────────────────────────────────┘
│  │  • Fix suggestions     │ │
│  └────────────────────────┘ │
│                              │
│  ┌────────────────────────┐ │
│  │   AutoFixer            │ │
│  │   (diagnosis.py)       │ │
│  │                        │ │
│  │  • Automatic repairs   │ │
│  │  • Retry strategies    │ │
│  │  • Verification tests  │ │
│  └────────────────────────┘ │
└─────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Persistence Layer                                  │
│                                                                              │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │      DoRunDatabase          │  │        Log Files                     │  │
│  │    (~/.cortex/do_runs.db)   │  │                                      │  │
│  │                             │  │  • terminal_watch.log                │  │
│  │  Tables:                    │  │  • terminal_commands.json            │  │
│  │  • do_runs                  │  │  • watch_service.log                 │  │
│  │  • do_sessions              │  │                                      │  │
│  └─────────────────────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. CLI Layer (`cli.py`)

The entry point for `cortex ask --do`. Handles:

- **Signal Handlers**: Ctrl+Z stops current command (not the session), Ctrl+C exits
- **Session Management**: Creates/tracks session IDs for history grouping
- **Interactive Loop**: "What would you like to do?" prompt with suggestions
- **Error Handling**: Graceful error display without exposing internal details

```python
# Key functions
_run_interactive_do_session(handler)  # Main interactive loop
handle_session_interrupt()            # Ctrl+Z handler
```

### 2. AskHandler (`ask.py`)

Manages LLM communication and response parsing:

- **Multi-LLM Support**: Claude (primary), Kimi K2, Ollama (local)
- **Response Types**:
  - `command` - Read-only info gathering (ls, cat, systemctl status)
  - `do_commands` - Commands requiring execution (apt install, systemctl restart)
  - `answer` - Final response to user
- **Guardrails**: Rejects non-Linux/technical queries
- **Chained Command Handling**: Splits `&&` chains into individual commands

```python
# Key methods
_get_do_mode_system_prompt()     # LLM system prompt
_handle_do_commands()            # Process do_commands response
_call_llm()                      # Make LLM API call with interrupt support
```

### 3. DoHandler (`do_runner/handler.py`)

The execution engine. Core responsibilities:

- **Conflict Detection**: Checks for existing resources before execution
- **Task Tree Building**: Creates structured execution plan
- **Command Execution**: Runs commands with approval workflow
- **Auto-Repair**: Handles failures with diagnostic commands
- **Manual Intervention**: Coordinates with TerminalMonitor

```python
# Key methods
execute_with_task_tree()         # Main execution method
_handle_resource_conflict()      # User prompts for conflicts
_execute_task_node()             # Execute single task
_interactive_session()           # Post-execution suggestions
```

### 4. ConflictDetector (`verification.py`)

Pre-flight checks before command execution:

| Resource Type | Check Method |
|--------------|--------------|
| Docker containers | `docker ps -a --filter name=X` |
| Systemd services | `systemctl is-active X` |
| Files/directories | `os.path.exists()` |
| Ports | `ss -tlnp \| grep :PORT` |
| Packages (apt) | `dpkg -l \| grep X` |
| Packages (pip) | `pip show X` |
| Users/groups | `getent passwd/group` |
| Databases | `mysql/psql -e "SHOW DATABASES"` |

### 5. TerminalMonitor (`terminal.py`)

Real-time monitoring for manual intervention mode:

- **Sources Monitored**:
  - `~/.bash_history` and `~/.zsh_history`
  - `~/.cortex/terminal_watch.log` (from shell hooks)
  - Cursor IDE terminal files
  - tmux panes

- **Features**:
  - Command detection with terminal ID tracking
  - Error detection in command output
  - LLM-powered error analysis
  - Desktop notifications for errors/fixes
  - Auto-fix execution (non-sudo only)

### 6. Watch Service (`watch_service.py`)

Background daemon for persistent terminal monitoring:

```bash
# Install and manage
cortex watch --install --service  # Install systemd service
cortex watch --status             # Check status
cortex watch --uninstall --service
```

- Runs as systemd user service
- Uses inotify for efficient file watching
- Auto-starts on login, auto-restarts on crash
- Logs to `~/.cortex/terminal_commands.json`

---

## Execution Flow

### Flow 1: Automatic Execution

```
User: "install nginx"
         │
         ▼
    ┌─────────────────┐
    │  LLM Analysis   │ ──→ Gathers system info (OS, existing packages)
    └─────────────────┘
         │
         ▼
    ┌─────────────────┐
    │ Conflict Check  │ ──→ Is nginx already installed?
    └─────────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 Conflict   No Conflict
    │         │
    ▼         │
┌─────────────────┐    │
│ User Choice:    │    │
│ 1. Use existing │    │
│ 2. Restart      │    │
│ 3. Recreate     │    │
└─────────────────┘    │
         │             │
         └──────┬──────┘
                │
                ▼
    ┌─────────────────┐
    │ Show Commands   │ ──→ Display planned commands for approval
    └─────────────────┘
         │
         ▼
    ┌─────────────────┐
    │ User Approval?  │
    └─────────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
   Yes        No ──→ Cancel
    │
    ▼
    ┌─────────────────┐
    │ Execute Tasks   │ ──→ Run commands one by one
    └─────────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 Success    Failure
    │         │
    │         ▼
    │   ┌─────────────────┐
    │   │ Error Diagnosis │ ──→ Pattern matching + LLM analysis
    │   └─────────────────┘
    │         │
    │         ▼
    │   ┌─────────────────┐
    │   │   Auto-Repair   │ ──→ Execute fix commands
    │   └─────────────────┘
    │         │
    │         ▼
    │   ┌─────────────────┐
    │   │ Verify Fix      │
    │   └─────────────────┘
    │         │
    └────┬────┘
         │
         ▼
    ┌─────────────────┐
    │ Verification    │ ──→ Run tests to confirm success
    └─────────────────┘
         │
         ▼
    ┌─────────────────┐
    │ Interactive     │ ──→ "What would you like to do next?"
    │ Session         │
    └─────────────────┘
```

### Flow 2: Manual Intervention

```
User requests sudo commands OR chooses manual execution
         │
         ▼
    ┌─────────────────────────────────────────────────────────┐
    │              Manual Intervention Mode                    │
    │                                                          │
    │  ┌────────────────────────────────────────────────────┐ │
    │  │          Cortex Terminal                           │ │
    │  │  Shows:                                            │ │
    │  │  • Commands to run                                 │ │
    │  │  • Live terminal feed                              │ │
    │  │  • Real-time feedback                              │ │
    │  └────────────────────────────────────────────────────┘ │
    │                         ▲                                │
    │                         │ monitors                       │
    │                         │                                │
    │  ┌────────────────────────────────────────────────────┐ │
    │  │          Other Terminal(s)                         │ │
    │  │  User runs:                                        │ │
    │  │  $ sudo systemctl restart nginx                    │ │
    │  │  $ sudo apt install package                        │ │
    │  └────────────────────────────────────────────────────┘ │
    └─────────────────────────────────────────────────────────┘
         │
         ▼
    ┌─────────────────┐
    │ Command Match?  │
    └─────────────────┘
         │
    ┌────┴────────────┐
    │         │       │
    ▼         ▼       ▼
 Correct   Wrong    Error in
 Command   Command  Output
    │         │       │
    │         ▼       ▼
    │    Notification  Notification
    │    "Expected:    "Fixing error..."
    │     <cmd>"       + Auto-fix
    │         │       │
    └────┬────┴───────┘
         │
         ▼
    User presses Enter when done
         │
         ▼
    ┌─────────────────┐
    │ Validate        │ ──→ Check if expected commands were run
    └─────────────────┘
         │
         ▼
    ┌─────────────────┐
    │ Continue or     │
    │ Show Next Steps │
    └─────────────────┘
```

---

## Terminal Monitoring

### Watch Hook Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Terminal with Hook Active                         │
│                                                                           │
│  $ sudo systemctl restart nginx                                          │
│       │                                                                   │
│       ▼                                                                   │
│  PROMPT_COMMAND triggers __cortex_log_cmd()                              │
│       │                                                                   │
│       ▼                                                                   │
│  Writes to ~/.cortex/terminal_watch.log                                  │
│  Format: pts_1|sudo systemctl restart nginx                              │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Watch Service (Daemon)                            │
│                                                                           │
│  Monitors with inotify:                                                   │
│  • ~/.cortex/terminal_watch.log                                          │
│  • ~/.bash_history                                                        │
│  • ~/.zsh_history                                                         │
│       │                                                                   │
│       ▼                                                                   │
│  Parses: TTY|COMMAND                                                      │
│       │                                                                   │
│       ▼                                                                   │
│  Writes to ~/.cortex/terminal_commands.json                              │
│  {"timestamp": "...", "command": "...", "source": "watch_hook",          │
│   "terminal_id": "pts_1"}                                                │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         TerminalMonitor (In Cortex)                       │
│                                                                           │
│  During manual intervention:                                              │
│  1. Reads terminal_watch.log                                              │
│  2. Detects new commands                                                  │
│  3. Shows in "Live Terminal Feed"                                         │
│  4. Checks if command matches expected                                    │
│  5. Detects errors in output                                              │
│  6. Triggers auto-fix if needed                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

### Log File Formats

**`~/.cortex/terminal_watch.log`** (Simple):
```
pts_1|docker ps
pts_1|sudo systemctl restart nginx
pts_2|ls -la
shared|cd /home/user
```

**`~/.cortex/terminal_commands.json`** (Detailed):
```json
{"timestamp": "2026-01-16T14:15:00.123", "command": "docker ps", "source": "watch_hook", "terminal_id": "pts_1"}
{"timestamp": "2026-01-16T14:15:05.456", "command": "sudo systemctl restart nginx", "source": "watch_hook", "terminal_id": "pts_1"}
{"timestamp": "2026-01-16T14:15:10.789", "command": "cd /home/user", "source": "history", "terminal_id": "shared"}
```

---

## Error Handling & Auto-Fix

### Error Diagnosis Pipeline

```
Command fails with error
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Pattern Matching                          │
│                                                              │
│  COMMAND_SHELL_ERRORS = {                                    │
│    "Permission denied": "permission_error",                  │
│    "command not found": "missing_package",                   │
│    "Connection refused": "service_not_running",              │
│    "No space left": "disk_full",                            │
│    ...                                                       │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLM Analysis (Claude)                     │
│                                                              │
│  Prompt: "Analyze this error and suggest a fix"             │
│  Response:                                                   │
│    CAUSE: Service not running                                │
│    FIX: sudo systemctl start nginx                          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    AutoFixer Execution                       │
│                                                              │
│  1. Check if fix requires sudo                               │
│     - Yes → Show manual instructions + notification          │
│     - No → Execute automatically                             │
│  2. Verify fix worked                                        │
│  3. Retry original command if fixed                          │
└─────────────────────────────────────────────────────────────┘
```

### Auto-Fix Strategies

| Error Type | Strategy | Actions |
|------------|----------|---------|
| `permission_error` | `fix_permissions` | `chmod`, `chown`, or manual sudo |
| `missing_package` | `install_package` | `apt install`, `pip install` |
| `service_not_running` | `start_service` | `systemctl start`, check logs |
| `port_in_use` | `kill_port_user` | Find and stop conflicting process |
| `disk_full` | `free_disk_space` | `apt clean`, suggest cleanup |
| `config_error` | `fix_config` | Backup + LLM-suggested fix |

---

## Session Management

### Session Structure

```
Session (session_id: sess_20260116_141500)
│
├── Run 1 (run_id: do_20260116_141500_abc123)
│   ├── Query: "install nginx"
│   ├── Commands:
│   │   ├── apt update
│   │   ├── apt install -y nginx
│   │   └── systemctl start nginx
│   └── Status: SUCCESS
│
├── Run 2 (run_id: do_20260116_141600_def456)
│   ├── Query: "configure nginx for my domain"
│   ├── Commands:
│   │   ├── cat /etc/nginx/sites-available/default
│   │   └── [manual: edit config]
│   └── Status: SUCCESS
│
└── Run 3 (run_id: do_20260116_141700_ghi789)
    ├── Query: "test nginx"
    ├── Commands:
    │   └── curl localhost
    └── Status: SUCCESS
```

### Database Schema

```sql
-- Sessions table
CREATE TABLE do_sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT,
    ended_at TEXT,
    total_runs INTEGER DEFAULT 0
);

-- Runs table
CREATE TABLE do_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT,
    summary TEXT,
    mode TEXT,
    commands TEXT,  -- JSON array
    started_at TEXT,
    completed_at TEXT,
    user_query TEXT,
    FOREIGN KEY (session_id) REFERENCES do_sessions(session_id)
);
```

---

## Key Files

| File | Purpose |
|------|---------|
| `cortex/cli.py` | CLI entry point, signal handlers, interactive loop |
| `cortex/ask.py` | LLM communication, response parsing, command validation |
| `cortex/do_runner/handler.py` | Main execution engine, conflict handling, task tree |
| `cortex/do_runner/executor.py` | Subprocess management, timeout handling |
| `cortex/do_runner/verification.py` | Conflict detection, verification tests |
| `cortex/do_runner/diagnosis.py` | Error patterns, diagnosis, auto-fix strategies |
| `cortex/do_runner/terminal.py` | Terminal monitoring, shell hooks |
| `cortex/do_runner/models.py` | Data models (TaskNode, DoRun, CommandStatus) |
| `cortex/do_runner/database.py` | SQLite persistence for runs/sessions |
| `cortex/watch_service.py` | Background daemon for terminal monitoring |
| `cortex/llm_router.py` | Multi-LLM routing (Claude, Kimi, Ollama) |

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Data Flow                                   │
│                                                                          │
│  User Query ──→ AskHandler ──→ LLM ──→ Response                         │
│       │              │          │         │                              │
│       │              │          │         ▼                              │
│       │              │          │    ┌─────────┐                        │
│       │              │          │    │ command │ ──→ Execute read-only  │
│       │              │          │    └─────────┘         │              │
│       │              │          │         │              │              │
│       │              │          │         ▼              │              │
│       │              │          │    Output added        │              │
│       │              │          │    to history ─────────┘              │
│       │              │          │         │                              │
│       │              │          │         ▼                              │
│       │              │          │    Loop back to LLM                    │
│       │              │          │         │                              │
│       │              │          ▼         │                              │
│       │              │    ┌──────────────┐│                              │
│       │              │    │ do_commands  ││                              │
│       │              │    └──────────────┘│                              │
│       │              │          │         │                              │
│       │              │          ▼         │                              │
│       │              │    DoHandler       │                              │
│       │              │          │         │                              │
│       │              │          ▼         │                              │
│       │              │    Task Tree ──────┘                              │
│       │              │          │                                        │
│       │              │          ▼                                        │
│       │              │    Execute ──→ Success ──→ Verify ──→ Done       │
│       │              │          │                                        │
│       │              │          ▼                                        │
│       │              │    Failure ──→ Diagnose ──→ Fix ──→ Retry        │
│       │              │                                                   │
│       │              ▼                                                   │
│       │    ┌────────────┐                                               │
│       │    │   answer   │ ──→ Display to user                           │
│       │    └────────────┘                                               │
│       │              │                                                   │
│       ▼              ▼                                                   │
│    ┌─────────────────────┐                                              │
│    │  Session Database   │                                              │
│    │  ~/.cortex/do_runs.db                                              │
│    └─────────────────────┘                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Usage Examples

### Basic Usage

```bash
# Start interactive session
cortex ask --do

# One-shot command
cortex ask --do "install docker and run hello-world"
```

### With Terminal Monitoring

```bash
# Terminal 1: Start Cortex
cortex ask --do
> install nginx with ssl

# Terminal 2: Run sudo commands shown by Cortex
$ sudo apt install nginx
$ sudo systemctl start nginx
```

### Check History

```bash
# View do history
cortex do history

# Shows:
# Session: sess_20260116_141500 (3 runs)
#   Run 1: install nginx - SUCCESS
#   Run 2: configure nginx - SUCCESS
#   Run 3: test nginx - SUCCESS
```

---

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | Required |
| `CORTEX_TERMINAL` | Marks Cortex's own terminal | Set automatically |
| `CORTEX_DO_TIMEOUT` | Command timeout (seconds) | 120 |

### Watch Service

```bash
# Install (recommended)
cortex watch --install --service

# Check status
cortex watch --status

# View logs
journalctl --user -u cortex-watch
cat ~/.cortex/watch_service.log
```

---

## Troubleshooting

### Terminal monitoring not working

1. Check if service is running: `cortex watch --status`
2. Check hook is in .bashrc: `grep "Cortex Terminal Watch" ~/.bashrc`
3. For existing terminals, run: `source ~/.cortex/watch_hook.sh`

### Commands not being detected

1. Check watch log: `cat ~/.cortex/terminal_watch.log`
2. Ensure format is `TTY|COMMAND` (e.g., `pts_1|ls -la`)
3. Restart service: `systemctl --user restart cortex-watch`

### Auto-fix not working

1. Check if command requires sudo (auto-fix can't run sudo)
2. Check error diagnosis: Look for `⚠ Fix requires manual execution`
3. Run suggested commands manually in another terminal

---

## See Also

- [LLM Integration](./LLM_INTEGRATION.md)
- [Error Handling](./modules/README_ERROR_PARSER.md)
- [Verification System](./modules/README_VERIFICATION.md)
- [Troubleshooting Guide](./TROUBLESHOOTING.md)

