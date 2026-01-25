# Command Blocks System Status

## Overview

The Command Blocks system implements Warp-style command grouping for CX Terminal. Commands and their outputs are wrapped in collapsible, interactive blocks with status indicators and quick actions.

## Implementation Status

### Completed Components

#### 1. Block Data Structure (`wezterm-gui/src/blocks/block.rs`)
- [x] `BlockId` - Unique identifier with atomic counter
- [x] `BlockState` - Running, Success, Failed, Interrupted states
- [x] `Block` struct with:
  - Command text and working directory
  - Start/end line tracking
  - Timestamps and duration
  - Collapse and pin states
  - Notes and tags
- [x] `BlockAction` enum for user interactions

#### 2. Block Manager (`wezterm-gui/src/blocks/manager.rs`)
- [x] Block lifecycle management (start, end, interrupt)
- [x] Block lookup by ID and line number
- [x] Selection management
- [x] Action execution with `BlockActionResult`
- [x] Search functionality
- [x] Automatic cleanup of old blocks
- [x] Statistics tracking

#### 3. OSC Parser (`wezterm-gui/src/blocks/parser.rs`)
- [x] CX sequence parsing (`777;cx;*`)
- [x] Block start/end markers
- [x] Prompt markers
- [x] CWD change tracking
- [x] AI request parsing
- [x] Agent request parsing
- [x] Feature flags

#### 4. Block Renderer (`wezterm-gui/src/blocks/renderer.rs`)
- [x] `BlockRenderConfig` with customizable colors
- [x] `BlockLayout` computation
- [x] Hit testing for click interactions
- [x] Hover state management
- [x] Block header rendering info
- [x] Status indicator colors

### Completed (Integration)

#### 5. Terminal Integration
- [x] Alert types for CX sequences (`Alert::CXBlockStart`, etc.)
- [x] OSC sequence interception in performer
- [x] TermWindow block state (`block_managers`, `block_renderer`, `pane_cwd`)
- [x] Notification handling for block events
- [x] Cursor line tracking for block boundaries

### In Progress

#### 6. Visual Rendering
- [ ] Block header overlay rendering in pane.rs
- [ ] Collapse/expand animations
- [ ] Block border drawing
- [ ] Hover effects
- [ ] Selection highlighting

### Not Started

#### 7. Mouse Interaction
- [ ] Click handling for collapse toggle
- [ ] Click handling for action buttons
- [ ] Right-click context menu
- [ ] Drag to resize

#### 8. Keyboard Interaction
- [ ] Navigate between blocks
- [ ] Collapse/expand with keyboard
- [ ] Copy block content
- [ ] Search blocks

## Architecture

```
Shell                    Terminal                     GUI
  |                          |                          |
  | printf OSC 777;cx;...    |                          |
  |------------------------->|                          |
  |                          | parse_cx_sequence()      |
  |                          |------------------------->|
  |                          |                          | Alert::CXBlockStart
  |                          |                          | block_managers.start_block()
  |                          |                          |
  | (command output)         |                          |
  |------------------------->|------------------------->|
  |                          |                          | (normal rendering)
  |                          |                          |
  | printf OSC 777;cx;end    |                          |
  |------------------------->|                          |
  |                          | parse_cx_sequence()      |
  |                          |------------------------->|
  |                          |                          | Alert::CXBlockEnd
  |                          |                          | block_managers.end_block()
```

## OSC Sequence Format

All CX sequences use the format: `OSC 777;cx;TYPE;PARAMS ST`

### Block Start
```
OSC 777;cx;block;start;cmd=<command>;time=<timestamp> ST
```

### Block End
```
OSC 777;cx;block;end;exit=<code>;time=<timestamp> ST
```

### CWD Change
```
OSC 777;cx;cwd;path=<directory> ST
```

### AI Request
```
OSC 777;cx;ai;explain;text=<text> ST
OSC 777;cx;ai;suggest;query=<query> ST
```

### Agent Request
```
OSC 777;cx;agent;name=<agent>;command=<cmd> ST
```

## Integration Points

### For Other Workers

#### AI Panel Worker
- Handle `Alert::CXAIExplain` and `Alert::CXAISuggest`
- Can access block content via `BlockManager::get()`
- Can trigger block actions via `BlockAction::Explain`

#### Agent System Worker
- Handle `Alert::CXAgentRequest`
- Block output can be captured and displayed in blocks

### Shell Integration
The shell integration script (`cx.sh`) should emit:
1. `block;start` before command execution
2. `block;end` after command completion
3. `cwd;path` on directory changes

## Performance Considerations

1. Block layouts are computed on each paint cycle - consider caching
2. Hit testing uses linear search - consider spatial indexing for many blocks
3. Old blocks are automatically pruned (default: 1000 max)
4. Collapsed blocks skip content rendering

## Testing

Unit tests exist for:
- `block.rs`: Block creation, completion, state transitions
- `manager.rs`: Lifecycle, search, action execution
- `parser.rs`: OSC sequence parsing
- `renderer.rs`: Hit testing, layout computation

## Known Issues

1. **Line Tracking**: Block start/end lines may drift if terminal is scrolled during execution
2. **Multi-pane**: Each pane has its own BlockManager, but renderer is shared
3. **No Persistence**: Blocks are lost when terminal closes

## Next Steps

1. Complete visual rendering integration in `render/pane.rs`
2. Add mouse click handlers in `mouseevent.rs`
3. Add keyboard navigation
4. Implement block content extraction for copy/share
5. Add configuration options to `cx.lua`
