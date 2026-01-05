#!/bin/bash
# Installation script for cortexd daemon

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

echo "=== Installing cortexd ==="

# Check if built
if [ ! -f "$BUILD_DIR/cortexd" ]; then
    echo "Error: cortexd binary not found. Run: ./daemon/scripts/build.sh"
    exit 1
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Installation requires root privileges"
    echo "Please run: sudo ./daemon/scripts/install.sh"
    exit 1
fi

echo "Installing binary..."
install -m 0755 "$BUILD_DIR/cortexd" /usr/local/bin/cortexd

echo "Installing systemd service..."
install -m 0644 "$SCRIPT_DIR/systemd/cortexd.service" /etc/systemd/system/
install -m 0644 "$SCRIPT_DIR/systemd/cortexd.socket" /etc/systemd/system/ || true

echo "Installing default configuration..."
mkdir -p /etc/default
install -m 0644 "$SCRIPT_DIR/config/cortexd.default" /etc/default/cortexd || true

echo "Creating log directory..."
mkdir -p /var/log/cortex
chmod 0755 /var/log/cortex

echo "Creating runtime directory..."
mkdir -p /run/cortex
chmod 0755 /run/cortex

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling cortexd service..."
systemctl enable cortexd

echo "Starting cortexd service..."
if ! systemctl start cortexd; then
    echo ""
    echo "✗ Failed to start cortexd service"
    echo ""
    echo "Troubleshooting:"
    echo "1. Check service status: systemctl status cortexd"
    echo "2. View logs: journalctl -xeu cortexd.service -n 50"
    echo "3. Verify binary: ls -lh /usr/local/bin/cortexd"
    exit 1
fi

echo ""
echo "✓ Installation complete!"
echo ""
echo "Service status:"
systemctl status cortexd --no-pager || true
echo ""
echo "View logs: journalctl -u cortexd -f"
echo "Stop service: systemctl stop cortexd"
