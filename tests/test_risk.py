from __future__ import annotations

from datetime import datetime, timezone

from polybot_v3.replicator import TargetPosition
from polybot_v3.risk import (
    categorize,
    daily_drawdown_check,
    daily_profit_freeze_check,
    filter_by_category_limit,
    filter_high_vol,
)
from polybot_v3.tracker import Position


def _snap(equity, offset_sec=0):
    ts = datetime.now(timezone.utc).timestamp() - offset_sec
    return {
        "timestamp": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
        "equity": equity,
        "bankroll": equity,
    }


def _pos(asset):
    return Position(
        asset=asset, side="LONG", size=1.0, entry_price=100.0, notional=100.0,
        source_traders=["0x"], opened_at="2026-04-22T10:00:00Z",
    )


def _target(asset, notional=50.0):
    return TargetPosition(asset=asset, side="LONG", notional=notional, source_traders=["0x"])


def test_categorize_known_assets():
    assert categorize("BTC") == "MAJOR"
    assert categorize("SOL") == "L1"
    assert categorize("UNI") == "DEFI"
    assert categorize("DOGE") == "MEME"
    assert categorize("UNKNOWN") == "OTHER"


def test_daily_drawdown_triggers_above_threshold():
    history = [_snap(1000, 3600), _snap(900, 1800), _snap(850, 0)]  # 15% drop
    kill, dd = daily_drawdown_check(history)
    assert kill is True
    assert dd >= 0.10


def test_daily_drawdown_no_trigger_small_dip():
    history = [_snap(1000, 3600), _snap(975, 0)]  # 2.5% dip
    kill, dd = daily_drawdown_check(history)
    assert kill is False


def test_daily_profit_freeze_triggers():
    history = [_snap(1000, 3600), _snap(1200, 0)]  # +20%
    freeze, gain = daily_profit_freeze_check(history, initial=1000)
    assert freeze is True


def test_filter_by_category_limit_drops_excess():
    # 4 L1 already held → 5th L1 target dropped
    current = {f"L1_{i}": _pos(asset) for i, asset in enumerate(["SOL", "AVAX", "NEAR", "ATOM"])}
    targets = {"APT": _target("APT"), "BTC": _target("BTC")}
    out = filter_by_category_limit(targets, current)
    assert "APT" not in out  # would exceed L1 cap of 4
    assert "BTC" in out  # MAJOR has no conflict


def test_filter_high_vol_drops_excessive():
    targets = {"BTC": _target("BTC"), "PEPE": _target("PEPE")}
    vol = {"BTC": 0.05, "PEPE": 0.50}  # 50% vol too high
    out = filter_high_vol(targets, vol)
    assert "BTC" in out
    assert "PEPE" not in out
