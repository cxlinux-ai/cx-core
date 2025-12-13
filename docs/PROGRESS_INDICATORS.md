# Progress Indicators Module

**Issue:** #259  
**Status:** Ready for Review  
**Bounty:** As specified in issue (+ bonus after funding)

## Overview

Beautiful, informative progress indicators for all Cortex operations. Uses the Rich library for stunning terminal UI when available, with graceful fallback to basic terminal output.

## Features

### Multiple Progress Types

| Type | Use Case | Visual |
|------|----------|--------|
| Spinner | Indeterminate operations | ⠋ Loading... |
| Progress Bar | Known duration operations | [████████░░] 80% |
| Multi-Step | Complex workflows | ✓ Step 1 → ● Step 2 → ○ Step 3 |
| Download | File transfers | ⬇️ 5.2 MB/s ETA 00:03 |
| Operation | General tasks | 📦 Installing Docker... |

### Automatic Fallback

Works beautifully with Rich library installed, falls back gracefully to basic terminal output when Rich isn't available.

```python
# Rich installed: Beautiful animated UI
# Rich not installed: Simple but functional text output
```

### Operation Type Icons

| Operation | Icon |
|-----------|------|
| INSTALL | 📦 |
| REMOVE | 🗑️ |
| UPDATE | 🔄 |
| DOWNLOAD | ⬇️ |
| CONFIGURE | ⚙️ |
| VERIFY | ✅ |
| ANALYZE | 🔍 |
| LLM_QUERY | 🧠 |
| DEPENDENCY_RESOLVE | 🔗 |
| ROLLBACK | ⏪ |

## Installation

```bash
# Basic functionality (no dependencies)
pip install cortex-linux

# With beautiful Rich UI (recommended)
pip install cortex-linux[ui]
# or
pip install rich
```

## Usage Examples

### Simple Spinner

```python
from cortex.progress_indicators import spinner

with spinner("Analyzing system..."):
    result = analyze_system()

# Output:
# ⠋ Analyzing system...
# ✓ Analyzing system...
```

### Operation with Updates

```python
from cortex.progress_indicators import operation, OperationType

with operation("Installing Docker", OperationType.INSTALL) as op:
    op.update("Checking dependencies...")
    check_deps()
    
    op.update("Downloading images...")
    download()
    
    op.update("Configuring...")
    configure()
    
    op.complete("Docker ready!")

# Output:
# 📦 Installing Docker - Checking dependencies...
# 📦 Installing Docker - Downloading images...
# 📦 Installing Docker - Configuring...
# ✓ Installing Docker - Docker ready!
```

### Progress Bar

```python
from cortex.progress_indicators import progress_bar

packages = ["nginx", "redis", "postgresql", "nodejs"]

for pkg in progress_bar(packages, "Installing packages"):
    install_package(pkg)

# Output:
# Installing packages: [████████████░░░░░░░░] 3/4
```

### Download Tracker

```python
from cortex.progress_indicators import ProgressIndicator

progress = ProgressIndicator()

tracker = progress.download_progress(total_bytes=50_000_000, description="Downloading update")

for chunk in download_stream():
    tracker.update(len(chunk))

tracker.complete()

# Output:
# ⬇️ Downloading update [████████████████░░░░] 40.0/50.0 MB 5.2 MB/s ETA 00:02
# ✓ Downloaded 50.0 MB in 9.6s (5.2 MB/s)
```

### Multi-Step Workflow

```python
from cortex.progress_indicators import ProgressIndicator

progress = ProgressIndicator()

tracker = progress.multi_step([
    {"name": "Download", "description": "Downloading package files"},
    {"name": "Verify", "description": "Checking file integrity"},
    {"name": "Extract", "description": "Extracting contents"},
    {"name": "Install", "description": "Installing to system"},
    {"name": "Configure", "description": "Configuring service"},
], title="Package Installation")

for i in range(5):
    tracker.start_step(i)
    do_step(i)
    tracker.complete_step(i)

tracker.finish()

# Output:
#           Package Installation
# ✓ Download    Downloading package files
# ✓ Verify      Checking file integrity
# ✓ Extract     Extracting contents
# ● Install     Installing to system
# ○ Configure   Configuring service
```

### Status Messages

```python
from cortex.progress_indicators import get_progress_indicator

progress = get_progress_indicator()

progress.print_success("Package installed successfully")
progress.print_error("Installation failed")
progress.print_warning("Disk space low")
progress.print_info("Using cached version")

# Output:
# ✓ Package installed successfully
# ✗ Installation failed
# ⚠ Disk space low
# ℹ Using cached version
```

## API Reference

### ProgressIndicator

Main class for all progress indicators.

**Constructor:**
```python
ProgressIndicator(use_rich: bool = True)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `operation(title, type, steps)` | Context manager for tracked operations |
| `spinner(message)` | Context manager for indeterminate progress |
| `progress_bar(items, description)` | Iterator with progress display |
| `download_progress(total, description)` | Create download tracker |
| `multi_step(steps, title)` | Create multi-step tracker |
| `print_success(message)` | Print success message |
| `print_error(message)` | Print error message |
| `print_warning(message)` | Print warning message |
| `print_info(message)` | Print info message |

### OperationType

Enum of supported operation types:

```python
class OperationType(Enum):
    INSTALL = "install"
    REMOVE = "remove"
    UPDATE = "update"
    DOWNLOAD = "download"
    CONFIGURE = "configure"
    VERIFY = "verify"
    ANALYZE = "analyze"
    LLM_QUERY = "llm_query"
    DEPENDENCY_RESOLVE = "dependency_resolve"
    ROLLBACK = "rollback"
    GENERIC = "generic"
```

### OperationStep

Dataclass representing a single step:

```python
@dataclass
class OperationStep:
    name: str
    description: str
    status: str = "pending"  # pending, running, completed, failed, skipped
    progress: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
```

### DownloadTracker

**Methods:**

| Method | Description |
|--------|-------------|
| `update(bytes)` | Update with bytes received |
| `complete()` | Mark download complete |
| `fail(error)` | Mark download failed |

### MultiStepTracker

**Methods:**

| Method | Description |
|--------|-------------|
| `start_step(index)` | Start a step |
| `complete_step(index)` | Complete a step |
| `fail_step(index, error)` | Fail a step |
| `skip_step(index, reason)` | Skip a step |
| `finish()` | Display final summary |

## Integration with Cortex

### CLI Integration

```python
# In cortex/cli.py
from cortex.progress_indicators import get_progress_indicator, OperationType

progress = get_progress_indicator()

@cli.command()
def install(package: str):
    with progress.operation(f"Installing {package}", OperationType.INSTALL) as op:
        op.update("Resolving dependencies...")
        deps = resolve_deps(package)
        
        op.update("Downloading...")
        download(package)
        
        op.update("Installing...")
        install(package)
        
        op.complete(f"{package} installed successfully")
```

### LLM Integration

```python
from cortex.progress_indicators import spinner

def query_llm(prompt: str) -> str:
    with spinner("🧠 Thinking..."):
        response = claude_api.complete(prompt)
    return response
```

### Batch Operations

```python
from cortex.progress_indicators import progress_bar

def install_batch(packages: List[str]):
    for pkg in progress_bar(packages, "Installing packages"):
        install_single(pkg)
```

## Customization

### Disable Rich (Force Fallback)

```python
progress = ProgressIndicator(use_rich=False)
```

### Custom Operation Tracking

```python
from cortex.progress_indicators import OperationContext, OperationType

context = OperationContext(
    operation_type=OperationType.INSTALL,
    title="Custom Operation",
    metadata={"package": "nginx", "version": "1.24"}
)

# Access timing info
print(f"Started: {context.start_time}")
print(f"Progress: {context.overall_progress:.0%}")
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│              ProgressIndicator                   │
│  ┌────────────┐ ┌─────────────┐ ┌────────────┐ │
│  │  Spinner   │ │ ProgressBar │ │ MultiStep  │ │
│  └────────────┘ └─────────────┘ └────────────┘ │
└─────────────────────┬───────────────────────────┘
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
┌─────────────┐ ┌───────────┐ ┌────────────┐
│    Rich     │ │  Fallback │ │   Output   │
│   Console   │ │  Progress │ │  Handlers  │
└─────────────┘ └───────────┘ └────────────┘
```

## Testing

```bash
# Run all tests
pytest tests/test_progress_indicators.py -v

# Run with coverage
pytest tests/test_progress_indicators.py --cov=cortex.progress_indicators

# Test Rich integration (if installed)
pytest tests/test_progress_indicators.py -k "Rich" -v
```

## Performance

- Spinner updates: 10 FPS (100ms interval)
- Progress bar: Updates on each iteration
- Multi-step: Renders on state change only
- Memory: Minimal overhead (<1MB)

## Troubleshooting

### Rich Not Detected

```python
from cortex.progress_indicators import RICH_AVAILABLE

print(f"Rich available: {RICH_AVAILABLE}")

# Install Rich if needed
# pip install rich
```

### Terminal Compatibility

```python
# Force simple output for non-interactive terminals
import sys

if not sys.stdout.isatty():
    progress = ProgressIndicator(use_rich=False)
```

### Progress Not Showing

```python
# Ensure stdout is flushed
import sys

with spinner("Working..."):
    sys.stdout.flush()
    do_work()
```

## Contributing

1. Add new operation types to `OperationType` enum
2. Create corresponding icons in `OPERATION_ICONS`
3. Add tests for new functionality
4. Update documentation

---

**Closes:** #259
