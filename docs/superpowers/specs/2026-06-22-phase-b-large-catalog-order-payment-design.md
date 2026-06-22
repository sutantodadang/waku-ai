# Phase B — Large Catalogs, LLM Orders & Payments

Status: Design approved · Date: 2026-06-22 · Owner: sutantodadang

## Context

Waku is a multi-tenant WhatsApp assistant for Indonesian UMKM. Phase A
(Kenal Langganan) shipped customer recognition. Phase B broadens Waku to
businesses with **hundreds of products** and upgrades the order pipeline so
the AI's structured order becomes the **source of truth**, with automatic
payment delivery and two-way WhatsApp ↔ dashboard sync.

This is one combined spec covering two coupled subsystems that share the
order/catalog pipeline:

- **B1 — Hybrid catalog retrieval:** the AI handles hundreds of SKUs without
  flooding the prompt, by retrieving only the relevant products per message.
- **B2 — Order pipeline upgrade:** the LLM extraction at order-close is the
  authoritative order; the bot auto-sends payment info (QRIS image / bank /
  e-wallet), handles order amendments, and syncs status changes back to the
  customer over WhatsApp.

### Current state (what exists)

- Catalog is truncated into the prompt: `conversation.py:305` caps the LLM
  context at 20 products, `:422` caps order-extraction at 30, the menu reply
  `:188` caps at 15. With hundreds of products, most of the catalog is dark.
- Orders are extracted by **regex per single message**
  (`main.py:294` → `extract_order_from_message`) and an order is created on
  every message that yields items. The conversation-aware LLM endpoint
  `/ai/extract-order` exists but the backend never calls it.
- There is **no payment** feature anywhere. Owners currently send QRIS /
  bank / e-wallet details to customers by hand.
- Dashboard → WhatsApp is **one-way**: orders appear in the dashboard, but a
  status change there does not notify the customer.

## Goals

1. AI replies and order extraction stay accurate over catalogs of hundreds
   of SKUs, with a prompt that never carries the whole catalog.
2. The order persisted to the DB is the LLM's interpretation of the whole
   conversation at close — not a per-message regex guess.
3. After an order is finalised, the bot sends the business's configured
   payment methods automatically; the owner can also re-send from the
   dashboard, and the bot answers "cara bayar?" on demand.
4. Customers can change their mind — mid-chat and after the order is final —
   and the persisted order and payment reflect the final intent.
5. When the owner changes an order's status in the dashboard, the customer
   is notified over WhatsApp (subject to the 24-hour window).

### Hard constraint: WhatsApp 24-hour window

WhatsApp forbids free-form outbound messages outside the 24-hour
customer-service window (since the customer's last inbound message).
All outbound sends in this spec — payment auto-send, payment re-send, and
status notifications — are gated on that window. Outside the window the send
is **skipped and logged**. Approved Meta templates (which can message outside
the window) are **out of scope**, consistent with the Phase A reorder-push
decision.

## Architecture

```
customer chat ──► [B1 retrieval] pick ~12 relevant products
                        │  keyword first, embedding fallback
                        ▼
                  /ai/reply  (lean prompt — top-k, never hundreds)
                        │  multi-turn order-state (existing)
                        ▼  customer closes ("itu aja")
                  [B2] LLM extract over full chat = final order
                        │  → ReplyResponse.order {items,total,status:"closed"}
                        ▼
   backend: update-or-create order (regex fallback) ──► recompute stats
                        │
                        ▼
                  [B2] send_payment_info → QRIS/bank/e-wallet (≤24h)
                        ▲
   dashboard status change ┘ → auto WA notify customer (≤24h)
```

**Separation of concerns:** the AI service owns the models (LLM **and**
embeddings). The backend owns the data (products, orders, payment config),
the cheap cosine math, and all outbound orchestration. The prompt sent to
the AI is always lean because the backend retrieves the relevant subset
before calling it.

---

## B1 — Hybrid catalog retrieval

### Problem

The prompt caps (20 / 30 / 15) silently drop everything past the cap. A
business with 200 SKUs effectively exposes ~10% of its catalog to the AI.

### Solution

The backend selects the top-k relevant products **before** calling the AI and
passes only those as the `catalog`. The AI service is unchanged in shape — it
still receives a `catalog` list, just a small, relevant one.

### Components

**1. Embeddings in the AI service** — `ai/embeddings.py`

- `embed_texts(texts: list[str]) -> list[list[float]]`. Mirrors the existing
  provider switch `settings.use_openai`: OpenAI-compatible
  (`text-embedding-3-small`) or Ollama (`nomic-embed-text`).
- New endpoint `POST /ai/embed` `{texts: [...]}` → `{vectors: [[float]]}`,
  gated by the existing `require_secret` dependency.
- On provider error: the endpoint returns HTTP 502; callers treat embeddings
  as unavailable and fall back to keyword-only (never crash).

**2. Stored product vectors** — `models.py`, `database.py`

- `Product` gains `embedding` (JSON list[float], null until computed) and
  `embedding_hash` (String, null until computed). Added idempotently through
  `_run_migrations` (`ALTER TABLE products ADD COLUMN`), same pattern as
  Phase A.
- The embedding text is `f"{name}. {description or ''}"`. The hash is a
  SHA-256 of that text. On product create/update the backend recomputes the
  embedding **only when the hash changed** (no-op on unrelated edits).
- Embedding failure is non-blocking: store nulls, log, proceed. The product
  is still found by keyword; its vector is filled on a later edit/backfill.

**3. Retrieval** — `backend/services/retrieval.py`

- `select_relevant_products(session, business_id, message, k=12) -> list[dict]`
  returning `[{name, price, stock?, description?}]` ready for the AI `catalog`.
- **Keyword first:** score each product by substring hits of the message's
  words against `name` (weight 3) and `description` (weight 1). (`category`
  is not a `Product` column — name + description only.) Rank by score.
- **Strong keyword → skip embeddings:** if keyword yields ≥ k products with a
  positive score, use the top-k and make no embedding call (saves latency).
- **Weak/empty keyword → embedding fallback:** embed the message via
  `/ai/embed`, cosine-similarity (brute force, pure Python) against stored
  product vectors, take top-k. Hundreds of products per business make brute
  force trivial — no vector database.
- **Fuse when both contribute:** simple Reciprocal Rank Fusion of the keyword
  ranking and the embedding ranking, dedup by product id, truncate to k.
- **Small catalog short-circuit:** if the business has ≤ k products, return
  all of them and skip retrieval entirely (no regression for small warungs).

**4. Lean prompt** — `ai/conversation.py`

- The hardcoded caps (`[:20]`, `[:30]`, `[:15]`) are removed; the AI uses the
  full `catalog` it is given, which is already the lean retrieved subset. The
  menu reply still elides a long list with "… dan N menu lainnya" when the
  retrieved subset itself is long.

### Edge cases

- AI service down / `/ai/embed` 502 → keyword-only retrieval; the bot keeps
  working with reduced recall.
- New product not yet embedded → found by keyword now, embedded on next edit
  or backfill.
- Catalog ≤ k → all products pass through; retrieval is skipped.

### Testing

- Keyword selects the correct subset from a 200-product catalog.
- Embedding fallback returns relevant products when keyword is empty
  (synonym / paraphrase), using a stubbed `/ai/embed`.
- Small catalog (≤ k) returns all products and makes no embedding call.
- `/ai/embed` failure → keyword-only path, no exception.
- `embedding_hash` unchanged → no recompute; changed → recompute.

---

## B2 — Order pipeline, payments, sync

### 1. Order finalisation (LLM = source of truth)

- The multi-turn order-state stays in `conversation.py` (existing close
  detection: "itu aja / cukup / selesai / …").
- When close is detected inside `/ai/reply`, the AI service runs
  `extract_order_from_chat(history, catalog)` (existing LLM extraction) and
  returns the result on a new `ReplyResponse.order` field:
  `{items: [{name, qty, price}], total, status: "closed"}`. On non-closing
  turns `order` is `null`.
- The mid-chat running summary built by `OrderState` is a **preview only**,
  labelled "(sementara)"; the authoritative order is the LLM extraction at
  close.
- Backend `_process_tenant_messages` reads `reply_resp.order`. When
  `status == "closed"`, it persists the order (see update-or-create below).
  The old per-message `extract_order_from_message` create path is removed;
  the regex remains as a **fallback** used only when `reply_resp.order` is
  null but the conversation clearly closed an order (e.g. AI service
  unavailable).

### 2. Order amendment (customer changes their mind)

- **Mid-chat:** handled for free by LLM-at-close — the extraction reads the
  whole transcript, so "gak jadi 2, 1 aja" or "ganti es teh jadi es jeruk"
  resolves to the correct final order. The rule-based running summary may be
  wrong mid-conversation (it only adds/increments); the "(sementara)" label
  sets that expectation and the close corrects it.
- **Post-final:** the in-memory `conv.order` (keyed by phone) survives after
  close. An order-related message after close reactivates it
  (`conv.order.active = True`); the next close re-extracts the full transcript
  and returns `ReplyResponse.order` again.
- **Backend update-or-create:** on receiving a closed `order`, the backend
  looks for the customer's most recent **non-terminal** order (status
  `pending` or `confirmed`, created within the last 6 hours). If found, it
  **updates** that order's items/total, recomputes stats, and re-sends payment
  with the new total. Otherwise it creates a new order.
- **Guard:** an order already `completed` or `cancelled` is never amended; a
  later change becomes a new order.

### 3. Payment delivery

- `Business` gains `payment_methods` (JSON `[{type, label, value}]`, where
  `type` ∈ `qris | rekening | ewallet`) and `qris_image_url` (String), added
  via `_run_migrations`.
- `backend/services/payment.py`:
  - `format_payment_text(business, total) -> str` — order total plus each
    configured method, e.g. `BCA 1234567890 a.n. Budi`, `GoPay 0812…`.
  - `send_payment_info(session, business, customer, order) -> bool` — sends
    the payment text over WhatsApp, then (if `qris_image_url` is set) an image
    message by link. Gated on the 24-hour window. Returns whether anything was
    sent.
- **Three entry points:**
  1. **Auto** — after an order is finalised in `_process_tenant_messages`
     (typically inside the window).
  2. **Dashboard** — `POST /api/orders/{id}/send-payment` (owner button).
  3. **On demand** — a "cara bayar?" message yields NLU intent
     `INQUIRY_PAYMENT`; the backend calls `send_payment_info`.
- **No methods configured** → skip sending payment details and reply asking
  the owner to set them up in Settings; never send an empty payment message.

### 4. Dashboard → WhatsApp status sync

- Hook into the existing `PATCH /api/orders/{id}` handler
  (`main.py:836`, right after `order.status = db_status`).
- Status → message map: `diproses` → "Pesanan kakak lagi disiapkan ya 🙏",
  `selesai` → "Pesanan kakak sudah selesai! Terima kasih 😊",
  `dibatalkan` → "Mohon maaf, pesanan kakak dibatalkan." Statuses without a
  mapped message send nothing.
- The notification is sent only within the 24-hour window; outside it, the
  status still updates in the DB and the send is skipped and logged.

### 5. WhatsApp 24-hour window helper

- `backend/services/whatsapp.py` gains
  `within_service_window(session, customer_id) -> bool`: find the customer's
  most recent **inbound** `Message`; return `now - timestamp <= 24h`. No
  inbound message → `False`.
- Used by payment auto-send/re-send and by status notifications.
- `services/whatsapp.py` also gains an image-by-link send (WhatsApp Cloud API
  `type: "image"`, `image.link`) for the QRIS image.

### QRIS image — decision

- v1: the owner pastes a **public https URL** of their QRIS image in
  Settings; WhatsApp sends it by link. File upload (backend-hosted media) is a
  later enhancement, not Phase B.

### Testing

- Close signal → LLM extract → exactly one order persisted; LLM unavailable →
  regex fallback persists a sane order.
- Amendment: a post-close change updates the existing non-terminal order
  rather than creating a new one; a `completed` order is not amended.
- `format_payment_text` renders each method; `send_payment_info` sends the
  image only when `qris_image_url` is set, and skips entirely when no methods
  are configured.
- All three payment entry points send (mocked `send_message`), each gated on
  the window.
- Status change within the window sends the mapped WA message; outside the
  window it skips and logs; an unmapped status sends nothing.
- `within_service_window` is correct at the 24-hour boundary and when there is
  no inbound message.

---

## Data model — new columns

| Table | Column | Type | Default | Meaning |
|---|---|---|---|---|
| products | `embedding` | JSON list[float], null | — | Cached product vector |
| products | `embedding_hash` | String, null | — | SHA-256 of name+desc; recompute trigger |
| businesses | `payment_methods` | JSON list | `[]` | `[{type, label, value}]` |
| businesses | `qris_image_url` | String, null | — | Public https URL of QRIS image |

All added idempotently in `database.py` `_run_migrations`
(`inspect` + `ALTER TABLE … ADD COLUMN`), the same mechanism Phase A used.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/ai/embed` | texts → vectors (AI service, secret-gated) |
| POST | `/api/orders/{id}/send-payment` | Owner re-sends payment info |
| PATCH | `/api/business` (extend) | Persist `payment_methods` + `qris_image_url` |

Schemas: `EmbedRequest`/`EmbedResponse` (AI service); `PaymentMethod`,
extended business update, `SendPaymentResponse` (backend). All backend
handlers stay scoped via `get_current_business`; cross-tenant access on an
order → 404, consistent with existing endpoints.

## Dashboard

- **Settings:** a payment-methods editor (add/remove `{type, label, value}`
  rows) and a QRIS image URL field, persisted through the existing
  `PATCH /api/business`.
- **Orders:** a "Kirim info bayar" button per order
  (`POST /api/orders/{id}/send-payment`). Status changes already exist and
  now also notify the customer over WhatsApp (backend-side).
- **Products:** no new UI — embeddings are computed automatically on save.
- Frontend plumbing: `lib/api.ts`, `lib/queries.ts`, `lib/types.ts` gain the
  payment + send-payment methods/hooks/types. Uses the existing design system.

## File map

**AI service:** `ai/embeddings.py` (new), `ai/ai_service.py`
(`/ai/embed`, `ReplyResponse.order`), `ai/conversation.py` (close → extract →
`order`, reopen/amendment, "(sementara)" label, drop caps), `ai/nlu.py`
(`INQUIRY_PAYMENT` intent).

**Backend:** `services/retrieval.py` (new), `services/payment.py` (new),
`services/whatsapp.py` (`within_service_window`, image-by-link send),
`main.py` (retrieval before reply, order update-or-create, payment three
triggers, status → WA notify, `/send-payment` endpoint), `models.py`
(4 columns), `database.py` (migrations), `schemas.py` (payment, send-payment).

**Dashboard:** `pages/Settings.tsx` (payment editor), `pages/Orders.tsx`
(payment button), `lib/api.ts`, `lib/queries.ts`, `lib/types.ts`.

## Out of scope (flagged, not Phase B)

- Approved Meta templates for messaging outside the 24-hour window (payment
  reminders, status updates a day later).
- Dynamic QRIS with amount embedded / payment-gateway integration
  (Midtrans / Xendit), merchant KYC, transaction fees.
- Backend-hosted QRIS image upload (v1 uses a pasted public URL).
- Per-business retrieval tuning (k, weights) — fixed defaults for now.
- Phase C (service businesses: salon, wedding, bookings).
