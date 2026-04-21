from __future__ import annotations

import logging
import math

from polybot_v3.config import MIN_TRADER_EQUITY, MIN_TRADER_ROI_30D

log = logging.getLogger(__name__)

MIN_VOLUME_30D = 50_000
MAX_ROI_30D = 2.0  # Cap at 200% to exclude lucky one-shot plays


def consistency_score(row: dict) -> float:
    """Compute a risk-adjusted score favoring consistent over lucky traders.

    score = roi_30d × consistency_factor × sqrt(equity_in_k)
    where consistency_factor penalizes large divergence between 30d and 7d ROI.
    """
    roi_30d = row.get("roi_30d", 0)
    roi_7d = row.get("roi_7d", 0)
    roi_1d = row.get("roi_1d", 0)
    equity = row.get("equity", 0)

    # Annualized implied ROIs for comparability
    implied_30d_from_7d = roi_7d * (30 / 7)
    implied_30d_from_1d = roi_1d * 30

    # Consistency: 7d and 1d trends aligned with 30d
    if roi_30d > 0:
        divergence_7d = abs(implied_30d_from_7d - roi_30d) / max(roi_30d, 0.01)
        divergence_1d = abs(implied_30d_from_1d - roi_30d) / max(roi_30d, 0.01)
        consistency = 1.0 / (1.0 + divergence_7d * 0.5 + divergence_1d * 0.25)
    else:
        consistency = 0.0

    size_weight = math.sqrt(max(equity, 1) / 1000)  # $1k → 1.0, $100k → 10
    return roi_30d * consistency * size_weight


def select_top_traders(rows: list[dict], max_traders: int) -> list[dict]:
    """Filter leaderboard and return top N traders ranked by consistency score.

    Filters (hard gates):
    - Equity >= MIN_TRADER_EQUITY (serious account)
    - 30d ROI in [MIN_TRADER_ROI_30D, MAX_ROI_30D] (positive, not outlier)
    - 30d volume >= MIN_VOLUME_30D (active trader)
    - 7d ROI >= 0 (recent performance not collapsing)

    Ranked by `consistency_score` which combines ROI, consistency
    between 30d/7d/1d trends, and account size.
    """
    filtered = [
        r for r in rows
        if r["equity"] >= MIN_TRADER_EQUITY
        and MIN_TRADER_ROI_30D <= r["roi_30d"] <= MAX_ROI_30D
        and r.get("vlm_30d", 0) >= MIN_VOLUME_30D
        and r.get("roi_7d", 0) >= 0
    ]
    for r in filtered:
        r["score"] = consistency_score(r)
    filtered.sort(key=lambda r: r["score"], reverse=True)
    top = filtered[:max_traders]
    log.info("Leaderboard: %d rows, %d pass filters, top %d by score",
             len(rows), len(filtered), len(top))
    return top
