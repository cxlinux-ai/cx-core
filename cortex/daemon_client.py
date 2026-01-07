"""
Cortex Daemon Client Library

Provides a Python interface for communicating with the cortexd daemon
via Unix socket using JSON-based protocol.
"""

import json
import logging
import os
import socket
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DaemonConnectionError(Exception):
    """Raised when unable to connect to daemon"""

    pass


class DaemonProtocolError(Exception):
    """Raised when daemon communication protocol fails"""

    pass


class CortexDaemonClient:
    """Client for communicating with cortexd daemon"""

    DEFAULT_SOCKET_PATH = "/run/cortex/cortex.sock"
    DEFAULT_TIMEOUT = 5.0
    MAX_MESSAGE_SIZE = 65536

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH, timeout: float = DEFAULT_TIMEOUT):
        """
        Initialize daemon client.

        Args:
            socket_path: Path to Unix socket (default: /run/cortex/cortex.sock)
            timeout: Socket timeout in seconds (default: 5.0)
        """
        self.socket_path = socket_path
        self.timeout = timeout

    def _connect(self, timeout: float | None = None) -> socket.socket:
        """
        Create and connect Unix socket.

        Args:
            timeout: Socket timeout in seconds (uses default if None)

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
            sock.settimeout(timeout if timeout is not None else self.timeout)
            sock.connect(self.socket_path)
            return sock
        except OSError as e:
            raise DaemonConnectionError(f"Failed to connect to daemon: {e}")

    def _send_request(
        self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """
        Send request to daemon and receive response.

        Args:
            method: Method name (status, health, alerts, etc)
            params: Optional method parameters
            timeout: Custom timeout for long-running operations (uses default if None)

        Returns:
            Response dictionary with 'success' and 'result' or 'error'

        Raises:
            DaemonConnectionError: If connection fails
            DaemonProtocolError: If protocol error occurs
        """
        # Build JSON-RPC style request
        request = {"method": method, "params": params or {}}

        request_json = json.dumps(request)
        logger.debug(f"Sending: {request_json}")

        try:
            sock = self._connect(timeout)
            sock.sendall(request_json.encode("utf-8"))

            # Receive response
            response_data = b""
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                    # Try to parse - if valid JSON, we're done
                    try:
                        json.loads(response_data.decode("utf-8"))
                        break
                    except json.JSONDecodeError:
                        continue
                except TimeoutError:
                    break

            sock.close()

            if not response_data:
                raise DaemonProtocolError("Empty response from daemon")

            response = json.loads(response_data.decode("utf-8"))
            logger.debug(f"Received: {response}")
            return response

        except json.JSONDecodeError as e:
            raise DaemonProtocolError(f"Invalid JSON response: {e}")
        except TimeoutError:
            raise DaemonConnectionError("Daemon connection timeout")

    def _check_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """
        Check response for success and extract result.

        Args:
            response: Response dictionary from daemon

        Returns:
            Result dictionary

        Raises:
            DaemonProtocolError: If response indicates error
        """
        if response.get("success", False):
            return response.get("result", {})
        else:
            error = response.get("error", {})
            if isinstance(error, dict):
                message = error.get("message", "Unknown error")
                code = error.get("code", -1)
            else:
                message = str(error)
                code = -1
            raise DaemonProtocolError(f"Daemon error ({code}): {message}")

    def is_running(self) -> bool:
        """
        Check if daemon is running.

        Returns:
            True if daemon is responding, False otherwise
        """
        try:
            response = self._send_request("ping")
            return response.get("success", False)
        except (DaemonConnectionError, DaemonProtocolError):
            return False

    def ping(self) -> bool:
        """
        Ping the daemon.

        Returns:
            True if daemon responded with pong
        """
        try:
            response = self._send_request("ping")
            result = self._check_response(response)
            return result.get("pong", False)
        except (DaemonConnectionError, DaemonProtocolError):
            return False

    def get_status(self) -> dict[str, Any]:
        """
        Get daemon status.

        Returns:
            Status dictionary containing version, uptime, etc.
        """
        response = self._send_request("status")
        return self._check_response(response)

    def get_health(self) -> dict[str, Any]:
        """
        Get daemon health snapshot.

        Returns:
            Health snapshot with CPU, memory, disk usage, etc.
        """
        response = self._send_request("health")
        return self._check_response(response)

    def get_version(self) -> dict[str, Any]:
        """
        Get daemon version info.

        Returns:
            Version dictionary with version and name
        """
        response = self._send_request("version")
        return self._check_response(response)

    def get_alerts(
        self, severity: str | None = None, alert_type: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get alerts from daemon.

        Args:
            severity: Optional filter by severity (info, warning, error, critical)
            alert_type: Optional filter by alert type
            limit: Maximum number of alerts to return

        Returns:
            List of alert dictionaries
        """
        params = {"limit": limit}
        if severity:
            params["severity"] = severity
        if alert_type:
            params["type"] = alert_type

        response = self._send_request("alerts", params)
        result = self._check_response(response)
        return result.get("alerts", [])

    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge an alert.

        Args:
            alert_id: Alert ID to acknowledge

        Returns:
            True if successful
        """
        response = self._send_request("alerts.acknowledge", {"id": alert_id})
        try:
            self._check_response(response)
            return True
        except DaemonProtocolError:
            return False

    def acknowledge_all_alerts(self) -> int:
        """
        Acknowledge all active alerts.

        Returns:
            Number of alerts acknowledged
        """
        response = self._send_request("alerts.acknowledge", {"all": True})
        result = self._check_response(response)
        return result.get("acknowledged_count", 0)

    def dismiss_alert(self, alert_id: str) -> bool:
        """
        Dismiss (delete) an alert.

        Args:
            alert_id: Alert ID to dismiss

        Returns:
            True if successful
        """
        response = self._send_request("alerts.dismiss", {"id": alert_id})
        try:
            self._check_response(response)
            return True
        except DaemonProtocolError:
            return False

    def reload_config(self) -> bool:
        """
        Reload daemon configuration.

        Returns:
            True if successful
        """
        response = self._send_request("config.reload")
        try:
            result = self._check_response(response)
            return result.get("reloaded", False)
        except DaemonProtocolError:
            return False

    def get_config(self) -> dict[str, Any]:
        """
        Get current daemon configuration.

        Returns:
            Configuration dictionary
        """
        response = self._send_request("config.get")
        return self._check_response(response)

    def shutdown(self) -> bool:
        """
        Request daemon shutdown.

        Returns:
            True if shutdown initiated
        """
        try:
            response = self._send_request("shutdown")
            self._check_response(response)
            return True
        except (DaemonConnectionError, DaemonProtocolError):
            # Daemon may have already shut down
            return True

    # LLM operations

    def get_llm_status(self) -> dict[str, Any]:
        """
        Get LLM engine status.

        Returns:
            LLM status dictionary
        """
        response = self._send_request("llm.status")
        return self._check_response(response)

    # Timeout for model loading (can take 30-120+ seconds for large models)
    MODEL_LOAD_TIMEOUT = 120.0

    def load_model(self, model_path: str) -> dict[str, Any]:
        """
        Load an LLM model.

        Args:
            model_path: Path to GGUF model file

        Returns:
            Model info dictionary
        """
        response = self._send_request(
            "llm.load", {"model_path": model_path}, timeout=self.MODEL_LOAD_TIMEOUT
        )
        return self._check_response(response)

    def unload_model(self) -> bool:
        """
        Unload the current LLM model.

        Returns:
            True if successful
        """
        response = self._send_request("llm.unload")
        try:
            result = self._check_response(response)
            return result.get("unloaded", False)
        except DaemonProtocolError:
            return False

    # Timeout for inference (depends on max_tokens and model size)
    INFERENCE_TIMEOUT = 60.0

    def infer(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: str | None = None,
    ) -> dict[str, Any]:
        """
        Run inference on loaded model.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
            stop: Optional stop sequence

        Returns:
            Inference result dictionary
        """
        params = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if stop:
            params["stop"] = stop

        response = self._send_request("llm.infer", params, timeout=self.INFERENCE_TIMEOUT)
        return self._check_response(response)

    # Convenience methods

    def get_alerts_by_severity(self, severity: str) -> list[dict[str, Any]]:
        """Get alerts filtered by severity"""
        return self.get_alerts(severity=severity)

    def get_alerts_by_type(self, alert_type: str) -> list[dict[str, Any]]:
        """Get alerts filtered by type"""
        return self.get_alerts(alert_type=alert_type)

    def get_active_alerts(self) -> list[dict[str, Any]]:
        """Get all active (unacknowledged) alerts"""
        return self.get_alerts()

    def format_health_snapshot(self, health: dict[str, Any]) -> str:
        """Format health snapshot for display"""
        lines = [
            f"  CPU Usage:          {health.get('cpu_usage_percent', 0):.1f}%",
            f"  Memory Usage:       {health.get('memory_usage_percent', 0):.1f}% ({health.get('memory_used_mb', 0):.0f} MB / {health.get('memory_total_mb', 0):.0f} MB)",
            f"  Disk Usage:         {health.get('disk_usage_percent', 0):.1f}% ({health.get('disk_used_gb', 0):.1f} GB / {health.get('disk_total_gb', 0):.1f} GB)",
            "",
            f"  Pending Updates:    {health.get('pending_updates', 0)}",
            f"  Security Updates:   {health.get('security_updates', 0)}",
            "",
            f"  LLM Loaded:         {'Yes' if health.get('llm_loaded') else 'No'}",
            f"  LLM Model:          {health.get('llm_model_name', '') or 'Not loaded'}",
            f"  Inference Queue:    {health.get('inference_queue_size', 0)}",
            "",
            f"  Active Alerts:      {health.get('active_alerts', 0)}",
            f"  Critical Alerts:    {health.get('critical_alerts', 0)}",
        ]
        return "\n".join(lines)

    def format_status(self, status: dict[str, Any]) -> str:
        """Format daemon status for display"""
        uptime = status.get("uptime_seconds", 0)
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

        lines = [
            f"  Version:            {status.get('version', 'unknown')}",
            f"  Running:            {'Yes' if status.get('running') else 'No'}",
            f"  Uptime:             {uptime_str}",
        ]

        # Add health info if present
        if "health" in status:
            lines.append("")
            lines.append("  Health:")
            health = status["health"]
            lines.append(f"    Memory:           {health.get('memory_usage_percent', 0):.1f}%")
            lines.append(f"    Disk:             {health.get('disk_usage_percent', 0):.1f}%")
            lines.append(f"    Active Alerts:    {health.get('active_alerts', 0)}")

        # Add LLM info if present
        if "llm" in status:
            lines.append("")
            lines.append("  LLM:")
            llm = status["llm"]
            lines.append(f"    Loaded:           {'Yes' if llm.get('loaded') else 'No'}")
            if llm.get("loaded"):
                lines.append(f"    Model:            {llm.get('model_name', 'unknown')}")
                lines.append(f"    Queue Size:       {llm.get('queue_size', 0)}")

        return "\n".join(lines)

    def format_alerts(self, alerts: list[dict[str, Any]]) -> str:
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
