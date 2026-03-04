"""Yahoo Finance polling-based paper trading engine."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

from tradeengine.data.models import Side, Timeframe
from tradeengine.data.store import DataStore
from tradeengine.data.yahoo_client import YahooClient
from tradeengine.strategies.base import BaseStrategy
from tradeengine.trading.executor import OrderExecutor
from tradeengine.trading.position_manager import PositionManager
from tradeengine.trading.risk_manager import RiskConfig, RiskManager

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yahoo-poll")


class YahooTradingEngine:
    """Polling-based paper trading engine for Yahoo Finance symbols.

    Replaces PionexWebSocket with periodic yfinance polling.
    Suitable for 15M+ timeframes (Yahoo free API has 15-min delay).
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        executor: OrderExecutor,
        yahoo_client: YahooClient,
        store: DataStore,
        symbol: str,
        timeframe: str,
        params: dict[str, Any],
        risk_config: RiskConfig | None = None,
        initial_capital: float = 10000.0,
        lookback: int = 200,
        poll_interval: int = 60,
    ):
        self.strategy = strategy
        self.executor = executor
        self.yahoo_client = yahoo_client
        self.store = store
        self.symbol = symbol
        self.timeframe = timeframe
        self.tf = Timeframe(timeframe)
        self.params = params
        self.initial_capital = initial_capital
        self.lookback = lookback
        self.poll_interval = poll_interval

        self.position_manager = PositionManager()
        self.risk_manager = RiskManager(
            risk_config or RiskConfig(), initial_capital
        )

        self._running = False
        self._candle_buffer: deque[dict] = deque(maxlen=lookback)
        self._last_signal_time: float = 0
        self._on_trade_callback: Callable | None = None

    def on_trade(self, callback: Callable):
        """Register callback for trade events."""
        self._on_trade_callback = callback

    async def start(self):
        """Start the Yahoo polling trading loop."""
        logger.info(
            f"Starting Yahoo trading engine: {self.strategy.display_name} | "
            f"{self.symbol} | {self.timeframe} (poll every {self.poll_interval}s)"
        )
        self._running = True
        await self._load_history()

        interval_seconds = self.tf.minutes * 60

        while self._running:
            await asyncio.sleep(self.poll_interval)

            # Poll latest price
            try:
                loop = asyncio.get_event_loop()
                price = await loop.run_in_executor(
                    _executor,
                    lambda: self.yahoo_client.get_latest_price(self.symbol),
                )
                if price > 0:
                    if hasattr(self.executor, "set_price"):
                        self.executor.set_price(self.symbol, price)
                    self.position_manager.update_unrealized_pnl(self.symbol, price)
                    quote = self._quote_asset()
                    balance = await self.executor.get_balance(quote)
                    pos = self.position_manager.get_position(self.symbol)
                    total_value = balance + (pos.size * price if pos else 0)
                    self.risk_manager.update(total_value)
            except Exception as e:
                logger.warning(f"Price poll failed: {e}")

            # Check candle boundary
            now = datetime.now(timezone.utc).timestamp()
            current_period = int(now // interval_seconds) * interval_seconds
            if current_period > self._last_signal_time:
                self._last_signal_time = current_period
                await self._evaluate_signals()

    async def stop(self):
        """Stop the polling loop."""
        self._running = False
        logger.info("Yahoo trading engine stopped")

    def _quote_asset(self) -> str:
        if "=" in self.symbol:
            return "USD"
        parts = self.symbol.split("_")
        return parts[1] if len(parts) > 1 else "USD"

    async def _load_history(self):
        """Pre-load historical candles from Yahoo Finance."""
        logger.info(f"Loading {self.lookback} historical candles from Yahoo Finance...")
        loop = asyncio.get_event_loop()
        klines = await loop.run_in_executor(
            _executor,
            lambda: self.yahoo_client.get_klines_full(
                self.symbol, self.timeframe, limit=self.lookback
            ),
        )
        for k in klines:
            self._candle_buffer.append(k)
        logger.info(f"Loaded {len(self._candle_buffer)} historical candles")

    async def _evaluate_signals(self):
        """Refresh candles and evaluate strategy signals."""
        if self.risk_manager.should_halt():
            logger.warning("Trading halted due to risk limits")
            return

        if len(self._candle_buffer) < 50:
            logger.debug("Not enough candles for signal generation")
            return

        # Refresh latest candles
        try:
            loop = asyncio.get_event_loop()
            latest = await loop.run_in_executor(
                _executor,
                lambda: self.yahoo_client.get_klines(
                    self.symbol, self.timeframe, limit=5
                ),
            )
            existing_ts = {c["timestamp"] for c in self._candle_buffer}
            for k in latest:
                if k["timestamp"] not in existing_ts:
                    self._candle_buffer.append(k)
        except Exception as e:
            logger.error(f"Failed to refresh candles: {e}")

        # Build DataFrame
        df = pd.DataFrame(list(self._candle_buffer))
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("datetime").sort_index()

        signals = self.strategy.generate_signals(df, self.params)

        has_position = self.position_manager.has_position(self.symbol)
        latest_entry_long = bool(signals.entries_long.iloc[-1])
        latest_exit_long = bool(signals.exits_long.iloc[-1])
        latest_entry_short = bool(signals.entries_short.iloc[-1])
        latest_exit_short = bool(signals.exits_short.iloc[-1])

        current_price = float(df["close"].iloc[-1])
        if hasattr(self.executor, "set_price"):
            self.executor.set_price(self.symbol, current_price)
        pos = self.position_manager.get_position(self.symbol)

        logger.info(
            f"Signal check [{self.symbol}]: "
            f"entry_long={latest_entry_long} exit_long={latest_exit_long} "
            f"entry_short={latest_entry_short} exit_short={latest_exit_short} "
            f"has_pos={has_position} price={current_price:.2f}"
        )

        try:
            if has_position and pos:
                if pos.side == Side.LONG and latest_exit_long:
                    await self._close_position(current_price)
                elif pos.side == Side.SHORT and latest_exit_short:
                    await self._close_position(current_price)
                elif self.risk_manager.check_stop_loss(pos.entry_price, current_price, pos.side.value):
                    logger.info(f"Stop-loss triggered for {self.symbol}")
                    await self._close_position(current_price)
                elif self.risk_manager.check_take_profit(pos.entry_price, current_price, pos.side.value):
                    logger.info(f"Take-profit triggered for {self.symbol}")
                    await self._close_position(current_price)
            else:
                if latest_entry_long:
                    await self._open_position(Side.LONG, current_price)
                elif latest_entry_short:
                    await self._open_position(Side.SHORT, current_price)
        except Exception as e:
            logger.error(f"Trade execution error: {e}")

    async def _open_position(self, side: Side, price: float):
        quote = self._quote_asset()
        balance = await self.executor.get_balance(quote)
        size = self.risk_manager.calculate_position_size(balance, price)

        if size <= 0:
            logger.warning("Calculated position size is 0, skipping")
            return

        order_side = "BUY" if side == Side.LONG else "SELL"
        logger.info(f"Opening {side.value} position: {order_side} {size:.4f} {self.symbol} @ {price:.2f}")
        order = await self.executor.place_market_order(self.symbol, order_side, size)

        fill_price = float(order.get("price", price))
        self.position_manager.open_position(self.symbol, side, fill_price, size)

        if self._on_trade_callback:
            try:
                self._on_trade_callback("open", side.value, fill_price, size, 0.0)
            except Exception:
                pass

    async def _close_position(self, price: float):
        pos = self.position_manager.get_position(self.symbol)
        if not pos:
            return

        pnl = (price - pos.entry_price) * pos.size if pos.side == Side.LONG else (pos.entry_price - price) * pos.size
        order_side = "SELL" if pos.side == Side.LONG else "BUY"
        logger.info(f"Closing {pos.side.value}: {order_side} {pos.size:.4f} {self.symbol} @ {price:.2f} PnL={pnl:+.2f}")
        await self.executor.place_market_order(self.symbol, order_side, pos.size)
        self.position_manager.close_position(self.symbol, price)

        if self._on_trade_callback:
            try:
                self._on_trade_callback("close", pos.side.value, price, pos.size, pnl)
            except Exception:
                pass

    # ─── Missed Signal Detection ──────────────────────────────────

    def detect_missed_signal(self, lookback_candles: int = 20) -> dict | None:
        """Detect if there's an unacted entry signal in recent history."""
        if len(self._candle_buffer) < 50:
            return None
        if self.position_manager.has_position(self.symbol):
            return None

        df = pd.DataFrame(list(self._candle_buffer))
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("datetime").sort_index()
        signals = self.strategy.generate_signals(df, self.params)

        start = len(df) - 2
        end = max(0, start - lookback_candles)
        for i in range(start, end, -1):
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
            if bool(signals.entries_short.iloc[i]):
                return {
                    "side": "short",
                    "signal_time": df.index[i].isoformat(),
                    "signal_price": float(df["close"].iloc[i]),
                    "candles_ago": start - i + 1,
                    "current_price": float(df["close"].iloc[-1]),
                }
        return None

    async def force_open_position(self, side: Side, price: float | None = None):
        """Force open a position at current market price."""
        if self.position_manager.has_position(self.symbol):
            raise RuntimeError("Already has an open position")
        if price is None:
            if self._candle_buffer:
                price = float(list(self._candle_buffer)[-1]["close"])
            else:
                raise RuntimeError("No price data available")
        if hasattr(self.executor, "set_price"):
            self.executor.set_price(self.symbol, price)
        await self._open_position(side, price)
