"""
Network Configuration and Proxy Detection for Cortex

Handles corporate proxies, VPNs, and network configurations automatically.
Detects system proxy settings and configures tools (apt, pip, httpx) accordingly.
"""

import getpass
import json
import logging
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import requests
from rich.console import Console

logger = logging.getLogger(__name__)

console = Console()


class NetworkConfig:
    """
    Detects and manages network configuration including proxies and VPN.

    Features:
    - Auto-detect system proxy settings
    - Support HTTP/HTTPS/SOCKS proxies
    - Handle proxy authentication
    - VPN detection
    - Connectivity testing
    """

    def __init__(
        self, force_proxy: str | None = None, offline_mode: bool = False, auto_detect: bool = True
    ):
        """
        Initialize network configuration.

        Args:
            force_proxy: Optional proxy URL to force use (overrides detection)
            offline_mode: If True, skip connectivity checks and enable cache
            auto_detect: If True, run detection immediately (default). Set to False for lazy loading.
        """
        self.force_proxy = force_proxy
        self.offline_mode = offline_mode
        self.proxy: dict[str, str] | None = None
        self.is_vpn = False
        self.is_online = False
        self.connection_quality = "unknown"
        self.cache_dir = Path.home() / ".cortex" / "cache"
        self._detected = False

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Skip detection if offline mode is enabled
        if offline_mode:
            self.is_online = False
            self._detected = True
        elif auto_detect:
            self.detect()

    def detect(self, check_quality: bool = False) -> None:
        """
        Run all detection methods.

        Args:
            check_quality: If True, also check connection quality (adds 1-5s delay).
                        Set to False to skip quality check for faster detection.

        Can be called manually for lazy loading or after initialization.
        """
        if self._detected:
            return  # Already detected, skip

        if self.force_proxy:
            self.proxy = self._parse_proxy_url(self.force_proxy)
        else:
            self.proxy = self.detect_proxy()

        self.is_vpn = self.detect_vpn()
        self.is_online = self.check_connectivity()

        # Only check quality if explicitly requested (saves 1-5 seconds)
        if self.is_online and check_quality:
            self.connection_quality = self.detect_network_quality()

        self._detected = True

    # === Proxy Detection ===

    def detect_proxy(self) -> dict[str, str] | None:
        """
        Detect proxy settings from multiple sources.

        Priority:
        1. Environment variables
        2. GNOME/KDE settings
        3. System configuration files

        Returns:
            Dict with 'http', 'https', 'no_proxy' keys, or None
        """
        # Try environment variables first
        proxy = self._detect_env_proxy()
        if proxy and proxy.get("http"):
            console.print("[dim] Detected proxy from environment[/dim]")
            return proxy

        # Try GNOME settings
        proxy = self._detect_gnome_proxy()
        if proxy:
            console.print("[dim] Detected proxy from GNOME settings[/dim]")
            return proxy

        # Try system files
        proxy = self._detect_system_proxy()
        if proxy:
            console.print("[dim] Detected proxy from system config[/dim]")
            return proxy

        return None

    def _detect_env_proxy(self) -> dict[str, str]:
        """Detect proxy from environment variables (including SOCKS)."""
        return {
            "http": os.getenv("HTTP_PROXY") or os.getenv("http_proxy"),
            "https": os.getenv("HTTPS_PROXY") or os.getenv("https_proxy"),
            "socks": os.getenv("SOCKS_PROXY") or os.getenv("socks_proxy"),
            "no_proxy": os.getenv("NO_PROXY") or os.getenv("no_proxy"),
        }

    def _detect_gnome_proxy(self) -> dict[str, str] | None:
        """Detect proxy from GNOME settings."""
        try:
            mode = (
                subprocess.check_output(
                    ["gsettings", "get", "org.gnome.system.proxy", "mode"],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
                .strip("'")
            )

            if mode != "manual":
                return None

            host = (
                subprocess.check_output(
                    ["gsettings", "get", "org.gnome.system.proxy.http", "host"],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
                .strip("'")
            )

            port = (
                subprocess.check_output(
                    ["gsettings", "get", "org.gnome.system.proxy.http", "port"],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )

            if host and port:
                # Proxy URLs use http:// protocol (traffic through proxy can be HTTPS)
                proxy_url = f"http://{host}:{port}"  # noqa: S105 NOSONAR
                return {"http": proxy_url, "https": proxy_url}
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            logger.debug(f"GNOME proxy settings not available: {e}")

        return None

    def _detect_system_proxy(self) -> dict[str, str] | None:
        """Detect proxy from system configuration files."""
        # Check /etc/environment
        try:
            with open("/etc/environment") as f:
                for line in f:
                    if "http_proxy=" in line.lower():
                        proxy_url = line.split("=")[1].strip().strip("\"'")
                        return {"http": proxy_url, "https": proxy_url}
        except (FileNotFoundError, PermissionError) as e:
            logger.debug(f"Cannot read /etc/environment: {e}")

        # Check apt proxy config
        apt_conf_paths = [
            "/etc/apt/apt.conf.d/proxy.conf",
            "/etc/apt/apt.conf",
        ]

        for conf_path in apt_conf_paths:
            try:
                with open(conf_path) as f:
                    content = f.read()
                    # Parse: Acquire::http::Proxy "http://proxy:8080";
                    if "Acquire::http::Proxy" in content:
                        for line in content.split("\n"):
                            if "Acquire::http::Proxy" in line and '"' in line:
                                proxy_url = line.split('"')[1]
                                return {"http": proxy_url, "https": proxy_url}
            except (FileNotFoundError, PermissionError) as e:
                logger.debug(f"Cannot read apt proxy config from {conf_path}: {e}")
                continue

        return None

    def _parse_proxy_url(self, proxy_url: str) -> dict[str, str]:
        """Parse a proxy URL string into a dict."""
        return {"http": proxy_url, "https": proxy_url}

    # === VPN Detection ===

    def detect_vpn(self) -> bool:
        """
        Detect if system is connected to a VPN.

        Checks for:
        - VPN network interfaces (tun, tap, ppp, wg)
        - VPN routes in routing table
        """
        # Check for VPN interfaces
        try:
            result = subprocess.check_output(
                ["ip", "link", "show"], stderr=subprocess.DEVNULL
            ).decode()
            vpn_keywords = ["tun", "tap", "ppp", "wg", "ipsec", "proton", "nordlynx", "mullvad"]
            if any(kw in result for kw in vpn_keywords):
                console.print("[dim] VPN connection detected[/dim]")
                return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            # ip command not available or failed - continue to next check
            pass

        # Check routing table
        try:
            result = subprocess.check_output(["ip", "route"], stderr=subprocess.DEVNULL).decode()
            if "tun" in result or "ppp" in result:
                console.print("[dim] VPN connection detected[/dim]")
                return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            # Routing table check failed - assume no VPN
            pass

        return False

    # === Connectivity Testing ===

    def check_connectivity(self, timeout: int = 3) -> bool:
        """
        Check if system has internet connectivity.

        Args:
            timeout: Timeout in seconds for each test

        Returns:
            True if internet is reachable
        """
        # Quick TCP connection check (doesn't affect global socket timeout)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(("8.8.8.8", 53))  # Google DNS on port 53
            sock.close()
            return True
        except OSError:
            # Connection failed - try HTTP endpoints
            pass

        # Try multiple HTTP endpoints
        test_urls = ["https://1.1.1.1", "https://8.8.8.8", "https://api.github.com"]

        for url in test_urls:
            try:
                requests.head(url, timeout=timeout, proxies=self.proxy)
                return True
            except requests.RequestException:
                continue

        console.print("[yellow] No internet connectivity detected[/yellow]")
        return False

    def detect_network_quality(self, timeout: int = 5) -> str:
        """
        Detect network connection quality.

        Returns:
            'good', 'slow', or 'offline'
        """
        try:
            start = time.time()
            requests.head("https://1.1.1.1", timeout=timeout, proxies=self.proxy)
            latency = time.time() - start

            if latency > 2:
                return "slow"
            return "good"
        except requests.RequestException:
            return "offline"

    # === Configuration Methods ===

    def configure_apt_proxy(self) -> bool:
        """
        Configure apt to use detected proxy.

        Creates /etc/apt/apt.conf.d/90cortex-proxy

        Returns:
            True if successful
        """
        if not self.proxy or not self.proxy.get("http"):
            return False

        http_proxy = self.proxy["http"]
        https_proxy = self.proxy.get("https", http_proxy)  # Use HTTPS proxy or fallback to HTTP

        apt_conf = f"""# Cortex auto-generated proxy configuration
Acquire::http::Proxy "{http_proxy}";
Acquire::https::Proxy "{https_proxy}";
"""

        conf_path = Path("/etc/apt/apt.conf.d/90cortex-proxy")

        try:
            # Need sudo to write to /etc
            subprocess.run(
                ["sudo", "tee", str(conf_path)],
                input=apt_conf.encode(),
                stdout=subprocess.DEVNULL,
                check=True,
            )
            console.print(
                f"[green] Configured apt for proxy: HTTP={http_proxy}, HTTPS={https_proxy}[/green]"
            )
            return True
        except (subprocess.CalledProcessError, PermissionError) as e:
            console.print(f"[yellow] Could not configure apt proxy: {e}[/yellow]")
            return False

    def configure_pip_proxy(self) -> None:
        """Configure pip to use detected proxy via environment variables."""
        if not self.proxy or not self.proxy.get("http"):
            return

        http_proxy = self.proxy["http"]
        https_proxy = self.proxy.get("https", http_proxy)  # Use HTTPS proxy or fallback to HTTP

        os.environ["HTTP_PROXY"] = http_proxy
        os.environ["HTTPS_PROXY"] = https_proxy

        console.print(
            f"[green] Configured pip for proxy: HTTP={http_proxy}, HTTPS={https_proxy}[/green]"
        )

    def get_httpx_proxy_config(self) -> dict | None:
        """
        Get proxy configuration for httpx/requests.

        Returns:
            Dict suitable for httpx.Client(proxies=...) or requests.get(proxies=...)
            Supports HTTP, HTTPS, and SOCKS proxies.
        """
        if not self.proxy:
            return None

        config = {}
        if self.proxy.get("http"):
            config["http://"] = self.proxy["http"]
        if self.proxy.get("https"):
            config["https://"] = self.proxy["https"]
        if self.proxy.get("socks"):
            # SOCKS proxy applies to all protocols
            config["all://"] = self.proxy["socks"]

        return config if config else None

    # === Package Caching for Offline Mode ===

    def cache_package_list(self, packages: list[str]) -> None:
        """
        Cache available package list for offline use.

        Args:
            packages: List of package names/IDs
        """
        cache_file = self.cache_dir / "available_packages.json"

        try:
            with open(cache_file, "w") as f:
                json.dump(
                    {
                        "packages": packages,
                        "cached_at": time.time(),
                    },
                    f,
                )
            logger.debug(f"Cached {len(packages)} packages to {cache_file}")
        except OSError as e:
            logger.warning(f"Could not cache package list: {e}")

    def get_cached_packages(self, max_age_hours: int = 24) -> list[str] | None:
        """
        Retrieve cached package list for offline use.

        Args:
            max_age_hours: Maximum age of cache in hours (default 24)

        Returns:
            List of cached packages or None if cache is too old/missing
        """
        cache_file = self.cache_dir / "available_packages.json"

        if not cache_file.exists():
            logger.debug("No cached package list found")
            return None

        try:
            with open(cache_file) as f:
                data = json.load(f)

            cached_at = data.get("cached_at", 0)
            age_hours = (time.time() - cached_at) / 3600

            if age_hours > max_age_hours:
                logger.debug(f"Cached package list is {age_hours:.1f}h old (max {max_age_hours}h)")
                return None

            packages = data.get("packages", [])
            logger.debug(f"Loaded {len(packages)} packages from cache ({age_hours:.1f}h old)")
            return packages

        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning(f"Could not read cached packages: {e}")
            return None

    def enable_offline_fallback(self) -> bool:
        """
        Enable offline fallback mode with cached package lists.

        Returns:
            True if cache is available
        """
        cached = self.get_cached_packages()
        if cached:
            console.print(f"[cyan]📦 Using cached package list ({len(cached)} packages)[/cyan]")
            return True
        else:
            console.print("[yellow]⚠️ No cached packages available for offline mode[/yellow]")
            return False

    def cleanup_apt_proxy(self) -> bool:
        """
        Remove Cortex proxy configuration from apt.

        Returns:
            True if successful
        """
        conf_path = Path("/etc/apt/apt.conf.d/90cortex-proxy")

        if not conf_path.exists():
            return True

        try:
            subprocess.run(["sudo", "rm", str(conf_path)], check=True, stderr=subprocess.DEVNULL)
            console.print("[dim]🧹 Cleaned up apt proxy configuration[/dim]")
            return True
        except subprocess.CalledProcessError:
            return False

    def auto_configure(self) -> None:
        """
        Automatically configure all tools based on detected network settings.

        This is called on startup to:
        - Configure apt to use proxy
        - Configure pip to use proxy
        - Set up httpx for LLM API calls
        - Handle offline mode gracefully
        """
        if self.offline_mode:
            console.print("[yellow]🔌 Offline mode - attempting to use cached packages[/yellow]")
            self.enable_offline_fallback()
            return

        # If no internet, inform user and try cache
        if not self.is_online:
            console.print(
                "[yellow]⚠️ No internet connection detected - attempting offline mode[/yellow]"
            )
            if not self.enable_offline_fallback():
                console.print("[red]No cached packages available. Some operations may fail.[/red]")
            return

        # If proxy detected, configure tools
        if self.proxy and self.proxy.get("http"):
            proxy_url = self.proxy["http"]
            console.print(f"[cyan] Detected proxy: {proxy_url}[/cyan]")

            # Configure apt (may prompt for sudo)
            self.configure_apt_proxy()

            # Configure pip (environment variables)
            self.configure_pip_proxy()

            console.print("[green] Network configuration complete[/green]")
        elif self.is_vpn:
            console.print("[cyan] VPN detected - using direct connection[/cyan]")

    # === Information Display ===

    def print_summary(self) -> None:
        """Print a summary of detected network configuration."""
        console.print("\n[bold]🌐 Network Configuration[/bold]")

        if self.proxy and self.proxy.get("http"):
            console.print(f"  Proxy: [cyan]{self.proxy['http']}[/cyan]")
        else:
            console.print("  Proxy: [dim]None detected[/dim]")

        console.print(f"  VPN: [cyan]{'Yes' if self.is_vpn else 'No'}[/cyan]")
        console.print(f"  Internet: [cyan]{'Online' if self.is_online else 'Offline'}[/cyan]")

        if self.is_online:
            quality_color = "green" if self.connection_quality == "good" else "yellow"
            console.print(
                f"  Quality: [{quality_color}]{self.connection_quality.title()}[/{quality_color}]"
            )

        console.print()


# === Helper Functions ===


def check_proxy_auth(proxy_url: str, timeout: int = 5) -> str:
    """
    Test if a proxy requires authentication.

    Args:
        proxy_url: Proxy URL to test
        timeout: Request timeout

    Returns:
        'success', 'auth_required', or 'failed'
    """
    try:
        response = requests.get(
            "https://httpbin.org/ip",
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=timeout,
        )
        if response.status_code == 200:
            return "success"
    except requests.exceptions.ProxyError as e:
        if "407" in str(e):
            return "auth_required"
    except requests.RequestException:
        # Connection failed for other reasons
        pass

    return "failed"


def prompt_proxy_credentials() -> tuple[str, str]:
    """
    Prompt user for proxy credentials.

    Returns:
        Tuple of (username, password)
    """
    console.print("\n[yellow] Proxy authentication required[/yellow]")
    username = input("Username: ")
    password = getpass.getpass("Password: ")
    return username, password


def add_proxy_auth(proxy_url: str, username: str, password: str) -> str:
    """
    Add authentication to a proxy URL with proper URL encoding.

    **Security Warning**: This embeds credentials directly in the URL.
    Credentials may be visible in logs, error messages, or process listings.
    Consider using environment variables or credential managers for production.

    Args:
        proxy_url: Base proxy URL
        username: Username (will be URL-encoded)
        password: Password (will be URL-encoded)

    Returns:
        Proxy URL with embedded, URL-encoded credentials
    """
    # URL-encode credentials to handle special characters (@, :, /, %, etc.)
    encoded_username = quote(username, safe="")
    encoded_password = quote(password, safe="")

    logger.warning("Embedding credentials in proxy URL - ensure logs are secured")

    if "://" in proxy_url:
        protocol, rest = proxy_url.split("://", 1)
        return f"{protocol}://{encoded_username}:{encoded_password}@{rest}"
    else:
        # Default to http:// for proxy URLs (standard for corporate proxies)
        return f"http://{encoded_username}:{encoded_password}@{proxy_url}"  # noqa: S105 NOSONAR
