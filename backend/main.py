"""
Waku Backend — FastAPI application for AI WhatsApp Assistant.
Indonesian MSMEs order management through WhatsApp.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import close_db, get_db, init_db
from models import Business, Customer, Message, Order, Product
from schemas import (
    BusinessRegister,
    BusinessResponse,
    DashboardSummary,
    DailySummary,
    OrderDashboardResponse,
    OrderResponse,
    OrderStatusUpdate,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    SettingsResponse,
    SettingsUpdate,
    UploadResponse,
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

DEFAULT_SETTINGS: dict = {
    "auto_reply_enabled": True,
    "greeting_message": "",
    "after_hours_message": "",
    "business_hours": {"open": "08:00", "close": "21:00"},
    "faq": [],
}


async def _get_default_business(session: AsyncSession) -> Business:
    """Resolve the default business for dashboard-facing endpoints.
    The dashboard has no business_id concept — it manages the first registered business."""
    stmt = select(Business).order_by(Business.id.asc()).limit(1)
    result = await session.execute(stmt)
    business = result.scalar_one_or_none()
    if business is None:
        raise HTTPException(
            status_code=404,
            detail="No business registered yet. Complete onboarding in the dashboard first.",
        )
    return business


def _order_to_dashboard_dict(order: Order, customer_name: str) -> dict:
    return {
        "id": order.id,
        "customer_name": customer_name,
        "status": DB_TO_DASHBOARD_STATUS.get(order.status, order.status),
        "total": order.total,
        "items": order.items or [],
        "created_at": order.created_at,
    }


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
#  DASHBOARD API — endpoints consumed by the Streamlit dashboard.
#  These operate on the default (first registered) business, since the
#  dashboard has no multi-tenant / business_id concept.
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(session: AsyncSession = Depends(get_db)):
    """GET /api/dashboard/summary — daily stats shaped for the dashboard home page."""
    business = await _get_default_business(session)
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
):
    """GET /api/orders — list orders for the default business, newest first."""
    business = await _get_default_business(session)

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
):
    """PATCH /api/orders/{id} — update order status. Accepts Indonesian status labels."""
    business = await _get_default_business(session)

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
    return _order_to_dashboard_dict(order, customer.name or customer.phone_number)


@app.get("/api/products", response_model=list[ProductResponse])
async def dashboard_list_products(session: AsyncSession = Depends(get_db)):
    """GET /api/products — list all products for the default business."""
    business = await _get_default_business(session)
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
):
    """POST /api/products — create a product for the default business."""
    business = await _get_default_business(session)
    product = Product(
        business_id=business.id,
        name=body.name,
        price=body.price,
        description=body.description,
        image_url=body.image_url,
    )
    session.add(product)
    await session.flush()
    logger.info("Product #%d '%s' created for business %d", product.id, product.name, business.id)
    return product


@app.put("/api/products/{product_id}", response_model=ProductResponse)
async def dashboard_update_product(
    product_id: int,
    body: ProductUpdate,
    session: AsyncSession = Depends(get_db),
):
    """PUT /api/products/{id} — update a product (partial update)."""
    business = await _get_default_business(session)
    stmt = select(Product).where(Product.id == product_id, Product.business_id == business.id)
    product = (await session.execute(stmt)).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found for this business.")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    await session.flush()
    return product


@app.delete("/api/products/{product_id}")
async def dashboard_delete_product(
    product_id: int,
    session: AsyncSession = Depends(get_db),
):
    """DELETE /api/products/{id} — delete a product."""
    business = await _get_default_business(session)
    stmt = select(Product).where(Product.id == product_id, Product.business_id == business.id)
    product = (await session.execute(stmt)).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found for this business.")

    await session.delete(product)
    await session.flush()
    return {"status": "ok", "deleted": product_id}


@app.get("/api/settings", response_model=SettingsResponse)
async def dashboard_get_settings(session: AsyncSession = Depends(get_db)):
    """GET /api/settings — return auto-reply settings for the default business.
    Missing keys are filled from DEFAULT_SETTINGS so the dashboard always gets a complete shape."""
    business = await _get_default_business(session)
    stored = business.settings or {}
    merged = {**DEFAULT_SETTINGS, **stored}
    return SettingsResponse(**merged)


@app.put("/api/settings", response_model=SettingsResponse)
async def dashboard_update_settings(
    body: SettingsUpdate,
    session: AsyncSession = Depends(get_db),
):
    """PUT /api/settings — merge partial settings into Business.settings JSON."""
    business = await _get_default_business(session)
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
