from cortex.hardware_detection import (
    detect_gpu_mode,
    detect_nvidia_gpu,
    estimate_gpu_battery_impact,
)


def test_detect_gpu_mode_returns_valid_state() -> None:
    mode: str = detect_gpu_mode()
    assert isinstance(mode, str)
    assert mode in {"Integrated", "Hybrid", "NVIDIA"}


def test_estimate_gpu_battery_impact_structure() -> None:
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


def test_detect_nvidia_gpu_is_safe_and_returns_bool() -> None:
    result = detect_nvidia_gpu()
    assert isinstance(result, bool)


def test_detect_gpu_mode_does_not_crash_and_returns_value() -> None:
    mode = detect_gpu_mode()
    assert mode is not None
