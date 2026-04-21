"""Trailing stop logic — track peak favorable price, close at X% below peak."""

from __future__ import annotations

from polybot_v3.tracker import Position


def update_peak(position: Position, current_price: float) -> Position:
    """Update peak_price if current price is more favorable than stored peak."""
    if position.side == "LONG":
        if position.peak_price == 0 or current_price > position.peak_price:
            position.peak_price = current_price
    else:
        if position.peak_price == 0 or current_price < position.peak_price:
            position.peak_price = current_price
    return position


def should_trail_close(
    position: Position,
    current_price: float,
    trail_pct: float,
    activation_pct: float = 0.03,
) -> bool:
    """Return True if trailing stop is triggered.

    Activates only after the position has moved at least `activation_pct`
    in our favor from entry. Then closes if price retraces `trail_pct`
    from the peak.
    """
    if position.peak_price == 0:
        return False

    if position.side == "LONG":
        favorable_move = (position.peak_price - position.entry_price) / position.entry_price
        retrace = (position.peak_price - current_price) / position.peak_price
    else:
        favorable_move = (position.entry_price - position.peak_price) / position.entry_price
        retrace = (current_price - position.peak_price) / position.peak_price

    if favorable_move < activation_pct:
        return False
    return retrace >= trail_pct
