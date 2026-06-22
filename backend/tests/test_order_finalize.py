"""LLM close-order is persisted once; a later close amends it, not duplicates."""
import main
from helpers import register, connect_wa, customer_message, auth


def _ai_order(items, total):
    return {"items": items, "total": total, "status": "closed"}


def test_close_creates_single_order(client, monkeypatch):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        order = _ai_order([{"name": "Nasi Goreng", "qty": 2, "price": 14000}], 28000) if "itu aja" in text else None
        return ("ok kak", order)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    customer_message(client, "PNID_T", "628123", "pesan 2 nasi goreng")
    customer_message(client, "PNID_T", "628123", "itu aja")
    orders = client.get("/api/orders", headers=auth(t["access_token"])).json()
    assert len(orders) == 1
    assert orders[0]["total"] == 28000


def test_second_close_amends_existing(client, monkeypatch):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    seq = iter([
        _ai_order([{"name": "Nasi Goreng", "qty": 1, "price": 14000}], 14000),
        _ai_order([{"name": "Nasi Goreng", "qty": 3, "price": 14000}], 42000),
    ])

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return ("ok", next(seq)) if "itu aja" in text else ("ok", None)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    customer_message(client, "PNID_T", "628777", "itu aja")
    customer_message(client, "PNID_T", "628777", "eh tambah, itu aja")
    orders = client.get("/api/orders", headers=auth(t["access_token"])).json()
    assert len(orders) == 1          # amended, not duplicated
    assert orders[0]["total"] == 42000
