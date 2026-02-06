"""Real-time P&L tracking with per-asset and rolling window stats."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TradeRecord:
    timestamp: float
    asset: str
    side: str
    entry_price: float
    size_usdc: float
    pnl: float
    outcome: str  # "WIN", "LOSS", "PENDING"


@dataclass
class AssetStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    total_volume: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades > 0 else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.trades if self.trades > 0 else 0.0

    @property
    def roi(self) -> float:
        return self.total_pnl / self.total_volume if self.total_volume > 0 else 0.0


@dataclass
class SessionStats:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    total_volume: float = 0.0
    peak_pnl: float = 0.0
    max_drawdown: float = 0.0
    avg_edge_captured: float = 0.0
    start_time: float = field(default_factory=time.time)

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades if self.total_trades > 0 else 0.0

    @property
    def roi(self) -> float:
        return self.total_pnl / self.total_volume if self.total_volume > 0 else 0.0


class PnlTracker:
    """Tracks real-time P&L across the trading session."""

    def __init__(self) -> None:
        self._trades: list[TradeRecord] = []
        self._asset_stats: dict[str, AssetStats] = defaultdict(AssetStats)
        self._session = SessionStats()
        self._cumulative_pnl = 0.0
        self._edge_sum = 0.0

    @property
    def session(self) -> SessionStats:
        return self._session

    @property
    def asset_stats(self) -> dict[str, AssetStats]:
        return dict(self._asset_stats)

    def record_trade(
        self,
        asset: str,
        side: str,
        entry_price: float,
        size_usdc: float,
        pnl: float,
        edge_at_entry: float = 0.0,
    ) -> None:
        """Record a completed trade with its P&L."""
        outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAK_EVEN"

        record = TradeRecord(
            timestamp=time.time(),
            asset=asset,
            side=side,
            entry_price=entry_price,
            size_usdc=size_usdc,
            pnl=pnl,
            outcome=outcome,
        )
        self._trades.append(record)

        # Update asset stats
        stats = self._asset_stats[asset]
        stats.trades += 1
        stats.total_pnl += pnl
        stats.total_volume += size_usdc
        if pnl > 0:
            stats.wins += 1
        elif pnl < 0:
            stats.losses += 1

        # Update session stats
        self._session.total_trades += 1
        self._session.total_pnl += pnl
        self._session.total_volume += size_usdc
        if pnl > 0:
            self._session.wins += 1
        elif pnl < 0:
            self._session.losses += 1

        self._cumulative_pnl += pnl
        self._session.peak_pnl = max(self._session.peak_pnl, self._cumulative_pnl)
        drawdown = self._session.peak_pnl - self._cumulative_pnl
        self._session.max_drawdown = max(self._session.max_drawdown, drawdown)

        if edge_at_entry > 0:
            self._edge_sum += edge_at_entry
            self._session.avg_edge_captured = self._edge_sum / self._session.total_trades

    def get_pnl_window(self, seconds: float) -> float:
        """Get P&L for the last N seconds."""
        cutoff = time.time() - seconds
        return sum(t.pnl for t in self._trades if t.timestamp >= cutoff)

    def get_pnl_1h(self) -> float:
        return self.get_pnl_window(3600)

    def get_pnl_24h(self) -> float:
        return self.get_pnl_window(86400)

    def get_pnl_7d(self) -> float:
        return self.get_pnl_window(604800)

    def get_recent_trades(self, n: int = 10) -> list[TradeRecord]:
        return self._trades[-n:]

    def summary(self) -> str:
        """Return a human-readable P&L summary."""
        s = self._session
        elapsed = time.time() - s.start_time
        hours = elapsed / 3600

        lines = [
            f"Session P&L: ${s.total_pnl:+.2f}",
            f"Trades: {s.total_trades} (W:{s.wins} L:{s.losses})",
            f"Win rate: {s.win_rate:.1%}",
            f"ROI: {s.roi:.1%}",
            f"Volume: ${s.total_volume:.2f}",
            f"Max drawdown: ${s.max_drawdown:.2f}",
            f"Avg edge: {s.avg_edge_captured:.3f}",
            f"Runtime: {hours:.1f}h",
        ]

        # Per-asset breakdown
        for asset, stats in sorted(self._asset_stats.items()):
            lines.append(
                f"  {asset}: ${stats.total_pnl:+.2f} "
                f"({stats.trades}T {stats.win_rate:.0%}WR)"
            )

        return "\n".join(lines)

    def summary_24h(self) -> str:
        """Return 24-hour P&L summary."""
        cutoff = time.time() - 86400
        recent = [t for t in self._trades if t.timestamp >= cutoff]
        wins = sum(1 for t in recent if t.pnl > 0)
        losses = sum(1 for t in recent if t.pnl < 0)
        pnl = sum(t.pnl for t in recent)
        volume = sum(t.size_usdc for t in recent)

        lines = [
            f"24h P&L: ${pnl:+.2f}",
            f"Trades: {len(recent)} (W:{wins} L:{losses})",
            f"Win rate: {wins / len(recent):.1%}" if recent else "Win rate: N/A",
            f"Volume: ${volume:.2f}",
        ]
        return "\n".join(lines)
