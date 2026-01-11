# Unified Package Manager

> Addresses Issue [#450](https://github.com/cortexlinux/cortex/issues/450): Snap/Flatpak Unified Manager

## Overview

The Unified Package Manager provides transparency and control over package sources on Ubuntu/Debian systems. It helps users understand whether packages are installed as .deb, snap, or flatpak, and provides tools to manage permissions and disable "forced" snap installations.

## Features

1. **Package Source Detection** - See where a package is available (deb/snap/flatpak)
2. **Package Comparison** - Compare versions and sizes across formats
3. **Installed Package Listing** - List packages by format
4. **Permission Management** - View and modify snap/flatpak permissions (like Flatseal)
5. **Snap Redirect Detection** - Find packages that redirect apt→snap
6. **Storage Analysis** - See disk usage breakdown by format

## Usage

### Check Package Sources

```bash
# See where a package is available
cortex pkg sources firefox

# Output shows availability in each format with version info
```

### Compare Packages

```bash
# Compare package across all formats
cortex pkg compare firefox

# Shows versions, sizes, and installation status for each format
```

### List Installed Packages

```bash
# List all packages by format
cortex pkg list

# Filter by format
cortex pkg list --format snap
cortex pkg list --format flatpak
cortex pkg list --format deb
```

### View Permissions

```bash
# View snap permissions (interfaces)
cortex pkg permissions firefox

# View flatpak permissions
cortex pkg permissions org.mozilla.firefox --format flatpak
```

### Analyze Storage

```bash
# See storage breakdown by package format
cortex pkg storage

# Shows total size and top packages for each format
```

### Manage Snap Redirects

```bash
# Check for snap redirects (apt packages that secretly install snaps)
cortex pkg snap-redirects

# Disable snap redirects (requires sudo)
sudo cortex pkg snap-redirects --disable
```

## Technical Details

### Module: `cortex/unified_package_manager.py`

Core classes:

- `UnifiedPackageManager` - Main manager class
- `PackageFormat` - Enum for deb/snap/flatpak
- `PackageInfo` - Package metadata dataclass
- `StorageAnalysis` - Storage breakdown dataclass

### CLI Commands

All commands are under the `cortex pkg` namespace:

| Command                     | Description             |
| --------------------------- | ----------------------- |
| `pkg sources <package>`     | Show available sources  |
| `pkg compare <package>`     | Compare across formats  |
| `pkg list [--format]`       | List installed packages |
| `pkg permissions <package>` | View permissions        |
| `pkg storage`               | Storage analysis        |
| `pkg snap-redirects`        | Check/disable redirects |

## Safety Notes

> [!WARNING]
> The `--disable` option for snap-redirects modifies system configuration at `/etc/apt/apt.conf.d/20snapd.conf`. A backup is created automatically, and the change can be reverted by restoring the backup.

## Testing

Run unit tests:

```bash
python -m pytest tests/test_unified_package_manager.py -v
```

The test suite includes 30+ test cases covering all functionality with mocked subprocess calls.
