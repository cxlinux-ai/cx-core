"""Signal engine: aggregates indicators into a unified trading signal."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from src.indicators.core import IndicatorSnapshot
from src.indicators.edge import EdgeResult
from src.indicators.market_phase import PhaseInfo
from src.indicators.orderbook import OrderbookMetrics

logger = logging.getLogger(__name__)


class Direction(str, Enum):
    BUY_YES = "BUY_YES"
    BUY_NO = "BUY_NO"
    HOLD = "HOLD"


@dataclass
class Signal:
    """Unified trading signal output."""
    direction: Direction
    edge: float
    confidence: float
    reasons: list[str] = field(default_factory=list)
    indicators_snapshot: dict | None = None


class SignalEngine:
    """Aggregates all indicator outputs into a BUY_YES / BUY_NO / HOLD signal."""

    def __init__(self, ml_predictor: object | None = None) -> None:
        self._ml_predictor = ml_predictor

    def evaluate(
        self,
        edge_result: EdgeResult,
        phase_info: PhaseInfo,
        core_indicators: IndicatorSnapshot,
        orderbook_metrics: OrderbookMetrics | None,
        min_edge_pct: float = 0.02,
        min_leader_confidence: float = 0.60,
        required_confirmations: int = 2,
    ) -> Signal:
        """Evaluate all inputs and produce a trading signal."""
        reasons: list[str] = []
        confirmations = 0

        # 1. Check edge threshold
        has_edge = edge_result.fee_adjusted_edge >= min_edge_pct
        if has_edge:
            reasons.append(
                f"Edge {edge_result.fee_adjusted_edge:.3f} >= {min_edge_pct:.3f} "
                f"(side={edge_result.best_side})"
            )

        # 2. Check leader confidence
        leader_price = max(edge_result.polymarket_yes_price, edge_result.polymarket_no_price)
        leader_confident = leader_price >= min_leader_confidence
        if leader_confident:
            reasons.append(f"Leader price {leader_price:.3f} >= {min_leader_confidence:.3f}")

        # 3. CVD direction confirmation
        cvd_confirms = False
        if core_indicators.cvd:
            if edge_result.best_side == "YES" and core_indicators.cvd.cvd_slope > 0:
                cvd_confirms = True
                confirmations += 1
                reasons.append(f"CVD slope positive ({core_indicators.cvd.cvd_slope:.4f})")
            elif edge_result.best_side == "NO" and core_indicators.cvd.cvd_slope < 0:
                cvd_confirms = True
                confirmations += 1
                reasons.append(f"CVD slope negative ({core_indicators.cvd.cvd_slope:.4f})")

        # 4. Orderbook imbalance confirmation
        book_confirms = False
        if orderbook_metrics:
            if edge_result.best_side == "YES" and orderbook_metrics.bid_ask_imbalance > 0.1:
                book_confirms = True
                confirmations += 1
                reasons.append(
                    f"Book imbalance bullish ({orderbook_metrics.bid_ask_imbalance:.3f})"
                )
            elif edge_result.best_side == "NO" and orderbook_metrics.bid_ask_imbalance < -0.1:
                book_confirms = True
                confirmations += 1
                reasons.append(
                    f"Book imbalance bearish ({orderbook_metrics.bid_ask_imbalance:.3f})"
                )

        # 5. Binance momentum confirmation
        momentum_confirms = False
        if core_indicators.momentum:
            roc = core_indicators.momentum.roc
            if edge_result.best_side == "YES" and roc > 0:
                momentum_confirms = True
                confirmations += 1
                reasons.append(f"Binance momentum positive ({roc:.5f})")
            elif edge_result.best_side == "NO" and roc < 0:
                momentum_confirms = True
                confirmations += 1
                reasons.append(f"Binance momentum negative ({roc:.5f})")

        # 6. ML model prediction (optional)
        ml_boost = 0.0
        if self._ml_predictor is not None:
            try:
                prediction = self._ml_predictor.predict(core_indicators, orderbook_metrics)
                if prediction and prediction.probability > 0.55:
                    ml_boost = 0.02
                    reasons.append(f"ML model confirms ({prediction.probability:.3f})")
            except Exception as exc:
                logger.debug("ML predictor error: %s", exc)

        # Decision logic
        if not has_edge:
            direction = Direction.HOLD
            reasons.insert(0, f"Insufficient edge: {edge_result.fee_adjusted_edge:.3f}")
        elif not leader_confident:
            direction = Direction.HOLD
            reasons.insert(0, f"Leader not confident enough: {leader_price:.3f}")
        elif confirmations < required_confirmations:
            direction = Direction.HOLD
            reasons.insert(0, f"Only {confirmations}/{required_confirmations} confirmations")
        else:
            direction = (
                Direction.BUY_YES if edge_result.best_side == "YES" else Direction.BUY_NO
            )

        combined_edge = edge_result.fee_adjusted_edge + ml_boost
        confidence = edge_result.confidence * phase_info.confidence

        signal = Signal(
            direction=direction,
            edge=combined_edge,
            confidence=confidence,
            reasons=reasons,
            indicators_snapshot={
                "edge": edge_result.best_edge,
                "fee_adj_edge": edge_result.fee_adjusted_edge,
                "leader_price": leader_price,
                "confirmations": confirmations,
                "phase": phase_info.phase.value,
                "remaining_s": phase_info.remaining_seconds,
            },
        )

        logger.info(
            "Signal: %s | edge=%.3f | conf=%.2f | confirmations=%d | %s",
            direction.value,
            combined_edge,
            confidence,
            confirmations,
            "; ".join(reasons[:3]),
        )

        return signal
