"""刀神海龜突破交易策略 (Turtle Pivot Breakout Strategy).

Converted from TradingView Pine Script.
Uses pivot highs/lows to identify breakout levels:
- Long entry: price breaks above the most recent pivot high
- Short entry: price breaks below the most recent pivot low
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


def _detect_pivots(
    high: np.ndarray, low: np.ndarray, left: int, right: int
) -> tuple[np.ndarray, np.ndarray]:
    """Detect pivot highs and pivot lows.

    A pivot high at bar i means high[i] is strictly greater than the
    ``left`` bars before it and the ``right`` bars after it.
    The pivot is confirmed (becomes visible) ``right`` bars later.

    Returns arrays of the same length with NaN where no pivot exists.
    """
    n = len(high)
    swh = np.full(n, np.nan)
    swl = np.full(n, np.nan)

    for i in range(left, n - right):
        # Pivot high
        is_ph = True
        for j in range(1, left + 1):
            if high[i - j] >= high[i]:
                is_ph = False
                break
        if is_ph:
            for j in range(1, right + 1):
                if high[i + j] >= high[i]:
                    is_ph = False
                    break
        if is_ph:
            swh[i + right] = high[i]

        # Pivot low
        is_pl = True
        for j in range(1, left + 1):
            if low[i - j] <= low[i]:
                is_pl = False
                break
        if is_pl:
            for j in range(1, right + 1):
                if low[i + j] <= low[i]:
                    is_pl = False
                    break
        if is_pl:
            swl[i + right] = low[i]

    return swh, swl


@register_strategy
class TurtleBreakoutStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "turtle_breakout"

    @property
    def display_name(self) -> str:
        return "刀神海龜突破策略"

    @property
    def description(self) -> str:
        return (
            "偵測樞紐高低點，價格突破樞紐高點做多、跌破樞紐低點做空 "
            "(Pivot High/Low Breakout)"
        )

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("left_bars", "左側K棒數", "int", 4, 1, 20, 1),
            StrategyParam("right_bars", "右側K棒數", "int", 2, 1, 10, 1),
        ]

    def generate_signals(
        self, ohlcv: pd.DataFrame, params: dict[str, Any]
    ) -> SignalOutput:
        p = self.validate_params(params)
        left_bars: int = p["left_bars"]
        right_bars: int = p["right_bars"]

        high_arr = ohlcv["high"].values.astype(float)
        low_arr = ohlcv["low"].values.astype(float)
        n = len(high_arr)

        if n < left_bars + right_bars + 2:
            return self._empty_signals(ohlcv.index)

        # Detect pivot highs / lows
        swh, swl = _detect_pivots(high_arr, low_arr, left_bars, right_bars)

        # State machine matching the Pine Script logic:
        #   hprice tracks the latest pivot high level
        #   le (long enabled) = True after a new pivot high, False after breakout
        #   Entry long fires when le was True and high breaks above hprice
        hprice = np.zeros(n)
        lprice = np.zeros(n)
        le = np.zeros(n, dtype=bool)
        se = np.zeros(n, dtype=bool)
        entry_long = np.zeros(n, dtype=bool)
        entry_short = np.zeros(n, dtype=bool)

        for i in range(1, n):
            hprice[i] = hprice[i - 1]
            lprice[i] = lprice[i - 1]

            # -- Pivot high / long breakout --
            if not np.isnan(swh[i]):
                hprice[i] = swh[i]
                le[i] = True
            else:
                if le[i - 1] and high_arr[i] > hprice[i]:
                    le[i] = False
                    entry_long[i] = True
                else:
                    le[i] = le[i - 1]

            # -- Pivot low / short breakdown --
            if not np.isnan(swl[i]):
                lprice[i] = swl[i]
                se[i] = True
            else:
                if se[i - 1] and low_arr[i] < lprice[i]:
                    se[i] = False
                    entry_short[i] = True
                else:
                    se[i] = se[i - 1]

        # In the Pine Script, entries reverse positions (no separate exits).
        # Map to our 4-signal system: opposite entry = exit.
        return SignalOutput(
            entries_long=pd.Series(entry_long, index=ohlcv.index),
            exits_long=pd.Series(entry_short, index=ohlcv.index),
            entries_short=pd.Series(entry_short, index=ohlcv.index),
            exits_short=pd.Series(entry_long, index=ohlcv.index),
        )
