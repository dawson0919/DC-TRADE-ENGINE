"""Triple EMA Alignment strategy (三刀流趨勢策略).

Ported from PineScript "三刀流 - 黃金 1H 趨勢策略".

Logic:
  - Three EMAs: fast (8), mid (15), slow (30)
  - Bullish alignment: fast > mid > slow
  - Bearish alignment: fast < mid < slow
  - Entry long: bullish alignment JUST formed (this bar aligned, previous bar not)
  - Entry short: bearish alignment JUST formed
  - Exit long: fast < mid (trend weakening)
  - Exit short: fast > mid
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import vectorbt as vbt

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


@register_strategy
class TripleEMAStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "triple_ema"

    @property
    def display_name(self) -> str:
        return "三刀流趨勢策略"

    @property
    def description(self) -> str:
        return "三條EMA排列趨勢追蹤: 快>中>慢做多, 快<中<慢做空 (Triple EMA Alignment)"

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("fast_len", "快線週期", "int", 8, 2, 50, 1),
            StrategyParam("mid_len", "中線週期", "int", 15, 5, 100, 1),
            StrategyParam("slow_len", "慢線週期", "int", 30, 10, 200, 1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        close = ohlcv["close"]

        # Calculate three EMAs
        fast = vbt.MA.run(close, p["fast_len"], ewm=True).ma
        mid = vbt.MA.run(close, p["mid_len"], ewm=True).ma
        slow = vbt.MA.run(close, p["slow_len"], ewm=True).ma

        # Alignment conditions
        bullish_alignment = (fast > mid) & (mid > slow)
        bearish_alignment = (fast < mid) & (mid < slow)

        # Entry: alignment JUST formed (current bar aligned, previous bar not)
        entries_long = bullish_alignment & ~bullish_alignment.shift(1).fillna(False)
        entries_short = bearish_alignment & ~bearish_alignment.shift(1).fillna(False)

        # Exit: fast crosses mid (trend weakening)
        exits_long = (fast < mid) & (fast.shift(1) >= mid.shift(1))
        exits_short = (fast > mid) & (fast.shift(1) <= mid.shift(1))

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=entries_short.fillna(False),
            exits_short=exits_short.fillna(False),
        )
