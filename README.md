# Polybot v3 — Hyperliquid Copy Trading

Autonomous bot that monitors top Hyperliquid traders and mirrors their perp positions in paper mode.

## Features

- **Leaderboard scanner**: Fetches the Hyperliquid leaderboard every 6h, filters by 30d ROI, equity, volume
- **Position mirroring**: Aggregates positions from top traders into a single target portfolio with proportional sizing based on each trader's equity exposure
- **Risk caps**: 20% of bankroll per asset, 80% total exposure, 5x max leverage, 5% stop-loss per position
- **Rich Flask dashboard**: Equity curve, filters, sortable tables, CSV export, pause/resume, analytics page
- **Telegram alerts**: Position opens/closes, stop-loss hits, leaderboard refreshes, cycle errors
- **Paper mode**: No real orders, JSON state tracking

## Quick start

```bash
# Install dependencies
python -m uv sync --extra dev

# Set environment (optional — bot works without Telegram)
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx

# View current state
python -m uv run python -m polybot_v3 status

# Start the bot (paper mode)
python -m uv run python -m polybot_v3 run

# Launch web dashboard in another terminal
python -m uv run python -m polybot_v3 dashboard
# -> http://localhost:5001
```

## Architecture

Three cycles share a JSON-based Tracker:

1. **Leaderboard scanner** (every 6h) — refresh top traders
2. **Trader monitor** (every 2min) — poll positions, compute target, reconcile
3. **Bankroll history** (per monitor cycle) — snapshot for dashboard chart

See [`docs/superpowers/specs/2026-04-20-polybot-v3-copy-trading.md`](docs/superpowers/specs/2026-04-20-polybot-v3-copy-trading.md) for the full design.

## Project structure

```
polybot_v3/
├── __main__.py              # CLI
├── config.py                # Constants, env vars, risk caps
├── hyperliquid_client.py    # Thin SDK wrapper
├── leaderboard.py           # Select top traders by ROI
├── trader_monitor.py        # Snapshot + delta detection
├── replicator.py            # Aggregate + risk caps
├── tracker.py               # JSON state + P&L + history
├── telegram.py              # Notifications
├── bot_state.py             # Pause/resume flag
├── loop.py                  # Main orchestration
└── dashboard/
    ├── app.py               # Flask factory + routes
    └── templates/*.html     # 5 pages
```

## Risk management

- **Per-asset cap**: 20% of bankroll ($100 on $500)
- **Total exposure cap**: 80% of bankroll (keeps 20% buffer)
- **Max leverage**: 5x (hard clamp even if traders use 20x+)
- **Stop-loss**: 5% per position
- **Drawdown alert**: Telegram notification if bankroll drops >10%
- **Trader quality**: Only copy traders with ROI >5%, equity >$10k, volume >$10k

## Disclaimer

Paper mode only. Live trading is out of scope for v3. Backtested strategies don't guarantee future performance. Copy trading carries substantial risk — traders can have losing streaks.
