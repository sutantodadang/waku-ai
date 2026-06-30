"""Backend embedding client — calls the AI service /ai/embed and caches vectors."""
from __future__ import annotations

import hashlib
import logging
import os

import httpx

logger = logging.getLogger(__name__)

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")
AI_SERVICE_SECRET = os.getenv("AI_SERVICE_SECRET", "")


def product_embed_text(name: str, description: str | None) -> str:
    """Canonical text embedded for a product."""
    return f"{name}. {description or ''}"


def product_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Call the AI service to embed texts. Raises on any failure (caller handles)."""
    headers = {"X-Waku-Secret": AI_SERVICE_SECRET} if AI_SERVICE_SECRET else {}
    with httpx.Client(timeout=20) as client:
        resp = client.post(f"{AI_SERVICE_URL}/ai/embed", json={"texts": texts}, headers=headers)
        resp.raise_for_status()
        return resp.json()["vectors"]


async def embed_product(session, product) -> None:
    """Compute + store a product's embedding when its text changed. Non-blocking:
    any failure logs and leaves the existing (or null) embedding in place."""
    try:
        text = product_embed_text(product.name, product.description)
        h = product_hash(text)
        if product.embedding_hash == h:
            return  # no-op: text unchanged
        vectors = embed_texts([text])
        product.embedding = vectors[0]
        product.embedding_hash = h
        await session.flush()
    except Exception as exc:  # provider/network/parse — never block the write
        logger.warning("Embedding skipped for product %s: %s", getattr(product, "id", "?"), exc)
