-- CX Terminal Theme Examples
-- Examples of custom color schemes and theming
-- Place at ~/.config/cx/cx.lua

local cx = require 'cx'
local config = cx.config_builder()

-------------------------------------------------------------------------------
-- THEME 1: CX Dark (Default)
-- A modern dark theme with cyan accents
-------------------------------------------------------------------------------
local cx_dark = {
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
        "#2d2d44",  -- black
        "#ff6b6b",  -- red
        "#69ff94",  -- green
        "#fff68f",  -- yellow
        "#6b9fff",  -- blue
        "#ff6bff",  -- magenta
        "#6bffff",  -- cyan
        "#e0e0e0",  -- white
    },
    brights = {
        "#4a4a6a",  -- bright black
        "#ff8888",  -- bright red
        "#88ffaa",  -- bright green
        "#ffffaa",  -- bright yellow
        "#88aaff",  -- bright blue
        "#ff88ff",  -- bright magenta
        "#88ffff",  -- bright cyan
        "#ffffff",  -- bright white
    },

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
        new_tab_hover = {
            bg_color = "#3d3d5c",
            fg_color = "#e0e0e0",
        },
    },
}

-------------------------------------------------------------------------------
-- THEME 2: CX Light
-- A clean light theme for daytime use
-------------------------------------------------------------------------------
local cx_light = {
    foreground = "#2d2d44",
    background = "#f8f8f8",
    cursor_bg = "#0088cc",
    cursor_fg = "#f8f8f8",
    cursor_border = "#0088cc",
    selection_fg = "#f8f8f8",
    selection_bg = "#0088cc",
    scrollbar_thumb = "#c0c0c0",
    split = "#d0d0d0",

    ansi = {
        "#2d2d44",  -- black
        "#cc0000",  -- red
        "#00aa00",  -- green
        "#aa8800",  -- yellow
        "#0055cc",  -- blue
        "#cc00cc",  -- magenta
        "#0088aa",  -- cyan
        "#f0f0f0",  -- white
    },
    brights = {
        "#555555",  -- bright black
        "#ff0000",  -- bright red
        "#00cc00",  -- bright green
        "#ccaa00",  -- bright yellow
        "#0077ff",  -- bright blue
        "#ff00ff",  -- bright magenta
        "#00aacc",  -- bright cyan
        "#ffffff",  -- bright white
    },

    tab_bar = {
        background = "#e8e8e8",
        active_tab = {
            bg_color = "#0088cc",
            fg_color = "#ffffff",
        },
        inactive_tab = {
            bg_color = "#d0d0d0",
            fg_color = "#555555",
        },
        inactive_tab_hover = {
            bg_color = "#c0c0c0",
            fg_color = "#2d2d44",
        },
        new_tab = {
            bg_color = "#e8e8e8",
            fg_color = "#555555",
        },
        new_tab_hover = {
            bg_color = "#c0c0c0",
            fg_color = "#2d2d44",
        },
    },
}

-------------------------------------------------------------------------------
-- THEME 3: CX Monokai
-- Classic Monokai-inspired theme
-------------------------------------------------------------------------------
local cx_monokai = {
    foreground = "#f8f8f2",
    background = "#272822",
    cursor_bg = "#f8f8f2",
    cursor_fg = "#272822",
    cursor_border = "#f8f8f2",
    selection_fg = "#272822",
    selection_bg = "#f8f8f2",
    scrollbar_thumb = "#49483e",
    split = "#49483e",

    ansi = {
        "#272822",  -- black
        "#f92672",  -- red
        "#a6e22e",  -- green
        "#f4bf75",  -- yellow
        "#66d9ef",  -- blue
        "#ae81ff",  -- magenta
        "#a1efe4",  -- cyan
        "#f8f8f2",  -- white
    },
    brights = {
        "#75715e",  -- bright black
        "#f92672",  -- bright red
        "#a6e22e",  -- bright green
        "#f4bf75",  -- bright yellow
        "#66d9ef",  -- bright blue
        "#ae81ff",  -- bright magenta
        "#a1efe4",  -- bright cyan
        "#f9f8f5",  -- bright white
    },

    tab_bar = {
        background = "#1e1f1c",
        active_tab = {
            bg_color = "#a6e22e",
            fg_color = "#272822",
        },
        inactive_tab = {
            bg_color = "#3e3d32",
            fg_color = "#75715e",
        },
        inactive_tab_hover = {
            bg_color = "#49483e",
            fg_color = "#f8f8f2",
        },
        new_tab = {
            bg_color = "#1e1f1c",
            fg_color = "#75715e",
        },
        new_tab_hover = {
            bg_color = "#49483e",
            fg_color = "#f8f8f2",
        },
    },
}

-------------------------------------------------------------------------------
-- THEME 4: CX Nord
-- Arctic, bluish clean and elegant theme
-------------------------------------------------------------------------------
local cx_nord = {
    foreground = "#d8dee9",
    background = "#2e3440",
    cursor_bg = "#88c0d0",
    cursor_fg = "#2e3440",
    cursor_border = "#88c0d0",
    selection_fg = "#2e3440",
    selection_bg = "#88c0d0",
    scrollbar_thumb = "#4c566a",
    split = "#4c566a",

    ansi = {
        "#3b4252",  -- black
        "#bf616a",  -- red
        "#a3be8c",  -- green
        "#ebcb8b",  -- yellow
        "#81a1c1",  -- blue
        "#b48ead",  -- magenta
        "#88c0d0",  -- cyan
        "#e5e9f0",  -- white
    },
    brights = {
        "#4c566a",  -- bright black
        "#bf616a",  -- bright red
        "#a3be8c",  -- bright green
        "#ebcb8b",  -- bright yellow
        "#81a1c1",  -- bright blue
        "#b48ead",  -- bright magenta
        "#8fbcbb",  -- bright cyan
        "#eceff4",  -- bright white
    },

    tab_bar = {
        background = "#242933",
        active_tab = {
            bg_color = "#88c0d0",
            fg_color = "#2e3440",
        },
        inactive_tab = {
            bg_color = "#3b4252",
            fg_color = "#d8dee9",
        },
        inactive_tab_hover = {
            bg_color = "#434c5e",
            fg_color = "#eceff4",
        },
        new_tab = {
            bg_color = "#242933",
            fg_color = "#d8dee9",
        },
        new_tab_hover = {
            bg_color = "#434c5e",
            fg_color = "#eceff4",
        },
    },
}

-------------------------------------------------------------------------------
-- APPLY THEME
-- Uncomment the theme you want to use
-------------------------------------------------------------------------------

-- Option 1: Use built-in scheme
config.color_scheme = "CX Dark"

-- Option 2: Use custom colors
-- config.colors = cx_dark
-- config.colors = cx_light
-- config.colors = cx_monokai
-- config.colors = cx_nord

-------------------------------------------------------------------------------
-- DYNAMIC THEME SWITCHING
-- Example of switching theme based on time
-------------------------------------------------------------------------------
-- local function get_appearance()
--     local hour = tonumber(os.date("%H"))
--     if hour >= 6 and hour < 18 then
--         return cx_light
--     else
--         return cx_dark
--     end
-- end
--
-- config.colors = get_appearance()

-------------------------------------------------------------------------------
-- BACKGROUND CUSTOMIZATION
-------------------------------------------------------------------------------
-- Solid color
config.window_background_opacity = 0.95

-- Background image (uncomment to use)
-- config.window_background_image = "/path/to/image.png"
-- config.window_background_image_hsb = {
--     brightness = 0.05,
--     saturation = 1.0,
--     hue = 1.0,
-- }

-- Gradient background (uncomment to use)
-- config.window_background_gradient = {
--     orientation = "Vertical",
--     colors = { "#1a1a2e", "#2d2d44" },
--     preset = "Warm",
-- }

-------------------------------------------------------------------------------
-- FONT STYLING
-------------------------------------------------------------------------------
config.font = cx.font("JetBrains Mono")
config.font_size = 14.0

-- Enable ligatures (for supported fonts)
config.harfbuzz_features = { "calt=1", "clig=1", "liga=1" }

-- Disable ligatures
-- config.harfbuzz_features = { "calt=0", "clig=0", "liga=0" }

return config
