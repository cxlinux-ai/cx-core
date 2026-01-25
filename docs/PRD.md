# CX Terminal - Product Requirements Document

**Version:** 1.0
**Date:** January 24, 2025
**Author:** CX Linux Team
**Status:** Draft

---

## Executive Summary

CX Terminal is an AI-native terminal emulator built for CX Linux. It combines modern terminal UX (command blocks, AI assistance) with deep OS integration, creating a differentiated product that increases CX Linux's value proposition and user stickiness.

**Core Thesis:** The terminal is the primary interface for power users. By making it intelligent and integrated with the OS, we create switching costs and justify premium pricing.

---

## Market Validation

### Target Users

| Segment | Size | Pain Points | Willingness to Pay |
|---------|------|-------------|-------------------|
| Developers | ~27M globally | Context switching, remembering commands | High ($10-20/mo) |
| DevOps/SysAdmins | ~4M globally | Multi-system management, repetitive tasks | Very High ($20-50/mo) |
| Data Scientists | ~3M globally | Environment management, tool integration | Medium ($10-15/mo) |
| Linux Enthusiasts | ~30M globally | Fragmented tools, lack of polish | Low-Medium (prefer free) |

### Competitive Landscape

| Product | Users | Pricing | Strengths | Weaknesses |
|---------|-------|---------|-----------|------------|
| **Warp** | ~500K | $0-15/mo | AI, modern UX, funding | No Linux (Mac only), cloud-dependent |
| **iTerm2** | ~2M | Free | Mature, Mac ecosystem | Mac only, no AI |
| **Kitty** | ~500K | Free | Fast, configurable | No AI, developer-focused |
| **Alacritty** | ~300K | Free | Minimal, fast | No features, no AI |
| **GNOME Terminal** | ~10M+ | Free | Default, stable | Dated UX, no AI |

### Market Gap

**No product offers:** Linux-native + AI-powered + OS-integrated + Privacy-focused

This is CX Terminal's positioning.

### Validation Signals

1. **Warp's Growth:** $73M raised, 500K+ users proves demand for AI terminals
2. **GitHub Copilot:** $100/yr, 1M+ users proves developers pay for AI assistance
3. **Linux Desktop Growth:** 4% market share (up from 2%), Steam Deck driving adoption
4. **Privacy Concerns:** 67% of developers worry about code leaving their machine (Stack Overflow 2024)

---

## Product Vision

### One-Liner
"The terminal that understands your system."

### Vision Statement
CX Terminal transforms the terminal from a command executor into an intelligent assistant. It learns from your usage, understands your system, and helps you work faster—all while keeping your data private.

### Success Metrics (12 months post-launch)

| Metric | Target | Rationale |
|--------|--------|-----------|
| DAU | 10,000 | 5% of CX Linux installs |
| Retention (D30) | 60% | Stickiness validation |
| Pro Conversion | 5% | Revenue validation |
| NPS | 50+ | Product-market fit |
| AI queries/user/day | 5+ | Feature adoption |

---

## Requirements

### P0 - Must Have (MVP)

#### 1. Command Blocks
**What:** Group terminal output into collapsible, interactive blocks
**Why:** Primary UX differentiator, matches Warp's key feature
**Acceptance Criteria:**
- [ ] Each command + output is wrapped in a block
- [ ] Blocks are collapsible/expandable
- [ ] Click to copy command or output
- [ ] Visual distinction between success/failure
- [ ] Works with bash, zsh, fish

#### 2. Basic AI Panel
**What:** Side panel for AI assistance
**Why:** Core value proposition
**Acceptance Criteria:**
- [ ] Toggle with Ctrl+Space
- [ ] Chat interface for queries
- [ ] "Explain this" for selected text/blocks
- [ ] Command suggestions
- [ ] Works with at least one provider (Claude or local)

#### 3. Shell Integration
**What:** Scripts that enable block detection
**Why:** Required for command blocks to work
**Acceptance Criteria:**
- [ ] Bash integration script
- [ ] Zsh integration script
- [ ] Fish integration script
- [ ] Auto-detection of shell
- [ ] Graceful fallback if not installed

#### 4. CX Branding
**What:** Renamed from WezTerm, CX themes
**Why:** Product identity
**Acceptance Criteria:**
- [ ] All references changed from WezTerm to CX Terminal
- [ ] CX Dark and CX Light color schemes
- [ ] CX icon and desktop entry
- [ ] `cx` Lua module alias works

### P1 - Should Have (v1.1)

#### 5. Agent System
**What:** Specialized AI agents for system tasks
**Why:** Differentiator, OS integration
**Acceptance Criteria:**
- [ ] Agent API defined
- [ ] System agent (basic info, services)
- [ ] File agent (search, navigate)
- [ ] Package agent (install, update)
- [ ] Agents callable from AI panel

#### 6. Local AI Support
**What:** Run AI locally via Ollama/llama.cpp
**Why:** Privacy, offline use
**Acceptance Criteria:**
- [ ] Ollama integration
- [ ] Works offline
- [ ] Configurable model selection
- [ ] Graceful fallback if unavailable

#### 7. Modern Input
**What:** Enhanced command input area
**Why:** UX polish, Warp parity
**Acceptance Criteria:**
- [ ] Multi-line input
- [ ] Syntax highlighting
- [ ] Auto-complete for commands/paths
- [ ] History search (Ctrl+R)

### P2 - Nice to Have (v1.2+)

#### 8. Workflows
**What:** Saved command sequences
**Why:** Productivity, stickiness
**Acceptance Criteria:**
- [ ] Create workflow from history
- [ ] Run workflows with one click
- [ ] Share workflows (export/import)
- [ ] Workflow marketplace integration

#### 9. Team Features
**What:** Collaboration features
**Why:** Enterprise revenue
**Acceptance Criteria:**
- [ ] Shared workflows
- [ ] Team AI context
- [ ] Audit logging
- [ ] SSO integration

#### 10. CX Linux Deep Integration
**What:** Direct daemon communication
**Why:** Unique value prop
**Acceptance Criteria:**
- [ ] Real-time system status in terminal
- [ ] Agent actions execute via CX daemon
- [ ] Unified settings with CX Linux

---

## Technical Architecture

### Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Terminal Core | WezTerm (Rust) | Proven, GPU-accelerated, MIT licensed |
| Config | Lua | WezTerm native, user-friendly |
| AI Integration | Rust + HTTP | Direct API calls, streaming support |
| Shell Integration | Bash/Zsh/Fish scripts | Universal compatibility |
| Local AI | Ollama protocol | Standard for local LLMs |

### Key Components

```
┌─────────────────────────────────────────────────────────┐
│                     CX Terminal                          │
├──────────────────┬──────────────────┬───────────────────┤
│   Terminal Core  │   AI Module      │   Agent Module    │
│   (WezTerm)      │                  │                   │
│   - PTY          │   - Panel UI     │   - Runtime       │
│   - Rendering    │   - Providers    │   - System Agent  │
│   - Tabs/Panes   │   - Chat         │   - File Agent    │
│   - Config       │   - Streaming    │   - Package Agent │
├──────────────────┴──────────────────┴───────────────────┤
│                    Block System                          │
│   - Parser (OSC sequences)                              │
│   - Manager (lifecycle)                                 │
│   - Renderer (UI)                                       │
├─────────────────────────────────────────────────────────┤
│                  Shell Integration                       │
│   - cx.bash / cx.zsh / cx.fish                         │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

```
User types command
       │
       ▼
Shell sends OSC "block start" ──► Block Manager creates block
       │
       ▼
Command executes, output streams ──► Block captures output
       │
       ▼
Shell sends OSC "block end" ──► Block marked complete
       │
       ▼
User clicks "Explain" ──► AI Panel receives block content
       │
       ▼
AI Provider returns response ──► Panel displays, optionally executes
```

---

## Timeline & Effort

### Realistic Estimates (Claude Code assisted)

**Assumptions:**
- One Claude Code session active ~8 hrs/day
- User available for build/test cycles 2-3x/day
- No major architectural pivots mid-development

| Phase | Deliverable | Calendar Days | Claude Hours | User Hours |
|-------|-------------|---------------|--------------|------------|
| **Phase 1** | Command Blocks (functional) | 5 | 30 | 5 |
| **Phase 2** | AI Panel (basic) | 4 | 24 | 4 |
| **Phase 3** | Shell Integration (all shells) | 2 | 12 | 2 |
| **Phase 4** | Polish & Bug Fixes | 3 | 18 | 5 |
| **MVP Total** | | **14 days** | **84 hrs** | **16 hrs** |
| **Phase 5** | Agent System | 5 | 30 | 5 |
| **Phase 6** | Local AI | 3 | 18 | 3 |
| **Phase 7** | Modern Input | 4 | 24 | 4 |
| **v1.1 Total** | | **+12 days** | **+72 hrs** | **+12 hrs** |

**Total to v1.1: ~26 calendar days, ~156 Claude hours, ~28 user hours**

### Parallel Claude Sessions?

**Yes, this can speed things up.** Here's how:

| Session | Focus | Dependencies |
|---------|-------|--------------|
| **Claude 1** | Block system (Rust) | None |
| **Claude 2** | AI Panel (Rust) | None initially |
| **Claude 3** | Shell integration (Bash/Zsh/Fish) | Block parser spec |

**Speedup:**
- Sequential: 14 days to MVP
- 2 parallel: ~9 days to MVP
- 3 parallel: ~7 days to MVP

**Coordination needed:**
- Shared interface definitions (I write first)
- Merge coordination (you manage git)
- Testing integration points

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| WezTerm architecture blocks feature | Low | High | Early spike on block rendering |
| AI provider rate limits | Medium | Medium | Local AI fallback, caching |
| Shell integration compatibility | Medium | Medium | Extensive testing, fallback mode |
| Performance regression | Medium | High | Benchmark suite, profiling |
| Scope creep | High | Medium | Strict P0/P1/P2 discipline |

---

## Open Questions

1. **AI Provider Default:** Claude API, OpenAI, or local-only for MVP?
2. **Pricing Tiers:** Finalize what's free vs Pro vs Enterprise
3. **CX Linux Daemon:** Does it exist? What's the API?
4. **Icon/Branding:** Need final assets
5. **Beta Program:** Who are first users?

---

## Appendix

### Why WezTerm (Not Build from Scratch)

| Factor | Build from Scratch | Fork WezTerm |
|--------|-------------------|---------------|
| Time to MVP | 6-9 months | 2-4 weeks |
| Terminal correctness | Risk of bugs | Battle-tested |
| GPU rendering | Major effort | Done |
| Cross-platform | Major effort | Done |
| Maintenance burden | High | Shared with upstream |
| Differentiation | 100% custom | Our features on solid base |

**Decision: Fork WezTerm.** The terminal layer is commodity. Our value is in the AI/agent layer.

### Competitive Response Scenarios

**If Warp launches Linux:**
- We have OS integration they can't match
- We have local AI they don't offer
- We're already default on CX Linux

**If Apple adds AI to Terminal.app:**
- Mac-only, not our market
- Likely cloud-dependent
- Validates the market

**If GNOME adds AI to Terminal:**
- Long development cycles (years)
- We'll be established by then
- May drive awareness to category
