from __future__ import annotations

import base64
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.constants import UPLOAD_DIR
from app.core.database import async_session_factory
from app.models import Business, Customer, OTPVerification, Product
from app.services.whatsapp import (
    PLATFORM_PHONE_NUMBER_ID,
    download_media,
    extract_phone_number_id,
    parse_statuses,
    parse_whatsapp_message,
    send_message,
    verify_signature,
    verify_webhook as verify_webhook_token,
    within_service_window,
)
from app.services.order_service import (
    create_order,
    extract_order_from_message,
    find_amendable_order,
    get_or_create_customer,
    is_regular,
    recompute_customer_stats,
    save_message,
    update_order_items,
)
from app.services.retrieval import select_relevant_products
from app.services.payment import send_payment_info
from app.services.booking_service import create_booking, resolve_staff

logger = logging.getLogger("waku.backend")

# ── AI service URL ──────────────────────────────────────────────────────────────
import os as _os
AI_SERVICE_URL = _os.getenv("AI_SERVICE_URL", "http://localhost:8001")
AI_SERVICE_SECRET = _os.getenv("AI_SERVICE_SECRET", "")

_AI_FALLBACK_ORDER_REGEX = True

PLATFORM_WHATSAPP_NUMBER = _os.getenv("PLATFORM_WHATSAPP_NUMBER", "")

AI_REPLY_FOOTER = "\n\n_🤖 Waku · balasan otomatis_"

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
#  WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/webhook")
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


@router.post("/webhook")
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


async def _reply_to_text(
    session: AsyncSession,
    business: Business,
    customer: Customer,
    text: str,
    message_id: str,
    *,
    save_inbound: bool = True,
) -> None:
    """Run the conversational reply pipeline for one inbound text (or image caption)."""
    if save_inbound:
        await save_message(session, business.id, customer.id, text, "inbound", wamid=message_id)

    reply, ai_order, ai_booking, ai_ok = await _generate_ai_reply(
        session, business, customer.phone_number, text, customer=customer
    )

    send_payment_after = False
    if business.business_type in ("salon", "wedding"):
        if ai_booking and ai_booking.get("status") == "closed":
            await _persist_ai_booking(session, business, customer, ai_booking)
    elif ai_order and ai_order.get("status") == "closed":
        await _persist_ai_order(session, business, customer, ai_order)
        # Defer payment until AFTER the confirm reply is sent (better UX).
        send_payment_after = True
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
        customer.phone_number, reply,
        phone_number_id=business.phone_number_id,
        access_token=business.access_token,
    )
    await save_message(session, business.id, customer.id, reply, "outbound")
    if send_payment_after:
        await _maybe_send_payment(session, business, customer)


async def _process_tenant_messages(session: AsyncSession, business: Business, messages: list[dict]) -> None:
    """Persist + AI-reply + send for each customer message of a business."""
    for msg in messages:
        from_number = msg.get("from_number", "")
        if not from_number:
            continue

        msg_type = msg.get("type", "text")
        message_id = msg.get("message_id", "")

        logger.info("Processing %s message from %s for business %d", msg_type, from_number, business.id)
        try:
            customer = await get_or_create_customer(session, business.id, from_number)

            if msg_type == "image" and msg.get("media_id"):
                await _handle_inbound_image(session, business, customer, msg)
                continue

            text = msg.get("text", "")
            if not text:
                continue

            await _reply_to_text(session, business, customer, text, message_id, save_inbound=True)
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


async def _handle_inbound_image(session: AsyncSession, business: Business, customer: Customer, msg: dict) -> None:
    """Download, persist, match, and reply for an inbound image message."""
    from_number = customer.phone_number
    message_id = msg.get("message_id", "")
    caption = msg.get("caption", "")

    result = await download_media(
        msg["media_id"],
        phone_number_id=business.phone_number_id,
        access_token=business.access_token,
    )

    if result is None:
        caption_stripped = caption.strip() if caption else ""
        if caption_stripped:
            await _reply_to_text(session, business, customer, caption_stripped, message_id, save_inbound=True)
            return
        await save_message(session, business.id, customer.id, "[gambar]", "inbound", wamid=message_id)
        reply = (
            "Waku terima gambarnya Kak 🙏 "
            "Tapi Waku belum bisa memproses gambar sekarang. "
            "Boleh sebutkan produk yang Kakak maksud?"
            + AI_REPLY_FOOTER
        )
        await send_message(from_number, reply, phone_number_id=business.phone_number_id, access_token=business.access_token)
        await save_message(session, business.id, customer.id, reply, "outbound")
        return

    content_bytes, mime = result

    # Derive extension from mime type
    ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp"}
    ext = ext_map.get(mime, ".jpg")
    safe_name = f"inbound_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
    dest = os.path.join(UPLOAD_DIR, safe_name)
    with open(dest, "wb") as f:
        f.write(content_bytes)
    media_url = f"/uploads/{safe_name}"

    await save_message(
        session, business.id, customer.id, caption or "[gambar]", "inbound",
        wamid=message_id, media_url=media_url,
    )

    # Load catalog for AI matching
    products = (await session.execute(
        select(Product).where(Product.business_id == business.id)
    )).scalars().all()
    catalog = []
    img_count = 0
    for p in products:
        item = {"name": p.name, "price": p.price, "image_url": p.image_url}
        if img_count < 8:
            loaded = _load_product_image_b64(p.image_url)
            if loaded:
                item["image_b64"], item["mime_type"] = loaded
                img_count += 1
        catalog.append(item)
    if img_count == 0:
        logger.info("No catalog product images available for visual match (business %d)", business.id)
    elif len([p for p in products if p.image_url]) > 8:
        logger.info("Catalog visual match capped at 8 images (business %d)", business.id)

    match = await _match_image_with_ai(business, content_bytes, mime, caption, catalog)
    matched_name = match.get("product_name") or ""
    caption_stripped = (caption or "").strip()
    if matched_name and caption_stripped:
        # Visual match AND the customer asked something — answer naturally, grounded.
        grounded = f"{caption_stripped}\n(Pelanggan mengirim foto produk yang dikenali: {matched_name})"
        await _reply_to_text(session, business, customer, grounded, message_id, save_inbound=False)
    else:
        # No visual match (not-available reply) OR matched-but-no-caption (confirm template).
        reply = f"{match.get('reply') or 'Waku terima gambarnya Kak 🙏'}{AI_REPLY_FOOTER}"
        await send_message(from_number, reply, phone_number_id=business.phone_number_id, access_token=business.access_token)
        await save_message(session, business.id, customer.id, reply, "outbound")


def _load_product_image_b64(image_url: Optional[str]) -> Optional[tuple[str, str]]:
    """Return (base64, mime_type) for a LOCAL product image, or None.

    Only resolves images stored under /uploads/ (uploaded via /api/upload).
    Remote URLs are NOT fetched — a tenant-controlled image_url would otherwise
    let the server fetch arbitrary internal/metadata endpoints (SSRF). Products
    that want visual matching must upload their photo. Externally-hosted
    image_url simply doesn't participate in visual matching.
    """
    if not image_url or not image_url.startswith("/uploads/"):
        return None
    _MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    try:
        path = os.path.join(UPLOAD_DIR, os.path.basename(image_url))
        if not os.path.exists(path):
            return None
        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode(), _MIME.get(ext, "image/jpeg")
    except Exception:
        logger.warning("Could not load product image %s", image_url)
    return None


async def _match_image_with_ai(
    business: Business,
    image_bytes: bytes,
    mime: str,
    caption: str,
    catalog: list[dict],
) -> dict:
    """POST to AI service /ai/match-image and return the response dict."""
    payload = {
        "image_b64": base64.b64encode(image_bytes).decode(),
        "mime_type": mime,
        "caption": caption or "",
        "catalog": catalog,
        "business_type": business.business_type,
    }
    headers = {"X-Waku-Secret": AI_SERVICE_SECRET} if AI_SERVICE_SECRET else {}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{AI_SERVICE_URL}/ai/match-image", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("AI match-image failed: %s", exc)
        return {
            "matched": False,
            "product_name": "",
            "price": 0.0,
            "reply": (
                "Waku terima gambarnya Kak 🙏 "
                "Tapi Waku belum yakin ini produk yang mana. "
                "Boleh sebutkan nama produknya ya?"
            ),
        }


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


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


async def _persist_ai_booking(session, business, customer, ai_booking: dict) -> None:
    items = ai_booking.get("items") or []
    if not items:
        return
    staff_id = await resolve_staff(session, business.id, ai_booking.get("staff_name"))
    await create_booking(
        session, business.id, customer.id,
        items=items,
        scheduled_at=_parse_iso(ai_booking.get("scheduled_at")),
        staff_id=staff_id,
        total=float(ai_booking.get("total") or sum(float(i.get("price") or 0) for i in items)),
        deposit_amount=ai_booking.get("deposit_amount"),
        notes=ai_booking.get("notes", ""),
    )


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
) -> tuple[str, Optional[dict], Optional[dict], bool]:
    """
    Forward the message to the AI service (/ai/reply), scoped to this business's
    catalog + context. Falls back to a sensible Indonesian reply when the AI
    service is unreachable.
    Returns (reply_text, ai_order, ai_booking, ai_ok) where:
      - ai_order is the order dict from the AI response (or None when the AI did not close an order)
      - ai_booking is the booking dict from the AI response (or None when no booking was closed)
      - ai_ok is True when the AI service responded successfully, False when unreachable/errored
    """
    catalog = await select_relevant_products(session, business.id, message_text, k=12)

    payload: dict[str, Any] = {
        "incoming_message": message_text,
        "session_id": session_id,
        "business_context": {"store_name": business.business_name, "owner_name": ""},
        "catalog": catalog,
        "business_type": business.business_type,
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
            ai_booking = data.get("booking")
            if reply:
                return reply, ai_order, ai_booking, True
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
        None,
        False,
    )


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
