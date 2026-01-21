# Cortexd - Core Daemon

**cortexd** is the core daemon foundation for the Cortex AI Package Manager. The essential daemon infrastructure with Unix socket IPC and basic handlers are implemented.

## Features

- 🚀 **Fast Startup**: < 1 second startup time
- 💾 **Low Memory**: < 30MB idle
- 🔌 **Unix Socket IPC**: JSON-RPC protocol at `/run/cortex/cortex.sock`
- ⚙️ **systemd Integration**: Type=notify, watchdog, journald logging
- 📝 **Configuration Management**: YAML-based configuration with hot reload
- 🔧 **IPC Handlers**: ping, version, config, shutdown, health, alerts
- 📊 **System Monitoring**: Continuous monitoring of CPU, memory, disk, and system services
- 🚨 **Alert Management**: SQLite-based alert persistence with severity levels and filtering

## Quick Start

### Recommended: Interactive Setup (Handles Everything)

```bash
# Run the interactive setup wizard
python daemon/scripts/setup_daemon.py
```

The setup wizard will:
1. ✅ Check and install required system dependencies (cmake, build-essential, etc.)
2. ✅ Build the daemon from source
3. ✅ Install the systemd service

### Manual Setup

If you prefer manual installation:

#### 1. Install System Dependencies

```bash
sudo apt-get install -y \
    cmake build-essential libsystemd-dev \
    libssl-dev uuid-dev pkg-config libcap-dev
```

#### 2. Build

```bash
cd daemon
./scripts/build.sh Release
```

#### 3. Install

```bash
sudo ./scripts/install.sh
```

### Verify

```bash
# Check status
systemctl status cortexd

# View logs (including startup time)
journalctl -u cortexd -f

# Check startup time
journalctl -u cortexd | grep "Startup completed"

# Test socket
echo '{"method":"ping"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock
```

**Quick startup time check:**
```bash
# Restart and immediately check startup time
sudo systemctl restart cortexd && sleep 1 && journalctl -u cortexd -n 10 | grep "Startup completed"
```

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                     cortex CLI (Python)                      │
└───────────────────────────┬─────────────────────────────────┘
                            │ Unix Socket (/run/cortex/cortex.sock)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      cortexd (C++)                           │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ IPC Server                                              │ │
│  │ ───────────                                             │ │
│  │ JSON-RPC Protocol                                       │ │
│  │ Handlers: ping, version, config, shutdown,              │ │
│  │          health, alerts                                 │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ System Monitor                                          │ │
│  │ ─────────────                                           │ │
│  │ • CPU/Memory/Disk monitoring                            │ │
│  │ • System uptime & failed services                       │ │
│  │ • Threshold-based alert generation                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Alert Manager                                           │ │
│  │ ────────────                                            │ │
│  │ • SQLite persistence                                    │ │
│  │ • Severity levels (INFO/WARNING/ERROR/CRITICAL)         │ │
│  │ • Categories (CPU/MEMORY/DISK/APT/CVE/SERVICE/SYSTEM)   │ │
│  │ • Filtering & querying                                  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Config Manager (YAML) │ Logger │ Daemon Lifecycle       │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## Directory Structure

```text
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
│   │   └── system_monitor.h
│   └── alerts/               # Alert management
│       └── alert_manager.h
├── src/                      # Implementation
│   ├── core/                 # Daemon lifecycle
│   ├── config/               # Configuration management
│   ├── ipc/                  # IPC server and handlers
│   ├── monitor/              # System monitoring implementation
│   ├── alerts/               # Alert management implementation
│   └── utils/                # Logging utilities
├── systemd/                  # Service files
├── config/                   # Config templates
└── scripts/                  # Build scripts
```

## CLI Commands

Cortex provides integrated CLI commands to interact with the daemon:

```bash
# Basic daemon commands
cortex daemon ping            # Health check
cortex daemon version         # Get daemon version
cortex daemon config          # Show configuration
cortex daemon reload-config   # Reload configuration
cortex daemon shutdown        # Request daemon shutdown

# System monitoring
cortex daemon health          # Get system health metrics

# Alert management
cortex daemon alerts                          # List all active alerts
cortex daemon alerts --severity warning      # Filter by severity
cortex daemon alerts --category cpu          # Filter by category
cortex daemon alerts --acknowledge-all       # Acknowledge all alerts
cortex daemon alerts --dismiss-all            # Dismiss all active and acknowledged alerts
cortex daemon alerts --dismiss <uuid>        # Dismiss specific alert

# Install/uninstall daemon
cortex daemon install
cortex daemon install --execute
cortex daemon uninstall
```

## IPC API

### Available Methods

| Method | Description |
|--------|-------------|
| `ping` | Health check |
| `version` | Get version info |
| `config.get` | Get configuration |
| `config.reload` | Reload config file |
| `shutdown` | Request shutdown |
| `health` | Get system health metrics (CPU, memory, disk, services) |
| `alerts` / `alerts.get` | Get alerts with optional filtering |
| `alerts.acknowledge` | Acknowledge alerts (all or by UUID) |
| `alerts.dismiss` | Dismiss alerts (all or by UUID) |

### Example

```bash
# Ping the daemon
echo '{"method":"ping"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock

# Response:
# {
#   "success": true,
#   "result": {"pong": true}
# }

# Get version
echo '{"method":"version"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock

# Response:
# {
#   "success": true,
#   "result": {
#     "version": "1.0.0",
#     "name": "cortexd"
#   }
# }

# Get system health
echo '{"method":"health"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock

# Response:
# {
#   "success": true,
#   "result": {
#     "cpu_usage_percent": 45.2,
#     "memory_usage_percent": 62.1,
#     "disk_usage_percent": 78.5,
#     "uptime_seconds": 86400,
#     "failed_services_count": 0,
#     "thresholds": { ... }
#   }
# }

# Get alerts
echo '{"method":"alerts"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock

# Get alerts filtered by severity
echo '{"method":"alerts","params":{"severity":"warning"}}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock

# Acknowledge all alerts
echo '{"method":"alerts.acknowledge","params":{"all":true}}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock

# Dismiss all alerts
echo '{"method":"alerts.dismiss","params":{"all":true}}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock
```

## Configuration

Default config: `/etc/cortex/daemon.yaml`

```yaml
socket:
  path: /run/cortex/cortex.sock
  timeout_ms: 5000

log_level: 1  # 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR

# Monitoring thresholds (optional - uses defaults if not specified)
monitoring:
  cpu:
    warning_threshold: 80.0    # CPU usage % to trigger warning alert
    critical_threshold: 95.0   # CPU usage % to trigger critical alert
  memory:
    warning_threshold: 80.0    # Memory usage % to trigger warning alert
    critical_threshold: 95.0   # Memory usage % to trigger critical alert
  disk:
    warning_threshold: 80.0    # Disk usage % to trigger warning alert
    critical_threshold: 95.0   # Disk usage % to trigger critical alert
  check_interval_seconds: 60  # How often to check system health
```

**Note**: Thresholds can be adjusted without restarting the daemon. After editing the config file, reload it with:
```bash
cortex daemon reload-config
# or
sudo systemctl reload cortexd
```

## System Monitoring

The daemon includes a built-in system monitor that continuously tracks system health metrics and generates alerts when thresholds are exceeded.

### Monitored Metrics

- **CPU Usage**: Percentage of CPU utilization across all cores
- **Memory Usage**: Total, used, and available memory
- **Disk Usage**: Total, used, and available disk space (primary mount point)
- **System Uptime**: System uptime in seconds
- **Failed Services**: Count of failed systemd services

### Monitoring Thresholds

The monitor uses configurable thresholds to determine when to generate alerts. These can be configured in `/etc/cortex/daemon.yaml`:

- **Warning Threshold**: Default 80% (CPU, memory, disk) - configurable via `monitoring.*.warning_threshold`
- **Critical Threshold**: Default 95% (CPU, memory, disk) - configurable via `monitoring.*.critical_threshold`
- **Check Interval**: Default 60 seconds - configurable via `monitoring.check_interval_seconds`

Thresholds can be updated without restarting the daemon by editing the config file and reloading:
```bash
sudo systemctl reload cortexd
# or
cortex daemon reload-config
```

### Check Interval

The monitor performs health checks every 60 seconds by default. This interval can be configured when creating the `SystemMonitor` instance.

### Alert Generation

When a metric exceeds a threshold, the monitor automatically creates an alert with:
- **Severity**: `WARNING` for threshold violations, `CRITICAL` for critical violations
- **Category**: `CPU`, `MEMORY`, `DISK`, or `SERVICE` (for failed services)
- **Source**: `SystemMonitor`
- **Message**: Brief description of the issue
- **Description**: Detailed information including current values and thresholds

Alerts are persisted to SQLite and can be queried via the IPC API or CLI commands.

## Alert Management

The daemon includes a comprehensive alert management system with SQLite persistence.

### Alert Database

Alerts are stored in `/var/lib/cortex/alerts.db` (SQLite database). The database is automatically created and initialized on first use.

### Alert Properties

- **UUID**: Unique identifier for each alert
- **Severity**: `INFO`, `WARNING`, `ERROR`, or `CRITICAL`
- **Category**: `CPU`, `MEMORY`, `DISK`, `APT`, `CVE`, `SERVICE`, or `SYSTEM`
- **Source**: Origin of the alert (e.g., `SystemMonitor`)
- **Message**: Brief alert message
- **Description**: Detailed alert description
- **Timestamp**: When the alert was created
- **Status**: `ACTIVE`, `ACKNOWLEDGED`, or `DISMISSED`
- **Acknowledged At**: Optional timestamp when alert was acknowledged
- **Dismissed At**: Optional timestamp when alert was dismissed

### Alert Lifecycle

1. **Created**: Alert is created and stored with `ACTIVE` status
2. **Acknowledged**: User acknowledges the alert (status changes to `ACKNOWLEDGED`)
3. **Dismissed**: User dismisses the alert (status changes to `DISMISSED`)

Dismissed alerts are excluded from default queries unless `include_dismissed=true` is specified.

### Filtering Alerts

Alerts can be filtered by:
- **Severity**: `info`, `warning`, `error`, `critical`
- **Category**: `cpu`, `memory`, `disk`, `apt`, `cve`, `service`, `system`
- **Status**: `active`, `acknowledged`, `dismissed`
- **Include Dismissed**: Include dismissed alerts in results (default: false)

### Alert Counts

The alert manager maintains real-time counts of alerts by severity:
- Total count
- Count by severity (INFO, WARNING, ERROR, CRITICAL)

These counts are updated atomically and returned with alert queries for quick status overview.


## Building from Source

### Prerequisites

The easiest way to install all prerequisites is using the setup wizard:

```bash
python daemon/scripts/setup_daemon.py
```

The wizard automatically checks and installs these required system packages:

| Package | Purpose |
|---------|---------|
| `cmake` | Build system generator |
| `build-essential` | GCC, G++, make, and other build tools |
| `libsystemd-dev` | systemd integration headers |
| `libssl-dev` | OpenSSL development libraries |
| `uuid-dev` | UUID generation libraries |
| `pkg-config` | Package configuration tool |
| `libcap-dev` | Linux capabilities library |

#### Manual Prerequisite Installation

If you prefer to install dependencies manually:

```bash
# Ubuntu/Debian - Core dependencies
sudo apt-get update
sudo apt-get install -y \
    cmake \
    build-essential \
    libsystemd-dev \
    libssl-dev \
    uuid-dev \
    pkg-config \
    libcap-dev
```

### Build

```bash
# Release build
./scripts/build.sh Release

# Debug build
./scripts/build.sh Debug

# Build with tests
./scripts/build.sh Release --with-tests

# Manual build
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

## Testing

### How Tests Work

Tests run against a **static library** (`cortexd_lib`) containing all daemon code, allowing testing without installing the daemon as a systemd service.

```text
┌──────────────────────────────────────────────────────────┐
│                    Test Executable                        │
│                   (e.g., test_config)                     │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                    cortexd_lib                            │
│          (Static library with all daemon code)            │
│                                                           │
│  • Config, Logger, Daemon, IPCServer, Handlers...         │
│  • Same code that runs in the actual daemon               │
└──────────────────────────────────────────────────────────┘
```

**Key Points:**
- **No daemon installation required** - Tests instantiate classes directly
- **No systemd needed** - Tests run in user space
- **Same code tested** - The library contains identical code to the daemon binary
- **Fast execution** - No service startup overhead

### Test Types

| Type | Purpose | Daemon Required? |
|------|---------|------------------|
| **Unit Tests** | Test individual classes/functions in isolation | No |
| **Integration Tests** | Test component interactions (IPC, handlers) | No |
| **End-to-End Tests** | Test the running daemon service | Yes (not yet implemented) |

### Building Tests

Tests are built separately from the main daemon. Use the `--with-tests` flag:

```bash
./scripts/build.sh Release --with-tests
```

Or use the setup wizard and select "yes" when asked to build tests:

```bash
python daemon/scripts/setup_daemon.py
```

### Running Tests

**Using Cortex CLI (recommended):**

```bash
# Run all tests
cortex daemon run-tests

# Run only unit tests
cortex daemon run-tests --unit

# Run only integration tests
cortex daemon run-tests --integration

# Run a specific test
cortex daemon run-tests --test config
cortex daemon run-tests -t daemon

# Verbose output
cortex daemon run-tests -v
```

**Using ctest directly:**

```bash
cd daemon/build

# Run all tests
ctest --output-on-failure

# Run specific tests
ctest -R test_config --output-on-failure

# Verbose output
ctest -V
```

### Test Structure

| Test | Type | Description |
|------|------|-------------|
| `test_config` | Unit | Configuration loading and validation |
| `test_protocol` | Unit | IPC message serialization |
| `test_rate_limiter` | Unit | Request rate limiting |
| `test_logger` | Unit | Logging subsystem |
| `test_common` | Unit | Common constants and types |
| `test_ipc_server` | Integration | IPC server lifecycle |
| `test_handlers` | Integration | IPC request handlers |
| `test_daemon` | Integration | Daemon lifecycle and services |

### Example: How Integration Tests Work

```cpp
// test_daemon.cpp - Tests Daemon class without systemd

TEST_F(DaemonTest, InitializeWithValidConfig) {
    // Instantiate Daemon directly (no systemd)
    auto& daemon = cortexd::Daemon::instance();
    
    // Call methods and verify behavior
    daemon.initialize(config_path_);
    EXPECT_TRUE(daemon.is_initialized());
    
    // Test config was loaded
    auto config = daemon.config();
    EXPECT_EQ(config.socket_path, expected_path);
}
```

The test creates a temporary config file, instantiates the `Daemon` class directly in memory, and verifies its behavior - all without touching systemd or installing anything.

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
| Startup time | < 1s | 100μs |
| Idle memory | < 30MB | ~700KB |
| Socket latency | < 50ms | ~5-15ms |

### Measuring Startup Time

The daemon automatically measures and logs its startup time on each start. The measurement begins when `Daemon::run()` is called and ends when all services are started and systemd is notified (READY=1).

**What's measured:**
- Service initialization
- IPC server startup
- Handler registration
- systemd notification

**Target:** < 1 second

#### Method 1: Check Daemon Logs (Recommended)

The daemon logs startup time directly in its log output:

```bash
# View recent logs
journalctl -u cortexd -n 20

# Look for the startup time message:
# [INFO] Daemon: Startup completed in XXXms (or XXXμs for very fast startups)

# Or filter for startup messages only
journalctl -u cortexd | grep "Startup completed"
```

**Example output:**
```text
[INFO] Daemon: Starting daemon
[INFO] Daemon: Starting service: IPCServer
[INFO] IPCServer: Started on /run/cortex/cortex.sock
[INFO] Daemon: Service started: IPCServer
[INFO] Daemon: Startup completed in 234.567ms
[INFO] Daemon: Daemon started successfully
```

**Note:** For very fast startups (< 1ms), the time is shown in microseconds (μs) for precision:
```text
[INFO] Daemon: Startup completed in 456μs
```
#### Method 2: Manual Timing with systemctl

Time the service start manually:

```bash
# Stop the service first
sudo systemctl stop cortexd

# Time the start command
time sudo systemctl start cortexd

# Check if it's running
systemctl is-active cortexd
```


### Measuring Idle Memory

The daemon should use less than 30MB of memory when idle (no active requests).

**Target:** < 30MB

#### Method 1: Using systemctl status

```bash
# Check current memory usage
systemctl status cortexd

# Look for the "Memory:" line in the output
# Example: Memory: 24.5M
```

#### Method 2: Using ps

```bash
# Check memory usage with ps
ps aux | grep cortexd | grep -v grep

# Or get just the RSS (Resident Set Size) in MB
ps -o pid,rss,comm -p $(pgrep cortexd) | awk 'NR>1 {print $2/1024 " MB"}'
```

#### Method 3: Using systemd-cgls

```bash
# Check memory usage via cgroup
systemctl show cortexd -p MemoryCurrent

# Output is in bytes, convert to MB:
# MemoryCurrent=25165824 (bytes) = ~24MB
```

**Note:** Ensure the daemon is idle (no active IPC requests) when measuring. Memory usage may temporarily spike during request handling, but should return to baseline when idle.

### Measuring Socket Latency

Socket latency is the time it takes for a request to travel from client to daemon and back (round-trip time).

**Target:** < 50ms

#### Method 1: Using time with socat

```bash
# Measure latency of a ping request
time echo '{"method":"ping"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock

# The "real" time shows the total round-trip latency
```

#### Method 2: Using time with cortex CLI

```bash
# If cortex CLI is available, time a command
time cortex daemon ping
```

**Note:** Socket latency can vary based on system load. For accurate measurement:
- Run when system is idle
- Take multiple measurements and average
- Ensure daemon is running and responsive

## Security

- Unix socket with 0666 permissions (local access only, not network accessible)
- No network exposure
- systemd hardening (NoNewPrivileges, ProtectSystem, etc.)
- Minimal attack surface (core daemon only)

## Contributing

1. Follow C++17 style
2. Add tests for new features
3. Update documentation
4. Test on Ubuntu 22.04+

## License

Apache 2.0 - See [LICENSE](../LICENSE)

## Support

- Issues: [GitHub Issues](https://github.com/cortexlinux/cortex/issues)
- Discord: [Discord](https://discord.gg/uCqHvxjU83)
