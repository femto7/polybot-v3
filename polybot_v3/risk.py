"""Risk guards: daily kill switch, daily profit freeze, correlation filter, volatility cap."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from polybot_v3.config import (
    DAILY_DRAWDOWN_KILL_PCT,
    DAILY_PROFIT_FREEZE_PCT,
    MAX_POSITIONS_PER_CATEGORY,
    MAX_VOL_24H_PCT,
)

log = logging.getLogger(__name__)

# Rough categorization — assets that tend to move together
ASSET_CATEGORIES: dict[str, str] = {
    # Majors
    "BTC": "MAJOR", "ETH": "MAJOR",
    # L1 alts
    "SOL": "L1", "AVAX": "L1", "NEAR": "L1", "APT": "L1", "SUI": "L1", "SEI": "L1",
    "ADA": "L1", "DOT": "L1", "ATOM": "L1", "ALGO": "L1", "INJ": "L1", "TON": "L1",
    # DeFi
    "UNI": "DEFI", "AAVE": "DEFI", "COMP": "DEFI", "SNX": "DEFI", "MKR": "DEFI",
    "CRV": "DEFI", "DYDX": "DEFI", "1INCH": "DEFI", "LDO": "DEFI",
    # Memes
    "DOGE": "MEME", "SHIB": "MEME", "PEPE": "MEME", "WIF": "MEME", "BONK": "MEME",
    "FLOKI": "MEME",
    # Gaming/NFT
    "GALA": "GAMING", "SAND": "GAMING", "AXS": "GAMING", "IMX": "GAMING",
    # Layer 2
    "OP": "L2", "ARB": "L2", "MATIC": "L2", "STRK": "L2",
}


def categorize(asset: str) -> str:
    return ASSET_CATEGORIES.get(asset, "OTHER")


def daily_drawdown_check(history: list[dict]) -> tuple[bool, float]:
    """Return (should_kill, drawdown_pct_from_day_peak).

    Looks at the last 24h of history snapshots; if equity dropped >X% from
    the high watermark of the day, return should_kill=True.
    """
    if not history:
        return False, 0.0
    now = datetime.now(timezone.utc)
    today = []
    for h in history:
        try:
            ts = datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00"))
        except Exception:
            continue
        if (now - ts).total_seconds() <= 86400:
            today.append(h)
    if not today:
        return False, 0.0
    peak = max(h.get("equity", 0) for h in today)
    current = today[-1].get("equity", 0)
    if peak <= 0:
        return False, 0.0
    dd = (peak - current) / peak
    return dd >= DAILY_DRAWDOWN_KILL_PCT, dd


def daily_profit_freeze_check(history: list[dict], initial: float) -> tuple[bool, float]:
    """Return (should_freeze, day_gain_pct) if today's gain exceeds threshold."""
    if not history:
        return False, 0.0
    now = datetime.now(timezone.utc)
    today_start = None
    for h in history:
        try:
            ts = datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00"))
        except Exception:
            continue
        if (now - ts).total_seconds() <= 86400:
            today_start = h
            break
    if today_start is None:
        return False, 0.0
    start_equity = today_start.get("equity", initial)
    current_equity = history[-1].get("equity", initial)
    if start_equity <= 0:
        return False, 0.0
    gain = (current_equity - start_equity) / start_equity
    return gain >= DAILY_PROFIT_FREEZE_PCT, gain


def filter_by_category_limit(
    targets: dict,
    current_positions: dict,
) -> dict:
    """Drop target positions if we already hit MAX_POSITIONS_PER_CATEGORY."""
    counts: dict[str, int] = {}
    for p in current_positions.values():
        cat = categorize(p.asset)
        counts[cat] = counts.get(cat, 0) + 1

    out = {}
    # Sort by notional desc so we keep the biggest signals first
    for asset, target in sorted(targets.items(), key=lambda x: -x[1].notional):
        cat = categorize(asset)
        if counts.get(cat, 0) >= MAX_POSITIONS_PER_CATEGORY:
            log.debug("Skipping %s — category %s full (%d)", asset, cat, counts[cat])
            continue
        out[asset] = target
        counts[cat] = counts.get(cat, 0) + 1
    return out


def filter_high_vol(targets: dict, vol_24h: dict[str, float]) -> dict:
    """Skip assets with > MAX_VOL_24H_PCT daily volatility."""
    if not vol_24h:
        return targets
    out = {}
    for asset, target in targets.items():
        v = vol_24h.get(asset)
        if v is not None and v > MAX_VOL_24H_PCT:
            log.debug("Skipping %s — vol %.1f%% > cap", asset, v * 100)
            continue
        out[asset] = target
    return out
