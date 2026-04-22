"""Trader intelligence — per-trader P&L attribution, auto-blacklist, streak tracking."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from polybot_v3.config import (
    AUTO_BLACKLIST_PNL,
    AUTO_BLACKLIST_STREAK,
    DATA_DIR,
)

log = logging.getLogger(__name__)

BLACKLIST_FILE = DATA_DIR / "blacklisted_traders.json"


def compute_trader_pnl(trades: list, traders: list[dict]) -> dict[str, dict]:
    """Return per-trader stats: attributed pnl, wins, losses, loss streak."""
    stats: dict[str, dict] = {
        t["address"]: {"pnl": 0.0, "wins": 0, "losses": 0, "loss_streak": 0, "count": 0}
        for t in traders
    }
    # Sort by closed_at chronologically for streak calc
    sorted_trades = sorted(trades, key=lambda t: getattr(t, "closed_at", ""))
    for trade in sorted_trades:
        share = 1.0 / max(len(trade.source_traders), 1)
        attributed_pnl = trade.realized_pnl * share
        for addr in trade.source_traders:
            if addr not in stats:
                continue
            s = stats[addr]
            s["pnl"] += attributed_pnl
            s["count"] += 1
            if attributed_pnl > 0:
                s["wins"] += 1
                s["loss_streak"] = 0
            else:
                s["losses"] += 1
                s["loss_streak"] += 1
    return stats


def auto_blacklist(trader_stats: dict[str, dict]) -> list[str]:
    """Return addresses that should be blacklisted (lose > threshold or hit streak)."""
    to_ban = []
    for addr, s in trader_stats.items():
        if s["pnl"] <= AUTO_BLACKLIST_PNL:
            to_ban.append(addr)
            continue
        if s["loss_streak"] >= AUTO_BLACKLIST_STREAK:
            to_ban.append(addr)
    return to_ban


def load_blacklist(path: Path = BLACKLIST_FILE) -> set[str]:
    if not Path(path).exists():
        return set()
    try:
        return set(json.loads(Path(path).read_text()))
    except Exception:
        return set()


def add_to_blacklist(addresses: list[str], path: Path = BLACKLIST_FILE) -> None:
    if not addresses:
        return
    current = load_blacklist(path)
    current.update(addresses)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(sorted(current), indent=2))
    log.warning("Blacklisted %d new traders: %s", len(addresses),
                ", ".join(a[:10] for a in addresses))
