from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, dict

from cortex.approval import ApprovalMode

# Default config location (adjust ONLY if your project already defines this elsewhere)
DEFAULT_CONFIG_PATH = Path.home() / ".cortex" / "config.json"


@dataclass
class UserPreferences:
    """
    Stores persistent user configuration for Cortex.
    """

    approval_mode: ApprovalMode = ApprovalMode.SUGGEST

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> UserPreferences:
        """
        Load user preferences from disk.
        Falls back to defaults if config does not exist.
        """
        if not path.exists():
            return cls()

        try:
            with path.open("r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupt config → fail safe
            return cls()

        return cls(
            approval_mode=ApprovalMode.from_string(
                data.get("approval_mode", ApprovalMode.SUGGEST.value)
            )
        )

    def save(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        """
        Persist user preferences to disk.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "approval_mode": self.approval_mode.value,
        }

        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
