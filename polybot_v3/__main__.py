"""CLI entry point: python -m polybot_v3"""

from __future__ import annotations

import argparse
import logging
import sys

from polybot_v3.config import DASHBOARD_PORT
from polybot_v3.tracker import Tracker


def _status() -> None:
    tracker = Tracker()
    positions = tracker.load_positions()
    trades = tracker.load_trades()
    traders = tracker.load_traders()
    bankroll = tracker.bankroll()
    realized = sum(t.realized_pnl for t in trades)
    wins = sum(1 for t in trades if t.realized_pnl > 0)
    losses = sum(1 for t in trades if t.realized_pnl <= 0)

    print(f"Bankroll: ${bankroll:.2f} (initial ${tracker._initial_bankroll:.2f})")
    print(f"Open positions: {len(positions)}")
    print(f"Closed trades: {len(trades)} ({wins}W/{losses}L, "
          f"P&L ${realized:+.2f})")
    print(f"Tracked traders: {len(traders)}")

    if positions:
        print("\nOpen positions:")
        for p in positions.values():
            print(f"  {p.side:5s} {p.asset:6s} size={p.size:.4f} "
                  f"entry={p.entry_price:.4f} notional=${p.notional:.2f}")

    if traders:
        print("\nTracked traders:")
        for t in traders[:5]:
            print(f"  {t['address'][:14]}... roi30d={t['roi_30d']*100:+.1f}% "
                  f"equity=${t['equity']:,.0f}")
        if len(traders) > 5:
            print(f"  ... and {len(traders) - 5} more")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Polybot v3 — Hyperliquid copy trading"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show current state")
    run_parser = sub.add_parser("run", help="Start the bot loop")
    run_parser.add_argument("--live", action="store_true",
                             help="LIVE mode — real orders (requires HYPERLIQUID_PRIVATE_KEY)")
    run_parser.add_argument("--no-ws", action="store_true",
                             help="Disable WebSocket (polling only)")

    dash = sub.add_parser("dashboard", help="Launch web dashboard")
    dash.add_argument("--port", type=int, default=DASHBOARD_PORT)

    args = parser.parse_args()

    if args.command == "status":
        _status()
        return 0
    if args.command == "run":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        from polybot_v3.loop import run_loop
        run_loop(use_websocket=not args.no_ws, live=args.live)
        return 0
    if args.command == "dashboard":
        logging.basicConfig(level=logging.INFO)
        from polybot_v3.dashboard.app import run_dashboard
        print(f"Dashboard: http://127.0.0.1:{args.port}")
        run_dashboard(port=args.port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
