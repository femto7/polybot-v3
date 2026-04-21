from __future__ import annotations

import os
from pathlib import Path

HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz"
HYPERLIQUID_WS_URL = "wss://api.hyperliquid.xyz/ws"
HYPERLIQUID_LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

BANKROLL_INITIAL = 500.0
MAX_TRADERS = 50
MAX_ASSETS = 60

MIN_TRADER_EQUITY = 10_000
MIN_TRADER_ROI_30D = 0.05
MIN_TRADER_TRADES_30D = 10
MAX_TRADER_DRAWDOWN = 0.30

MAX_POSITION_PCT = 0.20
MAX_TOTAL_EXPOSURE_PCT = 0.80
MAX_LEVERAGE = 5.0
STOP_LOSS_PCT = 0.05
TRAIL_STOP_PCT = 0.03  # Close if price retraces 3% from peak (after 3% favorable move)
TRAIL_ACTIVATION_PCT = 0.03
DRAWDOWN_ALERT_PCT = 0.10
CONSENSUS_PAUSE_THRESHOLD = -0.05  # If avg trader PnL ratio < -5%, pause bot (regime shift)
MIN_POSITION_USD = 1.0

LEADERBOARD_CYCLE_SECONDS = 6 * 3600
MONITOR_CYCLE_SECONDS = 15
PRICE_CYCLE_SECONDS = 15

DATA_DIR = Path(__file__).parent.parent / "data"
POSITIONS_FILE = DATA_DIR / "positions.json"
TRADES_FILE = DATA_DIR / "trades.json"
TRADERS_FILE = DATA_DIR / "traders.json"
TRADER_STATES_FILE = DATA_DIR / "trader_states.json"
BANKROLL_HISTORY_FILE = DATA_DIR / "bankroll_history.json"
BOT_STATE_FILE = DATA_DIR / "bot_state.json"

DASHBOARD_PORT = 5001
