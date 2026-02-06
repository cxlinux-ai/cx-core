"""Market definitions — token IDs, condition IDs, and asset metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Asset(str, Enum):
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"
    XRP = "XRP"


SUPPORTED_ASSETS: list[Asset] = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.XRP]

# Binance Futures symbol mapping
BINANCE_SYMBOLS: dict[Asset, str] = {
    Asset.BTC: "btcusdt",
    Asset.ETH: "ethusdt",
    Asset.SOL: "solusdt",
    Asset.XRP: "xrpusdt",
}

# Chainlink price feed addresses on Polygon
CHAINLINK_FEEDS: dict[Asset, str] = {
    Asset.BTC: "0xc907E116054Ad103354f2D350FD2514433D57F6f",
    Asset.ETH: "0xF9680D99D6C9589e2a93a78A04A279e509205945",
    Asset.SOL: "0x10C8264C0935b3B9870013e4003f4466e4F0998C",
    Asset.XRP: "0x785ba89291f676b5386652eB12b30cF361020694",
}


@dataclass
class MarketInfo:
    """Represents a single 15-min prediction market on Polymarket."""

    condition_id: str
    yes_token_id: str
    no_token_id: str
    asset: Asset
    question: str
    close_timestamp: float  # Unix timestamp when market resolves
    resolved: bool = False
    outcome: str | None = None  # "YES" or "NO" after resolution


@dataclass
class MarketConfig:
    """Configuration for discovering and filtering markets."""

    gamma_api_url: str = "https://gamma-api.polymarket.com"
    market_duration_seconds: int = 900  # 15 minutes
    refresh_interval_seconds: int = 30  # How often to scan for new markets

    # Keywords used to discover 15-min crypto prediction markets
    search_keywords: list[str] | None = None

    def __post_init__(self) -> None:
        if self.search_keywords is None:
            self.search_keywords = [
                "Will BTC",
                "Will ETH",
                "Will SOL",
                "Will XRP",
                "Bitcoin",
                "Ethereum",
                "Solana",
                "15 min",
                "15-min",
            ]
