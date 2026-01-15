"""
WiFi/Bluetooth Driver Auto-Matcher

Issue: #444 - WiFi/Bluetooth Driver Auto-Matcher

Identifies wireless hardware, searches driver database,
installs appropriate drivers, and validates connectivity.
"""

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class DeviceType(Enum):
    """Type of wireless device."""

    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    COMBO = "combo"  # Combined WiFi + Bluetooth


class ConnectionType(Enum):
    """Hardware connection type."""

    PCI = "pci"
    USB = "usb"
    SDIO = "sdio"


class DriverSource(Enum):
    """Source of driver package."""

    KERNEL = "kernel"  # Built into kernel
    DKMS = "dkms"  # DKMS module
    PACKAGE = "package"  # Distribution package
    MANUAL = "manual"  # Manual compilation required


@dataclass
class WirelessDevice:
    """Represents a detected wireless device."""

    name: str
    device_type: DeviceType
    connection: ConnectionType
    vendor_id: str = ""
    device_id: str = ""
    vendor: str = ""
    driver_loaded: str = ""
    is_working: bool = False


@dataclass
class DriverInfo:
    """Information about a driver."""

    name: str
    package: str = ""
    source: DriverSource = DriverSource.PACKAGE
    git_url: str = ""
    supported_ids: list = field(default_factory=list)
    notes: str = ""


# Driver database for common problematic chips
DRIVER_DATABASE = {
    # Realtek WiFi
    "rtl8821ce": DriverInfo(
        name="RTL8821CE",
        package="rtl8821ce-dkms",
        source=DriverSource.DKMS,
        git_url="https://github.com/tomaspinho/rtl8821ce",
        supported_ids=[("10ec", "c821"), ("10ec", "c82f")],
        notes="Common in budget laptops",
    ),
    "rtl8822be": DriverInfo(
        name="RTL8822BE",
        package="rtw88-dkms",
        source=DriverSource.DKMS,
        supported_ids=[("10ec", "b822")],
        notes="Uses rtw88 driver",
    ),
    "rtl8822ce": DriverInfo(
        name="RTL8822CE",
        package="rtw88-dkms",
        source=DriverSource.DKMS,
        supported_ids=[("10ec", "c822")],
        notes="Uses rtw88 driver",
    ),
    "rtl8852ae": DriverInfo(
        name="RTL8852AE",
        package="rtw89-dkms",
        source=DriverSource.DKMS,
        git_url="https://github.com/lwfinger/rtw89",
        supported_ids=[("10ec", "8852")],
        notes="WiFi 6 chip",
    ),
    "rtl8852be": DriverInfo(
        name="RTL8852BE",
        package="rtw89-dkms",
        source=DriverSource.DKMS,
        git_url="https://github.com/lwfinger/rtw89",
        supported_ids=[("10ec", "b852")],
        notes="WiFi 6 chip",
    ),
    # Mediatek WiFi
    "mt7921": DriverInfo(
        name="MT7921",
        package="linux-firmware",
        source=DriverSource.KERNEL,
        supported_ids=[("14c3", "7961")],
        notes="Kernel 5.12+ required",
    ),
    "mt7922": DriverInfo(
        name="MT7922",
        package="linux-firmware",
        source=DriverSource.KERNEL,
        supported_ids=[("14c3", "0616")],
        notes="Kernel 5.18+ required",
    ),
    # Intel WiFi
    "iwlwifi": DriverInfo(
        name="Intel Wireless",
        package="linux-firmware",
        source=DriverSource.KERNEL,
        supported_ids=[("8086", "2723"), ("8086", "2725"), ("8086", "a0f0")],
        notes="Standard kernel driver",
    ),
    # Broadcom
    "bcm4350": DriverInfo(
        name="Broadcom BCM4350",
        package="broadcom-sta-dkms",
        source=DriverSource.DKMS,
        supported_ids=[("14e4", "43a3")],
        notes="Proprietary driver",
    ),
    # Atheros
    "ath11k": DriverInfo(
        name="Atheros 11k",
        package="linux-firmware",
        source=DriverSource.KERNEL,
        supported_ids=[("17cb", "1103")],
        notes="WiFi 6 Qualcomm/Atheros",
    ),
}

# Bluetooth drivers
BLUETOOTH_DRIVERS = {
    "btrtl": DriverInfo(
        name="Realtek Bluetooth",
        package="linux-firmware",
        source=DriverSource.KERNEL,
        notes="Realtek USB Bluetooth",
    ),
    "btmtk": DriverInfo(
        name="Mediatek Bluetooth",
        package="linux-firmware",
        source=DriverSource.KERNEL,
        notes="Mediatek USB Bluetooth",
    ),
    "btintel": DriverInfo(
        name="Intel Bluetooth",
        package="linux-firmware",
        source=DriverSource.KERNEL,
        notes="Intel USB Bluetooth",
    ),
    "btbcm": DriverInfo(
        name="Broadcom Bluetooth",
        package="linux-firmware",
        source=DriverSource.KERNEL,
        notes="Broadcom USB Bluetooth",
    ),
}


class WirelessDriverMatcher:
    """Matches wireless hardware to appropriate drivers."""

    def __init__(self, verbose: bool = False):
        """Initialize the driver matcher."""
        self.verbose = verbose
        self.devices: list[WirelessDevice] = []

    def _run_command(self, cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
        """Run a command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"
        except FileNotFoundError:
            return 1, "", f"Command not found: {cmd[0]}"
        except Exception as e:
            return 1, "", str(e)

    def _detect_vendor(self, name: str) -> str:
        """Detect vendor from device name."""
        name_lower = name.lower()
        vendors = {
            "realtek": ["realtek", "rtl"],
            "intel": ["intel", "wireless-ac", "wifi 6"],
            "mediatek": ["mediatek", "mt7"],
            "broadcom": ["broadcom", "bcm"],
            "atheros": ["atheros", "qualcomm", "ath"],
            "ralink": ["ralink", "rt28", "rt38"],
        }
        for vendor, patterns in vendors.items():
            for pattern in patterns:
                if pattern in name_lower:
                    return vendor
        return "unknown"

    def detect_pci_devices(self) -> list[WirelessDevice]:
        """Detect PCI wireless devices using lspci."""
        devices = []

        # Get network controllers
        code, output, _ = self._run_command(["lspci", "-nn", "-D"])
        if code != 0:
            return devices

        # Parse for network controllers
        for line in output.splitlines():
            if "network" in line.lower() or "wireless" in line.lower():
                # Extract vendor:device ID
                match = re.search(r"\[([0-9a-f]{4}):([0-9a-f]{4})\]", line.lower())
                if match:
                    vendor_id, device_id = match.groups()

                    # Determine device type
                    device_type = DeviceType.WIFI
                    if "bluetooth" in line.lower():
                        device_type = DeviceType.BLUETOOTH

                    # Get driver info
                    driver = ""
                    pci_addr = line.split()[0] if line.split() else ""
                    if pci_addr:
                        _, drv_out, _ = self._run_command(["lspci", "-k", "-s", pci_addr])
                        drv_match = re.search(r"Kernel driver in use:\s*(\S+)", drv_out)
                        if drv_match:
                            driver = drv_match.group(1)

                    # Clean device name
                    name = line.split(":", 2)[-1].strip() if ":" in line else line

                    device = WirelessDevice(
                        name=name,
                        device_type=device_type,
                        connection=ConnectionType.PCI,
                        vendor_id=vendor_id,
                        device_id=device_id,
                        vendor=self._detect_vendor(name),
                        driver_loaded=driver,
                        is_working=bool(driver),
                    )
                    devices.append(device)

        return devices

    def detect_usb_devices(self) -> list[WirelessDevice]:
        """Detect USB wireless devices using lsusb."""
        devices = []

        code, output, _ = self._run_command(["lsusb"])
        if code != 0:
            return devices

        # Known USB wireless vendor IDs
        wireless_vendors = {
            "0bda": "realtek",
            "0cf3": "atheros",
            "0e8d": "mediatek",
            "8087": "intel",
            "0a5c": "broadcom",
            "148f": "ralink",
        }

        for line in output.splitlines():
            match = re.search(r"id\s+([0-9a-f]{4}):([0-9a-f]{4})", line.lower())
            if match:
                vendor_id, device_id = match.groups()
                if vendor_id in wireless_vendors:
                    # Determine if WiFi or Bluetooth
                    device_type = DeviceType.WIFI
                    if "bluetooth" in line.lower():
                        device_type = DeviceType.BLUETOOTH

                    name = line.split(":", 1)[-1].strip() if ":" in line else line

                    device = WirelessDevice(
                        name=name,
                        device_type=device_type,
                        connection=ConnectionType.USB,
                        vendor_id=vendor_id,
                        device_id=device_id,
                        vendor=wireless_vendors[vendor_id],
                    )
                    devices.append(device)

        return devices

    def detect_all_devices(self) -> list[WirelessDevice]:
        """Detect all wireless devices."""
        self.devices = []
        self.devices.extend(self.detect_pci_devices())
        self.devices.extend(self.detect_usb_devices())
        return self.devices

    def find_driver(self, device: WirelessDevice) -> DriverInfo | None:
        """Find appropriate driver for a device."""
        # Check by vendor:device ID
        for driver_name, driver in DRIVER_DATABASE.items():
            for vid, did in driver.supported_ids:
                if device.vendor_id == vid and device.device_id == did:
                    return driver

        # Check Bluetooth drivers
        if device.device_type == DeviceType.BLUETOOTH:
            vendor_bt_map = {
                "realtek": "btrtl",
                "intel": "btintel",
                "broadcom": "btbcm",
                "mediatek": "btmtk",
            }
            if device.vendor in vendor_bt_map:
                return BLUETOOTH_DRIVERS.get(vendor_bt_map[device.vendor])

        return None

    def check_connectivity(self) -> dict:
        """Check WiFi and Bluetooth connectivity status."""
        status = {
            "wifi_interface": None,
            "wifi_connected": False,
            "wifi_ssid": None,
            "bluetooth_available": False,
            "bluetooth_powered": False,
        }

        # Check WiFi
        code, output, _ = self._run_command(["ip", "link", "show"])
        if code == 0:
            for line in output.splitlines():
                if "wl" in line and "state UP" in line:
                    match = re.search(r"^\d+:\s+(\w+):", line)
                    if match:
                        status["wifi_interface"] = match.group(1)
                        status["wifi_connected"] = True

        # Get SSID if connected
        if status["wifi_connected"]:
            code, output, _ = self._run_command(["iwgetid", "-r"])
            if code == 0 and output.strip():
                status["wifi_ssid"] = output.strip()

        # Check Bluetooth
        code, output, _ = self._run_command(["bluetoothctl", "show"])
        if code == 0:
            status["bluetooth_available"] = True
            if "Powered: yes" in output:
                status["bluetooth_powered"] = True

        return status

    def get_install_commands(self, driver: DriverInfo) -> list[str]:
        """Get commands to install a driver."""
        commands = []

        if driver.source == DriverSource.PACKAGE:
            commands.append(f"sudo apt install -y {driver.package}")
        elif driver.source == DriverSource.DKMS:
            if driver.git_url:
                commands.extend(
                    [
                        f"git clone {driver.git_url}",
                        f"cd {driver.name.lower()} && sudo ./dkms-install.sh",
                    ]
                )
            else:
                commands.append(f"sudo apt install -y {driver.package}")
        elif driver.source == DriverSource.KERNEL:
            commands.append(f"sudo apt install -y {driver.package}")
            commands.append("sudo update-initramfs -u")

        return commands

    def install_driver(self, driver: DriverInfo) -> tuple[bool, str]:
        """Install a driver package."""
        if driver.source == DriverSource.PACKAGE or driver.source == DriverSource.KERNEL:
            code, _, stderr = self._run_command(
                ["sudo", "apt", "install", "-y", driver.package],
                timeout=300,
            )
            if code != 0:
                return False, f"Failed to install {driver.package}: {stderr}"
            return True, f"Installed {driver.package}"

        elif driver.source == DriverSource.DKMS:
            if driver.git_url:
                return False, f"Manual installation required: {driver.git_url}"
            else:
                code, _, stderr = self._run_command(
                    ["sudo", "apt", "install", "-y", driver.package],
                    timeout=300,
                )
                if code != 0:
                    return False, f"Failed to install {driver.package}: {stderr}"
                return True, f"Installed DKMS module {driver.package}"

        return False, "Unknown driver source"

    def display_status(self):
        """Display wireless device status."""
        self.detect_all_devices()
        connectivity = self.check_connectivity()

        # Connectivity status
        console.print(
            Panel(
                "[bold]Wireless Connectivity Status[/bold]",
                style="cyan",
            )
        )

        conn_table = Table(show_header=False, box=None)
        conn_table.add_column("Item", style="cyan")
        conn_table.add_column("Value")

        wifi_status = (
            "[green]Connected[/green]"
            if connectivity["wifi_connected"]
            else "[red]Not connected[/red]"
        )
        if connectivity["wifi_ssid"]:
            wifi_status += f" ({connectivity['wifi_ssid']})"
        conn_table.add_row("WiFi", wifi_status)

        bt_status = (
            "[green]Available[/green]"
            if connectivity["bluetooth_available"]
            else "[red]Not available[/red]"
        )
        if connectivity["bluetooth_powered"]:
            bt_status += " (Powered)"
        conn_table.add_row("Bluetooth", bt_status)

        console.print(conn_table)
        console.print()

        # Devices table
        console.print(
            Panel(
                "[bold]Detected Wireless Devices[/bold]",
                style="cyan",
            )
        )

        if not self.devices:
            console.print("[yellow]No wireless devices detected[/yellow]")
            return

        table = Table()
        table.add_column("Device", style="white")
        table.add_column("Type", style="cyan")
        table.add_column("Vendor", style="blue")
        table.add_column("Driver", style="green")
        table.add_column("Status", style="yellow")

        for device in self.devices:
            driver = self.find_driver(device)
            driver_name = driver.name if driver else device.driver_loaded or "Unknown"

            status = "[green]Working[/green]" if device.is_working else "[red]No driver[/red]"
            if driver and not device.is_working:
                status = "[yellow]Driver available[/yellow]"

            # Truncate long names
            name = device.name[:40] + "..." if len(device.name) > 40 else device.name

            table.add_row(
                name,
                device.device_type.value,
                device.vendor,
                driver_name,
                status,
            )

        console.print(table)

    def display_recommendations(self):
        """Display driver recommendations for problematic devices."""
        self.detect_all_devices()

        devices_needing_drivers = [d for d in self.devices if not d.is_working]

        if not devices_needing_drivers:
            console.print("[green]All wireless devices have working drivers[/green]")
            return

        console.print(
            Panel(
                "[bold]Driver Recommendations[/bold]",
                style="yellow",
            )
        )

        for device in devices_needing_drivers:
            driver = self.find_driver(device)

            if driver:
                console.print(f"\n[bold]{device.name}[/bold]")
                console.print(f"  Recommended driver: [cyan]{driver.name}[/cyan]")
                console.print(f"  Package: [green]{driver.package}[/green]")
                console.print(f"  Source: {driver.source.value}")
                if driver.notes:
                    console.print(f"  Notes: {driver.notes}")

                console.print("\n  Install commands:")
                for cmd in self.get_install_commands(driver):
                    console.print(f"    [dim]$ {cmd}[/dim]")
            else:
                console.print(f"\n[bold]{device.name}[/bold]")
                console.print("  [red]No known driver available[/red]")
                console.print(f"  Vendor ID: {device.vendor_id}")
                console.print(f"  Device ID: {device.device_id}")
                console.print("  Try searching: linux-hardware.org or wikidevi.wi-cat.ru")


def run_wifi_driver(
    action: str = "status",
    verbose: bool = False,
) -> int:
    """Run WiFi/Bluetooth driver matcher.

    Args:
        action: Action to perform (status, detect, recommend, install)
        verbose: Enable verbose output

    Returns:
        Exit code (0 for success)
    """
    matcher = WirelessDriverMatcher(verbose=verbose)

    if action == "status":
        matcher.display_status()
        return 0

    elif action == "detect":
        devices = matcher.detect_all_devices()
        if devices:
            console.print(f"[green]Found {len(devices)} wireless device(s)[/green]")
            for d in devices:
                console.print(f"  - {d.name} ({d.device_type.value})")
        else:
            console.print("[yellow]No wireless devices detected[/yellow]")
        return 0

    elif action == "recommend":
        matcher.display_recommendations()
        return 0

    elif action == "install":
        devices = matcher.detect_all_devices()
        devices_needing_drivers = [d for d in devices if not d.is_working]

        if not devices_needing_drivers:
            console.print("[green]All devices have working drivers[/green]")
            return 0

        for device in devices_needing_drivers:
            driver = matcher.find_driver(device)
            if driver:
                console.print(f"Installing driver for {device.name}...")
                success, message = matcher.install_driver(driver)
                if success:
                    console.print(f"[green]{message}[/green]")
                else:
                    console.print(f"[red]{message}[/red]")

        return 0

    elif action == "connectivity":
        status = matcher.check_connectivity()
        console.print(f"WiFi: {'Connected' if status['wifi_connected'] else 'Not connected'}")
        if status["wifi_ssid"]:
            console.print(f"  SSID: {status['wifi_ssid']}")
        console.print(
            f"Bluetooth: {'Available' if status['bluetooth_available'] else 'Not available'}"
        )
        return 0

    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Available actions: status, detect, recommend, install, connectivity")
        return 1
