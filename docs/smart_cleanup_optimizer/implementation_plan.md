# Implementation Plan - Smart Cleanup and Disk Space Optimizer (#125)

## Goal Description
Implement an intelligent cleanup system that identifies unused packages, clears caches, removes orphaned dependencies, cleans temp files, and compresses logs. The system will provide both a "scan" mode to estimate reclaimable space and a "run" mode to execute cleanup with safety checks.

## User Review Required
> [!IMPORTANT]
> - Confirm the logic for detecting "orphaned dependencies" (using `apt-get autoremove` simulation or similar?)
> - Confirm log compression retention policy (e.g., compress logs older than 7 days, delete older than 30?)
> - Review the CLI UX for `cortex cleanup scan` vs `cortex cleanup run`.

## Proposed Changes

### Core Logic (`cortex/optimizer.py` - NEW)
- Create `CleanupOptimizer` class.
- **Components**:
    - `scan()`: Aggregates stats from:
        - `PackageManager.get_cleanable_items()`
        - `LogManager.scan_logs()`
        - `TempCleaner.scan_temp()`
    - `clean(safe_mode=True)`: Generates commands and executes them using `InstallationCoordinator`.
    - `LogManager`:
        - `scan_logs()`: Checks `/var/log` for large/old files (e.g. `*.log`, `*.gz`).
        - `get_compression_commands()`: Returns commands to gzip old logs (`find /var/log -name "*.log" -mtime +7 -exec gzip {} \+`).
    - `TempCleaner`:
        - `scan_temp()`: Checks `/tmp` and similar dirs.
        - `get_cleanup_commands()`: Returns commands to remove temp files safely (`find /tmp -type f -atime +10 -delete`).

### Package Manager (`cortex/packages.py`)
- Enhance `get_cleanable_items()` to be more robust (handle PermissionDenied gracefully).
- Ensure `get_cleanup_commands` covers all package manager types properly.

### CLI (`cortex/cli.py`)
- Add `cleanup` command group.
- `scan`: Calls `optimizer.scan()` and uses `rich` table to display potential savings.
- `run`:
    - Generates all cleanup commands.
    - Shows them to user.
    - Asks for confirmation (unless `--yes`).
    - Uses `InstallationCoordinator` (existing class) to execute commands with progress bars.

## Verification Plan

### Automated Tests
- Unit tests for `optimizer.py`:
    - Mock `os.stat` and `os.walk` to test log/temp scanning.
    - Mock `PackageManager` to test aggregation.
- Integration tests:
    - Verify `cleanup` command structure.

### Manual Verification
- **Safety Check**: Run `cortex cleanup scan` and verify it detects actual junk files without false positives.
- **Execution**: Run `cortex cleanup run --safe --dry-run` to see generated commands.
- **Log Compression**: Verify `gzip` commands are generated for old logs.
- **Orphan Cleanup**: Verify `apt-get autoremove` is included.
