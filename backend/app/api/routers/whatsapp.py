from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_business
from app.models import Business
from app.schemas import (
    ConnectWhatsApp,
    EmbeddedSignup,
    WhatsAppConnectionResponse,
)
from app.services.whatsapp import (
    exchange_code_for_token,
    subscribe_app_to_waba,
)

logger = logging.getLogger("waku.backend")

router = APIRouter()


@router.put("/api/whatsapp/connect", response_model=WhatsAppConnectionResponse)
async def whatsapp_connect(
    body: ConnectWhatsApp,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """Manually attach Meta WhatsApp credentials to the authenticated business.
    Embedded Signup fills these same fields automatically once approved."""
    clash = (await session.execute(
        select(Business).where(
            Business.phone_number_id == body.phone_number_id,
            Business.id != business.id,
        )
    )).scalar_one_or_none()
    if clash:
        raise HTTPException(status_code=409, detail="phone_number_id sudah dipakai bisnis lain.")

    business.phone_number_id = body.phone_number_id
    business.waba_id = body.waba_id
    business.access_token = body.access_token  # encrypted at rest via EncryptedString
    business.is_connected = True
    await session.flush()
    return WhatsAppConnectionResponse(
        is_connected=True,
        phone_number_id=business.phone_number_id,
        waba_id=business.waba_id,
    )


@router.post("/api/whatsapp/embedded-signup", response_model=WhatsAppConnectionResponse)
async def whatsapp_embedded_signup(
    body: EmbeddedSignup,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """Finish Meta Embedded Signup: exchange the auth code for a business token,
    store creds, and subscribe our app to the WABA so webhooks flow."""
    clash = (await session.execute(
        select(Business).where(
            Business.phone_number_id == body.phone_number_id,
            Business.id != business.id,
        )
    )).scalar_one_or_none()
    if clash:
        raise HTTPException(status_code=409, detail="phone_number_id sudah dipakai bisnis lain.")

    try:
        token = await exchange_code_for_token(body.code)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError as exc:
        logger.error("Embedded Signup token exchange failed: %s", exc)
        raise HTTPException(status_code=502, detail="Gagal menukar kode dengan Meta.")

    business.phone_number_id = body.phone_number_id
    business.waba_id = body.waba_id
    business.access_token = token
    business.is_connected = True
    await session.flush()

    await subscribe_app_to_waba(body.waba_id, token)

    return WhatsAppConnectionResponse(
        is_connected=True,
        phone_number_id=business.phone_number_id,
        waba_id=business.waba_id,
    )


@router.get("/api/whatsapp/status", response_model=WhatsAppConnectionResponse)
async def whatsapp_status(business: Business = Depends(get_current_business)):
    """Connection status for the authenticated business."""
    return WhatsAppConnectionResponse(
        is_connected=business.is_connected,
        phone_number_id=business.phone_number_id,
        waba_id=business.waba_id,
    )
