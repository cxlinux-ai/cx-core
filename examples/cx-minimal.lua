-- CX Terminal Minimal Configuration
-- This is the bare minimum config to get started
-- Place at ~/.config/cx/cx.lua

local cx = require 'cx'
local config = cx.config_builder()

-- That's it! CX Terminal will use sensible defaults:
-- - JetBrains Mono font at 14pt
-- - CX Dark color scheme
-- - GPU acceleration enabled
-- - 10000 lines scrollback

return config
