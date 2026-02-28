"""Pionex WebSocket client for real-time market data."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

import websockets

logger = logging.getLogger(__name__)

WS_URL = "wss://ws.pionex.com/wsPub"


class PionexWebSocket:
    """Async WebSocket client for Pionex real-time data.

    Subscribes to trade and depth channels, aggregates candles from trades.
    """

    def __init__(self):
        self._ws = None
        self._running = False
        self._callbacks: dict[str, list[Callable]] = {}
        self._subscriptions: list[dict] = []
        self._last_pong = 0

    async def connect(self):
        """Connect to Pionex WebSocket."""
        self._ws = await websockets.connect(WS_URL, ping_interval=20)
        self._running = True
        logger.info("Connected to Pionex WebSocket")

    async def subscribe_trade(self, symbol: str):
        """Subscribe to trade stream for a symbol."""
        msg = {"op": "SUBSCRIBE", "topic": "TRADE", "symbol": symbol}
        self._subscriptions.append(msg)
        await self._ws.send(json.dumps(msg))
        logger.info(f"Subscribed to TRADE {symbol}")

    async def subscribe_depth(self, symbol: str):
        """Subscribe to order book depth stream."""
        msg = {"op": "SUBSCRIBE", "topic": "DEPTH", "symbol": symbol}
        self._subscriptions.append(msg)
        await self._ws.send(json.dumps(msg))
        logger.info(f"Subscribed to DEPTH {symbol}")

    def on(self, event: str, callback: Callable):
        """Register a callback for an event type (trade, depth, error)."""
        self._callbacks.setdefault(event, []).append(callback)

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
                if data.get("type") == "SUBSCRIBED":
                    logger.info(f"Subscription confirmed: {topic} {data.get('symbol', '')}")
                    continue
                if topic == "TRADE":
                    trades = data.get("data", [])
                    if isinstance(trades, list):
                        for t in trades:
                            await self._dispatch("trade", t)
                    else:
                        await self._dispatch("trade", trades)
                elif topic == "DEPTH":
                    await self._dispatch("depth", data.get("data", {}))

            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
                await self._reconnect()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await self._dispatch("error", {"error": str(e)})

    async def _dispatch(self, event: str, data: Any):
        for cb in self._callbacks.get(event, []):
            if asyncio.iscoroutinefunction(cb):
                await cb(data)
            else:
                cb(data)

    async def _reconnect(self):
        """Attempt to reconnect and restore subscriptions."""
        await asyncio.sleep(5)
        try:
            await self.connect()
            # Re-subscribe to all previous topics
            if self._ws:
                for msg in self._subscriptions:
                    try:
                        await self._ws.send(json.dumps(msg))
                        logger.info(f"Re-subscribed to {msg.get('topic', '?')}")
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Reconnect failed: {e}")

    async def close(self):
        self._running = False
        if self._ws:
            await self._ws.close()
