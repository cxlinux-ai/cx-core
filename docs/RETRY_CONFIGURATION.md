# Retry Configuration Guide

Cortex CLI includes a **Smart Retry** mechanism that automatically recovers from transient failures during package installations. This guide explains how retry logic works and how to configure it.

## How It Works

When an installation command fails, Cortex analyzes the error to determine if it's:

1. **Transient** (temporary, likely to resolve): Network timeouts, lock contention, etc.
2. **Permanent** (unlikely to resolve): Permission denied, package not found, disk full, etc.

For transient errors, Cortex retries the command with **exponential backoff**—waiting progressively longer between attempts (1s, 2s, 4s, etc.) to allow the issue to resolve.

## Default Retry Strategies

Each error type has its own retry strategy:

| Error Type | Max Retries | Base Backoff | Rationale |
|------------|-------------|--------------|-----------|
| **Network Error** | 5 | 1.0s | Short blips resolve quickly; retry aggressively |
| **Lock Error** | 3 | 5.0s | Locks take time to release; wait longer |
| **Unknown Error** | 2 | 2.0s | Conservative approach for unclassified errors |

**Permanent errors** (Permission Denied, Package Not Found, Disk Space, Dependency Missing, Configuration Error, Conflict) **never retry**—they fail immediately.

## Backoff Calculation

The wait time before each retry uses exponential backoff:

```text
wait_time = backoff_factor × 2^(attempt - 1)
```

Example for Network Error (backoff_factor = 1.0):
- Attempt 1: 1.0s wait
- Attempt 2: 2.0s wait
- Attempt 3: 4.0s wait
- Attempt 4: 8.0s wait
- Attempt 5: 16.0s wait

## Configuration via Environment Variables

Override default strategies using environment variables:

### Network Error Configuration
```bash
export CORTEX_RETRY_NETWORK_MAX=10        # Max retry attempts (default: 5)
export CORTEX_RETRY_NETWORK_BACKOFF=0.5   # Base backoff in seconds (default: 1.0)
```

### Lock Error Configuration
```bash
export CORTEX_RETRY_LOCK_MAX=5            # Max retry attempts (default: 3)
export CORTEX_RETRY_LOCK_BACKOFF=10.0     # Base backoff in seconds (default: 5.0)
```

### Unknown Error Configuration
```bash
export CORTEX_RETRY_UNKNOWN_MAX=3         # Max retry attempts (default: 2)
export CORTEX_RETRY_UNKNOWN_BACKOFF=1.0   # Base backoff in seconds (default: 2.0)
```

## Examples

### Aggressive Retry for Unstable Networks

If you're on an unstable connection and want more retries with shorter waits:

```bash
export CORTEX_RETRY_NETWORK_MAX=10
export CORTEX_RETRY_NETWORK_BACKOFF=0.5
cortex install docker --execute
```

This gives 10 attempts with waits: 0.5s, 1s, 2s, 4s, 8s, 16s, 32s, 64s, 128s, 256s.

### Patient Retry for Shared Systems

If you're on a shared server where `apt` locks are common:

```bash
export CORTEX_RETRY_LOCK_MAX=5
export CORTEX_RETRY_LOCK_BACKOFF=30.0
cortex install nginx --execute
```

This gives 5 attempts with waits: 30s, 60s, 120s, 240s, 480s (up to 8 minutes total wait).

### Disable All Retries

For CI/CD pipelines where you want fast failure:

```bash
export CORTEX_RETRY_NETWORK_MAX=0
export CORTEX_RETRY_LOCK_MAX=0
export CORTEX_RETRY_UNKNOWN_MAX=0
cortex install package --execute
```

## User Feedback

During retries, Cortex displays messages like:

```text
⚠️ NETWORK_ERROR detected. Retrying in 2.0s... (Attempt 2/5)
```

This shows:
- The error type that was detected
- How long until the next attempt
- The current attempt number and maximum attempts

## Error Categories Reference

### Transient (Retried)

| Category | Example Errors |
|----------|----------------|
| `NETWORK_ERROR` | "Connection timed out", "Temporary failure resolving" |
| `LOCK_ERROR` | "Could not get lock", "dpkg was interrupted" |
| `UNKNOWN` | Unclassified errors that might be transient |

### Permanent (Never Retried)

| Category | Example Errors |
|----------|----------------|
| `PERMISSION_DENIED` | "Permission denied", "Operation not permitted" |
| `PACKAGE_NOT_FOUND` | "Unable to locate package", "No such package" |
| `DISK_SPACE` | "No space left on device" |
| `DEPENDENCY_MISSING` | "Depends: X but it is not installable" |
| `CONFIGURATION_ERROR` | "Configuration file syntax error" |
| `CONFLICT` | "Conflicts with package X" |

## Programmatic Usage

For advanced use cases, you can customize strategies in code:

```python
from cortex.utils.retry import SmartRetry, RetryStrategy, DEFAULT_STRATEGIES
from cortex.error_parser import ErrorCategory

# Custom strategies
custom_strategies = dict(DEFAULT_STRATEGIES)
custom_strategies[ErrorCategory.NETWORK_ERROR] = RetryStrategy(
    max_retries=10,
    backoff_factor=0.5,
    description="Custom network retry"
)

retry = SmartRetry(strategies=custom_strategies)
result = retry.run(my_function)
```

## Troubleshooting

### Retries Not Happening

1. Check if the error is classified as permanent (see table above)
2. Verify environment variables are set correctly
3. Run with `--verbose` to see detailed error classification

### Retries Taking Too Long

Reduce `backoff_factor` or `max_retries` via environment variables.

### Need More Aggressive Retries

Increase `max_retries` and decrease `backoff_factor`.

---

**Version**: 0.9.0  
**Last Updated**: January 2026
