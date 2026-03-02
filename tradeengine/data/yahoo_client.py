"""Yahoo Finance client for traditional futures OHLCV data."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# yfinance max lookback per interval (free tier)
YAHOO_MAX_PERIOD = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "1h": "730d",
    "4h": "730d",
    "1d": "max",
}


class YahooClient:
    """Synchronous Yahoo Finance client.

    Fetches OHLCV data for futures (NQ=F, ES=F, SI=F, GC=F).
    Returns list[dict] in the same format as PionexClient.get_klines().

    Note: All methods are synchronous — use run_in_executor for async callers.
    """

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        end_time: int | None = None,
    ) -> list[dict]:
        """Fetch OHLCV bars from Yahoo Finance.

        Args:
            symbol: Yahoo Finance symbol (NQ=F, ES=F, SI=F, GC=F)
            interval: engine timeframe string (15m, 1h, 4h, 1d)
            limit: max number of bars to return
            end_time: ignored (kept for interface compatibility)
        """
        import yfinance as yf

        period = YAHOO_MAX_PERIOD.get(interval, "max")
        logger.info(f"Fetching {symbol} {interval} from Yahoo Finance (period={period})")

        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)

        if df is None or df.empty:
            logger.warning(f"No data from Yahoo Finance for {symbol} {interval}")
            return []

        # Normalize to UTC
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        df = df.sort_index()
        if limit and len(df) > limit:
            df = df.tail(limit)

        return self._to_kline_list(df)

    def get_klines_full(
        self,
        symbol: str,
        interval: str,
        limit: int = 5000,
        end_time: int | None = None,
    ) -> list[dict]:
        """Fetch full history (yfinance returns all available in one call)."""
        return self.get_klines(symbol, interval, limit=limit)

    def get_latest_price(self, symbol: str) -> float:
        """Fetch the most recent price for a symbol."""
        import yfinance as yf

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = getattr(info, "last_price", None) or getattr(info, "regular_market_price", None)
            if price:
                return float(price)
            df = ticker.history(period="1d", interval="1m", auto_adjust=True)
            if df is not None and not df.empty:
                return float(df["Close"].iloc[-1])
        except Exception as e:
            logger.warning(f"Could not fetch latest price for {symbol}: {e}")
        return 0.0

    @staticmethod
    def _to_kline_list(df: pd.DataFrame) -> list[dict]:
        """Convert yfinance DataFrame to list[dict] matching PionexClient format."""
        result = []
        for ts, row in df.iterrows():
            ts_ms = int(ts.timestamp() * 1000)
            result.append({
                "timestamp": ts_ms,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row.get("Volume", 0) or 0),
            })
        return result
