"""Whale trade tracker — polls Polymarket activity for tracked wallets."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

import aiohttp

from src.whale.wallets import WalletRegistry

logger = logging.getLogger(__name__)

ACTIVITY_URL = "https://data-api.polymarket.com/activity"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"

# Only BUY trades above this USD threshold trigger a whale alert.
ALERT_MIN_SIZE_USD = 1_000.0

# Signals older than this many seconds are pruned from get_active_signals().
SIGNAL_WINDOW_SECS = 15 * 60  # 15 minutes

# How often the leaderboard auto-refreshes (seconds).
LEADERBOARD_REFRESH_INTERVAL = 6 * 60 * 60  # 6 hours


@dataclass
class WhaleTrade:
    """A single whale trade detected from on-chain / API activity."""

    wallet_address: str
    condition_id: str
    token_id: str
    outcome: str
    side: str
    size_usdc: float
    price: float
    timestamp: float
    market_question: str = ""


@dataclass
class _WalletPerf:
    """Internal bookkeeping for per-wallet performance stats."""

    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0

    @property
    def win_rate(self) -> float:
        total = self.wins + self.losses
        return self.wins / total if total else 0.0


class WhaleTracker:
    """Polls Polymarket activity for a set of whale wallets and emits alerts."""

    def __init__(
        self,
        wallet_registry: WalletRegistry,
        on_whale_trade: Optional[Callable[[WhaleTrade], Awaitable[None]]] = None,
        poll_interval: float = 30.0,
    ) -> None:
        self._registry = wallet_registry
        self._on_whale_trade = on_whale_trade
        self._poll_interval = poll_interval

        # Last-seen timestamp per wallet to avoid duplicate alerts.
        self._last_seen_ts: dict[str, float] = {}

        # Recent whale trades kept around for get_active_signals().
        self._recent_trades: list[WhaleTrade] = []

        # Per-wallet performance tracking.
        self._perf: dict[str, _WalletPerf] = {}

        # Rotation state — we poll at most 5 wallets per cycle.
        self._rotation_offset: int = 0
        self._max_per_cycle: int = 5

        # Cache of condition_id -> market question to reduce lookups.
        self._question_cache: dict[str, str] = {}

        # Managed tasks.
        self._poll_task: Optional[asyncio.Task] = None
        self._leaderboard_task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._running: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the polling loop and periodic leaderboard refresh."""
        if self._running:
            logger.warning("WhaleTracker is already running")
            return

        self._running = True
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20)
        )
        self._poll_task = asyncio.create_task(self._poll_loop(), name="whale-poll")
        self._leaderboard_task = asyncio.create_task(
            self._leaderboard_loop(), name="whale-leaderboard"
        )
        logger.info(
            "WhaleTracker started (poll every %ds, tracking %d wallets)",
            self._poll_interval,
            len(self._registry.get_wallets()),
        )

    async def stop(self) -> None:
        """Gracefully shut down tasks and HTTP session."""
        self._running = False

        for task in (self._poll_task, self._leaderboard_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self._session and not self._session.closed:
            await self._session.close()

        self._poll_task = None
        self._leaderboard_task = None
        self._session = None
        logger.info("WhaleTracker stopped")

    # ------------------------------------------------------------------
    # Loops
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Main polling loop — runs until stop() is called."""
        while self._running:
            try:
                await self._poll_whale_activity()
            except Exception as exc:
                logger.error("Poll cycle failed: %s", exc, exc_info=True)
            await asyncio.sleep(self._poll_interval)

    async def _leaderboard_loop(self) -> None:
        """Periodically refresh wallets from the leaderboard."""
        while self._running:
            try:
                await self._registry.refresh_from_leaderboard()
            except Exception as exc:
                logger.error("Leaderboard refresh failed: %s", exc, exc_info=True)
            await asyncio.sleep(LEADERBOARD_REFRESH_INTERVAL)

    # ------------------------------------------------------------------
    # Core polling
    # ------------------------------------------------------------------

    async def _poll_whale_activity(self) -> None:
        """Fetch activity for the next batch of wallets in the rotation."""
        all_wallets = self._registry.get_wallets()
        if not all_wallets:
            return

        # Pick the next slice of wallets to poll this cycle.
        start = self._rotation_offset % len(all_wallets)
        batch = all_wallets[start : start + self._max_per_cycle]
        # If we wrapped around the list, also grab from the beginning.
        if len(batch) < self._max_per_cycle and start != 0:
            remaining = self._max_per_cycle - len(batch)
            batch += all_wallets[:remaining]
        self._rotation_offset = (start + self._max_per_cycle) % max(len(all_wallets), 1)

        for wallet in batch:
            try:
                await self._fetch_wallet_activity(wallet)
            except Exception as exc:
                logger.warning(
                    "Failed to fetch activity for %s: %s", wallet[:8], exc
                )

    async def _fetch_wallet_activity(self, wallet: str) -> None:
        """Fetch recent activity for a single wallet and process new trades."""
        assert self._session is not None

        params = {"address": wallet, "limit": "50", "offset": "0"}
        async with self._session.get(ACTIVITY_URL, params=params) as resp:
            resp.raise_for_status()
            activities = await resp.json()

        last_ts = self._last_seen_ts.get(wallet, 0.0)
        new_last_ts = last_ts

        for item in activities:
            if item.get("type") != "trade":
                continue

            ts = _parse_timestamp(item.get("timestamp", 0))
            if ts <= last_ts:
                continue

            new_last_ts = max(new_last_ts, ts)

            side = (item.get("side") or "").upper()
            size = float(item.get("size", 0))
            price = float(item.get("price", 0))
            size_usdc = size * price
            outcome = item.get("outcome", "")
            condition_id = item.get("condition_id", "")
            token_id = item.get("asset_id", "")

            # Resolve market question (best-effort).
            question = await self._resolve_question(condition_id)

            trade = WhaleTrade(
                wallet_address=wallet,
                condition_id=condition_id,
                token_id=token_id,
                outcome=outcome,
                side=side,
                size_usdc=size_usdc,
                price=price,
                timestamp=ts,
                market_question=question,
            )

            # Update performance tracking.
            self._update_perf(wallet, trade)

            # Only alert on BUY trades above the threshold.
            if side == "BUY" and size_usdc >= ALERT_MIN_SIZE_USD:
                logger.info(
                    "WHALE ALERT: %s bought %s on '%s' — $%.2f @ %.4f",
                    wallet[:8],
                    outcome,
                    question,
                    size_usdc,
                    price,
                )
                self._recent_trades.append(trade)

                if self._on_whale_trade is not None:
                    try:
                        await self._on_whale_trade(trade)
                    except Exception as cb_exc:
                        logger.error("on_whale_trade callback error: %s", cb_exc)

        self._last_seen_ts[wallet] = new_last_ts
        self._prune_signals()

    # ------------------------------------------------------------------
    # Market question resolution
    # ------------------------------------------------------------------

    async def _resolve_question(self, condition_id: str) -> str:
        """Look up the human-readable market question for a condition_id."""
        if not condition_id:
            return ""

        if condition_id in self._question_cache:
            return self._question_cache[condition_id]

        assert self._session is not None
        try:
            url = f"{GAMMA_API_BASE}/markets"
            params = {"condition_id": condition_id}
            async with self._session.get(url, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()

            # The Gamma API returns a list; take the first match.
            if isinstance(data, list) and data:
                question = data[0].get("question", "")
            elif isinstance(data, dict):
                question = data.get("question", "")
            else:
                question = ""

            self._question_cache[condition_id] = question
            return question
        except Exception as exc:
            logger.debug("Could not resolve question for %s: %s", condition_id, exc)
            return ""

    # ------------------------------------------------------------------
    # Performance tracking
    # ------------------------------------------------------------------

    def _update_perf(self, wallet: str, trade: WhaleTrade) -> None:
        """Heuristically track win/loss for a wallet.

        A BUY at price >= 0.5 that later settles to YES, or a BUY at
        price < 0.5 that settles to NO, counts as a win.  Since we don't
        know settlement at poll time, we use a rough heuristic: buying at
        price > 0.65 is counted as a tentative win (strong conviction
        trade), selling as realising PnL.
        """
        perf = self._perf.setdefault(wallet, _WalletPerf())

        if trade.side == "SELL":
            # Treat sells as PnL realisation.
            estimated_pnl = trade.size_usdc * (trade.price - 0.5)
            perf.total_pnl += estimated_pnl
            if estimated_pnl > 0:
                perf.wins += 1
            else:
                perf.losses += 1

    def get_wallet_stats(self, wallet: str) -> dict:
        """Return performance stats for a tracked wallet."""
        perf = self._perf.get(wallet.lower().strip(), _WalletPerf())
        return {
            "win_rate": round(perf.win_rate, 4),
            "total_pnl": round(perf.total_pnl, 2),
            "wins": perf.wins,
            "losses": perf.losses,
        }

    # ------------------------------------------------------------------
    # Active signals
    # ------------------------------------------------------------------

    def get_active_signals(self) -> list[WhaleTrade]:
        """Return whale BUY trades from the last 15 minutes."""
        self._prune_signals()
        return list(self._recent_trades)

    def _prune_signals(self) -> None:
        """Remove signals older than the active window."""
        cutoff = time.time() - SIGNAL_WINDOW_SECS
        self._recent_trades = [t for t in self._recent_trades if t.timestamp >= cutoff]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_timestamp(value) -> float:
    """Convert an API timestamp to a float epoch.

    The activity API may return either an ISO-8601 string or a numeric
    epoch (seconds or milliseconds).
    """
    if isinstance(value, (int, float)):
        # If the value looks like milliseconds, convert.
        if value > 1e12:
            return float(value) / 1000.0
        return float(value)

    if isinstance(value, str):
        # Try ISO-8601 parsing.
        import datetime

        try:
            dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.timestamp()
        except ValueError:
            pass

    return 0.0
