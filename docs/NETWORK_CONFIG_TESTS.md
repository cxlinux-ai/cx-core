# Network Configuration Tests Documentation

**Issue**: #25  
**Module**: `cortex/network_config.py`  
**Test File**: `tests/test_network_config.py`

> **See also**: [Network Configuration Module Documentation](./NETWORK_CONFIG.md) for details on how the module works.

## Overview

This document describes the test suite for the Network Configuration module, which handles proxy detection, VPN detection, connectivity checking, and network-related configuration for the Cortex package manager.

## Test Structure

The test suite is organized into the following test classes:

| Class | Description | Test Count |
|-------|-------------|------------|
| `TestNetworkConfigInit` | Initialization and constructor tests | 4 |
| `TestProxyDetection` | Proxy detection from various sources | 12 |
| `TestVPNDetection` | VPN interface detection | 4 |
| `TestConnectivity` | Network connectivity checks | 6 |
| `TestConfiguration` | Apt/pip proxy configuration | 10 |
| `TestPackageCaching` | Offline package cache functionality | 8 |
| `TestAutoConfigure` | Auto-configuration logic | 4 |
| `TestHelperFunctions` | Utility function tests | 6 |
| `TestPrintSummary` | Summary output tests | 2 |
| `TestIntegration` | End-to-end integration tests | 2 |

**Total: 58 tests**

## Test Classes

### TestNetworkConfigInit

Tests for `NetworkConfig` class initialization.

| Test | Description |
|------|-------------|
| `test_init_default` | Verifies default values for `force_proxy`, `offline_mode`, and `cache_dir` |
| `test_init_with_force_proxy` | Tests initialization with a forced proxy URL |
| `test_init_offline_mode` | Ensures `_detect_all` is skipped in offline mode |
| `test_cache_dir_created` | Verifies cache directory is created on init |

### TestProxyDetection

Tests for proxy detection from environment variables, GNOME settings, and system files.

| Test | Description |
|------|-------------|
| `test_detect_env_proxy_all_set` | All proxy env vars (HTTP, HTTPS, SOCKS, NO_PROXY) |
| `test_detect_env_proxy_lowercase` | Lowercase env var variants (`http_proxy`) |
| `test_detect_env_proxy_none_set` | No proxy environment variables set |
| `test_detect_env_proxy_uppercase_takes_priority` | Uppercase env vars override lowercase |
| `test_detect_gnome_proxy_manual_mode` | GNOME proxy in manual mode via `gsettings` |
| `test_detect_gnome_proxy_no_manual_mode` | GNOME proxy mode set to 'none' |
| `test_detect_gnome_proxy_not_available` | `gsettings` command not found |
| `test_detect_system_proxy_from_etc_environment` | Proxy from `/etc/environment` |
| `test_detect_system_proxy_from_apt_conf` | Proxy from apt configuration files |
| `test_detect_system_proxy_no_files` | No system proxy files exist |
| `test_detect_proxy_priority_env_first` | Environment variables take priority over GNOME |
| `test_parse_proxy_url` | Proxy URL parsing utility |

### TestVPNDetection

Tests for VPN interface detection.

| Test | Description |
|------|-------------|
| `test_detect_vpn_tun_interface` | Detects `tun0` interface (OpenVPN) |
| `test_detect_vpn_wireguard` | Detects `wg0` interface (WireGuard) |
| `test_detect_vpn_no_vpn` | Standard `eth0` interface (no VPN) |
| `test_detect_vpn_ip_command_not_found` | Handles missing `ip` command gracefully |

### TestConnectivity

Tests for network connectivity and quality detection.

| Test | Description |
|------|-------------|
| `test_check_connectivity_dns_success` | DNS resolution succeeds |
| `test_check_connectivity_fallback_to_http` | Falls back to HTTP when DNS fails |
| `test_check_connectivity_offline` | Both DNS and HTTP fail |
| `test_detect_network_quality_good` | Latency < 1s = "good" |
| `test_detect_network_quality_slow` | Latency > 2s = "slow" |
| `test_detect_network_quality_offline` | Request fails = "offline" |

### TestConfiguration

Tests for configuring apt and pip proxies.

| Test | Description |
|------|-------------|
| `test_configure_apt_proxy_success` | Successfully configures apt proxy |
| `test_configure_apt_proxy_no_proxy` | No-op when no proxy detected |
| `test_configure_apt_proxy_permission_denied` | Handles sudo permission errors |
| `test_configure_pip_proxy` | Sets `HTTP_PROXY` and `HTTPS_PROXY` env vars |
| `test_configure_pip_proxy_no_proxy` | No-op when no proxy |
| `test_get_httpx_proxy_config_http_https` | Generates httpx-compatible proxy config |
| `test_get_httpx_proxy_config_socks` | Handles SOCKS proxy for httpx |
| `test_get_httpx_proxy_config_none` | Returns None when no proxy |
| `test_cleanup_apt_proxy_success` | Removes apt proxy configuration file |
| `test_cleanup_apt_proxy_no_file` | No-op when config file doesn't exist |

### TestPackageCaching

Tests for offline package list caching.

| Test | Description |
|------|-------------|
| `test_cache_package_list` | Caches package list with timestamp |
| `test_cache_package_list_io_error` | Handles disk write errors gracefully |
| `test_get_cached_packages_success` | Retrieves valid cached packages |
| `test_get_cached_packages_expired` | Returns None for expired cache (>24h) |
| `test_get_cached_packages_no_file` | Returns None when cache file missing |
| `test_get_cached_packages_invalid_json` | Handles corrupted cache file |
| `test_enable_offline_fallback_cache_available` | Enables fallback with valid cache |
| `test_enable_offline_fallback_no_cache` | Returns False when no cache available |

### TestAutoConfigure

Tests for the `auto_configure()` method.

| Test | Description |
|------|-------------|
| `test_auto_configure_offline_mode` | Calls `enable_offline_fallback` in offline mode |
| `test_auto_configure_offline_no_cache` | Handles offline mode without cache |
| `test_auto_configure_with_proxy` | Configures both apt and pip proxies |
| `test_auto_configure_with_vpn` | Handles VPN detection without errors |

### TestHelperFunctions

Tests for module-level helper functions.

| Test | Description |
|------|-------------|
| `test_check_proxy_auth_success` | Proxy works without authentication |
| `test_check_proxy_auth_required` | Detects 407 Proxy Authentication Required |
| `test_check_proxy_auth_failed` | Handles connection failures |
| `test_add_proxy_auth` | Adds credentials to proxy URL |
| `test_add_proxy_auth_no_protocol` | Adds `http://` prefix when missing |
| `test_prompt_proxy_credentials` | Prompts for username/password |

### TestPrintSummary

Tests for the `print_summary()` method.

| Test | Description |
|------|-------------|
| `test_print_summary_with_proxy` | Prints summary with proxy configured |
| `test_print_summary_without_proxy` | Prints summary without proxy |

### TestIntegration

End-to-end integration tests.

| Test | Description |
|------|-------------|
| `test_full_detection_flow` | Complete detection with mocked system |
| `test_offline_mode_integration` | Full offline mode workflow |

## Running Tests

```bash
# Run all network config tests
pytest tests/test_network_config.py -v

# Run a specific test class
pytest tests/test_network_config.py::TestProxyDetection -v

# Run a specific test
pytest tests/test_network_config.py::TestProxyDetection::test_detect_env_proxy_all_set -v

# Run with coverage
pytest tests/test_network_config.py --cov=cortex.network_config --cov-report=term-missing
```

## Mocking Strategy

The tests use `unittest.mock` extensively to isolate the network configuration logic:

- **`patch.object(NetworkConfig, "_detect_all")`**: Prevents actual network detection during initialization
- **`patch.dict(os.environ, ...)`**: Simulates environment variables
- **`patch("subprocess.check_output")`**: Mocks system command outputs
- **`patch("socket.gethostbyname")`**: Mocks DNS resolution
- **`patch("requests.head/get")`**: Mocks HTTP requests
- **`mock_open()`**: Mocks file system operations

## Coverage Goals

Target: **>80% coverage** for `cortex/network_config.py`

Key areas covered:
- ✅ All proxy detection sources (env, GNOME, system files)
- ✅ VPN interface detection
- ✅ Connectivity checking with fallbacks
- ✅ Proxy configuration for apt and pip
- ✅ Package caching for offline mode
- ✅ Error handling for all external dependencies

## Adding New Tests

When adding tests for new functionality:

1. Add tests to the appropriate existing class, or create a new class
2. Follow the naming convention: `test_<method_name>_<scenario>`
3. Always patch `NetworkConfig._detect_all` when testing instance methods
4. Use descriptive docstrings
5. Test both success and failure scenarios

Example:

```python
def test_new_feature_success(self):
    """Test new feature works correctly."""
    with patch.object(NetworkConfig, "_detect_all"):
        config = NetworkConfig()
    
    with patch("external.dependency") as mock_dep:
        mock_dep.return_value = expected_value
        result = config.new_feature()
        assert result == expected_value
```

## Related Documentation

- [Network Configuration Module](./modules/network_config.md)
- [Graceful Degradation](./GRACEFUL_DEGRADATION.md)
- [Troubleshooting](./TROUBLESHOOTING.md)
