"""Fernet encryption for API keys at rest."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    """Derive Fernet key from ENCRYPTION_KEY env var."""
    raw_key = os.getenv("ENCRYPTION_KEY", "")
    if not raw_key:
        raise RuntimeError("ENCRYPTION_KEY environment variable not set")
    key_bytes = hashlib.sha256(raw_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string, return base64 ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a base64 ciphertext, return plaintext string."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
