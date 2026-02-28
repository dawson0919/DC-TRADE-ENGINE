"""Strategy auto-discovery and registry."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Type

from tradeengine.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, Type[BaseStrategy]] = {}


def register_strategy(cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
    """Decorator to register a strategy class."""
    instance = cls()
    _REGISTRY[instance.name] = cls
    logger.debug(f"Registered strategy: {instance.name}")
    return cls


def get_strategy(name: str) -> BaseStrategy:
    """Get a strategy instance by name."""
    if name not in _REGISTRY:
        raise KeyError(f"Strategy '{name}' not found. Available: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]()


def list_strategies() -> list[dict]:
    """List all registered strategies."""
    result = []
    for cls in _REGISTRY.values():
        s = cls()
        result.append({
            "name": s.name,
            "display_name": s.display_name,
            "description": s.description,
            "parameters": [
                {
                    "name": p.name,
                    "display_name": p.display_name,
                    "type": p.type,
                    "default": p.default,
                    "min": p.min_val,
                    "max": p.max_val,
                    "step": p.step,
                    "options": p.options,
                }
                for p in s.parameters()
            ],
        })
    return result


def auto_discover():
    """Import all built-in strategies to trigger @register_strategy decorators."""
    builtin_dir = Path(__file__).parent / "builtin"
    for py_file in builtin_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module_name = f"tradeengine.strategies.builtin.{py_file.stem}"
        try:
            importlib.import_module(module_name)
        except Exception as e:
            logger.warning(f"Failed to load strategy module {module_name}: {e}")

    # Also load user strategies
    user_dir = Path(__file__).parent.parent.parent / "user_strategies"
    if user_dir.exists():
        import sys
        for py_file in user_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[py_file.stem] = mod
                try:
                    spec.loader.exec_module(mod)
                except Exception as e:
                    logger.warning(f"Failed to load user strategy {py_file.name}: {e}")
