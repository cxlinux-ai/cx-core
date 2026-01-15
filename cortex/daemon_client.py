"""
Cortex Daemon IPC Client

Provides communication with the cortexd daemon via Unix socket IPC.
Supports the PR1 commands: ping, version, config.get, config.reload, shutdown.
"""

import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# Default socket path (matches daemon config)
DEFAULT_SOCKET_PATH = "/run/cortex/cortex.sock"
SOCKET_TIMEOUT = 5.0  # seconds
MAX_RESPONSE_SIZE = 65536  # 64KB

# Paths to check if daemon is installed
DAEMON_BINARY_PATH = "/usr/local/bin/cortexd"
DAEMON_SERVICE_PATH = "/etc/systemd/system/cortexd.service"


def is_daemon_installed() -> bool:
    """
    Check if the daemon is installed on the system.

    Returns:
        True if daemon binary or service file exists, False otherwise.
    """
    return Path(DAEMON_BINARY_PATH).exists() or Path(DAEMON_SERVICE_PATH).exists()


@dataclass
class DaemonResponse:
    """Response from the daemon."""

    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    error_code: int | None = None
    timestamp: int | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "DaemonResponse":
        """Parse a JSON response from the daemon."""
        return cls(
            success=data.get("success", False),
            result=data.get("result"),
            error=data.get("error", {}).get("message") if "error" in data else None,
            error_code=data.get("error", {}).get("code") if "error" in data else None,
            timestamp=data.get("timestamp"),
        )


class DaemonClient:
    """
    IPC client for communicating with the cortexd daemon.

    Uses Unix domain sockets for local communication.
    """

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH):
        """
        Initialize the daemon client.

        Args:
            socket_path: Path to the Unix socket.
        """
        self.socket_path = socket_path

    def is_daemon_running(self) -> bool:
        """
        Check if the daemon is running by testing socket connectivity.

        Returns:
            True if daemon is reachable, False otherwise.
        """
        if not Path(self.socket_path).exists():
            return False

        try:
            response = self.ping()
            return response.success
        except DaemonConnectionError:
            return False

    def _send_request(self, method: str, params: dict[str, Any] | None = None) -> DaemonResponse:
        """
        Send a request to the daemon and receive the response.

        Args:
            method: The IPC method to call.
            params: Optional parameters for the method.

        Returns:
            DaemonResponse containing the result or error.

        Raises:
            DaemonConnectionError: If unable to connect to daemon.
            DaemonProtocolError: If response is invalid.
        """
        request = {
            "method": method,
            "params": params or {},
        }

        try:
            # Create Unix socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(SOCKET_TIMEOUT)

            try:
                # Connect to daemon
                sock.connect(self.socket_path)

                # Send request
                request_json = json.dumps(request)
                sock.sendall(request_json.encode("utf-8"))

                # Receive response
                response_data = sock.recv(MAX_RESPONSE_SIZE)
                if not response_data:
                    raise DaemonProtocolError("Empty response from daemon")

                # Parse response
                response_json = json.loads(response_data.decode("utf-8"))
                return DaemonResponse.from_json(response_json)

            finally:
                sock.close()

        except FileNotFoundError:
            # Check if daemon is installed at all
            if not is_daemon_installed():
                raise DaemonNotInstalledError(
                    "The cortexd daemon is not installed. "
                    "Install it with: cortex daemon install --execute"
                )
            raise DaemonConnectionError(
                f"Daemon socket not found at {self.socket_path}. "
                "The daemon is installed but not running. Try: sudo systemctl start cortexd"
            )
        except ConnectionRefusedError:
            raise DaemonConnectionError(
                "Connection refused. The daemon is not running. Try: sudo systemctl start cortexd"
            )
        except TimeoutError:
            raise DaemonConnectionError("Connection timed out. The daemon may be unresponsive.")
        except json.JSONDecodeError as e:
            raise DaemonProtocolError(f"Invalid JSON response: {e}")

    # =========================================================================
    # PR1 IPC Methods
    # =========================================================================

    def ping(self) -> DaemonResponse:
        """
        Ping the daemon to check connectivity.

        Returns:
            DaemonResponse with {"pong": true} on success.
        """
        return self._send_request("ping")

    def version(self) -> DaemonResponse:
        """
        Get daemon version information.

        Returns:
            DaemonResponse with {"version": "x.x.x", "name": "cortexd"}.
        """
        return self._send_request("version")

    def config_get(self) -> DaemonResponse:
        """
        Get current daemon configuration.

        Returns:
            DaemonResponse with configuration key-value pairs.
        """
        return self._send_request("config.get")

    def config_reload(self) -> DaemonResponse:
        """
        Reload daemon configuration from disk.

        Returns:
            DaemonResponse with {"reloaded": true} on success.
        """
        return self._send_request("config.reload")

    def shutdown(self) -> DaemonResponse:
        """
        Request daemon shutdown.

        Returns:
            DaemonResponse with {"shutdown": "initiated"} on success.
        """
        return self._send_request("shutdown")


class DaemonNotInstalledError(Exception):
    """Raised when the daemon is not installed."""

    pass


class DaemonConnectionError(Exception):
    """Raised when unable to connect to the daemon (but it is installed)."""

    pass


class DaemonProtocolError(Exception):
    """Raised when the daemon response is invalid."""

    pass


# Convenience function for quick checks
def get_daemon_client(socket_path: str = DEFAULT_SOCKET_PATH) -> DaemonClient:
    """
    Get a daemon client instance.

    Args:
        socket_path: Path to the Unix socket.

    Returns:
        DaemonClient instance.
    """
    return DaemonClient(socket_path)
