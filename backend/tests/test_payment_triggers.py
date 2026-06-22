"""Three entry points send payment via send_payment_info (mocked).

NOTE: _generate_ai_reply returns a 3-tuple (reply, ai_order, ai_ok).
All fake_reply stubs here return the corrected 3-tuple form.
"""
import main
from helpers import register, connect_wa, customer_message, auth


def _set_payment(client, token):
    client.patch("/api/business", headers=auth(token), json={
        "business_name": "Warung",
        "payment_methods": [{"type": "rekening", "label": "BCA", "value": "123"}],
    })


def test_auto_send_payment_after_order_closed(client, monkeypatch):
    """Auto trigger: payment sent immediately after AI closes an order."""
    calls = []

    async def fake_pay(session, business, customer, total):
        calls.append(total)
        return True
    monkeypatch.setattr(main, "send_payment_info", fake_pay)

    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return ("ok", {"items": [{"name": "Nasi Goreng", "qty": 1, "price": 14000}], "total": 14000, "status": "closed"}, True)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_A", access_token="TKN_A")
    _set_payment(client, t["access_token"])
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    customer_message(client, "PNID_A", "628111", "1 nasi goreng")

    assert calls, "send_payment_info should have been called after order closed"


def test_dashboard_send_payment_endpoint(client, monkeypatch):
    """Dashboard trigger: POST /api/orders/{id}/send-payment calls send_payment_info."""
    sent = {}

    async def fake_pay(session, business, customer, total):
        sent["total"] = total
        return True
    monkeypatch.setattr(main, "send_payment_info", fake_pay)

    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return ("ok", {"items": [{"name": "Nasi Goreng", "qty": 1, "price": 14000}], "total": 14000, "status": "closed"}, True)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    _set_payment(client, t["access_token"])
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    customer_message(client, "PNID_T", "628123", "itu aja")
    order_id = client.get("/api/orders", headers=auth(t["access_token"])).json()[0]["id"]

    r = client.post(f"/api/orders/{order_id}/send-payment", headers=auth(t["access_token"]))
    assert r.status_code == 200
    assert r.json()["sent"] is True
    assert sent["total"] == 14000


def test_payment_intent_triggers_send(client, monkeypatch):
    """On-demand trigger: keyword 'cara bayar' in message calls send_payment_info."""
    calls = []

    async def fake_pay(session, business, customer, total):
        calls.append(total)
        return True
    monkeypatch.setattr(main, "send_payment_info", fake_pay)

    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return ("info bayar ya kak", None, True)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    _set_payment(client, t["access_token"])
    customer_message(client, "PNID_T", "628999", "kak cara bayar gimana?")
    assert calls, "PAYMENT intent → send_payment_info called"
