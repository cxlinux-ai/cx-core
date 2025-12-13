import json
import datetime
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
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
        self.config_dir = Path.home() / ".cortex"
        self.config_dir.mkdir(exist_ok=True)
        
        self.history_file = self.config_dir / "notification_history.json"
        self.config_file = self.config_dir / "notification_config.json"
        
        # Default configuration
        self.config = {
            "dnd_start": "22:00",
            "dnd_end": "08:00",
            "enabled": True
        }
        
        self._load_config()
        self.history = self._load_history()

    def _load_config(self):
        """Loads configuration from JSON. Creates default if missing."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    self.config.update(json.load(f))
            except json.JSONDecodeError:
                console.print("[yellow]⚠️ Config file corrupted. Using defaults.[/yellow]")
        else:
            self._save_config()

    def _save_config(self):
        """Saves current configuration to JSON."""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

    def _load_history(self) -> List[Dict]:
        """Loads notification history."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []

    def _save_history(self):
        """Saves the last 100 notifications to history."""
        with open(self.history_file, 'w') as f:
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

    def send(self, title: str, message: str, level: str = "normal", actions: Optional[List[str]] = None):
        """
        Sends a notification.
        :param level: 'low', 'normal', 'critical'. Critical bypasses DND.
        :param actions: List of button labels e.g. ["View Logs", "Retry"]
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
            console.print(f"[bold green]🔔 Notification Sent:[/bold green] {title} - {message}{action_text}")
            self._log_history(title, message, level, status="sent", actions=actions)
        else:
            # Fallback for environments without GUI (like WSL default)
            console.print(f"[bold yellow]🔔 [Simulation] Notification:[/bold yellow] {title} - {message}{action_text}")
            self._log_history(title, message, level, status="simulated", actions=actions)

    def _log_history(self, title, message, level, status, actions=None):
        """Appends entry to history log."""
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "title": title,
            "message": message,
            "level": level,
            "status": status,
            "actions": actions if actions else []
        }
        self.history.append(entry)
        self._save_history()

if __name__ == "__main__":
    mgr = NotificationManager()
    # Test with actions to verify the new feature
    mgr.send("Action Test", "Testing buttons support", actions=["View Logs", "Retry"])