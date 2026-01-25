-- CX Terminal Configuration
-- Place this file at ~/.config/cx/cx.lua or ~/.cx.lua

local cx = require 'cx'

-- Create config builder
local config = cx.config_builder()

-- Font settings
config.font = cx.font("JetBrains Mono")
config.font_size = 14.0

-- Color scheme (CX Dark is the default)
config.color_scheme = "CX Dark"

-- Window settings
config.window_background_opacity = 0.95
config.window_decorations = "RESIZE"
config.window_padding = {
  left = 8,
  right = 8,
  top = 8,
  bottom = 8,
}

-- Tab bar
config.hide_tab_bar_if_only_one_tab = true
config.tab_bar_at_bottom = false

-- Cursor settings
config.default_cursor_style = "SteadyBlock"

-- Scrollback
config.scrollback_lines = 10000

-- Key bindings example
config.keys = {
  -- Split pane horizontally
  { key = "d", mods = "CTRL|SHIFT", action = cx.action.SplitHorizontal { domain = "CurrentPaneDomain" } },
  -- Split pane vertically
  { key = "e", mods = "CTRL|SHIFT", action = cx.action.SplitVertical { domain = "CurrentPaneDomain" } },
  -- Close pane
  { key = "w", mods = "CTRL|SHIFT", action = cx.action.CloseCurrentPane { confirm = true } },
}

-- AI Integration (future feature)
-- config.ai = {
--   enabled = true,
--   provider = "claude",
--   keybinding = "CTRL+SPACE",
-- }

return config
