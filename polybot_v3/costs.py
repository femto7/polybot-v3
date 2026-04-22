"""Trading cost modeling for realistic paper P&L.

Hyperliquid perps charge taker fees (~0.045% of notional) on each fill,
plus small slippage on market orders. Funding rates apply hourly on open
positions (longs pay when rate > 0, shorts receive; reversed when < 0).
"""

from __future__ import annotations

import logging
from typing import Any

from polybot_v3.config import SLIPPAGE_PCT, TAKER_FEE_PCT

log = logging.getLogger(__name__)


def entry_cost(notional: float) -> float:
    """Taker fee + slippage charged when opening a market order."""
    return notional * (TAKER_FEE_PCT + SLIPPAGE_PCT)


def exit_cost(notional: float) -> float:
    """Same cost structure when closing with a market order."""
    return notional * (TAKER_FEE_PCT + SLIPPAGE_PCT)


def apply_slippage_to_entry(price: float, side: str) -> float:
    """Simulate getting filled slightly worse than mid."""
    if side == "LONG":
        return price * (1.0 + SLIPPAGE_PCT)
    return price * (1.0 - SLIPPAGE_PCT)


def apply_slippage_to_exit(price: float, side: str) -> float:
    """Exit worse than mid too."""
    if side == "LONG":
        return price * (1.0 - SLIPPAGE_PCT)
    return price * (1.0 + SLIPPAGE_PCT)


def funding_payment(
    position_side: str,
    position_notional: float,
    funding_rate_1h: float,
) -> float:
    """Compute funding P&L impact over 1 hour.

    Positive rate: longs pay, shorts receive.
    Returns signed float (positive = we receive, negative = we pay).
    """
    if position_side == "LONG":
        return -position_notional * funding_rate_1h
    return position_notional * funding_rate_1h


def fetch_funding_rates(client: Any) -> dict[str, float]:
    """Fetch hourly funding rates from Hyperliquid.

    client: HyperliquidClient instance.
    Returns: {asset: funding_rate_1h_as_float}. Returns {} on any failure.
    """
    try:
        meta = client._info.meta_and_asset_ctxs()
        # meta is (meta, asset_ctxs); asset_ctxs[i].funding is the current funding rate
        if not isinstance(meta, (list, tuple)) or len(meta) < 2:
            return {}
        universe = meta[0].get("universe", [])
        ctxs = meta[1] or []
        out = {}
        for u, c in zip(universe, ctxs):
            name = u.get("name")
            rate = c.get("funding", 0)
            try:
                out[name] = float(rate)
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        log.debug("Failed to fetch funding rates", exc_info=True)
        return {}
