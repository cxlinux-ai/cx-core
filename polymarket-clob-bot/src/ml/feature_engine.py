"""Feature engineering: build feature matrix from indicator snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.indicators.core import IndicatorSnapshot
from src.indicators.edge import EdgeResult
from src.indicators.market_phase import PhaseInfo
from src.indicators.orderbook import OrderbookMetrics


FEATURE_NAMES = [
    "vwap_deviation",
    "cvd_value",
    "cvd_slope",
    "book_imbalance",
    "book_spread_pct",
    "depth_asymmetry",
    "flow_imbalance",
    "realized_vol",
    "parkinson_vol",
    "atr",
    "momentum_roc",
    "momentum_acceleration",
    "trend_strength",
    "phase_elapsed_pct",
    "remaining_seconds",
    "leader_price",
    "leader_stability",
    "reversal_probability",
    "signal_noise_ratio",
    "edge_estimate",
    "binance_price_change",
]


@dataclass
class FeatureRow:
    """A single feature vector with metadata."""
    features: dict[str, float] = field(default_factory=dict)
    timestamp: float = 0.0
    asset: str = ""
    market_id: str = ""
    label: int | None = None  # 1 = leader won, 0 = leader lost (for training)


class FeatureEngine:
    """Builds feature matrices from live indicator data or historical CSVs."""

    def __init__(self) -> None:
        self._rolling_stats: dict[str, list[float]] = {name: [] for name in FEATURE_NAMES}
        self._max_history = 500  # Rolling window for z-score normalization

    def build_features(
        self,
        core: IndicatorSnapshot,
        orderbook: OrderbookMetrics | None,
        phase: PhaseInfo,
        edge: EdgeResult,
        yes_price: float,
        no_price: float,
    ) -> FeatureRow:
        """Build a feature vector from current indicator state."""
        leader_price = max(yes_price, no_price)

        features: dict[str, float] = {
            "vwap_deviation": self._vwap_dev(core, leader_price),
            "cvd_value": core.cvd.cvd if core.cvd else 0.0,
            "cvd_slope": core.cvd.cvd_slope if core.cvd else 0.0,
            "book_imbalance": orderbook.bid_ask_imbalance if orderbook else 0.0,
            "book_spread_pct": orderbook.spread_pct if orderbook else 0.0,
            "depth_asymmetry": orderbook.depth_asymmetry if orderbook else 0.0,
            "flow_imbalance": orderbook.order_flow_imbalance if orderbook else 0.0,
            "realized_vol": core.volatility.realized_vol if core.volatility else 0.0,
            "parkinson_vol": core.volatility.parkinson_vol if core.volatility else 0.0,
            "atr": core.volatility.atr if core.volatility else 0.0,
            "momentum_roc": core.momentum.roc if core.momentum else 0.0,
            "momentum_acceleration": core.momentum.acceleration if core.momentum else 0.0,
            "trend_strength": core.momentum.trend_strength if core.momentum else 0.0,
            "phase_elapsed_pct": phase.elapsed_pct,
            "remaining_seconds": phase.remaining_seconds,
            "leader_price": leader_price,
            "leader_stability": phase.leader_stability,
            "reversal_probability": phase.reversal_probability,
            "signal_noise_ratio": phase.signal_noise_ratio,
            "edge_estimate": edge.best_edge,
            "binance_price_change": edge.binance_price_change_pct,
        }

        # Update rolling stats for normalization
        for name, value in features.items():
            self._rolling_stats[name].append(value)
            if len(self._rolling_stats[name]) > self._max_history:
                self._rolling_stats[name] = self._rolling_stats[name][-self._max_history:]

        return FeatureRow(features=features, asset=core.asset)

    def normalize(self, row: FeatureRow) -> FeatureRow:
        """Apply rolling z-score normalization to features."""
        normalized: dict[str, float] = {}
        for name, value in row.features.items():
            history = self._rolling_stats.get(name, [])
            if len(history) >= 10:
                arr = np.array(history)
                mean = arr.mean()
                std = arr.std()
                if std > 1e-10:
                    normalized[name] = (value - mean) / std
                else:
                    normalized[name] = 0.0
            else:
                normalized[name] = value

        return FeatureRow(
            features=normalized,
            timestamp=row.timestamp,
            asset=row.asset,
            market_id=row.market_id,
            label=row.label,
        )

    def to_dataframe(self, rows: list[FeatureRow]) -> pd.DataFrame:
        """Convert feature rows to a pandas DataFrame."""
        records = []
        for row in rows:
            record = dict(row.features)
            record["timestamp"] = row.timestamp
            record["asset"] = row.asset
            record["market_id"] = row.market_id
            if row.label is not None:
                record["label"] = row.label
            records.append(record)
        return pd.DataFrame(records)

    @staticmethod
    def _vwap_dev(core: IndicatorSnapshot, current_price: float) -> float:
        """VWAP deviation: how far current price is from VWAP."""
        if core.vwap and core.vwap.vwap > 0:
            return (current_price - core.vwap.vwap) / core.vwap.vwap
        return 0.0
