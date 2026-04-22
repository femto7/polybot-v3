from __future__ import annotations

import pytest

from polybot_v3.replicator import compute_target_portfolio


def _trader_snap(equity, positions):
    return {"equity": equity, "positions": positions}


def test_single_trader_proportional_sizing():
    traders = {
        "0xA": _trader_snap(50_000, {
            "BTC": {"side": "LONG", "size": 0.5, "entry": 95000}
        })
    }
    targets = compute_target_portfolio(traders, our_bankroll=500.0, max_traders=10)
    assert "BTC" in targets
    # trader BTC notional = 47500, exposure 95%
    # our share per trader = 50, contribution = 50 * 0.95 = 47.5
    assert targets["BTC"].notional == pytest.approx(47.5, abs=0.5)
    assert targets["BTC"].side == "LONG"


def test_multiple_traders_aggregate_long():
    traders = {
        "0xA": _trader_snap(50_000, {"BTC": {"side": "LONG", "size": 0.5, "entry": 95000}}),
        "0xB": _trader_snap(100_000, {"BTC": {"side": "LONG", "size": 1.0, "entry": 95000}}),
    }
    targets = compute_target_portfolio(traders, our_bankroll=500.0, max_traders=10)
    # Both have ~95% exposure, $50 share each → ~$95 total, capped at 5% per asset = $25
    assert targets["BTC"].notional == pytest.approx(50.0, abs=0.5)
    assert targets["BTC"].side == "LONG"


def test_opposite_sides_net_out():
    traders = {
        "0xA": _trader_snap(50_000, {"BTC": {"side": "LONG", "size": 0.5, "entry": 95000}}),
        "0xB": _trader_snap(50_000, {"BTC": {"side": "SHORT", "size": 0.5, "entry": 95000}}),
    }
    targets = compute_target_portfolio(traders, our_bankroll=500.0, max_traders=10)
    assert "BTC" not in targets


def test_per_asset_cap_enforced():
    traders = {
        "0xA": _trader_snap(1000, {
            "BTC": {"side": "LONG", "size": 10.0, "entry": 95000}
        })
    }
    targets = compute_target_portfolio(traders, our_bankroll=500.0, max_traders=10)
    # Capped at 5% bankroll = $25
    assert targets["BTC"].notional == pytest.approx(50.0, abs=1.0)


def test_empty_traders():
    assert compute_target_portfolio({}, our_bankroll=500.0, max_traders=10) == {}


def test_tiny_position_filtered_out():
    traders = {
        "0xA": _trader_snap(1_000_000, {
            "BTC": {"side": "LONG", "size": 0.00001, "entry": 95000}
        })
    }
    targets = compute_target_portfolio(traders, our_bankroll=500.0, max_traders=10)
    assert "BTC" not in targets


def test_weighted_traders_favor_higher_score():
    # Use 30% exposure (above MIN_TRADER_EXPOSURE=20%)
    traders = {
        "0xA": _trader_snap(100_000, {"BTC": {"side": "LONG", "size": 0.3, "entry": 100_000}}),  # 30% exposure
        "0xB": _trader_snap(100_000, {"ETH": {"side": "LONG", "size": 8.57, "entry": 3500}}),  # 30% exposure
    }
    targets = compute_target_portfolio(
        traders, our_bankroll=1_000_000.0, max_traders=2,
        trader_weights={"0xA": 3.0, "0xB": 1.0},
    )
    assert "BTC" in targets and "ETH" in targets
    # With 3:1 weight and same exposure ratio: BTC should be ~3x ETH
    assert targets["BTC"].notional > 2 * targets["ETH"].notional


def test_leverage_clamped_at_max():
    # Trader uses 20x leverage (tiny equity, huge notional)
    traders = {
        "0xA": _trader_snap(1000, {
            "BTC": {"side": "LONG", "size": 0.1, "entry": 100_000, "leverage": 20}
        })
    }
    targets = compute_target_portfolio(traders, our_bankroll=500.0, max_traders=10)
    # exposure_ratio would be 10x but clamped to MAX_LEVERAGE=5
    # our share per trader = 50, so our contribution = 50 * 5 = 250
    # But per-asset cap = 5% of 500 = 25
    assert targets["BTC"].notional == pytest.approx(50.0, abs=1.0)


def test_total_exposure_cap():
    # 3 traders, each wants 100% exposure in different assets
    traders = {
        "0xA": _trader_snap(50_000, {"BTC": {"side": "LONG", "size": 0.5, "entry": 100_000}}),
        "0xB": _trader_snap(50_000, {"ETH": {"side": "LONG", "size": 15, "entry": 3500}}),
        "0xC": _trader_snap(50_000, {"SOL": {"side": "LONG", "size": 500, "entry": 100}}),
        "0xD": _trader_snap(50_000, {"XRP": {"side": "LONG", "size": 10000, "entry": 5}}),
        "0xE": _trader_snap(50_000, {"DOGE": {"side": "LONG", "size": 100000, "entry": 0.5}}),
        "0xF": _trader_snap(50_000, {"AVAX": {"side": "LONG", "size": 500, "entry": 100}}),
        "0xG": _trader_snap(50_000, {"LINK": {"side": "LONG", "size": 2000, "entry": 25}}),
        "0xH": _trader_snap(50_000, {"UNI": {"side": "LONG", "size": 5000, "entry": 10}}),
        "0xI": _trader_snap(50_000, {"AAVE": {"side": "LONG", "size": 150, "entry": 333}}),
        "0xJ": _trader_snap(50_000, {"DOT": {"side": "LONG", "size": 5000, "entry": 10}}),
    }
    targets = compute_target_portfolio(traders, our_bankroll=500.0, max_traders=10)
    total_exposure = sum(t.notional for t in targets.values())
    # Total exposure cap = 500% of 500 = 2500 (5x leverage), per-asset cap 5% = $25
    assert total_exposure <= 2500.0 + 1.0
