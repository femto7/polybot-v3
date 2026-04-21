"""Live order execution via Hyperliquid SDK Exchange class.

Requires:
- HYPERLIQUID_PRIVATE_KEY: wallet private key (API wallet recommended — not your main key)
- HYPERLIQUID_ACCOUNT_ADDRESS: your main account address (if using API wallet)

API wallet: generated at https://app.hyperliquid.xyz/API, cannot withdraw funds,
only places orders on your behalf. Safer than using your main private key.
"""

from __future__ import annotations

import logging
import os

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from polybot_v3.config import HYPERLIQUID_INFO_URL

log = logging.getLogger(__name__)


class LiveExecutor:
    def __init__(self) -> None:
        pk = os.environ.get("HYPERLIQUID_PRIVATE_KEY", "").strip()
        account_addr = os.environ.get("HYPERLIQUID_ACCOUNT_ADDRESS", "").strip()
        if not pk:
            raise RuntimeError("HYPERLIQUID_PRIVATE_KEY env var required for live mode")
        wallet = Account.from_key(pk)
        # If API wallet, pass the real account address
        account = account_addr if account_addr else None
        self._exchange = Exchange(wallet, HYPERLIQUID_INFO_URL, account_address=account)
        self._info = Info(HYPERLIQUID_INFO_URL, skip_ws=True)
        log.info("LiveExecutor ready (wallet=%s, account=%s)",
                 wallet.address[:10], (account or wallet.address)[:10])

    def market_open(self, asset: str, side: str, size: float) -> dict:
        """Open a market order. size in coin units (float), side LONG/SHORT.

        Returns the SDK response dict.
        """
        is_buy = side == "LONG"
        log.info("LIVE market_open %s %s size=%.6f", asset, side, size)
        return self._exchange.market_open(name=asset, is_buy=is_buy, sz=size)

    def market_close(self, asset: str) -> dict:
        """Close existing position for asset at market price."""
        log.info("LIVE market_close %s", asset)
        return self._exchange.market_close(coin=asset)

    def get_account_value(self) -> float:
        addr = self._exchange.account_address or self._exchange.wallet.address
        data = self._info.user_state(addr)
        return float(data.get("marginSummary", {}).get("accountValue", 0))
