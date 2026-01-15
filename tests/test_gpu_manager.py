"""
Tests for GPU Manager Module

Issue: #454 - Hybrid GPU (Optimus) Manager
"""

from unittest.mock import MagicMock, patch

import pytest

from cortex.gpu_manager import (
    APP_GPU_RECOMMENDATIONS,
    BATTERY_IMPACT,
    GPUDevice,
    GPUMode,
    GPUState,
    GPUVendor,
    HybridGPUManager,
    run_gpu_manager,
)


class TestGPUMode:
    """Tests for GPUMode enum."""

    def test_gpu_modes(self):
        """Test all GPU modes are defined."""
        assert GPUMode.INTEGRATED.value == "integrated"
        assert GPUMode.HYBRID.value == "hybrid"
        assert GPUMode.NVIDIA.value == "nvidia"
        assert GPUMode.COMPUTE.value == "compute"
        assert GPUMode.UNKNOWN.value == "unknown"


class TestGPUVendor:
    """Tests for GPUVendor enum."""

    def test_gpu_vendors(self):
        """Test all GPU vendors are defined."""
        assert GPUVendor.INTEL.value == "intel"
        assert GPUVendor.AMD.value == "amd"
        assert GPUVendor.NVIDIA.value == "nvidia"


class TestGPUDevice:
    """Tests for GPUDevice dataclass."""

    def test_default_values(self):
        """Test default device values."""
        device = GPUDevice(vendor=GPUVendor.INTEL, name="Intel HD Graphics")
        assert device.vendor == GPUVendor.INTEL
        assert device.name == "Intel HD Graphics"
        assert device.driver == ""
        assert device.memory_mb == 0
        assert device.is_active is False

    def test_nvidia_device(self):
        """Test NVIDIA device with full values."""
        device = GPUDevice(
            vendor=GPUVendor.NVIDIA,
            name="GeForce RTX 3080",
            driver="nvidia",
            memory_mb=10240,
            is_active=True,
        )
        assert device.memory_mb == 10240
        assert device.is_active is True


class TestGPUState:
    """Tests for GPUState dataclass."""

    def test_default_values(self):
        """Test default state values."""
        state = GPUState()
        assert state.mode == GPUMode.UNKNOWN
        assert state.devices == []
        assert state.active_gpu is None

    def test_is_hybrid_system_true(self):
        """Test hybrid system detection (NVIDIA + Intel)."""
        state = GPUState(
            devices=[
                GPUDevice(vendor=GPUVendor.INTEL, name="Intel"),
                GPUDevice(vendor=GPUVendor.NVIDIA, name="NVIDIA"),
            ]
        )
        assert state.is_hybrid_system is True

    def test_is_hybrid_system_nvidia_amd(self):
        """Test hybrid system detection (NVIDIA + AMD)."""
        state = GPUState(
            devices=[
                GPUDevice(vendor=GPUVendor.AMD, name="AMD"),
                GPUDevice(vendor=GPUVendor.NVIDIA, name="NVIDIA"),
            ]
        )
        assert state.is_hybrid_system is True

    def test_is_hybrid_system_false(self):
        """Test non-hybrid system detection."""
        state = GPUState(
            devices=[
                GPUDevice(vendor=GPUVendor.INTEL, name="Intel"),
            ]
        )
        assert state.is_hybrid_system is False


class TestBatteryImpact:
    """Tests for battery impact estimates."""

    def test_all_modes_have_estimates(self):
        """Test all modes have battery estimates."""
        for mode in [GPUMode.INTEGRATED, GPUMode.HYBRID, GPUMode.NVIDIA, GPUMode.COMPUTE]:
            assert mode in BATTERY_IMPACT
            assert "description" in BATTERY_IMPACT[mode]
            assert "impact" in BATTERY_IMPACT[mode]

    def test_integrated_best_battery(self):
        """Test integrated mode has best battery."""
        assert "best" in BATTERY_IMPACT[GPUMode.INTEGRATED]["description"].lower()


class TestAppGPURecommendations:
    """Tests for app GPU recommendations."""

    def test_recommendations_defined(self):
        """Test that recommendations exist."""
        assert len(APP_GPU_RECOMMENDATIONS) > 0

    def test_gaming_apps_recommend_nvidia(self):
        """Test gaming apps recommend NVIDIA."""
        assert APP_GPU_RECOMMENDATIONS.get("steam") == GPUVendor.NVIDIA
        assert APP_GPU_RECOMMENDATIONS.get("blender") == GPUVendor.NVIDIA

    def test_office_apps_recommend_integrated(self):
        """Test office apps recommend integrated GPU."""
        assert APP_GPU_RECOMMENDATIONS.get("code") == GPUVendor.INTEL
        assert APP_GPU_RECOMMENDATIONS.get("firefox") == GPUVendor.INTEL


class TestHybridGPUManager:
    """Tests for HybridGPUManager class."""

    @pytest.fixture
    def manager(self):
        """Create a manager instance."""
        return HybridGPUManager(verbose=False)

    def test_initialization(self, manager):
        """Test manager initialization."""
        assert manager.verbose is False
        assert manager._state is None

    def test_run_command_not_found(self, manager):
        """Test command not found handling."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            code, stdout, stderr = manager._run_command(["nonexistent"])
            assert code == 1
            assert "not found" in stderr.lower()

    def test_run_command_success(self, manager):
        """Test successful command execution."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")
            code, stdout, stderr = manager._run_command(["test"])
            assert code == 0
            assert stdout == "output"


class TestDetectGPUs:
    """Tests for GPU detection."""

    @pytest.fixture
    def manager(self):
        return HybridGPUManager()

    def test_detect_gpus_parses_lspci(self, manager):
        """Test lspci output parsing."""
        lspci_output = """00:02.0 VGA compatible controller [0300]: Intel Corporation Device 9a49 (rev 03)
01:00.0 3D controller [0302]: NVIDIA Corporation Device 2560 (rev a1)"""

        with patch.object(manager, "_run_command") as mock_cmd:
            # lspci succeeds, nvidia-smi fails
            mock_cmd.side_effect = [
                (0, lspci_output, ""),  # lspci
                (1, "", "not found"),  # nvidia-smi
            ]
            devices = manager.detect_gpus()

            assert len(devices) == 2
            vendors = [d.vendor for d in devices]
            assert GPUVendor.INTEL in vendors
            assert GPUVendor.NVIDIA in vendors

    def test_detect_gpus_with_nvidia_smi(self, manager):
        """Test NVIDIA detection with nvidia-smi."""
        lspci_output = "01:00.0 VGA: NVIDIA Corporation GeForce RTX 3080"

        with patch.object(manager, "_run_command") as mock_cmd:
            mock_cmd.side_effect = [
                (0, lspci_output, ""),  # lspci
                (0, "GeForce RTX 3080, 10240, 150.0", ""),  # nvidia-smi
                (1, "", ""),  # power state
            ]
            devices = manager.detect_gpus()

            nvidia_devices = [d for d in devices if d.vendor == GPUVendor.NVIDIA]
            assert len(nvidia_devices) >= 1
            assert nvidia_devices[0].memory_mb == 10240


class TestDetectMode:
    """Tests for GPU mode detection."""

    @pytest.fixture
    def manager(self):
        return HybridGPUManager()

    def test_detect_mode_prime_nvidia(self, manager):
        """Test detecting NVIDIA mode via prime-select."""
        with patch.object(manager, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, "nvidia", "")
            mode = manager.detect_mode()
            assert mode == GPUMode.NVIDIA

    def test_detect_mode_prime_ondemand(self, manager):
        """Test detecting hybrid mode via prime-select."""
        with patch.object(manager, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, "on-demand", "")
            mode = manager.detect_mode()
            assert mode == GPUMode.HYBRID

    def test_detect_mode_prime_intel(self, manager):
        """Test detecting integrated mode via prime-select."""
        with patch.object(manager, "_run_command") as mock_cmd:
            mock_cmd.return_value = (0, "intel", "")
            mode = manager.detect_mode()
            assert mode == GPUMode.INTEGRATED

    def test_detect_mode_unknown(self, manager):
        """Test unknown mode when no tool available."""
        with patch.object(manager, "_run_command") as mock_cmd:
            mock_cmd.return_value = (1, "", "not found")
            mode = manager.detect_mode()
            assert mode == GPUMode.UNKNOWN


class TestGetState:
    """Tests for get_state method."""

    @pytest.fixture
    def manager(self):
        return HybridGPUManager()

    def test_get_state_caches_result(self, manager):
        """Test that state is cached."""
        with patch.object(manager, "detect_gpus") as mock_gpus:
            with patch.object(manager, "detect_mode") as mock_mode:
                mock_gpus.return_value = []
                mock_mode.return_value = GPUMode.UNKNOWN

                state1 = manager.get_state()
                state2 = manager.get_state()

                # Should only call detect once
                assert mock_gpus.call_count == 1

    def test_get_state_refresh(self, manager):
        """Test state refresh."""
        with patch.object(manager, "detect_gpus") as mock_gpus:
            with patch.object(manager, "detect_mode") as mock_mode:
                mock_gpus.return_value = []
                mock_mode.return_value = GPUMode.UNKNOWN

                manager.get_state()
                manager.get_state(refresh=True)

                # Should call detect twice due to refresh
                assert mock_gpus.call_count == 2


class TestSwitchMode:
    """Tests for mode switching."""

    @pytest.fixture
    def manager(self):
        return HybridGPUManager()

    def test_switch_mode_non_hybrid(self, manager):
        """Test switching on non-hybrid system."""
        state = GPUState(devices=[GPUDevice(vendor=GPUVendor.INTEL, name="Intel")])
        with patch.object(manager, "get_state") as mock_state:
            mock_state.return_value = state

            success, message, command = manager.switch_mode(GPUMode.NVIDIA)
            assert not success
            assert "not a hybrid" in message.lower()

    def test_switch_mode_with_prime_select(self, manager):
        """Test switching with prime-select available."""
        state = GPUState(
            devices=[
                GPUDevice(vendor=GPUVendor.INTEL, name="Intel"),
                GPUDevice(vendor=GPUVendor.NVIDIA, name="NVIDIA"),
            ]
        )

        with patch.object(manager, "get_state") as mock_state:
            mock_state.return_value = state
            with patch.object(manager, "_run_command") as mock_cmd:
                # which prime-select succeeds
                mock_cmd.return_value = (0, "/usr/bin/prime-select", "")

                success, message, command = manager.switch_mode(GPUMode.NVIDIA)

                assert success
                assert command is not None
                assert "prime-select nvidia" in command


class TestGetAppLaunchCommand:
    """Tests for app launch command generation."""

    @pytest.fixture
    def manager(self):
        return HybridGPUManager()

    def test_launch_with_nvidia(self, manager):
        """Test launch command with NVIDIA GPU."""
        state = GPUState(
            mode=GPUMode.HYBRID,
            devices=[
                GPUDevice(vendor=GPUVendor.INTEL, name="Intel"),
                GPUDevice(vendor=GPUVendor.NVIDIA, name="NVIDIA"),
            ],
            render_offload_available=True,
        )

        with patch.object(manager, "get_state") as mock_state:
            mock_state.return_value = state

            command = manager.get_app_launch_command("steam", use_nvidia=True)

            assert "__NV_PRIME_RENDER_OFFLOAD=1" in command
            assert "steam" in command

    def test_launch_with_integrated(self, manager):
        """Test launch command with integrated GPU."""
        state = GPUState(
            mode=GPUMode.HYBRID,
            devices=[
                GPUDevice(vendor=GPUVendor.INTEL, name="Intel"),
                GPUDevice(vendor=GPUVendor.NVIDIA, name="NVIDIA"),
            ],
        )

        with patch.object(manager, "get_state") as mock_state:
            mock_state.return_value = state

            command = manager.get_app_launch_command("firefox", use_nvidia=False)

            assert "DRI_PRIME=0" in command

    def test_launch_non_hybrid(self, manager):
        """Test launch command on non-hybrid system."""
        state = GPUState(
            mode=GPUMode.UNKNOWN,
            devices=[GPUDevice(vendor=GPUVendor.INTEL, name="Intel")],
        )

        with patch.object(manager, "get_state") as mock_state:
            mock_state.return_value = state

            command = manager.get_app_launch_command("app")

            # Should just return the app name
            assert command == "app"


class TestGetBatteryEstimate:
    """Tests for battery estimate."""

    @pytest.fixture
    def manager(self):
        return HybridGPUManager()

    def test_battery_estimate_integrated(self, manager):
        """Test integrated mode estimate."""
        estimate = manager.get_battery_estimate(GPUMode.INTEGRATED)
        assert "best" in estimate["description"].lower()

    def test_battery_estimate_nvidia(self, manager):
        """Test NVIDIA mode estimate."""
        estimate = manager.get_battery_estimate(GPUMode.NVIDIA)
        assert "performance" in estimate["description"].lower()


class TestDisplayMethods:
    """Tests for display methods."""

    @pytest.fixture
    def manager(self):
        return HybridGPUManager()

    def test_display_status(self, manager, capsys):
        """Test display_status runs without error."""
        state = GPUState(
            mode=GPUMode.HYBRID,
            devices=[
                GPUDevice(vendor=GPUVendor.INTEL, name="Intel HD 630"),
                GPUDevice(vendor=GPUVendor.NVIDIA, name="GTX 1080", memory_mb=8192),
            ],
        )

        with patch.object(manager, "get_state") as mock_state:
            mock_state.return_value = state

            manager.display_status()
            captured = capsys.readouterr()

            assert "GPU" in captured.out
            assert "Intel" in captured.out or "NVIDIA" in captured.out

    def test_display_modes(self, manager, capsys):
        """Test display_modes runs without error."""
        manager.display_modes()
        captured = capsys.readouterr()

        # "integrated" may be truncated to "integra..." in table
        assert "integra" in captured.out.lower()
        assert "hybrid" in captured.out.lower()
        assert "nvidia" in captured.out.lower()

    def test_display_app_recommendations(self, manager, capsys):
        """Test display_app_recommendations runs without error."""
        state = GPUState(mode=GPUMode.HYBRID)

        with patch.object(manager, "get_state") as mock_state:
            mock_state.return_value = state

            manager.display_app_recommendations()
            captured = capsys.readouterr()

            assert "steam" in captured.out.lower() or "blender" in captured.out.lower()


class TestRunGPUManager:
    """Tests for run_gpu_manager entry point."""

    def test_run_status(self, capsys):
        """Test running status action."""
        with patch("cortex.gpu_manager.HybridGPUManager") as MockManager:
            mock_instance = MagicMock()
            MockManager.return_value = mock_instance

            result = run_gpu_manager("status")

            mock_instance.display_status.assert_called_once()
            assert result == 0

    def test_run_modes(self, capsys):
        """Test running modes action."""
        with patch("cortex.gpu_manager.HybridGPUManager") as MockManager:
            mock_instance = MagicMock()
            MockManager.return_value = mock_instance

            result = run_gpu_manager("modes")

            mock_instance.display_modes.assert_called_once()
            assert result == 0

    def test_run_apps(self):
        """Test running apps action."""
        with patch("cortex.gpu_manager.HybridGPUManager") as MockManager:
            mock_instance = MagicMock()
            MockManager.return_value = mock_instance

            result = run_gpu_manager("apps")

            mock_instance.display_app_recommendations.assert_called_once()
            assert result == 0

    def test_run_switch_no_mode(self, capsys):
        """Test switch without mode."""
        result = run_gpu_manager("switch", mode=None)
        assert result == 1
        captured = capsys.readouterr()
        assert "specify" in captured.out.lower()

    def test_run_switch_invalid_mode(self, capsys):
        """Test switch with invalid mode."""
        result = run_gpu_manager("switch", mode="invalid")
        assert result == 1
        captured = capsys.readouterr()
        assert "unknown" in captured.out.lower()

    def test_run_unknown_action(self, capsys):
        """Test unknown action."""
        result = run_gpu_manager("unknown_action")
        assert result == 1
        captured = capsys.readouterr()
        assert "unknown" in captured.out.lower()
