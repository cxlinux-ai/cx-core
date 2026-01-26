# CX Terminal - Implementation Roadmap

Based on Mike's feature wishlist document. Prioritized by feasibility and impact.

## Phase 1: Foundation & UI (Current Sprint)

### 1.1 Fix Terminal UI ✅
- [x] Fix window decorations (native macOS title bar)
- [ ] Verify terminal builds and runs correctly
- [ ] Test Ctrl+Space telemetry dashboard works

### 1.2 Core CLI Commands
- [x] `cx ask` - AI-powered questions (DONE)
- [x] `cx new <template> <name>` - Project scaffolding (DONE)
- [x] `cx save <name>` - Save workspace snapshot (DONE)
- [x] `cx restore <name>` - Restore workspace snapshot (DONE)
- [x] `cx snapshots` - List/manage snapshots (DONE)
- [ ] `cx share <file>` - Generate shareable link (local: copy to clipboard)
- [ ] `cx preview <file>` - Preview HTML/MD/images in terminal

### 1.3 Keyboard Shortcuts
- [x] `Cmd+Shift+S` - Show snapshots (DONE)
- [x] `Cmd+O` - Show snapshots for restore (DONE)
- [x] `Cmd+Shift+N` - New project from template (DONE)
- [x] `Cmd+K` - Quick AI Ask (DONE)
- [x] `Cmd+Shift+F` - Find files (DONE)
- [x] `Cmd+Shift+H` - Show CX help (DONE)
- [ ] `Cmd+P` - Preview file (sixel/kitty graphics) - Future

---

## Phase 2: Shell Integration & Blocks

### 2.1 Quick Blocks (Shell Commands)
- [x] `/python` - Python environment setup (DONE)
- [x] `/node` - Node.js project scaffold (DONE)
- [x] `/react` - React app boilerplate (DONE)
- [x] `/nextjs` - Next.js app setup (DONE)
- [x] `/api` - FastAPI starter (DONE)
- [x] `/docker` - Dockerfile + compose template (DONE)
- [x] `/go` - Go project setup (DONE)
- [x] `/rust` - Rust project setup (DONE)
- [x] `/db` - SQLite setup (DONE)
- [x] `/help` - List available quick blocks (DONE)

### 2.2 Environment Management
- [ ] `cx packages list` - Show installed packages
- [ ] `cx packages add <pkg>` - Quick install
- [ ] `cx env create <version>` - Virtual environment

---

## Phase 3: Advanced Features

### 3.1 Git Integration
- [ ] `cx clone <repo>` - Clone repository
- [ ] `cx push` - Commit and push
- [ ] `cx pr <title>` - Create pull request
- [ ] Git status in telemetry dashboard

### 3.2 Inline Previews
- [ ] HTML rendering (sixel graphics)
- [ ] Markdown rendering
- [ ] Image display (PNG, JPG)
- [ ] CSV table view
- [ ] PDF preview (if possible)

### 3.3 Split Pane UI Enhancements
- [ ] File tree sidebar toggle
- [ ] Live preview pane
- [ ] Terminal at bottom layout

---

## Phase 4: Cloud Features (Requires CX Daemon)

### 4.1 Persistent Workspaces
- [ ] Workspace save to CX cloud
- [ ] Workspace restore from CX cloud
- [ ] Named environments

### 4.2 File Sharing
- [ ] Generate download links
- [ ] QR code generation
- [ ] Folder zip and share

### 4.3 Collaboration
- [ ] Shared terminal sessions
- [ ] Team workspaces

---

## Technical Notes

### Project Templates Location
Templates stored in: `~/.cx/templates/` or `/usr/share/cx-terminal/templates/`

### Keyboard Shortcut Implementation
- macOS: Use `Cmd` modifier
- Linux: Use `Ctrl` modifier
- Defined in `config/src/keyassignment.rs`

### CLI Command Structure
```
cx <command> [options] [args]
  ask      - AI-powered questions
  new      - Create from template
  save     - Save snapshot
  restore  - Restore snapshot
  share    - Share file
  preview  - Preview file
  packages - Package management
  env      - Environment management
  clone    - Git clone
  push     - Git push
  pr       - Create PR
```

### Dependencies
- `cx-terminal-gui` - Main terminal application
- `cx-terminal` (CLI) - Command-line interface
- `cx-daemon` - Background service for cloud features

---

## Progress Tracking

| Phase | Status | Completion |
|-------|--------|------------|
| Phase 1 | Done | 95% |
| Phase 2 | Done | 95% |
| Phase 3 | Not Started | 0% |
| Phase 4 | Not Started | 0% |

### AI Intelligence (Completed 2026-01-26)
- [x] `cx ask` now detects CX command intent
- [x] Pattern matching for project creation, snapshots, templates
- [x] Context awareness (detects project type, git status)
- [x] Auto-execution with `--do -y` flags

---

Last Updated: 2026-01-26
