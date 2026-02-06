"""Backtest the Late Entry V3 strategy against historical CSV data."""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    market_id: str
    asset: str
    side: str
    entry_price: float
    size: float
    edge: float
    outcome: str
    pnl: float


@dataclass
class BacktestResult:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    total_volume: float = 0.0
    max_drawdown: float = 0.0
    peak_pnl: float = 0.0
    trades: list[BacktestTrade] = field(default_factory=list)
    asset_pnl: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades if self.total_trades > 0 else 0.0

    @property
    def roi(self) -> float:
        return self.total_pnl / self.total_volume if self.total_volume > 0 else 0.0

    def summary(self) -> str:
        lines = [
            "=" * 50,
            "BACKTEST RESULTS",
            "=" * 50,
            f"Total trades: {self.total_trades}",
            f"Wins: {self.wins}  Losses: {self.losses}",
            f"Win rate: {self.win_rate:.1%}",
            f"Total PnL: ${self.total_pnl:+.2f}",
            f"Total volume: ${self.total_volume:.2f}",
            f"ROI: {self.roi:.1%}",
            f"Max drawdown: ${self.max_drawdown:.2f}",
            "",
            "Per-asset breakdown:",
        ]
        for asset, pnl in sorted(self.asset_pnl.items()):
            asset_trades = [t for t in self.trades if t.asset == asset]
            asset_wins = sum(1 for t in asset_trades if t.pnl > 0)
            wr = asset_wins / len(asset_trades) if asset_trades else 0
            lines.append(f"  {asset}: ${pnl:+.2f} ({len(asset_trades)}T, {wr:.0%}WR)")

        return "\n".join(lines)


def simulate_strategy(
    trades_data: list[dict],
    min_edge: float = 0.02,
    max_position: float = 50.0,
    entry_window_pct: float = 0.73,  # Enter in last 27% of market (last ~4 min)
    min_leader_price: float = 0.60,
) -> BacktestResult:
    """Simulate the late entry strategy on historical trade data.

    This is a simplified backtest — it groups trades by market, determines
    the leader in the late phase, and simulates entering at that price.
    """
    result = BacktestResult()

    # Group trades by market
    markets: dict[str, list[dict]] = defaultdict(list)
    for row in trades_data:
        markets[row["market_id"]].append(row)

    for market_id, market_trades in markets.items():
        if len(market_trades) < 5:
            continue

        # Sort by timestamp
        market_trades.sort(key=lambda x: float(x.get("timestamp", 0)))

        # Get market metadata
        asset = market_trades[0].get("asset", "UNKNOWN")
        outcome = market_trades[0].get("outcome", "")

        if not outcome:
            continue

        # Find trades in the "late phase" (last ~27% of market duration)
        timestamps = [float(t.get("timestamp", 0)) for t in market_trades]
        market_start = min(timestamps)
        market_end = max(timestamps)
        duration = market_end - market_start

        if duration < 60:  # Too short
            continue

        late_cutoff = market_start + duration * entry_window_pct
        late_trades = [t for t in market_trades if float(t.get("timestamp", 0)) >= late_cutoff]

        if not late_trades:
            continue

        # Determine leader price in late phase
        prices = [float(t.get("price", 0.5)) for t in late_trades if float(t.get("price", 0)) > 0]
        if not prices:
            continue

        avg_price = sum(prices) / len(prices)

        # Determine leader side
        if avg_price > 0.5:
            leader_side = "YES"
            leader_price = avg_price
        else:
            leader_side = "NO"
            leader_price = 1.0 - avg_price

        # Check minimum leader confidence
        if leader_price < min_leader_price:
            continue

        # Simplified edge estimation (actual edge calc would use Binance data)
        estimated_edge = leader_price - 0.5  # Simple proxy
        if estimated_edge < min_edge:
            continue

        # Simulate trade
        entry_price = leader_price
        size = min(max_position, max_position * (estimated_edge / 0.1))

        # Determine outcome
        won = (leader_side == "YES" and outcome.upper() in ("YES", "1")) or \
              (leader_side == "NO" and outcome.upper() in ("NO", "0"))

        shares = size / entry_price if entry_price > 0 else 0
        pnl = (shares * 1.0 - size) if won else -size

        trade = BacktestTrade(
            market_id=market_id,
            asset=asset,
            side=f"BUY_{leader_side}",
            entry_price=entry_price,
            size=size,
            edge=estimated_edge,
            outcome="WIN" if won else "LOSS",
            pnl=pnl,
        )

        result.trades.append(trade)
        result.total_trades += 1
        result.total_pnl += pnl
        result.total_volume += size
        result.asset_pnl[asset] += pnl

        if pnl > 0:
            result.wins += 1
        else:
            result.losses += 1

        result.peak_pnl = max(result.peak_pnl, result.total_pnl)
        drawdown = result.peak_pnl - result.total_pnl
        result.max_drawdown = max(result.max_drawdown, drawdown)

    return result


def load_trades_csv(path: Path) -> list[dict]:
    """Load historical trades from CSV."""
    trades = []
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append(dict(row))
    return trades


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest Late Entry V3 strategy")
    parser.add_argument("--data", type=str, default="./data/trades_history.csv", help="CSV data file")
    parser.add_argument("--min-edge", type=float, default=0.02, help="Minimum edge threshold")
    parser.add_argument("--max-position", type=float, default=50.0, help="Max position size (USDC)")
    parser.add_argument("--min-leader", type=float, default=0.60, help="Min leader confidence")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        logger.error("Data file not found: %s", data_path)
        logger.info("Run scripts/collect_history.py first to gather historical data")
        sys.exit(1)

    trades = load_trades_csv(data_path)
    logger.info("Loaded %d trade records from %s", len(trades), data_path)

    result = simulate_strategy(
        trades,
        min_edge=args.min_edge,
        max_position=args.max_position,
        min_leader_price=args.min_leader,
    )

    print(result.summary())

    # Export backtest trades
    output_path = data_path.parent / "backtest_results.csv"
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["market_id", "asset", "side", "entry_price", "size", "edge", "outcome", "pnl"])
        for t in result.trades:
            writer.writerow([t.market_id, t.asset, t.side, t.entry_price, t.size, t.edge, t.outcome, t.pnl])
    logger.info("Backtest results saved to %s", output_path)


if __name__ == "__main__":
    main()
