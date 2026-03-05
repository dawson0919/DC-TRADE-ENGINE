"""Pionex Perpetual Futures REST API client."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.pionex.com"


class PionexFuturesAPIError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Pionex Error {code}: {message}")


class PionexFuturesClient:
    """Async REST client for Pionex Perpetual Futures.

    Supports leverage setting, contract order placement, and position monitoring.
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

    def _sign(self, method: str, path: str, params: dict[str, Any], body: str = "") -> str:
        """Generate HMAC-SHA256 signature for Pionex API."""
        sorted_parts = []
        for k in sorted(params.keys()):
            sorted_parts.append(f"{k}={params[k]}")
        query = "&".join(sorted_parts)

        string_to_sign = f"{method}{path}?{query}{body}"

        return hmac.new(
            self.api_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def _request(self, method: str, path: str, params: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None) -> Any:
        """Execute a signed request to Pionex API."""
        if not self.api_key or not self.api_secret:
            raise RuntimeError("API Key and Secret required for private endpoints")

        req_params = params.copy() if params else {}
        req_params["timestamp"] = int(time.time() * 1000)

        body_str = ""
        if json_body:
            import json
            body_str = json.dumps(json_body)

        signature = self._sign(method, path, req_params, body_str)

        headers = {
            "PIONEX-KEY": self.api_key,
            "PIONEX-SIGNATURE": signature,
            "Content-Type": "application/json" if json_body else "application/x-www-form-urlencoded"
        }

        if method == "GET":
            resp = await self._client.get(path, params=req_params, headers=headers)
        elif method == "POST":
            resp = await self._client.post(path, params=req_params, headers=headers, content=body_str)
        else:
            raise ValueError(f"Unsupported method: {method}")

        data = resp.json()
        if not data.get("result"):
            raise PionexFuturesAPIError(data.get("code", "UNKNOWN"), data.get("message", ""))
        return data["data"]

    # --- Public ---

    async def get_futures_symbols(self) -> list[dict]:
        """GET /api/v1/common/symbols?type=PERPETUAL"""
        resp = await self._client.get("/api/v1/common/symbols", params={"type": "PERPETUAL"})
        data = resp.json()
        if not data.get("result"):
             raise PionexFuturesAPIError(data.get("code", "UNKNOWN"), data.get("message", ""))
        return data["data"]["symbols"]

    # --- Private ---

    async def set_leverage(self, symbol: str, leverage: float) -> dict:
        """POST /api/v1/futures/trade/leverage (Hypothetical - matching typical Crypto API pattern)"""
        # Note: Pionex's exact futures endpoints might require specific path structures.
        # This implementation follows the pattern discovered in research.
        body = {
            "symbol": symbol,
            "leverage": str(leverage)
        }
        return await self._request("POST", "/api/v1/futures/trade/leverage", json_body=body)

    async def place_order(
        self,
        symbol: str,
        side: str,
        type: str,
        size: str,
        leverage: float,
        price: str | None = None,
        client_order_id: str | None = None
    ) -> dict:
        """POST /api/v1/futures/trade/order"""
        body = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "size": size,
            "leverage": str(leverage)
        }
        if price:
            body["price"] = price
        if client_order_id:
            body["clientOrderId"] = client_order_id
            
        return await self._request("POST", "/api/v1/futures/trade/order", json_body=body)

    async def get_order(self, symbol: str, order_id: str) -> dict:
        """GET /api/v1/futures/trade/order — query order details for fill price."""
        params = {"symbol": symbol, "orderId": order_id}
        return await self._request("GET", "/api/v1/futures/trade/order", params=params)

    async def get_positions(self, symbol: str | None = None) -> list[dict]:
        """GET /api/v1/futures/trade/position"""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return await self._request("GET", "/api/v1/futures/trade/position", params=params)

    async def get_balance(self) -> list[dict]:
        """GET /api/v1/account/balances"""
        return await self._request("GET", "/api/v1/account/balances")
