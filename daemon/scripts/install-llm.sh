#!/bin/bash
# Install script for Cortex LLM Service (llama.cpp server)
# This script installs cortex-llm.service as a separate systemd service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAEMON_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_FILE="$DAEMON_DIR/systemd/cortex-llm.service"
ENV_FILE="/etc/cortex/llm.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${CYAN}[*]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check if llama-server is installed
check_llama_server() {
    if ! command -v llama-server &> /dev/null; then
        print_warning "llama-server not found in PATH"
        print_status "You can install it from: https://github.com/ggerganov/llama.cpp"
        print_status "Or install via package manager if available"
        
        # Check common locations
        if [[ -f /usr/local/bin/llama-server ]]; then
            print_success "Found llama-server at /usr/local/bin/llama-server"
            return 0
        fi
        
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        print_success "llama-server found: $(which llama-server)"
    fi
}

# Create environment file
create_env_file() {
    local model_path="${1:-}"
    local threads="${2:-4}"
    local ctx_size="${3:-2048}"
    
    print_status "Creating environment file: $ENV_FILE"
    
    mkdir -p /etc/cortex
    
    cat > "$ENV_FILE" << EOF
# Cortex LLM Service Configuration
# This file is used by cortex-llm.service

# Path to the GGUF model file (REQUIRED)
CORTEX_LLM_MODEL_PATH=${model_path}

# Number of CPU threads for inference (default: 4)
CORTEX_LLM_THREADS=${threads}

# Context size in tokens (default: 2048)
CORTEX_LLM_CTX_SIZE=${ctx_size}
EOF

    chmod 600 "$ENV_FILE"
    print_success "Environment file created"
}

# Install systemd service
install_service() {
    print_status "Installing cortex-llm.service..."
    
    if [[ ! -f "$SERVICE_FILE" ]]; then
        print_error "Service file not found: $SERVICE_FILE"
        exit 1
    fi
    
    # Copy service file
    cp "$SERVICE_FILE" /etc/systemd/system/cortex-llm.service
    
    # Reload systemd
    systemctl daemon-reload
    
    print_success "Service installed: cortex-llm.service"
}

# Enable and start service
enable_service() {
    print_status "Enabling cortex-llm.service..."
    systemctl enable cortex-llm.service
    print_success "Service enabled"
}

start_service() {
    print_status "Starting cortex-llm.service..."
    
    # Check if model path is configured
    if [[ -f "$ENV_FILE" ]]; then
        source "$ENV_FILE"
        if [[ -z "$CORTEX_LLM_MODEL_PATH" || ! -f "$CORTEX_LLM_MODEL_PATH" ]]; then
            print_warning "Model path not configured or file not found"
            print_status "Configure model path in $ENV_FILE before starting"
            print_status "Then run: sudo systemctl start cortex-llm"
            return 0
        fi
    fi
    
    systemctl start cortex-llm.service
    
    # Wait a moment and check status
    sleep 2
    if systemctl is-active --quiet cortex-llm.service; then
        print_success "Service started successfully"
    else
        print_warning "Service may have failed to start. Check logs:"
        print_status "  journalctl -u cortex-llm -f"
    fi
}

# Show status
show_status() {
    echo
    print_status "Service Status:"
    systemctl status cortex-llm.service --no-pager || true
    echo
    print_status "Configuration: $ENV_FILE"
    if [[ -f "$ENV_FILE" ]]; then
        cat "$ENV_FILE"
    fi
}

# Uninstall service
uninstall_service() {
    print_status "Uninstalling cortex-llm.service..."
    
    # Stop if running
    systemctl stop cortex-llm.service 2>/dev/null || true
    
    # Disable
    systemctl disable cortex-llm.service 2>/dev/null || true
    
    # Remove files
    rm -f /etc/systemd/system/cortex-llm.service
    
    # Reload systemd
    systemctl daemon-reload
    
    print_success "Service uninstalled"
    print_status "Environment file kept at: $ENV_FILE"
    print_status "Remove manually if needed: sudo rm $ENV_FILE"
}

# Usage
usage() {
    echo "Usage: $0 [command] [options]"
    echo
    echo "Commands:"
    echo "  install [model_path] [threads] [ctx_size]  Install and configure service"
    echo "  uninstall                                   Remove service"
    echo "  status                                      Show service status"
    echo "  configure <model_path> [threads] [ctx_size] Update configuration"
    echo
    echo "Examples:"
    echo "  $0 install ~/.cortex/models/phi-2.gguf 4 2048"
    echo "  $0 configure /path/to/model.gguf 8"
    echo "  $0 status"
    echo "  $0 uninstall"
}

# Main
main() {
    local command="${1:-install}"
    
    case "$command" in
        install)
            check_root
            check_llama_server
            create_env_file "${2:-}" "${3:-4}" "${4:-2048}"
            install_service
            enable_service
            start_service
            show_status
            ;;
        uninstall)
            check_root
            uninstall_service
            ;;
        status)
            show_status
            ;;
        configure)
            check_root
            if [[ -z "$2" ]]; then
                print_error "Model path required"
                usage
                exit 1
            fi
            create_env_file "$2" "${3:-4}" "${4:-2048}"
            print_status "Restarting service..."
            systemctl restart cortex-llm.service || true
            show_status
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            print_error "Unknown command: $command"
            usage
            exit 1
            ;;
    esac
}

main "$@"

