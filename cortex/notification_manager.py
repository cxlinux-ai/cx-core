import datetime
import json
import shutil
import subprocess
import threading
from pathlib import Path

from rich.console import Console

# Initialize console for pretty logging
console = Console()


class NotificationManager:
    """
    Manages desktop notifications for Cortex OS.
    Features:
    - Cross-platform support (Linux notify-send / Fallback logging)
    - Do Not Disturb (DND) mode based on time windows
    - JSON-based history logging
    - Action buttons support (Interface level)
    """

    def __init__(self):
        # Set up configuration directory in user home
        """
        Initialize the NotificationManager.
        
        Creates the configuration directory (~/.cortex) if missing, sets paths for the history and config JSON files, establishes default DND configuration (dnd_start="22:00", dnd_end="08:00", enabled=True), loads persisted configuration and notification history, and initializes a thread lock for protecting history list and file I/O.
        """
        self.config_dir = Path.home() / ".cortex"
        self.config_dir.mkdir(exist_ok=True)

        self.history_file = self.config_dir / "notification_history.json"
        self.config_file = self.config_dir / "notification_config.json"

        # Default configuration
        self.config = {"dnd_start": "22:00", "dnd_end": "08:00", "enabled": True}

        self._load_config()
        self.history = self._load_history()
        self._history_lock = threading.Lock()  # Protect history list and file I/O

    def _load_config(self):
        """
        Load configuration from the config JSON file and merge it into the in-memory configuration.
        
        If the config file exists, parse it as JSON and update self.config with the parsed values. If the file contains invalid JSON, leave the current configuration unchanged and print a warning to the console. If the config file does not exist, create it by writing the current in-memory configuration to disk via _save_config().
        """
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    self.config.update(json.load(f))
            except json.JSONDecodeError:
                console.print("[yellow]⚠️ Config file corrupted. Using defaults.[/yellow]")
        else:
            self._save_config()

    def _save_config(self):
        """
        Write the in-memory configuration to the configured JSON file, overwriting its contents.
        
        The file is written with an indentation of 4 spaces to produce human-readable JSON.
        """
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=4)

    def _load_history(self) -> list[dict]:
        """
        Load the notification history from the configured history JSON file.
        
        If the history file exists and contains valid JSON, return the parsed list of history entry dicts.
        If the file is missing or contains invalid JSON, return an empty list.
        
        Returns:
            list[dict]: Parsed notification history entries, or an empty list if none are available.
        """
        # Note: Called only during __init__, but protected for consistency
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []

    def _save_history(self):
        """
        Write the most recent 100 notification entries to the history JSON file.
        
        This method overwrites the history file with up to the last 100 entries from self.history, serialized as indented JSON. Caller must hold self._history_lock to ensure thread safety.
        """
        # Caller must hold self._history_lock
        with open(self.history_file, "w") as f:
            json.dump(self.history[-100:], f, indent=4)

    def _get_current_time(self):
        """Helper method to get current time. Makes testing easier."""
        return datetime.datetime.now().time()

    def is_dnd_active(self) -> bool:
        """Checks if the current time falls within the Do Not Disturb window."""
        # If globally disabled, treat as DND active (suppress all except critical)
        if not self.config.get("enabled", True):
            return True

        now = self._get_current_time()
        start_str = self.config["dnd_start"]
        end_str = self.config["dnd_end"]

        # Parse time strings
        start_time = datetime.datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.datetime.strptime(end_str, "%H:%M").time()

        # Check time window (handles overnight windows like 22:00-08:00)
        if start_time < end_time:
            return start_time <= now <= end_time
        else:
            return now >= start_time or now <= end_time

    def send(
        self, title: str, message: str, level: str = "normal", actions: list[str] | None = None
    ):
        """
        Send a desktop notification with optional action buttons, honoring Do Not Disturb (DND) rules.
        
        Parameters:
            title (str): Notification title.
            message (str): Notification body text.
            level (str): Severity level; one of "low", "normal", or "critical". A "critical" notification bypasses DND.
            actions (list[str] | None): Optional list of action button labels (e.g., ["View Logs", "Retry"]). When supported by the platform, these are delivered as notification actions/hints.
        
        Behavior:
            - If DND is active and `level` is not "critical", the notification is suppressed.
            - Attempts to send a native notification when available; otherwise logs a simulated notification to the console.
            - Records every outcome to the notification history with a `status` of "suppressed", "sent", or "simulated".
        """
        # 1. Check DND status
        if self.is_dnd_active() and level != "critical":
            console.print(f"[dim]zzz DND Active. Suppressed: {title}[/dim]")
            self._log_history(title, message, level, status="suppressed", actions=actions)
            return

        # 2. Try native Linux notification (notify-send)
        success = False
        if shutil.which("notify-send"):
            try:
                cmd = ["notify-send", title, message, "-u", level, "-a", "Cortex"]

                # Add actions as hints if supported/requested
                if actions:
                    for action in actions:
                        cmd.extend(["--hint=string:action:" + action])

                subprocess.run(cmd, check=True)
                success = True
            except Exception as e:
                console.print(f"[red]Failed to send notification: {e}[/red]")

        # 3. Fallback / Logger output
        # Formats actions for display: " [Actions: View Logs, Retry]"
        action_text = f" [bold cyan][Actions: {', '.join(actions)}][/bold cyan]" if actions else ""

        if success:
            console.print(
                f"[bold green]🔔 Notification Sent:[/bold green] {title} - {message}{action_text}"
            )
            self._log_history(title, message, level, status="sent", actions=actions)
        else:
            # Fallback for environments without GUI (like WSL default)
            console.print(
                f"[bold yellow]🔔 [Simulation] Notification:[/bold yellow] {title} - {message}{action_text}"
            )
            self._log_history(title, message, level, status="simulated", actions=actions)

    def _log_history(self, title, message, level, status, actions=None):
        """
        Append a notification event to the manager's history and persist it to disk in a thread-safe manner.
        
        Parameters:
            title (str): Notification title.
            message (str): Notification body text.
            level (str): Notification severity (e.g., 'low', 'normal', 'critical').
            status (str): Outcome label for the entry (e.g., 'sent', 'suppressed', 'simulated').
            actions (list[str] | None): Optional list of action button labels; stored as an empty list if None.
        
        Notes:
            This method acquires an internal lock to ensure atomic append and save of the history entry. The entry includes an ISO 8601 timestamp.
        """
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "title": title,
            "message": message,
            "level": level,
            "status": status,
            "actions": actions if actions else [],
        }
        with self._history_lock:
            self.history.append(entry)
            self._save_history()


if __name__ == "__main__":
    mgr = NotificationManager()
    # Test with actions to verify the new feature
    mgr.send("Action Test", "Testing buttons support", actions=["View Logs", "Retry"])