from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.constants import BOOKING_STATUS_WA_MESSAGE
from app.core.database import get_db
from app.core.security import get_current_business
from app.models import Booking, Business, Customer, Staff
from app.schemas import BookingResponse, BookingUpdate, SendPaymentResponse
from app.services.booking_service import check_booking_clash
from app.services.payment import send_payment_info
from app.services.whatsapp import send_message, within_service_window

logger = logging.getLogger("waku.backend")

router = APIRouter()


def _fmt_when(dt) -> str:
    return dt.strftime("%d/%m %H:%M") if dt else "(waktu menyusul)"


async def _maybe_notify_booking_status(session, business, booking, customer, new_status) -> None:
    """Notify customer of booking status change (24h-gated); on confirmed, also send payment."""
    if not new_status:
        return
    template = BOOKING_STATUS_WA_MESSAGE.get(new_status)
    if template and await within_service_window(session, customer.id):
        msg = template.format(when=_fmt_when(booking.scheduled_at), store=business.business_name)
        try:
            await send_message(
                customer.phone_number, msg,
                phone_number_id=business.phone_number_id,
                access_token=business.access_token,
            )
        except Exception:
            logger.exception("Booking status notify failed for booking %d", booking.id)
    if new_status == "confirmed":
        amount = booking.deposit_amount if booking.deposit_amount else booking.total
        try:
            await send_payment_info(session, business, customer, amount)
        except Exception:
            logger.exception("Booking payment send failed for booking %d", booking.id)


async def _booking_to_dict(session: AsyncSession, b: Booking, customer_name: str) -> dict:
    clash = bool(await check_booking_clash(session, b.business_id, b.staff_id, b.scheduled_at, b.duration_minutes)) \
        if b.status in ("requested", "confirmed") else False
    return {
        "id": b.id, "customer_name": customer_name, "staff_id": b.staff_id,
        "items": b.items or [], "total": b.total, "deposit_amount": b.deposit_amount,
        "scheduled_at": b.scheduled_at, "duration_minutes": b.duration_minutes,
        "status": b.status, "notes": b.notes, "clash": clash, "created_at": b.created_at,
    }


async def _load_booking(session, business, booking_id):
    row = (await session.execute(
        select(Booking, Customer).join(Customer, Booking.customer_id == Customer.id)
        .where(Booking.id == booking_id, Booking.business_id == business.id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Booking not found for this business.")
    return row


@router.get("/api/bookings", response_model=list[BookingResponse])
async def list_bookings(
    status: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    stmt = (
        select(Booking, Customer)
        .join(Customer, Booking.customer_id == Customer.id)
        .where(Booking.business_id == business.id)
        .order_by(Booking.scheduled_at.asc().nullslast(), Booking.created_at.desc())
    )
    if status:
        stmt = stmt.where(Booking.status == status)
    if date:  # YYYY-MM-DD
        import datetime as _dt
        day = _dt.date.fromisoformat(date)
        start = _dt.datetime.combine(day, _dt.time.min)
        end = _dt.datetime.combine(day, _dt.time.max)
        stmt = stmt.where(Booking.scheduled_at >= start, Booking.scheduled_at <= end)
    rows = (await session.execute(stmt)).all()
    return [await _booking_to_dict(session, b, c.name or c.phone_number) for b, c in rows]


@router.patch("/api/bookings/{booking_id}", response_model=BookingResponse)
async def update_booking(
    booking_id: int,
    body: BookingUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    row = (await session.execute(
        select(Booking, Customer).join(Customer, Booking.customer_id == Customer.id)
        .where(Booking.id == booking_id, Booking.business_id == business.id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Booking not found for this business.")
    booking, customer = row
    if body.scheduled_at is not None:
        booking.scheduled_at = body.scheduled_at
    if body.staff_id is not None:
        staff = (await session.execute(
            select(Staff).where(Staff.id == body.staff_id, Staff.business_id == business.id)
        )).scalar_one_or_none()
        if staff is None:
            raise HTTPException(status_code=400, detail="Invalid staff_id for this business.")
        booking.staff_id = body.staff_id
    if body.status is not None:
        booking.status = body.status
    await session.flush()
    # Task 6 wires the status→WA notify + payment here.
    await _maybe_notify_booking_status(session, business, booking, customer, body.status)
    return await _booking_to_dict(session, booking, customer.name or customer.phone_number)


@router.post("/api/bookings/{booking_id}/remind", response_model=SendPaymentResponse)
async def remind_booking(
    booking_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    booking, customer = await _load_booking(session, business, booking_id)
    if not await within_service_window(session, customer.id):
        return SendPaymentResponse(sent=False)
    msg = f"Halo Kak, pengingat booking {_fmt_when(booking.scheduled_at)} ya 🙏"
    try:
        await send_message(customer.phone_number, msg,
                           phone_number_id=business.phone_number_id, access_token=business.access_token)
        return SendPaymentResponse(sent=True)
    except Exception:
        logger.exception("Reminder send failed for booking %d", booking.id)
        return SendPaymentResponse(sent=False)


@router.post("/api/bookings/{booking_id}/send-payment", response_model=SendPaymentResponse)
async def send_booking_payment(
    booking_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    booking, customer = await _load_booking(session, business, booking_id)
    amount = booking.deposit_amount if booking.deposit_amount else booking.total
    try:
        sent = await send_payment_info(session, business, customer, amount)
    except Exception:
        logger.exception("Payment send failed for booking %d", booking.id)
        sent = False
    return SendPaymentResponse(sent=sent)
