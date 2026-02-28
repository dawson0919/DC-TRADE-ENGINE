"""Core data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

    @property
    def minutes(self) -> int:
        mapping = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
        return mapping[self.value]

    @property
    def pandas_freq(self) -> str:
        mapping = {
            "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "1h", "4h": "4h", "1d": "1D",
        }
        return mapping[self.value]


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OHLCV(BaseModel):
    timestamp: int  # ms epoch
    open: float
    high: float
    low: float
    close: float
    volume: float


class Trade(BaseModel):
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    side: Side
    size: float
    pnl_pct: float
    pnl_usd: float
    fees: float = 0.0


class Position(BaseModel):
    symbol: str
    side: Side
    entry_price: float
    size: float
    unrealized_pnl: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop_pct: float | None = None
    entry_time: datetime | None = None


class BacktestMetrics(BaseModel):
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    profit_factor: float = 0.0
    avg_trade_pct: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
