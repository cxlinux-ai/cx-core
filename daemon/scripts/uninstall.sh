#!/bin/bash
# Uninstallation script for cortexd daemon

set -e

echo "=== Uninstalling cortexd ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Uninstallation requires root privileges"
    echo "Please run: sudo ./daemon/scripts/uninstall.sh"
    exit 1
fi

# Stop service
echo "Stopping cortexd service..."
systemctl stop cortexd || true

# Disable service
echo "Disabling cortexd service..."
systemctl disable cortexd || true

# Remove systemd files
echo "Removing systemd configuration..."
rm -f /etc/systemd/system/cortexd.service
rm -f /etc/systemd/system/cortexd.socket
systemctl daemon-reload || true

# Remove binary
echo "Removing binary..."
rm -f /usr/local/bin/cortexd

# Remove configuration
echo "Removing configuration..."
rm -f /etc/default/cortexd

# Clean up runtime files
echo "Cleaning up runtime files..."
rm -f /run/cortex.sock
rm -rf /run/cortex || true

echo ""
echo "✓ Uninstallation complete!"
