"""CLI commands for TradeEngine."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="tradeengine",
    help="加密貨幣交易引擎 - Local Crypto Trade Engine",
    no_args_is_help=True,
)
console = Console()


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _load_all():
    """Load config and discover strategies."""
    from tradeengine.config import load_config
    from tradeengine.strategies.registry import auto_discover
    config = load_config()
    auto_discover()
    return config


@app.command()
def backtest(
    strategy: str = typer.Option("ma_crossover", "--strategy", "-s", help="策略名稱"),
    symbol: str = typer.Option("BTC_USDT", "--symbol", help="交易對"),
    timeframe: str = typer.Option("1h", "--timeframe", "-t", help="時間框架"),
    csv: Optional[str] = typer.Option(None, "--csv", help="CSV 檔案路徑 (TradingView 匯出)"),
    limit: int = typer.Option(5000, "--limit", "-l", help="K線數量"),
    capital: float = typer.Option(10000.0, "--capital", "-c", help="初始資金"),
    sl: Optional[float] = typer.Option(None, "--sl", help="停損 % (例: 2.0)"),
    tp: Optional[float] = typer.Option(None, "--tp", help="停利 % (例: 5.0)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """執行策略回測 (Run backtest)"""
    _setup_logging(verbose)
    config = _load_all()

    from tradeengine.backtest.engine import BacktestEngine
    from tradeengine.data.fetcher import DataFetcher, load_csv
    from tradeengine.data.pionex_client import PionexClient
    from tradeengine.data.store import DataStore
    from tradeengine.strategies.registry import get_strategy

    async def _run():
        strat = get_strategy(strategy)
        params = config.strategies.get(strategy, {})

        console.print(f"\n[bold]回測策略:[/bold] {strat.display_name}")

        # Load data from CSV or Pionex
        if csv:
            console.print(f"[bold]CSV 檔案:[/bold] {csv}")
            ohlcv = load_csv(csv)
        else:
            console.print(f"[bold]交易對:[/bold] {symbol} | [bold]時間框架:[/bold] {timeframe}")
            client = PionexClient(config.pionex.api_key, config.pionex.api_secret)
            store = DataStore(config.data.cache_dir)
            fetcher = DataFetcher(client, store)
            with console.status("正在取得市場資料..."):
                ohlcv = await fetcher.fetch(symbol, timeframe, limit=limit)
            await client.close()

        console.print(f"[bold]K線數量:[/bold] {len(ohlcv)} | [bold]初始資金:[/bold] ${capital:,.0f}")
        console.print(f"[bold]期間:[/bold] {ohlcv.index[0]} ~ {ohlcv.index[-1]}\n")

        # Run backtest
        fees = config.trading.fees_pct / 100
        slippage = config.trading.slippage_pct / 100
        engine = BacktestEngine(capital, fees, slippage)

        sl_stop = sl / 100 if sl else None
        tp_stop = tp / 100 if tp else None

        with console.status("正在執行回測..."):
            result = engine.run(strat, ohlcv, params, sl_stop=sl_stop, tp_stop=tp_stop, freq=timeframe)

        # Display results
        m = result.metrics
        table = Table(title="回測結果", show_header=True, header_style="bold cyan")
        table.add_column("指標", style="bold")
        table.add_column("數值", justify="right")

        table.add_row("總報酬率", f"{m.total_return_pct:+.2f}%")
        table.add_row("年化報酬率", f"{m.annualized_return_pct:+.2f}%")
        table.add_row("最大回撤", f"{m.max_drawdown_pct:.2f}%")
        table.add_row("夏普比率", f"{m.sharpe_ratio:.3f}")
        table.add_row("索提諾比率", f"{m.sortino_ratio:.3f}")
        table.add_row("卡爾馬比率", f"{m.calmar_ratio:.3f}")
        table.add_row("勝率", f"{m.win_rate:.1f}%")
        table.add_row("交易次數", str(m.total_trades))
        table.add_row("獲利因子", f"{m.profit_factor:.3f}")
        table.add_row("最佳交易", f"{m.best_trade_pct:+.2f}%")
        table.add_row("最差交易", f"{m.worst_trade_pct:+.2f}%")

        console.print(table)

        # Show params
        console.print(f"\n[bold]參數:[/bold] {params}")

    asyncio.run(_run())


@app.command()
def optimize(
    strategy: str = typer.Option("ma_crossover", "--strategy", "-s", help="策略名稱"),
    symbol: str = typer.Option("BTC_USDT", "--symbol", help="交易對"),
    timeframe: str = typer.Option("1h", "--timeframe", "-t", help="時間框架"),
    csv: Optional[str] = typer.Option(None, "--csv", help="CSV 檔案路徑 (TradingView 匯出)"),
    limit: int = typer.Option(5000, "--limit", "-l", help="K線數量"),
    capital: float = typer.Option(10000.0, "--capital", "-c", help="初始資金"),
    sort_by: str = typer.Option("sharpe_ratio", "--sort", help="排序指標"),
    top_n: int = typer.Option(10, "--top", help="顯示前N個結果"),
    max_combos: int = typer.Option(5000, "--max-combos", help="最大組合數"),
    timeout: float = typer.Option(120.0, "--timeout", help="超時秒數"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """參數優化 (Parameter optimization)"""
    _setup_logging(verbose)
    config = _load_all()

    from tradeengine.backtest.engine import BacktestEngine
    from tradeengine.backtest.optimizer import OptimizationConfig, build_param_grid, estimate_combinations, optimize as run_optimize
    from tradeengine.data.fetcher import DataFetcher, load_csv
    from tradeengine.data.pionex_client import PionexClient
    from tradeengine.data.store import DataStore
    from tradeengine.strategies.registry import get_strategy

    async def _run():
        strat = get_strategy(strategy)
        grid = build_param_grid(strat)
        total = estimate_combinations(grid)

        console.print(f"\n[bold]優化策略:[/bold] {strat.display_name}")
        console.print(f"[bold]參數組合:[/bold] {total:,} | [bold]最大測試:[/bold] {max_combos:,}")
        console.print(f"[bold]排序指標:[/bold] {sort_by}\n")

        # Load data from CSV or Pionex
        if csv:
            ohlcv = load_csv(csv)
        else:
            client = PionexClient(config.pionex.api_key, config.pionex.api_secret)
            store = DataStore(config.data.cache_dir)
            fetcher = DataFetcher(client, store)
            with console.status("正在取得市場資料..."):
                ohlcv = await fetcher.fetch(symbol, timeframe, limit=limit)
            await client.close()

        console.print(f"K線數量: {len(ohlcv)}\n")

        # Optimize
        fees = config.trading.fees_pct / 100
        slippage = config.trading.slippage_pct / 100
        engine = BacktestEngine(capital, fees, slippage)

        opt_config = OptimizationConfig(
            param_ranges=grid,
            sort_by=sort_by,
            top_n=top_n,
            max_combinations=max_combos,
            deadline_seconds=timeout,
        )

        with console.status("正在進行參數優化..."):
            results = run_optimize(engine, strat, ohlcv, opt_config, freq=timeframe)

        # Display results table
        table = Table(title=f"優化結果 Top {len(results)}", show_header=True, header_style="bold cyan")
        table.add_column("#", justify="right", style="dim")
        table.add_column("參數")
        table.add_column("報酬率", justify="right")
        table.add_column("夏普", justify="right")
        table.add_column("回撤", justify="right")
        table.add_column("勝率", justify="right")
        table.add_column("交易數", justify="right")
        table.add_column("獲利因子", justify="right")

        for i, r in enumerate(results, 1):
            m = r.metrics
            params_str = ", ".join(f"{k}={v}" for k, v in r.params.items())
            table.add_row(
                str(i),
                params_str,
                f"{m.total_return_pct:+.1f}%",
                f"{m.sharpe_ratio:.2f}",
                f"{m.max_drawdown_pct:.1f}%",
                f"{m.win_rate:.0f}%",
                str(m.total_trades),
                f"{m.profit_factor:.2f}",
            )

        console.print(table)

    asyncio.run(_run())


@app.command()
def live(
    strategy: str = typer.Option(..., "--strategy", "-s", help="策略名稱"),
    symbol: str = typer.Option("BTC_USDT", "--symbol", help="交易對"),
    timeframe: str = typer.Option("1h", "--timeframe", "-t", help="時間框架"),
    paper: bool = typer.Option(False, "--paper", "-p", help="模擬交易模式"),
    capital: float = typer.Option(10000.0, "--capital", "-c", help="初始資金"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """啟動即時交易 (Start live trading)"""
    _setup_logging(verbose)
    config = _load_all()

    from tradeengine.data.pionex_client import PionexClient
    from tradeengine.strategies.registry import get_strategy
    from tradeengine.trading.engine import LiveTradingEngine
    from tradeengine.trading.paper_executor import PaperExecutor
    from tradeengine.trading.pionex_executor import PionexExecutor
    from tradeengine.trading.risk_manager import RiskConfig

    async def _run():
        strat = get_strategy(strategy)
        params = config.strategies.get(strategy, {})
        client = PionexClient(config.pionex.api_key, config.pionex.api_secret)

        mode = "模擬交易" if paper else "即時交易"
        console.print(f"\n[bold red]{'='*50}[/bold red]")
        console.print(f"[bold]{mode}模式[/bold]")
        console.print(f"策略: {strat.display_name}")
        console.print(f"交易對: {symbol} | 時間框架: {timeframe}")
        console.print(f"[bold red]{'='*50}[/bold red]\n")

        if paper:
            executor = PaperExecutor(capital)
        else:
            if not config.pionex.api_key:
                console.print("[red]錯誤: 未設置 Pionex API Key (.env)[/red]")
                return
            executor = PionexExecutor(client)
            console.print("[bold yellow]警告: 即時交易模式 - 真實資金[/bold yellow]")

        risk_config = RiskConfig(
            max_drawdown_pct=config.trading.max_drawdown_pct,
            max_position_pct=config.trading.max_position_pct,
        )

        engine = LiveTradingEngine(
            strategy=strat,
            executor=executor,
            client=client,
            symbol=symbol,
            timeframe=timeframe,
            params=params,
            risk_config=risk_config,
            initial_capital=capital,
        )

        try:
            await engine.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]正在停止交易引擎...[/yellow]")
            await engine.stop()
        finally:
            await client.close()

    asyncio.run(_run())


@app.command()
def paper(
    strategy: str = typer.Option(..., "--strategy", "-s", help="策略名稱"),
    symbol: str = typer.Option("BTC_USDT", "--symbol", help="交易對"),
    timeframe: str = typer.Option("1h", "--timeframe", "-t", help="時間框架"),
    capital: float = typer.Option(10000.0, "--capital", "-c", help="初始資金"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """啟動模擬交易 (Start paper trading)"""
    # Delegate to live with paper=True
    live(strategy=strategy, symbol=symbol, timeframe=timeframe, paper=True, capital=capital, verbose=verbose)


@app.command()
def strategies():
    """列出所有可用策略 (List all strategies)"""
    _load_all()
    from tradeengine.strategies.registry import list_strategies

    strats = list_strategies()
    table = Table(title="可用策略", show_header=True, header_style="bold cyan")
    table.add_column("名稱", style="bold")
    table.add_column("顯示名稱")
    table.add_column("說明")
    table.add_column("參數數量", justify="right")

    for s in strats:
        table.add_row(s["name"], s["display_name"], s["description"], str(len(s["parameters"])))

    console.print(table)


@app.command()
def cache():
    """顯示本地快取資料 (Show cached data)"""
    config = _load_all()
    from tradeengine.data.store import DataStore

    store = DataStore(config.data.cache_dir)
    cached = store.list_cached()

    if not cached:
        console.print("[yellow]尚無快取資料[/yellow]")
        return

    table = Table(title="本地快取資料", show_header=True, header_style="bold cyan")
    table.add_column("交易對")
    table.add_column("時間框架")
    table.add_column("K線數量", justify="right")

    for c in cached:
        table.add_row(c["symbol"], c["timeframe"], f"{c['candles']:,}")

    console.print(table)


@app.command()
def dashboard(
    port: int = typer.Option(int(os.environ.get("PORT", os.environ.get("DASHBOARD_PORT", "8000"))), "--port", "-p", help="端口"),
):
    """啟動 Web 儀表板 (Start web dashboard)"""
    _load_all()
    import uvicorn
    from tradeengine.dashboard.app import create_app

    console.print(f"\n[bold]啟動儀表板: http://localhost:{port}[/bold]\n")
    app_instance = create_app()
    uvicorn.run(app_instance, host="0.0.0.0", port=port)


if __name__ == "__main__":
    app()
