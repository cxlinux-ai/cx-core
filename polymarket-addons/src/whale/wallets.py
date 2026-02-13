"""Whale wallet registry for tracking top Polymarket traders."""

import json
import logging
import os
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

LEADERBOARD_URL = "https://data-api.polymarket.com/leaderboard"
DATA_DIR = Path("data")
WALLETS_FILE = DATA_DIR / "whale_wallets.json"

# Populated dynamically via refresh_from_leaderboard(); seed addresses can be
# added here if known ahead of time.
DEFAULT_WHALES: list[str] = []


class WalletRegistry:
    """Maintains a persistent set of whale wallet addresses to monitor."""

    def __init__(self, wallets_path: str | Path = WALLETS_FILE) -> None:
        self._wallets_path = Path(wallets_path)
        self._wallets: set[str] = set()
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load wallets from the JSON file on disk, falling back to defaults."""
        if self._wallets_path.exists():
            try:
                with open(self._wallets_path, "r") as fh:
                    data = json.load(fh)
                    self._wallets = set(data.get("wallets", []))
                    logger.info(
                        "Loaded %d whale wallets from %s",
                        len(self._wallets),
                        self._wallets_path,
                    )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load wallets file: %s", exc)
                self._wallets = set(DEFAULT_WHALES)
        else:
            self._wallets = set(DEFAULT_WHALES)
            logger.info(
                "No wallets file found — starting with %d default whales",
                len(self._wallets),
            )

    def _save(self) -> None:
        """Persist the current wallet set to disk."""
        self._wallets_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._wallets_path, "w") as fh:
                json.dump({"wallets": sorted(self._wallets)}, fh, indent=2)
        except OSError as exc:
            logger.error("Failed to save wallets file: %s", exc)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def add_wallet(self, address: str) -> None:
        """Add a wallet address to the tracked set."""
        normalised = address.lower().strip()
        if normalised and normalised not in self._wallets:
            self._wallets.add(normalised)
            self._save()
            logger.info("Added whale wallet %s", normalised)

    def remove_wallet(self, address: str) -> None:
        """Remove a wallet address from the tracked set."""
        normalised = address.lower().strip()
        self._wallets.discard(normalised)
        self._save()
        logger.info("Removed whale wallet %s", normalised)

    def get_wallets(self) -> list[str]:
        """Return a sorted list of all tracked wallet addresses."""
        return sorted(self._wallets)

    # ------------------------------------------------------------------
    # Leaderboard refresh
    # ------------------------------------------------------------------

    async def refresh_from_leaderboard(self) -> int:
        """Fetch the top-20 monthly leaderboard and add any new addresses.

        Returns the number of *new* wallets that were added.
        """
        added = 0
        try:
            async with aiohttp.ClientSession() as session:
                params = {"window": "month", "limit": "20"}
                async with session.get(
                    LEADERBOARD_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

            before = len(self._wallets)
            for entry in data:
                addr = entry.get("address", "").lower().strip()
                if addr:
                    self._wallets.add(addr)

            added = len(self._wallets) - before
            if added:
                self._save()
            logger.info(
                "Leaderboard refresh complete — %d new wallets added (%d total)",
                added,
                len(self._wallets),
            )
        except Exception as exc:
            logger.error("Leaderboard refresh failed: %s", exc)

        return added
