"""Strategy parameters — entry window, thresholds, sizing."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env_float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


@dataclass
class StrategyConfig:
    """Mutable strategy parameters — can be updated live via Telegram."""

    # Entry timing
    entry_window_seconds: int = field(
        default_factory=lambda: _env_int("ENTRY_WINDOW_SECONDS", 240)
    )

    # Edge requirements
    min_edge_pct: float = field(default_factory=lambda: _env_float("MIN_EDGE_PCT", 0.02))

    # Position sizing
    max_position_usdc: float = field(
        default_factory=lambda: _env_float("MAX_POSITION_USDC", 50.0)
    )
    kelly_fraction: float = field(default_factory=lambda: _env_float("KELLY_FRACTION", 0.25))

    # Leader confidence
    min_leader_confidence: float = field(
        default_factory=lambda: _env_float("MIN_LEADER_CONFIDENCE", 0.60)
    )

    # Confirmation requirements
    required_confirmations: int = field(
        default_factory=lambda: _env_int("REQUIRED_CONFIRMATIONS", 2)
    )

    def update(self, param: str, value: str) -> str:
        """Update a strategy parameter at runtime. Returns a status message."""
        param_lower = param.lower()
        field_map: dict[str, type] = {
            "entry_window_seconds": int,
            "min_edge_pct": float,
            "max_position_usdc": float,
            "kelly_fraction": float,
            "min_leader_confidence": float,
            "required_confirmations": int,
        }

        if param_lower not in field_map:
            return f"Unknown parameter: {param}. Valid: {', '.join(field_map.keys())}"

        try:
            cast_fn = field_map[param_lower]
            parsed = cast_fn(value)
            setattr(self, param_lower, parsed)
            return f"Updated {param_lower} = {parsed}"
        except (ValueError, TypeError) as exc:
            return f"Invalid value for {param_lower}: {exc}"

    def summary(self) -> str:
        """Return a human-readable summary of current strategy parameters."""
        lines = [
            f"  entry_window_seconds: {self.entry_window_seconds}",
            f"  min_edge_pct: {self.min_edge_pct}",
            f"  max_position_usdc: {self.max_position_usdc}",
            f"  kelly_fraction: {self.kelly_fraction}",
            f"  min_leader_confidence: {self.min_leader_confidence}",
            f"  required_confirmations: {self.required_confirmations}",
        ]
        return "\n".join(lines)
