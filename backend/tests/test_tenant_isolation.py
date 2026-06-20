"""Every dashboard resource must be scoped to the authenticated business."""
from helpers import register, auth


def two_tenants(client):
    t1 = register(client, email="a@x.com", business_name="Warung A", phone="081111111111")
    t2 = register(client, email="b@x.com", business_name="Warung B", phone="082222222222")
    return t1, t2


def test_products_isolated(client):
    t1, t2 = two_tenants(client)
    r = client.post("/api/products", headers=auth(t1["access_token"]), json={"name": "Nasi Goreng", "price": 15000})
    assert r.status_code == 201
    assert len(client.get("/api/products", headers=auth(t1["access_token"])).json()) == 1
    assert len(client.get("/api/products", headers=auth(t2["access_token"])).json()) == 0


def test_cannot_delete_other_tenants_product(client):
    t1, t2 = two_tenants(client)
    pid = client.post("/api/products", headers=auth(t1["access_token"]), json={"name": "X", "price": 1000}).json()["id"]
    # tenant 2 must not be able to delete tenant 1's product
    assert client.delete(f"/api/products/{pid}", headers=auth(t2["access_token"])).status_code == 404
    # owner can
    assert client.delete(f"/api/products/{pid}", headers=auth(t1["access_token"])).status_code == 200


def test_settings_isolated(client):
    t1, t2 = two_tenants(client)
    client.put("/api/settings", headers=auth(t1["access_token"]), json={"greeting_message": "Halo dari A"})
    assert client.get("/api/settings", headers=auth(t1["access_token"])).json()["greeting_message"] == "Halo dari A"
    assert client.get("/api/settings", headers=auth(t2["access_token"])).json()["greeting_message"] == ""
