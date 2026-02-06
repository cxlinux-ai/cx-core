"""Central configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_float(key: str, default: float = 0.0) -> float:
    return float(os.getenv(key, str(default)))


def _env_int(key: str, default: int = 0) -> int:
    return int(os.getenv(key, str(default)))


def _env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


@dataclass(frozen=True)
class PolymarketSettings:
    private_key: str = field(default_factory=lambda: _env("POLYMARKET_PRIVATE_KEY"))
    funder_address: str = field(default_factory=lambda: _env("POLYMARKET_FUNDER_ADDRESS"))
    signature_type: int = field(default_factory=lambda: _env_int("POLYMARKET_SIGNATURE_TYPE", 0))
    api_host: str = field(
        default_factory=lambda: _env("POLYMARKET_API_HOST", "https://clob.polymarket.com")
    )
    chain_id: int = field(default_factory=lambda: _env_int("POLYMARKET_CHAIN_ID", 137))


@dataclass(frozen=True)
class TelegramSettings:
    bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))


@dataclass(frozen=True)
class RiskSettings:
    max_daily_loss_usdc: float = field(
        default_factory=lambda: _env_float("MAX_DAILY_LOSS_USDC", 200.0)
    )
    max_consecutive_losses: int = field(
        default_factory=lambda: _env_int("MAX_CONSECUTIVE_LOSSES", 5)
    )
    max_drawdown_pct: float = field(
        default_factory=lambda: _env_float("MAX_DRAWDOWN_PCT", 0.15)
    )
    max_concurrent_positions: int = field(
        default_factory=lambda: _env_int("MAX_CONCURRENT_POSITIONS", 4)
    )


@dataclass(frozen=True)
class DataSettings:
    log_trades_csv: bool = field(default_factory=lambda: _env_bool("LOG_TRADES_CSV", True))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "./data")))


@dataclass(frozen=True)
class Settings:
    """Top-level settings container aggregating all config sections."""

    polymarket: PolymarketSettings = field(default_factory=PolymarketSettings)
    telegram: TelegramSettings = field(default_factory=TelegramSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    data: DataSettings = field(default_factory=DataSettings)

    def validate(self) -> list[str]:
        """Return a list of configuration warnings/errors."""
        issues: list[str] = []
        if not self.polymarket.private_key:
            issues.append("POLYMARKET_PRIVATE_KEY is not set")
        if not self.telegram.bot_token:
            issues.append("TELEGRAM_BOT_TOKEN is not set — Telegram alerts disabled")
        return issues
