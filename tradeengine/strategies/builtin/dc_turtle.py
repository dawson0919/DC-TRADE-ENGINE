"""[DC] 海龜策略 (DC Turtle Strategy with TP/SL/Trailing Stop).

Converted from TradingView Pine Script "[DC] TURTLE strategy".
Pivot breakout entries + profit target / stop loss / trailing stop exits.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy
from tradeengine.strategies.builtin.turtle_breakout import _detect_pivots


@register_strategy
class DCTurtleStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "dc_turtle"

    @property
    def display_name(self) -> str:
        return "[DC] 海龜停利停損策略"

    @property
    def description(self) -> str:
        return (
            "樞紐突破進場 + 停利/停損/移動停利三重出場機制。"
            "偵測樞紐高低點突破進場，搭配固定停利停損與"
            "移動停利保護獲利。"
        )

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("left_bars", "左側K棒數", "int", 3, 1, 20, 1),
            StrategyParam("right_bars", "右側K棒數", "int", 2, 1, 10, 1),
            StrategyParam("tp_pct", "停利 %", "float", 5.0, 0.5, 20.0, 0.1),
            StrategyParam("sl_pct", "停損 %", "float", 2.0, 0.5, 10.0, 0.1),
            StrategyParam("trail_tgt_pct", "移動停利啟動 %", "float", 3.0, 0.5, 15.0, 0.1),
            StrategyParam("trail_pct", "移動停利回撤 %", "float", 50.0, 10.0, 90.0, 1.0),
        ]

    def generate_signals(
        self, ohlcv: pd.DataFrame, params: dict[str, Any]
    ) -> SignalOutput:
        p = self.validate_params(params)
        left_bars: int = p["left_bars"]
        right_bars: int = p["right_bars"]
        tp_pct: float = p["tp_pct"] / 100.0
        sl_pct: float = p["sl_pct"] / 100.0
        trail_tgt_pct: float = p["trail_tgt_pct"] / 100.0
        trail_pct: float = p["trail_pct"] / 100.0

        high_arr = ohlcv["high"].values.astype(float)
        low_arr = ohlcv["low"].values.astype(float)
        close_arr = ohlcv["close"].values.astype(float)
        n = len(high_arr)

        if n < left_bars + right_bars + 2:
            return self._empty_signals(ohlcv.index)

        # Detect pivot highs / lows
        swh, swl = _detect_pivots(high_arr, low_arr, left_bars, right_bars)

        # State machine for entries (same as turtle_breakout)
        hprice = np.zeros(n)
        lprice = np.zeros(n)
        le = np.zeros(n, dtype=bool)
        se = np.zeros(n, dtype=bool)
        raw_entry_long = np.zeros(n, dtype=bool)
        raw_entry_short = np.zeros(n, dtype=bool)

        for i in range(1, n):
            hprice[i] = hprice[i - 1]
            lprice[i] = lprice[i - 1]

            if not np.isnan(swh[i]):
                hprice[i] = swh[i]
                le[i] = True
            else:
                if le[i - 1] and high_arr[i] > hprice[i]:
                    le[i] = False
                    raw_entry_long[i] = True
                else:
                    le[i] = le[i - 1]

            if not np.isnan(swl[i]):
                lprice[i] = swl[i]
                se[i] = True
            else:
                if se[i - 1] and low_arr[i] < lprice[i]:
                    se[i] = False
                    raw_entry_short[i] = True
                else:
                    se[i] = se[i - 1]

        # Position management with TP/SL/Trailing
        entry_long = np.zeros(n, dtype=bool)
        exit_long = np.zeros(n, dtype=bool)
        entry_short = np.zeros(n, dtype=bool)
        exit_short = np.zeros(n, dtype=bool)

        # 0 = flat, 1 = long, -1 = short
        position = 0
        entry_price = 0.0
        trail_value = 0.0

        for i in range(1, n):
            if position == 0:
                # Flat — look for entries
                if raw_entry_long[i]:
                    entry_long[i] = True
                    position = 1
                    entry_price = close_arr[i]
                    trail_value = high_arr[i]
                elif raw_entry_short[i]:
                    entry_short[i] = True
                    position = -1
                    entry_price = close_arr[i]
                    trail_value = low_arr[i]

            elif position == 1:
                # Long position — check exits
                trail_value = max(trail_value, high_arr[i])
                exited = False

                # Take profit
                if close_arr[i] >= entry_price * (1.0 + tp_pct):
                    exit_long[i] = True
                    exited = True
                # Stop loss
                elif close_arr[i] <= entry_price * (1.0 - sl_pct):
                    exit_long[i] = True
                    exited = True
                # Trailing stop
                elif trail_value >= entry_price * (1.0 + trail_tgt_pct):
                    trail_exit = trail_value - trail_pct * (trail_value - entry_price)
                    if close_arr[i] < trail_exit:
                        exit_long[i] = True
                        exited = True

                if exited:
                    position = 0
                elif raw_entry_short[i]:
                    # Reverse: long → short
                    exit_long[i] = True
                    entry_short[i] = True
                    position = -1
                    entry_price = close_arr[i]
                    trail_value = low_arr[i]

            elif position == -1:
                # Short position — check exits
                trail_value = min(trail_value, low_arr[i])
                exited = False

                # Take profit (price drops)
                if close_arr[i] <= entry_price * (1.0 - tp_pct):
                    exit_short[i] = True
                    exited = True
                # Stop loss (price rises)
                elif close_arr[i] >= entry_price * (1.0 + sl_pct):
                    exit_short[i] = True
                    exited = True
                # Trailing stop
                elif trail_value <= entry_price * (1.0 - trail_tgt_pct):
                    trail_exit = trail_value + trail_pct * (entry_price - trail_value)
                    if close_arr[i] > trail_exit:
                        exit_short[i] = True
                        exited = True

                if exited:
                    position = 0
                elif raw_entry_long[i]:
                    # Reverse: short → long
                    exit_short[i] = True
                    entry_long[i] = True
                    position = 1
                    entry_price = close_arr[i]
                    trail_value = high_arr[i]

        return SignalOutput(
            entries_long=pd.Series(entry_long, index=ohlcv.index),
            exits_long=pd.Series(exit_long, index=ohlcv.index),
            entries_short=pd.Series(entry_short, index=ohlcv.index),
            exits_short=pd.Series(exit_short, index=ohlcv.index),
        )
