"""SuperTrend strategy (SuperTrend 趨勢追蹤策略)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


def calc_supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                    period: int, multiplier: float) -> tuple[pd.Series, pd.Series]:
    """Calculate SuperTrend indicator.

    Returns (supertrend_line, direction) where direction is 1 for uptrend, -1 for downtrend.
    """
    hl2 = (high + low) / 2
    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = pd.Series(np.nan, index=close.index)
    direction = pd.Series(1, index=close.index, dtype=int)

    for i in range(period, len(close)):
        if close.iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
            if direction.iloc[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i - 1]:
                lower_band.iloc[i] = lower_band.iloc[i - 1]
            if direction.iloc[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i - 1]:
                upper_band.iloc[i] = upper_band.iloc[i - 1]

        supertrend.iloc[i] = lower_band.iloc[i] if direction.iloc[i] == 1 else upper_band.iloc[i]

    return supertrend, direction


@register_strategy
class SuperTrendStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "supertrend"

    @property
    def display_name(self) -> str:
        return "SuperTrend 趨勢追蹤策略"

    @property
    def description(self) -> str:
        return "SuperTrend 翻多做多，翻空做空 (SuperTrend Trend Following)"

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("period", "ATR 週期", "int", 10, 5, 50, 1),
            StrategyParam("multiplier", "ATR 倍數", "float", 3.0, 1.0, 6.0, 0.1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)

        _, direction = calc_supertrend(
            ohlcv["high"], ohlcv["low"], ohlcv["close"],
            p["period"], p["multiplier"],
        )

        # Direction flips from -1 to 1 -> enter long
        entries_long = (direction == 1) & (direction.shift(1) == -1)
        exits_long = (direction == -1) & (direction.shift(1) == 1)

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=exits_long.fillna(False),
            exits_short=entries_long.fillna(False),
        )
