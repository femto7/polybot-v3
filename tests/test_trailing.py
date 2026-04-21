from __future__ import annotations

from polybot_v3.trailing import should_trail_close, update_peak
from polybot_v3.tracker import Position


def _pos(side="LONG", entry=100.0, peak=0.0):
    return Position(
        asset="BTC", side=side, size=1.0, entry_price=entry,
        notional=entry, source_traders=["0x"], opened_at="", peak_price=peak,
    )


def test_update_peak_long_tracks_highest():
    p = _pos(side="LONG", entry=100)
    update_peak(p, 102)
    assert p.peak_price == 102
    update_peak(p, 105)
    assert p.peak_price == 105
    update_peak(p, 103)  # doesn't go down
    assert p.peak_price == 105


def test_update_peak_short_tracks_lowest():
    p = _pos(side="SHORT", entry=100)
    update_peak(p, 98)
    assert p.peak_price == 98
    update_peak(p, 95)
    assert p.peak_price == 95
    update_peak(p, 97)  # doesn't go up
    assert p.peak_price == 95


def test_trail_not_activated_before_favorable_move():
    p = _pos(side="LONG", entry=100, peak=101)
    # Only 1% favorable, below 3% activation → no close
    assert should_trail_close(p, 99, trail_pct=0.03) is False


def test_trail_long_closes_on_retrace():
    p = _pos(side="LONG", entry=100, peak=110)
    # +10% favorable, then retrace to 106 (retrace 3.6% from peak) → close
    assert should_trail_close(p, 106, trail_pct=0.03) is True


def test_trail_long_not_close_on_small_retrace():
    p = _pos(side="LONG", entry=100, peak=110)
    # +10% favorable, retrace to 109 (retrace 0.9%) → hold
    assert should_trail_close(p, 109, trail_pct=0.03) is False


def test_trail_short_closes_on_retrace():
    p = _pos(side="SHORT", entry=100, peak=90)
    # +10% favorable, then price bounces to 93 (retrace 3.3%) → close
    assert should_trail_close(p, 93, trail_pct=0.03) is True
