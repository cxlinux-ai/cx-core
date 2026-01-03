from abc import ABC, abstractmethod
from typing import Literal

from cortex.approval import ApprovalMode

ActionType = Literal[
    "show",
    "file_edit",
    "shell_command",
]


class ApprovalPolicy(ABC):
    """
    Base class for approval policies.
    Defines what actions are allowed under each approval mode.
    """

    def __init__(self, mode: ApprovalMode):
        self.mode = mode

    @abstractmethod
    def allow(self, action: ActionType) -> bool:
        """Return True if the action is allowed."""
        pass

    @abstractmethod
    def requires_confirmation(self, action: ActionType) -> bool:
        """Return True if the action requires user confirmation."""
        pass


# ------------------ Policies ------------------


class SuggestPolicy(ApprovalPolicy):
    def allow(self, action: ActionType) -> bool:
        return action == "show"

    def requires_confirmation(self, action: ActionType) -> bool:
        return False


class AutoEditPolicy(ApprovalPolicy):
    def allow(self, action: ActionType) -> bool:
        return action in {"show", "file_edit", "shell_command"}

    def requires_confirmation(self, action: ActionType) -> bool:
        return action == "shell_command"


class FullAutoPolicy(ApprovalPolicy):
    def allow(self, action: ActionType) -> bool:
        return True

    def requires_confirmation(self, action: ActionType) -> bool:
        return False


# ------------------ Factory ------------------


def get_approval_policy(mode: ApprovalMode) -> ApprovalPolicy:
    """
    Factory method to get the correct approval policy.
    """
    if mode == ApprovalMode.SUGGEST:
        return SuggestPolicy(mode)
    if mode == ApprovalMode.AUTO_EDIT:
        return AutoEditPolicy(mode)
    if mode == ApprovalMode.FULL_AUTO:
        return FullAutoPolicy(mode)

    raise ValueError(f"Unsupported approval mode: {mode}")
