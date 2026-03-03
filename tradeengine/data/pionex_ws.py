"""Pionex WebSocket client for real-time market data."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Callable

import websockets

logger = logging.getLogger(__name__)

WS_URL = "wss://ws.pionex.com/wsPub"

# Retry settings for rate-limited connections
_MAX_RETRIES = 6
_BASE_DELAY = 2.0   # seconds
_MAX_DELAY = 60.0    # seconds


class PionexWebSocket:
    """Async WebSocket client for Pionex real-time data.

    Supports shared usage: multiple engines can subscribe to different symbols
    on a single connection, with symbol-based callback routing.
    """

    def __init__(self):
        self._ws = None
        self._running = False
        self._callbacks: dict[str, list[Callable]] = {}
        self._symbol_callbacks: dict[str, dict[str, list[Callable]]] = {}
        self._subscriptions: list[dict] = []
        self._subscribed_symbols: set[str] = set()
        self._last_pong = 0
        self._retry_count = 0
        self._listen_task: asyncio.Task | None = None

    async def connect(self):
        """Connect to Pionex WebSocket with exponential backoff on 429."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._ws = await websockets.connect(WS_URL, ping_interval=20)
                self._running = True
                self._retry_count = 0
                logger.info("Connected to Pionex WebSocket")
                return
            except Exception as e:
                is_429 = "429" in str(e)
                if attempt >= _MAX_RETRIES:
                    logger.error(f"WebSocket connect failed after {_MAX_RETRIES} attempts: {e}")
                    raise
                if is_429:
                    # 429 rate limit: use longer delays (30s base)
                    delay = min(30.0 * (2 ** (attempt - 1)), 120.0)
                else:
                    delay = min(_BASE_DELAY * (2 ** (attempt - 1)), _MAX_DELAY)
                jitter = random.uniform(0, delay * 0.3)
                wait = delay + jitter
                logger.warning(
                    f"WebSocket connect attempt {attempt}/{_MAX_RETRIES} failed "
                    f"({'rate limited' if is_429 else str(e)}), "
                    f"retrying in {wait:.1f}s"
                )
                await asyncio.sleep(wait)

    async def subscribe_trade(self, symbol: str):
        """Subscribe to trade stream for a symbol.

        Safe to call multiple times — skips if already subscribed.
        """
        if symbol in self._subscribed_symbols:
            logger.info(f"Already subscribed to TRADE {symbol}, skipping")
            return
        msg = {"op": "SUBSCRIBE", "topic": "TRADE", "symbol": symbol}
        self._subscriptions.append(msg)
        self._subscribed_symbols.add(symbol)
        if self._ws:
            await self._ws.send(json.dumps(msg))
        logger.info(f"Subscribed to TRADE {symbol}")

    async def unsubscribe_trade(self, symbol: str):
        """Unsubscribe from trade stream for a symbol."""
        if symbol not in self._subscribed_symbols:
            return
        msg = {"op": "UNSUBSCRIBE", "topic": "TRADE", "symbol": symbol}
        try:
            if self._ws:
                await self._ws.send(json.dumps(msg))
        except Exception:
            pass
        self._subscribed_symbols.discard(symbol)
        self._subscriptions = [
            s for s in self._subscriptions
            if not (s.get("topic") == "TRADE" and s.get("symbol") == symbol)
        ]
        # Remove symbol-specific callbacks
        for event in list(self._symbol_callbacks):
            self._symbol_callbacks[event].pop(symbol, None)
        logger.info(f"Unsubscribed from TRADE {symbol}")

    async def subscribe_depth(self, symbol: str):
        """Subscribe to order book depth stream."""
        if symbol in self._subscribed_symbols:
            return
        msg = {"op": "SUBSCRIBE", "topic": "DEPTH", "symbol": symbol}
        self._subscriptions.append(msg)
        self._subscribed_symbols.add(symbol)
        if self._ws:
            await self._ws.send(json.dumps(msg))
        logger.info(f"Subscribed to DEPTH {symbol}")

    def on(self, event: str, callback: Callable):
        """Register a global callback for an event type (trade, depth, error)."""
        self._callbacks.setdefault(event, []).append(callback)

    def on_symbol(self, event: str, symbol: str, callback: Callable):
        """Register a callback for a specific symbol's events."""
        self._symbol_callbacks.setdefault(event, {}).setdefault(symbol, []).append(callback)

    def off_symbol(self, event: str, symbol: str, callback: Callable | None = None):
        """Remove callback(s) for a specific symbol.

        If callback is None, removes all callbacks for that symbol/event.
        """
        if event not in self._symbol_callbacks:
            return
        if symbol not in self._symbol_callbacks[event]:
            return
        if callback is None:
            del self._symbol_callbacks[event][symbol]
        else:
            self._symbol_callbacks[event][symbol] = [
                cb for cb in self._symbol_callbacks[event][symbol] if cb != callback
            ]

    async def ensure_listening(self):
        """Start the listen loop as a background task if not already running."""
        if self._listen_task is None or self._listen_task.done():
            self._listen_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self):
        """Background listen loop — wraps listen() with auto-restart."""
        while self._running:
            try:
                await self.listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Listen loop crashed: {e}, restarting...")
                await asyncio.sleep(2)

    async def listen(self):
        """Main listen loop. Dispatches messages to registered callbacks."""
        while self._running and self._ws:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=30)
                data = json.loads(raw)

                if data.get("op") == "PING":
                    await self._ws.send(json.dumps({"op": "PONG", "timestamp": data.get("timestamp")}))
                    self._last_pong = time.time()
                    continue

                topic = data.get("topic", "")
                msg_symbol = data.get("symbol", "")

                if data.get("type") == "SUBSCRIBED":
                    logger.info(f"Subscription confirmed: {topic} {msg_symbol}")
                    continue
                if topic == "TRADE":
                    trades = data.get("data", [])
                    if isinstance(trades, list):
                        for t in trades:
                            await self._dispatch("trade", t, symbol=msg_symbol)
                    else:
                        await self._dispatch("trade", trades, symbol=msg_symbol)
                elif topic == "DEPTH":
                    await self._dispatch("depth", data.get("data", {}), symbol=msg_symbol)

            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
                await self._reconnect()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await self._dispatch("error", {"error": str(e)})

    async def _dispatch(self, event: str, data: Any, symbol: str = ""):
        """Dispatch event to both global and symbol-specific callbacks."""
        # Global callbacks (backward compatible)
        for cb in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(data)
                else:
                    cb(data)
            except Exception as e:
                logger.error(f"Callback error ({event}): {e}")

        # Symbol-specific callbacks
        if symbol and event in self._symbol_callbacks:
            for cb in self._symbol_callbacks[event].get(symbol, []):
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(data)
                    else:
                        cb(data)
                except Exception as e:
                    logger.error(f"Symbol callback error ({event}/{symbol}): {e}")

    async def _reconnect(self):
        """Attempt to reconnect with exponential backoff and restore subscriptions."""
        self._retry_count += 1
        delay = min(_BASE_DELAY * (2 ** (self._retry_count - 1)), _MAX_DELAY)
        jitter = random.uniform(0, delay * 0.3)
        wait = delay + jitter
        logger.info(f"Reconnecting in {wait:.1f}s (attempt {self._retry_count})...")
        await asyncio.sleep(wait)
        try:
            await self.connect()
            self._retry_count = 0  # reset on success
            # Re-subscribe to all previous topics
            if self._ws:
                for msg in self._subscriptions:
                    try:
                        await self._ws.send(json.dumps(msg))
                        logger.info(f"Re-subscribed to {msg.get('topic', '?')} {msg.get('symbol', '')}")
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Reconnect failed: {e}")

    async def close(self):
        self._running = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
        self._subscribed_symbols.clear()

    @property
    def is_connected(self) -> bool:
        """Check if the WebSocket is connected and running."""
        return self._running and self._ws is not None
