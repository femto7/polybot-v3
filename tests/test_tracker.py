from __future__ import annotations

import pytest

from polybot_v3.tracker import Position, Tracker


def _pos(asset="BTC", side="LONG", size=0.001, entry=95000.0, source_traders=None):
    return Position(
        asset=asset,
        side=side,
        size=size,
        entry_price=entry,
        notional=size * entry,
        source_traders=source_traders or ["0xdead"],
        opened_at="2026-04-20T12:00:00Z",
    )


def test_empty_positions(tmp_tracker_files):
    t = Tracker(**tmp_tracker_files)
    assert t.load_positions() == {}


def test_add_and_load_position(tmp_tracker_files):
    t = Tracker(**tmp_tracker_files)
    t.upsert_position(_pos())
    loaded = t.load_positions()
    assert "BTC" in loaded
    assert loaded["BTC"].size == pytest.approx(0.001)


def test_close_position_records_trade(tmp_tracker_files):
    t = Tracker(**tmp_tracker_files)
    t.upsert_position(_pos(entry=95000.0))
    trade = t.close_position("BTC", exit_price=100000.0)
    assert trade is not None
    assert trade.realized_pnl == pytest.approx(0.001 * (100000 - 95000))
    assert t.load_positions() == {}
    assert len(t.load_trades()) == 1


def test_short_position_pnl(tmp_tracker_files):
    t = Tracker(**tmp_tracker_files)
    t.upsert_position(_pos(side="SHORT", entry=100000.0))
    trade = t.close_position("BTC", exit_price=95000.0)
    assert trade.realized_pnl == pytest.approx(0.001 * (100000 - 95000))


def test_bankroll_starts_at_initial(tmp_tracker_files):
    t = Tracker(**tmp_tracker_files, initial_bankroll=500.0)
    assert t.bankroll() == 500.0


def test_bankroll_after_win(tmp_tracker_files):
    t = Tracker(**tmp_tracker_files, initial_bankroll=500.0)
    t.upsert_position(_pos(entry=95000.0))
    t.close_position("BTC", exit_price=100000.0)
    assert t.bankroll() == pytest.approx(500.0 + 5.0, abs=0.01)


def test_unrealized_pnl(tmp_tracker_files):
    t = Tracker(**tmp_tracker_files)
    t.upsert_position(_pos(entry=95000.0))
    unrealized = t.unrealized_pnl({"BTC": 100000.0})
    assert unrealized == pytest.approx(5.0)


def test_record_bankroll_snapshot(tmp_tracker_files):
    t = Tracker(**tmp_tracker_files, initial_bankroll=500.0)
    t.record_bankroll_snapshot(current_prices={})
    history = t.load_bankroll_history()
    assert len(history) == 1
    assert history[0]["bankroll"] == 500.0


def test_save_and_load_traders(tmp_tracker_files):
    t = Tracker(**tmp_tracker_files)
    t.save_traders([{"address": "0xabc", "roi": 0.15, "equity": 50000}])
    loaded = t.load_traders()
    assert len(loaded) == 1
    assert loaded[0]["address"] == "0xabc"


def test_save_and_load_trader_states(tmp_tracker_files):
    t = Tracker(**tmp_tracker_files)
    t.save_trader_states({"0xabc": {"BTC": {"size": 0.5, "entry": 90000}}})
    loaded = t.load_trader_states()
    assert loaded["0xabc"]["BTC"]["size"] == 0.5
