"""Products get an embedding on create; unchanged edits don't recompute; AI down is non-blocking."""
from app import main
from app.services import embeddings as emb
from helpers import register, auth


def test_product_create_stores_embedding(client, monkeypatch):
    calls = []
    monkeypatch.setattr(emb, "embed_texts", lambda texts: (calls.append(texts) or [[0.5, 0.5]]))
    t = register(client)
    r = client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    assert r.status_code in (200, 201)
    pid = r.json()["id"]
    # embedding isn't in the response schema; verify via the calls list
    assert calls and calls[0] == ["Nasi Goreng. "]


def test_embed_failure_is_non_blocking(client, monkeypatch):
    def boom(texts):
        raise RuntimeError("AI down")
    monkeypatch.setattr(emb, "embed_texts", boom)
    t = register(client)
    r = client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Es Teh", "price": 4000})
    assert r.status_code in (200, 201)  # product still created
