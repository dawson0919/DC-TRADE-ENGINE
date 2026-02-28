"""Unified data fetcher: pulls from Pionex, CSV files, or cache."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from tradeengine.data.pionex_client import PionexClient
from tradeengine.data.store import DataStore

logger = logging.getLogger(__name__)


def load_csv(path: str | Path) -> pd.DataFrame:
    """Load OHLCV from a TradingView-exported CSV file.

    Handles:
    - Unix seconds ``time`` column (TradingView format)
    - Uppercase ``Volume`` column
    - Extra indicator columns (ignored)

    Returns DataFrame with DatetimeIndex and lowercase ohlcv columns.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    df = pd.read_csv(path)

    # Normalise column names
    col_map = {}
    for c in df.columns:
        cl = c.strip().lower()
        if cl == "time":
            col_map[c] = "time"
        elif cl == "open":
            col_map[c] = "open"
        elif cl == "high":
            col_map[c] = "high"
        elif cl == "low":
            col_map[c] = "low"
        elif cl == "close":
            col_map[c] = "close"
        elif cl == "volume":
            col_map[c] = "volume"

    df = df.rename(columns=col_map)

    required = {"time", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")

    # Keep only OHLCV columns
    keep = ["time", "open", "high", "low", "close"]
    if "volume" in df.columns:
        keep.append("volume")
    df = df[keep].copy()

    # Detect timestamp unit: if max < 1e12 it is seconds; otherwise ms
    if df["time"].max() < 1e12:
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df["timestamp"] = (df["time"] * 1000).astype(int)
    else:
        df["datetime"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        df["timestamp"] = df["time"].astype(int)

    df = df.set_index("datetime").sort_index()

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    else:
        df["volume"] = 0.0

    logger.info(f"Loaded {len(df)} candles from CSV: {path.name} ({df.index[0]} ~ {df.index[-1]})")
    return df


class DataFetcher:
    """Fetches OHLCV data from Pionex and caches in local Parquet store."""

    def __init__(self, client: PionexClient, store: DataStore):
        self.client = client
        self.store = store

    async def fetch(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 5000,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Fetch OHLCV data, using cache when available.

        Returns a DataFrame with columns: timestamp, open, high, low, close, volume
        and a DatetimeIndex.
        """
        if use_cache:
            cached = self.store.load_ohlcv(symbol, timeframe)
            if cached is not None and len(cached) >= limit:
                logger.info(f"Using {len(cached)} cached candles for {symbol} {timeframe}")
                df = cached.tail(limit).reset_index(drop=True)
                return self._prepare_df(df)

        # Fetch from Pionex
        logger.info(f"Fetching {limit} candles from Pionex for {symbol} {timeframe}")
        klines = await self.client.get_klines_full(symbol, timeframe, limit=limit)

        if not klines:
            # Fallback to cache even if fewer candles than requested
            cached = self.store.load_ohlcv(symbol, timeframe)
            if cached is not None and len(cached) > 0:
                return self._prepare_df(cached)
            raise ValueError(f"No data available for {symbol} {timeframe}")

        df = pd.DataFrame(klines)
        # Cache it
        self.store.save_ohlcv(symbol, timeframe, df)

        return self._prepare_df(df.tail(limit).reset_index(drop=True))

    async def update_cache(self, symbol: str, timeframe: str) -> int:
        """Incrementally update cache with newest candles.

        Returns number of new candles fetched.
        """
        latest_ts = self.store.get_latest_timestamp(symbol, timeframe)
        klines = await self.client.get_klines(symbol, timeframe, limit=500)

        if not klines:
            return 0

        if latest_ts is not None:
            klines = [k for k in klines if k["timestamp"] > latest_ts]

        if klines:
            df = pd.DataFrame(klines)
            self.store.save_ohlcv(symbol, timeframe, df)

        return len(klines)

    @staticmethod
    def _prepare_df(df: pd.DataFrame) -> pd.DataFrame:
        """Convert raw OHLCV DataFrame to indexed format for vectorBT."""
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("datetime")
        df = df.sort_index()
        # Ensure correct dtypes
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
