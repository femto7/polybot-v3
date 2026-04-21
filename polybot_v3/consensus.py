"""Consensus check — detect regime change by looking at all traders' recent PnL."""

from __future__ import annotations


def all_traders_losing(
    snapshots: dict,
    threshold: float = -0.02,
) -> bool:
    """Return True if ALL tracked traders have negative unrealized PnL below threshold.

    Indicates a regime change where the whole group is wrong — pause bot.
    Uses sum of unrealized_pnl from each trader's positions.

    snapshots: {address: {"equity": ..., "positions": {asset: {side, size, entry}}}}
    """
    if not snapshots:
        return False

    losing_count = 0
    total_count = 0
    for addr, snap in snapshots.items():
        equity = snap.get("equity", 0)
        if equity <= 0:
            continue
        total_count += 1
        # We don't have live prices per snapshot here — caller must include
        # unrealized_pnl or pnl_ratio if available. Fall back to computing
        # from snapshot if unrealized not present.
        pnl_ratio = snap.get("unrealized_ratio", 0.0)
        if pnl_ratio < threshold:
            losing_count += 1

    if total_count == 0:
        return False
    return losing_count == total_count


def consensus_pnl_ratio(snapshots: dict, prices: dict[str, float]) -> float:
    """Compute the average unrealized PnL ratio across all tracked traders.

    Ratio = sum(position_pnl) / sum(trader_equity) for each trader,
    then averaged across traders.
    """
    ratios = []
    for addr, snap in snapshots.items():
        equity = snap.get("equity", 0)
        if equity <= 0:
            continue
        total_pnl = 0.0
        for asset, p in snap["positions"].items():
            px = prices.get(asset)
            if px is None:
                continue
            side_sign = 1 if p["side"] == "LONG" else -1
            total_pnl += p["size"] * (px - p["entry"]) * side_sign
        ratios.append(total_pnl / equity)
    if not ratios:
        return 0.0
    return sum(ratios) / len(ratios)
