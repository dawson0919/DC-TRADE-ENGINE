"""Bot management: create, start, stop, monitor trading bots."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BOT_STORE_PATH = Path(__file__).parent.parent.parent / "data" / "bots.json"

# Fields to persist to DB / JSON
_BOT_FIELDS = [
    "bot_id", "user_id", "name", "strategy", "symbol", "timeframe",
    "capital", "params", "paper_mode", "sl_pct", "tp_pct",
    "max_drawdown_pct", "created_at", "status", "signal_source",
    "webhook_token", "total_pnl", "total_trades", "win_rate",
    "last_signal", "last_signal_time", "trade_history", "error_msg",
    "auto_start",
]


class BotStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"
    PAUSED = "paused"


@dataclass
class BotConfig:
    """Bot configuration."""
    bot_id: str
    user_id: str = ""
    name: str = ""
    strategy: str = ""
    symbol: str = ""
    timeframe: str = ""
    capital: float = 10000.0
    params: dict[str, Any] = field(default_factory=dict)
    paper_mode: bool = True
    sl_pct: float | None = None
    tp_pct: float | None = None
    max_drawdown_pct: float = 20.0
    created_at: str = ""
    status: str = "stopped"
    # Webhook support
    signal_source: str = "strategy"  # "strategy" or "webhook"
    webhook_token: str = ""          # unique token for webhook URL
    # Runtime stats
    total_pnl: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    last_signal: str = ""
    last_signal_time: str = ""
    trade_history: list[dict] = field(default_factory=list)
    error_msg: str = ""
    auto_start: bool = False


def _bot_to_row(bot: BotConfig) -> dict:
    """Convert BotConfig to a DB row dict."""
    return {
        "bot_id": bot.bot_id,
        "user_id": bot.user_id,
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
        "status": bot.status,
        "signal_source": bot.signal_source,
        "webhook_token": bot.webhook_token,
        "total_pnl": bot.total_pnl,
        "total_trades": bot.total_trades,
        "win_rate": bot.win_rate,
        "last_signal": bot.last_signal,
        "last_signal_time": bot.last_signal_time,
        "trade_history": bot.trade_history[-50:],
        "error_msg": "",
        "auto_start": bot.auto_start,
    }


def _row_to_bot(row: dict) -> BotConfig:
    """Convert a DB row / JSON dict to BotConfig."""
    # Ensure defaults for missing fields
    row.setdefault("user_id", "")
    row.setdefault("signal_source", "strategy")
    row.setdefault("webhook_token", "")
    row.setdefault("trade_history", [])
    row.setdefault("error_msg", "")
    row.setdefault("max_drawdown_pct", 20.0)
    row.setdefault("total_pnl", 0.0)
    row.setdefault("total_trades", 0)
    row.setdefault("win_rate", 0.0)
    row.setdefault("last_signal", "")
    row.setdefault("last_signal_time", "")
    row.setdefault("created_at", "")
    row.setdefault("auto_start", False)
    # Filter only known fields
    known = {f.name for f in BotConfig.__dataclass_fields__.values()}
    filtered = {k: v for k, v in row.items() if k in known}
    return BotConfig(**filtered)


class BotManager:
    """Manages trading bot lifecycle.

    Runtime state (running tasks/engines) is in-memory only.
    Persistence is via Supabase (SaaS mode) or JSON file (local mode).
    """

    def __init__(self):
        self._bots: dict[str, BotConfig] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._running_engines: dict[str, Any] = {}
        self._webhook_executors: dict[str, Any] = {}
        self._webhook_positions: dict[str, dict] = {}
        self._pending_restart: set[str] = set()
        self._db_client: Any = None  # Supabase client
        self._load_bots_json()  # Load from JSON first as fallback

    async def init_db(self):
        """Initialize Supabase storage. Call after DB is ready."""
        try:
            from tradeengine.database.connection import get_session
            self._db_client = await get_session()
            await self._load_bots_db()
            # DB is the source of truth; sync JSON to match
            self._save_bots_json()
            logger.info("BotManager: using Supabase storage")
        except Exception as e:
            logger.warning(f"BotManager: DB init failed, using JSON fallback: {e}")
            self._db_client = None

    # ─── Persistence ──────────────────────────────────────────────

    def _load_bots_json(self):
        """Load bots from disk (JSON fallback for local mode)."""
        if BOT_STORE_PATH.exists():
            try:
                data = json.loads(BOT_STORE_PATH.read_text(encoding="utf-8"))
                for bot_data in data:
                    bot = _row_to_bot(bot_data)
                    bot.status = "stopped"
                    self._bots[bot.bot_id] = bot
                    if bot.auto_start:
                        self._pending_restart.add(bot.bot_id)
                logger.info(f"Loaded {len(self._bots)} bots from JSON")
            except Exception as e:
                logger.warning(f"Failed to load bots from JSON: {e}")

    async def _load_bots_db(self):
        """Load bots from Supabase."""
        try:
            result = self._db_client.table("bots").select("*").execute()
            rows = result.data or []
            self._bots.clear()
            self._pending_restart.clear()
            for row in rows:
                bot = _row_to_bot(row)
                bot.status = "stopped"
                self._bots[bot.bot_id] = bot
                # Use auto_start flag (persists across deploys)
                if bot.auto_start:
                    self._pending_restart.add(bot.bot_id)
            logger.info(f"Loaded {len(self._bots)} bots from Supabase")
        except Exception as e:
            logger.warning(f"Failed to load bots from DB: {e}")

    def _save_bots(self):
        """Persist bots — to Supabase if available, else JSON."""
        if self._db_client:
            self._save_bots_db()
        self._save_bots_json()

    def _save_bots_json(self):
        """Save all bots to JSON file."""
        try:
            BOT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = [_bot_to_row(bot) for bot in self._bots.values()]
            BOT_STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save bots to JSON: {e}")

    def _save_bots_db(self):
        """Upsert all bots to Supabase."""
        if not self._db_client:
            return
        try:
            rows = [_bot_to_row(bot) for bot in self._bots.values()]
            if rows:
                self._db_client.table("bots").upsert(rows, on_conflict="bot_id").execute()
        except Exception as e:
            logger.warning(f"Failed to save bots to DB: {e}")

    def _save_one_bot(self, bot: BotConfig):
        """Save a single bot to DB (more efficient for frequent updates)."""
        if self._db_client:
            try:
                self._db_client.table("bots").upsert(
                    _bot_to_row(bot), on_conflict="bot_id"
                ).execute()
            except Exception as e:
                logger.warning(f"Failed to save bot {bot.bot_id} to DB: {e}")
        self._save_bots_json()

    def _delete_bot_db(self, bot_id: str):
        """Delete a bot from Supabase."""
        if self._db_client:
            try:
                self._db_client.table("bots").delete().eq("bot_id", bot_id).execute()
            except Exception as e:
                logger.warning(f"Failed to delete bot {bot_id} from DB: {e}")

    # ─── CRUD ─────────────────────────────────────────────────────

    def create_bot(
        self,
        name: str,
        strategy: str,
        symbol: str,
        timeframe: str,
        capital: float,
        params: dict | None = None,
        paper_mode: bool = True,
        sl_pct: float | None = None,
        tp_pct: float | None = None,
        user_id: str = "",
        signal_source: str = "strategy",
    ) -> BotConfig:
        """Create a new trading bot."""
        bot_id = str(uuid.uuid4())[:8]
        webhook_token = str(uuid.uuid4()) if signal_source == "webhook" else ""
        bot = BotConfig(
            bot_id=bot_id,
            user_id=user_id,
            name=name,
            strategy=strategy or "webhook",
            symbol=symbol,
            timeframe=timeframe,
            capital=capital,
            params=params or {},
            paper_mode=paper_mode,
            sl_pct=sl_pct,
            tp_pct=tp_pct,
            signal_source=signal_source,
            webhook_token=webhook_token,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._bots[bot_id] = bot
        self._save_one_bot(bot)
        logger.info(f"Created bot {bot_id}: {name} ({strategy}/{signal_source} on {symbol}) user={user_id}")
        return bot

    def delete_bot(self, bot_id: str, user_id: str = "") -> bool:
        """Delete a bot (must be stopped first)."""
        bot = self._bots.get(bot_id)
        if not bot:
            return False
        if user_id and bot.user_id and bot.user_id != user_id:
            return False
        if bot.status == "running":
            return False
        del self._bots[bot_id]
        self._delete_bot_db(bot_id)
        self._save_bots_json()
        return True

    def update_bot(self, bot_id: str, user_id: str = "", **updates) -> BotConfig | None:
        """Update a stopped bot's configuration."""
        bot = self._bots.get(bot_id)
        if not bot:
            return None
        if user_id and bot.user_id and bot.user_id != user_id:
            return None
        if bot.status == "running":
            return None
        allowed = {"name", "strategy", "symbol", "timeframe", "capital", "params",
                   "paper_mode", "sl_pct", "tp_pct"}
        for key, val in updates.items():
            if key in allowed:
                setattr(bot, key, val)
        self._save_one_bot(bot)
        logger.info(f"Updated bot {bot_id}: {list(updates.keys())}")
        return bot

    def get_bot(self, bot_id: str, user_id: str = "") -> BotConfig | None:
        bot = self._bots.get(bot_id)
        if bot and user_id and bot.user_id and bot.user_id != user_id:
            return None
        return bot

    def list_bots(self, user_id: str = "") -> list[BotConfig]:
        if user_id:
            return [b for b in self._bots.values() if b.user_id == user_id]
        return list(self._bots.values())

    # ─── Start / Stop ─────────────────────────────────────────────

    async def start_bot(self, bot_id: str, app_config=None, api_key: str = "", api_secret: str = "") -> bool:
        """Start a bot's trading loop.

        Accepts either app_config (legacy) or direct api_key/api_secret.
        """
        bot = self._bots.get(bot_id)
        if not bot or bot.status == "running":
            return False

        from tradeengine.data.pionex_client import PionexClient
        from tradeengine.strategies.registry import get_strategy
        from tradeengine.trading.engine import LiveTradingEngine
        from tradeengine.trading.paper_executor import PaperExecutor
        from tradeengine.trading.pionex_executor import PionexExecutor
        from tradeengine.trading.risk_manager import RiskConfig

        try:
            strat = get_strategy(bot.strategy)

            # Resolve API credentials
            key = api_key or (app_config.pionex.api_key if app_config else "")
            secret = api_secret or (app_config.pionex.api_secret if app_config else "")
            client = PionexClient(key, secret)

            if bot.paper_mode:
                executor = PaperExecutor(bot.capital)
            else:
                if "_PERP" in bot.symbol:
                    bot.status = "error"
                    bot.error_msg = "合約交易對僅支援模擬交易（Pionex API 未開放合約下單）"
                    self._save_one_bot(bot)
                    return False
                if not key or key == "your_api_key_here":
                    bot.status = "error"
                    bot.error_msg = "Pionex API Key not configured"
                    self._save_one_bot(bot)
                    return False
                executor = PionexExecutor(client)

            risk_config = RiskConfig(
                max_drawdown_pct=bot.max_drawdown_pct,
                default_sl_pct=bot.sl_pct,
                default_tp_pct=bot.tp_pct,
            )

            engine = LiveTradingEngine(
                strategy=strat,
                executor=executor,
                client=client,
                symbol=bot.symbol,
                timeframe=bot.timeframe,
                params=bot.params,
                risk_config=risk_config,
                initial_capital=bot.capital,
            )

            bot.status = "running"
            bot.error_msg = ""
            bot.auto_start = True
            self._running_engines[bot_id] = engine

            # Register trade callback to update bot stats
            def _on_engine_trade(action, side, price, size, pnl, _bid=bot_id):
                b = self._bots.get(_bid)
                if not b:
                    return
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if action == "close":
                    b.total_trades += 1
                    b.total_pnl += pnl
                    if pnl > 0:
                        wins = round(b.win_rate / 100 * max(b.total_trades - 1, 0))
                        b.win_rate = round((wins + 1) / b.total_trades * 100, 1)
                    elif b.total_trades > 1:
                        wins = round(b.win_rate / 100 * (b.total_trades - 1))
                        b.win_rate = round(wins / b.total_trades * 100, 1)
                    else:
                        b.win_rate = 0.0
                    b.trade_history.append({
                        "action": action, "side": side,
                        "price": price, "size": size,
                        "pnl": round(pnl, 4), "time": now_str,
                    })
                b.last_signal = f"{action} {side}"
                b.last_signal_time = now_str
                self._save_one_bot(b)

            engine.on_trade(_on_engine_trade)
            self._save_one_bot(bot)

            task = asyncio.create_task(self._run_bot(bot_id, engine, client))
            self._running_tasks[bot_id] = task
            return True
        except Exception as e:
            bot.status = "error"
            bot.error_msg = str(e)
            self._save_one_bot(bot)
            logger.error(f"Failed to start bot {bot_id}: {e}")
            return False

    async def _run_bot(self, bot_id: str, engine, client):
        """Bot execution wrapper with error handling."""
        bot = self._bots.get(bot_id)
        try:
            await engine.start()
        except asyncio.CancelledError:
            logger.info(f"Bot {bot_id} cancelled")
        except Exception as e:
            if bot:
                bot.status = "error"
                bot.error_msg = str(e)
                self._save_one_bot(bot)
            logger.error(f"Bot {bot_id} error: {e}")
        finally:
            if bot and bot.status == "running":
                bot.status = "stopped"
                self._save_one_bot(bot)
            try:
                await client.close()
            except Exception:
                pass

    async def stop_bot(self, bot_id: str, user_id: str = "") -> bool:
        """Stop a running bot."""
        bot = self._bots.get(bot_id)
        if not bot:
            return False
        if user_id and bot.user_id and bot.user_id != user_id:
            return False

        engine = self._running_engines.pop(bot_id, None)
        if engine:
            try:
                await engine.stop()
            except Exception as e:
                logger.warning(f"Error stopping engine: {e}")

        task = self._running_tasks.pop(bot_id, None)
        if task and not task.done():
            task.cancel()

        # Clean up webhook executor
        self._webhook_executors.pop(bot_id, None)
        self._webhook_positions.pop(bot_id, None)

        bot.status = "stopped"
        bot.error_msg = ""
        bot.auto_start = False
        self._save_one_bot(bot)
        return True

    # ─── Webhook Support ─────────────────────────────────────────────

    def get_bot_by_webhook_token(self, token: str) -> BotConfig | None:
        """Find a bot by its webhook token."""
        for bot in self._bots.values():
            if bot.webhook_token == token:
                return bot
        return None

    async def start_webhook_bot(
        self, bot_id: str, app_config=None, api_key: str = "", api_secret: str = "", user_id: str = ""
    ) -> bool:
        """Start a webhook bot — sets up executor but no candle loop."""
        bot = self._bots.get(bot_id)
        if not bot or bot.status == "running":
            return False
        if user_id and bot.user_id and bot.user_id != user_id:
            return False

        from tradeengine.data.pionex_client import PionexClient
        from tradeengine.trading.paper_executor import PaperExecutor
        from tradeengine.trading.pionex_executor import PionexExecutor

        try:
            key = api_key or (app_config.pionex.api_key if app_config else "")
            secret = api_secret or (app_config.pionex.api_secret if app_config else "")

            if bot.paper_mode:
                executor = PaperExecutor(bot.capital)
            else:
                if "_PERP" in bot.symbol:
                    bot.status = "error"
                    bot.error_msg = "合約交易對僅支援模擬交易"
                    self._save_one_bot(bot)
                    return False
                if not key or key == "your_api_key_here":
                    bot.status = "error"
                    bot.error_msg = "Pionex API Key not configured"
                    self._save_one_bot(bot)
                    return False
                client = PionexClient(key, secret)
                executor = PionexExecutor(client)

            self._webhook_executors[bot_id] = executor
            self._webhook_positions[bot_id] = {"side": None, "entry_price": 0.0, "size": 0.0}
            bot.status = "running"
            bot.error_msg = ""
            bot.auto_start = True
            self._save_one_bot(bot)
            logger.info(f"Webhook bot {bot_id} started, waiting for signals")
            return True
        except Exception as e:
            bot.status = "error"
            bot.error_msg = str(e)
            self._save_one_bot(bot)
            logger.error(f"Failed to start webhook bot {bot_id}: {e}")
            return False

    async def execute_webhook_signal(self, token: str, action: str, price: float | None = None) -> dict:
        """Execute a trade from a webhook signal."""
        bot = self.get_bot_by_webhook_token(token)
        if not bot:
            return {"error": "Invalid webhook token", "status": "rejected"}
        if bot.status != "running":
            return {"error": f"Bot is {bot.status}, not running", "status": "rejected"}

        executor = self._webhook_executors.get(bot.bot_id)
        if not executor:
            return {"error": "Executor not ready", "status": "rejected"}

        pos = self._webhook_positions.get(bot.bot_id, {"side": None, "entry_price": 0.0, "size": 0.0})
        action_lower = action.lower().strip()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        result_actions = []

        try:
            if action_lower == "buy":
                if pos["side"] == "short":
                    pnl = self._calc_webhook_pnl(pos, price or 0, "short")
                    self._record_webhook_trade(bot, "close_short", price, pnl)
                    result_actions.append("closed_short")
                size = bot.capital / (price or 1.0)
                pos.update({"side": "long", "entry_price": price or 0, "size": size})
                bot.last_signal = f"BUY @ ${price:,.2f}" if price else "BUY"
                result_actions.append("opened_long")

            elif action_lower == "sell":
                if pos["side"] == "long":
                    pnl = self._calc_webhook_pnl(pos, price or 0, "long")
                    self._record_webhook_trade(bot, "close_long", price, pnl)
                    result_actions.append("closed_long")
                size = bot.capital / (price or 1.0)
                pos.update({"side": "short", "entry_price": price or 0, "size": size})
                bot.last_signal = f"SELL @ ${price:,.2f}" if price else "SELL"
                result_actions.append("opened_short")

            elif action_lower in ("close", "close_long", "close_short"):
                if pos["side"]:
                    pnl = self._calc_webhook_pnl(pos, price or 0, pos["side"])
                    self._record_webhook_trade(bot, "close", price, pnl)
                    pos.update({"side": None, "entry_price": 0, "size": 0})
                    bot.last_signal = f"CLOSE @ ${price:,.2f}" if price else "CLOSE"
                    result_actions.append("closed_position")
                else:
                    result_actions.append("no_position")

            else:
                return {"error": f"Unknown action: {action}", "status": "rejected"}

            bot.last_signal_time = now_str
            self._webhook_positions[bot.bot_id] = pos
            self._save_one_bot(bot)

            logger.info(f"Webhook signal for bot {bot.bot_id}: {action} -> {result_actions}")
            return {
                "status": "executed",
                "bot_id": bot.bot_id,
                "actions": result_actions,
                "signal": bot.last_signal,
                "total_pnl": bot.total_pnl,
                "total_trades": bot.total_trades,
            }

        except Exception as e:
            bot.error_msg = f"Webhook execution error: {e}"
            self._save_one_bot(bot)
            logger.error(f"Webhook signal execution failed for bot {bot.bot_id}: {e}")
            return {"error": str(e), "status": "error"}

    def _calc_webhook_pnl(self, pos: dict, exit_price: float, side: str) -> float:
        """Calculate PnL for a webhook position close."""
        if not pos["entry_price"] or not exit_price:
            return 0.0
        if side == "long":
            return (exit_price - pos["entry_price"]) / pos["entry_price"] * pos.get("size", 0) * pos["entry_price"]
        else:
            return (pos["entry_price"] - exit_price) / pos["entry_price"] * pos.get("size", 0) * pos["entry_price"]

    def _record_webhook_trade(self, bot: BotConfig, action: str, price: float | None, pnl: float):
        """Record a trade and update bot stats."""
        bot.total_pnl += pnl
        bot.total_trades += 1
        if pnl > 0:
            wins = int(bot.win_rate / 100 * (bot.total_trades - 1)) + 1
        else:
            wins = int(bot.win_rate / 100 * (bot.total_trades - 1))
        bot.win_rate = (wins / bot.total_trades * 100) if bot.total_trades > 0 else 0.0

        trade = {
            "action": action,
            "price": price,
            "pnl": round(pnl, 4),
            "time": datetime.now(timezone.utc).isoformat(),
        }
        bot.trade_history.append(trade)
        if len(bot.trade_history) > 50:
            bot.trade_history = bot.trade_history[-50:]

    def get_position_info(self, bot_id: str) -> dict | None:
        """Get current position info from a running engine or webhook bot.

        Returns dict with side, entry_price, size, unrealized_pnl, current_price
        or None if no position is open.
        """
        # Strategy bot — check engine's position manager
        engine = self._running_engines.get(bot_id)
        if engine:
            pm = getattr(engine, "position_manager", None)
            bot = self._bots.get(bot_id)
            if pm and bot:
                pos = pm.get_position(bot.symbol)
                if pos:
                    # Try to get current price from executor
                    current_price = 0.0
                    executor = getattr(engine, "executor", None)
                    if executor and hasattr(executor, "_current_prices"):
                        current_price = executor._current_prices.get(bot.symbol, 0.0)
                    # Calculate unrealized PnL in USD
                    unrealized_pnl_usd = 0.0
                    if current_price > 0 and pos.entry_price > 0:
                        if pos.side.value == "long":
                            unrealized_pnl_usd = (current_price - pos.entry_price) * pos.size
                        else:
                            unrealized_pnl_usd = (pos.entry_price - current_price) * pos.size
                    return {
                        "side": pos.side.value,
                        "entry_price": pos.entry_price,
                        "size": pos.size,
                        "unrealized_pnl": pos.unrealized_pnl,
                        "unrealized_pnl_usd": round(unrealized_pnl_usd, 4),
                        "current_price": current_price,
                        "entry_time": pos.entry_time.isoformat() if pos.entry_time else None,
                    }

        # Webhook bot — check webhook positions
        wh_pos = self._webhook_positions.get(bot_id)
        if wh_pos and wh_pos.get("side"):
            return {
                "side": wh_pos["side"],
                "entry_price": wh_pos.get("entry_price", 0.0),
                "size": wh_pos.get("size", 0.0),
                "unrealized_pnl": 0.0,
                "unrealized_pnl_usd": 0.0,
                "current_price": 0.0,
                "entry_time": None,
            }

        return None

    def get_bot_stats(self, bot_id: str) -> dict:
        """Get runtime stats for a bot."""
        bot = self._bots.get(bot_id)
        if not bot:
            return {}
        return {
            "bot_id": bot.bot_id,
            "name": bot.name,
            "status": bot.status,
            "total_pnl": bot.total_pnl,
            "total_trades": bot.total_trades,
            "win_rate": bot.win_rate,
            "last_signal": bot.last_signal,
            "last_signal_time": bot.last_signal_time,
            "error_msg": bot.error_msg,
        }

    # ─── Auto-Restart ─────────────────────────────────────────────

    async def auto_restart_bots(self, app_config=None) -> list[str]:
        """Restart bots that were running before server shutdown."""
        if not self._pending_restart:
            logger.info("No bots to auto-restart")
            return []

        restarted = []
        failed = []
        to_restart = list(self._pending_restart)
        self._pending_restart.clear()

        for i, bot_id in enumerate(to_restart):
            bot = self._bots.get(bot_id)
            if not bot:
                continue

            # Stagger bot startups to avoid WebSocket rate limiting (429)
            if i > 0:
                delay = 3.0 + i * 2.0  # 5s, 7s, 9s, ...
                logger.info(f"Waiting {delay:.0f}s before starting bot {bot_id} (stagger)")
                await asyncio.sleep(delay)

            try:
                # For live (non-paper) bots, fetch user's API keys from DB
                api_key = ""
                api_secret = ""
                if not bot.paper_mode and bot.user_id and self._db_client:
                    try:
                        from tradeengine.database.crud import get_user_api_key
                        creds = await get_user_api_key(self._db_client, bot.user_id)
                        if creds:
                            api_key = creds["api_key"]
                            api_secret = creds["api_secret"]
                    except Exception as e:
                        logger.warning(f"Failed to fetch API key for bot {bot_id}: {e}")

                if bot.signal_source == "webhook":
                    ok = await self.start_webhook_bot(
                        bot_id, app_config=app_config,
                        api_key=api_key, api_secret=api_secret,
                    )
                else:
                    ok = await self.start_bot(
                        bot_id, app_config=app_config,
                        api_key=api_key, api_secret=api_secret,
                    )

                if ok:
                    restarted.append(bot_id)
                    logger.info(f"Auto-restarted bot {bot_id} ({bot.name})")
                else:
                    failed.append(bot_id)
                    logger.warning(f"Failed to auto-restart bot {bot_id}: {bot.error_msg}")
            except Exception as e:
                failed.append(bot_id)
                logger.error(f"Error auto-restarting bot {bot_id}: {e}")

        logger.info(f"Auto-restart complete: {len(restarted)} restarted, {len(failed)} failed")
        return restarted
