"""CRUD operations using Supabase REST API."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Admin email — auto-promoted to admin on first login
ADMIN_EMAIL = "nbamoment@gmail.com"


class _UserProxy:
    """Lightweight proxy to match the ORM-style attribute access used by app.py."""
    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name: str):
        if name.startswith("_"):
            return super().__getattribute__(name)
        return self._data.get(name)


class _CredProxy:
    """Proxy for api_credentials row."""
    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name: str):
        if name.startswith("_"):
            return super().__getattribute__(name)
        return self._data.get(name)


# ── User CRUD ────────────────────────────────────────────────────────

async def get_or_create_user(
    client: Any, clerk_id: str, email: str, display_name: str = ""
) -> _UserProxy:
    """Get existing user or create on first login."""
    result = client.table("users").select("*").eq("clerk_id", clerk_id).execute()
    if result.data:
        row = result.data[0]
        # Backfill email/name if previously empty (Clerk API wasn't available)
        updates = {}
        if email and not row.get("email"):
            updates["email"] = email
        if display_name and not row.get("display_name"):
            updates["display_name"] = display_name
        if updates:
            client.table("users").update(updates).eq("clerk_id", clerk_id).execute()
            row.update(updates)
        return _UserProxy(row)

    is_admin = email.lower() == ADMIN_EMAIL.lower()

    # Migrate placeholder seed user → real Clerk ID
    if is_admin:
        seed = client.table("users").select("*").eq("clerk_id", "test123").execute()
        if seed.data:
            client.table("users").update({
                "clerk_id": clerk_id,
                "email": email,
                "display_name": display_name or seed.data[0].get("display_name", ""),
            }).eq("clerk_id", "test123").execute()
            # Also update api_credentials FK
            client.table("api_credentials").update({
                "user_id": clerk_id,
            }).eq("user_id", "test123").execute()
            logger.info(f"Migrated seed user test123 → {clerk_id}")
            migrated = client.table("users").select("*").eq("clerk_id", clerk_id).execute()
            if migrated.data:
                return _UserProxy(migrated.data[0])

    new_user = {
        "clerk_id": clerk_id,
        "email": email,
        "display_name": display_name,
        "role": "admin" if is_admin else "user",
        "is_active": True,
        "max_bots": 999 if is_admin else 1,
    }
    result = client.table("users").insert(new_user).execute()
    return _UserProxy(result.data[0])


async def get_user(client: Any, clerk_id: str) -> _UserProxy | None:
    result = client.table("users").select("*").eq("clerk_id", clerk_id).execute()
    return _UserProxy(result.data[0]) if result.data else None


async def list_all_users(client: Any) -> list[_UserProxy]:
    result = client.table("users").select("*").order("created_at", desc=True).execute()
    return [_UserProxy(row) for row in result.data]


async def toggle_user_active(client: Any, clerk_id: str) -> bool:
    user = await get_user(client, clerk_id)
    if not user:
        return False
    new_active = not user.is_active
    client.table("users").update({"is_active": new_active}).eq("clerk_id", clerk_id).execute()
    return True


async def update_user_max_bots(client: Any, clerk_id: str, max_bots: int) -> bool:
    user = await get_user(client, clerk_id)
    if not user:
        return False
    client.table("users").update({"max_bots": max_bots}).eq("clerk_id", clerk_id).execute()
    return True


# ── API Credential CRUD ─────────────────────────────────────────────

async def save_api_credential(
    client: Any, user_id: str, api_key_enc: str,
    api_secret_enc: str, exchange: str = "pionex", label: str = ""
) -> _CredProxy:
    """Upsert: one credential per user+exchange."""
    result = (
        client.table("api_credentials")
        .select("*")
        .eq("user_id", user_id)
        .eq("exchange", exchange)
        .execute()
    )
    if result.data:
        # Update existing
        updated = (
            client.table("api_credentials")
            .update({
                "api_key_encrypted": api_key_enc,
                "api_secret_encrypted": api_secret_enc,
                "label": label,
            })
            .eq("id", result.data[0]["id"])
            .execute()
        )
        return _CredProxy(updated.data[0])
    else:
        # Insert new
        inserted = (
            client.table("api_credentials")
            .insert({
                "user_id": user_id,
                "exchange": exchange,
                "api_key_encrypted": api_key_enc,
                "api_secret_encrypted": api_secret_enc,
                "label": label,
            })
            .execute()
        )
        return _CredProxy(inserted.data[0])


async def get_api_credential(
    client: Any, user_id: str, exchange: str = "pionex"
) -> _CredProxy | None:
    result = (
        client.table("api_credentials")
        .select("*")
        .eq("user_id", user_id)
        .eq("exchange", exchange)
        .execute()
    )
    return _CredProxy(result.data[0]) if result.data else None


async def delete_api_credential(
    client: Any, user_id: str, exchange: str = "pionex"
) -> bool:
    result = (
        client.table("api_credentials")
        .delete()
        .eq("user_id", user_id)
        .eq("exchange", exchange)
        .execute()
    )
    return len(result.data) > 0


# ── Backtest Results CRUD ──────────────────────────────────────────

async def save_backtest_result(client: Any, user_id: str, result_data: dict) -> dict | None:
    """Save a backtest result to DB."""
    row = {
        "user_id": user_id,
        "strategy": result_data.get("strategy_name", result_data.get("strategy", "")),
        "symbol": result_data.get("symbol", ""),
        "timeframe": result_data.get("timeframe", ""),
        "capital": result_data.get("capital", 10000),
        "params": result_data.get("params", {}),
        "metrics": result_data.get("metrics", {}),
        "equity_curve": result_data.get("equity_curve", []),
        "trades": result_data.get("trades", []),
        "total_candles": result_data.get("total_candles", 0),
        "period": result_data.get("period", ""),
    }
    result = client.table("backtest_results").insert(row).execute()
    return result.data[0] if result.data else None


async def list_backtest_results(client: Any, user_id: str, limit: int = 50) -> list[dict]:
    """List user's backtest history (newest first, without large fields)."""
    result = (
        client.table("backtest_results")
        .select("id,strategy,symbol,timeframe,capital,params,metrics,total_candles,period,created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


async def get_backtest_result(client: Any, result_id: int, user_id: str) -> dict | None:
    """Get a single backtest result (full data including equity_curve + trades)."""
    result = (
        client.table("backtest_results")
        .select("*")
        .eq("id", result_id)
        .eq("user_id", user_id)
        .execute()
    )
    return result.data[0] if result.data else None


async def delete_backtest_result(client: Any, result_id: int, user_id: str) -> bool:
    """Delete a backtest result."""
    result = (
        client.table("backtest_results")
        .delete()
        .eq("id", result_id)
        .eq("user_id", user_id)
        .execute()
    )
    return len(result.data) > 0 if result.data else False
