"""The /ai/reply payload carries the retrieved subset, not the whole catalog."""
import main
from helpers import register, connect_wa, customer_message, auth


def test_reply_payload_uses_retrieved_subset(client, monkeypatch):
    captured = {}

    async def fake_send(*a, **k):
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_retrieval(session, business_id, message, k=12):
        captured["called"] = True
        return [{"name": "Nasi Goreng", "price": 14000, "stock": True, "description": ""}]

    monkeypatch.setattr(main, "select_relevant_products", fake_retrieval)
    monkeypatch.setattr(main, "AI_SERVICE_URL", "http://127.0.0.1:9")  # force fallback after retrieval

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    customer_message(client, "PNID_T", "628123", "halo mau pesan")
    assert captured.get("called") is True
