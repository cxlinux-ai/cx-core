# CX-Core MVP Product Requirements Document

> **Version:** 1.0
> **Date:** 2026-02-10
> **Status:** Draft
> **Owner:** CX Linux Team

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Current State Assessment](#3-current-state-assessment)
4. [MVP Definition & Success Criteria](#4-mvp-definition--success-criteria)
5. [Phase 0: Foundation Wiring (Blocker)](#5-phase-0-foundation-wiring-blocker)
6. [Phase 1: Core Intelligence (MVP)](#6-phase-1-core-intelligence-mvp)
7. [Phase 2: System Awareness (Post-MVP)](#7-phase-2-system-awareness-post-mvp)
8. [Phase 3: Configuration & Security (v1.1)](#8-phase-3-configuration--security-v11)
9. [Phase 4: Advanced Intelligence (v1.2)](#9-phase-4-advanced-intelligence-v12)
10. [Dependency Map](#10-dependency-map)
11. [Risk Register](#11-risk-register)
12. [Appendix: Full Item Tracker](#12-appendix-full-item-tracker)

---

## 1. Executive Summary

CX Terminal is an AI-native terminal emulator for CX Linux. The core value proposition is: **"Talk to your Linux system in plain English, and it does the right thing."**

Of the 147 planned features in the CX-Core layer, **23 are done (16%), 12 are partial (8%), and 112 remain (76%)**. This PRD prioritizes the remaining work into four phases based on two principles:

1. **Does it unblock other work?** Foundation items that everything else depends on ship first.
2. **Does the user see it immediately?** Customer-facing features that demonstrate the product's value get priority over backend infrastructure.

The MVP target is a terminal where a user can install packages, check system status, manage services, and get AI assistance — all through natural language — across Ubuntu, Fedora, and Arch.

---

## 2. Problem Statement

Linux is powerful but hostile to newcomers and tedious for experts. Users must:

- Memorize package manager syntax that differs across distros (`apt install` vs `pacman -S` vs `dnf install`)
- Read man pages to understand system state (`df -h`, `free -m`, `systemctl status`)
- Hand-edit config files with arcane syntax (nginx blocks, systemd units, php.ini)
- Manage firewalls with complex rule syntax (nftables, iptables, ufw)

**CX Terminal eliminates this friction.** Users say what they want. The system figures out the how.

**Target users for MVP:**
- Linux newcomers (coming from Windows/macOS) who don't know package managers
- Developers who use Linux daily but waste time on repetitive admin tasks
- DevOps engineers managing multiple distros who need a single interface

---

## 3. Current State Assessment

### What's Built and Working

| Component | Status | Notes |
|-----------|--------|-------|
| Terminal core (WezTerm fork) | **Production-ready** | GPU-accelerated, cross-platform |
| CLI command routing | **Complete** | 30+ commands, `cx ask/install/fix/explain` |
| Pattern matching | **Complete** | 70+ patterns, confidence scoring |
| AI Providers (Claude + Ollama) | **Complete** | Streaming, fallback logic, auto-detect |
| Agent runtime + 5 agents | **Complete** | System, File, Git, Package, Docker |
| Shell integration (bash/zsh/fish) | **Complete** | OSC sequences, error capture, blocks |
| Block data structures | **Complete** | States, actions, metadata |
| Daemon protocol | **Complete** | Full JSON schema, serialization |
| Chat history system | **Complete** | Message management, capacity limits |
| Learning system | **Scaffolded** | Written but `#![allow(dead_code)]` |

### What's Built But Not Wired

This is the **single biggest gap**: production-ready backend code exists but isn't connected to the GUI.

| Component | Code Location | What's Missing |
|-----------|---------------|----------------|
| Agent system | `wezterm-gui/src/agents/` | Not connected to GUI event loop |
| AI panel | `wezterm-gui/src/ai/` | Widget not rendered, no keyboard shortcut |
| Block renderer | `wezterm-gui/src/blocks/renderer.rs` | Not integrated into terminal paint loop |
| Block parser | `wezterm-gui/src/blocks/parser.rs` | OSC sequences not consumed |
| Daemon client | `wezterm-gui/src/cx_daemon/client.rs` | Socket connection not established |

### What Doesn't Exist Yet

| Section | Items | Priority |
|---------|-------|----------|
| Configuration Management (1.2) | 17 items | Phase 3 |
| Network Status (1.3.3) | 5 items | Phase 2 |
| Firewall Management (1.5) | 11 items | Phase 3 |
| Multi-Agent Orchestrator (1.6.1) | 6 items | Phase 1 |
| Local LLM Runtime (1.7.1) | 7 items | Phase 4 |
| Tiny Embedded Model (1.7.2) | 4 items | Phase 4 |

---

## 4. MVP Definition & Success Criteria

### MVP = "A user can manage their Linux system through natural language in the terminal"

**The MVP is reached when a user can:**

1. Type `cx install nginx` and have it work on Ubuntu, Fedora, or Arch
2. Ask "how much disk space do I have?" and get a clear answer
3. Say "restart nginx" and have the service restart with confirmation
4. Get AI-powered explanations of errors and commands
5. See command output organized in collapsible blocks
6. Have all of the above work with local AI (Ollama) — no cloud required

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Core commands work across 3 distros | 100% | Automated testing on Ubuntu, Fedora, Arch |
| AI response latency (local) | < 3 seconds | End-to-end from Enter to first token |
| AI response latency (cloud) | < 1.5 seconds | End-to-end from Enter to first token |
| Zero data loss on package operations | 100% | No partial installs, no broken deps |
| Shell integration works | bash, zsh, fish | Manual + automated tests |

---

## 5. Phase 0: Foundation Wiring (Blocker)

> **Priority: CRITICAL — Everything else depends on this**
> **Estimated scope: The existing code needs to be connected**
> **Risk: Low (code exists, needs plumbing)**

Phase 0 is not about writing new features. It's about connecting the production-ready backend code to the GUI so users can actually experience what's already built.

### P0-1: Wire Block System into Terminal Renderer

**Why it blocks everything:** Blocks are the primary UX differentiator. Without them, the terminal looks like every other terminal. AI explanations, command output, error highlighting — all render inside blocks.

| Task | Description | Depends On |
|------|-------------|------------|
| P0-1a | Connect `BlockParser` to terminal's OSC sequence handler so `777;cx;block;start/end` markers create `Block` objects | Nothing |
| P0-1b | Connect `BlockManager` to the GUI's render loop so blocks appear visually in the terminal viewport | P0-1a |
| P0-1c | Wire `BlockRenderer` to paint block chrome (collapse button, status icon, copy button, re-run button) over terminal output | P0-1b |
| P0-1d | Implement block click handlers (collapse, copy, re-run, explain) as GUI events | P0-1c |

**Acceptance criteria:** User runs `ls -la` in CX Terminal with shell integration sourced, sees output wrapped in a block with a green checkmark, can click to collapse/copy/re-run.

### P0-2: Wire AI Panel into GUI

**Why it blocks everything:** The AI panel is the primary interface for natural language interaction within the GUI (beyond CLI).

| Task | Description | Depends On |
|------|-------------|------------|
| P0-2a | Implement `Ctrl+Space` keyboard shortcut to toggle AI panel visibility | Nothing |
| P0-2b | Wire `ai/widget.rs` into the GUI's layout system (side panel rendering) | P0-2a |
| P0-2c | Connect chat input to `AIManager` so typed queries go to Claude/Ollama and responses stream back | P0-2b |
| P0-2d | Wire "Explain" block action to send block content to AI panel | P0-1d, P0-2c |

**Acceptance criteria:** User presses `Ctrl+Space`, AI panel slides open, user types "what does grep -r do?", gets streaming response from Claude or Ollama.

### P0-3: Wire Agent System to GUI

**Why it blocks everything:** Agents are the execution backbone. Package installs, service management, system queries all route through agents.

| Task | Description | Depends On |
|------|-------------|------------|
| P0-3a | Connect `AgentRuntime` initialization to GUI startup (register all 5 built-in agents) | Nothing |
| P0-3b | Wire `@agent command` syntax in AI panel input to `AgentRuntime::execute()` | P0-2c, P0-3a |
| P0-3c | Route agent responses back to AI panel (or inline in terminal) for display | P0-3b |
| P0-3d | Implement confirmation dialog when agents return commands requiring `require_confirmation` | P0-3c |

**Acceptance criteria:** User types `@package install nginx` in AI panel, sees the apt/pacman/dnf command, confirms, and the package installs.

### P0-4: Wire Daemon Client

**Why it blocks everything:** The daemon enables persistent state, learning, and cross-terminal coordination.

| Task | Description | Depends On |
|------|-------------|------------|
| P0-4a | Implement daemon socket connection on terminal startup (with graceful fallback if daemon not running) | Nothing |
| P0-4b | Wire `RegisterTerminal` / `UnregisterTerminal` lifecycle messages | P0-4a |
| P0-4c | Route AI queries through daemon when available (daemon → local fallback) | P0-4a, P0-2c |
| P0-4d | Wire `LearnFromHistory` messages so completed commands feed the learning system | P0-4a, P0-1a |

**Acceptance criteria:** Terminal connects to daemon on start, routes AI queries through it, and falls back to direct provider if daemon is unavailable.

---

## 6. Phase 1: Core Intelligence (MVP)

> **Priority: HIGH — This is what makes CX Terminal worth using**
> **Depends on: Phase 0 complete**
> **Target: First public beta**

Phase 1 completes the features that a user interacts with daily. These are the "wow" moments.

### 1A: Complete Package Management (1.1)

Package management is the #1 reason Linux newcomers struggle. This is the flagship feature.

#### 1A-1: Finish Package Adapters (High Priority — Customer Facing)

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 1 | Flatpak integration as secondary source | 1.1.1 | Many apps (Spotify, Discord, VS Code) are Flatpak-only. Users will hit this in week 1. | Package agent working |
| 2 | Snap integration as secondary source | 1.1.1 | Ubuntu users expect Snap. Canonical pushes it for many packages. | Package agent working |
| 3 | AUR helper integration (yay/paru) | 1.1.1 | Arch users live in the AUR. Without it, Arch support is incomplete. | Package agent working |

**Acceptance criteria:** User says `cx install spotify`. System detects it's not in apt repos, finds it on Flathub, offers to install via Flatpak.

#### 1A-2: Safety & Reliability (High Priority — Trust Building)

Users must trust CX Terminal before they let it modify their system. These features build trust.

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 4 | Dependency pre-check system | 1.1.1 | Before installing anything, show what will change. Prevents surprises. | Package adapters |
| 5 | Installation verification post-install | 1.1.1 | After installing, confirm it worked. Catch silent failures. | Package adapters |
| 6 | Rollback point creation before operations | 1.1.1 | Safety net. Users need to know they can undo. | Package adapters |

**Acceptance criteria:** User says `cx install nginx`. System shows: "This will install nginx (1.24.0), libpcre2-8-0, and 3 other packages (12MB). Rollback point created. Proceed? [Y/n]". After install: "nginx installed successfully. Binary available at /usr/sbin/nginx. Service not yet started."

#### 1A-3: Search & Discovery (Medium Priority — Customer Facing)

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 7 | "What package provides X" queries | 1.1.2 | "I typed `convert` and it said command not found" — this is how newcomers discover packages. | Package adapters |
| 8 | Package recommendation engine | 1.1.2 | After installing Node, suggest npm/yarn. After installing Python, suggest pip/venv. Low-hanging fruit for UX. | Package adapters, AI provider |
| 9 | Package comparison feature | 1.1.2 | "Should I use nginx or apache?" Users ask this constantly. | AI provider |
| 10 | Package popularity/usage metrics | 1.1.2 | Show download counts and popularity to help users choose. | Package adapters |

#### 1A-4: System Updates (Medium Priority — Customer Facing)

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 11 | Pre-update impact analysis | 1.1.3 | "Your kernel will update from 6.1 to 6.5. 23 packages will change." | Safe update command (done) |
| 12 | Update changelog summary | 1.1.3 | AI-summarized changelogs. "This update fixes 2 CVEs and adds USB4 support." | AI provider, safe update (done) |
| 13 | Selective update capability | 1.1.3 | "Update everything except the kernel." Essential for production systems. | Safe update (done) |
| 14 | Kernel update safety checks | 1.1.3 | Verify bootloader, initramfs, fallback kernel before kernel updates. | Safe update (done) |
| 15 | Post-update verification | 1.1.3 | After update, verify services restarted and system is healthy. | Safe update (done), service status (done) |

### 1B: Complete System Status Queries (1.3)

System status queries are the second most common interaction. Users ask "what's going on?" constantly.

#### 1B-1: Hardware Status Gaps (High Priority — Customer Facing)

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 16 | GPU status queries (NVIDIA/AMD) | 1.3.1 | Gamers, ML engineers, and content creators all need GPU info. Steam Deck driving Linux adoption. | System agent (done) |
| 17 | Temperature monitoring | 1.3.1 | "Why is my laptop fan screaming?" — immediate, visible value. | System agent (done) |
| 18 | Complete hardware inventory | 1.3.1 | Finish the partial implementation. Full inventory (CPU, RAM, disks, GPU, NICs, USB). | System agent (done) |

#### 1B-2: Software Status Gaps (High Priority — Customer Facing)

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 19 | Port status queries ("What's on port 80?") | 1.3.2 | Developers and admins check ports daily. "Something is already using port 3000." | System agent (done) |
| 20 | Complete process listing with filtering | 1.3.2 | Finish partial impl. "Show all Python processes using >1GB RAM." | System agent (done) |
| 21 | Dependency tree visualization | 1.3.2 | "What depends on libssl?" Critical for understanding removal impact. | Package agent (done) |

#### 1B-3: Network Status (Medium Priority — Customer Facing)

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 22 | Network interface status | 1.3.3 | "Is my WiFi connected?" Basic question, no current answer. | New: Network agent |
| 23 | IP address queries | 1.3.3 | "What's my IP?" — the most-googled networking question. | Network agent |
| 24 | Connection status queries | 1.3.3 | Active connections, established sessions. Debug connectivity. | Network agent |
| 25 | DNS resolution queries | 1.3.3 | "Why can't I reach google.com?" DNS is the #1 networking issue. | Network agent |
| 26 | Route table display | 1.3.3 | Routing info in readable format. Less common but needed. | Network agent |

### 1C: Complete Service Management (1.4)

Service management is the third pillar. Users need to start, stop, and debug services.

#### 1C-1: Systemctl Completion (High Priority — Customer Facing)

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 27 | Complete start/stop/restart adapters | 1.4.1 | Currently partial — detect service but don't execute. Must actually start/stop services. | Service agent |
| 28 | Enable/disable command adapters | 1.4.1 | "Make nginx start on boot." Basic lifecycle management. | #27 |
| 29 | Service log viewing (journalctl) | 1.4.1 | "Why did nginx fail?" Users need logs. Journalctl is cryptic. | #27 |
| 30 | Failed service diagnosis | 1.4.1 | Auto-diagnose: check logs, verify config, test ports, suggest fixes. AI-powered. | #29, AI provider |
| 31 | Service dependency visualization | 1.4.1 | Show what starts before/after a service. Understand boot order. | #27 |

#### 1C-2: Process Management (Medium Priority — Customer Facing)

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 32 | Implement Process agent | 1.4.2 | Declared in `BuiltinAgent::Process` but never implemented. | Agent runtime (done) |
| 33 | Process search by name | 1.4.2 | "Find all nginx processes." Basic ops. | #32 |
| 34 | Process kill with confirmation | 1.4.2 | "Kill the process on port 3000." With safety confirmation. | #32, #33 |
| 35 | Complete resource hog detection | 1.4.2 | Finish partial impl. CPU + memory + file descriptors. | #32 |

#### 1C-3: Cron Job Management (Low Priority — Customer Facing)

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 36 | Cron job listing | 1.4.3 | "What cron jobs are running?" | System agent (done) |
| 37 | Cron job creation via natural language | 1.4.3 | "Run backup.sh every night at 2am." | #36 |
| 38 | Cron job modification | 1.4.3 | Change schedule or command of existing jobs. | #36 |
| 39 | Cron job deletion with confirmation | 1.4.3 | Remove jobs safely. | #36 |
| 40 | Cron syntax validation | 1.4.3 | Validate before saving. Show "next 5 runs" in plain English. | #36 |

### 1D: Multi-Agent Orchestrator (1.6.1)

The orchestrator is what turns individual agents into an intelligent system.

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 41 | Intent parser and router | 1.6.1 | Central brain: "install nginx and configure it for my site" → routes to Package agent then Config agent. | Agent runtime (done), AI provider (done) |
| 42 | Task decomposition logic | 1.6.1 | Break "set up a LAMP stack" into: install Apache, install MySQL, install PHP, configure each. | #41 |
| 43 | Execution order manager | 1.6.1 | Dependencies: install MySQL before configuring it. Parallelize independent tasks. | #42 |
| 44 | Inter-agent message queue | 1.6.1 | Agents need to pass results to each other. Redis or in-process channel. | #43 |
| 45 | Timeout and retry handling | 1.6.1 | Package installs can take minutes. Handle timeouts gracefully. | #43 |
| 46 | Finish agent communication schema | 1.6.1 | Complete the partial `DaemonRequest`/`DaemonResponse` protocol. | Daemon protocol (done) |

### 1E: Cloud LLM Completion (1.7.3)

| # | Task | Roadmap Ref | Why Now | Depends On |
|---|------|-------------|---------|------------|
| 47 | Complete OpenAI API integration | 1.7.3 | Some users prefer GPT. Stub exists, needs implementation. | AI provider trait (done) |
| 48 | Response caching | 1.7.3 | "What does grep do?" — cache this. Saves API costs, reduces latency. | AI providers (done) |
| 49 | Usage tracking for billing | 1.7.3 | Track tokens consumed per provider. Essential for Pro tier pricing. | AI providers (done) |

---

## 7. Phase 2: System Awareness (Post-MVP)

> **Priority: MEDIUM — Deepens the product, builds retention**
> **Depends on: Phase 1 substantially complete**
> **Target: v1.1 release**

Phase 2 makes the agents smarter and the system more autonomous.

### 2A: Specialist Agents (1.6.2–1.6.7)

#### Package Agent Enhancement

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 50 | Conflict detection | 1.6.2 | Package agent (done) |
| 51 | Dependency resolution with explanation | 1.6.2 | #50 |
| 52 | Rollback support for agent | 1.6.2 | Rollback system (#6) |

#### Config Agent (New)

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 53 | Implement safe file modification | 1.6.3 | Agent runtime (done) |
| 54 | Add syntax validation | 1.6.3 | #53 |
| 55 | Create backup management | 1.6.3 | #53 |

#### Service Agent Enhancement

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 56 | Complete systemctl wrapper | 1.6.4 | Service management (#27-31) |
| 57 | Deep journalctl integration | 1.6.4 | #56, #29 |
| 58 | Health monitoring (beyond running/stopped) | 1.6.4 | #56 |

#### Security Agent (New)

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 59 | Implement firewall management | 1.6.5 | Agent runtime (done) |
| 60 | Permission checking | 1.6.5 | #59 |
| 61 | Security scanning (CVE, open ports, weak perms) | 1.6.5 | #59 |

#### Diagnostic Agent (New)

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 62 | Log analysis | 1.6.6 | Agent runtime (done), journalctl (#29) |
| 63 | Error pattern recognition | 1.6.6 | #62 |
| 64 | Fix suggestions | 1.6.6 | #62, #63, AI provider |

#### Conflict Resolver (New)

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 65 | Dependency conflict detection | 1.6.7 | Package agent (#50) |
| 66 | Version conflict resolution | 1.6.7 | #65 |
| 67 | User-guided resolution flow | 1.6.7 | #66 |

### 2B: Wire Learning System

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 68 | Integrate learning/collector.rs into GUI event loop | 1.7.4 | Phase 0 wiring |
| 69 | Connect privacy filter to data pipeline | 1.7.4 | #68 |
| 70 | Enable model update pipeline | 1.7.4 | #68, #69 |

---

## 8. Phase 3: Configuration & Security (v1.1)

> **Priority: MEDIUM — Expands from "status queries" to "system modification"**
> **Depends on: Phase 2 Config Agent and Security Agent exist**
> **Target: v1.1 release**

### 3A: Configuration Management (1.2.1)

#### Config File Parsers

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 71 | nginx.conf parser | 1.2.1 | Config agent (#53) |
| 72 | systemd unit parser | 1.2.1 | Config agent (#53) |
| 73 | .env file parser | 1.2.1 | Config agent (#53) |
| 74 | php.ini parser | 1.2.1 | Config agent (#53) |
| 75 | apache2.conf parser | 1.2.1 | Config agent (#53) |

**Priority note:** nginx and systemd are the most common config files developers touch. .env files are ubiquitous in application development. php.ini and apache2.conf serve a narrower audience and can follow.

#### Config Safety

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 76 | Natural language intent detection for config | 1.2.1 | Config parsers (#71-75), AI provider |
| 77 | Diff preview before applying changes | 1.2.1 | Config parsers (#71-75) |
| 78 | Automatic backup before modification | 1.2.1 | Config agent backup (#55) |
| 79 | Rollback capability for config changes | 1.2.1 | #78 |
| 80 | Config validation before applying | 1.2.1 | Config parsers (#71-75), #54 |
| 81 | Syntax error detection and fix suggestions | 1.2.1 | #80, AI provider |

#### Config Templates (1.2.2)

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 82 | LEMP stack template (nginx + MySQL + PHP) | 1.2.2 | nginx parser (#71), systemd parser (#72) |
| 83 | LAMP stack template (Apache + MySQL + PHP) | 1.2.2 | apache parser (#75), systemd parser (#72) |
| 84 | Node.js app config template | 1.2.2 | nginx parser (#71), systemd parser (#72) |
| 85 | Python/FastAPI config template | 1.2.2 | nginx parser (#71), systemd parser (#72) |
| 86 | Reverse proxy templates | 1.2.2 | nginx parser (#71) |
| 87 | SSL/TLS config templates | 1.2.2 | nginx parser (#71), apache parser (#75) |

### 3B: Firewall Management (1.5)

#### nftables Adapter (1.5.1)

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 88 | Port opening commands | 1.5.1 | Security agent (#59) |
| 89 | Port closing commands | 1.5.1 | #88 |
| 90 | IP allow/block commands | 1.5.1 | #88 |
| 91 | Rate limiting rules | 1.5.1 | #88 |
| 92 | Rule preview before applying | 1.5.1 | #88 |
| 93 | Firewall status display | 1.5.1 | #88 |
| 94 | Firewall rule backup/restore | 1.5.1 | #88 |
| 95 | Common preset rules (web server, database, SSH) | 1.5.1 | #88 |

#### UFW Integration (1.5.2)

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 96 | UFW status queries | 1.5.2 | Security agent (#59) |
| 97 | UFW allow/deny commands | 1.5.2 | #96 |
| 98 | Application profile support | 1.5.2 | #96 |

---

## 9. Phase 4: Advanced Intelligence (v1.2)

> **Priority: LOW — Optimization and differentiation**
> **Depends on: Phases 1-3 substantially complete**
> **Target: v1.2 release**

### 4A: Local LLM Runtime (1.7.1)

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 99 | llama.cpp service integration | 1.7.1 | Ollama provider (done) as reference |
| 100 | GGUF model loader | 1.7.1 | #99 |
| 101 | GPU acceleration — CUDA | 1.7.1 | #99 |
| 102 | GPU acceleration — ROCm | 1.7.1 | #99 |
| 103 | CPU fallback (complete, beyond Ollama) | 1.7.1 | #99 |
| 104 | Model hot-swapping | 1.7.1 | #99, #100 |
| 105 | Model versioning | 1.7.1 | #99, #100 |

### 4B: Tiny Embedded Model (1.7.2)

| # | Task | Roadmap Ref | Depends On |
|---|------|-------------|------------|
| 106 | Training data from apt commands | 1.7.2 | Learning system (#68-70) |
| 107 | Build quantized model (~5MB) | 1.7.2 | #106 |
| 108 | Offline-first inference | 1.7.2 | #107 |
| 109 | Common command caching (complete) | 1.7.2 | #108 |

---

## 10. Dependency Map

```
PHASE 0 (Foundation Wiring) ─── BLOCKS EVERYTHING
├── P0-1: Block system → GUI
├── P0-2: AI panel → GUI
├── P0-3: Agent system → GUI
└── P0-4: Daemon client → GUI

PHASE 1 (MVP) ─── Depends on Phase 0
├── 1A: Package Management
│   ├── Flatpak/Snap/AUR (independent, can parallel)
│   ├── Safety features ← depends on adapters
│   └── Search/Discovery ← depends on adapters + AI
├── 1B: System Status
│   ├── Hardware gaps (independent)
│   ├── Software gaps (independent)
│   └── Network status ← needs NEW Network agent
├── 1C: Service Management
│   ├── Complete systemctl ← needs service agent wiring
│   ├── Process management ← needs NEW Process agent
│   └── Cron management ← needs system agent
├── 1D: Multi-Agent Orchestrator
│   ├── Intent parser ← needs AI provider + agent runtime
│   ├── Task decomposition ← needs intent parser
│   ├── Execution order ← needs decomposition
│   └── Message queue ← needs execution order
└── 1E: Cloud LLM
    ├── OpenAI (independent)
    ├── Caching (independent)
    └── Usage tracking (independent)

PHASE 2 (Post-MVP) ─── Depends on Phase 1
├── Specialist agents (Config, Security, Diagnostic)
├── Enhanced Package/Service agents
├── Conflict resolver
└── Learning system integration

PHASE 3 (v1.1) ─── Depends on Phase 2 agents
├── Config file parsers ← needs Config agent
├── Config safety features ← needs parsers
├── Config templates ← needs parsers + safety
├── Firewall (nftables) ← needs Security agent
└── Firewall (UFW) ← needs Security agent

PHASE 4 (v1.2) ─── Depends on Phases 1-3
├── llama.cpp runtime (independent research)
├── Tiny embedded model ← needs learning data
└── Advanced offline features ← needs model
```

### Critical Path

The longest dependency chain determining the minimum time to MVP:

```
Phase 0 wiring → Network agent → Network status queries
Phase 0 wiring → Process agent → Process management
Phase 0 wiring → Service agent completion → Journalctl → Failed service diagnosis
Phase 0 wiring → Intent parser → Task decomposition → Execution order → Message queue
```

### Parallelization Opportunities

These can be built simultaneously by different contributors:

| Track | Items | Independent? |
|-------|-------|--------------|
| Package adapters (Flatpak, Snap, AUR) | #1, #2, #3 | Yes — each is independent |
| System status gaps | #16, #17, #18 | Yes — each is independent |
| Network agent + queries | #22-26 | Yes — new agent, no deps |
| Process agent + queries | #32-35 | Yes — new agent, no deps |
| OpenAI integration | #47 | Yes — follows existing pattern |
| Response caching | #48 | Yes — no dependencies |
| Cron management | #36-40 | Yes — system agent exists |

---

## 11. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Phase 0 takes longer than expected** (WezTerm internals are complex) | Medium | Critical | Spike on block rendering first. If it takes >1 week, reassess architecture. |
| **Flatpak/Snap APIs change** | Low | Medium | Abstract behind adapter interface. Pin to stable API versions. |
| **nftables syntax varies across distros** | Medium | Medium | Test on Ubuntu 24.04, Fedora 40, Arch (rolling). Maintain distro-specific rule generation. |
| **LLM quality insufficient for intent parsing** | Low | High | Use Claude for complex intent, pattern matching for common cases (already working). Keep human confirmation in the loop. |
| **Config file modification breaks user systems** | Medium | Critical | Mandatory backup before every change. Mandatory validation before apply. Mandatory diff preview. Never auto-apply config changes. |
| **Daemon socket permission issues** | Medium | Low | Fallback to direct provider. User-level socket path (XDG_RUNTIME_DIR). |
| **Scope creep** | High | Medium | Strict phase discipline. No feature moves to an earlier phase without something moving out. |

---

## 12. Appendix: Full Item Tracker

### Summary by Status

| Status | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Total |
|--------|---------|---------|---------|---------|---------|-------|
| Not started | 16 | 49 | 21 | 28 | 11 | 125 |
| **Total items** | **16** | **49** | **21** | **28** | **11** | **125** |

> Note: 125 items = 112 not-done + 12 partial + 1 (wiring tasks not in original list)

### Items Already Done (23 total — not re-listed above)

For reference, these are complete and not part of the roadmap:

- ✅ Intent parser for package installation (1.1.1)
- ✅ Distro detection module (1.1.1)
- ✅ Package name resolver / cross-distro (1.1.1)
- ✅ apt adapter (1.1.1)
- ✅ pacman adapter (1.1.1)
- ✅ dnf adapter (1.1.1)
- ✅ Natural language package search (1.1.2)
- ✅ Safe system update command (1.1.3)
- ✅ Disk space queries (1.3.1)
- ✅ Memory usage queries (1.3.1)
- ✅ CPU usage queries (1.3.1)
- ✅ Package version queries (1.3.2)
- ✅ Service status queries (1.3.2)
- ✅ Installed package listing (1.3.2)
- ✅ Status command adapter (1.4.1)
- ✅ Full package management capabilities (1.6.2)
- ✅ Claude API integration (1.7.3)
- ✅ Fallback routing logic (1.7.3)
- ✅ Execution logging (1.7.4) — scaffolded
- ✅ Success/failure classification (1.7.4) — scaffolded
- ✅ Training data collection (1.7.4) — scaffolded
- ✅ Privacy-safe data extraction (1.7.4) — scaffolded
- ✅ Model update pipeline (1.7.4) — scaffolded

---

*This document should be treated as a living artifact. Update item statuses as work is completed. Review phase boundaries quarterly.*
