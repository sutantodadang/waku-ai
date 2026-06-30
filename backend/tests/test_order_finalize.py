"""LLM close-order is persisted once; a later close amends it, not duplicates."""
from app.api.routers import webhook
from helpers import register, connect_wa, customer_message, auth


def _ai_order(items, total):
    return {"items": items, "total": total, "status": "closed"}


def test_close_creates_single_order(client, monkeypatch):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(webhook, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, customer=None):
        order = _ai_order([{"name": "Nasi Goreng", "qty": 2, "price": 14000}], 28000) if "itu aja" in text else None
        return ("ok kak", order, None, True)
    monkeypatch.setattr(webhook, "_generate_ai_reply", fake_reply)

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
    monkeypatch.setattr(webhook, "send_message", fake_send)

    seq = iter([
        _ai_order([{"name": "Nasi Goreng", "qty": 1, "price": 14000}], 14000),
        _ai_order([{"name": "Nasi Goreng", "qty": 3, "price": 14000}], 42000),
    ])

    async def fake_reply(session, business, sid, text, customer=None):
        return ("ok", next(seq), None, True) if "itu aja" in text else ("ok", None, None, True)
    monkeypatch.setattr(webhook, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    customer_message(client, "PNID_T", "628777", "itu aja")
    customer_message(client, "PNID_T", "628777", "eh tambah, itu aja")
    orders = client.get("/api/orders", headers=auth(t["access_token"])).json()
    assert len(orders) == 1          # amended, not duplicated
    assert orders[0]["total"] == 42000


def test_regex_fallback_only_when_ai_unreachable(client, monkeypatch):
    """Spec: regex fallback fires ONLY when AI is unreachable (ai_ok=False).
    Mid-conversation turns where AI is reachable but hasn't closed an order
    must NOT create phantom orders even if the message names a catalog product.
    """
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(webhook, "send_message", fake_send)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})

    # --- Case 1: AI reachable, no closed order (mid-conversation) ---
    # Even though the message names a catalog product, NO order must be created.
    async def fake_reply_reachable(session, business, sid, text, customer=None):
        return ("ok", None, None, True)  # ai_ok=True, no closed order
    monkeypatch.setattr(webhook, "_generate_ai_reply", fake_reply_reachable)

    customer_message(client, "PNID_T", "628123", "beli 2 nasi goreng")
    orders = client.get("/api/orders", headers=auth(t["access_token"])).json()
    assert orders == [], "Reachable AI with no closed order must NOT create a phantom order"

    # --- Case 2: AI unreachable (ai_ok=False) + regex enabled → order IS created ---
    # Monkeypatch _generate_ai_reply to simulate the unreachable AI path (ai_ok=False).
    async def fake_reply_unreachable(session, business, sid, text, customer=None):
        return (
            "Halo! Saya asisten Waku untuk UMKM.",
            None,
            None,
            False,  # ai_ok=False — AI was unreachable
        )
    monkeypatch.setattr(webhook, "_generate_ai_reply", fake_reply_unreachable)

    customer_message(client, "PNID_T", "628456", "beli 2 nasi goreng")
    orders2 = client.get("/api/orders", headers=auth(t["access_token"])).json()
    assert len(orders2) == 1, "Unreachable AI must trigger regex fallback and create an order"
