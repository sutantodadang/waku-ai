"""Hybrid retrieval: keyword subset, embedding fallback, small-catalog passthrough."""
import asyncio

from app.services import retrieval as retr
from app.services import embeddings as emb
from helpers import register, auth


def _make_products(client, token, names_prices):
    for name, price in names_prices:
        client.post("/api/products", headers=auth(token), json={"name": name, "price": price})


def test_keyword_picks_relevant_subset(client, monkeypatch):
    monkeypatch.setattr(emb, "embed_texts", lambda texts: [[0.0]] * len(texts))
    t = register(client)
    _make_products(client, t["access_token"], [(f"Produk {i}", 1000 + i) for i in range(50)] + [("Nasi Goreng", 14000)])
    from app.core import database
    from app import models
    from sqlalchemy import select

    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            return await retr.select_relevant_products(s, biz.id, "mau pesan nasi goreng", k=12)

    out = asyncio.run(_run())
    assert any(p["name"] == "Nasi Goreng" for p in out)
    assert len(out) <= 12


def test_small_catalog_returns_all_no_embed(client, monkeypatch):
    def boom(texts):
        raise AssertionError("embed must not be called for small catalog")
    monkeypatch.setattr(emb, "embed_texts", boom)
    t = register(client)
    _make_products(client, t["access_token"], [("Nasi Goreng", 14000), ("Es Teh", 4000)])
    from app.core import database
    from app import models
    from sqlalchemy import select

    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            return await retr.select_relevant_products(s, biz.id, "xyz tidak cocok", k=12)

    out = asyncio.run(_run())
    assert len(out) == 2  # all products, embed never called
