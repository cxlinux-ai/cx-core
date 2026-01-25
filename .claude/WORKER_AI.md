# Claude Worker: AI Panel System

## Your Assignment
You are responsible for the **AI Panel** - the intelligence layer.

## Scope
```
wezterm-gui/src/ai/
├── mod.rs       ✅ Done - module exports, config
├── panel.rs     ✅ Done - AIPanel state
├── chat.rs      ✅ Done - ChatHistory, ChatMessage
├── provider.rs  ✅ Done - Provider trait, formats
├── claude.rs    ⏳ YOUR TASK - Claude API client
├── ollama.rs    ⏳ YOUR TASK - Ollama client
└── widget.rs    ⏳ YOUR TASK - Panel UI rendering
```

## Your Tasks

### 1. Claude API Client (P0)
Create `wezterm-gui/src/ai/claude.rs`:
- Implement AIProvider trait
- HTTP client for Anthropic API
- Streaming response support
- Error handling (rate limits, auth)

### 2. Ollama Client (P1)
Create `wezterm-gui/src/ai/ollama.rs`:
- Implement AIProvider trait
- HTTP client for local Ollama
- Model listing
- Fallback when cloud unavailable

### 3. Panel Widget (P0)
Create `wezterm-gui/src/ai/widget.rs`:
- Render AI panel (right side of terminal)
- Chat message display
- Input field
- Loading/streaming indicator
- Toggle visibility (Ctrl+Space)

### 4. Wire into GUI (P0)
Modify `wezterm-gui/src/termwindow/`:
- Add AI panel to window layout
- Handle Ctrl+Space keybinding
- Route "Explain" actions from blocks to panel

## Key Files to Study
- `wezterm-gui/src/termwindow/mod.rs` - Window management
- `wezterm-gui/src/overlay/` - How overlays work
- `config/src/keyassignment.rs` - Key bindings

## Interface Contract
AIPanel must expose:
```rust
pub fn toggle(&mut self);
pub fn is_visible(&self) -> bool;
pub fn width(&self, total_width: u32) -> u32;
pub fn submit(&mut self) -> Option<AIAction>;
pub fn append_response(&mut self, chunk: &str);
pub fn complete_response(&mut self);
pub fn explain(&mut self, text: String) -> AIAction;
```

## Success Criteria
- [ ] Panel toggles with Ctrl+Space
- [ ] Can send message and receive response
- [ ] Streaming responses display incrementally
- [ ] "Explain" from block works
- [ ] Claude API integration works
- [ ] Ollama fallback works

## Do NOT Touch
- Block system (another worker)
- Agent system (another worker)
- Shell integration scripts (done)

## Configuration
AI config in Lua:
```lua
config.ai = {
  enabled = true,
  provider = "claude",  -- or "ollama", "openai"
  api_key = "...",      -- for cloud providers
  model = "claude-3-5-sonnet-20241022",
}
```

## Communication
When done, create a summary in `docs/AI_STATUS.md` with:
- What's implemented
- API integration details
- Known issues
- Integration points for other workers
