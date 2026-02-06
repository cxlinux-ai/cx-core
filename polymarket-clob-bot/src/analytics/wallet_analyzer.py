"""Wallet analyzer: fetch and analyze any Polymarket wallet's trade history."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

logger = logging.getLogger(__name__)

POLYMARKET_DATA_API = "https://data-api.polymarket.com"


@dataclass
class WalletTrade:
    timestamp: float
    market: str
    side: str
    price: float
    size: float
    outcome: str
    pnl: float


@dataclass
class WalletProfile:
    address: str
    total_trades: int
    total_pnl: float
    win_rate: float
    avg_position_size: float
    preferred_assets: list[str]
    timing_pattern: str  # "early", "mid", "late"
    trades: list[WalletTrade]


class WalletAnalyzer:
    """Analyzes any Polymarket wallet's trade history and patterns."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)

    async def analyze(self, address: str) -> WalletProfile | None:
        """Fetch and analyze a wallet's complete trade history."""
        trades = await self._fetch_trades(address)
        if not trades:
            logger.warning("No trades found for wallet %s", address)
            return None

        # Compute stats
        total_pnl = sum(t.pnl for t in trades)
        wins = sum(1 for t in trades if t.pnl > 0)
        total = len(trades)
        win_rate = wins / total if total > 0 else 0.0
        avg_size = sum(t.size for t in trades) / total if total > 0 else 0.0

        # Preferred assets
        asset_counts: dict[str, int] = {}
        for t in trades:
            market_upper = t.market.upper()
            for asset in ["BTC", "ETH", "SOL", "XRP"]:
                if asset in market_upper:
                    asset_counts[asset] = asset_counts.get(asset, 0) + 1
        preferred = sorted(asset_counts, key=asset_counts.get, reverse=True)[:3]

        # Timing pattern (based on when in the 15-min cycle trades are placed)
        # This is approximate — we'd need market close times for precision
        timing = "unknown"

        profile = WalletProfile(
            address=address,
            total_trades=total,
            total_pnl=total_pnl,
            win_rate=win_rate,
            avg_position_size=avg_size,
            preferred_assets=preferred,
            timing_pattern=timing,
            trades=trades,
        )

        # Export
        await self._export_csv(profile)
        await self._generate_chart(profile)

        return profile

    async def _fetch_trades(self, address: str) -> list[WalletTrade]:
        """Fetch trade history from Polymarket Data API."""
        trades: list[WalletTrade] = []
        url = f"{POLYMARKET_DATA_API}/trades"
        cursor: str | None = None

        async with aiohttp.ClientSession() as session:
            for _ in range(100):  # Max pages
                params: dict = {"maker": address, "limit": 500}
                if cursor:
                    params["cursor"] = cursor

                try:
                    async with session.get(
                        url, params=params, timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        if resp.status != 200:
                            logger.warning("Data API returned %d", resp.status)
                            break
                        data = await resp.json()
                except Exception as exc:
                    logger.error("Data API request failed: %s", exc)
                    break

                results = data if isinstance(data, list) else data.get("data", [])
                if not results:
                    break

                for r in results:
                    try:
                        trades.append(WalletTrade(
                            timestamp=float(r.get("timestamp", 0)),
                            market=r.get("market", ""),
                            side=r.get("side", ""),
                            price=float(r.get("price", 0)),
                            size=float(r.get("size", 0)),
                            outcome=r.get("outcome", ""),
                            pnl=float(r.get("pnl", 0)),
                        ))
                    except (ValueError, TypeError):
                        continue

                cursor = data.get("next_cursor") if isinstance(data, dict) else None
                if not cursor:
                    break

        trades.sort(key=lambda t: t.timestamp)
        logger.info("Fetched %d trades for wallet %s", len(trades), address[:10])
        return trades

    async def _export_csv(self, profile: WalletProfile) -> Path:
        """Export wallet trades to CSV."""
        path = self._data_dir / f"wallet_{profile.address[:10]}.csv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "market", "side", "price", "size", "outcome", "pnl", "cumulative_pnl"])
            cum_pnl = 0.0
            for t in profile.trades:
                cum_pnl += t.pnl
                writer.writerow([t.timestamp, t.market, t.side, t.price, t.size, t.outcome, t.pnl, cum_pnl])
        logger.info("Exported wallet CSV to %s", path)
        return path

    async def _generate_chart(self, profile: WalletProfile) -> Path:
        """Generate accumulation (cumulative PnL) chart."""
        path = self._data_dir / f"wallet_{profile.address[:10]}_chart.png"

        timestamps = [datetime.utcfromtimestamp(t.timestamp) for t in profile.trades]
        cum_pnl: list[float] = []
        running = 0.0
        for t in profile.trades:
            running += t.pnl
            cum_pnl.append(running)

        if not timestamps:
            return path

        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(timestamps, cum_pnl, linewidth=1.5, color="#2196F3")
        ax.fill_between(
            timestamps, cum_pnl, alpha=0.1,
            where=[p >= 0 for p in cum_pnl], color="green",
        )
        ax.fill_between(
            timestamps, cum_pnl, alpha=0.1,
            where=[p < 0 for p in cum_pnl], color="red",
        )
        ax.set_title(f"Cumulative PnL — {profile.address[:10]}...")
        ax.set_xlabel("Date")
        ax.set_ylabel("PnL (USDC)")
        ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.5)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)

        logger.info("Generated wallet chart at %s", path)
        return path
