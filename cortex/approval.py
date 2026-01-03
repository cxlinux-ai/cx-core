from enum import Enum


class ApprovalMode(str, Enum):
    """
    Defines how much autonomy Cortex has when performing actions.
    This is the single source of truth for approval modes.
    """

    SUGGEST = "suggest"
    AUTO_EDIT = "auto-edit"
    FULL_AUTO = "full-auto"

    @classmethod
    def from_string(cls, value: str) -> "ApprovalMode":
        """
        Convert user/config input into ApprovalMode.
        Raises ValueError for invalid modes.
        """
        try:
            return cls(value)
        except ValueError as exc:
            valid = ", ".join([m.value for m in cls])
            raise ValueError(f"Invalid approval mode '{value}'. Valid modes are: {valid}") from exc
