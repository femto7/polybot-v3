from __future__ import annotations

import logging

from polybot_v3.hyperliquid_client import UserState

log = logging.getLogger(__name__)


def snapshot_trader_positions(state: UserState) -> dict:
    """Convert UserState to a dict for diffing: {asset: {side, size, entry}}."""
    out = {}
    for p in state.positions:
        out[p.asset] = {
            "side": p.side,
            "size": p.size,
            "entry": p.entry_price,
        }
    return out


def detect_changes(previous: dict, current: dict) -> tuple[list[str], list[str], list[str]]:
    """Return (opened, closed, changed) asset lists comparing two snapshots."""
    prev_assets = set(previous.keys())
    curr_assets = set(current.keys())

    opened = sorted(curr_assets - prev_assets)
    closed = sorted(prev_assets - curr_assets)

    changed = []
    for asset in sorted(prev_assets & curr_assets):
        p = previous[asset]
        c = current[asset]
        if p["side"] != c["side"] or abs(p["size"] - c["size"]) > 1e-9:
            changed.append(asset)
    return opened, closed, changed
