# Cortex Linux User Guide

## Basic Commands

### Installation
```bash
# Natural language installation
cortex install "python for data science"

# Specific packages
cortex install nginx postgresql redis

# With optimization
cortex install "cuda drivers" --optimize-gpu
```

### System Management
```bash
# Check what's installed
cortex list

# System health check
cortex health

# View installation history
cortex history

# Rollback last installation
cortex rollback

# Rollback to specific point
cortex rollback --to <timestamp>
```

### Simulation Mode

Test installations without making changes:
```bash
cortex simulate "install oracle 23 ai"
# Shows: disk space, dependencies, estimated time
```

### Predictive Error Prevention

Cortex automatically analyzes installation requests for potential risks (kernel mismatch, low RAM, disk space) before execution. If a risk is detected, you will see a warning panel and be asked for confirmation.

```bash
# Example warning for risky hardware/software combo
cortex install "nvidia-cuda-latest"
```

### Progress & Notifications
```bash
# Installation with progress
cortex install "docker kubernetes" --show-progress

# Desktop notifications (if available)
cortex install "large-package" --notify
```

## Advanced Features

### Import from Requirements
```bash
# Python projects
cortex import requirements.txt

# Node projects
cortex import package.json
```

### Configuration Templates
```bash
# Generate nginx config
cortex config nginx --template webserver

# Generate PostgreSQL config
cortex config postgresql --template production
```

### System Profiles
```bash
# Install complete stacks
cortex profile "web-development"
cortex profile "data-science"
cortex profile "devops"
```

## Troubleshooting

### Installation Failed
```bash
# View error details
cortex log --last

# Auto-fix attempt
cortex fix --last-error

# Manual rollback
cortex rollback
```

### Check Dependencies
```bash
# View dependency tree
cortex deps <package>

# Check conflicts
cortex check conflicts
```

## Getting Help

- **Discord:** https://discord.gg/uCqHvxjU83
- **FAQ:** [FAQ](FAQ)
- **Issues:** https://github.com/cortexlinux/cortex/issues
