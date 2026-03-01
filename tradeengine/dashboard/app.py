"""FastAPI web dashboard application - Multi-user SaaS trading platform."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tradeengine.config import load_config
from tradeengine.strategies.registry import auto_discover, list_strategies, get_strategy

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
CSV_DIR = Path(__file__).parent.parent.parent  # project root for CSVs

# Whether DB is available (set during startup)
_db_available = False


def create_app() -> FastAPI:
    app = FastAPI(title="THE DC'S TRADE ENGINE", version="2.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    auto_discover()
    config = load_config()
    clerk_pk = os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "")

    # Bot manager (singleton)
    from tradeengine.dashboard.bot_manager import BotManager
    bot_manager = BotManager()

    # ─── Startup / Shutdown ──────────────────────────────────────────

    @app.on_event("startup")
    async def startup():
        global _db_available
        supabase_url = os.getenv("SUPABASE_URL", "")
        if supabase_url:
            try:
                from tradeengine.database.connection import init_db
                await init_db()
                _db_available = True
                logger.info("Database connected")
            except Exception as e:
                logger.warning(f"Database init failed (running without DB): {e}")
        else:
            logger.info("SUPABASE_URL not set, running without database")

        # Initialize bot storage with Supabase if available
        if _db_available:
            await bot_manager.init_db()

        # Auto-restart bots that were running before shutdown
        restarted = await bot_manager.auto_restart_bots(app_config=config)
        if restarted:
            logger.info(f"Auto-restarted {len(restarted)} bot(s): {restarted}")

    @app.on_event("shutdown")
    async def shutdown():
        if _db_available:
            from tradeengine.database.connection import close_db
            await close_db()

    # ─── Auth helpers ────────────────────────────────────────────────

    async def _optional_user(request: Request) -> dict | None:
        """Try to extract user from Bearer token. Returns None if auth unavailable."""
        if not _db_available or not clerk_pk:
            return None
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        try:
            from tradeengine.dashboard.auth import verify_clerk_token, _fetch_clerk_user
            from tradeengine.database.connection import get_session
            from tradeengine.database.crud import get_or_create_user

            token = auth_header.split("Bearer ", 1)[1]
            claims = verify_clerk_token(token)
            session = await get_session()
            try:
                email = claims.get("email", "")
                name = claims.get("name", claims.get("first_name", ""))

                # Clerk session JWTs don't include email — fetch from Backend API
                if not email:
                    clerk_user = _fetch_clerk_user(claims["sub"])
                    email = clerk_user.get("email", "")
                    name = name or clerk_user.get("name", "")

                user = await get_or_create_user(
                    session,
                    clerk_id=claims["sub"],
                    email=email,
                    display_name=name,
                )
                if not user.is_active:
                    return None
                return {
                    "user_id": user.clerk_id,
                    "email": user.email,
                    "display_name": user.display_name,
                    "role": user.role,
                    "max_bots": user.max_bots,
                    "is_active": user.is_active,
                }
            finally:
                await session.close()
        except Exception as e:
            logger.warning(f"Auth failed: {e}", exc_info=True)
            return None

    # ─── Discover CSV files ─────────────────────────────────────────

    def find_csv_files() -> list[dict]:
        import re
        csvs = []
        for f in CSV_DIR.glob("*.csv"):
            name = f.stem
            upper = name.upper()
            symbol = "UNKNOWN"
            if "_" in name:
                pair_part = name.split(",")[0].split("_", 1)[-1]
                pair_part = re.sub(r"\.\w+$", "", pair_part)
                symbol = pair_part
            elif "BTC" in upper:
                symbol = "BTCUSD"
            elif "ETH" in upper:
                symbol = "ETHUSD"
            if ", 240" in name or ",240" in name:
                tf = "4h"
            elif ", 60" in name or ",60" in name:
                tf = "1h"
            elif ", 15" in name or ",15" in name:
                tf = "15m"
            elif "1D" in name or "1d" in name:
                tf = "1d"
            else:
                tf = "unknown"
            csvs.append({
                "path": str(f), "filename": f.name,
                "symbol": symbol, "timeframe": tf,
                "label": f"{symbol} {tf} ({f.name})",
            })
        csvs.sort(key=lambda c: (c["symbol"], c["timeframe"]))
        return csvs

    # ─── Pages ───────────────────────────────────────────────────────

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": "2.0.0", "db": _db_available}

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "clerk_publishable_key": clerk_pk,
        })

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        strats = list_strategies()
        csv_files = find_csv_files()
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "strategies": strats,
            "config": config,
            "csv_files": csv_files,
            "clerk_publishable_key": clerk_pk,
            "auth_enabled": _db_available and bool(clerk_pk),
        })

    # ─── Account / User API ──────────────────────────────────────────

    @app.get("/api/account/me")
    async def api_account_me(request: Request):
        user = await _optional_user(request)
        if not user:
            return JSONResponse({"error": "Not authenticated"}, status_code=401)
        return user

    @app.post("/api/account/update")
    async def api_account_update(request: Request):
        user = await _optional_user(request)
        if not user:
            return JSONResponse({"error": "Not authenticated"}, status_code=401)
        data = await request.json()
        display_name = data.get("display_name", "").strip()
        if not display_name:
            return JSONResponse({"error": "顯示名稱不能為空"}, status_code=400)
        from tradeengine.database.connection import get_session
        session = await get_session()
        try:
            session.table("users").update({"display_name": display_name}).eq("clerk_id", user["user_id"]).execute()
            currentUser = user.copy()
            currentUser["display_name"] = display_name
            return {"status": "ok", "display_name": display_name}
        finally:
            await session.close()

    @app.get("/api/account/balance")
    async def api_account_balance(request: Request):
        from tradeengine.data.pionex_client import PionexClient

        # Try user's own API key first (from DB)
        api_key, api_secret = None, None
        user = await _optional_user(request)
        if user and _db_available:
            try:
                from tradeengine.database.connection import get_session
                from tradeengine.database.crud import get_api_credential
                from tradeengine.database.encryption import decrypt_value
                session = await get_session()
                try:
                    cred = await get_api_credential(session, user["user_id"])
                    if cred:
                        api_key = decrypt_value(cred.api_key_encrypted)
                        api_secret = decrypt_value(cred.api_secret_encrypted)
                finally:
                    await session.close()
            except Exception:
                pass

        # Fall back to server config ONLY in local mode (no auth)
        if not api_key and not (_db_available and clerk_pk):
            api_key = config.pionex.api_key
            api_secret = config.pionex.api_secret

        if not api_key or api_key == "your_api_key_here":
            return JSONResponse({"error": "API key not configured"}, status_code=400)

        client = PionexClient(api_key, api_secret)
        try:
            usdt = await client.get_balance("USDT")
            btc = await client.get_balance("BTC")
            eth = await client.get_balance("ETH")
            return {
                "balances": [
                    {"asset": "USDT", "free": usdt["free"], "frozen": usdt["frozen"]},
                    {"asset": "BTC", "free": btc["free"], "frozen": btc["frozen"]},
                    {"asset": "ETH", "free": eth["free"], "frozen": eth["frozen"]},
                ],
                "connected": True,
            }
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        finally:
            await client.close()

    # ─── API Key CRUD ────────────────────────────────────────────────

    @app.get("/api/api-keys")
    async def api_get_keys(request: Request):
        user = await _optional_user(request)
        # Auth mode: check user's DB credential
        if user and _db_available:
            try:
                from tradeengine.database.connection import get_session
                from tradeengine.database.crud import get_api_credential
                session = await get_session()
                try:
                    cred = await get_api_credential(session, user["user_id"])
                    if cred:
                        from tradeengine.database.encryption import decrypt_value
                        raw_key = decrypt_value(cred.api_key_encrypted)
                        preview = raw_key[:6] + "..." + raw_key[-4:] if len(raw_key) > 10 else "***"
                        return {"has_key": True, "key_preview": preview, "label": cred.label}
                    return {"has_key": False}
                finally:
                    await session.close()
            except Exception:
                return {"has_key": False}
        # Local mode (no auth): check server config
        if not (_db_available and clerk_pk):
            key = config.pionex.api_key
            if key and key != "your_api_key_here":
                preview = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
                return {"has_key": True, "key_preview": preview, "label": "伺服器設定檔", "source": "config"}
        return {"has_key": False}

    @app.post("/api/api-keys")
    async def api_save_keys(request: Request):
        user = await _optional_user(request)
        if not user:
            return JSONResponse({"error": "Not authenticated"}, status_code=401)
        if not _db_available:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        data = await request.json()
        api_key = data.get("api_key", "").strip()
        api_secret = data.get("api_secret", "").strip()
        if not api_key or not api_secret:
            return JSONResponse({"error": "API Key and Secret are required"}, status_code=400)

        from tradeengine.database.connection import get_session
        from tradeengine.database.crud import save_api_credential
        from tradeengine.database.encryption import encrypt_value

        session = await get_session()
        try:
            await save_api_credential(
                session,
                user_id=user["user_id"],
                api_key_enc=encrypt_value(api_key),
                api_secret_enc=encrypt_value(api_secret),
            )
            return {"status": "saved"}
        finally:
            await session.close()

    @app.delete("/api/api-keys")
    async def api_delete_keys(request: Request):
        user = await _optional_user(request)
        if not user:
            return JSONResponse({"error": "Not authenticated"}, status_code=401)
        if not _db_available:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        from tradeengine.database.connection import get_session
        from tradeengine.database.crud import delete_api_credential

        session = await get_session()
        try:
            await delete_api_credential(session, user["user_id"])
            return {"status": "deleted"}
        finally:
            await session.close()

    # ─── Strategy API ────────────────────────────────────────────────

    @app.get("/api/strategies")
    async def api_strategies():
        return list_strategies()

    @app.get("/api/strategy/{name}")
    async def api_strategy_detail(name: str):
        try:
            strat = get_strategy(name)
            return {
                "name": strat.name,
                "display_name": strat.display_name,
                "description": strat.description,
                "parameters": [
                    {
                        "name": p.name, "display_name": p.display_name,
                        "type": p.type, "default": p.default,
                        "min": p.min_val, "max": p.max_val,
                        "step": p.step, "options": p.options,
                    }
                    for p in strat.parameters()
                ],
            }
        except KeyError:
            return JSONResponse({"error": f"Strategy '{name}' not found"}, status_code=404)

    # ─── Backtest API ────────────────────────────────────────────────

    def _extract_equity(result) -> list[dict]:
        """Extract equity curve data from a BacktestResult."""
        if result.equity_curve is None:
            return []
        eq = result.equity_curve
        if len(eq) > 500:
            step = max(1, len(eq) // 500)
            eq = eq.iloc[::step]
        return [{"time": str(t), "value": round(float(v), 2)} for t, v in eq.items()]

    def _extract_trades(result) -> list[dict]:
        """Extract trade list from a BacktestResult."""
        if result.trades_df is None or len(result.trades_df) == 0:
            return []
        trades = []
        for _, row in result.trades_df.iterrows():
            trades.append({
                "entry_time": str(row.get("Entry Timestamp", "")),
                "exit_time": str(row.get("Exit Timestamp", "")),
                "direction": str(row.get("Direction", "Long")),
                "size": round(float(row.get("Size", 0)), 6),
                "entry_price": round(float(row.get("Avg Entry Price", 0)), 2),
                "exit_price": round(float(row.get("Avg Exit Price", 0)), 2),
                "pnl": round(float(row.get("PnL", 0)), 2),
                "return_pct": round(float(row.get("Return", 0)) * 100, 2),
            })
        return trades

    @app.get("/api/backtest")
    async def api_backtest(
        request: Request,
        strategy: str = "ma_crossover",
        symbol: str = "BTC_USDT",
        timeframe: str = "1h",
        limit: int = 2000,
        capital: float = 10000.0,
        csv_path: Optional[str] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        params_json: Optional[str] = None,
        oos_pct: int = 0,
    ):
        from tradeengine.backtest.engine import BacktestEngine
        from tradeengine.data.fetcher import DataFetcher, load_csv
        from tradeengine.data.pionex_client import PionexClient
        from tradeengine.data.store import DataStore

        try:
            strat = get_strategy(strategy)
            if params_json:
                try:
                    custom_params = json.loads(params_json)
                except Exception:
                    custom_params = {}
            else:
                custom_params = config.strategies.get(strategy, {})

            if csv_path:
                ohlcv = load_csv(csv_path)
            else:
                client = PionexClient(config.pionex.api_key, config.pionex.api_secret)
                store = DataStore(config.data.cache_dir)
                fetcher = DataFetcher(client, store)
                try:
                    ohlcv = await fetcher.fetch(symbol, timeframe, limit=limit)
                finally:
                    await client.close()

            fees = config.trading.fees_pct / 100
            slippage = config.trading.slippage_pct / 100
            engine = BacktestEngine(capital, fees, slippage)
            sl_stop = sl / 100 if sl else None
            tp_stop = tp / 100 if tp else None

            # Full-period backtest
            result = engine.run(strat, ohlcv, custom_params, sl_stop=sl_stop, tp_stop=tp_stop, freq=timeframe)

            response_data = {
                "strategy": strat.display_name,
                "strategy_name": strat.name,
                "symbol": symbol if not csv_path else Path(csv_path).stem,
                "timeframe": timeframe,
                "params": custom_params,
                "metrics": result.metrics.model_dump(),
                "equity_curve": _extract_equity(result),
                "trades": _extract_trades(result)[-100:],
                "total_candles": len(ohlcv),
                "period": f"{ohlcv.index[0]} ~ {ohlcv.index[-1]}",
                "capital": capital,
            }

            # IS/OOS split
            if oos_pct and 5 <= oos_pct <= 50:
                split_idx = int(len(ohlcv) * (1 - oos_pct / 100))
                ohlcv_is = ohlcv.iloc[:split_idx]
                ohlcv_oos = ohlcv.iloc[split_idx:]
                if len(ohlcv_is) >= 50 and len(ohlcv_oos) >= 20:
                    result_is = engine.run(strat, ohlcv_is, custom_params, sl_stop=sl_stop, tp_stop=tp_stop, freq=timeframe)
                    result_oos = engine.run(strat, ohlcv_oos, custom_params, sl_stop=sl_stop, tp_stop=tp_stop, freq=timeframe)
                    response_data["oos_pct"] = oos_pct
                    response_data["is_metrics"] = result_is.metrics.model_dump()
                    response_data["is_equity_curve"] = _extract_equity(result_is)
                    response_data["is_trades"] = _extract_trades(result_is)[-100:]
                    response_data["is_period"] = f"{ohlcv_is.index[0]} ~ {ohlcv_is.index[-1]}"
                    response_data["is_candles"] = len(ohlcv_is)
                    response_data["oos_metrics"] = result_oos.metrics.model_dump()
                    response_data["oos_equity_curve"] = _extract_equity(result_oos)
                    response_data["oos_trades"] = _extract_trades(result_oos)[-100:]
                    response_data["oos_period"] = f"{ohlcv_oos.index[0]} ~ {ohlcv_oos.index[-1]}"
                    response_data["oos_candles"] = len(ohlcv_oos)

            # Auto-save backtest result for logged-in users
            user = await _optional_user(request)
            if user and _db_available:
                try:
                    from tradeengine.database.connection import get_session
                    from tradeengine.database.crud import save_backtest_result
                    session = await get_session()
                    try:
                        saved = await save_backtest_result(session, user["user_id"], response_data)
                        if saved:
                            response_data["id"] = saved.get("id")
                    finally:
                        await session.close()
                except Exception as e:
                    logger.warning(f"Failed to save backtest result: {e}")

            return response_data
        except Exception as e:
            logger.exception("Backtest failed")
            return JSONResponse({"error": str(e)}, status_code=500)

    # ─── Backtest History API ─────────────────────────────────────────

    @app.get("/api/backtest/history")
    async def api_backtest_history(request: Request):
        """List user's saved backtest results."""
        user = await _optional_user(request)
        if not user:
            return JSONResponse({"error": "請先登入"}, status_code=401)
        try:
            from tradeengine.database.connection import get_session
            from tradeengine.database.crud import list_backtest_results
            session = await get_session()
            try:
                results = await list_backtest_results(session, user["user_id"])
            finally:
                await session.close()
            return {"results": results}
        except Exception as e:
            logger.exception("Failed to list backtest history")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/api/backtest/history/{result_id}")
    async def api_backtest_detail(result_id: int, request: Request):
        """Get a single backtest result with full data."""
        user = await _optional_user(request)
        if not user:
            return JSONResponse({"error": "請先登入"}, status_code=401)
        try:
            from tradeengine.database.connection import get_session
            from tradeengine.database.crud import get_backtest_result
            session = await get_session()
            try:
                result = await get_backtest_result(session, result_id, user["user_id"])
            finally:
                await session.close()
            if not result:
                return JSONResponse({"error": "找不到回測結果"}, status_code=404)
            return result
        except Exception as e:
            logger.exception("Failed to get backtest detail")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.delete("/api/backtest/history/{result_id}")
    async def api_delete_backtest(result_id: int, request: Request):
        """Delete a backtest result."""
        user = await _optional_user(request)
        if not user:
            return JSONResponse({"error": "請先登入"}, status_code=401)
        try:
            from tradeengine.database.connection import get_session
            from tradeengine.database.crud import delete_backtest_result
            session = await get_session()
            try:
                ok = await delete_backtest_result(session, result_id, user["user_id"])
            finally:
                await session.close()
            if ok:
                return {"status": "deleted"}
            return JSONResponse({"error": "刪除失敗"}, status_code=400)
        except Exception as e:
            logger.exception("Failed to delete backtest result")
            return JSONResponse({"error": str(e)}, status_code=500)

    # ─── Optimize API ────────────────────────────────────────────────

    @app.get("/api/optimize")
    async def api_optimize(
        request: Request,
        strategy: str = "ma_crossover",
        symbol: str = "BTC_USDT",
        timeframe: str = "1h",
        limit: int = 3000,
        capital: float = 10000.0,
        csv_path: Optional[str] = None,
        sort_by: str = "sharpe_ratio",
        top_n: int = 10,
        max_combos: int = 2000,
        oos_pct: int = 0,
    ):
        from tradeengine.backtest.engine import BacktestEngine
        from tradeengine.backtest.optimizer import OptimizationConfig, build_param_grid, estimate_combinations, optimize
        from tradeengine.data.fetcher import DataFetcher, load_csv
        from tradeengine.data.pionex_client import PionexClient
        from tradeengine.data.store import DataStore

        try:
            strat = get_strategy(strategy)
            grid = build_param_grid(strat)
            total = estimate_combinations(grid)

            if csv_path:
                ohlcv = load_csv(csv_path)
            else:
                client = PionexClient(config.pionex.api_key, config.pionex.api_secret)
                store = DataStore(config.data.cache_dir)
                fetcher = DataFetcher(client, store)
                try:
                    ohlcv = await fetcher.fetch(symbol, timeframe, limit=limit)
                finally:
                    await client.close()

            fees = config.trading.fees_pct / 100
            slippage = config.trading.slippage_pct / 100
            engine = BacktestEngine(capital, fees, slippage)

            # Decide which data to optimize on
            use_oos = oos_pct and 5 <= oos_pct <= 50
            if use_oos:
                split_idx = int(len(ohlcv) * (1 - oos_pct / 100))
                ohlcv_is = ohlcv.iloc[:split_idx]
                ohlcv_oos = ohlcv.iloc[split_idx:]
            else:
                ohlcv_is = ohlcv

            opt_config = OptimizationConfig(
                param_ranges=grid, sort_by=sort_by,
                top_n=top_n, max_combinations=max_combos,
                deadline_seconds=120.0,
            )
            results = optimize(engine, strat, ohlcv_is, opt_config, freq=timeframe)

            result_rows = []
            for i, r in enumerate(results):
                row = {"rank": i + 1, "params": r.params, "metrics": r.metrics.model_dump()}
                if use_oos:
                    row["is_metrics"] = row["metrics"]
                    try:
                        oos_result = engine.run(strat, ohlcv_oos, r.params, freq=timeframe)
                        row["oos_metrics"] = oos_result.metrics.model_dump()
                    except Exception:
                        row["oos_metrics"] = None
                result_rows.append(row)

            response_data = {
                "strategy": strat.display_name,
                "total_combinations": total,
                "tested": min(total, max_combos),
                "results": result_rows,
            }
            if use_oos:
                response_data["oos_pct"] = oos_pct
                response_data["is_period"] = f"{ohlcv_is.index[0]} ~ {ohlcv_is.index[-1]}"
                response_data["oos_period"] = f"{ohlcv_oos.index[0]} ~ {ohlcv_oos.index[-1]}"

            # Auto-save for logged-in users
            user = await _optional_user(request)
            if user and _db_available:
                try:
                    from tradeengine.database.connection import get_session
                    from tradeengine.database.crud import save_optimize_result
                    session = await get_session()
                    try:
                        saved = await save_optimize_result(session, user["user_id"], {
                            "strategy": strat.display_name,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "sort_by": sort_by,
                            "tested": min(total, max_combos),
                            "total_combinations": total,
                            "results": response_data["results"],
                        })
                        if saved:
                            response_data["id"] = saved["id"]
                    finally:
                        await session.close()
                except Exception:
                    logger.warning("Failed to save optimize result", exc_info=True)

            return response_data
        except Exception as e:
            logger.exception("Optimization failed")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/api/optimize/history")
    async def api_optimize_history(request: Request):
        """List user's saved optimization results."""
        user = await _optional_user(request)
        if not user:
            return JSONResponse({"error": "請先登入"}, status_code=401)
        try:
            from tradeengine.database.connection import get_session
            from tradeengine.database.crud import list_optimize_results
            session = await get_session()
            try:
                results = await list_optimize_results(session, user["user_id"])
            finally:
                await session.close()
            return {"results": results}
        except Exception as e:
            logger.exception("Failed to list optimize history")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/api/optimize/history/{result_id}")
    async def api_optimize_detail(result_id: int, request: Request):
        """Get a single optimization result with full data."""
        user = await _optional_user(request)
        if not user:
            return JSONResponse({"error": "請先登入"}, status_code=401)
        try:
            from tradeengine.database.connection import get_session
            from tradeengine.database.crud import get_optimize_result
            session = await get_session()
            try:
                result = await get_optimize_result(session, result_id, user["user_id"])
            finally:
                await session.close()
            if not result:
                return JSONResponse({"error": "找不到優化結果"}, status_code=404)
            return result
        except Exception as e:
            logger.exception("Failed to get optimize detail")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.delete("/api/optimize/history/{result_id}")
    async def api_delete_optimize(result_id: int, request: Request):
        """Delete an optimization result."""
        user = await _optional_user(request)
        if not user:
            return JSONResponse({"error": "請先登入"}, status_code=401)
        try:
            from tradeengine.database.connection import get_session
            from tradeengine.database.crud import delete_optimize_result
            session = await get_session()
            try:
                ok = await delete_optimize_result(session, result_id, user["user_id"])
            finally:
                await session.close()
            if ok:
                return {"status": "deleted"}
            return JSONResponse({"error": "刪除失敗"}, status_code=400)
        except Exception as e:
            logger.exception("Failed to delete optimize result")
            return JSONResponse({"error": str(e)}, status_code=500)

    # ─── Bot Management API ──────────────────────────────────────────

    @app.get("/api/bots")
    async def api_list_bots(request: Request):
        user = await _optional_user(request)
        # Auth mode: require login to see bots
        if _db_available and clerk_pk and not user:
            return JSONResponse([], status_code=401)
        user_id = user["user_id"] if user else ""
        # Auto-claim legacy bots (no owner) for admin
        if user and user["role"] == "admin":
            claimed = False
            for b in bot_manager.list_bots():  # all bots
                if not b.user_id:
                    b.user_id = user["user_id"]
                    claimed = True
            if claimed:
                bot_manager._save_bots()
        return [_bot_to_dict(b, bot_manager) for b in bot_manager.list_bots(user_id=user_id)]

    @app.post("/api/bots")
    async def api_create_bot(request: Request):
        user = await _optional_user(request)
        user_id = user["user_id"] if user else None

        # Check bot limit
        if user and user["max_bots"] < 999:
            current_bots = len(bot_manager.list_bots(user_id=user_id))
            if current_bots >= user["max_bots"]:
                return JSONResponse(
                    {"error": f"已達機器人上限 ({user['max_bots']}個)，請升級方案或聯繫管理員"},
                    status_code=403,
                )

        data = await request.json()
        signal_source = data.get("signal_source", "strategy")
        bot = bot_manager.create_bot(
            name=data.get("name", "New Bot"),
            strategy=data.get("strategy", "webhook") if signal_source == "webhook" else data["strategy"],
            symbol=data["symbol"],
            timeframe=data.get("timeframe", "") if signal_source == "webhook" else data["timeframe"],
            capital=float(data.get("capital", 10000)),
            params=data.get("params", {}),
            paper_mode=data.get("paper_mode", True),
            sl_pct=float(data["sl_pct"]) if data.get("sl_pct") else None,
            tp_pct=float(data["tp_pct"]) if data.get("tp_pct") else None,
            user_id=user_id,
            signal_source=signal_source,
        )
        return _bot_to_dict(bot, bot_manager)

    @app.put("/api/bots/{bot_id}")
    async def api_update_bot(bot_id: str, request: Request):
        user = await _optional_user(request)
        user_id = user["user_id"] if user else None
        data = await request.json()
        updates = {}
        if "name" in data:
            updates["name"] = data["name"]
        if "strategy" in data:
            updates["strategy"] = data["strategy"]
        if "symbol" in data:
            updates["symbol"] = data["symbol"]
        if "timeframe" in data:
            updates["timeframe"] = data["timeframe"]
        if "capital" in data:
            updates["capital"] = float(data["capital"])
        if "params" in data:
            updates["params"] = data["params"]
        if "paper_mode" in data:
            updates["paper_mode"] = data["paper_mode"]
        if "sl_pct" in data:
            updates["sl_pct"] = float(data["sl_pct"]) if data["sl_pct"] else None
        if "tp_pct" in data:
            updates["tp_pct"] = float(data["tp_pct"]) if data["tp_pct"] else None
        bot = bot_manager.update_bot(bot_id, user_id=user_id or "", **updates)
        if not bot:
            return JSONResponse({"error": "機器人不存在、運行中或無權限"}, status_code=400)
        return _bot_to_dict(bot, bot_manager)

    @app.post("/api/bots/{bot_id}/start")
    async def api_start_bot(bot_id: str, request: Request):
        user = await _optional_user(request)
        user_id = user["user_id"] if user else None
        logger.info(f"Start bot {bot_id}: user={user_id}, auth_header={'Yes' if request.headers.get('Authorization') else 'No'}")

        # Try to use user's own API keys for live trading
        api_key, api_secret = None, None
        if user and _db_available:
            try:
                from tradeengine.database.connection import get_session
                from tradeengine.database.crud import get_api_credential
                from tradeengine.database.encryption import decrypt_value
                session = await get_session()
                try:
                    cred = await get_api_credential(session, user["user_id"])
                    if cred:
                        api_key = decrypt_value(cred.api_key_encrypted)
                        api_secret = decrypt_value(cred.api_secret_encrypted)
                finally:
                    await session.close()
            except Exception as e:
                logger.warning(f"Failed to load API key for user {user['user_id']}: {e}")

        # Check if this is a webhook bot
        bot = bot_manager.get_bot(bot_id, user_id=user_id)
        if not bot:
            return JSONResponse({"error": "Bot not found"}, status_code=404)

        # If no user API key found, decide based on auth mode
        if not api_key:
            if _db_available and clerk_pk:
                # Auth mode: paper trading can use server config (klines are public),
                # but live trading always requires user's own API key
                if bot.paper_mode:
                    api_key = config.pionex.api_key or ""
                    api_secret = config.pionex.api_secret or ""
                else:
                    return JSONResponse({"error": "請先在帳戶頁面設定 API 金鑰"}, status_code=400)
            else:
                # Local mode (no auth): use server config
                api_key = config.pionex.api_key
                api_secret = config.pionex.api_secret
                if not api_key or api_key == "your_api_key_here":
                    return JSONResponse({"error": "API 金鑰未設定"}, status_code=400)

        if bot.signal_source == "webhook":
            ok = await bot_manager.start_webhook_bot(
                bot_id, app_config=None if api_key else config,
                api_key=api_key, api_secret=api_secret, user_id=user_id or "",
            )
        elif api_key:
            ok = await bot_manager.start_bot(bot_id, app_config=None, api_key=api_key, api_secret=api_secret)
        else:
            ok = await bot_manager.start_bot(bot_id, config)

        if ok:
            return {"status": "started", "bot_id": bot_id}
        bot = bot_manager.get_bot(bot_id, user_id=user_id)
        err = bot.error_msg if bot else "Bot not found"
        return JSONResponse({"error": err}, status_code=400)

    @app.post("/api/bots/{bot_id}/stop")
    async def api_stop_bot(bot_id: str, request: Request):
        user = await _optional_user(request)
        user_id = user["user_id"] if user else None
        ok = await bot_manager.stop_bot(bot_id, user_id=user_id)
        if ok:
            return {"status": "stopped", "bot_id": bot_id}
        return JSONResponse({"error": "Failed to stop"}, status_code=400)

    @app.delete("/api/bots/{bot_id}")
    async def api_delete_bot(bot_id: str, request: Request):
        user = await _optional_user(request)
        user_id = user["user_id"] if user else None
        ok = bot_manager.delete_bot(bot_id, user_id=user_id)
        if ok:
            return {"status": "deleted"}
        return JSONResponse({"error": "Cannot delete running bot"}, status_code=400)

    @app.get("/api/bots/{bot_id}")
    async def api_bot_detail(bot_id: str, request: Request):
        user = await _optional_user(request)
        user_id = user["user_id"] if user else None
        bot = bot_manager.get_bot(bot_id, user_id=user_id)
        if not bot:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return _bot_to_dict(bot, bot_manager)

    # ─── Webhook API ────────────────────────────────────────────────

    @app.post("/api/webhook/{token}")
    async def api_webhook(token: str, request: Request):
        """TradingView webhook endpoint — token-based auth, no Bearer required."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

        action = body.get("action", "").strip()
        if not action:
            return JSONResponse({"error": "Missing 'action' field"}, status_code=400)

        price = None
        if "price" in body:
            try:
                price = float(body["price"])
            except (ValueError, TypeError):
                pass

        result = await bot_manager.execute_webhook_signal(token, action, price)
        if result.get("status") == "rejected":
            return JSONResponse(result, status_code=400)
        if result.get("status") == "error":
            return JSONResponse(result, status_code=500)
        return result

    @app.get("/api/bots/{bot_id}/webhook-info")
    async def api_webhook_info(bot_id: str, request: Request):
        """Get webhook URL and TradingView Alert Message template."""
        user = await _optional_user(request)
        user_id = user["user_id"] if user else None
        bot = bot_manager.get_bot(bot_id, user_id=user_id)
        if not bot:
            return JSONResponse({"error": "Bot not found"}, status_code=404)
        if bot.signal_source != "webhook":
            return JSONResponse({"error": "Not a webhook bot"}, status_code=400)

        # Build webhook URL from request
        base_url = str(request.base_url).rstrip("/")
        webhook_url = f"{base_url}/api/webhook/{bot.webhook_token}"

        alert_template = json.dumps({
            "action": "{{strategy.order.action}}",
            "price": "{{close}}",
            "time": "{{time}}",
        }, indent=2)

        return {
            "bot_id": bot.bot_id,
            "webhook_url": webhook_url,
            "token": bot.webhook_token,
            "alert_message_template": alert_template,
        }

    # ─── CSV API ─────────────────────────────────────────────────────

    @app.get("/api/csv-files")
    async def api_csv_files():
        return find_csv_files()

    # ─── Cache API ───────────────────────────────────────────────────

    @app.get("/api/cache")
    async def api_cache():
        from tradeengine.data.store import DataStore
        store = DataStore(config.data.cache_dir)
        return store.list_cached()

    # ─── Admin API ───────────────────────────────────────────────────

    @app.get("/api/admin/users")
    async def api_admin_users(request: Request):
        user = await _optional_user(request)
        if not user or user["role"] != "admin":
            return JSONResponse({"error": "需要管理員權限"}, status_code=403)
        if not _db_available:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        from tradeengine.database.connection import get_session
        from tradeengine.database.crud import list_all_users
        session = await get_session()
        try:
            users = await list_all_users(session)
            return [
                {
                    "clerk_id": u.clerk_id,
                    "email": u.email,
                    "display_name": u.display_name,
                    "role": u.role,
                    "max_bots": u.max_bots,
                    "is_active": u.is_active,
                    "created_at": str(u.created_at) if u.created_at else "",
                }
                for u in users
            ]
        finally:
            await session.close()

    @app.post("/api/admin/users/{clerk_id}/toggle")
    async def api_admin_toggle_user(clerk_id: str, request: Request):
        user = await _optional_user(request)
        if not user or user["role"] != "admin":
            return JSONResponse({"error": "需要管理員權限"}, status_code=403)

        from tradeengine.database.connection import get_session
        from tradeengine.database.crud import toggle_user_active
        session = await get_session()
        try:
            ok = await toggle_user_active(session, clerk_id)
            return {"status": "ok"} if ok else JSONResponse({"error": "User not found"}, status_code=404)
        finally:
            await session.close()

    @app.post("/api/admin/users/{clerk_id}/max-bots")
    async def api_admin_max_bots(clerk_id: str, request: Request):
        user = await _optional_user(request)
        if not user or user["role"] != "admin":
            return JSONResponse({"error": "需要管理員權限"}, status_code=403)

        data = await request.json()
        max_bots = int(data.get("max_bots", 1))

        from tradeengine.database.connection import get_session
        from tradeengine.database.crud import update_user_max_bots
        session = await get_session()
        try:
            ok = await update_user_max_bots(session, clerk_id, max_bots)
            return {"status": "ok"} if ok else JSONResponse({"error": "User not found"}, status_code=404)
        finally:
            await session.close()

    @app.post("/api/admin/users/{clerk_id}/role")
    async def api_admin_update_role(clerk_id: str, request: Request):
        user = await _optional_user(request)
        if not user or user["role"] != "admin":
            return JSONResponse({"error": "需要管理員權限"}, status_code=403)

        data = await request.json()
        role = data.get("role", "standard")

        from tradeengine.database.connection import get_session
        from tradeengine.database.crud import update_user_role
        session = await get_session()
        try:
            ok = await update_user_role(session, clerk_id, role)
            if not ok:
                return JSONResponse({"error": "無效角色或用戶不存在"}, status_code=400)
            from tradeengine.database.crud import ROLE_BOT_LIMITS
            return {"status": "ok", "role": role, "max_bots": ROLE_BOT_LIMITS.get(role, 1)}
        finally:
            await session.close()

    @app.post("/api/admin/users/{clerk_id}/update")
    async def api_admin_update_user(clerk_id: str, request: Request):
        user = await _optional_user(request)
        if not user or user["role"] != "admin":
            return JSONResponse({"error": "需要管理員權限"}, status_code=403)

        data = await request.json()
        allowed = {"email", "display_name"}
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return JSONResponse({"error": "無有效欄位"}, status_code=400)

        from tradeengine.database.connection import get_session
        session = await get_session()
        try:
            session.table("users").update(updates).eq("clerk_id", clerk_id).execute()
            return {"status": "ok"}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        finally:
            await session.close()

    @app.post("/api/admin/sync-clerk")
    async def api_admin_sync_clerk(request: Request):
        """Batch-fetch email/name from Clerk for users missing email."""
        user = await _optional_user(request)
        if not user or user["role"] != "admin":
            return JSONResponse({"error": "需要管理員權限"}, status_code=403)

        from tradeengine.dashboard.auth import _fetch_clerk_user
        from tradeengine.database.connection import get_session

        session = await get_session()
        try:
            result = session.table("users").select("clerk_id,email").execute()
            updated = 0
            for row in result.data or []:
                if row.get("email"):
                    continue
                clerk_id = row.get("clerk_id", "")
                if not clerk_id:
                    continue
                info = _fetch_clerk_user(clerk_id)
                if not info.get("email"):
                    continue
                updates = {"email": info["email"]}
                if info.get("name"):
                    updates["display_name"] = info["name"]
                session.table("users").update(updates).eq("clerk_id", clerk_id).execute()
                updated += 1
            return {"status": "ok", "updated": updated}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        finally:
            await session.close()

    return app


def _bot_to_dict(bot, mgr=None) -> dict:
    """Convert BotConfig to serializable dict."""
    d = {
        "bot_id": bot.bot_id,
        "name": bot.name,
        "strategy": bot.strategy,
        "symbol": bot.symbol,
        "timeframe": bot.timeframe,
        "capital": bot.capital,
        "params": bot.params,
        "paper_mode": bot.paper_mode,
        "sl_pct": bot.sl_pct,
        "tp_pct": bot.tp_pct,
        "max_drawdown_pct": bot.max_drawdown_pct,
        "created_at": bot.created_at,
        "status": bot.status,
        "signal_source": bot.signal_source,
        "webhook_token": bot.webhook_token,
        "total_pnl": bot.total_pnl,
        "total_trades": bot.total_trades,
        "win_rate": bot.win_rate,
        "last_signal": bot.last_signal,
        "last_signal_time": bot.last_signal_time,
        "error_msg": bot.error_msg,
        "position": None,
    }
    if mgr:
        pos = mgr.get_position_info(bot.bot_id)
        if pos:
            d["position"] = pos
    return d
