from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from polybot_v3.config import (
    BANKROLL_HISTORY_FILE,
    BANKROLL_INITIAL,
    POSITIONS_FILE,
    TRADER_STATES_FILE,
    TRADERS_FILE,
    TRADES_FILE,
)


@dataclass
class Position:
    asset: str
    side: str  # "LONG" or "SHORT"
    size: float
    entry_price: float
    notional: float
    source_traders: list[str]
    opened_at: str


@dataclass
class Trade:
    asset: str
    side: str
    size: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    source_traders: list[str]
    opened_at: str
    closed_at: str


class Tracker:
    def __init__(
        self,
        positions: Path = POSITIONS_FILE,
        trades: Path = TRADES_FILE,
        traders: Path = TRADERS_FILE,
        trader_states: Path = TRADER_STATES_FILE,
        bankroll_history: Path = BANKROLL_HISTORY_FILE,
        initial_bankroll: float = BANKROLL_INITIAL,
    ):
        self._positions_file = Path(positions)
        self._trades_file = Path(trades)
        self._traders_file = Path(traders)
        self._trader_states_file = Path(trader_states)
        self._bankroll_history_file = Path(bankroll_history)
        self._initial_bankroll = initial_bankroll
        self._positions_file.parent.mkdir(parents=True, exist_ok=True)

    def load_positions(self) -> dict[str, Position]:
        if not self._positions_file.exists():
            return {}
        raw = json.loads(self._positions_file.read_text())
        return {k: Position(**v) for k, v in raw.items()}

    def save_positions(self, positions: dict[str, Position]) -> None:
        self._positions_file.write_text(
            json.dumps({k: asdict(v) for k, v in positions.items()}, indent=2)
        )

    def upsert_position(self, position: Position) -> None:
        positions = self.load_positions()
        positions[position.asset] = position
        self.save_positions(positions)

    def close_position(self, asset: str, exit_price: float) -> Trade | None:
        positions = self.load_positions()
        pos = positions.pop(asset, None)
        if pos is None:
            return None
        side_sign = 1 if pos.side == "LONG" else -1
        realized_pnl = pos.size * (exit_price - pos.entry_price) * side_sign
        trade = Trade(
            asset=pos.asset,
            side=pos.side,
            size=pos.size,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            realized_pnl=realized_pnl,
            source_traders=pos.source_traders,
            opened_at=pos.opened_at,
            closed_at=datetime.now(timezone.utc).isoformat(),
        )
        self.save_positions(positions)
        trades = self.load_trades()
        trades.append(trade)
        self.save_trades(trades)
        return trade

    def load_trades(self) -> list[Trade]:
        if not self._trades_file.exists():
            return []
        return [Trade(**t) for t in json.loads(self._trades_file.read_text())]

    def save_trades(self, trades: list[Trade]) -> None:
        self._trades_file.write_text(
            json.dumps([asdict(t) for t in trades], indent=2)
        )

    def bankroll(self) -> float:
        trades = self.load_trades()
        realized = sum(t.realized_pnl for t in trades)
        return self._initial_bankroll + realized

    def unrealized_pnl(self, prices: dict[str, float]) -> float:
        positions = self.load_positions()
        total = 0.0
        for asset, pos in positions.items():
            px = prices.get(asset)
            if px is None:
                continue
            side_sign = 1 if pos.side == "LONG" else -1
            total += pos.size * (px - pos.entry_price) * side_sign
        return total

    def equity(self, prices: dict[str, float]) -> float:
        return self.bankroll() + self.unrealized_pnl(prices)

    def committed_capital(self) -> float:
        positions = self.load_positions()
        return sum(p.notional for p in positions.values())

    def available_cash(self, prices: dict[str, float]) -> float:
        return self.equity(prices) - self.committed_capital()

    def record_bankroll_snapshot(self, current_prices: dict[str, float]) -> None:
        history = self.load_bankroll_history()
        history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bankroll": round(self.bankroll(), 2),
            "equity": round(self.equity(current_prices), 2),
            "unrealized": round(self.unrealized_pnl(current_prices), 2),
            "open_count": len(self.load_positions()),
        })
        history = history[-5000:]
        self._bankroll_history_file.parent.mkdir(parents=True, exist_ok=True)
        self._bankroll_history_file.write_text(json.dumps(history, indent=2))

    def load_bankroll_history(self) -> list[dict]:
        if not self._bankroll_history_file.exists():
            return []
        return json.loads(self._bankroll_history_file.read_text())

    def load_traders(self) -> list[dict]:
        if not self._traders_file.exists():
            return []
        return json.loads(self._traders_file.read_text())

    def save_traders(self, traders: list[dict]) -> None:
        self._traders_file.write_text(json.dumps(traders, indent=2))

    def load_trader_states(self) -> dict:
        if not self._trader_states_file.exists():
            return {}
        return json.loads(self._trader_states_file.read_text())

    def save_trader_states(self, states: dict) -> None:
        self._trader_states_file.write_text(json.dumps(states, indent=2))
