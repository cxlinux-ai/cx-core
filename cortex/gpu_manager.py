"""
Cortex Hybrid GPU Manager

Manages hybrid GPU systems (Intel/AMD + NVIDIA Optimus).
Shows GPU state, per-app assignment, easy switching, battery estimates.

Issue: #454
"""

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.table import Table

from cortex.branding import CORTEX_CYAN, console, cx_header, cx_print


class GPUMode(Enum):
    """GPU operation modes."""

    INTEGRATED = "integrated"  # Intel/AMD only (best battery)
    HYBRID = "hybrid"  # Auto-switching (balanced)
    NVIDIA = "nvidia"  # NVIDIA only (best performance)
    COMPUTE = "compute"  # NVIDIA for compute only
    UNKNOWN = "unknown"


class GPUVendor(Enum):
    """GPU vendors."""

    INTEL = "intel"
    AMD = "amd"
    NVIDIA = "nvidia"
    UNKNOWN = "unknown"


@dataclass
class GPUDevice:
    """Represents a GPU device."""

    vendor: GPUVendor
    name: str
    driver: str = ""
    pci_id: str = ""
    power_state: str = ""
    memory_mb: int = 0
    is_active: bool = False
    is_primary: bool = False


@dataclass
class GPUState:
    """Current GPU system state."""

    mode: GPUMode = GPUMode.UNKNOWN
    devices: list[GPUDevice] = field(default_factory=list)
    active_gpu: GPUDevice | None = None
    prime_profile: str = ""
    render_offload_available: bool = False
    power_management: str = ""

    @property
    def is_hybrid_system(self) -> bool:
        """Check if this is a hybrid GPU system."""
        vendors = {d.vendor for d in self.devices}
        return GPUVendor.NVIDIA in vendors and (
            GPUVendor.INTEL in vendors or GPUVendor.AMD in vendors
        )


@dataclass
class AppGPUConfig:
    """Per-application GPU configuration."""

    name: str
    executable: str
    gpu: GPUVendor
    env_vars: dict[str, str] = field(default_factory=dict)


# Battery impact estimates (hours difference)
BATTERY_IMPACT = {
    GPUMode.INTEGRATED: {"description": "Best battery life", "impact": "+2-4 hours"},
    GPUMode.HYBRID: {"description": "Balanced", "impact": "+1-2 hours"},
    GPUMode.NVIDIA: {"description": "Full performance", "impact": "Baseline"},
    GPUMode.COMPUTE: {"description": "GPU for compute only", "impact": "+0.5-1 hours"},
}

# Common apps and their recommended GPU
APP_GPU_RECOMMENDATIONS = {
    "steam": GPUVendor.NVIDIA,
    "blender": GPUVendor.NVIDIA,
    "davinci-resolve": GPUVendor.NVIDIA,
    "chrome": GPUVendor.INTEL,
    "firefox": GPUVendor.INTEL,
    "code": GPUVendor.INTEL,
    "slack": GPUVendor.INTEL,
    "vlc": GPUVendor.INTEL,
    "kdenlive": GPUVendor.NVIDIA,
    "gimp": GPUVendor.INTEL,
}


class HybridGPUManager:
    """
    Manages hybrid GPU systems.

    Features:
    - Detect hybrid GPU configuration
    - Show current GPU state
    - Switch between GPU modes
    - Per-app GPU assignment
    - Battery impact estimates
    """

    PRIME_PROFILES = ["on-demand", "nvidia", "intel"]
    CONFIG_DIR = Path.home() / ".config" / "cortex" / "gpu"

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._state: GPUState | None = None

    def _run_command(self, cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
        """Run a command and return (returncode, stdout, stderr)."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode, result.stdout, result.stderr
        except FileNotFoundError:
            return 1, "", f"Command not found: {cmd[0]}"
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"

    def detect_gpus(self) -> list[GPUDevice]:
        """Detect all GPU devices in the system."""
        devices = []

        # Try lspci first
        returncode, stdout, _ = self._run_command(["lspci", "-nn"])
        if returncode == 0:
            for line in stdout.split("\n"):
                line_lower = line.lower()
                if "vga" in line_lower or "3d" in line_lower or "display" in line_lower:
                    device = self._parse_lspci_line(line)
                    if device:
                        devices.append(device)

        # Check for NVIDIA specifically
        nvidia_device = self._detect_nvidia_gpu()
        if nvidia_device:
            # Update or add NVIDIA device
            found = False
            for i, d in enumerate(devices):
                if d.vendor == GPUVendor.NVIDIA:
                    devices[i] = nvidia_device
                    found = True
                    break
            if not found:
                devices.append(nvidia_device)

        return devices

    def _parse_lspci_line(self, line: str) -> GPUDevice | None:
        """Parse an lspci output line for GPU info."""
        line_lower = line.lower()

        # Determine vendor
        if "nvidia" in line_lower:
            vendor = GPUVendor.NVIDIA
        elif "intel" in line_lower:
            vendor = GPUVendor.INTEL
        elif "amd" in line_lower or "ati" in line_lower or "radeon" in line_lower:
            vendor = GPUVendor.AMD
        else:
            vendor = GPUVendor.UNKNOWN

        # Extract PCI ID
        pci_match = re.match(r"^([0-9a-f:\.]+)", line, re.IGNORECASE)
        pci_id = pci_match.group(1) if pci_match else ""

        # Extract name (everything after the type)
        name_match = re.search(r"(?:VGA|3D|Display)[^:]*:\s*(.+?)(?:\s*\[|$)", line, re.IGNORECASE)
        name = name_match.group(1).strip() if name_match else line

        return GPUDevice(
            vendor=vendor,
            name=name,
            pci_id=pci_id,
        )

    def _detect_nvidia_gpu(self) -> GPUDevice | None:
        """Detect NVIDIA GPU with detailed info."""
        returncode, stdout, _ = self._run_command(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,power.draw",
                "--format=csv,noheader,nounits",
            ]
        )

        if returncode != 0 or not stdout.strip():
            return None

        parts = stdout.strip().split(",")
        name = parts[0].strip() if len(parts) > 0 else "NVIDIA GPU"
        memory = int(float(parts[1].strip())) if len(parts) > 1 else 0

        # Check power state
        power_returncode, power_stdout, _ = self._run_command(
            ["cat", "/sys/bus/pci/devices/0000:01:00.0/power/runtime_status"]
        )
        power_state = power_stdout.strip() if power_returncode == 0 else "unknown"

        return GPUDevice(
            vendor=GPUVendor.NVIDIA,
            name=name,
            driver="nvidia",
            memory_mb=memory,
            power_state=power_state,
            is_active=power_state == "active",
        )

    def detect_mode(self) -> GPUMode:
        """Detect current GPU mode."""
        # Check for PRIME profile
        returncode, stdout, _ = self._run_command(["prime-select", "query"])
        if returncode == 0:
            profile = stdout.strip().lower()
            if profile == "nvidia":
                return GPUMode.NVIDIA
            elif profile == "intel" or profile == "integrated":
                return GPUMode.INTEGRATED
            elif profile == "on-demand":
                return GPUMode.HYBRID

        # Check envycontrol if available
        returncode, stdout, _ = self._run_command(["envycontrol", "--query"])
        if returncode == 0:
            mode = stdout.strip().lower()
            if "nvidia" in mode:
                return GPUMode.NVIDIA
            elif "integrated" in mode:
                return GPUMode.INTEGRATED
            elif "hybrid" in mode:
                return GPUMode.HYBRID

        # Check system76-power if available
        returncode, stdout, _ = self._run_command(["system76-power", "graphics"])
        if returncode == 0:
            mode = stdout.strip().lower()
            if "nvidia" in mode:
                return GPUMode.NVIDIA
            elif "integrated" in mode or "intel" in mode:
                return GPUMode.INTEGRATED
            elif "hybrid" in mode:
                return GPUMode.HYBRID

        return GPUMode.UNKNOWN

    def get_state(self, refresh: bool = False) -> GPUState:
        """Get current GPU system state."""
        if self._state and not refresh:
            return self._state

        state = GPUState()
        state.devices = self.detect_gpus()
        state.mode = self.detect_mode()

        # Find active GPU
        for device in state.devices:
            if device.is_active or (
                state.mode == GPUMode.NVIDIA and device.vendor == GPUVendor.NVIDIA
            ):
                state.active_gpu = device
                break
            elif state.mode == GPUMode.INTEGRATED and device.vendor in [
                GPUVendor.INTEL,
                GPUVendor.AMD,
            ]:
                state.active_gpu = device
                break

        # Check for render offload availability
        returncode, _, _ = self._run_command(["which", "__NV_PRIME_RENDER_OFFLOAD"])
        state.render_offload_available = returncode == 0 or state.mode == GPUMode.HYBRID

        self._state = state
        return state

    def switch_mode(self, mode: GPUMode, apply: bool = False) -> tuple[bool, str, str | None]:
        """
        Switch GPU mode.

        Args:
            mode: Target GPU mode
            apply: If True, actually switch (requires sudo)

        Returns:
            Tuple of (success, message, command_to_run)
        """
        state = self.get_state()

        if not state.is_hybrid_system:
            return False, "Not a hybrid GPU system", None

        # Determine the command to use
        command = None

        # Try prime-select
        returncode, _, _ = self._run_command(["which", "prime-select"])
        if returncode == 0:
            mode_map = {
                GPUMode.NVIDIA: "nvidia",
                GPUMode.INTEGRATED: "intel",
                GPUMode.HYBRID: "on-demand",
            }
            if mode in mode_map:
                command = f"sudo prime-select {mode_map[mode]}"

        # Try envycontrol
        if not command:
            returncode, _, _ = self._run_command(["which", "envycontrol"])
            if returncode == 0:
                mode_map = {
                    GPUMode.NVIDIA: "--nvidia",
                    GPUMode.INTEGRATED: "--integrated",
                    GPUMode.HYBRID: "--hybrid",
                }
                if mode in mode_map:
                    command = f"sudo envycontrol -s {mode_map[mode]}"

        # Try system76-power
        if not command:
            returncode, _, _ = self._run_command(["which", "system76-power"])
            if returncode == 0:
                mode_map = {
                    GPUMode.NVIDIA: "nvidia",
                    GPUMode.INTEGRATED: "integrated",
                    GPUMode.HYBRID: "hybrid",
                }
                if mode in mode_map:
                    command = f"sudo system76-power graphics {mode_map[mode]}"

        if not command:
            return (
                False,
                "No GPU switching tool found. Install prime-select, envycontrol, or system76-power.",
                None,
            )

        if apply:
            # Actually run the command (would need sudo)
            return False, "Switching requires sudo. Run the command manually.", command
        else:
            return True, f"To switch to {mode.value} mode, run:", command

    def get_app_launch_command(self, app: str, use_nvidia: bool = True) -> str:
        """
        Get command to launch an app with specific GPU.

        Args:
            app: Application name or command
            use_nvidia: If True, use NVIDIA GPU

        Returns:
            Launch command with appropriate environment
        """
        state = self.get_state()

        if not state.is_hybrid_system:
            return app

        if state.mode == GPUMode.NVIDIA:
            # Already on NVIDIA
            return app

        if use_nvidia:
            # Use PRIME render offload
            if state.render_offload_available:
                return f"__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia {app}"
            else:
                return f"DRI_PRIME=1 {app}"
        else:
            # Use integrated GPU
            return f"DRI_PRIME=0 {app}"

    def get_battery_estimate(self, mode: GPUMode) -> dict[str, str]:
        """Get battery impact estimate for a mode."""
        return BATTERY_IMPACT.get(mode, {"description": "Unknown", "impact": "Unknown"})

    def display_status(self):
        """Display current GPU status with rich formatting."""
        state = self.get_state(refresh=True)

        cx_header("GPU Status")

        if not state.devices:
            cx_print("No GPUs detected", "warning")
            return

        # GPU devices table
        table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style=CORTEX_CYAN,
            box=box.ROUNDED,
        )
        table.add_column("GPU", style="cyan")
        table.add_column("Vendor", style="white")
        table.add_column("Status", style="green")
        table.add_column("Memory", style="white")

        for device in state.devices:
            vendor_str = device.vendor.value.upper()

            if device.is_active or device.power_state == "active":
                status = "[green]● Active[/green]"
            elif device.power_state == "suspended":
                status = "[yellow]○ Suspended[/yellow]"
            else:
                status = "[dim]○ Idle[/dim]"

            memory = f"{device.memory_mb} MB" if device.memory_mb else "N/A"

            table.add_row(device.name[:40], vendor_str, status, memory)

        console.print(table)
        console.print()

        # Current mode
        mode_colors = {
            GPUMode.INTEGRATED: "green",
            GPUMode.HYBRID: "cyan",
            GPUMode.NVIDIA: "yellow",
            GPUMode.COMPUTE: "blue",
            GPUMode.UNKNOWN: "red",
        }
        mode_color = mode_colors.get(state.mode, "white")

        mode_info = self.get_battery_estimate(state.mode)
        mode_panel = f"""[bold]Current Mode:[/bold] [{mode_color}]{state.mode.value.upper()}[/{mode_color}]

[dim]{mode_info['description']}[/dim]
Battery Impact: {mode_info['impact']}
"""
        console.print(
            Panel(
                mode_panel,
                title="[bold cyan]GPU Mode[/bold cyan]",
                border_style=CORTEX_CYAN,
                padding=(1, 2),
            )
        )

        if state.is_hybrid_system:
            console.print()
            console.print("[bold]Hybrid GPU System Detected[/bold]")
            console.print("[dim]Use 'cortex gpu switch <mode>' to change modes[/dim]")

    def display_modes(self):
        """Display available GPU modes with descriptions."""
        cx_header("Available GPU Modes")

        table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style=CORTEX_CYAN,
            box=box.ROUNDED,
        )
        table.add_column("Mode", style="cyan", width=12)
        table.add_column("Description", style="white", width=30)
        table.add_column("Battery", style="green", width=15)
        table.add_column("Best For", style="dim", width=25)

        modes_info = [
            (GPUMode.INTEGRATED, "Uses Intel/AMD only", "Best", "Web browsing, office work"),
            (GPUMode.HYBRID, "Auto-switches per app", "Good", "Mixed workloads"),
            (GPUMode.NVIDIA, "NVIDIA always on", "Low", "Gaming, 3D, ML"),
            (GPUMode.COMPUTE, "NVIDIA for compute", "Medium", "ML training, rendering"),
        ]

        for mode, desc, battery, best_for in modes_info:
            table.add_row(mode.value.upper(), desc, battery, best_for)

        console.print(table)

    def display_app_recommendations(self):
        """Display per-app GPU recommendations."""
        cx_header("App GPU Recommendations")

        table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style=CORTEX_CYAN,
            box=box.ROUNDED,
        )
        table.add_column("Application", style="cyan")
        table.add_column("Recommended GPU", style="white")
        table.add_column("Launch Command", style="dim")

        state = self.get_state()

        for app, gpu in APP_GPU_RECOMMENDATIONS.items():
            gpu_str = gpu.value.upper()
            if gpu == GPUVendor.NVIDIA:
                launch_cmd = self.get_app_launch_command(app, use_nvidia=True)
                gpu_str = f"[yellow]{gpu_str}[/yellow]"
            else:
                launch_cmd = app
                gpu_str = f"[green]{gpu_str}[/green]"

            # Truncate launch command if too long
            if len(launch_cmd) > 50:
                launch_cmd = launch_cmd[:47] + "..."

            table.add_row(app, gpu_str, launch_cmd)

        console.print(table)


def run_gpu_manager(action: str = "status", mode: str | None = None, verbose: bool = False) -> int:
    """
    Main entry point for cortex gpu command.

    Args:
        action: One of "status", "modes", "switch", "apps"
        mode: Target mode for switch action
        verbose: Verbose output

    Returns:
        Exit code
    """
    manager = HybridGPUManager(verbose=verbose)

    if action == "status":
        manager.display_status()
    elif action == "modes":
        manager.display_modes()
    elif action == "apps":
        manager.display_app_recommendations()
    elif action == "switch":
        if not mode:
            cx_print("Specify a mode: integrated, hybrid, nvidia", "error")
            return 1

        mode_map = {
            "integrated": GPUMode.INTEGRATED,
            "hybrid": GPUMode.HYBRID,
            "nvidia": GPUMode.NVIDIA,
            "compute": GPUMode.COMPUTE,
        }

        target_mode = mode_map.get(mode.lower())
        if not target_mode:
            cx_print(f"Unknown mode: {mode}. Use: integrated, hybrid, nvidia", "error")
            return 1

        success, message, command = manager.switch_mode(target_mode)
        if success:
            cx_print(message, "info")
            if command:
                console.print(f"\n[bold cyan]{command}[/bold cyan]\n")
                cx_print("A reboot is required after switching.", "warning")
        else:
            cx_print(message, "error")
            if command:
                console.print(f"\n[bold cyan]{command}[/bold cyan]\n")
            return 1
    else:
        cx_print(f"Unknown action: {action}", "error")
        return 1

    return 0
