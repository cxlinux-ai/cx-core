# CX Terminal Configuration Reference

CX Terminal uses Lua for configuration, providing full programmability.

## Configuration File Locations

CX Terminal looks for configuration in order:
1. `$CX_CONFIG_FILE` (environment variable)
2. `$XDG_CONFIG_HOME/cx/cx.lua`
3. `~/.config/cx/cx.lua`
4. `~/.cx.lua`

## Basic Structure

```lua
local cx = require 'cx'
local config = cx.config_builder()

-- Your settings here
config.font_size = 14.0

return config
```

## Font Configuration

### Basic Font
```lua
config.font = cx.font("JetBrains Mono")
config.font_size = 14.0
```

### Font with Fallbacks
```lua
config.font = cx.font_with_fallback({
    "JetBrains Mono",
    "Noto Color Emoji",
    "Symbols Nerd Font",
})
```

### Font Attributes
```lua
config.font = cx.font("JetBrains Mono", {
    weight = "Bold",       -- Thin, ExtraLight, Light, Regular, Medium, SemiBold, Bold, ExtraBold, Black
    style = "Italic",      -- Normal, Italic, Oblique
    stretch = "Normal",    -- UltraCondensed, ExtraCondensed, Condensed, SemiCondensed, Normal, SemiExpanded, Expanded, ExtraExpanded, UltraExpanded
})
```

### Font Rules (Bold/Italic Variants)
```lua
config.font_rules = {
    {
        intensity = "Bold",
        font = cx.font("JetBrains Mono", { weight = "Bold" }),
    },
    {
        italic = true,
        font = cx.font("JetBrains Mono", { style = "Italic" }),
    },
}
```

### Font Metrics
```lua
config.line_height = 1.0       -- Line height multiplier
config.cell_width = 1.0        -- Cell width multiplier
config.underline_position = -2 -- Underline vertical offset
config.underline_thickness = 1 -- Underline thickness
```

### Font Features (Ligatures)
```lua
-- Enable ligatures
config.harfbuzz_features = { "calt=1", "clig=1", "liga=1" }

-- Disable ligatures
config.harfbuzz_features = { "calt=0", "clig=0", "liga=0" }
```

## Color Schemes

### Built-in Scheme
```lua
config.color_scheme = "CX Dark"
```

### Custom Colors
```lua
config.colors = {
    foreground = "#e0e0e0",
    background = "#1a1a2e",
    cursor_bg = "#00d4ff",
    cursor_fg = "#1a1a2e",
    cursor_border = "#00d4ff",
    selection_fg = "#1a1a2e",
    selection_bg = "#00d4ff",
    scrollbar_thumb = "#3d3d5c",
    split = "#3d3d5c",

    ansi = {
        "#2d2d44", "#ff6b6b", "#69ff94", "#fff68f",
        "#6b9fff", "#ff6bff", "#6bffff", "#e0e0e0",
    },
    brights = {
        "#4a4a6a", "#ff8888", "#88ffaa", "#ffffaa",
        "#88aaff", "#ff88ff", "#88ffff", "#ffffff",
    },
}
```

### Tab Bar Colors
```lua
config.colors = {
    tab_bar = {
        background = "#16162b",
        active_tab = {
            bg_color = "#00d4ff",
            fg_color = "#1a1a2e",
        },
        inactive_tab = {
            bg_color = "#2d2d44",
            fg_color = "#808080",
        },
        inactive_tab_hover = {
            bg_color = "#3d3d5c",
            fg_color = "#e0e0e0",
        },
        new_tab = {
            bg_color = "#16162b",
            fg_color = "#808080",
        },
    },
}
```

## Window Configuration

### Window Appearance
```lua
config.window_background_opacity = 0.95
config.window_decorations = "RESIZE"  -- FULL, RESIZE, NONE, TITLE
config.window_padding = {
    left = 8,
    right = 8,
    top = 8,
    bottom = 8,
}
```

### Window Size
```lua
config.initial_cols = 120
config.initial_rows = 35
```

### Background Image
```lua
config.window_background_image = "/path/to/image.png"
config.window_background_image_hsb = {
    brightness = 0.05,
    saturation = 1.0,
    hue = 1.0,
}
```

### Background Gradient
```lua
config.window_background_gradient = {
    orientation = "Vertical",  -- Horizontal, Vertical, Radial
    colors = { "#1a1a2e", "#2d2d44" },
}
```

## Tab Bar

```lua
config.enable_tab_bar = true
config.hide_tab_bar_if_only_one_tab = false
config.tab_bar_at_bottom = false
config.use_fancy_tab_bar = true
config.show_tab_index_in_tab_bar = true
config.tab_max_width = 25
```

## Cursor

```lua
config.default_cursor_style = "SteadyBlock"
-- Options: SteadyBlock, BlinkingBlock, SteadyUnderline, BlinkingUnderline, SteadyBar, BlinkingBar

config.cursor_blink_rate = 500
config.cursor_blink_ease_in = "Constant"   -- Constant, Linear, EaseIn, EaseOut
config.cursor_blink_ease_out = "Constant"
config.force_reverse_video_cursor = false
```

## Scrollback

```lua
config.scrollback_lines = 10000
config.enable_scroll_bar = true
```

## Terminal Behavior

```lua
config.automatically_reload_config = true
config.check_for_updates = false
config.exit_behavior = "CloseOnCleanExit"  -- Close, Hold, CloseOnCleanExit

-- Bell
config.audible_bell = "Disabled"  -- Disabled, SystemBeep
config.visual_bell = {
    fade_in_duration_ms = 75,
    fade_out_duration_ms = 75,
    target = "CursorColor",  -- CursorColor, BackgroundColor
}

-- Confirmation
config.window_close_confirmation = "AlwaysPrompt"  -- AlwaysPrompt, NeverPrompt
```

## Hyperlinks

```lua
-- Use default rules
config.hyperlink_rules = cx.default_hyperlink_rules()

-- Or define custom rules
config.hyperlink_rules = {
    -- URLs
    {
        regex = "\\b\\w+://[\\w.-]+\\S*\\b",
        format = "$0",
    },
    -- File paths
    {
        regex = "\\b/[\\w./]+\\b",
        format = "file://$0",
    },
}
```

## Key Bindings

See [KEYBINDINGS.md](KEYBINDINGS.md) for complete reference.

### Leader Key
```lua
config.leader = { key = "a", mods = "CTRL", timeout_milliseconds = 1000 }
```

### Key Assignments
```lua
config.keys = {
    { key = "d", mods = "CTRL|SHIFT", action = cx.action.SplitHorizontal { domain = "CurrentPaneDomain" } },
    { key = "c", mods = "LEADER", action = cx.action.SpawnTab "CurrentPaneDomain" },
}
```

## Mouse Bindings

```lua
config.mouse_bindings = {
    {
        event = { Down = { streak = 1, button = "Right" } },
        mods = "NONE",
        action = cx.action.PasteFrom "Clipboard",
    },
}
```

## Domains

### Unix Domain (Multiplexer)
```lua
config.unix_domains = {
    { name = "unix" },
}
config.default_gui_startup_args = { "connect", "unix" }
```

### SSH Domains
```lua
config.ssh_domains = {
    {
        name = "server",
        remote_address = "server.example.com",
        username = "user",
        remote_wezterm_path = "/usr/bin/wezterm",
    },
}
```

### WSL Domains (Windows)
```lua
config.wsl_domains = {
    {
        name = "WSL:Ubuntu",
        distribution = "Ubuntu",
    },
}
```

## Launch Menu

```lua
config.launch_menu = {
    {
        label = "Bash",
        args = { "/bin/bash" },
    },
    {
        label = "Zsh",
        args = { "/bin/zsh" },
    },
    {
        label = "Top",
        args = { "top" },
    },
}
```

## Environment Variables

```lua
config.set_environment_variables = {
    TERM = "xterm-256color",
    COLORTERM = "truecolor",
}
```

## Quick Select Patterns

```lua
config.quick_select_patterns = {
    -- Match git hashes
    "[0-9a-f]{7,40}",
    -- Match UUIDs
    "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
}
```

## Dynamic Configuration

Lua allows dynamic configuration:

```lua
-- Time-based theme
local hour = tonumber(os.date("%H"))
if hour >= 6 and hour < 18 then
    config.color_scheme = "CX Light"
else
    config.color_scheme = "CX Dark"
end

-- Host-based config
local hostname = cx.hostname()
if hostname:find("work") then
    config.font_size = 12.0
end
```

## Events

```lua
-- Window resize event
cx.on("window-resized", function(window, pane)
    window:set_right_status("Cols: " .. pane:get_dimensions().cols)
end)

-- Tab format
cx.on("format-tab-title", function(tab, tabs, panes, config, hover)
    return string.format(" %d: %s ", tab.tab_index + 1, tab.active_pane.title)
end)
```

## Full Example

See `examples/cx-full.lua` for a complete configuration example.
