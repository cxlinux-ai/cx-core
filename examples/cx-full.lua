-- CX Terminal Full Configuration
-- Complete configuration with all features enabled
-- Place at ~/.config/cx/cx.lua

local cx = require 'cx'
local config = cx.config_builder()

-------------------------------------------------------------------------------
-- FONTS
-------------------------------------------------------------------------------
config.font = cx.font_with_fallback({
    "JetBrains Mono",
    "Noto Color Emoji",
    "Symbols Nerd Font",
})
config.font_size = 14.0
config.line_height = 1.1
config.cell_width = 1.0

-- Font rules for bold/italic
config.font_rules = {
    {
        intensity = "Bold",
        font = cx.font("JetBrains Mono", { weight = "Bold" }),
    },
    {
        italic = true,
        font = cx.font("JetBrains Mono", { style = "Italic" }),
    },
    {
        intensity = "Bold",
        italic = true,
        font = cx.font("JetBrains Mono", { weight = "Bold", style = "Italic" }),
    },
}

-------------------------------------------------------------------------------
-- COLOR SCHEME
-------------------------------------------------------------------------------
config.color_scheme = "CX Dark"

-- Or define custom colors:
-- config.colors = {
--     foreground = "#e0e0e0",
--     background = "#1a1a2e",
--     cursor_bg = "#00d4ff",
--     cursor_fg = "#1a1a2e",
--     cursor_border = "#00d4ff",
--     selection_fg = "#1a1a2e",
--     selection_bg = "#00d4ff",
--     ansi = {
--         "#2d2d44", "#ff6b6b", "#69ff94", "#fff68f",
--         "#6b9fff", "#ff6bff", "#6bffff", "#e0e0e0",
--     },
--     brights = {
--         "#4a4a6a", "#ff8888", "#88ffaa", "#ffffaa",
--         "#88aaff", "#ff88ff", "#88ffff", "#ffffff",
--     },
-- }

-------------------------------------------------------------------------------
-- WINDOW
-------------------------------------------------------------------------------
config.window_background_opacity = 0.95
config.window_decorations = "RESIZE"
config.window_close_confirmation = "AlwaysPrompt"
config.window_padding = {
    left = 12,
    right = 12,
    top = 12,
    bottom = 12,
}
config.initial_cols = 120
config.initial_rows = 35

-------------------------------------------------------------------------------
-- TAB BAR
-------------------------------------------------------------------------------
config.enable_tab_bar = true
config.hide_tab_bar_if_only_one_tab = false
config.tab_bar_at_bottom = false
config.use_fancy_tab_bar = true
config.show_tab_index_in_tab_bar = true
config.tab_max_width = 25

-------------------------------------------------------------------------------
-- CURSOR
-------------------------------------------------------------------------------
config.default_cursor_style = "SteadyBlock"
-- Options: SteadyBlock, BlinkingBlock, SteadyUnderline,
-- BlinkingUnderline, SteadyBar, BlinkingBar
config.cursor_blink_rate = 500
config.cursor_blink_ease_in = "Constant"
config.cursor_blink_ease_out = "Constant"

-------------------------------------------------------------------------------
-- SCROLLBACK
-------------------------------------------------------------------------------
config.scrollback_lines = 50000
config.enable_scroll_bar = true

-------------------------------------------------------------------------------
-- TERMINAL BEHAVIOR
-------------------------------------------------------------------------------
config.automatically_reload_config = true
config.check_for_updates = false
config.exit_behavior = "CloseOnCleanExit"
-- Options: Close, Hold, CloseOnCleanExit
config.audible_bell = "Disabled"
-- Options: Disabled, SystemBeep
config.visual_bell = {
    fade_in_duration_ms = 75,
    fade_out_duration_ms = 75,
    target = "CursorColor",
}

-------------------------------------------------------------------------------
-- HYPERLINKS
-------------------------------------------------------------------------------
config.hyperlink_rules = cx.default_hyperlink_rules()

-------------------------------------------------------------------------------
-- KEY BINDINGS
-------------------------------------------------------------------------------
config.leader = { key = "a", mods = "CTRL", timeout_milliseconds = 1000 }

config.keys = {
    -- Split panes
    { key = "d", mods = "LEADER", action = cx.action.SplitHorizontal { domain = "CurrentPaneDomain" } },
    { key = "e", mods = "LEADER", action = cx.action.SplitVertical { domain = "CurrentPaneDomain" } },

    -- Navigate panes
    { key = "h", mods = "LEADER", action = cx.action.ActivatePaneDirection "Left" },
    { key = "j", mods = "LEADER", action = cx.action.ActivatePaneDirection "Down" },
    { key = "k", mods = "LEADER", action = cx.action.ActivatePaneDirection "Up" },
    { key = "l", mods = "LEADER", action = cx.action.ActivatePaneDirection "Right" },

    -- Resize panes
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
    { key = "6", mods = "LEADER", action = cx.action.ActivateTab(5) },
    { key = "7", mods = "LEADER", action = cx.action.ActivateTab(6) },
    { key = "8", mods = "LEADER", action = cx.action.ActivateTab(7) },
    { key = "9", mods = "LEADER", action = cx.action.ActivateTab(8) },

    -- Copy mode
    { key = "[", mods = "LEADER", action = cx.action.ActivateCopyMode },

    -- Quick select
    { key = "f", mods = "LEADER", action = cx.action.QuickSelect },

    -- Search
    { key = "/", mods = "LEADER", action = cx.action.Search "CurrentSelectionOrEmptyString" },

    -- Zoom pane
    { key = "z", mods = "LEADER", action = cx.action.TogglePaneZoomState },

    -- Show launcher
    { key = "space", mods = "LEADER", action = cx.action.ShowLauncher },

    -- Reload config
    { key = "r", mods = "LEADER", action = cx.action.ReloadConfiguration },

    -- AI Panel toggle (CX specific)
    -- { key = "a", mods = "CTRL|SHIFT", action = cx.action.ToggleAIPanel },
}

-------------------------------------------------------------------------------
-- MOUSE BINDINGS
-------------------------------------------------------------------------------
config.mouse_bindings = {
    -- Right click paste
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
}

-------------------------------------------------------------------------------
-- MULTIPLEXER
-------------------------------------------------------------------------------
config.unix_domains = {
    { name = "unix" },
}
config.default_gui_startup_args = { "connect", "unix" }

-------------------------------------------------------------------------------
-- SSH DOMAINS
-------------------------------------------------------------------------------
-- config.ssh_domains = {
--     {
--         name = "server",
--         remote_address = "server.example.com",
--         username = "user",
--     },
-- }

-------------------------------------------------------------------------------
-- AI INTEGRATION (CX Specific - Future Feature)
-------------------------------------------------------------------------------
-- config.cx_ai = {
--     enabled = true,
--     provider = "claude",
--     api_key_cmd = { "pass", "show", "anthropic-api-key" },
--     panel_position = "right",
--     panel_width = 40,
--     keybinding = "CTRL+SPACE",
--     auto_suggest = true,
-- }

return config
