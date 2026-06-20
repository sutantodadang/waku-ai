"""
Token encryption at rest.

WhatsApp access tokens are sensitive long-lived credentials — we never store
them in plaintext. `EncryptedString` is a SQLAlchemy TypeDecorator that
transparently Fernet-encrypts on write and decrypts on read, so model code can
treat `Business.access_token` as a normal string.

Key comes from env `TOKEN_ENCRYPTION_KEY` (a urlsafe base64 Fernet key).
Generate one with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, TypeDecorator

logger = logging.getLogger(__name__)

_RAW_KEY = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()

if _RAW_KEY:
    try:
        _FERNET = Fernet(_RAW_KEY.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is malformed — it must be a 32-byte urlsafe base64 "
            "Fernet key. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        ) from exc
else:
    # Dev fallback: ephemeral key so the app boots without config. Tokens
    # encrypted with this key DO NOT survive a restart — set TOKEN_ENCRYPTION_KEY
    # in production.
    logger.warning(
        "TOKEN_ENCRYPTION_KEY not set — using an ephemeral key. "
        "Encrypted tokens will be unreadable after restart. Set it in production."
    )
    _FERNET = Fernet(Fernet.generate_key())


def encrypt(value: str) -> str:
    """Encrypt a plaintext string to a urlsafe token string."""
    return _FERNET.encrypt(value.encode()).decode()


def decrypt(token: str) -> Optional[str]:
    """Decrypt a token string. Returns None if it can't be decrypted."""
    try:
        return _FERNET.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        logger.error("Failed to decrypt token: %s", exc)
        return None


class EncryptedString(TypeDecorator):
    """SQLAlchemy column type that encrypts/decrypts transparently.

    Stores ciphertext in a String column; exposes plaintext to Python.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None or value == "":
            return value
        return encrypt(value)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None or value == "":
            return value
        return decrypt(value)
