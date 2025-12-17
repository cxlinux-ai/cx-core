# Comprehensive Logging & Diagnostics

Complete enterprise-grade logging system with multiple outputs, rotation, and diagnostics.

## Features
- Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Colored console output
- File logging with rotation  
- Structured JSON logging
- Operation timing
- Log search and export
- Error summaries

## Usage

```python
from logging_system import CortexLogger, LogContext

logger = CortexLogger("cortex")

# Basic logging
logger.info("Application started")
logger.error("Error occurred", exc_info=True)

# With context
logger.info("User action", {"user": "john", "action": "install"})

# Operation timing
with LogContext(logger, "install_package"):
    # Your code here
    pass

# Search logs
results = logger.search_logs("error", level="ERROR", limit=10)

# Export logs
logger.export_logs("backup.json", format="json")
```

## Testing
```bash
python test_logging_system.py
```

**Issue #29** | **Bounty**: $100
