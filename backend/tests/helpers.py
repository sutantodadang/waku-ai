"""Shared test helpers."""


def register(client, email="a@x.com", password="secret1", business_name="Warung A", phone="081111111111"):
    r = client.post("/api/auth/register", json={
        "email": email, "password": password,
        "business_name": business_name, "phone_number": phone,
    })
    assert r.status_code == 200, r.text
    return r.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def connect_wa(client, token, phone_number_id="PNID_1", access_token="TKN_1", waba_id="WABA_1"):
    r = client.put("/api/whatsapp/connect", headers=auth(token), json={
        "phone_number_id": phone_number_id, "access_token": access_token, "waba_id": waba_id,
    })
    assert r.status_code == 200, r.text
    return r.json()


def request_otp(client, phone="081111111111", purpose="login"):
    r = client.post("/api/auth/otp/request", json={"phone_number": phone, "purpose": purpose})
    assert r.status_code == 200, r.text
    return r.json()["code"]


def deliver_otp_via_wa(client, wa_from, code, phone_number_id="PLATFORM_TEST"):
    """Simulate the owner sending the code from their WhatsApp to the platform number."""
    return client.post("/webhook", json={"entry": [{"changes": [{"value": {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": phone_number_id},
        "messages": [{"from": wa_from, "id": "w", "text": {"body": f"kode saya {code}"}}],
    }}]}]})


def customer_message(client, phone_number_id, wa_from, text):
    """Simulate a customer messaging a tenant's WhatsApp number."""
    return client.post("/webhook", json={"entry": [{"changes": [{"value": {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": phone_number_id},
        "messages": [{"from": wa_from, "id": "m", "text": {"body": text}}],
    }}]}]})
