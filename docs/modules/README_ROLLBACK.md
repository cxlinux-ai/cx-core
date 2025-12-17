# Installation History and Rollback System

Complete installation tracking with safe rollback capabilities for Cortex Linux.

## Features

- ✅ **Full Installation Tracking** - Every installation recorded in SQLite
- ✅ **Before/After Snapshots** - Package states captured automatically
- ✅ **Safe Rollback** - Restore previous system state
- ✅ **Dry Run Mode** - Preview rollback actions
- ✅ **History Export** - JSON/CSV export for analysis
- ✅ **Automatic Cleanup** - Remove old records
- ✅ **CLI and Programmatic Access**
- ✅ **Production-Ready** - Handles errors, conflicts, partial installations

## Usage

### View Installation History

```bash
# List recent installations
cortex history

# List last 10
cortex history --limit 10

# Filter by status
cortex history --status failed

# Show specific installation details
cortex history show <install_id>
```

**Example Output:**
```
ID                 Date                 Operation    Packages                       Status         
====================================================================================================
a3f4c8e1d2b9f5a7  2025-11-09 14:23:15  install      docker, containerd +2          success
b2e1f3d4c5a6b7e8  2025-11-09 13:45:32  upgrade      nginx                          success
c1d2e3f4a5b6c7d8  2025-11-09 12:10:01  install      postgresql +3                  failed
```

### View Detailed Installation

```bash
cortex history show a3f4c8e1d2b9f5a7
```

**Example Output:**
```
Installation Details: a3f4c8e1d2b9f5a7
============================================================
Timestamp: 2025-11-09T14:23:15.123456
Operation: install
Status: success
Duration: 127.45s

Packages: docker, containerd, docker-ce-cli, docker-buildx-plugin

Commands executed:
  sudo apt-get update
  sudo apt-get install -y docker
  sudo apt-get install -y containerd

Rollback available: True
```

### Rollback Installation

```bash
# Dry run (show what would happen)
cortex rollback a3f4c8e1d2b9f5a7 --dry-run

# Actually rollback
cortex rollback a3f4c8e1d2b9f5a7
```

**Dry Run Output:**
```
Rollback actions (dry run):
sudo apt-get remove -y docker
sudo apt-get remove -y containerd
sudo apt-get remove -y docker-ce-cli
sudo apt-get remove -y docker-buildx-plugin
```

### Export History

```bash
# Export to JSON
python3 installation_history.py export history.json

# Export to CSV
python3 installation_history.py export history.csv --format csv
```

### Cleanup Old Records

```bash
# Remove records older than 90 days (default)
python3 installation_history.py cleanup

# Remove records older than 30 days
python3 installation_history.py cleanup --days 30
```

## Programmatic Usage

### Recording Installations

```python
from installation_history import (
    InstallationHistory,
    InstallationType,
    InstallationStatus
)
from datetime import datetime

history = InstallationHistory()

# Start recording
install_id = history.record_installation(
    operation_type=InstallationType.INSTALL,
    packages=['nginx', 'nginx-common'],
    commands=[
        'sudo apt-get update',
        'sudo apt-get install -y nginx'
    ],
    start_time=datetime.now()
)

# ... perform installation ...

# Update with result
history.update_installation(
    install_id,
    InstallationStatus.SUCCESS
)

# Or if failed:
history.update_installation(
    install_id,
    InstallationStatus.FAILED,
    error_message="Package not found"
)
```

### Querying History

```python
# Get recent history
recent = history.get_history(limit=20)

for record in recent:
    print(f"{record.id}: {record.operation_type.value}")
    print(f"  Packages: {', '.join(record.packages)}")
    print(f"  Status: {record.status.value}")

# Get specific installation
record = history.get_installation(install_id)
if record:
    print(f"Duration: {record.duration_seconds}s")
```

### Performing Rollback

```python
# Check if rollback is available
record = history.get_installation(install_id)
if record.rollback_available:
    
    # Dry run first
    success, message = history.rollback(install_id, dry_run=True)
    print(f"Would execute:\n{message}")
    
    # Confirm with user
    if user_confirms():
        success, message = history.rollback(install_id)
        if success:
            print(f"✅ Rollback successful: {message}")
        else:
            print(f"❌ Rollback failed: {message}")
```

## Data Model

### InstallationRecord

```python
@dataclass
class InstallationRecord:
    id: str                          # Unique identifier
    timestamp: str                   # ISO format datetime
    operation_type: InstallationType # install/upgrade/remove/rollback
    packages: List[str]              # Package names
    status: InstallationStatus       # success/failed/rolled_back
    before_snapshot: List[PackageSnapshot]  # State before
    after_snapshot: List[PackageSnapshot]   # State after
    commands_executed: List[str]     # Commands run
    error_message: Optional[str]     # Error if failed
    rollback_available: bool         # Can be rolled back
    duration_seconds: Optional[float] # How long it took
```

### PackageSnapshot

```python
@dataclass
class PackageSnapshot:
    package_name: str       # Package identifier
    version: str            # Version installed
    status: str             # installed/not-installed/config-files
    dependencies: List[str] # Package dependencies
    config_files: List[str] # Configuration files
```

## Database Schema

SQLite database stored at `/var/lib/cortex/history.db` (or `~/.cortex/history.db` if system directory not accessible):

```sql
CREATE TABLE installations (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    packages TEXT NOT NULL,
    status TEXT NOT NULL,
    before_snapshot TEXT,
    after_snapshot TEXT,
    commands_executed TEXT,
    error_message TEXT,
    rollback_available INTEGER,
    duration_seconds REAL
);

CREATE INDEX idx_timestamp ON installations(timestamp);
```

## Integration with Cortex

### Automatic Recording

The installation history is automatically recorded when using `cortex install`:

```bash
$ cortex install docker --execute
🧠 Understanding request...
📦 Planning installation...
⚙️ Installing docker...

Generated commands:
  1. sudo apt-get update
  2. sudo apt-get install -y docker.io

Executing commands...

✅ docker installed successfully!

Completed in 45.23 seconds

📝 Installation recorded (ID: a3f4c8e1d2b9f5a7)
   To rollback: cortex rollback a3f4c8e1d2b9f5a7
```

### Cortex CLI Integration

```bash
# After any cortex install
$ cortex install docker
🧠 Analyzing dependencies...
📦 Installing docker and 4 dependencies...
✅ Installation complete (ID: a3f4c8e1d2b9f5a7)
   To rollback: cortex rollback a3f4c8e1d2b9f5a7

# View history
$ cortex history
ID                 Date                 Operation    Packages
================================================================
a3f4c8e1d2b9f5a7  2025-11-09 14:23:15  install      docker +4

# Rollback if needed
$ cortex rollback a3f4c8e1d2b9f5a7
⚠️  This will remove: docker, containerd, docker-ce-cli, docker-buildx-plugin
Continue? (y/N): y
🔧 Rolling back installation...
✅ Rollback complete
```

## Rollback Logic

### What Gets Rolled Back

1. **New Installations** → Packages are removed
2. **Upgrades/Downgrades** → Original version reinstalled
3. **Removals** → Packages reinstalled
4. **Failed Installations** → Partial changes reverted

### Rollback Limitations

**Cannot rollback:**
- System packages (apt, dpkg, etc.)
- Packages with broken dependencies
- Installations older than snapshots
- Manual file modifications

**Safety measures:**
- Dry run preview before execution
- Snapshot validation
- Dependency checking
- Conflict detection

## Performance

- **Recording overhead:** <0.5s per installation
- **Database size:** ~100KB per 1000 installations
- **Rollback speed:** ~30s for typical package
- **History query:** <0.1s for 1000 records

## Security Considerations

1. **Database permissions:** Only root/sudoers can modify
2. **Snapshot integrity:** Checksums for config files
3. **Command validation:** Sanitized before storage
4. **Audit trail:** All operations logged

## Testing

```bash
# Run unit tests
python -m pytest test/test_installation_history.py -v

# Test with real packages (requires sudo)
sudo python3 installation_history.py list
```

## Troubleshooting

### Database Locked

```bash
# Check for processes using database
lsof /var/lib/cortex/history.db

# If stuck, restart
sudo systemctl restart cortex
```

### Rollback Failed

```bash
# View error details
cortex history show <install_id>

# Try manual rollback
sudo apt-get install -f
```

### Disk Space

```bash
# Check database size
du -h /var/lib/cortex/history.db

# Clean old records
python3 installation_history.py cleanup --days 30
```

## Future Enhancements

- [ ] Snapshot compression for large installations
- [ ] Incremental snapshots (only changed files)
- [ ] Remote backup integration
- [ ] Web UI for history browsing
- [ ] Automated rollback on boot failure
- [ ] Configuration file diff viewing
- [ ] Multi-installation atomic rollback

## Examples

### Scenario 1: Failed Installation Cleanup

```python
# Installation fails
install_id = history.record_installation(...)
try:
    install_package('broken-package')
except Exception as e:
    history.update_installation(install_id, InstallationStatus.FAILED, str(e))
    
    # Automatically rollback partial changes
    if auto_rollback_enabled:
        history.rollback(install_id)
```

### Scenario 2: Testing Package Updates

```python
# Install update
install_id = cortex_install(['nginx=1.24.0'])

# Test update
if not system_tests_pass():
    # Rollback to previous version
    history.rollback(install_id)
    print("Update rolled back - system restored")
```

### Scenario 3: Audit Trail

```python
# Export last month's installations
history = InstallationHistory()
history.export_history('audit_november.json')

# Analyze failures
failed = history.get_history(
    limit=1000,
    status_filter=InstallationStatus.FAILED
)
print(f"Failed installations: {len(failed)}")
```

## License

MIT License - Part of Cortex Linux

