# Network Configuration Module

**Module**: `cortex/network_config.py`  
**Issue**: #25

## Overview

The Network Configuration module provides automatic detection and configuration of network settings for the Cortex package manager. It handles corporate proxies, VPN detection, connectivity testing, and graceful offline fallback—ensuring Cortex works seamlessly in any network environment.

## Features

- **Auto-detect proxy settings** from multiple sources (env vars, GNOME, system files)
- **Support for HTTP/HTTPS/SOCKS proxies**
- **Proxy authentication handling**
- **VPN detection** (OpenVPN, WireGuard, IPSec)
- **Connectivity testing** with fallback mechanisms
- **Network quality detection** (good/slow/offline)
- **Offline mode** with package caching
- **Auto-configuration** of apt and pip proxies

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      NetworkConfig                               │
├─────────────────────────────────────────────────────────────────┤
│  Initialization                                                  │
│  ├── force_proxy (optional override)                            │
│  ├── offline_mode (skip detection)                              │
│  └── _detect_all() → runs all detection methods                 │
├─────────────────────────────────────────────────────────────────┤
│  Proxy Detection (Priority Order)                               │
│  1. Environment Variables (HTTP_PROXY, HTTPS_PROXY, etc.)       │
│  2. GNOME/KDE Settings (gsettings)                              │
│  3. System Files (/etc/environment, apt.conf)                   │
├─────────────────────────────────────────────────────────────────┤
│  VPN Detection                                                   │
│  ├── Network Interfaces (tun, tap, wg, ppp, ipsec)              │
│  └── Routing Table Analysis                                      │
├─────────────────────────────────────────────────────────────────┤
│  Connectivity                                                    │
│  ├── DNS Resolution (google.com)                                │
│  ├── HTTP Fallback (1.1.1.1, 8.8.8.8, api.github.com)          │
│  └── Quality Detection (latency-based)                          │
├─────────────────────────────────────────────────────────────────┤
│  Configuration                                                   │
│  ├── configure_apt_proxy() → /etc/apt/apt.conf.d/90cortex-proxy│
│  ├── configure_pip_proxy() → HTTP_PROXY env vars               │
│  └── get_httpx_proxy_config() → for LLM API calls              │
├─────────────────────────────────────────────────────────────────┤
│  Offline Mode                                                    │
│  ├── cache_package_list() → ~/.cortex/cache/                   │
│  ├── get_cached_packages() → with expiration check             │
│  └── enable_offline_fallback()                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Usage

### Basic Usage

```python
from cortex.network_config import NetworkConfig

# Auto-detect everything
config = NetworkConfig()

# Check results
print(f"Proxy: {config.proxy}")
print(f"VPN: {config.is_vpn}")
print(f"Online: {config.is_online}")
print(f"Quality: {config.connection_quality}")

# Auto-configure apt and pip
config.auto_configure()
```

### Force Specific Proxy

```python
config = NetworkConfig(force_proxy="http://proxy.company.com:8080")
```

### Offline Mode

```python
config = NetworkConfig(offline_mode=True)
config.auto_configure()  # Uses cached packages if available
```

### Get Proxy for HTTP Clients

```python
import httpx

config = NetworkConfig()
proxy_config = config.get_httpx_proxy_config()

# Use with httpx
client = httpx.Client(proxies=proxy_config)

# Use with requests
import requests
response = requests.get("https://api.example.com", proxies=config.proxy)
```

### Proxy Authentication

```python
from cortex.network_config import (
    check_proxy_auth,
    prompt_proxy_credentials,
    add_proxy_auth,
)

# Check if proxy needs auth
status = check_proxy_auth("http://proxy:8080")

if status == "auth_required":
    username, password = prompt_proxy_credentials()
    auth_proxy = add_proxy_auth("http://proxy:8080", username, password)
    config = NetworkConfig(force_proxy=auth_proxy)
```

---

## API Reference

### Class: `NetworkConfig`

Main class for network configuration detection and management.

#### Constructor

```python
NetworkConfig(force_proxy: str | None = None, offline_mode: bool = False)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `force_proxy` | `str \| None` | `None` | Override detected proxy with this URL |
| `offline_mode` | `bool` | `False` | Skip connectivity checks, use cache |

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `proxy` | `dict[str, str] \| None` | Detected proxy settings |
| `is_vpn` | `bool` | True if VPN connection detected |
| `is_online` | `bool` | True if internet is reachable |
| `connection_quality` | `str` | "good", "slow", or "offline" |
| `cache_dir` | `Path` | Cache directory (`~/.cortex/cache`) |

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `detect_proxy()` | `dict \| None` | Detect proxy from all sources |
| `detect_vpn()` | `bool` | Check for VPN connection |
| `check_connectivity(timeout=3)` | `bool` | Test internet connectivity |
| `detect_network_quality(timeout=5)` | `str` | Measure connection quality |
| `configure_apt_proxy()` | `bool` | Configure apt to use proxy |
| `configure_pip_proxy()` | `None` | Set pip proxy env vars |
| `get_httpx_proxy_config()` | `dict \| None` | Get httpx-compatible proxy dict |
| `cache_package_list(packages)` | `None` | Cache package list for offline |
| `get_cached_packages(max_age_hours=24)` | `list \| None` | Retrieve cached packages |
| `enable_offline_fallback()` | `bool` | Enable offline mode with cache |
| `cleanup_apt_proxy()` | `bool` | Remove apt proxy configuration |
| `auto_configure()` | `None` | Auto-configure all tools |
| `print_summary()` | `None` | Print network status summary |

---

## Proxy Detection Details

### Detection Priority

1. **Environment Variables** (highest priority)
2. **GNOME/KDE Settings**
3. **System Configuration Files** (lowest priority)

### Environment Variables

The module checks these environment variables (uppercase takes priority):

| Variable | Description |
|----------|-------------|
| `HTTP_PROXY` / `http_proxy` | HTTP proxy URL |
| `HTTPS_PROXY` / `https_proxy` | HTTPS proxy URL |
| `SOCKS_PROXY` / `socks_proxy` | SOCKS5 proxy URL |
| `NO_PROXY` / `no_proxy` | Comma-separated bypass list |

**Note**: When both uppercase and lowercase variants exist, uppercase takes priority.

### GNOME Settings

Reads proxy configuration via `gsettings`:

```bash
gsettings get org.gnome.system.proxy mode        # 'manual', 'none', 'auto'
gsettings get org.gnome.system.proxy.http host   # proxy hostname
gsettings get org.gnome.system.proxy.http port   # proxy port
```

Only used when mode is set to `'manual'`.

### System Configuration Files

Checks these files in order:

| File | Format |
|------|--------|
| `/etc/environment` | `HTTP_PROXY="http://proxy:8080"` |
| `/etc/apt/apt.conf.d/proxy.conf` | `Acquire::http::Proxy "http://proxy:8080";` |
| `/etc/apt/apt.conf` | `Acquire::http::Proxy "http://proxy:8080";` |

---

## VPN Detection

Detects VPN connections by checking network interfaces and routing tables.

### Network Interfaces

```bash
ip link show
```

Looks for these interface prefixes:

| Prefix | VPN Type |
|--------|----------|
| `tun` | OpenVPN, generic TUN devices |
| `tap` | TAP devices (Layer 2 VPN) |
| `wg` | WireGuard |
| `ppp` | Point-to-Point Protocol |
| `ipsec` | IPSec tunnels |

### Routing Table

```bash
ip route
```

Checks for VPN-related routes (tun/ppp entries).

---

## Connectivity Testing

### Test Sequence

1. **DNS Check** (fastest)
   ```python
   socket.gethostbyname("google.com")
   ```

2. **HTTP Fallback** (more reliable through proxies)
   - `https://1.1.1.1` (Cloudflare)
   - `https://8.8.8.8` (Google)
   - `https://api.github.com`

### Network Quality Thresholds

| Latency | Quality | Description |
|---------|---------|-------------|
| < 2 seconds | `good` | Normal connection |
| ≥ 2 seconds | `slow` | High latency detected |
| Timeout/Error | `offline` | No connectivity |

---

## Offline Mode & Caching

### Cache Location

```
~/.cortex/cache/available_packages.json
```

### Cache Format

```json
{
  "packages": ["nginx", "docker", "python3"],
  "cached_at": 1703203200.0
}
```

### Cache Expiration

Default: **24 hours** (configurable via `max_age_hours` parameter)

### Enabling Offline Mode

```python
# Explicit offline mode
config = NetworkConfig(offline_mode=True)

# Automatic fallback when no internet
config = NetworkConfig()
if not config.is_online:
    config.enable_offline_fallback()
```

---

## APT Proxy Configuration

When a proxy is detected, Cortex creates:

```
/etc/apt/apt.conf.d/90cortex-proxy
```

Contents:
```
# Cortex auto-generated proxy configuration
Acquire::http::Proxy "http://proxy:8080";
Acquire::https::Proxy "http://proxy:8080";
```

**Note**: Requires sudo access. Use `cleanup_apt_proxy()` to remove.

---

## Helper Functions

### `check_proxy_auth(proxy_url, timeout=5)`

Tests if a proxy requires authentication.

```python
from cortex.network_config import check_proxy_auth

status = check_proxy_auth("http://proxy:8080")
# Returns: "success", "auth_required", or "failed"
```

### `prompt_proxy_credentials()`

Interactive prompt for username/password.

```python
from cortex.network_config import prompt_proxy_credentials

username, password = prompt_proxy_credentials()
```

### `add_proxy_auth(proxy_url, username, password)`

Embeds credentials in proxy URL.

```python
from cortex.network_config import add_proxy_auth

auth_url = add_proxy_auth("http://proxy:8080", "user", "pass")
# Returns: "http://user:pass@proxy:8080"
```

**⚠️ Security Warning**: Credentials may be visible in logs, error messages, or process listings. Consider using environment variables or credential managers in production.

---

## Error Handling

The module handles these errors gracefully (logged but don't crash):

| Error | Cause | Handling |
|-------|-------|----------|
| `FileNotFoundError` | Commands/files not available | Skip that detection method |
| `subprocess.CalledProcessError` | Command execution failed | Try next method |
| `PermissionError` | Cannot read system files | Skip that file |
| `socket.gaierror` | DNS resolution failed | Try HTTP fallback |
| `requests.RequestException` | HTTP request failed | Mark as offline |
| `json.JSONDecodeError` | Corrupted cache file | Return None |

---

## Integration with Cortex

### Automatic Configuration

The `auto_configure()` method is called during Cortex startup:

```python
# In cortex/cli.py or coordinator
config = NetworkConfig()
config.auto_configure()
```

### LLM API Calls

```python
# Get proxy config for LLM providers
proxy = config.get_httpx_proxy_config()

# Used by anthropic, openai clients
client = httpx.Client(proxies=proxy)
```

### Package Installation

```python
# Proxy is automatically applied to:
# - apt install commands
# - pip install commands  
# - HTTP requests to package repositories
```

---

## Troubleshooting

### Proxy Not Detected

1. Check environment variables:
   ```bash
   echo $HTTP_PROXY $HTTPS_PROXY
   ```

2. Check GNOME settings:
   ```bash
   gsettings get org.gnome.system.proxy mode
   ```

3. Force a specific proxy:
   ```python
   config = NetworkConfig(force_proxy="http://proxy:8080")
   ```

### Proxy Authentication Issues

```python
from cortex.network_config import check_proxy_auth

status = check_proxy_auth("http://proxy:8080")
if status == "auth_required":
    # Prompt for credentials or use add_proxy_auth()
    pass
```

### Offline Mode Not Working

1. Ensure cache exists:
   ```bash
   ls ~/.cortex/cache/available_packages.json
   ```

2. Check cache age:
   ```python
   config.get_cached_packages(max_age_hours=48)  # Increase max age
   ```

### VPN Not Detected

Check if VPN interface is visible:
```bash
ip link show | grep -E 'tun|wg|tap|ppp'
```

---

## Related Documentation

- [Network Configuration Tests](./NETWORK_CONFIG_TESTS.md)
- [Graceful Degradation](./GRACEFUL_DEGRADATION.md)
- [Troubleshooting](./TROUBLESHOOTING.md)
- [Configuration Guide](./CONFIGURATION.md)
