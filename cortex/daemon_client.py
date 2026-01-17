"""
Cortex Daemon IPC Client

Provides communication with the cortexd daemon via Unix socket IPC.
Supports the PR1 commands: ping, version, config.get, config.reload, shutdown.
"""

import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Default socket path (matches daemon config)
# NOTE: These paths assume standard installation locations:
# - Socket: /run/cortex/cortex.sock (systemd RuntimeDirectory)
# - Binary: /usr/local/bin/cortexd (standard install prefix)
# - Service: /etc/systemd/system/cortexd.service (systemd system directory)
# If installing to a custom prefix (e.g., /opt/cortex), these should be
# made configurable or adjusted accordingly.
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
        # Handle error field defensively - it may be a dict, string, or missing
        error_obj = data.get("error")
        if isinstance(error_obj, dict):
            error = error_obj.get("message")
            error_code = error_obj.get("code")
        elif isinstance(error_obj, str):
            error = error_obj
            error_code = None
        else:
            error = None
            error_code = None

        return cls(
            success=data.get("success", False),
            result=data.get("result"),
            error=error,
            error_code=error_code,
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
            # Create Unix socket and use context manager for automatic cleanup
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)

                # Connect to daemon
                sock.connect(self.socket_path)

                # Send request
                request_json = json.dumps(request)
                sock.sendall(request_json.encode("utf-8"))

                # Receive response - loop to handle partial reads
                # Unix sockets are stream-based, so data may arrive in multiple chunks
                chunks: list[bytes] = []
                total_received = 0
                response_data = b""

                while total_received < MAX_RESPONSE_SIZE:
                    chunk = sock.recv(4096)
                    if not chunk:
                        # Connection closed by server
                        break
                    chunks.append(chunk)
                    total_received += len(chunk)
                    response_data = b"".join(chunks)

                    # Try to parse - check for complete JSON object
                    # More efficient than joining on every iteration
                    try:
                        # Check if we have a complete JSON object by counting braces
                        # This is a simple heuristic - proper solution would use streaming parser
                        decoded = response_data.decode("utf-8")
                        if decoded.count("{") > 0 and decoded.count("{") == decoded.count("}"):
                            # Likely complete JSON, try parsing
                            response_json = json.loads(decoded)
                            return DaemonResponse.from_json(response_json)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # Incomplete JSON or invalid UTF-8, continue receiving
                        continue

                # If we get here, either connection closed or max size reached
                if not chunks:
                    raise DaemonProtocolError("Empty response from daemon")

                # Final attempt to parse (handles case where exactly MAX_RESPONSE_SIZE bytes sent)
                try:
                    response_json = json.loads(response_data.decode("utf-8"))
                    return DaemonResponse.from_json(response_json)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    raise DaemonProtocolError(f"Invalid JSON response: {e}")

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
