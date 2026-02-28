"""MACD Signal Crossover strategy (MACD 訊號交叉策略)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import vectorbt as vbt

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


@register_strategy
class MACDStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "macd"

    @property
    def display_name(self) -> str:
        return "MACD 訊號交叉策略"

    @property
    def description(self) -> str:
        return "MACD 線上穿訊號線做多，下穿做空 (MACD Crossover)"

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("fast_period", "快線週期", "int", 12, 2, 50, 1),
            StrategyParam("slow_period", "慢線週期", "int", 26, 10, 100, 1),
            StrategyParam("signal_period", "訊號線週期", "int", 9, 2, 50, 1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        close = ohlcv["close"]

        macd_result = vbt.MACD.run(
            close,
            fast_window=p["fast_period"],
            slow_window=p["slow_period"],
            signal_window=p["signal_period"],
        )
        macd_line = macd_result.macd
        signal_line = macd_result.signal

        # MACD crosses above signal line -> long
        entries_long = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
        exits_long = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=exits_long.fillna(False),
            exits_short=entries_long.fillna(False),
        )
