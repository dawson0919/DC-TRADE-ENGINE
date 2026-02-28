"""Configuration loader with Pydantic validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

CONFIG_DIR = Path(__file__).parent.parent / "config"


class PionexConfig(BaseModel):
    api_key: str = ""
    api_secret: str = ""


class TradingConfig(BaseModel):
    initial_capital: float = 10000.0
    fees_pct: float = 0.05
    slippage_pct: float = 0.05
    max_position_pct: float = 95.0
    max_drawdown_pct: float = 20.0


class DataConfig(BaseModel):
    cache_dir: str = "data"
    default_timeframe: str = "1h"
    default_symbol: str = "BTC_USDT"


class DashboardConfig(BaseModel):
    port: int = 8000
    language: str = "zh-TW"


class ClerkConfig(BaseModel):
    publishable_key: str = ""
    secret_key: str = ""


class AppConfig(BaseModel):
    pionex: PionexConfig = Field(default_factory=PionexConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    clerk: ClerkConfig = Field(default_factory=ClerkConfig)
    strategies: dict[str, dict[str, Any]] = Field(default_factory=dict)


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from YAML file, override with env vars."""
    path = config_path or CONFIG_DIR / "default.yaml"

    raw: dict = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    config = AppConfig(**raw)

    # Override API keys from env
    config.pionex.api_key = os.getenv("PIONEX_API_KEY", config.pionex.api_key)
    config.pionex.api_secret = os.getenv("PIONEX_API_SECRET", config.pionex.api_secret)

    port_env = os.getenv("PORT") or os.getenv("DASHBOARD_PORT")
    if port_env:
        config.dashboard.port = int(port_env)

    # Clerk auth
    config.clerk.publishable_key = os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "")
    config.clerk.secret_key = os.getenv("CLERK_SECRET_KEY", "")

    return config
