"""超籃自在極意多空突破策略 (Consecutive Breakout Strategy).

Based on TradingView Pine Script by Dawson0919.
Core idea: Use configurable MA as trend filter, then enter on consecutive
up/down bars with different thresholds depending on bull/bear zone.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from tradeengine.strategies.base import BaseStrategy, SignalOutput, StrategyParam
from tradeengine.strategies.registry import register_strategy


# ─── Custom MA functions ─────────────────────────────────────────────

def _smma(src: pd.Series, length: int) -> pd.Series:
    """Smoothed Moving Average (SMMA / RMA)."""
    result = src.copy() * np.nan
    # Seed with SMA
    result.iloc[length - 1] = src.iloc[:length].mean()
    for i in range(length, len(src)):
        result.iloc[i] = (result.iloc[i - 1] * (length - 1) + src.iloc[i]) / length
    return result


def _wma(src: pd.Series, length: int) -> pd.Series:
    """Weighted Moving Average (linear weights)."""
    weights = np.arange(1, length + 1, dtype=float)
    return src.rolling(window=length).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def _hma(src: pd.Series, length: int) -> pd.Series:
    """Hull Moving Average."""
    half_len = max(1, length // 2)
    sqrt_len = max(1, int(math.sqrt(length)))
    wma_half = _wma(src, half_len)
    wma_full = _wma(src, length)
    diff = 2 * wma_half - wma_full
    return _wma(diff, sqrt_len)


def _tma(src: pd.Series, length: int) -> pd.Series:
    """Triangular Moving Average (SMA of SMA)."""
    sma1 = src.rolling(window=length).mean()
    return sma1.rolling(window=length).mean()


def _calc_ma(close: pd.Series, ma_type: str, length: int) -> pd.Series:
    """Calculate MA of the requested type."""
    if ma_type == "EMA":
        return close.ewm(span=length, adjust=False).mean()
    elif ma_type == "WMA":
        return _wma(close, length)
    elif ma_type == "SMMA":
        return _smma(close, length)
    elif ma_type == "HMA":
        return _hma(close, length)
    elif ma_type == "TMA":
        return _tma(close, length)
    else:  # SMA
        return close.rolling(window=length).mean()


# ─── Consecutive bar counting (vectorized) ────────────────────────────

def _consecutive_count(condition: pd.Series) -> pd.Series:
    """Count consecutive True values. Resets to 0 on False.

    Example: [F, T, T, T, F, T] → [0, 1, 2, 3, 0, 1]
    """
    # Groups break each time condition is False
    groups = (~condition).cumsum()
    return condition.groupby(groups).cumcount()


# ─── Strategy ─────────────────────────────────────────────────────────

@register_strategy
class ConsecutiveBreakoutStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "consecutive_breakout"

    @property
    def display_name(self) -> str:
        return "超籃自在極意多空突破"

    @property
    def description(self) -> str:
        return (
            "根據價格相對均線位置，以不同連續K線條數閾值判斷多空進場。"
            "多頭區與空頭區各有獨立的連漲/連跌參數。"
        )

    def parameters(self) -> list[StrategyParam]:
        return [
            StrategyParam("ma_type", "均線類型", "select", "SMA",
                          options=["SMA", "EMA", "WMA", "HMA", "SMMA", "TMA"]),
            StrategyParam("ma_length", "均線週期", "int", 25, 5, 200, 1),
            StrategyParam("bull_bars_up", "多頭區連漲進多條數", "int", 1, 1, 10, 1),
            StrategyParam("bull_bars_down", "多頭區連跌進空條數", "int", 4, 1, 10, 1),
            StrategyParam("bear_bars_up", "空頭區連漲進多條數", "int", 2, 1, 10, 1),
            StrategyParam("bear_bars_down", "空頭區連跌進空條數", "int", 2, 1, 10, 1),
            StrategyParam("exit_bars", "反向連續條數平倉", "int", 3, 1, 10, 1),
            StrategyParam("use_ma_exit", "均線反穿平倉", "select", "yes",
                          options=["yes", "no"]),
        ]

    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        p = self.validate_params(params)
        close = ohlcv["close"]

        # 1. Calculate MA
        ma = _calc_ma(close, p["ma_type"], p["ma_length"])

        # 2. Consecutive up/down bar counts
        is_up = close > close.shift(1)
        is_down = close < close.shift(1)
        ups = _consecutive_count(is_up)
        dns = _consecutive_count(is_down)

        # 3. Bull/Bear zone
        bull_zone = close > ma
        bear_zone = ~bull_zone

        # 4. Dynamic thresholds based on zone
        up_thresh = bull_zone.map({True: p["bull_bars_up"], False: p["bear_bars_up"]}).astype(int)
        down_thresh = bull_zone.map({True: p["bull_bars_down"], False: p["bear_bars_down"]}).astype(int)

        # Raw conditions: consecutive bars meet threshold
        long_cond = ups >= up_thresh
        short_cond = dns >= down_thresh

        # Only trigger on the first bar that meets threshold (edge detection)
        prev_ups = ups.shift(1).fillna(0)
        prev_dns = dns.shift(1).fillna(0)
        prev_up_thresh = up_thresh.shift(1).fillna(1)
        prev_down_thresh = down_thresh.shift(1).fillna(1)

        entries_long = long_cond & ~(prev_ups >= prev_up_thresh)
        entries_short = short_cond & ~(prev_dns >= prev_down_thresh)

        # 5. Exit signals
        exit_bars = p["exit_bars"]
        use_ma_exit = p["use_ma_exit"] == "yes"

        # Exit on consecutive opposite bars
        exits_long = dns >= exit_bars
        exits_short = ups >= exit_bars

        # Optional: MA crossover exit
        if use_ma_exit:
            ma_cross_down = (close < ma) & (close.shift(1) >= ma.shift(1))
            ma_cross_up = (close > ma) & (close.shift(1) <= ma.shift(1))
            exits_long = exits_long | ma_cross_down
            exits_short = exits_short | ma_cross_up

        return SignalOutput(
            entries_long=entries_long.fillna(False),
            exits_long=exits_long.fillna(False),
            entries_short=entries_short.fillna(False),
            exits_short=exits_short.fillna(False),
        )
