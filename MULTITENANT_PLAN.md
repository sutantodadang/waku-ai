# Waku — Multi-Tenant SaaS Refactor Plan

Status: Scope A DONE + tested · Scope B skeleton in place. Owner: dadangsutanto. Date: 2026-06-20.

Turns a single-tenant WhatsApp auto-reply into a multi-tenant SaaS where each
UMKM connects its own WhatsApp number, logs into its own dashboard, and gets
AI auto-replies scoped to its own catalog and orders.

---

## 1. Mental model — 3 layers, 2 cost meters

| Layer | Owner | Role | Cost |
|-------|-------|------|------|
| WhatsApp Cloud API | Meta | transport (receive/send) | service msg (reply within 24h) FREE, 1000/mo · templates paid |
| AI reply | us (OpenAI/Ollama) | generate reply text | gpt-4o-mini paid-per-token (cheap) · Ollama local free |
| reverse-OTP | us (plain code) | match a login code | free, no AI |

Meta does not know or care that a reply came from AI — to Meta it is a normal
text body = service message = free within the 24h window. The LLM token cost is
a **separate meter** (OpenAI), not Meta's.

---

## 2. Two distinct "logins" (do not conflate)

1. **Dashboard auth** — UMKM owner signs into the Streamlit dashboard.
   - Primary: email + password (bcrypt). Free, full control.
   - Optional: reverse-OTP — owner sends a code FROM their WhatsApp TO the
     platform number (user-initiated service message = free). Proves they
     control the number; does NOT grant a send token.
2. **Connect WhatsApp** — UMKM links their own WhatsApp Business number so we
   can send on their behalf. ONLY obtainable via **Embedded Signup** (Meta
   OAuth) → yields `waba_id` + `phone_number_id` + `access_token`. reverse-OTP
   is NOT sufficient here.

---

## 3. Data model changes

### New: `users`
`id, email (unique), password_hash, business_id (FK), created_at`

### New: `otp_verifications`
`id, phone_number, code, purpose (login|connect), expires_at, consumed, created_at`

Security hardening: `/otp/verify` requires the `code` (not just the phone),
checks `expires_at`, and DELETES the record on success (single-use, no replay).
The webhook only consumes a code when the WhatsApp sender matches the registered
phone. Phone matching is full E.164 (0→62 for ID), not last-N digits.

### Changed: `businesses`
- `phone_number` → keep as `display_phone` (human number, e.g. 0812...).
- add `phone_number_id` (Meta routing id; webhook resolves business by this).
- add `waba_id` (WhatsApp Business Account id).
- add `access_token` (Meta send token, **encrypted at rest** via Fernet).
- add `owner_id` (FK users) — optional, mirrors users.business_id.
- add `is_connected` (bool; true once Embedded Signup completes).

Token at rest: `backend/crypto.py` Fernet `EncryptedString` TypeDecorator,
key from env `TOKEN_ENCRYPTION_KEY`. No plaintext tokens in DB.

### Migration (SQLite)
`create_all` makes the new `users`/`otp_verifications` tables, but will NOT add
columns to an existing `businesses` table. `database.py::_run_migrations()` runs
idempotent `PRAGMA table_info` + `ALTER TABLE businesses ADD COLUMN ...` so
existing `waku.db` keeps its data. Called from `init_db()`.

---

## 4. Webhook routing (multi-tenant)

`POST /webhook` resolves the target by `value.metadata.phone_number_id`:

1. If `phone_number_id == PLATFORM_PHONE_NUMBER_ID` (our own platform number)
   → this is a **system channel** message → check pending reverse-OTP; verify if
   it matches. **Never** route OTP/system messages to the LLM.
2. Else look up `Business` by `phone_number_id`.
   - found → customer message → AI auto-reply scoped to that business
     (its catalog + business_context), send via that business's `access_token`.
   - not found → ignore (drop the `_get_default_business` "first business"
     fallback — it leaks tenants together).

Sending: `services/whatsapp.send_message(to, body, *, phone_number_id, access_token)`
uses the per-business credentials, not the global env.

---

## 5. AI reply wiring fix (current bug)

- `backend/main.py` posts to `AI_SERVICE_URL + "/chat"` with
  `{business_id, customer_id, message}` — but the AI service exposes
  **`/ai/reply`** expecting
  `{incoming_message, business_context, message_history, catalog, session_id}`
  and returns `{reply, intent, ...}`. Result today: AI never fires, always
  rule-based fallback.
- Fix: POST `/ai/reply` with `incoming_message=text`,
  `session_id=customer phone`, `business_context={store_name, owner_name}`,
  `catalog=[{name, price, stock}]` from the business's products,
  `message_history=` recent messages. Read `data["reply"]`.

## 6. Other contract bugs found (fix in passing)
- `services/whatsapp.py` reads env `PHONE_NUMBER_ID`, but `.env.example`
  defines `WHATSAPP_PHONE_NUMBER_ID` → global send was always unconfigured.
- Dashboard wizard posts `{name, phone}` to `/api/business/register`, which
  expects `{business_name, phone_number}` → registration silently failed.

---

## 7. Scope split

### A — build now (no Meta approval)
1. crypto.py + auth.py (bcrypt, JWT, Fernet).
2. models.py + migration (User, OTP, Business columns).
3. Auth endpoints: register, login (email+pass), reverse-OTP request/verify.
4. JWT-scope every dashboard endpoint to the authenticated business; drop
   `_get_default_business`.
5. Webhook routing by `phone_number_id` + per-business send token + OTP channel.
6. Fix AI reply wiring + pass catalog & business_context.
7. Dashboard: login/register gate, JWT in api_client, fix register contract.

### B — skeleton now, live after Meta App Review
8. `GET /api/whatsapp/embedded-signup/callback` — exchange OAuth `code` for a
   long-lived/system-user token, store `waba_id`+`phone_number_id`+`access_token`
   on the business, set `is_connected=true`. Built but inert until App Review +
   Tech Provider + business verification are granted on Meta's side.

---

## 8. New env vars
Backend:
- `TOKEN_ENCRYPTION_KEY` — Fernet key (generate: `Fernet.generate_key()`).
- `JWT_SECRET` — HS256 signing secret.
- `PLATFORM_PHONE_NUMBER_ID` — our platform number id (reverse-OTP channel).
- `META_APP_ID`, `META_APP_SECRET`, `META_CONFIG_ID` — Embedded Signup (Scope B).

---

## 10. Tests

`backend/tests/` (pytest + pytest-asyncio). Run from `backend/`:
```
uv run pytest -q
```
Coverage: auth (register/login/guards), tenant isolation (no cross-tenant leak),
WhatsApp connect + token-encrypted-at-rest + signup-skeleton 501, reverse-OTP
security (no-code/wrong-code/replay/wrong-sender all blocked), webhook routing
(per-business send creds, unknown-tenant drop, order extraction), and the
idempotent SQLite migration. 24 tests.

## 9. Out of scope (note, do not build)
- Billing / template message sending UI.
- Multi-user-per-business (assume 1 owner per business for MVP).
- Conversation memory persistence across AI-service restarts (in-memory today).
