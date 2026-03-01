"""Backtest & Optimize: Donchian + SuperTrend dual-channel strategy on PAXG_USDT 4H."""

from __future__ import annotations

import asyncio
import itertools
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from tradeengine.config import load_config
from tradeengine.strategies.registry import auto_discover, get_strategy
from tradeengine.backtest.engine import BacktestEngine, BacktestResult
from tradeengine.backtest.optimizer import OptimizationConfig, build_param_grid, estimate_combinations, optimize
from tradeengine.data.fetcher import DataFetcher
from tradeengine.data.pionex_client import PionexClient
from tradeengine.data.store import DataStore

console = Console()

SYMBOL = "PAXG_USDT"
TIMEFRAME = "4h"
FREQ = "4h"
LIMIT = 5000
CAPITAL = 10000.0


async def fetch_data(config) -> pd.DataFrame:
    """Fetch OHLCV data from Pionex."""
    client = PionexClient(config.pionex.api_key, config.pionex.api_secret)
    store = DataStore(config.data.cache_dir)
    fetcher = DataFetcher(client, store)
    try:
        with console.status(f"[bold]正在取得 {SYMBOL} {TIMEFRAME} 市場資料..."):
            ohlcv = await fetcher.fetch(SYMBOL, TIMEFRAME, limit=LIMIT)
        return ohlcv
    finally:
        await client.close()


def run_default_backtest(engine: BacktestEngine, strategy, ohlcv: pd.DataFrame) -> BacktestResult:
    """Run backtest with default parameters."""
    default_params = {p.name: p.default for p in strategy.parameters()}
    return engine.run(strategy, ohlcv, default_params, freq=FREQ)


def run_optimization(engine: BacktestEngine, strategy, ohlcv: pd.DataFrame) -> list[BacktestResult]:
    """Run parameter optimization."""
    grid = build_param_grid(strategy)
    total = estimate_combinations(grid)

    console.print(f"\n[bold cyan]參數優化空間:[/bold cyan] {total:,} 組合")
    for k, v in grid.items():
        console.print(f"  {k}: {v}")

    opt_config = OptimizationConfig(
        param_ranges=grid,
        sort_by="sharpe_ratio",
        top_n=15,
        max_combinations=5000,
        deadline_seconds=300.0,
    )

    with console.status("[bold]正在進行參數優化..."):
        t0 = time.time()
        results = optimize(engine, strategy, ohlcv, opt_config, freq=FREQ)
        elapsed = time.time() - t0

    console.print(f"[green]優化完成！[/green] 耗時 {elapsed:.1f} 秒\n")
    return results


def print_single_result(result: BacktestResult, title: str):
    """Print detailed backtest result."""
    m = result.metrics
    table = Table(title=title, show_header=True, header_style="bold cyan", width=60)
    table.add_column("指標", style="bold", width=25)
    table.add_column("數值", justify="right", width=25)

    table.add_row("總報酬率", f"{m.total_return_pct:+.2f}%")
    table.add_row("年化報酬率", f"{m.annualized_return_pct:+.2f}%")
    table.add_row("最大回撤", f"{m.max_drawdown_pct:.2f}%")
    table.add_row("夏普比率", f"{m.sharpe_ratio:.3f}")
    table.add_row("索提諾比率", f"{m.sortino_ratio:.3f}")
    table.add_row("卡爾馬比率", f"{m.calmar_ratio:.3f}")
    table.add_row("勝率", f"{m.win_rate:.1f}%")
    table.add_row("交易次數", str(m.total_trades))
    table.add_row("獲利因子", f"{m.profit_factor:.3f}")
    table.add_row("平均獲利", f"{m.avg_win_pct:+.2f}%")
    table.add_row("平均虧損", f"{m.avg_loss_pct:+.2f}%")
    table.add_row("最佳交易", f"{m.best_trade_pct:+.2f}%")
    table.add_row("最差交易", f"{m.worst_trade_pct:+.2f}%")
    table.add_row("最大連勝", str(m.max_consecutive_wins))
    table.add_row("最大連敗", str(m.max_consecutive_losses))

    console.print(table)
    params_str = ", ".join(f"{k}={v}" for k, v in result.params.items())
    console.print(f"  [bold]參數:[/bold] {params_str}\n")


def print_optimization_table(results: list[BacktestResult]):
    """Print top optimization results."""
    table = Table(
        title=f"優化結果 Top {len(results)} (按夏普比率排序)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("進場週期", justify="right", width=7)
    table.add_column("出場週期", justify="right", width=7)
    table.add_column("ST週期", justify="right", width=7)
    table.add_column("ST倍數", justify="right", width=7)
    table.add_column("報酬率", justify="right", width=10)
    table.add_column("年化", justify="right", width=10)
    table.add_column("夏普", justify="right", width=8)
    table.add_column("回撤", justify="right", width=8)
    table.add_column("勝率", justify="right", width=7)
    table.add_column("交易數", justify="right", width=6)
    table.add_column("獲利因子", justify="right", width=8)

    for i, r in enumerate(results, 1):
        m = r.metrics
        style = "bold green" if i == 1 else ""
        table.add_row(
            str(i),
            str(r.params.get("entry_period", "")),
            str(r.params.get("exit_period", "")),
            str(r.params.get("st_period", "")),
            str(r.params.get("st_multiplier", "")),
            f"{m.total_return_pct:+.1f}%",
            f"{m.annualized_return_pct:+.1f}%",
            f"{m.sharpe_ratio:.2f}",
            f"{m.max_drawdown_pct:.1f}%",
            f"{m.win_rate:.0f}%",
            str(m.total_trades),
            f"{m.profit_factor:.2f}",
            style=style,
        )

    console.print(table)


async def main():
    config = load_config()
    auto_discover()

    strategy = get_strategy("donchian_supertrend")

    # Header
    console.print(Panel(
        Text.from_markup(
            f"[bold]{strategy.display_name}[/bold]\n"
            f"交易對: {SYMBOL} | 時間框架: {TIMEFRAME}\n"
            f"初始資金: ${CAPITAL:,.0f}"
        ),
        title="回測報告",
        border_style="cyan",
    ))

    # 1. Fetch data
    ohlcv = await fetch_data(config)
    console.print(f"[bold]K線數量:[/bold] {len(ohlcv)}")
    console.print(f"[bold]期間:[/bold] {ohlcv.index[0]} ~ {ohlcv.index[-1]}\n")

    fees = config.trading.fees_pct / 100
    slippage = config.trading.slippage_pct / 100
    engine = BacktestEngine(CAPITAL, fees, slippage)

    # 2. Default params backtest
    console.rule("[bold cyan]Phase 1: 預設參數回測")
    default_result = run_default_backtest(engine, strategy, ohlcv)
    print_single_result(default_result, "預設參數回測結果")

    # 3. Optimization
    console.rule("[bold cyan]Phase 2: 參數優化")
    opt_results = run_optimization(engine, strategy, ohlcv)
    print_optimization_table(opt_results)

    # 4. Best result detail
    if opt_results:
        console.rule("[bold cyan]Phase 3: 最佳參數回測詳情")
        best = opt_results[0]
        print_single_result(best, "最佳參數回測結果")

        # Compare default vs best
        console.rule("[bold cyan]預設 vs 最佳 對比")
        comp_table = Table(show_header=True, header_style="bold cyan", width=60)
        comp_table.add_column("指標", style="bold", width=20)
        comp_table.add_column("預設參數", justify="right", width=18)
        comp_table.add_column("最佳參數", justify="right", width=18)

        dm = default_result.metrics
        bm = best.metrics
        rows = [
            ("總報酬率", f"{dm.total_return_pct:+.2f}%", f"{bm.total_return_pct:+.2f}%"),
            ("年化報酬率", f"{dm.annualized_return_pct:+.2f}%", f"{bm.annualized_return_pct:+.2f}%"),
            ("最大回撤", f"{dm.max_drawdown_pct:.2f}%", f"{bm.max_drawdown_pct:.2f}%"),
            ("夏普比率", f"{dm.sharpe_ratio:.3f}", f"{bm.sharpe_ratio:.3f}"),
            ("索提諾比率", f"{dm.sortino_ratio:.3f}", f"{bm.sortino_ratio:.3f}"),
            ("勝率", f"{dm.win_rate:.1f}%", f"{bm.win_rate:.1f}%"),
            ("交易次數", str(dm.total_trades), str(bm.total_trades)),
            ("獲利因子", f"{dm.profit_factor:.3f}", f"{bm.profit_factor:.3f}"),
        ]
        for label, dv, bv in rows:
            comp_table.add_row(label, dv, bv)
        console.print(comp_table)

        # Best params summary
        console.print(Panel(
            Text.from_markup(
                f"[bold green]建議最佳參數:[/bold green]\n"
                + "\n".join(f"  {k} = {v}" for k, v in best.params.items())
            ),
            title="結論",
            border_style="green",
        ))


if __name__ == "__main__":
    asyncio.run(main())
