# Package Sandbox Testing Environment

Test packages in isolated Docker containers before installing to the main system.

## Overview

The sandbox feature provides a safe way to test packages before committing to a system-wide installation. It uses Docker containers as isolated environments, allowing you to:

- Install packages without affecting your system
- Run automated tests to validate functionality
- Safely promote tested packages to your main system
- Clean up test environments when done

## Requirements

- **Docker** is required for sandbox commands
- Docker must be installed and running
- Other Cortex commands work without Docker

```bash
# Check if Docker is available
docker --version
docker info
```

If Docker is not installed, sandbox commands will show:
```
Error: Docker is required for sandbox commands.
Install Docker from https://docs.docker.com/get-docker/
```

## Quick Start

```bash
# Create a sandbox environment
$ cortex sandbox create test-env
✓ Sandbox environment 'test-env' created

# Install a package in the sandbox
$ cortex sandbox install test-env nginx
✓ nginx installed in sandbox

# Run tests to validate the package
$ cortex sandbox test test-env
Running tests in sandbox 'test-env'...
   ✓  nginx: binary exists
   ✓  nginx: functional (--version)
   ✓  nginx: no conflicts
All tests passed

# Promote to main system (fresh install on host)
$ cortex sandbox promote test-env nginx
Promote 'nginx' to main system? [Y/n]: y
✓ nginx installed on main system

# Clean up the sandbox
$ cortex sandbox cleanup test-env
✓ Sandbox 'test-env' removed
```

## Commands

### `cortex sandbox create <name>`

Create a new sandbox environment.

```bash
cortex sandbox create test-env
cortex sandbox create test-env --image debian:12
```

Options:
- `--image`: Docker image to use (default: `ubuntu:22.04`)

### `cortex sandbox install <name> <package>`

Install a package in the sandbox environment.

```bash
cortex sandbox install test-env nginx
cortex sandbox install test-env docker.io
```

### `cortex sandbox test <name> [package]`

Run automated tests in the sandbox.

```bash
# Test all installed packages
cortex sandbox test test-env

# Test a specific package
cortex sandbox test test-env nginx
```

Tests performed:
- **Binary exists**: Checks if package binary is available
- **Functional**: Runs `--version` or `--help` to verify it works
- **No conflicts**: Runs `dpkg --audit` to check for issues

### `cortex sandbox promote <name> <package>`

Install a tested package on the main system.

```bash
cortex sandbox promote test-env nginx
cortex sandbox promote test-env nginx --dry-run  # Preview only
cortex sandbox promote test-env nginx -y         # Skip confirmation
```

Options:
- `--dry-run`: Show what would be installed without executing
- `-y, --yes`: Skip the confirmation prompt

**Important**: Promotion runs a fresh `apt install` on the host system. It does NOT copy files from the container.

### `cortex sandbox cleanup <name>`

Remove a sandbox environment.

```bash
cortex sandbox cleanup test-env
cortex sandbox cleanup test-env --force
```

Options:
- `-f, --force`: Force removal even if container is running

### `cortex sandbox list`

List all sandbox environments.

```bash
cortex sandbox list
```

### `cortex sandbox exec <name> <command...>`

Execute an arbitrary command in the sandbox.

```bash
cortex sandbox exec test-env cat /etc/os-release
cortex sandbox exec test-env apt list --installed
```

## Workflow Example

### Testing a Complex Installation

```bash
# Create isolated environment
cortex sandbox create docker-test

# Install Docker in sandbox
cortex sandbox install docker-test docker.io

# Run tests
cortex sandbox test docker-test
# Output:
#    ✓  docker.io: package installed
#    ✓  docker.io: no conflicts

# Check version
cortex sandbox exec docker-test docker --version

# If satisfied, promote to main system
cortex sandbox promote docker-test docker.io

# Clean up
cortex sandbox cleanup docker-test
```

### Testing Multiple Packages

```bash
cortex sandbox create webstack

cortex sandbox install webstack nginx
cortex sandbox install webstack postgresql
cortex sandbox install webstack redis-server

cortex sandbox test webstack

# Promote all
cortex sandbox promote webstack nginx -y
cortex sandbox promote webstack postgresql -y
cortex sandbox promote webstack redis-server -y

cortex sandbox cleanup webstack
```

## Limitations

Sandbox environments run inside Docker containers. The following **cannot** be tested in sandbox:

| Category | Examples | Reason |
|----------|----------|--------|
| System services | `systemctl start nginx` | No systemd in container |
| Kernel modules | `modprobe`, `insmod` | Shared host kernel |
| Hardware access | `nvidia-smi`, `lspci` | No device passthrough |
| Network config | `iptables`, `ufw` | Network namespace isolation |
| Boot/init | `reboot`, `shutdown` | Container lifecycle |

### What Works Well

✅ Package installation (`apt install`)
✅ Binary version checks (`--version`)
✅ Basic functionality tests
✅ Dependency resolution
✅ Conflict detection

### What Doesn't Work

❌ Service management (`systemctl`, `service`)
❌ Kernel operations (`modprobe`, `sysctl`)
❌ Hardware detection and drivers
❌ Network firewall rules
❌ System boot behavior

## How Promotion Works

When you run `cortex sandbox promote`, Cortex does **NOT**:
- Export Docker container filesystem
- Copy files from container to host
- Use any Docker layer magic

Instead, it simply runs:
```bash
sudo apt-get install -y <package>
```

The sandbox is a **validation step only**. Think of it as a "dry run with real installation" to catch issues before they affect your system.

## Data Storage

Sandbox metadata is stored in `~/.cortex/sandboxes/`:
```
~/.cortex/sandboxes/
├── test-env.json
├── webstack.json
└── docker-test.json
```

Each file contains:
- Sandbox name
- Container ID
- Docker image used
- Creation timestamp
- List of installed packages

## Troubleshooting

### Docker permission denied

```bash
# Add your user to the docker group
sudo usermod -aG docker $USER
# Log out and back in
```

### Container won't start

```bash
# Check if Docker daemon is running
sudo systemctl status docker

# Start Docker if needed
sudo systemctl start docker
```

### Sandbox metadata out of sync

If a container was removed manually:
```bash
# Force cleanup metadata
rm ~/.cortex/sandboxes/<name>.json
```

### Tests failing unexpectedly

Some packages don't have binaries matching their package name:
```bash
# Use exec to investigate
cortex sandbox exec test-env dpkg -L <package>
cortex sandbox exec test-env apt show <package>
```

## Integration with Cortex

The sandbox feature integrates with Cortex's AI command generation. When running in sandbox mode, the LLM is constrained to:

- Use only `apt` for installation
- Avoid `systemctl`, `service`, and kernel commands
- Prefer version checks (`--version`) for validation

This ensures generated commands are compatible with the Docker sandbox environment.
