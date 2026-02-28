"""Local data storage: SQLite for metadata, Parquet for OHLCV data."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class DataStore:
    """Manages local OHLCV data cache using Parquet files.

    File layout: {cache_dir}/parquet/{symbol}_{timeframe}.parquet
    """

    def __init__(self, cache_dir: str = "data"):
        self.cache_dir = Path(cache_dir)
        self.parquet_dir = self.cache_dir / "parquet"
        self.parquet_dir.mkdir(parents=True, exist_ok=True)

    def _parquet_path(self, symbol: str, timeframe: str) -> Path:
        safe_symbol = symbol.replace("/", "_")
        return self.parquet_dir / f"{safe_symbol}_{timeframe}.parquet"

    def save_ohlcv(self, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        """Save OHLCV DataFrame to Parquet, merging with existing data."""
        path = self._parquet_path(symbol, timeframe)

        if path.exists():
            existing = pd.read_parquet(path)
            df = pd.concat([existing, df]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        df.to_parquet(path, index=False, engine="pyarrow")
        logger.info(f"Saved {len(df)} candles to {path}")

    def load_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> pd.DataFrame | None:
        """Load OHLCV data from Parquet cache.

        Returns None if no cached data exists.
        """
        path = self._parquet_path(symbol, timeframe)
        if not path.exists():
            return None

        df = pd.read_parquet(path)
        if start_ts is not None:
            df = df[df["timestamp"] >= start_ts]
        if end_ts is not None:
            df = df[df["timestamp"] <= end_ts]

        return df.reset_index(drop=True) if len(df) > 0 else None

    def get_latest_timestamp(self, symbol: str, timeframe: str) -> int | None:
        """Get the most recent timestamp in cached data."""
        path = self._parquet_path(symbol, timeframe)
        if not path.exists():
            return None
        df = pd.read_parquet(path, columns=["timestamp"])
        return int(df["timestamp"].max()) if len(df) > 0 else None

    def get_candle_count(self, symbol: str, timeframe: str) -> int:
        """Count cached candles for a symbol/timeframe pair."""
        path = self._parquet_path(symbol, timeframe)
        if not path.exists():
            return 0
        df = pd.read_parquet(path, columns=["timestamp"])
        return len(df)

    def list_cached(self) -> list[dict]:
        """List all cached symbol/timeframe pairs with candle counts."""
        result = []
        for path in self.parquet_dir.glob("*.parquet"):
            name = path.stem  # e.g. BTC_USDT_1h
            parts = name.rsplit("_", 1)
            if len(parts) == 2:
                symbol, timeframe = parts
                df = pd.read_parquet(path, columns=["timestamp"])
                result.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "candles": len(df),
                    "file": str(path),
                })
        return result
