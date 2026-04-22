from __future__ import annotations

import pytest

from polybot_v3.costs import (
    apply_slippage_to_entry,
    apply_slippage_to_exit,
    entry_cost,
    exit_cost,
    funding_payment,
)


def test_entry_cost_is_fee_plus_slippage():
    cost = entry_cost(1000.0)
    # 0.045% fee + 0.05% slippage = 0.095% = $0.95
    assert cost == pytest.approx(0.95, abs=0.01)


def test_exit_cost_same_as_entry():
    assert exit_cost(1000.0) == pytest.approx(0.95, abs=0.01)


def test_long_entry_slippage_worse_price():
    # Long buys — gets filled slightly above mid
    assert apply_slippage_to_entry(100.0, "LONG") > 100.0


def test_short_entry_slippage_worse_price():
    # Short sells — gets filled slightly below mid
    assert apply_slippage_to_entry(100.0, "SHORT") < 100.0


def test_long_exit_slippage_worse_price():
    # Long sells to close — gets filled slightly below mid
    assert apply_slippage_to_exit(100.0, "LONG") < 100.0


def test_funding_long_pays_positive_rate():
    # Positive funding → longs pay
    pnl = funding_payment("LONG", position_notional=1000.0, funding_rate_1h=0.0001)
    assert pnl == pytest.approx(-0.10)  # $1000 × 0.01% = -$0.10


def test_funding_short_receives_positive_rate():
    pnl = funding_payment("SHORT", position_notional=1000.0, funding_rate_1h=0.0001)
    assert pnl == pytest.approx(0.10)


def test_funding_long_receives_negative_rate():
    pnl = funding_payment("LONG", position_notional=1000.0, funding_rate_1h=-0.0001)
    assert pnl == pytest.approx(0.10)
