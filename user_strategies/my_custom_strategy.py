"""
自訂策略範本 (Custom Strategy Template)

複製此文件並修改 generate_signals() 來建立自己的策略。
放在 user_strategies/ 目錄下即可自動載入。

Copy this file and modify generate_signals() to create your own strategy.
Place it in the user_strategies/ directory for auto-discovery.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import vectorbt as vbt

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


# Uncomment the decorator below to activate this strategy
# @register_strategy
class MyCustomStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "my_custom"

    @property
    def display_name(self) -> str:
        return "我的自訂策略"

    @property
    def description(self) -> str:
        return "自訂策略範本 - 修改此文件建立自己的策略"

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("fast_period", "快線週期", "int", 10, 2, 100, 1),
            StrategyParam("slow_period", "慢線週期", "int", 30, 5, 200, 1),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        close = ohlcv["close"]

        # --- 在這裡寫你的策略邏輯 ---
        fast_ma = vbt.MA.run(close, p["fast_period"], ewm=True).ma
        slow_ma = vbt.MA.run(close, p["slow_period"], ewm=True).ma

        entries_long = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
        exits_long = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))
        # --- 策略邏輯結束 ---

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=exits_long.fillna(False),
            exits_short=entries_long.fillna(False),
        )
