# Issue: Make `cx` CLI Work Standalone in Any Terminal

**Priority:** High
**Labels:** feature, architecture
**Milestone:** v0.2.0 Identity Reset

## Summary

Ensure the `cx` CLI works fully in any terminal emulator (iTerm, GNOME Terminal, Konsole, etc.) without requiring the CX Terminal app.

## Rationale

- Removes WezTerm dependency for 90% of use cases
- Expands addressable market to all Linux/macOS users
- CLI becomes the growth engine, Terminal becomes premium upsell
- Easier adoption: `pip install cx-linux` vs. downloading an app

## Current State

Some features may be tightly coupled to the WezTerm terminal:
- AI sidebar (Terminal-only - that's fine)
- Command blocks visualization
- Voice capture integration

## Target State

| Feature | Any Terminal | CX Terminal |
|---------|--------------|-------------|
| `cx ask "..."` | Yes | Yes |
| `cx install <pkg>` | Yes | Yes |
| `cx hire <agent>` | Yes | Yes |
| `cx fire <agent>` | Yes | Yes |
| AI Sidebar | No | Yes (Pro) |
| Voice Commands | No | Yes (Pro) |
| Visual Command Blocks | No | Yes (Pro) |
| Workflow Learning | Basic | Advanced |

## Changes Required

### 1. Decouple CLI from Terminal
- [ ] Audit CLI for terminal-specific dependencies
- [ ] Create fallback paths for non-CX-Terminal environments
- [ ] Graceful degradation for Pro features

### 2. Packaging
- [ ] `pip install cx-linux` works standalone
- [ ] `.deb` package for apt installation
- [ ] Homebrew formula for macOS

### 3. Detection Logic
```python
def is_cx_terminal():
    """Detect if running inside CX Terminal"""
    return os.environ.get('CX_TERMINAL') == '1'

def get_feature_level():
    if is_cx_terminal() and has_pro_license():
        return 'pro'
    return 'free'
```

## Acceptance Criteria

- [ ] `pip install cx-linux && cx ask "hello"` works in bash/zsh
- [ ] All core AI features work without CX Terminal
- [ ] Pro features gracefully prompt for upgrade when unavailable
- [ ] No crashes or errors in non-CX-Terminal environments
