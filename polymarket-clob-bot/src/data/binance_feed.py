"""Binance Futures WebSocket feed — aggTrade, bookTicker, markPrice."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import websockets
from websockets.exceptions import ConnectionClosed

from config.markets import BINANCE_SYMBOLS, Asset
from src.data.data_store import DataStore, OrderbookSnapshot, Trade

logger = logging.getLogger(__name__)

BINANCE_WS_BASE = "wss://fstream.binance.com/stream?streams="


@dataclass
class MarkPrice:
    asset: str
    mark_price: float
    funding_rate: float
    timestamp: float


class BinanceFeed:
    """Manages Binance Futures WebSocket connections for multiple assets."""

    def __init__(self, store: DataStore, assets: list[Asset] | None = None) -> None:
        self._store = store
        self._assets = assets or list(BINANCE_SYMBOLS.keys())
        self._running = False
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._mark_prices: dict[str, MarkPrice] = {}
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

    def _build_stream_url(self) -> str:
        streams: list[str] = []
        for asset in self._assets:
            sym = BINANCE_SYMBOLS[asset]
            streams.extend([
                f"{sym}@aggTrade",
                f"{sym}@bookTicker",
                f"{sym}@markPrice@1s",
            ])
        return BINANCE_WS_BASE + "/".join(streams)

    async def start(self) -> None:
        """Connect and begin consuming messages. Reconnects on failure."""
        self._running = True
        while self._running:
            try:
                url = self._build_stream_url()
                logger.info("Connecting to Binance WebSocket: %d streams", len(self._assets) * 3)
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    self._ws = ws
                    self._reconnect_delay = 1.0
                    logger.info("Binance WebSocket connected — %s streams active",
                                ", ".join(a.value for a in self._assets))
                    await self._consume(ws)
            except ConnectionClosed as exc:
                logger.warning("Binance WebSocket closed: %s", exc)
            except Exception as exc:
                logger.error("Binance WebSocket error: %s", exc)

            if self._running:
                logger.info("Reconnecting in %.1fs...", self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()

    def get_mark_price(self, asset: str) -> MarkPrice | None:
        return self._mark_prices.get(asset.upper())

    async def _consume(self, ws: websockets.WebSocketClientProtocol) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
                stream: str = msg.get("stream", "")
                data: dict = msg.get("data", {})

                if "@aggTrade" in stream:
                    await self._handle_agg_trade(stream, data)
                elif "@bookTicker" in stream:
                    await self._handle_book_ticker(stream, data)
                elif "@markPrice" in stream:
                    self._handle_mark_price(stream, data)
            except Exception as exc:
                logger.debug("Error parsing Binance message: %s", exc)

    async def _handle_agg_trade(self, stream: str, data: dict) -> None:
        asset = self._asset_from_stream(stream)
        if not asset:
            return
        trade = Trade(
            timestamp=data["T"] / 1000.0,
            source="binance",
            asset=asset,
            price=float(data["p"]),
            quantity=float(data["q"]),
            is_buyer_maker=data["m"],
        )
        await self._store.add_trade(trade)

    async def _handle_book_ticker(self, stream: str, data: dict) -> None:
        asset = self._asset_from_stream(stream)
        if not asset:
            return
        snapshot = OrderbookSnapshot(
            timestamp=time.time(),
            source="binance",
            asset=asset,
            bids=[(float(data["b"]), float(data["B"]))],
            asks=[(float(data["a"]), float(data["A"]))],
        )
        await self._store.add_orderbook(snapshot)

    def _handle_mark_price(self, stream: str, data: dict) -> None:
        asset = self._asset_from_stream(stream)
        if not asset:
            return
        self._mark_prices[asset] = MarkPrice(
            asset=asset,
            mark_price=float(data["p"]),
            funding_rate=float(data.get("r", 0)),
            timestamp=data["E"] / 1000.0,
        )

    def _asset_from_stream(self, stream: str) -> str | None:
        """Extract asset name from stream like 'btcusdt@aggTrade'."""
        symbol = stream.split("@")[0].upper()
        for asset, sym in BINANCE_SYMBOLS.items():
            if sym.upper() == symbol:
                return asset.value
        return None
