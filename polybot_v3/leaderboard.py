from __future__ import annotations

import logging

from polybot_v3.config import MIN_TRADER_EQUITY, MIN_TRADER_ROI_30D

log = logging.getLogger(__name__)

MIN_VOLUME_30D = 10_000


def select_top_traders(rows: list[dict], max_traders: int) -> list[dict]:
    """Filter leaderboard and return top N traders ranked by 30d ROI."""
    filtered = [
        r for r in rows
        if r["equity"] >= MIN_TRADER_EQUITY
        and r["roi_30d"] >= MIN_TRADER_ROI_30D
        and r.get("vlm_30d", 0) >= MIN_VOLUME_30D
    ]
    filtered.sort(key=lambda r: r["roi_30d"], reverse=True)
    top = filtered[:max_traders]
    log.info("Leaderboard: %d rows, %d pass filters, selecting top %d",
             len(rows), len(filtered), len(top))
    return top
