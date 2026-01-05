# Cortexd Daemon - Troubleshooting Guide

## Common Issues & Solutions

### Build Issues

#### CMake not found
**Error**: `cmake: command not found`

**Solution**:
```bash
sudo apt install cmake
cmake --version
```

#### Missing system libraries
**Error**: `error: 'systemd/sd-daemon.h' file not found`

**Solution**:
```bash
# Check which package is missing
pkg-config --cflags --libs systemd
pkg-config --cflags --libs openssl
pkg-config --cflags --libs sqlite3
pkg-config --cflags --libs uuid

# Install missing packages
sudo apt install libsystemd-dev libssl-dev libsqlite3-dev uuid-dev

# Retry build
cd daemon && ./scripts/build.sh Release
```

#### Linker errors
**Error**: `undefined reference to socket`

**Solution**: Check CMakeLists.txt contains `pthread` in link libraries:
```bash
grep -n "pthread" daemon/CMakeLists.txt
```

#### Build hangs
**Symptom**: Build process stops responding

**Solution**:
```bash
# Cancel build
Ctrl+C

# Clean and retry with reduced parallelism
cd daemon
rm -rf build
./scripts/build.sh Release

# Or manually:
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j2  # Use 2 jobs instead of all cores
```

---

### Installation Issues

#### Permission denied
**Error**: `Permission denied` when running install script

**Solution**:
```bash
# Install script requires sudo
sudo ./daemon/scripts/install.sh

# Verify installation
ls -la /usr/local/bin/cortexd
systemctl status cortexd
```

#### Socket already in use
**Error**: `Address already in use` when starting daemon

**Solution**:
```bash
# Check if socket file exists
ls -la /run/cortex.sock

# Kill any existing daemon
pkill -f cortexd
# or
sudo systemctl stop cortexd

# Remove socket file if stale
sudo rm -f /run/cortex.sock

# Restart daemon
sudo systemctl start cortexd
```

#### Service failed to start
**Error**: `Job for cortexd.service failed`

**Solution**:
```bash
# Check detailed error
systemctl status cortexd -l

# View daemon logs
journalctl -u cortexd -e

# Try running daemon manually
/usr/local/bin/cortexd --verbose

# Check binary exists and is executable
ls -la /usr/local/bin/cortexd
file /usr/local/bin/cortexd
```

---

### Runtime Issues

#### Daemon not responding
**Symptom**: `cortex daemon status` hangs or times out

**Solution**:
```bash
# Check if daemon is running
systemctl is-active cortexd

# Verify socket exists
ls -la /run/cortex.sock

# Test socket manually
echo '{"command":"health"}' | socat - UNIX-CONNECT:/run/cortex.sock

# Check daemon logs
journalctl -u cortexd -f

# Restart daemon
sudo systemctl restart cortexd
```

#### High memory usage
**Symptom**: `ps aux | grep cortexd` shows high memory %

**Solution**:
```bash
# Check current usage
ps aux | grep cortexd
# Example: cortexd 25 200M (200 MB)

# Reduce configured memory limit
cat ~/.cortex/daemon.conf
# Change: memory_limit_mb: 100

# Disable LLM if not needed
# Change: in config

# Reload config
cortex daemon reload-config

# Or restart
sudo systemctl restart cortexd
```

#### CPU usage too high
**Symptom**: Daemon using 50%+ CPU at idle

**Solution**:
```bash
# Check monitoring interval (should be 300s = 5min)
cat ~/.cortex/daemon.conf | grep monitoring_interval

# Increase interval to reduce frequency
# Change: monitoring_interval_seconds: 600

# Reload config
cortex daemon reload-config

# Disable unnecessary checks
# Change: enable_cve_scanning: false
```

#### Socket timeout errors
**Error**: `timeout` when connecting to daemon

**Solution**:
```bash
# Increase socket timeout in client
python3 -c "from cortex.daemon_client import CortexDaemonClient; \
c = CortexDaemonClient(timeout=10.0); print(c.is_running())"

# Or check if daemon is overloaded
journalctl -u cortexd | grep "ERROR\|busy"

# Reduce alert volume if there are too many
cortex daemon alerts
# Too many alerts slow down responses

# Restart daemon with verbose logging
sudo systemctl stop cortexd
/usr/local/bin/cortexd --verbose
```

---

### Configuration Issues

#### Config file not being read
**Symptom**: Changes to ~/.cortex/daemon.conf have no effect

**Solution**:
```bash
# Verify config file exists
cat ~/.cortex/daemon.conf

# Reload config
cortex daemon reload-config

# Or restart daemon
sudo systemctl restart cortexd

# Check if loaded successfully in logs
journalctl -u cortexd | grep "Configuration loaded"
```

#### Invalid configuration values
**Error**: `Failed to parse config` or similar

**Solution**:
```bash
# Check config file syntax (YAML-like)
cat ~/.cortex/daemon.conf

# Must be key: value format (with colon and space)
# Check for typos: monitoring_interval_seconds (not interval)

# Restore defaults if corrupted
rm ~/.cortex/daemon.conf

# Daemon will use built-in defaults
sudo systemctl restart cortexd
```

#### Model file not found
**Error**: `Model file not found` in logs

**Solution**:
```bash
# Check configured model path
cat ~/.cortex/daemon.conf | grep model_path

# Verify file exists
ls -la ~/.cortex/models/default.gguf

# Download model if missing
mkdir -p ~/.cortex/models
# Download model...

# Update config path if needed
echo "model_path: ~/.cortex/models/your-model.gguf" >> ~/.cortex/daemon.conf

# Reload
cortex daemon reload-config
```

---

### Alert Issues

#### Too many alerts
**Symptom**: `cortex daemon alerts` shows hundreds of alerts

**Solution**:
```bash
# Clear acknowledged alerts
cortex daemon alerts --acknowledge-all

# Or clear all
journalctl --rotate
journalctl --vacuum-time=1d

# Adjust thresholds in config
# Change: thresholds for disk, memory, etc.

# Reload config
cortex daemon reload-config
```

#### Alerts not appearing
**Symptom**: System issues but no alerts created

**Solution**:
```bash
# Check monitoring is enabled
systemctl is-active cortexd

# Check logs
journalctl -u cortexd | grep "monitoring\|alert"

# Verify thresholds are low enough
# Example: disk threshold might be >95%, actual is 80%

# Check alert queue isn't full
cortex daemon health | grep alert

# Restart monitoring
sudo systemctl restart cortexd
```

---

### CLI Issues

#### `cortex daemon` command not found
**Error**: `cortex: error: invalid choice: 'daemon'`

**Solution**:
```bash
# Ensure cortex is up to date
pip install -e ~/path/to/cortex

# Or reinstall CLI
cd /path/to/cortex
pip install -e .

# Verify daemon_commands.py is in place
ls -la cortex/daemon_commands.py

# Check cortex cli imports daemon_commands
grep "daemon_commands" cortex/cli.py
```

#### Python import errors
**Error**: `ModuleNotFoundError: No module named 'cortex.daemon_client'`

**Solution**:
```bash
# Reinstall cortex package
cd /path/to/cortex
pip install -e .

# Verify files exist
ls -la cortex/daemon_client.py
ls -la cortex/daemon_commands.py

# Check Python path
python3 -c "import cortex; print(cortex.__path__)"
```

#### Socket permission denied
**Error**: `Permission denied` when CLI tries to connect

**Solution**:
```bash
# Check socket permissions
ls -la /run/cortex.sock
# Should be: srw-rw-rw-

# If not world-writable, run CLI with sudo
sudo cortex daemon health

# Or change socket permissions (temporary)
sudo chmod 666 /run/cortex.sock

# To fix permanently, modify daemon code to set 0666 on socket
```

---

### Logging Issues

#### Logs not appearing
**Symptom**: `journalctl -u cortexd` returns nothing

**Solution**:
```bash
# Check if journald is enabled in config
cat ~/.cortex/daemon.conf | grep journald

# Verify daemon is actually logging
/usr/local/bin/cortexd --verbose

# Check journald is running
systemctl status systemd-journald

# View all daemon activity
journalctl | grep cortexd
```

#### Too many logs (disk full)
**Symptom**: Disk usage high, logs are huge

**Solution**:
```bash
# Reduce log level
cat ~/.cortex/daemon.conf
# Change: log_level: 3 (ERROR only)

# Or disable debug logging
# Reload config
cortex daemon reload-config

# Clean up old logs
journalctl --vacuum-time=7d
journalctl --vacuum-size=100M

# Check disk usage
df -h /var/log/journal/
```

---

### Systemd Integration Issues

#### Daemon won't start on boot
**Symptom**: After reboot, `systemctl status cortexd` shows inactive

**Solution**:
```bash
# Check if enabled
systemctl is-enabled cortexd

# Enable for auto-start
sudo systemctl enable cortexd

# Verify
sudo systemctl status cortexd
systemctl is-enabled cortexd
```

#### Daemon crashes immediately
**Symptom**: `systemctl status cortexd` shows `Main process exited`

**Solution**:
```bash
# Check error in logs
journalctl -u cortexd -n 100

# Run manually to see full error
sudo /usr/local/bin/cortexd

# Common issues:
# - Socket path not writable
# - Configuration error
# - Missing shared libraries

# Fix and restart
sudo systemctl restart cortexd
```

#### systemd unit not found
**Error**: `Failed to get unit file state`

**Solution**:
```bash
# Verify service file exists
ls -la /etc/systemd/system/cortexd.service

# Reload systemd daemon
sudo systemctl daemon-reload

# Verify
systemctl status cortexd
```

---

### Performance Issues

#### Slow response times
**Symptom**: `cortex daemon health` takes 5+ seconds

**Solution**:
```bash
# Check if daemon is busy
journalctl -u cortexd | grep "busy\|queue"

# Reduce monitoring frequency
cat ~/.cortex/daemon.conf
# Change: monitoring_interval_seconds: 600

# Disable expensive checks
# Change: enable_cve_scanning: false

# Reload
cortex daemon reload-config
```

#### Memory leak
**Symptom**: Memory usage grows over time

**Solution**:
```bash
# Monitor memory with time
watch -n 10 'ps aux | grep cortexd'

# After 24+ hours, memory should stabilize

# If still growing:
# 1. Stop daemon
sudo systemctl stop cortexd

# 2. Build with ASAN (Address Sanitizer)
cmake -DCMAKE_CXX_FLAGS="-fsanitize=address,undefined" ..
make

# 3. Run with debug output
ASAN_OPTIONS=verbosity=1 /usr/local/bin/cortexd

# 4. Look for memory errors
```

---

## Diagnostic Commands

### Check Daemon Health

```bash
#!/bin/bash
echo "=== Cortexd Diagnostics ==="

# 1. Process check
echo "1. Process Status:"
ps aux | grep cortexd

# 2. Socket check
echo "2. Socket Status:"
ls -la /run/cortex.sock 2>/dev/null || echo "Socket not found"

# 3. Systemd check
echo "3. Systemd Status:"
systemctl status cortexd --no-pager

# 4. Log check
echo "4. Recent Logs:"
journalctl -u cortexd -n 20 --no-pager

# 5. Config check
echo "5. Configuration:"
cat ~/.cortex/daemon.conf 2>/dev/null || echo "No user config"

# 6. Memory check
echo "6. Memory Usage:"
ps aux | grep cortexd | awk '{print "Memory:", $6/1024 "MB, CPU:", $3"%"}'

# 7. IPC test
echo "7. IPC Test:"
echo '{"command":"health"}' | socat - UNIX-CONNECT:/run/cortex.sock 2>/dev/null | jq '.' 2>/dev/null || echo "IPC failed"

echo "=== End Diagnostics ==="
```

### Quick Restart

```bash
sudo systemctl restart cortexd && sleep 1 && systemctl status cortexd
```

### Full Reset

```bash
# Complete daemon reset
sudo systemctl stop cortexd
sudo rm -f /run/cortex.sock
rm -rf ~/.cortex/daemon.conf
sudo systemctl start cortexd
sleep 1
cortex daemon status
```

---

## Getting Help

### Enable Verbose Logging

```bash
# In ~/.cortex/daemon.conf
log_level: 0  # DEBUG

cortex daemon reload-config
journalctl -u cortexd -f
```

### Collect Diagnostic Info

```bash
# Create diagnostic bundle
mkdir ~/cortex-diagnostics
ps aux | grep cortexd > ~/cortex-diagnostics/processes.txt
systemctl status cortexd > ~/cortex-diagnostics/systemd-status.txt
journalctl -u cortexd -n 500 > ~/cortex-diagnostics/logs.txt
cat ~/.cortex/daemon.conf > ~/cortex-diagnostics/config.txt 2>/dev/null
ls -la /run/cortex.sock > ~/cortex-diagnostics/socket-info.txt 2>/dev/null

# Share for debugging
tar czf cortex-diagnostics.tar.gz ~/cortex-diagnostics/
```

### Report Issues

When reporting issues, include:

1. Cortex version: `cortex --version`
2. OS version: `lsb_release -a`
3. Daemon status: `systemctl status cortexd`
4. Recent logs: `journalctl -u cortexd -n 100`
5. Config file: `cat ~/.cortex/daemon.conf`
6. Diagnostic bundle (see above)

---

## Performance Tuning

### For High-Load Systems

```yaml
# ~/.cortex/daemon.conf
monitoring_interval_seconds: 600      # Less frequent checks
max_inference_queue_size: 50          # Smaller queue
memory_limit_mb: 200                  # More memory available
enable_cve_scanning: false            # Disable heavy checks
log_level: 2                          # Reduce logging
```

### For Resource-Constrained Systems

```yaml
# ~/.cortex/daemon.conf
monitoring_interval_seconds: 900      # Very infrequent checks
max_inference_queue_size: 10          # Minimal queue
memory_limit_mb: 100                  # Tight memory limit
enable_cve_scanning: false            # Disable CVE scanning
log_level: 3                          # Errors only
```

