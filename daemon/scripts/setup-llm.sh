#!/bin/bash
# Setup LLM for Cortex Daemon

set -e

echo "=== Cortex Daemon LLM Setup ==="
echo ""

# Create directories
echo "Creating directories..."
mkdir -p ~/.cortex/models
mkdir -p /tmp/cortex-setup

# Check if model exists
MODEL_NAME="tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
MODEL_PATH="$HOME/.cortex/models/$MODEL_NAME"

if [ -f "$MODEL_PATH" ]; then
    echo "✓ Model already exists: $MODEL_PATH"
else
    echo "Downloading TinyLlama 1.1B model (~600MB)..."
    echo "This may take a few minutes..."
    cd ~/.cortex/models
    wget -q --show-progress "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/$MODEL_NAME"
    echo "✓ Model downloaded: $MODEL_PATH"
fi

# Create config file
CONFIG_PATH="/etc/cortex/daemon.conf"
echo ""
echo "Creating configuration file..."
sudo mkdir -p /etc/cortex

sudo tee "$CONFIG_PATH" > /dev/null << EOF
# Cortex Daemon Configuration
socket_path: /run/cortex.sock
model_path: $MODEL_PATH
monitoring_interval_seconds: 300
enable_cve_scanning: true
enable_journald_logging: true
log_level: 1
max_inference_queue_size: 100
memory_limit_mb: 150
EOF

echo "✓ Configuration created: $CONFIG_PATH"

# Restart daemon
echo ""
echo "Restarting daemon to load model..."
sudo systemctl restart cortexd
sleep 3

# Check status
echo ""
echo "Checking daemon status..."
if systemctl is-active --quiet cortexd; then
    echo "✓ Daemon is running"
    
    # Check if model loaded
    echo ""
    echo "Checking if model loaded..."
    journalctl -u cortexd -n 50 --no-pager | grep -i "model" | tail -5
    
    echo ""
    echo "=== Setup Complete ==="
    echo ""
    echo "To check LLM status:"
    echo "  cortex daemon health"
    echo ""
    echo "To view logs:"
    echo "  sudo journalctl -u cortexd -f"
else
    echo "✗ Daemon is not running!"
    echo "Check logs: sudo journalctl -u cortexd -n 50"
    exit 1
fi
