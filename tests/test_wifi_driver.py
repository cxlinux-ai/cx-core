"""
Tests for WiFi/Bluetooth Driver Auto-Matcher

Issue: #444 - WiFi/Bluetooth Driver Auto-Matcher
"""

from unittest.mock import MagicMock, patch

import pytest

from cortex.wifi_driver import (
    BLUETOOTH_DRIVERS,
    DRIVER_DATABASE,
    ConnectionType,
    DeviceType,
    DriverInfo,
    DriverSource,
    WirelessDevice,
    WirelessDriverMatcher,
    run_wifi_driver,
)


class TestDeviceType:
    """Tests for DeviceType enum."""

    def test_device_types(self):
        """Test all device types are defined."""
        assert DeviceType.WIFI.value == "wifi"
        assert DeviceType.BLUETOOTH.value == "bluetooth"
        assert DeviceType.COMBO.value == "combo"


class TestConnectionType:
    """Tests for ConnectionType enum."""

    def test_connection_types(self):
        """Test all connection types are defined."""
        assert ConnectionType.PCI.value == "pci"
        assert ConnectionType.USB.value == "usb"
        assert ConnectionType.SDIO.value == "sdio"


class TestDriverSource:
    """Tests for DriverSource enum."""

    def test_driver_sources(self):
        """Test all driver sources are defined."""
        assert DriverSource.KERNEL.value == "kernel"
        assert DriverSource.DKMS.value == "dkms"
        assert DriverSource.PACKAGE.value == "package"
        assert DriverSource.MANUAL.value == "manual"


class TestWirelessDevice:
    """Tests for WirelessDevice dataclass."""

    def test_default_values(self):
        """Test default device values."""
        device = WirelessDevice(
            name="Test WiFi",
            device_type=DeviceType.WIFI,
            connection=ConnectionType.PCI,
        )
        assert device.name == "Test WiFi"
        assert device.vendor_id == ""
        assert device.is_working is False

    def test_full_device(self):
        """Test device with full values."""
        device = WirelessDevice(
            name="Intel Wireless",
            device_type=DeviceType.WIFI,
            connection=ConnectionType.PCI,
            vendor_id="8086",
            device_id="2723",
            vendor="intel",
            driver_loaded="iwlwifi",
            is_working=True,
        )
        assert device.vendor == "intel"
        assert device.is_working is True
        assert device.driver_loaded == "iwlwifi"


class TestDriverInfo:
    """Tests for DriverInfo dataclass."""

    def test_default_values(self):
        """Test default driver values."""
        driver = DriverInfo(name="Test Driver")
        assert driver.package == ""
        assert driver.source == DriverSource.PACKAGE
        assert driver.supported_ids == []

    def test_full_driver(self):
        """Test driver with full values."""
        driver = DriverInfo(
            name="RTL8821CE",
            package="rtl8821ce-dkms",
            source=DriverSource.DKMS,
            git_url="https://github.com/test/driver",
            supported_ids=[("10ec", "c821")],
            notes="Test notes",
        )
        assert driver.source == DriverSource.DKMS
        assert len(driver.supported_ids) == 1


class TestDriverDatabase:
    """Tests for driver database constants."""

    def test_realtek_drivers_defined(self):
        """Test Realtek drivers are defined."""
        assert "rtl8821ce" in DRIVER_DATABASE
        assert "rtl8822ce" in DRIVER_DATABASE

    def test_mediatek_drivers_defined(self):
        """Test Mediatek drivers are defined."""
        assert "mt7921" in DRIVER_DATABASE

    def test_intel_drivers_defined(self):
        """Test Intel drivers are defined."""
        assert "iwlwifi" in DRIVER_DATABASE

    def test_bluetooth_drivers_defined(self):
        """Test Bluetooth drivers are defined."""
        assert "btrtl" in BLUETOOTH_DRIVERS
        assert "btintel" in BLUETOOTH_DRIVERS


class TestWirelessDriverMatcher:
    """Tests for WirelessDriverMatcher class."""

    @pytest.fixture
    def matcher(self):
        """Create a matcher instance."""
        return WirelessDriverMatcher(verbose=False)

    def test_initialization(self, matcher):
        """Test matcher initialization."""
        assert matcher.verbose is False
        assert matcher.devices == []

    def test_detect_vendor_realtek(self, matcher):
        """Test Realtek vendor detection."""
        assert matcher._detect_vendor("Realtek RTL8821CE") == "realtek"
        assert matcher._detect_vendor("RTL8852AE") == "realtek"

    def test_detect_vendor_intel(self, matcher):
        """Test Intel vendor detection."""
        assert matcher._detect_vendor("Intel Wireless-AC 9560") == "intel"
        assert matcher._detect_vendor("Intel WiFi 6 AX200") == "intel"

    def test_detect_vendor_mediatek(self, matcher):
        """Test Mediatek vendor detection."""
        assert matcher._detect_vendor("Mediatek MT7921") == "mediatek"
        assert matcher._detect_vendor("MT7922 WiFi") == "mediatek"

    def test_detect_vendor_broadcom(self, matcher):
        """Test Broadcom vendor detection."""
        assert matcher._detect_vendor("Broadcom BCM4350") == "broadcom"

    def test_detect_vendor_unknown(self, matcher):
        """Test unknown vendor detection."""
        assert matcher._detect_vendor("Random WiFi Card") == "unknown"


class TestDetectPCIDevices:
    """Tests for PCI device detection."""

    @pytest.fixture
    def matcher(self):
        return WirelessDriverMatcher()

    def test_detect_pci_devices_parses_lspci(self, matcher):
        """Test lspci parsing for wireless devices."""
        lspci_output = """00:00.0 Host bridge [0600]: Intel Corporation Device [8086:a700]
02:00.0 Network controller [0280]: Intel Corporation Wi-Fi 6 AX201 [8086:a0f0]"""

        lspci_driver = """02:00.0 Network controller: Intel Corporation Wi-Fi 6 AX201
        Kernel driver in use: iwlwifi"""

        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.side_effect = [
                (0, lspci_output, ""),
                (0, lspci_driver, ""),
            ]

            devices = matcher.detect_pci_devices()

            assert len(devices) >= 1
            wifi_devices = [d for d in devices if d.device_type == DeviceType.WIFI]
            assert len(wifi_devices) >= 1

    def test_detect_pci_devices_empty(self, matcher):
        """Test when no wireless devices detected."""
        lspci_output = """00:00.0 Host bridge [0600]: Intel Corporation Device [8086:a700]"""

        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, lspci_output, "")

            devices = matcher.detect_pci_devices()
            assert devices == []

    def test_detect_pci_command_failure(self, matcher):
        """Test handling lspci failure."""
        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.return_value = (1, "", "command not found")

            devices = matcher.detect_pci_devices()
            assert devices == []


class TestDetectUSBDevices:
    """Tests for USB device detection."""

    @pytest.fixture
    def matcher(self):
        return WirelessDriverMatcher()

    def test_detect_usb_devices_parses_lsusb(self, matcher):
        """Test lsusb parsing for wireless devices."""
        lsusb_output = """Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 001 Device 003: ID 0bda:c820 Realtek Semiconductor Corp. RTL8821C"""

        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, lsusb_output, "")

            devices = matcher.detect_usb_devices()

            assert len(devices) >= 1
            realtek = [d for d in devices if d.vendor == "realtek"]
            assert len(realtek) >= 1

    def test_detect_usb_devices_bluetooth(self, matcher):
        """Test USB Bluetooth detection."""
        lsusb_output = """Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 001 Device 002: ID 8087:0a2b Intel Corp. Bluetooth wireless interface"""

        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, lsusb_output, "")

            devices = matcher.detect_usb_devices()

            bt_devices = [d for d in devices if d.device_type == DeviceType.BLUETOOTH]
            assert len(bt_devices) >= 1

    def test_detect_usb_devices_empty(self, matcher):
        """Test when no wireless USB devices."""
        lsusb_output = """Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub"""

        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, lsusb_output, "")

            devices = matcher.detect_usb_devices()
            assert devices == []


class TestFindDriver:
    """Tests for driver matching."""

    @pytest.fixture
    def matcher(self):
        return WirelessDriverMatcher()

    def test_find_driver_by_id(self, matcher):
        """Test finding driver by vendor:device ID."""
        device = WirelessDevice(
            name="Test Device",
            device_type=DeviceType.WIFI,
            connection=ConnectionType.PCI,
            vendor_id="10ec",
            device_id="c821",
        )

        driver = matcher.find_driver(device)
        assert driver is not None
        assert driver.name == "RTL8821CE"

    def test_find_bluetooth_driver(self, matcher):
        """Test finding Bluetooth driver."""
        device = WirelessDevice(
            name="Intel Bluetooth",
            device_type=DeviceType.BLUETOOTH,
            connection=ConnectionType.USB,
            vendor="intel",
        )

        driver = matcher.find_driver(device)
        assert driver is not None
        assert "intel" in driver.name.lower()

    def test_find_driver_not_found(self, matcher):
        """Test when no driver found."""
        device = WirelessDevice(
            name="Unknown Device",
            device_type=DeviceType.WIFI,
            connection=ConnectionType.PCI,
            vendor_id="ffff",
            device_id="ffff",
        )

        driver = matcher.find_driver(device)
        assert driver is None


class TestCheckConnectivity:
    """Tests for connectivity checking."""

    @pytest.fixture
    def matcher(self):
        return WirelessDriverMatcher()

    def test_check_wifi_connected(self, matcher):
        """Test WiFi connected status."""
        ip_output = """1: lo: <LOOPBACK,UP,LOWER_UP>
2: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> state UP"""

        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.side_effect = [
                (0, ip_output, ""),
                (0, "MyNetwork", ""),
                (0, "", ""),
            ]

            status = matcher.check_connectivity()
            assert status["wifi_connected"] is True

    def test_check_wifi_not_connected(self, matcher):
        """Test WiFi not connected."""
        ip_output = """1: lo: <LOOPBACK,UP,LOWER_UP>
2: wlan0: <BROADCAST,MULTICAST> state DOWN"""

        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.side_effect = [
                (0, ip_output, ""),
                (1, "", ""),
            ]

            status = matcher.check_connectivity()
            assert status["wifi_connected"] is False

    def test_check_bluetooth_available(self, matcher):
        """Test Bluetooth availability."""
        bt_output = """Controller 00:11:22:33:44:55 (public)
        Powered: yes"""

        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.side_effect = [
                (0, "1: wlan0: state DOWN", ""),
                (0, bt_output, ""),
            ]

            status = matcher.check_connectivity()
            assert status["bluetooth_available"] is True
            assert status["bluetooth_powered"] is True


class TestGetInstallCommands:
    """Tests for install command generation."""

    @pytest.fixture
    def matcher(self):
        return WirelessDriverMatcher()

    def test_package_install_commands(self, matcher):
        """Test package install commands."""
        driver = DriverInfo(
            name="Test",
            package="test-driver",
            source=DriverSource.PACKAGE,
        )

        commands = matcher.get_install_commands(driver)
        assert "sudo apt install -y test-driver" in commands

    def test_dkms_with_git_commands(self, matcher):
        """Test DKMS with git repo commands."""
        driver = DriverInfo(
            name="rtl8821ce",
            package="rtl8821ce-dkms",
            source=DriverSource.DKMS,
            git_url="https://github.com/test/rtl8821ce",
        )

        commands = matcher.get_install_commands(driver)
        assert any("git clone" in cmd for cmd in commands)

    def test_kernel_install_commands(self, matcher):
        """Test kernel driver install commands."""
        driver = DriverInfo(
            name="Test",
            package="linux-firmware",
            source=DriverSource.KERNEL,
        )

        commands = matcher.get_install_commands(driver)
        assert any("linux-firmware" in cmd for cmd in commands)
        assert any("update-initramfs" in cmd for cmd in commands)


class TestInstallDriver:
    """Tests for driver installation."""

    @pytest.fixture
    def matcher(self):
        return WirelessDriverMatcher()

    def test_install_package_success(self, matcher):
        """Test successful package installation."""
        driver = DriverInfo(
            name="Test",
            package="linux-firmware",
            source=DriverSource.PACKAGE,
        )

        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, "", "")

            success, message = matcher.install_driver(driver)
            assert success is True
            assert "linux-firmware" in message

    def test_install_package_failure(self, matcher):
        """Test failed package installation."""
        driver = DriverInfo(
            name="Test",
            package="nonexistent-package",
            source=DriverSource.PACKAGE,
        )

        with patch.object(matcher, "_run_command") as mock_cmd:
            mock_cmd.return_value = (1, "", "package not found")

            success, message = matcher.install_driver(driver)
            assert success is False

    def test_install_dkms_with_git(self, matcher):
        """Test DKMS with git requires manual install."""
        driver = DriverInfo(
            name="rtl8821ce",
            package="rtl8821ce-dkms",
            source=DriverSource.DKMS,
            git_url="https://github.com/test/driver",
        )

        success, message = matcher.install_driver(driver)
        assert success is False
        assert "manual" in message.lower()


class TestDisplayMethods:
    """Tests for display methods."""

    @pytest.fixture
    def matcher(self):
        return WirelessDriverMatcher()

    def test_display_status(self, matcher, capsys):
        """Test display_status runs without error."""
        with patch.object(matcher, "detect_all_devices") as mock_detect:
            with patch.object(matcher, "check_connectivity") as mock_conn:
                mock_detect.return_value = []
                mock_conn.return_value = {
                    "wifi_interface": None,
                    "wifi_connected": False,
                    "wifi_ssid": None,
                    "bluetooth_available": False,
                    "bluetooth_powered": False,
                }

                matcher.display_status()
                captured = capsys.readouterr()
                assert "wifi" in captured.out.lower() or "wireless" in captured.out.lower()

    def test_display_recommendations_no_issues(self, matcher, capsys):
        """Test recommendations when all devices working."""
        with patch.object(matcher, "detect_all_devices") as mock_detect:
            mock_detect.return_value = [
                WirelessDevice(
                    name="Working WiFi",
                    device_type=DeviceType.WIFI,
                    connection=ConnectionType.PCI,
                    is_working=True,
                )
            ]

            matcher.display_recommendations()
            captured = capsys.readouterr()
            assert "working" in captured.out.lower()


class TestRunWifiDriver:
    """Tests for run_wifi_driver entry point."""

    def test_run_status(self, capsys):
        """Test running status action."""
        with patch("cortex.wifi_driver.WirelessDriverMatcher") as MockMatcher:
            mock_instance = MagicMock()
            MockMatcher.return_value = mock_instance

            result = run_wifi_driver("status")

            mock_instance.display_status.assert_called_once()
            assert result == 0

    def test_run_detect(self, capsys):
        """Test running detect action."""
        with patch("cortex.wifi_driver.WirelessDriverMatcher") as MockMatcher:
            mock_instance = MagicMock()
            mock_instance.detect_all_devices.return_value = []
            MockMatcher.return_value = mock_instance

            result = run_wifi_driver("detect")

            mock_instance.detect_all_devices.assert_called_once()
            assert result == 0

    def test_run_recommend(self, capsys):
        """Test running recommend action."""
        with patch("cortex.wifi_driver.WirelessDriverMatcher") as MockMatcher:
            mock_instance = MagicMock()
            MockMatcher.return_value = mock_instance

            result = run_wifi_driver("recommend")

            mock_instance.display_recommendations.assert_called_once()
            assert result == 0

    def test_run_unknown_action(self, capsys):
        """Test unknown action."""
        result = run_wifi_driver("unknown")
        assert result == 1
        captured = capsys.readouterr()
        assert "unknown" in captured.out.lower()

    def test_run_connectivity(self, capsys):
        """Test running connectivity check."""
        with patch("cortex.wifi_driver.WirelessDriverMatcher") as MockMatcher:
            mock_instance = MagicMock()
            mock_instance.check_connectivity.return_value = {
                "wifi_connected": True,
                "wifi_ssid": "TestNetwork",
                "bluetooth_available": True,
            }
            MockMatcher.return_value = mock_instance

            result = run_wifi_driver("connectivity")
            assert result == 0
