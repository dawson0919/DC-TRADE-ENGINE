"""Bollinger Bands Mean Reversion strategy (布林通道均值回歸策略)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import vectorbt as vbt

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


@register_strategy
class BollingerBandsStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "bollinger"

    @property
    def display_name(self) -> str:
        return "布林通道均值回歸策略"

    @property
    def description(self) -> str:
        return "價格觸及下軌做多，觸及上軌平倉 (Bollinger Bands Mean Reversion)"

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("period", "布林通道週期", "int", 20, 5, 100, 1),
            StrategyParam("std_dev", "標準差倍數", "float", 2.0, 0.5, 4.0, 0.1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        close = ohlcv["close"]

        bb = vbt.BBANDS.run(close, window=p["period"], alpha=p["std_dev"])
        upper = bb.upper
        lower = bb.lower
        middle = bb.middle

        # Enter long when price touches lower band
        entries_long = (close <= lower) & (close.shift(1) > lower.shift(1))
        # Exit long when price touches upper band or middle
        exits_long = (close >= upper) & (close.shift(1) < upper.shift(1))

        # Enter short when price touches upper band
        entries_short = exits_long.copy()
        exits_short = entries_long.copy()

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=entries_short.fillna(False),
            exits_short=exits_short.fillna(False),
        )
