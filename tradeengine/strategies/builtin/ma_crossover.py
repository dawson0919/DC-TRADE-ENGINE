"""Moving Average Crossover strategy (均線交叉策略)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import vectorbt as vbt

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


@register_strategy
class MACrossoverStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "ma_crossover"

    @property
    def display_name(self) -> str:
        return "均線交叉策略"

    @property
    def description(self) -> str:
        return "快線上穿慢線做多，快線下穿慢線做空 (MA Crossover)"

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("fast_period", "快線週期", "int", 9, 2, 200, 1),
            StrategyParam("slow_period", "慢線週期", "int", 21, 5, 500, 1),
            StrategyParam("ma_type", "均線類型", "select", "EMA", options=["SMA", "EMA"]),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        close = ohlcv["close"]

        use_ewm = p["ma_type"] == "EMA"
        fast = vbt.MA.run(close, p["fast_period"], ewm=use_ewm).ma
        slow = vbt.MA.run(close, p["slow_period"], ewm=use_ewm).ma

        # Golden cross: fast crosses above slow
        entries_long = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        # Death cross: fast crosses below slow
        exits_long = (fast < slow) & (fast.shift(1) >= slow.shift(1))

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=exits_long.fillna(False),
            exits_short=entries_long.fillna(False),
        )
