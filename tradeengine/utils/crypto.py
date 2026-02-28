"""Cryptographic utilities for exchange API authentication."""

from __future__ import annotations

import hashlib
import hmac
import time


def pionex_signature(api_secret: str, method: str, path: str, params: dict | None = None) -> tuple[str, int]:
    """Generate HMAC-SHA256 signature for Pionex API.

    Returns (signature, timestamp_ms).
    """
    timestamp_ms = int(time.time() * 1000)
    query_parts = []
    if params:
        for k in sorted(params.keys()):
            query_parts.append(f"{k}={params[k]}")
    query_string = "&".join(query_parts)

    # Pionex signature format: METHOD + PATH + ? + sorted_query + timestamp
    string_to_sign = f"{method}{path}"
    if query_string:
        string_to_sign += f"?{query_string}"

    signature = hmac.new(
        api_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return signature, timestamp_ms
