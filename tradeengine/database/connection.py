"""Supabase REST API connection for multi-user SaaS."""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

_client = None


async def init_db():
    """Initialize Supabase client."""
    global _client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")

    from supabase import create_client
    _client = create_client(url, key)
    # Quick connectivity test
    _client.table("users").select("clerk_id").limit(1).execute()
    logger.info("Supabase connected (REST API)")


def get_client():
    """Get the Supabase client."""
    if _client is None:
        raise RuntimeError("Supabase not initialized. Call init_db() first.")
    return _client


class _SessionWrapper:
    """Wrapper that adds a no-op close() for compatibility with existing try/finally code."""

    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        return getattr(self._client, name)

    async def close(self):
        pass  # REST API client is stateless


async def get_session():
    """Compatibility wrapper — returns a Supabase client with close() support."""
    return _SessionWrapper(get_client())


async def close_db():
    """Release Supabase client."""
    global _client
    _client = None
    logger.info("Supabase client released")
