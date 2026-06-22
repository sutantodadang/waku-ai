"""
Waku Backend — FastAPI application for AI WhatsApp Assistant.
Indonesian MSMEs order management through WhatsApp.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    create_access_token,
    get_current_business,
    hash_password,
    verify_password,
)
from database import async_session_factory, close_db, get_db, init_db
from models import Business, Customer, Message, OTPVerification, Order, Product, Staff, User
from schemas import (
    BusinessProfileUpdate,
    BusinessRegister,
    BusinessResponse,
    ConnectWhatsApp,
    CustomerDetailResponse,
    CustomerResponse,
    CustomerUpdate,
    DashboardSummary,
    DailySummary,
    EmbeddedSignup,
    OrderDashboardResponse,
    OrderResponse,
    OrderStatusUpdate,
    OTPRequest,
    OTPRequestResponse,
    OTPVerify,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    SettingsResponse,
    SettingsUpdate,
    TokenResponse,
    SendPaymentResponse,
    StaffCreate,
    StaffResponse,
    UploadResponse,
    UserLogin,
    UserRegister,
    WhatsAppConnectionResponse,
    WhatsAppWebhookPayload,
)
from services.whatsapp import (
    PLATFORM_PHONE_NUMBER_ID,
    exchange_code_for_token,
    extract_phone_number_id,
    parse_statuses,
    parse_whatsapp_message,
    send_message,
    subscribe_app_to_waba,
    verify_signature,
    verify_webhook as verify_webhook_token,
    within_service_window,
)
from services.order_service import (
    create_order,
    extract_order_from_message,
    find_amendable_order,
    get_daily_summary,
    get_or_create_customer,
    get_orders_for_business,
    is_regular,
    recompute_customer_stats,
    save_message,
    update_order_items,
)
from services.embeddings import embed_product
from services.retrieval import select_relevant_products
from services.payment import send_payment_info

load_dotenv()

# ── Logging ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("waku.backend")

# ── AI service URL ──────────────────────────────────────────────────────────────
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")
# Shared secret sent to the AI service (X-Waku-Secret). Must match AI_SERVICE_SECRET there.
AI_SERVICE_SECRET = os.getenv("AI_SERVICE_SECRET", "")

# When True, fall back to regex-based order extraction if the AI service is unreachable.
_AI_FALLBACK_ORDER_REGEX = True

# Human-readable display number of the platform WhatsApp (where owners send the
# reverse-OTP code). Shown in the dashboard. e.g. "+1 555-648-9439".
PLATFORM_WHATSAPP_NUMBER = os.getenv("PLATFORM_WHATSAPP_NUMBER", "")

# Appended to every customer-facing AI reply so customers know it's automated.
# WhatsApp italic (_..._) renders as a subtle footnote.
AI_REPLY_FOOTER = "\n\n_🤖 Waku · balasan otomatis_"


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

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

DASHBOARD_TO_DB_STATUS = {
    "baru": "pending",
    "diproses": "confirmed",
    "selesai": "completed",
    "dibatalkan": "cancelled",
}
DB_TO_DASHBOARD_STATUS = {v: k for k, v in DASHBOARD_TO_DB_STATUS.items()}

STATUS_WA_MESSAGE = {
    "confirmed": "Pesanan kakak lagi disiapkan ya 🙏",
    "completed": "Pesanan kakak sudah selesai! Terima kasih 😊",
    "cancelled": "Mohon maaf, pesanan kakak dibatalkan.",
}

DEFAULT_SETTINGS: dict = {
    "auto_reply_enabled": True,
    "greeting_message": "",
    "after_hours_message": "",
    "business_hours": {"open": "08:00", "close": "21:00"},
    "faq": [],
}


def _order_to_dashboard_dict(order: Order, customer_name: str) -> dict:
    return {
        "id": order.id,
        "customer_name": customer_name,
        "status": DB_TO_DASHBOARD_STATUS.get(order.status, order.status),
        "total": order.total,
        "items": order.items or [],
        "created_at": order.created_at,
    }


def _build_customer_card(cust: Customer) -> Optional[dict]:
    """Compact personalisation context for the AI. Returns None for an unknown
    customer (no real name, no orders, no notes/tags) so the AI never fabricates."""
    name = (cust.name or "").strip()
    known_name = bool(name) and name != cust.phone_number
    if (cust.order_count or 0) == 0 and not known_name and not cust.notes and not (cust.tags or []):
        return None

    card: dict = {"order_count": cust.order_count or 0, "is_regular": is_regular(cust)}
    if known_name:
        card["name"] = name
    if cust.top_items:
        card["usual_items"] = [t["name"] for t in cust.top_items]
    if cust.last_order_at:
        card["last_order_at"] = cust.last_order_at.isoformat()
        if cust.avg_cadence_days:
            due = cust.last_order_at + timedelta(days=cust.avg_cadence_days)
            card["reorder_due"] = datetime.utcnow() > due
            card["avg_cadence_days"] = round(cust.avg_cadence_days, 1)
    if cust.notes:
        card["notes"] = cust.notes
    if cust.tags:
        card["tags"] = cust.tags
    return card


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
async def webhook_post(request: Request):
    """
    POST /webhook — receive incoming WhatsApp messages from Meta Cloud API.
    Routing by metadata.phone_number_id:
      • our PLATFORM number → reverse-OTP / system channel (never calls the LLM)
      • a business's number → AI auto-reply scoped to that business
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature.")

    payload: dict = await request.json()
    incoming_messages = parse_whatsapp_message(payload)
    if not incoming_messages:
        # Likely a delivery-status callback — log it so send failures are visible.
        statuses = parse_statuses(payload)
        for s in statuses:
            if s.get("errors"):
                logger.warning("WhatsApp delivery %s → %s — ERROR %s", s["status"], s["recipient_id"], s["errors"])
            else:
                logger.info("WhatsApp delivery %s → %s", s["status"], s["recipient_id"])
        if not statuses:
            logger.info("No messages in webhook payload — returning 200 OK.")
        return {"status": "ok", "messages_processed": 0, "statuses": len(statuses)}

    phone_number_id = extract_phone_number_id(payload)

    async with async_session_factory() as session:
        business = await _resolve_business(session, phone_number_id)
        is_platform = bool(phone_number_id and PLATFORM_PHONE_NUMBER_ID and phone_number_id == PLATFORM_PHONE_NUMBER_ID)

        # ── Platform channel: reverse-OTP first; OTP messages never hit the LLM. ──
        if is_platform:
            otp_matched = 0
            leftover: list[dict] = []
            for msg in incoming_messages:
                if await _handle_platform_message(session, msg.get("from_number", ""), msg.get("text", "")):
                    otp_matched += 1
                else:
                    leftover.append(msg)
            # Non-OTP messages fall through to AI only if a business is connected to
            # this number (e.g. one test number doubling as platform + tenant).
            if business is not None and leftover:
                await _process_tenant_messages(session, business, leftover)
            await session.commit()
            return {
                "status": "ok", "channel": "platform",
                "otp_matched": otp_matched,
                "ai_handled": len(leftover) if business is not None else 0,
            }

        # ── Tenant channel: resolve by phone_number_id (no fallback). ──
        if business is None:
            logger.warning("No business registered for phone_number_id=%s — ignoring.", phone_number_id)
            return {"status": "ok", "messages_processed": 0, "reason": "unknown_business"}
        await _process_tenant_messages(session, business, incoming_messages)
        await session.commit()

    return {"status": "ok", "messages_processed": len(incoming_messages)}


async def _process_tenant_messages(session: AsyncSession, business: Business, messages: list[dict]) -> None:
    """Persist + AI-reply + send for each customer message of a business."""
    for msg in messages:
        from_number = msg.get("from_number", "")
        text = msg.get("text", "")
        message_id = msg.get("message_id", "")
        if not from_number or not text:
            continue

        logger.info("Processing message from %s for business %d: %.80s", from_number, business.id, text)
        try:
            customer = await get_or_create_customer(session, business.id, from_number)
            await save_message(session, business.id, customer.id, text, "inbound", wamid=message_id)

            reply, ai_order, ai_ok = await _generate_ai_reply(
                session, business, customer.phone_number, text, customer=customer
            )

            if ai_order and ai_order.get("status") == "closed":
                await _persist_ai_order(session, business, customer, ai_order)
                # Auto-send payment after the order is finalised (Task 10 wires this).
                await _maybe_send_payment(session, business, customer)
            elif (not ai_ok) and _AI_FALLBACK_ORDER_REGEX:
                # AI unreachable → degraded regex fallback so orders aren't lost.
                products = (await session.execute(
                    select(Product).where(Product.business_id == business.id)
                )).scalars().all()
                known = {p.name: p.price for p in products}
                regex_items = extract_order_from_message(text, known or None)
                if regex_items:
                    await create_order(session, business.id, customer.id, regex_items)
                    try:
                        await recompute_customer_stats(session, customer.id)
                    except Exception:
                        logger.exception("recompute failed")

            # On-demand payment: customer asked how to pay → send payment info.
            if any(kw in text.lower() for kw in (
                "cara bayar", "gimana bayar", "bayar gimana",
                "pembayaran", "no rekening", "nomor rekening",
            )):
                _order = await find_amendable_order(session, business.id, customer.id)
                _total = _order.total if _order else 0.0
                try:
                    await send_payment_info(session, business, customer, _total)
                except Exception:
                    logger.exception("On-demand payment send failed")

            reply = f"{reply}{AI_REPLY_FOOTER}"

            await send_message(
                from_number, reply,
                phone_number_id=business.phone_number_id,
                access_token=business.access_token,
            )
            await save_message(session, business.id, customer.id, reply, "outbound")
        except Exception as exc:
            logger.exception("Error processing message from %s: %s", from_number, exc)
            try:
                await send_message(
                    from_number, "Maaf, terjadi kesalahan. Silakan coba lagi nanti.",
                    phone_number_id=business.phone_number_id,
                    access_token=business.access_token,
                )
            except Exception:
                logger.error("Failed to send error reply to %s", from_number)


def _normalize_phone(phone: str) -> str:
    """Normalize to E.164-style digits (Indonesian 0-prefix → 62). Full-number
    comparison — no last-N truncation, to avoid cross-number collisions."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    return digits


def _normalize_ai_items(ai_items: list[dict]) -> list[dict]:
    """AI items use `qty`; backend orders use `quantity`."""
    out = []
    for it in ai_items or []:
        out.append({
            "name": it.get("name", ""),
            "quantity": int(it.get("qty") or it.get("quantity") or 1),
            "price": it.get("price"),
        })
    return [it for it in out if it["name"]]


async def _persist_ai_order(session, business, customer, ai_order: dict) -> None:
    """Update the customer's amendable order or create a new one from the AI order."""
    items = _normalize_ai_items(ai_order.get("items", []))
    if not items:
        return
    existing = await find_amendable_order(session, business.id, customer.id)
    if existing is not None:
        await update_order_items(session, existing, items)
    else:
        await create_order(session, business.id, customer.id, items)
    try:
        await recompute_customer_stats(session, customer.id)
    except Exception:
        logger.exception("Failed to recompute stats for customer %d", customer.id)


async def _maybe_send_payment(session, business, customer) -> None:
    """Auto-send payment for the customer's latest amendable order, best-effort."""
    order = await find_amendable_order(session, business.id, customer.id)
    if order is None:
        return
    try:
        await send_payment_info(session, business, customer, order.total)
    except Exception:
        logger.exception("Auto payment send failed for customer %d", customer.id)


async def _resolve_business(session: AsyncSession, phone_number_id: Optional[str]) -> Optional[Business]:
    """Look up the business that owns this Meta phone_number_id. No default fallback."""
    if not phone_number_id:
        return None
    stmt = select(Business).where(Business.phone_number_id == phone_number_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _handle_platform_message(session: AsyncSession, from_number: str, text: str) -> bool:
    """Match an inbound platform-channel message against a pending reverse-OTP code,
    consuming it on success. Returns True if an OTP was verified."""
    if not from_number or not text:
        return False
    now = datetime.utcnow()
    stmt = (
        select(OTPVerification)
        .where(OTPVerification.consumed == False, OTPVerification.expires_at >= now)  # noqa: E712
        .order_by(OTPVerification.created_at.desc())
    )
    otps = (await session.execute(stmt)).scalars().all()
    sender = _normalize_phone(from_number)
    for otp in otps:
        if otp.code in text and _normalize_phone(otp.phone_number) == sender:
            otp.consumed = True
            await session.flush()
            logger.info("Reverse-OTP verified for %s (purpose=%s).", from_number, otp.purpose)
            # Confirm back over WhatsApp so the user knows the code was accepted.
            # No creds passed → sends from the platform number (default creds).
            try:
                await send_message(
                    from_number,
                    "✅ Kode terverifikasi! Anda berhasil masuk ke Waku.\n"
                    "Silakan kembali ke dashboard untuk melanjutkan ya 🎉",
                )
            except Exception:
                logger.warning("Failed to send reverse-OTP confirmation to %s", from_number)
            return True
    return False


async def _generate_ai_reply(
    session: AsyncSession,
    business: Business,
    session_id: str,
    message_text: str,
    customer: Optional[Customer] = None,
) -> tuple[str, Optional[dict], bool]:
    """
    Forward the message to the AI service (/ai/reply), scoped to this business's
    catalog + context. Falls back to a sensible Indonesian reply when the AI
    service is unreachable.
    Returns (reply_text, ai_order, ai_ok) where:
      - ai_order is the order dict from the AI response (or None when the AI did not close an order)
      - ai_ok is True when the AI service responded successfully, False when unreachable/errored
    """
    catalog = await select_relevant_products(session, business.id, message_text, k=12)

    payload: dict[str, Any] = {
        "incoming_message": message_text,
        "session_id": session_id,
        "business_context": {"store_name": business.business_name, "owner_name": ""},
        "catalog": catalog,
    }

    if customer is not None:
        card = _build_customer_card(customer)
        if card is not None:
            payload["customer"] = card

    headers = {"X-Waku-Secret": AI_SERVICE_SECRET} if AI_SERVICE_SECRET else {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{AI_SERVICE_URL}/ai/reply", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("reply", "")
            ai_order = data.get("order")
            if reply:
                return reply, ai_order, True
    except httpx.RequestError as exc:
        logger.warning("AI service unreachable (%s) — using fallback reply.", exc)
    except Exception as exc:
        logger.exception("AI service error: %s", exc)

    # Fallback reply in Indonesian — AI service was unreachable
    return (
        "Halo! 👋 Saya asisten Waku untuk UMKM.\n\n"
        "Saya bisa bantu mencatat pesanan Anda. Cukup ketik pesanan seperti:\n"
        "• \"beli 2 nasi goreng, 1 es teh\"\n"
        "• \"saya mau pesan 3 ayam geprek\"\n\n"
        "Ada yang bisa saya bantu?",
        None,
        False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTH API — dashboard login for UMKM owners
# ═══════════════════════════════════════════════════════════════════════════════

OTP_TTL_MINUTES = 10


@app.post("/api/auth/register", response_model=TokenResponse)
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


@app.post("/api/auth/login", response_model=TokenResponse)
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


@app.post("/api/auth/otp/request", response_model=OTPRequestResponse)
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


@app.post("/api/auth/otp/verify", response_model=TokenResponse)
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


# ═══════════════════════════════════════════════════════════════════════════════
#  WHATSAPP CONNECTION API
# ═══════════════════════════════════════════════════════════════════════════════

@app.put("/api/whatsapp/connect", response_model=WhatsAppConnectionResponse)
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


@app.post("/api/whatsapp/embedded-signup", response_model=WhatsAppConnectionResponse)
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


@app.get("/api/whatsapp/status", response_model=WhatsAppConnectionResponse)
async def whatsapp_status(business: Business = Depends(get_current_business)):
    """Connection status for the authenticated business."""
    return WhatsAppConnectionResponse(
        is_connected=business.is_connected,
        phone_number_id=business.phone_number_id,
        waba_id=business.waba_id,
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


@app.get("/api/business", response_model=BusinessResponse)
async def get_business_profile(
    business: Business = Depends(get_current_business),
):
    """GET /api/business — the authenticated owner's business profile."""
    return business


@app.patch("/api/business", response_model=BusinessResponse)
async def update_business_profile(
    body: BusinessProfileUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """PATCH /api/business — rename the authenticated owner's business."""
    business.business_name = body.business_name
    if body.payment_methods is not None:
        business.payment_methods = [m.model_dump() for m in body.payment_methods]
    if body.qris_image_url is not None:
        business.qris_image_url = body.qris_image_url or None
    await session.flush()
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
#  STAFF API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/staff", response_model=list[StaffResponse])
async def list_staff(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    rows = (await session.execute(
        select(Staff).where(Staff.business_id == business.id, Staff.active == True)  # noqa: E712
    )).scalars().all()
    return list(rows)


@app.post("/api/staff", response_model=StaffResponse)
async def create_staff(
    body: StaffCreate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    staff = Staff(business_id=business.id, name=body.name, active=True)
    session.add(staff)
    await session.flush()
    return staff


@app.delete("/api/staff/{staff_id}")
async def delete_staff(
    staff_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    staff = (await session.execute(
        select(Staff).where(Staff.id == staff_id, Staff.business_id == business.id)
    )).scalar_one_or_none()
    if staff is None:
        raise HTTPException(status_code=404, detail="Staff not found for this business.")
    staff.active = False  # soft-delete keeps historical bookings' staff_id valid
    await session.flush()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
#  DASHBOARD API — endpoints consumed by the Streamlit dashboard.
#  Every endpoint is scoped to the authenticated owner's business (JWT).
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/dashboard/summary — daily stats shaped for the dashboard home page."""
    today = date.today()
    day_start = datetime.combine(today, datetime.min.time())
    day_end = datetime.combine(today, datetime.max.time())

    orders_today_stmt = (
        select(Order)
        .where(
            Order.business_id == business.id,
            Order.created_at >= day_start,
            Order.created_at <= day_end,
        )
        .order_by(Order.created_at.desc())
    )
    orders_today = list((await session.execute(orders_today_stmt)).scalars().all())

    revenue_today = sum(o.total for o in orders_today)

    messages_handled_stmt = (
        select(func.count(Message.id))
        .where(
            Message.business_id == business.id,
            Message.direction == "outbound",
            Message.timestamp >= day_start,
            Message.timestamp <= day_end,
        )
    )
    messages_handled = (await session.execute(messages_handled_stmt)).scalar() or 0

    pending_stmt = (
        select(func.count(Order.id))
        .where(
            Order.business_id == business.id,
            Order.status.in_(["pending", "confirmed"]),
        )
    )
    pending_orders = (await session.execute(pending_stmt)).scalar() or 0

    product_counts: dict[str, dict] = {}
    for o in orders_today:
        for item in (o.items or []):
            name = (item.get("name") or "").strip().lower()
            if not name:
                continue
            qty = int(item.get("quantity") or item.get("qty") or 1)
            entry = product_counts.setdefault(name, {"name": item.get("name", name), "count": 0})
            entry["count"] += qty
    top_products = sorted(product_counts.values(), key=lambda x: x["count"], reverse=True)[:5]

    return DashboardSummary(
        orders_today=len(orders_today),
        revenue_today=revenue_today,
        messages_handled=messages_handled,
        pending_orders=pending_orders,
        top_products=top_products,
    )


@app.get("/api/orders", response_model=list[OrderDashboardResponse])
async def dashboard_list_orders(
    status: Optional[str] = Query(None, description="Filter: baru|diproses|selesai|dibatalkan"),
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/orders — list orders for the authenticated business, newest first."""
    stmt = (
        select(Order, Customer)
        .join(Customer, Order.customer_id == Customer.id)
        .where(Order.business_id == business.id)
        .order_by(Order.created_at.desc())
    )
    if status and status in DASHBOARD_TO_DB_STATUS:
        stmt = stmt.where(Order.status == DASHBOARD_TO_DB_STATUS[status])

    rows = (await session.execute(stmt)).all()
    return [_order_to_dashboard_dict(order, customer.name or customer.phone_number) for order, customer in rows]


@app.patch("/api/orders/{order_id}", response_model=OrderDashboardResponse)
async def dashboard_update_order_status(
    order_id: int,
    body: OrderStatusUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """PATCH /api/orders/{id} — update order status. Accepts Indonesian status labels."""
    db_status = DASHBOARD_TO_DB_STATUS.get(body.status)
    if db_status is None:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{body.status}'. Expected one of: {', '.join(DASHBOARD_TO_DB_STATUS.keys())}",
        )

    stmt = (
        select(Order, Customer)
        .join(Customer, Order.customer_id == Customer.id)
        .where(Order.id == order_id, Order.business_id == business.id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found for this business.")
    order, customer = row

    order.status = db_status
    await session.flush()
    try:
        await recompute_customer_stats(session, order.customer_id)
    except Exception:
        logger.exception("Failed to recompute stats for customer %d", order.customer_id)

    msg = STATUS_WA_MESSAGE.get(db_status)
    if msg and await within_service_window(session, customer.id):
        try:
            await send_message(
                customer.phone_number, msg,
                phone_number_id=business.phone_number_id, access_token=business.access_token,
            )
        except Exception:
            logger.exception("Status notification failed for order %d", order.id)

    return _order_to_dashboard_dict(order, customer.name or customer.phone_number)


@app.post("/api/orders/{order_id}/send-payment", response_model=SendPaymentResponse)
async def send_order_payment(
    order_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """Owner re-sends payment info for an order to its customer."""
    row = (await session.execute(
        select(Order, Customer)
        .join(Customer, Order.customer_id == Customer.id)
        .where(Order.id == order_id, Order.business_id == business.id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found for this business.")
    order, customer = row
    sent = await send_payment_info(session, business, customer, order.total)
    return SendPaymentResponse(sent=sent)


# ═══════════════════════════════════════════════════════════════════════════════
#  CUSTOMERS API (Kenal Langganan)
# ═══════════════════════════════════════════════════════════════════════════════

def _customer_to_dict(c: Customer) -> dict:
    return {
        "id": c.id,
        "name": None if (c.name or "") == c.phone_number else c.name,
        "phone_number": c.phone_number,
        "is_regular": is_regular(c),
        "order_count": c.order_count or 0,
        "total_spent": c.total_spent or 0.0,
        "last_order_at": c.last_order_at,
        "top_items": c.top_items or [],
        "tags": c.tags or [],
    }


@app.get("/api/customers", response_model=list[CustomerResponse])
async def dashboard_list_customers(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/customers — customers for this business, most recent first."""
    stmt = (
        select(Customer)
        .where(Customer.business_id == business.id)
        .order_by(Customer.last_order_at.desc().nullslast(), Customer.id.desc())
    )
    customers = (await session.execute(stmt)).scalars().all()
    return [_customer_to_dict(c) for c in customers]


@app.get("/api/customers/{customer_id}", response_model=CustomerDetailResponse)
async def dashboard_get_customer(
    customer_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/customers/{id} — profile + recent orders."""
    cust = (await session.execute(
        select(Customer).where(Customer.id == customer_id, Customer.business_id == business.id)
    )).scalar_one_or_none()
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found for this business.")

    orders = (await session.execute(
        select(Order).where(Order.customer_id == cust.id).order_by(Order.created_at.desc()).limit(10)
    )).scalars().all()

    data = _customer_to_dict(cust)
    data.update({
        "notes": cust.notes,
        "is_regular_override": cust.is_regular_override,
        "avg_cadence_days": cust.avg_cadence_days,
        "recent_orders": [_order_to_dashboard_dict(o, cust.name or cust.phone_number) for o in orders],
    })
    return data


@app.patch("/api/customers/{customer_id}", response_model=CustomerDetailResponse)
async def dashboard_update_customer(
    customer_id: int,
    body: CustomerUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """PATCH /api/customers/{id} — update owner notes / tags / loyalty override."""
    cust = (await session.execute(
        select(Customer).where(Customer.id == customer_id, Customer.business_id == business.id)
    )).scalar_one_or_none()
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found for this business.")

    if body.tags is not None:
        if len(body.tags) > 10 or any(len(t) > 60 for t in body.tags):
            raise HTTPException(status_code=422, detail="Maks 10 tag, tiap tag ≤ 60 karakter.")
        cust.tags = body.tags
    if body.notes is not None:
        cust.notes = body.notes
    if body.is_regular_override is not None:
        cust.is_regular_override = body.is_regular_override
    await session.flush()

    orders = (await session.execute(
        select(Order).where(Order.customer_id == cust.id).order_by(Order.created_at.desc()).limit(10)
    )).scalars().all()
    data = _customer_to_dict(cust)
    data.update({
        "notes": cust.notes,
        "is_regular_override": cust.is_regular_override,
        "avg_cadence_days": cust.avg_cadence_days,
        "recent_orders": [_order_to_dashboard_dict(o, cust.name or cust.phone_number) for o in orders],
    })
    return data


@app.get("/api/products", response_model=list[ProductResponse])
async def dashboard_list_products(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/products — list all products for the authenticated business."""
    stmt = (
        select(Product)
        .where(Product.business_id == business.id)
        .order_by(Product.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@app.post("/api/products", response_model=ProductResponse, status_code=201)
async def dashboard_create_product(
    body: ProductCreate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """POST /api/products — create a product for the authenticated business."""
    product = Product(
        business_id=business.id,
        name=body.name,
        price=body.price,
        description=body.description,
        image_url=body.image_url,
    )
    session.add(product)
    await session.flush()
    await embed_product(session, product)
    logger.info("Product #%d '%s' created for business %d", product.id, product.name, business.id)
    return product


@app.put("/api/products/{product_id}", response_model=ProductResponse)
async def dashboard_update_product(
    product_id: int,
    body: ProductUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """PUT /api/products/{id} — update a product (partial update)."""
    stmt = select(Product).where(Product.id == product_id, Product.business_id == business.id)
    product = (await session.execute(stmt)).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found for this business.")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    await session.flush()
    await embed_product(session, product)
    return product


@app.delete("/api/products/{product_id}")
async def dashboard_delete_product(
    product_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """DELETE /api/products/{id} — delete a product."""
    stmt = select(Product).where(Product.id == product_id, Product.business_id == business.id)
    product = (await session.execute(stmt)).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found for this business.")

    await session.delete(product)
    await session.flush()
    return {"status": "ok", "deleted": product_id}


@app.get("/api/settings", response_model=SettingsResponse)
async def dashboard_get_settings(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/settings — return auto-reply settings for the authenticated business.
    Missing keys are filled from DEFAULT_SETTINGS so the dashboard always gets a complete shape."""
    stored = business.settings or {}
    merged = {**DEFAULT_SETTINGS, **stored}
    return SettingsResponse(**merged)


@app.put("/api/settings", response_model=SettingsResponse)
async def dashboard_update_settings(
    body: SettingsUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """PUT /api/settings — merge partial settings into Business.settings JSON."""
    current = dict(business.settings or {})

    update_data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "business_hours" in update_data and isinstance(update_data["business_hours"], dict):
        bh = update_data["business_hours"]
        current_bh = current.get("business_hours", {})
        current["business_hours"] = {**current_bh, **bh}
        update_data.pop("business_hours")
    if "faq" in update_data:
        current["faq"] = [f.model_dump() if hasattr(f, "model_dump") else f for f in body.faq]
        update_data.pop("faq")

    current.update(update_data)
    business.settings = current
    await session.flush()
    return SettingsResponse(**{**DEFAULT_SETTINGS, **current})


@app.post("/api/upload", response_model=UploadResponse)
async def dashboard_upload_image(file: UploadFile = File(...)):
    """POST /api/upload — save an image to uploads/ and return its public URL."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Only image files are accepted.")

    suffix = os.path.splitext(file.filename or "")[1] or ".jpg"
    safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{suffix}"
    dest = os.path.join(UPLOAD_DIR, safe_name)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    return UploadResponse(url=f"/uploads/{safe_name}")


# ═══════════════════════════════════════════════════════════════════════════════
#  HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    """Simple health-check endpoint."""
    return {"status": "healthy", "service": "waku-backend"}
