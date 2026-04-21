"""Real-time WebSocket listener for tracked traders' fills.

Subscribes to `userFills` for each trader. When a fill arrives, sets an event
flag so the main loop can wake up and reconcile within seconds instead of
waiting the 30s poll cycle.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from hyperliquid.info import Info

from polybot_v3.config import HYPERLIQUID_INFO_URL

log = logging.getLogger(__name__)


class RealtimeMonitor:
    """Subscribe to tracked traders' userFills; fire a callback on each fill."""

    def __init__(self, on_fill: Callable[[str, dict], None]):
        self._on_fill = on_fill
        self._info: Info | None = None
        self._subscriptions: dict[str, int] = {}  # address -> subscription id
        self._lock = threading.Lock()

    def start(self) -> None:
        # skip_ws=False → WebsocketManager started automatically
        self._info = Info(HYPERLIQUID_INFO_URL, skip_ws=False)
        log.info("Realtime WebSocket connected")

    def stop(self) -> None:
        if self._info is None:
            return
        with self._lock:
            for sub_id in self._subscriptions.values():
                try:
                    self._info.unsubscribe({"type": "userFills"}, sub_id)
                except Exception:
                    pass
            self._subscriptions.clear()
        self._info = None

    def subscribe_trader(self, address: str) -> None:
        if self._info is None:
            log.warning("Cannot subscribe — WS not started")
            return
        with self._lock:
            if address in self._subscriptions:
                return
            try:
                sub_id = self._info.subscribe(
                    {"type": "userFills", "user": address},
                    lambda msg, addr=address: self._handle(addr, msg),
                )
                self._subscriptions[address] = sub_id
                log.info("Subscribed to fills for %s", address[:10])
            except Exception:
                log.warning("Subscribe failed for %s", address, exc_info=True)

    def unsubscribe_trader(self, address: str) -> None:
        with self._lock:
            sub_id = self._subscriptions.pop(address, None)
        if sub_id is not None and self._info is not None:
            try:
                self._info.unsubscribe({"type": "userFills", "user": address}, sub_id)
            except Exception:
                pass

    def sync_subscriptions(self, tracked_addresses: list[str]) -> None:
        """Ensure subscriptions match the tracked list: add new, remove gone."""
        tracked_set = set(tracked_addresses)
        current = set(self._subscriptions.keys())
        for addr in tracked_set - current:
            self.subscribe_trader(addr)
        for addr in current - tracked_set:
            self.unsubscribe_trader(addr)

    def _handle(self, address: str, msg: dict) -> None:
        try:
            self._on_fill(address, msg)
        except Exception:
            log.warning("on_fill callback failed", exc_info=True)
