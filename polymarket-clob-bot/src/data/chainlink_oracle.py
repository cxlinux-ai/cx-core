"""Chainlink price oracle on Polygon for settlement reference prices."""

from __future__ import annotations

import asyncio
import logging
import time

from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.contract import AsyncContract

from config.markets import CHAINLINK_FEEDS, Asset
from src.data.data_store import DataStore, OraclePrice

logger = logging.getLogger(__name__)

# Chainlink AggregatorV3Interface ABI (minimal)
AGGREGATOR_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"name": "roundId", "type": "uint80"},
            {"name": "answer", "type": "int256"},
            {"name": "startedAt", "type": "uint256"},
            {"name": "updatedAt", "type": "uint256"},
            {"name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

POLYGON_RPC = "https://polygon-rpc.com"


class ChainlinkOracle:
    """Polls Chainlink price feeds on Polygon for settlement reference."""

    def __init__(
        self,
        store: DataStore,
        assets: list[Asset] | None = None,
        poll_interval: float = 5.0,
        rpc_url: str = POLYGON_RPC,
    ) -> None:
        self._store = store
        self._assets = assets or list(CHAINLINK_FEEDS.keys())
        self._poll_interval = poll_interval
        self._running = False
        self._w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self._contracts: dict[str, AsyncContract] = {}
        self._decimals: dict[str, int] = {}
        self._latest: dict[str, OraclePrice] = {}

    async def start(self) -> None:
        """Initialize contracts and begin polling."""
        self._running = True
        await self._init_contracts()
        logger.info("Chainlink oracle started — polling %s", ", ".join(a.value for a in self._assets))

        while self._running:
            await self._poll_all()
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        self._running = False

    def get_price(self, asset: str) -> OraclePrice | None:
        return self._latest.get(asset.upper())

    async def _init_contracts(self) -> None:
        for asset in self._assets:
            addr = CHAINLINK_FEEDS.get(asset)
            if not addr:
                logger.warning("No Chainlink feed for %s", asset.value)
                continue
            contract = self._w3.eth.contract(
                address=self._w3.to_checksum_address(addr),
                abi=AGGREGATOR_ABI,
            )
            self._contracts[asset.value] = contract
            try:
                decimals = await contract.functions.decimals().call()
                self._decimals[asset.value] = decimals
            except Exception as exc:
                logger.error("Failed to get decimals for %s: %s", asset.value, exc)
                self._decimals[asset.value] = 8  # Default

    async def _poll_all(self) -> None:
        tasks = [self._poll_one(asset) for asset in self._contracts]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _poll_one(self, asset: str) -> None:
        contract = self._contracts.get(asset)
        if not contract:
            return
        try:
            result = await contract.functions.latestRoundData().call()
            _, answer, _, updated_at, _ = result
            decimals = self._decimals.get(asset, 8)
            price = float(answer) / (10 ** decimals)

            oracle_price = OraclePrice(
                timestamp=time.time(),
                asset=asset,
                price=price,
                source="chainlink",
            )
            self._latest[asset] = oracle_price
            await self._store.add_oracle_price(oracle_price)
        except Exception as exc:
            logger.debug("Chainlink poll failed for %s: %s", asset, exc)
