# Polybot v3 — Hyperliquid Copy Trading

Autonomous bot that monitors top Hyperliquid traders and mirrors their perp positions. Paper mode by default, live mode with `--live` flag.

## Features

- **Consistency-scored traders**: Hyperliquid top traders filtered + ranked by consistency score (ROI × trend alignment × sqrt(equity)), not pure ROI → favors stable performers over lucky pumps
- **Score-weighted copy**: Capital allocated to each trader proportional to their score
- **Leverage-aware sizing**: Respects trader leverage up to MAX_LEVERAGE (5x clamp)
- **Compounding**: Positions scale with current equity (realized + unrealized) — winnings reinvest automatically
- **Trailing stops**: Lock in profits after 3% favorable move, close on 3% retrace from peak
- **Consensus drawdown pause**: If traders collectively losing >5%, skip new entries (regime change detector)
- **WebSocket real-time**: Subscribes to trader fills → reconciles within <1s of their trade
- **Parallel fetch**: All 10 trader positions fetched concurrently (ThreadPool)
- **Risk caps**: 20% bankroll per asset, 80% total exposure, 5% hard stop-loss
- **Rich Flask dashboard**: Equity curve, filters, sortable tables, CSV export, pause/resume, analytics
- **Telegram alerts**: Opens/closes, stop hits, trailing stops, consensus pauses, drawdown alerts
- **Paper + Live modes**: `--live` flag places real orders via Hyperliquid SDK Exchange

## Quick start

```bash
# Install dependencies
python -m uv sync --extra dev

# Set environment
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx

# Paper mode (default) — no real orders
python -m uv run python -m polybot_v3 run

# Live mode — real orders (be careful!)
export HYPERLIQUID_PRIVATE_KEY=0x...          # API wallet recommended, not main key
export HYPERLIQUID_ACCOUNT_ADDRESS=0x...      # your main account (if using API wallet)
python -m uv run python -m polybot_v3 run --live

# Polling only (no WebSocket)
python -m uv run python -m polybot_v3 run --no-ws

# View state + dashboard
python -m uv run python -m polybot_v3 status
python -m uv run python -m polybot_v3 dashboard       # http://localhost:5001
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Polybot v3 Main Loop                  │
└─────────────────────────────────────────────────────────┘
                          │
    ┌─────────────────────┼─────────────────────┐
    ▼                     ▼                     ▼
 Leaderboard         Trader Monitor         Replicator
  (every 6h)         (30s + WS wake)      (score-weighted
                                              + risk caps)
                          │                     │
                          └─────────────────────┤
                                                ▼
                                   Tracker (JSON) ──→ Dashboard/Telegram
                                                ▼
                                     LiveExecutor (--live only)
                                     or Paper ledger
```

## Risk management

| Guard | Default |
|-------|---------|
| Per-asset cap | 20% of equity |
| Total exposure cap | 80% of equity |
| Max leverage clamp | 5x |
| Hard stop-loss | 5% per position |
| Trailing stop | 3% retrace after 3% gain |
| Consensus pause | skip new entries if traders avg < -5% PnL |
| Drawdown alert | Telegram warning at -10% total |
| Trader quality filter | ROI 5–200%, equity ≥$10k, volume ≥$50k |

## Project structure

```
polybot_v3/
├── __main__.py              # CLI (status, run, dashboard)
├── config.py                # Constants, env vars, risk caps
├── hyperliquid_client.py    # REST SDK wrapper
├── realtime.py              # WebSocket subscriber
├── leaderboard.py           # Select top traders by consistency score
├── consensus.py             # Detect group drawdown regime
├── trader_monitor.py        # Snapshot + delta detection
├── trailing.py              # Trailing stop logic
├── replicator.py            # Aggregate + score-weighted + risk caps
├── tracker.py               # JSON state + P&L + equity + history
├── executor.py              # LiveExecutor (Hyperliquid Exchange)
├── telegram.py              # Notifications
├── bot_state.py             # Pause/resume flag
├── loop.py                  # Main orchestration
└── dashboard/
    ├── app.py               # Flask factory + routes
    └── templates/*.html     # 5 pages (dashboard, positions, trades, traders, analytics)
```

## Disclaimer

Copy trading carries substantial risk. Even profitable leaderboard traders have drawdowns — a 200% monthly ROI often comes with 50%+ max drawdown. Start in paper mode, let the bot run a few weeks to see if the system captures edge, then scale live with small capital.
