from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Business, OTPVerification, User
from app.schemas import (
    OTPRequest,
    OTPRequestResponse,
    OTPVerify,
    TokenResponse,
    UserLogin,
    UserRegister,
)
from app.api.routers.webhook import _normalize_phone, PLATFORM_WHATSAPP_NUMBER

logger = logging.getLogger("waku.backend")

OTP_TTL_MINUTES = 10

router = APIRouter()


@router.post("/api/auth/register", response_model=TokenResponse)
async def auth_register(body: UserRegister, session: AsyncSession = Depends(get_db)):
    """Register an owner + create their business in one step. Returns a JWT."""
    # Reserve the synthetic passwordless namespace so it cannot be squatted.
    if body.email.lower().endswith("@waku.local"):
        raise HTTPException(status_code=422, detail="Domain email @waku.local tidak diizinkan.")
    existing = (await session.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email sudah terdaftar.")

    dup_phone = (await session.execute(
        select(Business).where(Business.phone_number == body.phone_number)
    )).scalar_one_or_none()
    if dup_phone:
        raise HTTPException(status_code=409, detail="Nomor WhatsApp sudah terdaftar.")

    business = Business(phone_number=body.phone_number, business_name=body.business_name, settings={})
    session.add(business)
    await session.flush()

    user = User(email=body.email, password_hash=hash_password(body.password), business_id=business.id)
    session.add(user)
    await session.flush()

    token = create_access_token(user.id, business.id, user.email)
    logger.info("Owner %s registered business #%d.", user.email, business.id)
    return TokenResponse(access_token=token, business_id=business.id, business_name=business.business_name)


@router.post("/api/auth/login", response_model=TokenResponse)
async def auth_login(body: UserLogin, session: AsyncSession = Depends(get_db)):
    """Email + password login. Returns a JWT."""
    user = (await session.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email atau password salah.")
    business_name = None
    if user.business_id:
        business = (await session.execute(select(Business).where(Business.id == user.business_id))).scalar_one_or_none()
        business_name = business.business_name if business else None
    token = create_access_token(user.id, user.business_id, user.email)
    return TokenResponse(access_token=token, business_id=user.business_id, business_name=business_name)


@router.post("/api/auth/otp/request", response_model=OTPRequestResponse)
async def auth_otp_request(body: OTPRequest, session: AsyncSession = Depends(get_db)):
    """Issue a reverse-OTP code. The owner sends this code from their WhatsApp to
    the Waku platform number; the webhook verifies it (free service message)."""
    code = f"WAKU-{secrets.randbelow(900000) + 100000}"
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)
    otp = OTPVerification(phone_number=body.phone_number, code=code, purpose=body.purpose, expires_at=expires_at)
    session.add(otp)
    await session.flush()
    target = PLATFORM_WHATSAPP_NUMBER or "(nomor platform belum di-set di server)"
    return OTPRequestResponse(
        code=code,
        expires_at=expires_at,
        platform_number=PLATFORM_WHATSAPP_NUMBER or None,
        instructions=(
            f"Kirim pesan berisi kode {code} dari WhatsApp Anda ke nomor Waku {target}, "
            f"lalu klik Verifikasi. Kode berlaku {OTP_TTL_MINUTES} menit."
        ),
    )


@router.post("/api/auth/otp/verify", response_model=TokenResponse)
async def auth_otp_verify(body: OTPVerify, session: AsyncSession = Depends(get_db)):
    """Confirm a reverse-OTP. The supplied code must (a) match a record that was
    received from the owner's WhatsApp (consumed by the webhook), (b) still be
    within its expiry, and (c) match the given phone. Single-use: the record is
    deleted on success so a verified code cannot be replayed for another JWT.

    Auto-signup: if no account exists for this verified phone, a passwordless
    account (synthetic email, placeholder business name) is provisioned — making
    reverse-OTP a full WhatsApp-native signup + login path."""
    norm = _normalize_phone(body.phone_number)
    now = datetime.utcnow()
    stmt = (
        select(OTPVerification)
        .where(
            OTPVerification.code == body.code,
            OTPVerification.consumed == True,  # noqa: E712  (received via WhatsApp)
            OTPVerification.expires_at >= now,
        )
        .order_by(OTPVerification.created_at.desc())
    )
    otps = (await session.execute(stmt)).scalars().all()
    matched = next((o for o in otps if _normalize_phone(o.phone_number) == norm), None)
    if matched is None:
        raise HTTPException(
            status_code=400,
            detail="Kode belum diterima atau sudah kedaluwarsa. Minta kode baru lalu kirim dari WhatsApp Anda.",
        )

    businesses = (await session.execute(select(Business))).scalars().all()
    business = next((b for b in businesses if _normalize_phone(b.phone_number) == norm), None)
    if business is None:
        # OTP auto-signup — provision a passwordless account for this verified phone.
        business = Business(
            phone_number=body.phone_number,
            business_name=f"Bisnis {body.phone_number}",  # placeholder; owner can rename
            settings={},
        )
        session.add(business)
        await session.flush()
        logger.info("OTP auto-signup: created business #%d for %s.", business.id, body.phone_number)

    # Resolve the owner via the authoritative business_id link — NEVER by the
    # (guessable) synthetic email, which would let a squatted row be reassigned.
    user = (await session.execute(select(User).where(User.business_id == business.id))).scalar_one_or_none()
    if user is None:
        # Passwordless WhatsApp account. Email carries a random suffix so it is
        # not guessable and cannot collide with a pre-registered squat.
        synthetic_email = f"wa-{norm}-{secrets.token_hex(8)}@waku.local"
        user = User(email=synthetic_email, password_hash=None, business_id=business.id)
        session.add(user)
        await session.flush()

    # Single-use: spend the OTP so it cannot be replayed.
    await session.delete(matched)
    await session.flush()

    token = create_access_token(user.id, business.id, user.email)
    return TokenResponse(access_token=token, business_id=business.id, business_name=business.business_name)
