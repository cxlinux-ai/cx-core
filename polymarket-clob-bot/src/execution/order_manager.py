"""Order lifecycle management: create, monitor, cancel, retry."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from src.execution.clob_client import ClobClient, OrderResult, OrderSide, TimeInForce

logger = logging.getLogger(__name__)


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    MATCHED = "MATCHED"
    CONFIRMED = "CONFIRMED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class ManagedOrder:
    """An order tracked by the order manager."""
    order_id: str
    token_id: str
    side: OrderSide
    price: float
    size_usdc: float
    status: OrderStatus = OrderStatus.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    fill_price: float = 0.0
    fill_size: float = 0.0
    error: str = ""
    market_condition_id: str = ""
    asset: str = ""


class OrderManager:
    """Manages order lifecycle: creation, monitoring, cancellation."""

    STALE_ORDER_TIMEOUT = 120.0  # Cancel orders older than 2 minutes

    def __init__(self, clob_client: ClobClient) -> None:
        self._client = clob_client
        self._orders: dict[str, ManagedOrder] = {}
        self._running = False

    @property
    def active_orders(self) -> list[ManagedOrder]:
        return [
            o for o in self._orders.values()
            if o.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.MATCHED)
        ]

    async def place_market_order(
        self,
        token_id: str,
        side: OrderSide,
        size_usdc: float,
        asset: str = "",
        condition_id: str = "",
    ) -> ManagedOrder:
        """Place a market order (FOK) and track it."""
        order = ManagedOrder(
            order_id="",
            token_id=token_id,
            side=side,
            price=0.0,  # Market order — price determined at fill
            size_usdc=size_usdc,
            asset=asset,
            market_condition_id=condition_id,
        )

        result = await self._client.place_market_order(token_id, side, size_usdc)
        self._apply_result(order, result)
        self._orders[order.order_id or f"pending_{time.time()}"] = order

        logger.info(
            "Market order %s: %s %s $%.2f | status=%s",
            order.order_id[:8] if order.order_id else "?",
            side.value,
            asset,
            size_usdc,
            order.status.value,
        )
        return order

    async def place_limit_order(
        self,
        token_id: str,
        side: OrderSide,
        price: float,
        size_usdc: float,
        tif: TimeInForce = TimeInForce.GTC,
        asset: str = "",
        condition_id: str = "",
    ) -> ManagedOrder:
        """Place a limit order and track it."""
        order = ManagedOrder(
            order_id="",
            token_id=token_id,
            side=side,
            price=price,
            size_usdc=size_usdc,
            asset=asset,
            market_condition_id=condition_id,
        )

        result = await self._client.place_limit_order(token_id, side, price, size_usdc, tif)
        self._apply_result(order, result)
        self._orders[order.order_id or f"pending_{time.time()}"] = order

        logger.info(
            "Limit order %s: %s %s $%.2f @ %.4f | status=%s",
            order.order_id[:8] if order.order_id else "?",
            side.value,
            asset,
            size_usdc,
            price,
            order.status.value,
        )
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order."""
        success = await self._client.cancel_order(order_id)
        if success and order_id in self._orders:
            self._orders[order_id].status = OrderStatus.CANCELLED
            self._orders[order_id].updated_at = time.time()
        return success

    async def cancel_all(self) -> int:
        """Cancel all open orders."""
        count = await self._client.cancel_all_orders()
        for order in self.active_orders:
            order.status = OrderStatus.CANCELLED
            order.updated_at = time.time()
        logger.info("Cancelled %d orders", count)
        return count

    async def cleanup_stale(self) -> int:
        """Cancel orders that have been open too long."""
        now = time.time()
        cancelled = 0
        for order in self.active_orders:
            if now - order.created_at > self.STALE_ORDER_TIMEOUT:
                logger.info("Cancelling stale order %s (age=%.0fs)",
                            order.order_id[:8], now - order.created_at)
                await self.cancel_order(order.order_id)
                cancelled += 1
        return cancelled

    def get_order(self, order_id: str) -> ManagedOrder | None:
        return self._orders.get(order_id)

    def get_orders_for_market(self, condition_id: str) -> list[ManagedOrder]:
        return [
            o for o in self._orders.values()
            if o.market_condition_id == condition_id
        ]

    def _apply_result(self, order: ManagedOrder, result: OrderResult) -> None:
        order.updated_at = time.time()
        if result.success:
            order.order_id = result.order_id
            order.status = OrderStatus.SUBMITTED
            order.fill_size = result.filled_size
            order.fill_price = result.filled_price
        else:
            order.status = OrderStatus.FAILED
            order.error = result.error
