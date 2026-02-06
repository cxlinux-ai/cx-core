"""Main orchestrator — entrypoint that wires and runs all components."""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import signal
import sys
import time
from pathlib import Path

from config.settings import Settings
from config.strategy import StrategyConfig
from config.markets import MarketConfig
from src.analytics.pnl_tracker import PnlTracker
from src.analytics.trade_logger import TradeLogEntry, SignalLogEntry, TradeLogger
from src.data.binance_feed import BinanceFeed
from src.data.chainlink_oracle import ChainlinkOracle
from src.data.data_store import DataStore
from src.data.polymarket_feed import PolymarketFeed
from src.execution.clob_client import ClobClient, OrderSide
from src.execution.order_manager import OrderManager
from src.execution.redeemer import Redeemer
from src.indicators.market_phase import MarketPhase
from src.ml.predictor import Predictor
from src.strategy.late_entry import LateEntryStrategy
from src.strategy.risk_manager import RiskManager
from src.strategy.signal_engine import Direction, SignalEngine
from src.telegram.bot import TelegramBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            "bot.log", maxBytes=10 * 1024 * 1024, backupCount=5
        ),
    ],
)
# Quiet noisy libraries
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class Bot:
    """Top-level orchestrator that manages all subsystems."""

    HEARTBEAT_INTERVAL = 60.0
    EVAL_INTERVAL = 5.0  # Seconds between strategy evaluations

    def __init__(self) -> None:
        self._running = False
        self._settings = Settings()
        self._strategy_config = StrategyConfig()

        # Core data layer
        self._store = DataStore()
        self._binance_feed = BinanceFeed(self._store)
        self._polymarket_feed = PolymarketFeed(self._store, MarketConfig())
        self._chainlink = ChainlinkOracle(self._store)

        # Execution
        self._clob = ClobClient(self._settings.polymarket)
        self._order_manager = OrderManager(self._clob)
        self._redeemer = Redeemer(self._clob)

        # Analytics
        self._pnl = PnlTracker()
        self._trade_logger = TradeLogger(self._settings.data.data_dir)

        # ML (optional)
        self._predictor = Predictor(self._settings.data.data_dir)

        # Strategy
        self._risk = RiskManager(self._settings.risk)
        self._signal_engine = SignalEngine(
            ml_predictor=self._predictor if self._predictor.is_loaded else None
        )
        self._strategy = LateEntryStrategy(
            store=self._store,
            strategy_config=self._strategy_config,
            risk_manager=self._risk,
            signal_engine=self._signal_engine,
        )

        # Telegram
        self._telegram = TelegramBot(
            settings=self._settings.telegram,
            pnl_tracker=self._pnl,
            risk_manager=self._risk,
            strategy_config=self._strategy_config,
            clob_client=self._clob,
            order_manager=self._order_manager,
        )

        # Active trade tracking
        self._active_trades: dict[str, dict] = {}  # condition_id -> trade info

    async def run(self) -> None:
        """Main entry point — start everything and run the event loop."""
        logger.info("Loading config from .env")

        # Validate config
        issues = self._settings.validate()
        for issue in issues:
            logger.warning("Config: %s", issue)

        # Initialize CLOB client
        if not await self._clob.initialize():
            logger.error("Failed to initialize CLOB client — check credentials")
            return

        balance = await self._clob.get_balance()
        logger.info("CLOB client authenticated — Balance: $%.2f USDC", balance)
        self._risk.update_balance(balance)

        # Set up redeemer callback
        self._redeemer.set_redeem_callback(self._on_redemption)

        # Set up Telegram callbacks
        self._telegram.set_callbacks(
            on_start=self._on_telegram_start,
            on_stop=self._on_telegram_stop,
        )

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        self._running = True

        # Launch all subsystems concurrently
        tasks = [
            asyncio.create_task(self._binance_feed.start(), name="binance_feed"),
            asyncio.create_task(self._polymarket_feed.start(), name="polymarket_feed"),
            asyncio.create_task(self._chainlink.start(), name="chainlink_oracle"),
            asyncio.create_task(self._telegram.start(), name="telegram_bot"),
            asyncio.create_task(self._redeemer.start(), name="redeemer"),
            asyncio.create_task(self._main_loop(), name="main_loop"),
            asyncio.create_task(self._heartbeat_loop(), name="heartbeat"),
        ]

        logger.info("Bot running. Waiting for Phase 3 entry window...")

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        finally:
            self._trade_logger.close()
            logger.info("Bot shut down.")

    async def shutdown(self) -> None:
        """Graceful shutdown — stop all components."""
        if not self._running:
            return
        self._running = False
        logger.info("Shutting down...")

        await self._binance_feed.stop()
        await self._polymarket_feed.stop()
        await self._chainlink.stop()
        await self._redeemer.stop()
        await self._telegram.stop()

        # Cancel remaining orders
        await self._order_manager.cancel_all()

        self._trade_logger.close()

    async def _main_loop(self) -> None:
        """Core trading loop: discover → evaluate → execute → track."""
        # Wait for data feeds to initialize
        await asyncio.sleep(5)

        while self._running:
            try:
                await self._evaluate_all_markets()
                await self._check_resolutions()
                await self._order_manager.cleanup_stale()
            except Exception as exc:
                logger.error("Main loop error: %s", exc, exc_info=True)

            await asyncio.sleep(self.EVAL_INTERVAL)

    async def _evaluate_all_markets(self) -> None:
        """Evaluate strategy for all active Polymarket markets."""
        active_markets = self._polymarket_feed.active_markets

        for cid, state in active_markets.items():
            if cid in self._active_trades:
                continue  # Already have a position in this market

            try:
                decision = await self._strategy.evaluate(
                    market=state.market,
                    yes_price=state.yes_price,
                    no_price=state.no_price,
                )

                # Log signal evaluation
                if self._settings.data.log_trades_csv:
                    self._trade_logger.log_signal(SignalLogEntry(
                        timestamp=time.time(),
                        asset=state.market.asset.value,
                        market_id=cid,
                        signal_direction=decision.signal.direction.value,
                        edge=decision.signal.edge,
                        confidence=decision.signal.confidence,
                        phase=decision.phase_info.phase.value,
                        reasons="; ".join(decision.signal.reasons[:3]),
                        traded=decision.should_trade,
                    ))

                if decision.should_trade:
                    await self._execute_trade(cid, state, decision)

            except Exception as exc:
                logger.debug("Error evaluating market %s: %s", cid[:8], exc)

    async def _execute_trade(self, cid: str, state, decision) -> None:
        """Execute a trade based on the strategy decision."""
        # Determine which token to buy
        if decision.signal.direction == Direction.BUY_YES:
            token_id = state.market.yes_token_id
            side_str = "BUY_YES"
            entry_price = state.yes_price
        else:
            token_id = state.market.no_token_id
            side_str = "BUY_NO"
            entry_price = state.no_price

        logger.info(
            "Executing: %s %s $%.2f @ %.4f (edge=%.3f)",
            side_str, state.market.asset.value, decision.position_size_usdc,
            entry_price, decision.signal.edge,
        )

        # Place market order
        order = await self._order_manager.place_market_order(
            token_id=token_id,
            side=OrderSide.BUY,
            size_usdc=decision.position_size_usdc,
            asset=state.market.asset.value,
            condition_id=cid,
        )

        if order.status.value in ("SUBMITTED", "MATCHED", "CONFIRMED"):
            self._active_trades[cid] = {
                "order": order,
                "side": side_str,
                "entry_price": entry_price,
                "size": decision.position_size_usdc,
                "edge": decision.signal.edge,
                "asset": state.market.asset.value,
                "phase": decision.phase_info.phase.value,
                "leader_confidence": max(state.yes_price, state.no_price),
            }
            self._risk.add_position()
            self._redeemer.add_pending(cid, token_id)

            # Telegram alert
            await self._telegram.alert_trade(
                side=side_str,
                asset=state.market.asset.value,
                price=entry_price,
                size=decision.position_size_usdc,
                edge=decision.signal.edge,
            )
        else:
            logger.warning("Order failed: %s", order.error)

    async def _check_resolutions(self) -> None:
        """Check if any active trades' markets have resolved."""
        active_markets = self._polymarket_feed.active_markets

        for cid in list(self._active_trades.keys()):
            state = active_markets.get(cid)
            if state is None:
                # Market no longer active — likely resolved
                trade_info = self._active_trades.pop(cid)
                await self._handle_resolution(cid, trade_info, resolved=True)
            elif state.market.resolved:
                trade_info = self._active_trades.pop(cid)
                await self._handle_resolution(
                    cid, trade_info, resolved=True, outcome=state.market.outcome
                )

    async def _handle_resolution(
        self, cid: str, trade_info: dict, resolved: bool = False, outcome: str | None = None
    ) -> None:
        """Process a market resolution for an active trade."""
        side = trade_info["side"]
        entry_price = trade_info["entry_price"]
        size = trade_info["size"]
        asset = trade_info["asset"]

        # Determine PnL
        # If outcome matches our side, we win (shares worth $1 each)
        # Our cost was entry_price * shares, where shares = size / entry_price
        shares = size / entry_price if entry_price > 0 else 0
        won = False
        if outcome:
            won = (outcome == "YES" and side == "BUY_YES") or (
                outcome == "NO" and side == "BUY_NO"
            )

        if won:
            pnl = shares * 1.0 - size  # Won $1 per share, paid entry_price per share
        else:
            pnl = -size  # Lost entire position

        # Record
        self._pnl.record_trade(
            asset=asset,
            side=side,
            entry_price=entry_price,
            size_usdc=size,
            pnl=pnl,
            edge_at_entry=trade_info.get("edge", 0),
        )
        self._risk.record_trade_result(pnl)
        self._risk.remove_position()

        if self._settings.data.log_trades_csv:
            self._trade_logger.log_trade(TradeLogEntry(
                timestamp=time.time(),
                asset=asset,
                market_id=cid,
                side=side,
                entry_price=entry_price,
                size_usdc=size,
                edge_at_entry=trade_info.get("edge", 0),
                phase=trade_info.get("phase", ""),
                leader_confidence=trade_info.get("leader_confidence", 0),
                outcome="WIN" if won else "LOSS",
                pnl=pnl,
                cumulative_pnl=0.0,  # Logger will compute this
            ))

        # Telegram alert
        await self._telegram.alert_resolution(
            asset=asset,
            outcome=f"{'WIN' if won else 'LOSS'} ({outcome or 'unknown'})",
            pnl=pnl,
        )

        # Check risk state
        if self._risk.state.is_killed:
            await self._telegram.alert_risk(self._risk.state.kill_reason)

        self._strategy.cleanup_market(cid)

        logger.info(
            "Resolution: %s %s PnL=$%.2f outcome=%s",
            asset, side, pnl, outcome or "unknown",
        )

    async def _on_redemption(self, result) -> None:
        """Callback when a position is successfully redeemed."""
        logger.info("Redeemed $%.2f for %s", result.amount, result.condition_id[:8])
        # Update balance
        balance = await self._clob.get_balance()
        self._risk.update_balance(balance)

    async def _on_telegram_start(self) -> None:
        """Callback when /start is received via Telegram."""
        if self._risk.state.is_killed:
            self._risk.reset_kill()
        logger.info("Trading resumed via Telegram")

    async def _on_telegram_stop(self) -> None:
        """Callback when /stop is received via Telegram."""
        await self._order_manager.cancel_all()
        logger.info("Trading paused via Telegram")

    async def _heartbeat_loop(self) -> None:
        """Log system health every HEARTBEAT_INTERVAL seconds."""
        while self._running:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            active_markets = len(self._polymarket_feed.active_markets)
            active_trades = len(self._active_trades)
            balance = self._risk.state.current_balance
            daily_pnl = self._risk.state.daily_pnl
            logger.info(
                "Heartbeat: markets=%d trades=%d balance=$%.2f daily_pnl=$%.2f killed=%s",
                active_markets,
                active_trades,
                balance,
                daily_pnl,
                self._risk.state.is_killed,
            )


def main() -> None:
    bot = Bot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    main()
