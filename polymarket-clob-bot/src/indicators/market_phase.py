"""Market phase detection for 15-minute prediction markets."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from config.markets import MarketInfo


class MarketPhase(str, Enum):
    EARLY = "early"          # 0:00 - 5:00 — high noise, skip trading
    TRANSITION = "transition" # 5:00 - 11:00 — information pricing in, monitor only
    LATE = "late"            # 11:00 - 15:00 — entry window, market leader likely holds
    CLOSED = "closed"        # Market has ended


@dataclass
class PhaseInfo:
    phase: MarketPhase
    elapsed_seconds: float
    remaining_seconds: float
    elapsed_pct: float  # 0.0 to 1.0
    confidence: float  # Phase detection confidence
    leader_stability: float  # How stable the leader has been (0-1)
    reversal_probability: float  # Estimated probability leader changes
    signal_noise_ratio: float  # Higher = cleaner signal


# Phase boundaries in seconds
PHASE_1_END = 300   # 5 minutes
PHASE_2_END = 660   # 11 minutes
MARKET_DURATION = 900  # 15 minutes


class PhaseDetector:
    """Detects the current phase of a 15-minute market and computes phase metrics."""

    def __init__(self) -> None:
        # Track leader history per market for stability calculation
        self._leader_history: dict[str, list[tuple[float, str]]] = {}

    def detect(
        self,
        market: MarketInfo,
        yes_price: float,
        no_price: float,
    ) -> PhaseInfo:
        """Determine the current market phase and compute metrics."""
        now = time.time()
        market_start = market.close_timestamp - MARKET_DURATION
        elapsed = now - market_start
        remaining = market.close_timestamp - now

        if remaining <= 0:
            return PhaseInfo(
                phase=MarketPhase.CLOSED,
                elapsed_seconds=MARKET_DURATION,
                remaining_seconds=0,
                elapsed_pct=1.0,
                confidence=1.0,
                leader_stability=0.0,
                reversal_probability=0.0,
                signal_noise_ratio=0.0,
            )

        elapsed = max(0, min(elapsed, MARKET_DURATION))
        elapsed_pct = elapsed / MARKET_DURATION

        # Determine phase
        if elapsed < PHASE_1_END:
            phase = MarketPhase.EARLY
        elif elapsed < PHASE_2_END:
            phase = MarketPhase.TRANSITION
        else:
            phase = MarketPhase.LATE

        # Determine current leader
        current_leader = "YES" if yes_price >= no_price else "NO"
        leader_price = max(yes_price, no_price)

        # Track leader history
        cid = market.condition_id
        if cid not in self._leader_history:
            self._leader_history[cid] = []
        self._leader_history[cid].append((now, current_leader))

        # Compute leader stability (fraction of recent time the current leader has led)
        history = self._leader_history[cid]
        if len(history) >= 2:
            recent = history[-min(len(history), 60):]  # Last ~60 samples
            same_leader = sum(1 for _, l in recent if l == current_leader)
            leader_stability = same_leader / len(recent)
        else:
            leader_stability = 0.5

        # Reversal probability decreases as we approach close and leader is stronger
        base_reversal = 0.5 * (1 - elapsed_pct)  # Decreases over time
        price_factor = 1.0 - abs(yes_price - 0.5) * 2  # Lower when price is extreme
        reversal_probability = max(0.0, min(1.0, base_reversal * price_factor))

        # Signal-to-noise ratio increases with time and leader strength
        snr = elapsed_pct * leader_stability * (1 + abs(yes_price - 0.5))

        # Phase confidence
        confidence = min(1.0, leader_stability * (0.5 + elapsed_pct))

        return PhaseInfo(
            phase=phase,
            elapsed_seconds=elapsed,
            remaining_seconds=remaining,
            elapsed_pct=elapsed_pct,
            confidence=confidence,
            leader_stability=leader_stability,
            reversal_probability=reversal_probability,
            signal_noise_ratio=snr,
        )

    def cleanup(self, condition_id: str) -> None:
        """Remove history for a resolved market."""
        self._leader_history.pop(condition_id, None)
