"""Backtest engine wrapping vectorBT Portfolio.from_signals()."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import vectorbt as vbt

from tradeengine.backtest.metrics import extract_metrics
from tradeengine.data.models import BacktestMetrics
from tradeengine.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Result of a single backtest run."""

    strategy_name: str
    params: dict[str, Any]
    metrics: BacktestMetrics
    portfolio: Any = field(repr=False)  # vbt.Portfolio object
    equity_curve: pd.Series = field(default=None, repr=False)
    trades_df: pd.DataFrame = field(default=None, repr=False)


class BacktestEngine:
    """Runs strategy backtests using vectorBT.

    Core method: run() takes a strategy + OHLCV data + params,
    generates signals, and simulates via vbt.Portfolio.from_signals().
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        fees: float = 0.0005,
        slippage: float = 0.0005,
    ):
        self.initial_capital = initial_capital
        self.fees = fees
        self.slippage = slippage

    def run(
        self,
        strategy: BaseStrategy,
        ohlcv: pd.DataFrame,
        params: dict[str, Any],
        sl_stop: float | None = None,
        tp_stop: float | None = None,
        freq: str = "1h",
    ) -> BacktestResult:
        """Run a single backtest.

        Args:
            strategy: strategy instance
            ohlcv: DataFrame with OHLCV data and DatetimeIndex
            params: strategy parameters
            sl_stop: stop-loss as fraction (e.g. 0.02 = 2%)
            tp_stop: take-profit as fraction
            freq: candle frequency for annualization

        Returns:
            BacktestResult with metrics, equity curve, trades.
        """
        signals = strategy.generate_signals(ohlcv, params)

        # Build portfolio kwargs
        pf_kwargs: dict[str, Any] = {
            "close": ohlcv["close"],
            "entries": signals.entries_long,
            "exits": signals.exits_long,
            "short_entries": signals.entries_short,
            "short_exits": signals.exits_short,
            "init_cash": self.initial_capital,
            "fees": self.fees,
            "slippage": self.slippage,
            "freq": freq,
        }

        if sl_stop is not None:
            pf_kwargs["sl_stop"] = sl_stop
        if tp_stop is not None:
            pf_kwargs["tp_stop"] = tp_stop

        portfolio = vbt.Portfolio.from_signals(**pf_kwargs)

        metrics = extract_metrics(portfolio)
        equity = portfolio.value()

        # Extract trades DataFrame
        trades_df = None
        try:
            trades_df = portfolio.trades.records_readable
        except Exception:
            pass

        return BacktestResult(
            strategy_name=strategy.name,
            params=params,
            metrics=metrics,
            portfolio=portfolio,
            equity_curve=equity,
            trades_df=trades_df,
        )

    def run_multi(
        self,
        strategy: BaseStrategy,
        ohlcv: pd.DataFrame,
        param_list: list[dict[str, Any]],
        sort_by: str = "sharpe_ratio",
        top_n: int = 10,
        freq: str = "1h",
    ) -> list[BacktestResult]:
        """Run multiple parameter combinations and return top results.

        For small param sets. For large sets, use the optimizer module.
        """
        results = []
        for params in param_list:
            try:
                result = self.run(strategy, ohlcv, params, freq=freq)
                results.append(result)
            except Exception as e:
                logger.warning(f"Backtest failed for params {params}: {e}")

        # Sort by the specified metric
        results.sort(key=lambda r: getattr(r.metrics, sort_by, 0), reverse=True)
        return results[:top_n]
