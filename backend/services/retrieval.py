"""Hybrid catalog retrieval — keyword first, embedding fallback, RRF fusion."""
from __future__ import annotations

import logging
import math
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Product
from services.embeddings import embed_texts

logger = logging.getLogger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _to_dict(p: Product) -> dict:
    return {"name": p.name, "price": p.price, "stock": True, "description": p.description or ""}


def _keyword_rank(products: list[Product], message: str) -> list[Product]:
    words = [w for w in re.findall(r"\w+", message.lower()) if len(w) >= 3]
    scored = []
    for p in products:
        name = (p.name or "").lower()
        desc = (p.description or "").lower()
        score = sum(3 for w in words if w in name) + sum(1 for w in words if w in desc)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda sp: sp[0], reverse=True)
    return [p for _, p in scored]


async def select_relevant_products(
    session: AsyncSession, business_id: int, message: str, k: int = 12
) -> list[dict]:
    """Return up to k products relevant to `message`, ready for the AI catalog."""
    products = list((await session.execute(
        select(Product).where(Product.business_id == business_id)
    )).scalars().all())

    # Small catalog: send everything, skip retrieval entirely.
    if len(products) <= k:
        return [_to_dict(p) for p in products]

    keyword = _keyword_rank(products, message)

    # Strong keyword signal → use it, skip embeddings.
    if len(keyword) >= k:
        return [_to_dict(p) for p in keyword[:k]]

    # Weak/empty keyword → embedding fallback.
    embed_rank: list[Product] = []
    embedded = [p for p in products if p.embedding]
    if embedded:
        try:
            qvec = embed_texts([message])[0]
            sims = sorted(embedded, key=lambda p: _cosine(qvec, p.embedding), reverse=True)
            embed_rank = sims
        except Exception as exc:
            logger.warning("Embedding retrieval failed, keyword-only: %s", exc)

    # RRF fusion of the two rankings (dedup by id).
    rrf: dict[int, float] = {}
    by_id: dict[int, Product] = {}
    for rank_list in (keyword, embed_rank):
        for i, p in enumerate(rank_list):
            rrf[p.id] = rrf.get(p.id, 0.0) + 1.0 / (60 + i)
            by_id[p.id] = p
    if not rrf:  # nothing matched either way → fall back to first k
        return [_to_dict(p) for p in products[:k]]
    top = sorted(rrf, key=lambda pid: rrf[pid], reverse=True)[:k]
    return [_to_dict(by_id[pid]) for pid in top]
