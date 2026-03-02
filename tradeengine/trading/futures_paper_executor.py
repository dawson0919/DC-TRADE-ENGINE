"""Paper executor for futures symbols (NQ=F, ES=F, SI=F, GC=F)."""

from __future__ import annotations

import logging
import time

from tradeengine.trading.paper_executor import PaperExecutor

logger = logging.getLogger(__name__)


class FuturesPaperExecutor(PaperExecutor):
    """PaperExecutor variant for USD-denominated futures contracts.

    Handles symbols like NQ=F where there is no base/quote split.
    Capital is always in USD.
    """

    def __init__(self, initial_balance: float = 10000.0):
        super().__init__(initial_balance=initial_balance, quote_asset="USD")

    async def place_market_order(self, symbol: str, side: str, size: float) -> dict:
        price = self._current_prices.get(symbol, 0.0)
        if price <= 0:
            raise ValueError(f"No price available for {symbol}")

        self._order_counter += 1
        order_id = self._order_counter

        cost = size * price
        fee = cost * 0.0005

        if side == "BUY":
            if self._balances.get("USD", 0) < cost + fee:
                raise ValueError(
                    f"Insufficient USD balance: "
                    f"{self._balances.get('USD', 0):.2f} < {cost + fee:.2f}"
                )
            self._balances["USD"] = self._balances.get("USD", 0) - cost - fee
            self._balances[symbol] = self._balances.get(symbol, 0) + size
        else:
            if self._balances.get(symbol, 0) < size:
                raise ValueError(
                    f"Insufficient {symbol} position: "
                    f"{self._balances.get(symbol, 0):.4f} < {size:.4f}"
                )
            self._balances[symbol] = self._balances.get(symbol, 0) - size
            self._balances["USD"] = self._balances.get("USD", 0) + cost - fee

        order = {
            "orderId": order_id,
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "size": size,
            "price": price,
            "fee": fee,
            "status": "FILLED",
            "timestamp": int(time.time() * 1000),
        }
        self._orders.append(order)
        logger.info(f"FUTURES PAPER {side} {size:.4f} {symbol} @ {price:.2f} (fee: {fee:.4f})")

        self._update_position(symbol, side, size, price)
        return order

    async def get_balance(self, asset: str) -> float:
        if asset in ("USD", "USDT"):
            return self._balances.get("USD", 0.0)
        return self._balances.get(asset, 0.0)
