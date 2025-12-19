import pytest

import cortex.stack_manager as stack_manager
from cortex.stack_manager import StackManager


def test_suggest_stack_ml_gpu_and_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that 'ml' stack falls back to 'ml-cpu' when no GPU is detected."""
    manager = StackManager()

    monkeypatch.setattr(stack_manager, "has_nvidia_gpu", lambda: False)
    assert manager.suggest_stack("ml") == "ml-cpu"

    monkeypatch.setattr(stack_manager, "has_nvidia_gpu", lambda: True)
    assert manager.suggest_stack("ml") == "ml"
