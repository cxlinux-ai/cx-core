"""Polymarket CLOB client wrapper — auth, orders, positions, balance."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from functools import partial

from py_clob_client.client import ClobClient as _PyClobClient
from py_clob_client.clob_types import (
    MarketOrderArgs,
    OrderArgs,
    OrderType,
)

from config.settings import PolymarketSettings

logger = logging.getLogger(__name__)


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TimeInForce(str, Enum):
    FOK = "FOK"  # Fill or Kill
    GTC = "GTC"  # Good Til Cancel


@dataclass
class OrderResult:
    success: bool
    order_id: str = ""
    error: str = ""
    filled_size: float = 0.0
    filled_price: float = 0.0


@dataclass
class Position:
    token_id: str
    size: float
    avg_price: float
    side: str
    market: str = ""


class ClobClient:
    """Async wrapper around py-clob-client for Polymarket CLOB operations."""

    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(self, settings: PolymarketSettings) -> None:
        self._settings = settings
        self._client: _PyClobClient | None = None
        self._has_creds = False

    async def initialize(self) -> bool:
        """Initialize the CLOB client and verify authentication."""
        try:
            logger.info(
                "CLOB init: host=%s chain=%d sig_type=%d funder=%s",
                self._settings.api_host,
                self._settings.chain_id,
                self._settings.signature_type,
                self._settings.funder_address or "none",
            )
            self._client = _PyClobClient(
                host=self._settings.api_host,
                key=self._settings.private_key,
                chain_id=self._settings.chain_id,
                funder=self._settings.funder_address or None,
                signature_type=self._settings.signature_type,
            )
            # Derive L2 API credentials — call create_or_derive first, then set
            try:
                creds = await self._run_sync(self._client.create_or_derive_api_creds)
                if creds:
                    self._client.set_api_creds(creds)
                    self._has_creds = True
                    logger.info("CLOB client authenticated successfully (L2 creds set)")
                else:
                    logger.warning("L2 cred derivation returned None — balance/order calls will be skipped")
            except Exception as cred_exc:
                logger.error("L2 cred derivation failed: %s", cred_exc)
            return True
        except Exception as exc:
            logger.error("Failed to initialize CLOB client: %s", exc)
            return False

    async def get_balance(self) -> float:
        """Get USDC balance."""
        if not self._has_creds:
            logger.warning("get_balance skipped — no L2 credentials")
            return 0.0
        try:
            result = await self._run_sync(
                self._client.get_balance_allowance,
                self._settings.signature_type,
            )
            if isinstance(result, dict):
                balance = float(result.get("balance", 0))
                logger.info("Balance: $%.2f USDC", balance)
                return balance
            return 0.0
        except Exception as exc:
            logger.error("Failed to get balance: %s", exc)
            return 0.0

    async def get_positions(self) -> list[Position]:
        """Get all open positions."""
        try:
            raw = await self._run_sync(self._client.get_positions)
            positions: list[Position] = []
            if isinstance(raw, list):
                for p in raw:
                    positions.append(Position(
                        token_id=p.get("asset", ""),
                        size=float(p.get("size", 0)),
                        avg_price=float(p.get("avgPrice", 0)),
                        side=p.get("side", ""),
                        market=p.get("market", ""),
                    ))
            return positions
        except Exception as exc:
            logger.error("Failed to get positions: %s", exc)
            return []

    async def place_market_order(
        self,
        token_id: str,
        side: OrderSide,
        size: float,
    ) -> OrderResult:
        """Place a market order (FOK — Fill or Kill)."""
        for attempt in range(self.MAX_RETRIES):
            try:
                order_args = MarketOrderArgs(
                    token_id=token_id,
                    amount=size,
                )
                if side == OrderSide.BUY:
                    result = await self._run_sync(self._client.create_and_post_order, order_args)
                else:
                    result = await self._run_sync(self._client.create_and_post_order, order_args)

                if isinstance(result, dict):
                    order_id = result.get("orderID", result.get("id", ""))
                    return OrderResult(
                        success=True,
                        order_id=order_id,
                        filled_size=size,
                    )
                return OrderResult(success=True, order_id=str(result))

            except Exception as exc:
                logger.warning(
                    "Market order attempt %d/%d failed: %s",
                    attempt + 1, self.MAX_RETRIES, exc,
                )
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))

        return OrderResult(success=False, error="Max retries exceeded")

    async def place_limit_order(
        self,
        token_id: str,
        side: OrderSide,
        price: float,
        size: float,
        tif: TimeInForce = TimeInForce.GTC,
    ) -> OrderResult:
        """Place a limit order."""
        for attempt in range(self.MAX_RETRIES):
            try:
                order_args = OrderArgs(
                    token_id=token_id,
                    price=price,
                    size=size,
                    side=side.value,
                )
                signed = await self._run_sync(self._client.create_order, order_args)
                result = await self._run_sync(self._client.post_order, signed, order_type=OrderType.GTC if tif == TimeInForce.GTC else OrderType.FOK)

                if isinstance(result, dict):
                    order_id = result.get("orderID", result.get("id", ""))
                    return OrderResult(success=True, order_id=order_id)
                return OrderResult(success=True, order_id=str(result))

            except Exception as exc:
                logger.warning(
                    "Limit order attempt %d/%d failed: %s",
                    attempt + 1, self.MAX_RETRIES, exc,
                )
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))

        return OrderResult(success=False, error="Max retries exceeded")

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        try:
            await self._run_sync(self._client.cancel, order_id)
            return True
        except Exception as exc:
            logger.error("Failed to cancel order %s: %s", order_id, exc)
            return False

    async def cancel_all_orders(self) -> int:
        """Cancel all open orders. Returns count of cancelled orders."""
        try:
            result = await self._run_sync(self._client.cancel_all)
            if isinstance(result, dict):
                return int(result.get("canceled", 0))
            return 0
        except Exception as exc:
            logger.error("Failed to cancel all orders: %s", exc)
            return 0

    async def get_open_orders(self) -> list[dict]:
        """Get all open orders."""
        try:
            result = await self._run_sync(self._client.get_orders)
            return result if isinstance(result, list) else []
        except Exception as exc:
            logger.error("Failed to get open orders: %s", exc)
            return []

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous py-clob-client method in a thread executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))
