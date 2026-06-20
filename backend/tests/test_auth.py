"""Email + password auth."""
from helpers import register, auth


def test_register_returns_token_and_business(client):
    data = register(client)
    assert data["access_token"]
    assert data["business_id"] >= 1
    assert data["business_name"] == "Warung A"


def test_duplicate_email_rejected(client):
    register(client, email="a@x.com", phone="081111111111")
    r = client.post("/api/auth/register", json={
        "email": "a@x.com", "password": "secret9", "business_name": "Dup", "phone_number": "082222222222",
    })
    assert r.status_code == 409


def test_duplicate_phone_rejected(client):
    register(client, email="a@x.com", phone="081111111111")
    r = client.post("/api/auth/register", json={
        "email": "b@x.com", "password": "secret9", "business_name": "Dup", "phone_number": "081111111111",
    })
    assert r.status_code == 409


def test_short_password_rejected_by_schema(client):
    r = client.post("/api/auth/register", json={
        "email": "c@x.com", "password": "x", "business_name": "C", "phone_number": "083333333333",
    })
    assert r.status_code == 422


def test_login_ok_and_wrong_password(client):
    register(client, email="a@x.com", password="secret1")
    assert client.post("/api/auth/login", json={"email": "a@x.com", "password": "secret1"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "a@x.com", "password": "WRONG"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@x.com", "password": "secret1"}).status_code == 401


def test_unauthenticated_dashboard_rejected(client):
    assert client.get("/api/products").status_code == 401
    assert client.get("/api/orders").status_code == 401
    assert client.get("/api/dashboard/summary").status_code == 401


def test_invalid_token_rejected(client):
    assert client.get("/api/products", headers=auth("garbage.token.value")).status_code == 401


def test_register_rejects_reserved_synthetic_namespace(client):
    # The wa-...@waku.local namespace is reserved for passwordless OTP accounts;
    # registering into it (to squat a victim's phone) must be rejected.
    r = client.post("/api/auth/register", json={
        "email": "wa-6281242046113@waku.local", "password": "secret1",
        "business_name": "Squat", "phone_number": "081242046113",
    })
    assert r.status_code == 422
