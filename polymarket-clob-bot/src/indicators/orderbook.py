"""Orderbook indicators: imbalance, spread, depth, pressure."""

from __future__ import annotations

from dataclasses import dataclass

from src.data.data_store import DataStore, OrderbookSnapshot


@dataclass
class OrderbookMetrics:
    """Computed orderbook metrics for a single snapshot."""
    asset: str
    source: str
    bid_ask_imbalance: float  # (bid_size - ask_size) / (bid_size + ask_size), range [-1, 1]
    weighted_midpoint: float  # Size-weighted midpoint price
    spread_pct: float  # Spread as percentage of midpoint
    depth_asymmetry: float  # Total bid depth vs total ask depth ratio
    order_flow_imbalance: float  # Trade-weighted flow direction


class OrderbookIndicators:
    """Computes orderbook-derived indicators from Polymarket and Binance books."""

    def __init__(self, store: DataStore) -> None:
        self._store = store

    async def compute(
        self, asset: str, source: str = "polymarket", top_n: int = 5
    ) -> OrderbookMetrics | None:
        """Compute orderbook metrics from the latest snapshot."""
        snapshot = await self._store.get_orderbook_snapshot(source, asset)
        if not snapshot or not snapshot.bids or not snapshot.asks:
            return None

        bids = sorted(snapshot.bids, key=lambda x: x[0], reverse=True)[:top_n]
        asks = sorted(snapshot.asks, key=lambda x: x[0])[:top_n]

        if not bids or not asks:
            return None

        # Bid/ask imbalance at top N levels
        total_bid_size = sum(s for _, s in bids)
        total_ask_size = sum(s for _, s in asks)
        total = total_bid_size + total_ask_size
        imbalance = (total_bid_size - total_ask_size) / total if total > 0 else 0.0

        # Weighted midpoint
        best_bid_price, best_bid_size = bids[0]
        best_ask_price, best_ask_size = asks[0]
        total_top = best_bid_size + best_ask_size
        if total_top > 0:
            weighted_mid = (
                best_bid_price * best_ask_size + best_ask_price * best_bid_size
            ) / total_top
        else:
            weighted_mid = (best_bid_price + best_ask_price) / 2

        # Spread
        spread = best_ask_price - best_bid_price
        midpoint = (best_bid_price + best_ask_price) / 2
        spread_pct = spread / midpoint if midpoint > 0 else 0.0

        # Depth asymmetry (full book)
        all_bid_size = sum(s for _, s in snapshot.bids)
        all_ask_size = sum(s for _, s in snapshot.asks)
        depth_total = all_bid_size + all_ask_size
        depth_asymmetry = (all_bid_size - all_ask_size) / depth_total if depth_total > 0 else 0.0

        # Order flow imbalance from recent trades
        trades = await self._store.get_trades(source, asset, last_n_seconds=60)
        buy_vol = sum(t.quantity for t in trades if not t.is_buyer_maker)
        sell_vol = sum(t.quantity for t in trades if t.is_buyer_maker)
        flow_total = buy_vol + sell_vol
        flow_imbalance = (buy_vol - sell_vol) / flow_total if flow_total > 0 else 0.0

        return OrderbookMetrics(
            asset=asset,
            source=source,
            bid_ask_imbalance=imbalance,
            weighted_midpoint=weighted_mid,
            spread_pct=spread_pct,
            depth_asymmetry=depth_asymmetry,
            order_flow_imbalance=flow_imbalance,
        )

    async def get_binance_book_pressure(self, asset: str) -> float:
        """Get Binance futures book pressure as directional signal.

        Returns value in [-1, 1]: positive = bullish pressure, negative = bearish.
        """
        metrics = await self.compute(asset, source="binance", top_n=1)
        if not metrics:
            return 0.0
        # Combine imbalance and flow
        return 0.6 * metrics.bid_ask_imbalance + 0.4 * metrics.order_flow_imbalance
