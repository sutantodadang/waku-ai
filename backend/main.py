"""
Waku Backend — FastAPI application for AI WhatsApp Assistant.
Indonesian MSMEs order management through WhatsApp.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import close_db, get_db, init_db
from models import Business, Customer, Order, Product
from schemas import (
    BusinessRegister,
    BusinessResponse,
    DailySummary,
    OrderResponse,
    WhatsAppWebhookPayload,
)
from services.whatsapp import (
    parse_whatsapp_message,
    send_message,
    verify_signature,
    verify_webhook as verify_webhook_token,
)
from services.order_service import (
    create_order,
    extract_order_from_message,
    get_daily_summary,
    get_or_create_customer,
    get_orders_for_business,
    save_message,
)

load_dotenv()

# ── Logging ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("waku.backend")

# ── AI service URL ──────────────────────────────────────────────────────────────
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")


# ── Lifespan ────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB. Shutdown: dispose engine."""
    await init_db()
    logger.info("Waku backend started.")
    yield
    await close_db()
    logger.info("Waku backend shut down.")


# ── App ─────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Waku Backend API",
    description="AI WhatsApp Assistant untuk UMKM Indonesia",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
#  WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/webhook")
async def webhook_get(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """
    GET /webhook — Meta webhook verification handshake.
    Returns the challenge string when verification succeeds.
    """
    result = verify_webhook_token(hub_mode, hub_token, hub_challenge)
    if result is None:
        logger.warning("Webhook verification failed.")
        raise HTTPException(status_code=403, detail="Verification failed — token mismatch.")
    logger.info("Webhook verified!")
    return int(result)


@app.post("/webhook")
async def webhook_post(
    request: Request,
):
    """
    POST /webhook — receive incoming WhatsApp messages from Meta Cloud API.
    1. Verifies HMAC signature (if APP_SECRET is set).
    2. Parses the message payload.
    3. Forwards to AI service for reply generation.
    4. Sends reply back via WhatsApp Cloud API.
    """
    # Read raw body for signature verification
    raw_body = await request.body()

    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature.")

    payload: dict = await request.json()
    logger.debug("Webhook payload received: %s", payload)

    # Parse messages from payload
    incoming_messages = parse_whatsapp_message(payload)
    if not incoming_messages:
        logger.info("No messages in webhook payload — returning 200 OK.")
        return {"status": "ok", "messages_processed": 0}

    # Process each incoming message
    for msg in incoming_messages:
        from_number: str = msg.get("from_number", "")
        text: str = msg.get("text", "")
        message_id: str = msg.get("message_id", "")

        if not from_number or not text:
            logger.debug("Skipping message missing from_number or text.")
            continue

        logger.info("Processing message from %s: %.80s", from_number, text)

        # We need a business context — use the first registered business or
        # resolve dynamically from the recipient phone number (phone_number_id).
        # For now, use the business that matches the recipient.
        # In a multi-business scenario, the webhook payload's `metadata.phone_number_id`
        # tells us which business this message is for.
        business_id: Optional[int] = await _resolve_business_from_payload(payload)

        if business_id is None:
            logger.warning("No matching business found for incoming message from %s — replying generic.", from_number)
            # Still try to be helpful
            async for session in get_db():
                customer = await get_or_create_customer(session, business_id=1, phone_number=from_number)
                await save_message(session, business_id=1, customer_id=customer.id, content=text, direction="inbound", wamid=message_id)
                reply = "Maaf, saya belum bisa melayani pesanan Anda karena akun bisnis belum terdaftar. Silakan hubungi admin."
                await send_message(from_number, reply)
                await save_message(session, business_id=1, customer_id=customer.id, content=reply, direction="outbound")
            continue

        async for session in get_db():
            try:
                # 1. Get or create customer
                customer = await get_or_create_customer(session, business_id, from_number)

                # 2. Save inbound message
                await save_message(session, business_id, customer.id, text, "inbound", wamid=message_id)

                # 3. Try to extract order from message
                order_items = extract_order_from_message(text)
                if order_items:
                    order = await create_order(session, business_id, customer.id, order_items)
                    logger.info("Order #%d auto-extracted from message.", order.id)

                # 4. Forward to AI service for reply
                reply = await _generate_ai_reply(business_id, customer.id, text, order_items if order_items else None)

                # 5. Send reply via WhatsApp
                await send_message(from_number, reply)

                # 6. Save outbound message
                await save_message(session, business_id, customer.id, reply, "outbound")

            except Exception as exc:
                logger.exception("Error processing message from %s: %s", from_number, exc)
                try:
                    await send_message(from_number, "Maaf, terjadi kesalahan. Silakan coba lagi nanti.")
                except Exception:
                    logger.error("Failed to send error reply to %s", from_number)

    return {"status": "ok", "messages_processed": len(incoming_messages)}


async def _resolve_business_from_payload(payload: dict) -> Optional[int]:
    """
    Determine which business this webhook payload targets.
    Meta sends `metadata.phone_number_id` — we look up the business by that ID.
    If not found, fall back to the first registered business.
    """
    phone_number_id = (
        payload.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
        .get("metadata", {})
        .get("phone_number_id")
    )

    if phone_number_id:
        async for session in get_db():
            stmt = select(Business).where(Business.phone_number == phone_number_id)
            result = await session.execute(stmt)
            business = result.scalar_one_or_none()
            if business:
                return business.id

    # Fallback: return first registered business
    async for session in get_db():
        stmt = select(Business).limit(1)
        result = await session.execute(stmt)
        business = result.scalar_one_or_none()
        if business:
            return business.id

    return None


async def _generate_ai_reply(
    business_id: int,
    customer_id: int,
    message_text: str,
    extracted_order: Optional[list[dict]] = None,
) -> str:
    """
    Forward the message to the AI service for a smart reply.
    If the AI service is unreachable, return a sensible fallback.
    """
    import httpx

    payload: dict[str, Any] = {
        "business_id": business_id,
        "customer_id": customer_id,
        "message": message_text,
    }
    if extracted_order:
        payload["extracted_order"] = extracted_order

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{AI_SERVICE_URL}/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("reply", "")
            if reply:
                return reply
    except httpx.RequestError as exc:
        logger.warning("AI service unreachable (%s) — using fallback reply.", exc)
    except Exception as exc:
        logger.exception("AI service error: %s", exc)

    # Fallback replies in Indonesian
    if extracted_order:
        items_desc = ", ".join(f"{it.get('quantity', 1)}x {it.get('name', '?')}" for it in extracted_order)
        return (
            f"Terima kasih atas pesanannya! 🎉\n\n"
            f"Saya sudah mencatat pesanan Anda:\n{items_desc}\n\n"
            f"Pesanan akan segera diproses. Apakah ada yang ingin ditambahkan?"
        )
    return (
        "Halo! 👋 Saya asisten Waku untuk UMKM.\n\n"
        "Saya bisa bantu mencatat pesanan Anda. Cukup ketik pesanan seperti:\n"
        "• \"beli 2 nasi goreng, 1 es teh\"\n"
        "• \"saya mau pesan 3 ayam geprek\"\n\n"
        "Ada yang bisa saya bantu?"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  BUSINESS API
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/business/register", response_model=BusinessResponse)
async def register_business(body: BusinessRegister, session: AsyncSession = Depends(get_db)):
    """
    Register a new business (UMKM) in the system.
    """
    # Check existing
    stmt = select(Business).where(Business.phone_number == body.phone_number)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Business with this phone number already registered.")

    business = Business(
        phone_number=body.phone_number,
        business_name=body.business_name,
        settings=body.settings or {},
    )
    session.add(business)
    await session.flush()
    logger.info("Business #%d '%s' registered.", business.id, business.business_name)
    return business


@app.get("/api/business/{business_id}/orders", response_model=list[OrderResponse])
async def list_orders(
    business_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """List orders for a business, newest first."""
    # Verify business exists
    stmt = select(Business).where(Business.id == business_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Business not found.")

    orders = await get_orders_for_business(session, business_id, limit=limit, offset=offset)
    return orders


@app.get("/api/business/{business_id}/summary", response_model=DailySummary)
async def business_summary(
    business_id: int,
    day: Optional[str] = Query(None, description="Date in YYYY-MM-DD format. Defaults to today."),
    session: AsyncSession = Depends(get_db),
):
    """Daily summary of conversations, orders, and revenue."""
    # Verify business
    stmt = select(Business).where(Business.id == business_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Business not found.")

    target_date = date.fromisoformat(day) if day else date.today()
    summary = await get_daily_summary(session, business_id, day=target_date)
    return summary


# ═══════════════════════════════════════════════════════════════════════════════
#  HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    """Simple health-check endpoint."""
    return {"status": "healthy", "service": "waku-backend"}
