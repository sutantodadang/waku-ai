"""Tests for POST /api/qris/generate — QRIS payload → PNG upload."""
import os

SAMPLE_PAYLOAD = (
    "00020101021126610014COM.GO-JEK.WWW011893600914"
    "01234567890123456789520459455303360"
    "5802ID5910Toko Budi6007Jakarta6304ABCD"
)


def test_generate_qris_returns_png_url(client, tmp_path, monkeypatch):
    """Valid payload → 200 with /uploads/qris_*.png URL; file is valid PNG."""
    from app.api.routers import media
    upload_dir = str(tmp_path)
    monkeypatch.setattr(media, "UPLOAD_DIR", upload_dir)

    r = client.post("/api/qris/generate", json={"payload": SAMPLE_PAYLOAD})
    assert r.status_code == 200, r.text
    data = r.json()
    url: str = data["url"]
    assert url.startswith("/uploads/qris_"), f"Unexpected url: {url}"
    assert url.endswith(".png"), f"Unexpected url: {url}"

    filename = url.split("/uploads/")[1]
    filepath = os.path.join(upload_dir, filename)
    assert os.path.exists(filepath), "PNG file not created on disk"
    with open(filepath, "rb") as f:
        header = f.read(4)
    assert header == b"\x89PNG", f"Not a PNG: {header!r}"


def test_generate_qris_empty_payload_returns_422(client):
    """Empty payload → 422 Unprocessable Entity."""
    r = client.post("/api/qris/generate", json={"payload": ""})
    assert r.status_code == 422


def test_generate_qris_whitespace_payload_returns_422(client):
    """Whitespace-only payload → 422."""
    r = client.post("/api/qris/generate", json={"payload": "   "})
    assert r.status_code == 422
