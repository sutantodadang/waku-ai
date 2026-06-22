"""Owner can save + read payment methods and a QRIS image URL."""
from helpers import register, auth


def test_patch_and_get_payment_methods(client):
    t = register(client)
    h = auth(t["access_token"])
    body = {
        "business_name": "Warung Bu Tini",
        "payment_methods": [
            {"type": "rekening", "label": "BCA", "value": "1234567890 a.n. Tini"},
            {"type": "ewallet", "label": "GoPay", "value": "0812..."},
        ],
        "qris_image_url": "https://example.com/qris.png",
    }
    r = client.patch("/api/business", headers=h, json=body)
    assert r.status_code == 200
    data = r.json()
    assert len(data["payment_methods"]) == 2
    assert data["qris_image_url"] == "https://example.com/qris.png"


def test_get_business_profile_round_trip(client):
    """PATCH then GET must return identical payment_methods + qris_image_url."""
    t = register(client)
    h = auth(t["access_token"])
    methods = [
        {"type": "rekening", "label": "Mandiri", "value": "9876543210 a.n. Budi"},
        {"type": "ewallet", "label": "OVO", "value": "0811-222-333"},
    ]
    patch_body = {
        "business_name": "Toko Pak Budi",
        "payment_methods": methods,
        "qris_image_url": "https://example.com/qris-budi.png",
    }
    rp = client.patch("/api/business", headers=h, json=patch_body)
    assert rp.status_code == 200

    rg = client.get("/api/business", headers=h)
    assert rg.status_code == 200
    got = rg.json()
    assert got["business_name"] == "Toko Pak Budi"
    assert len(got["payment_methods"]) == 2
    assert got["payment_methods"][0]["label"] == "Mandiri"
    assert got["payment_methods"][1]["label"] == "OVO"
    assert got["qris_image_url"] == "https://example.com/qris-budi.png"
