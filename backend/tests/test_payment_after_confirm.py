"""TDD: AI confirm reply must be sent BEFORE the auto-payment message.

Bug: `_maybe_send_payment` was called before `send_message(reply)`, so the
customer received QRIS first, then the order confirmation — jarring UX.

Fix: set `send_payment_after = True`, defer the `_maybe_send_payment` call
until AFTER `send_message(reply)` + `save_message(...)`.
"""
from app.api.routers import webhook
from helpers import register, connect_wa, customer_message, auth


def _set_payment(client, token):
    client.patch(
        "/api/business",
        headers=auth(token),
        json={
            "business_name": "Warung",
            "payment_methods": [{"type": "rekening", "label": "BCA", "value": "123"}],
        },
    )


def test_confirm_sent_before_payment(client, monkeypatch):
    """Order-of-calls: send_message(reply) must precede send_payment_info call."""
    call_log = []

    async def fake_pay(session, business, customer, total=None):
        call_log.append("payment")
        return True

    async def fake_send(phone, msg, **kw):
        call_log.append(f"send:{msg[:20]}")
        return {"ok": True}

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return (
            "Pesanan kamu sudah dikonfirmasi!",
            {"items": [{"name": "Nasi Goreng", "qty": 1, "price": 14000}], "total": 14000, "status": "closed"},
            None,
            True,
        )

    monkeypatch.setattr(webhook, "send_payment_info", fake_pay)
    monkeypatch.setattr(webhook, "send_message", fake_send)
    monkeypatch.setattr(webhook, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_OC", access_token="TKN_OC")
    _set_payment(client, t["access_token"])
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})

    customer_message(client, "PNID_OC", "628777", "1 nasi goreng")

    # Both must have been called
    assert any("send:" in e for e in call_log), "reply must be sent"
    assert "payment" in call_log, "payment must be sent (no regression)"

    # Find positions
    send_pos = next(i for i, e in enumerate(call_log) if e.startswith("send:"))
    pay_pos = call_log.index("payment")
    assert send_pos < pay_pos, (
        f"confirm reply must be sent BEFORE payment. call_log={call_log}"
    )


def test_payment_still_sent_on_close(client, monkeypatch):
    """Regression: payment is still sent when an order closes (no regression)."""
    calls = []

    async def fake_pay(session, business, customer, total=None):
        calls.append(total)
        return True

    async def fake_send(*a, **k):
        return {"ok": True}

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return (
            "ok",
            {"items": [{"name": "Nasi Goreng", "qty": 1, "price": 14000}], "total": 14000, "status": "closed"},
            None,
            True,
        )

    monkeypatch.setattr(webhook, "send_payment_info", fake_pay)
    monkeypatch.setattr(webhook, "send_message", fake_send)
    monkeypatch.setattr(webhook, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_OC2", access_token="TKN_OC2")
    _set_payment(client, t["access_token"])
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})

    customer_message(client, "PNID_OC2", "628888", "1 nasi goreng")

    assert calls, "send_payment_info must still be called after order closes"
