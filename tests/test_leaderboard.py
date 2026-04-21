from __future__ import annotations

from polybot_v3.leaderboard import consistency_score, select_top_traders


def _row(address, equity, roi_30d, vlm_30d=50_000):
    return {
        "address": address,
        "equity": equity,
        "roi_30d": roi_30d,
        "pnl_30d": equity * roi_30d,
        "vlm_30d": vlm_30d,
        "roi_7d": roi_30d / 4,
        "roi_1d": roi_30d / 30,
    }


def test_select_filters_low_equity():
    rows = [_row("0x1", 5_000, 0.10), _row("0x2", 50_000, 0.10)]
    selected = select_top_traders(rows, max_traders=10)
    assert len(selected) == 1
    assert selected[0]["address"] == "0x2"


def test_select_filters_low_roi():
    rows = [_row("0x1", 50_000, 0.01), _row("0x2", 50_000, 0.10)]
    selected = select_top_traders(rows, max_traders=10)
    assert len(selected) == 1
    assert selected[0]["address"] == "0x2"


def test_select_sorts_by_roi():
    rows = [_row("0x1", 50_000, 0.08), _row("0x2", 50_000, 0.15)]
    selected = select_top_traders(rows, max_traders=10)
    assert selected[0]["address"] == "0x2"


def test_select_caps_at_max_traders():
    rows = [_row(f"0x{i}", 50_000, 0.10 + i * 0.01) for i in range(20)]
    selected = select_top_traders(rows, max_traders=5)
    assert len(selected) == 5


def test_select_filters_low_volume():
    rows = [
        _row("0x1", 50_000, 0.10, vlm_30d=1_000),
        _row("0x2", 50_000, 0.10, vlm_30d=100_000),
    ]
    selected = select_top_traders(rows, max_traders=10)
    assert len(selected) == 1
    assert selected[0]["address"] == "0x2"


def test_select_empty_rows():
    assert select_top_traders([], max_traders=10) == []


def test_select_all_filtered_out():
    rows = [_row("0x1", 1000, 0.001)]
    assert select_top_traders(rows, max_traders=10) == []


def test_consistency_score_rewards_stable_traders():
    # Both have 20% 30d ROI, but A has aligned 7d/1d, B has divergent
    a = {"roi_30d": 0.20, "roi_7d": 0.05, "roi_1d": 0.007, "equity": 50_000}
    b = {"roi_30d": 0.20, "roi_7d": 0.19, "roi_1d": 0.001, "equity": 50_000}
    assert consistency_score(a) > consistency_score(b)


def test_consistency_score_prefers_bigger_equity():
    small = {"roi_30d": 0.20, "roi_7d": 0.05, "roi_1d": 0.007, "equity": 10_000}
    big = {"roi_30d": 0.20, "roi_7d": 0.05, "roi_1d": 0.007, "equity": 1_000_000}
    assert consistency_score(big) > consistency_score(small)


def test_select_ranks_by_score_not_pure_roi():
    # Trader A: higher ROI but inconsistent
    # Trader B: lower ROI but very consistent
    a = _row("0xA", 50_000, 0.60)
    a["roi_7d"] = 0.55  # huge divergence
    a["roi_1d"] = -0.01
    b = _row("0xB", 50_000, 0.30)
    b["roi_7d"] = 0.075  # aligned: 7d * 30/7 ≈ 0.32 ≈ 0.30
    b["roi_1d"] = 0.010  # aligned: 1d * 30 = 0.30
    selected = select_top_traders([a, b], max_traders=10)
    assert selected[0]["address"] == "0xB"
