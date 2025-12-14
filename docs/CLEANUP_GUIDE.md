# Disk Cleanup Guide

This guide explains how to use Cortex's disk cleanup functionality to reclaim storage space on your system.

## Overview

Cortex provides intelligent disk cleanup capabilities that can:

- **Scan** for reclaimable space across multiple categories
- **Clean** package caches, orphaned packages, temporary files, and old logs
- **Undo** cleanup operations by restoring files from quarantine
- **Schedule** automatic cleanup tasks

## Quick Start

```bash
# Scan for cleanup opportunities
cortex cleanup scan

# Run cleanup (with confirmation)
cortex cleanup run

# Run cleanup without confirmation (safe mode)
cortex cleanup run --safe --yes
```

## Commands

### Scan

Identify cleanup opportunities without making any changes:

```bash
cortex cleanup scan
```

**Output example:**

```text
💾 Cleanup Opportunities:

Category           Items    Size
Package Cache      45       2.5 GB
Orphaned Packages  8        450 MB
Temporary Files    123      380 MB
Old Logs           12       1.2 GB

Total reclaimable: 4.5 GB
```

### Run

Execute cleanup operations:

```bash
# Safe mode (default) - with confirmation
cortex cleanup run

# Safe mode - skip confirmation
cortex cleanup run --safe --yes

# Force mode - clean all items (use with caution)
cortex cleanup run --force --yes
```

**Options:**

| Option | Description |
|--------|-------------|
| `--safe` | Only perform safe cleanup operations (default) |
| `--force` | Clean all found items including potentially risky ones |
| `-y, --yes` | Skip confirmation prompt |

### Undo

Restore files that were cleaned:

```bash
# List restorable items
cortex cleanup undo

# Restore a specific item
cortex cleanup undo <item-id>
```

**Example:**

```text
$ cortex cleanup undo
ID       File              Size       Date
abc123   temp_file.txt     1.2 MB     2024-01-15 10:30
def456   old_log.log       500 KB     2024-01-15 10:30

Run 'cortex cleanup undo <id>' to restore.

$ cortex cleanup undo abc123
✓ Restored item abc123
```

### Schedule

Configure automatic cleanup:

```bash
# Show current schedule status
cortex cleanup schedule --show

# Enable weekly cleanup (default)
cortex cleanup schedule --enable

# Enable daily cleanup
cortex cleanup schedule --enable --interval daily

# Enable monthly cleanup
cortex cleanup schedule --enable --interval monthly

# Disable scheduled cleanup
cortex cleanup schedule --disable
```

**Supported intervals:**

| Interval | Description |
|----------|-------------|
| `daily` | Run at 3:00 AM every day |
| `weekly` | Run at 3:00 AM every Sunday |
| `monthly` | Run at 3:00 AM on the 1st of each month |

## Cleanup Categories

### Package Cache

Location: `/var/cache/apt/archives`

Removes downloaded `.deb` package files that are no longer needed after installation.

### Orphaned Packages

Packages that were installed as dependencies but are no longer required by any installed package.

### Temporary Files

Location: `/tmp` and `~/.cache`

Old temporary files (default: older than 7 days).

### Old Logs

Location: `/var/log`

Large log files older than a specified age (default: >100MB and >7 days).

## Safety Features

### Quarantine System

When Cortex cleans files, they are first moved to a quarantine directory (`~/.cortex/trash/`) rather than being permanently deleted. This allows you to restore files using the `undo` command.

Quarantined files are automatically removed after 30 days.

### Safe Mode

The default `--safe` mode ensures that only non-critical files are removed:

- Package cache (safe to remove)
- Orphaned packages (safe to remove)
- Old temporary files (safe to remove)
- Old logs (compressed, not deleted)

### Dry Run

While not directly exposed, the underlying system supports dry-run operations for testing.

## Scheduling Implementation

Cortex supports two scheduling backends:

1. **systemd timers** (preferred) - Used automatically if available
2. **cron** - Fallback option

Configuration is stored in `~/.cortex/cleanup_schedule.json`.

## Troubleshooting

### Permission Denied

Some cleanup operations require root privileges:

```bash
# Clean system package cache
sudo cortex cleanup run
```

### No Space Reclaimed

If scan shows reclaimable space but run reports no space freed:

1. Check if files were already cleaned by another process
2. Verify write permissions to target directories
3. Check system logs for errors

### Restore Failed

If `undo` fails to restore a file:

1. Verify the quarantine file exists in `~/.cortex/trash/`
2. Check if the original path is writable
3. Ensure parent directory exists

## Configuration

Default settings for cleanup:

| Setting | Default | Description |
|---------|---------|-------------|
| Temp file age | 7 days | Minimum age to consider temp files |
| Log min size | 100 MB | Minimum log file size to consider |
| Log age | 7 days | Minimum age for log files |
| Quarantine retention | 30 days | Days before quarantined files are deleted |

---

For more information, visit: [Cortex Cleanup Documentation](https://cortexlinux.com/docs/cleanup)
