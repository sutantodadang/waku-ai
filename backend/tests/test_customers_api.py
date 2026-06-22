"""Customer endpoints: scoping, update, bounds."""
import main
from helpers import register, connect_wa, customer_message, auth


def _setup(client, monkeypatch, pnid="PNID_C"):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "AI_SERVICE_URL", "http://127.0.0.1:9")
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id=pnid, access_token="TKN")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    return t


def test_list_and_detail(client, monkeypatch):
    t = _setup(client, monkeypatch)
    customer_message(client, "PNID_C", "628111", "pesan 2 nasi goreng")

    rows = client.get("/api/customers", headers=auth(t["access_token"])).json()
    assert len(rows) == 1
    cid = rows[0]["id"]
    assert rows[0]["order_count"] == 1 and rows[0]["total_spent"] == 28000

    detail = client.get(f"/api/customers/{cid}", headers=auth(t["access_token"])).json()
    assert detail["phone_number"] == "628111"
    assert len(detail["recent_orders"]) == 1


def test_patch_notes_and_override(client, monkeypatch):
    t = _setup(client, monkeypatch)
    customer_message(client, "PNID_C", "628111", "pesan 2 nasi goreng")
    cid = client.get("/api/customers", headers=auth(t["access_token"])).json()[0]["id"]

    r = client.patch(f"/api/customers/{cid}", headers=auth(t["access_token"]),
                     json={"notes": "tanpa pedas", "tags": ["alergi udang"], "is_regular_override": True})
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == "tanpa pedas" and body["tags"] == ["alergi udang"]
    assert body["is_regular"] is True  # override forces langganan


def test_tags_bound_rejected(client, monkeypatch):
    t = _setup(client, monkeypatch)
    customer_message(client, "PNID_C", "628111", "pesan 2 nasi goreng")
    cid = client.get("/api/customers", headers=auth(t["access_token"])).json()[0]["id"]
    r = client.patch(f"/api/customers/{cid}", headers=auth(t["access_token"]),
                     json={"tags": [f"t{i}" for i in range(11)]})
    assert r.status_code == 422


def test_cross_tenant_denied(client, monkeypatch):
    t1 = _setup(client, monkeypatch, pnid="PNID_A")
    customer_message(client, "PNID_A", "628111", "pesan 2 nasi goreng")
    cid = client.get("/api/customers", headers=auth(t1["access_token"])).json()[0]["id"]

    t2 = register(client, email="b@x.com", phone="082222222222")
    r = client.get(f"/api/customers/{cid}", headers=auth(t2["access_token"]))
    assert r.status_code == 404
    r = client.patch(f"/api/customers/{cid}", headers=auth(t2["access_token"]), json={"notes": "x"})
    assert r.status_code == 404
