"""
Tests for Network Configuration Module

Issue: #25
"""

import json
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

import requests

from cortex.network_config import (
    NetworkConfig,
    add_proxy_auth,
    check_proxy_auth,
    prompt_proxy_credentials,
)


class TestNetworkConfigInit:
    """Tests for NetworkConfig initialization."""

    def test_init_default(self):
        """Test default initialization."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            assert config.force_proxy is None
            assert config.offline_mode is False
            assert config.cache_dir == Path.home() / ".cortex" / "cache"

    def test_init_with_force_proxy(self):
        """Test initialization with forced proxy."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig(force_proxy="http://proxy:8080")
            assert config.force_proxy == "http://proxy:8080"

    def test_init_offline_mode(self):
        """Test initialization in offline mode."""
        with patch.object(NetworkConfig, "detect") as mock_detect:
            config = NetworkConfig(offline_mode=True)
            assert config.offline_mode is True
            mock_detect.assert_not_called()

    def test_cache_dir_created(self):
        """Test cache directory is created on init."""
        with patch.object(NetworkConfig, "detect"):
            with patch("pathlib.Path.mkdir") as mock_mkdir:
                config = NetworkConfig()
                mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestProxyDetection:
    """Tests for proxy detection methods."""

    def test_detect_env_proxy_all_set(self):
        """Test environment variable proxy detection."""
        env_vars = {
            "HTTP_PROXY": "http://proxy:8080",
            "HTTPS_PROXY": "https://proxy:8443",
            "SOCKS_PROXY": "socks5://proxy:1080",
            "NO_PROXY": "localhost,127.0.0.1",
        }
        with patch.dict(os.environ, env_vars):
            with patch.object(NetworkConfig, "detect"):
                config = NetworkConfig()
                result = config._detect_env_proxy()
                assert result["http"] == "http://proxy:8080"
                assert result["https"] == "https://proxy:8443"
                assert result["socks"] == "socks5://proxy:1080"
                assert result["no_proxy"] == "localhost,127.0.0.1"

    def test_detect_env_proxy_lowercase(self):
        """Test lowercase environment variables work."""
        env_vars = {
            "http_proxy": "http://proxy:8080",
            "https_proxy": "https://proxy:8443",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            with patch.object(NetworkConfig, "detect"):
                config = NetworkConfig()
                result = config._detect_env_proxy()
                assert result["http"] == "http://proxy:8080"
                assert result["https"] == "https://proxy:8443"

    def test_detect_env_proxy_none_set(self):
        """Test when no proxy environment variables are set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(NetworkConfig, "detect"):
                config = NetworkConfig()
                result = config._detect_env_proxy()
                assert result["http"] is None
                assert result["https"] is None

    def test_detect_env_proxy_uppercase_takes_priority(self):
        """Uppercase env vars should take priority over lowercase."""
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://uppercase:8080",
                "http_proxy": "http://lowercase:8080",
            },
        ):
            with patch.object(NetworkConfig, "detect"):
                config = NetworkConfig()
                proxy = config._detect_env_proxy()
                assert proxy["http"] == "http://uppercase:8080"

    def test_detect_gnome_proxy_manual_mode(self):
        """Test GNOME proxy detection in manual mode."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("subprocess.check_output") as mock_check:
            mock_check.side_effect = [
                b"'manual'\n",  # mode
                b"'proxy.company.com'\n",  # host
                b"8080\n",  # port
            ]
            result = config._detect_gnome_proxy()
            assert result is not None
            assert result["http"] == "http://proxy.company.com:8080"
            assert result["https"] == "http://proxy.company.com:8080"

    def test_detect_gnome_proxy_no_manual_mode(self):
        """Test GNOME proxy when not in manual mode."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("subprocess.check_output") as mock_check:
            mock_check.return_value = b"'none'\n"
            result = config._detect_gnome_proxy()
            assert result is None

    def test_detect_gnome_proxy_not_available(self):
        """Test GNOME proxy when gsettings not available."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("subprocess.check_output") as mock_check:
            mock_check.side_effect = FileNotFoundError()
            result = config._detect_gnome_proxy()
            assert result is None

    def test_detect_system_proxy_from_etc_environment(self):
        """Test proxy detection from /etc/environment."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        file_content = 'HTTP_PROXY="http://proxy:8080"\nPATH="/usr/bin"\n'
        with patch("builtins.open", mock_open(read_data=file_content)):
            result = config._detect_system_proxy()
            assert result is not None
            assert result["http"] == "http://proxy:8080"

    def test_detect_system_proxy_from_apt_conf(self):
        """Test proxy detection from apt configuration."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        apt_content = 'Acquire::http::Proxy "http://proxy:8080";\n'

        # First file doesn't exist, second has proxy
        with patch("builtins.open") as mock_file:
            mock_file.side_effect = [
                FileNotFoundError(),  # proxy.conf doesn't exist
                mock_open(read_data=apt_content)(),  # apt.conf exists
            ]
            result = config._detect_system_proxy()
            assert result is not None
            assert result["http"] == "http://proxy:8080"

    def test_detect_system_proxy_no_files(self):
        """Test when no system proxy files exist."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("builtins.open", side_effect=FileNotFoundError()):
            result = config._detect_system_proxy()
            assert result is None

    def test_detect_proxy_priority_env_first(self):
        """Test proxy detection prioritizes environment variables."""
        with patch.dict(os.environ, {"HTTP_PROXY": "http://env-proxy:8080"}):
            with patch.object(NetworkConfig, "detect"):
                config = NetworkConfig()

            with patch.object(
                config, "_detect_gnome_proxy", return_value={"http": "http://gnome-proxy:8080"}
            ):
                result = config.detect_proxy()
                assert result["http"] == "http://env-proxy:8080"

    def test_parse_proxy_url(self):
        """Test proxy URL parsing."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        result = config._parse_proxy_url("http://proxy:8080")
        assert result["http"] == "http://proxy:8080"
        assert result["https"] == "http://proxy:8080"


class TestVPNDetection:
    """Tests for VPN detection."""

    def test_detect_vpn_tun_interface(self):
        """Test VPN detection via tun interface."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("subprocess.check_output") as mock_check:
            mock_check.return_value = b"1: tun0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP>\n"
            result = config.detect_vpn()
            assert result is True

    def test_detect_vpn_wireguard(self):
        """Test VPN detection via WireGuard."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("subprocess.check_output") as mock_check:
            mock_check.return_value = b"1: wg0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP>\n"
            result = config.detect_vpn()
            assert result is True

    def test_detect_vpn_no_vpn(self):
        """Test VPN detection when no VPN present."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("subprocess.check_output") as mock_check:
            mock_check.return_value = b"1: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP>\n"
            result = config.detect_vpn()
            assert result is False

    def test_detect_vpn_ip_command_not_found(self):
        """Test VPN detection when ip command not available."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("subprocess.check_output") as mock_check:
            mock_check.side_effect = FileNotFoundError()
            result = config.detect_vpn()
            assert result is False


class TestConnectivity:
    """Tests for connectivity checking."""

    def test_check_connectivity_socket_success(self):
        """Test connectivity check via socket."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig(auto_detect=False)

        with patch("socket.socket") as mock_socket:
            mock_sock_instance = MagicMock()
            mock_socket.return_value = mock_sock_instance
            result = config.check_connectivity()
            assert result is True

    def test_check_connectivity_fallback_to_http(self):
        """Test connectivity falls back to HTTP checks."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig(auto_detect=False)

        with patch("socket.socket") as mock_socket:
            mock_sock_instance = MagicMock()
            mock_sock_instance.connect.side_effect = OSError("Connection failed")
            mock_socket.return_value = mock_sock_instance

            with patch("requests.head") as mock_head:
                mock_head.return_value = MagicMock(status_code=200)
                result = config.check_connectivity()
                assert result is True

    def test_check_connectivity_offline(self):
        """Test connectivity check when offline."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig(auto_detect=False)

        with patch("socket.socket") as mock_socket:
            mock_sock_instance = MagicMock()
            mock_sock_instance.connect.side_effect = OSError("Network unreachable")
            mock_socket.return_value = mock_sock_instance

            with patch("requests.head", side_effect=requests.RequestException()):
                result = config.check_connectivity()
                assert result is False

    def test_detect_network_quality_good(self):
        """Test network quality detection - good."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig(auto_detect=False)

        with patch("requests.head") as mock_head:
            with patch("time.time", side_effect=[0, 0.5]):  # 0.5s latency
                mock_head.return_value = MagicMock(status_code=200)
                result = config.detect_network_quality()
                assert result == "good"

    def test_detect_network_quality_slow(self):
        """Test network quality detection - slow."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig(auto_detect=False)

        with patch("requests.head") as mock_head:
            with patch("time.time", side_effect=[0, 3]):  # 3s latency
                mock_head.return_value = MagicMock(status_code=200)
                result = config.detect_network_quality()
                assert result == "slow"

    def test_detect_network_quality_offline(self):
        """Test network quality detection - offline."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig(auto_detect=False)

        with patch("requests.head", side_effect=requests.RequestException()):
            result = config.detect_network_quality()
            assert result == "offline"


class TestConfiguration:
    """Tests for configuration methods."""

    def test_configure_apt_proxy_success(self):
        """Test apt proxy configuration."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = {"http": "http://proxy:8080"}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = config.configure_apt_proxy()
            assert result is True
            mock_run.assert_called_once()
            assert "sudo" in mock_run.call_args[0][0]

    def test_configure_apt_proxy_no_proxy(self):
        """Test apt configuration when no proxy."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = None

        result = config.configure_apt_proxy()
        assert result is False

    def test_configure_apt_proxy_permission_denied(self):
        """Test apt configuration with permission error."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = {"http": "http://proxy:8080"}

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "sudo")):
            result = config.configure_apt_proxy()
            assert result is False

    def test_configure_pip_proxy(self):
        """Test pip proxy configuration."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = {"http": "http://proxy:8080"}

        with patch.dict(os.environ, {}, clear=True):
            config.configure_pip_proxy()
            assert os.environ["HTTP_PROXY"] == "http://proxy:8080"
            assert os.environ["HTTPS_PROXY"] == "http://proxy:8080"

    def test_configure_pip_proxy_no_proxy(self):
        """Test pip configuration when no proxy."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = None

        with patch.dict(os.environ, {}, clear=True):
            config.configure_pip_proxy()
            assert "HTTP_PROXY" not in os.environ

    def test_get_httpx_proxy_config_http_https(self):
        """Test httpx proxy config generation."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = {"http": "http://proxy:8080", "https": "https://proxy:8443"}

        result = config.get_httpx_proxy_config()
        assert result["http://"] == "http://proxy:8080"
        assert result["https://"] == "https://proxy:8443"

    def test_get_httpx_proxy_config_socks(self):
        """Test httpx proxy config with SOCKS."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = {"socks": "socks5://proxy:1080"}

        result = config.get_httpx_proxy_config()
        assert result["all://"] == "socks5://proxy:1080"

    def test_get_httpx_proxy_config_none(self):
        """Test httpx proxy config when no proxy."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = None

        result = config.get_httpx_proxy_config()
        assert result is None

    def test_cleanup_apt_proxy_success(self):
        """Test cleanup of apt proxy configuration."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0)
                result = config.cleanup_apt_proxy()
                assert result is True

    def test_cleanup_apt_proxy_no_file(self):
        """Test cleanup when no apt proxy file exists."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("pathlib.Path.exists", return_value=False):
            result = config.cleanup_apt_proxy()
            assert result is True


class TestPackageCaching:
    """Tests for package caching functionality."""

    def test_cache_package_list(self):
        """Test caching package list."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        packages = ["nginx", "docker", "python3"]

        with patch("builtins.open", mock_open()) as mock_file:
            with patch("json.dump") as mock_dump:
                config.cache_package_list(packages)
                mock_dump.assert_called_once()
                call_args = mock_dump.call_args[0][0]
                assert call_args["packages"] == packages
                assert "cached_at" in call_args

    def test_cache_package_list_io_error(self):
        """Test caching with IO error."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("builtins.open", side_effect=OSError("Disk full")):
            # Should not raise exception
            config.cache_package_list(["nginx"])

    def test_get_cached_packages_success(self):
        """Test retrieving cached packages."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        cache_data = {
            "packages": ["nginx", "docker", "python3"],
            "cached_at": time.time(),
        }

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
                result = config.get_cached_packages()
                assert result == ["nginx", "docker", "python3"]

    def test_get_cached_packages_expired(self):
        """Test retrieving expired cache."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        # Cache from 48 hours ago (older than default 24h)
        cache_data = {
            "packages": ["nginx"],
            "cached_at": time.time() - (48 * 3600),
        }

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
                result = config.get_cached_packages(max_age_hours=24)
                assert result is None

    def test_get_cached_packages_no_file(self):
        """Test retrieving cache when file doesn't exist."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("pathlib.Path.exists", return_value=False):
            result = config.get_cached_packages()
            assert result is None

    def test_get_cached_packages_invalid_json(self):
        """Test retrieving cache with invalid JSON."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="invalid json")):
                result = config.get_cached_packages()
                assert result is None

    def test_enable_offline_fallback_cache_available(self):
        """Test offline fallback with cache available."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch.object(config, "get_cached_packages", return_value=["nginx", "docker"]):
            result = config.enable_offline_fallback()
            assert result is True

    def test_enable_offline_fallback_no_cache(self):
        """Test offline fallback without cache."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()

        with patch.object(config, "get_cached_packages", return_value=None):
            result = config.enable_offline_fallback()
            assert result is False


class TestAutoConfigure:
    """Tests for auto_configure method."""

    def test_auto_configure_offline_mode(self):
        """Test offline mode auto_configures with cache."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig(offline_mode=True)

        with patch.object(config, "enable_offline_fallback") as mock_fallback:
            config.auto_configure()
            mock_fallback.assert_called_once()

    def test_auto_configure_offline_no_cache(self):
        """Test auto_configure when offline without cache."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.is_online = False

        with patch.object(config, "enable_offline_fallback", return_value=False):
            # Should not raise exception
            config.auto_configure()

    def test_auto_configure_with_proxy(self):
        """Test auto_configure with proxy detected."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = {"http": "http://proxy:8080"}
            config.is_online = True

        with patch.object(config, "configure_apt_proxy") as mock_apt:
            with patch.object(config, "configure_pip_proxy") as mock_pip:
                config.auto_configure()
                mock_apt.assert_called_once()
                mock_pip.assert_called_once()

    def test_auto_configure_with_vpn(self):
        """Test auto_configure with VPN detected."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.is_vpn = True
            config.is_online = True
            config.proxy = None

        # Should not raise exception
        config.auto_configure()


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_check_proxy_auth_success(self):
        """Test proxy auth check - success."""
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=200)
            result = check_proxy_auth("http://proxy:8080")
            assert result == "success"

    def test_check_proxy_auth_required(self):
        """Test proxy auth check - auth required."""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ProxyError(
                "407 Proxy Authentication Required"
            )
            result = check_proxy_auth("http://proxy:8080")
            assert result == "auth_required"

    def test_check_proxy_auth_failed(self):
        """Test proxy auth check - failed."""
        with patch("requests.get", side_effect=requests.RequestException()):
            result = check_proxy_auth("http://proxy:8080")
            assert result == "failed"

    def test_add_proxy_auth(self):
        """Test adding authentication to proxy URL."""
        test_user = "user"
        test_pass = "pass"
        test_proxy = "http://proxy:8080"
        expected_url = f"http://{test_user}:{test_pass}@proxy:8080"

        result = add_proxy_auth(test_proxy, test_user, test_pass)
        assert result == expected_url

    def test_add_proxy_auth_no_protocol(self):
        """Test adding auth to proxy without protocol."""
        test_user = "user"
        test_pass = "pass"
        test_proxy = "proxy:8080"
        expected_url = f"http://{test_user}:{test_pass}@proxy:8080"

        result = add_proxy_auth(test_proxy, test_user, test_pass)
        assert result == expected_url

    def test_prompt_proxy_credentials(self):
        """Test prompting for proxy credentials."""
        with patch("builtins.input", return_value="testuser"):
            with patch("getpass.getpass", return_value="testpass"):
                username, password = prompt_proxy_credentials()
                assert username == "testuser"
                assert password == "testpass"


class TestPrintSummary:
    """Tests for print_summary method."""

    def test_print_summary_with_proxy(self):
        """Test summary printing with proxy."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = {"http": "http://proxy:8080"}
            config.is_vpn = False
            config.is_online = True
            config.connection_quality = "good"

        # Should not raise exception
        config.print_summary()

    def test_print_summary_without_proxy(self):
        """Test summary printing without proxy."""
        with patch.object(NetworkConfig, "detect"):
            config = NetworkConfig()
            config.proxy = None
            config.is_vpn = True
            config.is_online = False

        # Should not raise exception
        config.print_summary()


class TestIntegration:
    """Integration tests for NetworkConfig."""

    def test_full_detection_flow(self):
        """Test full detection flow with mocked system."""
        with patch.dict(os.environ, {"HTTP_PROXY": "http://proxy:8080"}):
            with patch("socket.socket") as mock_socket:
                mock_sock_instance = MagicMock()
                mock_socket.return_value = mock_sock_instance

                with patch("subprocess.check_output", return_value=b"eth0: UP"):
                    with patch("requests.head") as mock_head:
                        mock_head.return_value = MagicMock(status_code=200)

                        config = NetworkConfig()

                        assert config.proxy is not None
                        assert config.proxy["http"] == "http://proxy:8080"
                        assert config.is_online is True
                        assert config.is_vpn is False

    def test_offline_mode_integration(self):
        """Test complete offline mode flow."""
        cache_data = {
            "packages": ["nginx", "docker"],
            "cached_at": time.time(),
        }

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=json.dumps(cache_data))):
                config = NetworkConfig(offline_mode=True)
                config.auto_configure()

                cached = config.get_cached_packages()
                assert cached == ["nginx", "docker"]
