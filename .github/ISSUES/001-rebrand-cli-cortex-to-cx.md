# Issue: Rebrand CLI from `cortex` to `cx`

**Priority:** Critical
**Labels:** branding, breaking-change
**Milestone:** v0.2.0 Identity Reset

## Summary

Rename the CLI command from `cortex` to `cx` for a cleaner, more memorable brand identity.

## Rationale

- `cx` is shorter, faster to type
- Avoids confusion with other "Cortex" products in the market
- Aligns with domain names (cxlinux.com, cxlinux.ai)
- Single syllable = better recall

## Changes Required

### 1. Binary/Entry Point
- [ ] Rename main binary from `cortex` to `cx`
- [ ] Update `setup.py` / `pyproject.toml` entry points
- [ ] Update Cargo.toml binary name (Rust components)

### 2. Code References
- [ ] `cortex/` directory → `cx/`
- [ ] All `import cortex` → `import cx`
- [ ] CLI help text updates
- [ ] Error messages referencing "cortex"

### 3. Documentation
- [ ] README.md examples
- [ ] All docs/*.md files
- [ ] Shell integration scripts

### 4. User Migration
- [ ] Add deprecation warning if user runs `cortex` (symlink to `cx`)
- [ ] Update install instructions

## Example

**Before:**
```bash
cortex ask "Why is nginx failing?"
cortex install docker
```

**After:**
```bash
cx ask "Why is nginx failing?"
cx install docker
```

## Acceptance Criteria

- [ ] `cx` command works as primary entry point
- [ ] All documentation updated
- [ ] No references to "cortex" in user-facing strings (except deprecation notice)
- [ ] Tests pass with new binary name
