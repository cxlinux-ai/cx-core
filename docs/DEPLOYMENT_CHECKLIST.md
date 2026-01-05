# Cortexd Deployment Checklist

This checklist ensures cortexd is properly built, tested, and deployed.

## 📋 Pre-Deployment Verification

### Build Environment
- [ ] CMake 3.20+ installed: `cmake --version`
- [ ] C++17 compiler available: `g++ --version` (GCC 9+)
- [ ] pkg-config installed: `pkg-config --version`
- [ ] Required dev packages: `sudo apt-get install systemd libsystemd-dev`
- [ ] Python 3.10+ for CLI: `python3 --version`

### System Requirements
- [ ] Running Ubuntu 22.04+ or Debian 12+
- [ ] systemd available: `systemctl --version`
- [ ] /run directory writable by root
- [ ] /etc/default available for config
- [ ] ~250MB free disk for daemon binary + build files

---

## 🔨 Build Verification

### Step 1: Clean Build
```bash
cd /path/to/cortex/daemon
rm -rf build
./scripts/build.sh Release
```

**Verification**:
- [ ] Build completes without errors
- [ ] Final message: "✓ Cortexd Release build complete"
- [ ] Binary created: `build/bin/cortexd` (exists and executable)
- [ ] Size reasonable: `ls -lh build/bin/cortexd` (~8MB)

### Step 2: Run Unit Tests
```bash
cd daemon/build
ctest --output-on-failure -VV
```

**Verification**:
- [ ] All tests pass (or N/A if stubs)
- [ ] No memory errors reported
- [ ] No segfaults
- [ ] Test output clean

### Step 3: Verify Binary
```bash
./daemon/build/bin/cortexd --version
./daemon/build/bin/cortexd --help
```

**Verification**:
- [ ] Version output shows: "cortexd version 0.1.0"
- [ ] Help message displays usage
- [ ] No missing dependencies error

---

## 🔧 Installation Verification

### Step 1: Install System-Wide
```bash
sudo ./daemon/scripts/install.sh
```

**Verification**:
- [ ] Script completes without error
- [ ] Binary copied: `ls -l /usr/local/bin/cortexd`
- [ ] Service file installed: `ls -l /etc/systemd/system/cortexd.service`
- [ ] Socket file installed: `ls -l /etc/systemd/system/cortexd.socket`
- [ ] Config template created: `ls -l /etc/default/cortexd`

### Step 2: Systemd Integration
```bash
systemctl status cortexd.socket
systemctl daemon-reload
systemctl enable cortexd.service
```

**Verification**:
- [ ] Socket unit is enabled
- [ ] Daemon reload succeeds
- [ ] Service enabled in systemd
- [ ] No systemctl errors

### Step 3: Start Daemon
```bash
sudo systemctl start cortexd.service
sleep 1
systemctl status cortexd.service
```

**Verification**:
- [ ] Service starts successfully
- [ ] Status shows "active (running)"
- [ ] PID is non-zero
- [ ] No errors in status output

---

## ✅ Functional Verification

### Step 1: CLI Commands
```bash
# Status command
cortex daemon status

# Health command
cortex daemon health

# Alerts command
cortex daemon alerts

# Config reload command
cortex daemon reload-config
```

**Verification**:
- [ ] `cortex daemon status` shows daemon running
- [ ] `cortex daemon health` shows memory/disk stats
- [ ] `cortex daemon alerts` shows empty alerts list (or existing alerts)
- [ ] `cortex daemon reload-config` succeeds
- [ ] No "connection refused" errors
- [ ] All commands return JSON-parseable output

### Step 2: Direct Socket Test
```bash
echo '{"jsonrpc":"2.0","id":"test-1","method":"status"}' | \
  socat - UNIX-CONNECT:/run/cortex.sock | jq .
```

**Verification**:
- [ ] Socket connection succeeds
- [ ] JSON response received
- [ ] Response contains: `jsonrpc`, `id`, `result` or `error`
- [ ] No timeout errors
- [ ] Data format is valid JSON

### Step 3: Journald Logging
```bash
journalctl -u cortexd -n 20 --no-pager
journalctl -u cortexd -f  # Live view
```

**Verification**:
- [ ] Logs appear in journald
- [ ] Log format: `cortexd[PID]: message`
- [ ] Multiple log levels visible (INFO, DEBUG, WARN, ERROR)
- [ ] Recent timestamps show daemon running
- [ ] No errors reported in logs

---

## 🧪 Performance Verification

### Step 1: Startup Performance
```bash
# Restart daemon and time startup
sudo systemctl restart cortexd.service
time sleep 0.1  # Brief delay

# Check startup message in logs
journalctl -u cortexd -n 5 --no-pager
```

**Verification**:
- [ ] Startup completes in < 1 second
- [ ] Log shows: "Cortexd starting" + "Ready to accept connections"
- [ ] Time elapsed < 100ms
- [ ] No startup errors

### Step 2: Memory Usage
```bash
# Check process memory
ps aux | grep cortexd
systemctl status cortexd.service

# More detailed memory stats
cat /proc/$(pidof cortexd)/status | grep VmRSS
```

**Verification**:
- [ ] Memory usage: 30-50 MB (RSS)
- [ ] Memory grows < 5MB per hour (stability)
- [ ] No memory leaks visible
- [ ] CPU usage: < 1% idle

### Step 3: Socket Latency
```bash
# Test response time with multiple requests
for i in {1..10}; do
  time (echo '{"jsonrpc":"2.0","id":"test-'$i'","method":"health"}' | \
    socat - UNIX-CONNECT:/run/cortex.sock > /dev/null)
done
```

**Verification**:
- [ ] Average latency < 50ms
- [ ] Max latency < 100ms
- [ ] No timeouts
- [ ] Consistent response times

---

## 🔐 Security Verification

### Step 1: File Permissions
```bash
ls -l /usr/local/bin/cortexd
ls -l /etc/systemd/system/cortexd.*
ls -l /run/cortex.sock
ls -la ~/.cortex/  2>/dev/null || echo "Not present for non-root"
```

**Verification**:
- [ ] Binary: `-rwxr-xr-x` (755) or similar
- [ ] Service files: `-rw-r--r--` (644)
- [ ] Socket: `srwxrwxrwx` (666) - world accessible
- [ ] Config readable by root only

### Step 2: Systemd Security
```bash
systemctl cat cortexd.service | grep -A 50 "\[Service\]"
```

**Verification**:
- [ ] PrivateTmp=yes present
- [ ] NoNewPrivileges=yes present
- [ ] ProtectSystem settings present
- [ ] Resource limits defined (MemoryMax)

### Step 3: Process Isolation
```bash
# Check daemon runs as root (expected)
ps aux | grep cortexd | grep -v grep
```

**Verification**:
- [ ] Process runs as root (needed for system monitoring)
- [ ] Single cortexd process (no duplicates)
- [ ] Parent is systemd
- [ ] No suspicious child processes

---

## 🚨 Stability Verification

### Step 1: Extended Runtime (1 Hour)
```bash
# Monitor for 1 hour
watch -n 10 'systemctl status cortexd.service | head -10'

# In another terminal, generate activity
for i in {1..360}; do
  cortex daemon health > /dev/null 2>&1
  sleep 10
done
```

**Verification**:
- [ ] Daemon remains active for 1+ hour
- [ ] No unexpected restarts
- [ ] Memory usage stable (no growth)
- [ ] CPU remains low
- [ ] No errors in logs

### Step 2: Heavy Load Test
```bash
# Simulate multiple concurrent requests
for i in {1..20}; do
  (
    for j in {1..50}; do
      cortex daemon health > /dev/null 2>&1
    done
  ) &
done
wait

# Check daemon still healthy
cortex daemon status
```

**Verification**:
- [ ] All requests complete successfully
- [ ] No "connection refused" errors
- [ ] Daemon remains responsive
- [ ] No resource exhaustion
- [ ] Memory usage spike temporary (< 150MB)

### Step 3: Graceful Shutdown
```bash
# Test graceful shutdown
sudo systemctl stop cortexd.service

# Verify it stopped
systemctl is-active cortexd.service  # Should show "inactive"

# Check shutdown message in logs
journalctl -u cortexd -n 5 --no-pager | grep -i "shut"
```

**Verification**:
- [ ] Service stops cleanly (no timeout)
- [ ] Log shows: "Shutting down" message
- [ ] Process exits with code 0
- [ ] No stale socket file (`/run/cortex.sock` removed)

---

## 📊 24-Hour Stability Test (Pre-Production)

This is the final gate before production deployment.

### Setup
```bash
# Create test script
cat > /tmp/cortexd_monitor.sh << 'EOF'
#!/bin/bash
LOGFILE="/tmp/cortexd_24hr_test.log"
START_TIME=$(date +%s)
ERROR_COUNT=0
SUCCESS_COUNT=0

echo "Starting 24-hour stability test at $(date)" | tee $LOGFILE

# Test every minute for 24 hours (1440 minutes)
for minute in {1..1440}; do
  # Health check
  if cortex daemon health > /dev/null 2>&1; then
    ((SUCCESS_COUNT++))
  else
    ((ERROR_COUNT++))
    echo "[ERROR] Health check failed at minute $minute" >> $LOGFILE
  fi
  
  # Memory check
  MEM=$(ps aux | grep "[c]ortexd" | awk '{print $6}')
  if [ -z "$MEM" ]; then
    echo "[ERROR] Daemon crashed at minute $minute" >> $LOGFILE
    exit 1
  fi
  
  # Write progress every 60 minutes
  if (( minute % 60 == 0 )); then
    echo "[$(date)] Hour $(( minute / 60 )): Success=$SUCCESS_COUNT, Errors=$ERROR_COUNT, Memory=${MEM}KB" >> $LOGFILE
  fi
  
  sleep 60
done

END_TIME=$(date +%s)
ELAPSED=$(( (END_TIME - START_TIME) / 3600 ))
echo "Test complete: ${ELAPSED}h elapsed, $SUCCESS_COUNT successes, $ERROR_COUNT errors" | tee -a $LOGFILE
EOF

chmod +x /tmp/cortexd_monitor.sh

# Start background monitoring
nohup /tmp/cortexd_monitor.sh > /tmp/cortexd_monitor.out 2>&1 &
MONITOR_PID=$!
echo "Monitor PID: $MONITOR_PID"
```

### During Test
```bash
# Check progress
tail -f /tmp/cortexd_24hr_test.log

# Check for crashes
journalctl -u cortexd -f --since "1 day ago" 2>/dev/null

# Spot check health
cortex daemon health
cortex daemon status
cortex daemon alerts
```

### Acceptance Criteria
- [ ] Test runs for 24+ hours
- [ ] 0 errors in health checks
- [ ] 0 daemon crashes (monitored PID always running)
- [ ] Memory usage ≤ 50MB throughout
- [ ] Memory growth < 100KB total
- [ ] CPU usage < 1% average
- [ ] All commands responsive
- [ ] No unexpected restarts
- [ ] Logs clean (no repeated errors)

### Success Report
```bash
# After 24 hours
cat /tmp/cortexd_24hr_test.log
systemctl status cortexd.service
ps aux | grep cortexd
journalctl -u cortexd --since "24 hours ago" | tail -20
```

---

## ✨ Pre-Production Sign-Off

When all checkboxes above are checked:

1. **Build Verification**: ✅ Binary built successfully
2. **Functional Verification**: ✅ All CLI commands work
3. **Performance Verification**: ✅ Meets all targets
4. **Security Verification**: ✅ Proper permissions and isolation
5. **Stability Verification**: ✅ 24-hour test passed
6. **Load Testing**: ✅ Handles concurrent requests
7. **Documentation**: ✅ All guides complete and accurate

**Status**: ✅ **READY FOR PRODUCTION**

---

## 🔄 Rollback Procedure

If issues occur:

```bash
# Stop daemon
sudo systemctl stop cortexd.service

# Uninstall
sudo ./daemon/scripts/uninstall.sh

# Or manual rollback
sudo rm -f /usr/local/bin/cortexd
sudo rm -f /etc/systemd/system/cortexd.*
sudo systemctl daemon-reload

# Verify removed
systemctl status cortexd.service  # Should be not found
```

---

## 📞 Deployment Support

**Documentation Available**:
- `DAEMON_BUILD.md` - Build troubleshooting
- `DAEMON_SETUP.md` - Installation guide
- `DAEMON_TROUBLESHOOTING.md` - Runtime issues
- `DAEMON_ARCHITECTURE.md` - Technical reference

**Diagnostic Commands**:
```bash
# Status
systemctl status cortexd.service
ps aux | grep cortexd
ls -l /run/cortex.sock

# Logs
journalctl -u cortexd -n 50 --no-pager
journalctl -u cortexd -f

# Connectivity
echo '{"jsonrpc":"2.0","id":"test","method":"status"}' | \
  socat - UNIX-CONNECT:/run/cortex.sock 2>&1

# CLI
cortex daemon health
cortex daemon status
cortex daemon alerts
```

---

## 📝 Sign-Off

**Deployment Date**: _______________

**Verified By**: _______________

**Organization**: Cortex Linux

**Version**: 0.1.0

**Status**: ✅ Production Ready

---

**Questions?** See the documentation or check the GitHub issues.

