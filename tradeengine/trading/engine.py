"""Async live/paper trading engine."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

from tradeengine.data.models import Side, Timeframe
from tradeengine.data.pionex_client import PionexClient
from tradeengine.data.pionex_ws import PionexWebSocket
from tradeengine.strategies.base import BaseStrategy
from tradeengine.trading.executor import OrderExecutor
from tradeengine.trading.position_manager import PositionManager
from tradeengine.trading.risk_manager import RiskConfig, RiskManager

logger = logging.getLogger(__name__)


class LiveTradingEngine:
    """Async live/paper trading loop.

    1. Connects to Pionex WebSocket for real-time trade data
    2. Aggregates trades into candles for the specified timeframe
    3. On each new candle close, evaluates strategy signals
    4. Executes orders through the provided executor (live or paper)
    5. Applies risk management (SL/TP/trailing/max DD)
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        executor: OrderExecutor,
        client: PionexClient,
        symbol: str,
        timeframe: str,
        params: dict[str, Any],
        risk_config: RiskConfig | None = None,
        initial_capital: float = 10000.0,
        leverage: float = 1.0,
        lookback: int = 200,
        shared_ws: PionexWebSocket | None = None,
    ):
        self.strategy = strategy
        self.executor = executor
        self.client = client
        self.symbol = symbol
        self.timeframe = timeframe
        self.tf = Timeframe(timeframe)
        self.params = params
        self.initial_capital = initial_capital
        self.leverage = min(leverage, 5.0)  # Constraint
        self.lookback = lookback
        # Spot SHORT restriction only applies to live mode
        self._can_short = "_PERP" in symbol or "Paper" in type(executor).__name__ or "Signal" in type(executor).__name__

        self.position_manager = PositionManager()
        self.risk_manager = RiskManager(
            risk_config or RiskConfig(), initial_capital
        )

        self._running = False
        self._candle_buffer: deque[dict] = deque(maxlen=lookback)
        self._current_candle: dict | None = None
        self._shared_ws = shared_ws
        self._ws: PionexWebSocket | None = None
        self._owns_ws = False
        self._stop_event: asyncio.Event | None = None
        self._last_signal_time: float = 0
        self._signal_log: deque[dict] = deque(maxlen=10)
        self._on_trade_callback: Callable | None = None

    def on_trade(self, callback: Callable):
        """Register callback for trade events: callback(side, price, size, pnl)."""
        self._on_trade_callback = callback

    async def start(self):
        """Start the trading loop."""
        logger.info(
            f"Starting trading engine: {self.strategy.display_name} | "
            f"{self.symbol} | {self.timeframe}"
        )
        self._running = True
        self._stop_event = asyncio.Event()

        # 1. Load historical candles for lookback
        await self._load_history()

        # 2. Connect WebSocket
        if self._shared_ws:
            # Shared mode: reuse existing connection
            self._ws = self._shared_ws
            self._owns_ws = False
            if not self._ws.is_connected:
                await self._ws.connect()
            await self._ws.subscribe_trade(self.symbol)
            self._ws.on_symbol("trade", self.symbol, self._on_trade)
            await self._ws.ensure_listening()

            # 3. Start candle aggregation loop
            asyncio.create_task(self._candle_loop())

            # 4. Block until stopped
            await self._stop_event.wait()
        else:
            # Solo mode: create own WebSocket (backward compatible)
            self._ws = PionexWebSocket()
            self._owns_ws = True
            await self._ws.connect()
            await self._ws.subscribe_trade(self.symbol)
            self._ws.on("trade", self._on_trade)

            # 3. Start candle aggregation loop
            asyncio.create_task(self._candle_loop())

            # 4. Main listen loop (blocks)
            await self._ws.listen()

    async def stop(self):
        """Stop the trading loop."""
        self._running = False
        if self._ws and self._owns_ws:
            # Solo mode: close our own WebSocket
            await self._ws.close()
        elif self._ws and not self._owns_ws:
            # Shared mode: remove only this engine's callback
            try:
                self._ws.off_symbol("trade", self.symbol, self._on_trade)
                # Only unsubscribe from WS if no other engines need this symbol
                remaining = self._ws.symbol_callback_count("trade", self.symbol)
                if remaining == 0:
                    await self._ws.unsubscribe_trade(self.symbol)
            except Exception:
                pass
        # Unblock start() if waiting on stop_event
        if self._stop_event:
            self._stop_event.set()
        logger.info("Trading engine stopped")

    async def _load_history(self):
        """Pre-load historical candles for strategy lookback."""
        logger.info(f"Loading {self.lookback} historical candles...")
        klines = await self.client.get_klines_full(
            self.symbol, self.timeframe, limit=self.lookback
        )
        for k in klines:
            self._candle_buffer.append(k)
        logger.info(f"Loaded {len(self._candle_buffer)} historical candles")

    async def _on_trade(self, data: dict):
        """Handle incoming trade from WebSocket."""
        if isinstance(data, dict) and "price" in data:
            price = float(data["price"])
            # Keep paper executor price in sync
            if hasattr(self.executor, "set_price"):
                self.executor.set_price(self.symbol, price)
            # Update position PnL
            self.position_manager.update_unrealized_pnl(self.symbol, price)
            # Check risk
            balance = await self.executor.get_balance("USDT")
            pos = self.position_manager.get_position(self.symbol)
            total_value = balance + (pos.size * price if pos else 0)
            self.risk_manager.update(total_value)

    async def _candle_loop(self):
        """Periodically check for new candle and evaluate strategy."""
        interval_seconds = self.tf.minutes * 60

        while self._running:
            await asyncio.sleep(10)  # Check every 10 seconds

            now = datetime.now(timezone.utc).timestamp()
            # Check if a new candle period has started
            current_period = int(now // interval_seconds) * interval_seconds
            if current_period > self._last_signal_time:
                self._last_signal_time = current_period
                await self._evaluate_signals()

    async def _evaluate_signals(self):
        """Evaluate strategy and execute trades."""
        if self.risk_manager.should_halt():
            logger.warning("Trading halted due to risk limits")
            return

        if len(self._candle_buffer) < 50:
            logger.debug("Not enough candles for signal generation")
            return

        # Refresh latest candles from API
        try:
            latest = await self.client.get_klines(self.symbol, self.timeframe, limit=5)
            for k in latest:
                # Update or append
                existing_ts = {c["timestamp"] for c in self._candle_buffer}
                if k["timestamp"] not in existing_ts:
                    self._candle_buffer.append(k)
        except Exception as e:
            logger.error(f"Failed to refresh candles: {e}")

        # Build DataFrame
        df = pd.DataFrame(list(self._candle_buffer))
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("datetime").sort_index()

        # Generate signals
        signals = self.strategy.generate_signals(df, self.params)

        # Check signal on the last COMPLETED candle (iloc[-2])
        # iloc[-1] is the current in-progress candle — signals aren't final yet
        has_position = self.position_manager.has_position(self.symbol)
        latest_entry_long = bool(signals.entries_long.iloc[-2])
        latest_exit_long = bool(signals.exits_long.iloc[-2])
        latest_entry_short = bool(signals.entries_short.iloc[-2])
        latest_exit_short = bool(signals.exits_short.iloc[-2])

        # Prefer real-time WS price over stale candle close
        candle_close = float(df["close"].iloc[-1])
        if hasattr(self.executor, "_current_prices") and self.symbol in self.executor._current_prices:
            current_price = self.executor._current_prices[self.symbol]
        else:
            current_price = candle_close
            if hasattr(self.executor, "set_price"):
                self.executor.set_price(self.symbol, current_price)
        pos = self.position_manager.get_position(self.symbol)

        logger.info(
            f"Signal check: entry_long={latest_entry_long} exit_long={latest_exit_long} "
            f"entry_short={latest_entry_short} exit_short={latest_exit_short} "
            f"has_pos={has_position} price={current_price:.2f}"
        )

        # Determine action for signal log
        if has_position and pos:
            if pos.side == Side.LONG and latest_exit_long:
                sig_action = "平多"
            elif pos.side == Side.SHORT and latest_exit_short:
                sig_action = "平空"
            else:
                sig_action = "持倉中"
        elif latest_entry_long:
            sig_action = "做多"
        elif latest_entry_short and self._can_short:
            sig_action = "做空"
        else:
            sig_action = "無信號"

        self._signal_log.append({
            "time": datetime.now(timezone.utc).strftime("%m/%d %H:%M"),
            "price": round(current_price, 2),
            "action": sig_action,
        })

        try:
            if has_position and pos:
                # Check exits
                if pos.side == Side.LONG and latest_exit_long:
                    await self._close_position(current_price)
                elif pos.side == Side.SHORT and latest_exit_short:
                    await self._close_position(current_price)
                # Check risk-based exits
                elif self.risk_manager.check_stop_loss(pos.entry_price, current_price, pos.side.value):
                    logger.info(f"Stop-loss triggered for {self.symbol}")
                    await self._close_position(current_price)
                elif self.risk_manager.check_take_profit(pos.entry_price, current_price, pos.side.value):
                    logger.info(f"Take-profit triggered for {self.symbol}")
                    await self._close_position(current_price)
            else:
                # Check entries (spot live pairs can only go long)
                if latest_entry_long:
                    await self._open_position(Side.LONG, current_price)
                elif latest_entry_short and self._can_short:
                    await self._open_position(Side.SHORT, current_price)
        except Exception as e:
            logger.error(f"Trade execution error: {e}")

    async def _open_position(self, side: Side, price: float):
        """Open a new position."""
        balance = await self.executor.get_balance("USDT")
        # Calculate position size with leverage
        size = self.risk_manager.calculate_position_size(
            balance, price, leverage=self.leverage
        )

        if size <= 0:
            logger.warning("Calculated position size is 0, skipping")
            return

        order_side = "BUY" if side == Side.LONG else "SELL"
        logger.info(f"Opening {side.value} position: {order_side} {size:.8f} {self.symbol} @ {price:.2f}")
        order = await self.executor.place_market_order(
            self.symbol, order_side, size, leverage=self.leverage
        )

        fill_price = float(order.get("price", price))
        self.position_manager.open_position(self.symbol, side, fill_price, size)

        if self._on_trade_callback:
            try:
                self._on_trade_callback("open", side.value, fill_price, size, 0.0)
            except Exception:
                pass

    async def _close_position(self, price: float):
        """Close current position."""
        pos = self.position_manager.get_position(self.symbol)
        if not pos:
            return

        order_side = "SELL" if pos.side == Side.LONG else "BUY"
        logger.info(f"Closing {pos.side.value} position: {order_side} {pos.size:.8f} {self.symbol} @ {price:.2f}")
        order = await self.executor.place_market_order(
            self.symbol, order_side, pos.size, leverage=self.leverage
        )

        # Use actual fill price if available
        fill_price = float(order.get("price", price))
        pnl = (fill_price - pos.entry_price) * pos.size if pos.side == Side.LONG else (pos.entry_price - fill_price) * pos.size
        logger.info(f"Closed at fill_price={fill_price:.2f} PnL={pnl:+.2f}")
        self.position_manager.close_position(self.symbol, fill_price)

        if self._on_trade_callback:
            try:
                self._on_trade_callback("close", pos.side.value, fill_price, pos.size, pnl)
            except Exception:
                pass

    # ─── Missed Signal Detection ──────────────────────────────────

    def detect_missed_signal(self, lookback_candles: int = 20) -> dict | None:
        """Detect if there's an unacted entry signal in recent history.

        Walks backwards from the 2nd-most-recent candle (skip latest —
        the engine's candle loop handles it) looking for entry signals
        not followed by an exit signal.

        Returns dict with side/signal_time/signal_price/candles_ago/current_price
        or None if no missed signal.
        """
        if len(self._candle_buffer) < 50:
            return None
        if self.position_manager.has_position(self.symbol):
            return None

        df = pd.DataFrame(list(self._candle_buffer))
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("datetime").sort_index()
        signals = self.strategy.generate_signals(df, self.params)

        start = len(df) - 2  # skip latest candle
        end = max(0, start - lookback_candles)
        for i in range(start, end, -1):
            # Exit found first → position was closed, no missed entry
            if bool(signals.exits_long.iloc[i]) or bool(signals.exits_short.iloc[i]):
                return None
            if bool(signals.entries_long.iloc[i]):
                return {
                    "side": "long",
                    "signal_time": df.index[i].isoformat(),
                    "signal_price": float(df["close"].iloc[i]),
                    "candles_ago": start - i + 1,
                    "current_price": float(df["close"].iloc[-1]),
                }
            if bool(signals.entries_short.iloc[i]) and self._can_short:
                return {
                    "side": "short",
                    "signal_time": df.index[i].isoformat(),
                    "signal_price": float(df["close"].iloc[i]),
                    "candles_ago": start - i + 1,
                    "current_price": float(df["close"].iloc[-1]),
                }
        return None

    async def force_open_position(self, side: Side, price: float | None = None):
        """Force open a position at current market price.

        Used for missed signal recovery. Reuses the same position sizing
        and execution path as normal trading.
        """
        if self.position_manager.has_position(self.symbol):
            raise RuntimeError("Already has an open position")
        if side == Side.SHORT and not self._can_short:
            raise RuntimeError("現貨交易對不支援做空，僅合約 (PERP) 可做空")
        if price is None:
            if self._candle_buffer:
                price = float(list(self._candle_buffer)[-1]["close"])
            else:
                raise RuntimeError("No price data available")
        if hasattr(self.executor, "set_price"):
            self.executor.set_price(self.symbol, price)
        await self._open_position(side, price)
