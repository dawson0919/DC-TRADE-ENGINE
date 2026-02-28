"""Async live/paper trading engine."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

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
        lookback: int = 200,
    ):
        self.strategy = strategy
        self.executor = executor
        self.client = client
        self.symbol = symbol
        self.timeframe = timeframe
        self.tf = Timeframe(timeframe)
        self.params = params
        self.initial_capital = initial_capital
        self.lookback = lookback

        self.position_manager = PositionManager()
        self.risk_manager = RiskManager(
            risk_config or RiskConfig(), initial_capital
        )

        self._running = False
        self._candle_buffer: deque[dict] = deque(maxlen=lookback)
        self._current_candle: dict | None = None
        self._ws: PionexWebSocket | None = None
        self._last_signal_time: float = 0

    async def start(self):
        """Start the trading loop."""
        logger.info(
            f"Starting trading engine: {self.strategy.display_name} | "
            f"{self.symbol} | {self.timeframe}"
        )
        self._running = True

        # 1. Load historical candles for lookback
        await self._load_history()

        # 2. Connect WebSocket
        self._ws = PionexWebSocket()
        await self._ws.connect()
        await self._ws.subscribe_trade(self.symbol)

        self._ws.on("trade", self._on_trade)

        # 3. Start candle aggregation loop
        asyncio.create_task(self._candle_loop())

        # 4. Main listen loop
        await self._ws.listen()

    async def stop(self):
        """Stop the trading loop."""
        self._running = False
        if self._ws:
            await self._ws.close()
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
        # Update current price for risk management
        if isinstance(data, dict) and "price" in data:
            price = float(data["price"])
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

        # Check latest signal
        has_position = self.position_manager.has_position(self.symbol)
        latest_entry_long = bool(signals.entries_long.iloc[-1])
        latest_exit_long = bool(signals.exits_long.iloc[-1])
        latest_entry_short = bool(signals.entries_short.iloc[-1])
        latest_exit_short = bool(signals.exits_short.iloc[-1])

        current_price = float(df["close"].iloc[-1])
        pos = self.position_manager.get_position(self.symbol)

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
                # Check entries
                if latest_entry_long:
                    await self._open_position(Side.LONG, current_price)
                elif latest_entry_short:
                    await self._open_position(Side.SHORT, current_price)
        except Exception as e:
            logger.error(f"Trade execution error: {e}")

    async def _open_position(self, side: Side, price: float):
        """Open a new position."""
        balance = await self.executor.get_balance("USDT")
        size = self.risk_manager.calculate_position_size(balance, price)

        if size <= 0:
            logger.warning("Calculated position size is 0, skipping")
            return

        order_side = "BUY" if side == Side.LONG else "SELL"
        order = await self.executor.place_market_order(self.symbol, order_side, size)

        fill_price = float(order.get("price", price))
        self.position_manager.open_position(self.symbol, side, fill_price, size)

    async def _close_position(self, price: float):
        """Close current position."""
        pos = self.position_manager.get_position(self.symbol)
        if not pos:
            return

        order_side = "SELL" if pos.side == Side.LONG else "BUY"
        await self.executor.place_market_order(self.symbol, order_side, pos.size)
        self.position_manager.close_position(self.symbol, price)
