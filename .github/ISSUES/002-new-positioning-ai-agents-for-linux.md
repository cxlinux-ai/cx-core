# Issue: New Positioning - "AI Agents for Linux"

**Priority:** Critical
**Labels:** branding, documentation
**Milestone:** v0.2.0 Identity Reset

## Summary

Pivot messaging from "AI Terminal" to "AI Agents for Linux Administration" to differentiate from the WezTerm foundation and emphasize our unique value.

## The Problem

Current positioning:
> "CX AI Terminal - The AI-Native Terminal"

This ties our identity to the terminal (which is a WezTerm fork) rather than our actual innovation (the AI agent layer).

## New Positioning

**Primary Tagline:**
> "CX Linux - AI Agents for Linux Administration"

**Secondary Messages:**
- "The AI Layer for Linux"
- "Works in any terminal. Or use our AI-native terminal."
- "Agentic system administration for Debian, Ubuntu, and beyond."

## Value Hierarchy (New)

1. **AI Agents** (our core innovation)
2. **CLI that works anywhere** (accessibility)
3. **Premium Terminal** (optional upgrade)
4. **Full Distro** (complete experience)

## Changes Required

### README.md
- [ ] New hero section with agent-first messaging
- [ ] De-emphasize terminal, emphasize CLI
- [ ] Add "Works in any terminal" badge

### Taglines to Update
- [ ] GitHub repo description
- [ ] Package descriptions (PyPI, apt)
- [ ] Discord server description
- [ ] Website meta tags

### Documentation Structure
- [ ] Lead with CLI usage, not terminal installation
- [ ] "Getting Started" = `pip install cx-linux && cx ask "hello"`
- [ ] Terminal becomes "Advanced" or "Pro Features" section

## Acceptance Criteria

- [ ] All user-facing copy reflects agent-first positioning
- [ ] Terminal is presented as optional/premium, not core
- [ ] New users can use CX without downloading the terminal
