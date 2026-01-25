# CX Terminal Architecture

## Vision
AI-native terminal for CX Linux. Warp-style UX with deep OS integration.

## Core Differentiators vs Warp

| Feature | Warp | CX Terminal |
|---------|------|-------------|
| OS Integration | None | Deep CX Linux agents |
| AI Backend | Cloud only | Local + Cloud + Fine-tuned |
| Learning | Static | Continuous from usage |
| Open Source | No | BSL (open core) |
| Linux Support | Limited | Native, first-class |
| Pricing | Subscription | Bundled with CX Linux |

---

## Command Blocks

### What They Are
Every command + output is wrapped in a collapsible, interactive block.

```
┌─────────────────────────────────────────────────┐
│ $ ls -la                                    ▼ ⋮ │
├─────────────────────────────────────────────────┤
│ total 64                                        │
│ drwxr-xr-x  12 user  staff   384 Jan 24 10:00 . │
│ drwxr-xr-x   5 user  staff   160 Jan 24 09:00 ..│
│ -rw-r--r--   1 user  staff  1024 Jan 24 10:00 f │
└─────────────────────────────────────────────────┘
```

### Block Features
- **Collapse/Expand** - Hide long output
- **Copy** - One-click copy command or output
- **Re-run** - Execute command again
- **Edit & Run** - Modify and re-execute
- **Share** - Export as snippet
- **AI Explain** - Send to AI panel for explanation
- **Pin** - Keep important blocks visible

### Implementation Strategy

```rust
// New module: wezterm-gui/src/blocks.rs

pub struct CommandBlock {
    id: BlockId,
    command: String,
    output: Vec<Line>,
    start_line: usize,
    end_line: usize,
    collapsed: bool,
    pinned: bool,
    timestamp: DateTime<Utc>,
    exit_code: Option<i32>,
    duration: Duration,
}

pub struct BlockManager {
    blocks: Vec<CommandBlock>,
    active_block: Option<BlockId>,
}
```

### Detection Strategy
1. **Shell Integration** - Inject markers via PROMPT_COMMAND/precmd
2. **OSC Sequences** - Custom escape codes for block boundaries
3. **Heuristic** - Detect prompt patterns as fallback

---

## AI Panel

### Layout
```
┌──────────────────────────────────────┬─────────────────┐
│                                      │                 │
│         Terminal Panes               │    AI Panel     │
│                                      │                 │
│  ┌────────────────────────────────┐  │  ┌───────────┐  │
│  │ Command Block 1                │  │  │ Chat      │  │
│  └────────────────────────────────┘  │  │           │  │
│  ┌────────────────────────────────┐  │  │ > explain │  │
│  │ Command Block 2                │  │  │   this    │  │
│  └────────────────────────────────┘  │  │   error   │  │
│                                      │  │           │  │
│  ┌────────────────────────────────┐  │  ├───────────┤  │
│  │ Command Block 3 (active)       │  │  │ Suggested │  │
│  │ $ cargo build                  │  │  │ Commands  │  │
│  │ error[E0432]: unresolved...    │  │  │           │  │
│  └────────────────────────────────┘  │  │ fix:      │  │
│                                      │  │ cargo add │  │
│  ┌────────────────────────────────┐  │  │ tokio     │  │
│  │ Input Area                     │  │  │           │  │
│  │ $ _                            │  │  └───────────┘  │
│  └────────────────────────────────┘  │                 │
└──────────────────────────────────────┴─────────────────┘
```

### AI Panel Modes
1. **Chat** - Conversational interface
2. **Explain** - Auto-explain errors/output
3. **Suggest** - Command suggestions
4. **Agent** - CX Linux system agents
5. **History** - AI interaction history

### Keybindings
- `Ctrl+Space` - Toggle AI panel
- `Ctrl+E` - Explain selected block
- `Ctrl+G` - Generate command from description
- `Ctrl+/` - AI command search

---

## Agent API

### CX Linux Integration
```rust
pub trait CXAgent {
    fn name(&self) -> &str;
    fn description(&self) -> &str;
    fn capabilities(&self) -> Vec<Capability>;

    async fn execute(&self, intent: Intent) -> Result<Response>;
    async fn stream(&self, intent: Intent) -> impl Stream<Item = ResponseChunk>;
}

pub enum Capability {
    FileSystem,
    Process,
    Network,
    Package,
    System,
    Custom(String),
}
```

### Built-in Agents
1. **System Agent** - OS info, resources, services
2. **File Agent** - Navigation, search, operations
3. **Package Agent** - Install, update, remove
4. **Network Agent** - Connections, firewall, DNS
5. **Process Agent** - Monitor, kill, prioritize
6. **Git Agent** - Repo operations, history
7. **Docker Agent** - Containers, images, compose

### Agent Communication
```
Terminal <-> Agent Runtime <-> CX Linux Daemon
    │              │                  │
    │   WebSocket  │    Unix Socket   │
    │              │                  │
    ▼              ▼                  ▼
  UI Events    Intent Router    System Calls
```

---

## Modern Input Editor

### Features
- Multi-line editing
- Syntax highlighting (shell, common languages)
- Auto-complete (commands, paths, git branches)
- History search (Ctrl+R)
- AI-powered suggestions
- Snippet expansion

### Implementation
Extend Wezterm's input handling:
```rust
pub struct ModernInput {
    buffer: String,
    cursor: Position,
    mode: InputMode,
    completions: Vec<Completion>,
    ai_suggestions: Vec<Suggestion>,
}

pub enum InputMode {
    Normal,
    MultiLine,
    Search,
    AIPrompt,
}
```

---

## Theming System

### CX Theme Format
```lua
-- ~/.config/cx/themes/custom.lua
return {
    name = "My Theme",
    colors = {
        background = "#0d0e14",
        foreground = "#c0caf5",
        cursor = "#7aa2f7",
        selection = "#33467c",

        -- Block colors
        block_header = "#1a1b26",
        block_border = "#414868",
        block_success = "#9ece6a",
        block_error = "#f7768e",

        -- AI panel
        ai_background = "#13141a",
        ai_user = "#7aa2f7",
        ai_assistant = "#bb9af7",
    },
    fonts = {
        main = "JetBrains Mono",
        ui = "Inter",
    },
}
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Shell integration markers (bash/zsh/fish)
- [ ] Block detection and boundaries
- [ ] Basic block rendering
- [ ] Collapse/expand functionality

### Phase 2: Block Features (Week 2-3)
- [ ] Block toolbar (copy, rerun, share)
- [ ] Block search and filtering
- [ ] Pinned blocks
- [ ] Block export

### Phase 3: AI Panel (Week 3-4)
- [ ] Panel layout and toggle
- [ ] Chat interface
- [ ] LLM integration (local + cloud)
- [ ] Explain command integration

### Phase 4: Agent System (Week 4-5)
- [ ] Agent trait and API
- [ ] Built-in agents (system, file, package)
- [ ] CX Linux daemon communication
- [ ] Agent UI in terminal

### Phase 5: Polish (Week 5-6)
- [ ] Modern input editor
- [ ] Advanced theming
- [ ] Performance optimization
- [ ] Documentation

---

## File Structure

```
cx-terminal/
├── wezterm-gui/src/
│   ├── blocks/           # Command blocks system
│   │   ├── mod.rs
│   │   ├── block.rs      # Block struct
│   │   ├── manager.rs    # Block lifecycle
│   │   ├── renderer.rs   # Block rendering
│   │   └── toolbar.rs    # Block actions
│   ├── ai/               # AI panel
│   │   ├── mod.rs
│   │   ├── panel.rs      # Panel UI
│   │   ├── chat.rs       # Chat interface
│   │   ├── provider.rs   # LLM providers
│   │   └── suggest.rs    # Suggestions
│   ├── agents/           # CX Linux agents
│   │   ├── mod.rs
│   │   ├── runtime.rs    # Agent runtime
│   │   ├── system.rs     # System agent
│   │   ├── file.rs       # File agent
│   │   └── package.rs    # Package agent
│   └── input/            # Modern input
│       ├── mod.rs
│       ├── editor.rs     # Multi-line editor
│       ├── complete.rs   # Completions
│       └── highlight.rs  # Syntax highlighting
└── shell-integration/    # Shell scripts
    ├── cx.bash
    ├── cx.zsh
    └── cx.fish
```

---

## Competitive Analysis

### vs Warp
- **Win**: Open source, Linux-native, OS integration, local AI
- **Lose**: Established brand, team size, funding

### vs Kitty
- **Win**: AI features, modern UX, command blocks
- **Match**: Performance, configurability

### vs Alacritty
- **Win**: Features, AI, blocks
- **Lose**: Pure simplicity crowd

### vs iTerm2
- **Win**: Cross-platform, AI, modern
- **Lose**: macOS ecosystem lock-in users

---

## Success Metrics

1. **Performance**: < 16ms frame time
2. **Startup**: < 200ms cold start
3. **Memory**: < 100MB base usage
4. **AI Latency**: < 500ms for suggestions
5. **Block Detection**: > 99% accuracy
