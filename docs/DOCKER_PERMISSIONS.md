# Docker Permission Management

Address and repair file ownership issues that occur when Docker containers create files in host-mounted directories.

## Overview

When using Docker bind mounts on Linux, files created by processes inside the container are often owned by the `root` user (UID 0) or a container-specific UID. This results in "Permission Denied" errors when the host user tries to edit or delete these files.

The `cortex docker permissions` command automates the identification and reclamation of these files, ensuring your local development workflow remains seamless.

## Usage

### Basic Usage
```bash
# Scan and fix permissions in the current directory (dry-run by default)
cortex docker permissions

# Actually apply ownership changes (reclaims files for host user)
cortex docker permissions --execute

# Run without interactive confirmation prompts
cortex docker permissions --yes
```

### Command Options

| Option | Short | Description |
|--------|-------|-------------|
| `--execute` | `-e` | Apply ownership changes (default: dry-run) |
| `--yes` | `-y` | Skip the confirmation prompt for repairs |

## Features

### 1. Ownership Diagnosis

Cortex recursively scans the target directory to find files where the owner UID/GID does not match the current host user.

**Smart Exclusions:** Automatically skips performance-heavy or system directories:
- `.git`
- `node_modules`
- `venv` / `.venv`
- `__pycache__`

### 2. Automated Repair

When a mismatch is found, Cortex constructs a targeted `chown` command.

- **Safety:** Uses `sudo` only for the specific paths requiring repair.
- **Verification:** Detection is based on `os.getuid()` and `os.getgid()` to ensure files are returned to the correct active user.

### 3. Compose Validation

The tool checks for the existence of a `docker-compose.yml` file and analyzes service definitions.

- **Prevention:** If a service is missing a `user:` mapping, Cortex suggests the exact line to add to prevent future root-owned files.

## Examples

### Identifying Permission Issues
```bash
$ cortex docker permissions

📋 Found 12 files owned by root (UID 0)

Files requiring repair:
  • ./logs/app.log
  • ./data/db.sqlite
  • ./uploads/image_01.png
  ... and 9 more

To reclaim ownership, run with --execute flag
Example: cortex docker permissions --execute
```

### Executing a Repair
```bash
$ cortex docker permissions --execute

📋 Found 12 files owned by root (UID 0)
Reclaim ownership for these files? [Y/n]: y

Applying repairs...
[sudo] password for user: 

✅ Ownership reclaimed for 12 files.
All files are now owned by user (1000:1000)
```

## Technical Implementation

### UID/GID Detection

The tool utilizes the `os` and `pathlib` Python modules to compare file metadata:
```python
import os
from pathlib import Path

# Get host user context
host_uid = os.getuid()
host_gid = os.getgid()

# Check file stats
file_info = Path("data/app.log").stat()
if file_info.st_uid != host_uid:
    print("Mismatch detected!")
```

## Troubleshooting

### Sudo Requirement

Because reclaiming files owned by `root` requires elevated privileges, you will be prompted for your system password when running with `--execute`.

### Directory Permissions

If the parent directory itself is owned by root and lacks "Write" permissions for your user, Cortex will attempt to repair the directory ownership first before processing the files inside.

## Related Commands

- `cortex sandbox <cmd>` - Run and test packages in an isolated environment.
- `cortex status` - Check system health and Docker daemon status.
- `cortex history` - Review changes made to the system.