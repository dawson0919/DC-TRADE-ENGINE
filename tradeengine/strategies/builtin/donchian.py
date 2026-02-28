"""Donchian Channel Breakout strategy (唐奇安通道突破策略)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


@register_strategy
class DonchianBreakoutStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "donchian"

    @property
    def display_name(self) -> str:
        return "唐奇安通道突破策略"

    @property
    def description(self) -> str:
        return "價格突破N週期高點做多，跌破N週期低點平倉 (Donchian Channel Breakout)"

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("entry_period", "進場週期", "int", 20, 5, 100, 1),
            StrategyParam("exit_period", "出場週期", "int", 10, 3, 50, 1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]

        # Donchian channels
        upper = high.rolling(window=p["entry_period"]).max().shift(1)
        lower = low.rolling(window=p["entry_period"]).min().shift(1)
        exit_lower = low.rolling(window=p["exit_period"]).min().shift(1)
        exit_upper = high.rolling(window=p["exit_period"]).max().shift(1)

        # Breakout above upper channel -> long
        entries_long = close > upper
        exits_long = close < exit_lower

        # Breakout below lower channel -> short
        entries_short = close < lower
        exits_short = close > exit_upper

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=entries_short.fillna(False),
            exits_short=exits_short.fillna(False),
        )
