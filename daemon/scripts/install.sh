#!/bin/bash
# Installation script for cortexd daemon

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

echo "=== Installing cortexd ==="

# Check if built
if [ ! -f "$BUILD_DIR/cortexd" ]; then
    echo "Error: cortexd binary not found."
    echo "Run: ./scripts/build.sh"
    exit 1
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Installation requires root privileges"
    echo "Please run: sudo ./scripts/install.sh"
    exit 1
fi

# Get the actual user who invoked sudo (not root)
INSTALL_USER="${SUDO_USER:-$USER}"
if [ "$INSTALL_USER" = "root" ]; then
    # Try to get the user from logname if SUDO_USER is not set
    INSTALL_USER=$(logname 2>/dev/null || echo "root")
fi

# Stop existing service if running
if systemctl is-active --quiet cortexd 2>/dev/null; then
    echo "Stopping existing cortexd service..."
    systemctl stop cortexd
fi

# Install binary
echo "Installing binary to /usr/local/bin..."
install -m 0755 "$BUILD_DIR/cortexd" /usr/local/bin/cortexd

# Install systemd files
# Note: We only install the service file, not a socket file.
# The daemon manages its own socket to avoid conflicts with systemd socket activation.
echo "Installing systemd service files..."
install -m 0644 "$SCRIPT_DIR/systemd/cortexd.service" /etc/systemd/system/

# Create config directory
echo "Creating configuration directory..."
mkdir -p /etc/cortex
if [ ! -f /etc/cortex/daemon.yaml ]; then
    # SCRIPT_DIR points to daemon/, so config is at daemon/config/
    install -m 0644 "$SCRIPT_DIR/config/cortexd.yaml.example" /etc/cortex/daemon.yaml
    echo "  Created default config: /etc/cortex/daemon.yaml"
fi

# Create cortex group for socket access
echo "Setting up cortex group for socket access..."
if ! getent group cortex >/dev/null 2>&1; then
    groupadd cortex
    echo "  Created 'cortex' group"
else
    echo "  Group 'cortex' already exists"
fi

# Add the installing user to the cortex group
if [ "$INSTALL_USER" != "root" ]; then
    if id -nG "$INSTALL_USER" | grep -qw cortex; then
        echo "  User '$INSTALL_USER' is already in 'cortex' group"
    else
        usermod -aG cortex "$INSTALL_USER"
        echo "  Added user '$INSTALL_USER' to 'cortex' group"
        GROUP_ADDED=1
    fi
fi

# Create state directories
echo "Creating state directories..."
mkdir -p /var/lib/cortex
chown root:cortex /var/lib/cortex
chmod 0750 /var/lib/cortex

mkdir -p /run/cortex
chown root:cortex /run/cortex
chmod 0755 /run/cortex

# Create user config directory for installing user
if [ "$INSTALL_USER" != "root" ]; then
    INSTALL_USER_HOME=$(getent passwd "$INSTALL_USER" | cut -d: -f6)
    if [ -n "$INSTALL_USER_HOME" ]; then
        mkdir -p "$INSTALL_USER_HOME/.cortex"
        chown "$INSTALL_USER:$INSTALL_USER" "$INSTALL_USER_HOME/.cortex"
        chmod 0700 "$INSTALL_USER_HOME/.cortex"
    fi
fi

# Also create root's config directory
mkdir -p /root/.cortex
chmod 0700 /root/.cortex

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable service
echo "Enabling cortexd service..."
systemctl enable cortexd

# Start service
echo "Starting cortexd service..."
if systemctl start cortexd; then
    echo ""
    echo "=== Installation Complete ==="
    echo ""
    systemctl status cortexd --no-pager || true
    echo ""
    echo "Commands:"
    echo "  Status:   systemctl status cortexd"
    echo "  Logs:     journalctl -u cortexd -f"
    echo "  Stop:     systemctl stop cortexd"
    echo "  Config:   /etc/cortex/daemon.yaml"
    
else
    echo ""
    echo "=== Installation Complete (service failed to start) ==="
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check logs: journalctl -xeu cortexd -n 50"
    echo "  2. Verify binary: /usr/local/bin/cortexd --version"
    echo "  3. Check config: cat /etc/cortex/daemon.yaml"
    echo ""
    exit 1
fi
