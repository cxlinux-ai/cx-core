"""
Cortex Dashboard - Enhanced Terminal UI with Progress Tracking
Supports real-time monitoring, system metrics, process tracking, and installation management

Design Principles:
- Explicit user intent required for all system inspection
- No automatic data collection on startup
- Thread-safe state management
- Platform-agnostic implementations
"""

import atexit
import contextlib
import io
import json
import logging
import os
import platform
import re
import sys
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

try:
    from rich.box import ROUNDED
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
except ImportError:
    print("Error: The 'rich' library is required but not installed.", file=sys.stderr)
    print("Please install it with: pip install rich>=13.0.0", file=sys.stderr)
    sys.exit(1)

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    # Create a mock module for testing compatibility
    # Set stub attributes to None to allow unittest.mock.patch to override them
    from types import ModuleType

    psutil = ModuleType("psutil")  # type: ignore
    # Set to None so patch can create the attribute with proper mock
    psutil.cpu_percent = None  # type: ignore
    psutil.virtual_memory = None  # type: ignore
    psutil.process_iter = None  # type: ignore

# Optional GPU support - graceful degradation if unavailable
try:
    import pynvml

    GPU_LIBRARY_AVAILABLE = True
except ImportError:
    GPU_LIBRARY_AVAILABLE = False
    pynvml = None

# HTTP requests for Ollama API
try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Cross-platform keyboard input
if sys.platform == "win32":
    import msvcrt
else:
    import select
    import termios
    import tty

# Suppress verbose logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS - Centralized configuration values
# =============================================================================

# UI Display Constants
BAR_WIDTH = 20  # Characters for progress/resource bars
MAX_PROCESS_NAME_LENGTH = 20  # Max chars for process name display
MAX_PROCESSES_DISPLAYED = 8  # Max processes shown in UI panel
MAX_PROCESSES_TRACKED = 15  # Max processes kept in memory
MAX_CMDLINE_LENGTH = 60  # Max chars for command line display (kept for internal use)
MAX_HISTORY_COMMANDS = 10  # Max shell history commands to load
MAX_HISTORY_DISPLAYED = 5  # Max history commands shown in UI
MAX_COMMAND_DISPLAY_LENGTH = 50  # Max chars per command in display
MAX_INPUT_LENGTH = 50  # Max chars for package name input
MAX_LIBRARIES_DISPLAYED = 5  # Max libraries shown in progress panel

# Resource Threshold Constants (percentages)
CRITICAL_THRESHOLD = 75  # Red bar above this percentage
WARNING_THRESHOLD = 50  # Yellow bar above this percentage
DISK_WARNING_THRESHOLD = 90  # Disk space warning threshold
MEMORY_WARNING_THRESHOLD = 95  # Memory warning threshold
CPU_WARNING_THRESHOLD = 90  # CPU load warning threshold

# Error/Status Messages
CHECK_UNAVAILABLE_MSG = "Unable to check"  # Fallback message for failed checks

# Timing Constants (seconds)
CPU_SAMPLE_INTERVAL = 0.1  # psutil CPU sampling interval
MONITOR_LOOP_INTERVAL = 1.0  # Background metrics collection interval
UI_INPUT_CHECK_INTERVAL = 0.1  # Keyboard input check interval
UI_REFRESH_RATE = 2  # Rich Live refresh rate (per second)
STARTUP_DELAY = 1  # Delay before starting dashboard UI
BENCH_STEP_DELAY = 0.8  # Delay between benchmark steps
DOCTOR_CHECK_DELAY = 0.5  # Delay between doctor checks
INSTALL_STEP_DELAY = 0.6  # Delay between installation steps (simulation)
INSTALL_TOTAL_STEPS = 5  # Number of simulated installation steps

# Unit Conversion Constants
BYTES_PER_GB = 1024**3  # Bytes in a gigabyte

# Simulation Mode - Set to False when real CLI integration is ready
# TODO: Replace simulated installation with actual CLI calls
# Simulation Mode - Set to False when real CLI integration is ready
SIMULATION_MODE = False

# Ollama API Configuration
DEFAULT_OLLAMA_API_BASE = "http://localhost:11434"
OLLAMA_API_TIMEOUT = 2.0  # seconds
MAX_MODELS_DISPLAYED = 5  # Max models shown in UI

# UI Panel Title Constants
LOADED_MODELS_PANEL_TITLE = "🤖 Loaded Models"

# Regex Patterns for Text Cleaning
COLOR_TAG_PATTERN = r"\[[^\]]*\]"  # Pattern to match and remove [color] tags


def _get_ollama_api_base() -> str:
    """Determine Ollama API base URL from env or config file"""
    env_value = os.environ.get("OLLAMA_API_BASE")
    if env_value:
        return env_value.rstrip("/")

    try:
        prefs_path = Path.home() / ".cortex" / "preferences.yaml"
        if prefs_path.exists():
            with open(prefs_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            value = data.get("ollama_api_base")
            if isinstance(value, str) and value.strip():
                return value.strip().rstrip("/")
    except Exception as e:
        logger.debug(f"Failed to read Ollama base from config: {type(e).__name__}: {e}")

    return DEFAULT_OLLAMA_API_BASE


OLLAMA_API_BASE = _get_ollama_api_base()


# =============================================================================
# ENUMS
# =============================================================================


class DashboardTab(Enum):
    """Available dashboard tabs"""

    HOME = "home"
    PROGRESS = "progress"


class InstallationState(Enum):
    """Installation states"""

    IDLE = "idle"
    WAITING_INPUT = "waiting_input"
    WAITING_CONFIRMATION = "waiting_confirmation"
    WAITING_PASSWORD = "waiting_password"
    PROCESSING = "processing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionType(Enum):
    """Action types for dashboard"""

    NONE = "none"
    INSTALL = "install"
    BENCH = "bench"
    DOCTOR = "doctor"
    CANCEL = "cancel"


# =============================================================================
# ACTION MAP - Centralized key bindings and action configuration
# =============================================================================

# Single source of truth for all dashboard actions
# Format: key -> (label, action_type, handler_method_name)
ACTION_MAP: dict[str, tuple[str, ActionType, str]] = {
    "1": ("Install", ActionType.INSTALL, "_start_installation"),
    "2": ("Bench", ActionType.BENCH, "_start_bench"),
    "3": ("Doctor", ActionType.DOCTOR, "_start_doctor"),
    "4": ("Cancel", ActionType.CANCEL, "_cancel_operation"),
}


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class SystemMetrics:
    """Container for system metrics"""

    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    gpu_percent: float | None = None
    gpu_memory_percent: float | None = None
    timestamp: datetime | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class InstallationProgress:
    """Tracks installation progress"""

    state: InstallationState = InstallationState.IDLE
    package: str = ""
    current_step: int = 0
    total_steps: int = 0
    current_library: str = ""
    libraries: list[str] = field(default_factory=list)
    error_message: str = ""
    success_message: str = ""
    start_time: float | None = None
    elapsed_time: float = 0.0
    estimated_remaining: float = 0.0

    def update_elapsed(self) -> None:
        """Update elapsed time and estimate remaining time"""
        if self.start_time:
            self.elapsed_time = time.time() - self.start_time
            # Compute per-step time and estimate remaining time
            if self.current_step > 0 and self.total_steps > 0:
                per_step_time = self.elapsed_time / max(1, self.current_step)
                self.estimated_remaining = per_step_time * max(
                    0, self.total_steps - self.current_step
                )
            else:
                self.estimated_remaining = 0.0


# =============================================================================
# PLATFORM UTILITIES
# =============================================================================


def get_root_disk_path() -> str:
    """Get the root disk path in a platform-agnostic way."""
    if platform.system() == "Windows":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


# =============================================================================
# SYSTEM MONITOR
# =============================================================================


class SystemMonitor:
    """
    Monitors CPU, RAM, and GPU metrics in a thread-safe manner.

    This class collects system metrics using psutil and, if available, pynvml for GPU monitoring.
    Metrics are updated synchronously via `update_metrics()` and accessed via `get_metrics()`.
    Thread safety is ensured using a threading.Lock to protect access to the current metrics.

    IMPORTANT: GPU initialization is deferred until explicitly enabled to respect user privacy.
    No system inspection occurs until the user explicitly requests it.

    Threading Model:
        - All access to metrics is protected by a lock.
        - Safe to call `update_metrics()` and `get_metrics()` from multiple threads.

    Example:
        monitor = SystemMonitor()
        monitor.enable_monitoring()  # User explicitly enables monitoring
        monitor.update_metrics()
        metrics = monitor.get_metrics()
        print(f"CPU: {metrics.cpu_percent}%")
    """

    def __init__(self):
        self.current_metrics = SystemMetrics(
            cpu_percent=0.0, ram_percent=0.0, ram_used_gb=0.0, ram_total_gb=0.0
        )
        self.lock = threading.Lock()
        self.gpu_initialized = False
        self._monitoring_enabled = False
        self._cpu_initialized = False
        # GPU initialization is deferred - not called in constructor

    def enable_monitoring(self) -> None:
        """Enable system monitoring. Must be called before collecting metrics."""
        self._monitoring_enabled = True

    def enable_gpu(self) -> None:
        """
        Initialize GPU monitoring if available.
        Called only when user explicitly requests GPU-related operations.
        """
        if not GPU_LIBRARY_AVAILABLE or self.gpu_initialized:
            return
        try:
            pynvml.nvmlInit()
            self.gpu_initialized = True
        except Exception as e:
            logger.debug(f"GPU init failed: {e}")

    def shutdown_gpu(self) -> None:
        """Cleanup GPU monitoring resources."""
        if self.gpu_initialized and GPU_LIBRARY_AVAILABLE:
            try:
                pynvml.nvmlShutdown()
                self.gpu_initialized = False
            except Exception as e:
                logger.debug(f"GPU shutdown error: {e}")

    def get_metrics(self) -> SystemMetrics:
        """Get current metrics (thread-safe)"""
        with self.lock:
            return self.current_metrics

    def update_metrics(self) -> None:
        """Update all metrics. Only collects data if monitoring is enabled."""
        if not self._monitoring_enabled:
            return
        if not PSUTIL_AVAILABLE:
            if not callable(getattr(psutil, "cpu_percent", None)) or not callable(
                getattr(psutil, "virtual_memory", None)
            ):
                return

        try:
            # Use non-blocking CPU calls after first initialization
            if not self._cpu_initialized:
                psutil.cpu_percent(interval=CPU_SAMPLE_INTERVAL)
                self._cpu_initialized = True
                # On first call, use a blocking call to get non-zero value
                cpu_percent = psutil.cpu_percent(interval=CPU_SAMPLE_INTERVAL)
            else:
                cpu_percent = psutil.cpu_percent(interval=None)

            # Handle case where cpu_percent returns None
            if cpu_percent is None:
                cpu_percent = 0.0

            vm = psutil.virtual_memory()

            gpu_percent = None
            gpu_memory_percent = None

            if self.gpu_initialized:
                try:
                    device_count = pynvml.nvmlDeviceGetCount()
                    if device_count > 0:
                        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                        gpu_percent = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
                        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                        gpu_memory_percent = (mem_info.used / mem_info.total) * 100
                except Exception as e:
                    logger.debug(f"GPU metrics error: {e}")

            metrics = SystemMetrics(
                cpu_percent=cpu_percent,
                ram_percent=vm.percent,
                ram_used_gb=vm.used / BYTES_PER_GB,
                ram_total_gb=vm.total / BYTES_PER_GB,
                gpu_percent=gpu_percent,
                gpu_memory_percent=gpu_memory_percent,
            )

            with self.lock:
                self.current_metrics = metrics
        except Exception as e:
            logger.error(f"Metrics error: {e}", exc_info=True)


# =============================================================================
# PROCESS LISTER
# =============================================================================


class ProcessLister:
    """
    Lists running processes related to AI/ML workloads.

    Filters processes based on keywords like 'python', 'ollama', 'pytorch', etc.
    Process information is cached and accessed in a thread-safe manner.

    IMPORTANT: Process enumeration is NOT automatic. Must be explicitly triggered
    by calling update_processes() after user consent.

    Privacy: Only PID and process name are collected. Command-line arguments
    are NOT stored or displayed to protect user privacy.

    Attributes:
        KEYWORDS: Set of keywords used to filter relevant processes.
        processes: Cached list of process information.
    """

    KEYWORDS = {
        "python",
        "node",
        "ollama",
        "llama",
        "bert",
        "gpt",
        "transformers",
        "inference",
        "pytorch",
        "tensorflow",
        "cortex",
        "cuda",
    }

    def __init__(self):
        self.processes: list[dict] = []
        self.lock = threading.Lock()
        self._enabled = False
        # No automatic process enumeration in constructor

    def enable(self) -> None:
        """Enable process listing. Must be called before collecting process data."""
        self._enabled = True

    def update_processes(self) -> None:
        """
        Update process list. Only runs if enabled.

        Privacy note: Only collects PID and process name.
        Command-line arguments are NOT collected.
        """
        if not self._enabled:
            return
        if not PSUTIL_AVAILABLE:
            return

        try:
            processes = []
            # Only request pid and name - NOT cmdline for privacy
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    name = proc.info.get("name", "").lower()
                    # Only filter by process name, not command line
                    if any(kw in name for kw in self.KEYWORDS):
                        processes.append(
                            {
                                "pid": proc.info.get("pid"),
                                "name": proc.info.get("name", "unknown"),
                                # cmdline intentionally NOT collected for privacy
                            }
                        )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            with self.lock:
                self.processes = processes[:MAX_PROCESSES_TRACKED]
        except Exception as e:
            logger.error(f"Process listing error: {e}")

    def get_processes(self) -> list[dict]:
        """Get current processes (thread-safe)"""
        with self.lock:
            return list(self.processes)


# =============================================================================
# MODEL LISTER (Ollama Integration)
# =============================================================================


class ModelLister:
    """
    Lists loaded LLM models from Ollama.

    Queries the local Ollama API to discover running models.
    This provides visibility into which AI models are currently loaded.

    IMPORTANT: Only queries Ollama when explicitly enabled by user.
    """

    def __init__(self):
        self.models: list[dict] = []
        self.lock = threading.Lock()
        self._enabled = False
        self.ollama_available = False
        # Cache for get_available_models with 5s TTL
        self._models_cache: list[dict] = []
        self._models_last_fetched: float = 0.0

    def enable(self) -> None:
        """Enable model listing."""
        self._enabled = True

    def check_ollama(self) -> bool:
        """Check if Ollama is running."""
        if not REQUESTS_AVAILABLE:
            return False
        try:
            response = requests.get(f"{OLLAMA_API_BASE}/api/tags", timeout=OLLAMA_API_TIMEOUT)
            self.ollama_available = response.status_code == 200
            return self.ollama_available
        except Exception as e:
            logger.debug(f"Ollama API check failed: {type(e).__name__}: {e}", exc_info=True)
            self.ollama_available = False
            return False

    def update_models(self) -> None:
        """Update list of loaded models from Ollama."""
        if not self._enabled or not REQUESTS_AVAILABLE:
            return

        try:
            # Check running models via Ollama API
            response = requests.get(f"{OLLAMA_API_BASE}/api/ps", timeout=OLLAMA_API_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                models = []
                for model in data.get("models", []):
                    models.append(
                        {
                            "name": model.get("name", "unknown"),
                            "size": model.get("size", 0),
                            "digest": model.get("digest", "")[:8],
                        }
                    )
                with self.lock:
                    self.models = models[:MAX_MODELS_DISPLAYED]
                    self.ollama_available = True
            else:
                with self.lock:
                    self.models = []
        except Exception as e:
            logger.debug(f"Model update failed: {type(e).__name__}: {e}", exc_info=True)
            with self.lock:
                self.models = []
                self.ollama_available = False

        # Also update available models cache with TTL check
        self._update_available_models_cache()

    def _update_available_models_cache(self) -> None:
        """Update available models cache (respects 5s TTL)."""
        if not self._enabled or not REQUESTS_AVAILABLE:
            return

        # Check TTL
        current_time = time.time()
        with self.lock:
            if current_time - self._models_last_fetched < 5.0:
                return  # Still within TTL

        try:
            # Fetch available (downloaded) models
            response = requests.get(f"{OLLAMA_API_BASE}/api/tags", timeout=OLLAMA_API_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                models = []
                for model in data.get("models", []):
                    size_gb = round(model.get("size", 0) / BYTES_PER_GB, 1)
                    models.append(
                        {
                            "name": model.get("name", "unknown"),
                            "size_gb": size_gb,
                        }
                    )
                with self.lock:
                    self._models_cache = models[:MAX_MODELS_DISPLAYED]
                    self._models_last_fetched = current_time
            else:
                with self.lock:
                    self._models_cache = []
                    self._models_last_fetched = current_time
        except Exception as e:
            logger.debug(
                f"Available models cache update failed: {type(e).__name__}: {e}", exc_info=True
            )
            with self.lock:
                self._models_cache = []
                self._models_last_fetched = current_time

    def get_models(self) -> list[dict]:
        """Get current models (thread-safe)"""
        with self.lock:
            return list(self.models)

    def get_available_models(self) -> list[dict]:
        """Get list of available (downloaded) models from Ollama (cached, no network calls)."""
        if not REQUESTS_AVAILABLE:
            return []

        # Return cached data immediately - NO network calls
        # Cache is populated by background update loop via _update_available_models_cache()
        with self.lock:
            if not self._enabled:
                return []
            # Return cached models (may be empty if never fetched or fetch failed)
            return list(self._models_cache)


# =============================================================================
# COMMAND HISTORY
# =============================================================================


class CommandHistory:
    """
    Loads and tracks shell command history.

    Reads command history from bash and zsh history files and maintains
    a rolling buffer of recent commands.

    IMPORTANT: History is NOT loaded automatically. Must be explicitly triggered
    by calling load_history() after user consent.

    Args:
        max_size: Maximum number of commands to keep in history (default: 10)
    """

    def __init__(self, max_size: int = MAX_HISTORY_COMMANDS):
        self.max_size = max_size
        self.history: deque = deque(maxlen=max_size)
        self.lock = threading.Lock()
        self._loaded = False
        # No automatic history loading in constructor

    def load_history(self) -> None:
        """
        Load from shell history files.
        Only called when user explicitly requests history display.
        """
        if self._loaded:
            return

        for history_file in [
            os.path.expanduser("~/.bash_history"),
            os.path.expanduser("~/.zsh_history"),
        ]:
            if os.path.exists(history_file):
                try:
                    new_entries: list[str] = []
                    with open(history_file, encoding="utf-8", errors="ignore") as f:
                        for line in f.readlines()[-self.max_size :]:
                            cmd = line.strip()
                            if cmd and not cmd.startswith(":"):
                                new_entries.append(cmd)

                    if new_entries:
                        with self.lock:
                            for cmd in new_entries:
                                self.history.append(cmd)
                            self._loaded = True
                            break
                except Exception as e:
                    logger.warning(f"Could not read history file {history_file}: {e}")

    def add_command(self, command: str) -> None:
        """Add command to history"""
        if command.strip():
            with self.lock:
                self.history.append(command)

    def get_history(self) -> list[str]:
        """Get history"""
        with self.lock:
            return list(self.history)


# =============================================================================
# UI RENDERER
# =============================================================================


class UIRenderer:
    """Renders the dashboard UI with multi-tab support"""

    def __init__(
        self,
        monitor: SystemMonitor,
        lister: ProcessLister,
        history: CommandHistory,
        model_lister: "ModelLister | None" = None,
    ):
        self.console = Console()
        self.monitor = monitor
        self.lister = lister
        self.history = history
        self.model_lister = model_lister
        self.running = False
        self.should_quit = False
        self.current_tab = DashboardTab.HOME

        # Thread synchronization
        self.state_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.audit_lock = threading.Lock()  # Protects audit file read-modify-write

        # Installation state
        self.installation_progress = InstallationProgress()
        self.input_text = ""
        self.input_active = False
        self._pending_commands: list[str] = []  # Commands pending confirmation
        self._cached_sudo_password = ""  # Cache sudo password for entire session

        # Current action state (for display)
        self.current_action = ActionType.NONE
        self.last_pressed_key = ""
        self.status_message = ""

        # Doctor results
        self.doctor_results: list[tuple] = []
        self.doctor_running = False

        # Bench results
        self.bench_status = "Ready to run benchmark"
        self.bench_running = False

        # Track if user has enabled monitoring
        self._user_started_monitoring = False

    def _create_bar(self, label: str, percent: float | None, width: int = BAR_WIDTH) -> str:
        """Create a resource bar"""
        if percent is None:
            return f"{label}: N/A"

        filled = int((percent / 100) * width)
        bar = "[green]" + "█" * filled + "[/green]" + "░" * (width - filled)
        if percent > CRITICAL_THRESHOLD:
            bar = "[red]" + "█" * filled + "[/red]" + "░" * (width - filled)
        elif percent > WARNING_THRESHOLD:
            bar = "[yellow]" + "█" * filled + "[/yellow]" + "░" * (width - filled)

        return f"{label}: {bar} {percent:.1f}%"

    def _render_header(self) -> Panel:
        """Render header with tab indicator"""
        title = Text("🚀 CORTEX DASHBOARD", style="bold cyan")
        timestamp = Text(datetime.now().strftime("%H:%M:%S"), style="dim")

        # Tab indicator
        tab_text = ""
        for tab in DashboardTab:
            if tab == self.current_tab:
                tab_text += f"[bold cyan]▸ {tab.value.upper()} ◂[/bold cyan] "
            else:
                tab_text += f"[dim]{tab.value}[/dim] "

        content = f"{title}  {timestamp}\n[dim]{tab_text}[/dim]"
        return Panel(content, style="blue", box=ROUNDED)

    def _render_resources(self) -> Panel:
        """Render resources section"""
        if not self._user_started_monitoring:
            content = "[dim]Press 2 (Bench) or 3 (Doctor) to start monitoring[/dim]"
            return Panel(content, title="📊 System Resources", padding=(1, 1), box=ROUNDED)

        metrics = self.monitor.get_metrics()
        lines = [
            self._create_bar("CPU", metrics.cpu_percent),
            self._create_bar("RAM", metrics.ram_percent),
            f"     Used: {metrics.ram_used_gb:.1f}GB / {metrics.ram_total_gb:.1f}GB",
        ]

        if metrics.gpu_percent is not None:
            lines.append(self._create_bar("GPU", metrics.gpu_percent))
        if metrics.gpu_memory_percent is not None:
            lines.append(self._create_bar("VRAM", metrics.gpu_memory_percent))

        return Panel("\n".join(lines), title="📊 System Resources", padding=(1, 1), box=ROUNDED)

    def _render_processes(self) -> Panel:
        """Render processes section"""
        if not self._user_started_monitoring:
            content = "[dim]Monitoring not started[/dim]"
            return Panel(content, title="⚙️ Running Processes", padding=(1, 1), box=ROUNDED)

        processes = self.lister.get_processes()
        if not processes:
            content = "[dim]No AI/ML processes detected[/dim]"
        else:
            lines = [
                f"  {p['pid']} {p['name'][:MAX_PROCESS_NAME_LENGTH]}"
                for p in processes[:MAX_PROCESSES_DISPLAYED]
            ]
            content = "\n".join(lines)

        return Panel(content, title="⚙️ Running Processes", padding=(1, 1), box=ROUNDED)

    def _render_models(self) -> Panel:
        """Render loaded models section (Ollama)"""
        if not self._user_started_monitoring or self.model_lister is None:
            content = "[dim]Press 2 (Bench) to check Ollama models[/dim]"
            return Panel(content, title=LOADED_MODELS_PANEL_TITLE, padding=(1, 1), box=ROUNDED)

        if not self.model_lister.ollama_available:
            content = "[dim]Ollama not running[/dim]\n[dim]Start with: ollama serve[/dim]"
            return Panel(content, title=LOADED_MODELS_PANEL_TITLE, padding=(1, 1), box=ROUNDED)

        # Show running models (in memory)
        running_models = self.model_lister.get_models()
        available_models = self.model_lister.get_available_models()

        lines = []
        if running_models:
            lines.append("[bold green]Running:[/bold green]")
            for m in running_models:
                lines.append(f"  [green]●[/green] {m['name']}")
        else:
            lines.append("[dim]No models loaded[/dim]")

        if available_models and not running_models:
            lines.append("\n[bold]Available:[/bold]")
            for m in available_models[:3]:
                lines.append(f"  [dim]○[/dim] {m['name']} ({m['size_gb']}GB)")

        content = "\n".join(lines) if lines else "[dim]No models found[/dim]"
        return Panel(content, title=LOADED_MODELS_PANEL_TITLE, padding=(1, 1), box=ROUNDED)

    def _render_history(self) -> Panel:
        """Render history section"""
        cmds = self.history.get_history()
        if not cmds:
            content = "[dim]No history loaded[/dim]"
        else:
            lines = [
                f"  {c[:MAX_COMMAND_DISPLAY_LENGTH]}"
                for c in reversed(list(cmds)[-MAX_HISTORY_DISPLAYED:])
            ]
            content = "\n".join(lines)

        return Panel(content, title="📝 Recent Commands", padding=(1, 1), box=ROUNDED)

    def _render_actions(self) -> Panel:
        """Render action menu with pressed indicator"""
        # Build action items from centralized ACTION_MAP
        actions = []
        for key, (name, _, _) in ACTION_MAP.items():
            actions.append(f"[cyan]{key}[/cyan] {name}")

        content = "  ".join(actions)

        # Add pressed indicator if a key was recently pressed
        if self.last_pressed_key:
            content += (
                f"  [dim]|[/dim]  [bold yellow]► {self.last_pressed_key} pressed[/bold yellow]"
            )

        return Panel(content, title="⚡ Actions", padding=(1, 1), box=ROUNDED)

    def _render_home_tab(self) -> Group:
        """Render home tab"""
        return Group(
            self._render_header(),
            "",
            Columns([self._render_resources(), self._render_processes()], expand=True),
            "",
            Columns([self._render_models(), self._render_history()], expand=True),
            "",
            self._render_actions(),
            "",
        )

    def _render_input_dialog(self) -> Panel:
        """Render input dialog for package selection"""
        instructions = (
            "[cyan]Enter package name[/cyan] (e.g., nginx, docker, python)\n"
            "[dim]Press Enter to install, Esc to cancel[/dim]"
        )
        content = f"{instructions}\n\n[bold]>[/bold] {self.input_text}[blink_fast]█[/blink_fast]"
        return Panel(
            content, title="📦 What would you like to install?", padding=(2, 2), box=ROUNDED
        )

    def _render_password_dialog(self) -> Panel:
        """Render password input dialog for sudo commands"""
        instructions = (
            "[cyan]Enter sudo password[/cyan] to continue installation\n"
            "[dim]Press Enter to submit, Esc to cancel[/dim]"
        )
        # Show dots instead of actual characters for security
        password_display = "•" * len(self.input_text)
        content = f"{instructions}\n\n[bold]>[/bold] {password_display}[blink_fast]█[/blink_fast]"
        return Panel(content, title="🔐 Sudo Password Required", padding=(2, 2), box=ROUNDED)

    def _render_confirmation_dialog(self) -> Panel:
        """Render confirmation dialog for installation"""
        progress = self.installation_progress
        package = progress.package

        lines = []
        lines.append("[bold yellow]⚠️  Confirm Installation[/bold yellow]")
        lines.append("")
        lines.append(f"You are about to install: [bold cyan]{package}[/bold cyan]")
        lines.append("")

        # Show generated commands if available
        if hasattr(self, "_pending_commands") and self._pending_commands:
            lines.append("[bold]Commands to execute:[/bold]")
            for i, cmd in enumerate(self._pending_commands[:5], 1):
                # Truncate long commands
                display_cmd = cmd if len(cmd) <= 60 else cmd[:57] + "..."
                lines.append(f"  [dim]{i}.[/dim] {display_cmd}")
            if len(self._pending_commands) > 5:
                lines.append(f"  [dim]... and {len(self._pending_commands) - 5} more[/dim]")
            lines.append("")

        lines.append("[bold green]Press Y[/bold green] to confirm and install")
        lines.append("[bold red]Press N[/bold red] or [bold red]Esc[/bold red] to cancel")

        content = "\n".join(lines)
        return Panel(content, title="⚠️ Confirm Installation", padding=(2, 2), box=ROUNDED)

    def _render_progress_panel(self) -> Panel:
        """Render progress panel with support for install, bench, doctor"""
        progress = self.installation_progress

        if progress.state == InstallationState.WAITING_INPUT:
            return self._render_input_dialog()

        if progress.state == InstallationState.WAITING_PASSWORD:
            return self._render_password_dialog()

        if progress.state == InstallationState.WAITING_CONFIRMATION:
            return self._render_confirmation_dialog()

        lines = []

        # Operation name and status
        if progress.package:
            lines.append(f"[bold cyan]Operation:[/bold cyan] {progress.package}")

        # Progress bar
        if progress.total_steps > 0:
            filled = int((progress.current_step / progress.total_steps) * BAR_WIDTH)
            bar = "[green]" + "█" * filled + "[/green]" + "░" * (BAR_WIDTH - filled)
            percentage = int((progress.current_step / progress.total_steps) * 100)
            lines.append(f"\n[cyan]Progress:[/cyan] {bar} {percentage}%")
            lines.append(f"[dim]Step {progress.current_step}/{progress.total_steps}[/dim]")

        # Current step being processed
        if progress.current_library:
            lines.append(f"\n[bold]Current:[/bold] {progress.current_library}")

        # Time info
        if progress.elapsed_time > 0:
            lines.append(f"\n[dim]Elapsed: {progress.elapsed_time:.1f}s[/dim]")

        # Doctor results display
        if self.doctor_results:
            lines.append("\n[bold]Check Results:[/bold]")
            for name, passed, detail in self.doctor_results:
                icon = "[green]✓[/green]" if passed else "[red]✗[/red]"
                lines.append(f"  {icon} {name}: {detail}")

        # Show installed libraries for install operations
        if progress.libraries and progress.package not in ["System Benchmark", "System Doctor"]:
            lines.append(
                f"\n[dim]Libraries: {', '.join(progress.libraries[:MAX_LIBRARIES_DISPLAYED])}[/dim]"
            )
            if len(progress.libraries) > MAX_LIBRARIES_DISPLAYED:
                remaining = len(progress.libraries) - MAX_LIBRARIES_DISPLAYED
                lines.append(f"[dim]... and {remaining} more[/dim]")

        # Status messages
        if progress.error_message:
            lines.append(f"\n[red]✗ {progress.error_message}[/red]")
        elif progress.success_message:
            lines.append(f"\n[green]✓ {progress.success_message}[/green]")

        # Idle state message
        if progress.state == InstallationState.IDLE:
            lines.append("[dim]Press 1 for Install, 2 for Bench, 3 for Doctor[/dim]")

        content = (
            "\n".join(lines)
            if lines
            else (
                "[dim]No operation in progress\n"
                "Press 1 for Install, 2 for Bench, 3 for Doctor[/dim]"
            )
        )

        title_map = {
            InstallationState.IDLE: "📋 Progress",
            InstallationState.WAITING_INPUT: "📦 Installation",
            InstallationState.WAITING_CONFIRMATION: "⚠️ Confirm Installation",
            InstallationState.PROCESSING: "🔄 Processing",
            InstallationState.IN_PROGRESS: "⏳ In Progress",
            InstallationState.COMPLETED: "✅ Completed",
            InstallationState.FAILED: "❌ Failed",
        }

        title = title_map.get(progress.state, "📋 Progress")

        return Panel(content, title=title, padding=(1, 2), box=ROUNDED)

    def _render_progress_tab(self) -> Group:
        """Render progress tab with actions"""
        return Group(
            self._render_header(),
            "",
            self._render_progress_panel(),
            "",
            self._render_actions(),
            "",
        )

    def _render_footer(self) -> Panel:
        """Render footer"""
        footer_text = (
            "[cyan]q[/cyan] Quit  |  [cyan]Tab[/cyan] Switch Tab  |  [cyan]1-4[/cyan] Actions"
        )
        return Panel(footer_text, style="dim", box=ROUNDED)

    def _render_screen(self):
        """Render full screen based on current tab"""
        if self.current_tab == DashboardTab.HOME:
            content = self._render_home_tab()
        elif self.current_tab == DashboardTab.PROGRESS:
            content = self._render_progress_tab()
        else:
            content = self._render_home_tab()

        return Group(content, self._render_footer())

    def _enable_monitoring(self) -> None:
        """Enable system monitoring with user consent."""
        if not self._user_started_monitoring:
            self._user_started_monitoring = True
            self.monitor.enable_monitoring()
            self.lister.enable()
            self.history.load_history()
            # Enable model listing (Ollama)
            if self.model_lister:
                self.model_lister.enable()
                self.model_lister.check_ollama()
            # GPU is enabled separately only for bench operations

    def _handle_key_press(self, key: str) -> None:
        """Handle key press using centralized action map"""
        # Clear previous pressed indicator
        self.last_pressed_key = ""

        if key == "q":
            self.should_quit = True
            return

        elif key == "\t":  # Tab key
            # Switch tabs
            tabs = list(DashboardTab)
            current_idx = tabs.index(self.current_tab)
            self.current_tab = tabs[(current_idx + 1) % len(tabs)]
            self.last_pressed_key = "Tab"
            return

        # Handle input mode first if active
        if self.input_active:
            if key == "\n" or key == "\r":  # Enter
                self._submit_installation_input()
            elif key == "\x1b":  # Lone Escape (not arrow key)
                self._cancel_operation()
            elif key == "\b" or key == "\x7f":  # Backspace
                self.input_text = self.input_text[:-1]
            elif key in ["<UP>", "<DOWN>", "<LEFT>", "<RIGHT>"]:
                # Arrow keys in input mode - show in status
                self.last_pressed_key = key
                # Could implement history navigation or cursor movement here
            elif key and key.isprintable() and len(self.input_text) < MAX_INPUT_LENGTH:
                self.input_text += key
            return

        # Handle password input mode
        if self.installation_progress.state == InstallationState.WAITING_PASSWORD:
            if key == "\n" or key == "\r":  # Enter
                self._submit_password()
            elif key == "\x1b":  # Escape - cancel password entry
                self._cancel_operation()
            elif key == "\b" or key == "\x7f":  # Backspace
                self.input_text = self.input_text[:-1]
            elif key and key.isprintable() and len(self.input_text) < MAX_INPUT_LENGTH:
                self.input_text += key
            return

        # Handle confirmation mode (Y/N)
        if self.installation_progress.state == InstallationState.WAITING_CONFIRMATION:
            if key.lower() == "y":
                self._confirm_installation()
            elif key.lower() == "n" or key == "\x1b":  # N or lone Escape
                self._cancel_operation()
            elif key in ["<UP>", "<DOWN>", "<LEFT>", "<RIGHT>"]:
                # Arrow keys in confirmation - show pressed
                self.last_pressed_key = key
            return

        # Handle action keys using centralized ACTION_MAP
        if key in ACTION_MAP:
            label, _, handler_name = ACTION_MAP[key]
            self.last_pressed_key = label
            handler = getattr(self, handler_name, None)
            if handler and callable(handler):
                handler()

    def _start_bench(self) -> None:
        """Start benchmark - explicitly enables monitoring"""
        with self.state_lock:
            # Atomic check-and-set: verify conditions and update state atomically
            if self.bench_running or self.installation_progress.state in [
                InstallationState.IN_PROGRESS,
                InstallationState.PROCESSING,
            ]:
                return

            # Clear stale cancellation flag from previous operations
            self.stop_event.clear()

            # Atomically set running state before releasing lock
            self.bench_running = True

            # User explicitly requested bench - enable monitoring
            self._enable_monitoring()
            self.monitor.enable_gpu()  # GPU only enabled for bench

            # Reset state for new benchmark
            self.installation_progress = InstallationProgress()
            self.doctor_results = []
            self.bench_status = "Running benchmark..."
            self.current_tab = DashboardTab.PROGRESS
            self.installation_progress.state = InstallationState.PROCESSING
            self.installation_progress.package = "System Benchmark"

        # Log audit entry
        self._audit_log("bench", "System Benchmark", "started")

        # Run benchmark in background thread
        def run_bench():
            bench_results = []
            steps = [
                ("CPU Test", self._bench_cpu),
                ("Memory Test", self._bench_memory),
                ("Disk I/O Test", self._bench_disk),
                ("System Info", self._bench_system_info),
            ]

            # Initialize progress with lock
            with self.state_lock:
                self.installation_progress.total_steps = len(steps)
                self.installation_progress.start_time = time.time()
                self.installation_progress.state = InstallationState.IN_PROGRESS

            for i, (step_name, bench_func) in enumerate(steps, 1):
                with self.state_lock:
                    if (
                        self.stop_event.is_set()
                        or not self.running
                        or not self.bench_running
                        or self.installation_progress.state == InstallationState.FAILED
                    ):
                        break
                    self.installation_progress.current_step = i
                    self.installation_progress.current_library = f"Running {step_name}..."
                    self.installation_progress.update_elapsed()

                # Run actual benchmark (outside lock)
                try:
                    result = bench_func()
                    bench_results.append((step_name, True, result))
                except Exception as e:
                    bench_results.append((step_name, False, str(e)))

            # Store results and finalize with lock
            with self.state_lock:
                self.doctor_results = bench_results

                # Only mark completed if not cancelled/failed
                if self.installation_progress.state != InstallationState.FAILED:
                    self.bench_status = "Benchmark complete - System OK"
                    self.installation_progress.state = InstallationState.COMPLETED
                    all_passed = all(r[1] for r in bench_results)
                    if all_passed:
                        self.installation_progress.success_message = "All benchmarks passed!"
                    else:
                        self.installation_progress.success_message = "Some benchmarks had issues."

                self.installation_progress.current_library = ""
                self.bench_running = False

        threading.Thread(target=run_bench, daemon=True).start()

    def _bench_cpu(self) -> str:
        """Lightweight CPU benchmark"""
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        freq_str = f"{cpu_freq.current:.0f}MHz" if cpu_freq else "N/A"
        cpu_percent = psutil.cpu_percent(interval=0.5)
        return f"{cpu_count} cores @ {freq_str}, {cpu_percent:.1f}% load"

    def _bench_memory(self) -> str:
        """Lightweight memory benchmark"""
        mem = psutil.virtual_memory()
        total_gb = mem.total / BYTES_PER_GB
        avail_gb = mem.available / BYTES_PER_GB
        return f"{avail_gb:.1f}GB free / {total_gb:.1f}GB total ({mem.percent:.1f}% used)"

    def _bench_disk(self) -> str:
        """Lightweight disk benchmark"""
        disk_path = get_root_disk_path()
        disk = psutil.disk_usage(disk_path)
        total_gb = disk.total / BYTES_PER_GB
        free_gb = disk.free / BYTES_PER_GB
        return f"{free_gb:.1f}GB free / {total_gb:.1f}GB total ({disk.percent:.1f}% used)"

    def _bench_system_info(self) -> str:
        """Get system info"""
        return f"Python {sys.version_info.major}.{sys.version_info.minor}, {platform.system()} {platform.release()}"

    def _start_doctor(self) -> None:
        """Start doctor system check - explicitly enables monitoring"""
        with self.state_lock:
            # Atomic check-and-set: verify conditions and update state atomically
            if self.doctor_running or self.installation_progress.state in [
                InstallationState.IN_PROGRESS,
                InstallationState.PROCESSING,
            ]:
                return

            # Clear stale cancellation flag from previous operations
            self.stop_event.clear()

            # Atomically set running state before releasing lock
            self.doctor_running = True

            # User explicitly requested doctor - enable monitoring
            self._enable_monitoring()

            # Reset state for new doctor check
            self.installation_progress = InstallationProgress()
            self.doctor_results = []
            self.current_tab = DashboardTab.PROGRESS
            self.installation_progress.state = InstallationState.PROCESSING
            self.installation_progress.package = "System Doctor"

        # Log audit entry
        self._audit_log("doctor", "System Doctor", "started")

        # Run doctor in background thread
        def run_doctor():
            # Use platform-agnostic disk path
            disk_path = get_root_disk_path()
            try:
                disk_percent = psutil.disk_usage(disk_path).percent
                disk_ok = disk_percent < DISK_WARNING_THRESHOLD
                disk_detail = f"{disk_percent:.1f}% used"
            except Exception as e:
                logger.debug(f"Disk usage check failed: {type(e).__name__}: {e}", exc_info=True)
                disk_ok = False
                disk_detail = CHECK_UNAVAILABLE_MSG

            try:
                mem_percent = psutil.virtual_memory().percent
                mem_ok = mem_percent < MEMORY_WARNING_THRESHOLD
                mem_detail = f"{mem_percent:.1f}% used"
            except Exception as e:
                logger.debug(f"Memory usage check failed: {type(e).__name__}: {e}", exc_info=True)
                mem_ok = False
                mem_detail = CHECK_UNAVAILABLE_MSG

            try:
                cpu_load = psutil.cpu_percent()
                cpu_ok = cpu_load < CPU_WARNING_THRESHOLD
                cpu_detail = f"{cpu_load:.1f}% load"
            except Exception as e:
                logger.debug(f"CPU load check failed: {type(e).__name__}: {e}", exc_info=True)
                cpu_ok = False
                cpu_detail = CHECK_UNAVAILABLE_MSG

            checks = [
                (
                    "Python version",
                    True,
                    f"Python {sys.version_info.major}.{sys.version_info.minor}",
                ),
                ("psutil module", True, "Installed"),
                ("rich module", True, "Installed"),
                ("Disk space", disk_ok, disk_detail),
                ("Memory available", mem_ok, mem_detail),
                ("CPU load", cpu_ok, cpu_detail),
            ]

            # Initialize progress with lock
            with self.state_lock:
                self.installation_progress.total_steps = len(checks)
                self.installation_progress.start_time = time.time()
                self.installation_progress.state = InstallationState.IN_PROGRESS

            for i, (name, passed, detail) in enumerate(checks, 1):
                with self.state_lock:
                    if (
                        self.stop_event.is_set()
                        or not self.running
                        or not self.doctor_running
                        or self.installation_progress.state == InstallationState.FAILED
                    ):
                        break
                    self.installation_progress.current_step = i
                    self.installation_progress.current_library = f"Checking {name}..."
                    self.doctor_results.append((name, passed, detail))
                    self.installation_progress.update_elapsed()

                time.sleep(DOCTOR_CHECK_DELAY)

            # Finalize with lock
            with self.state_lock:
                # Only mark completed if not cancelled/failed
                if self.installation_progress.state != InstallationState.FAILED:
                    all_passed = all(r[1] for r in self.doctor_results)
                    self.installation_progress.state = InstallationState.COMPLETED
                    if all_passed:
                        self.installation_progress.success_message = (
                            "All checks passed! System is healthy."
                        )
                    else:
                        self.installation_progress.success_message = (
                            "Some checks failed. Review results above."
                        )

                self.installation_progress.current_library = ""
                self.doctor_running = False

        threading.Thread(target=run_doctor, daemon=True).start()

    def _cancel_operation(self) -> None:
        """Cancel any ongoing operation"""
        with self.state_lock:
            target = ""
            # Cancel installation
            if self.installation_progress.state in [
                InstallationState.IN_PROGRESS,
                InstallationState.PROCESSING,
                InstallationState.WAITING_INPUT,
                InstallationState.WAITING_CONFIRMATION,
            ]:
                target = self.installation_progress.package or "install"
                self.installation_progress.state = InstallationState.FAILED
                self.installation_progress.error_message = "Operation cancelled by user"
                self.installation_progress.current_library = ""
                # Clear pending commands
                if hasattr(self, "_pending_commands"):
                    self._pending_commands = []

            # Cancel bench
            if self.bench_running:
                target = "bench"
                self.bench_running = False
                self.bench_status = "Benchmark cancelled"

            # Cancel doctor
            if self.doctor_running:
                target = "doctor"
                self.doctor_running = False

            # Reset input
            self.input_active = False
            self.input_text = ""

            # Signal stop to threads
            self.stop_event.set()

        # Log audit entry
        if target:
            self._audit_log("cancel", target, "cancelled")

        self.status_message = "Operation cancelled"

    def _clean_error_message(
        self, error_output: str, fallback_msg: str, max_length: int = 80
    ) -> str:
        """
        Clean and truncate error messages from CLI output.

        Args:
            error_output: Raw error output (may contain color codes)
            fallback_msg: Message to use if cleaning results in empty string
            max_length: Maximum length for the cleaned message

        Returns:
            Cleaned error message string
        """
        clean_msg = re.sub(COLOR_TAG_PATTERN, "", error_output)
        clean_msg = clean_msg.strip()
        if clean_msg:
            lines = clean_msg.split("\n")
            first_line = lines[0].strip()[:max_length]
            return first_line or fallback_msg
        return fallback_msg

    def _audit_log(self, action: str, target: str, outcome: str) -> None:
        """Log dashboard action to audit history.

        Args:
            action: Action name from ACTION_MAP
            target: Target package/operation name
            outcome: One of: started, succeeded, failed, cancelled
        """
        try:
            # Acquire lock for thread-safe file operations
            with self.audit_lock:
                audit_file = Path.home() / ".cortex" / "history.db"
                audit_file.parent.mkdir(parents=True, exist_ok=True)

                entry = {
                    "action": action,
                    "target": target,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "outcome": outcome,
                }

                # Atomic write using temp file and rename
                with tempfile.NamedTemporaryFile(
                    mode="a",
                    dir=audit_file.parent,
                    delete=False,
                    prefix=".audit_",
                    suffix=".tmp",
                ) as tmp:
                    # Read existing entries if file exists
                    if audit_file.exists():
                        with open(audit_file, encoding="utf-8") as f:
                            tmp.write(f.read())

                    # Append new entry
                    tmp.write(json.dumps(entry) + "\n")
                    tmp.flush()
                    os.fsync(tmp.fileno())
                    temp_name = tmp.name

                # Atomic rename
                os.replace(temp_name, audit_file)

        except OSError as e:
            # Never crash UI on logging failure - use specific exceptions
            logger.debug(f"Audit log IO error: {type(e).__name__}: {e}", exc_info=True)
        except Exception as e:
            # Catch any other unexpected errors
            logger.debug(f"Audit log unexpected error: {type(e).__name__}: {e}", exc_info=True)

    def _start_installation(self) -> None:
        """Start installation process"""
        with self.state_lock:
            # Atomic check-and-set: verify conditions and update state atomically
            if self.installation_progress.state in [
                InstallationState.IN_PROGRESS,
                InstallationState.PROCESSING,
                InstallationState.WAITING_INPUT,
                InstallationState.WAITING_CONFIRMATION,
            ]:
                return

            # Atomically set state before releasing lock
            # Reset progress state for new installation
            self.installation_progress = InstallationProgress()
            self.installation_progress.state = InstallationState.WAITING_INPUT

            self.input_active = True
            self.input_text = ""
            self._pending_commands = []  # Clear any pending commands
            self.current_tab = DashboardTab.PROGRESS

        # Log audit entry
        self._audit_log("install", "", "started")

    def _submit_installation_input(self) -> None:
        """Submit installation input with validation"""
        with self.state_lock:
            package = self.input_text.strip()
            if not package:
                return

            # Basic validation: alphanumeric, dash, underscore, dot only
            if not re.match(r"^[a-zA-Z0-9._-]+$", package):
                self.status_message = "Invalid package name format"
                self.input_text = ""
                return

            self.installation_progress.package = package
            self.installation_progress.state = InstallationState.PROCESSING
            self.input_active = False

        if SIMULATION_MODE:
            # TODO: Replace with actual CLI integration
            # This simulation will be replaced with:
            # from cortex.cli import CortexCLI
            # cli = CortexCLI()
            # cli.install(package, dry_run=False)
            self._simulate_installation()
        else:
            # Run dry-run first to get commands, then show confirmation
            self._run_dry_run_and_confirm()

    def _submit_password(self) -> None:
        """Submit password for sudo commands"""
        with self.state_lock:
            password = self.input_text
            self.input_text = ""  # Clear for next use
            self.installation_progress.state = InstallationState.IN_PROGRESS
            # Store password for execution
            self._cached_sudo_password = password

    def _run_dry_run_and_confirm(self) -> None:
        """
        Run dry-run to get commands, then show confirmation dialog.
        Executes in background thread with progress feedback.
        """
        self.stop_event.clear()
        threading.Thread(target=self._execute_dry_run, daemon=True).start()

    def _execute_dry_run(self) -> None:
        """Execute dry-run to get commands, then show confirmation"""
        from cortex.cli import CortexCLI

        progress = self.installation_progress
        package_name = progress.package

        progress.state = InstallationState.IN_PROGRESS
        progress.start_time = time.time()
        progress.total_steps = 3  # Check, Parse, Confirm
        progress.libraries = []

        try:
            # Step 1: Check prerequisites
            with self.state_lock:
                progress.current_step = 1
                progress.current_library = "Checking prerequisites..."
                progress.update_elapsed()

            # Check for API key first
            api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                with self.state_lock:
                    progress.state = InstallationState.FAILED
                    progress.error_message = (
                        "No API key found!\n"
                        "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment.\n"
                        "Run 'cortex wizard' to configure."
                    )
                return

            with self.state_lock:
                if self.stop_event.is_set() or progress.state == InstallationState.FAILED:
                    return

            # Step 2: Initialize CLI and get commands
            with self.state_lock:
                progress.current_step = 2
                progress.current_library = "Planning installation..."
                progress.update_elapsed()

            cli = CortexCLI()

            # Use JSON output for machine-readable response
            with io.StringIO() as stdout_capture, io.StringIO() as stderr_capture:
                try:
                    with (
                        contextlib.redirect_stdout(stdout_capture),
                        contextlib.redirect_stderr(stderr_capture),
                    ):
                        # Suppress CX prints that can contaminate JSON plan output
                        silent_prev = os.environ.get("CORTEX_SILENT_OUTPUT")
                        os.environ["CORTEX_SILENT_OUTPUT"] = "1"
                        try:
                            result = cli.install(
                                package_name, dry_run=True, execute=False, json_output=True
                            )
                        finally:
                            # Restore previous state - always runs even on exception
                            if silent_prev is None:
                                os.environ.pop("CORTEX_SILENT_OUTPUT", None)
                            else:
                                os.environ["CORTEX_SILENT_OUTPUT"] = silent_prev
                except Exception as e:
                    result = 1
                    stderr_capture.write(str(e))

                stdout_output = stdout_capture.getvalue()
                stderr_output = stderr_capture.getvalue()

            with self.state_lock:
                if self.stop_event.is_set() or progress.state == InstallationState.FAILED:
                    return

            if result != 0:
                with self.state_lock:
                    progress.state = InstallationState.FAILED
                    error_msg = stderr_output.strip() or stdout_output.strip()
                    progress.error_message = self._clean_error_message(
                        error_msg, f"Failed to plan install for '{package_name}'"
                    )
                return

            # Step 3: Parse JSON response
            with self.state_lock:
                progress.current_step = 3
                progress.current_library = "Ready for confirmation..."
                progress.update_elapsed()

            # Parse JSON output for commands
            try:
                json_data = json.loads(stdout_output)
                if not json_data.get("success", False):
                    with self.state_lock:
                        progress.state = InstallationState.FAILED
                        error = json_data.get("error", "Unknown error")
                        progress.error_message = self._clean_error_message(
                            error, f"Failed to plan install for '{package_name}'"
                        )
                    return

                commands = json_data.get("commands", [])
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"JSON parse failed: {type(e).__name__}: {e}", exc_info=True)
                with self.state_lock:
                    progress.state = InstallationState.FAILED
                    progress.error_message = "Failed to parse installation plan"
                return

            with self.state_lock:
                self._pending_commands = commands
                progress.libraries = [f"Package: {package_name}"]
                if commands:
                    progress.libraries.append(f"Commands: {len(commands)}")

                # Show confirmation dialog
                progress.state = InstallationState.WAITING_CONFIRMATION
                progress.current_library = ""

        except ImportError as e:
            logger.error(f"Import error during dry-run: {e}", exc_info=True)
            with self.state_lock:
                progress.state = InstallationState.FAILED
                progress.error_message = f"Missing package: {e}"
        except OSError as e:
            logger.error(f"IO error during dry-run: {e}", exc_info=True)
            with self.state_lock:
                progress.state = InstallationState.FAILED
                progress.error_message = f"System error: {str(e)[:80]}"
        except Exception as e:
            logger.exception("Dry-run install planning failed", exc_info=True)
            with self.state_lock:
                progress.state = InstallationState.FAILED
                progress.error_message = f"Error: {str(e)[:80]}"

    def _confirm_installation(self) -> None:
        """User confirmed installation - execute with --execute flag"""
        with self.state_lock:
            package_name = self.installation_progress.package
            self.installation_progress.state = InstallationState.PROCESSING
            self.stop_event.clear()

        # Log audit entry
        self._audit_log("install_confirmed", package_name, "started")

        threading.Thread(target=self._execute_confirmed_install, daemon=True).start()

    def _execute_confirmed_install(self) -> None:
        """Execute the confirmed installation with execute=True"""
        from cortex.cli import CortexCLI
        from cortex.sandbox.sandbox_executor import SandboxExecutor

        # Get package name with lock
        with self.state_lock:
            package_name = self.installation_progress.package

        # Initialize progress with lock
        with self.state_lock:
            self.installation_progress.state = InstallationState.IN_PROGRESS
            self.installation_progress.start_time = time.time()
            self.installation_progress.total_steps = 3  # Init, Execute, Complete
            self.installation_progress.current_step = 1
            self.installation_progress.current_library = "Starting installation..."
            self.installation_progress.update_elapsed()

        try:
            if self.stop_event.is_set():
                return

            # Get pending commands and check if sudo password is needed
            with self.state_lock:
                commands = self._pending_commands[:] if self._pending_commands else []

            # Check if any command requires sudo and we don't have password yet
            needs_password = any(cmd.strip().startswith("sudo") for cmd in commands)
            if needs_password and not self._cached_sudo_password:
                with self.state_lock:
                    self.installation_progress.state = InstallationState.WAITING_PASSWORD
                    self.installation_progress.current_library = "Waiting for sudo password..."
                # Wait for password to be entered by user via _submit_password
                # Use a loop with timeout and check cancellation/state changes
                timeout_end = time.time() + 300  # 5 minute timeout
                while time.time() < timeout_end:
                    if self._cached_sudo_password:
                        break
                    if self.stop_event.is_set():
                        with self.state_lock:
                            self.installation_progress.state = InstallationState.FAILED
                            self.installation_progress.error_message = (
                                "Installation canceled while waiting for password"
                            )
                        return
                    if not self.running:
                        with self.state_lock:
                            self.installation_progress.state = InstallationState.FAILED
                            self.installation_progress.error_message = (
                                "Installation stopped while waiting for password"
                            )
                        return
                    time.sleep(0.1)

                # Check if we timed out waiting for password
                if not self._cached_sudo_password:
                    with self.state_lock:
                        self.installation_progress.state = InstallationState.FAILED
                        self.installation_progress.error_message = (
                            "Timeout waiting for sudo password"
                        )
                    return

            # Step 2: Execute installation
            with self.state_lock:
                self.installation_progress.current_step = 2
                self.installation_progress.current_library = f"Installing {package_name}..."
                self.installation_progress.update_elapsed()

            # Execute via SandboxExecutor for security
            try:
                sandbox = SandboxExecutor()

                if not commands:
                    result = 1
                    stdout_output = ""
                    stderr_output = (
                        "No confirmed commands to execute. Please re-plan the installation."
                    )
                else:
                    # Execute each command via sandbox, showing output and commands
                    all_success = True
                    outputs = []
                    total_commands = len(commands)

                    for cmd_idx, cmd in enumerate(commands, 1):
                        if self.stop_event.is_set():
                            return

                        # Show the command being executed
                        with self.state_lock:
                            display_cmd = cmd if len(cmd) <= 70 else cmd[:67] + "..."
                            self.installation_progress.current_library = (
                                f"[{cmd_idx}/{total_commands}] {display_cmd}"
                            )
                            self.installation_progress.update_elapsed()

                        # Prepare command - if sudo is needed, inject password via stdin
                        exec_cmd = cmd
                        stdin_input = None
                        if cmd.strip().startswith("sudo") and self._cached_sudo_password:
                            # Use sudo -S -p "" to suppress prompts and read password from stdin
                            # Remove 'sudo' from command and pass password via stdin
                            exec_cmd = f'sudo -S -p "" {cmd[4:].strip()}'
                            stdin_input = f"{self._cached_sudo_password}\n"

                        # Execute the command with stdin if password is needed
                        exec_result = sandbox.execute(exec_cmd, stdin=stdin_input)
                        output_text = exec_result.stdout or ""
                        outputs.append(output_text)

                        # Update with result indicator
                        if exec_result.success:
                            with self.state_lock:
                                lines = output_text.split("\n") if output_text else []
                                # Show last meaningful line of output
                                preview = next((l for l in reversed(lines) if l.strip()), "")
                                if preview and len(preview) > 60:
                                    preview = preview[:57] + "..."
                                status = f"✓ [{cmd_idx}/{total_commands}]"
                                self.installation_progress.current_library = (
                                    f"{status} {preview}" if preview else status
                                )
                        else:
                            all_success = False
                            with self.state_lock:
                                self.installation_progress.current_library = (
                                    f"✗ [{cmd_idx}/{total_commands}] Failed"
                                )
                            break

                    result = 0 if all_success else 1
                    stdout_output = "\n".join(outputs)
                    stderr_output = "" if all_success else "Command execution failed"
            except OSError as e:
                logger.error(f"Sandbox execution IO error: {e}", exc_info=True)
                result = 1
                stdout_output = ""
                stderr_output = f"System error: {str(e)}"
            except Exception as e:
                logger.error(f"Sandbox execution failed: {e}", exc_info=True)
                result = 1
                stdout_output = ""
                stderr_output = str(e)

            if self.stop_event.is_set():
                return

            # Step 3: Complete
            with self.state_lock:
                self.installation_progress.current_step = 3
                self.installation_progress.current_library = "Finalizing..."
                self.installation_progress.update_elapsed()

                if result == 0:
                    self.installation_progress.state = InstallationState.COMPLETED
                    self.installation_progress.success_message = (
                        f"✓ Successfully installed '{package_name}'!"
                    )
                    # Log success audit
                    self._audit_log("install_execute", package_name, "succeeded")
                else:
                    self.installation_progress.state = InstallationState.FAILED
                    error_msg = stderr_output.strip() or stdout_output.strip()
                    self.installation_progress.error_message = self._clean_error_message(
                        error_msg, f"Installation failed for '{package_name}'"
                    )
                    # Log failure audit
                    self._audit_log("install_execute", package_name, "failed")

        except ImportError as e:
            logger.error(f"Import error during installation: {e}", exc_info=True)
            with self.state_lock:
                self.installation_progress.state = InstallationState.FAILED
                self.installation_progress.error_message = f"Missing package: {e}"
            self._audit_log("install_execute", package_name, "failed")
        except OSError as e:
            logger.error(f"IO error during installation: {e}", exc_info=True)
            with self.state_lock:
                self.installation_progress.state = InstallationState.FAILED
                self.installation_progress.error_message = f"System error: {str(e)[:80]}"
            self._audit_log("install_execute", package_name, "failed")
        except Exception as e:
            logger.exception("Installation execution failed", exc_info=True)
            with self.state_lock:
                self.installation_progress.state = InstallationState.FAILED
                self.installation_progress.error_message = f"Error: {str(e)[:80]}"
            self._audit_log("install_execute", package_name, "failed")
        finally:
            with self.state_lock:
                self.installation_progress.current_library = ""
                self._pending_commands = []

    def _run_real_installation(self) -> None:
        """
        Run real installation using Cortex CLI.
        Executes in background thread with progress feedback.
        """
        self.stop_event.clear()
        threading.Thread(target=self._execute_cli_install, daemon=True).start()

    def _execute_cli_install(self) -> None:
        """Execute actual CLI installation in background thread"""
        import contextlib
        import io

        from cortex.cli import CortexCLI

        progress = self.installation_progress
        package_name = progress.package

        progress.state = InstallationState.IN_PROGRESS
        progress.start_time = time.time()
        progress.total_steps = 4  # Check, Parse, Plan, Complete
        progress.libraries = []

        try:
            # Step 1: Check prerequisites
            with self.state_lock:
                progress.current_step = 1
                progress.current_library = "Checking prerequisites..."
                progress.update_elapsed()

            # Check for API key first
            api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                with self.state_lock:
                    progress.state = InstallationState.FAILED
                    progress.error_message = (
                        "No API key found!\n"
                        "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment.\n"
                        "Run 'cortex wizard' to configure."
                    )
                return

            with self.state_lock:
                if self.stop_event.is_set() or progress.state == InstallationState.FAILED:
                    return

            # Step 2: Initialize CLI
            with self.state_lock:
                progress.current_step = 2
                progress.current_library = "Initializing Cortex CLI..."
                progress.update_elapsed()

            cli = CortexCLI()

            with self.state_lock:
                if self.stop_event.is_set() or progress.state == InstallationState.FAILED:
                    return

            # Step 3: Run installation (capture output)
            with self.state_lock:
                progress.current_step = 3
                progress.current_library = f"Planning install for: {package_name}"
                progress.libraries.append(f"Package: {package_name}")
                progress.update_elapsed()

            # Capture CLI output
            with io.StringIO() as stdout_capture, io.StringIO() as stderr_capture:
                try:
                    with (
                        contextlib.redirect_stdout(stdout_capture),
                        contextlib.redirect_stderr(stderr_capture),
                    ):
                        result = cli.install(package_name, dry_run=True, execute=False)
                except Exception as e:
                    result = 1
                    stderr_capture.write(str(e))

                stdout_output = stdout_capture.getvalue()
                stderr_output = stderr_capture.getvalue()

            with self.state_lock:
                if self.stop_event.is_set() or progress.state == InstallationState.FAILED:
                    return

            # Step 4: Complete
            with self.state_lock:
                progress.current_step = 4
                progress.current_library = "Finalizing..."
                progress.update_elapsed()

                if result == 0:
                    progress.state = InstallationState.COMPLETED
                    # Extract generated commands if available
                    commands_header = "Generated commands:"
                    has_commands_header = any(
                        line.strip().startswith(commands_header)
                        for line in stdout_output.splitlines()
                    )
                    if has_commands_header:
                        progress.success_message = (
                            f"✓ Plan ready for '{package_name}'!\n"
                            "Run in terminal: cortex install " + package_name + " --execute"
                        )
                    else:
                        progress.success_message = (
                            f"Dry-run complete for '{package_name}'!\n"
                            "Run 'cortex install <pkg> --execute' in terminal to apply."
                        )
                else:
                    progress.state = InstallationState.FAILED
                    # Try to extract meaningful error from output
                    error_msg = stderr_output.strip() or stdout_output.strip()
                    # Remove Rich formatting characters for cleaner display
                    import re

                    clean_msg = re.sub(COLOR_TAG_PATTERN, "", error_msg)  # Remove [color] tags
                    clean_msg = re.sub(r" CX[^│✗✓⠋]*[│✗✓⠋]", "", clean_msg)  # Remove CX prefix
                    clean_msg = clean_msg.strip()

                    if "doesn't look valid" in clean_msg or "wizard" in clean_msg.lower():
                        progress.error_message = (
                            "API key invalid. Run 'cortex wizard' to configure."
                        )
                    elif "not installed" in clean_msg.lower() and "openai" in clean_msg.lower():
                        progress.error_message = "OpenAI not installed. Run: pip install openai"
                    elif "not installed" in clean_msg.lower() and "anthropic" in clean_msg.lower():
                        progress.error_message = (
                            "Anthropic not installed. Run: pip install anthropic"
                        )
                    elif "API key" in error_msg or "api_key" in error_msg.lower():
                        progress.error_message = "API key not configured. Run 'cortex wizard'"
                    elif clean_msg:
                        # Show cleaned error, truncated
                        lines = clean_msg.split("\n")
                        first_line = lines[0].strip()[:80]
                        progress.error_message = first_line or f"Failed to install '{package_name}'"
                    else:
                        progress.error_message = f"Failed to plan install for '{package_name}'"

        except ImportError as e:
            with self.state_lock:
                progress.state = InstallationState.FAILED
                progress.error_message = f"Missing package: {e}"
        except Exception as e:
            with self.state_lock:
                progress.state = InstallationState.FAILED
                progress.error_message = f"Error: {str(e)[:80]}"
        finally:
            with self.state_lock:
                progress.current_library = ""

    def _run_installation(self) -> None:
        """Run simulated installation in background thread (for testing)"""
        progress = self.installation_progress
        package_name = progress.package

        progress.state = InstallationState.IN_PROGRESS
        progress.start_time = time.time()
        progress.total_steps = INSTALL_TOTAL_STEPS
        progress.libraries = []

        # TODO: Replace simulation with actual CLI call
        # Simulated installation steps
        install_steps = [
            f"Preparing {package_name}",
            "Resolving dependencies",
            "Downloading packages",
            "Installing components",
            "Verifying installation",
        ]

        for i, step in enumerate(install_steps, 1):
            if (
                self.stop_event.is_set()
                or not self.running
                or progress.state == InstallationState.FAILED
            ):
                break
            progress.current_step = i
            progress.current_library = step
            progress.libraries.append(step)
            progress.update_elapsed()
            time.sleep(INSTALL_STEP_DELAY)

        if progress.state != InstallationState.FAILED:
            progress.state = InstallationState.COMPLETED
            if SIMULATION_MODE:
                progress.success_message = f"[SIMULATED] Successfully installed {package_name}!"
            else:
                progress.success_message = f"Successfully installed {package_name}!"
        progress.current_library = ""

    def _simulate_installation(self) -> None:
        """Start simulated installation in background thread"""
        self.stop_event.clear()
        threading.Thread(target=self._run_installation, daemon=True).start()

    def _reset_to_home(self) -> None:
        """Reset state and go to home tab"""
        with self.state_lock:
            self.installation_progress = InstallationProgress()
            self.input_text = ""
            self.input_active = False
            self.current_tab = DashboardTab.HOME
            self.doctor_results = []
            self.bench_status = "Ready to run benchmark"
            self.stop_event.clear()

    def _check_keyboard_input(self) -> str | None:
        """Check for keyboard input (cross-platform) with ANSI escape sequence handling"""
        try:
            if sys.platform == "win32":
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode("utf-8", errors="ignore")
                    return key
            else:
                if select.select([sys.stdin], [], [], 0)[0]:
                    key = sys.stdin.read(1)
                    # Handle ANSI escape sequences (arrow keys, etc.)
                    if key == "\x1b":
                        # Peek for CSI sequence (ESC + [ + code)
                        if select.select([sys.stdin], [], [], 0.01)[0]:
                            next_char = sys.stdin.read(1)
                            if next_char == "[":
                                # Read the final character of CSI sequence
                                if select.select([sys.stdin], [], [], 0.01)[0]:
                                    code = sys.stdin.read(1)
                                    # Map arrow keys to named keys
                                    arrow_map = {
                                        "A": "<UP>",
                                        "B": "<DOWN>",
                                        "C": "<RIGHT>",
                                        "D": "<LEFT>",
                                    }
                                    return arrow_map.get(code, None)  # Ignore unknown CSI
                            # Not a CSI sequence, return ESC as is
                            return key
                        # Lone ESC with no following characters
                        return key
                    return key
        except OSError as e:
            logger.warning(f"Keyboard check error: {e}")
        except Exception as e:
            logger.error(f"Unexpected keyboard error: {e}")
        return None

    def run(self) -> None:
        """Run dashboard with proper terminal state management"""
        self.running = True
        self.should_quit = False
        self.stop_event.clear()

        # Save terminal settings on Unix
        old_settings = None
        if sys.platform != "win32":
            try:
                old_settings = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            except Exception as e:
                logger.debug(f"Failed to set terminal attributes: {e}")

        def restore_terminal():
            """Restore terminal settings - registered with atexit for safety"""
            if old_settings is not None:
                try:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                except Exception as e:
                    logger.warning(f"Failed to restore terminal settings: {e}")

        # Register cleanup with atexit for safety
        if old_settings is not None:
            atexit.register(restore_terminal)

        def monitor_loop():
            while self.running and not self.stop_event.is_set():
                try:
                    # Only update if monitoring has been enabled
                    if self._user_started_monitoring:
                        self.monitor.update_metrics()
                        self.lister.update_processes()
                        # Update model list (Ollama)
                        if self.model_lister:
                            self.model_lister.update_models()

                    # Update progress if in progress tab
                    if self.current_tab == DashboardTab.PROGRESS:
                        with self.state_lock:
                            self.installation_progress.update_elapsed()

                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                time.sleep(MONITOR_LOOP_INTERVAL)

        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()

        try:
            with Live(
                self._render_screen(),
                console=self.console,
                refresh_per_second=UI_REFRESH_RATE,
                screen=True,
            ) as live:
                while self.running and not self.should_quit:
                    # Check for keyboard input
                    key = self._check_keyboard_input()
                    if key:
                        self._handle_key_press(key)

                    # Update display
                    live.update(self._render_screen())
                    time.sleep(UI_INPUT_CHECK_INTERVAL)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Keyboard interrupt received. Shutting down...[/yellow]")
            self.should_quit = True

        finally:
            self.running = False
            self.stop_event.set()
            # Restore terminal settings
            restore_terminal()
            # Unregister atexit handler since we've already cleaned up
            if old_settings is not None:
                try:
                    atexit.unregister(restore_terminal)
                except Exception:
                    pass


# =============================================================================
# DASHBOARD APP
# =============================================================================


class DashboardApp:
    """
    Main dashboard application orchestrator.

    Coordinates all dashboard components including system monitoring,
    process listing, command history, model listing, and UI rendering.
    Provides the main entry point for running the dashboard.

    Example:
        app = DashboardApp()
        app.run()
    """

    def __init__(self):
        self.monitor = SystemMonitor()
        self.lister = ProcessLister()
        self.history = CommandHistory()
        self.model_lister = ModelLister()
        self.ui = UIRenderer(
            self.monitor,
            self.lister,
            self.history,
            self.model_lister,
        )

    def run(self) -> int:
        """Run the app and return exit code"""
        if not PSUTIL_AVAILABLE:
            print("Error: The 'psutil' library is required but not installed.", file=sys.stderr)
            print("Please install it with: pip install psutil>=5.9.0", file=sys.stderr)
            return 1

        console = Console()
        try:
            console.print("[bold cyan]Starting Cortex Dashboard...[/bold cyan]")
            console.print("[dim]Press [cyan]q[/cyan] to quit[/dim]")
            console.print("[dim]System monitoring starts when you run Bench or Doctor[/dim]\n")
            time.sleep(STARTUP_DELAY)
            self.ui.run()
            return 0
        except KeyboardInterrupt:
            console.print("\n[yellow]Keyboard interrupt received.[/yellow]")
            return 0
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return 1
        finally:
            self.ui.running = False
            self.ui.stop_event.set()
            # Cleanup GPU resources
            self.monitor.shutdown_gpu()
            console.print("\n[yellow]Dashboard shutdown[/yellow]")


def main() -> int:
    """Entry point"""
    if not PSUTIL_AVAILABLE:
        print("Error: The 'psutil' library is required but not installed.", file=sys.stderr)
        print("Please install it with: pip install psutil>=5.9.0", file=sys.stderr)
        return 1

    app = DashboardApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
