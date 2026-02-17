-- CX Terminal Minimal Configuration
-- This is the bare minimum config to get started
-- Place at ~/.config/cx/cx.lua

local cx = require 'cx'
local config = cx.config_builder()

-- That's it! CX Terminal will use sensible defaults:
-- - System default font at 14pt (Menlo on macOS, DejaVu Sans Mono on Linux)
-- - CX Dark color scheme
-- - GPU acceleration enabled
-- - 10000 lines scrollback

return config
