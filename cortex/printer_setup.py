"""
Cortex Printer/Scanner Auto-Setup Module

Automatically detects, configures, and tests printers and scanners.

Issue: #451
"""

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cortex.branding import CORTEX_CYAN, console, cx_header, cx_print


class DeviceType(Enum):
    """Type of printing device."""

    PRINTER = "printer"
    SCANNER = "scanner"
    MULTIFUNCTION = "multifunction"
    UNKNOWN = "unknown"


class ConnectionType(Enum):
    """Device connection type."""

    USB = "usb"
    NETWORK = "network"
    BLUETOOTH = "bluetooth"
    UNKNOWN = "unknown"


@dataclass
class PrinterDevice:
    """Represents a detected printer/scanner device."""

    name: str
    device_type: DeviceType
    connection: ConnectionType
    uri: str = ""
    vendor: str = ""
    model: str = ""
    driver: str = ""
    is_configured: bool = False
    is_default: bool = False
    state: str = "unknown"
    usb_id: str = ""  # vendor:product


@dataclass
class DriverInfo:
    """Printer driver information."""

    name: str
    ppd_path: str = ""
    recommended: bool = False
    source: str = ""  # cups, gutenprint, hplip, etc.


# Common driver packages for different vendors
DRIVER_PACKAGES = {
    "hp": ["hplip", "hplip-gui"],
    "epson": ["epson-inkjet-printer-escpr", "epson-inkjet-printer-escpr2"],
    "canon": ["cnijfilter2"],
    "brother": ["brother-driver-printer"],
    "samsung": ["samsung-unified-driver"],
    "xerox": ["xerox-phaser-drivers"],
    "lexmark": ["lexmark-driver"],
}

# Scanner driver packages
SCANNER_PACKAGES = {
    "hp": ["hplip", "sane-airscan"],
    "epson": ["imagescan-plugin-networkscan", "sane-airscan"],
    "canon": ["scangearmp2", "sane-airscan"],
    "brother": ["brscan4", "sane-airscan"],
    "generic": ["sane", "sane-airscan", "simple-scan"],
}


class PrinterSetup:
    """
    Automatic printer and scanner setup.

    Features:
    - Detect USB and network printers
    - Identify correct drivers
    - Configure via CUPS
    - Test print and scan functions
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._cups_available = self._check_cups()
        self._sane_available = self._check_sane()

    def _run_command(self, cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
        """Run a command and return (returncode, stdout, stderr)."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except FileNotFoundError:
            return 1, "", f"Command not found: {cmd[0]}"
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"

    def _check_cups(self) -> bool:
        """Check if CUPS is available."""
        returncode, _, _ = self._run_command(["which", "lpstat"])
        return returncode == 0

    def _check_sane(self) -> bool:
        """Check if SANE is available."""
        returncode, _, _ = self._run_command(["which", "scanimage"])
        return returncode == 0

    def detect_usb_printers(self) -> list[PrinterDevice]:
        """Detect USB-connected printers."""
        devices = []

        # Try lsusb
        returncode, stdout, _ = self._run_command(["lsusb"])
        if returncode != 0:
            return devices

        # Parse lsusb output for printers
        printer_keywords = ["printer", "mfp", "print", "scan", "hp ", "canon", "epson", "brother"]

        for line in stdout.split("\n"):
            line_lower = line.lower()
            if any(kw in line_lower for kw in printer_keywords):
                # Extract vendor:product ID
                id_match = re.search(r"ID ([0-9a-f]{4}):([0-9a-f]{4})", line, re.IGNORECASE)
                if id_match:
                    usb_id = f"{id_match.group(1)}:{id_match.group(2)}"

                    # Extract name
                    name_match = re.search(r"ID [0-9a-f:]+\s+(.+)$", line, re.IGNORECASE)
                    name = name_match.group(1).strip() if name_match else "USB Printer"

                    # Determine vendor
                    vendor = self._detect_vendor(name)

                    # Determine device type
                    if "scan" in line_lower or "mfp" in line_lower:
                        device_type = DeviceType.MULTIFUNCTION
                    else:
                        device_type = DeviceType.PRINTER

                    devices.append(PrinterDevice(
                        name=name,
                        device_type=device_type,
                        connection=ConnectionType.USB,
                        vendor=vendor,
                        usb_id=usb_id,
                    ))

        return devices

    def detect_network_printers(self) -> list[PrinterDevice]:
        """Detect network printers using CUPS and DNS-SD."""
        devices = []

        if not self._cups_available:
            return devices

        # Try lpinfo for network printers
        returncode, stdout, _ = self._run_command(["lpinfo", "-v"], timeout=15)
        if returncode == 0:
            for line in stdout.split("\n"):
                if "ipp://" in line or "socket://" in line or "dnssd://" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        uri = parts[1]
                        name = uri.split("/")[-1] if "/" in uri else uri

                        devices.append(PrinterDevice(
                            name=name,
                            device_type=DeviceType.PRINTER,
                            connection=ConnectionType.NETWORK,
                            uri=uri,
                            vendor=self._detect_vendor(name),
                        ))

        return devices

    def detect_configured_printers(self) -> list[PrinterDevice]:
        """Get list of already configured printers."""
        devices = []

        if not self._cups_available:
            return devices

        # Get configured printers
        returncode, stdout, _ = self._run_command(["lpstat", "-p", "-d"])
        if returncode != 0:
            return devices

        default_printer = ""
        for line in stdout.split("\n"):
            if "system default destination:" in line.lower():
                default_printer = line.split(":")[-1].strip()

        # Parse printer status
        for line in stdout.split("\n"):
            if line.startswith("printer "):
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[1]
                    state = "idle" if "is idle" in line else "printing" if "printing" in line else "disabled" if "disabled" in line else "unknown"

                    devices.append(PrinterDevice(
                        name=name,
                        device_type=DeviceType.PRINTER,
                        connection=ConnectionType.UNKNOWN,
                        is_configured=True,
                        is_default=name == default_printer,
                        state=state,
                    ))

        return devices

    def detect_scanners(self) -> list[PrinterDevice]:
        """Detect scanners using SANE."""
        devices = []

        if not self._sane_available:
            return devices

        # Try scanimage to list devices
        returncode, stdout, _ = self._run_command(["scanimage", "-L"], timeout=30)
        if returncode == 0:
            for line in stdout.split("\n"):
                if "device" in line.lower():
                    # Parse device line: device `epson2:net:192.168.1.100' is a Epson Scanner
                    match = re.search(r"device `([^']+)'.*is a (.+)$", line, re.IGNORECASE)
                    if match:
                        uri = match.group(1)
                        name = match.group(2).strip()

                        connection = ConnectionType.USB
                        if "net:" in uri or "airscan:" in uri:
                            connection = ConnectionType.NETWORK

                        devices.append(PrinterDevice(
                            name=name,
                            device_type=DeviceType.SCANNER,
                            connection=connection,
                            uri=uri,
                            vendor=self._detect_vendor(name),
                            is_configured=True,
                        ))

        return devices

    def _detect_vendor(self, name: str) -> str:
        """Detect vendor from device name."""
        name_lower = name.lower()
        vendors = {
            "hp": ["hp ", "hewlett", "laserjet", "officejet", "deskjet", "envy"],
            "epson": ["epson"],
            "canon": ["canon", "pixma", "imageclass"],
            "brother": ["brother", "mfc-", "hl-", "dcp-"],
            "samsung": ["samsung", "xpress"],
            "xerox": ["xerox", "phaser", "workcentre"],
            "lexmark": ["lexmark"],
            "ricoh": ["ricoh"],
            "kyocera": ["kyocera"],
        }

        for vendor, keywords in vendors.items():
            if any(kw in name_lower for kw in keywords):
                return vendor

        return "generic"

    def find_driver(self, device: PrinterDevice) -> DriverInfo | None:
        """Find the best driver for a device."""
        if not self._cups_available:
            return None

        # Try lpinfo to find drivers
        search_terms = [device.vendor, device.model, device.name]
        search_terms = [t for t in search_terms if t]

        for term in search_terms:
            returncode, stdout, _ = self._run_command(["lpinfo", "-m"])
            if returncode == 0:
                for line in stdout.split("\n"):
                    if term.lower() in line.lower():
                        parts = line.split(maxsplit=1)
                        if len(parts) >= 2:
                            return DriverInfo(
                                name=parts[1],
                                ppd_path=parts[0],
                                recommended=True,
                                source="cups",
                            )

        # Return generic driver if nothing specific found
        return DriverInfo(
            name="Generic PostScript Printer",
            ppd_path="drv:///sample.drv/generic.ppd",
            recommended=False,
            source="cups-generic",
        )

    def get_driver_packages(self, device: PrinterDevice) -> list[str]:
        """Get recommended driver packages for a device."""
        packages = []

        vendor = device.vendor.lower() if device.vendor else "generic"

        if device.device_type in [DeviceType.PRINTER, DeviceType.MULTIFUNCTION]:
            packages.extend(DRIVER_PACKAGES.get(vendor, []))

        if device.device_type in [DeviceType.SCANNER, DeviceType.MULTIFUNCTION]:
            packages.extend(SCANNER_PACKAGES.get(vendor, SCANNER_PACKAGES["generic"]))

        return list(set(packages))

    def setup_printer(
        self,
        device: PrinterDevice,
        driver: DriverInfo | None = None,
        make_default: bool = False,
    ) -> tuple[bool, str]:
        """
        Set up a printer with CUPS.

        Args:
            device: Printer device to set up
            driver: Driver to use (auto-detected if not provided)
            make_default: Make this the default printer

        Returns:
            Tuple of (success, message)
        """
        if not self._cups_available:
            return False, "CUPS is not installed. Install cups package first."

        if not driver:
            driver = self.find_driver(device)

        if not driver:
            return False, f"Could not find driver for {device.name}"

        # Generate a safe printer name
        printer_name = re.sub(r'[^a-zA-Z0-9_-]', '_', device.name)[:30]

        # Determine URI
        uri = device.uri
        if not uri and device.connection == ConnectionType.USB:
            # Try to find USB URI
            returncode, stdout, _ = self._run_command(["lpinfo", "-v"])
            if returncode == 0:
                for line in stdout.split("\n"):
                    if "usb://" in line and device.vendor.lower() in line.lower():
                        uri = line.split()[-1]
                        break

        if not uri:
            return False, f"Could not determine device URI for {device.name}"

        # Add printer
        cmd = [
            "lpadmin",
            "-p", printer_name,
            "-v", uri,
            "-m", driver.ppd_path,
            "-E",  # Enable
        ]

        returncode, _, stderr = self._run_command(cmd)
        if returncode != 0:
            return False, f"Failed to add printer: {stderr}"

        # Set as default if requested
        if make_default:
            self._run_command(["lpadmin", "-d", printer_name])

        return True, f"Printer '{printer_name}' configured successfully"

    def test_print(self, printer_name: str) -> tuple[bool, str]:
        """Send a test page to a printer."""
        if not self._cups_available:
            return False, "CUPS is not installed"

        # Use CUPS test page
        returncode, _, stderr = self._run_command([
            "lp", "-d", printer_name,
            "/usr/share/cups/data/testprint"
        ])

        if returncode == 0:
            return True, "Test page sent to printer"
        else:
            return False, f"Failed to print test page: {stderr}"

    def test_scan(self, scanner_uri: str | None = None) -> tuple[bool, str]:
        """Test scanner functionality."""
        if not self._sane_available:
            return False, "SANE is not installed"

        cmd = ["scanimage", "--test"]
        if scanner_uri:
            cmd.extend(["-d", scanner_uri])

        returncode, stdout, stderr = self._run_command(cmd, timeout=60)

        if returncode == 0:
            return True, "Scanner test passed"
        else:
            return False, f"Scanner test failed: {stderr or stdout}"

    def display_status(self):
        """Display detected printers and scanners."""
        cx_header("Printer/Scanner Status")

        # Check dependencies
        if not self._cups_available:
            cx_print("CUPS not installed. Run: sudo apt install cups", "warning")
        if not self._sane_available:
            cx_print("SANE not installed. Run: sudo apt install sane", "warning")

        console.print()

        # Configured printers
        configured = self.detect_configured_printers()
        if configured:
            table = Table(
                title="[bold cyan]Configured Printers[/bold cyan]",
                show_header=True,
                header_style="bold cyan",
                border_style=CORTEX_CYAN,
                box=box.ROUNDED,
            )
            table.add_column("Name", style="cyan")
            table.add_column("Status", style="white")
            table.add_column("Default", style="green")

            for printer in configured:
                status_color = "green" if printer.state == "idle" else "yellow" if printer.state == "printing" else "red"
                table.add_row(
                    printer.name,
                    f"[{status_color}]{printer.state}[/{status_color}]",
                    "✓" if printer.is_default else ""
                )

            console.print(table)
            console.print()

        # Detected USB printers
        usb_printers = self.detect_usb_printers()
        if usb_printers:
            console.print("[bold]Detected USB Devices:[/bold]")
            for printer in usb_printers:
                icon = "🖨️" if printer.device_type == DeviceType.PRINTER else "📠" if printer.device_type == DeviceType.MULTIFUNCTION else "📷"
                console.print(f"  {icon} {printer.name} ({printer.vendor})")
            console.print()

        # Network printers
        network_printers = self.detect_network_printers()
        if network_printers:
            console.print("[bold]Detected Network Printers:[/bold]")
            for printer in network_printers:
                console.print(f"  🌐 {printer.name} - {printer.uri}")
            console.print()

        # Scanners
        scanners = self.detect_scanners()
        if scanners:
            console.print("[bold]Detected Scanners:[/bold]")
            for scanner in scanners:
                console.print(f"  📷 {scanner.name}")
            console.print()

        if not configured and not usb_printers and not network_printers and not scanners:
            cx_print("No printers or scanners detected", "info")

    def display_setup_guide(self, device: PrinterDevice):
        """Display setup instructions for a device."""
        cx_header(f"Setup: {device.name}")

        packages = self.get_driver_packages(device)
        driver = self.find_driver(device)

        content_lines = []
        content_lines.append(f"[bold]Device:[/bold] {device.name}")
        content_lines.append(f"[bold]Vendor:[/bold] {device.vendor or 'Unknown'}")
        content_lines.append(f"[bold]Type:[/bold] {device.device_type.value}")
        content_lines.append(f"[bold]Connection:[/bold] {device.connection.value}")

        if packages:
            content_lines.append("")
            content_lines.append("[bold]Recommended Packages:[/bold]")
            for pkg in packages:
                content_lines.append(f"  - {pkg}")
            content_lines.append("")
            content_lines.append(f"[dim]Install with: sudo apt install {' '.join(packages)}[/dim]")

        if driver:
            content_lines.append("")
            content_lines.append(f"[bold]Driver:[/bold] {driver.name}")
            if driver.recommended:
                content_lines.append("[green]✓ Recommended driver available[/green]")

        console.print(Panel(
            "\n".join(content_lines),
            title="[bold cyan]Setup Information[/bold cyan]",
            border_style=CORTEX_CYAN,
            padding=(1, 2),
        ))


def run_printer_setup(action: str = "status", verbose: bool = False) -> int:
    """
    Main entry point for cortex printer command.

    Args:
        action: One of "status", "detect", "setup"
        verbose: Verbose output

    Returns:
        Exit code
    """
    setup = PrinterSetup(verbose=verbose)

    if action == "status":
        setup.display_status()
    elif action == "detect":
        setup.display_status()
    else:
        cx_print(f"Unknown action: {action}", "error")
        return 1

    return 0
