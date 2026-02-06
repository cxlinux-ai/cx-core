# Polymarket CLOB Trading Bot

Automated trading system for Polymarket 15-minute crypto prediction markets. Combines real-time Binance price data with Polymarket orderbook intelligence to execute a "Late Entry" strategy.

## Strategy

**Late Entry V3** — enter positions on the market-phase favorite approximately 3-4 minutes before market close when information efficiency peaks.

1. Wait for Phase 3 (last ~4 minutes) of each 15-minute market cycle
2. Identify the current market leader (YES vs NO)
3. Compute edge: compare fair value (from Binance data) to Polymarket price
4. Check confirmations: CVD direction, orderbook imbalance, Binance momentum
5. If edge > threshold AND confirmations align → enter on the favorite
6. Hold until market resolution (binary outcome)

## Supported Assets

BTC, ETH, SOL, XRP — UP/DOWN prediction markets

## Quick Start

```bash
# Clone and setup
cd polymarket-clob-bot
./scripts/setup.sh

# Configure credentials
nano .env

# Run
source venv/bin/activate
python -m src.main
```

## Configuration

All configuration is via environment variables (`.env` file). See `.env.example` for all options.

Key parameters:
- `POLYMARKET_PRIVATE_KEY` — Polygon wallet private key
- `ENTRY_WINDOW_SECONDS` — How early before close to enter (default: 240s)
- `MIN_EDGE_PCT` — Minimum edge required (default: 2%)
- `MAX_POSITION_USDC` — Max position per market (default: $50)
- `MAX_DAILY_LOSS_USDC` — Daily loss limit (default: $200)

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Start trading |
| `/stop` | Stop trading |
| `/status` | Current positions, balance, risk state |
| `/pnl` | Session P&L summary |
| `/pnl24h` | 24-hour P&L |
| `/trades` | Last 10 trades |
| `/kill` | Emergency stop — cancel all orders |
| `/config` | Show strategy parameters |
| `/set <param> <value>` | Update parameter live |

## Architecture

```
config/          — Settings, market definitions, strategy parameters
src/data/        — Binance & Polymarket WebSocket feeds, Chainlink oracle, data store
src/indicators/  — Technical indicators, orderbook metrics, phase detection, edge calc
src/strategy/    — Late Entry V3, signal engine, risk management
src/execution/   — CLOB client, order manager, auto-redemption
src/analytics/   — P&L tracking, CSV logging, wallet analyzer
src/ml/          — Optional ML model for enhanced predictions
src/telegram/    — Telegram bot for control and alerts
scripts/         — Setup, data collection, backtesting, model training
```

## Scripts

```bash
# Collect historical data for backtesting/training
python scripts/collect_history.py --limit 200

# Backtest strategy on historical data
python scripts/backtest.py --data ./data/trades_history.csv

# Train ML model
python scripts/train_model.py --model xgboost
```

## Deployment

### Railway (Recommended — easiest)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app), create a new project, connect your repo
3. Add all env vars from `.env.example` in the Railway dashboard under **Variables**
4. Railway auto-detects the `Dockerfile` and deploys — set to **Always On** (not sleep)
5. That's it. Bot restarts automatically if it crashes.

> Railway Starter plan ($5/mo) gives you enough compute. The bot uses minimal CPU/RAM.

### VPS (DigitalOcean, Hetzner, etc.)

```bash
# SSH into your VPS
ssh root@your-server-ip

# Clone and configure
git clone <your-repo-url> polymarket-clob-bot
cd polymarket-clob-bot
cp .env.example .env
nano .env  # Add your credentials

# Run with Docker Compose (auto-restarts on crash/reboot)
docker compose up -d

# Check logs
docker compose logs -f

# Stop
docker compose down
```

### Docker (any host)

```bash
docker build -t polymarket-bot .
docker run -d --restart always --env-file .env --name polybot polymarket-bot
```

## Risk Management

- Maximum daily loss limit (configurable)
- Maximum concurrent positions: 4
- Drawdown-based pause (15% from session peak)
- Kill switch on 5 consecutive losses
- Fractional Kelly criterion position sizing

## Disclaimer

This bot trades real money on Polymarket using USDC on Polygon. Start with small position sizes ($5-10) until you verify the strategy performs as expected. You are solely responsible for any financial outcomes.
