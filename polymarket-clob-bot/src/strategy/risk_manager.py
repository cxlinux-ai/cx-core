"""Risk manager: position sizing, exposure limits, drawdown, kill switch."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

from config.settings import RiskSettings

logger = logging.getLogger(__name__)


@dataclass
class RiskState:
    """Current risk state of the trading session."""
    daily_pnl: float = 0.0
    session_peak_balance: float = 0.0
    current_balance: float = 0.0
    consecutive_losses: int = 0
    active_positions: int = 0
    is_killed: bool = False
    kill_reason: str = ""
    trades_today: int = 0
    wins_today: int = 0
    losses_today: int = 0


class RiskManager:
    """Enforces risk limits and computes position sizing."""

    def __init__(self, settings: RiskSettings, initial_balance: float = 0.0) -> None:
        self._settings = settings
        self._state = RiskState(
            current_balance=initial_balance,
            session_peak_balance=initial_balance,
        )
        self._daily_reset_time = time.time()

    @property
    def state(self) -> RiskState:
        return self._state

    @property
    def is_trading_allowed(self) -> bool:
        """Check if all risk conditions allow trading."""
        if self._state.is_killed:
            return False

        self._check_daily_reset()

        if self._state.daily_pnl <= -self._settings.max_daily_loss_usdc:
            self._kill(f"Daily loss limit hit: ${self._state.daily_pnl:.2f}")
            return False

        if self._state.consecutive_losses >= self._settings.max_consecutive_losses:
            self._kill(
                f"Consecutive losses: {self._state.consecutive_losses}"
            )
            return False

        drawdown = self._current_drawdown()
        if drawdown >= self._settings.max_drawdown_pct:
            self._kill(f"Max drawdown hit: {drawdown:.1%}")
            return False

        if self._state.active_positions >= self._settings.max_concurrent_positions:
            return False

        return True

    def compute_position_size(
        self,
        edge: float,
        win_probability: float,
        max_position: float,
    ) -> float:
        """Compute position size using fractional Kelly criterion.

        Kelly formula: f* = (bp - q) / b
        where b = odds, p = win prob, q = 1 - p
        """
        if edge <= 0 or win_probability <= 0.5:
            return 0.0

        # Kelly sizing
        # For binary outcomes at Polymarket: payoff is 1/price - 1
        # Simplified: edge-proportional sizing
        b = (1.0 / win_probability) - 1.0  # odds
        q = 1.0 - win_probability
        kelly_fraction = (b * win_probability - q) / b if b > 0 else 0.0

        # Apply fractional Kelly (conservative)
        from config.strategy import StrategyConfig
        strategy = StrategyConfig()
        sized = kelly_fraction * strategy.kelly_fraction * self._state.current_balance

        # Apply limits
        remaining_daily = self._settings.max_daily_loss_usdc + self._state.daily_pnl
        sized = min(sized, max_position, remaining_daily)
        sized = max(sized, 0.0)

        # Round to 2 decimals (USDC precision)
        return math.floor(sized * 100) / 100

    def record_trade_result(self, pnl: float) -> None:
        """Record a completed trade outcome."""
        self._state.daily_pnl += pnl
        self._state.current_balance += pnl
        self._state.trades_today += 1

        if pnl > 0:
            self._state.wins_today += 1
            self._state.consecutive_losses = 0
            self._state.session_peak_balance = max(
                self._state.session_peak_balance, self._state.current_balance
            )
        elif pnl < 0:
            self._state.losses_today += 1
            self._state.consecutive_losses += 1

        logger.info(
            "Trade recorded: PnL=$%.2f | Daily=$%.2f | Streak=%d | Balance=$%.2f",
            pnl,
            self._state.daily_pnl,
            -self._state.consecutive_losses if self._state.consecutive_losses > 0 else 0,
            self._state.current_balance,
        )

    def add_position(self) -> None:
        self._state.active_positions += 1

    def remove_position(self) -> None:
        self._state.active_positions = max(0, self._state.active_positions - 1)

    def update_balance(self, balance: float) -> None:
        self._state.current_balance = balance
        self._state.session_peak_balance = max(self._state.session_peak_balance, balance)

    def kill(self) -> None:
        """Emergency kill switch — stop all trading."""
        self._kill("Manual kill switch activated")

    def reset_kill(self) -> None:
        """Reset the kill switch to resume trading."""
        self._state.is_killed = False
        self._state.kill_reason = ""
        self._state.consecutive_losses = 0
        logger.info("Kill switch reset — trading resumed")

    def summary(self) -> str:
        lines = [
            f"  Balance: ${self._state.current_balance:.2f}",
            f"  Daily P&L: ${self._state.daily_pnl:.2f}",
            f"  Trades: {self._state.trades_today} (W:{self._state.wins_today} L:{self._state.losses_today})",
            f"  Active positions: {self._state.active_positions}/{self._settings.max_concurrent_positions}",
            f"  Drawdown: {self._current_drawdown():.1%}",
            f"  Kill switch: {'ON — ' + self._state.kill_reason if self._state.is_killed else 'OFF'}",
        ]
        return "\n".join(lines)

    def _kill(self, reason: str) -> None:
        self._state.is_killed = True
        self._state.kill_reason = reason
        logger.warning("KILL SWITCH ACTIVATED: %s", reason)

    def _current_drawdown(self) -> float:
        if self._state.session_peak_balance <= 0:
            return 0.0
        return (
            (self._state.session_peak_balance - self._state.current_balance)
            / self._state.session_peak_balance
        )

    def _check_daily_reset(self) -> None:
        """Reset daily stats if a new day has started."""
        now = time.time()
        if now - self._daily_reset_time > 86400:
            self._state.daily_pnl = 0.0
            self._state.trades_today = 0
            self._state.wins_today = 0
            self._state.losses_today = 0
            self._daily_reset_time = now
            logger.info("Daily risk stats reset")
