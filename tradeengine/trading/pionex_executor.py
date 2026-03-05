"""Live order executor for Pionex exchange."""

from __future__ import annotations

import asyncio
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

        is_futures = leverage > 1.0 or "_PERP" in symbol

        if is_futures:
            if not self.futures_client:
                raise RuntimeError("PionexFuturesClient required for leveraged orders")

            await self.futures_client.set_leverage(symbol, leverage)

            result = await self.futures_client.place_order(
                symbol=symbol, side=side, type="MARKET", size=str(size), leverage=leverage
            )
        else:
            if side == "BUY":
                result = await self.client.new_order(
                    symbol=symbol, side="BUY", order_type="MARKET", size=str(size)
                )
            else:
                result = await self.client.new_order(
                    symbol=symbol, side="SELL", order_type="MARKET", size=str(size)
                )
        logger.info(f"Order placed: {result}")

        # Query actual fill price after market order
        fill_price = await self._query_fill_price(result, symbol, is_futures)
        if fill_price:
            result["price"] = fill_price
            logger.info(f"Actual fill price: {fill_price:.2f}")

        return result

    async def _query_fill_price(
        self, order_result: dict, symbol: str, is_futures: bool
    ) -> float | None:
        """Query order details to get actual fill price after market order."""
        order_id = order_result.get("orderId")
        if not order_id:
            return None

        await asyncio.sleep(0.5)  # Brief wait for order to fill

        try:
            if is_futures and self.futures_client:
                order_info = await self.futures_client.get_order(symbol, str(order_id))
            else:
                order_info = await self.client.get_order(int(order_id))

            # Try different field names Pionex might use
            filled_size = float(order_info.get("filledSize", 0) or order_info.get("dealSize", 0) or 0)
            filled_amount = float(order_info.get("filledAmount", 0) or order_info.get("dealFunds", 0) or 0)

            if filled_size > 0 and filled_amount > 0:
                return filled_amount / filled_size

            # Direct price field
            if order_info.get("price") and float(order_info["price"]) > 0:
                return float(order_info["price"])

        except Exception as e:
            logger.warning(f"Failed to query fill price for order {order_id}: {e}")

        return None

    async def place_limit_order(
        self, symbol: str, side: str, size: float, price: float, leverage: float = 1.0
    ) -> dict:
        logger.info(f"LIVE ORDER: {side} {size} {symbol} @ {price} (Leverage: {leverage}x)")
        
        if leverage > 1.0 or "_PERP" in symbol:
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
