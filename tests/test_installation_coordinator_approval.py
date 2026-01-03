from cortex.approval import ApprovalMode
from cortex.coordinator import InstallationCoordinator
from cortex.user_preferences import UserPreferences


def test_suggest_mode_blocks_execution(monkeypatch):
    # Force suggest mode
    monkeypatch.setattr(
        UserPreferences,
        "load",
        lambda: type("Prefs", (), {"approval_mode": ApprovalMode.SUGGEST})(),
    )

    coordinator = InstallationCoordinator(
        commands=["echo hello"],
        descriptions=["test command"],
    )

    result = coordinator.execute()

    assert not result.success
    assert result.steps[0].status.value == "skipped"
