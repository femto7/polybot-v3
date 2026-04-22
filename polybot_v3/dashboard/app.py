from __future__ import annotations

import csv
import io
import logging
from dataclasses import asdict

from flask import Flask, Response, jsonify, render_template, request

from polybot_v3.bot_state import is_paused, set_paused
from polybot_v3.hyperliquid_client import HyperliquidClient
from polybot_v3.tracker import Tracker

log = logging.getLogger(__name__)


def create_app(
    tracker: Tracker | None = None,
    client: HyperliquidClient | None = None,
) -> Flask:
    app = Flask(__name__)
    _tracker = tracker or Tracker()
    _client = client

    def _prices():
        if _client is None:
            return {}
        try:
            return _client.fetch_mids()
        except Exception:
            log.warning("Failed to fetch mids", exc_info=True)
            return {}

    def _stats():
        prices = _prices()
        positions = list(_tracker.load_positions().values())
        trades = _tracker.load_trades()
        traders = _tracker.load_traders()
        history = _tracker.load_bankroll_history()
        bankroll = _tracker.bankroll()
        unrealized = _tracker.unrealized_pnl(prices)
        equity = bankroll + unrealized

        wins = [t for t in trades if t.realized_pnl > 0]
        losses = [t for t in trades if t.realized_pnl <= 0]
        winrate = (len(wins) / len(trades) * 100) if trades else 0.0
        realized = sum(t.realized_pnl for t in trades)

        pos_list = []
        for p in positions:
            px = prices.get(p.asset, p.entry_price)
            side_sign = 1 if p.side == "LONG" else -1
            upnl = p.size * (px - p.entry_price) * side_sign
            pnl_pct = ((px - p.entry_price) / p.entry_price * 100 * side_sign) if p.entry_price else 0
            pos_list.append({
                **asdict(p),
                "current_price": px,
                "unrealized_pnl": round(upnl, 2),
                "unrealized_pct": round(pnl_pct, 2),
            })
        pos_list.sort(key=lambda p: -abs(p["unrealized_pnl"]))

        trader_stats = []
        for t in traders:
            attrib_pnl = 0.0
            attrib_count = 0
            wins = 0
            losses = 0
            for trade in trades:
                if t["address"] in trade.source_traders:
                    p = trade.realized_pnl / len(trade.source_traders)
                    attrib_pnl += p
                    attrib_count += 1
                    if p > 0:
                        wins += 1
                    else:
                        losses += 1
            open_contrib = 0.0
            for p in positions:
                if t["address"] in p.source_traders:
                    open_contrib += p.notional / len(p.source_traders)
            wr = (wins / max(wins + losses, 1)) * 100 if attrib_count else 0
            trader_stats.append({
                **t,
                "attrib_pnl": round(attrib_pnl, 2),
                "attrib_trades": attrib_count,
                "attrib_wins": wins,
                "attrib_losses": losses,
                "attrib_winrate": round(wr, 1),
                "open_contribution": round(open_contrib, 2),
            })
        # Rank: best P&L traders first
        trader_stats.sort(key=lambda x: -x["attrib_pnl"])

        # Best/worst asset by realized PnL
        asset_pnl = {}
        for t in trades:
            asset_pnl[t.asset] = asset_pnl.get(t.asset, 0) + t.realized_pnl
        best_asset = max(asset_pnl.items(), key=lambda x: x[1]) if asset_pnl else ("-", 0)
        worst_asset = min(asset_pnl.items(), key=lambda x: x[1]) if asset_pnl else ("-", 0)

        # Max drawdown from history
        max_dd = 0.0
        if history:
            peak = history[0]["equity"]
            for h in history:
                if h["equity"] > peak:
                    peak = h["equity"]
                dd = (peak - h["equity"]) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)

        avg_pnl = (realized / len(trades)) if trades else 0.0

        cum_funding = _tracker.cumulative_funding() if hasattr(_tracker, "cumulative_funding") else 0.0
        cum_fees = _tracker.cumulative_fees() if hasattr(_tracker, "cumulative_fees") else 0.0
        try:
            from polybot_v3.trader_intel import load_blacklist
            blacklist_count = len(load_blacklist())
        except Exception:
            blacklist_count = 0

        return {
            "bankroll": round(bankroll, 2),
            "equity": round(equity, 2),
            "unrealized_pnl": round(unrealized, 2),
            "realized_pnl": round(realized, 2),
            "cum_funding": round(cum_funding, 2),
            "cum_fees": round(cum_fees, 2),
            "blacklisted_count": blacklist_count,
            "initial": _tracker._initial_bankroll,
            "pct_change": round(
                (equity - _tracker._initial_bankroll) / _tracker._initial_bankroll * 100, 2
            ),
            "open_count": len(positions),
            "closed_count": len(trades),
            "winrate": round(winrate, 1),
            "wins": len(wins),
            "losses": len(losses),
            "total_exposure": round(sum(p.notional for p in positions), 2),
            "max_drawdown": round(max_dd * 100, 2),
            "avg_pnl": round(avg_pnl, 2),
            "best_asset": {"name": best_asset[0], "pnl": round(best_asset[1], 2)},
            "worst_asset": {"name": worst_asset[0], "pnl": round(worst_asset[1], 2)},
            "positions": pos_list,
            "trades": [asdict(t) for t in trades[-100:][::-1]],
            "traders": trader_stats,
            "history": history[-1000:],
            "paused": is_paused(),
        }

    @app.route("/")
    def index():
        return render_template("index.html", data=_stats())

    @app.route("/positions")
    def positions():
        return render_template("positions.html", data=_stats())

    @app.route("/trades")
    def trades():
        return render_template("trades.html", data=_stats())

    @app.route("/traders")
    def traders():
        return render_template("traders.html", data=_stats())

    @app.route("/analytics")
    def analytics():
        return render_template("analytics.html", data=_stats())

    @app.route("/api/data")
    def api_data():
        return jsonify(_stats())

    @app.route("/api/trades.csv")
    def trades_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "asset", "side", "size", "entry", "exit", "pnl",
            "source_traders", "opened", "closed",
        ])
        for t in _tracker.load_trades():
            writer.writerow([
                t.asset, t.side, t.size, t.entry_price, t.exit_price,
                t.realized_pnl, ",".join(t.source_traders),
                t.opened_at, t.closed_at,
            ])
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=trades.csv"},
        )

    @app.route("/api/positions.csv")
    def positions_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "asset", "side", "size", "entry", "notional", "source_traders", "opened",
        ])
        for p in _tracker.load_positions().values():
            writer.writerow([
                p.asset, p.side, p.size, p.entry_price, p.notional,
                ",".join(p.source_traders), p.opened_at,
            ])
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=positions.csv"},
        )

    @app.route("/api/pause", methods=["POST"])
    def api_pause():
        set_paused(True)
        return jsonify({"paused": True})

    @app.route("/api/resume", methods=["POST"])
    def api_resume():
        set_paused(False)
        return jsonify({"paused": False})

    @app.route("/api/remove-trader/<address>", methods=["POST"])
    def api_remove_trader(address):
        traders = _tracker.load_traders()
        traders = [t for t in traders if t.get("address") != address]
        _tracker.save_traders(traders)
        return jsonify({"removed": address})

    return app


def run_dashboard(port: int = 5001) -> None:
    client = HyperliquidClient()
    app = create_app(client=client)
    app.run(host="127.0.0.1", port=port, debug=False)
