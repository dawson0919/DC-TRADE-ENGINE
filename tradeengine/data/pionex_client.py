"""Pionex exchange REST API client."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.pionex.com"

# Interval mapping: our Timeframe enum value -> Pionex interval string
INTERVAL_MAP = {
    "1m": "1M",
    "5m": "5M",
    "15m": "15M",
    "30m": "30M",
    "1h": "60M",
    "4h": "4H",
    "1d": "1D",
}


def _sign(api_secret: str, method: str, path: str, params: dict[str, Any]) -> str:
    """Generate HMAC-SHA256 signature for Pionex API."""
    # Sort params by key in ascending ASCII order
    sorted_parts = []
    for k in sorted(params.keys()):
        sorted_parts.append(f"{k}={params[k]}")
    query = "&".join(sorted_parts)

    # Build string to sign: METHOD + PATH + ? + sorted_query
    string_to_sign = f"{method}{path}?{query}"

    return hmac.new(
        api_secret.encode(),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()


def _sign_post(
    api_secret: str, method: str, path: str, params: dict[str, Any], body: str
) -> str:
    """Generate HMAC-SHA256 signature for POST/DELETE requests."""
    sorted_parts = []
    for k in sorted(params.keys()):
        sorted_parts.append(f"{k}={params[k]}")
    query = "&".join(sorted_parts)

    string_to_sign = f"{method}{path}?{query}{body}"

    return hmac.new(
        api_secret.encode(),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()


class PionexClient:
    """Async REST client for Pionex exchange.

    Handles HMAC-SHA256 authentication, klines, orders, and balances.
    """

    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self._client = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    # ── Public endpoints ──────────────────────────────────────────────

    async def get_symbols(self, market_type: str = "SPOT") -> list[dict]:
        """GET /api/v1/common/symbols"""
        params: dict[str, Any] = {}
        if market_type:
            params["type"] = market_type
        resp = await self._client.get("/api/v1/common/symbols", params=params)
        data = resp.json()
        if not data.get("result"):
            raise PionexAPIError(data.get("code", "UNKNOWN"), data.get("message", ""))
        return data["data"]["symbols"]

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        end_time: int | None = None,
    ) -> list[dict]:
        """GET /api/v1/market/klines

        Args:
            symbol: e.g. "BTC_USDT"
            interval: our timeframe value, e.g. "1h", "4h", "1d"
            limit: 1-500 (default 500)
            end_time: ms timestamp (optional)

        Returns list of {time, open, high, low, close, volume}.
        """
        pionex_interval = INTERVAL_MAP.get(interval, interval.upper())
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": pionex_interval,
            "limit": min(limit, 500),
        }
        if end_time is not None:
            params["endTime"] = end_time

        resp = await self._client.get("/api/v1/market/klines", params=params)
        data = resp.json()
        if not data.get("result"):
            raise PionexAPIError(data.get("code", "UNKNOWN"), data.get("message", ""))

        klines = data["data"]["klines"]
        # Normalize: Pionex returns string values for OHLCV
        return [
            {
                "timestamp": int(k["time"]),
                "open": float(k["open"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "close": float(k["close"]),
                "volume": float(k["volume"]),
            }
            for k in klines
        ]

    async def get_klines_full(
        self,
        symbol: str,
        interval: str,
        limit: int = 5000,
        end_time: int | None = None,
    ) -> list[dict]:
        """Fetch up to `limit` klines by paginating (500 per request)."""
        all_klines: list[dict] = []
        remaining = limit
        current_end = end_time

        while remaining > 0:
            batch_size = min(remaining, 500)
            batch = await self.get_klines(symbol, interval, batch_size, current_end)
            if not batch:
                break
            all_klines = batch + all_klines  # prepend older data
            remaining -= len(batch)
            # Move end_time to before the oldest candle in this batch
            current_end = batch[0]["timestamp"] - 1
            if len(batch) < batch_size:
                break  # No more data available

        return all_klines

    async def get_ticker_24h(self, symbol: str) -> dict:
        """GET /api/v1/market/tickers (24h ticker)."""
        resp = await self._client.get(
            "/api/v1/market/tickers", params={"symbol": symbol}
        )
        data = resp.json()
        if not data.get("result"):
            raise PionexAPIError(data.get("code", "UNKNOWN"), data.get("message", ""))
        tickers = data["data"]["tickers"]
        return tickers[0] if tickers else {}

    # ── Private endpoints (require auth) ──────────────────────────────

    def _auth_headers(self, method: str, path: str, params: dict[str, Any], body: str = "") -> dict:
        """Build auth headers with timestamp, PIONEX-KEY, PIONEX-SIGNATURE."""
        timestamp_ms = int(time.time() * 1000)
        params_with_ts = {**params, "timestamp": timestamp_ms}

        if method == "GET":
            sig = _sign(self.api_secret, method, path, params_with_ts)
        else:
            sig = _sign_post(self.api_secret, method, path, params_with_ts, body)

        return {
            "PIONEX-KEY": self.api_key,
            "PIONEX-SIGNATURE": sig,
            "Content-Type": "application/json",
        }, params_with_ts

    async def get_balances(self) -> list[dict]:
        """GET /api/v1/account/balances

        Returns list of {coin, free, frozen}.
        """
        path = "/api/v1/account/balances"
        headers, params = self._auth_headers("GET", path, {})
        resp = await self._client.get(path, params=params, headers=headers)
        data = resp.json()
        if not data.get("result"):
            raise PionexAPIError(data.get("code", "UNKNOWN"), data.get("message", ""))
        return data["data"]["balances"]

    async def get_balance(self, coin: str) -> dict:
        """Get balance for a specific coin."""
        balances = await self.get_balances()
        for b in balances:
            if b["coin"].upper() == coin.upper():
                return {"coin": b["coin"], "free": float(b["free"]), "frozen": float(b["frozen"])}
        return {"coin": coin, "free": 0.0, "frozen": 0.0}

    async def new_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: str | None = None,
        price: str | None = None,
        amount: str | None = None,
        client_order_id: str | None = None,
        ioc: bool = False,
    ) -> dict:
        """POST /api/v1/trade/order

        Args:
            symbol: e.g. "BTC_USDT"
            side: "BUY" or "SELL"
            order_type: "LIMIT" or "MARKET"
            size: quantity (required for LIMIT and MARKET SELL)
            price: price (required for LIMIT)
            amount: quote amount (required for MARKET BUY)
            client_order_id: optional client order ID
            ioc: immediate-or-cancel flag

        Returns {orderId, clientOrderId}.
        """
        import json

        path = "/api/v1/trade/order"
        body_dict: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
        }
        if size is not None:
            body_dict["size"] = size
        if price is not None:
            body_dict["price"] = price
        if amount is not None:
            body_dict["amount"] = amount
        if client_order_id:
            body_dict["clientOrderId"] = client_order_id
        if ioc:
            body_dict["IOC"] = True

        body_str = json.dumps(body_dict, separators=(",", ":"))
        headers, params = self._auth_headers("POST", path, {}, body_str)
        resp = await self._client.post(
            path, params=params, headers=headers, content=body_str
        )
        data = resp.json()
        if not data.get("result"):
            raise PionexAPIError(data.get("code", "UNKNOWN"), data.get("message", ""))
        return data["data"]

    async def get_order(self, order_id: int) -> dict:
        """GET /api/v1/trade/order"""
        path = "/api/v1/trade/order"
        headers, params = self._auth_headers("GET", path, {"orderId": order_id})
        resp = await self._client.get(path, params=params, headers=headers)
        data = resp.json()
        if not data.get("result"):
            raise PionexAPIError(data.get("code", "UNKNOWN"), data.get("message", ""))
        return data["data"]

    async def cancel_order(self, symbol: str, order_id: int) -> dict:
        """DELETE /api/v1/trade/order"""
        import json

        path = "/api/v1/trade/order"
        body_dict = {"symbol": symbol, "orderId": order_id}
        body_str = json.dumps(body_dict, separators=(",", ":"))
        headers, params = self._auth_headers("DELETE", path, {}, body_str)
        resp = await self._client.request(
            "DELETE", path, params=params, headers=headers, content=body_str
        )
        data = resp.json()
        if not data.get("result"):
            raise PionexAPIError(data.get("code", "UNKNOWN"), data.get("message", ""))
        return data.get("data", {})

    async def get_open_orders(self, symbol: str) -> list[dict]:
        """GET /api/v1/trade/openOrders"""
        path = "/api/v1/trade/openOrders"
        headers, params = self._auth_headers("GET", path, {"symbol": symbol})
        resp = await self._client.get(path, params=params, headers=headers)
        data = resp.json()
        if not data.get("result"):
            raise PionexAPIError(data.get("code", "UNKNOWN"), data.get("message", ""))
        return data["data"].get("orders", [])


class PionexAPIError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Pionex API error [{code}]: {message}")
