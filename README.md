# CX Terminal

*An AI-native, GPU-accelerated terminal emulator for CX Linux*

Based on [WezTerm](https://github.com/wezterm/wezterm) by [@wez](https://github.com/wez).

## Features

- GPU-accelerated rendering
- Lua-configurable
- AI integration ready
- Cross-platform (Linux, macOS, Windows)
- Built-in multiplexer
- Native CX Linux integration

## Installation

```bash
# Build from source
cargo build --release

# Binary located at
./target/release/cx-terminal
./target/release/cx-terminal-gui
```

## Configuration

CX Terminal uses `~/.config/cx/cx.lua` for configuration.

```lua
-- Example cx.lua
local cx = require 'cx'

return {
  font = cx.font("JetBrains Mono"),
  font_size = 14.0,
  color_scheme = "CX Dark",
}
```

## Credits

CX Terminal is a fork of WezTerm. Thanks to Wez Furlong for creating the foundation.

## License

BSL 1.1 (CX additions) + MIT (WezTerm base) - See [LICENSE.md](LICENSE.md)
