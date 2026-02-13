"""Polymarket CLOB arbitrage scanner.

Continuously scans all active Polymarket markets for mispriced YES/NO
token pairs. An arbitrage exists when the sum of the best ask for YES
and the best ask for NO is less than $0.98 (i.e. $1.00 minus the 2%
winner fee), guaranteeing a risk-free profit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

# An arb exists when total cost to buy both sides is below this threshold.
ARB_THRESHOLD = 0.98

# Pagination size for the Gamma markets endpoint.
MARKETS_PAGE_SIZE = 100

# How long (seconds) to cache the full market list before re-fetching.
MARKET_CACHE_TTL = 60.0

# Rate-limit: max requests per second to external APIs.
MAX_REQUESTS_PER_SECOND = 20

# Interval between full scan cycles.
SCAN_INTERVAL_SECONDS = 10


@dataclass
class ArbOpportunity:
    """A detected arbitrage opportunity."""

    condition_id: str
    question: str
    yes_token_id: str
    no_token_id: str
    yes_ask: float
    no_ask: float
    total_cost: float
    profit: float
    timestamp: float = field(default_factory=time.time)


class ArbScanner:
    """Scans Polymarket CLOB for arbitrage opportunities.

    Parameters
    ----------
    store:
        Optional DataStore instance for persistence. May be ``None``.
    on_arb_callback:
        Optional async callable invoked whenever an arb is found.
        Signature: ``async callback(opportunity: ArbOpportunity) -> None``.
    """

    def __init__(
        self,
        store: Any = None,
        on_arb_callback: Optional[
            Callable[[ArbOpportunity], Coroutine[Any, Any, None]]
        ] = None,
    ) -> None:
        self.store = store
        self._on_arb_callback = on_arb_callback

        # Accumulated arb opportunities across all scans.
        self.arbs_found: List[ArbOpportunity] = []

        # Internal state
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

        # Rate-limiter state: token-bucket
        self._rate_tokens: float = MAX_REQUESTS_PER_SECOND
        self._rate_max: float = MAX_REQUESTS_PER_SECOND
        self._rate_last_refill: float = time.monotonic()
        self._rate_lock: asyncio.Lock = asyncio.Lock()

        # Market list cache
        self._cached_markets: List[Dict[str, Any]] = []
        self._cache_timestamp: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the continuous scan loop in a background task."""
        if self._running:
            logger.warning("Scanner is already running")
            return

        self._running = True
        self._session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._loop())
        logger.info("ArbScanner started")

    async def stop(self) -> None:
        """Gracefully stop the scanner and release resources."""
        self._running = False

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

        logger.info(
            "ArbScanner stopped. Total arbs found this session: %d",
            len(self.arbs_found),
        )

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Run scans on a fixed interval until stopped."""
        while self._running:
            try:
                await self._run_scan()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scan cycle failed unexpectedly")

            await asyncio.sleep(SCAN_INTERVAL_SECONDS)

    async def _run_scan(self) -> None:
        """Execute a single full scan across all active markets."""
        markets = await self._get_markets()
        logger.info("Scanning %d active markets for arbs", len(markets))

        for market in markets:
            if not self._running:
                break
            await self._process_market(market)

    # ------------------------------------------------------------------
    # Market fetching (with cache)
    # ------------------------------------------------------------------

    async def _get_markets(self) -> List[Dict[str, Any]]:
        """Return the active market list, using a cache with TTL."""
        now = time.monotonic()
        if self._cached_markets and (now - self._cache_timestamp) < MARKET_CACHE_TTL:
            return self._cached_markets

        markets = await self._scan_all_markets()
        self._cached_markets = markets
        self._cache_timestamp = time.monotonic()
        return markets

    async def _scan_all_markets(self) -> List[Dict[str, Any]]:
        """Fetch ALL active, non-closed markets from the Gamma API.

        Paginates through results ``MARKETS_PAGE_SIZE`` at a time until
        the API returns fewer results than the page size.
        """
        all_markets: List[Dict[str, Any]] = []
        offset = 0

        while True:
            params = {
                "limit": str(MARKETS_PAGE_SIZE),
                "offset": str(offset),
                "active": "true",
                "closed": "false",
            }

            data = await self._rate_limited_get(
                f"{GAMMA_API_BASE}/markets", params=params
            )

            if data is None:
                break

            if not isinstance(data, list):
                logger.warning("Unexpected Gamma API response type: %s", type(data))
                break

            all_markets.extend(data)

            if len(data) < MARKETS_PAGE_SIZE:
                break

            offset += MARKETS_PAGE_SIZE

        logger.debug("Fetched %d total active markets from Gamma API", len(all_markets))
        return all_markets

    # ------------------------------------------------------------------
    # Per-market processing
    # ------------------------------------------------------------------

    async def _process_market(self, market: Dict[str, Any]) -> None:
        """Extract token IDs from a market and check for an arb."""
        condition_id: str = market.get("condition_id", "")
        question: str = market.get("question", "Unknown")

        yes_token_id, no_token_id = self._extract_token_ids(market)
        if yes_token_id is None or no_token_id is None:
            return

        opportunity = await self._check_arb(
            condition_id=condition_id,
            question=question,
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
        )

        if opportunity is not None:
            self.arbs_found.append(opportunity)
            logger.info(
                "ARB FOUND | %s | yes_ask=%.4f no_ask=%.4f | "
                "total_cost=%.4f | est_profit=%.4f",
                opportunity.question,
                opportunity.yes_ask,
                opportunity.no_ask,
                opportunity.total_cost,
                opportunity.profit,
            )
            await self._notify_callback(opportunity)

    @staticmethod
    def _extract_token_ids(
        market: Dict[str, Any],
    ) -> tuple[Optional[str], Optional[str]]:
        """Parse clobTokenIds and outcomes from a Gamma market dict.

        The Gamma API returns ``clobTokenIds`` and ``outcomes`` either as
        JSON-encoded strings or as native lists depending on context.
        This helper normalises both forms and maps outcomes to token IDs.

        Returns
        -------
        (yes_token_id, no_token_id) or (None, None) on failure.
        """
        raw_token_ids = market.get("clobTokenIds")
        raw_outcomes = market.get("outcomes")

        if raw_token_ids is None or raw_outcomes is None:
            return None, None

        # Normalise JSON strings to Python lists.
        if isinstance(raw_token_ids, str):
            try:
                raw_token_ids = json.loads(raw_token_ids)
            except (json.JSONDecodeError, TypeError):
                return None, None

        if isinstance(raw_outcomes, str):
            try:
                raw_outcomes = json.loads(raw_outcomes)
            except (json.JSONDecodeError, TypeError):
                return None, None

        if len(raw_token_ids) != 2 or len(raw_outcomes) != 2:
            return None, None

        # Build outcome -> token_id mapping.
        outcome_map: Dict[str, str] = {}
        for outcome, token_id in zip(raw_outcomes, raw_token_ids):
            outcome_map[outcome] = token_id

        yes_token_id = outcome_map.get("Yes")
        no_token_id = outcome_map.get("No")

        # Some markets use "Up"/"Down" instead of "Yes"/"No". In that
        # case treat "Up" as YES and "Down" as NO for arb purposes.
        if yes_token_id is None:
            yes_token_id = outcome_map.get("Up")
        if no_token_id is None:
            no_token_id = outcome_map.get("Down")

        if yes_token_id is None or no_token_id is None:
            return None, None

        return yes_token_id, no_token_id

    # ------------------------------------------------------------------
    # Arb detection
    # ------------------------------------------------------------------

    async def _check_arb(
        self,
        condition_id: str,
        question: str,
        yes_token_id: str,
        no_token_id: str,
    ) -> Optional[ArbOpportunity]:
        """Fetch orderbooks for both tokens and evaluate arb conditions.

        Returns an ``ArbOpportunity`` when the total ask cost is below
        ``ARB_THRESHOLD``, otherwise ``None``.
        """
        yes_ask = await self._get_best_ask(yes_token_id)
        no_ask = await self._get_best_ask(no_token_id)

        if yes_ask is None or no_ask is None:
            return None

        total_cost = yes_ask + no_ask

        if total_cost < ARB_THRESHOLD:
            profit = 1.0 - total_cost  # gross profit before fee
            return ArbOpportunity(
                condition_id=condition_id,
                question=question,
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
                yes_ask=yes_ask,
                no_ask=no_ask,
                total_cost=total_cost,
                profit=profit,
                timestamp=time.time(),
            )

        return None

    async def _get_best_ask(self, token_id: str) -> Optional[float]:
        """Return the lowest ask price from the CLOB orderbook for a token.

        Returns ``None`` if the orderbook is empty or the request fails.
        """
        data = await self._rate_limited_get(
            f"{CLOB_API_BASE}/book", params={"token_id": token_id}
        )

        if data is None:
            return None

        asks = data.get("asks", [])
        if not asks:
            return None

        try:
            best_ask = min(float(ask["price"]) for ask in asks)
        except (KeyError, ValueError, TypeError):
            logger.warning("Malformed ask data for token %s", token_id)
            return None

        return best_ask

    # ------------------------------------------------------------------
    # Callback
    # ------------------------------------------------------------------

    async def _notify_callback(self, opportunity: ArbOpportunity) -> None:
        """Invoke the external arb callback if one was provided."""
        if self._on_arb_callback is None:
            return
        try:
            await self._on_arb_callback(opportunity)
        except Exception:
            logger.exception(
                "on_arb_callback raised for market %s", opportunity.condition_id
            )

    # ------------------------------------------------------------------
    # HTTP helpers with rate limiting
    # ------------------------------------------------------------------

    async def _rate_limited_get(
        self, url: str, params: Optional[Dict[str, str]] = None
    ) -> Optional[Any]:
        """Perform a GET request, respecting the rate limit.

        Returns the parsed JSON body, or ``None`` on any failure.
        """
        await self._acquire_rate_token()

        assert self._session is not None  # noqa: S101
        try:
            async with self._session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(
                        "HTTP %d from %s (params=%s)", resp.status, url, params
                    )
                    return None
                return await resp.json()
        except asyncio.TimeoutError:
            logger.warning("Request timed out: %s", url)
            return None
        except aiohttp.ClientError as exc:
            logger.warning("HTTP error for %s: %s", url, exc)
            return None

    async def _acquire_rate_token(self) -> None:
        """Block until a rate-limit token is available (token bucket)."""
        while True:
            async with self._rate_lock:
                now = time.monotonic()
                elapsed = now - self._rate_last_refill
                self._rate_tokens = min(
                    self._rate_max,
                    self._rate_tokens + elapsed * self._rate_max,
                )
                self._rate_last_refill = now

                if self._rate_tokens >= 1.0:
                    self._rate_tokens -= 1.0
                    return

            # Not enough tokens; wait briefly and retry.
            await asyncio.sleep(1.0 / self._rate_max)
