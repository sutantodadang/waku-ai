"""Reverse-OTP hardening: code-bound, expiry-checked, single-use, sender-bound."""
import main
from helpers import register, request_otp, deliver_otp_via_wa, auth


def test_otp_autosignup_provisions_account_for_new_phone(client):
    phone = "081999000111"
    # no prior register for this phone
    code = request_otp(client, phone)
    assert deliver_otp_via_wa(client, "6281999000111", code).json()["otp_matched"] == 1
    r = client.post("/api/auth/otp/verify", json={"phone_number": phone, "code": code})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["access_token"] and data["business_id"]
    # the freshly minted token works on a tenant-scoped endpoint
    assert client.get("/api/products", headers=auth(data["access_token"])).status_code == 200


def test_otp_login_existing_account_keeps_same_business(client):
    reg = register(client, email="a@x.com", business_name="Warung A", phone="081999000222")
    code = request_otp(client, "081999000222")
    deliver_otp_via_wa(client, "6281999000222", code)
    r = client.post("/api/auth/otp/verify", json={"phone_number": "081999000222", "code": code})
    assert r.status_code == 200
    # logs into the SAME business, does not create a duplicate
    assert r.json()["business_id"] == reg["business_id"]


def test_verify_requires_code_field(client):
    register(client, phone="081111111111")
    assert client.post("/api/auth/otp/verify", json={"phone_number": "081111111111"}).status_code == 422


def test_verify_before_delivery_fails(client):
    register(client, phone="081111111111")
    code = request_otp(client, "081111111111")
    # code requested but never sent from WhatsApp → no consumed record
    assert client.post("/api/auth/otp/verify", json={"phone_number": "081111111111", "code": code}).status_code == 400


def test_legit_flow_then_replay_blocked(client):
    register(client, email="a@x.com", phone="081111111111")
    code = request_otp(client, "081111111111")
    assert deliver_otp_via_wa(client, "6281111111111", code).json()["otp_matched"] == 1
    ok = client.post("/api/auth/otp/verify", json={"phone_number": "081111111111", "code": code})
    assert ok.status_code == 200 and ok.json()["access_token"]
    # replay with the same code must fail — single-use
    replay = client.post("/api/auth/otp/verify", json={"phone_number": "081111111111", "code": code})
    assert replay.status_code == 400


def test_wrong_code_rejected_even_with_consumed_record(client):
    register(client, phone="081111111111")
    code = request_otp(client, "081111111111")
    deliver_otp_via_wa(client, "6281111111111", code)
    assert client.post("/api/auth/otp/verify", json={"phone_number": "081111111111", "code": "WAKU-000000"}).status_code == 400


def test_code_from_wrong_sender_not_consumed(client):
    register(client, phone="081111111111")
    code = request_otp(client, "081111111111")
    # delivered from a DIFFERENT WhatsApp number → must not consume the victim's OTP
    assert deliver_otp_via_wa(client, "6289999999999", code).json()["otp_matched"] == 0
    assert client.post("/api/auth/otp/verify", json={"phone_number": "081111111111", "code": code}).status_code == 400


def test_platform_channel_sends_otp_confirmation(client, monkeypatch):
    sent = {"n": 0}

    async def fake_send(*a, **k):
        sent["n"] += 1
        return {}

    monkeypatch.setattr(main, "send_message", fake_send)
    register(client, phone="081111111111")
    code = request_otp(client, "081111111111")
    r = deliver_otp_via_wa(client, "6281111111111", code)
    assert r.json().get("channel") == "platform"
    assert sent["n"] == 1  # one confirmation reply; OTP path still never calls the LLM
