"""Webhook routing: per-business send creds, unknown-tenant drop, order extraction."""
from app import main
from app.services.whatsapp import parse_statuses
from helpers import register, connect_wa, customer_message, request_otp, deliver_otp_via_wa, auth


def test_platform_number_doubling_as_tenant_routes_nonotp_to_ai(client, monkeypatch):
    """A single test number set as PLATFORM but also connected to a business:
    non-OTP customer messages must still get an AI reply."""
    sent = []

    async def fake_send(to, body, *, phone_number_id=None, access_token=None):
        sent.append(to)
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "AI_SERVICE_URL", "http://127.0.0.1:9")

    t = register(client, phone="081111111111")
    connect_wa(client, t["access_token"], phone_number_id="PLATFORM_TEST", access_token="TKN_P")

    wh = customer_message(client, "PLATFORM_TEST", "628777", "halo kak")
    body = wh.json()
    assert body["channel"] == "platform"
    assert body["ai_handled"] == 1
    assert sent == ["628777"]


def test_platform_number_otp_not_sent_to_ai(client, monkeypatch):
    """An OTP message on the platform number is consumed, never routed to AI."""
    sent = []

    async def fake_send(to, body, *, phone_number_id=None, access_token=None):
        sent.append(to)
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)

    t = register(client, phone="081111111111")
    connect_wa(client, t["access_token"], phone_number_id="PLATFORM_TEST", access_token="TKN_P")
    code = request_otp(client, "081111111111")
    wh = deliver_otp_via_wa(client, "6281111111111", code)
    body = wh.json()
    assert body["otp_matched"] == 1
    assert body["ai_handled"] == 0
    assert sent == ["6281111111111"]  # only the confirmation reply, never the LLM


def test_delivery_status_callback_logged_not_a_message(client):
    payload = {"entry": [{"changes": [{"value": {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": "X"},
        "statuses": [{"status": "failed", "recipient_id": "628",
                      "errors": [{"code": 131030, "title": "Recipient not in allowed list"}]}],
    }}]}]}
    r = client.post("/webhook", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["statuses"] == 1 and body["messages_processed"] == 0


def test_parse_statuses_extracts_error_code():
    payload = {"entry": [{"changes": [{"value": {"statuses": [
        {"status": "failed", "recipient_id": "628",
         "errors": [{"code": 131030, "title": "Bad", "error_data": {"details": "not allowed"}}]},
    ]}}]}]}
    out = parse_statuses(payload)
    assert len(out) == 1
    assert out[0]["status"] == "failed"
    assert out[0]["errors"][0]["code"] == 131030
    assert out[0]["errors"][0]["detail"] == "not allowed"


def test_unknown_business_ignored(client):
    wh = customer_message(client, "NOT_A_REAL_PNID", "628999", "halo")
    assert wh.status_code == 200
    assert wh.json().get("reason") == "unknown_business"


def test_tenant_message_uses_per_business_credentials(client, monkeypatch):
    sent = []

    async def fake_send(to, body, *, phone_number_id=None, access_token=None):
        sent.append((to, body, phone_number_id, access_token))
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "AI_SERVICE_URL", "http://127.0.0.1:9")  # force fast AI fallback

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    wh = customer_message(client, "PNID_T", "628123", "halo kak")
    assert wh.json()["messages_processed"] == 1
    assert len(sent) == 1
    to, body, pnid, token = sent[0]
    assert to == "628123"
    assert pnid == "PNID_T"
    assert token == "TKN_T"   # decrypted per-business token handed to send_message
    assert body                # fallback reply is non-empty


def test_order_auto_extracted_from_message(client, monkeypatch):
    """AI closes an order → exactly one order is persisted."""
    async def fake_send(*a, **k):
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, customer=None):
        order = {"items": [{"name": "nasi goreng", "qty": 2, "price": None}, {"name": "es teh", "qty": 1, "price": None}], "total": 0, "status": "closed"}
        return ("ok", order, None, True)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    customer_message(client, "PNID_T", "628123", "beli 2 nasi goreng dan 1 es teh")

    orders = client.get("/api/orders", headers=auth(t["access_token"])).json()
    assert len(orders) == 1


def test_offcatalog_item_creates_no_order(client, monkeypatch):
    """AI returns no closed order for off-catalog items; closed order creates exactly one."""
    async def fake_send(*a, **k):
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)

    replies = iter([
        ("ok", None, None, True),  # off-catalog message → AI does not close an order
        ("ok", {"items": [{"name": "Nasi Goreng", "qty": 2, "price": 14000}], "total": 28000, "status": "closed"}, None, True),
    ])

    async def fake_reply(session, business, sid, text, customer=None):
        return next(replies)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)
    # Disable regex fallback so off-catalog text cannot sneak through.
    monkeypatch.setattr(main, "_AI_FALLBACK_ORDER_REGEX", False)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})

    # Off-catalog request → no order created.
    customer_message(client, "PNID_T", "628123", "aku mau pesan 1 motor")
    assert client.get("/api/orders", headers=auth(t["access_token"])).json() == []

    # Real catalog item (AI closes) → one order with the real total.
    customer_message(client, "PNID_T", "628123", "pesan 2 nasi goreng")
    orders = client.get("/api/orders", headers=auth(t["access_token"])).json()
    assert len(orders) == 1
    assert orders[0]["total"] == 28000


def test_order_updates_customer_stats(client, monkeypatch):
    """AI close-order triggers stats recompute; customer reflects one order."""
    async def fake_send(*a, **k):
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, customer=None):
        order = {"items": [{"name": "Nasi Goreng", "qty": 2, "price": 14000}], "total": 28000, "status": "closed"}
        return ("ok", order, None, True)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})

    customer_message(client, "PNID_T", "628777", "pesan 2 nasi goreng")
    rows = client.get("/api/customers", headers=auth(t["access_token"])).json()
    assert len(rows) == 1
    assert rows[0]["order_count"] == 1
    assert rows[0]["total_spent"] == 28000
