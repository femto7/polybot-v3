from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from polybot_v3.bot_state import is_paused
from polybot_v3.config import (
    LEADERBOARD_CYCLE_SECONDS,
    MAX_TRADERS,
    MONITOR_CYCLE_SECONDS,
    STOP_LOSS_PCT,
)
from polybot_v3.hyperliquid_client import HyperliquidClient
from polybot_v3.leaderboard import select_top_traders
from polybot_v3.replicator import TargetPosition, compute_target_portfolio
from polybot_v3.telegram import send_message
from polybot_v3.tracker import Position, Tracker
from polybot_v3.trader_monitor import snapshot_trader_positions

log = logging.getLogger(__name__)


def refresh_leaderboard(client: HyperliquidClient, tracker: Tracker) -> list[dict]:
    rows = client.fetch_leaderboard()
    top = select_top_traders(rows, max_traders=MAX_TRADERS)
    tracker.save_traders(top)
    log.info("Leaderboard refreshed: %d traders", len(top))
    send_message(f"📋 Leaderboard updated: {len(top)} traders tracked")
    return top


def poll_trader_snapshots(client: HyperliquidClient, traders: list[dict]) -> dict:
    snapshots = {}
    for t in traders:
        addr = t["address"]
        try:
            state = client.fetch_user_positions(addr)
            snapshots[addr] = {
                "equity": state.equity,
                "positions": snapshot_trader_positions(state),
            }
        except Exception:
            log.warning("Failed to fetch positions for %s", addr, exc_info=True)
    return snapshots


def reconcile_positions(
    tracker: Tracker,
    targets: dict[str, TargetPosition],
    prices: dict[str, float],
) -> None:
    current = tracker.load_positions()

    # Close positions no longer in target (or sides flipped)
    for asset in list(current.keys()):
        target = targets.get(asset)
        if target is None or target.side != current[asset].side:
            px = prices.get(asset, current[asset].entry_price)
            trade = tracker.close_position(asset, exit_price=px)
            if trade:
                emoji = "✅" if trade.realized_pnl >= 0 else "❌"
                send_message(
                    f"{emoji} CLOSED {asset} {trade.side} "
                    f"PnL ${trade.realized_pnl:+.2f}"
                )

    # Stop-loss + trailing stop check on remaining positions
    current = tracker.load_positions()
    for asset, pos in list(current.items()):
        px = prices.get(asset)
        if px is None:
            continue
        side_sign = 1 if pos.side == "LONG" else -1
        pnl_pct = (px - pos.entry_price) / pos.entry_price * side_sign

        # Hard stop-loss
        if pnl_pct <= -STOP_LOSS_PCT:
            trade = tracker.close_position(asset, exit_price=px)
            if trade:
                send_message(
                    f"🛑 STOP-LOSS {asset} {trade.side} "
                    f"PnL ${trade.realized_pnl:+.2f}"
                )
            continue

        # Trailing stop — update peak then check retrace
        pos = update_peak(pos, px)
        tracker.upsert_position(pos)
        if should_trail_close(pos, px, trail_pct=TRAIL_STOP_PCT,
                               activation_pct=TRAIL_ACTIVATION_PCT):
            trade = tracker.close_position(asset, exit_price=px)
            if trade:
                send_message(
                    f"🎯 TRAIL-STOP {asset} {trade.side} "
                    f"PnL ${trade.realized_pnl:+.2f}"
                )

    # Open new positions or resize
    current = tracker.load_positions()
    for asset, target in targets.items():
        px = prices.get(asset)
        if px is None:
            continue
        size = target.notional / px
        if asset in current and current[asset].side == target.side:
            existing = current[asset]
            delta = abs(existing.notional - target.notional) / max(existing.notional, 1.0)
            if delta < 0.10:
                continue
        pos = Position(
            asset=asset,
            side=target.side,
            size=size,
            entry_price=px,
            notional=target.notional,
            source_traders=target.source_traders,
            opened_at=datetime.now(timezone.utc).isoformat(),
        )
        was_open = asset in current
        tracker.upsert_position(pos)
        action = "RESIZED" if was_open else "OPENED"
        send_message(
            f"📝 {action} {asset} {target.side} "
            f"${target.notional:.2f} @ {px:.4f}"
        )


def run_monitor_cycle(client: HyperliquidClient, tracker: Tracker) -> None:
    if is_paused():
        log.info("Bot paused, skipping monitor cycle")
        return

    traders = tracker.load_traders()
    if not traders:
        log.warning("No traders tracked — running leaderboard refresh first")
        traders = refresh_leaderboard(client, tracker)
        if not traders:
            return

    snapshots = poll_trader_snapshots(client, traders)
    prices = client.fetch_mids()

    targets = compute_target_portfolio(
        snapshots,
        our_bankroll=tracker.bankroll(),
        max_traders=MAX_TRADERS,
    )

    reconcile_positions(tracker, targets, prices)
    tracker.record_bankroll_snapshot(prices)


def run_loop() -> None:
    client = HyperliquidClient()
    tracker = Tracker()
    log.info("Polybot v3 started (paper mode)")
    send_message("🚀 Polybot v3 started (paper copy trading)")

    last_leaderboard = 0.0
    while True:
        try:
            now = time.time()
            if now - last_leaderboard >= LEADERBOARD_CYCLE_SECONDS:
                refresh_leaderboard(client, tracker)
                last_leaderboard = now

            run_monitor_cycle(client, tracker)
        except Exception:
            log.error("Cycle failed", exc_info=True)
            send_message("⚠️ Cycle failed — check logs")

        time.sleep(MONITOR_CYCLE_SECONDS)
