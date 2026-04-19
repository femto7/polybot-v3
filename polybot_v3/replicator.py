from __future__ import annotations

import logging
from dataclasses import dataclass

from polybot_v3.config import (
    MAX_POSITION_PCT,
    MAX_TOTAL_EXPOSURE_PCT,
    MIN_POSITION_USD,
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
) -> dict[str, TargetPosition]:
    """
    Aggregate trader positions proportionally into a target portfolio.

    trader_snapshots: {address: {"equity": float, "positions": {asset: {side, size, entry}}}}
    """
    if not trader_snapshots:
        return {}

    share_per_trader = our_bankroll / max_traders
    per_asset_cap = our_bankroll * MAX_POSITION_PCT
    total_exposure_cap = our_bankroll * MAX_TOTAL_EXPOSURE_PCT

    net_notional: dict[str, float] = {}
    contributors: dict[str, list[str]] = {}

    for address, snap in trader_snapshots.items():
        equity = snap["equity"]
        if equity <= 0:
            continue
        for asset, p in snap["positions"].items():
            trader_notional = p["size"] * p["entry"]
            exposure_ratio = trader_notional / equity
            our_contribution = share_per_trader * exposure_ratio
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
