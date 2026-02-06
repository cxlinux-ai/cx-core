"""Thread-safe in-memory rolling window store for all market data."""

from __future__ import annotations

import asyncio
import csv
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Trade:
    timestamp: float
    source: str  # "binance" or "polymarket"
    asset: str
    price: float
    quantity: float
    is_buyer_maker: bool


@dataclass
class OrderbookSnapshot:
    timestamp: float
    source: str
    asset: str
    bids: list[tuple[float, float]]  # (price, size)
    asks: list[tuple[float, float]]


@dataclass
class OraclePrice:
    timestamp: float
    asset: str
    price: float
    source: str = "chainlink"


@dataclass
class OHLCV:
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    buy_volume: float = 0.0
    sell_volume: float = 0.0


class DataStore:
    """Rolling-window in-memory store with async-safe access."""

    MAX_WINDOW_SECONDS: float = 3600.0  # 60 minutes

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

        # Keyed by (source, asset)
        self._trades: dict[tuple[str, str], deque[Trade]] = defaultdict(
            lambda: deque(maxlen=100_000)
        )
        self._orderbooks: dict[tuple[str, str], deque[OrderbookSnapshot]] = defaultdict(
            lambda: deque(maxlen=10_000)
        )
        self._oracle_prices: dict[str, deque[OraclePrice]] = defaultdict(
            lambda: deque(maxlen=10_000)
        )

    async def add_trade(self, trade: Trade) -> None:
        async with self._lock:
            key = (trade.source, trade.asset)
            self._trades[key].append(trade)
            self._prune_trades(key)

    async def add_orderbook(self, snapshot: OrderbookSnapshot) -> None:
        async with self._lock:
            key = (snapshot.source, snapshot.asset)
            self._orderbooks[key].append(snapshot)
            self._prune_orderbooks(key)

    async def add_oracle_price(self, price: OraclePrice) -> None:
        async with self._lock:
            self._oracle_prices[price.asset].append(price)
            self._prune_oracle(price.asset)

    async def get_trades(
        self, source: str, asset: str, last_n_seconds: float | None = None
    ) -> list[Trade]:
        async with self._lock:
            key = (source, asset)
            trades = list(self._trades.get(key, []))
        if last_n_seconds is not None:
            cutoff = time.time() - last_n_seconds
            trades = [t for t in trades if t.timestamp >= cutoff]
        return trades

    async def get_orderbook_snapshot(
        self, source: str, asset: str
    ) -> OrderbookSnapshot | None:
        async with self._lock:
            key = (source, asset)
            book = self._orderbooks.get(key)
            if book:
                return book[-1]
            return None

    async def get_oracle_price(self, asset: str) -> OraclePrice | None:
        async with self._lock:
            prices = self._oracle_prices.get(asset)
            if prices:
                return prices[-1]
            return None

    async def get_ohlcv(
        self, asset: str, interval_seconds: float, source: str = "binance"
    ) -> list[OHLCV]:
        """Build OHLCV bars from raw trade data."""
        trades = await self.get_trades(source, asset)
        if not trades:
            return []

        bars: list[OHLCV] = []
        if not trades:
            return bars

        bar_start = trades[0].timestamp
        bar_start = bar_start - (bar_start % interval_seconds)

        current_bar: dict[str, Any] = {
            "timestamp": bar_start,
            "open": trades[0].price,
            "high": trades[0].price,
            "low": trades[0].price,
            "close": trades[0].price,
            "volume": 0.0,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
        }

        for trade in trades:
            # Check if trade belongs to a new bar
            if trade.timestamp >= bar_start + interval_seconds:
                bars.append(OHLCV(**current_bar))
                bar_start = trade.timestamp - (trade.timestamp % interval_seconds)
                current_bar = {
                    "timestamp": bar_start,
                    "open": trade.price,
                    "high": trade.price,
                    "low": trade.price,
                    "close": trade.price,
                    "volume": 0.0,
                    "buy_volume": 0.0,
                    "sell_volume": 0.0,
                }

            current_bar["high"] = max(current_bar["high"], trade.price)
            current_bar["low"] = min(current_bar["low"], trade.price)
            current_bar["close"] = trade.price
            current_bar["volume"] += trade.quantity
            if trade.is_buyer_maker:
                current_bar["sell_volume"] += trade.quantity
            else:
                current_bar["buy_volume"] += trade.quantity

        # Append the last partial bar
        bars.append(OHLCV(**current_bar))
        return bars

    async def export_trades_csv(self, path: Path, source: str, asset: str) -> int:
        """Export trades to CSV. Returns number of rows written."""
        trades = await self.get_trades(source, asset)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["timestamp", "source", "asset", "price", "quantity", "is_buyer_maker"]
            )
            for t in trades:
                writer.writerow(
                    [t.timestamp, t.source, t.asset, t.price, t.quantity, t.is_buyer_maker]
                )
        return len(trades)

    # --- Internal pruning ---

    def _prune_trades(self, key: tuple[str, str]) -> None:
        cutoff = time.time() - self.MAX_WINDOW_SECONDS
        dq = self._trades[key]
        while dq and dq[0].timestamp < cutoff:
            dq.popleft()

    def _prune_orderbooks(self, key: tuple[str, str]) -> None:
        cutoff = time.time() - self.MAX_WINDOW_SECONDS
        dq = self._orderbooks[key]
        while dq and dq[0].timestamp < cutoff:
            dq.popleft()

    def _prune_oracle(self, asset: str) -> None:
        cutoff = time.time() - self.MAX_WINDOW_SECONDS
        dq = self._oracle_prices[asset]
        while dq and dq[0].timestamp < cutoff:
            dq.popleft()
