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
