"""Booking creation, per-staff clash, any-staff capacity, staff resolve."""
import asyncio
import datetime

import services.booking_service as bk
import database, models
from sqlalchemy import select
from helpers import register, auth


def _biz_cust(client):
    t = register(client)
    h = auth(t["access_token"])
    client.post("/api/products", headers=h, json={"name": "Facial", "price": 80000, "duration_minutes": 60})
    cust_phone = "628700700700"
    return t, h


async def _seed_confirmed(session, business_id, customer_id, staff_id, when, dur, status="confirmed"):
    b = await bk.create_booking(session, business_id, customer_id,
                                items=[{"name": "Facial", "price": 80000, "duration_minutes": dur}],
                                scheduled_at=when, staff_id=staff_id, total=80000,
                                deposit_amount=None, notes="")
    b.status = status
    await session.flush()
    return b


def test_create_and_clash_same_staff(client):
    t, h = _biz_cust(client)

    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            cust = models.Customer(phone_number="628700", business_id=biz.id, name="A")
            staff = models.Staff(business_id=biz.id, name="Sari", active=True)
            s.add_all([cust, staff]); await s.flush()
            base = datetime.datetime(2026, 7, 1, 14, 0)
            await _seed_confirmed(s, biz.id, cust.id, staff.id, base, 60)
            # overlapping 14:30 for same staff → clash
            clash = await bk.check_booking_clash(s, biz.id, staff.id, base + datetime.timedelta(minutes=30), 60)
            # non-overlapping 16:00 → no clash
            free = await bk.check_booking_clash(s, biz.id, staff.id, base + datetime.timedelta(hours=2), 60)
            return len(clash), len(free)

    n_clash, n_free = asyncio.get_event_loop().run_until_complete(_run())
    assert n_clash == 1 and n_free == 0


def test_resolve_staff(client):
    t, h = _biz_cust(client)

    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            staff = models.Staff(business_id=biz.id, name="Sari", active=True)
            s.add(staff); await s.flush()
            hit = await bk.resolve_staff(s, biz.id, "sari")
            miss = await bk.resolve_staff(s, biz.id, "siapa aja")
            none = await bk.resolve_staff(s, biz.id, None)
            return hit, miss, none, staff.id

    hit, miss, none, sid = asyncio.get_event_loop().run_until_complete(_run())
    assert hit == sid and miss is None and none is None
