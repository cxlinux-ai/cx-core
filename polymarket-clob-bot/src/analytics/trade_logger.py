"""CSV trade logger with daily rotation."""

from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TradeLogEntry:
    timestamp: float
    asset: str
    market_id: str
    side: str  # BUY_YES, BUY_NO
    entry_price: float
    size_usdc: float
    edge_at_entry: float
    phase: str
    leader_confidence: float
    outcome: str  # WIN, LOSS, PENDING
    pnl: float
    cumulative_pnl: float


@dataclass
class SignalLogEntry:
    timestamp: float
    asset: str
    market_id: str
    signal_direction: str
    edge: float
    confidence: float
    phase: str
    reasons: str
    traded: bool


CSV_HEADERS = [
    "timestamp", "datetime", "asset", "market_id", "side", "entry_price",
    "size_usdc", "edge_at_entry", "phase", "leader_confidence",
    "outcome", "pnl", "cumulative_pnl",
]

SIGNAL_HEADERS = [
    "timestamp", "datetime", "asset", "market_id", "signal_direction",
    "edge", "confidence", "phase", "reasons", "traded",
]


class TradeLogger:
    """Logs trades and signal evaluations to CSV files with daily rotation."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._cumulative_pnl = 0.0
        self._current_date: str = ""
        self._trade_writer: csv.writer | None = None
        self._signal_writer: csv.writer | None = None
        self._trade_file = None
        self._signal_file = None

    def _ensure_files(self) -> None:
        """Open or rotate log files based on current date."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if today == self._current_date:
            return

        self._close_files()
        self._current_date = today

        # Trade log
        trade_path = self._data_dir / f"trades_{today}.csv"
        write_header = not trade_path.exists()
        self._trade_file = open(trade_path, "a", newline="")
        self._trade_writer = csv.writer(self._trade_file)
        if write_header:
            self._trade_writer.writerow(CSV_HEADERS)

        # Signal log
        signal_path = self._data_dir / f"signals_{today}.csv"
        write_header = not signal_path.exists()
        self._signal_file = open(signal_path, "a", newline="")
        self._signal_writer = csv.writer(self._signal_file)
        if write_header:
            self._signal_writer.writerow(SIGNAL_HEADERS)

    def log_trade(self, entry: TradeLogEntry) -> None:
        """Log a trade to CSV."""
        self._ensure_files()
        self._cumulative_pnl += entry.pnl
        entry.cumulative_pnl = self._cumulative_pnl

        dt = datetime.utcfromtimestamp(entry.timestamp).isoformat()
        row = [
            entry.timestamp, dt, entry.asset, entry.market_id, entry.side,
            entry.entry_price, entry.size_usdc, entry.edge_at_entry,
            entry.phase, entry.leader_confidence, entry.outcome,
            entry.pnl, entry.cumulative_pnl,
        ]

        if self._trade_writer:
            self._trade_writer.writerow(row)
            self._trade_file.flush()

        logger.debug("Trade logged: %s %s $%.2f PnL=$%.2f", entry.side, entry.asset, entry.size_usdc, entry.pnl)

    def log_signal(self, entry: SignalLogEntry) -> None:
        """Log a signal evaluation to CSV (including non-trades)."""
        self._ensure_files()
        dt = datetime.utcfromtimestamp(entry.timestamp).isoformat()
        row = [
            entry.timestamp, dt, entry.asset, entry.market_id,
            entry.signal_direction, entry.edge, entry.confidence,
            entry.phase, entry.reasons, entry.traded,
        ]

        if self._signal_writer:
            self._signal_writer.writerow(row)
            self._signal_file.flush()

    def _close_files(self) -> None:
        if self._trade_file:
            self._trade_file.close()
            self._trade_file = None
            self._trade_writer = None
        if self._signal_file:
            self._signal_file.close()
            self._signal_file = None
            self._signal_writer = None

    def close(self) -> None:
        """Close all open files."""
        self._close_files()

    def __del__(self) -> None:
        self._close_files()
