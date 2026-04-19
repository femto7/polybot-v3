from __future__ import annotations

import logging

from polybot_v3.config import MIN_TRADER_EQUITY, MIN_TRADER_ROI_30D

log = logging.getLogger(__name__)

MIN_VOLUME_30D = 50_000
MAX_ROI_30D = 2.0  # Cap at 200% to exclude lucky one-shot plays


def select_top_traders(rows: list[dict], max_traders: int) -> list[dict]:
    """Filter leaderboard and return top N traders ranked by 30d ROI.

    Filters:
    - Equity >= MIN_TRADER_EQUITY (serious account)
    - 30d ROI in [MIN_TRADER_ROI_30D, MAX_ROI_30D] (consistent, not outlier)
    - 30d volume >= MIN_VOLUME_30D (active trader)
    - 7d ROI >= 0 (recent performance not collapsing)
    """
    filtered = [
        r for r in rows
        if r["equity"] >= MIN_TRADER_EQUITY
        and MIN_TRADER_ROI_30D <= r["roi_30d"] <= MAX_ROI_30D
        and r.get("vlm_30d", 0) >= MIN_VOLUME_30D
        and r.get("roi_7d", 0) >= 0
    ]
    filtered.sort(key=lambda r: r["roi_30d"], reverse=True)
    top = filtered[:max_traders]
    log.info("Leaderboard: %d rows, %d pass filters, selecting top %d",
             len(rows), len(filtered), len(top))
    return top
