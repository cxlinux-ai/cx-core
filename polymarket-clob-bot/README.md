# Polymarket CLOB Trading Bot

Automated trading system for [Polymarket](https://polymarket.com) 15-minute crypto prediction markets. Combines real-time Binance price data, Chainlink oracle feeds, and Polymarket orderbook intelligence to execute a **Late Entry V3** strategy.

## How It Works

Polymarket runs 15-minute binary prediction markets for crypto assets (e.g., "Will BTC go up in the next 15 minutes?"). This bot:

1. **Discovers** active 15-min markets via slug-based lookup on the Gamma API
2. **Monitors** real-time Binance price feeds, Polymarket orderbooks, and Chainlink oracles
3. **Waits** for Phase 3 (last ~4 minutes) of each market cycle
4. **Identifies** the current market leader (YES/Up vs NO/Down)
5. **Computes edge** by comparing fair value (from Binance data) to Polymarket price
6. **Checks confirmations**: CVD direction, orderbook imbalance, Binance momentum
7. **Enters** on the favorite if edge > threshold AND confirmations align
8. **Holds** until market resolution (binary outcome: win $1/share or lose position)

## Supported Assets

| Asset | Binance Feed | Chainlink Oracle | Polymarket Markets |
|-------|-------------|-----------------|-------------------|
| BTC   | btcusdt     | Polygon          | btc-updown-15m    |
| ETH   | ethusdt     | Polygon          | eth-updown-15m    |
| SOL   | solusdt     | Polygon          | sol-updown-15m    |
| XRP   | xrpusdt     | Polygon          | xrp-updown-15m   |

## Quick Start

```bash
# Clone and setup
git clone <your-repo-url> polymarket-clob-bot
cd polymarket-clob-bot
./scripts/setup.sh

# Configure credentials
cp .env.example .env
nano .env

# Run
source venv/bin/activate
python -m src.main
```

## Configuration

All configuration is via environment variables (`.env` file). See `.env.example` for all options.

### Required

| Variable | Description |
|----------|-------------|
| `POLYMARKET_PRIVATE_KEY` | Polygon wallet private key |
| `POLYMARKET_FUNDER_ADDRESS` | Funder address (for Google/Magic wallets) |
| `POLYMARKET_SIGNATURE_TYPE` | `0` for EOA wallets, `1` for Google/Magic wallets |

### Strategy Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `ENTRY_WINDOW_SECONDS` | `240` | How early before close to enter (seconds) |
| `MIN_EDGE_PCT` | `0.02` | Minimum edge required to trade (2%) |
| `MAX_POSITION_USDC` | `50.0` | Maximum position size per market |
| `MIN_LEADER_CONFIDENCE` | `0.60` | Minimum leader price to consider entry |
| `REQUIRED_CONFIRMATIONS` | `2` | Number of confirming signals needed |
| `KELLY_FRACTION` | `0.25` | Kelly criterion fraction for position sizing |

### Risk Management

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_DAILY_LOSS_USDC` | `200.0` | Daily loss limit — bot pauses if hit |
| `MAX_CONSECUTIVE_LOSSES` | `5` | Consecutive loss kill switch |
| `MAX_DRAWDOWN_PCT` | `0.15` | Max drawdown from session peak (15%) |
| `MAX_CONCURRENT_POSITIONS` | `4` | Maximum simultaneous positions |

### Modes

| Variable | Default | Description |
|----------|---------|-------------|
| `PAPER_TRADING` | `false` | Paper trading mode — simulates trades without placing real orders |
| `LOG_TRADES_CSV` | `true` | Log all trades and signals to CSV |

### Telegram

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID (restricts access to only your account) |

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Start trading |
| `/stop` | Stop trading |
| `/status` | Current positions, balance, risk state |
| `/pnl` | Session P&L summary |
| `/pnl24h` | 24-hour P&L |
| `/trades` | Last 10 trades with outcomes |
| `/kill` | Emergency stop — cancel all orders immediately |
| `/config` | Show current strategy parameters |
| `/set <param> <value>` | Update a parameter live without restarting |

## Architecture

```
polymarket-clob-bot/
├── config/
│   ├── settings.py        # Environment-based configuration
│   ├── markets.py         # Asset definitions, token mappings
│   └── strategy.py        # Strategy parameter defaults
├── src/
│   ├── main.py            # Orchestrator — wires and runs all components
│   ├── data/
│   │   ├── binance_feed.py      # Binance Futures WebSocket (price, trades, orderbook)
│   │   ├── polymarket_feed.py   # Polymarket CLOB WebSocket + Gamma API discovery
│   │   ├── chainlink_oracle.py  # Chainlink price feeds on Polygon
│   │   └── data_store.py        # In-memory ring-buffer data store
│   ├── indicators/
│   │   ├── core.py              # OHLCV, VWAP, CVD, volatility
│   │   ├── orderbook.py         # Orderbook imbalance, spread, depth
│   │   ├── market_phase.py      # 15-min market phase detection (1-4)
│   │   └── edge.py              # Edge calculation (fair value vs market price)
│   ├── strategy/
│   │   ├── late_entry.py        # Late Entry V3 strategy logic
│   │   ├── signal_engine.py     # Signal aggregation and confirmation
│   │   └── risk_manager.py      # Position limits, drawdown, kill switch
│   ├── execution/
│   │   ├── clob_client.py       # Polymarket CLOB API wrapper
│   │   ├── order_manager.py     # Order lifecycle management
│   │   └── redeemer.py          # Auto-redeem winning positions
│   ├── analytics/
│   │   ├── pnl_tracker.py       # Real-time P&L tracking
│   │   ├── trade_logger.py      # CSV logging for trades and signals
│   │   └── wallet_analyzer.py   # Wallet performance analysis
│   ├── ml/
│   │   ├── predictor.py         # ML model inference
│   │   ├── feature_engine.py    # Feature engineering pipeline
│   │   └── trainer.py           # Offline model training
│   └── telegram/
│       └── bot.py               # Telegram bot for control and alerts
├── scripts/
│   ├── setup.sh                 # Environment setup
│   ├── collect_history.py       # Historical data collection
│   ├── backtest.py              # Strategy backtesting
│   └── train_model.py           # ML model training
├── Dockerfile                   # Container build
├── docker-compose.yml           # Docker Compose config
├── railway.json                 # Railway deployment config
└── requirements.txt             # Python dependencies
```

## Data Flow

```
Binance WebSocket ──→ DataStore ──→ Indicators ──→ SignalEngine ──→ LateEntry ──→ OrderManager ──→ Polymarket CLOB
                         ↑                                                              ↓
Chainlink Oracle ────────┘                                                        Redeemer (auto-redeem wins)
                         ↑                                                              ↓
Polymarket WebSocket ────┘                                                        TelegramBot (alerts)
```

## Deployment

### Railway (Recommended)

1. Push repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add all env vars from `.env.example` in **Variables**
4. Railway auto-detects the `Dockerfile` and deploys
5. Set service to **Always On** (not sleep)

> Railway Starter plan ($5/mo) provides enough compute. The bot uses minimal CPU/RAM.

### Docker

```bash
docker build -t polymarket-bot .
docker run -d --restart always --env-file .env --name polybot polymarket-bot
```

### Docker Compose

```bash
cp .env.example .env
# Edit .env with your credentials
docker compose up -d
docker compose logs -f  # Monitor logs
```

### VPS (DigitalOcean, Hetzner, etc.)

```bash
ssh root@your-server-ip
git clone <your-repo-url> polymarket-clob-bot
cd polymarket-clob-bot
cp .env.example .env && nano .env
docker compose up -d
```

## Scripts

```bash
# Collect historical trade data for backtesting/training
python scripts/collect_history.py --limit 200

# Backtest strategy on historical data
python scripts/backtest.py --data ./data/trades_history.csv

# Train ML model (XGBoost or LightGBM)
python scripts/train_model.py --model xgboost
```

## Risk Management

- **Daily loss limit** — bot pauses trading when daily loss exceeds threshold
- **Consecutive loss kill switch** — auto-stops after N consecutive losses
- **Drawdown protection** — pauses at 15% drawdown from session peak
- **Position limits** — maximum 4 concurrent positions
- **Fractional Kelly** — position sizing based on edge and bankroll
- **Telegram kill switch** — `/kill` command instantly cancels all orders

## Paper Trading

Set `PAPER_TRADING=true` to simulate trades without placing real orders. The bot will:
- Discover markets and evaluate signals normally
- Log simulated trades with `[PAPER]` prefix
- Track simulated P&L
- Send Telegram alerts for paper trades

Use paper trading to validate strategy performance before going live.

## Tech Stack

- **Python 3.11+**
- **py-clob-client** — Polymarket CLOB API SDK
- **websockets** — Binance & Polymarket real-time feeds
- **web3.py** — Chainlink oracle reads on Polygon
- **python-telegram-bot** — Telegram integration
- **XGBoost / LightGBM** — Optional ML predictions
- **Docker** — Containerized deployment

## Disclaimer

This bot trades real money on Polymarket using USDC on Polygon. Start with paper trading mode or small position sizes ($5-10) until you verify the strategy performs as expected. You are solely responsible for any financial outcomes.
