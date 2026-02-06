"""Backfill historical market data to CSV for training and backtesting."""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import aiohttp

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"


async def fetch_resolved_markets(limit: int = 500) -> list[dict]:
    """Fetch recently resolved 15-min crypto markets from Gamma API."""
    markets: list[dict] = []
    offset = 0

    async with aiohttp.ClientSession() as session:
        while len(markets) < limit:
            params = {
                "closed": "true",
                "limit": 100,
                "offset": offset,
                "order": "endDate",
                "ascending": "false",
            }
            async with session.get(
                f"{GAMMA_API}/markets", params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    logger.warning("Gamma API returned %d", resp.status)
                    break
                data = await resp.json()

            if not data:
                break

            for m in data:
                question = m.get("question", "").lower()
                is_crypto_15m = any(
                    kw in question for kw in ["btc", "eth", "sol", "xrp", "bitcoin", "ethereum", "15 min"]
                )
                if is_crypto_15m:
                    markets.append(m)

            offset += 100
            if len(data) < 100:
                break

    logger.info("Found %d resolved crypto markets", len(markets))
    return markets[:limit]


async def fetch_market_trades(market_id: str, session: aiohttp.ClientSession) -> list[dict]:
    """Fetch all trades for a specific market."""
    trades: list[dict] = []
    cursor = None

    for _ in range(50):
        params: dict = {"market": market_id, "limit": 500}
        if cursor:
            params["cursor"] = cursor

        try:
            async with session.get(
                f"{DATA_API}/trades", params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    break
                data = await resp.json()
        except Exception:
            break

        results = data if isinstance(data, list) else data.get("data", [])
        if not results:
            break

        trades.extend(results)
        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        if not cursor:
            break

    return trades


async def main(args: argparse.Namespace) -> None:
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Fetching resolved markets (limit=%d)...", args.limit)
    markets = await fetch_resolved_markets(args.limit)

    if not markets:
        logger.error("No markets found")
        return

    # Export market metadata
    meta_path = output_dir / "markets_history.csv"
    with open(meta_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["condition_id", "question", "end_date", "outcome", "volume"])
        for m in markets:
            writer.writerow([
                m.get("conditionId", ""),
                m.get("question", ""),
                m.get("endDate", ""),
                m.get("outcome", ""),
                m.get("volume", ""),
            ])
    logger.info("Wrote market metadata to %s", meta_path)

    # Fetch trades for each market
    trades_path = output_dir / "trades_history.csv"
    total_trades = 0

    async with aiohttp.ClientSession() as session:
        with open(trades_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "market_id", "question", "side", "price",
                "size", "outcome", "asset",
            ])

            for i, m in enumerate(markets):
                cid = m.get("conditionId", "")
                question = m.get("question", "")
                outcome = m.get("outcome", "")

                # Detect asset
                asset = "UNKNOWN"
                for a in ["BTC", "ETH", "SOL", "XRP"]:
                    if a in question.upper():
                        asset = a
                        break

                logger.info(
                    "[%d/%d] Fetching trades for %s...",
                    i + 1, len(markets), question[:50],
                )
                trades = await fetch_market_trades(cid, session)

                for t in trades:
                    writer.writerow([
                        t.get("timestamp", ""),
                        cid,
                        question,
                        t.get("side", ""),
                        t.get("price", ""),
                        t.get("size", ""),
                        outcome,
                        asset,
                    ])
                    total_trades += 1

                # Rate limiting
                await asyncio.sleep(0.5)

    logger.info("Wrote %d trades to %s", total_trades, trades_path)
    logger.info("Collection complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect historical Polymarket data")
    parser.add_argument("--limit", type=int, default=200, help="Max markets to fetch")
    parser.add_argument("--output", type=str, default="./data", help="Output directory")
    args = parser.parse_args()
    asyncio.run(main(args))
