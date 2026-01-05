# Cortexd llama.cpp Integration - Setup & Testing Guide

Complete walkthrough to setup, test, and validate the embedded llama.cpp inference implementation.

---

## Phase 1: Environment Setup

### Step 1.1: Check System Requirements

```bash
# Check Ubuntu/Debian version
lsb_release -a
# Expected: Ubuntu 22.04 LTS or Debian 12+

# Check CPU cores (for thread configuration)
nproc
# Expected: 2+ cores

# Check RAM
free -h
# Expected: 4GB+ recommended (2GB minimum)

# Check disk space
df -h ~
# Expected: 10GB+ free for models and build
```

### Step 1.2: Install Build Dependencies

```bash
# Update package list
sudo apt update

# Install required build tools
sudo apt install -y \
    cmake \
    build-essential \
    git \
    libsystemd-dev \
    libssl-dev \
    libsqlite3-dev \
    uuid-dev \
    pkg-config

# Verify installations
cmake --version      # Should be >= 3.20
g++ --version        # Should be >= 9
pkg-config --version
```

### Step 1.3: Install llama.cpp

**Option A: Package Manager (Recommended)**
```bash
sudo apt install -y libllama-dev

# Verify installation
pkg-config --cflags llama
pkg-config --libs llama
# Should output: -I/usr/include -L/usr/lib -llama
```

**Option B: Build from Source**
```bash
cd /tmp
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install

# Verify
sudo ldconfig
ldconfig -p | grep llama
# Should show libllama.so
```

### Step 1.4: Create Model Directory

```bash
# Create directory
mkdir -p ~/.cortex/models
chmod 755 ~/.cortex/models

# Verify
ls -la ~/.cortex/
```

---

## Phase 2: Download & Prepare Models

### Step 2.1: Download a Test Model

**Option A: Phi 2.7B (Fast, Recommended for Testing)**
```bash
# Fast download for quick testing (~1.6GB)
cd ~/.cortex/models
wget -c https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf

# Verify download
ls -lh phi-2.Q4_K_M.gguf
md5sum phi-2.Q4_K_M.gguf
```

**Option B: Mistral 7B (Balanced Quality, Larger)**
```bash
# Better quality but slower (~6.5GB)
cd ~/.cortex/models
wget -c https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/main/Mistral-7B-Instruct-v0.1.Q4_K_M.gguf
```

**Option C: Orca Mini (Ultra-Fast for Testing)**
```bash
# Smallest model for quick validation (~1.3GB)
cd ~/.cortex/models
wget -c https://huggingface.co/TheBloke/orca-mini-3b-gguf/resolve/main/orca-mini-3b.Q4_K_M.gguf
```

### Step 2.2: Verify Model Files

```bash
# List models
ls -lh ~/.cortex/models/

# Verify GGUF format
file ~/.cortex/models/*.gguf
# Should show: GGUF format model

# Check file integrity
du -sh ~/.cortex/models/
# Should match expected size
```

---

## Phase 3: Build Cortexd

### Step 3.1: Clean Build

```bash
cd /home/sujay/internship/cortex/daemon

# Clean previous build
rm -rf build

# Create build directory
mkdir build
cd build

# Configure with CMake
cmake -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_TESTS=ON \
      -DCMAKE_VERBOSE_MAKEFILE=ON \
      ..

# Check CMake output
# Should show:
# - Found systemd
# - Found OpenSSL
# - Found SQLite3
# - pkg-config checks passed
```

### Step 3.2: Build

```bash
# Parallel build
make -j$(nproc)

# Monitor output for:
# ✅ Compiling src/llm/llama_wrapper.cpp
# ✅ Linking cortexd
# ✅ No errors or warnings

# Expected output:
# [100%] Built target cortexd
```

**If build fails**, check:
```bash
# Missing llama.cpp?
pkg-config --cflags llama
# If error: install libllama-dev

# Missing systemd?
pkg-config --cflags systemd
# If error: sudo apt install libsystemd-dev

# Missing openssl?
pkg-config --cflags openssl
# If error: sudo apt install libssl-dev
```

### Step 3.3: Verify Build

```bash
# Check binary exists
ls -lh bin/cortexd

# Check binary size (~8-10MB is normal)
du -h bin/cortexd

# Check dependencies
ldd bin/cortexd | grep llama
# Should show: libllama.so.1 => ...

# Verify it's not stripped
strings bin/cortexd | grep -i llama | head -5
```

---

## Phase 4: Configure Daemon

### Step 4.1: Create Configuration File

```bash
# Create cortex config directory
mkdir -p ~/.cortex

# Create daemon configuration
cat > ~/.cortex/daemon.conf << 'EOF'
[socket]
socket_path=/run/cortex.sock

[llm]
# Point to your model
model_path=/home/$(whoami)/.cortex/models/phi-2.Q4_K_M.gguf
n_threads=4
n_ctx=512
use_mmap=true

[monitoring]
monitoring_interval_seconds=300
enable_cve_scanning=false
enable_journald_logging=true

[logging]
log_level=1
EOF

# Verify config
cat ~/.cortex/daemon.conf
```

### Step 4.2: Fix Paths

```bash
# Get your username
echo $USER

# Update config with correct path
sed -i "s|\$(whoami)|$USER|g" ~/.cortex/daemon.conf

# Verify model path
grep model_path ~/.cortex/daemon.conf
# Should show full path to model
```

---

## Phase 5: Pre-Installation Testing

### Step 5.1: Test Binary Directly

```bash
# Run daemon in foreground (won't stay running)
cd /home/sujay/internship/cortex/daemon/build

# Optional: Set debug environment
export CORTEXD_LOG_LEVEL=0  # DEBUG level

# Try to start daemon (Ctrl+C to stop)
timeout 5 ./bin/cortexd 2>&1 | head -20

# Should show:
# "cortexd starting"
# "Loading configuration"
# "Socket created" or similar
```

### Step 5.2: Test Unit Tests

```bash
# Build tests
cd /home/sujay/internship/cortex/daemon/build
make

# Run tests
ctest --output-on-failure -VV

# Or run specific test
./socket_server_test

# Check for:
# - Test compilation succeeds
# - Tests pass or show expected failures
# - No segfaults
```

---

## Phase 6: Installation

### Step 6.1: Install System-Wide

```bash
# Use install script
cd /home/sujay/internship/cortex/daemon
sudo ./scripts/install.sh

# Verify installation
which cortexd
ls -la /usr/local/bin/cortexd
ls -la /etc/systemd/system/cortexd.*
```

### Step 6.2: Verify Systemd Integration

```bash
# Check systemd recognizes the service
systemctl status cortexd

# Should show:
# "Unit cortexd.service could not be found" (not started yet)

# Check service file
cat /etc/systemd/system/cortexd.service | grep -A 5 "\[Service\]"

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable cortexd.service

# Check enabled
systemctl is-enabled cortexd
# Should show: enabled
```

---

## Phase 7: Basic Testing

### Step 7.1: Start Daemon

```bash
# Start service
sudo systemctl start cortexd

# Check status
systemctl status cortexd

# Should show:
# Active: active (running)
# PID: xxxxx

# If failed, check logs:
journalctl -u cortexd -n 20 --no-pager
```

### Step 7.2: Check Socket Creation

```bash
# Verify socket exists
ls -la /run/cortex.sock

# Check permissions
stat /run/cortex.sock
# Should show: 0666 (world accessible)

# Test connectivity
echo "test" | socat - UNIX-CONNECT:/run/cortex.sock 2>&1
# May error on invalid JSON, but shows connection works
```

### Step 7.3: Test CLI Status Command

```bash
# Check if daemon is running
cortex daemon status

# Expected output:
# Daemon Status
# PID: xxxxx
# Memory: 30-50 MB
# Status: running
```

---

## Phase 8: Model Loading Test

### Step 8.1: Check Health

```bash
# Get health snapshot
cortex daemon health

# Should show:
# System Health
# Memory: XX MB
# Disk: XX%
# Model loaded: true/false
# Inference queue: 0
```

### Step 8.2: Watch Model Load in Logs

```bash
# In terminal 1: Watch logs
journalctl -u cortexd -f

# In terminal 2: Trigger health check a few times
for i in {1..5}; do cortex daemon health; sleep 2; done

# Look for in logs:
# "Loading model from /path/to/model.gguf"
# "Model loaded successfully"
# "Context created"

# Or errors:
# "Failed to load model"
# "File not found"
```

---

## Phase 9: Inference Testing

### Step 9.1: Test via CLI (If Implemented)

```bash
# Some CLI may have inference command
cortex daemon inference "What is Linux?" 2>&1

# Or check available commands
cortex daemon --help | grep -i infer
```

### Step 9.2: Test via Unix Socket

```bash
# Create test request
cat > /tmp/inference_test.json << 'EOF'
{
  "command": "inference",
  "params": {
    "prompt": "Q: What is 2+2?\nA:",
    "max_tokens": 50,
    "temperature": 0.7
  }
}
EOF

# Send request
cat /tmp/inference_test.json | socat - UNIX-CONNECT:/run/cortex.sock > /tmp/response.json

# Check response
cat /tmp/response.json | jq .

# Expected structure:
# {
#   "status": "ok",
#   "data": {
#     "output": "4",
#     "tokens_used": XX,
#     "inference_time_ms": XX
#   },
#   "timestamp": XXXX
# }
```

### Step 9.3: Test Multiple Requests

```bash
# Test concurrent requests (should queue)
for i in {1..3}; do
  echo "Request $i..."
  cat /tmp/inference_test.json | socat - UNIX-CONNECT:/run/cortex.sock &
  sleep 0.1
done
wait

echo "All requests completed"
```

### Step 9.4: Monitor During Inference

```bash
# Terminal 1: Watch daemon logs
journalctl -u cortexd -f

# Terminal 2: Watch process
while true; do
  ps aux | grep "[c]ortexd"
  sleep 1
done

# Terminal 3: Send inference requests
for i in {1..5}; do
  cat /tmp/inference_test.json | socat - UNIX-CONNECT:/run/cortex.sock | jq .data.inference_time_ms
  sleep 2
done
```

---

## Phase 10: Performance Testing

### Step 10.1: Measure Inference Latency

```bash
# Create latency test script
cat > /tmp/latency_test.sh << 'SCRIPT'
#!/bin/bash
for i in {1..10}; do
  START=$(date +%s%N)
  result=$(cat /tmp/inference_test.json | socat - UNIX-CONNECT:/run/cortex.sock)
  END=$(date +%s%N)
  LATENCY=$(( (END - START) / 1000000 ))
  echo "Request $i: ${LATENCY}ms"
  echo "$result" | jq .data.inference_time_ms
  sleep 1
done
SCRIPT

chmod +x /tmp/latency_test.sh
/tmp/latency_test.sh
```

### Step 10.2: Memory Usage Monitoring

```bash
# Start background monitoring
(while true; do ps aux | grep cortexd | grep -v grep; sleep 2; done) > /tmp/memory.log &
MONITOR_PID=$!

# Run inference tests
for i in {1..5}; do
  cat /tmp/inference_test.json | socat - UNIX-CONNECT:/run/cortex.sock > /dev/null
  sleep 1
done

# Stop monitoring
kill $MONITOR_PID

# Analyze
cat /tmp/memory.log | awk '{print $6}' | sort -n
# Should stay relatively stable, not growing
```

### Step 10.3: Check System Impact

```bash
# During inference request
time (cat /tmp/inference_test.json | socat - UNIX-CONNECT:/run/cortex.sock > /dev/null)

# CPU usage during inference
top -bn1 | grep cortexd

# Check no file descriptor leaks
lsof -p $(pgrep cortexd) | wc -l
# Run multiple times, should stay same
```

---

## Phase 11: Error & Edge Case Testing

### Step 11.1: Test Model Not Loaded

```bash
# Stop daemon
sudo systemctl stop cortexd

# Edit config to bad path
sed -i 's|model_path=.*|model_path=/nonexistent/model.gguf|g' ~/.cortex/daemon.conf

# Start daemon
sudo systemctl start cortexd

# Try inference - should get error
cat /tmp/inference_test.json | socat - UNIX-CONNECT:/run/cortex.sock | jq .

# Expected: error about model not loaded

# Check logs
journalctl -u cortexd -n 5 --no-pager | grep -i error
```

### Step 11.2: Test Invalid Requests

```bash
# Invalid JSON
echo "not json" | socat - UNIX-CONNECT:/run/cortex.sock

# Missing required field
echo '{"command":"inference"}' | socat - UNIX-CONNECT:/run/cortex.sock | jq .

# Invalid command
echo '{"command":"invalid_cmd"}' | socat - UNIX-CONNECT:/run/cortex.sock | jq .

# Negative max_tokens
echo '{"command":"inference","params":{"prompt":"test","max_tokens":-10}}' | \
  socat - UNIX-CONNECT:/run/cortex.sock | jq .
```

### Step 11.3: Test Resource Limits

```bash
# Very large prompt
LARGE_PROMPT=$(python3 -c "print('x' * 10000)")
echo "{\"command\":\"inference\",\"params\":{\"prompt\":\"$LARGE_PROMPT\",\"max_tokens\":10}}" | \
  socat - UNIX-CONNECT:/run/cortex.sock | jq .

# Very large max_tokens (should be capped at 256)
echo '{"command":"inference","params":{"prompt":"test","max_tokens":10000}}' | \
  socat - UNIX-CONNECT:/run/cortex.sock | jq .data.tokens_used
# Should be <= 256
```

### Step 11.4: Test Rapid Fire Requests

```bash
# Queue stress test
for i in {1..50}; do
  cat /tmp/inference_test.json | socat - UNIX-CONNECT:/run/cortex.sock > /dev/null &
  if [ $((i % 10)) -eq 0 ]; then
    echo "Queued $i requests"
    sleep 1
  fi
done
wait

# Check daemon still healthy
cortex daemon health

# Check no crashes in logs
journalctl -u cortexd -n 10 --no-pager | grep -i "error\|crash\|segfault"
```

---

## Phase 12: Configuration Testing

### Step 12.1: Test Thread Configuration

```bash
# Edit config
nano ~/.cortex/daemon.conf
# Change: n_threads to 2, 8, 16 (test different values)

# Reload
cortex daemon reload-config

# Check logs
journalctl -u cortexd -n 5 --no-pager | grep -i thread

# Measure difference
# - Lower threads: slower inference, less CPU
# - Higher threads: faster inference, more CPU
```

### Step 12.2: Test Context Window

```bash
# Edit config  
sed -i 's|n_ctx=.*|n_ctx=256|g' ~/.cortex/daemon.conf
cortex daemon reload-config

# Try inference with longer prompt
LONG_PROMPT=$(python3 -c "print('test ' * 200)")
echo "{\"command\":\"inference\",\"params\":{\"prompt\":\"$LONG_PROMPT\",\"max_tokens\":50}}" | \
  socat - UNIX-CONNECT:/run/cortex.sock | jq .

# Smaller context = less memory, potentially worse quality
```

---

## Phase 13: Stability Testing

### Step 13.1: 1-Hour Stability Test

```bash
# Create stability test script
cat > /tmp/stability_test.sh << 'SCRIPT'
#!/bin/bash
START=$(date +%s)
END=$((START + 3600))  # 1 hour
COUNT=0

while [ $(date +%s) -lt $END ]; do
  cat /tmp/inference_test.json | socat - UNIX-CONNECT:/run/cortex.sock > /dev/null 2>&1
  COUNT=$((COUNT + 1))
  
  if [ $((COUNT % 10)) -eq 0 ]; then
    TIME_ELAPSED=$(($(date +%s) - START))
    echo "[$(date)] Completed $COUNT requests in ${TIME_ELAPSED}s"
    ps aux | grep "[c]ortexd" | awk '{print "Memory: " $6 "KB"}'
    cortex daemon health 2>&1 | grep -i "memory\|queue"
  fi
  
  sleep 5
done

echo "Stability test complete: $COUNT requests in $(( $(date +%s) - START ))s"
SCRIPT

chmod +x /tmp/stability_test.sh
/tmp/stability_test.sh
```

### Step 13.2: Monitor for Issues

```bash
# Watch for during test:
# ✅ Memory stays stable (shouldn't grow continuously)
# ✅ No "out of memory" errors
# ✅ Daemon doesn't restart unexpectedly
# ✅ Response times consistent
# ✅ No file descriptor leaks

# Check during test
watch -n 5 'ps aux | grep cortexd | grep -v grep; journalctl -u cortexd -n 2 --no-pager'
```

---

## Phase 14: Comprehensive Checklist

### Build & Compilation
- [ ] CMake detects llama.cpp (shows "Found llama" or similar)
- [ ] Build completes without errors
- [ ] Binary size reasonable (~8-10MB)
- [ ] All dependencies linked (`ldd` shows libllama.so)
- [ ] No compiler warnings

### Installation
- [ ] Binary installed to /usr/local/bin/cortexd
- [ ] Systemd service file present and valid
- [ ] Configuration file created correctly
- [ ] Socket permissions set to 0666
- [ ] Service enabled (`systemctl is-enabled cortexd` shows enabled)

### Runtime
- [ ] Daemon starts without errors
- [ ] Socket created at /run/cortex.sock
- [ ] Model loads successfully (check logs)
- [ ] No immediate segfaults
- [ ] Responds to status command

### Model & Inference
- [ ] Model file exists and correct format
- [ ] Model loads in 5-30 seconds
- [ ] Inference produces output (not empty)
- [ ] Response latency < 500ms (depends on model)
- [ ] Multiple requests handled correctly

### Error Handling
- [ ] Invalid JSON handled gracefully
- [ ] Missing model path shows error
- [ ] Bad model path doesn't crash daemon
- [ ] Queue limits respected
- [ ] Resource limits enforced

### Performance
- [ ] Idle memory < 50MB
- [ ] Inference latency consistent
- [ ] No memory leaks (stable over time)
- [ ] CPU usage reasonable
- [ ] Can handle concurrent requests

---

## Known Limitations & Future Improvements

### Current Limitations
1. **Single Request Processing**: Inference processes one request at a time (queue-based)
2. **No Token Streaming**: Returns full response at once
3. **Fixed Context**: Context window not dynamically adjustable
4. **No Model Hot-Swap**: Must restart daemon to change models
5. **No Batching**: Can't batch multiple prompts

### Identified Bugs to Watch For
```
1. Memory leaks if model load fails mid-stream
   → Monitor memory during failed loads

2. Socket timeout not enforced on long inference
   → Check if requests >30s timeout properly

3. No rate limiting on queue
   → Test with 1000+ rapid requests

4. Config reload doesn't reload model
   → Must restart daemon to change model

5. Error messages could be more specific
   → "Failed to load model" doesn't say why
```

### Areas for Improvement
1. **Streaming Inference**: Real-time token output via Server-Sent Events
2. **Model Management**: Hot-swap models without restart
3. **Batch Processing**: Process multiple prompts in parallel
4. **Caching**: Cache inference results for identical prompts
5. **Metrics**: Export Prometheus metrics
6. **Rate Limiting**: Configurable request limits per second
7. **Custom Prompts**: System prompts and prompt templates
8. **Token Probabilities**: Return token alternatives
9. **Context Persistence**: Keep context between requests
10. **Model Info**: Return model name, size, parameters

---

## Troubleshooting During Testing

### Socket Connection Refused
```bash
# Check daemon running
systemctl status cortexd

# Check socket exists
ls -la /run/cortex.sock

# Try restarting
sudo systemctl restart cortexd
sleep 2

# Try again
cortex daemon status
```

### Model Load Fails
```bash
# Check model file
ls -la ~/.cortex/models/
file ~/.cortex/models/*.gguf

# Check config
cat ~/.cortex/daemon.conf | grep model_path

# Check logs
journalctl -u cortexd -n 20 --no-pager | grep -i "model\|load"

# Try with full path
sed -i "s|~|$HOME|g" ~/.cortex/daemon.conf
cortex daemon reload-config
```

### Compilation Fails
```bash
# Check llama.cpp installed
pkg-config --cflags llama
pkg-config --libs llama

# Try reinstalling
sudo apt install --reinstall libllama-dev

# Check CMake output carefully
cd daemon/build
cmake -DCMAKE_VERBOSE_MAKEFILE=ON ..
```

---

## Next Steps After Testing

1. **If all tests pass**: Ready for production deployment
2. **If issues found**: Review logs and update code
3. **Performance tuning**: Adjust n_threads based on hardware
4. **Model selection**: Choose model for your use case
5. **Monitoring**: Set up log aggregation and metrics

---

**Testing Expected Duration**: 2-4 hours total

