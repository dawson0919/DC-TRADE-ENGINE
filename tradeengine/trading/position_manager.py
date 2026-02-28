"""Position tracking and PnL calculation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from tradeengine.data.models import Position, Side

logger = logging.getLogger(__name__)


class PositionManager:
    """Tracks open positions and trade history."""

    def __init__(self):
        self._positions: dict[str, Position] = {}
        self._trade_history: list[dict] = []

    @property
    def positions(self) -> dict[str, Position]:
        return self._positions.copy()

    @property
    def trade_history(self) -> list[dict]:
        return self._trade_history.copy()

    def open_position(
        self,
        symbol: str,
        side: Side,
        entry_price: float,
        size: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Position:
        """Open a new position."""
        pos = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            size=size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=datetime.now(timezone.utc),
        )
        self._positions[symbol] = pos
        logger.info(
            f"Opened {side.value} position: {symbol} size={size:.8f} @ {entry_price:.2f}"
        )
        return pos

    def close_position(self, symbol: str, exit_price: float) -> dict | None:
        """Close a position and record the trade."""
        pos = self._positions.pop(symbol, None)
        if pos is None:
            logger.warning(f"No open position for {symbol}")
            return None

        if pos.side == Side.LONG:
            pnl_pct = (exit_price - pos.entry_price) / pos.entry_price * 100
            pnl_usd = (exit_price - pos.entry_price) * pos.size
        else:
            pnl_pct = (pos.entry_price - exit_price) / pos.entry_price * 100
            pnl_usd = (pos.entry_price - exit_price) * pos.size

        trade = {
            "symbol": symbol,
            "side": pos.side.value,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "size": pos.size,
            "pnl_pct": round(pnl_pct, 2),
            "pnl_usd": round(pnl_usd, 4),
            "entry_time": pos.entry_time.isoformat() if pos.entry_time else None,
            "exit_time": datetime.now(timezone.utc).isoformat(),
        }
        self._trade_history.append(trade)
        logger.info(
            f"Closed {pos.side.value} position: {symbol} PnL={pnl_pct:+.2f}% (${pnl_usd:+.4f})"
        )
        return trade

    def update_unrealized_pnl(self, symbol: str, current_price: float):
        """Update unrealized PnL for a position."""
        pos = self._positions.get(symbol)
        if pos is None:
            return
        if pos.side == Side.LONG:
            pos.unrealized_pnl = (current_price - pos.entry_price) / pos.entry_price * 100
        else:
            pos.unrealized_pnl = (pos.entry_price - current_price) / pos.entry_price * 100

    def has_position(self, symbol: str) -> bool:
        return symbol in self._positions

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)
