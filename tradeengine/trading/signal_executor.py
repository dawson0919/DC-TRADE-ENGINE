"""Pionex Signal Bot executor — sends signals to /api/v1/bot/signal/listener."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from tradeengine.data.pionex_client import PionexClient
from tradeengine.trading.executor import OrderExecutor

logger = logging.getLogger(__name__)

SIGNAL_REFERENCE_USDT = 100.0  # Pionex Signal API uses 100 USDT as reference


class SignalExecutor(OrderExecutor):
    """Sends trading signals to Pionex Signal Bot API for copy trading.

    Converts engine trade sizes into signal contracts using:
        contracts = size * 100 / capital
    Tracks cumulative position_size (positive=long, negative=short, 0=flat).
    """

    def __init__(
        self,
        client: PionexClient,
        signal_type_id: str,
        capital: float = 10000.0,
        signal_param: str = "{}",
    ):
        self.client = client
        self.signal_type_id = signal_type_id
        self.capital = capital
        self.signal_param = signal_param
        self._position_size: float = 0.0
        self._current_prices: dict[str, float] = {}
        self._positions: dict[str, dict] = {}
        self._order_counter = 0

    def set_price(self, symbol: str, price: float):
        """Update current market price (called by trading engine)."""
        self._current_prices[symbol] = price

    async def place_market_order(
        self, symbol: str, side: str, size: float, leverage: float = 1.0
    ) -> dict:
        price = self._current_prices.get(symbol, 0.0)
        if price <= 0:
            raise ValueError(f"No price available for {symbol}")

        # Convert engine size to signal contracts
        contracts = size * SIGNAL_REFERENCE_USDT / self.capital

        # Determine action and update position_size
        if side == "BUY":
            action = "buy"
            self._position_size += contracts
        else:
            action = "sell"
            self._position_size -= contracts

        # Snap near-zero to exactly 0
        if abs(self._position_size) < 1e-10:
            self._position_size = 0.0

        # Parse base/quote from symbol (e.g. ETH_USDT or ETH_USDT_PERP)
        parts = symbol.replace("_PERP", "").split("_")
        base = parts[0]
        quote = parts[1] if len(parts) > 1 else "USDT"

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        payload = {
            "signalType": self.signal_type_id,
            "signalParam": self.signal_param,
            "base": base,
            "quote": quote,
            "time": now_iso,
            "price": f"{price}",
            "data": {
                "action": action,
                "amount": f"{abs(contracts)}",
                "position_size": f"{self._position_size}",
            },
        }

        logger.info(
            f"SIGNAL {action.upper()}: contracts={abs(contracts):.8f}, "
            f"position_size={self._position_size:.8f}, price={price:.2f}, "
            f"symbol={symbol}"
        )

        result = await self.client.send_signal(payload)

        # Update internal position tracking (for engine compatibility)
        self._update_position(symbol, side, size, price, leverage)

        self._order_counter += 1
        return {
            "orderId": self._order_counter,
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "size": size,
            "price": price,
            "status": "SIGNAL_SENT",
            "signal_response": result,
            "timestamp": int(time.time() * 1000),
        }

    async def place_limit_order(
        self, symbol: str, side: str, size: float, price: float, leverage: float = 1.0
    ) -> dict:
        # Signal API doesn't support limit orders; treat as market at the given price
        self._current_prices[symbol] = price
        return await self.place_market_order(symbol, side, size, leverage)

    async def cancel_order(self, symbol: str, order_id: Any) -> dict:
        return {"orderId": order_id, "status": "NOT_APPLICABLE"}

    async def get_balance(self, asset: str) -> float:
        return self.capital

    async def get_open_orders(self, symbol: str) -> list[dict]:
        return []

    async def get_position(self, symbol: str) -> dict | None:
        return self._positions.get(symbol)

    def restore_position_size(self, position_size: float):
        """Restore signal position_size from persisted state (bot restart)."""
        self._position_size = position_size
        logger.info(f"Restored signal position_size: {position_size}")

    def _update_position(
        self, symbol: str, side: str, size: float, price: float, leverage: float = 1.0
    ):
        """Track position for engine compatibility (mirrors PaperExecutor pattern)."""
        pos = self._positions.get(symbol)
        if pos is None:
            self._positions[symbol] = {
                "side": "long" if side == "BUY" else "short",
                "size": size,
                "entry_price": price,
                "leverage": leverage,
            }
        else:
            closing = (pos["side"] == "long" and side == "SELL") or (
                pos["side"] == "short" and side == "BUY"
            )
            if closing:
                if size >= pos["size"]:
                    del self._positions[symbol]
                else:
                    pos["size"] -= size
            else:
                total_cost = pos["entry_price"] * pos["size"] + price * size
                pos["size"] += size
                pos["entry_price"] = total_cost / pos["size"]
