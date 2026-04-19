from __future__ import annotations

import json

from polybot_v3.dashboard.app import create_app
from polybot_v3.tracker import Position, Tracker


def _tracker_with(tmp_path, with_data=False):
    t = Tracker(
        positions=tmp_path / "p.json",
        trades=tmp_path / "t.json",
        traders=tmp_path / "tr.json",
        trader_states=tmp_path / "ts.json",
        bankroll_history=tmp_path / "bh.json",
        initial_bankroll=500.0,
    )
    if with_data:
        t.upsert_position(Position(
            asset="BTC", side="LONG", size=0.001, entry_price=95000.0,
            notional=95.0, source_traders=["0xabc"],
            opened_at="2026-04-20T12:00:00Z",
        ))
        t.save_traders([{"address": "0xabc", "equity": 50000,
                         "roi_30d": 0.2, "pnl_30d": 10000,
                         "vlm_30d": 300000, "roi_7d": 0.05, "roi_1d": 0.007}])
    return t


def _mock_prices():
    class Client:
        def fetch_mids(self):
            return {"BTC": 100000.0}
    return Client()


def test_dashboard_index_200(tmp_path):
    tracker = _tracker_with(tmp_path)
    tracker.record_bankroll_snapshot({})
    app = create_app(tracker=tracker)
    client = app.test_client()
    assert client.get("/").status_code == 200


def test_dashboard_all_pages_200(tmp_path):
    tracker = _tracker_with(tmp_path, with_data=True)
    tracker.record_bankroll_snapshot({})
    app = create_app(tracker=tracker, client=_mock_prices())
    client = app.test_client()
    for path in ("/", "/positions", "/trades", "/traders", "/analytics"):
        assert client.get(path).status_code == 200, f"{path} failed"


def test_dashboard_api_data(tmp_path):
    tracker = _tracker_with(tmp_path)
    tracker.record_bankroll_snapshot({})
    app = create_app(tracker=tracker)
    client = app.test_client()
    resp = client.get("/api/data")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["bankroll"] == 500.0
    assert "positions" in data
    assert "trades" in data
    assert "traders" in data


def test_dashboard_pause_resume(tmp_path):
    import polybot_v3.bot_state as bot_state
    import polybot_v3.dashboard.app as app_module

    # Redirect bot_state file to tmp
    tmp_state = tmp_path / "bot_state.json"
    original = bot_state.BOT_STATE_FILE

    # Patch via monkey assignment
    bot_state.BOT_STATE_FILE = tmp_state

    tracker = _tracker_with(tmp_path)
    app = create_app(tracker=tracker)
    client = app.test_client()

    r = client.post("/api/pause")
    assert r.status_code == 200
    assert json.loads(r.data)["paused"] is True

    r = client.post("/api/resume")
    assert json.loads(r.data)["paused"] is False

    # Restore
    bot_state.BOT_STATE_FILE = original


def test_dashboard_trades_csv(tmp_path):
    tracker = _tracker_with(tmp_path)
    app = create_app(tracker=tracker)
    client = app.test_client()
    resp = client.get("/api/trades.csv")
    assert resp.status_code == 200
    assert "asset,side" in resp.data.decode()


def test_dashboard_positions_csv(tmp_path):
    tracker = _tracker_with(tmp_path, with_data=True)
    app = create_app(tracker=tracker)
    client = app.test_client()
    resp = client.get("/api/positions.csv")
    assert resp.status_code == 200
    assert "BTC" in resp.data.decode()


def test_dashboard_remove_trader(tmp_path):
    tracker = _tracker_with(tmp_path, with_data=True)
    app = create_app(tracker=tracker)
    client = app.test_client()
    resp = client.post("/api/remove-trader/0xabc")
    assert resp.status_code == 200
    assert tracker.load_traders() == []
