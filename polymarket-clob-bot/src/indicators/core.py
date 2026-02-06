"""Core indicators: OHLCV bars, VWAP, CVD, volatility, momentum."""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.data.data_store import OHLCV, DataStore, Trade


@dataclass
class VWAPResult:
    vwap: float
    cumulative_volume: float
    cumulative_pv: float  # price * volume sum


@dataclass
class CVDResult:
    """Cumulative Volume Delta — buy volume minus sell volume."""
    cvd: float
    buy_volume: float
    sell_volume: float
    cvd_slope: float  # Rate of change of CVD (positive = buying pressure)


@dataclass
class VolatilityResult:
    realized_vol: float  # Standard deviation of returns
    parkinson_vol: float  # High-low estimator
    atr: float  # Average true range


@dataclass
class MomentumResult:
    roc: float  # Rate of change (percentage)
    acceleration: float  # Second derivative of price
    trend_strength: float  # Absolute momentum magnitude (0-1 normalized)


@dataclass
class IndicatorSnapshot:
    """All core indicator outputs for a single asset at a point in time."""
    asset: str
    vwap: VWAPResult | None = None
    cvd: CVDResult | None = None
    volatility: VolatilityResult | None = None
    momentum: MomentumResult | None = None


class CoreIndicators:
    """Computes core technical indicators from trade and OHLCV data."""

    def __init__(self, store: DataStore) -> None:
        self._store = store

    async def compute(self, asset: str, source: str = "binance") -> IndicatorSnapshot:
        """Compute all core indicators for an asset."""
        bars = await self._store.get_ohlcv(asset, interval_seconds=5.0, source=source)
        trades = await self._store.get_trades(source, asset, last_n_seconds=900)

        snapshot = IndicatorSnapshot(asset=asset)
        if trades:
            snapshot.vwap = self._compute_vwap(trades)
            snapshot.cvd = self._compute_cvd(trades)
        if len(bars) >= 2:
            snapshot.volatility = self._compute_volatility(bars)
            snapshot.momentum = self._compute_momentum(bars)
        return snapshot

    @staticmethod
    def _compute_vwap(trades: list[Trade]) -> VWAPResult:
        cum_pv = 0.0
        cum_vol = 0.0
        for t in trades:
            cum_pv += t.price * t.quantity
            cum_vol += t.quantity
        vwap = cum_pv / cum_vol if cum_vol > 0 else 0.0
        return VWAPResult(vwap=vwap, cumulative_volume=cum_vol, cumulative_pv=cum_pv)

    @staticmethod
    def _compute_cvd(trades: list[Trade]) -> CVDResult:
        buy_vol = 0.0
        sell_vol = 0.0
        cvd_series: list[float] = []
        running_cvd = 0.0

        for t in trades:
            if t.is_buyer_maker:
                sell_vol += t.quantity
                running_cvd -= t.quantity
            else:
                buy_vol += t.quantity
                running_cvd += t.quantity
            cvd_series.append(running_cvd)

        # CVD slope: linear regression slope over last N points
        slope = 0.0
        n = min(len(cvd_series), 50)
        if n >= 2:
            recent = cvd_series[-n:]
            x_mean = (n - 1) / 2.0
            y_mean = sum(recent) / n
            num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(recent))
            den = sum((i - x_mean) ** 2 for i in range(n))
            slope = num / den if den > 0 else 0.0

        return CVDResult(
            cvd=running_cvd,
            buy_volume=buy_vol,
            sell_volume=sell_vol,
            cvd_slope=slope,
        )

    @staticmethod
    def _compute_volatility(bars: list[OHLCV]) -> VolatilityResult:
        # Realized volatility (std of log returns)
        log_returns: list[float] = []
        for i in range(1, len(bars)):
            if bars[i - 1].close > 0 and bars[i].close > 0:
                lr = math.log(bars[i].close / bars[i - 1].close)
                log_returns.append(lr)

        realized_vol = 0.0
        if len(log_returns) >= 2:
            mean_r = sum(log_returns) / len(log_returns)
            variance = sum((r - mean_r) ** 2 for r in log_returns) / (len(log_returns) - 1)
            realized_vol = math.sqrt(variance)

        # Parkinson estimator (high-low range)
        parkinson_sum = 0.0
        valid_bars = 0
        for bar in bars:
            if bar.high > 0 and bar.low > 0 and bar.high != bar.low:
                parkinson_sum += (math.log(bar.high / bar.low)) ** 2
                valid_bars += 1
        parkinson_vol = 0.0
        if valid_bars > 0:
            parkinson_vol = math.sqrt(parkinson_sum / (4 * valid_bars * math.log(2)))

        # ATR (Average True Range)
        true_ranges: list[float] = []
        for i in range(1, len(bars)):
            tr = max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - bars[i - 1].close),
                abs(bars[i].low - bars[i - 1].close),
            )
            true_ranges.append(tr)
        atr = sum(true_ranges) / len(true_ranges) if true_ranges else 0.0

        return VolatilityResult(
            realized_vol=realized_vol,
            parkinson_vol=parkinson_vol,
            atr=atr,
        )

    @staticmethod
    def _compute_momentum(bars: list[OHLCV]) -> MomentumResult:
        closes = [b.close for b in bars if b.close > 0]
        if len(closes) < 3:
            return MomentumResult(roc=0.0, acceleration=0.0, trend_strength=0.0)

        # Rate of change (last vs N bars ago)
        lookback = min(len(closes) - 1, 20)
        roc = (closes[-1] - closes[-1 - lookback]) / closes[-1 - lookback] if closes[-1 - lookback] > 0 else 0.0

        # Acceleration (change in rate of change)
        if len(closes) >= 4:
            roc_prev = (closes[-2] - closes[-2 - min(lookback, len(closes) - 3)]) / closes[-2 - min(lookback, len(closes) - 3)] if closes[-2 - min(lookback, len(closes) - 3)] > 0 else 0.0
            acceleration = roc - roc_prev
        else:
            acceleration = 0.0

        # Trend strength: normalized absolute momentum (0-1)
        # Using a simple ratio of directional moves to total moves
        up_moves = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1])
        total_moves = len(closes) - 1
        trend_strength = abs(2 * (up_moves / total_moves) - 1) if total_moves > 0 else 0.0

        return MomentumResult(roc=roc, acceleration=acceleration, trend_strength=trend_strength)
