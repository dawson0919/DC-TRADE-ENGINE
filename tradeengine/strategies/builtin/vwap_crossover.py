"""VWAP 交叉策略 (VWAP Stdev Bands Crossover Strategy).

Based on TradingView "VWAP Stdev Bands v2 Mod":
- Session-based VWAP (daily reset at 00:00 UTC)
- hl2 as typical price
- Standard deviation bands
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


def calc_session_vwap(high: pd.Series, low: pd.Series, volume: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Calculate session-based VWAP with daily reset (matches PineScript logic).

    Returns (vwap, dev) where dev is the volume-weighted standard deviation.
    """
    hl2 = (high + low) / 2
    hl2_vals = hl2.values
    vol_vals = volume.values

    # Detect new session (day boundary in UTC)
    dates = high.index.normalize()
    new_session = np.concatenate(([True], dates[1:] != dates[:-1]))

    # Cumulative sums that reset each session
    n = len(hl2_vals)
    vwap_sum = np.empty(n)
    vol_sum = np.empty(n)
    v2_sum = np.empty(n)

    for i in range(n):
        if new_session[i]:
            vwap_sum[i] = hl2_vals[i] * vol_vals[i]
            vol_sum[i] = vol_vals[i]
            v2_sum[i] = vol_vals[i] * hl2_vals[i] ** 2
        else:
            vwap_sum[i] = vwap_sum[i - 1] + hl2_vals[i] * vol_vals[i]
            vol_sum[i] = vol_sum[i - 1] + vol_vals[i]
            v2_sum[i] = v2_sum[i - 1] + vol_vals[i] * hl2_vals[i] ** 2

    vwap = pd.Series(vwap_sum / vol_sum, index=high.index)
    dev = pd.Series(np.sqrt(np.maximum(v2_sum / vol_sum - (vwap_sum / vol_sum) ** 2, 0)), index=high.index)

    return vwap, dev


@register_strategy
class VWAPCrossoverStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "vwap_crossover"

    @property
    def display_name(self) -> str:
        return "VWAP 標準差帶交叉策略"

    @property
    def description(self) -> str:
        return (
            "Session VWAP 標準差帶交叉策略（每日重置）。"
            "價格突破上軌做多，跌破下軌做空。"
            "可加 EMA 趨勢過濾器。"
        )

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("band_mult", "標準差倍數", "float", 1.28, 0.5, 5.0, 0.01),
            StrategyParam("ema_period", "EMA 濾網週期 (0=關閉)", "int", 0, 0, 500, 1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        high, low, close = ohlcv["high"], ohlcv["low"], ohlcv["close"]
        volume = ohlcv["volume"]

        # Session-based VWAP (daily reset, hl2 typical price)
        vwap, dev = calc_session_vwap(high, low, volume)

        # Standard deviation bands
        band_mult = p["band_mult"]
        upper = vwap + band_mult * dev
        lower = vwap - band_mult * dev

        # EMA trend filter
        if p["ema_period"] > 0:
            ema = vbt.MA.run(close, p["ema_period"], ewm=True).ma
            ema_long_ok = close > ema
            ema_short_ok = close < ema
        else:
            ema_long_ok = pd.Series(True, index=close.index)
            ema_short_ok = pd.Series(True, index=close.index)

        # Conditions: price breaks above upper band (long), below lower band (short)
        long_cond = (close > upper) & ema_long_ok
        short_cond = (close < lower) & ema_short_ok

        # Edge-trigger on state change
        entries_long = long_cond & (~long_cond.shift(1).fillna(False))
        exits_long = (~long_cond) & long_cond.shift(1).fillna(False)
        entries_short = short_cond & (~short_cond.shift(1).fillna(False))
        exits_short = (~short_cond) & short_cond.shift(1).fillna(False)

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=entries_short.fillna(False),
            exits_short=exits_short.fillna(False),
        )
