from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from hyperliquid.info import Info

from polybot_v3.config import HYPERLIQUID_INFO_URL, HYPERLIQUID_LEADERBOARD_URL

log = logging.getLogger(__name__)


@dataclass
class TraderPosition:
    asset: str
    size: float
    side: str
    entry_price: float
    leverage: float
    unrealized_pnl: float


@dataclass
class UserState:
    equity: float
    positions: list[TraderPosition]


class HyperliquidClient:
    def __init__(self) -> None:
        self._info = Info(HYPERLIQUID_INFO_URL, skip_ws=True)

    def fetch_user_positions(self, address: str) -> UserState:
        data = self._info.user_state(address)
        equity = float(data.get("marginSummary", {}).get("accountValue", 0))
        positions = []
        for p in data.get("assetPositions", []):
            pos = p.get("position", {})
            size_raw = float(pos.get("szi", 0))
            if size_raw == 0:
                continue
            side = "LONG" if size_raw > 0 else "SHORT"
            lev = pos.get("leverage", {}).get("value", 1)
            positions.append(TraderPosition(
                asset=pos.get("coin", ""),
                size=abs(size_raw),
                side=side,
                entry_price=float(pos.get("entryPx", 0)),
                leverage=float(lev),
                unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
            ))
        return UserState(equity=equity, positions=positions)

    def fetch_mids(self) -> dict[str, float]:
        raw = self._info.all_mids()
        return {k: float(v) for k, v in raw.items()}

    def fetch_leaderboard(self) -> list[dict]:
        """Return simplified leaderboard rows with essential metrics."""
        resp = httpx.get(HYPERLIQUID_LEADERBOARD_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        rows = []
        for row in data.get("leaderboardRows", []):
            perfs = {k: v for k, v in row.get("windowPerformances", [])}
            month = perfs.get("month", {})
            week = perfs.get("week", {})
            day = perfs.get("day", {})
            rows.append({
                "address": row.get("ethAddress", ""),
                "equity": float(row.get("accountValue", 0)),
                "roi_30d": float(month.get("roi", 0)),
                "pnl_30d": float(month.get("pnl", 0)),
                "vlm_30d": float(month.get("vlm", 0)),
                "roi_7d": float(week.get("roi", 0)),
                "roi_1d": float(day.get("roi", 0)),
            })
        return rows
