# Troubleshooting Guide

Common errors and solutions for Cortex Linux.

## Table of Contents

- [API Key Issues](#api-key-issues)
- [Installation Errors](#installation-errors)
- [Network & Connectivity](#network--connectivity)
- [Permission Problems](#permission-problems)
- [LLM Provider Issues](#llm-provider-issues)
- [Package Manager Conflicts](#package-manager-conflicts)
- [Performance Issues](#performance-issues)
- [Rollback & Recovery](#rollback--recovery)

---

## API Key Issues

### Error: "No API key found"

**Symptom:**
```text
Error: No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.
```

**Solutions:**

1. **Use Ollama (FREE - No API key needed):**
```bash
# Quick setup
python scripts/setup_ollama.py
export CORTEX_PROVIDER=ollama
cortex install nginx --dry-run

# See full guide: docs/OLLAMA_SETUP.md
```

2. **Set the environment variable (Cloud APIs):**
```bash
# For Claude (recommended)
export ANTHROPIC_API_KEY='<YOUR_ANTHROPIC_API_KEY>'

# For OpenAI
export OPENAI_API_KEY='<YOUR_OPENAI_API_KEY>'
```

3.  **Add to shell config for persistence:**
```bash
echo 'export ANTHROPIC_API_KEY="<YOUR_ANTHROPIC_API_KEY>"' >> ~/.bashrc
source ~/.bashrc
```

4.  **Use the setup wizard:**
```bash
cortex wizard
```
```bash
export CORTEX_PROVIDER=ollama
cortex install docker
```

### Error: "API rate limit exceeded"

**Symptom:**
```text
Error: Rate limit exceeded. Please wait before trying again.
```

**Solutions:**
1.  **Wait and retry:**
```bash
sleep 60 && cortex install docker
```

2.  **Use a different provider temporarily:**
```bash
export CORTEX_PROVIDER=ollama
```

---

## Installation Errors

### Error: "Package not found"

**Symptom:**
```text
E: Unable to locate package xyz
```

**Solutions:**

1.  **Update package lists:**
```bash
sudo apt update
```

2.  **Use natural language for better matching:**
```bash
cortex install "text editor like vim" # Instead of exact package name
```

### Error: "Dependency problems"

**Solutions:**

1.  **Fix broken packages:**
```bash
sudo apt --fix-broken install
```

2.  **Update and upgrade:**
```bash
sudo apt update && sudo apt upgrade
```


### Error: "dpkg lock"

**Symptom:**
```text
E: Could not get lock /var/lib/dpkg/lock-frontend
```

**Solutions:**

1.  **Check what's using it:**
```bash
sudo lsof /var/lib/dpkg/lock-frontend
```

2. **If it's genuinely stuck, stop the specific process (use with caution):**
```bash
# Check for apt, apt-get, or unattended-upgrades
ps aux | egrep 'apt|apt-get|unattended' | egrep -v egrep

# Then (only if needed) kill the specific PID (replace <PID>):
sudo kill <PID>

# Recovery: Run these if the package manager breaks after killing the process
sudo dpkg --configure -a
sudo apt --fix-broken install
```
---

## Network & Connectivity

### Error: "Could not resolve host"

**Symptom:**
```text
Could not resolve 'archive.ubuntu.com'
```

**Solutions:**

1.  **Check internet connection:**
```bash
ping -c 3 8.8.8.8
```

2.  **Try different DNS (Temporary):**
    *Note: `/etc/resolv.conf` is often overwritten. Use `resolvectl` for permanent changes.*
```bash
# Append Google DNS
echo "nameserver 8.8.8.8" | sudo tee -a /etc/resolv.conf

# Rollback (Undo): Edit the file and remove the line
sudo nano /etc/resolv.conf
```


### Error: "SSL certificate problem"

**Solutions:**

1.  **Update CA certificates:**
```bash
sudo apt install ca-certificates
sudo update-ca-certificates
```

2.  **Check system time (SSL requires correct time):**
```bash
timedatectl status
sudo timedatectl set-ntp true
```
---

## Permission Problems

### Error: "Permission denied"

**Solutions:**

1.  **Run with sudo for system packages:**
```bash
sudo cortex install docker --execute
```

2.  **Check file ownership:**
```bash
ls -la ~/.cortex/
```

---

## LLM Provider Issues

### Error: "Ollama not running"

**Symptom:**
```text
Error: Could not connect to Ollama at localhost:11434
Ollama request failed. Is Ollama running? (ollama serve)
```

**Solutions:**

1.  **Quick Setup (Recommended):**
```bash
# Use the setup script
python scripts/setup_ollama.py

# Or follow the quick start guide
cat OLLAMA_QUICKSTART.md
```

2.  **Start Ollama Service:**
```bash
# Check if installed
which ollama

# Start service
ollama serve &

# Or use systemd
sudo systemctl start ollama
sudo systemctl enable ollama  # Auto-start on boot
```

3.  **Verify Ollama is running:**
```bash
# List models (also tests connection)
ollama list

# Test API endpoint
curl http://localhost:11434/api/tags
```

4.  **Install Ollama if missing:**
```bash
# Automated installation
curl -fsSL https://ollama.ai/install.sh | sh

# Or use setup script
python scripts/setup_ollama.py
```

### Error: "No Ollama models found"

**Symptom:**
```text
Error: Model 'llama3.2' not found
```

**Solutions:**

1.  **Download a model:**
```bash
# Recommended (2GB)
ollama pull llama3.2

# Alternatives
ollama pull llama3.2:1b      # Smaller (1.3GB)
ollama pull llama3.1:8b      # More capable (4.7GB)
```

2.  **Check downloaded models:**
```bash
ollama list
```

3.  **Update config to use installed model:**
```bash
# In .env file
export OLLAMA_MODEL=your-model-name

# Or in ~/.cortex/config.json
{
  "ollama_model": "your-model-name"
}
```

### Error: "Ollama out of memory"

**Symptom:**
```text
Error: Failed to load model: out of memory
```

**Solutions:**

1.  **Use smaller model:**
```bash
# Switch to 1B parameter model (uses less RAM)
ollama pull llama3.2:1b
export OLLAMA_MODEL=llama3.2:1b
```

2.  **Check available RAM:**
```bash
free -h
```

3.  **Close other applications** to free up memory

4.  **See model requirements:**
```bash
# Check model size
ollama list

# See: docs/OLLAMA_SETUP.md for RAM requirements
```

### Error: "Context length exceeded"

**Symptom:**

```text
Error: This model's maximum context length is 4096 tokens
```

**Solutions:**

1.  **Simplify your request:**
    Instead of asking for a "complete development environment," try installing tools individually (e.g., "python development tools").

2.  **Change Provider:**
    Switch to a provider that supports larger context windows (e.g., Anthropic) using the wizard:

```bash
cortex wizard
```
---

## Package Manager Conflicts

### Error: "Snap vs apt conflict"

**Symptom:**
```text
error: cannot install "firefox": classic confinement requires snaps
```

**Solutions:**

1.  **Use snap with classic:**
```bash
sudo snap install firefox --classic
```
---

## Performance Issues

### Slow AI responses

**Solutions:**

1.  **Use local LLM:**
```bash
export CORTEX_PROVIDER=ollama
```

2.  **Check network latency:**
```bash
ping api.anthropic.com
```
---

## Rollback & Recovery

### How to undo an installation
```bash
# View installation history
cortex history

# Rollback last installation
cortex rollback

# Rollback specific installation
cortex rollback <installation-id>
```

### System recovery

If Cortex causes system issues:

1.  **Boot into recovery mode**
2.  **Use dpkg to fix:**
```bash
sudo dpkg --configure -a
sudo apt --fix-broken install
```