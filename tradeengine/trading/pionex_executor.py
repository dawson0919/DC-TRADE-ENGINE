"""Live order executor for Pionex exchange."""

from __future__ import annotations

import logging
from typing import Any

from tradeengine.data.pionex_client import PionexClient
from tradeengine.trading.executor import OrderExecutor

logger = logging.getLogger(__name__)


class PionexExecutor(OrderExecutor):
    """Executes real orders on Pionex."""

    def __init__(self, client: PionexClient):
        self.client = client
        self._positions: dict[str, dict] = {}

    async def place_market_order(self, symbol: str, side: str, size: float) -> dict:
        logger.info(f"LIVE ORDER: {side} {size} {symbol} @ MARKET")
        if side == "BUY":
            # Market buy on Pionex uses 'amount' (quote currency)
            # For simplicity, we pass size as the base currency amount
            result = await self.client.new_order(
                symbol=symbol, side="BUY", order_type="MARKET", size=str(size)
            )
        else:
            result = await self.client.new_order(
                symbol=symbol, side="SELL", order_type="MARKET", size=str(size)
            )
        logger.info(f"Order placed: {result}")
        return result

    async def place_limit_order(
        self, symbol: str, side: str, size: float, price: float
    ) -> dict:
        logger.info(f"LIVE ORDER: {side} {size} {symbol} @ {price}")
        result = await self.client.new_order(
            symbol=symbol,
            side=side,
            order_type="LIMIT",
            size=str(size),
            price=str(price),
        )
        logger.info(f"Limit order placed: {result}")
        return result

    async def cancel_order(self, symbol: str, order_id: Any) -> dict:
        logger.info(f"Cancelling order {order_id} for {symbol}")
        return await self.client.cancel_order(symbol, int(order_id))

    async def get_balance(self, asset: str) -> float:
        bal = await self.client.get_balance(asset)
        return bal["free"]

    async def get_open_orders(self, symbol: str) -> list[dict]:
        return await self.client.get_open_orders(symbol)

    async def get_position(self, symbol: str) -> dict | None:
        return self._positions.get(symbol)
