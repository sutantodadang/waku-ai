# Phase C — Service Businesses & Bookings

Status: Design approved · Date: 2026-06-22 · Owner: sutantodadang

## Context

Waku is a multi-tenant WhatsApp assistant for Indonesian UMKM. Phase A
(Kenal Langganan) added customer recognition; Phase B (large catalogs, LLM
orders, payments) made the AI's structured order the source of truth and
added payment delivery. Phase C broadens Waku from product-selling warungs
to **service businesses** — salons (appointments with staff) and wedding
services (event bookings with a deposit).

This is the conceptual shift the Phase A roadmap anticipated: it needs a
`business_type` field and a `Booking` model. Phase C is one combined spec
covering both service types because they share the booking pipeline, but
their booking mechanics differ (salon = date+time slot with staff; wedding =
event date + package + deposit).

Phase C **depends on Phase B** (PR #11): it reuses the catalog retrieval,
the payment delivery service (`send_payment_info`), the 24-hour window gate
(`within_service_window`), and the dashboard→WhatsApp status-sync pattern.
Its implementation branch starts from the Phase B branch.

### Current state (what exists)

- `Business` has no `business_type`. `Order` (product items + total + status)
  and the per-message order flow are warung-specific. `Product` has
  name/price/description/embedding (Phase B retrieval).
- NLU intents: GREETING, ORDER, INQUIRY_PRICE/STOCK, COMPLAINT, PAYMENT,
  CLOSING — no booking/appointment intent.
- Payment (`services/payment.py`), the 24h window (`within_service_window`),
  and status→WA notifications (in `PATCH /api/orders/{id}`) all exist from
  Phase B and are reused here.

## Goals

1. A business can declare its type (warung / salon / wedding); the type
   drives both the AI conversation flow and the dashboard, with **zero
   regression** for existing warungs (default `warung`).
2. A salon customer can request an appointment (service + date/time +
   optional staff) over WhatsApp; the AI does a rough clash check and records
   the request; the owner confirms.
3. A wedding customer can request an event booking (package + event date);
   the owner confirms; a deposit can be requested.
4. On owner confirmation, the customer is notified over WhatsApp and sent
   payment info (deposit or total) — all within the 24h window.
5. The owner manages bookings, staff, and service durations from the
   dashboard, and can manually remind a customer of an upcoming booking.

### Hard constraint: WhatsApp 24-hour window

As in Phase A/B, free-form outbound messages are only allowed within 24 hours
of the customer's last inbound message. Booking confirmation notifications,
status notifications, payment sends, and the manual reminder are all gated on
`within_service_window`; outside it they skip and log. **Automatic** reminders
(e.g. day-before) would require an approved Meta template and a scheduler —
out of scope. The reminder here is **dashboard-only and manual** (an owner
button that sends only if the customer is still within the window).

## Architecture

```
business_type (Business) ── drives ──► AI flow + dashboard nav/labels
   warung  → product order flow (Phase A/B, unchanged)
   salon   → booking flow: service + date/time + staff, rough clash check
   wedding → booking flow: package + event date + deposit

customer chat ──► [retrieval Phase B] relevant services/packages
                      ▼  multi-turn booking flow
                LLM extract at close → ReplyResponse.booking
                      ▼
   backend: resolve staff → create Booking (status "requested")
                      ▼
   owner confirms in dashboard ──► WA notify customer + send payment/DP (24h-gated)
```

**Separation of concerns:** `business_type` is the single switch that routes
the AI flow and the dashboard. Salon/wedding share the `Booking` model and the
booking endpoints; their differences (staff + clash for salon, deposit for
wedding) are fields and small branches, not separate subsystems. Everything
product/order stays exactly as Phase B left it.

## Data model

Added idempotently in `database._run_migrations` (`inspect` + `ALTER TABLE …
ADD COLUMN`; `create_all` builds the new tables), the same pattern as
Phase A/B.

### New columns on existing tables

| Table | Column | Type | Default | Meaning |
|---|---|---|---|---|
| businesses | `business_type` | String(16) | `'warung'` | `warung` \| `salon` \| `wedding` |
| products | `duration_minutes` | Int, null | — | Salon service duration; null for wedding/warung |

### New table: `staff` (salon multi-staff)

| Column | Type | Meaning |
|---|---|---|
| `id` | Int PK | |
| `business_id` | Int FK | owner |
| `name` | String(255) | staff display name |
| `active` | Bool, default True | inactive staff are hidden from new bookings |

### New table: `bookings`

| Column | Type | Meaning |
|---|---|---|
| `id` | Int PK | |
| `business_id` | Int FK | |
| `customer_id` | Int FK | |
| `staff_id` | Int FK, null | salon assigned staff; null = "any staff" / wedding |
| `items` | JSON | `[{name, price, duration_minutes}]` services/packages |
| `total` | Float, default 0 | sum of item prices |
| `deposit_amount` | Float, null | wedding DP; null/0 = pay full / on-site |
| `scheduled_at` | DateTime, null | salon slot start; wedding event date |
| `duration_minutes` | Int, null | salon total duration (Σ item durations); used for clash |
| `status` | String(16), default `'requested'` | requested → confirmed/rejected → completed/cancelled |
| `notes` | Text, null | special requests |
| `created_at` | DateTime | |

`Booking` is intentionally distinct from `Order` (it needs `scheduled_at` +
`staff` + clash semantics). `Product` is reused as the catalog item for all
business types (so services/packages get Phase B retrieval, embedding, and
the catalog UI for free); only `duration_minutes` is added.

**Booking status lifecycle:** `requested` (created by the AI on the customer's
behalf) → owner sets `confirmed` or `rejected` → `completed` or `cancelled`.
Terminal states (`completed`, `cancelled`, `rejected`) cannot be re-confirmed.

## AI conversation flow

### Routing by business_type

- `ReplyRequest` gains `business_type: Optional[str]`. The backend sends
  `business.business_type`.
- `conversation.generate_reply`: `warung` → the existing order flow
  (unchanged). `salon` / `wedding` → the booking flow.

### NLU

- New intent `BOOKING` (patterns: "booking", "janji", "reservasi", "jadwal",
  "kapan bisa", "tanggal", "jam", "reservasi"). Existing `INQUIRY_PRICE` and
  `PAYMENT` are reused.

### Booking flow (multi-turn, mirrors the order flow)

1. Customer asks for a service → Phase B retrieval surfaces relevant
   services/packages → the AI lists them (name, price; plus duration for
   salon).
2. Customer picks one or more + states a time (salon: date+time; wedding:
   event date) + optional staff ("sama mbak Sari" / "siapa aja").
3. **Rough clash check (salon):** the AI looks at the chosen staff's
   `confirmed` bookings overlapping the requested window; if it looks full it
   warns ("jam itu sepertinya sudah terisi Kak, mau jam lain?") but **still
   proceeds** — the owner is the final authority (hybrid).
4. On a closing signal → **LLM extract at close** (mirrors the Phase B order
   extraction) → the final booking.
5. The AI replies: "Permintaan booking dicatat ya Kak, menunggu konfirmasi
   pemilik. Nanti Waku kabari 🙏". The booking is persisted with status
   `requested`.

### LLM extract — `extract_booking_from_chat`

The hardest part is parsing Indonesian dates/times ("besok jam 2", "sabtu
depan", "tanggal 15 jam 10"). The LLM extracts a structured result:

```json
{
  "items": [{"name": "Facial", "price": 80000, "duration_minutes": 60}],
  "scheduled_at": "2026-06-25T14:00:00",
  "staff_name": "Sari",
  "deposit_amount": null,
  "notes": "kulit sensitif",
  "status": "closed"
}
```

- `ReplyResponse` gains `booking: Optional[dict]` (parallel to Phase B's
  `order`); null on non-closing turns.
- **Ambiguity guardrail:** if the date/time is unclear, the AI asks to
  clarify ("Untuk tanggal berapa ya Kak?") and does NOT create a booking. It
  must never invent a date.
- The owner can edit `scheduled_at` in the dashboard — the safety net for a
  mis-parse.
- Composes with the existing anti-fabrication + prompt-injection guardrails:
  an off-catalog service is refused and the real menu shown.

## Backend

### `backend/services/booking_service.py` (new)

- `create_booking(session, business_id, customer_id, items, scheduled_at,
  staff_id, total, deposit_amount, notes) -> Booking` — status `requested`.
- `check_booking_clash(session, business_id, staff_id, scheduled_at,
  duration_minutes) -> list[Booking]` — `confirmed` bookings whose
  `[scheduled_at, scheduled_at + duration)` window overlaps the requested
  one, for that staff. When `staff_id` is null ("any staff"), it counts
  overlapping confirmed bookings across all active staff and reports a clash
  only when they meet or exceed the active-staff count (rough capacity
  check). Used for the AI warning and the dashboard clash badge.
- `resolve_staff(session, business_id, staff_name) -> Optional[int]` —
  case-insensitive name match among active staff; null when not found or
  "siapa aja".

Reuses Phase B: `within_service_window`, `send_payment_info`, `send_message`.

### Endpoints (all scoped via `get_current_business`; cross-tenant → 404)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/bookings` | list (filters `?status=`, `?date=`); each row carries a clash flag |
| PATCH | `/api/bookings/{id}` | change status and/or edit `scheduled_at` / `staff_id` |
| POST | `/api/bookings/{id}/remind` | manual reminder (24h-gated) |
| POST | `/api/bookings/{id}/send-payment` | send payment / deposit (reuse Phase B) |
| GET/POST/DELETE | `/api/staff` | manage staff (salon) |
| PATCH | `/api/business` (extend) | set `business_type` |
| product create/update (extend) | accept `duration_minutes` |

### Booking → WhatsApp status sync (mirrors Phase B order status sync)

`PATCH /api/bookings/{id}` status change notifies the customer (24h-gated):

- `confirmed` → "Booking kakak tanggal {tgl} jam {jam} sudah dikonfirmasi ✅"
  **and auto-sends payment** (`deposit_amount` set → DP, else `total`).
- `rejected` → "Mohon maaf, jadwal yang diminta belum bisa. Boleh pilih waktu
  lain Kak?"
- `completed` → "Terima kasih sudah datang ke {toko} ya Kak 😊".
- `cancelled` → "Booking kakak dibatalkan."

### Reminder (dashboard-only, manual)

`POST /api/bookings/{id}/remind` sends "Halo Kak, pengingat booking besok jam
{jam} ya 🙏" — only when `within_service_window` is true; otherwise returns
`{sent: false}` (the owner reminds by other means). The dashboard flags
next-day bookings and shows a "Ingatkan" button.

### Booking persist from the AI (in `_process_tenant_messages`)

- `business_type` salon/wedding AND `ReplyResponse.booking` status closed →
  `resolve_staff(staff_name)` → `create_booking` (status `requested`). No
  payment is sent (it waits for owner confirmation).
- `business_type` warung → the existing Phase B order path, unchanged.

## Dashboard

### Type-aware nav + labels

- `business_type` drives the nav and vocabulary: `warung` → **Pesanan**
  (Orders, existing); `salon` / `wedding` → **Booking** (new page) takes that
  slot. Catalog label adapts: warung "Produk", salon "Layanan", wedding
  "Paket".

### Settings

- A `business_type` selector (warung / salon / wedding).
- A **staff manager** (shown only for salon): add / remove / toggle-active
  staff.
- Reuses the Phase B payment-methods editor (deposit is per-booking via
  `deposit_amount`, not a settings field).

### Catalog (Products page, extended)

- A `duration_minutes` field, shown only for salon (minutes); hidden for
  wedding/warung.

### Bookings page (new)

- A **"Besok"** section at the top: next-day bookings with an **"Ingatkan"**
  button (24h-gated).
- A booking list: customer, service/package, `scheduled_at`, staff, status,
  and a **clash badge** when `check_booking_clash` finds an overlap.
- Per-booking actions: **Konfirmasi / Tolak** (requested), **Selesai /
  Batal** (confirmed), **Kirim bayar/DP**, and edit `scheduled_at` + staff.
- Status changes trigger the WA notification (backend).

### Plumbing

`lib/types.ts`, `lib/api.ts`, `lib/queries.ts`: Booking, Staff,
`business_type`. Reuses the Phase B design system (Card / Button / Field).

## Error handling & edge cases

- **business_type warung** → the booking code path is skipped entirely; the
  order flow is byte-for-byte unchanged (regression-proof).
- **Ambiguous date** → the AI asks to clarify and does not create a booking.
- **Staff not found / "siapa aja"** → `staff_id` null; the owner assigns in
  the dashboard.
- **Clash** → AI warning + dashboard badge, but the booking still becomes
  `requested`; confirming over a clash is the owner's decision (hybrid).
- **Outside the 24h window** → all notifications / reminders / payment sends
  skip and log (reuse Phase B).
- **Terminal booking** (completed / cancelled / rejected) → cannot be
  re-confirmed.

## Testing

- **`booking_service`:** create; clash overlap (per-staff; "any staff"
  capacity); `resolve_staff` match/miss; no clash when staff or time differ.
- **Endpoints:** bookings list/patch scoped; cross-tenant → 404; status → WA
  notify (24h-gated); confirm → payment (with deposit vs total); remind
  window-gated; staff CRUD.
- **AI:** business_type routing (warung does NOT enter the booking flow);
  `extract_booking_from_chat` shape; ambiguous date → clarify (no booking);
  off-catalog service refused.
- **Migration:** new columns/tables added idempotently; existing businesses
  default to `warung`.
- **Frontend:** tsc + build; type-aware nav renders the right page per type.

## Out of scope (flagged, not Phase C)

- Automatic reminders + Meta message templates (dashboard-manual only here).
- Multi-type businesses (one type per business).
- Visual calendar / drag-drop scheduling (a list first).
- Recurring bookings; detailed per-staff working hours.
- Online payment gateway (reuse Phase B manual payment).
