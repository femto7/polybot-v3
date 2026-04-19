from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from polybot_v3.hyperliquid_client import HyperliquidClient


def test_fetch_user_positions_parses_response():
    fake_response = {
        "marginSummary": {"accountValue": "50000.5"},
        "assetPositions": [
            {
                "position": {
                    "coin": "BTC",
                    "szi": "0.5",
                    "entryPx": "95000",
                    "leverage": {"value": 10},
                    "unrealizedPnl": "1250.0",
                }
            },
            {
                "position": {
                    "coin": "ETH",
                    "szi": "-10.0",
                    "entryPx": "3500",
                    "leverage": {"value": 5},
                    "unrealizedPnl": "-300.0",
                }
            },
        ],
    }
    mock_info = MagicMock()
    mock_info.user_state = MagicMock(return_value=fake_response)

    client = HyperliquidClient.__new__(HyperliquidClient)
    client._info = mock_info

    result = client.fetch_user_positions("0xtest")
    assert result.equity == pytest.approx(50000.5)
    assert len(result.positions) == 2
    btc = result.positions[0]
    assert btc.asset == "BTC"
    assert btc.size == pytest.approx(0.5)
    assert btc.side == "LONG"
    assert btc.entry_price == pytest.approx(95000)
    eth = result.positions[1]
    assert eth.side == "SHORT"
    assert eth.size == pytest.approx(10.0)


def test_fetch_user_positions_skips_zero_size():
    fake_response = {
        "marginSummary": {"accountValue": "10000"},
        "assetPositions": [
            {"position": {"coin": "BTC", "szi": "0", "entryPx": "0",
                          "leverage": {"value": 1}, "unrealizedPnl": "0"}},
            {"position": {"coin": "ETH", "szi": "1.0", "entryPx": "3500",
                          "leverage": {"value": 1}, "unrealizedPnl": "0"}},
        ],
    }
    mock_info = MagicMock()
    mock_info.user_state = MagicMock(return_value=fake_response)
    client = HyperliquidClient.__new__(HyperliquidClient)
    client._info = mock_info

    result = client.fetch_user_positions("0xtest")
    assert len(result.positions) == 1
    assert result.positions[0].asset == "ETH"


def test_fetch_mids_returns_float_dict():
    mock_info = MagicMock()
    mock_info.all_mids = MagicMock(return_value={"BTC": "95000.5", "ETH": "3500.0"})

    client = HyperliquidClient.__new__(HyperliquidClient)
    client._info = mock_info

    mids = client.fetch_mids()
    assert mids["BTC"] == pytest.approx(95000.5)
    assert mids["ETH"] == pytest.approx(3500.0)


def test_fetch_leaderboard_parses_rows(monkeypatch):
    fake_data = {
        "leaderboardRows": [
            {
                "ethAddress": "0xabc",
                "accountValue": "50000",
                "windowPerformances": [
                    ["day", {"pnl": "100", "roi": "0.002", "vlm": "10000"}],
                    ["week", {"pnl": "800", "roi": "0.016", "vlm": "60000"}],
                    ["month", {"pnl": "10000", "roi": "0.20", "vlm": "300000"}],
                ],
            },
        ]
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=fake_data)
    monkeypatch.setattr("polybot_v3.hyperliquid_client.httpx.get",
                        MagicMock(return_value=mock_resp))

    client = HyperliquidClient.__new__(HyperliquidClient)
    client._info = MagicMock()
    rows = client.fetch_leaderboard()
    assert len(rows) == 1
    assert rows[0]["address"] == "0xabc"
    assert rows[0]["equity"] == pytest.approx(50000)
    assert rows[0]["roi_30d"] == pytest.approx(0.20)
    assert rows[0]["pnl_30d"] == pytest.approx(10000)
    assert rows[0]["vlm_30d"] == pytest.approx(300000)
