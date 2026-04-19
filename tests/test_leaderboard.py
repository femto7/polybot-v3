from __future__ import annotations

from polybot_v3.leaderboard import select_top_traders


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
