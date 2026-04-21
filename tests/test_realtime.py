from __future__ import annotations

from unittest.mock import MagicMock

from polybot_v3.realtime import RealtimeMonitor


def test_sync_subscriptions_adds_new():
    rm = RealtimeMonitor(on_fill=lambda *a: None)
    rm._info = MagicMock()
    rm._info.subscribe = MagicMock(return_value=42)
    rm.sync_subscriptions(["0xA", "0xB"])
    assert "0xA" in rm._subscriptions
    assert "0xB" in rm._subscriptions
    assert rm._info.subscribe.call_count == 2


def test_sync_subscriptions_removes_gone():
    rm = RealtimeMonitor(on_fill=lambda *a: None)
    rm._info = MagicMock()
    rm._info.subscribe = MagicMock(return_value=42)
    rm._info.unsubscribe = MagicMock(return_value=True)
    rm.sync_subscriptions(["0xA", "0xB"])
    rm.sync_subscriptions(["0xA"])  # 0xB should be unsubscribed
    assert "0xA" in rm._subscriptions
    assert "0xB" not in rm._subscriptions


def test_on_fill_callback_fires():
    calls = []
    rm = RealtimeMonitor(on_fill=lambda addr, msg: calls.append((addr, msg)))
    rm._info = MagicMock()
    rm._handle("0xA", {"fill": "data"})
    assert calls == [("0xA", {"fill": "data"})]
