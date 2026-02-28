"""RSI Overbought/Oversold strategy (RSI 超買超賣策略)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import vectorbt as vbt

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


@register_strategy
class RSIStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "rsi"

    @property
    def display_name(self) -> str:
        return "RSI 超買超賣策略"

    @property
    def description(self) -> str:
        return "RSI 低於超賣線做多，高於超買線平倉 (RSI Mean Reversion)"

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("period", "RSI 週期", "int", 14, 2, 100, 1),
            StrategyParam("oversold", "超賣線", "int", 30, 5, 45, 1),
            StrategyParam("overbought", "超買線", "int", 70, 55, 95, 1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        close = ohlcv["close"]

        rsi = vbt.RSI.run(close, p["period"]).rsi

        # Enter long when RSI crosses below oversold
        entries_long = (rsi < p["oversold"]) & (rsi.shift(1) >= p["oversold"])
        # Exit long when RSI crosses above overbought
        exits_long = (rsi > p["overbought"]) & (rsi.shift(1) <= p["overbought"])

        # Enter short when RSI crosses above overbought
        entries_short = exits_long.copy()
        exits_short = entries_long.copy()

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=entries_short.fillna(False),
            exits_short=exits_short.fillna(False),
        )
