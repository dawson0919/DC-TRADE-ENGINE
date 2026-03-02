"""Ichimoku Cloud Breakout + EMA 200 trend filter (一目均衡表雲圖突破+EMA趨勢濾網)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import vectorbt as vbt

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


@register_strategy
class IchimokuCloudStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "ichimoku_cloud"

    @property
    def display_name(self) -> str:
        return "一目均衡表 (Cloud Breakout + EMA)"

    @property
    def description(self) -> str:
        return (
            "雲圖突破 (Cloud Breakout) 結合 EMA 200 趨勢濾網。"
            "當價格在雲層上方、轉換線穿過基準線且價格高於 EMA 200 時做多；"
            "價格在雲層下方、轉換線低於基準線且價格低於 EMA 200 時做空。"
        )

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("tenkan_period", "轉換線週期 (Tenkan)", "int", 9, 2, 100, 1),
            StrategyParam("kijun_period", "基準線週期 (Kijun)", "int", 26, 5, 200, 1),
            StrategyParam("senkou_b_period", "先行帶B週期 (Senkou B)", "int", 52, 10, 500, 1),
            StrategyParam("ema_period", "EMA 濾網週期", "int", 200, 0, 500, 1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]

        tenkan_p = p["tenkan_period"]
        kijun_p = p["kijun_period"]
        senkou_b_p = p["senkou_b_period"]
        ema_p = p["ema_period"]

        # --- Ichimoku components ---
        # Tenkan-sen (Conversion Line)
        tenkan = (high.rolling(tenkan_p).max() + low.rolling(tenkan_p).min()) / 2

        # Kijun-sen (Base Line)
        kijun = (high.rolling(kijun_p).max() + low.rolling(kijun_p).min()) / 2

        # Senkou Span A (Leading Span A) – shifted forward by kijun_period
        senkou_a = ((tenkan + kijun) / 2).shift(kijun_p)

        # Senkou Span B (Leading Span B) – shifted forward by kijun_period
        senkou_b = (
            (high.rolling(senkou_b_p).max() + low.rolling(senkou_b_p).min()) / 2
        ).shift(kijun_p)

        # Cloud boundaries
        cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
        cloud_bottom = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)

        # --- EMA trend filter ---
        if ema_p > 0:
            ema = vbt.MA.run(close, ema_p, ewm=True).ma
            ema_long_ok = close > ema
            ema_short_ok = close < ema
        else:
            # ema_period=0 disables the filter
            ema_long_ok = pd.Series(True, index=close.index)
            ema_short_ok = pd.Series(True, index=close.index)

        # --- Signal logic ---
        # Long: price > cloud top AND tenkan > kijun AND price > EMA
        long_cond = (close > cloud_top) & (tenkan > kijun) & ema_long_ok

        # Short: price < cloud bottom AND tenkan < kijun AND price < EMA
        short_cond = (close < cloud_bottom) & (tenkan < kijun) & ema_short_ok

        # Edge-trigger: only fire on state change
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
