"""Unified data fetcher: pulls from Pionex, CSV files, or cache."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from tradeengine.data.pionex_client import PionexClient
from tradeengine.data.store import DataStore

logger = logging.getLogger(__name__)

# Mapping from TradingView CSV symbol fragments → Yahoo/API symbols
_CSV_SYMBOL_MAP = {
    "MINI_NQ1!": "NQ=F",
    "MINI_ES1!": "ES=F",
    "NQ1!": "NQ=F",
    "ES1!": "ES=F",
    "GC1!": "GC=F",
    "SI1!": "SI=F",
    "CL1!": "CL=F",
    "SI_F": "SI=F",
    "GC_F": "GC=F",
    "NQ_F": "NQ=F",
    "ES_F": "ES=F",
    "CL_F": "CL=F",
}

_supplement_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="csv-supplement")


def _resolve_csv_symbol(csv_path: str, fallback_symbol: str = "") -> str:
    """Infer API symbol from CSV filename or fallback to explicit symbol."""
    name = Path(csv_path).stem.upper()
    # Check each mapping key against the filename
    for fragment, api_sym in _CSV_SYMBOL_MAP.items():
        if fragment.upper() in name:
            return api_sym
    # Fallback: only use if it's a futures symbol or the base matches the filename
    if fallback_symbol:
        if "=F" in fallback_symbol:
            return fallback_symbol
        if "_" in fallback_symbol:
            base = fallback_symbol.split("_")[0].upper()
            if base in name:
                return fallback_symbol
    return ""


async def supplement_csv(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    """Supplement CSV data with latest candles from online API.

    Fetches candles newer than the CSV's last timestamp from
    Yahoo Finance (for futures) or Pionex (for crypto), then merges.
    """
    import asyncio

    if df.empty:
        return df

    last_ts = int(df["timestamp"].iloc[-1])
    last_dt = df.index[-1]
    logger.info(f"CSV ends at {last_dt}, fetching newer data for {symbol} {timeframe}...")

    try:
        if "=F" in symbol:
            from tradeengine.data.yahoo_client import YahooClient
            client = YahooClient()
            loop = asyncio.get_event_loop()
            klines = await loop.run_in_executor(
                _supplement_executor,
                lambda: client.get_klines_full(symbol, timeframe, limit=5000),
            )
        else:
            client = PionexClient("", "")
            klines = await client.get_klines_full(symbol, timeframe, limit=500)
            await client.close()
    except Exception as e:
        logger.warning(f"Failed to fetch supplement data for {symbol}: {e}")
        return df

    if not klines:
        logger.info("No supplement data available")
        return df

    # Filter: only keep candles AFTER the CSV's last timestamp
    new_klines = [k for k in klines if k["timestamp"] > last_ts]
    if not new_klines:
        logger.info(f"CSV is already up to date (no new candles after {last_dt})")
        return df

    new_df = DataFetcher._prepare_df(pd.DataFrame(new_klines))
    combined = pd.concat([df, new_df])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()

    logger.info(
        f"Supplemented {len(new_klines)} new candles: "
        f"{df.index[0]} ~ {combined.index[-1]} (total {len(combined)})"
    )
    return combined


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
        df["timestamp"] = (df["time"] * 1000).astype("int64")
    else:
        df["datetime"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        df["timestamp"] = df["time"].astype("int64")

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
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("datetime")
        df = df.sort_index()
        # Ensure correct dtypes
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
