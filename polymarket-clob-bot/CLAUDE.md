# Polymarket CLOB Bot — CLAUDE.md

## Project Purpose

Automated trading bot for Polymarket 15-minute crypto prediction markets (BTC, ETH, SOL, XRP UP/DOWN). Implements a "Late Entry V3" strategy — entering positions on the market-phase favorite approximately 3-4 minutes before market close when information efficiency peaks.

## Architecture Overview

```
config/          — Settings, market definitions, strategy parameters
src/data/        — WebSocket feeds (Binance, Polymarket), Chainlink oracle, in-memory store
src/indicators/  — OHLCV, VWAP, CVD, volatility, orderbook metrics, phase detection, edge calc
src/strategy/    — Late Entry V3 logic, signal aggregation, risk management
src/execution/   — Polymarket CLOB client, order lifecycle, auto-redemption
src/analytics/   — P&L tracking, CSV trade logging, wallet analyzer
src/ml/          — Feature engineering, XGBoost/LightGBM predictor, offline training
src/telegram/    — Telegram bot for control and alerts
scripts/         — Setup, data collection, backtesting, model training
```

## How to Run

```bash
# Setup
./scripts/setup.sh
# Edit .env with credentials

# Run
python -m src.main
```

## How to Add New Indicators

1. Create a new file in `src/indicators/` (e.g., `my_indicator.py`)
2. Define a dataclass for the output
3. Implement a class with a `compute(asset, ...)` async method that reads from `DataStore`
4. Wire it into `SignalEngine.evaluate()` in `src/strategy/signal_engine.py`
5. Optionally add it as a feature in `src/ml/feature_engine.py`

## How to Modify Strategy Parameters

- **Runtime via Telegram:** `/set <param> <value>` (e.g., `/set min_edge_pct 0.03`)
- **Config file:** Edit values in `.env` and restart
- **Parameters:** `entry_window_seconds`, `min_edge_pct`, `max_position_usdc`, `kelly_fraction`, `min_leader_confidence`, `required_confirmations`

## Code Style

- **Formatter:** Black
- **Type hints:** Required on all functions and classes
- **Data models:** Use `dataclasses` — no raw dicts for structured data
- **Async:** All I/O operations must use `asyncio`
- **Logging:** Use the `logging` module with structured messages (DEBUG/INFO/WARNING/ERROR)
- **Error handling:** Every external call wrapped in try/except with retry logic

## Testing

- **Framework:** pytest
- **Focus areas:** Strategy logic, indicator calculations, risk management
- **Run:** `pytest tests/`

## Build & Run Commands

```bash
python -m src.main          # Run the bot
python scripts/backtest.py  # Backtest on historical data
python scripts/train_model.py  # Train ML model
python scripts/collect_history.py  # Collect historical data
```

## HTML/UI Elements

Every HTML/UI element must have unique id attributes following the pattern: `id="section-component-element"`
