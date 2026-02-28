"""Risk management: stop-loss, take-profit, trailing stop, max drawdown."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """Risk management configuration."""

    max_drawdown_pct: float = 20.0  # Kill switch: halt trading
    max_position_pct: float = 95.0  # Max % of capital per position
    default_sl_pct: float | None = None  # Default stop-loss %
    default_tp_pct: float | None = None  # Default take-profit %
    trailing_stop_pct: float | None = None  # Trailing stop %


class RiskManager:
    """Monitors risk and enforces limits."""

    def __init__(self, config: RiskConfig, initial_capital: float):
        self.config = config
        self.initial_capital = initial_capital
        self.peak_capital = initial_capital
        self._halted = False

    def update(self, current_capital: float):
        """Update with current portfolio value. Checks drawdown."""
        if current_capital > self.peak_capital:
            self.peak_capital = current_capital

        drawdown_pct = (1 - current_capital / self.peak_capital) * 100
        if drawdown_pct >= self.config.max_drawdown_pct:
            logger.critical(
                f"MAX DRAWDOWN REACHED: {drawdown_pct:.1f}% >= {self.config.max_drawdown_pct}%"
            )
            self._halted = True

    def should_halt(self) -> bool:
        """Check if trading should be halted."""
        return self._halted

    def calculate_position_size(
        self, capital: float, price: float
    ) -> float:
        """Calculate max position size in base currency."""
        max_capital = capital * (self.config.max_position_pct / 100)
        return max_capital / price

    def check_stop_loss(
        self, entry_price: float, current_price: float, side: str
    ) -> bool:
        """Check if stop-loss is triggered."""
        if self.config.default_sl_pct is None:
            return False
        sl_pct = self.config.default_sl_pct / 100
        if side == "long":
            return current_price <= entry_price * (1 - sl_pct)
        else:
            return current_price >= entry_price * (1 + sl_pct)

    def check_take_profit(
        self, entry_price: float, current_price: float, side: str
    ) -> bool:
        """Check if take-profit is triggered."""
        if self.config.default_tp_pct is None:
            return False
        tp_pct = self.config.default_tp_pct / 100
        if side == "long":
            return current_price >= entry_price * (1 + tp_pct)
        else:
            return current_price <= entry_price * (1 - tp_pct)

    def reset(self):
        """Reset risk manager state."""
        self._halted = False
        self.peak_capital = self.initial_capital
