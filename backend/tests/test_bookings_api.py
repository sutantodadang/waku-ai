"""Bookings list/patch scoped; cross-tenant 404; status edit."""
import asyncio
import datetime

from app.core import database
from app import models
from app.services import booking_service as bk
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
    return asyncio.run(_run())


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


def test_cross_tenant_staff_id_idor(client):
    """IDOR fix: tenant A cannot attach tenant B's staff to A's booking (expect 400)."""
    a = register(client)
    b = register(client, email="b2@x.com", phone="082333333333")

    # Tenant B creates a staff member.
    ha = auth(a["access_token"])
    hb = auth(b["access_token"])
    staff_b = client.post("/api/staff", headers=hb, json={"name": "Bob"}).json()
    staff_b_id = staff_b["id"]

    # Tenant A creates a booking.
    bid = _seed_booking(client, a["access_token"])

    # Tenant A tries to set tenant B's staff_id on their own booking → 400.
    r = client.patch(f"/api/bookings/{bid}", headers=ha, json={"staff_id": staff_b_id})
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"

    # Sanity: tenant A using their OWN valid staff works → 200.
    staff_a = client.post("/api/staff", headers=ha, json={"name": "Alice"}).json()
    r2 = client.patch(f"/api/bookings/{bid}", headers=ha, json={"staff_id": staff_a["id"]})
    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}: {r2.text}"
    assert r2.json()["staff_id"] == staff_a["id"]
