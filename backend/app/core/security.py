"""
Authentication — password hashing (bcrypt), JWT issue/verify, and the
`get_current_business` FastAPI dependency that scopes every dashboard request to
the authenticated owner's business.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Business, User

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
if not JWT_SECRET:
    logger.warning("JWT_SECRET not set — using an insecure dev default. Set it in production.")
    JWT_SECRET = "dev-insecure-secret-change-me"

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "168"))  # 7 days

bearer_scheme = HTTPBearer(auto_error=False)


# ── Passwords ─────────────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    # bcrypt caps input at 72 bytes — truncate to stay within that limit.
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────
def create_access_token(user_id: int, business_id: Optional[int], email: str) -> str:
    """Issue a signed JWT carrying the user and their business."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "business_id": business_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode + validate a JWT. Raises 401 on any problem."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesi sudah berakhir. Silakan login lagi.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token tidak valid.")


# ── Dependencies ──────────────────────────────────────────────────────────────
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated User from the Bearer token."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Belum login.")
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token tidak valid.")
    user = (await session.execute(select(User).where(User.id == int(user_id)))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Pengguna tidak ditemukan.")
    return user


async def get_current_business(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Business:
    """Resolve the authenticated owner's Business — the tenant scope for all
    dashboard endpoints. 404 if the user hasn't created a business yet."""
    if user.business_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bisnis belum dibuat. Selesaikan onboarding dulu.")
    business = (await session.execute(select(Business).where(Business.id == user.business_id))).scalar_one_or_none()
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bisnis tidak ditemukan.")
    return business
