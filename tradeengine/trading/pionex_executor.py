"""Live order executor for Pionex exchange."""

from __future__ import annotations

import logging
from typing import Any

from tradeengine.data.pionex_client import PionexClient
from tradeengine.data.pionex_futures_client import PionexFuturesClient
from tradeengine.trading.executor import OrderExecutor

logger = logging.getLogger(__name__)


class PionexExecutor(OrderExecutor):
    """Executes real orders on Pionex."""

    def __init__(self, client: PionexClient, futures_client: PionexFuturesClient | None = None):
        self.client = client
        self.futures_client = futures_client
        self._positions: dict[str, dict] = {}

    async def place_market_order(
        self, symbol: str, side: str, size: float, leverage: float = 1.0
    ) -> dict:
        logger.info(f"LIVE ORDER: {side} {size} {symbol} @ MARKET (Leverage: {leverage}x)")
        
        if leverage > 1.0:
            if not self.futures_client:
                raise RuntimeError("PionexFuturesClient required for leveraged orders")
            
            # For futures, we might need to set leverage first
            await self.futures_client.set_leverage(symbol, leverage)
            
            result = await self.futures_client.place_order(
                symbol=symbol, side=side, type="MARKET", size=str(size), leverage=leverage
            )
        else:
            if side == "BUY":
                # Market buy on Pionex uses 'amount' (quote currency)
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
        self, symbol: str, side: str, size: float, price: float, leverage: float = 1.0
    ) -> dict:
        logger.info(f"LIVE ORDER: {side} {size} {symbol} @ {price} (Leverage: {leverage}x)")
        
        if leverage > 1.0:
            if not self.futures_client:
                raise RuntimeError("PionexFuturesClient required for leveraged orders")
                
            await self.futures_client.set_leverage(symbol, leverage)
            result = await self.futures_client.place_order(
                symbol=symbol,
                side=side,
                type="LIMIT",
                size=str(size),
                price=str(price),
                leverage=leverage
            )
        else:
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
