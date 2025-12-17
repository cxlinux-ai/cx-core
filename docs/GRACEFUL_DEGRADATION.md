# Graceful Degradation Module

**Issue:** #257  
**Status:** Ready for Review  
**Bounty:** As specified in issue (+ bonus after funding)

## Overview

The Graceful Degradation module ensures Cortex continues to function even when the LLM API is unavailable. It provides multiple fallback strategies to maintain core functionality:

1. **Response Caching** - Uses previously cached LLM responses
2. **Pattern Matching** - Local regex-based command generation
3. **Manual Mode** - Direct apt command guidance

## Features

### Multi-Level Fallback System

```
API Available → Full AI Mode (100% confidence)
     ↓ (API fails)
Cache Hit → Cached Response (90% confidence)
     ↓ (no cache)
Similar Cache → Fuzzy Match (70% confidence)
     ↓ (no similar)
Pattern Match → Local Regex (70-80% confidence)
     ↓ (no pattern)
Manual Mode → User Guidance (0% confidence)
```

### Response Caching

- SQLite-based persistent cache
- Automatic caching of successful LLM responses
- Similar query matching using keyword overlap
- Cache statistics and cleanup utilities

### Pattern Matching

Pre-built patterns for common operations:

| Category | Examples |
|----------|----------|
| Web Dev | docker, nginx, nodejs, python, postgresql |
| Dev Tools | git, vim, curl, wget, htop, tmux |
| Languages | rust, golang, java |
| ML/AI | cuda, tensorflow, pytorch |
| Operations | update, clean, search, remove |

### Health Monitoring

- Automatic API health checks
- Configurable check intervals
- Failure counting with automatic mode switching
- Recovery detection when API returns

## Installation

```python
from cortex.graceful_degradation import GracefulDegradation, process_with_fallback

# Quick usage with convenience function
result = process_with_fallback("install docker")
print(result["command"])  # sudo apt install docker.io

# Or with full control
manager = GracefulDegradation()
result = manager.process_query("install nginx", llm_fn=your_llm_function)
```

## Usage Examples

### Basic Usage

```python
from cortex.graceful_degradation import GracefulDegradation

manager = GracefulDegradation()

# Process a query with automatic fallback
result = manager.process_query("install docker")

print(f"Source: {result['source']}")
print(f"Confidence: {result['confidence']:.0%}")
print(f"Command: {result['command']}")
```

### With LLM Integration

```python
def call_claude(query: str) -> str:
    # Your Claude API call here
    return response

manager = GracefulDegradation()
result = manager.process_query("install docker", llm_fn=call_claude)

# If Claude is available: source="llm", confidence=100%
# If Claude fails: automatically falls back to cache/patterns
```

### Checking System Status

```python
status = manager.get_status()
print(f"Mode: {status['mode']}")
print(f"API Status: {status['api_status']}")
print(f"Cache Entries: {status['cache_entries']}")
print(f"Cache Hits: {status['cache_hits']}")
```

### Manual Health Check

```python
# With default check (API key presence)
result = manager.check_api_health()

# With custom health check
def ping_claude():
    try:
        # Lightweight API ping
        return True
    except:
        return False

result = manager.check_api_health(api_check_fn=ping_claude)
print(f"API Status: {result.status.value}")
```

## API Reference

### GracefulDegradation

Main class for handling graceful degradation.

**Constructor Parameters:**
- `cache` (ResponseCache, optional): Custom cache instance
- `health_check_interval` (int): Seconds between health checks (default: 60)
- `api_timeout` (float): API timeout in seconds (default: 10.0)

**Methods:**

| Method | Description |
|--------|-------------|
| `process_query(query, llm_fn)` | Process query with automatic fallback |
| `check_api_health(api_check_fn)` | Check if API is available |
| `get_status()` | Get current degradation status |
| `force_mode(mode)` | Force a specific operating mode |
| `reset()` | Reset to default state |

### ResponseCache

SQLite-based cache for LLM responses.

**Methods:**

| Method | Description |
|--------|-------------|
| `get(query)` | Get cached response for exact query |
| `put(query, response)` | Store a response |
| `get_similar(query, limit)` | Get similar cached responses |
| `get_stats()` | Get cache statistics |
| `clear_old_entries(days)` | Remove old entries |

### PatternMatcher

Local pattern matching for common operations.

**Methods:**

| Method | Description |
|--------|-------------|
| `match(query)` | Match query against known patterns |

## Operating Modes

| Mode | Description | When Used |
|------|-------------|-----------|
| `FULL_AI` | Normal operation with LLM | API available |
| `CACHED_ONLY` | Use cached responses only | After 1-2 API failures |
| `PATTERN_MATCHING` | Local regex matching | After 3+ failures, no cache |
| `MANUAL_MODE` | User guidance only | Unknown queries |

## Response Format

```python
{
    "query": "original query",
    "response": "human-readable response",
    "command": "apt command if applicable",
    "source": "llm|cache|cache_similar|pattern_matching|manual_mode",
    "confidence": 0.0-1.0,
    "mode": "current operating mode",
    "cached": True/False
}
```

## Configuration

### Environment Variables

The module checks for API keys to determine initial health:

- `ANTHROPIC_API_KEY` - Claude API key
- `OPENAI_API_KEY` - OpenAI API key

### Cache Location

Default: `~/.cortex/response_cache.db`

Override by passing custom `ResponseCache`:

```python
from pathlib import Path
cache = ResponseCache(Path("/custom/path/cache.db"))
manager = GracefulDegradation(cache=cache)
```

## Testing

```bash
# Run all tests
pytest tests/test_graceful_degradation.py -v

# Run with coverage
pytest tests/test_graceful_degradation.py --cov=cortex.graceful_degradation

# Run specific test class
pytest tests/test_graceful_degradation.py::TestGracefulDegradation -v
```

## Integration with Cortex

This module integrates with the main Cortex CLI:

```python
# In cortex/cli.py
from cortex.graceful_degradation import get_degradation_manager

manager = get_degradation_manager()

def handle_user_query(query: str):
    result = manager.process_query(query, llm_fn=call_claude)
    
    if result["confidence"] < 0.5:
        print("⚠️  Running in offline mode - results may be limited")
    
    return result["command"]
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Query                           │
└─────────────────────┬───────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────┐
│              GracefulDegradation                        │
│  ┌───────────────┐  ┌───────────────┐  ┌────────────┐  │
│  │  Health Check │→ │ Mode Selector │→ │  Processor │  │
│  └───────────────┘  └───────────────┘  └────────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      ▼
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌───────────┐  ┌───────────┐  ┌───────────┐
│  LLM API  │  │   Cache   │  │  Pattern  │
│           │  │ (SQLite)  │  │  Matcher  │
└───────────┘  └───────────┘  └───────────┘
```

## Troubleshooting

### Cache Not Working

```python
# Check cache status
stats = manager.cache.get_stats()
print(f"Entries: {stats['total_entries']}")
print(f"DB Size: {stats['db_size_kb']:.1f} KB")

# Clear corrupted cache
import os
os.remove(Path.home() / ".cortex" / "response_cache.db")
```

### Stuck in Offline Mode

```python
# Force reset
manager.reset()

# Or manually check API
result = manager.check_api_health()
print(f"Status: {result.status.value}")
print(f"Error: {result.error_message}")
```

### Pattern Not Matching

```python
# Test pattern directly
matcher = PatternMatcher()
result = matcher.match("your query")
print(result)  # None if no match

# Check available patterns
print(matcher.INSTALL_PATTERNS.keys())
```

## Contributing

To add new patterns:

1. Edit `PatternMatcher.INSTALL_PATTERNS` or `OPERATION_PATTERNS`
2. Use regex with `(?:...)` for non-capturing groups
3. Add tests in `tests/test_graceful_degradation.py`
4. Submit PR referencing this issue

---

**Closes:** #257
