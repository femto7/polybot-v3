from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_tracker_files(tmp_path: Path):
    return {
        "positions": tmp_path / "positions.json",
        "trades": tmp_path / "trades.json",
        "traders": tmp_path / "traders.json",
        "trader_states": tmp_path / "trader_states.json",
        "bankroll_history": tmp_path / "bankroll_history.json",
    }
