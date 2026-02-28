"""Combined Multi-Indicator strategy (多指標組合策略)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import vectorbt as vbt

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


@register_strategy
class CombinedStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "combined"

    @property
    def display_name(self) -> str:
        return "多指標組合策略"

    @property
    def description(self) -> str:
        return "EMA 趨勢 + RSI 過濾 + MACD 確認 (Combined Multi-Indicator)"

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("ema_fast", "EMA 快線", "int", 9, 2, 50, 1),
            StrategyParam("ema_slow", "EMA 慢線", "int", 21, 10, 100, 1),
            StrategyParam("rsi_period", "RSI 週期", "int", 14, 5, 50, 1),
            StrategyParam("rsi_low", "RSI 下限", "int", 40, 20, 50, 1),
            StrategyParam("rsi_high", "RSI 上限", "int", 60, 50, 80, 1),
            StrategyParam("macd_fast", "MACD 快線", "int", 12, 5, 30, 1),
            StrategyParam("macd_slow", "MACD 慢線", "int", 26, 15, 60, 1),
            StrategyParam("macd_signal", "MACD 訊號", "int", 9, 3, 20, 1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        close = ohlcv["close"]

        # EMA trend
        ema_fast = vbt.MA.run(close, p["ema_fast"], ewm=True).ma
        ema_slow = vbt.MA.run(close, p["ema_slow"], ewm=True).ma
        trend_up = ema_fast > ema_slow
        trend_down = ema_fast < ema_slow

        # RSI filter
        rsi = vbt.RSI.run(close, p["rsi_period"]).rsi
        rsi_ok_long = rsi < p["rsi_high"]  # Not overbought
        rsi_ok_short = rsi > p["rsi_low"]  # Not oversold

        # MACD confirmation
        macd = vbt.MACD.run(close, p["macd_fast"], p["macd_slow"], p["macd_signal"])
        macd_bull = macd.macd > macd.signal
        macd_bear = macd.macd < macd.signal

        # Combined: trend + RSI filter + MACD confirmation
        # Enter long: EMA uptrend AND RSI not overbought AND MACD bullish (cross)
        macd_cross_up = macd_bull & (~macd_bull.shift(1).fillna(False))
        macd_cross_down = macd_bear & (~macd_bear.shift(1).fillna(False))

        entries_long = trend_up & rsi_ok_long & macd_cross_up
        exits_long = trend_down | macd_cross_down

        entries_short = trend_down & rsi_ok_short & macd_cross_down
        exits_short = trend_up | macd_cross_up

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=entries_short.fillna(False),
            exits_short=exits_short.fillna(False),
        )
