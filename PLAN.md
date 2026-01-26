# CX Terminal - AI Intelligence Plan

## Goal
Make `cx ask` smart enough to use the primitives we built (`cx new`, `cx save`, shell blocks).

## Current State
- `cx ask` works with Claude/Ollama for general questions
- `cx new` creates projects from templates
- `cx save/restore` manages snapshots
- Pattern matching fallback exists but is basic

## What Needs to Change

### Phase 1: Smart Command Detection
Make `cx ask` recognize when to use CX commands instead of generic responses.

**Input → Output mapping:**
- "create a python project" → `cx new python <name>`
- "set up react app" → `cx new react <name>`
- "save my work" → `cx save <smart-name>`
- "list my snapshots" → `cx snapshots -l`
- "restore my project" → `cx restore <name>`
- "install docker" → pattern match + execute
- "how to install node" → show command

### Phase 2: Context Awareness
- Detect current directory name for smart naming
- Check if in a git repo
- Detect existing project type (package.json, pyproject.toml, etc.)

### Phase 3: Execution Flow
1. Parse user query
2. Match against known CX commands
3. If match: generate command, ask for confirmation (unless --do -y)
4. If no match: fall back to AI provider
5. Execute and show results

## Files to Modify

1. `wezterm/src/cli/ask.rs` - Main AI logic (refactor, keep <300 lines)
2. `wezterm/src/cli/ask_patterns.rs` - NEW: Pattern matching logic
3. `wezterm/src/cli/ask_context.rs` - NEW: Context detection

## Implementation Steps

- [x] Create `ask_patterns.rs` - CX command pattern matching
- [x] Create `ask_context.rs` - Directory/project context detection
- [x] Refactor `ask.rs` - Use new modules, cleaner code
- [x] Build and test
- [x] Verify all commands work

## Completed (2026-01-26)
Smart command detection now works:
- `cx ask "create a python project called my-app"` → detects & generates `cx new python my-app`
- `cx ask "save my work"` → detects & generates `cx save <name>`
- `cx ask "list snapshots"` → detects & generates `cx snapshots -l`
- `cx ask -d -y "..."` → auto-executes the detected command

Note: Flags must come BEFORE the query text due to `trailing_var_arg` parsing.

## Success Criteria
```bash
cx ask "create a python ml project" --do
# → Detects intent, runs: cx new python ml-project

cx ask "save my work" --do
# → Detects intent, runs: cx save <current-dir-name>

cx ask "how do I install docker"
# → Returns: curl -fsSL https://get.docker.com | sh
```
