"""
=================================================================
 TradeEngine — 全策略優化 & KPI 排名
 針對 BTC/ETH 60分鐘 CSV 資料
=================================================================
"""

import io
import logging
import sys
import time
from pathlib import Path

import pandas as pd

# Fix Windows console encoding for Chinese + special chars
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("optimizer")

# ── 載入 CSV 資料 ──────────────────────────────────────────────

from tradeengine.data.fetcher import load_csv

BASE = Path(__file__).parent

CSV_FILES = {
    "BTC_60m": BASE / "BINANCE_BTCUSD.P, 60.csv",
    "ETH_60m": BASE / "COINBASE_ETHUSD, 60 (1).csv",
}

datasets = {}
for label, path in CSV_FILES.items():
    datasets[label] = load_csv(path)

# ── 載入策略 ────────────────────────────────────────────────────

from tradeengine.strategies.registry import auto_discover, get_strategy, list_strategies

auto_discover()
all_strategies = list_strategies()
strategy_names = [s["name"] for s in all_strategies]

print(f"\n{'='*80}")
print(f"  策略數: {len(strategy_names)} | 資料集: {list(datasets.keys())}")
print(f"{'='*80}\n")

# ── 回測引擎 & 優化設定 ─────────────────────────────────────────

from tradeengine.backtest.engine import BacktestEngine
from tradeengine.backtest.optimizer import (
    OptimizationConfig,
    build_param_grid,
    estimate_combinations,
    optimize,
)

engine = BacktestEngine(
    initial_capital=10000.0,
    fees=0.0005,       # 0.05% (Pionex maker fee)
    slippage=0.0005,   # 0.05%
)

# ── 執行優化 ────────────────────────────────────────────────────

all_results = []

for ds_label, ohlcv in datasets.items():
    print(f"\n{'─'*60}")
    print(f"  資料集: {ds_label}  ({len(ohlcv)} 根K線)")
    print(f"  期間: {ohlcv.index[0].strftime('%Y-%m-%d')} ~ {ohlcv.index[-1].strftime('%Y-%m-%d')}")
    print(f"{'─'*60}")

    for sname in strategy_names:
        strat = get_strategy(sname)
        grid = build_param_grid(strat, step_mult=2.0)  # 粗略網格, 加速
        total_combos = estimate_combinations(grid)

        print(f"\n  ▸ {strat.display_name} ({sname}): {total_combos:,} 組合...", end=" ", flush=True)

        t0 = time.time()
        opt_config = OptimizationConfig(
            param_ranges=grid,
            sort_by="sharpe_ratio",
            top_n=1,
            max_combinations=3000,
            deadline_seconds=180.0,
        )

        try:
            results = optimize(engine, strat, ohlcv, opt_config, freq="1h")
        except Exception as e:
            print(f"FAILED: {e}")
            continue

        elapsed = time.time() - t0

        if results:
            best = results[0]
            m = best.metrics
            all_results.append({
                "dataset": ds_label,
                "strategy": sname,
                "display_name": strat.display_name,
                "params": str(best.params),
                "total_return_pct": m.total_return_pct,
                "annualized_return_pct": m.annualized_return_pct,
                "max_drawdown_pct": m.max_drawdown_pct,
                "sharpe_ratio": m.sharpe_ratio,
                "sortino_ratio": m.sortino_ratio,
                "calmar_ratio": m.calmar_ratio,
                "win_rate": m.win_rate,
                "total_trades": m.total_trades,
                "profit_factor": m.profit_factor,
                "avg_win_pct": m.avg_win_pct,
                "avg_loss_pct": m.avg_loss_pct,
                "best_trade_pct": m.best_trade_pct,
                "worst_trade_pct": m.worst_trade_pct,
                "max_consecutive_wins": m.max_consecutive_wins,
                "max_consecutive_losses": m.max_consecutive_losses,
                "combos_tested": min(total_combos, opt_config.max_combinations),
                "elapsed_sec": round(elapsed, 1),
            })
            print(
                f"OK ({elapsed:.1f}s) | "
                f"Return={m.total_return_pct:+.1f}% | "
                f"Sharpe={m.sharpe_ratio:.2f} | "
                f"DD={m.max_drawdown_pct:.1f}% | "
                f"WR={m.win_rate:.0f}% | "
                f"Trades={m.total_trades}"
            )
        else:
            print(f"NO RESULTS ({elapsed:.1f}s)")

# ── 排名表格 ────────────────────────────────────────────────────

if not all_results:
    print("\n沒有結果可顯示!")
    exit()

df_results = pd.DataFrame(all_results)

# 分別產出 BTC 和 ETH 排名
for ds in ["BTC_60m", "ETH_60m"]:
    subset = df_results[df_results["dataset"] == ds].copy()
    if subset.empty:
        continue

    subset = subset.sort_values("sharpe_ratio", ascending=False).reset_index(drop=True)
    subset.index = subset.index + 1  # 1-based rank

    print(f"\n\n{'='*100}")
    print(f"  {ds} 策略排名 (依 Sharpe Ratio 排序)")
    print(f"{'='*100}")

    # KPI 表格
    display_cols = [
        ("strategy", "策略"),
        ("total_return_pct", "總報酬%"),
        ("annualized_return_pct", "年化%"),
        ("max_drawdown_pct", "最大回撤%"),
        ("sharpe_ratio", "Sharpe"),
        ("sortino_ratio", "Sortino"),
        ("calmar_ratio", "Calmar"),
        ("win_rate", "勝率%"),
        ("total_trades", "交易數"),
        ("profit_factor", "獲利因子"),
        ("avg_win_pct", "平均盈%"),
        ("avg_loss_pct", "平均虧%"),
        ("best_trade_pct", "最佳%"),
        ("worst_trade_pct", "最差%"),
    ]

    # Print header
    header = f"{'#':>3} "
    for col, label in display_cols:
        if col == "strategy":
            header += f"{label:<14}"
        else:
            header += f"{label:>10}"
    print(header)
    print("-" * len(header))

    for rank, (_, row) in enumerate(subset.iterrows(), 1):
        line = f"{rank:>3} "
        for col, label in display_cols:
            val = row[col]
            if col == "strategy":
                line += f"{val:<14}"
            elif col == "total_trades":
                line += f"{int(val):>10}"
            elif col in ("sharpe_ratio", "sortino_ratio", "calmar_ratio", "profit_factor"):
                line += f"{val:>10.2f}"
            else:
                line += f"{val:>10.1f}"
        print(line)

    # 最佳參數
    print(f"\n  最佳參數明細:")
    for _, row in subset.iterrows():
        print(f"    {row['strategy']:<14}: {row['params']}")

# ── 總排名 (跨市場) ─────────────────────────────────────────────

print(f"\n\n{'='*100}")
print(f"  跨市場策略排名 (BTC + ETH 平均 Sharpe Ratio)")
print(f"{'='*100}")

cross = df_results.groupby("strategy").agg({
    "total_return_pct": "mean",
    "annualized_return_pct": "mean",
    "max_drawdown_pct": "mean",
    "sharpe_ratio": "mean",
    "sortino_ratio": "mean",
    "calmar_ratio": "mean",
    "win_rate": "mean",
    "total_trades": "mean",
    "profit_factor": "mean",
}).round(2).sort_values("sharpe_ratio", ascending=False)

cross.index.name = "strategy"
cross = cross.reset_index()

header = f"{'#':>3} {'策略':<14}{'平均報酬%':>10}{'平均回撤%':>10}{'Sharpe':>10}{'Sortino':>10}{'勝率%':>10}{'交易數':>10}{'獲利因子':>10}"
print(header)
print("-" * len(header))

for rank, (_, row) in enumerate(cross.iterrows(), 1):
    print(
        f"{rank:>3} "
        f"{row['strategy']:<14}"
        f"{row['total_return_pct']:>10.1f}"
        f"{row['max_drawdown_pct']:>10.1f}"
        f"{row['sharpe_ratio']:>10.2f}"
        f"{row['sortino_ratio']:>10.2f}"
        f"{row['win_rate']:>10.1f}"
        f"{int(row['total_trades']):>10}"
        f"{row['profit_factor']:>10.2f}"
    )

# ── 儲存結果到 CSV ──────────────────────────────────────────────

output_path = BASE / "data" / "optimization_results.csv"
output_path.parent.mkdir(parents=True, exist_ok=True)
df_results.to_csv(output_path, index=False, encoding="utf-8-sig")
print(f"\n結果已存到: {output_path}")
print(f"完成！\n")
