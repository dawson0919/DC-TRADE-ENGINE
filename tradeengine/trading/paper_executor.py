"""Paper trading executor - simulated order execution."""

from __future__ import annotations

import logging
import time
from typing import Any

from tradeengine.trading.executor import OrderExecutor

logger = logging.getLogger(__name__)


class PaperExecutor(OrderExecutor):
    """Simulated paper trading executor.

    Tracks a virtual portfolio with fills at market price.
    """

    def __init__(self, initial_balance: float = 10000.0, quote_asset: str = "USDT"):
        self._balances: dict[str, float] = {quote_asset: initial_balance}
        self._orders: list[dict] = []
        self._order_counter = 0
        self._positions: dict[str, dict] = {}
        self._current_prices: dict[str, float] = {}
        self.quote_asset = quote_asset

    def set_price(self, symbol: str, price: float):
        """Update current market price for a symbol (called by trading engine)."""
        self._current_prices[symbol] = price

    async def place_market_order(self, symbol: str, side: str, size: float) -> dict:
        price = self._current_prices.get(symbol, 0.0)
        if price <= 0:
            raise ValueError(f"No price available for {symbol}")

        self._order_counter += 1
        order_id = self._order_counter

        # Parse base/quote from symbol (e.g. BTC_USDT)
        base = symbol.split("_")[0]
        quote = symbol.split("_")[1] if "_" in symbol else self.quote_asset

        cost = size * price
        fee = cost * 0.0005  # 0.05% fee simulation

        if side == "BUY":
            if self._balances.get(quote, 0) < cost + fee:
                raise ValueError(f"Insufficient {quote} balance: {self._balances.get(quote, 0):.2f} < {cost + fee:.2f}")
            self._balances[quote] = self._balances.get(quote, 0) - cost - fee
            self._balances[base] = self._balances.get(base, 0) + size
        else:
            if self._balances.get(base, 0) < size:
                raise ValueError(f"Insufficient {base} balance: {self._balances.get(base, 0):.8f} < {size:.8f}")
            self._balances[base] = self._balances.get(base, 0) - size
            self._balances[quote] = self._balances.get(quote, 0) + cost - fee

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
        logger.info(f"PAPER {side} {size:.8f} {symbol} @ {price:.2f} (fee: {fee:.4f})")

        # Update position tracking
        self._update_position(symbol, side, size, price)

        return order

    async def place_limit_order(
        self, symbol: str, side: str, size: float, price: float
    ) -> dict:
        # Paper trading: immediately fill limit orders at specified price
        self._current_prices[symbol] = price
        return await self.place_market_order(symbol, side, size)

    async def cancel_order(self, symbol: str, order_id: Any) -> dict:
        return {"orderId": order_id, "status": "CANCELLED"}

    async def get_balance(self, asset: str) -> float:
        return self._balances.get(asset, 0.0)

    async def get_open_orders(self, symbol: str) -> list[dict]:
        return []  # Paper executor fills everything immediately

    async def get_position(self, symbol: str) -> dict | None:
        return self._positions.get(symbol)

    def _update_position(self, symbol: str, side: str, size: float, price: float):
        """Track position state."""
        pos = self._positions.get(symbol)
        if pos is None:
            if side == "BUY":
                self._positions[symbol] = {"side": "long", "size": size, "entry_price": price}
            else:
                self._positions[symbol] = {"side": "short", "size": size, "entry_price": price}
        else:
            if (pos["side"] == "long" and side == "SELL") or (pos["side"] == "short" and side == "BUY"):
                # Closing position
                if size >= pos["size"]:
                    del self._positions[symbol]
                else:
                    pos["size"] -= size
            else:
                # Adding to position
                total_cost = pos["entry_price"] * pos["size"] + price * size
                pos["size"] += size
                pos["entry_price"] = total_cost / pos["size"]

    def get_portfolio_value(self) -> float:
        """Calculate total portfolio value in quote currency."""
        total = self._balances.get(self.quote_asset, 0.0)
        for symbol, pos in self._positions.items():
            price = self._current_prices.get(symbol, 0.0)
            total += pos["size"] * price
        return total

    @property
    def trade_history(self) -> list[dict]:
        return self._orders.copy()
