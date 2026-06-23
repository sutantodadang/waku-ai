"""business_type round-trips; product duration_minutes round-trips."""
from helpers import register, auth


def test_business_type_patch_get(client):
    t = register(client)
    h = auth(t["access_token"])
    assert client.get("/api/business", headers=h).json()["business_type"] == "warung"
    r = client.patch("/api/business", headers=h, json={"business_name": "Salon Sari", "business_type": "salon"})
    assert r.status_code == 200 and r.json()["business_type"] == "salon"


def test_business_type_rejects_invalid(client):
    t = register(client)
    h = auth(t["access_token"])
    r = client.patch("/api/business", headers=h, json={"business_name": "X", "business_type": "bengkel"})
    assert r.status_code == 422


def test_product_duration_round_trip(client):
    t = register(client)
    h = auth(t["access_token"])
    pid = client.post("/api/products", headers=h, json={"name": "Facial", "price": 80000, "duration_minutes": 60}).json()["id"]
    got = client.get(f"/api/products/{pid}", headers=h) if False else None  # GET-by-id may not exist
    listed = client.get("/api/products", headers=h).json()
    row = next(p for p in listed if p["id"] == pid)
    assert row["duration_minutes"] == 60
