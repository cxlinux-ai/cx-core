"""Telegram bot for trading control, alerts, and P&L reports."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from config.settings import TelegramSettings

if TYPE_CHECKING:
    from src.analytics.pnl_tracker import PnlTracker
    from src.execution.clob_client import ClobClient
    from src.execution.order_manager import OrderManager
    from src.strategy.risk_manager import RiskManager
    from config.strategy import StrategyConfig

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for controlling the trading bot and receiving alerts."""

    def __init__(
        self,
        settings: TelegramSettings,
        pnl_tracker: PnlTracker | None = None,
        risk_manager: RiskManager | None = None,
        strategy_config: StrategyConfig | None = None,
        clob_client: ClobClient | None = None,
        order_manager: OrderManager | None = None,
    ) -> None:
        self._settings = settings
        self._pnl = pnl_tracker
        self._risk = risk_manager
        self._strategy = strategy_config
        self._clob = clob_client
        self._orders = order_manager
        self._app: Application | None = None
        self._bot_running = False
        self._trading_active = False

        # Callbacks for start/stop
        self._on_start: callable | None = None
        self._on_stop: callable | None = None

    def set_callbacks(
        self,
        on_start: callable | None = None,
        on_stop: callable | None = None,
    ) -> None:
        self._on_start = on_start
        self._on_stop = on_stop

    async def start(self) -> None:
        """Initialize and start the Telegram bot."""
        if not self._settings.bot_token:
            logger.warning("Telegram bot token not configured — bot disabled")
            return

        self._app = Application.builder().token(self._settings.bot_token).build()

        # Register command handlers
        handlers = [
            ("start", self._cmd_start),
            ("stop", self._cmd_stop),
            ("status", self._cmd_status),
            ("pnl", self._cmd_pnl),
            ("pnl24h", self._cmd_pnl24h),
            ("trades", self._cmd_trades),
            ("kill", self._cmd_kill),
            ("config", self._cmd_config),
            ("set", self._cmd_set),
        ]
        for name, handler in handlers:
            self._app.add_handler(CommandHandler(name, handler))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        self._bot_running = True
        logger.info("Telegram bot started — listening for commands")

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._app and self._bot_running:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._bot_running = False

    async def send_alert(self, message: str) -> None:
        """Send a push notification to the configured chat."""
        if not self._app or not self._settings.chat_id:
            return
        try:
            await self._app.bot.send_message(
                chat_id=self._settings.chat_id,
                text=message,
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.debug("Failed to send Telegram alert: %s", exc)

    async def alert_trade(
        self, side: str, asset: str, price: float, size: float, edge: float
    ) -> None:
        msg = (
            f"*Trade Executed*\n"
            f"Side: {side}\n"
            f"Asset: {asset}\n"
            f"Price: {price:.4f}\n"
            f"Size: ${size:.2f}\n"
            f"Edge: {edge:.3f}"
        )
        await self.send_alert(msg)

    async def alert_resolution(
        self, asset: str, outcome: str, pnl: float
    ) -> None:
        emoji = "+" if pnl >= 0 else ""
        msg = (
            f"*Market Resolved*\n"
            f"Asset: {asset}\n"
            f"Outcome: {outcome}\n"
            f"PnL: {emoji}${pnl:.2f}"
        )
        await self.send_alert(msg)

    async def alert_risk(self, reason: str) -> None:
        msg = f"*Risk Alert*\n{reason}"
        await self.send_alert(msg)

    async def alert_connection(self, source: str, status: str) -> None:
        msg = f"*Connection*\n{source}: {status}"
        await self.send_alert(msg)

    # --- Command handlers ---

    def _is_authorized(self, update: Update) -> bool:
        if not self._settings.chat_id:
            return True
        return str(update.effective_chat.id) == str(self._settings.chat_id)

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        self._trading_active = True
        if self._on_start:
            await self._on_start()
        await update.message.reply_text("Trading bot started.")

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        self._trading_active = False
        if self._on_stop:
            await self._on_stop()
        await update.message.reply_text("Trading bot stopped.")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        lines = [f"Trading: {'ACTIVE' if self._trading_active else 'STOPPED'}"]

        if self._clob:
            balance = await self._clob.get_balance()
            lines.append(f"Balance: ${balance:.2f}")

        if self._risk:
            lines.append(f"Risk:\n{self._risk.summary()}")

        if self._orders:
            active = self._orders.active_orders
            lines.append(f"Open orders: {len(active)}")

        await update.message.reply_text("\n".join(lines))

    async def _cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        if self._pnl:
            await update.message.reply_text(self._pnl.summary())
        else:
            await update.message.reply_text("PnL tracker not available.")

    async def _cmd_pnl24h(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        if self._pnl:
            await update.message.reply_text(self._pnl.summary_24h())
        else:
            await update.message.reply_text("PnL tracker not available.")

    async def _cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        if not self._pnl:
            await update.message.reply_text("PnL tracker not available.")
            return

        recent = self._pnl.get_recent_trades(10)
        if not recent:
            await update.message.reply_text("No trades yet.")
            return

        lines = ["Last 10 trades:"]
        for t in recent:
            lines.append(
                f"  {t.asset} {t.side} ${t.size_usdc:.2f} → "
                f"${t.pnl:+.2f} ({t.outcome})"
            )
        await update.message.reply_text("\n".join(lines))

    async def _cmd_kill(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        self._trading_active = False
        if self._risk:
            self._risk.kill()
        if self._orders:
            count = await self._orders.cancel_all()
            await update.message.reply_text(
                f"KILL SWITCH ACTIVATED\nCancelled {count} orders.\nTrading stopped."
            )
        else:
            await update.message.reply_text("KILL SWITCH ACTIVATED\nTrading stopped.")

    async def _cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        if self._strategy:
            await update.message.reply_text(f"Strategy config:\n{self._strategy.summary()}")
        else:
            await update.message.reply_text("Strategy config not available.")

    async def _cmd_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_authorized(update):
            return
        if not self._strategy:
            await update.message.reply_text("Strategy config not available.")
            return

        args = context.args
        if not args or len(args) < 2:
            await update.message.reply_text("Usage: /set <param> <value>")
            return

        param = args[0]
        value = args[1]
        result = self._strategy.update(param, value)
        await update.message.reply_text(result)
