"""Abstract order executor interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OrderExecutor(ABC):
    """Interface for order execution (live or paper)."""

    @abstractmethod
    async def place_market_order(self, symbol: str, side: str, size: float) -> dict:
        """Place a market order. Returns order info dict."""
        ...

    @abstractmethod
    async def place_limit_order(
        self, symbol: str, side: str, size: float, price: float
    ) -> dict:
        """Place a limit order. Returns order info dict."""
        ...

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: Any) -> dict:
        """Cancel an order."""
        ...

    @abstractmethod
    async def get_balance(self, asset: str) -> float:
        """Get free balance for an asset."""
        ...

    @abstractmethod
    async def get_open_orders(self, symbol: str) -> list[dict]:
        """Get all open orders for a symbol."""
        ...

    @abstractmethod
    async def get_position(self, symbol: str) -> dict | None:
        """Get current position for a symbol, or None if flat."""
        ...
