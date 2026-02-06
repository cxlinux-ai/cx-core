"""Edge calculation: fair value model, Polymarket vs Binance price delta."""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.data.data_store import DataStore
from src.indicators.core import CoreIndicators, IndicatorSnapshot


@dataclass
class EdgeResult:
    """Computed edge for a market position."""
    fair_value_yes: float  # Model's estimated probability of YES outcome
    fair_value_no: float  # 1 - fair_value_yes
    polymarket_yes_price: float
    polymarket_no_price: float
    edge_yes: float  # fair_value_yes - polymarket_yes_price (positive = underpriced)
    edge_no: float  # fair_value_no - polymarket_no_price
    best_side: str  # "YES" or "NO"
    best_edge: float  # Max of edge_yes, edge_no
    fee_adjusted_edge: float  # Edge after accounting for fees
    binance_price_change_pct: float  # Binance price movement in market window
    confidence: float  # Model confidence (0-1)


# Polymarket fee structure
POLYMARKET_FEE_PCT = 0.02  # ~2% effective fee on winning positions


class EdgeCalculator:
    """Computes fair value and edge for Polymarket prediction markets.

    Uses Binance price data + volatility to estimate the true probability
    of the market outcome, then compares to Polymarket prices.
    """

    def __init__(self, store: DataStore, core_indicators: CoreIndicators) -> None:
        self._store = store
        self._core = core_indicators

    async def compute(
        self,
        asset: str,
        yes_price: float,
        no_price: float,
        market_remaining_seconds: float,
        strike_direction: str = "UP",  # "UP" or "DOWN"
    ) -> EdgeResult:
        """Compute edge for a market.

        Args:
            asset: Asset symbol (BTC, ETH, etc.)
            yes_price: Current Polymarket YES price
            no_price: Current Polymarket NO price
            market_remaining_seconds: Seconds until market closes
            strike_direction: Whether market resolves YES on UP or DOWN move
        """
        indicators = await self._core.compute(asset, source="binance")

        # Get Binance price data for fair value model
        binance_price_change = self._get_price_change(indicators)
        binance_vol = self._get_volatility(indicators)

        # Compute fair value probability using Black-Scholes-like model
        fair_value_yes = self._model_fair_value(
            price_change_pct=binance_price_change,
            volatility=binance_vol,
            remaining_seconds=market_remaining_seconds,
            direction=strike_direction,
            momentum=indicators.momentum.roc if indicators.momentum else 0.0,
            cvd_slope=indicators.cvd.cvd_slope if indicators.cvd else 0.0,
        )
        fair_value_no = 1.0 - fair_value_yes

        # Compute edges
        edge_yes = fair_value_yes - yes_price
        edge_no = fair_value_no - no_price

        if edge_yes >= edge_no:
            best_side = "YES"
            best_edge = edge_yes
        else:
            best_side = "NO"
            best_edge = edge_no

        fee_adjusted = best_edge - POLYMARKET_FEE_PCT

        # Confidence based on data quality and indicator agreement
        confidence = self._compute_confidence(indicators, market_remaining_seconds)

        return EdgeResult(
            fair_value_yes=fair_value_yes,
            fair_value_no=fair_value_no,
            polymarket_yes_price=yes_price,
            polymarket_no_price=no_price,
            edge_yes=edge_yes,
            edge_no=edge_no,
            best_side=best_side,
            best_edge=best_edge,
            fee_adjusted_edge=fee_adjusted,
            binance_price_change_pct=binance_price_change,
            confidence=confidence,
        )

    @staticmethod
    def _get_price_change(indicators: IndicatorSnapshot) -> float:
        if indicators.momentum:
            return indicators.momentum.roc
        return 0.0

    @staticmethod
    def _get_volatility(indicators: IndicatorSnapshot) -> float:
        if indicators.volatility:
            return indicators.volatility.realized_vol
        return 0.001  # Default low volatility

    @staticmethod
    def _model_fair_value(
        price_change_pct: float,
        volatility: float,
        remaining_seconds: float,
        direction: str,
        momentum: float,
        cvd_slope: float,
    ) -> float:
        """Estimate fair probability using a simplified model.

        Combines current price trajectory, volatility-adjusted time remaining,
        and order flow signals to estimate P(outcome = YES).

        For "UP" markets: YES wins if price is higher at close.
        For "DOWN" markets: YES wins if price is lower at close.
        """
        # Time decay factor: as time decreases, current state matters more
        # Remaining time as fraction of 15 min
        time_fraction = remaining_seconds / 900.0

        # Volatility-adjusted standard deviations remaining
        # More time + more vol = more uncertainty
        vol_adjusted = volatility * math.sqrt(max(time_fraction, 0.001))

        # Current "drift" — how much price has moved directionally
        drift = price_change_pct

        # CVD contribution (order flow momentum)
        flow_signal = 0.0
        if cvd_slope != 0:
            # Normalize CVD slope to a reasonable range
            flow_signal = max(-0.1, min(0.1, cvd_slope * 0.01))

        # Combined signal
        combined_signal = drift + flow_signal

        # For DOWN markets, invert the signal
        if direction == "DOWN":
            combined_signal = -combined_signal

        # Convert to probability using normal CDF approximation
        # z-score: how many vol-adjusted SDs is the signal
        if vol_adjusted > 0:
            z = combined_signal / vol_adjusted
        else:
            z = combined_signal * 100  # Very high confidence if no vol

        # Normal CDF approximation (Abramowitz & Stegun)
        prob = _normal_cdf(z)

        # As time runs out, probability gravitates toward current state
        # (less time for reversal)
        time_weight = 1.0 - time_fraction
        prob = prob * (1 - time_weight * 0.3) + (1.0 if combined_signal > 0 else 0.0) * (time_weight * 0.3)

        return max(0.01, min(0.99, prob))

    @staticmethod
    def _compute_confidence(indicators: IndicatorSnapshot, remaining_seconds: float) -> float:
        """Confidence in the fair value estimate (0-1)."""
        confidence = 0.5

        # More data = higher confidence
        if indicators.vwap and indicators.vwap.cumulative_volume > 0:
            confidence += 0.1
        if indicators.cvd:
            confidence += 0.1
        if indicators.volatility:
            confidence += 0.1

        # Less time remaining = higher confidence (less uncertainty)
        time_fraction = remaining_seconds / 900.0
        confidence += 0.2 * (1 - time_fraction)

        return min(1.0, confidence)


def _normal_cdf(x: float) -> float:
    """Approximate the standard normal CDF using the logistic approximation."""
    return 1.0 / (1.0 + math.exp(-1.7 * x))
