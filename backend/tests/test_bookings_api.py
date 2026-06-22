"""Bookings list/patch scoped; cross-tenant 404; status edit."""
import asyncio
import datetime

import database, models
import services.booking_service as bk
from sqlalchemy import select
from helpers import register, auth


def _seed_booking(client, token, when=None):
    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            cust = models.Customer(phone_number="628701", business_id=biz.id, name="Budi")
            s.add(cust); await s.flush()
            b = await bk.create_booking(s, biz.id, cust.id,
                                        items=[{"name": "Facial", "price": 80000, "duration_minutes": 60}],
                                        scheduled_at=when or datetime.datetime(2026, 7, 1, 14, 0),
                                        staff_id=None, total=80000, deposit_amount=None, notes="")
            await s.commit()
            return b.id
    return asyncio.get_event_loop().run_until_complete(_run())


def test_list_and_patch_status(client):
    t = register(client)
    h = auth(t["access_token"])
    bid = _seed_booking(client, t["access_token"])
    rows = client.get("/api/bookings", headers=h).json()
    assert any(r["id"] == bid and r["status"] == "requested" for r in rows)

    r = client.patch(f"/api/bookings/{bid}", headers=h, json={"status": "confirmed"})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"


def test_cross_tenant_patch_404(client):
    a = register(client)
    b = register(client, email="b@x.com", phone="082222222222")
    bid = _seed_booking(client, a["access_token"])
    r = client.patch(f"/api/bookings/{bid}", headers=auth(b["access_token"]), json={"status": "confirmed"})
    assert r.status_code == 404


def test_invalid_status_422(client):
    t = register(client)
    bid = _seed_booking(client, t["access_token"])
    r = client.patch(f"/api/bookings/{bid}", headers=auth(t["access_token"]), json={"status": "ngawur"})
    assert r.status_code == 422
