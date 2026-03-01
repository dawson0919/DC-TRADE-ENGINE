"""葛蘭碧大師策略 (Granville Pro Strategy).

Converted from QuantSignal's granville_eth_4h.js.
Uses EMA crossover with stop-loss deviation:
- Golden Cross: price crosses above EMA -> Long
- Death Cross: price crosses below EMA -> Short
- Stop Loss: price deviates beyond SL% from EMA -> Exit

Optimized defaults (4H):
  BTC: EMA-178, SL 0.5%
  ETH: EMA-203, SL 0.5%
  SOL: EMA-156, SL 0.5%
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import vectorbt as vbt

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


@register_strategy
class GranvilleProStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "granville_pro"

    @property
    def display_name(self) -> str:
        return "葛蘭碧大師策略"

    @property
    def description(self) -> str:
        return (
            "葛蘭碧法則精華版 — EMA 交叉做多空 + 停損偏離 "
            "(Granville Pro)"
        )

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("ema_period", "EMA 週期", "int", 203, 5, 500, 1),
            StrategyParam("sl_pct", "停損偏離 %", "float", 0.5, 0.1, 5.0, 0.1),
        ]

    def generate_signals(
        self, ohlcv: pd.DataFrame, params: dict[str, Any]
    ) -> SignalOutput:
        p = self.validate_params(params)
        ema_period: int = p["ema_period"]
        sl_pct: float = p["sl_pct"] / 100.0  # convert percentage to ratio

        close = ohlcv["close"]
        n = len(close)

        if n < ema_period + 2:
            return self._empty_signals(ohlcv.index)

        # Calculate EMA using vectorBT
        ema = vbt.MA.run(close, ema_period, ewm=True).ma

        prev_close = close.shift(1)
        prev_ema = ema.shift(1)

        # Golden Cross: previous close below previous EMA, current close above EMA
        entry_long = (prev_close < prev_ema) & (close > ema)

        # Death Cross: previous close above previous EMA, current close below EMA
        entry_short = (prev_close > prev_ema) & (close < ema)

        # Stop Loss exits: price deviates beyond SL% from EMA
        exit_long = close < ema * (1 - sl_pct)
        exit_short = close > ema * (1 + sl_pct)

        # Combine: opposite entry also serves as exit (reversal system)
        exits_long = exit_long | entry_short
        exits_short = exit_short | entry_long

        return SignalOutput(
            entries_long=entry_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=entry_short.fillna(False),
            exits_short=exits_short.fillna(False),
        )
