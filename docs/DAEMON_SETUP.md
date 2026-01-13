# Cortexd Daemon - Setup & Usage Guide

## Quick Start

### Installation (One Command)

```bash
# Build and install cortexd
cd /path/to/cortex
sudo ./daemon/scripts/install.sh

# Verify installation
cortex daemon status
```

### Uninstallation

```bash
sudo ./daemon/scripts/uninstall.sh
```

## Manual Installation

If you prefer manual installation or the scripts don't work:

```bash
# 1. Build the daemon (see DAEMON_BUILD.md)
cd daemon
./scripts/build.sh Release

# 2. Copy binary
sudo install -m 0755 build/cortexd /usr/local/bin/

# 3. Install systemd service
sudo install -m 0644 systemd/cortexd.service /etc/systemd/system/
sudo install -m 0644 systemd/cortexd.socket /etc/systemd/system/

# 4. Configure
sudo mkdir -p /etc/default
sudo install -m 0644 config/cortexd.default /etc/default/cortexd

# 5. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable cortexd
sudo systemctl start cortexd

# 6. Verify
systemctl status cortexd
```

## Configuration

### Default Configuration Location

- **Systemd**: `/etc/systemd/system/cortexd.service`
- **System Config**: `/etc/cortex/daemon.yaml`
- **User Config**: `~/.cortex/daemon.yaml`
- **Runtime Socket**: `/run/cortex/cortex.sock`
- **Logs**: `journalctl -u cortexd`

### Configuration File Format

Create `~/.cortex/daemon.yaml` or `/etc/cortex/daemon.yaml`:

```yaml
# Cortexd Daemon Configuration

# Socket configuration
socket:
  path: /run/cortex/cortex.sock
  backlog: 16
  timeout_ms: 5000

# LLM configuration
llm:
  # Backend type: "local", "cloud_claude", "cloud_openai", or "none"
  backend: "none"
  
  # Local llama.cpp configuration (when backend: local)
  local:
    base_url: "http://127.0.0.1:8085"
  
  # Legacy embedded LLM settings (deprecated)
  model_path: ""
  context_length: 2048
  threads: 4

# System monitoring configuration
monitoring:
  interval_sec: 300
  enable_apt: true
  enable_cve: true
  enable_deps: true

# Alert thresholds (0.0 - 1.0)
thresholds:
  disk_warn: 0.80
  disk_crit: 0.95
  mem_warn: 0.85
  mem_crit: 0.95

# Alert configuration
alerts:
  db_path: ~/.cortex/alerts.db
  retention_hours: 168
  enable_ai: true

# Rate limiting
rate_limit:
  max_requests_per_sec: 100
  max_inference_queue: 100

# Logging level (0=DEBUG, 1=INFO, 2=WARN, 3=ERROR)
log_level: 1
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `socket.path` | string | `/run/cortex/cortex.sock` | Unix socket path |
| `socket.timeout_ms` | int | 5000 | Socket timeout in milliseconds |
| `llm.backend` | string | `none` | LLM backend: `local`, `cloud_claude`, `cloud_openai`, or `none` |
| `llm.local.base_url` | string | `http://127.0.0.1:8085` | URL for local llama.cpp server |
| `llm.model_path` | string | (empty) | Path to GGUF model (legacy) |
| `llm.threads` | int | 4 | Number of threads for LLM inference |
| `llm.context_length` | int | 2048 | Context window size for LLM |
| `monitoring.interval_sec` | int | 300 | System monitoring check interval |
| `monitoring.enable_cve` | bool | true | Enable CVE vulnerability scanning |
| `monitoring.enable_apt` | bool | true | Enable APT package monitoring |
| `alerts.enable_ai` | bool | true | Enable AI-enhanced alerts with LLM analysis |
| `alerts.db_path` | string | `~/.cortex/alerts.db` | SQLite database for alert persistence |
| `log_level` | int | 1 | Log level (0=DEBUG, 1=INFO, 2=WARN, 3=ERROR) |

## LLM Model Setup

### Getting a Model

Download a GGUF format model (quantized for efficiency):

```bash
# Create models directory
mkdir -p ~/.cortex/models

# Download example models:
# Option 1: Mistral 7B (6.5GB)
wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/main/Mistral-7B-Instruct-v0.1.Q4_K_M.gguf \
  -O ~/.cortex/models/mistral-7b.gguf

# Option 2: Llama 2 7B (3.8GB)
wget https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf \
  -O ~/.cortex/models/llama2-7b.gguf

# Option 3: Phi 2.7B (1.6GB, fastest)
wget https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf \
  -O ~/.cortex/models/phi-2.7b.gguf
```

### Recommended Models

| Model | Size | Speed | Memory | Command |
|-------|------|-------|--------|---------|
| **Phi 2.7B** | 1.6GB | Fast | 2-3GB | Recommended for servers |
| **Mistral 7B** | 6.5GB | Medium | 8-12GB | Good balance |
| **Llama 2 7B** | 3.8GB | Medium | 5-8GB | Quality focused |
| **Orca Mini** | 1.3GB | Very Fast | 2GB | For low-end systems |

### Configure Model Path

Update `~/.cortex/daemon.yaml`:

```yaml
llm:
  backend: "local"
  local:
    base_url: "http://127.0.0.1:8085"
  # Or use embedded model (legacy):
  model_path: ~/.cortex/models/mistral-7b.gguf
  threads: 4
  context_length: 2048
```

Or set environment variable:
```bash
export CORTEXD_MODEL_PATH="$HOME/.cortex/models/mistral-7b.gguf"
```

### Test Model Loading

```bash
# Check if daemon can load model
cortex daemon health

# Watch logs during inference
journalctl -u cortexd -f
```

## AI-Enhanced Alerts

Cortexd features intelligent, AI-powered alerts that provide actionable recommendations. This feature is **enabled by default** when an LLM model is loaded.

### Features

- **Context-aware analysis**: The LLM receives detailed system metrics for accurate recommendations
- **Type-specific prompts**: Different analysis for disk, memory, and security alerts
- **Actionable suggestions**: Provides specific commands and steps to resolve issues
- **Graceful fallback**: If LLM is unavailable, standard alerts are still generated

### Example

When disk usage exceeds the warning threshold, you'll see:

```
⚠️  High disk usage
Disk usage is at 85% on root filesystem

💡 AI Analysis:
Your disk is filling up quickly. Run `du -sh /* | sort -hr | head -10` 
to find large directories. Consider clearing old logs with 
`sudo journalctl --vacuum-time=7d` or removing unused packages with 
`sudo apt autoremove`.
```

### Configuration

AI alerts are enabled by default. To disable:

```yaml
# In ~/.cortex/daemon.yaml or /etc/cortex/daemon.yaml
alerts:
  enable_ai: false
```

### Viewing AI-Enhanced Alerts

```bash
# View all alerts (AI-enhanced alerts show 💡 AI Analysis section)
cortex daemon alerts

# Check daemon logs to see AI generation
journalctl -u cortexd -f
# Look for: "Generating AI alert analysis..." and "AI analysis generated in XXXms"
```

## Usage

### CLI Commands

#### Check Daemon Status

```bash
# Quick status check
cortex daemon status

# Detailed status with health metrics
cortex daemon status --verbose
```

#### View Health Snapshot

```bash
cortex daemon health
```

Output:
```
Daemon Health Snapshot:
  CPU Usage:          45.2%
  Memory Usage:       28.5%
  Disk Usage:         65.3%
  Active Processes:   156
  Open Files:         128
  LLM Loaded:         Yes
  Inference Queue:    3
  Alert Count:        2
```

#### View Alerts

```bash
# All active alerts
cortex daemon alerts

# Filter by severity
cortex daemon alerts --severity warning
cortex daemon alerts --severity critical

# Acknowledge all alerts
cortex daemon alerts --acknowledge-all

# Dismiss (delete) a specific alert by ID
cortex daemon alerts --dismiss <alert-id>
# Example: cortex daemon alerts --dismiss a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Alert Table:
```
Alerts (5):
[INFO] Disk usage normal (a1b2c3d4...)
[WARNING] Memory usage high - 87% (e5f6g7h8...)
[ERROR] CVE found in openssh (i9j0k1l2...)
[CRITICAL] Dependency conflict (m3n4o5p6...)
[WARNING] APT updates available (q7r8s9t0...)
```

**Note:** The alert ID shown in the table (e.g., `a1b2c3d4...`) is truncated. Use the full UUID when dismissing alerts.

#### Install/Uninstall Daemon

```bash
# Install and start daemon
cortex daemon install

# Uninstall and stop daemon
cortex daemon uninstall
```

#### Reload Configuration

```bash
cortex daemon reload-config
```

### System Service Management

Using systemd directly:

```bash
# Start daemon
sudo systemctl start cortexd

# Stop daemon
sudo systemctl stop cortexd

# Restart daemon
sudo systemctl restart cortexd

# Check status
systemctl status cortexd

# View logs
journalctl -u cortexd -f

# Show recent errors
journalctl -u cortexd --since "1 hour ago" -p err

# Enable/disable auto-start
sudo systemctl enable cortexd
sudo systemctl disable cortexd
```

## Monitoring

### Check Daemon Logs

```bash
# Real-time logs
journalctl -u cortexd -f

# Last 50 lines
journalctl -u cortexd -n 50

# Errors only
journalctl -u cortexd -p err

# Last hour
journalctl -u cortexd --since "1 hour ago"

# With timestamps
journalctl -u cortexd -o short-precise
```

### System Resource Usage

```bash
# Monitor daemon memory
watch -n 1 "ps aux | grep cortexd"

# Check file descriptors
lsof -p $(pgrep cortexd)

# Verify socket
ss -lp | grep cortex/cortex.sock
# or
netstat -lp | grep cortex
```

### Integration with Monitoring Tools

#### Prometheus

```yaml
# Example prometheus scrape config
scrape_configs:
  - job_name: 'cortexd'
    static_configs:
      - targets: ['localhost:9100']
    metric_path: '/metrics'
```

#### CloudWatch (AWS)

```bash
# Log daemon to CloudWatch
journalctl -u cortexd --since "1 hour ago" | aws logs put-log-events \
  --log-group-name /cortex/daemon \
  --log-stream-name $(hostname) \
  --log-events time=$(date +%s000),message='...'
```

## Troubleshooting

### Daemon Won't Start

```bash
# Check systemd status
systemctl status cortexd

# Check logs for errors
journalctl -u cortexd -e

# Try running in foreground
/usr/local/bin/cortexd --verbose

# Verify socket isn't already in use
lsof /run/cortex/cortex.sock
```

### Socket Connection Issues

```bash
# Verify socket exists
ls -la /run/cortex/cortex.sock

# Check permissions
stat /run/cortex/cortex.sock
# Should be: Access: (0666/-rw-rw-rw-) Uid: ( 0/ root) Gid: ( 0/ root)

# Test socket manually
echo '{"method":"health"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock
```

### High Memory Usage

```bash
# Check current usage
ps aux | grep cortexd

# Reduce model size in config
# OR adjust memory_limit_mb in daemon.conf

# Restart daemon
sudo systemctl restart cortexd
```

### CLI Commands Not Working

```bash
# Verify daemon is running
systemctl is-active cortexd

# Try direct socket test
socat - UNIX-CONNECT:/run/cortex/cortex.sock <<< '{"method":"status"}'

# Check Python client library
python3 -c "from cortex.daemon_client import CortexDaemonClient; c = CortexDaemonClient(); print(c.is_running())"
```

## Performance Optimization

### Reduce CPU Usage

```yaml
# In ~/.cortex/daemon.yaml
monitoring:
  interval_sec: 600        # Increase from 300
  enable_cve: false        # Disable if not needed
```

### Reduce Memory Usage

```yaml
# In ~/.cortex/daemon.yaml
rate_limit:
  max_inference_queue: 50  # Reduce from 100
```

### Improve Response Time

```yaml
# In ~/.cortex/daemon.yaml
log_level: 2               # Reduce debug logging (INFO=1, WARN=2)
```

## Security

### Socket Permissions

The daemon socket is created with `0666` permissions (world-readable/writable):

```bash
ls -la /run/cortex/cortex.sock
# srw-rw-rw- 1 root root 0 Jan  2 10:30 /run/cortex/cortex.sock=
```

To restrict access to a specific group:

```bash
# Create cortex group
sudo groupadd cortex

# Add users to group
sudo usermod -aG cortex $USER

# Update daemon.conf to use restrictive permissions
# (requires daemon modification)
```

### Firewall Rules

The daemon uses only Unix domain sockets (local-only communication):

```bash
# Verify no network listening
sudo ss -tlnp | grep cortexd
# Should return nothing (good - Unix socket only)
```

## Backup and Recovery

### Backup Configuration

```bash
# Backup daemon config
cp ~/.cortex/daemon.yaml ~/.cortex/daemon.yaml.backup

# Backup system service file
sudo cp /etc/systemd/system/cortexd.service ~/cortexd.service.backup
```

### Reset to Defaults

```bash
# Remove user config (uses system defaults)
rm ~/.cortex/daemon.yaml

# Restart daemon
sudo systemctl restart cortexd
```

## Performance Targets

After installation, verify daemon meets performance targets:

| Metric | Target | How to Check |
|--------|--------|-------------|
| Startup time | < 1s | `time systemctl start cortexd` |
| Idle memory | ≤ 50MB | `ps aux \| grep cortexd` |
| Active memory | ≤ 150MB | During inference: `watch ps aux` |
| Cached inference | < 100ms | `cortex daemon health` |
| Socket latency | < 50ms | `time echo '...' \| socat ...` |

## Uninstallation

### Clean Uninstall

```bash
# Method 1: Using script
sudo ./daemon/scripts/uninstall.sh

# Method 2: Manual
sudo systemctl stop cortexd
sudo systemctl disable cortexd
sudo rm -f /usr/local/bin/cortexd
sudo rm -f /etc/systemd/system/cortexd.service
sudo rm -f /etc/systemd/system/cortexd.socket
sudo rm -f /etc/default/cortexd
sudo systemctl daemon-reload
rm -rf ~/.cortex/daemon.yaml
```

## Upgrade Cortexd

```bash
# Stop current daemon
sudo systemctl stop cortexd

# Build new version (see DAEMON_BUILD.md)
cd daemon
./scripts/build.sh Release

# Backup current binary
sudo cp /usr/local/bin/cortexd /usr/local/bin/cortexd.backup

# Install new binary
sudo install -m 0755 build/cortexd /usr/local/bin/

# Start new version
sudo systemctl start cortexd

# Verify
systemctl status cortexd
```

## Integration with Cortex CLI

The daemon is fully integrated with the Cortex CLI:

```bash
# See daemon status in cortex status
cortex status

# Install via cortex
cortex daemon install

# Manage via cortex
cortex daemon health
cortex daemon alerts
cortex daemon reload-config

# View daemon-related logs
cortex daemon status --verbose
```

## Next Steps

1. **Configure monitoring** - Adjust thresholds in daemon.conf
2. **Setup alerts** - Configure alert routing
3. **Monitor performance** - Use tools in Monitoring section
4. **Integrate with CI/CD** - Deploy to production

## Support & Documentation

- **LLM Setup (Detailed)**: See [LLM_SETUP.md](LLM_SETUP.md) for comprehensive model configuration
- **Build Issues**: See [DAEMON_BUILD.md](DAEMON_BUILD.md)
- **Troubleshooting**: See [DAEMON_TROUBLESHOOTING.md](DAEMON_TROUBLESHOOTING.md)
- **API Reference**: See [DAEMON_API.md](DAEMON_API.md)
- **Architecture**: See [DAEMON_ARCHITECTURE.md](DAEMON_ARCHITECTURE.md)

