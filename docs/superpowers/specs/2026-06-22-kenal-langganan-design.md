# Kenal Langganan — Customer Recognition (Phase A)

Status: Design approved · Date: 2026-06-22 · Owner: sutantodadang

## Context

Waku is a multi-tenant WhatsApp assistant for Indonesian UMKM. Today the AI
treats every customer as a stranger: it reads the catalog and the current
message, but has no memory of who it's talking to. The owner wants the bot to
feel like it *knows the regulars* — greet by name, recall the usual order, note
preferences (no chili, shrimp allergy), and recognise loyal customers.

This is **Phase A** of a three-phase roadmap to broaden Waku beyond food
warungs:

- **Phase A — Kenal Langganan (this spec):** customer recognition. Cross-cutting,
  benefits every business type, uses data already in the DB.
- **Phase B — Large catalogs:** product retrieval so the AI handles hundreds of
  SKUs without flooding the prompt. Own spec.
- **Phase C — Service businesses (salon, wedding):** services + bookings /
  appointments. Needs a `business_type` field and a `Booking` model. Own spec.

Phase A is independent and ships first.

## Goal

When a returning customer messages a connected business, the AI personalises its
reply from that customer's history and the owner's notes; and the owner gets a
**Pelanggan** page to see and manage customers.

Four behaviours (all in scope):

1. **Greet by name + usual order** — "Halo Kak Budi! Nasi goreng 2 seperti biasa?"
2. **Reorder hint (reactive)** — within a conversation, if the customer is overdue
   versus their normal cadence, the AI may nudge ("sudah waktunya restock galon?").
3. **Loyalty status** — count orders / spend; mark `langganan` past a threshold.
4. **Notes & preferences** — owner (and later AI) stores per-customer notes/tags
   the AI uses in later replies.

### Hard constraint: WhatsApp 24-hour window

WhatsApp does not allow unsolicited free-form messages outside the 24-hour
customer-service window. So the **reorder hint is reactive** — it appears only
when the customer messages first. Proactive reorder *push* (approved Meta
template + opt-in) is a separate, later feature, **out of scope** for Phase A.

## Architecture: cached profile (write-time full recompute)

Customer statistics are denormalised onto the `customers` row for fast reads by
both the AI path and the dashboard. To avoid the usual cache-invalidation
pitfalls, stats are **fully recomputed from orders on every write** (order
created or status changed) by a single function — cheap, since a customer has
few orders, and there is exactly one place that can make the cache wrong.

```
order created / status changed
        │
        ▼
recompute_customer_stats(session, customer_id)   ← single source of truth
        │  writes cached columns
        ▼
customers row (cache) ──► read by AI reply path  ("kartu pelanggan")
                      └─► read by dashboard       (Pelanggan page)
```

## Data model — new `customers` columns

Added idempotently via the existing `_run_migrations` mechanism in
`database.py` (`inspect` + `ALTER TABLE customers ADD COLUMN`), the same pattern
already used for `businesses`.

| Column | Type | Default | Meaning |
|---|---|---|---|
| `notes` | Text, null | — | Owner free-form note |
| `tags` | JSON list[str] | `[]` | Preferences, e.g. `["alergi udang","tanpa pedas"]` |
| `is_regular_override` | Bool, null | — | Owner manually marks as langganan |
| `order_count` | Int | `0` | Cache: non-cancelled order count |
| `total_spent` | Float | `0` | Cache: sum of non-cancelled order totals |
| `last_order_at` | DateTime, null | — | Cache: most recent order time |
| `top_items` | JSON list | `[]` | Cache: `[{name, count}]`, top 3 by quantity |
| `avg_cadence_days` | Float, null | — | Cache: mean gap between orders (≥2 orders) |
| `stats_updated_at` | DateTime, null | — | Cache: last recompute time |

**Loyalty status** is derived, not stored:
`is_regular = is_regular_override is True or order_count >= REGULAR_THRESHOLD`,
where `REGULAR_THRESHOLD = 5` is a module constant (per-business threshold is a
later enhancement, YAGNI now).

**Bounds:** `tags` capped at 10 entries, each ≤ 60 chars; `notes` ≤ 1000 chars.
Keeps the prompt small and the UI sane.

## Components

### 1. `recompute_customer_stats(session, customer_id)` — `services/order_service.py`

- Load the customer's **non-cancelled** orders (`status != "cancelled"`).
- `order_count` = count; `total_spent` = Σ total; `last_order_at` = max created_at.
- `top_items` = aggregate item names across orders' `items` JSON, summed by
  quantity, top 3 as `[{name, count}]`.
- `avg_cadence_days` = mean of gaps between consecutive order dates when ≥2
  orders, else null.
- Write all cached columns + `stats_updated_at`.
- Called after `create_order` and after an order status change (PATCH
  `/api/orders/{id}`). Wrapped so a recompute failure logs and never blocks the
  order write or the customer reply.

### 2. AI personalisation — "kartu pelanggan"

- Backend `_generate_ai_reply` builds a compact `customer` dict from the cached
  columns + name + notes/tags and adds it to the `/ai/reply` payload.
- AI service `ReplyRequest` gains `customer: Optional[dict] = None`. The reply
  prompt (`_llm_reply`, and the order-flow greeting) renders it as:

  ```
  PELANGGAN:
  - Nama: Budi (langganan, 8 order)
  - Biasa pesan: Nasi Goreng, Es Teh
  - Terakhir: 3 hari lalu (biasanya tiap ~5 hari)
  - Catatan: tanpa pedas; alergi udang
  ```

- **Personalisation guardrail:** include only fields that exist. A new/unknown
  customer (`order_count == 0`, or `name` equals the phone number) gets an empty
  card and today's behaviour — the AI must not fabricate a name, a usual order,
  or a cadence. The reorder hint is included only when `avg_cadence_days` is
  known and `now > last_order_at + avg_cadence_days`. Composes with the existing
  catalog and prompt-injection guardrails.

### 3. Dashboard — Pelanggan page

- New route `/customers` + a nav entry. Bottom nav stays **5 items**: "Koneksi"
  moves into Settings (it's one-time setup, rarely revisited) and "Pelanggan"
  takes its slot.
- **List:** customers sorted by `last_order_at` desc. Row: name, loyalty badge
  (langganan / baru), `order_count`, `total_spent`, relative last-order time.
- **Detail:** profile with stats, favourite items (chips), recent order history,
  an editable notes textarea, tag chips (add/remove), and a "Tandai langganan"
  override toggle.
- Uses the existing redesigned design system (Card, ink total, etc.).

### 4. Endpoints — `main.py`, scoped via `get_current_business`

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/customers` | List with cached stats |
| GET | `/api/customers/{id}` | Detail + recent orders |
| PATCH | `/api/customers/{id}` | Update `notes`, `tags`, `is_regular_override` |

Schemas: `CustomerResponse`, `CustomerDetailResponse`, `CustomerUpdate`.
Every handler checks `customer.business_id == business.id` and returns 404
otherwise (tenant isolation, consistent with existing endpoints).

Frontend: `api.ts` methods, `queries.ts` hooks (`useCustomers`, `useCustomer`,
`useUpdateCustomer`), `types.ts` types.

## Error handling & edge cases

- **New customer, no history:** empty personalisation; AI behaves as today.
- **Name unknown (== phone number):** do not greet with the phone number; stay
  neutral.
- **Cancelled orders:** excluded from all stats.
- **Tags/notes bounds:** enforced on PATCH (reject over-limit) to prevent prompt
  bloat.
- **Cross-tenant access:** PATCH/GET on another business's customer → 404.
- **Recompute failure:** logged; never blocks the order write or the reply.

## Testing

- **Unit:** `recompute_customer_stats` — counts, total, `top_items`, cadence,
  cancelled-excluded, single-order (cadence null).
- **API:** GET/PATCH `/api/customers` scoped to the business; cross-tenant → 404;
  tag/notes bound validation.
- **AI:** customer card built correctly from stats; empty for a new customer;
  reorder hint only when overdue; no fabrication when data is missing.

## Out of scope (flagged, not Phase A)

- Proactive reorder **push** (Meta template + opt-in).
- Automated loyalty discounts / rewards.
- Per-business loyalty threshold (constant `5` for now).
- Phase B (catalog retrieval) and Phase C (services / bookings).
