from __future__ import annotations

import pytest

from polybot_v3.consensus import consensus_pnl_ratio


def _snap(equity, positions):
    return {"equity": equity, "positions": positions}


def test_consensus_empty_returns_zero():
    assert consensus_pnl_ratio({}, {}) == 0.0


def test_consensus_all_winning():
    snaps = {
        "0xA": _snap(10_000, {"BTC": {"side": "LONG", "size": 0.1, "entry": 90_000}}),
        "0xB": _snap(10_000, {"ETH": {"side": "LONG", "size": 1, "entry": 3_000}}),
    }
    prices = {"BTC": 100_000, "ETH": 3_500}
    # A: (100k-90k)*0.1 = 1000, ratio 0.1
    # B: (3500-3000)*1 = 500, ratio 0.05
    # avg: 0.075
    assert consensus_pnl_ratio(snaps, prices) == pytest.approx(0.075, abs=0.01)


def test_consensus_all_losing():
    snaps = {
        "0xA": _snap(10_000, {"BTC": {"side": "LONG", "size": 0.1, "entry": 100_000}}),
    }
    prices = {"BTC": 95_000}
    # loss = -5000 * 0.1 = -500, ratio -0.05
    assert consensus_pnl_ratio(snaps, prices) == pytest.approx(-0.05, abs=0.01)


def test_consensus_skips_missing_prices():
    snaps = {
        "0xA": _snap(10_000, {"BTC": {"side": "LONG", "size": 0.1, "entry": 100_000}}),
    }
    prices = {}  # no price for BTC
    # No PnL recorded → ratio 0
    assert consensus_pnl_ratio(snaps, prices) == 0.0
