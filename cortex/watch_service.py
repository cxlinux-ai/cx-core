#!/usr/bin/env python3
"""
Cortex Watch Service - Background terminal monitoring daemon.

This service runs in the background and monitors all terminal activity,
logging commands for Cortex to use during manual intervention.

Features:
- Runs as a systemd user service
- Auto-starts on login
- Auto-restarts on crash
- Assigns unique IDs to each terminal
- Excludes Cortex's own terminal from logging
"""

import datetime
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


class CortexWatchDaemon:
    """Background daemon that monitors terminal activity."""

    def __init__(self):
        self.running = False
        self.cortex_dir = Path.home() / ".cortex"
        self.watch_log = self.cortex_dir / "terminal_watch.log"
        self.terminals_dir = self.cortex_dir / "terminals"
        self.pid_file = self.cortex_dir / "watch_service.pid"
        self.state_file = self.cortex_dir / "watch_state.json"

        # Terminal tracking
        self.terminals: dict[str, dict[str, Any]] = {}
        self.terminal_counter = 0

        # Track commands seen from watch_hook to avoid duplicates with bash_history
        self._watch_hook_commands: set[str] = set()
        self._recent_commands: list[str] = []  # Last 100 commands for dedup

        # Ensure directories exist
        self.cortex_dir.mkdir(parents=True, exist_ok=True)
        self.terminals_dir.mkdir(parents=True, exist_ok=True)

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGHUP, self._handle_reload)

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        self.log(f"Received signal {signum}, shutting down...")
        self.running = False

    def _handle_reload(self, signum, frame):
        """Handle reload signal (SIGHUP)."""
        self.log("Received SIGHUP, reloading configuration...")
        self._load_state()

    def log(self, message: str):
        """Log a message to the service log."""
        log_file = self.cortex_dir / "watch_service.log"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a") as f:
            f.write(f"[{timestamp}] {message}\n")

    def _load_state(self):
        """Load saved state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    state = json.load(f)
                    self.terminal_counter = state.get("terminal_counter", 0)
                    self.terminals = state.get("terminals", {})
            except Exception as e:
                self.log(f"Error loading state: {e}")

    def _save_state(self):
        """Save current state to file."""
        try:
            state = {
                "terminal_counter": self.terminal_counter,
                "terminals": self.terminals,
                "last_update": datetime.datetime.now().isoformat(),
            }
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.log(f"Error saving state: {e}")

    def _get_terminal_id(self, pts: str) -> str:
        """Generate or retrieve a unique terminal ID."""
        if pts in self.terminals:
            return self.terminals[pts]["id"]

        self.terminal_counter += 1
        terminal_id = f"term_{self.terminal_counter:04d}"

        self.terminals[pts] = {
            "id": terminal_id,
            "pts": pts,
            "created": datetime.datetime.now().isoformat(),
            "is_cortex": False,
            "command_count": 0,
        }

        self._save_state()
        return terminal_id

    def _is_cortex_terminal(self, pid: int) -> bool:
        """Check if a process is a Cortex terminal."""
        try:
            # Check environment variables
            environ_file = Path(f"/proc/{pid}/environ")
            if environ_file.exists():
                environ = environ_file.read_bytes()
                if b"CORTEX_TERMINAL=1" in environ:
                    return True

            # Check command line
            cmdline_file = Path(f"/proc/{pid}/cmdline")
            if cmdline_file.exists():
                cmdline = cmdline_file.read_bytes().decode("utf-8", errors="ignore")
                if "cortex" in cmdline.lower():
                    return True
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            pass

        return False

    def _get_active_terminals(self) -> list[dict]:
        """Get list of active terminal processes."""
        terminals = []

        try:
            # Find all pts (pseudo-terminal) devices
            pts_dir = Path("/dev/pts")
            if pts_dir.exists():
                for pts_file in pts_dir.iterdir():
                    if pts_file.name.isdigit():
                        pts_path = str(pts_file)

                        # Find process using this pts
                        result = subprocess.run(
                            ["fuser", pts_path], capture_output=True, text=True, timeout=2
                        )

                        if result.stdout.strip():
                            pids = result.stdout.strip().split()
                            for pid_str in pids:
                                try:
                                    pid = int(pid_str)
                                    is_cortex = self._is_cortex_terminal(pid)
                                    terminal_id = self._get_terminal_id(pts_path)

                                    # Update cortex flag
                                    if pts_path in self.terminals:
                                        self.terminals[pts_path]["is_cortex"] = is_cortex

                                    terminals.append(
                                        {
                                            "pts": pts_path,
                                            "pid": pid,
                                            "id": terminal_id,
                                            "is_cortex": is_cortex,
                                        }
                                    )
                                except ValueError:
                                    continue

        except Exception as e:
            self.log(f"Error getting terminals: {e}")

        return terminals

    def _monitor_bash_history(self):
        """Monitor bash history for new commands using inotify if available."""
        history_files = [
            Path.home() / ".bash_history",
            Path.home() / ".zsh_history",
        ]

        positions: dict[str, int] = {}
        last_commands: dict[str, str] = {}  # Track last command per file to avoid duplicates

        # Initialize positions to current end of file
        for hist_file in history_files:
            if hist_file.exists():
                positions[str(hist_file)] = hist_file.stat().st_size
                # Read last line to track for dedup
                try:
                    content = hist_file.read_text()
                    lines = content.strip().split("\n")
                    if lines:
                        last_commands[str(hist_file)] = lines[-1].strip()
                except Exception:
                    pass

        # Try to use inotify for more efficient monitoring
        try:
            import ctypes
            import select
            import struct

            # Check if inotify is available
            libc = ctypes.CDLL("libc.so.6")
            inotify_init = libc.inotify_init
            inotify_add_watch = libc.inotify_add_watch

            IN_MODIFY = 0x00000002
            IN_CLOSE_WRITE = 0x00000008

            fd = inotify_init()
            if fd < 0:
                raise OSError("Failed to initialize inotify")

            watches = {}
            for hist_file in history_files:
                if hist_file.exists():
                    wd = inotify_add_watch(fd, str(hist_file).encode(), IN_MODIFY | IN_CLOSE_WRITE)
                    if wd >= 0:
                        watches[wd] = hist_file

            self.log(f"Using inotify to monitor {len(watches)} history files")

            while self.running:
                # Wait for inotify event with timeout
                r, _, _ = select.select([fd], [], [], 1.0)
                if not r:
                    continue

                data = os.read(fd, 4096)
                # Process inotify events
                for hist_file in history_files:
                    key = str(hist_file)
                    if not hist_file.exists():
                        continue

                    try:
                        current_size = hist_file.stat().st_size

                        if key not in positions:
                            positions[key] = current_size
                            continue

                        if current_size < positions[key]:
                            positions[key] = current_size
                            continue

                        if current_size > positions[key]:
                            with open(hist_file) as f:
                                f.seek(positions[key])
                                new_content = f.read()

                                for line in new_content.split("\n"):
                                    line = line.strip()
                                    # Skip empty, short, or duplicate commands
                                    if line and len(line) > 1:
                                        if last_commands.get(key) != line:
                                            self._log_command(line, "history")
                                            last_commands[key] = line

                            positions[key] = current_size
                    except Exception as e:
                        self.log(f"Error reading {hist_file}: {e}")

            os.close(fd)
            return

        except Exception as e:
            self.log(f"Inotify not available, using polling: {e}")

        # Fallback to polling
        while self.running:
            for hist_file in history_files:
                if not hist_file.exists():
                    continue

                key = str(hist_file)
                try:
                    current_size = hist_file.stat().st_size

                    if key not in positions:
                        positions[key] = current_size
                        continue

                    if current_size < positions[key]:
                        # File was truncated
                        positions[key] = current_size
                        continue

                    if current_size > positions[key]:
                        with open(hist_file) as f:
                            f.seek(positions[key])
                            new_content = f.read()

                            for line in new_content.split("\n"):
                                line = line.strip()
                                if line and len(line) > 1:
                                    if last_commands.get(key) != line:
                                        self._log_command(line, "history")
                                        last_commands[key] = line

                        positions[key] = current_size

                except Exception as e:
                    self.log(f"Error reading {hist_file}: {e}")

            time.sleep(0.3)

    def _monitor_watch_hook(self):
        """Monitor the watch hook log file and sync to terminal_commands.json."""
        position = 0

        while self.running:
            try:
                if not self.watch_log.exists():
                    time.sleep(0.5)
                    continue

                current_size = self.watch_log.stat().st_size

                if current_size < position:
                    position = 0

                if current_size > position:
                    with open(self.watch_log) as f:
                        f.seek(position)
                        new_content = f.read()

                        for line in new_content.split("\n"):
                            line = line.strip()
                            if not line or len(line) < 2:
                                continue

                            # Parse format: TTY|COMMAND (new format from updated hook)
                            # Skip lines that don't have the TTY| prefix or have "shared|"
                            if "|" not in line:
                                continue

                            parts = line.split("|", 1)
                            terminal_id = parts[0]

                            # Skip "shared" entries (those come from bash_history monitor)
                            if terminal_id == "shared":
                                continue

                            # Must have valid TTY format (pts_X, tty_X, etc.)
                            if not terminal_id or terminal_id == "unknown":
                                continue

                            command = parts[1] if len(parts) > 1 else ""
                            if not command:
                                continue

                            # Skip duplicates
                            if self._is_duplicate(command):
                                continue

                            # Mark this command as seen from watch_hook
                            self._watch_hook_commands.add(command)

                            # Log to terminal_commands.json only
                            self._log_to_json(command, "watch_hook", terminal_id)

                    position = current_size

            except Exception as e:
                self.log(f"Error monitoring watch hook: {e}")

            time.sleep(0.2)

    def _log_to_json(self, command: str, source: str, terminal_id: str):
        """Log a command only to terminal_commands.json."""
        try:
            detailed_log = self.cortex_dir / "terminal_commands.json"
            entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "command": command,
                "source": source,
                "terminal_id": terminal_id,
            }

            with open(detailed_log, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            self.log(f"Error logging to JSON: {e}")

    def _is_duplicate(self, command: str) -> bool:
        """Check if command was recently logged to avoid duplicates."""
        if command in self._recent_commands:
            return True

        # Keep last 100 commands
        self._recent_commands.append(command)
        if len(self._recent_commands) > 100:
            self._recent_commands.pop(0)

        return False

    def _log_command(self, command: str, source: str = "unknown", terminal_id: str | None = None):
        """Log a command from bash_history (watch_hook uses _log_to_json directly)."""
        # Skip cortex commands
        if command.lower().startswith("cortex "):
            return
        if "watch_hook" in command:
            return
        if command.startswith("source ") and ".cortex" in command:
            return

        # Skip if this command was already logged by watch_hook
        if command in self._watch_hook_commands:
            self._watch_hook_commands.discard(command)  # Clear it for next time
            return

        # Skip duplicates
        if self._is_duplicate(command):
            return

        # For bash_history source, we can't know which terminal - use "shared"
        if terminal_id is None:
            terminal_id = "shared"

        try:
            # Write to watch_log with format TTY|COMMAND
            with open(self.watch_log, "a") as f:
                f.write(f"{terminal_id}|{command}\n")

            # Log to JSON
            self._log_to_json(command, source, terminal_id)

        except Exception as e:
            self.log(f"Error logging command: {e}")

    def _cleanup_stale_terminals(self):
        """Remove stale terminal entries."""
        while self.running:
            try:
                active_pts = set()
                pts_dir = Path("/dev/pts")
                if pts_dir.exists():
                    for pts_file in pts_dir.iterdir():
                        if pts_file.name.isdigit():
                            active_pts.add(str(pts_file))

                # Remove stale entries
                stale = [pts for pts in self.terminals if pts not in active_pts]
                for pts in stale:
                    del self.terminals[pts]

                if stale:
                    self._save_state()

            except Exception as e:
                self.log(f"Error cleaning up terminals: {e}")

            time.sleep(30)  # Check every 30 seconds

    def start(self):
        """Start the watch daemon."""
        # Check if already running
        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text().strip())
                os.kill(pid, 0)  # Check if process exists
                self.log(f"Daemon already running with PID {pid}")
                return False
            except (ProcessLookupError, ValueError):
                # Stale PID file
                self.pid_file.unlink()

        # Write PID file
        self.pid_file.write_text(str(os.getpid()))

        self.running = True
        self._load_state()

        self.log("Cortex Watch Service starting...")

        # Start monitor threads
        threads = [
            threading.Thread(target=self._monitor_bash_history, daemon=True),
            threading.Thread(target=self._monitor_watch_hook, daemon=True),
            threading.Thread(target=self._cleanup_stale_terminals, daemon=True),
        ]

        for t in threads:
            t.start()

        self.log(f"Cortex Watch Service started (PID: {os.getpid()})")

        # Main loop - just keep alive and handle signals
        try:
            while self.running:
                time.sleep(1)
        finally:
            self._shutdown()

        return True

    def _shutdown(self):
        """Clean shutdown."""
        self.log("Shutting down...")
        self._save_state()

        if self.pid_file.exists():
            self.pid_file.unlink()

        self.log("Cortex Watch Service stopped")

    def stop(self):
        """Stop the running daemon."""
        if not self.pid_file.exists():
            return False, "Service not running"

        try:
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)

            # Wait for process to exit
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.5)
                except ProcessLookupError:
                    break

            return True, f"Service stopped (PID: {pid})"

        except ProcessLookupError:
            self.pid_file.unlink()
            return True, "Service was not running"
        except Exception as e:
            return False, f"Error stopping service: {e}"

    def status(self) -> dict:
        """Get service status."""
        status = {
            "running": False,
            "pid": None,
            "terminals": 0,
            "commands_logged": 0,
        }

        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text().strip())
                os.kill(pid, 0)
                status["running"] = True
                status["pid"] = pid
            except (ProcessLookupError, ValueError):
                pass

        if self.watch_log.exists():
            try:
                content = self.watch_log.read_text()
                status["commands_logged"] = len([l for l in content.split("\n") if l.strip()])
            except Exception:
                pass

        self._load_state()
        status["terminals"] = len(self.terminals)

        return status


def get_systemd_service_content() -> str:
    """Generate systemd service file content."""
    python_path = sys.executable
    service_script = Path(__file__).resolve()

    return f"""[Unit]
Description=Cortex Terminal Watch Service
Documentation=https://github.com/cortexlinux/cortex
After=default.target

[Service]
Type=simple
ExecStart={python_path} {service_script} --daemon
ExecStop={python_path} {service_script} --stop
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
"""


def install_service() -> tuple[bool, str]:
    """Install the systemd user service."""
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_file = service_dir / "cortex-watch.service"

    try:
        # Create directory
        service_dir.mkdir(parents=True, exist_ok=True)

        # Write service file
        service_file.write_text(get_systemd_service_content())

        # Reload systemd
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)

        # Enable and start service
        subprocess.run(["systemctl", "--user", "enable", "cortex-watch.service"], check=True)
        subprocess.run(["systemctl", "--user", "start", "cortex-watch.service"], check=True)

        # Enable lingering so service runs even when not logged in
        subprocess.run(["loginctl", "enable-linger", os.getenv("USER", "")], capture_output=True)

        return (
            True,
            f"""✓ Cortex Watch Service installed and started!

Service file: {service_file}

The service will:
  • Start automatically on login
  • Restart automatically if it crashes
  • Monitor all terminal activity

Commands:
  systemctl --user status cortex-watch   # Check status
  systemctl --user restart cortex-watch  # Restart
  systemctl --user stop cortex-watch     # Stop
  journalctl --user -u cortex-watch      # View logs
""",
        )
    except subprocess.CalledProcessError as e:
        return False, f"Failed to install service: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def uninstall_service() -> tuple[bool, str]:
    """Uninstall the systemd user service."""
    service_file = Path.home() / ".config" / "systemd" / "user" / "cortex-watch.service"

    try:
        # Stop and disable service
        subprocess.run(["systemctl", "--user", "stop", "cortex-watch.service"], capture_output=True)
        subprocess.run(
            ["systemctl", "--user", "disable", "cortex-watch.service"], capture_output=True
        )

        # Remove service file
        if service_file.exists():
            service_file.unlink()

        # Reload systemd
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)

        return True, "✓ Cortex Watch Service uninstalled"
    except Exception as e:
        return False, f"Error: {e}"


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Cortex Watch Service")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--stop", action="store_true", help="Stop the daemon")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--install", action="store_true", help="Install systemd service")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall systemd service")

    args = parser.parse_args()

    daemon = CortexWatchDaemon()

    if args.install:
        success, msg = install_service()
        print(msg)
        sys.exit(0 if success else 1)

    if args.uninstall:
        success, msg = uninstall_service()
        print(msg)
        sys.exit(0 if success else 1)

    if args.status:
        status = daemon.status()
        print(f"Running: {status['running']}")
        if status["pid"]:
            print(f"PID: {status['pid']}")
        print(f"Terminals tracked: {status['terminals']}")
        print(f"Commands logged: {status['commands_logged']}")
        sys.exit(0)

    if args.stop:
        success, msg = daemon.stop()
        print(msg)
        sys.exit(0 if success else 1)

    if args.daemon:
        daemon.start()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
