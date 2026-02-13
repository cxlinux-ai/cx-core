"""Late Entry V3 Strategy: enter on the market-phase favorite ~3-4 min before close."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from config.markets import MarketInfo
from config.strategy import StrategyConfig
from src.data.data_store import DataStore
from src.indicators.core import CoreIndicators
from src.indicators.edge import EdgeCalculator, EdgeResult
from src.indicators.market_phase import MarketPhase, PhaseDetector, PhaseInfo
from src.indicators.orderbook import OrderbookIndicators, OrderbookMetrics
from src.strategy.signal_engine import Direction, Signal, SignalEngine
from src.strategy.risk_manager import RiskManager

logger = logging.getLogger(__name__)


@dataclass
class TradeDecision:
    """Output of the strategy evaluation for a single market."""
    market: MarketInfo
    signal: Signal
    phase_info: PhaseInfo
    edge_result: EdgeResult
    position_size_usdc: float
    should_trade: bool
    skip_reason: str = ""


class LateEntryStrategy:
    """Late Entry V3 — enter on the favorite in the last ~4 minutes before close.

    Core logic:
    1. Wait for Phase 3 of market (last ~4 minutes before close)
    2. Identify the current market leader (YES vs NO)
    3. Compute edge: is the leader's price below fair value?
    4. Check confirmations: CVD, orderbook imbalance, Binance momentum
    5. If edge > threshold AND confirmations align → enter on favorite
    6. Size position with fractional Kelly criterion
    7. Hold until resolution (binary outcome)
    """

    def __init__(
        self,
        store: DataStore,
        strategy_config: StrategyConfig,
        risk_manager: RiskManager,
        signal_engine: SignalEngine | None = None,
    ) -> None:
        self._store = store
        self._config = strategy_config
        self._risk = risk_manager
        self._core = CoreIndicators(store)
        self._orderbook = OrderbookIndicators(store)
        self._edge_calc = EdgeCalculator(store, self._core)
        self._phase_detector = PhaseDetector()
        self._signal_engine = signal_engine or SignalEngine()

    async def evaluate(
        self,
        market: MarketInfo,
        yes_price: float,
        no_price: float,
    ) -> TradeDecision:
        """Evaluate whether to enter a position on this market.

        Returns a TradeDecision with the signal, edge, and sizing.
        """
        # 1. Detect market phase
        phase_info = self._phase_detector.detect(market, yes_price, no_price)

        # Early return if not in trading phase
        if phase_info.phase != MarketPhase.LATE:
            return TradeDecision(
                market=market,
                signal=Signal(direction=Direction.HOLD, edge=0.0, confidence=0.0,
                              reasons=[f"Phase: {phase_info.phase.value}"]),
                phase_info=phase_info,
                edge_result=EdgeResult(
                    fair_value_yes=0.5, fair_value_no=0.5,
                    polymarket_yes_price=yes_price, polymarket_no_price=no_price,
                    edge_yes=0.0, edge_no=0.0,
                    best_side="NONE", best_edge=0.0, fee_adjusted_edge=0.0,
                    binance_price_change_pct=0.0, confidence=0.0,
                ),
                position_size_usdc=0.0,
                should_trade=False,
                skip_reason=f"Not in late phase (current: {phase_info.phase.value})",
            )

        # Check if within entry window
        if phase_info.remaining_seconds > self._config.entry_window_seconds:
            return TradeDecision(
                market=market,
                signal=Signal(direction=Direction.HOLD, edge=0.0, confidence=0.0,
                              reasons=["Outside entry window"]),
                phase_info=phase_info,
                edge_result=EdgeResult(
                    fair_value_yes=0.5, fair_value_no=0.5,
                    polymarket_yes_price=yes_price, polymarket_no_price=no_price,
                    edge_yes=0.0, edge_no=0.0,
                    best_side="NONE", best_edge=0.0, fee_adjusted_edge=0.0,
                    binance_price_change_pct=0.0, confidence=0.0,
                ),
                position_size_usdc=0.0,
                should_trade=False,
                skip_reason=f"Entry window not reached ({phase_info.remaining_seconds:.0f}s remaining)",
            )

        # 2. Check risk limits
        if not self._risk.is_trading_allowed:
            return TradeDecision(
                market=market,
                signal=Signal(direction=Direction.HOLD, edge=0.0, confidence=0.0,
                              reasons=["Risk limit reached"]),
                phase_info=phase_info,
                edge_result=EdgeResult(
                    fair_value_yes=0.5, fair_value_no=0.5,
                    polymarket_yes_price=yes_price, polymarket_no_price=no_price,
                    edge_yes=0.0, edge_no=0.0,
                    best_side="NONE", best_edge=0.0, fee_adjusted_edge=0.0,
                    binance_price_change_pct=0.0, confidence=0.0,
                ),
                position_size_usdc=0.0,
                should_trade=False,
                skip_reason=f"Risk limit: {self._risk.state.kill_reason or 'max positions'}",
            )

        # 3. Compute edge
        # Detect if this is an UP or DOWN market from the question
        direction = "UP" if "up" in market.question.lower() else "DOWN"
        edge_result = await self._edge_calc.compute(
            asset=market.asset.value,
            yes_price=yes_price,
            no_price=no_price,
            market_remaining_seconds=phase_info.remaining_seconds,
            strike_direction=direction,
        )

        # 4. Get indicators for signal engine
        core_snap = await self._core.compute(market.asset.value)
        book_metrics = await self._orderbook.compute(market.asset.value, source="polymarket")

        # 5. Generate signal
        signal = self._signal_engine.evaluate(
            edge_result=edge_result,
            phase_info=phase_info,
            core_indicators=core_snap,
            orderbook_metrics=book_metrics,
            min_edge_pct=self._config.min_edge_pct,
            min_leader_confidence=self._config.min_leader_confidence,
            required_confirmations=self._config.required_confirmations,
        )

        # 6. Compute position size if signal is actionable
        position_size = 0.0
        should_trade = signal.direction != Direction.HOLD

        if should_trade:
            leader_price = max(yes_price, no_price)
            # Use the price of the side we're buying as entry price for Kelly odds
            entry_price = yes_price if signal.direction == Direction.BUY_YES else no_price
            position_size = self._risk.compute_position_size(
                edge=signal.edge,
                win_probability=edge_result.fair_value_yes if signal.direction == Direction.BUY_YES else edge_result.fair_value_no,
                max_position=self._config.max_position_usdc,
                entry_price=entry_price,
            )
            if position_size < 1.0:  # Minimum viable position
                should_trade = False
                signal = Signal(
                    direction=Direction.HOLD,
                    edge=signal.edge,
                    confidence=signal.confidence,
                    reasons=signal.reasons + [f"Position size too small: ${position_size:.2f}"],
                )
                position_size = 0.0

        skip_reason = "" if should_trade else (signal.reasons[0] if signal.reasons else "No signal")

        decision = TradeDecision(
            market=market,
            signal=signal,
            phase_info=phase_info,
            edge_result=edge_result,
            position_size_usdc=position_size,
            should_trade=should_trade,
            skip_reason=skip_reason,
        )

        if should_trade:
            logger.info(
                "TRADE SIGNAL: %s %s | edge=%.3f | size=$%.2f | %s",
                signal.direction.value,
                market.asset.value,
                signal.edge,
                position_size,
                market.question[:50],
            )
        else:
            logger.debug(
                "No trade: %s | %s | %s",
                market.asset.value,
                phase_info.phase.value,
                skip_reason,
            )

        return decision

    def cleanup_market(self, condition_id: str) -> None:
        """Clean up state for a resolved market."""
        self._phase_detector.cleanup(condition_id)
