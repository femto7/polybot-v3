from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from polybot_v3.bot_state import is_paused
from polybot_v3.consensus import consensus_pnl_ratio
from polybot_v3.config import (
    CONSENSUS_PAUSE_THRESHOLD,
    LEADERBOARD_CYCLE_SECONDS,
    MAX_TRADERS,
    MONITOR_CYCLE_SECONDS,
    STOP_LOSS_PCT,
    TRAIL_ACTIVATION_PCT,
    TRAIL_STOP_PCT,
)
from polybot_v3.hyperliquid_client import HyperliquidClient
from polybot_v3.leaderboard import select_top_traders
from polybot_v3.realtime import RealtimeMonitor
from polybot_v3.replicator import TargetPosition, compute_target_portfolio
from polybot_v3.telegram import send_message
from polybot_v3.tracker import Position, Tracker
from polybot_v3.trader_monitor import snapshot_trader_positions
from polybot_v3.trailing import should_trail_close, update_peak

log = logging.getLogger(__name__)


def refresh_leaderboard(client: HyperliquidClient, tracker: Tracker) -> list[dict]:
    rows = client.fetch_leaderboard()
    top = select_top_traders(rows, max_traders=MAX_TRADERS)
    tracker.save_traders(top)
    log.info("Leaderboard refreshed: %d traders", len(top))
    send_message(f"📋 Leaderboard updated: {len(top)} traders tracked")
    return top


def poll_trader_snapshots(client: HyperliquidClient, traders: list[dict]) -> dict:
    """Fetch all traders' positions concurrently using a thread pool."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    snapshots: dict = {}

    def _one(addr: str):
        state = client.fetch_user_positions(addr)
        return addr, {
            "equity": state.equity,
            "positions": snapshot_trader_positions(state),
        }

    with ThreadPoolExecutor(max_workers=min(10, max(1, len(traders)))) as ex:
        futures = {ex.submit(_one, t["address"]): t["address"] for t in traders}
        for fut in as_completed(futures):
            addr = futures[fut]
            try:
                addr2, snap = fut.result()
                snapshots[addr2] = snap
            except Exception:
                log.warning("Failed to fetch positions for %s", addr, exc_info=True)
    return snapshots


def reconcile_positions(
    tracker: Tracker,
    targets: dict[str, TargetPosition],
    prices: dict[str, float],
    open_new: bool = True,
    executor=None,
) -> None:
    current = tracker.load_positions()

    # Close positions no longer in target (or sides flipped)
    for asset in list(current.keys()):
        target = targets.get(asset)
        if target is None or target.side != current[asset].side:
            px = prices.get(asset, current[asset].entry_price)
            if executor is not None:
                try:
                    executor.market_close(asset)
                except Exception:
                    log.error("LIVE close failed for %s", asset, exc_info=True)
                    continue
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

    # Open new positions or resize (unless skipped by consensus pause)
    if not open_new:
        return
    current = tracker.load_positions()
    for asset, target in targets.items():
        px = prices.get(asset)
        if px is None:
            continue
        size = target.notional / px
        if asset in current and current[asset].side == target.side:
            existing = current[asset]
            delta = abs(existing.notional - target.notional) / max(existing.notional, 1.0)
            if delta < 0.25:  # Don't churn on < 25% sizing changes
                continue

        if executor is not None:
            try:
                # If resizing (same side), close first then reopen at new size
                if asset in current and current[asset].side == target.side:
                    executor.market_close(asset)
                executor.market_open(asset, target.side, size)
            except Exception:
                log.error("LIVE open failed for %s", asset, exc_info=True)
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


def run_monitor_cycle(client: HyperliquidClient, tracker: Tracker, executor=None) -> None:
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

    # Consensus drawdown: if all traders collectively losing, pause new entries
    consensus = consensus_pnl_ratio(snapshots, prices)
    if consensus < CONSENSUS_PAUSE_THRESHOLD:
        log.warning("CONSENSUS DRAWDOWN %.2f%% — skipping new entries this cycle",
                    consensus * 100)
        send_message(
            f"⚠️ Consensus drawdown {consensus*100:+.1f}% — "
            f"holding fire (traders losing collectively)"
        )
        # Still check existing positions for stops, just don't open new
        reconcile_positions(tracker, {}, prices, open_new=False, executor=executor)
        tracker.record_bankroll_snapshot(prices)
        return

    # Compound: size positions based on current equity (realized + unrealized)
    # so winnings are reinvested automatically
    equity = tracker.equity(prices)
    trader_weights = {t["address"]: t.get("score", 1.0) for t in traders}
    targets = compute_target_portfolio(
        snapshots,
        our_bankroll=equity,
        max_traders=MAX_TRADERS,
        trader_weights=trader_weights,
    )

    reconcile_positions(tracker, targets, prices, executor=executor)
    tracker.record_bankroll_snapshot(prices)


def run_loop(use_websocket: bool = True, live: bool = False) -> None:
    client = HyperliquidClient()
    tracker = Tracker()
    executor = None
    if live:
        from polybot_v3.executor import LiveExecutor
        executor = LiveExecutor()
        log.warning("LIVE MODE ACTIVE — real orders will be placed")
        send_message("⚡ Polybot v3 LIVE MODE ACTIVE — real orders!")
    else:
        log.info("Polybot v3 started (paper mode, ws=%s)", use_websocket)
        send_message(f"🚀 Polybot v3 started (paper, ws={'on' if use_websocket else 'off'})")

    # Wake event fired by WS on a trader's fill → triggers immediate reconcile
    wake_event = threading.Event()
    rt = None
    if use_websocket:
        def on_fill(addr: str, msg: dict):
            log.info("WS fill received for %s — waking cycle", addr[:10])
            wake_event.set()
        try:
            rt = RealtimeMonitor(on_fill=on_fill)
            rt.start()
        except Exception:
            log.warning("WebSocket failed to start, falling back to polling only",
                         exc_info=True)
            rt = None

    last_leaderboard = 0.0
    while True:
        try:
            now = time.time()
            if now - last_leaderboard >= LEADERBOARD_CYCLE_SECONDS:
                refresh_leaderboard(client, tracker)
                last_leaderboard = now
                if rt is not None:
                    rt.sync_subscriptions([t["address"] for t in tracker.load_traders()])

            run_monitor_cycle(client, tracker, executor=executor)
        except Exception:
            log.error("Cycle failed", exc_info=True)
            send_message("⚠️ Cycle failed — check logs")

        # Sleep but wake early if WS signals a fill
        wake_event.wait(timeout=MONITOR_CYCLE_SECONDS)
        wake_event.clear()
