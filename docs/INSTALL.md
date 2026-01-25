# CX Terminal Installation Guide

## Prerequisites

### Required
- Rust 1.75+ (with cargo)
- Git

### Platform-Specific Dependencies

#### Linux (Debian/Ubuntu)
```bash
sudo apt install -y \
    build-essential \
    cmake \
    pkg-config \
    libfontconfig1-dev \
    libfreetype6-dev \
    libxcb-render0-dev \
    libxcb-shape0-dev \
    libxcb-xfixes0-dev \
    libxcb-keysyms1-dev \
    libxcb-icccm4-dev \
    libxcb-image0-dev \
    libxkbcommon-dev \
    libxkbcommon-x11-dev \
    libwayland-dev \
    libssl-dev \
    libegl1-mesa-dev \
    libgl1-mesa-dev
```

#### Linux (Fedora/RHEL)
```bash
sudo dnf install -y \
    gcc-c++ \
    cmake \
    pkg-config \
    fontconfig-devel \
    freetype-devel \
    libxcb-devel \
    libxkbcommon-devel \
    libxkbcommon-x11-devel \
    wayland-devel \
    openssl-devel \
    mesa-libEGL-devel \
    mesa-libGL-devel
```

#### Linux (Arch)
```bash
sudo pacman -S \
    base-devel \
    cmake \
    pkg-config \
    fontconfig \
    freetype2 \
    libxcb \
    libxkbcommon \
    wayland \
    openssl \
    mesa
```

#### macOS
```bash
# Install Xcode Command Line Tools
xcode-select --install

# Install Homebrew dependencies
brew install pkg-config fontconfig freetype openssl
```

#### Windows
- Install Visual Studio Build Tools 2019+
- Install CMake
- Install Perl (for OpenSSL)

## Installing Rust

If you don't have Rust installed:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env
```

## Building from Source

### Clone the Repository
```bash
git clone https://github.com/cortexlinux/cortex-terminal.git
cd cortex-terminal
```

### Quick Build
```bash
# Debug build (faster compilation, slower runtime)
cargo build

# Release build (slower compilation, optimized runtime)
cargo build --release
```

### Build Specific Binaries
```bash
# GUI application only
cargo build --release -p wezterm-gui

# CLI only
cargo build --release -p wezterm

# Mux server
cargo build --release -p wezterm-mux-server
```

## Installation

### Install Locally
```bash
# Build release binaries
cargo build --release

# Copy to local bin
mkdir -p ~/.local/bin
cp target/release/wezterm ~/.local/bin/cx-terminal
cp target/release/wezterm-gui ~/.local/bin/cx-terminal-gui
cp target/release/wezterm-mux-server ~/.local/bin/cx-mux-server

# Add to PATH (add to ~/.bashrc or ~/.zshrc)
export PATH="$HOME/.local/bin:$PATH"
```

### Install System-Wide (Linux)
```bash
sudo install -Dm755 target/release/wezterm /usr/bin/cx-terminal
sudo install -Dm755 target/release/wezterm-gui /usr/bin/cx-terminal-gui
sudo install -Dm755 target/release/wezterm-mux-server /usr/bin/cx-mux-server
```

### Install Shell Integration
```bash
# Bash
echo 'source /usr/share/cx-terminal/shell-integration/cx.bash' >> ~/.bashrc

# Zsh
echo 'source /usr/share/cx-terminal/shell-integration/cx.zsh' >> ~/.zshrc

# Fish
echo 'source /usr/share/cx-terminal/shell-integration/cx.fish' >> ~/.config/fish/config.fish
```

Or install manually:
```bash
sudo mkdir -p /usr/share/cx-terminal/shell-integration
sudo cp shell-integration/cx.* /usr/share/cx-terminal/shell-integration/
```

## Configuration

CX Terminal looks for configuration in:
1. `$XDG_CONFIG_HOME/cx/cx.lua` (usually `~/.config/cx/cx.lua`)
2. `~/.cx.lua`
3. `~/.config/cx/cx.lua`

### Quick Start Configuration
```bash
mkdir -p ~/.config/cx
cp examples/cx.lua ~/.config/cx/cx.lua
```

See [CONFIG.md](CONFIG.md) for full configuration reference.

## Verification

```bash
# Check version
cx-terminal --version

# Run with debug output
WEZTERM_LOG=debug cx-terminal-gui

# Test configuration
cx-terminal-gui --config-file examples/cx.lua
```

## Troubleshooting

### Build Fails: Missing Dependencies
Run the dependency install commands for your platform above.

### Build Fails: OpenSSL Not Found
```bash
# Linux
export OPENSSL_DIR=/usr

# macOS (Homebrew)
export OPENSSL_DIR=$(brew --prefix openssl)
```

### GPU Issues
Try software rendering:
```bash
WGPU_BACKEND=gl cx-terminal-gui
```

### Wayland Issues
Force X11:
```bash
WAYLAND_DISPLAY= cx-terminal-gui
```

## Development Build

For development with faster iteration:
```bash
# Watch mode (requires cargo-watch)
cargo install cargo-watch
cargo watch -x 'build -p wezterm-gui'

# Run tests
cargo test

# Run specific test
cargo test -p termwiz -- test_name

# Check without building
cargo check
```

## CI/CD Artifacts

Pre-built binaries are available from GitHub Actions for:
- Ubuntu 20.04, 22.04, 24.04
- Fedora 39, 40, 41
- macOS (Intel and ARM)
- Windows

Download from: [GitHub Releases](https://github.com/cortexlinux/cortex-terminal/releases)
