# CX Terminal Key Bindings Reference

## Modifier Keys

| Modifier | macOS | Linux/Windows |
|----------|-------|---------------|
| `SUPER`, `CMD`, `WIN` | Command | Windows/Super |
| `CTRL` | Control | Control |
| `SHIFT` | Shift | Shift |
| `ALT`, `OPT`, `META` | Option | Alt |
| `LEADER` | User-defined leader key | User-defined leader key |

Combine modifiers with `|`: `"CTRL|SHIFT"`, `"CMD|ALT"`

## Default Key Bindings

### General

| Action | macOS | Linux/Windows |
|--------|-------|---------------|
| Copy | `CMD+C` | `CTRL+SHIFT+C` |
| Paste | `CMD+V` | `CTRL+SHIFT+V` |
| New Tab | `CMD+T` | `CTRL+SHIFT+T` |
| Close Tab | `CMD+W` | `CTRL+SHIFT+W` |
| New Window | `CMD+N` | `CTRL+SHIFT+N` |
| Close Window | `CMD+SHIFT+W` | `ALT+F4` |
| Reload Config | `CMD+R` | `CTRL+SHIFT+R` |
| Show Debug Overlay | `CTRL+SHIFT+L` | `CTRL+SHIFT+L` |
| Search | `CMD+F` | `CTRL+SHIFT+F` |

### Tabs

| Action | macOS | Linux/Windows |
|--------|-------|---------------|
| Next Tab | `CMD+SHIFT+]` | `CTRL+TAB` |
| Previous Tab | `CMD+SHIFT+[` | `CTRL+SHIFT+TAB` |
| Tab 1-9 | `CMD+1-9` | `ALT+1-9` |
| Move Tab Right | `CMD+SHIFT+PageDown` | `CTRL+SHIFT+PageDown` |
| Move Tab Left | `CMD+SHIFT+PageUp` | `CTRL+SHIFT+PageUp` |

### Panes

| Action | macOS | Linux/Windows |
|--------|-------|---------------|
| Split Horizontal | `CMD+SHIFT+D` | `CTRL+SHIFT+D` |
| Split Vertical | `CMD+SHIFT+E` | `CTRL+SHIFT+E` |
| Close Pane | `CMD+W` | `CTRL+SHIFT+W` |
| Navigate Left | `CMD+ALT+Left` | `ALT+Left` |
| Navigate Right | `CMD+ALT+Right` | `ALT+Right` |
| Navigate Up | `CMD+ALT+Up` | `ALT+Up` |
| Navigate Down | `CMD+ALT+Down` | `ALT+Down` |
| Zoom Toggle | `CMD+SHIFT+Z` | `CTRL+SHIFT+Z` |

### Scrolling

| Action | macOS | Linux/Windows |
|--------|-------|---------------|
| Scroll Up | `PageUp` | `SHIFT+PageUp` |
| Scroll Down | `PageDown` | `SHIFT+PageDown` |
| Scroll to Top | `CMD+Home` | `CTRL+SHIFT+Home` |
| Scroll to Bottom | `CMD+End` | `CTRL+SHIFT+End` |

### Font Size

| Action | macOS | Linux/Windows |
|--------|-------|---------------|
| Increase | `CMD++` | `CTRL++` |
| Decrease | `CMD+-` | `CTRL+-` |
| Reset | `CMD+0` | `CTRL+0` |

## Leader Key Mode

The leader key provides tmux-like keybindings. Default: `CTRL+A`

Configure the leader key:
```lua
config.leader = { key = "a", mods = "CTRL", timeout_milliseconds = 1000 }
```

### Recommended Leader Bindings

```lua
config.keys = {
    -- Pane splits
    { key = "d", mods = "LEADER", action = cx.action.SplitHorizontal { domain = "CurrentPaneDomain" } },
    { key = "e", mods = "LEADER", action = cx.action.SplitVertical { domain = "CurrentPaneDomain" } },

    -- Pane navigation (vim-style)
    { key = "h", mods = "LEADER", action = cx.action.ActivatePaneDirection "Left" },
    { key = "j", mods = "LEADER", action = cx.action.ActivatePaneDirection "Down" },
    { key = "k", mods = "LEADER", action = cx.action.ActivatePaneDirection "Up" },
    { key = "l", mods = "LEADER", action = cx.action.ActivatePaneDirection "Right" },

    -- Pane resize
    { key = "H", mods = "LEADER|SHIFT", action = cx.action.AdjustPaneSize { "Left", 5 } },
    { key = "J", mods = "LEADER|SHIFT", action = cx.action.AdjustPaneSize { "Down", 5 } },
    { key = "K", mods = "LEADER|SHIFT", action = cx.action.AdjustPaneSize { "Up", 5 } },
    { key = "L", mods = "LEADER|SHIFT", action = cx.action.AdjustPaneSize { "Right", 5 } },

    -- Close pane
    { key = "x", mods = "LEADER", action = cx.action.CloseCurrentPane { confirm = true } },

    -- Tabs
    { key = "c", mods = "LEADER", action = cx.action.SpawnTab "CurrentPaneDomain" },
    { key = "n", mods = "LEADER", action = cx.action.ActivateTabRelative(1) },
    { key = "p", mods = "LEADER", action = cx.action.ActivateTabRelative(-1) },

    -- Tab by number
    { key = "1", mods = "LEADER", action = cx.action.ActivateTab(0) },
    { key = "2", mods = "LEADER", action = cx.action.ActivateTab(1) },
    { key = "3", mods = "LEADER", action = cx.action.ActivateTab(2) },
    { key = "4", mods = "LEADER", action = cx.action.ActivateTab(3) },
    { key = "5", mods = "LEADER", action = cx.action.ActivateTab(4) },

    -- Copy mode
    { key = "[", mods = "LEADER", action = cx.action.ActivateCopyMode },

    -- Quick select
    { key = "f", mods = "LEADER", action = cx.action.QuickSelect },

    -- Search
    { key = "/", mods = "LEADER", action = cx.action.Search "CurrentSelectionOrEmptyString" },

    -- Zoom
    { key = "z", mods = "LEADER", action = cx.action.TogglePaneZoomState },

    -- Launcher
    { key = "space", mods = "LEADER", action = cx.action.ShowLauncher },
}
```

## Copy Mode

Enter copy mode with `CTRL+SHIFT+X` or `LEADER+[`

### Copy Mode Navigation

| Key | Action |
|-----|--------|
| `h`, `Left` | Move left |
| `j`, `Down` | Move down |
| `k`, `Up` | Move up |
| `l`, `Right` | Move right |
| `w` | Forward word |
| `b` | Backward word |
| `0`, `Home` | Start of line |
| `$`, `End` | End of line |
| `g` | Top of scrollback |
| `G` | Bottom of scrollback |
| `CTRL+U` | Page up |
| `CTRL+D` | Page down |

### Copy Mode Selection

| Key | Action |
|-----|--------|
| `v` | Start selection |
| `V` | Select line |
| `CTRL+V` | Block selection |
| `y` | Copy selection |
| `Escape`, `q` | Cancel |

## Quick Select Mode

Enter with `CTRL+SHIFT+Space` or `LEADER+f`

Highlights URLs, paths, hashes, and other patterns. Press the letter to copy.

### Custom Patterns
```lua
config.quick_select_patterns = {
    "[0-9a-f]{7,40}",  -- Git hashes
    "\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b",  -- IPs
}
```

## Search Mode

Enter with `CTRL+SHIFT+F` or `LEADER+/`

| Key | Action |
|-----|--------|
| `Enter` | Find next |
| `SHIFT+Enter` | Find previous |
| `Escape` | Cancel |
| `CTRL+R` | Toggle regex mode |
| `CTRL+U` | Clear search |

## Key Assignment Actions

### Available Actions

```lua
-- Navigation
cx.action.ActivatePaneDirection "Left"
cx.action.ActivatePaneDirection "Right"
cx.action.ActivatePaneDirection "Up"
cx.action.ActivatePaneDirection "Down"
cx.action.ActivateTabRelative(1)
cx.action.ActivateTabRelative(-1)
cx.action.ActivateTab(0)

-- Pane Management
cx.action.SplitHorizontal { domain = "CurrentPaneDomain" }
cx.action.SplitVertical { domain = "CurrentPaneDomain" }
cx.action.CloseCurrentPane { confirm = true }
cx.action.AdjustPaneSize { "Left", 5 }
cx.action.TogglePaneZoomState

-- Tab Management
cx.action.SpawnTab "CurrentPaneDomain"
cx.action.CloseCurrentTab { confirm = true }
cx.action.MoveTab(1)
cx.action.MoveTabRelative(1)

-- Clipboard
cx.action.CopyTo "Clipboard"
cx.action.PasteFrom "Clipboard"
cx.action.CopyTo "PrimarySelection"
cx.action.PasteFrom "PrimarySelection"

-- Modes
cx.action.ActivateCopyMode
cx.action.QuickSelect
cx.action.Search "CurrentSelectionOrEmptyString"

-- Font
cx.action.IncreaseFontSize
cx.action.DecreaseFontSize
cx.action.ResetFontSize

-- Misc
cx.action.ShowLauncher
cx.action.ShowDebugOverlay
cx.action.ReloadConfiguration
cx.action.Nop  -- Do nothing
cx.action.DisableDefaultAssignment
cx.action.ScrollByPage(1)
cx.action.ScrollByPage(-1)
cx.action.ScrollToPrompt(-1)
cx.action.ScrollToPrompt(1)
```

### Conditional Actions

```lua
{
    key = "w",
    mods = "CMD",
    action = cx.action_callback(function(window, pane)
        if pane:get_cursor_position().is_active then
            window:perform_action(cx.action.CloseCurrentPane { confirm = true }, pane)
        else
            window:perform_action(cx.action.CloseCurrentTab { confirm = true }, pane)
        end
    end),
}
```

## Disable Default Bindings

```lua
config.keys = {
    {
        key = "m",
        mods = "CMD",
        action = cx.action.DisableDefaultAssignment,
    },
}
```

## Clear All Defaults

```lua
config.disable_default_key_bindings = true
```

## Mouse Bindings

```lua
config.mouse_bindings = {
    -- Right-click paste
    {
        event = { Down = { streak = 1, button = "Right" } },
        mods = "NONE",
        action = cx.action.PasteFrom "Clipboard",
    },
    -- Cmd-click open link
    {
        event = { Up = { streak = 1, button = "Left" } },
        mods = "CMD",
        action = cx.action.OpenLinkAtMouseCursor,
    },
    -- Triple-click select line
    {
        event = { Down = { streak = 3, button = "Left" } },
        mods = "NONE",
        action = cx.action.SelectTextAtMouseCursor "Line",
    },
}
```

## CX-Specific Bindings (Future)

```lua
-- AI Panel (planned)
-- { key = "a", mods = "CTRL|SHIFT", action = cx.action.ToggleAIPanel },

-- Command Block Navigation (planned)
-- { key = "k", mods = "CTRL|SHIFT", action = cx.action.ScrollToPrompt(-1) },
-- { key = "j", mods = "CTRL|SHIFT", action = cx.action.ScrollToPrompt(1) },
```
