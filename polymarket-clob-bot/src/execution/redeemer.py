"""Auto-redeem winnings after market resolution."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from src.execution.clob_client import ClobClient

logger = logging.getLogger(__name__)


@dataclass
class RedemptionResult:
    condition_id: str
    token_id: str
    amount: float
    success: bool
    error: str = ""
    timestamp: float = field(default_factory=time.time)


class Redeemer:
    """Automatically redeems winning positions after market resolution."""

    POLL_INTERVAL = 30.0  # Seconds between redemption checks
    MAX_RETRIES = 3

    def __init__(self, clob_client: ClobClient) -> None:
        self._client = clob_client
        self._running = False
        self._pending_redemptions: dict[str, str] = {}  # condition_id -> token_id
        self._completed: list[RedemptionResult] = []
        self._on_redeem_callback: callable | None = None

    def set_redeem_callback(self, callback: callable) -> None:
        """Set a callback to be called on successful redemption.

        Callback signature: async def callback(result: RedemptionResult)
        """
        self._on_redeem_callback = callback

    def add_pending(self, condition_id: str, token_id: str) -> None:
        """Register a position for automatic redemption after resolution."""
        self._pending_redemptions[condition_id] = token_id
        logger.info("Registered for auto-redeem: condition=%s token=%s",
                     condition_id[:8], token_id[:8])

    async def start(self) -> None:
        """Begin the redemption polling loop."""
        self._running = True
        logger.info("Redeemer started — polling every %.0fs", self.POLL_INTERVAL)

        while self._running:
            if self._pending_redemptions:
                await self._check_and_redeem()
            await asyncio.sleep(self.POLL_INTERVAL)

    async def stop(self) -> None:
        self._running = False

    async def redeem_all(self) -> list[RedemptionResult]:
        """Attempt to redeem all pending positions immediately."""
        results: list[RedemptionResult] = []
        for condition_id in list(self._pending_redemptions.keys()):
            result = await self._try_redeem(condition_id)
            if result:
                results.append(result)
        return results

    @property
    def completed_redemptions(self) -> list[RedemptionResult]:
        return list(self._completed)

    async def _check_and_redeem(self) -> None:
        """Check for resolved markets and redeem winnings."""
        positions = await self._client.get_positions()
        redeemable_tokens = {p.token_id for p in positions if p.size > 0}

        for condition_id in list(self._pending_redemptions.keys()):
            token_id = self._pending_redemptions[condition_id]
            if token_id in redeemable_tokens:
                result = await self._try_redeem(condition_id)
                if result and result.success:
                    logger.info(
                        "Redeemed $%.2f for condition %s",
                        result.amount, condition_id[:8],
                    )

    async def _try_redeem(self, condition_id: str) -> RedemptionResult | None:
        token_id = self._pending_redemptions.get(condition_id)
        if not token_id:
            return None

        for attempt in range(self.MAX_RETRIES):
            try:
                # Check current position size
                positions = await self._client.get_positions()
                position = next(
                    (p for p in positions if p.token_id == token_id), None
                )

                if not position or position.size <= 0:
                    # Already redeemed or no position
                    self._pending_redemptions.pop(condition_id, None)
                    return None

                # Attempt redemption by selling the winning tokens
                # In Polymarket, winning shares are worth $1 each
                result = await self._client.place_market_order(
                    token_id=token_id,
                    side="SELL",
                    size=position.size,
                )

                if result.success:
                    redemption = RedemptionResult(
                        condition_id=condition_id,
                        token_id=token_id,
                        amount=position.size,  # Each winning share = $1
                        success=True,
                    )
                    self._completed.append(redemption)
                    self._pending_redemptions.pop(condition_id, None)

                    if self._on_redeem_callback:
                        try:
                            await self._on_redeem_callback(redemption)
                        except Exception as exc:
                            logger.debug("Redeem callback error: %s", exc)

                    return redemption

            except Exception as exc:
                logger.warning(
                    "Redeem attempt %d/%d failed for %s: %s",
                    attempt + 1, self.MAX_RETRIES, condition_id[:8], exc,
                )
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2.0 * (attempt + 1))

        return RedemptionResult(
            condition_id=condition_id,
            token_id=token_id,
            amount=0.0,
            success=False,
            error="Max retries exceeded",
        )
