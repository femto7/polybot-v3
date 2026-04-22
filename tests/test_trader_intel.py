from __future__ import annotations

from polybot_v3.trader_intel import (
    add_to_blacklist,
    auto_blacklist,
    compute_trader_pnl,
    load_blacklist,
)
from polybot_v3.tracker import Trade


def _trade(addr, pnl, closed_at="2026-04-22T10:00:00"):
    return Trade(
        asset="BTC", side="LONG", size=1.0, entry_price=100.0, exit_price=100.0,
        realized_pnl=pnl, source_traders=[addr],
        opened_at=closed_at, closed_at=closed_at,
    )


def test_compute_trader_pnl_single_trader():
    trades = [_trade("0xA", 10.0), _trade("0xA", -5.0)]
    traders = [{"address": "0xA"}]
    stats = compute_trader_pnl(trades, traders)
    assert stats["0xA"]["pnl"] == 5.0
    assert stats["0xA"]["wins"] == 1
    assert stats["0xA"]["losses"] == 1


def test_loss_streak_tracking():
    trades = [
        _trade("0xA", 10.0, closed_at="2026-04-22T10:00:00"),
        _trade("0xA", -5.0, closed_at="2026-04-22T10:01:00"),
        _trade("0xA", -5.0, closed_at="2026-04-22T10:02:00"),
        _trade("0xA", -5.0, closed_at="2026-04-22T10:03:00"),
    ]
    stats = compute_trader_pnl(trades, [{"address": "0xA"}])
    assert stats["0xA"]["loss_streak"] == 3


def test_loss_streak_resets_on_win():
    trades = [
        _trade("0xA", -5.0, closed_at="2026-04-22T10:00:00"),
        _trade("0xA", -5.0, closed_at="2026-04-22T10:01:00"),
        _trade("0xA", 10.0, closed_at="2026-04-22T10:02:00"),
    ]
    stats = compute_trader_pnl(trades, [{"address": "0xA"}])
    assert stats["0xA"]["loss_streak"] == 0


def test_auto_blacklist_on_cumulative_loss():
    stats = {"0xA": {"pnl": -100.0, "wins": 1, "losses": 5, "loss_streak": 1}}
    banned = auto_blacklist(stats)
    assert "0xA" in banned


def test_auto_blacklist_on_streak():
    stats = {"0xA": {"pnl": 10.0, "wins": 2, "losses": 6, "loss_streak": 6}}
    banned = auto_blacklist(stats)
    assert "0xA" in banned


def test_blacklist_persistence(tmp_path):
    path = tmp_path / "bl.json"
    assert load_blacklist(path) == set()
    add_to_blacklist(["0xA", "0xB"], path=path)
    assert load_blacklist(path) == {"0xA", "0xB"}
    add_to_blacklist(["0xC"], path=path)
    assert load_blacklist(path) == {"0xA", "0xB", "0xC"}
