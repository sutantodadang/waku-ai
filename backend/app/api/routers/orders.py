from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.constants import DASHBOARD_TO_DB_STATUS, DB_TO_DASHBOARD_STATUS, STATUS_WA_MESSAGE
from app.core.database import get_db
from app.core.security import get_current_business
from app.models import Business, Customer, Order
from app.schemas import (
    OrderDashboardResponse,
    OrderStatusUpdate,
    SendPaymentResponse,
)
from app.services.order_service import recompute_customer_stats
from app.services.payment import send_payment_info
from app.services.whatsapp import send_message, within_service_window

logger = logging.getLogger("waku.backend")

router = APIRouter()


def _order_to_dashboard_dict(order: Order, customer_name: str) -> dict:
    return {
        "id": order.id,
        "order_seq": order.order_seq,
        "customer_name": customer_name,
        "status": DB_TO_DASHBOARD_STATUS.get(order.status, order.status),
        "total": order.total,
        "items": order.items or [],
        "created_at": order.created_at,
    }


@router.get("/api/orders", response_model=list[OrderDashboardResponse])
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


@router.patch("/api/orders/{order_id}", response_model=OrderDashboardResponse)
async def dashboard_update_order_status(
    order_id: str,
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
            logger.exception("Status notification failed for order %s", order.id)

    return _order_to_dashboard_dict(order, customer.name or customer.phone_number)


@router.post("/api/orders/{order_id}/send-payment", response_model=SendPaymentResponse)
async def send_order_payment(
    order_id: str,
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
