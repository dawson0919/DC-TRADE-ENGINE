"""Parameter optimization using vectorBT broadcasting and grid/random search."""

from __future__ import annotations

import itertools
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from tradeengine.backtest.engine import BacktestEngine, BacktestResult
from tradeengine.strategies.base import BaseStrategy, StrategyParam

logger = logging.getLogger(__name__)


@dataclass
class OptimizationConfig:
    """Configuration for parameter optimization."""

    param_ranges: dict[str, list[Any]]  # param_name -> list of values to try
    sort_by: str = "sharpe_ratio"
    top_n: int = 10
    max_combinations: int = 5000
    deadline_seconds: float = 120.0  # Max time for optimization


def build_param_grid(strategy: BaseStrategy, step_mult: float = 1.0) -> dict[str, list[Any]]:
    """Build a parameter grid from strategy parameter definitions.

    Args:
        strategy: strategy with parameter definitions
        step_mult: multiplier for step size (>1 = coarser grid, <1 = finer)
    """
    grid: dict[str, list[Any]] = {}
    for p in strategy.parameters():
        if p.type == "select":
            grid[p.name] = p.options if p.options else [p.default]
        elif p.min_val is not None and p.max_val is not None and p.step is not None:
            step = p.step * step_mult
            if p.type == "int":
                grid[p.name] = list(range(int(p.min_val), int(p.max_val) + 1, max(1, int(step))))
            else:
                vals = np.arange(p.min_val, p.max_val + step / 2, step).tolist()
                grid[p.name] = [round(v, 4) for v in vals]
        else:
            grid[p.name] = [p.default]
    return grid


def estimate_combinations(grid: dict[str, list[Any]]) -> int:
    """Estimate total number of parameter combinations."""
    total = 1
    for values in grid.values():
        total *= len(values)
    return total


def optimize(
    engine: BacktestEngine,
    strategy: BaseStrategy,
    ohlcv: pd.DataFrame,
    config: OptimizationConfig,
    freq: str = "1h",
) -> list[BacktestResult]:
    """Run parameter optimization.

    Uses full grid search if combinations <= max_combinations,
    otherwise random sampling.
    """
    grid = config.param_ranges
    total = estimate_combinations(grid)
    logger.info(f"Optimization: {total} total combinations, max={config.max_combinations}")

    # Generate parameter combinations
    keys = list(grid.keys())
    if total <= config.max_combinations:
        # Full grid search
        combos = [dict(zip(keys, vals)) for vals in itertools.product(*[grid[k] for k in keys])]
    else:
        # Random sampling
        combos = []
        for _ in range(config.max_combinations):
            combo = {k: random.choice(grid[k]) for k in keys}
            combos.append(combo)
        logger.info(f"Random sampling {config.max_combinations} of {total} combinations")

    results: list[BacktestResult] = []
    deadline = time.time() + config.deadline_seconds

    for i, params in enumerate(combos):
        if time.time() > deadline:
            logger.warning(f"Optimization deadline reached after {i}/{len(combos)} combinations")
            break

        try:
            result = engine.run(strategy, ohlcv, params, freq=freq)
            results.append(result)
        except Exception as e:
            logger.debug(f"Params {params} failed: {e}")

        if (i + 1) % 100 == 0:
            logger.info(f"Progress: {i + 1}/{len(combos)} combinations tested")

    # Sort by metric
    results.sort(key=lambda r: getattr(r.metrics, config.sort_by, 0), reverse=True)
    return results[: config.top_n]
