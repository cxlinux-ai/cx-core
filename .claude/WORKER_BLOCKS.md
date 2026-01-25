# Claude Worker: Command Blocks System

## Your Assignment
You are responsible for the **Command Blocks** feature - the core UX differentiator.

## Scope
```
wezterm-gui/src/blocks/
├── mod.rs       ✅ Done - module exports
├── block.rs     ✅ Done - Block struct
├── manager.rs   ✅ Done - BlockManager
├── parser.rs    ✅ Done - OSC sequence parser
└── renderer.rs  ⏳ YOUR TASK - Block rendering
```

## Your Tasks

### 1. Block Renderer (P0)
Create `wezterm-gui/src/blocks/renderer.rs`:
- Render block headers (command, status, duration)
- Render collapse/expand controls
- Render block borders
- Handle click events on blocks
- Integrate with WezTerm's existing render pipeline

### 2. Wire Parser into Terminal (P0)
Modify `wezterm-gui/src/termwindow/` to:
- Intercept OSC sequences starting with "777;cx;"
- Route to BlockParser
- Update BlockManager state

### 3. Wire Renderer into GUI (P0)
Modify rendering to:
- Draw block overlays on terminal output
- Show block toolbar on hover
- Handle block selection

## Key Files to Study
- `wezterm-gui/src/termwindow/render.rs` - Main rendering
- `wezterm-gui/src/termwindow/mod.rs` - Window management
- `termwiz/src/escape/osc.rs` - OSC parsing

## Interface Contract
BlockManager must expose:
```rust
pub fn start_block(&mut self, command: String, cwd: String, line: usize) -> BlockId;
pub fn end_block(&mut self, exit_code: i32, line: usize);
pub fn block_at_line(&self, line: usize) -> Option<&Block>;
pub fn visible_blocks(&self) -> impl Iterator<Item = &Block>;
```

## Success Criteria
- [ ] Blocks visually wrap command output
- [ ] Collapse/expand works
- [ ] Status indicator (success/fail) shows
- [ ] Duration displays for completed blocks
- [ ] No performance regression (benchmark)

## Do NOT Touch
- AI panel code (another worker)
- Agent system (another worker)
- Shell integration scripts (done)

## Communication
When done, create a summary in `docs/BLOCKS_STATUS.md` with:
- What's implemented
- Known issues
- Integration points for other workers
