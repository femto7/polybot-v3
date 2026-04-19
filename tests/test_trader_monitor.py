from __future__ import annotations

from polybot_v3.hyperliquid_client import TraderPosition, UserState
from polybot_v3.trader_monitor import detect_changes, snapshot_trader_positions


def _tp(asset, side, size, entry=100.0):
    return TraderPosition(asset=asset, size=size, side=side, entry_price=entry,
                          leverage=1.0, unrealized_pnl=0.0)


def test_snapshot_returns_dict_of_positions():
    state = UserState(equity=50_000, positions=[
        _tp("BTC", "LONG", 0.5),
        _tp("ETH", "SHORT", 10.0),
    ])
    snap = snapshot_trader_positions(state)
    assert "BTC" in snap
    assert snap["BTC"]["side"] == "LONG"
    assert snap["BTC"]["size"] == 0.5
    assert snap["ETH"]["side"] == "SHORT"


def test_detect_changes_new_position():
    prev = {"BTC": {"side": "LONG", "size": 0.5, "entry": 95000}}
    current = {"BTC": {"side": "LONG", "size": 0.5, "entry": 95000},
               "ETH": {"side": "SHORT", "size": 5.0, "entry": 3500}}
    opened, closed, changed = detect_changes(prev, current)
    assert opened == ["ETH"]
    assert closed == []
    assert changed == []


def test_detect_changes_closed_position():
    prev = {"BTC": {"side": "LONG", "size": 0.5, "entry": 95000}}
    current = {}
    opened, closed, changed = detect_changes(prev, current)
    assert opened == []
    assert closed == ["BTC"]


def test_detect_changes_size_change():
    prev = {"BTC": {"side": "LONG", "size": 0.5, "entry": 95000}}
    current = {"BTC": {"side": "LONG", "size": 1.0, "entry": 95000}}
    opened, closed, changed = detect_changes(prev, current)
    assert changed == ["BTC"]


def test_detect_changes_side_flip_is_changed():
    prev = {"BTC": {"side": "LONG", "size": 0.5, "entry": 95000}}
    current = {"BTC": {"side": "SHORT", "size": 0.5, "entry": 96000}}
    opened, closed, changed = detect_changes(prev, current)
    assert changed == ["BTC"]


def test_detect_no_changes_when_identical():
    prev = {"BTC": {"side": "LONG", "size": 0.5, "entry": 95000}}
    current = {"BTC": {"side": "LONG", "size": 0.5, "entry": 95000}}
    opened, closed, changed = detect_changes(prev, current)
    assert opened == []
    assert closed == []
    assert changed == []
