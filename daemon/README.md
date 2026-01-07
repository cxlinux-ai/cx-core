# Cortexd - AI-Native System Daemon

**cortexd** is a production-grade C++ daemon for the Cortex AI Package Manager. It provides persistent system monitoring, embedded LLM inference via llama.cpp, and a Unix socket API for CLI integration.

## Features

- 🚀 **Fast Startup**: < 1 second startup time
- 💾 **Low Memory**: < 50MB idle, < 150MB with model loaded
- 🔌 **Unix Socket IPC**: JSON-RPC protocol at `/run/cortex.sock`
- 🤖 **Embedded LLM**: llama.cpp integration for local inference
- 📊 **System Monitoring**: CPU, memory, disk, APT updates, CVE scanning
- 🔔 **Smart Alerts**: SQLite-persisted alerts with deduplication
- ⚙️ **systemd Integration**: Type=notify, watchdog, journald logging

## Quick Start

### Build

```bash
cd daemon
./scripts/build.sh Release
```

### Install

```bash
sudo ./scripts/install.sh
```

### Verify

```bash
# Check status
systemctl status cortexd

# View logs
journalctl -u cortexd -f

# Test socket
echo '{"method":"ping"}' | socat - UNIX-CONNECT:/run/cortex.sock
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     cortex CLI (Python)                      │
└───────────────────────────┬─────────────────────────────────┘
                            │ Unix Socket (/run/cortex.sock)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      cortexd (C++)                           │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ IPC Server  │  │ System Monitor  │  │   LLM Engine    │  │
│  │ ─────────── │  │ ─────────────── │  │ ─────────────── │  │
│  │ JSON-RPC    │  │ Memory/Disk     │  │ llama.cpp       │  │
│  │ Handlers    │  │ APT/CVE         │  │ Inference Queue │  │
│  └─────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Alert Manager (SQLite) │ Config Manager (YAML) │ Logger │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
daemon/
├── include/cortexd/          # Public headers
│   ├── common.h              # Types, constants
│   ├── config.h              # Configuration
│   ├── logger.h              # Logging
│   ├── core/                 # Daemon core
│   │   ├── daemon.h
│   │   └── service.h
│   ├── ipc/                  # IPC layer
│   │   ├── server.h
│   │   ├── protocol.h
│   │   └── handlers.h
│   ├── monitor/              # System monitoring
│   │   ├── system_monitor.h
│   │   ├── memory_monitor.h
│   │   ├── disk_monitor.h
│   │   ├── apt_monitor.h
│   │   └── cve_scanner.h
│   ├── llm/                  # LLM inference
│   │   ├── engine.h
│   │   └── llama_backend.h
│   └── alerts/               # Alert system
│       └── alert_manager.h
├── src/                      # Implementation
├── systemd/                  # Service files
├── config/                   # Config templates
├── scripts/                  # Build scripts
└── tests/                    # Test suite
```

## CLI Commands

Cortex provides integrated CLI commands to interact with the daemon:

```bash
# Check daemon status
cortex daemon status

# View system health metrics  
cortex daemon health

# List active alerts
cortex daemon alerts

# Filter alerts by severity
cortex daemon alerts --severity warning
cortex daemon alerts --severity critical

# Acknowledge all alerts
cortex daemon alerts --acknowledge-all

# Dismiss (delete) a specific alert by ID
cortex daemon alerts --dismiss <alert-id>

# Reload daemon configuration
cortex daemon reload-config

# Install/uninstall daemon
cortex daemon install
cortex daemon uninstall
```

## IPC API

### Methods

| Method | Description |
|--------|-------------|
| `ping` | Health check |
| `status` | Get daemon status |
| `health` | Get system health snapshot |
| `version` | Get version info |
| `alerts` | Get active alerts |
| `alerts.acknowledge` | Acknowledge alert(s) |
| `alerts.dismiss` | Dismiss (delete) an alert |
| `config.get` | Get configuration |
| `config.reload` | Reload config file |
| `llm.status` | Get LLM status |
| `llm.load` | Load model |
| `llm.unload` | Unload model |
| `llm.infer` | Run inference |
| `shutdown` | Request shutdown |

### Example

```bash
# Get health status via socat
echo '{"method":"health"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock

# Response:
# {
#   "success": true,
#   "result": {
#     "cpu_usage_percent": 12.5,
#     "memory_usage_percent": 45.2,
#     "disk_usage_percent": 67.8,
#     "llm_loaded": false,
#     "active_alerts": 0
#   }
# }
```

## Configuration

Default config: `/etc/cortex/daemon.yaml`

```yaml
socket:
  path: /run/cortex.sock
  timeout_ms: 5000

llm:
  model_path: ""  # Path to GGUF model
  context_length: 2048
  threads: 4
  lazy_load: true

monitoring:
  interval_sec: 300
  enable_apt: true
  enable_cve: true

thresholds:
  disk_warn: 0.80
  disk_crit: 0.95
  mem_warn: 0.85
  mem_crit: 0.95

alerts:
  db_path: ~/.cortex/alerts.db
  retention_hours: 168

log_level: 1  # 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR
```

## Building from Source

### Prerequisites

```bash
# Ubuntu/Debian
sudo apt install -y \
    cmake \
    build-essential \
    libsystemd-dev \
    libssl-dev \
    libsqlite3-dev \
    uuid-dev \
    pkg-config

# Optional: llama.cpp for LLM features
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && mkdir build && cd build
cmake .. && make -j$(nproc)
sudo make install
```

### Build

```bash
# Release build
./scripts/build.sh Release

# Debug build
./scripts/build.sh Debug

# Manual build
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

## systemd Management

```bash
# Start daemon
sudo systemctl start cortexd

# Stop daemon
sudo systemctl stop cortexd

# View status
sudo systemctl status cortexd

# View logs
journalctl -u cortexd -f

# Reload config
sudo systemctl reload cortexd

# Enable at boot
sudo systemctl enable cortexd
```

## Performance

| Metric | Target | Actual |
|--------|--------|--------|
| Startup time | < 1s | ~0.3-0.5s |
| Idle memory | < 50MB | ~30-40MB |
| Active memory | < 150MB | ~80-120MB |
| Socket latency | < 50ms | ~5-15ms |

## Security

- Runs as root (required for system monitoring)
- Unix socket with 0666 permissions (local access only)
- No network exposure
- systemd hardening (NoNewPrivileges, ProtectSystem, etc.)

## Contributing

1. Follow C++17 style
2. Add tests for new features
3. Update documentation
4. Test on Ubuntu 22.04+

## License

Apache 2.0 - See [LICENSE](../LICENSE)

## Support

- Issues: https://github.com/cortexlinux/cortex/issues
- Discord: https://discord.gg/uCqHvxjU83

