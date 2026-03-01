"""Clerk JWT verification for FastAPI."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any
from urllib.request import Request as UrlRequest, urlopen
import json as _json

import jwt
from jwt import PyJWKClient
from fastapi import Request, HTTPException, Depends

logger = logging.getLogger(__name__)

_jwks_client: PyJWKClient | None = None
_clerk_domain: str = ""


def _get_jwks_client() -> PyJWKClient:
    """Lazily initialize JWKS client from Clerk's publishable key."""
    global _jwks_client, _clerk_domain
    if _jwks_client is None:
        pk = os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "")
        if not pk:
            raise RuntimeError("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY not set")
        # Extract domain from pk_test_<base64> or pk_live_<base64>
        encoded = pk.replace("pk_test_", "").replace("pk_live_", "")
        # Add padding
        encoded += "=" * (4 - len(encoded) % 4)
        _clerk_domain = base64.b64decode(encoded).decode().rstrip("$")
        jwks_url = f"https://{_clerk_domain}/.well-known/jwks.json"
        logger.info(f"Clerk JWKS URL: {jwks_url}")
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


def _fetch_clerk_user(user_id: str) -> dict:
    """Fetch user profile from Clerk Backend API to get email etc."""
    secret = os.getenv("CLERK_SECRET_KEY", "")
    if not secret:
        return {}
    try:
        url = f"https://api.clerk.com/v1/users/{user_id}"
        req = UrlRequest(url, headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "User-Agent": "TradeEngine/1.0",
        })
        with urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read())
        email = ""
        addrs = data.get("email_addresses", [])
        if addrs:
            primary_id = data.get("primary_email_address_id", "")
            for addr in addrs:
                if addr.get("id") == primary_id:
                    email = addr.get("email_address", "")
                    break
            if not email:
                email = addrs[0].get("email_address", "")
        name = " ".join(filter(None, [data.get("first_name", ""), data.get("last_name", "")])).strip()
        return {"email": email, "name": name}
    except Exception as e:
        logger.warning(f"Failed to fetch Clerk user {user_id}: {e}")
        return {}


def verify_clerk_token(token: str) -> dict[str, Any]:
    """Verify a Clerk JWT and return its claims."""
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_exp": True, "verify_aud": False},
        )
        return claims
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def get_current_user(request: Request) -> dict[str, Any]:
    """FastAPI dependency — extracts and verifies Clerk JWT from Authorization header.

    Returns user dict with: user_id, email, display_name, role, max_bots, is_active.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = auth_header.split("Bearer ", 1)[1]
    claims = verify_clerk_token(token)

    from tradeengine.database.connection import get_session
    from tradeengine.database.crud import get_or_create_user

    session = await get_session()
    try:
        # Extract email from JWT claims first
        email = claims.get("email", "")
        name = claims.get("name", claims.get("first_name", ""))

        # Clerk session JWTs don't include email — fetch from Backend API
        if not email:
            clerk_user = _fetch_clerk_user(claims["sub"])
            email = clerk_user.get("email", "")
            name = name or clerk_user.get("name", "")

        user = await get_or_create_user(
            session,
            clerk_id=claims["sub"],
            email=email,
            display_name=name,
        )

        if not user.is_active:
            raise HTTPException(status_code=403, detail="帳號已停用")

        return {
            "user_id": user.clerk_id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "max_bots": user.max_bots,
            "is_active": user.is_active,
        }
    finally:
        await session.close()


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency — requires admin role."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return user
