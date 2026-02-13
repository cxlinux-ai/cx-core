"""Polymarket CLOB feed — REST API polling for orderbook prices + Gamma API discovery."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

import aiohttp

from config.markets import Asset, MarketConfig, MarketInfo
from src.data.data_store import DataStore, OrderbookSnapshot, Trade

logger = logging.getLogger(__name__)

CLOB_API = "https://clob.polymarket.com"


@dataclass
class MarketState:
    """Tracks the lifecycle of a single 15-min market."""

    market: MarketInfo
    yes_price: float = 0.5
    no_price: float = 0.5
    yes_bids: list[tuple[float, float]] = field(default_factory=list)
    yes_asks: list[tuple[float, float]] = field(default_factory=list)
    no_bids: list[tuple[float, float]] = field(default_factory=list)
    no_asks: list[tuple[float, float]] = field(default_factory=list)
    last_update: float = 0.0


class PolymarketFeed:
    """Discovers 15-min markets via Gamma API, polls CLOB REST for prices."""

    PRICE_POLL_INTERVAL = 5.0  # Seconds between orderbook polls

    def __init__(
        self,
        store: DataStore,
        market_config: MarketConfig | None = None,
    ) -> None:
        self._store = store
        self._config = market_config or MarketConfig()
        self._running = False
        self._active_markets: dict[str, MarketState] = {}
        self._session: aiohttp.ClientSession | None = None

    @property
    def active_markets(self) -> dict[str, MarketState]:
        return dict(self._active_markets)

    async def start(self) -> None:
        """Run market discovery and price polling concurrently."""
        self._running = True
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        try:
            await asyncio.gather(
                self._discovery_loop(),
                self._price_poll_loop(),
            )
        finally:
            if self._session:
                await self._session.close()

    async def stop(self) -> None:
        self._running = False
        if self._session:
            await self._session.close()
            self._session = None

    # CX Terminal: Slug-based 15-min market discovery
    # 15-min crypto markets use slugs like "btc-updown-15m-{timestamp}"
    # where timestamp = floor(unix_time / 900) * 900

    ASSET_SLUG_MAP: dict[Asset, str] = {
        Asset.BTC: "btc",
        Asset.ETH: "eth",
        Asset.SOL: "sol",
        Asset.XRP: "xrp",
    }

    async def _discovery_loop(self) -> None:
        """Periodically discover new 15-min prediction markets via slug lookup."""
        while self._running:
            try:
                await self._discover_markets()
            except Exception as exc:
                logger.error("Market discovery error: %s", exc)
            await asyncio.sleep(self._config.refresh_interval_seconds)

    async def _discover_markets(self) -> None:
        """Look up current 15-min crypto markets by constructing their slugs."""
        now = time.time()
        current_slot = int(now // 900) * 900
        # Check current and next slot
        slots = [current_slot, current_slot + 900]
        logger.info("Discovery: checking slots %s (now=%.0f, active=%d)",
                     slots, now, len(self._active_markets))

        for slot_ts in slots:
            for asset, coin in self.ASSET_SLUG_MAP.items():
                slug = f"{coin}-updown-15m-{slot_ts}"
                # Skip if we already track this slug
                if any(
                    s.market.question.endswith(str(slot_ts))
                    for s in self._active_markets.values()
                    if s.market.asset == asset
                ):
                    continue

                await self._fetch_market_by_slug(slug, asset, slot_ts)

        # Prune resolved/expired markets
        expired = [
            cid for cid, state in self._active_markets.items()
            if state.market.close_timestamp < now - 300
        ]
        for cid in expired:
            del self._active_markets[cid]

    async def _fetch_market_by_slug(self, slug: str, asset: Asset, slot_ts: int) -> None:
        """Fetch a single market from the Gamma API by slug."""
        url = f"{self._config.gamma_api_url}/markets"
        params = {"slug": slug, "closed": "false"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return
                    markets_raw = await resp.json()
        except Exception as exc:
            logger.debug("Gamma API slug lookup failed for %s: %s", slug, exc)
            return

        if not markets_raw:
            logger.debug("No market found for slug: %s", slug)
            return

        m = markets_raw[0] if isinstance(markets_raw, list) else markets_raw
        condition_id = m.get("conditionId", m.get("condition_id", ""))
        if not condition_id or condition_id in self._active_markets:
            return

        tokens = m.get("tokens", [])
        outcomes = m.get("outcomes", [])
        clob_token_ids = m.get("clobTokenIds", [])

        # Gamma API sometimes returns these as JSON strings instead of arrays
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except (json.JSONDecodeError, TypeError):
                outcomes = []
        if isinstance(clob_token_ids, str):
            try:
                clob_token_ids = json.loads(clob_token_ids)
            except (json.JSONDecodeError, TypeError):
                clob_token_ids = []

        # Gamma API returns tokens as either a nested array or separate fields
        if tokens and len(tokens) >= 2:
            yes_token_id = next((t["token_id"] for t in tokens if t.get("outcome") in ("Yes", "Up")), None)
            no_token_id = next((t["token_id"] for t in tokens if t.get("outcome") in ("No", "Down")), None)
        elif len(outcomes) >= 2 and len(clob_token_ids) >= 2:
            # Gamma API format: outcomes=["Up","Down"], clobTokenIds=["id1","id2"]
            up_idx = next((i for i, o in enumerate(outcomes) if o in ("Yes", "Up")), None)
            down_idx = next((i for i, o in enumerate(outcomes) if o in ("No", "Down")), None)
            yes_token_id = clob_token_ids[up_idx] if up_idx is not None else None
            no_token_id = clob_token_ids[down_idx] if down_idx is not None else None
        else:
            logger.warning("Slug %s: no parseable tokens (tokens=%d outcomes=%d clobIds=%d)",
                           slug, len(tokens), len(outcomes), len(clob_token_ids))
            return

        if not yes_token_id or not no_token_id:
            logger.warning("Slug %s: missing token IDs (yes=%s no=%s)", slug, yes_token_id, no_token_id)
            return

        close_timestamp = float(slot_ts + 900)
        question = m.get("question", slug)

        market_info = MarketInfo(
            condition_id=condition_id,
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            asset=asset,
            question=question,
            close_timestamp=close_timestamp,
        )

        self._active_markets[condition_id] = MarketState(market=market_info)
        logger.info("Discovered 15m market: %s [%s] closes at %.0f",
                     question[:60], asset.value, close_timestamp)

    # --- REST API price polling ---

    async def _price_poll_loop(self) -> None:
        """Poll CLOB REST API for orderbook prices on active markets."""
        # Wait for discovery to populate some markets
        await asyncio.sleep(3)
        logger.info("Polymarket price polling started (every %.0fs)", self.PRICE_POLL_INTERVAL)

        while self._running:
            try:
                await self._poll_all_books()
            except Exception as exc:
                logger.error("Price poll error: %s", exc)
            await asyncio.sleep(self.PRICE_POLL_INTERVAL)

    async def _poll_all_books(self) -> None:
        """Fetch orderbooks for all active market tokens via CLOB REST API."""
        if not self._active_markets or not self._session:
            return

        # Collect all token IDs to fetch
        token_requests = []
        for cid, state in self._active_markets.items():
            token_requests.append({"token_id": state.market.yes_token_id})
            token_requests.append({"token_id": state.market.no_token_id})

        # Use batch endpoint POST /books (up to 15 per request)
        try:
            async with self._session.post(
                f"{CLOB_API}/books",
                json=token_requests,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status != 200:
                    # Fall back to individual requests
                    logger.debug("Batch /books returned %d, falling back to individual", resp.status)
                    await self._poll_individual_books()
                    return
                books = await resp.json()
        except Exception as exc:
            logger.debug("Batch /books failed: %s — falling back to individual", exc)
            await self._poll_individual_books()
            return

        # Process batch response
        if isinstance(books, list):
            for book in books:
                await self._process_book(book)
        elif isinstance(books, dict):
            # Might be a single book or keyed by token_id
            if "asset_id" in books:
                await self._process_book(books)
            else:
                for token_id, book in books.items():
                    if isinstance(book, dict):
                        await self._process_book(book)

    async def _poll_individual_books(self) -> None:
        """Fallback: fetch each token's orderbook individually."""
        if not self._session:
            return

        for cid, state in self._active_markets.items():
            for token_id in [state.market.yes_token_id, state.market.no_token_id]:
                try:
                    async with self._session.get(
                        f"{CLOB_API}/book",
                        params={"token_id": token_id},
                    ) as resp:
                        if resp.status == 200:
                            book = await resp.json()
                            await self._process_book(book)
                except Exception as exc:
                    logger.debug("Individual /book failed for %s: %s", token_id[:16], exc)

    async def _process_book(self, book: dict) -> None:
        """Process a single orderbook response and update market state."""
        asset_id = book.get("asset_id", book.get("market", ""))
        if not asset_id:
            return

        # Find which market and side
        state: MarketState | None = None
        side = ""
        for cid, s in self._active_markets.items():
            if asset_id == s.market.yes_token_id:
                state, side = s, "yes"
                break
            elif asset_id == s.market.no_token_id:
                state, side = s, "no"
                break

        if state is None:
            return

        now = time.time()
        bids = self._parse_book_levels(book.get("bids", []))
        asks = self._parse_book_levels(book.get("asks", []))

        # Sort bids descending, asks ascending
        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        if side == "yes":
            state.yes_bids = bids or state.yes_bids
            state.yes_asks = asks or state.yes_asks
            if bids and asks:
                state.yes_price = (bids[0][0] + asks[0][0]) / 2
        else:
            state.no_bids = bids or state.no_bids
            state.no_asks = asks or state.no_asks
            if bids and asks:
                state.no_price = (bids[0][0] + asks[0][0]) / 2

        state.last_update = now

        if bids and asks:
            logger.info("Book %s %s: bid=%.3f ask=%.3f mid=%.3f",
                        side.upper(), state.market.asset.value,
                        bids[0][0], asks[0][0],
                        state.yes_price if side == "yes" else state.no_price)

        # Store snapshot
        snapshot = OrderbookSnapshot(
            timestamp=now,
            source="polymarket",
            asset=state.market.asset.value,
            bids=bids,
            asks=asks,
        )
        await self._store.add_orderbook(snapshot)

    @staticmethod
    def _parse_book_levels(levels_raw: list) -> list[tuple[float, float]]:
        """Parse bid/ask levels from Polymarket format.

        Polymarket returns levels as either:
        - {"price": "0.55", "size": "100"} (dict format)
        - ["0.55", "100"] (array format)
        """
        levels: list[tuple[float, float]] = []
        for item in levels_raw:
            try:
                if isinstance(item, dict):
                    price = float(item.get("price", 0))
                    size = float(item.get("size", 0))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    price = float(item[0])
                    size = float(item[1])
                else:
                    continue
                if size > 0:
                    levels.append((price, size))
            except (ValueError, TypeError, IndexError):
                continue
        return levels
