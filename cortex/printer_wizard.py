import subprocess
import shlex
from typing import List, Tuple
from rich.prompt import Prompt, Confirm
from cortex.branding import console, cx_print, cx_header

class PrinterWizard:
    """
    Interactive wizard for setting up printers using CUPS (lpadmin).
    
    This class handles the detection and configuration of network and USB printers
    by generating the appropriate `lpadmin` commands.
    """

    def setup(self, dry_run: bool = False):
        """
        Run the interactive printer setup wizard.

        Args:
            dry_run (bool): If True, generate commands but do not execute them.
        """
        cx_header("Printer Auto-Setup (CUPS)")
        
        console.print("[dim]This wizard helps you add a printer via CUPS (lpadmin).[/dim]\n")
        
        # 1. Printer Name
        name = Prompt.ask("[bold cyan]Printer Name (no spaces)[/bold cyan]", default="MyPrinter")
        name = name.replace(" ", "_").strip()

        # 2. Connection Type
        conn_type = Prompt.ask(
            "Connection Type", 
            choices=["network", "usb", "manual_uri"], 
            default="network"
        )
        
        uri = ""
        if conn_type == "network":
            ip = Prompt.ask("Printer IP Address", default="192.168.1.100")
            proto = Prompt.ask("Protocol", choices=["socket", "ipp", "lpd"], default="socket")
            
            if proto == "socket":
                uri = f"socket://{ip}:9100"
            elif proto == "ipp":
                uri = f"ipp://{ip}/ipp/print"
            else:
                uri = f"lpd://{ip}/queue"
                
        elif conn_type == "usb":
            console.print("[yellow]Ensure printer is connected via USB.[/yellow]")
            uri = Prompt.ask("USB URI (run 'lpinfo -v' to find)", default="usb://auto-detect")
        else:
            uri = Prompt.ask("Enter full Device URI")

        # 3. Method/Driver
        console.print("\n[dim]Driver Selection:[/dim]")
        driver_mode = Prompt.ask(
            "Driver/Model", 
            choices=["driverless (everywhere)", "ppd_file"], 
            default="driverless (everywhere)"
        )
        
        model_flag = ""
        if "driverless" in driver_mode:
            model_flag = "-m everywhere"
        else:
            ppd_path = Prompt.ask("Path to PPD file")
            if ppd_path:
                 # Use shlex.quote locally if needed, but for command string generation we keep it simple
                 model_flag = f"-P {ppd_path}"
            else:
                 model_flag = "-m everywhere" # Fallback

        # 4. Description & Location
        desc = Prompt.ask("Description", default="Office Printer")
        location = Prompt.ask("Location", default="Local")

        # Build Command
        cmd_parts = [
            "sudo", "lpadmin",
            "-p", name,
            "-v", uri,
            "-E",
            model_flag,
            "-D", f'"{desc}"',
            "-L", f'"{location}"'
        ]
        
        cmd_str = " ".join(cmd_parts)
        
        print()
        cx_print(f"Generated Command: [bold]{cmd_str}[/bold]", "info")
        
        if dry_run:
            cx_print("[Dry Run] Skipping execution.", "warning")
            return

        if Confirm.ask("Execute this command now?"):
            self._run_command(cmd_str)

    def _run_command(self, cmd_str: str):
        """
        Execute the generated shell command using subprocess.
        """
        try:
            subprocess.check_call(cmd_str, shell=True)
            cx_print(f"Printer added successfully.", "success")
            
            if Confirm.ask("Print a test page?"):
                printer_name = cmd_str.split()[3] # crude parsing, but effective/MVP
                test_cmd = f"lp -d {printer_name} /usr/share/cups/data/testprint"
                subprocess.call(test_cmd, shell=True)

        except subprocess.CalledProcessError as e:
            cx_print(f"Failed to add printer: {e}", "error")
        except Exception as e:
            cx_print(f"Error: {e}", "error")


class ScannerWizard:
    """
    Interactive wizard for setting up and testing scanners using SANE.
    """

    def setup(self, dry_run: bool = False):
        """
        Run the interactive scanner setup wizard.

        Detects scanners using `scanimage -L` and offers to run a test scan.
        """
        cx_header("Scanner Setup (SANE)")
        
        console.print("[dim]Checking for scanners using 'scanimage -L'...[/dim]")
        
        # Check for dependency
        if shutil.which("scanimage") is None and not dry_run:
             cx_print("Error: 'scanimage' (sane-utils) not found. Please install it.", "error")
             return

        devices = self._detect_devices(dry_run)

        if not devices:
            console.print("[yellow]No scanners found.[/yellow]")
            return

        console.print(f"\nFound {len(devices)} scanner(s):")
        for idx, (dev, desc) in enumerate(devices):
            console.print(f"{idx+1}. [bold]{desc.strip()}[/bold] ({dev})")
            
        choice = Prompt.ask(
            "Select scanner to test", 
            choices=[str(i+1) for i in range(len(devices))], 
            default="1"
        )
        selected_dev = devices[int(choice)-1][0]
        
        console.print(f"\nSelected: [cyan]{selected_dev}[/cyan]")
        
        if Confirm.ask("Perform test scan?"):
            self._test_scan(selected_dev, dry_run)

    def _detect_devices(self, dry_run: bool) -> List[Tuple[str, str]]:
        """Run scanimage -L and parse output."""
        devices = []
        if dry_run:
            return [("backend:mock_scanner", "Mock Scanner Device")]
            
        try:
            output = subprocess.check_output(["scanimage", "-L"], text=True)
            # Format: device `beh:/dev/usb/lp0' is a Brother DCP-7065DN virtual device
            for line in output.splitlines():
                if "device `" in line:
                     parts = line.split("`")
                     if len(parts) > 1:
                         # Split at ' is a '
                         rest = parts[1]
                         dev_part, desc_part = rest.split("' is a ", 1)
                         devices.append((dev_part, desc_part))
        except Exception as e:
            cx_print(f"Detection warning: {e}", "warning")
            
        return devices

    def _test_scan(self, device: str, dry_run: bool):
        """Run a test scan."""
        cmd = f"scanimage -d {device} --format=pnm > test_scan.pnm"
        
        if dry_run:
            cx_print(f"[Dry Run] {cmd}", "info")
            return

        cx_print("Scanning... (this may take a while)", "info")
        try:
             subprocess.check_call(cmd, shell=True)
             cx_print("Scan saved to 'test_scan.pnm'.", "success")
        except subprocess.CalledProcessError:
             cx_print("Scan failed.", "error")

import shutil # Late import fix
