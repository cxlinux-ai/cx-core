"""
Addon modules: Arb Scanner, Whale Tracker, AI Event Trader.

These modules run independently of the core 15-min crypto strategy.
They can be:
  1. Imported and started from the existing main.py (recommended)
  2. Run standalone: python -m src.addons

Integration with existing main.py requires only ~10 lines of changes.
See INTEGRATION.md for details.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

from src.arb.scanner import ArbOpportunity, ArbScanner
from src.events.analyzer import MarketAnalyzer
from src.events.trader import EventSignal, EventTrader
from src.whale.tracker import WhaleTrade, WhaleTracker
from src.whale.wallets import WalletRegistry

logger = logging.getLogger(__name__)


class AddonRunner:
    """Manages the lifecycle of add-on trading modules."""

    def __init__(
        self,
        data_dir: str = "data",
        paper_trading: bool = True,
        send_telegram=None,  # Optional async callable(str) -> None
    ) -> None:
        self.paper_trading = paper_trading
        self._send_telegram = send_telegram
        self._running = False

        # --- Arb scanner ---
        self.arb_scanner = ArbScanner(on_arb_callback=self._on_arb_found)

        # --- Whale tracker ---
        wallets_path = Path(data_dir) / "whale_wallets.json"
        self.wallet_registry = WalletRegistry(wallets_path=wallets_path)
        self.whale_tracker = WhaleTracker(
            wallet_registry=self.wallet_registry,
            on_whale_trade=self._on_whale_trade,
        )

        # --- Event trader (requires ANTHROPIC_API_KEY) ---
        self.event_trader: Optional[EventTrader] = None
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key:
            analyzer = MarketAnalyzer(api_key=api_key)
            self.event_trader = EventTrader(
                analyzer=analyzer,
                on_signal=self._on_event_signal,
            )
            logger.info("Event trader enabled (Claude API)")
        else:
            logger.info("Event trader disabled (set ANTHROPIC_API_KEY to enable)")

        # Stats
        self._arb_count = 0
        self._whale_count = 0
        self._event_count = 0
        self._start_ts: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> list[asyncio.Task]:
        """Start all addon modules. Returns list of background tasks."""
        self._running = True
        self._start_ts = time.time()
        tasks = []

        tasks.append(
            asyncio.create_task(self.arb_scanner.start(), name="arb_scanner")
        )
        tasks.append(
            asyncio.create_task(self.whale_tracker.start(), name="whale_tracker")
        )
        if self.event_trader:
            tasks.append(
                asyncio.create_task(self.event_trader.start(), name="event_trader")
            )

        modules = ["arb_scanner", "whale_tracker"]
        if self.event_trader:
            modules.append("event_trader")
        logger.info("Addon modules started: %s", ", ".join(modules))

        return tasks

    async def stop(self) -> None:
        """Stop all addon modules gracefully."""
        self._running = False
        logger.info("Stopping addon modules...")
        await self.arb_scanner.stop()
        await self.whale_tracker.stop()
        if self.event_trader:
            await self.event_trader.stop()
        logger.info("Addon modules stopped")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    async def _on_arb_found(self, opp: ArbOpportunity) -> None:
        """Handle an arbitrage opportunity."""
        self._arb_count += 1
        logger.info(
            "[ARB] %s: YES=%.3f + NO=%.3f = %.4f  profit=$%.4f",
            opp.question[:50],
            opp.yes_ask,
            opp.no_ask,
            opp.total_cost,
            opp.profit,
        )
        await self._notify(
            f"ARB FOUND\n"
            f"{opp.question[:80]}\n"
            f"YES={opp.yes_ask:.3f} + NO={opp.no_ask:.3f} = {opp.total_cost:.4f}\n"
            f"Profit: ${opp.profit:.4f}"
        )

    async def _on_whale_trade(self, trade: WhaleTrade) -> None:
        """Handle a whale trade detection."""
        self._whale_count += 1
        logger.info(
            "[WHALE] %s %s $%.0f @ %.3f -- %s",
            trade.side,
            trade.outcome,
            trade.size_usdc,
            trade.price,
            trade.market_question[:50],
        )
        await self._notify(
            f"WHALE ALERT\n"
            f"Wallet: {trade.wallet_address[:10]}...\n"
            f"{trade.side} {trade.outcome} ${trade.size_usdc:.0f} @ {trade.price:.3f}\n"
            f"{trade.market_question[:80]}"
        )

    async def _on_event_signal(self, signal: EventSignal) -> None:
        """Handle an AI event trading signal."""
        self._event_count += 1
        logger.info(
            "[EVENT] %s '%s' | edge=%.1f%% | confidence=%.0f%% | size=$%.2f",
            signal.side,
            signal.question[:50],
            signal.edge * 100,
            signal.confidence * 100,
            signal.position_size_usdc,
        )
        await self._notify(
            f"AI EVENT SIGNAL\n"
            f"{signal.side} on: {signal.question[:80]}\n"
            f"Edge: {signal.edge:.1%} | Confidence: {signal.confidence:.0%}\n"
            f"Size: ${signal.position_size_usdc:.2f} @ {signal.entry_price:.3f}\n"
            f"Reasoning: {signal.reasoning[:150]}"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _notify(self, message: str) -> None:
        """Send a notification via telegram if connected."""
        if self._send_telegram:
            try:
                await self._send_telegram(message)
            except Exception as e:
                logger.debug("Telegram send failed: %s", e)

    def summary(self) -> str:
        """Return a summary of addon module stats."""
        uptime = int((time.time() - self._start_ts) // 60) if self._start_ts else 0
        lines = [
            f"  Arb opportunities: {self._arb_count}",
            f"  Whale alerts: {self._whale_count}",
            f"  Event signals: {self._event_count}",
            f"  Wallets tracked: {len(self.wallet_registry.get_wallets())}",
        ]
        if self.event_trader:
            lines.append(
                f"  Active event signals: {len(self.event_trader.get_active_signals())}"
            )
        else:
            lines.append("  Event trader: disabled")
        lines.append(f"  Addon uptime: {uptime}m")
        return "\n".join(lines)


# ----------------------------------------------------------------------
# Standalone runner
# ----------------------------------------------------------------------

async def _run_standalone() -> None:
    """Run addon modules standalone (without the main crypto bot)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    runner = AddonRunner(data_dir="data", paper_trading=True)
    tasks = await runner.start()

    logger.info("Addon modules running standalone. Press Ctrl+C to stop.")

    try:
        # Print summary every 5 minutes
        while True:
            await asyncio.sleep(300)
            logger.info("Addon stats:\n%s", runner.summary())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await runner.stop()


if __name__ == "__main__":
    asyncio.run(_run_standalone())
