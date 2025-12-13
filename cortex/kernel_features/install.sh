#!/bin/bash
# Cortex Linux Kernel Features Installer
# 
# Installs sysctl tuning, systemd templates, and helper scripts
# for LLM-optimized system configuration.
#
# Usage:
#   sudo ./install.sh          # Full install
#   sudo ./install.sh --sysctl # Sysctl only
#   sudo ./install.sh --remove # Uninstall

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-/usr}"
SYSCONFDIR="${SYSCONFDIR:-/etc}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root: sudo $0"
        exit 1
    fi
}

# Install sysctl configuration
install_sysctl() {
    log_info "Installing sysctl configuration..."
    
    mkdir -p "$SYSCONFDIR/sysctl.d"
    cp "$SCRIPT_DIR/sysctl.d/99-cortex-llm.conf" "$SYSCONFDIR/sysctl.d/"
    chmod 644 "$SYSCONFDIR/sysctl.d/99-cortex-llm.conf"
    
    log_info "Applying sysctl settings..."
    sysctl -p "$SYSCONFDIR/sysctl.d/99-cortex-llm.conf" || {
        log_warn "Some sysctl settings may not have applied (this is normal on some systems)"
    }
    
    log_info "Sysctl configuration installed"
}

# Install systemd service templates
install_systemd() {
    log_info "Installing systemd templates..."
    
    SYSTEMD_DIR="$PREFIX/lib/systemd/system"
    mkdir -p "$SYSTEMD_DIR"
    
    cp "$SCRIPT_DIR/systemd/cortex-model@.service" "$SYSTEMD_DIR/"
    cp "$SCRIPT_DIR/systemd/cortex-inference.slice" "$SYSTEMD_DIR/"
    chmod 644 "$SYSTEMD_DIR/cortex-model@.service"
    chmod 644 "$SYSTEMD_DIR/cortex-inference.slice"
    
    # Create service user if it doesn't exist
    if ! id "cortex-llm" &>/dev/null; then
        log_info "Creating cortex-llm service user..."
        useradd -r -s /bin/false -d /var/lib/cortex cortex-llm || true
    fi
    
    # Create directories
    mkdir -p /var/lib/cortex/models
    mkdir -p /run/cortex
    mkdir -p "$SYSCONFDIR/cortex"
    chown -R cortex-llm:cortex-llm /var/lib/cortex
    chown -R cortex-llm:cortex-llm /run/cortex
    
    # Reload systemd
    systemctl daemon-reload
    
    log_info "Systemd templates installed"
    log_info "Usage: systemctl start cortex-model@<model-name>"
}

# Install helper scripts
install_scripts() {
    log_info "Installing helper scripts..."
    
    BIN_DIR="$PREFIX/bin"
    mkdir -p "$BIN_DIR"
    
    # Install scripts
    for script in cortex-model-validate cortex-gpu-warmup cortex-gpu-cleanup; do
        if [ -f "$SCRIPT_DIR/bin/$script" ]; then
            cp "$SCRIPT_DIR/bin/$script" "$BIN_DIR/"
            chmod 755 "$BIN_DIR/$script"
        fi
    done
    
    # Install Python modules
    if [ -f "$SCRIPT_DIR/hardware_detect.py" ]; then
        cp "$SCRIPT_DIR/hardware_detect.py" "$BIN_DIR/cortex-detect-hardware"
        chmod 755 "$BIN_DIR/cortex-detect-hardware"
    fi
    
    log_info "Helper scripts installed"
}

# Install eBPF scheduler
install_ebpf() {
    log_info "Installing eBPF scheduler..."
    
    EBPF_DIR="$PREFIX/share/cortex/ebpf"
    mkdir -p "$EBPF_DIR"
    
    if [ -d "$SCRIPT_DIR/ebpf" ]; then
        cp "$SCRIPT_DIR/ebpf/"* "$EBPF_DIR/"
        chmod 755 "$EBPF_DIR/cortex_sched_loader.py"
        
        # Create symlink for easy access
        ln -sf "$EBPF_DIR/cortex_sched_loader.py" "$PREFIX/bin/cortex-sched"
    fi
    
    log_info "eBPF scheduler installed"
    log_info "Usage: sudo cortex-sched start"
}

# Configure huge pages
configure_hugepages() {
    log_info "Configuring huge pages..."
    
    # Check available memory
    TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    TOTAL_MEM_GB=$((TOTAL_MEM_KB / 1024 / 1024))
    
    # Allocate 25% of RAM to huge pages (max 16GB)
    HUGEPAGES=$((TOTAL_MEM_GB * 1024 / 4 / 2))  # 25% of RAM in 2MB pages
    if [ "$HUGEPAGES" -gt 8192 ]; then
        HUGEPAGES=8192  # Max 16GB
    fi
    
    log_info "System has ${TOTAL_MEM_GB}GB RAM, allocating $HUGEPAGES huge pages (${HUGEPAGES}*2MB)"
    
    # Update sysctl
    sed -i "s/vm.nr_hugepages = .*/vm.nr_hugepages = $HUGEPAGES/" \
        "$SYSCONFDIR/sysctl.d/99-cortex-llm.conf" 2>/dev/null || true
    
    # Apply
    echo "$HUGEPAGES" > /proc/sys/vm/nr_hugepages 2>/dev/null || true
    
    # Add to GRUB for persistence
    if [ -f /etc/default/grub ]; then
        if ! grep -q "hugepages=" /etc/default/grub; then
            log_info "Adding hugepages to GRUB config..."
            sed -i "s/GRUB_CMDLINE_LINUX=\"/GRUB_CMDLINE_LINUX=\"hugepages=$HUGEPAGES /" \
                /etc/default/grub
            log_warn "Run 'update-grub' and reboot for huge pages to persist"
        fi
    fi
}

# Full installation
install_all() {
    log_info "=== Cortex Linux Kernel Features Installer ==="
    echo
    
    install_sysctl
    install_systemd
    install_scripts
    install_ebpf
    configure_hugepages
    
    echo
    log_info "=== Installation Complete ==="
    echo
    echo "Installed components:"
    echo "  ✓ Sysctl LLM optimization profile"
    echo "  ✓ Systemd model.service template"
    echo "  ✓ Helper scripts (cortex-model-validate, cortex-gpu-warmup, etc.)"
    echo "  ✓ eBPF ML scheduler"
    echo "  ✓ Huge page configuration"
    echo
    echo "Quick start:"
    echo "  cortex-detect-hardware          # Detect GPUs/NPUs"
    echo "  sudo cortex-sched start         # Start ML scheduler"
    echo "  systemctl start cortex-model@llama3-8b  # Start a model"
    echo
    echo "Documentation: /usr/share/doc/cortex/KERNEL_CONFIG.md"
}

# Remove installation
remove_all() {
    log_info "Removing Cortex kernel features..."
    
    rm -f "$SYSCONFDIR/sysctl.d/99-cortex-llm.conf"
    rm -f "$PREFIX/lib/systemd/system/cortex-model@.service"
    rm -f "$PREFIX/lib/systemd/system/cortex-inference.slice"
    rm -f "$PREFIX/bin/cortex-model-validate"
    rm -f "$PREFIX/bin/cortex-gpu-warmup"
    rm -f "$PREFIX/bin/cortex-gpu-cleanup"
    rm -f "$PREFIX/bin/cortex-detect-hardware"
    rm -f "$PREFIX/bin/cortex-sched"
    rm -rf "$PREFIX/share/cortex/ebpf"
    
    systemctl daemon-reload
    
    log_info "Removal complete"
}

# Parse arguments
case "${1:-all}" in
    --sysctl)
        check_root
        install_sysctl
        ;;
    --systemd)
        check_root
        install_systemd
        ;;
    --scripts)
        check_root
        install_scripts
        ;;
    --ebpf)
        check_root
        install_ebpf
        ;;
    --hugepages)
        check_root
        configure_hugepages
        ;;
    --remove)
        check_root
        remove_all
        ;;
    all|--all)
        check_root
        install_all
        ;;
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo
        echo "Options:"
        echo "  --all       Full installation (default)"
        echo "  --sysctl    Install sysctl tuning only"
        echo "  --systemd   Install systemd templates only"
        echo "  --scripts   Install helper scripts only"
        echo "  --ebpf      Install eBPF scheduler only"
        echo "  --hugepages Configure huge pages only"
        echo "  --remove    Remove all installed components"
        echo "  --help      Show this help"
        ;;
    *)
        log_error "Unknown option: $1"
        exit 1
        ;;
esac
