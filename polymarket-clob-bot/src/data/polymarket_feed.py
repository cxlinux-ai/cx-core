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
            return

        m = markets_raw[0] if isinstance(markets_raw, list) else markets_raw
        condition_id = m.get("conditionId", m.get("condition_id", ""))
        if not condition_id or condition_id in self._active_markets:
            return

        tokens = m.get("tokens", [])
        if len(tokens) < 2:
            return

        yes_token = next((t for t in tokens if t.get("outcome") in ("Yes", "Up")), None)
        no_token = next((t for t in tokens if t.get("outcome") in ("No", "Down")), None)
        if not yes_token or not no_token:
            return

        close_timestamp = float(slot_ts + 900)
        question = m.get("question", slug)

        market_info = MarketInfo(
            condition_id=condition_id,
            yes_token_id=yes_token["token_id"],
            no_token_id=no_token["token_id"],
            asset=asset,
            question=question,
            close_timestamp=close_timestamp,
        )

        self._active_markets[condition_id] = MarketState(market=market_info)
        logger.info("Discovered 15m market: %s [%s] closes at %.0f",
                     question[:60], asset.value, close_timestamp)

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

    async def _subscribe_active(self, ws: websockets.WebSocketClientProtocol) -> None:
        """Subscribe to orderbook channels for all active markets."""
        for cid, state in self._active_markets.items():
            for token_id in [state.market.yes_token_id, state.market.no_token_id]:
                sub_msg = json.dumps({
                    "type": "subscribe",
                    "channel": "orderbook",
                    "market": token_id,
                })
                await ws.send(sub_msg)

    async def _consume(self, ws: websockets.WebSocketClientProtocol) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                if msg_type in ("book", "orderbook_update"):
                    await self._handle_orderbook(msg)
                elif msg_type == "trade":
                    await self._handle_trade(msg)
            except Exception as exc:
                logger.debug("Error parsing Polymarket message: %s", exc)

    async def _handle_orderbook(self, msg: dict) -> None:
        """Process orderbook snapshot or delta."""
        market_id = msg.get("market", "")
        now = time.time()

        # Find which market/side this belongs to
        for cid, state in self._active_markets.items():
            if market_id == state.market.yes_token_id:
                side = "yes"
            elif market_id == state.market.no_token_id:
                side = "no"
            else:
                continue

            bids_raw = msg.get("bids", [])
            asks_raw = msg.get("asks", [])
            bids = [(float(b["price"]), float(b["size"])) for b in bids_raw if float(b.get("size", 0)) > 0]
            asks = [(float(a["price"]), float(a["size"])) for a in asks_raw if float(a.get("size", 0)) > 0]

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

            # Store as orderbook snapshot
            snapshot = OrderbookSnapshot(
                timestamp=now,
                source="polymarket",
                asset=state.market.asset.value,
                bids=bids,
                asks=asks,
            )
            await self._store.add_orderbook(snapshot)
            break

    async def _handle_trade(self, msg: dict) -> None:
        """Process trade event."""
        market_id = msg.get("market", "")
        now = time.time()

        for cid, state in self._active_markets.items():
            if market_id in (state.market.yes_token_id, state.market.no_token_id):
                trade = Trade(
                    timestamp=now,
                    source="polymarket",
                    asset=state.market.asset.value,
                    price=float(msg.get("price", 0)),
                    quantity=float(msg.get("size", 0)),
                    is_buyer_maker=msg.get("side", "") == "sell",
                )
                await self._store.add_trade(trade)
                break
