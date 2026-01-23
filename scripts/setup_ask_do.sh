#!/bin/bash
#
# Cortex ask --do Setup Script
# 
# This script sets up everything needed for the AI-powered command execution:
# - Ollama Docker container with a local LLM
# - Cortex Watch service for terminal monitoring
# - Shell hooks for command logging
#
# Usage:
#   ./scripts/setup_ask_do.sh [options]
#
# Options:
#   --no-docker     Skip Docker/Ollama setup
#   --model MODEL   Ollama model (default: mistral, alternatives: phi, llama2)
#   --skip-watch    Skip watch service installation
#   --uninstall     Remove all components
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Defaults
MODEL="mistral"
NO_DOCKER=false
SKIP_WATCH=false
UNINSTALL=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-docker)
            NO_DOCKER=true
            shift
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --skip-watch)
            SKIP_WATCH=true
            shift
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --no-docker     Skip Docker/Ollama setup"
            echo "  --model MODEL   Ollama model (default: mistral)"
            echo "  --skip-watch    Skip watch service installation"
            echo "  --uninstall     Remove all components"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

print_header() {
    echo -e "\n${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}\n"
}

print_step() {
    echo -e "${BLUE}▶${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Banner
echo -e "\n${BOLD}${CYAN}"
echo "  ██████╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗"
echo " ██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝"
echo " ██║     ██║   ██║██████╔╝   ██║   █████╗   ╚███╔╝ "
echo " ██║     ██║   ██║██╔══██╗   ██║   ██╔══╝   ██╔██╗ "
echo " ╚██████╗╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗"
echo "  ╚═════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝"
echo -e "${NC}"
echo -e "  ${DIM}ask --do Setup Wizard${NC}\n"

# Uninstall
if [ "$UNINSTALL" = true ]; then
    print_header "Uninstalling Cortex ask --do Components"
    
    # Stop watch service
    print_step "Stopping watch service..."
    systemctl --user stop cortex-watch.service 2>/dev/null || true
    systemctl --user disable cortex-watch.service 2>/dev/null || true
    rm -f ~/.config/systemd/user/cortex-watch.service
    systemctl --user daemon-reload
    print_success "Watch service removed"
    
    # Remove shell hooks
    print_step "Removing shell hooks..."
    if [ -f ~/.bashrc ]; then
        sed -i '/# Cortex Terminal Watch Hook/,/^$/d' ~/.bashrc
        sed -i '/alias cw=/d' ~/.bashrc
    fi
    if [ -f ~/.zshrc ]; then
        sed -i '/# Cortex Terminal Watch Hook/,/^$/d' ~/.zshrc
    fi
    print_success "Shell hooks removed"
    
    # Remove cortex files
    print_step "Removing cortex watch files..."
    rm -f ~/.cortex/watch_hook.sh
    rm -f ~/.cortex/terminal_watch.log
    rm -f ~/.cortex/terminal_commands.json
    rm -f ~/.cortex/watch_service.log
    rm -f ~/.cortex/watch_service.pid
    rm -f ~/.cortex/watch_state.json
    print_success "Watch files removed"
    
    # Ask about Ollama
    if docker ps -a --format '{{.Names}}' | grep -q '^ollama$'; then
        print_step "Ollama container found"
        read -p "  Remove Ollama container and data? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker stop ollama 2>/dev/null || true
            docker rm ollama 2>/dev/null || true
            docker volume rm ollama 2>/dev/null || true
            print_success "Ollama removed"
        fi
    fi
    
    print_success "Uninstallation complete"
    exit 0
fi

# Check Python environment
print_header "Checking Environment"

print_step "Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    print_success "Python installed: $PYTHON_VERSION"
else
    print_error "Python 3 not found"
    exit 1
fi

# Check if in virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    print_warning "Not in a virtual environment"
    if [ -f "venv/bin/activate" ]; then
        print_step "Activating venv..."
        source venv/bin/activate
        print_success "Activated venv"
    else
        print_warning "Consider running: python3 -m venv venv && source venv/bin/activate"
    fi
else
    print_success "Virtual environment active: $VIRTUAL_ENV"
fi

# Check cortex installation
print_step "Checking Cortex installation..."
if command -v cortex &> /dev/null; then
    print_success "Cortex is installed"
else
    print_warning "Cortex not found in PATH, installing..."
    pip install -e . -q
    print_success "Cortex installed"
fi

# Setup Ollama
if [ "$NO_DOCKER" = false ]; then
    print_header "Setting up Ollama (Local LLM)"
    
    print_step "Checking Docker..."
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        echo -e "  ${DIM}Install Docker: https://docs.docker.com/get-docker/${NC}"
        NO_DOCKER=true
    elif ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        echo -e "  ${DIM}Run: sudo systemctl start docker${NC}"
        NO_DOCKER=true
    else
        print_success "Docker is available"
        
        # Check Ollama container
        if docker ps --format '{{.Names}}' | grep -q '^ollama$'; then
            print_success "Ollama container is running"
        elif docker ps -a --format '{{.Names}}' | grep -q '^ollama$'; then
            print_step "Starting Ollama container..."
            docker start ollama
            print_success "Ollama started"
        else
            print_step "Pulling Ollama image..."
            docker pull ollama/ollama
            print_success "Ollama image pulled"
            
            print_step "Starting Ollama container..."
            docker run -d \
                --name ollama \
                -p 11434:11434 \
                -v ollama:/root/.ollama \
                --restart unless-stopped \
                ollama/ollama
            print_success "Ollama container started"
            
            sleep 3
        fi
        
        # Check model
        print_step "Checking for $MODEL model..."
        if docker exec ollama ollama list 2>/dev/null | grep -q "$MODEL"; then
            print_success "Model $MODEL is installed"
        else
            print_step "Pulling $MODEL model (this may take a few minutes)..."
            echo -e "  ${DIM}Model size: ~4GB for mistral, ~2GB for phi${NC}"
            docker exec ollama ollama pull "$MODEL"
            print_success "Model $MODEL installed"
        fi
    fi
else
    print_warning "Skipping Docker/Ollama setup (--no-docker)"
fi

# Setup Watch Service
if [ "$SKIP_WATCH" = false ]; then
    print_header "Setting up Cortex Watch Service"
    
    print_step "Installing watch service..."
    cortex watch --install --service 2>/dev/null || {
        # Manual installation if CLI fails
        mkdir -p ~/.config/systemd/user
        
        # Get Python path
        PYTHON_PATH=$(which python3)
        CORTEX_PATH=$(which cortex 2>/dev/null || echo "$HOME/.local/bin/cortex")
        
        cat > ~/.config/systemd/user/cortex-watch.service << EOF
[Unit]
Description=Cortex Terminal Watch Service
After=default.target

[Service]
Type=simple
ExecStart=$PYTHON_PATH -m cortex.watch_service
Restart=always
RestartSec=5
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
WorkingDirectory=$HOME

[Install]
WantedBy=default.target
EOF
        
        systemctl --user daemon-reload
        systemctl --user enable cortex-watch.service
        systemctl --user start cortex-watch.service
    }
    
    sleep 2
    
    if systemctl --user is-active cortex-watch.service &> /dev/null; then
        print_success "Watch service is running"
    else
        print_warning "Watch service installed but may need attention"
        echo -e "  ${DIM}Check with: systemctl --user status cortex-watch.service${NC}"
    fi
else
    print_warning "Skipping watch service (--skip-watch)"
fi

# Setup Shell Hooks
print_header "Setting up Shell Hooks"

CORTEX_DIR="$HOME/.cortex"
mkdir -p "$CORTEX_DIR"

# Create watch hook
print_step "Creating watch hook script..."
cat > "$CORTEX_DIR/watch_hook.sh" << 'EOF'
#!/bin/bash
# Cortex Terminal Watch Hook

__cortex_last_histnum=""
__cortex_log_cmd() {
    local histnum="$(history 1 | awk '{print $1}')"
    [[ "$histnum" == "$__cortex_last_histnum" ]] && return
    __cortex_last_histnum="$histnum"
    
    local cmd="$(history 1 | sed "s/^[ ]*[0-9]*[ ]*//")"
    [[ -z "${cmd// /}" ]] && return
    [[ "$cmd" == cortex* ]] && return
    [[ "$cmd" == *"source"*".cortex"* ]] && return
    [[ "$cmd" == *"watch_hook"* ]] && return
    [[ -n "$CORTEX_TERMINAL" ]] && return
    
    local tty_name="$(tty 2>/dev/null | sed 's|/dev/||' | tr '/' '_')"
    echo "${tty_name:-unknown}|$cmd" >> ~/.cortex/terminal_watch.log
}
export PROMPT_COMMAND='history -a; __cortex_log_cmd'
echo "✓ Cortex is now watching this terminal"
EOF
chmod +x "$CORTEX_DIR/watch_hook.sh"
print_success "Created watch hook script"

# Add to .bashrc
MARKER="# Cortex Terminal Watch Hook"
if [ -f ~/.bashrc ]; then
    if ! grep -q "$MARKER" ~/.bashrc; then
        print_step "Adding hook to .bashrc..."
        cat >> ~/.bashrc << 'EOF'

# Cortex Terminal Watch Hook
__cortex_last_histnum=""
__cortex_log_cmd() {
    local histnum="$(history 1 | awk '{print $1}')"
    [[ "$histnum" == "$__cortex_last_histnum" ]] && return
    __cortex_last_histnum="$histnum"
    
    local cmd="$(history 1 | sed "s/^[ ]*[0-9]*[ ]*//")"
    [[ -z "${cmd// /}" ]] && return
    [[ "$cmd" == cortex* ]] && return
    [[ "$cmd" == *"source"*".cortex"* ]] && return
    [[ "$cmd" == *"watch_hook"* ]] && return
    [[ -n "$CORTEX_TERMINAL" ]] && return
    
    local tty_name="$(tty 2>/dev/null | sed 's|/dev/||' | tr '/' '_')"
    echo "${tty_name:-unknown}|$cmd" >> ~/.cortex/terminal_watch.log
}
export PROMPT_COMMAND='history -a; __cortex_log_cmd'

alias cw="source ~/.cortex/watch_hook.sh"
EOF
        print_success "Hook added to .bashrc"
    else
        print_success "Hook already in .bashrc"
    fi
fi

# Check API keys
print_header "Checking API Keys"

HAS_API_KEY=false
if [ -n "$ANTHROPIC_API_KEY" ]; then
    print_success "ANTHROPIC_API_KEY found in environment"
    HAS_API_KEY=true
fi
if [ -n "$OPENAI_API_KEY" ]; then
    print_success "OPENAI_API_KEY found in environment"
    HAS_API_KEY=true
fi
if [ -f ".env" ]; then
    if grep -q "ANTHROPIC_API_KEY" .env || grep -q "OPENAI_API_KEY" .env; then
        print_success "API key(s) found in .env file"
        HAS_API_KEY=true
    fi
fi

if [ "$HAS_API_KEY" = false ] && [ "$NO_DOCKER" = true ]; then
    print_warning "No API keys found and Ollama not set up"
    echo -e "  ${DIM}Set ANTHROPIC_API_KEY or OPENAI_API_KEY for cloud LLM${NC}"
fi

# Verify
print_header "Verification"

print_step "Checking cortex command..."
if cortex --version &> /dev/null; then
    print_success "Cortex: $(cortex --version 2>&1)"
else
    print_error "Cortex command not working"
fi

print_step "Checking watch service..."
if systemctl --user is-active cortex-watch.service &> /dev/null; then
    print_success "Watch service: running"
else
    print_warning "Watch service: not running"
fi

if [ "$NO_DOCKER" = false ]; then
    print_step "Checking Ollama..."
    if docker ps --format '{{.Names}}' | grep -q '^ollama$'; then
        print_success "Ollama: running"
        MODELS=$(docker exec ollama ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ', ' | sed 's/,$//')
        if [ -n "$MODELS" ]; then
            print_success "Models: $MODELS"
        fi
    else
        print_warning "Ollama: not running"
    fi
fi

# Final message
print_header "Setup Complete! 🎉"

echo -e "${GREEN}Everything is ready!${NC}"
echo ""
echo -e "${BOLD}To use Cortex ask --do:${NC}"
echo "  cortex ask --do"
echo ""
echo -e "${BOLD}To start an interactive session:${NC}"
echo "  cortex ask --do \"install nginx and configure it\""
echo ""
echo -e "${BOLD}For terminal monitoring in existing terminals:${NC}"
echo "  source ~/.cortex/watch_hook.sh"
echo -e "  ${DIM}(or just type 'cw' after opening a new terminal)${NC}"
echo ""
echo -e "${BOLD}To check status:${NC}"
echo "  cortex watch --status"
echo ""

