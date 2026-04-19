# Polybot v3 — Hyperliquid Copy Trading Bot

## Goal

Autonomous bot that monitors top profitable traders on Hyperliquid and mirrors their perp positions with proportional sizing and risk caps. Paper mode first, live mode later. Flask dashboard + Telegram notifications.

## Constraints

- **Bankroll (paper)**: $500 starting
- **Platform**: Hyperliquid perps only (v3 scope)
- **Mode**: Paper trading (live mode is out of scope for v3)
- **API**: Hyperliquid public endpoints (no auth needed for reading)
- **Max traders to copy**: 10 simultaneous
- **Max assets in portfolio**: 20

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Polybot v3 Main Loop                    │
└────────────────────────────────────────────────────────────┘
                            │
  ┌─────────────────────────┼─────────────────────────────┐
  ▼                         ▼                             ▼
┌──────────────┐    ┌───────────────┐              ┌──────────────┐
│ Leaderboard  │    │   Trader      │              │   Tracker    │
│   Scanner    │─→  │   Monitor     │─→  ┌──────→  │  (JSON +     │
│   (6h cycle) │    │  (2min poll)  │    │         │   P&L)       │
└──────────────┘    └───────────────┘    │         └──────────────┘
                            │            │                 │
                            ▼            │                 │
                    ┌───────────────┐    │                 │
                    │  Replicator   │────┘                 │
                    │  (sizing +    │                      │
                    │   risk caps)  │                      │
                    └───────────────┘                      │
                                                           ▼
                                                  ┌──────────────┐
                                                  │  Dashboard   │
                                                  │  (Flask)     │
                                                  │  Telegram    │
                                                  └──────────────┘
```

## Components

### Component 1: Leaderboard Scanner (every 6h)

Fetch Hyperliquid leaderboard and filter top traders.

**API:** `https://stats-data.hyperliquid.xyz/Mainnet/leaderboard` (public GET/POST).

**Filter criteria:**
- Min account equity: $10,000 (avoid small/new wallets)
- Min 30-day ROI: 5% (consistent profit)
- Min trades in last 30 days: 10 (active trader)
- Max drawdown: 30% (risk sanity)

**Rank by:** Sharpe-like score = `(roi_30d / max_drawdown_30d)` to favor risk-adjusted return.

**Output:** Top 10 trader addresses saved to `data/traders.json`.

### Component 2: Trader Monitor (every 2min)

For each tracked trader, poll their current positions via `POST https://api.hyperliquid.xyz/info` with `{"type": "clearinghouseState", "user": address}`.

**Detect:**
- New positions opened (asset not previously held by trader)
- Positions closed (asset previously held but now 0)
- Position size changes (partial entries/exits)

**State:** Cache previous snapshot in `data/trader_states.json` to detect deltas.

### Component 3: Replicator

Translate tracked traders' positions into our aggregated portfolio.

**Sizing formula (per asset):**

For each asset X, sum across all copied traders T:
```
our_target_notional(X) = sum_over_T (trader_T_notional(X) / trader_T_equity * OUR_EQUITY_SHARE_PER_TRADER)
```

Where `OUR_EQUITY_SHARE_PER_TRADER = our_bankroll / max_traders`.

**Risk caps:**
- Max notional per asset: 20% of bankroll ($100 on $500)
- Max leverage: 5x (clamp even if traders use more)
- Max total exposure: 80% of bankroll (reserve 20% for drawdown buffer)
- Per-position stop-loss: 5% (close on drawdown)

**Side:** LONG if net_size > 0, SHORT if < 0. Ignore if |net_size| < $2 (noise floor).

### Component 4: Tracker (JSON state)

Persist state and compute P&L.

**Files:**
- `data/positions.json` — current open positions (asset, side, size, entry, unrealized_pnl)
- `data/trades.json` — closed trades with realized P&L
- `data/traders.json` — currently tracked top traders
- `data/trader_states.json` — previous snapshot per trader (for delta detection)
- `data/bankroll_history.json` — hourly snapshots for dashboard graph

**P&L calc (paper mode):**
- Current mid price from Hyperliquid `allMids`
- `unrealized_pnl = (current_price - entry_price) * size * side_sign`
- On close: `realized_pnl = (exit_price - entry_price) * size * side_sign`

### Component 5: Dashboard (Flask) — Rich UI with filters and controls

Web UI at `http://localhost:5001`. Dark/light mode toggle, auto-refresh 15s, mobile-responsive.

**Pages:**
- `/` — main dashboard (summary + open positions + traders)
- `/positions` — detailed positions view with filters
- `/trades` — closed trades history with filters + export CSV
- `/traders` — tracked traders with per-trader performance attribution
- `/analytics` — charts (equity curve, drawdown, per-asset PnL, win rate, Sharpe)
- `/api/data` — JSON for auto-refresh
- `/api/trades.csv` — CSV export
- `/api/pause` (POST) — pause the bot
- `/api/resume` (POST) — resume the bot
- `/api/force-refresh` (POST) — trigger immediate cycle
- `/api/remove-trader/<address>` (POST) — stop copying a specific trader

**Main dashboard layout:**
- **Header**: bankroll, % change today/all-time, open count, total exposure, status indicator (live/paused)
- **KPI row**: Sharpe ratio, max drawdown, winrate, avg PnL per trade, best/worst asset
- **Equity curve** (Chart.js): bankroll evolution last 7d/30d/all-time with toggle
- **Drawdown chart**: underwater equity curve
- **Open positions table**: asset, side, size, entry, current, unrealized P&L, stop distance, source trader(s)
  - Filters: by asset, by side (long/short), by source trader, by P&L range (winning/losing/all)
  - Sortable columns (click headers)
  - Row click → expand to show which traders contributed to the position
- **Tracked traders table**: address (truncated), 30d ROI, equity, contribution to our portfolio, trades copied, win rate
  - Filter: sort by ROI, equity, or contribution
  - Row click → modal with trader's full position history and our P&L attribution
  - "Remove" button per trader (fires POST /api/remove-trader)
- **Recent trades table**: last 50 closed, with asset, side, entry, exit, realized P&L, %, source trader, duration
  - Filters: win only, loss only, by asset, by trader, date range

**Analytics page** (charts):
- Equity vs initial benchmark line
- Rolling Sharpe (7d window)
- P&L distribution histogram
- Heatmap: P&L per asset × per trader
- Win rate over time
- Asset allocation pie chart (current exposure)

**Control panel (sticky top-right):**
- Pause/Resume toggle
- Force refresh button
- Settings gear → adjust risk caps on the fly (with confirmation)
- Theme toggle (light/dark)

**Export features:**
- CSV export of trades
- CSV export of positions
- CSV export of tracked traders

**Visuals:**
- Color-coded P&L (green/red)
- Mini-sparkline charts per position (price last 24h)
- Status badges (ACTIVE/PAUSED/ERROR)
- Loading spinners during refresh
- Toast notifications on actions (pause, remove trader, etc.)

### Component 6: Telegram Notifications

- Bot starts / stops
- New position opened (with trader attribution)
- Position closed (with P&L)
- Daily summary at 08:00 UTC
- Alerts on drawdown > 10%

### Component 7: Main Loop

```
Every 2 minutes:
  1. Check tracked traders' positions (Trader Monitor)
  2. Compute target portfolio (Replicator)
  3. Diff vs current positions, execute changes (Tracker paper update)
  4. Update prices and recompute unrealized P&L
  5. Record bankroll snapshot

Every 6 hours:
  1. Refresh leaderboard top 10 (Leaderboard Scanner)
  2. Close positions from removed traders
  3. Send Telegram summary
```

## Tech Stack

- **Python 3.13** + uv
- **hyperliquid-python-sdk** — official API client
- **httpx** — async HTTP
- **flask** — dashboard
- **pytest** — tests
- No database — JSON state only

## Project Structure

```
polybot-v3/
├── pyproject.toml
├── README.md
├── .gitignore
├── start_bot.bat              # Windows launcher (gitignored)
├── data/                      # Runtime JSON (gitignored)
├── polybot_v3/
│   ├── __init__.py
│   ├── __main__.py            # CLI: status, run, dashboard
│   ├── config.py              # Constants + env vars
│   ├── hyperliquid_client.py  # Thin SDK wrapper
│   ├── leaderboard.py         # Scanner + trader filter
│   ├── trader_monitor.py      # Poll positions, detect deltas
│   ├── replicator.py          # Sizing + risk caps
│   ├── tracker.py             # JSON persistence + P&L
│   ├── telegram.py            # Notifications
│   ├── loop.py                # Main orchestration
│   └── dashboard/
│       ├── __init__.py
│       ├── app.py
│       └── templates/
│           └── index.html
└── tests/
    ├── conftest.py
    ├── test_leaderboard.py
    ├── test_trader_monitor.py
    ├── test_replicator.py
    ├── test_tracker.py
    └── test_dashboard.py
```

## Environment Variables

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

No wallet/API keys needed for paper mode (all Hyperliquid data is public).

## Risk Management

- **Position cap**: 20% bankroll per asset ($100 on $500)
- **Total exposure**: 80% of bankroll max
- **Leverage clamp**: Max 5x (even if traders use 20x+)
- **Stop-loss**: 5% per position (hard)
- **Drawdown alert**: Telegram notification if bankroll drops > 10%
- **Trader quality**: Only copy traders passing Sharpe filter

## Out of Scope (v3)

- Live trading (real orders on Hyperliquid)
- Polymarket copy trading
- Custom wallet tracking (only leaderboard traders)
- Backtesting the copy strategy on historical data
- Performance attribution per copied trader beyond simple P&L split
