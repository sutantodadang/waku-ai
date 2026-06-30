"""Manual reminder + send-payment are window-gated."""
import asyncio
import datetime

from app import main
from app.core import database
from app import models
from app.services import booking_service as bk
from sqlalchemy import select
from helpers import register, connect_wa, auth


def _seed(client, token, with_inbound):
    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            cust = models.Customer(phone_number="628703", business_id=biz.id, name="Budi")
            s.add(cust); await s.flush()
            if with_inbound:
                s.add(models.Message(business_id=biz.id, customer_id=cust.id, content="hi", direction="inbound"))
            b = await bk.create_booking(s, biz.id, cust.id, items=[{"name": "Facial", "price": 80000}],
                                        scheduled_at=datetime.datetime(2026, 7, 1, 14, 0),
                                        staff_id=None, total=80000, deposit_amount=None, notes="")
            await s.commit()
            return b.id
    return asyncio.get_event_loop().run_until_complete(_run())


def test_remind_sends_within_window(client, monkeypatch):
    async def cap_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", cap_send)
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    bid = _seed(client, t["access_token"], with_inbound=True)
    r = client.post(f"/api/bookings/{bid}/remind", headers=auth(t["access_token"]))
    assert r.status_code == 200 and r.json()["sent"] is True


def test_remind_skips_outside_window(client, monkeypatch):
    async def cap_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", cap_send)
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    bid = _seed(client, t["access_token"], with_inbound=False)  # no inbound → window closed
    r = client.post(f"/api/bookings/{bid}/remind", headers=auth(t["access_token"]))
    assert r.status_code == 200 and r.json()["sent"] is False


def test_remind_send_failure_returns_false(client, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(main, "send_message", boom)
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    bid = _seed(client, t["access_token"], with_inbound=True)  # window open
    r = client.post(f"/api/bookings/{bid}/remind", headers=auth(t["access_token"]))
    assert r.status_code == 200 and r.json()["sent"] is False


def test_send_payment_delegates(client, monkeypatch):
    captured = {}
    async def cap_pay(session, business, customer, amount):
        captured["amount"] = amount
        return True
    monkeypatch.setattr(main, "send_payment_info", cap_pay)
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    bid = _seed(client, t["access_token"], with_inbound=True)
    r = client.post(f"/api/bookings/{bid}/send-payment", headers=auth(t["access_token"]))
    assert r.status_code == 200 and r.json()["sent"] is True
    assert captured["amount"] == 80000  # no deposit → total


def test_send_payment_exception_returns_false(client, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("send blew up")
    monkeypatch.setattr(main, "send_payment_info", boom)
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    bid = _seed(client, t["access_token"], with_inbound=True)
    r = client.post(f"/api/bookings/{bid}/send-payment", headers=auth(t["access_token"]))
    assert r.status_code == 200 and r.json()["sent"] is False


def test_cross_tenant_booking_404(client):
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    bid = _seed(client, t["access_token"], with_inbound=True)
    other = register(client, email="b@x.com", phone="082222222222")  # second tenant
    for path in (f"/api/bookings/{bid}/remind", f"/api/bookings/{bid}/send-payment"):
        r = client.post(path, headers=auth(other["access_token"]))
        assert r.status_code == 404
