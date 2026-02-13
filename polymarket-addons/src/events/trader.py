"""
EventTrader: Discovers non-crypto Polymarket event markets, analyzes them with an LLM,
and emits trading signals when the AI-estimated probability diverges from market price.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import aiohttp

from .analyzer import AnalysisResult, MarketAnalyzer

logger = logging.getLogger(__name__)

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"
CLOB_API_URL = "https://clob.polymarket.com"

# Keywords that identify crypto up/down markets (we want to exclude these)
CRYPTO_EXCLUDE_KEYWORDS = [
    "Up or Down",
    "15-minute",
    "15 minute",
    "updown",
    "up-down",
]


@dataclass
class EventSignal:
    condition_id: str
    question: str
    side: str  # "YES" or "NO"
    entry_price: float
    ai_probability: float
    edge: float
    confidence: float
    reasoning: str
    position_size_usdc: float
    timestamp: float = field(default_factory=lambda: time.time())


class EventTrader:
    """
    Discovers non-crypto Polymarket event markets, uses an LLM to estimate
    true probabilities, and generates trading signals when edges are found.
    """

    def __init__(
        self,
        analyzer: MarketAnalyzer,
        min_edge: float = 0.05,
        min_confidence: float = 0.7,
        max_position_usdc: float = 25.0,
        on_signal: Optional[Callable[[EventSignal], Awaitable[None]]] = None,
    ):
        self.analyzer = analyzer
        self.min_edge = min_edge
        self.min_confidence = min_confidence
        self.max_position_usdc = max_position_usdc
        self.on_signal = on_signal

        self._active_signals: list[EventSignal] = []
        self._evaluated_ids: dict[str, float] = {}  # condition_id -> timestamp
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._discovery_interval = 5 * 60  # 5 minutes

    async def start(self) -> None:
        """Start the market discovery loop."""
        if self._running:
            logger.warning("EventTrader is already running")
            return

        self._running = True
        self._session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "EventTrader started (min_edge=%.1f%%, min_confidence=%.0f%%, max_position=$%.0f)",
            self.min_edge * 100,
            self.min_confidence * 100,
            self.max_position_usdc,
        )

    async def stop(self) -> None:
        """Stop the discovery loop and clean up."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._task = None
        logger.info("EventTrader stopped")

    def get_active_signals(self) -> list[EventSignal]:
        """Return current actionable signals."""
        return list(self._active_signals)

    async def _run_loop(self) -> None:
        """Main discovery loop that runs every 5 minutes."""
        while self._running:
            try:
                await self._discovery_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Discovery cycle error: %s", e, exc_info=True)

            # Sleep in short intervals so we can stop promptly
            for _ in range(self._discovery_interval):
                if not self._running:
                    break
                await asyncio.sleep(1)

    async def _discovery_cycle(self) -> None:
        """Run a single discovery cycle: fetch markets, evaluate, emit signals."""
        logger.info("Starting market discovery cycle")

        markets = await self._discover_markets()
        if not markets:
            logger.info("No qualifying markets found")
            return

        logger.info("Discovered %d candidate event markets", len(markets))

        # Purge stale evaluated IDs (older than cache TTL)
        cache_ttl = self.analyzer._cache_ttl
        now = time.time()
        self._evaluated_ids = {
            cid: ts
            for cid, ts in self._evaluated_ids.items()
            if now - ts < cache_ttl
        }

        evaluated_count = 0
        signal_count = 0

        for market in markets:
            if not self._running:
                break

            condition_id = market.get("condition_id", "")
            if not condition_id:
                continue

            # Skip if recently evaluated (within cache window)
            if condition_id in self._evaluated_ids:
                continue

            try:
                signal = await self._evaluate_market(market)
                self._evaluated_ids[condition_id] = time.time()
                evaluated_count += 1

                if signal:
                    signal_count += 1
            except Exception as e:
                logger.error(
                    "Error evaluating market '%s': %s",
                    market.get("question", "?")[:50],
                    e,
                )

        logger.info(
            "Discovery cycle complete: evaluated=%d, signals=%d",
            evaluated_count,
            signal_count,
        )

    async def _discover_markets(self) -> list[dict[str, Any]]:
        """
        Fetch active non-crypto event markets from the Gamma API.

        Filters:
        - active=True, closed=False
        - Not containing crypto up/down keywords
        - volume > $10,000
        - liquidity > $5,000
        - Sorted by volume descending, limited to top 50
        """
        if not self._session:
            logger.error("No HTTP session available")
            return []

        try:
            params = {
                "active": "true",
                "closed": "false",
                "limit": "200",
                "order": "volume",
                "ascending": "false",
            }

            async with self._session.get(GAMMA_API_URL, params=params) as resp:
                if resp.status != 200:
                    logger.error("Gamma API returned status %d", resp.status)
                    return []
                markets = await resp.json()

        except Exception as e:
            logger.error("Failed to fetch markets from Gamma API: %s", e)
            return []

        filtered = []
        for m in markets:
            question = m.get("question", "")

            # Exclude crypto up/down markets
            if any(kw.lower() in question.lower() for kw in CRYPTO_EXCLUDE_KEYWORDS):
                continue

            # Volume and liquidity filters
            try:
                volume = float(m.get("volume", 0))
                liquidity = float(m.get("liquidity", 0))
            except (ValueError, TypeError):
                continue

            if volume <= 10000 or liquidity <= 5000:
                continue

            filtered.append(m)

        # Sort by volume descending and take top 50
        filtered.sort(key=lambda x: float(x.get("volume", 0)), reverse=True)
        return filtered[:50]

    async def _evaluate_market(self, market: dict[str, Any]) -> Optional[EventSignal]:
        """
        Evaluate a single market: get prices, run LLM analysis, emit signal if edge found.
        """
        condition_id = market.get("condition_id", "")
        question = market.get("question", "")
        description = market.get("description", "")
        outcomes = market.get("outcomes", [])
        tags = market.get("tags", [])
        clob_token_ids = market.get("clobTokenIds", [])

        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                outcomes = ["Yes", "No"]

        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = []

        if isinstance(clob_token_ids, str):
            try:
                clob_token_ids = json.loads(clob_token_ids)
            except json.JSONDecodeError:
                clob_token_ids = []

        # Get current YES price from CLOB orderbook
        yes_price = await self._get_yes_price(clob_token_ids)
        if yes_price is None:
            logger.debug("Could not get price for '%s'", question[:50])
            return None

        # Run LLM analysis
        analysis = await self.analyzer.analyze_market(
            question=question,
            description=description,
            current_yes_price=yes_price,
            outcomes=outcomes,
            tags=tags,
            condition_id=condition_id,
        )

        if analysis is None:
            return None

        # Check if edge is actionable
        side = analysis.recommended_side
        if side == "NONE":
            return None

        if side == "YES":
            edge = analysis.edge_yes
            ai_prob = analysis.probability_yes
            entry_price = yes_price
        else:
            edge = analysis.edge_no
            ai_prob = analysis.probability_no
            entry_price = 1.0 - yes_price

        if abs(edge) < self.min_edge:
            return None

        if analysis.confidence < self.min_confidence:
            return None

        # Calculate position size: scale by edge and confidence, cap at max
        raw_size = self.max_position_usdc * min(abs(edge) / 0.15, 1.0) * analysis.confidence
        position_size = min(raw_size, self.max_position_usdc)
        position_size = round(position_size, 2)

        signal = EventSignal(
            condition_id=condition_id,
            question=question,
            side=side,
            entry_price=entry_price,
            ai_probability=ai_prob,
            edge=edge,
            confidence=analysis.confidence,
            reasoning=analysis.reasoning,
            position_size_usdc=position_size,
        )

        self._active_signals.append(signal)

        logger.info(
            "EVENT SIGNAL: %s '%s' | edge=%.1f%% | AI_prob=%.1f%% vs market=%.1f%%",
            side,
            question[:50],
            edge * 100,
            ai_prob * 100,
            entry_price * 100,
        )

        # Fire callback if registered
        if self.on_signal:
            try:
                await self.on_signal(signal)
            except Exception as e:
                logger.error("on_signal callback error: %s", e)

        return signal

    async def _get_yes_price(
        self, clob_token_ids: list[str]
    ) -> Optional[float]:
        """
        Get the current YES token mid-price from the CLOB API orderbook.

        The first token ID in clobTokenIds corresponds to the first outcome (YES).
        """
        if not clob_token_ids or not self._session:
            return None

        yes_token_id = clob_token_ids[0]

        try:
            url = f"{CLOB_API_URL}/book"
            params = {"token_id": yes_token_id}

            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                book = await resp.json()

            bids = book.get("bids", [])
            asks = book.get("asks", [])

            if bids and asks:
                best_bid = float(bids[0].get("price", 0))
                best_ask = float(asks[0].get("price", 0))
                if best_bid > 0 and best_ask > 0:
                    return (best_bid + best_ask) / 2.0

            # Fallback: use best bid or best ask alone
            if bids:
                return float(bids[0].get("price", 0))
            if asks:
                return float(asks[0].get("price", 0))

        except Exception as e:
            logger.debug("Failed to get orderbook for token %s: %s", yes_token_id, e)

        return None
