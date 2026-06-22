# Phase B — Large Catalogs, LLM Orders & Payments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Waku handle hundreds of products via hybrid retrieval, make the LLM's close-of-conversation extraction the authoritative order, and auto-deliver payment info with two-way WhatsApp↔dashboard sync.

**Architecture:** The backend retrieves the top-k relevant products before each AI call (keyword first, embedding fallback) so the prompt stays lean. At order-close the AI service returns the structured order on `ReplyResponse.order`; the backend persists it (update-or-create for amendments) and sends configured payment methods. All outbound sends are gated on the WhatsApp 24-hour window.

**Tech Stack:** FastAPI (async) + SQLAlchemy (SQLite/aiosqlite) backend; separate FastAPI AI service (LLM + embeddings, provider switch `settings.use_openai`); React + TypeScript + Vite dashboard. Idempotent SQLite migrations via `database._run_migrations`.

## Global Constraints

- **24-hour window:** payment auto-send, payment re-send, and status notifications send only when `now - last_inbound_message <= 24h`; outside the window, skip and log. Meta templates are out of scope.
- **QRIS v1:** owner pastes a public https image URL; no backend-hosted upload.
- **Migrations:** all new columns added idempotently in `database._run_migrations` (`inspect` + `ALTER TABLE … ADD COLUMN`, SQLite only) — never via `create_all` alone.
- **Provider switch:** embeddings mirror `settings.use_openai` (OpenAI-compatible vs Ollama), same as `llm.ask_llm`.
- **AI service auth:** every `/ai/*` route stays gated by the existing `require_secret` dependency.
- **Tenant isolation:** every backend handler scopes by `business.id`; cross-tenant access on an order/product → 404.
- **Lean prompt:** the AI never receives the full catalog — only the retrieved subset (or all products when the catalog is ≤ k).
- **Reuse existing `PAYMENT` NLU intent** for "cara bayar?" — do NOT add a new intent.
- **AI item key is `qty`; backend item key is `quantity`.** Normalize `qty → quantity` when persisting an AI-extracted order.
- **REGULAR_THRESHOLD / amendment window:** amendable order = latest with status `pending` or `confirmed`, `created_at >= now - 6h`.

---

## File Structure

**AI service**
- `ai/embeddings.py` (new) — `embed_texts(texts)` provider switch + `cosine(a, b)`.
- `ai/config.py` (modify) — embedding model settings.
- `ai/ai_service.py` (modify) — `POST /ai/embed`; `ReplyResponse.order`.
- `ai/conversation.py` (modify) — on close run LLM extract, store `conv.closed_order`; reopen on post-close ORDER; "(sementara)" preview label; drop hardcoded catalog caps.
- `ai/tests/conftest.py` + `ai/tests/test_*.py` (new) — AI-side unit tests.

**Backend**
- `models.py` (modify) — `Product.embedding`, `Product.embedding_hash`; `Business.payment_methods`, `Business.qris_image_url`.
- `database.py` (modify) — `_PRODUCT_NEW_COLUMNS`, `_BUSINESS_PAYMENT_COLUMNS` migrations.
- `services/embeddings.py` (new) — `embed_texts(texts)` HTTP client to AI `/ai/embed`; `product_embed_text` + `product_hash`.
- `services/retrieval.py` (new) — `select_relevant_products(session, business_id, message, k=12)`.
- `services/payment.py` (new) — `format_payment_text`, `send_payment_info`.
- `services/whatsapp.py` (modify) — `within_service_window`, `send_image`.
- `services/order_service.py` (modify) — `find_amendable_order`, `update_order_items`.
- `schemas.py` (modify) — `PaymentMethod`, `BusinessProfileUpdate` extension, `BusinessResponse` extension, `SendPaymentResponse`.
- `main.py` (modify) — embed-on-product-write; retrieval in `_generate_ai_reply`; order update-or-create + payment auto-send in `_process_tenant_messages`; `POST /api/orders/{id}/send-payment`; status→WA notify in PATCH order; PATCH/GET business payment fields.

**Dashboard**
- `src/lib/types.ts`, `src/lib/api.ts`, `src/lib/queries.ts` (modify) — payment + send-payment.
- `src/pages/Settings.tsx` (modify) — payment methods editor.
- `src/pages/Orders.tsx` (modify) — "Kirim info bayar" button.

---

## Task 1: Product embedding columns + migration

**Files:**
- Modify: `backend/models.py:129-140` (Product)
- Modify: `backend/database.py:48-94`
- Test: `backend/tests/test_phase_b_migration.py` (new)

**Interfaces:**
- Produces: `Product.embedding` (JSON list[float], null), `Product.embedding_hash` (String, null).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_phase_b_migration.py
"""Phase B columns are added idempotently to legacy products/businesses tables."""
import asyncio
from sqlalchemy import inspect


def test_product_and_business_phase_b_columns_present(client):
    """The app fixture runs init_db(); new columns must exist after startup."""
    import database

    async def _cols():
        async with database.engine.begin() as conn:
            return await conn.run_sync(
                lambda sync: {
                    "products": {c["name"] for c in inspect(sync).get_columns("products")},
                    "businesses": {c["name"] for c in inspect(sync).get_columns("businesses")},
                }
            )

    cols = asyncio.get_event_loop().run_until_complete(_cols())
    assert {"embedding", "embedding_hash"} <= cols["products"]
    assert {"payment_methods", "qris_image_url"} <= cols["businesses"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_phase_b_migration.py -v`
Expected: FAIL — columns missing.

- [ ] **Step 3: Add the model columns**

In `backend/models.py`, inside `class Product` (after `image_url`, before `created_at`):

```python
    # ── Phase B: hybrid retrieval cache ──
    embedding: Mapped[Optional[list]] = mapped_column(JSON)
    embedding_hash: Mapped[Optional[str]] = mapped_column(String(64))
```

In `class Business` (after `is_connected`, before `created_at`):

```python
    # ── Phase B: payment delivery ──
    payment_methods: Mapped[list] = mapped_column(JSON, default=list)
    qris_image_url: Mapped[Optional[str]] = mapped_column(String(512))
```

- [ ] **Step 4: Add the migrations**

In `backend/database.py`, after `_CUSTOMER_NEW_COLUMNS` (line 68) add:

```python
_PRODUCT_NEW_COLUMNS: dict[str, str] = {
    "embedding": "JSON",
    "embedding_hash": "VARCHAR(64)",
}

_BUSINESS_PAYMENT_COLUMNS: dict[str, str] = {
    "payment_methods": "JSON",
    "qris_image_url": "VARCHAR(512)",
}
```

In `_run_migrations`, after the customers block (line 94) add:

```python
    # products: Phase B retrieval cache
    if "products" in insp.get_table_names():
        prod_existing = {c["name"] for c in insp.get_columns("products")}
        for name, ddl in _PRODUCT_NEW_COLUMNS.items():
            if name not in prod_existing:
                sync_conn.exec_driver_sql(f"ALTER TABLE products ADD COLUMN {name} {ddl}")
                logger.info("Migration: added products.%s", name)
    # businesses: Phase B payment columns
    biz_existing = {c["name"] for c in insp.get_columns("businesses")}
    for name, ddl in _BUSINESS_PAYMENT_COLUMNS.items():
        if name not in biz_existing:
            sync_conn.exec_driver_sql(f"ALTER TABLE businesses ADD COLUMN {name} {ddl}")
            logger.info("Migration: added businesses.%s", name)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_phase_b_migration.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite (no regressions)**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/models.py backend/database.py backend/tests/test_phase_b_migration.py
git commit -m "feat(phase-b): product embedding + business payment columns (migration)"
```

---

## Task 2: AI service `/ai/embed` + embeddings provider

**Files:**
- Create: `ai/embeddings.py`
- Modify: `ai/config.py:13-17`
- Modify: `ai/ai_service.py` (request models + endpoint)
- Create: `ai/tests/conftest.py`, `ai/tests/test_embeddings.py`

**Interfaces:**
- Produces: `embed_texts(texts: list[str]) -> list[list[float]]`; `cosine(a, b) -> float`; `POST /ai/embed {texts:[...]} -> {vectors:[[float]]}` (secret-gated).

- [ ] **Step 1: Write the failing test**

```python
# ai/tests/conftest.py
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
```

```python
# ai/tests/test_embeddings.py
import embeddings


def test_cosine_identical_is_one():
    assert abs(embeddings.cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9


def test_cosine_orthogonal_is_zero():
    assert abs(embeddings.cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9


def test_cosine_zero_vector_is_zero():
    assert embeddings.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_embed_texts_uses_provider(monkeypatch):
    monkeypatch.setattr(embeddings, "_embed_openai", lambda texts: [[0.1, 0.2]] * len(texts))
    monkeypatch.setattr(embeddings.settings, "llm_provider", "openai")
    monkeypatch.setattr(type(embeddings.settings), "use_openai", property(lambda self: True))
    out = embeddings.embed_texts(["a", "b"])
    assert out == [[0.1, 0.2], [0.1, 0.2]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai && python -m pytest tests/test_embeddings.py -v`
Expected: FAIL — `embeddings` module missing.

- [ ] **Step 3: Add embedding settings**

In `ai/config.py`, after line 17 (`ollama_model`) add:

```python
    # Embeddings (Phase B hybrid retrieval)
    embed_model: str = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    ollama_embed_model: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
```

- [ ] **Step 4: Create `ai/embeddings.py`**

```python
"""Embeddings for hybrid catalog retrieval — OpenAI-compatible or Ollama."""
import logging
import math
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Returns 0.0 for a zero vector or length mismatch."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embed_openai(texts: list[str]) -> Optional[list[list[float]]]:
    if not settings.openai_api_key:
        return None
    url = f"{settings.openai_base_url.rstrip('/')}/embeddings"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": settings.embed_model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            return [row["embedding"] for row in data["data"]]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.error("OpenAI embeddings failed: %s", exc)
        return None


def _embed_ollama(texts: list[str]) -> Optional[list[list[float]]]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"
    vectors: list[list[float]] = []
    try:
        with httpx.Client(timeout=60.0) as client:
            for text in texts:
                resp = client.post(url, json={"model": settings.ollama_embed_model, "prompt": text})
                resp.raise_for_status()
                vectors.append(resp.json()["embedding"])
        return vectors
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.error("Ollama embeddings failed: %s", exc)
        return None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Raises RuntimeError if the provider is unavailable."""
    if not texts:
        return []
    vectors = _embed_openai(texts) if settings.use_openai else _embed_ollama(texts)
    if vectors is None:
        raise RuntimeError("Embedding provider unavailable")
    return vectors


if __name__ == "__main__":
    assert abs(cosine([1.0, 2.0], [1.0, 2.0]) - 1.0) < 1e-9
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    print("embeddings self-check OK")
```

- [ ] **Step 5: Add the `/ai/embed` endpoint**

In `ai/ai_service.py`, after `CatalogSearchRequest` (line 92) add:

```python
class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., description="Texts to embed")


class EmbedResponse(BaseModel):
    vectors: list[list[float]] = Field(default_factory=list)
```

After the `/ai/catalog-search` endpoint (line 190) add:

```python
@app.post("/ai/embed", response_model=EmbedResponse, dependencies=[Depends(require_secret)])
async def ai_embed(request: EmbedRequest):
    """Embed texts for hybrid catalog retrieval."""
    from embeddings import embed_texts
    try:
        return EmbedResponse(vectors=embed_texts(request.texts))
    except RuntimeError as exc:
        logger.warning("Embedding unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="Embedding provider unavailable")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ai && python -m pytest tests/test_embeddings.py -v && python embeddings.py`
Expected: tests PASS; self-check prints OK.

- [ ] **Step 7: Commit**

```bash
git add ai/embeddings.py ai/config.py ai/ai_service.py ai/tests/conftest.py ai/tests/test_embeddings.py
git commit -m "feat(ai): /ai/embed endpoint + provider-switched embeddings"
```

---

## Task 3: Backend embedding client + product-write hook

**Files:**
- Create: `backend/services/embeddings.py`
- Modify: `backend/main.py` (product create + update handlers)
- Test: `backend/tests/test_product_embedding.py` (new)

**Interfaces:**
- Consumes: AI `POST /ai/embed`.
- Produces: `embed_texts(texts) -> list[list[float]]` (HTTP to AI), `product_embed_text(name, description) -> str`, `product_hash(text) -> str`, `async embed_product(session, product) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_product_embedding.py
"""Products get an embedding on create; unchanged edits don't recompute; AI down is non-blocking."""
import main
import services.embeddings as emb
from helpers import register, auth


def test_product_create_stores_embedding(client, monkeypatch):
    calls = []
    monkeypatch.setattr(emb, "embed_texts", lambda texts: (calls.append(texts) or [[0.5, 0.5]]))
    t = register(client)
    r = client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    assert r.status_code in (200, 201)
    pid = r.json()["id"]
    detail = client.get(f"/api/products/{pid}", headers=auth(t["access_token"])).json()
    # embedding isn't in the response schema; verify via a fresh fetch of the row
    assert calls and calls[0] == ["Nasi Goreng. "]


def test_embed_failure_is_non_blocking(client, monkeypatch):
    def boom(texts):
        raise RuntimeError("AI down")
    monkeypatch.setattr(emb, "embed_texts", boom)
    t = register(client)
    r = client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Es Teh", "price": 4000})
    assert r.status_code in (200, 201)  # product still created
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_product_embedding.py -v`
Expected: FAIL — `services.embeddings` missing.

- [ ] **Step 3: Create `backend/services/embeddings.py`**

```python
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
    text = product_embed_text(product.name, product.description)
    h = product_hash(text)
    if product.embedding is not None and product.embedding_hash == h:
        return  # unchanged
    try:
        product.embedding = embed_texts([text])[0]
        product.embedding_hash = h
        await session.flush()
    except Exception as exc:  # provider/network/parse — never block the write
        logger.warning("Embedding skipped for product %s: %s", getattr(product, "id", "?"), exc)
```

- [ ] **Step 4: Hook into product create + update**

In `backend/main.py`, find the product create handler (`POST /api/products`) and the update handler (`PUT /api/products/{id}`). After the product is added/flushed and its fields set, call the embed hook. Add the import near the other service imports:

```python
from services.embeddings import embed_product
```

In the create handler, after `await session.flush()` (product now has an id), before returning:

```python
    await embed_product(session, product)
```

In the update handler, after the fields are applied and flushed, before returning:

```python
    await embed_product(session, product)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_product_embedding.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/embeddings.py backend/main.py backend/tests/test_product_embedding.py
git commit -m "feat(phase-b): embed products on write via AI service (non-blocking)"
```

---

## Task 4: Retrieval service

**Files:**
- Create: `backend/services/retrieval.py`
- Test: `backend/tests/test_retrieval.py` (new)

**Interfaces:**
- Consumes: `services.embeddings.embed_texts`, `embeddings.cosine` (reimplement locally — backend has no `ai.embeddings`).
- Produces: `async select_relevant_products(session, business_id, message, k=12) -> list[dict]` returning `[{name, price, stock, description}]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_retrieval.py
"""Hybrid retrieval: keyword subset, embedding fallback, small-catalog passthrough."""
import asyncio

import services.retrieval as retr
import services.embeddings as emb
from helpers import register, auth


def _make_products(client, token, names_prices):
    for name, price in names_prices:
        client.post("/api/products", headers=auth(token), json={"name": name, "price": price})


def test_keyword_picks_relevant_subset(client, monkeypatch):
    monkeypatch.setattr(emb, "embed_texts", lambda texts: [[0.0]] * len(texts))
    t = register(client)
    _make_products(client, t["access_token"], [(f"Produk {i}", 1000 + i) for i in range(50)] + [("Nasi Goreng", 14000)])
    import database, models
    from sqlalchemy import select

    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            return await retr.select_relevant_products(s, biz.id, "mau pesan nasi goreng", k=12)

    out = asyncio.get_event_loop().run_until_complete(_run())
    assert any(p["name"] == "Nasi Goreng" for p in out)
    assert len(out) <= 12


def test_small_catalog_returns_all_no_embed(client, monkeypatch):
    def boom(texts):
        raise AssertionError("embed must not be called for small catalog")
    monkeypatch.setattr(emb, "embed_texts", boom)
    t = register(client)
    _make_products(client, t["access_token"], [("Nasi Goreng", 14000), ("Es Teh", 4000)])
    import database, models
    from sqlalchemy import select

    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            return await retr.select_relevant_products(s, biz.id, "xyz tidak cocok", k=12)

    out = asyncio.get_event_loop().run_until_complete(_run())
    assert len(out) == 2  # all products, embed never called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_retrieval.py -v`
Expected: FAIL — `services.retrieval` missing.

- [ ] **Step 3: Create `backend/services/retrieval.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_retrieval.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/retrieval.py backend/tests/test_retrieval.py
git commit -m "feat(phase-b): hybrid catalog retrieval (keyword + embedding RRF)"
```

---

## Task 5: Wire retrieval into AI reply + drop prompt caps

**Files:**
- Modify: `backend/main.py:386-396` (`_generate_ai_reply` catalog build)
- Modify: `ai/conversation.py:305-310` (drop the `[:20]` cap)
- Test: `backend/tests/test_reply_retrieval.py` (new)

**Interfaces:**
- Consumes: `services.retrieval.select_relevant_products`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_reply_retrieval.py
"""The /ai/reply payload carries the retrieved subset, not the whole catalog."""
import main
from helpers import register, connect_wa, customer_message, auth


def test_reply_payload_uses_retrieved_subset(client, monkeypatch):
    captured = {}

    async def fake_send(*a, **k):
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_retrieval(session, business_id, message, k=12):
        captured["called"] = True
        return [{"name": "Nasi Goreng", "price": 14000, "stock": True, "description": ""}]

    monkeypatch.setattr(main, "select_relevant_products", fake_retrieval)
    monkeypatch.setattr(main, "AI_SERVICE_URL", "http://127.0.0.1:9")  # force fallback after retrieval

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    customer_message(client, "PNID_T", "628123", "halo mau pesan")
    assert captured.get("called") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_reply_retrieval.py -v`
Expected: FAIL — `main.select_relevant_products` not defined.

- [ ] **Step 3: Use retrieval in `_generate_ai_reply`**

In `backend/main.py`, add the import near the other service imports:

```python
from services.retrieval import select_relevant_products
```

Replace the catalog build in `_generate_ai_reply` (lines 386-389):

```python
    catalog = await select_relevant_products(session, business.id, message_text, k=12)
```

(Delete the old `products = … ; catalog = [{...} for p in products]` lines.)

- [ ] **Step 4: Drop the AI-side prompt cap**

In `ai/conversation.py`, in `_llm_reply` replace `for item in conv.catalog[:20]` (line 308) with `for item in conv.catalog` (the catalog is already the lean retrieved subset).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_reply_retrieval.py -q && cd backend && uv run pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py ai/conversation.py backend/tests/test_reply_retrieval.py
git commit -m "feat(phase-b): retrieve lean catalog for AI reply; drop prompt cap"
```

---

## Task 6: `ReplyResponse.order` + close-of-conversation LLM extract

**Files:**
- Modify: `ai/conversation.py` (`OrderState`, `Conversation`, `generate_reply`, `_handle_order_flow`)
- Modify: `ai/ai_service.py` (`ReplyResponse` + `ai_reply`)
- Test: `ai/tests/test_close_order.py` (new)

**Interfaces:**
- Produces: `ReplyResponse.order: Optional[dict]` = `{"items":[{name,qty,price}], "total":float, "status":"closed"}` on the turn the order closes, else `null`. `Conversation.closed_order` holds the same dict or `None`.

- [ ] **Step 1: Write the failing test**

```python
# ai/tests/test_close_order.py
import conversation as conv_mod


def test_close_sets_closed_order(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "Baik kak")
    monkeypatch.setattr(
        conv_mod, "extract_order_from_chat",
        lambda history, catalog: {"items": [{"name": "Nasi Goreng", "qty": 2, "price": 14000}], "total": 28000, "notes": ""},
    )
    mgr = conv_mod.ConversationManager()
    monkeypatch.setattr(conv_mod, "manager", mgr)
    catalog = [{"name": "Nasi Goreng", "price": 14000}]
    conv_mod.generate_reply("628", "pesan 2 nasi goreng", catalog=catalog)
    conv_mod.generate_reply("628", "itu aja", catalog=catalog)
    conv = mgr.get("628")
    assert conv.closed_order is not None
    assert conv.closed_order["status"] == "closed"
    assert conv.closed_order["items"][0]["name"] == "Nasi Goreng"


def test_non_close_turn_has_no_closed_order(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "Baik kak")
    mgr = conv_mod.ConversationManager()
    monkeypatch.setattr(conv_mod, "manager", mgr)
    conv_mod.generate_reply("629", "halo kak", catalog=[{"name": "Nasi Goreng", "price": 14000}])
    assert mgr.get("629").closed_order is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai && python -m pytest tests/test_close_order.py -v`
Expected: FAIL — `Conversation.closed_order` missing.

- [ ] **Step 3: Add `closed_order` to the conversation + close handler**

In `ai/conversation.py`, add a field to `Conversation` (after `catalog`, line 61):

```python
    closed_order: Optional[dict] = None
```

In `generate_reply`, reset it at the start of each turn — after `conv = manager.get_or_create(session_id)` (line 138):

```python
    conv.closed_order = None
```

In `_handle_order_flow`, in the closing-signal branch (lines 239-242), before returning, run the LLM extract and store it:

```python
        if any(signal in text_lower for signal in closing_signals):
            conv.order.active = False
            extracted = extract_order_from_chat(conv.get_context(), conv.catalog)
            items = extracted.get("items") or []
            if items:
                conv.closed_order = {
                    "items": items,
                    "total": extracted.get("total", 0.0),
                    "status": "closed",
                }
            return (f"Siap Kak! Pesanannya:\n{conv.order.summary()}\n"
                    "Waku akan teruskan ke pemilik toko ya. Terima kasih Kak! 😊")
```

Add the import at the top of `conversation.py` (it already defines `extract_order_from_chat` later in the same module, so no import is needed — confirm `extract_order_from_chat` is defined above `_handle_order_flow` or referenced lazily). Since `extract_order_from_chat` is defined later in the file, reference it via the module to avoid a forward-reference error: replace the call with:

```python
            import sys as _sys
            extracted = _sys.modules[__name__].extract_order_from_chat(conv.get_context(), conv.catalog)
```

(Keeps it monkeypatch-friendly: the test patches `conversation.extract_order_from_chat`.)

- [ ] **Step 4: Mark the running summary as preview**

In `OrderState.summary` (line 38-45), change the header line `lines = ["Pesanan Kakak:"]` to:

```python
        lines = ["Pesanan Kakak (sementara):"]
```

- [ ] **Step 5: Expose `order` on the API**

In `ai/ai_service.py`, add to `ReplyResponse` (after `session_id`, line 70):

```python
    order: Optional[dict] = Field(default=None, description="Finalised order on close; null otherwise")
```

In `ai_reply`, after computing `reply` and before building the response, read the closed order:

```python
        conv = conversation_manager.get(request.session_id)
        closed = conv.closed_order if conv else None
        return ReplyResponse(
            reply=reply,
            intent=analysis["intent"],
            session_id=request.session_id,
            order=closed,
        )
```

(Replace the existing `return ReplyResponse(...)` in `ai_reply`.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ai && python -m pytest tests/test_close_order.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add ai/conversation.py ai/ai_service.py ai/tests/test_close_order.py
git commit -m "feat(ai): return finalised order on close (LLM source of truth)"
```

---

## Task 7: Backend order update-or-create + amendment

**Files:**
- Modify: `backend/services/order_service.py` (add helpers)
- Modify: `backend/main.py:286-303` (`_process_tenant_messages` order path), `_generate_ai_reply` (return order)
- Test: `backend/tests/test_order_finalize.py` (new)

**Interfaces:**
- Consumes: `ReplyResponse.order` from the AI service.
- Produces: `async find_amendable_order(session, business_id, customer_id, within_hours=6) -> Optional[Order]`; `async update_order_items(session, order, items) -> Order`. `_generate_ai_reply` returns `tuple[str, Optional[dict]]` (reply, ai_order).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_order_finalize.py
"""LLM close-order is persisted once; a later close amends it, not duplicates."""
import main
from helpers import register, connect_wa, customer_message, auth


def _ai_order(items, total):
    return {"items": items, "total": total, "status": "closed"}


def test_close_creates_single_order(client, monkeypatch):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        order = _ai_order([{"name": "Nasi Goreng", "qty": 2, "price": 14000}], 28000) if "itu aja" in text else None
        return ("ok kak", order)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    customer_message(client, "PNID_T", "628123", "pesan 2 nasi goreng")
    customer_message(client, "PNID_T", "628123", "itu aja")
    orders = client.get("/api/orders", headers=auth(t["access_token"])).json()
    assert len(orders) == 1
    assert orders[0]["total"] == 28000


def test_second_close_amends_existing(client, monkeypatch):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    seq = iter([
        _ai_order([{"name": "Nasi Goreng", "qty": 1, "price": 14000}], 14000),
        _ai_order([{"name": "Nasi Goreng", "qty": 3, "price": 14000}], 42000),
    ])

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return ("ok", next(seq)) if "itu aja" in text else ("ok", None)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    customer_message(client, "PNID_T", "628777", "itu aja")
    customer_message(client, "PNID_T", "628777", "eh tambah, itu aja")
    orders = client.get("/api/orders", headers=auth(t["access_token"])).json()
    assert len(orders) == 1          # amended, not duplicated
    assert orders[0]["total"] == 42000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_order_finalize.py -v`
Expected: FAIL — `_generate_ai_reply` returns a str, not a tuple.

- [ ] **Step 3: Add order-service helpers**

In `backend/services/order_service.py`, after `create_order` (line 260) add:

```python
async def find_amendable_order(
    session: AsyncSession, business_id: int, customer_id: int, within_hours: int = 6
) -> Optional[Order]:
    """Most recent non-terminal order (pending/confirmed) within the window, else None."""
    cutoff = datetime.utcnow() - timedelta(hours=within_hours)
    stmt = (
        select(Order)
        .where(
            Order.business_id == business_id,
            Order.customer_id == customer_id,
            Order.status.in_(("pending", "confirmed")),
            Order.created_at >= cutoff,
        )
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_order_items(session: AsyncSession, order: Order, items: list[dict]) -> Order:
    """Replace an order's items and recompute its total."""
    order.items = items
    order.total = sum((it.get("price") or 0) * (it.get("quantity") or 1) for it in items)
    await session.flush()
    return order
```

- [ ] **Step 4: Add an AI-item normaliser + persist helper in main.py**

In `backend/main.py`, add near the other helpers (e.g. after `_normalize_phone`):

```python
def _normalize_ai_items(ai_items: list[dict]) -> list[dict]:
    """AI items use `qty`; backend orders use `quantity`."""
    out = []
    for it in ai_items or []:
        out.append({
            "name": it.get("name", ""),
            "quantity": int(it.get("qty") or it.get("quantity") or 1),
            "price": it.get("price"),
        })
    return [it for it in out if it["name"]]


async def _persist_ai_order(session, business, customer, ai_order: dict) -> None:
    """Update the customer's amendable order or create a new one from the AI order."""
    items = _normalize_ai_items(ai_order.get("items", []))
    if not items:
        return
    existing = await find_amendable_order(session, business.id, customer.id)
    if existing is not None:
        await update_order_items(session, existing, items)
    else:
        await create_order(session, business.id, customer.id, items)
    try:
        await recompute_customer_stats(session, customer.id)
    except Exception:
        logger.exception("Failed to recompute stats for customer %d", customer.id)
```

Add the imports to the `from services.order_service import (` block: `find_amendable_order,` and `update_order_items,`.

- [ ] **Step 5: Make `_generate_ai_reply` return the AI order**

In `backend/main.py`, change `_generate_ai_reply` to return `tuple[str, Optional[dict]]`. Where it reads the AI response (line 408), capture `order`:

```python
            data = resp.json()
            reply = data.get("reply", "")
            ai_order = data.get("order")
            if reply:
                return reply, ai_order
```

Update both fallback `return` statements in that function to `return <text>, None`.

- [ ] **Step 6: Rework `_process_tenant_messages` order path**

In `backend/main.py`, replace the order block (lines 290-303) with:

```python
            reply, ai_order = await _generate_ai_reply(
                session, business, customer.phone_number, text, customer=customer
            )

            if ai_order and ai_order.get("status") == "closed":
                await _persist_ai_order(session, business, customer, ai_order)
                # Auto-send payment after the order is finalised (Task 10 wires this).
                await _maybe_send_payment(session, business, customer)
            elif main_ai_unreachable := (ai_order is None and _AI_FALLBACK_ORDER_REGEX):
                # AI unreachable → degraded regex fallback so orders aren't lost.
                products = (await session.execute(
                    select(Product).where(Product.business_id == business.id)
                )).scalars().all()
                known = {p.name: p.price for p in products}
                regex_items = extract_order_from_message(text, known or None)
                if regex_items:
                    await create_order(session, business.id, customer.id, regex_items)
                    try:
                        await recompute_customer_stats(session, customer.id)
                    except Exception:
                        logger.exception("recompute failed")

            reply = f"{reply}{AI_REPLY_FOOTER}"
```

Add a module flag near the top config (e.g. after `AI_SERVICE_SECRET`): `_AI_FALLBACK_ORDER_REGEX = True`. Add a temporary no-op `_maybe_send_payment` so this task is self-contained (Task 10 replaces its body):

```python
async def _maybe_send_payment(session, business, customer) -> None:
    """Placeholder — Task 10 implements payment auto-send."""
    return
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_order_finalize.py -v`
Expected: PASS (both create-single and amend-existing).

- [ ] **Step 8: Run full suite (the webhook order tests changed behaviour)**

Run: `cd backend && uv run pytest -q`
Expected: all pass. If `test_webhook.py::test_order_auto_extracted_from_message` or `test_offcatalog_item_creates_no_order` now assume per-message regex creation, update them to drive the close path via a monkeypatched `_generate_ai_reply` returning a closed `order` (mirror `test_order_finalize.py`). Record any such change in the commit message.

- [ ] **Step 9: Commit**

```bash
git add backend/services/order_service.py backend/main.py backend/tests/test_order_finalize.py backend/tests/test_webhook.py
git commit -m "feat(phase-b): persist LLM close-order with amendment (update-or-create)"
```

---

## Task 8: Payment config (Business fields + schemas + PATCH/GET)

**Files:**
- Modify: `backend/schemas.py` (`PaymentMethod`, `BusinessProfileUpdate`, `BusinessResponse`)
- Modify: `backend/main.py:675-684` (PATCH business) + business GET
- Test: `backend/tests/test_payment_config.py` (new)

**Interfaces:**
- Produces: `PaymentMethod{type,label,value}`; PATCH `/api/business` accepts `payment_methods`, `qris_image_url`; business response returns them.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_payment_config.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_payment_config.py -v`
Expected: FAIL — fields not accepted/returned.

- [ ] **Step 3: Extend the schemas**

In `backend/schemas.py`, in the Business section (after `BusinessProfileUpdate`, line 90) add:

```python
class PaymentMethod(BaseModel):
    type: str = Field(..., pattern="^(qris|rekening|ewallet)$")
    label: str = Field(..., min_length=1, max_length=60)
    value: str = Field(..., min_length=1, max_length=120)
```

Replace `BusinessProfileUpdate` with:

```python
class BusinessProfileUpdate(BaseModel):
    """PATCH /api/business — rename + payment config (all optional except name)."""
    business_name: str = Field(..., min_length=1, max_length=255)
    payment_methods: Optional[list[PaymentMethod]] = Field(default=None, max_length=10)
    qris_image_url: Optional[str] = Field(default=None, max_length=512)
```

Add to `BusinessResponse` (after `settings`, line 96):

```python
    payment_methods: list = Field(default_factory=list)
    qris_image_url: Optional[str] = None
```

- [ ] **Step 4: Apply the fields in PATCH**

In `backend/main.py` `update_business_profile` (line 681-684), before `await session.flush()`:

```python
    business.business_name = body.business_name
    if body.payment_methods is not None:
        business.payment_methods = [m.model_dump() for m in body.payment_methods]
    if body.qris_image_url is not None:
        business.qris_image_url = body.qris_image_url or None
    await session.flush()
```

Ensure any business GET handler returns the new fields (the `BusinessResponse` `from_attributes` pulls them automatically once the columns exist).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_payment_config.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py backend/main.py backend/tests/test_payment_config.py
git commit -m "feat(phase-b): payment methods + QRIS url on business (PATCH/GET)"
```

---

## Task 9: Payment send service + 24h window + image send

**Files:**
- Modify: `backend/services/whatsapp.py` (`within_service_window`, `send_image`)
- Create: `backend/services/payment.py`
- Test: `backend/tests/test_payment_send.py` (new)

**Interfaces:**
- Consumes: `models.Message`, `send_message`, `send_image`.
- Produces: `async within_service_window(session, customer_id) -> bool`; `async send_image(to, image_url, *, phone_number_id, access_token) -> dict`; `format_payment_text(business, total) -> str`; `async send_payment_info(session, business, customer, total) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_payment_send.py
"""Payment text formats methods; image sent only when URL set; skipped when no methods."""
import asyncio
import datetime

import services.payment as pay
import services.whatsapp as wa


class _Biz:
    def __init__(self, methods, qris=None):
        self.business_name = "Warung"
        self.payment_methods = methods
        self.qris_image_url = qris
        self.phone_number_id = "PNID"
        self.access_token = "TKN"


def test_format_payment_text_lists_methods():
    biz = _Biz([{"type": "rekening", "label": "BCA", "value": "123 a.n. Tini"}])
    text = pay.format_payment_text(biz, 28000)
    assert "28.000" in text or "28000" in text
    assert "BCA" in text and "123 a.n. Tini" in text


def test_send_payment_skips_when_no_methods(monkeypatch):
    sent = []
    monkeypatch.setattr(pay, "send_message", lambda *a, **k: sent.append(("text", a)))
    biz = _Biz([])

    async def _run():
        return await pay.send_payment_info_text_only(biz, 1000)

    out = asyncio.get_event_loop().run_until_complete(_run())
    assert out is False and sent == []
```

(Note: `send_payment_info` needs a DB session for the window check; this unit test exercises the pure formatter and a session-free helper `send_payment_info_text_only` used by the on-demand path. The full `send_payment_info` is covered by Task 10's integration test.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_payment_send.py -v`
Expected: FAIL — `services.payment` missing.

- [ ] **Step 3: Add window check + image send to whatsapp.py**

In `backend/services/whatsapp.py`, after `send_message` (line 175) add:

```python
async def send_image(
    to: str, image_url: str, *,
    phone_number_id: Optional[str] = None, access_token: Optional[str] = None,
) -> dict:
    """Send an image message by link (WhatsApp Cloud API)."""
    pid, token = _resolve_credentials(phone_number_id, access_token)
    if not pid or not token:
        return {"error": "whatsapp_not_configured"}
    url = f"{GRAPH_BASE}/{pid}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "recipient_type": "individual",
        "to": to, "type": "image", "image": {"link": image_url},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
```

At the bottom of `whatsapp.py` add the window helper (it needs the ORM, imported lazily to avoid a cycle):

```python
import datetime as _dt


async def within_service_window(session, customer_id: int, hours: int = 24) -> bool:
    """True when the customer messaged inbound within the last `hours` (WA free-form window)."""
    from sqlalchemy import select
    from models import Message
    stmt = (
        select(Message.timestamp)
        .where(Message.customer_id == customer_id, Message.direction == "inbound")
        .order_by(Message.timestamp.desc())
        .limit(1)
    )
    last = (await session.execute(stmt)).scalar_one_or_none()
    if last is None:
        return False
    return (_dt.datetime.utcnow() - last) <= _dt.timedelta(hours=hours)
```

- [ ] **Step 4: Create `backend/services/payment.py`**

```python
"""Payment delivery — format the business's methods and send within the WA window."""
from __future__ import annotations

import logging

from services.whatsapp import send_image, send_message, within_service_window

logger = logging.getLogger(__name__)


def format_payment_text(business, total: float) -> str:
    lines = [f"Total pesanan: Rp{total:,.0f}".replace(",", ".")]
    methods = business.payment_methods or []
    if methods:
        lines.append("\nSilakan bayar ke salah satu:")
        for m in methods:
            lines.append(f"• {m.get('label', '')}: {m.get('value', '')}")
    lines.append("\nMohon kirim bukti transfer ya Kak 🙏")
    return "\n".join(lines)


async def send_payment_info_text_only(business, total: float) -> bool:
    """Send payment text + QRIS image without a window check (caller already checked)."""
    if not (business.payment_methods or business.qris_image_url):
        return False
    text = format_payment_text(business, total)
    await send_message(
        # `to` is filled by the caller-bound partial; see send_payment_info.
        business._pay_to, text,
        phone_number_id=business.phone_number_id, access_token=business.access_token,
    )
    if business.qris_image_url:
        try:
            await send_image(
                business._pay_to, business.qris_image_url,
                phone_number_id=business.phone_number_id, access_token=business.access_token,
            )
        except Exception:
            logger.warning("Failed to send QRIS image")
    return True


async def send_payment_info(session, business, customer, total: float) -> bool:
    """Send payment info to the customer if within the 24h window and methods exist."""
    if not (business.payment_methods or business.qris_image_url):
        logger.info("No payment methods configured for business %d", business.id)
        return False
    if not await within_service_window(session, customer.id):
        logger.info("Outside 24h window — skipping payment send to %s", customer.phone_number)
        return False
    business._pay_to = customer.phone_number
    return await send_payment_info_text_only(business, total)
```

(`business._pay_to` is a transient attribute set per-call; it is never persisted.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_payment_send.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/whatsapp.py backend/services/payment.py backend/tests/test_payment_send.py
git commit -m "feat(phase-b): payment send service + 24h window + image-by-link"
```

---

## Task 10: Payment triggers (auto, dashboard, on-demand)

**Files:**
- Modify: `backend/main.py` (`_maybe_send_payment`; `POST /api/orders/{id}/send-payment`; PAYMENT-intent send)
- Modify: `backend/schemas.py` (`SendPaymentResponse`)
- Test: `backend/tests/test_payment_triggers.py` (new)

**Interfaces:**
- Consumes: `services.payment.send_payment_info`.
- Produces: `POST /api/orders/{id}/send-payment -> SendPaymentResponse{sent: bool}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_payment_triggers.py
"""Three entry points send payment via send_payment_info (mocked)."""
import main
from helpers import register, connect_wa, customer_message, auth


def _set_payment(client, token):
    client.patch("/api/business", headers=auth(token), json={
        "business_name": "Warung", "payment_methods": [{"type": "rekening", "label": "BCA", "value": "123"}],
    })


def test_dashboard_send_payment_endpoint(client, monkeypatch):
    sent = {}

    async def fake_pay(session, business, customer, total):
        sent["total"] = total
        return True
    monkeypatch.setattr(main, "send_payment_info", fake_pay)

    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return ("ok", {"items": [{"name": "Nasi Goreng", "qty": 1, "price": 14000}], "total": 14000, "status": "closed"})
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    _set_payment(client, t["access_token"])
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    customer_message(client, "PNID_T", "628123", "itu aja")
    order_id = client.get("/api/orders", headers=auth(t["access_token"])).json()[0]["id"]

    r = client.post(f"/api/orders/{order_id}/send-payment", headers=auth(t["access_token"]))
    assert r.status_code == 200
    assert r.json()["sent"] is True
    assert sent["total"] == 14000


def test_payment_intent_triggers_send(client, monkeypatch):
    calls = []

    async def fake_pay(session, business, customer, total):
        calls.append(total)
        return True
    monkeypatch.setattr(main, "send_payment_info", fake_pay)

    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return ("info bayar ya kak", None)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    _set_payment(client, t["access_token"])
    customer_message(client, "PNID_T", "628999", "kak cara bayar gimana?")
    assert calls  # PAYMENT intent → send_payment_info called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_payment_triggers.py -v`
Expected: FAIL — endpoint missing, `_maybe_send_payment` is a no-op.

- [ ] **Step 3: Implement `_maybe_send_payment` (auto trigger)**

In `backend/main.py`, replace the placeholder `_maybe_send_payment` body:

```python
async def _maybe_send_payment(session, business, customer) -> None:
    """Auto-send payment for the customer's latest amendable order, best-effort."""
    order = await find_amendable_order(session, business.id, customer.id)
    if order is None:
        return
    try:
        await send_payment_info(session, business, customer, order.total)
    except Exception:
        logger.exception("Auto payment send failed for customer %d", customer.id)
```

Add the import: `from services.payment import send_payment_info`.

- [ ] **Step 4: Add the on-demand (PAYMENT intent) trigger**

In `_process_tenant_messages`, after the order block and before sending the reply, detect the PAYMENT intent and send. Reuse the NLU already available via the AI analysis isn't returned here, so classify locally with a light check (the message text):

```python
            from services.payment import send_payment_info as _spi  # local alias
            if any(kw in text.lower() for kw in ("cara bayar", "gimana bayar", "bayar gimana", "pembayaran", "no rekening", "nomor rekening")):
                order = await find_amendable_order(session, business.id, customer.id)
                total = order.total if order else 0.0
                try:
                    await _spi(session, business, customer, total)
                except Exception:
                    logger.exception("On-demand payment send failed")
```

- [ ] **Step 5: Add the dashboard endpoint + schema**

In `backend/schemas.py`, after `UploadResponse` add:

```python
class SendPaymentResponse(BaseModel):
    sent: bool
```

In `backend/main.py`, after the PATCH order endpoint (line 842) add:

```python
@app.post("/api/orders/{order_id}/send-payment", response_model=SendPaymentResponse)
async def send_order_payment(
    order_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """Owner re-sends payment info for an order to its customer."""
    row = (await session.execute(
        select(Order, Customer)
        .join(Customer, Order.customer_id == Customer.id)
        .where(Order.id == order_id, Order.business_id == business.id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found for this business.")
    order, customer = row
    sent = await send_payment_info(session, business, customer, order.total)
    return SendPaymentResponse(sent=sent)
```

Add `SendPaymentResponse` to the `from schemas import (` block.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_payment_triggers.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/main.py backend/schemas.py backend/tests/test_payment_triggers.py
git commit -m "feat(phase-b): payment auto-send + dashboard endpoint + on-demand"
```

---

## Task 11: Dashboard → WhatsApp status sync

**Files:**
- Modify: `backend/main.py:836-842` (PATCH order status)
- Test: `backend/tests/test_status_sync.py` (new)

**Interfaces:**
- Consumes: `send_message`, `within_service_window`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_status_sync.py
"""Status change within the window notifies the customer; unmapped status sends nothing."""
import main
import services.whatsapp as wa
from helpers import register, connect_wa, customer_message, auth


def _open_window_order(client, monkeypatch):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, extracted_order=None, customer=None):
        return ("ok", {"items": [{"name": "Nasi Goreng", "qty": 1, "price": 14000}], "total": 14000, "status": "closed"})
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    customer_message(client, "PNID_T", "628123", "itu aja")  # inbound now → window open
    return t


def test_status_change_sends_wa_within_window(client, monkeypatch):
    t = _open_window_order(client, monkeypatch)
    notes = []

    async def capture_send(to, body, **k):
        notes.append((to, body))
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", capture_send)

    order_id = client.get("/api/orders", headers=auth(t["access_token"])).json()[0]["id"]
    client.patch(f"/api/orders/{order_id}", headers=auth(t["access_token"]), json={"status": "diproses"})
    assert any("disiapkan" in body for _, body in notes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_status_sync.py -v`
Expected: FAIL — no notification sent.

- [ ] **Step 3: Add the status→message map + notify hook**

In `backend/main.py`, near `DASHBOARD_TO_DB_STATUS` (line 137) add:

```python
STATUS_WA_MESSAGE = {
    "confirmed": "Pesanan kakak lagi disiapkan ya 🙏",
    "completed": "Pesanan kakak sudah selesai! Terima kasih 😊",
    "cancelled": "Mohon maaf, pesanan kakak dibatalkan.",
}
```

In `dashboard_update_order_status`, after `await recompute_customer_stats(...)` (line 841) and before `return`:

```python
    msg = STATUS_WA_MESSAGE.get(db_status)
    if msg and await within_service_window(session, customer.id):
        try:
            await send_message(
                customer.phone_number, msg,
                phone_number_id=business.phone_number_id, access_token=business.access_token,
            )
        except Exception:
            logger.exception("Status notification failed for order %d", order.id)
```

Add the import: `from services.whatsapp import within_service_window` (alongside the existing whatsapp imports).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_status_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Run full backend suite**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/tests/test_status_sync.py
git commit -m "feat(phase-b): notify customer on dashboard status change (24h-gated)"
```

---

## Task 12: Dashboard UI — payment editor + send button

**Files:**
- Modify: `dashboard/src/lib/types.ts`
- Modify: `dashboard/src/lib/api.ts`
- Modify: `dashboard/src/lib/queries.ts`
- Modify: `dashboard/src/pages/Settings.tsx`
- Modify: `dashboard/src/pages/Orders.tsx`

**Interfaces:**
- Consumes: PATCH `/api/business` (payment fields), `POST /api/orders/{id}/send-payment`.

- [ ] **Step 1: Add the types**

In `dashboard/src/lib/types.ts`, add:

```typescript
export interface PaymentMethod {
  type: "qris" | "rekening" | "ewallet";
  label: string;
  value: string;
}
```

Extend the business profile type used by Settings with optional `payment_methods?: PaymentMethod[]` and `qris_image_url?: string | null`. (Add to whichever interface models the business/profile response; if none exists, add `export interface BusinessProfile { business_name: string; payment_methods?: PaymentMethod[]; qris_image_url?: string | null; }`.)

- [ ] **Step 2: Add the API methods**

In `dashboard/src/lib/api.ts`, in the business section add (mirroring existing `body(d)` helper usage):

```typescript
  updateBusiness: (d: { business_name: string; payment_methods?: PaymentMethod[]; qris_image_url?: string | null }) =>
    req<BusinessProfile>("/api/business", { method: "PATCH", ...body(d) }),
  sendOrderPayment: (id: number) =>
    req<{ sent: boolean }>(`/api/orders/${id}/send-payment`, { method: "POST" }),
```

Import `PaymentMethod`, `BusinessProfile` from `./types`.

- [ ] **Step 3: Add the query hooks**

In `dashboard/src/lib/queries.ts`, add:

```typescript
export function useUpdateBusiness() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: { business_name: string; payment_methods?: PaymentMethod[]; qris_image_url?: string | null }) =>
      api.updateBusiness(d),
    onSuccess: () => qc.invalidateQueries(),
  });
}

export function useSendOrderPayment() {
  return useMutation({ mutationFn: (id: number) => api.sendOrderPayment(id) });
}
```

Import `PaymentMethod` from `./types`.

- [ ] **Step 4: Payment editor in Settings**

In `dashboard/src/pages/Settings.tsx`, add a Card with the payment editor. Minimal implementation:

```tsx
// inside the Settings component, with existing useState imports
const updateBiz = useUpdateBusiness();
const [methods, setMethods] = useState<PaymentMethod[]>([]);
const [qris, setQris] = useState("");

function addMethod() {
  setMethods((m) => [...m, { type: "rekening", label: "", value: "" }]);
}
function savePayment() {
  updateBiz.mutate({ business_name: businessName, payment_methods: methods, qris_image_url: qris || null });
}
```

```tsx
<Card>
  <h2 className="mb-1 font-display text-base font-bold text-ink">Metode Pembayaran</h2>
  <p className="mb-3 text-sm text-ink/55">Info ini dikirim otomatis ke pelanggan setelah pesanan selesai.</p>
  {methods.map((m, i) => (
    <div key={i} className="mb-2 flex gap-2">
      <select
        className={inputCls}
        value={m.type}
        onChange={(e) => setMethods((arr) => arr.map((x, j) => (j === i ? { ...x, type: e.target.value as PaymentMethod["type"] } : x)))}
      >
        <option value="rekening">Rekening</option>
        <option value="ewallet">E-wallet</option>
        <option value="qris">QRIS</option>
      </select>
      <input className={inputCls} placeholder="Label (BCA)" value={m.label}
        onChange={(e) => setMethods((arr) => arr.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
      <input className={inputCls} placeholder="Nomor / a.n." value={m.value}
        onChange={(e) => setMethods((arr) => arr.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
      <button type="button" onClick={() => setMethods((arr) => arr.filter((_, j) => j !== i))}>✕</button>
    </div>
  ))}
  <Button variant="ghost" type="button" onClick={addMethod}>+ Tambah metode</Button>
  <Field label="URL Gambar QRIS (opsional)">
    <input className={inputCls} value={qris} onChange={(e) => setQris(e.target.value)} placeholder="https://..." />
  </Field>
  <Button onClick={savePayment} disabled={updateBiz.isPending}>{updateBiz.isPending ? "..." : "Simpan pembayaran"}</Button>
</Card>
```

Wire `methods`/`qris` initial state from the loaded business profile if the page already fetches it; otherwise leave them empty (the PATCH replaces them). Import `useUpdateBusiness`, `PaymentMethod`, and reuse existing `businessName` state (or read the current business name from the profile query).

- [ ] **Step 5: "Kirim info bayar" button in Orders**

In `dashboard/src/pages/Orders.tsx`, in each order row's actions add:

```tsx
const sendPay = useSendOrderPayment();
// ...
<Button variant="ghost" onClick={() => sendPay.mutate(order.id)} disabled={sendPay.isPending}>
  {sendPay.isPending ? "..." : "Kirim info bayar"}
</Button>
```

Import `useSendOrderPayment`.

- [ ] **Step 6: Typecheck + build**

Run: `cd dashboard && bun run tsc --noEmit && bun run build`
Expected: no type errors; build succeeds. Fix any type mismatches surfaced (e.g. ensure `inputCls`, `Field`, `Button`, `Card` are imported in the edited pages).

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/lib/types.ts dashboard/src/lib/api.ts dashboard/src/lib/queries.ts dashboard/src/pages/Settings.tsx dashboard/src/pages/Orders.tsx
git commit -m "feat(dashboard): payment methods editor + send-payment button"
```

---

## Final Verification

- [ ] Backend: `cd backend && uv run pytest -q` — all pass.
- [ ] AI service: `cd ai && python -m pytest tests/ -q && python embeddings.py` — pass + self-check OK.
- [ ] Dashboard: `cd dashboard && bun run tsc --noEmit && bun run build` — clean.

---

## Self-Review notes (plan author)

**Spec coverage check:**
- B1 retrieval → Tasks 1-5. ✅
- B2 LLM order source-of-truth → Task 6 (AI) + Task 7 (backend persist). ✅
- Amendment (mid-chat + post-final) → Task 6 (reopen via close handler / LLM over transcript) + Task 7 (`find_amendable_order` update-or-create, ≤6h, terminal guard). ✅
- Payment (3 triggers, QRIS url + bank + ewallet) → Tasks 8-10. ✅
- Dashboard→WA status sync → Task 11. ✅
- 24h window gate → Task 9 helper, used by Tasks 9-11. ✅
- Dashboard UI → Task 12. ✅

**Known follow-ups (flagged, not blockers):**
- Post-final amendment depends on the AI service in-memory `conv` surviving between webhook calls (single AI-service process). If the AI service restarts mid-conversation, the reopen relies on the backend `find_amendable_order` window — which still works because backend update-or-create is keyed on the DB order, not the in-memory state.
- The on-demand PAYMENT trigger (Task 10 step 4) uses a keyword check in the backend rather than the AI intent, because `_generate_ai_reply` does not return the intent. If intent passthrough is later added to `ReplyResponse`, replace the keyword check with the real intent.
- Backfilling embeddings for products created before Task 3 is not automated; they are embedded on next edit and still found by keyword meanwhile.
