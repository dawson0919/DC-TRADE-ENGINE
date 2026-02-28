"""Tests for strategy framework."""

import numpy as np
import pandas as pd
import pytest


def _make_ohlcv(n: int = 500) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=n, freq="1h", tz="UTC")
    close = 30000 + np.cumsum(np.random.randn(n) * 100)
    high = close + np.abs(np.random.randn(n) * 50)
    low = close - np.abs(np.random.randn(n) * 50)
    open_ = close + np.random.randn(n) * 30
    volume = np.abs(np.random.randn(n) * 1000) + 100

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "timestamp": [int(d.timestamp() * 1000) for d in dates],
    }, index=dates)


class TestStrategyRegistry:
    def test_auto_discover(self):
        from tradeengine.strategies.registry import auto_discover, list_strategies
        auto_discover()
        strats = list_strategies()
        assert len(strats) >= 7  # 7 built-in strategies
        names = [s["name"] for s in strats]
        assert "ma_crossover" in names
        assert "rsi" in names
        assert "macd" in names
        assert "bollinger" in names
        assert "donchian" in names
        assert "supertrend" in names
        assert "combined" in names

    def test_get_strategy(self):
        from tradeengine.strategies.registry import auto_discover, get_strategy
        auto_discover()
        strat = get_strategy("ma_crossover")
        assert strat.name == "ma_crossover"
        assert len(strat.parameters()) > 0


class TestMACrossover:
    def test_generate_signals(self):
        from tradeengine.strategies.registry import auto_discover, get_strategy
        auto_discover()
        strat = get_strategy("ma_crossover")
        ohlcv = _make_ohlcv()
        signals = strat.generate_signals(ohlcv, {"fast_period": 9, "slow_period": 21, "ma_type": "EMA"})
        assert len(signals.entries_long) == len(ohlcv)
        assert signals.entries_long.dtype == bool
        assert signals.entries_long.any()  # Should have some entries


class TestRSI:
    def test_generate_signals(self):
        from tradeengine.strategies.registry import auto_discover, get_strategy
        auto_discover()
        strat = get_strategy("rsi")
        ohlcv = _make_ohlcv()
        signals = strat.generate_signals(ohlcv, {"period": 14, "oversold": 30, "overbought": 70})
        assert len(signals.entries_long) == len(ohlcv)


class TestBacktestEngine:
    def test_run_backtest(self):
        from tradeengine.backtest.engine import BacktestEngine
        from tradeengine.strategies.registry import auto_discover, get_strategy
        auto_discover()

        strat = get_strategy("ma_crossover")
        ohlcv = _make_ohlcv()
        engine = BacktestEngine(initial_capital=10000, fees=0.001, slippage=0.0005)
        result = engine.run(strat, ohlcv, {"fast_period": 9, "slow_period": 21, "ma_type": "EMA"})

        assert result.metrics.total_trades >= 0
        assert result.equity_curve is not None
        assert len(result.equity_curve) == len(ohlcv)
