from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from polybot_v3.bot_state import is_paused
from polybot_v3.consensus import consensus_pnl_ratio
from polybot_v3.config import (
    CONSENSUS_PAUSE_THRESHOLD,
    FUNDING_INTERVAL_HOURS,
    LEADERBOARD_CYCLE_SECONDS,
    MAX_TRADERS,
    MONITOR_CYCLE_SECONDS,
    STOP_LOSS_PCT,
    TRAIL_ACTIVATION_PCT,
    TRAIL_STOP_PCT,
)
from polybot_v3.costs import (
    apply_slippage_to_entry,
    apply_slippage_to_exit,
    entry_cost,
    exit_cost,
    fetch_funding_rates,
    funding_payment,
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
            raw_px = prices.get(asset, current[asset].entry_price)
            px = apply_slippage_to_exit(raw_px, current[asset].side)
            if executor is not None:
                try:
                    executor.market_close(asset)
                except Exception:
                    log.error("LIVE close failed for %s", asset, exc_info=True)
                    continue
            # Charge exit fee
            tracker.add_cash_adjustment(fees=-exit_cost(current[asset].notional))
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
        raw_px = prices.get(asset)
        if raw_px is None:
            continue
        # Apply entry slippage
        px = apply_slippage_to_entry(raw_px, target.side)
        size = target.notional / px
        if asset in current and current[asset].side == target.side:
            existing = current[asset]
            delta = abs(existing.notional - target.notional) / max(existing.notional, 1.0)
            if delta < 0.25:  # Don't churn on < 25% sizing changes
                continue
        # Charge entry fee on new/resized portion
        if asset in current and current[asset].side == target.side:
            fee_notional = abs(target.notional - current[asset].notional)
        else:
            fee_notional = target.notional
        tracker.add_cash_adjustment(fees=-entry_cost(fee_notional))

        if executor is not None:
            try:
                # If resizing (same side), close first then reopen at new size
                if asset in current and current[asset].side == target.side:
                    executor.market_close(asset)
                executor.market_open(asset, target.side, size)
            except Exception:
                log.error("LIVE open failed for %s", asset, exc_info=True)
                continue

        # On same-side resize: preserve entry_price (weighted avg if scaling up)
        # so unrealized P&L reflects actual move from original entry, not resets to 0
        if asset in current and current[asset].side == target.side:
            existing = current[asset]
            if target.notional > existing.notional:
                # Scaling up: weighted average entry
                added_notional = target.notional - existing.notional
                added_size = added_notional / px
                new_size = existing.size + added_size
                weighted_entry = (
                    existing.size * existing.entry_price + added_size * px
                ) / new_size
                entry_price = weighted_entry
                size = new_size
                opened_at = existing.opened_at
                peak = existing.peak_price
            else:
                # Scaling down: keep original entry
                entry_price = existing.entry_price
                opened_at = existing.opened_at
                peak = existing.peak_price
        else:
            entry_price = px
            opened_at = datetime.now(timezone.utc).isoformat()
            peak = 0.0

        pos = Position(
            asset=asset,
            side=target.side,
            size=size,
            entry_price=entry_price,
            notional=target.notional,
            source_traders=target.source_traders,
            opened_at=opened_at,
            peak_price=peak,
        )
        was_open = asset in current
        tracker.upsert_position(pos)
        action = "RESIZED" if was_open else "OPENED"
        send_message(
            f"📝 {action} {asset} {target.side} "
            f"${target.notional:.2f} @ {px:.4f}"
        )


def accrue_funding(client: HyperliquidClient, tracker: Tracker) -> None:
    """Apply hourly funding payments to all open positions."""
    positions = tracker.load_positions()
    if not positions:
        return
    rates = fetch_funding_rates(client)
    if not rates:
        return
    total = 0.0
    for asset, pos in positions.items():
        rate = rates.get(asset)
        if rate is None:
            continue
        pnl = funding_payment(pos.side, pos.notional, rate)
        total += pnl
    if abs(total) > 0.01:
        tracker.add_cash_adjustment(funding=total)
        log.info("Funding accrued: $%+.2f across %d positions", total, len(positions))


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
    last_funding = 0.0
    while True:
        try:
            now = time.time()
            if now - last_leaderboard >= LEADERBOARD_CYCLE_SECONDS:
                refresh_leaderboard(client, tracker)
                last_leaderboard = now
                if rt is not None:
                    rt.sync_subscriptions([t["address"] for t in tracker.load_traders()])

            if now - last_funding >= FUNDING_INTERVAL_HOURS * 3600:
                accrue_funding(client, tracker)
                last_funding = now

            run_monitor_cycle(client, tracker, executor=executor)
        except Exception:
            log.error("Cycle failed", exc_info=True)
            send_message("⚠️ Cycle failed — check logs")

        # Sleep but wake early if WS signals a fill
        wake_event.wait(timeout=MONITOR_CYCLE_SECONDS)
        wake_event.clear()
