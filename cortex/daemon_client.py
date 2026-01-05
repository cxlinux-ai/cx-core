"""
Cortex Daemon Client Library

Provides a Python interface for communicating with the cortexd daemon
via Unix socket using JSON-based protocol.
"""

import socket
import json
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class DaemonConnectionError(Exception):
    """Raised when unable to connect to daemon"""
    pass

class DaemonProtocolError(Exception):
    """Raised when daemon communication protocol fails"""
    pass

class CortexDaemonClient:
    """Client for communicating with cortexd daemon"""

    DEFAULT_SOCKET_PATH = "/run/cortex.sock"
    DEFAULT_TIMEOUT = 5.0
    MAX_MESSAGE_SIZE = 65536

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH, timeout: float = DEFAULT_TIMEOUT):
        """
        Initialize daemon client.

        Args:
            socket_path: Path to Unix socket (default: /run/cortex.sock)
            timeout: Socket timeout in seconds (default: 5.0)
        """
        self.socket_path = socket_path
        self.timeout = timeout

    def _connect(self) -> socket.socket:
        """
        Create and connect Unix socket.

        Returns:
            Connected socket object

        Raises:
            DaemonConnectionError: If connection fails
        """
        if not os.path.exists(self.socket_path):
            raise DaemonConnectionError(
                f"Daemon socket not found at {self.socket_path}. "
                "Is cortexd running? Run: systemctl start cortexd"
            )

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect(self.socket_path)
            return sock
        except socket.error as e:
            raise DaemonConnectionError(f"Failed to connect to daemon: {e}")

    def _send_command(self, command: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send command to daemon and receive response.

        Args:
            command: Command name (status, alerts, health, etc)
            params: Optional command parameters

        Returns:
            Response dictionary

        Raises:
            DaemonConnectionError: If connection fails
            DaemonProtocolError: If protocol error occurs
        """
        request = {"command": command}
        if params:
            request.update(params)

        request_json = json.dumps(request)

        try:
            sock = self._connect()
            sock.sendall(request_json.encode('utf-8'))

            # Receive response
            response_data = b""
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                except socket.timeout:
                    break

            sock.close()

            if not response_data:
                raise DaemonProtocolError("Empty response from daemon")

            response = json.loads(response_data.decode('utf-8'))
            return response

        except json.JSONDecodeError as e:
            raise DaemonProtocolError(f"Invalid JSON response: {e}")
        except socket.timeout:
            raise DaemonConnectionError("Daemon connection timeout")

    def is_running(self) -> bool:
        """
        Check if daemon is running.

        Returns:
            True if daemon is responding, False otherwise
        """
        try:
            self._send_command("status")
            return True
        except (DaemonConnectionError, DaemonProtocolError):
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Get daemon status.

        Returns:
            Status dictionary containing version, uptime, etc.
        """
        return self._send_command("status")

    def get_health(self) -> Dict[str, Any]:
        """
        Get daemon health snapshot.

        Returns:
            Health snapshot with CPU, memory, disk usage, etc.
        """
        response = self._send_command("health")
        return response.get("health", {})

    def get_alerts(self, severity: Optional[str] = None, alert_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get alerts from daemon.

        Args:
            severity: Optional filter by severity (info, warning, error, critical)
            alert_type: Optional filter by alert type

        Returns:
            List of alert dictionaries
        """
        params = {}
        if severity:
            params["severity"] = severity
        if alert_type:
            params["type"] = alert_type

        response = self._send_command("alerts", params)
        return response.get("alerts", [])

    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge an alert.

        Args:
            alert_id: Alert ID to acknowledge

        Returns:
            True if successful
        """
        response = self._send_command("acknowledge_alert", {"alert_id": alert_id})
        return response.get("status") == "success"

    def reload_config(self) -> bool:
        """
        Reload daemon configuration.

        Returns:
            True if successful
        """
        response = self._send_command("config_reload")
        return response.get("status") == "success"

    def shutdown(self) -> bool:
        """
        Request daemon shutdown.

        Returns:
            True if shutdown initiated
        """
        try:
            response = self._send_command("shutdown")
            return response.get("status") == "success"
        except (DaemonConnectionError, DaemonProtocolError):
            # Daemon may have already shut down
            return True

    def get_alerts_by_severity(self, severity: str) -> List[Dict[str, Any]]:
        """Get alerts filtered by severity"""
        return self.get_alerts(severity=severity)

    def get_alerts_by_type(self, alert_type: str) -> List[Dict[str, Any]]:
        """Get alerts filtered by type"""
        return self.get_alerts(alert_type=alert_type)

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active (unacknowledged) alerts"""
        return self.get_alerts()

    def format_health_snapshot(self, health: Dict[str, Any]) -> str:
        """Format health snapshot for display"""
        lines = [
            "Daemon Health Snapshot:",
            f"  CPU Usage:          {health.get('cpu_usage', 0):.1f}%",
            f"  Memory Usage:       {health.get('memory_usage', 0):.1f}%",
            f"  Disk Usage:         {health.get('disk_usage', 0):.1f}%",
            f"  Active Processes:   {health.get('active_processes', 0)}",
            f"  Open Files:         {health.get('open_files', 0)}",
            f"  LLM Loaded:         {'Yes' if health.get('llm_loaded') else 'No'}",
            f"  Inference Queue:    {health.get('inference_queue_size', 0)}",
            f"  Alert Count:        {health.get('alerts_count', 0)}",
        ]
        return "\n".join(lines)

    def format_alerts(self, alerts: List[Dict[str, Any]]) -> str:
        """Format alerts for display"""
        if not alerts:
            return "No alerts"

        lines = [f"Alerts ({len(alerts)}):"]
        for alert in alerts:
            severity = alert.get("severity", "unknown").upper()
            title = alert.get("title", "Unknown")
            alert_id = alert.get("id", "")[:8]
            lines.append(f"  [{severity}] {title} ({alert_id}...)")

        return "\n".join(lines)
