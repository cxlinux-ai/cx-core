"""Polymarket CLOB WebSocket feed — orderbook, trades, market events."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed

from config.markets import Asset, MarketConfig, MarketInfo
from src.data.data_store import DataStore, OrderbookSnapshot, Trade

logger = logging.getLogger(__name__)

POLYMARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


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
    """Connects to Polymarket CLOB WebSocket and Gamma API for market discovery."""

    def __init__(
        self,
        store: DataStore,
        market_config: MarketConfig | None = None,
    ) -> None:
        self._store = store
        self._config = market_config or MarketConfig()
        self._running = False
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._active_markets: dict[str, MarketState] = {}
        self._subscribed_tokens: set[str] = set()
        self._reconnect_delay = 1.0

    @property
    def active_markets(self) -> dict[str, MarketState]:
        return dict(self._active_markets)

    async def start(self) -> None:
        """Run market discovery and WebSocket feed concurrently."""
        self._running = True
        await asyncio.gather(
            self._discovery_loop(),
            self._ws_loop(),
        )

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()

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

        # Subscribe on the live WebSocket if connected
        await self._subscribe_market(market_info)

    # --- WebSocket feed ---

    async def _ws_loop(self) -> None:
        """Connect to Polymarket WebSocket and consume orderbook updates."""
        while self._running:
            try:
                logger.info("Connecting to Polymarket WebSocket")
                async with websockets.connect(
                    POLYMARKET_WS_URL, ping_interval=30, ping_timeout=15
                ) as ws:
                    self._ws = ws
                    self._reconnect_delay = 1.0
                    logger.info("Polymarket WebSocket connected — monitoring 15-min markets")
                    await self._subscribe_active(ws)
                    await self._consume(ws)
            except ConnectionClosed as exc:
                logger.warning("Polymarket WebSocket closed: %s", exc)
            except Exception as exc:
                logger.error("Polymarket WebSocket error: %s", exc)

            if self._running:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60.0)

    async def _subscribe_market(self, market: MarketInfo) -> None:
        """Subscribe to orderbook channels for a single market on the live WebSocket."""
        if not self._ws:
            return
        new_tokens = []
        for token_id in [market.yes_token_id, market.no_token_id]:
            if token_id not in self._subscribed_tokens:
                new_tokens.append(token_id)
                self._subscribed_tokens.add(token_id)

        if new_tokens:
            try:
                # Polymarket market channel format: {"assets_ids": [...], "type": "market"}
                sub_msg = json.dumps({
                    "assets_ids": new_tokens,
                    "type": "market",
                })
                await self._ws.send(sub_msg)
                logger.info("Subscribed to %d token orderbooks", len(new_tokens))
            except Exception as exc:
                logger.warning("Failed to subscribe tokens: %s", exc)
                for t in new_tokens:
                    self._subscribed_tokens.discard(t)

    async def _subscribe_active(self, ws: websockets.WebSocketClientProtocol) -> None:
        """Subscribe to orderbook channels for all active markets."""
        self._subscribed_tokens.clear()
        all_tokens = []
        for cid, state in self._active_markets.items():
            all_tokens.append(state.market.yes_token_id)
            all_tokens.append(state.market.no_token_id)
            self._subscribed_tokens.add(state.market.yes_token_id)
            self._subscribed_tokens.add(state.market.no_token_id)

        if all_tokens:
            try:
                sub_msg = json.dumps({
                    "assets_ids": all_tokens,
                    "type": "market",
                })
                await ws.send(sub_msg)
                logger.info("Subscribed to %d token orderbooks (bulk)", len(all_tokens))
            except Exception as exc:
                logger.warning("Failed to bulk subscribe: %s", exc)

    async def _consume(self, ws: websockets.WebSocketClientProtocol) -> None:
        msg_count = 0
        async for raw in ws:
            try:
                msg = json.loads(raw)
                msg_count += 1

                # Log first 10 raw messages to diagnose format
                if msg_count <= 10:
                    # Truncate large fields for readability
                    log_msg = {k: (str(v)[:80] + "..." if len(str(v)) > 80 else v)
                               for k, v in msg.items()}
                    logger.info("WS msg #%d: %s", msg_count, json.dumps(log_msg, default=str))

                event_type = msg.get("event_type", msg.get("type", ""))

                if event_type == "book":
                    await self._handle_book(msg)
                elif event_type == "price_change":
                    await self._handle_price_change(msg)
                elif event_type == "last_trade_price":
                    await self._handle_trade(msg)
                elif event_type not in ("", "subscribed"):
                    logger.info("Unhandled WS event_type=%s keys=%s", event_type, list(msg.keys()))
            except Exception as exc:
                logger.warning("Error parsing Polymarket message: %s raw=%s", exc, raw[:200])

    def _find_market_side(self, asset_id: str) -> tuple[MarketState | None, str]:
        """Find which market and side (yes/no) an asset_id belongs to."""
        for cid, state in self._active_markets.items():
            if asset_id == state.market.yes_token_id:
                return state, "yes"
            elif asset_id == state.market.no_token_id:
                return state, "no"
        return None, ""

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

    async def _handle_book(self, msg: dict) -> None:
        """Process full orderbook snapshot (event_type=book)."""
        asset_id = msg.get("asset_id", msg.get("market", ""))
        state, side = self._find_market_side(asset_id)
        if state is None:
            return

        now = time.time()
        bids = self._parse_book_levels(msg.get("bids", []))
        asks = self._parse_book_levels(msg.get("asks", []))

        # Sort bids descending, asks ascending
        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        if side == "yes":
            state.yes_bids = bids or state.yes_bids
            state.yes_asks = asks or state.yes_asks
            if bids and asks:
                state.yes_price = (bids[0][0] + asks[0][0]) / 2
                logger.debug("Book update YES %s: bid=%.3f ask=%.3f mid=%.3f",
                             state.market.asset.value, bids[0][0], asks[0][0], state.yes_price)
        else:
            state.no_bids = bids or state.no_bids
            state.no_asks = asks or state.no_asks
            if bids and asks:
                state.no_price = (bids[0][0] + asks[0][0]) / 2
                logger.debug("Book update NO %s: bid=%.3f ask=%.3f mid=%.3f",
                             state.market.asset.value, bids[0][0], asks[0][0], state.no_price)

        state.last_update = now

        snapshot = OrderbookSnapshot(
            timestamp=now,
            source="polymarket",
            asset=state.market.asset.value,
            bids=bids,
            asks=asks,
        )
        await self._store.add_orderbook(snapshot)

    async def _handle_price_change(self, msg: dict) -> None:
        """Process price change event (event_type=price_change)."""
        changes = msg.get("price_changes", [msg])
        now = time.time()

        for change in changes:
            asset_id = change.get("asset_id", change.get("market", ""))
            state, side = self._find_market_side(asset_id)
            if state is None:
                continue

            # price_change events may include best_bid, best_ask, or price
            best_bid = change.get("best_bid")
            best_ask = change.get("best_ask")
            price = change.get("price")

            if best_bid is not None and best_ask is not None:
                mid = (float(best_bid) + float(best_ask)) / 2
            elif price is not None:
                mid = float(price)
            else:
                continue

            if side == "yes":
                state.yes_price = mid
            else:
                state.no_price = mid

            state.last_update = now
            logger.debug("Price change %s %s: %.3f", side.upper(), state.market.asset.value, mid)

    async def _handle_trade(self, msg: dict) -> None:
        """Process trade / last_trade_price event."""
        asset_id = msg.get("asset_id", msg.get("market", ""))
        state, side = self._find_market_side(asset_id)
        if state is None:
            return

        now = time.time()
        price = float(msg.get("price", msg.get("last_trade_price", 0)))
        size = float(msg.get("size", msg.get("amount", 0)))

        trade = Trade(
            timestamp=now,
            source="polymarket",
            asset=state.market.asset.value,
            price=price,
            quantity=size,
            is_buyer_maker=msg.get("side", "") == "sell",
        )
        await self._store.add_trade(trade)
