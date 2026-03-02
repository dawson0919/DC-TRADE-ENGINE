"""Async DataFetcher wrapper for Yahoo Finance."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from tradeengine.data.fetcher import DataFetcher
from tradeengine.data.store import DataStore
from tradeengine.data.yahoo_client import YahooClient

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yfinance")


class YahooFetcher:
    """Async DataFetcher for Yahoo Finance futures data.

    Same .fetch() interface as DataFetcher but sources from yfinance.
    """

    def __init__(self, client: YahooClient, store: DataStore):
        self.client = client
        self.store = store

    async def fetch(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 5000,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Fetch OHLCV from Yahoo Finance with Parquet caching."""
        if use_cache:
            cached = self.store.load_ohlcv(symbol, timeframe)
            if cached is not None and len(cached) >= limit:
                logger.info(f"Using {len(cached)} cached candles for {symbol} {timeframe}")
                df = cached.tail(limit).reset_index(drop=True)
                return DataFetcher._prepare_df(df)

        logger.info(f"Fetching {symbol} {timeframe} from Yahoo Finance...")
        loop = asyncio.get_event_loop()
        klines = await loop.run_in_executor(
            _executor,
            lambda: self.client.get_klines_full(symbol, timeframe, limit=limit),
        )

        if not klines:
            cached = self.store.load_ohlcv(symbol, timeframe)
            if cached is not None and len(cached) > 0:
                return DataFetcher._prepare_df(cached)
            raise ValueError(f"No data available for {symbol} {timeframe} from Yahoo Finance")

        df = pd.DataFrame(klines)
        self.store.save_ohlcv(symbol, timeframe, df)
        return DataFetcher._prepare_df(df.tail(limit).reset_index(drop=True))

    async def get_latest_price_async(self, symbol: str) -> float:
        """Async wrapper around YahooClient.get_latest_price()."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self.client.get_latest_price(symbol),
        )
