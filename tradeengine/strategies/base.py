"""Base strategy class - the core abstraction all strategies implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class StrategyParam:
    """Defines a single tunable parameter for a strategy."""

    name: str
    display_name: str  # Traditional Chinese supported
    type: str  # 'int', 'float', 'select'
    default: Any
    min_val: float | None = None
    max_val: float | None = None
    step: float | None = None
    options: list[str] = field(default_factory=list)


@dataclass
class SignalOutput:
    """Boolean signal Series for entry/exit.

    These feed directly into vectorBT's Portfolio.from_signals().
    """

    entries_long: pd.Series
    exits_long: pd.Series
    entries_short: pd.Series
    exits_short: pd.Series


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies.

    Subclasses must implement:
    - name: strategy identifier (snake_case)
    - display_name: human-readable name
    - description: what the strategy does
    - parameters(): list of tunable parameters
    - generate_signals(): produce entry/exit boolean Series from OHLCV data
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier (snake_case)."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Strategy description."""
        ...

    @abstractmethod
    def parameters(self) -> list[StrategyParam]:
        """Return the list of configurable parameters."""
        ...

    @abstractmethod
    def generate_signals(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> SignalOutput:
        """Generate entry/exit signals from OHLCV data.

        Args:
            ohlcv: DataFrame with columns [open, high, low, close, volume]
                   and a DatetimeIndex.
            params: dict of parameter name -> value.

        Returns:
            SignalOutput with boolean Series aligned to ohlcv index.
        """
        ...

    def validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate and fill defaults for parameters."""
        validated = {}
        for p in self.parameters():
            val = params.get(p.name, p.default)
            try:
                if p.type == "int":
                    val = int(val)
                elif p.type == "float":
                    val = float(val)
            except (ValueError, TypeError):
                val = p.default
            # Clamp to min/max bounds
            if isinstance(val, (int, float)):
                if p.min_val is not None and val < p.min_val:
                    val = p.min_val if p.type == "float" else int(p.min_val)
                if p.max_val is not None and val > p.max_val:
                    val = p.max_val if p.type == "float" else int(p.max_val)
            validated[p.name] = val
        return validated

    def _empty_signals(self, index: pd.Index) -> SignalOutput:
        """Return empty (all-False) signals for the given index."""
        false_series = pd.Series(False, index=index)
        return SignalOutput(
            entries_long=false_series.copy(),
            exits_long=false_series.copy(),
            entries_short=false_series.copy(),
            exits_short=false_series.copy(),
        )
