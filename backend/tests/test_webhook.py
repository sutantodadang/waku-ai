"""Webhook routing: per-business send creds, unknown-tenant drop, order extraction."""
import main
from services.whatsapp import parse_statuses
from helpers import register, connect_wa, customer_message, auth


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
    async def fake_send(*a, **k):
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "AI_SERVICE_URL", "http://127.0.0.1:9")

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    customer_message(client, "PNID_T", "628123", "beli 2 nasi goreng dan 1 es teh")

    orders = client.get("/api/orders", headers=auth(t["access_token"])).json()
    assert len(orders) == 1
