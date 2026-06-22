"""Status change within the window notifies the customer; unmapped status sends nothing."""
import main
import services.whatsapp as wa
from helpers import register, connect_wa, customer_message, auth


def _open_window_order(client, monkeypatch):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    # 3-tuple: (reply_text, ai_order_dict, ai_ok)
    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return ("ok", {"items": [{"name": "Nasi Goreng", "qty": 1, "price": 14000}], "total": 14000, "status": "closed"}, True)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    customer_message(client, "PNID_T", "628111000001", "mau pesan nasi goreng 1")
    # inbound message recorded → window open
    return t


def test_status_change_sends_wa_within_window(client, monkeypatch):
    t = _open_window_order(client, monkeypatch)
    notes = []

    async def capture_send(to, body, **k):
        notes.append((to, body))
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", capture_send)

    order_id = client.get("/api/orders", headers=auth(t["access_token"])).json()[0]["id"]
    client.patch(f"/api/orders/{order_id}", headers=auth(t["access_token"]), json={"status": "diproses"})
    assert any("disiapkan" in body for _, body in notes)


def test_unmapped_status_sends_nothing(client, monkeypatch):
    t = _open_window_order(client, monkeypatch)
    notes = []

    async def capture_send(to, body, **k):
        notes.append((to, body))
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", capture_send)

    order_id = client.get("/api/orders", headers=auth(t["access_token"])).json()[0]["id"]
    # "baru" → db "pending" — not in STATUS_WA_MESSAGE → no WA send
    client.patch(f"/api/orders/{order_id}", headers=auth(t["access_token"]), json={"status": "baru"})
    assert len(notes) == 0


def test_outside_window_skips_notification(client, monkeypatch):
    t = _open_window_order(client, monkeypatch)
    notes = []

    async def capture_send(to, body, **k):
        notes.append((to, body))
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", capture_send)

    # Force within_service_window to return False (outside window)
    async def outside_window(session, customer_id, hours=24):
        return False
    monkeypatch.setattr(wa, "within_service_window", outside_window)
    monkeypatch.setattr(main, "within_service_window", outside_window)

    order_id = client.get("/api/orders", headers=auth(t["access_token"])).json()[0]["id"]
    client.patch(f"/api/orders/{order_id}", headers=auth(t["access_token"]), json={"status": "diproses"})
    assert len(notes) == 0
