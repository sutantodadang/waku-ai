"""Confirm → WA notify + payment; within-window only."""
import asyncio
import datetime

from app import main
from app.core import database
from app import models
from app.services import booking_service as bk
from sqlalchemy import select
from helpers import register, connect_wa, auth


def _seed(client, token, with_inbound=True):
    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            cust = models.Customer(phone_number="628702", business_id=biz.id, name="Budi")
            s.add(cust); await s.flush()
            if with_inbound:
                s.add(models.Message(business_id=biz.id, customer_id=cust.id,
                                     content="hi", direction="inbound"))
            b = await bk.create_booking(s, biz.id, cust.id,
                                        items=[{"name": "Facial", "price": 80000, "duration_minutes": 60}],
                                        scheduled_at=datetime.datetime(2026, 7, 1, 14, 0),
                                        staff_id=None, total=80000, deposit_amount=20000, notes="")
            await s.commit()
            return b.id
    return asyncio.get_event_loop().run_until_complete(_run())


def test_confirm_notifies_and_sends_deposit(client, monkeypatch):
    notes, pay = [], {}

    async def cap_send(to, body, **k):
        notes.append(body); return {"ok": True}

    async def cap_pay(session, business, customer, total):
        pay["total"] = total; return True

    monkeypatch.setattr(main, "send_message", cap_send)
    monkeypatch.setattr(main, "send_payment_info", cap_pay)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    bid = _seed(client, t["access_token"])
    client.patch(f"/api/bookings/{bid}", headers=auth(t["access_token"]), json={"status": "confirmed"})
    assert any("dikonfirmasi" in n for n in notes)
    assert pay.get("total") == 20000  # deposit, not full total
