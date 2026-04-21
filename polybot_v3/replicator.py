from __future__ import annotations

import logging
from dataclasses import dataclass

from polybot_v3.config import (
    MAX_LEVERAGE,
    MAX_POSITION_PCT,
    MAX_TOTAL_EXPOSURE_PCT,
    MIN_POSITION_USD,
    MIN_TRADER_EXPOSURE,
)

log = logging.getLogger(__name__)


@dataclass
class TargetPosition:
    asset: str
    side: str
    notional: float  # always positive USD
    source_traders: list[str]


def compute_target_portfolio(
    trader_snapshots: dict,
    our_bankroll: float,
    max_traders: int,
    trader_weights: dict[str, float] | None = None,
) -> dict[str, TargetPosition]:
    """
    Aggregate trader positions proportionally into a target portfolio.

    trader_snapshots: {address: {"equity": float, "positions": {asset: {side, size, entry, leverage?}}}}
    trader_weights: optional {address: weight} for score-based allocation.
                    If None, equal 1/max_traders share per trader.

    Leverage-aware: each trader's exposure_ratio = notional / equity (can be > 1 for leverage).
    The resulting our_contribution is also naturally leveraged up to MAX_LEVERAGE,
    then clamped per-asset and total-exposure caps.
    """
    if not trader_snapshots:
        return {}

    # If weights provided: normalize to sum=1 across max_traders slots (fills empty slots with 0)
    # If no weights: equal 1/max_traders share (capital allocation is stable regardless of trader count)
    if trader_weights:
        total_w = sum(max(0.0, trader_weights.get(addr, 0)) for addr in trader_snapshots)
        if total_w > 0:
            trader_weights = {
                addr: max(0.0, trader_weights.get(addr, 0)) / total_w / max_traders * len(trader_snapshots)
                for addr in trader_snapshots
            }
        else:
            trader_weights = None
    if not trader_weights:
        equal = 1.0 / max_traders
        trader_weights = {addr: equal for addr in trader_snapshots}

    per_asset_cap = our_bankroll * MAX_POSITION_PCT
    total_exposure_cap = our_bankroll * MAX_TOTAL_EXPOSURE_PCT

    net_notional: dict[str, float] = {}
    contributors: dict[str, list[str]] = {}

    for address, snap in trader_snapshots.items():
        equity = snap["equity"]
        if equity <= 0:
            continue
        trader_share = our_bankroll * trader_weights.get(address, 0)
        if trader_share <= 0:
            continue
        for asset, p in snap["positions"].items():
            trader_notional = p["size"] * p["entry"]
            exposure_ratio = trader_notional / equity  # can be > 1 if leverage
            # Skip low-conviction positions (< MIN_TRADER_EXPOSURE of equity)
            if exposure_ratio < MIN_TRADER_EXPOSURE:
                continue
            # Clamp exposure to MAX_LEVERAGE (even if trader uses 20x)
            exposure_ratio = min(exposure_ratio, MAX_LEVERAGE)
            our_contribution = trader_share * exposure_ratio
            if p["side"] == "SHORT":
                our_contribution = -our_contribution
            net_notional[asset] = net_notional.get(asset, 0) + our_contribution
            contributors.setdefault(asset, []).append(address)

    targets: dict[str, TargetPosition] = {}
    total_abs = 0.0
    for asset, signed in sorted(net_notional.items(), key=lambda x: -abs(x[1])):
        if abs(signed) < MIN_POSITION_USD:
            continue
        side = "LONG" if signed > 0 else "SHORT"
        notional = min(abs(signed), per_asset_cap)
        if total_abs + notional > total_exposure_cap:
            notional = max(0, total_exposure_cap - total_abs)
            if notional < MIN_POSITION_USD:
                continue
        targets[asset] = TargetPosition(
            asset=asset,
            side=side,
            notional=round(notional, 2),
            source_traders=contributors[asset],
        )
        total_abs += notional
    return targets
