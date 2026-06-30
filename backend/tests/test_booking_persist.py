"""Salon close-booking is persisted requested; warung path unaffected."""
from app.api.routers import webhook
from helpers import register, connect_wa, customer_message, auth

def _ai(reply, *, order=None, booking=None, ok=True):
    return (reply, order, booking, ok)

def test_salon_booking_persisted(client, monkeypatch):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(webhook, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, customer=None):
        bk = {"items": [{"name": "Facial", "price": 80000, "duration_minutes": 60}],
              "scheduled_at": "2026-07-01T14:00:00", "staff_name": None,
              "deposit_amount": None, "notes": "", "total": 80000, "status": "closed"} if "itu aja" in text else None
        return _ai("ok kak", booking=bk)
    monkeypatch.setattr(webhook, "_generate_ai_reply", fake_reply)

    t = register(client)
    h = auth(t["access_token"])
    client.patch("/api/business", headers=h, json={"business_name": "Salon", "business_type": "salon"})
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    customer_message(client, "PNID_T", "628123", "booking facial")
    customer_message(client, "PNID_T", "628123", "itu aja")

    rows = client.get("/api/bookings", headers=h).json()
    assert len(rows) == 1 and rows[0]["status"] == "requested"
    assert rows[0]["total"] == 80000
