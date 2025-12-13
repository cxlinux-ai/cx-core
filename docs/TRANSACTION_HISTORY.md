# Transaction History and Undo Module

**Issue:** #258  
**Status:** Ready for Review  
**Bounty:** As specified in issue (+ bonus after funding)

## Overview

Complete transaction tracking and undo capabilities for all Cortex package operations. Every install, remove, upgrade, and configure operation is recorded with full state snapshots, enabling safe rollback when needed.

## Features

### Full Transaction Tracking

- Records all package operations with timestamps
- Captures before/after package states
- Tracks operation duration and success/failure
- Stores rollback commands automatically

### Safe Undo Operations

- Preview what undo will do before executing
- Dry-run mode for safety
- Warnings for system-critical packages
- Partial rollback recovery

### Rich History Search

- Filter by package name
- Filter by operation type
- Filter by date range
- Filter by status

## Installation

```python
from cortex.transaction_history import (
    TransactionHistory,
    UndoManager,
    record_install,
    undo_last,
    show_history
)
```

## Usage Examples

### Recording Transactions

```python
from cortex.transaction_history import TransactionHistory, TransactionType

history = TransactionHistory()

# Start a transaction
tx = history.begin_transaction(
    TransactionType.INSTALL,
    ["nginx", "redis"],
    "cortex install nginx redis"
)

# ... perform the actual installation ...

# Complete the transaction
history.complete_transaction(tx, success=True)
```

### Using Convenience Functions

```python
from cortex.transaction_history import record_install, record_remove

# Record an install
tx = record_install(["docker"], "cortex install docker")
# ... do installation ...
tx.complete(success=True)

# Record a removal
tx = record_remove(["vim"], "cortex remove vim")
# ... do removal ...
tx.complete(success=True)
```

### Viewing History

```python
from cortex.transaction_history import show_history, get_history

# Quick view of recent transactions
recent = show_history(limit=10)
for tx in recent:
    print(f"{tx['timestamp']} | {tx['transaction_type']} | {tx['packages']}")

# Advanced search
history = get_history()
nginx_txs = history.search(package="nginx")
installs = history.search(transaction_type=TransactionType.INSTALL)
today = history.search(since=datetime.now() - timedelta(days=1))
```

### Undo Operations

```python
from cortex.transaction_history import UndoManager, get_undo_manager

manager = get_undo_manager()

# Check if undo is possible
can_undo, reason = manager.can_undo(transaction_id)
print(f"Can undo: {can_undo}, Reason: {reason}")

# Preview the undo
preview = manager.preview_undo(transaction_id)
print(f"Commands to execute: {preview['commands']}")
print(f"Safe to undo: {preview['is_safe']}")

# Execute undo (dry run first)
result = manager.undo(transaction_id, dry_run=True)
print(f"Would execute: {result['commands']}")

# Execute for real
result = manager.undo(transaction_id)
print(f"Success: {result['success']}")
```

### Quick Undo Last Operation

```python
from cortex.transaction_history import undo_last

# Preview
result = undo_last(dry_run=True)

# Execute
result = undo_last()
if result['success']:
    print("Rollback complete!")
else:
    print(f"Error: {result['error']}")
```

## API Reference

### TransactionHistory

Main class for transaction storage and retrieval.

**Constructor:**
```python
TransactionHistory(db_path: Optional[Path] = None)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `begin_transaction(type, packages, command)` | Start tracking a transaction |
| `complete_transaction(tx, success, error_message)` | Complete a transaction |
| `get_transaction(id)` | Get transaction by ID |
| `get_recent(limit, status_filter)` | Get recent transactions |
| `search(package, type, since, until)` | Search with filters |
| `get_stats()` | Get statistics |

### UndoManager

Handles undo/rollback operations.

**Methods:**

| Method | Description |
|--------|-------------|
| `can_undo(transaction_id)` | Check if transaction can be undone |
| `preview_undo(transaction_id)` | Preview undo operation |
| `undo(transaction_id, dry_run, force)` | Execute undo |
| `undo_last(dry_run)` | Undo most recent transaction |

### Transaction Types

```python
class TransactionType(Enum):
    INSTALL = "install"
    REMOVE = "remove"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    AUTOREMOVE = "autoremove"
    PURGE = "purge"
    CONFIGURE = "configure"
    BATCH = "batch"
```

### Transaction Statuses

```python
class TransactionStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIALLY_COMPLETED = "partially_completed"
```

## Data Model

### Transaction

```python
@dataclass
class Transaction:
    id: str                          # Unique transaction ID
    transaction_type: TransactionType
    packages: List[str]              # Packages involved
    timestamp: datetime              # When started
    status: TransactionStatus
    before_state: Dict[str, PackageState]  # State before operation
    after_state: Dict[str, PackageState]   # State after operation
    command: str                     # Original command
    user: str                        # User who ran it
    duration_seconds: float          # How long it took
    error_message: Optional[str]     # Error if failed
    rollback_commands: List[str]     # Commands to undo
    is_rollback_safe: bool          # Safe to rollback?
    rollback_warning: Optional[str]  # Warning message
```

### PackageState

```python
@dataclass
class PackageState:
    name: str                        # Package name
    version: Optional[str]           # Version if installed
    installed: bool                  # Is it installed?
    config_files: List[str]          # Config file paths
    dependencies: List[str]          # Package dependencies
```

## Storage

### Database Location

Default: `~/.cortex/transaction_history.db`

Override:
```python
history = TransactionHistory(Path("/custom/path/history.db"))
```

### Schema

```sql
CREATE TABLE transactions (
    id TEXT PRIMARY KEY,
    transaction_type TEXT NOT NULL,
    packages TEXT NOT NULL,          -- JSON array
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,
    before_state TEXT,               -- JSON object
    after_state TEXT,                -- JSON object
    command TEXT,
    user TEXT,
    duration_seconds REAL,
    error_message TEXT,
    rollback_commands TEXT,          -- JSON array
    is_rollback_safe INTEGER,
    rollback_warning TEXT
);
```

## Rollback Safety

### Safe Operations

| Operation | Rollback | Notes |
|-----------|----------|-------|
| Install | Remove | Full restore |
| Remove | Install | Restores package |
| Upgrade | Downgrade | Restores previous version |

### Unsafe Operations

| Operation | Rollback | Warning |
|-----------|----------|---------|
| Purge | Install | Config files lost |
| System packages | Varies | May affect stability |

### Critical Packages

These packages trigger safety warnings:
- `apt`, `dpkg`, `libc6`
- `systemd`, `bash`, `coreutils`
- `linux-image`, `grub`, `init`

## CLI Integration

```python
# In cortex/cli.py
from cortex.transaction_history import get_history, get_undo_manager

@cli.command()
def install(packages: List[str]):
    history = get_history()
    
    # Record the transaction
    tx = history.begin_transaction(
        TransactionType.INSTALL,
        packages,
        f"cortex install {' '.join(packages)}"
    )
    
    try:
        # Do the actual installation
        result = do_install(packages)
        history.complete_transaction(tx, success=True)
    except Exception as e:
        history.complete_transaction(tx, success=False, error_message=str(e))
        raise

@cli.command()
def undo(transaction_id: Optional[str] = None, dry_run: bool = False):
    manager = get_undo_manager()
    
    if transaction_id:
        result = manager.undo(transaction_id, dry_run=dry_run)
    else:
        result = manager.undo_last(dry_run=dry_run)
    
    if result['success']:
        print("✓ Rollback complete")
    else:
        print(f"✗ {result['error']}")

@cli.command()
def history(limit: int = 10, package: Optional[str] = None):
    history = get_history()
    
    if package:
        transactions = history.search(package=package, limit=limit)
    else:
        transactions = history.get_recent(limit=limit)
    
    for tx in transactions:
        print(f"{tx.timestamp:%Y-%m-%d %H:%M} | {tx.transaction_type.value:10} | {', '.join(tx.packages)}")
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Commands                          │
│         install / remove / upgrade / undo               │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│               TransactionHistory                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ begin_tx()  │  │ complete_tx()│  │   search()    │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                  UndoManager                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ can_undo()  │  │ preview()    │  │   undo()      │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                SQLite Database                           │
│              ~/.cortex/transaction_history.db            │
└─────────────────────────────────────────────────────────┘
```

## Testing

```bash
# Run all tests
pytest tests/test_transaction_history.py -v

# Run with coverage
pytest tests/test_transaction_history.py --cov=cortex.transaction_history

# Test specific functionality
pytest tests/test_transaction_history.py -k "undo" -v
```

## Troubleshooting

### Database Corruption

```python
import os
from pathlib import Path

# Backup and recreate
db_path = Path.home() / ".cortex" / "transaction_history.db"
if db_path.exists():
    db_path.rename(db_path.with_suffix('.db.bak'))

# New database will be created automatically
history = TransactionHistory()
```

### Undo Not Working

```python
manager = get_undo_manager()

# Check why undo failed
can_undo, reason = manager.can_undo(tx_id)
print(f"Can undo: {can_undo}")
print(f"Reason: {reason}")

# Preview what would happen
preview = manager.preview_undo(tx_id)
print(f"Commands: {preview['commands']}")
print(f"Warning: {preview['warning']}")
```

### Missing State Information

```python
# Transaction was created before state capture was implemented
tx = history.get_transaction(tx_id)
if not tx.before_state:
    print("No state information - cannot safely undo")
    print("Consider manual rollback")
```

## Contributing

1. Add new transaction types to `TransactionType` enum
2. Update rollback command calculation in `_calculate_rollback_commands`
3. Add tests for new functionality
4. Update documentation

---

**Closes:** #258
