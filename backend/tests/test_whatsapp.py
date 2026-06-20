"""WhatsApp connection: status, clash protection, token encryption at rest, signup skeleton."""
import asyncio

from sqlalchemy import select, text

from database import async_session_factory
from models import Business
from helpers import register, auth, connect_wa


def test_connect_and_status(client):
    t = register(client)
    assert client.get("/api/whatsapp/status", headers=auth(t["access_token"])).json()["is_connected"] is False
    connect_wa(client, t["access_token"], phone_number_id="PNID_X", access_token="SECRET", waba_id="W1")
    status = client.get("/api/whatsapp/status", headers=auth(t["access_token"])).json()
    assert status["is_connected"] is True
    assert status["phone_number_id"] == "PNID_X"


def test_phone_number_id_cannot_be_claimed_twice(client):
    t1 = register(client, email="a@x.com", phone="081111111111")
    t2 = register(client, email="b@x.com", phone="082222222222")
    connect_wa(client, t1["access_token"], phone_number_id="SHARED")
    r = client.put("/api/whatsapp/connect", headers=auth(t2["access_token"]),
                   json={"phone_number_id": "SHARED", "access_token": "x"})
    assert r.status_code == 409


def test_token_encrypted_at_rest(client):
    t = register(client)
    bid = t["business_id"]
    connect_wa(client, t["access_token"], phone_number_id="PNID_E", access_token="SUPER_SECRET_TOKEN")

    async def check():
        async with async_session_factory() as s:
            biz = (await s.execute(select(Business).where(Business.id == bid))).scalar_one()
            assert biz.access_token == "SUPER_SECRET_TOKEN"  # decrypts transparently
            raw = (await s.execute(text("SELECT access_token FROM businesses WHERE id=:i"), {"i": bid})).scalar()
            assert raw != "SUPER_SECRET_TOKEN"  # stored ciphertext, not plaintext
    asyncio.run(check())


def test_embedded_signup_skeleton_returns_501_without_meta_creds(client):
    t = register(client)
    r = client.get("/api/whatsapp/embedded-signup/callback?code=abc", headers=auth(t["access_token"]))
    assert r.status_code == 501
