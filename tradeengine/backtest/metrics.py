"""Extract performance metrics from vectorBT Portfolio."""

from __future__ import annotations

import numpy as np

from tradeengine.data.models import BacktestMetrics


def extract_metrics(portfolio) -> BacktestMetrics:
    """Extract comprehensive metrics from a vectorbt Portfolio object."""
    stats = portfolio.stats()

    total_return = _safe_float(portfolio.total_return()) * 100
    max_dd = _safe_float(portfolio.max_drawdown()) * 100

    # Sharpe & Sortino
    sharpe = _safe_float(portfolio.sharpe_ratio())
    sortino = _safe_float(portfolio.sortino_ratio())

    # Calmar
    calmar = abs(total_return / max_dd) if max_dd != 0 else 0.0

    # Trade stats
    trades = portfolio.trades.records_readable if hasattr(portfolio.trades, 'records_readable') else None
    total_trades = int(stats.get("Total Trades", 0))
    win_rate = _safe_float(stats.get("Win Rate [%]", 0))

    profit_factor = _safe_float(stats.get("Profit Factor", 0))
    avg_trade = _safe_float(stats.get("Avg Winning Trade [%]", 0)) if win_rate > 50 else _safe_float(stats.get("Avg Losing Trade [%]", 0))

    best_trade = _safe_float(stats.get("Best Trade [%]", 0))
    worst_trade = _safe_float(stats.get("Worst Trade [%]", 0))
    avg_win = _safe_float(stats.get("Avg Winning Trade [%]", 0))
    avg_loss = _safe_float(stats.get("Avg Losing Trade [%]", 0))
    max_wins = int(stats.get("Max Consecutive Wins", 0)) if "Max Consecutive Wins" in stats else 0
    max_losses = int(stats.get("Max Consecutive Losses", 0)) if "Max Consecutive Losses" in stats else 0

    # Annualized return
    ann_return = _safe_float(stats.get("Annualized Return [%]", 0))

    return BacktestMetrics(
        total_return_pct=round(total_return, 2),
        annualized_return_pct=round(ann_return, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 3),
        sortino_ratio=round(sortino, 3),
        calmar_ratio=round(calmar, 3),
        win_rate=round(win_rate, 1),
        total_trades=total_trades,
        profit_factor=round(profit_factor, 3),
        avg_trade_pct=round(avg_trade, 2),
        best_trade_pct=round(best_trade, 2),
        worst_trade_pct=round(worst_trade, 2),
        avg_win_pct=round(avg_win, 2),
        avg_loss_pct=round(avg_loss, 2),
        max_consecutive_wins=max_wins,
        max_consecutive_losses=max_losses,
    )


def _safe_float(val) -> float:
    """Safely convert to float, handling NaN/None."""
    if val is None:
        return 0.0
    try:
        f = float(val)
        return 0.0 if np.isnan(f) or np.isinf(f) else f
    except (ValueError, TypeError):
        return 0.0
