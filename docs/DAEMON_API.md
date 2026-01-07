# Cortexd API Documentation

## Overview

Cortexd provides a JSON-based RPC interface via Unix domain socket (`/run/cortex.sock`). All communication uses UTF-8 encoded JSON.

**Socket Path**: `/run/cortex.sock`
**Protocol**: JSON-RPC 2.0 (subset)
**Timeout**: 5 seconds per request
**Max Message Size**: 64 KB

## Request Format

All requests follow this structure:

```json
{
  "method": "status",
  "params": {}
}
```

### Required Fields

- `method` (string): Method name (status, alerts, health, etc)
- `params` (object, optional): Method-specific parameters

## Response Format

Responses follow this structure:

```json
{
  "status": "ok",
  "data": {},
  "timestamp": 1672574400,
  "error": null
}
```

### Fields

- `status` (string): `"ok"`, `"error"`, `"success"`
- `data` (object): Response-specific data
- `timestamp` (int): Unix timestamp
- `error` (string, optional): Error message if status is "error"

## API Reference

### 1. Status

Get daemon status and version information.

**Request**:
```json
{
  "method": "status"
}
```

**Response**:
```json
{
  "status": "ok",
  "data": {
    "version": "0.1.0",
    "uptime_seconds": 3600,
    "pid": 1234,
    "socket_path": "/run/cortex.sock",
    "config_loaded": true
  },
  "timestamp": 1672574400
}
```

### 2. Health

Get detailed health snapshot with system metrics. Alert counts are always fetched fresh from the AlertManager.

**Request**:
```json
{
  "method": "health"
}
```

**Response**:
```json
{
  "status": "ok",
  "data": {
    "health": {
      "cpu_usage": 25.5,
      "memory_usage": 35.2,
      "disk_usage": 65.8,
      "active_processes": 156,
      "open_files": 128,
      "llm_loaded": true,
      "inference_queue_size": 2,
      "alerts_count": 3
    }
  },
  "timestamp": 1672574400
}
```

**Fields**:
- `cpu_usage` (float): CPU usage percentage (0-100)
- `memory_usage` (float): Memory usage percentage (0-100)
- `disk_usage` (float): Disk usage percentage (0-100)
- `active_processes` (int): Number of active processes
- `open_files` (int): Number of open file descriptors
- `llm_loaded` (bool): Is LLM model loaded
- `inference_queue_size` (int): Queued inference requests
- `alerts_count` (int): Number of active alerts

### 3. Alerts

Get active system alerts.

**Request**:
```json
{
  "method": "alerts",
  "params": {
    "severity": "warning",
    "type": "memory_usage"
  }
}
```

**Parameters** (all optional):
- `severity` (string): Filter by severity: `info`, `warning`, `error`, `critical`
- `type` (string): Filter by alert type: `apt_updates`, `disk_usage`, `memory_usage`, `cve_found`, `dependency_conflict`, `system_error`, `daemon_status`
- `limit` (int): Maximum alerts to return (default: 100)
- `offset` (int): Pagination offset (default: 0)

**Response**:
```json
{
  "status": "ok",
  "data": {
    "alerts": [
      {
        "id": "a1b2c3d4-e5f6-4g7h-8i9j-0k1l2m3n4o5p",
        "timestamp": 1672574400,
        "severity": "warning",
        "type": "memory_usage",
        "title": "High Memory Usage",
        "description": "Memory usage at 87%, consider freeing space",
        "acknowledged": false,
        "metadata": {
          "usage_percent": "87",
          "threshold": "85"
        }
      }
    ],
    "total": 5,
    "count": 1
  },
  "timestamp": 1672574400
}
```

**Alert Fields**:
- `id` (string, UUID): Unique alert identifier
- `timestamp` (int): Unix timestamp of alert creation
- `severity` (string): `info`, `warning`, `error`, `critical`
- `type` (string): Alert category
- `title` (string): Human-readable title
- `description` (string): Detailed description
- `acknowledged` (bool): Has alert been acknowledged
- `metadata` (object): Additional alert data

### 4. Acknowledge Alert

Mark an alert as acknowledged.

**Request**:
```json
{
  "method": "alerts.acknowledge",
  "params": {
    "id": "a1b2c3d4-e5f6-4g7h-8i9j-0k1l2m3n4o5p"
  }
}
```

To acknowledge all alerts:
```json
{
  "method": "alerts.acknowledge",
  "params": {
    "all": true
  }
}
```

**Response**:
```json
{
  "status": "success",
  "data": {
    "message": "Alert acknowledged",
    "alert_id": "a1b2c3d4-e5f6-4g7h-8i9j-0k1l2m3n4o5p"
  },
  "timestamp": 1672574400
}
```

### 5. Dismiss Alert

Dismiss (permanently delete) an alert.

**Request**:
```json
{
  "method": "alerts.dismiss",
  "params": {
    "id": "a1b2c3d4-e5f6-4g7h-8i9j-0k1l2m3n4o5p"
  }
}
```

**Response**:
```json
{
  "success": true,
  "result": {
    "dismissed": "a1b2c3d4-e5f6-4g7h-8i9j-0k1l2m3n4o5p"
  }
}
```

### 6. Config Reload

Reload daemon configuration from disk.

**Request**:
```json
{
  "method": "config.reload"
}
```

**Response**:
```json
{
  "status": "success",
  "data": {
    "message": "Configuration reloaded",
    "config_file": "/home/user/.cortex/daemon.conf"
  },
  "timestamp": 1672574400
}
```

### 7. Shutdown

Request daemon shutdown (graceful).

**Request**:
```json
{
  "method": "shutdown"
}
```

**Response** (before shutdown):
```json
{
  "status": "success",
  "data": {
    "message": "Shutdown initiated",
    "timeout_seconds": 10
  },
  "timestamp": 1672574400
}
```

### 8. Inference

Run LLM inference using llama.cpp (requires model to be loaded).

**Request**:
```json
{
  "method": "llm.infer",
  "params": {
    "prompt": "What packages are installed?",
    "max_tokens": 256,
    "temperature": 0.7
  }
}
```

**Parameters**:
- `prompt` (string, required): Input prompt for the LLM
- `max_tokens` (int, optional): Max output tokens (default: 256, max: 256)
- `temperature` (float, optional): Sampling temperature (default: 0.7, range: 0.0-2.0)

**Response (Success)**:
```json
{
  "status": "ok",
  "data": {
    "output": "The installed packages include nginx, python3, git...",
    "tokens_used": 150,
    "inference_time_ms": 85.5
  },
  "timestamp": 1672574400
}
```

**Response (Model Not Loaded)**:
```json
{
  "status": "error",
  "error": {
    "code": "MODEL_NOT_LOADED",
    "message": "Model not loaded. Configure model_path in daemon.conf",
    "details": {}
  },
  "timestamp": 1672574400
}
```

**Inference Characteristics**:
- **Model Load Time**: 5-30s (one-time, depends on model size)
- **Inference Latency**: 50-200ms (cached), 200-500ms (cold)
- **Max Tokens**: 256 (per request, configurable)
- **Concurrent Requests**: Queued, one at a time
- **Queue Size**: Configurable (default: 100)

**llama.cpp Integration**:
- Uses native C API for maximum efficiency
- Supports GGUF quantized models
- Configurable thread count (default: 4)
- Memory-mapped model loading for faster startup

## Error Responses

### Format

```json
{
  "status": "error",
  "error": {
    "code": "INVALID_COMMAND",
    "message": "Unknown command 'foo'",
    "details": {}
  },
  "timestamp": 1672574400
}
```

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `INVALID_COMMAND` | 400 | Unknown command |
| `INVALID_PARAMS` | 400 | Invalid or missing parameters |
| `CONNECTION_FAILED` | 503 | Unable to connect to daemon |
| `TIMEOUT` | 408 | Request timed out |
| `NOT_FOUND` | 404 | Resource not found (e.g., alert ID) |
| `INTERNAL_ERROR` | 500 | Daemon internal error |
| `DAEMON_BUSY` | 429 | Daemon is busy, try again |
| `UNAUTHORIZED` | 401 | Authorization required |

### Example Error Response

```json
{
  "status": "error",
  "error": {
    "code": "INVALID_COMMAND",
    "message": "Unknown command 'foo'",
    "details": {
      "available_commands": ["status", "health", "alerts", "shutdown"]
    }
  },
  "timestamp": 1672574400
}
```

## Python Client Usage

### Basic Usage

```python
from cortex.daemon_client import CortexDaemonClient

# Create client
client = CortexDaemonClient()

# Check if daemon is running
if client.is_running():
    print("Daemon is running")
else:
    print("Daemon is not running")

# Get status
status = client.get_status()
print(f"Version: {status['data']['version']}")

# Get health
health = client.get_health()
print(f"Memory: {health['data']['health']['memory_usage']}%")

# Get alerts
alerts = client.get_alerts()
for alert in alerts:
    print(f"{alert['severity']}: {alert['title']}")
```

### Error Handling

```python
from cortex.daemon_client import CortexDaemonClient, DaemonConnectionError

try:
    client = CortexDaemonClient()
    health = client.get_health()
except DaemonConnectionError as e:
    print(f"Connection error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Command-Line Usage

### Using socat

```bash
# Direct socket command
echo '{"method":"status"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock

# Pretty-printed response
echo '{"method":"health"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock | jq '.'

# Piped to file
echo '{"method":"alerts"}' | socat - UNIX-CONNECT:/run/cortex/cortex.sock > alerts.json
```

### Using nc (netcat)

```bash
# Note: nc doesn't work well with Unix sockets, use socat or Python client
```

### Using curl (with socat proxy)

```bash
# Setup proxy (in another terminal)
socat TCP-LISTEN:9999,reuseaddr UNIX-CONNECT:/run/cortex/cortex.sock &

# Make request
curl -X POST http://localhost:9999 \
  -H "Content-Type: application/json" \
  -d '{"method":"status"}'
```

## Rate Limiting

Currently no rate limiting is implemented. Future versions may include:
- Max 1000 requests/second per client
- Max 100 concurrent connections
- Backpressure handling for slow clients

## Performance

Typical response times:

| Command | Time |
|---------|------|
| `status` | 1-2ms |
| `health` | 5-10ms |
| `alerts` | 2-5ms |
| `inference` | 50-200ms |
| `shutdown` | 100-500ms |

## Future API Additions

Planned API endpoints for future versions:

```json
{
  "command": "metrics",  // Prometheus-style metrics
  "command": "config_get",  // Get current configuration
  "command": "config_set",  // Set configuration value
  "command": "logs",  // Retrieve logs from memory
  "command": "performance",  // Detailed performance metrics
  "command": "alerts_history"  // Historical alerts
}
```

## Backward Compatibility

- API versioning uses `command` names, not separate version field
- Responses are backward-compatible (new fields may be added)
- Deprecated commands will return 400 error with deprecation notice

