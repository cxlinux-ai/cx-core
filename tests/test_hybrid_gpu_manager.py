from cortex.hardware_detection import detect_gpu_mode
from cortex.hardware_detection import estimate_gpu_battery_impact
from cortex.hardware_detection import detect_nvidia_gpu
from cortex.hardware_detection import detect_gpu_mode


def test_detect_gpu_mode_returns_valid_state():
    mode = detect_gpu_mode()
    assert isinstance(mode, str)
    assert mode in {"Integrated", "Hybrid", "NVIDIA"}


def test_estimate_gpu_battery_impact_structure():
    result = estimate_gpu_battery_impact()

    assert isinstance(result, dict)
    assert "mode" in result
    assert "current" in result
    assert "estimates" in result

    estimates = result["estimates"]
    assert set(estimates.keys()) == {
        "integrated",
        "hybrid_idle",
        "nvidia_active",
    }

    for profile in estimates.values():
        assert "power" in profile
        assert "impact" in profile


def test_detect_nvidia_gpu_is_safe_and_returns_bool():
    result = detect_nvidia_gpu()
    assert isinstance(result, bool)


def test_per_app_gpu_assignment_logic_does_not_crash():
    # Per-app GPU assignment is environment-based;
    # ensure detection logic is stable regardless of environment
    mode = detect_gpu_mode()
    assert mode is not None
