"""Staff CRUD is scoped to the authenticated business."""
from helpers import register, auth


def test_staff_create_list_delete(client):
    t = register(client)
    h = auth(t["access_token"])
    r = client.post("/api/staff", headers=h, json={"name": "Sari"})
    assert r.status_code in (200, 201)
    sid = r.json()["id"]
    assert r.json()["name"] == "Sari" and r.json()["active"] is True

    rows = client.get("/api/staff", headers=h).json()
    assert any(s["id"] == sid for s in rows)

    d = client.delete(f"/api/staff/{sid}", headers=h)
    assert d.status_code == 200
    rows2 = client.get("/api/staff", headers=h).json()
    assert all(s["id"] != sid for s in rows2)


def test_staff_cross_tenant_delete_404(client):
    a = register(client)
    b = register(client, email="b@x.com", phone="082222222222")
    sid = client.post("/api/staff", headers=auth(a["access_token"]), json={"name": "Sari"}).json()["id"]
    d = client.delete(f"/api/staff/{sid}", headers=auth(b["access_token"]))
    assert d.status_code == 404
