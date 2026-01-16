"""
Tests for Printer/Scanner Setup Module

Issue: #451 - Printer/Scanner Auto-Setup
"""

from unittest.mock import MagicMock, patch

import pytest

from cortex.printer_setup import (
    DRIVER_PACKAGES,
    SCANNER_PACKAGES,
    ConnectionType,
    DeviceType,
    DriverInfo,
    PrinterDevice,
    PrinterSetup,
    run_printer_setup,
)


class TestDeviceType:
    """Tests for DeviceType enum."""

    def test_device_types(self):
        """Test all device types are defined."""
        assert DeviceType.PRINTER.value == "printer"
        assert DeviceType.SCANNER.value == "scanner"
        assert DeviceType.MULTIFUNCTION.value == "multifunction"


class TestConnectionType:
    """Tests for ConnectionType enum."""

    def test_connection_types(self):
        """Test all connection types are defined."""
        assert ConnectionType.USB.value == "usb"
        assert ConnectionType.NETWORK.value == "network"


class TestPrinterDevice:
    """Tests for PrinterDevice dataclass."""

    def test_default_values(self):
        """Test default device values."""
        device = PrinterDevice(
            name="Test Printer",
            device_type=DeviceType.PRINTER,
            connection=ConnectionType.USB,
        )
        assert device.name == "Test Printer"
        assert device.is_configured is False
        assert device.is_default is False

    def test_full_device(self):
        """Test device with full values."""
        device = PrinterDevice(
            name="HP LaserJet",
            device_type=DeviceType.MULTIFUNCTION,
            connection=ConnectionType.NETWORK,
            vendor="hp",
            model="M428",
            is_configured=True,
        )
        assert device.vendor == "hp"
        assert device.is_configured is True


class TestDriverInfo:
    """Tests for DriverInfo dataclass."""

    def test_default_values(self):
        """Test default driver values."""
        driver = DriverInfo(name="Test Driver")
        assert driver.ppd_path == ""
        assert driver.recommended is False

    def test_full_driver(self):
        """Test driver with full values."""
        driver = DriverInfo(
            name="HP LaserJet",
            ppd_path="drv:///hp.ppd",
            recommended=True,
            source="hplip",
        )
        assert driver.recommended is True
        assert driver.source == "hplip"


class TestDriverPackages:
    """Tests for driver package constants."""

    def test_driver_packages_defined(self):
        """Test driver packages are defined."""
        assert "hp" in DRIVER_PACKAGES
        assert "epson" in DRIVER_PACKAGES
        assert "canon" in DRIVER_PACKAGES

    def test_scanner_packages_defined(self):
        """Test scanner packages are defined."""
        assert "hp" in SCANNER_PACKAGES
        assert "generic" in SCANNER_PACKAGES


class TestPrinterSetup:
    """Tests for PrinterSetup class."""

    @pytest.fixture
    def setup(self):
        """Create a setup instance."""
        with patch.object(PrinterSetup, "_check_cups", return_value=True):
            with patch.object(PrinterSetup, "_check_sane", return_value=True):
                return PrinterSetup(verbose=False)

    def test_initialization(self, setup):
        """Test setup initialization."""
        assert setup.verbose is False

    def test_detect_vendor_hp(self, setup):
        """Test HP vendor detection."""
        assert setup._detect_vendor("HP LaserJet Pro") == "hp"
        assert setup._detect_vendor("Hewlett Packard") == "hp"

    def test_detect_vendor_epson(self, setup):
        """Test Epson vendor detection."""
        assert setup._detect_vendor("Epson WorkForce") == "epson"

    def test_detect_vendor_canon(self, setup):
        """Test Canon vendor detection."""
        assert setup._detect_vendor("Canon PIXMA") == "canon"

    def test_detect_vendor_brother(self, setup):
        """Test Brother vendor detection."""
        assert setup._detect_vendor("Brother MFC-9340") == "brother"

    def test_detect_vendor_unknown(self, setup):
        """Test unknown vendor detection."""
        assert setup._detect_vendor("Random Printer") == "generic"


class TestDetectUSBPrinters:
    """Tests for USB printer detection."""

    @pytest.fixture
    def setup(self):
        with patch.object(PrinterSetup, "_check_cups", return_value=True):
            with patch.object(PrinterSetup, "_check_sane", return_value=True):
                return PrinterSetup()

    def test_detect_usb_printers_parses_lsusb(self, setup):
        """Test lsusb parsing for printers."""
        lsusb_output = """Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 001 Device 005: ID 03f0:8711 HP, Inc HP LaserJet Pro M428"""

        with patch.object(setup, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, lsusb_output, "")

            devices = setup.detect_usb_printers()

            assert len(devices) >= 1
            hp_devices = [d for d in devices if d.vendor == "hp"]
            assert len(hp_devices) >= 1

    def test_detect_usb_printers_empty(self, setup):
        """Test when no printers detected."""
        with patch.object(setup, "_run_command") as mock_cmd:
            mock_cmd.return_value = (
                0,
                "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
                "",
            )

            devices = setup.detect_usb_printers()
            assert devices == []


class TestDetectConfiguredPrinters:
    """Tests for configured printer detection."""

    @pytest.fixture
    def setup(self):
        with patch.object(PrinterSetup, "_check_cups", return_value=True):
            with patch.object(PrinterSetup, "_check_sane", return_value=True):
                return PrinterSetup()

    def test_detect_configured_printers(self, setup):
        """Test lpstat parsing."""
        lpstat_output = """printer HP_LaserJet is idle.  enabled since Tue Jan 14
system default destination: HP_LaserJet"""

        with patch.object(setup, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, lpstat_output, "")

            devices = setup.detect_configured_printers()

            assert len(devices) >= 1
            assert devices[0].is_configured is True
            assert devices[0].is_default is True


class TestGetDriverPackages:
    """Tests for get_driver_packages method."""

    @pytest.fixture
    def setup(self):
        with patch.object(PrinterSetup, "_check_cups", return_value=True):
            with patch.object(PrinterSetup, "_check_sane", return_value=True):
                return PrinterSetup()

    def test_get_hp_printer_packages(self, setup):
        """Test HP printer packages."""
        device = PrinterDevice(
            name="HP LaserJet",
            device_type=DeviceType.PRINTER,
            connection=ConnectionType.USB,
            vendor="hp",
        )

        packages = setup.get_driver_packages(device)
        assert "hplip" in packages

    def test_get_multifunction_packages(self, setup):
        """Test multifunction device packages."""
        device = PrinterDevice(
            name="HP OfficeJet",
            device_type=DeviceType.MULTIFUNCTION,
            connection=ConnectionType.USB,
            vendor="hp",
        )

        packages = setup.get_driver_packages(device)
        assert "hplip" in packages


class TestSetupPrinter:
    """Tests for setup_printer method."""

    @pytest.fixture
    def setup(self):
        with patch.object(PrinterSetup, "_check_cups", return_value=True):
            with patch.object(PrinterSetup, "_check_sane", return_value=True):
                return PrinterSetup()

    def test_setup_printer_no_cups(self):
        """Test setup when CUPS not available."""
        with patch.object(PrinterSetup, "_check_cups", return_value=False):
            with patch.object(PrinterSetup, "_check_sane", return_value=True):
                setup = PrinterSetup()

                device = PrinterDevice(
                    name="Test",
                    device_type=DeviceType.PRINTER,
                    connection=ConnectionType.USB,
                )

                success, message = setup.setup_printer(device)
                assert not success
                assert "cups" in message.lower()


class TestTestPrint:
    """Tests for test_print method."""

    @pytest.fixture
    def setup(self):
        with patch.object(PrinterSetup, "_check_cups", return_value=True):
            with patch.object(PrinterSetup, "_check_sane", return_value=True):
                return PrinterSetup()

    def test_print_success(self, setup):
        """Test successful print."""
        with patch.object(setup, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, "", "")

            success, message = setup.test_print("TestPrinter")
            assert success

    def test_print_failure(self, setup):
        """Test failed print."""
        with patch.object(setup, "_run_command") as mock_cmd:
            mock_cmd.return_value = (1, "", "printer not found")

            success, message = setup.test_print("NonExistent")
            assert not success


class TestTestScan:
    """Tests for test_scan method."""

    @pytest.fixture
    def setup(self):
        with patch.object(PrinterSetup, "_check_cups", return_value=True):
            with patch.object(PrinterSetup, "_check_sane", return_value=True):
                return PrinterSetup()

    def test_scan_success(self, setup):
        """Test successful scan."""
        with patch.object(setup, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, "", "")

            success, message = setup.test_scan()
            assert success

    def test_scan_no_sane(self):
        """Test scan when SANE not available."""
        with patch.object(PrinterSetup, "_check_cups", return_value=True):
            with patch.object(PrinterSetup, "_check_sane", return_value=False):
                setup = PrinterSetup()

                success, message = setup.test_scan()
                assert not success
                assert "sane" in message.lower()


class TestDisplayMethods:
    """Tests for display methods."""

    @pytest.fixture
    def setup(self):
        with patch.object(PrinterSetup, "_check_cups", return_value=True):
            with patch.object(PrinterSetup, "_check_sane", return_value=True):
                return PrinterSetup()

    def test_display_status(self, setup, capsys):
        """Test display_status runs without error."""
        with patch.object(setup, "detect_configured_printers") as mock_conf:
            with patch.object(setup, "detect_usb_printers") as mock_usb:
                with patch.object(setup, "detect_network_printers") as mock_net:
                    with patch.object(setup, "detect_scanners") as mock_scan:
                        mock_conf.return_value = []
                        mock_usb.return_value = []
                        mock_net.return_value = []
                        mock_scan.return_value = []

                        setup.display_status()
                        captured = capsys.readouterr()
                        assert "Printer" in captured.out or "Status" in captured.out


class TestRunPrinterSetup:
    """Tests for run_printer_setup entry point."""

    def test_run_status(self, capsys):
        """Test running status action."""
        with patch("cortex.printer_setup.PrinterSetup") as MockSetup:
            mock_instance = MagicMock()
            MockSetup.return_value = mock_instance

            result = run_printer_setup("status")

            mock_instance.display_status.assert_called_once()
            assert result == 0

    def test_run_unknown_action(self, capsys):
        """Test unknown action."""
        result = run_printer_setup("unknown")
        assert result == 1
