#!/bin/bash
# Cortex Linux Installer
# Zero-friction installation script
# Usage: curl -fsSL https://cortexlinux.com/install.sh | bash

set -euo pipefail

# Check if running in non-interactive mode
NON_INTERACTIVE=false
if [ -n "${CI:-}" ] || [ -n "${DEBIAN_FRONTEND:-}" ] || [ ! -t 0 ]; then
    NON_INTERACTIVE=true
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Emoji support
EMOJI_BRAIN="🧠"
EMOJI_CHECK="✅"
EMOJI_WARN="⚠️"
EMOJI_ERROR="❌"
EMOJI_INFO="ℹ️"

# Print functions
print_header() {
    echo -e "${BLUE}${EMOJI_BRAIN} Cortex Linux Installer${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}${EMOJI_CHECK} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}${EMOJI_WARN} $1${NC}"
}

print_error() {
    echo -e "${RED}${EMOJI_ERROR} $1${NC}" >&2
}

print_info() {
    echo -e "${BLUE}${EMOJI_INFO} $1${NC}"
}

# Detect OS
detect_os() {
    if [ ! -f /etc/os-release ]; then
        print_error "Cannot detect OS. /etc/os-release not found."
        exit 1
    fi

    . /etc/os-release
    
    if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
        print_error "Cortex Linux currently supports Ubuntu and Debian only."
        print_info "Detected: $ID"
        exit 1
    fi

    OS_NAME="$ID"
    OS_VERSION="${VERSION_ID:-unknown}"
    
    print_info "Detected: ${OS_NAME^} ${OS_VERSION}"
}

# Check Python version
check_python() {
    # Try python3 first, then python
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        print_error "Python 3 not found. Please install Python 3.10 or higher."
        exit 1
    fi

    # Check version
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    # Handle version comparison safely
    if ! [[ "$PYTHON_MAJOR" =~ ^[0-9]+$ ]] || ! [[ "$PYTHON_MINOR" =~ ^[0-9]+$ ]]; then
        print_error "Could not parse Python version: $PYTHON_VERSION"
        exit 1
    fi

    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
        print_error "Python 3.10+ required. Found: $PYTHON_VERSION"
        exit 1
    fi

    print_info "Python version: $PYTHON_VERSION"
}

# Create venv in ~/.cortex/
setup_venv() {
    CORTEX_DIR="$HOME/.cortex"
    VENV_DIR="$CORTEX_DIR/venv"

    print_info "Installing to $CORTEX_DIR..."

    # Create .cortex directory if it doesn't exist
    mkdir -p "$CORTEX_DIR"

    # Create virtual environment
    if [ -d "$VENV_DIR" ]; then
        if [ "$NON_INTERACTIVE" = true ]; then
            print_warning "Virtual environment already exists at $VENV_DIR"
            print_info "Removing existing virtual environment (non-interactive mode)"
            rm -rf "$VENV_DIR"
        else
            print_warning "Virtual environment already exists at $VENV_DIR"
            read -p "Remove and recreate? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                rm -rf "$VENV_DIR"
            else
                print_info "Using existing virtual environment"
                return
            fi
        fi
    fi

    print_info "Creating virtual environment..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    
    print_success "Virtual environment created"
}

# Install cortex-linux
install_cortex() {
    VENV_DIR="$HOME/.cortex/venv"
    PIP_CMD="$VENV_DIR/bin/pip"
    PYTHON_CMD="$VENV_DIR/bin/python"

    print_info "Installing cortex-linux..."
    
    # Upgrade pip first
    "$PIP_CMD" install --quiet --upgrade pip > /dev/null 2>&1 || true
    
    # Try to install from PyPI first
    if "$PIP_CMD" install --quiet cortex-linux 2>/dev/null; then
        print_success "cortex-linux installed successfully from PyPI"
        return 0
    fi
    
    # Fallback: Try installing from GitHub
    print_info "PyPI package not found, installing from GitHub..."
    if "$PIP_CMD" install --quiet "git+https://github.com/cortexlinux/cortex.git" 2>/dev/null; then
        print_success "cortex-linux installed successfully from GitHub"
        return 0
    fi
    
    # Last resort: If we're in the cortex repo directory, install from local source
    if [ -f "setup.py" ] || [ -f "pyproject.toml" ]; then
        print_info "Installing from local source..."
        if "$PIP_CMD" install --quiet -e . 2>/dev/null; then
            print_success "cortex-linux installed successfully from local source"
            return 0
        fi
    fi
    
    print_error "Failed to install cortex-linux from PyPI, GitHub, or local source"
    print_info "Make sure you have internet access and the package is available"
    exit 1
}

# Add to PATH
add_to_path() {
    CORTEX_BIN="$HOME/.cortex/venv/bin"
    CORTEX_SYMLINK="$HOME/.local/bin/cortex"
    LOCAL_BIN="$HOME/.local/bin"

    # Create ~/.local/bin if it doesn't exist
    mkdir -p "$LOCAL_BIN"

    # Create symlink
    if [ -L "$CORTEX_SYMLINK" ] || [ -f "$CORTEX_SYMLINK" ]; then
        rm -f "$CORTEX_SYMLINK"
    fi
    
    ln -s "$CORTEX_BIN/cortex" "$CORTEX_SYMLINK"
    print_success "Created symlink: $CORTEX_SYMLINK"

    # Check if ~/.local/bin is in PATH
    if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
        print_warning "$LOCAL_BIN is not in your PATH"
        echo ""
        print_info "Add this to your ~/.bashrc or ~/.zshrc:"
        echo -e "${GREEN}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
        echo ""
        
        # Detect shell and offer to add automatically
        if [ "$NON_INTERACTIVE" = false ]; then
            SHELL_NAME=$(basename "$SHELL")
            if [ -f "$HOME/.${SHELL_NAME}rc" ]; then
                read -p "Add to PATH automatically? [Y/n] " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                    if ! grep -q "$LOCAL_BIN" "$HOME/.${SHELL_NAME}rc" 2>/dev/null; then
                        echo "" >> "$HOME/.${SHELL_NAME}rc"
                        echo "# Added by Cortex Linux installer" >> "$HOME/.${SHELL_NAME}rc"
                        echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$HOME/.${SHELL_NAME}rc"
                        print_success "Added to $HOME/.${SHELL_NAME}rc"
                        print_info "Run 'source ~/.${SHELL_NAME}rc' or restart your terminal"
                    else
                        print_info "PATH already configured in $HOME/.${SHELL_NAME}rc"
                    fi
                fi
            fi
        else
            print_info "Non-interactive mode: Please add ~/.local/bin to your PATH manually"
        fi
    else
        print_success "$LOCAL_BIN is already in your PATH"
    fi
}

# Check for API key
check_api_key() {
    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        print_success "Found ANTHROPIC_API_KEY in environment"
        return 0
    fi

    if [ -n "${OPENAI_API_KEY:-}" ]; then
        print_success "Found OPENAI_API_KEY in environment"
        return 0
    fi

    # Check for .env file
    if [ -f "$HOME/.cortex/.env" ]; then
        if grep -q "ANTHROPIC_API_KEY\|OPENAI_API_KEY" "$HOME/.cortex/.env" 2>/dev/null; then
            print_success "Found API key in ~/.cortex/.env"
            return 0
        fi
    fi

    print_warning "No API key detected"
    echo ""
    print_info "Cortex requires an API key for AI features:"
    echo "  1. Claude API (Anthropic) - Recommended"
    echo "  2. OpenAI API"
    echo "  3. Local LLM (Ollama) - Free, runs on your machine"
    echo ""
    
    if [ "$NON_INTERACTIVE" = true ]; then
        print_info "Non-interactive mode: Skipping API key setup"
        print_info "Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable, or run 'cortex wizard'"
        return 0
    fi
    
    read -p "Would you like to configure an API key now? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        echo ""
        echo "Choose an option:"
        echo "  1) Claude API (Anthropic)"
        echo "  2) OpenAI API"
        echo "  3) Skip (you can run 'cortex wizard' later)"
        echo ""
        read -p "Enter choice [1-3]: " -n 1 -r
        echo
        
        case $REPLY in
            1)
                read -sp "Enter your ANTHROPIC_API_KEY: " API_KEY
                echo
                if [ -n "$API_KEY" ]; then
                    # Save to .env file
                    mkdir -p "$HOME/.cortex"
                    echo "ANTHROPIC_API_KEY=$API_KEY" >> "$HOME/.cortex/.env"
                    export ANTHROPIC_API_KEY="$API_KEY"
                    
                    # Also add to shell rc for persistence
                    SHELL_NAME=$(basename "$SHELL")
                    if [ -f "$HOME/.${SHELL_NAME}rc" ]; then
                        if ! grep -q "ANTHROPIC_API_KEY" "$HOME/.${SHELL_NAME}rc" 2>/dev/null; then
                            echo "" >> "$HOME/.${SHELL_NAME}rc"
                            echo "# Added by Cortex Linux installer" >> "$HOME/.${SHELL_NAME}rc"
                            echo "export ANTHROPIC_API_KEY=\"$API_KEY\"" >> "$HOME/.${SHELL_NAME}rc"
                        fi
                    fi
                    
                    print_success "API key saved to ~/.cortex/.env and ~/.${SHELL_NAME}rc"
                fi
                ;;
            2)
                read -sp "Enter your OPENAI_API_KEY: " API_KEY
                echo
                if [ -n "$API_KEY" ]; then
                    # Save to .env file
                    mkdir -p "$HOME/.cortex"
                    echo "OPENAI_API_KEY=$API_KEY" >> "$HOME/.cortex/.env"
                    export OPENAI_API_KEY="$API_KEY"
                    
                    # Also add to shell rc for persistence
                    SHELL_NAME=$(basename "$SHELL")
                    if [ -f "$HOME/.${SHELL_NAME}rc" ]; then
                        if ! grep -q "OPENAI_API_KEY" "$HOME/.${SHELL_NAME}rc" 2>/dev/null; then
                            echo "" >> "$HOME/.${SHELL_NAME}rc"
                            echo "# Added by Cortex Linux installer" >> "$HOME/.${SHELL_NAME}rc"
                            echo "export OPENAI_API_KEY=\"$API_KEY\"" >> "$HOME/.${SHELL_NAME}rc"
                        fi
                    fi
                    
                    print_success "API key saved to ~/.cortex/.env and ~/.${SHELL_NAME}rc"
                fi
                ;;
            *)
                print_info "Skipping API key setup. Run 'cortex wizard' to configure later."
                ;;
        esac
    else
        print_info "Skipping API key setup. Run 'cortex wizard' to configure later."
    fi
}

# Verify installation
verify_installation() {
    CORTEX_CMD="$HOME/.local/bin/cortex"
    
    # If not in PATH yet, use full path
    if ! command -v cortex &> /dev/null; then
        if [ ! -f "$CORTEX_CMD" ]; then
            CORTEX_CMD="$HOME/.cortex/venv/bin/cortex"
        fi
    else
        CORTEX_CMD="cortex"
    fi

    print_info "Verifying installation..."
    echo ""
    
    if "$CORTEX_CMD" --help &> /dev/null; then
        print_success "Installation verified!"
        echo ""
        echo -e "${GREEN}${EMOJI_CHECK} Installed! Run: ${NC}cortex install nginx"
        echo ""
        print_info "Quick start:"
        echo "  cortex install nginx          # Install a package"
        echo "  cortex wizard                 # Run setup wizard"
        echo "  cortex --help                 # See all commands"
    else
        print_error "Installation verification failed"
        print_info "Try running: $CORTEX_CMD --help"
        exit 1
    fi
}

# Main installation flow
main() {
    print_header
    
    detect_os
    check_python
    setup_venv
    install_cortex
    add_to_path
    check_api_key
    verify_installation
}

# Run main function
main

