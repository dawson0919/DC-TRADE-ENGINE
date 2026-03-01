"""Donchian Momentum + SuperTrend strategy.

Combination of Donchian Channel Breakout and SuperTrend trend filter.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy
from tradeengine.strategies.builtin.supertrend import calc_supertrend


@register_strategy
class DonchianSuperTrendStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "donchian_supertrend"

    @property
    def display_name(self) -> str:
        return "唐奇安動能 + SuperTrend 策略"

    @property
    def description(self) -> str:
        return "價格突破唐奇安上軌且 SuperTrend 翻多時進場，跌破唐奇安下軌或 SuperTrend 翻空時出場。"

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("entry_period", "唐奇安進場週期", "int", 20, 5, 100, 1),
            StrategyParam("exit_period", "唐奇安出場週期", "int", 10, 3, 50, 1),
            StrategyParam("st_period", "SuperTrend ATR 週期", "int", 10, 5, 50, 1),
            StrategyParam("st_multiplier", "SuperTrend ATR 倍數", "float", 3.0, 1.0, 6.0, 0.1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]

        # 1. Donchian Channels
        upper = high.rolling(window=p["entry_period"]).max().shift(1)
        lower = low.rolling(window=p["entry_period"]).min().shift(1)
        exit_lower = low.rolling(window=p["exit_period"]).min().shift(1)
        exit_upper = high.rolling(window=p["exit_period"]).max().shift(1)

        # 2. SuperTrend
        _, direction = calc_supertrend(high, low, close, p["st_period"], p["st_multiplier"])
        st_up = direction == 1
        st_down = direction == -1

        # 3. Signals
        # Long: Breakout above upper AND SuperTrend is up
        entries_long = (close > upper) & st_up
        # Exit Long: Breakout below exit_lower OR SuperTrend flips down
        exits_long = (close < exit_lower) | st_down

        # Short: Breakout below lower AND SuperTrend is down
        entries_short = (close < lower) & st_down
        # Exit Short: Breakout above exit_upper OR SuperTrend flips up
        exits_short = (close > exit_upper) | st_up

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=entries_short.fillna(False),
            exits_short=exits_short.fillna(False),
        )
