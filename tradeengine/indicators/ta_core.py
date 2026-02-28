"""Custom indicators not built into vectorBT."""

from __future__ import annotations

import numpy as np
import pandas as pd


def donchian_channel(
    high: pd.Series, low: pd.Series, period: int
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Donchian Channel.

    Returns (upper, lower, middle).
    """
    upper = high.rolling(window=period).max()
    lower = low.rolling(window=period).min()
    middle = (upper + lower) / 2
    return upper, lower, middle


def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int, multiplier: float
) -> tuple[pd.Series, pd.Series]:
    """Calculate SuperTrend indicator.

    Returns (supertrend_line, direction) where direction is 1=up, -1=down.
    """
    from tradeengine.strategies.builtin.supertrend import calc_supertrend
    return calc_supertrend(high, low, close, period, multiplier)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Average True Range."""
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average Directional Index."""
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr_val = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_val)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_val)

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di) * 100
    adx_val = dx.rolling(window=period).mean()
    return adx_val
