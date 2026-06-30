"""Booking creation, rough clash detection (hybrid), staff name resolution."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Staff

logger = logging.getLogger(__name__)


async def create_booking(session: AsyncSession, business_id: int, customer_id: int,
                         items: list[dict], scheduled_at: Optional[datetime],
                         staff_id: Optional[int], total: float,
                         deposit_amount: Optional[float], notes: str) -> Booking:
    duration = sum(int(it.get("duration_minutes") or 0) for it in (items or [])) or None
    booking = Booking(
        business_id=business_id, customer_id=customer_id, staff_id=staff_id,
        items=items, total=total, deposit_amount=deposit_amount,
        scheduled_at=scheduled_at, duration_minutes=duration,
        status="requested", notes=notes or None,
    )
    session.add(booking)
    await session.flush()
    logger.info("Booking #%d requested — business=%d customer=%d", booking.id, business_id, customer_id)
    return booking


def _overlaps(a_start: datetime, a_dur: int, b_start: datetime, b_dur: int) -> bool:
    a_end = a_start + timedelta(minutes=a_dur or 0)
    b_end = b_start + timedelta(minutes=b_dur or 0)
    return a_start < b_end and b_start < a_end


async def check_booking_clash(session: AsyncSession, business_id: int, staff_id: Optional[int],
                              scheduled_at: Optional[datetime], duration_minutes: Optional[int]) -> list[Booking]:
    """Confirmed bookings overlapping the requested window. For a specific staff,
    overlaps for that staff. For 'any staff' (staff_id None), returns the overlapping
    confirmed bookings only when they meet/exceed the active-staff count (capacity full)."""
    if scheduled_at is None:
        return []
    dur = duration_minutes or 0
    stmt = select(Booking).where(
        Booking.business_id == business_id, Booking.status == "confirmed",
        Booking.scheduled_at.isnot(None),
    )
    if staff_id is not None:
        stmt = stmt.where(Booking.staff_id == staff_id)
    candidates = list((await session.execute(stmt)).scalars().all())
    overlapping = [b for b in candidates if _overlaps(scheduled_at, dur, b.scheduled_at, b.duration_minutes or 0)]
    if staff_id is not None:
        return overlapping
    # any-staff: clash only when capacity (active staff) is full
    staff_count = (await session.execute(
        select(func.count(Staff.id)).where(Staff.business_id == business_id, Staff.active == True)  # noqa: E712
    )).scalar() or 0
    return overlapping if staff_count and len(overlapping) >= staff_count else []


async def resolve_staff(session: AsyncSession, business_id: int, staff_name: Optional[str]) -> Optional[int]:
    """Case-insensitive active-staff name match. None for missing / 'siapa aja' / null."""
    if not staff_name:
        return None
    row = (await session.execute(
        select(Staff).where(
            Staff.business_id == business_id, Staff.active == True,  # noqa: E712
            func.lower(Staff.name) == staff_name.strip().lower(),
        )
    )).scalar_one_or_none()
    return row.id if row else None
