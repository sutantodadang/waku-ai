# Phase C — Service Businesses & Bookings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Waku serve salon (appointments + staff) and wedding (event + deposit) businesses with a WhatsApp booking flow, owner confirmation, and payment — with zero regression for product warungs.

**Architecture:** A `business_type` field on `Business` routes both the AI flow (order vs booking) and the dashboard. `Product` is reused as the service/package catalog (plus `duration_minutes`); new `Staff` + `Booking` tables hold appointments. The AI extracts the booking at conversation-close (`ReplyResponse.booking`, mirroring Phase B's `order`); the backend creates it `requested`; the owner confirms in the dashboard, which notifies the customer and sends payment. Reuses Phase B retrieval, payment, the 24h window, and the status→WA pattern.

**Tech Stack:** FastAPI (async) + SQLAlchemy (SQLite/aiosqlite); separate FastAPI AI service; React + TS + Vite dashboard. Branches from `feat/phase-b` (depends on Phase B).

## Global Constraints

- **business_type** ∈ `warung | salon | wedding`, column default `'warung'`; `warung` keeps the exact Phase A/B order flow (zero regression). `salon`/`wedding` use the booking flow.
- **Booking status lifecycle:** `requested → confirmed | rejected → completed | cancelled`. Terminal (`completed`/`cancelled`/`rejected`) cannot be re-confirmed.
- **24-hour window** is the only outbound gate (reuse `within_service_window`): booking confirm-notify, status notify, payment, and the manual reminder all skip+log outside it. No Meta templates (out of scope).
- **Hybrid availability:** the AI does a rough clash check and warns, but always records the booking `requested`; the owner is the final authority.
- **Ambiguity guardrail:** if the date/time is unclear the AI asks to clarify and does NOT create a booking — never invents a date.
- **Migrations:** idempotent in `database._run_migrations` (`ALTER TABLE` for new columns); new tables (`staff`, `bookings`) are built by `create_all`. SQLite only.
- **Tenant isolation:** every endpoint scoped via `get_current_business`; cross-tenant access → 404.
- **Reuse Phase B verbatim:** `select_relevant_products`, `send_payment_info`, `within_service_window`, `send_message`, the status→WA notify pattern. Do not duplicate them.
- **AI item key is `qty`; backend uses `quantity`** (same as Phase B) — normalize when persisting booking items that carry quantities. Booking items are `[{name, price, duration_minutes}]` (no qty in the common case).

---

## File Structure

**Backend**
- `models.py` — `Business.business_type`, `Product.duration_minutes`; new `Staff`, `Booking`.
- `database.py` — `_BUSINESS_TYPE_COLUMN`, `_PRODUCT_DURATION_COLUMN` migrations.
- `services/booking_service.py` (new) — `create_booking`, `check_booking_clash`, `resolve_staff`.
- `schemas.py` — `StaffCreate/Response`, `BookingResponse`, `BookingUpdate`, business_type + duration fields.
- `main.py` — staff CRUD, booking endpoints, booking status→WA + payment, remind, booking persist in `_process_tenant_messages`, `_generate_ai_reply` 4-tuple + business_type payload.

**AI service**
- `nlu.py` — `BOOKING` intent.
- `ai_service.py` — `ReplyRequest.business_type`, `ReplyResponse.booking`.
- `conversation.py` — booking flow routing, `extract_booking_from_chat`, `Conversation.closed_booking`.

**Dashboard**
- `lib/{types,api,queries}.ts` — Booking, Staff, business_type.
- `pages/Settings.tsx` — business_type selector + staff manager.
- `pages/Products.tsx` — `duration_minutes` field (salon).
- `pages/Bookings.tsx` (new) — booking list + tomorrow + actions + clash badge + remind.
- `components/BottomNav.tsx` — type-aware nav.

---

## Task 1: Migrations + Staff/Booking models

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/database.py`
- Test: `backend/tests/test_phase_c_migration.py` (new)

**Interfaces:**
- Produces: `Business.business_type` (default `"warung"`), `Product.duration_minutes` (Int null); `Staff(id, business_id, name, active)`; `Booking(id, business_id, customer_id, staff_id, items, total, deposit_amount, scheduled_at, duration_minutes, status, notes, created_at)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_phase_c_migration.py
"""Phase C columns + tables exist after init_db; existing businesses default to warung."""
import asyncio
from sqlalchemy import inspect


def test_phase_c_schema(client):
    import database

    async def _schema():
        async with database.engine.begin() as conn:
            return await conn.run_sync(lambda s: {
                "tables": set(inspect(s).get_table_names()),
                "businesses": {c["name"] for c in inspect(s).get_columns("businesses")},
                "products": {c["name"] for c in inspect(s).get_columns("products")},
            })

    s = asyncio.get_event_loop().run_until_complete(_schema())
    assert {"staff", "bookings"} <= s["tables"]
    assert "business_type" in s["businesses"]
    assert "duration_minutes" in s["products"]


def test_existing_business_defaults_to_warung(client):
    from helpers import register, auth
    t = register(client)
    r = client.get("/api/business", headers=auth(t["access_token"]))
    assert r.status_code == 200
    assert r.json()["business_type"] == "warung"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_phase_c_migration.py -v`
Expected: FAIL (tables/columns missing; `business_type` not in response).

- [ ] **Step 3: Add model columns + tables**

In `backend/models.py`, in `class Business` (after `qris_image_url`, before `created_at`):

```python
    business_type: Mapped[str] = mapped_column(String(16), default="warung", nullable=False)
```

In `class Product` (after `embedding_hash`, before `created_at`):

```python
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
```

At the end of the file add the two new tables:

```python
class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)
    staff_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("staff.id"))
    items: Mapped[list] = mapped_column(JSON, default=list)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    deposit_amount: Mapped[Optional[float]] = mapped_column(Float)
    scheduled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="requested", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
```

- [ ] **Step 4: Add the migrations**

In `backend/database.py`, after `_BUSINESS_PAYMENT_COLUMNS` add:

```python
_BUSINESS_TYPE_COLUMN: dict[str, str] = {
    "business_type": "VARCHAR(16) DEFAULT 'warung' NOT NULL",
}

_PRODUCT_DURATION_COLUMN: dict[str, str] = {
    "duration_minutes": "INTEGER",
}
```

In `_run_migrations`, after the businesses-payment block add:

```python
    for name, ddl in _BUSINESS_TYPE_COLUMN.items():
        if name not in biz_existing:
            sync_conn.exec_driver_sql(f"ALTER TABLE businesses ADD COLUMN {name} {ddl}")
            logger.info("Migration: added businesses.%s", name)
```

In the products block (next to `_PRODUCT_NEW_COLUMNS`), after it add:

```python
        for name, ddl in _PRODUCT_DURATION_COLUMN.items():
            if name not in prod_existing:
                sync_conn.exec_driver_sql(f"ALTER TABLE products ADD COLUMN {name} {ddl}")
                logger.info("Migration: added products.%s", name)
```

(`biz_existing` and `prod_existing` are the column sets already computed in the existing Phase B blocks; reuse them. `create_all` creates the new `staff`/`bookings` tables automatically.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_phase_c_migration.py -v`
Expected: PASS. (`GET /api/business` is added in Task 3 — if it does not yet exist, the second test is xfail until Task 3; mark it `@pytest.mark.skip(reason="GET /api/business added in Task 3")` and remove the skip in Task 3. Note this in the commit.)

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/models.py backend/database.py backend/tests/test_phase_c_migration.py
git commit -m "feat(phase-c): business_type + duration + staff/bookings models (migration)"
```

---

## Task 2: Staff CRUD endpoints

**Files:**
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_staff_api.py` (new)

**Interfaces:**
- Produces: `StaffCreate{name}`, `StaffResponse{id,name,active}`; `GET/POST /api/staff`, `DELETE /api/staff/{id}` — scoped to the business.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_staff_api.py
"""Staff CRUD is scoped to the authenticated business."""
from helpers import register, auth


def test_staff_create_list_delete(client):
    t = register(client)
    h = auth(t["access_token"])
    r = client.post("/api/staff", headers=h, json={"name": "Sari"})
    assert r.status_code in (200, 201)
    sid = r.json()["id"]
    assert r.json()["name"] == "Sari" and r.json()["active"] is True

    rows = client.get("/api/staff", headers=h).json()
    assert any(s["id"] == sid for s in rows)

    d = client.delete(f"/api/staff/{sid}", headers=h)
    assert d.status_code == 200
    rows2 = client.get("/api/staff", headers=h).json()
    assert all(s["id"] != sid for s in rows2)


def test_staff_cross_tenant_delete_404(client):
    a = register(client)
    b = register(client, phone="082222222222")
    sid = client.post("/api/staff", headers=auth(a["access_token"]), json={"name": "Sari"}).json()["id"]
    d = client.delete(f"/api/staff/{sid}", headers=auth(b["access_token"]))
    assert d.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_staff_api.py -v`
Expected: FAIL (endpoints missing).

- [ ] **Step 3: Add schemas**

In `backend/schemas.py`, after the business section add:

```python
class StaffCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class StaffResponse(BaseModel):
    id: int
    name: str
    active: bool

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Add the endpoints**

In `backend/main.py`, add `Staff` to the `from models import (...)` block and `StaffCreate, StaffResponse` to `from schemas import (...)`. Add a staff section (near the business endpoints):

```python
@app.get("/api/staff", response_model=list[StaffResponse])
async def list_staff(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    rows = (await session.execute(
        select(Staff).where(Staff.business_id == business.id, Staff.active == True)  # noqa: E712
    )).scalars().all()
    return list(rows)


@app.post("/api/staff", response_model=StaffResponse)
async def create_staff(
    body: StaffCreate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    staff = Staff(business_id=business.id, name=body.name, active=True)
    session.add(staff)
    await session.flush()
    return staff


@app.delete("/api/staff/{staff_id}")
async def delete_staff(
    staff_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    staff = (await session.execute(
        select(Staff).where(Staff.id == staff_id, Staff.business_id == business.id)
    )).scalar_one_or_none()
    if staff is None:
        raise HTTPException(status_code=404, detail="Staff not found for this business.")
    staff.active = False  # soft-delete keeps historical bookings' staff_id valid
    await session.flush()
    return {"ok": True}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_staff_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py backend/main.py backend/tests/test_staff_api.py
git commit -m "feat(phase-c): staff CRUD endpoints (soft-delete, scoped)"
```

---

## Task 3: business_type + product duration endpoints

**Files:**
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_business_type.py` (new)

**Interfaces:**
- Produces: `GET /api/business` returns `business_type`; `PATCH /api/business` accepts `business_type`; product create/update accept `duration_minutes`; `ProductResponse` returns it.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_business_type.py
"""business_type round-trips; product duration_minutes round-trips."""
from helpers import register, auth


def test_business_type_patch_get(client):
    t = register(client)
    h = auth(t["access_token"])
    assert client.get("/api/business", headers=h).json()["business_type"] == "warung"
    r = client.patch("/api/business", headers=h, json={"business_name": "Salon Sari", "business_type": "salon"})
    assert r.status_code == 200 and r.json()["business_type"] == "salon"


def test_business_type_rejects_invalid(client):
    t = register(client)
    h = auth(t["access_token"])
    r = client.patch("/api/business", headers=h, json={"business_name": "X", "business_type": "bengkel"})
    assert r.status_code == 422


def test_product_duration_round_trip(client):
    t = register(client)
    h = auth(t["access_token"])
    pid = client.post("/api/products", headers=h, json={"name": "Facial", "price": 80000, "duration_minutes": 60}).json()["id"]
    got = client.get(f"/api/products/{pid}", headers=h) if False else None  # GET-by-id may not exist
    listed = client.get("/api/products", headers=h).json()
    row = next(p for p in listed if p["id"] == pid)
    assert row["duration_minutes"] == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_business_type.py -v`
Expected: FAIL.

- [ ] **Step 3: Extend schemas**

In `backend/schemas.py`:
- Add `business_type` to `BusinessProfileUpdate`:
  ```python
      business_type: Optional[str] = Field(default=None, pattern="^(warung|salon|wedding)$")
  ```
- Add `business_type: str = "warung"` to `BusinessResponse`.
- Add `duration_minutes: Optional[int] = Field(default=None, ge=0)` to `ProductCreate` and `ProductUpdate`, and `duration_minutes: Optional[int] = None` to `ProductResponse`.

- [ ] **Step 4: Apply in handlers + add GET /api/business**

In `backend/main.py` `update_business_profile`, before the flush:

```python
    if body.business_type is not None:
        business.business_type = body.business_type
```

Add a GET handler beside it:

```python
@app.get("/api/business", response_model=BusinessResponse)
async def get_business_profile(business: Business = Depends(get_current_business)):
    """GET /api/business — the authenticated owner's business profile."""
    return business
```

In the product create handler, set `duration_minutes=body.duration_minutes` on the new `Product`. In the product update handler, apply `if body.duration_minutes is not None: product.duration_minutes = body.duration_minutes`. (If a `GET /api/business` already exists from Phase B, skip re-adding it; verify with `grep -n '"/api/business"' backend/main.py`.)

- [ ] **Step 5: Run tests to verify they pass + un-skip Task 1's test**

Run: `cd backend && uv run pytest tests/test_business_type.py tests/test_phase_c_migration.py -v`
Expected: PASS. Remove the `@pytest.mark.skip` from `test_existing_business_defaults_to_warung` if it was added in Task 1.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py backend/main.py backend/tests/test_business_type.py backend/tests/test_phase_c_migration.py
git commit -m "feat(phase-c): business_type + product duration_minutes (PATCH/GET)"
```

---

## Task 4: booking_service (create, clash, resolve staff)

**Files:**
- Create: `backend/services/booking_service.py`
- Test: `backend/tests/test_booking_service.py` (new)

**Interfaces:**
- Produces: `async create_booking(session, business_id, customer_id, items, scheduled_at, staff_id, total, deposit_amount, notes) -> Booking`; `async check_booking_clash(session, business_id, staff_id, scheduled_at, duration_minutes) -> list[Booking]`; `async resolve_staff(session, business_id, staff_name) -> Optional[int]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_booking_service.py
"""Booking creation, per-staff clash, any-staff capacity, staff resolve."""
import asyncio
import datetime

import services.booking_service as bk
import database, models
from sqlalchemy import select
from helpers import register, auth


def _biz_cust(client):
    t = register(client)
    h = auth(t["access_token"])
    client.post("/api/products", headers=h, json={"name": "Facial", "price": 80000, "duration_minutes": 60})
    cust_phone = "628700700700"
    return t, h


async def _seed_confirmed(session, business_id, customer_id, staff_id, when, dur, status="confirmed"):
    b = await bk.create_booking(session, business_id, customer_id,
                                items=[{"name": "Facial", "price": 80000, "duration_minutes": dur}],
                                scheduled_at=when, staff_id=staff_id, total=80000,
                                deposit_amount=None, notes="")
    b.status = status
    await session.flush()
    return b


def test_create_and_clash_same_staff(client):
    t, h = _biz_cust(client)

    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            cust = models.Customer(phone_number="628700", business_id=biz.id, name="A")
            staff = models.Staff(business_id=biz.id, name="Sari", active=True)
            s.add_all([cust, staff]); await s.flush()
            base = datetime.datetime(2026, 7, 1, 14, 0)
            await _seed_confirmed(s, biz.id, cust.id, staff.id, base, 60)
            # overlapping 14:30 for same staff → clash
            clash = await bk.check_booking_clash(s, biz.id, staff.id, base + datetime.timedelta(minutes=30), 60)
            # non-overlapping 16:00 → no clash
            free = await bk.check_booking_clash(s, biz.id, staff.id, base + datetime.timedelta(hours=2), 60)
            return len(clash), len(free)

    n_clash, n_free = asyncio.get_event_loop().run_until_complete(_run())
    assert n_clash == 1 and n_free == 0


def test_resolve_staff(client):
    t, h = _biz_cust(client)

    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            staff = models.Staff(business_id=biz.id, name="Sari", active=True)
            s.add(staff); await s.flush()
            hit = await bk.resolve_staff(s, biz.id, "sari")
            miss = await bk.resolve_staff(s, biz.id, "siapa aja")
            none = await bk.resolve_staff(s, biz.id, None)
            return hit, miss, none, staff.id

    hit, miss, none, sid = asyncio.get_event_loop().run_until_complete(_run())
    assert hit == sid and miss is None and none is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_booking_service.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Create `backend/services/booking_service.py`**

```python
"""Booking creation, rough clash detection (hybrid), staff name resolution."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Booking, Staff

logger = logging.getLogger(__name__)

_TERMINAL = ("completed", "cancelled", "rejected")


async def create_booking(session: AsyncSession, business_id: int, customer_id: int,
                         items: list[dict], scheduled_at: Optional[datetime],
                         staff_id: Optional[int], total: float,
                         deposit_amount: Optional[float], notes: str) -> Booking:
    duration = sum(int(it.get("duration_minutes") or 0) for it in (items or [])) or None
    booking = Booking(
        business_id=business_id, customer_id=customer_id, staff_id=staff_id,
        items=items, total=total, deposit_amount=deposit_amount,
        scheduled_at=scheduled_at, duration_minutes=duration,
        status="requested", notes=notes or None,
    )
    session.add(booking)
    await session.flush()
    logger.info("Booking #%d requested — business=%d customer=%d", booking.id, business_id, customer_id)
    return booking


def _overlaps(a_start: datetime, a_dur: int, b_start: datetime, b_dur: int) -> bool:
    a_end = a_start + timedelta(minutes=a_dur or 0)
    b_end = b_start + timedelta(minutes=b_dur or 0)
    return a_start < b_end and b_start < a_end


async def check_booking_clash(session: AsyncSession, business_id: int, staff_id: Optional[int],
                              scheduled_at: Optional[datetime], duration_minutes: Optional[int]) -> list[Booking]:
    """Confirmed bookings overlapping the requested window. For a specific staff,
    overlaps for that staff. For 'any staff' (staff_id None), returns the overlapping
    confirmed bookings only when they meet/exceed the active-staff count (capacity full)."""
    if scheduled_at is None:
        return []
    dur = duration_minutes or 0
    stmt = select(Booking).where(
        Booking.business_id == business_id, Booking.status == "confirmed",
        Booking.scheduled_at.isnot(None),
    )
    if staff_id is not None:
        stmt = stmt.where(Booking.staff_id == staff_id)
    candidates = list((await session.execute(stmt)).scalars().all())
    overlapping = [b for b in candidates if _overlaps(scheduled_at, dur, b.scheduled_at, b.duration_minutes or 0)]
    if staff_id is not None:
        return overlapping
    # any-staff: clash only when capacity (active staff) is full
    staff_count = (await session.execute(
        select(func.count(Staff.id)).where(Staff.business_id == business_id, Staff.active == True)  # noqa: E712
    )).scalar() or 0
    return overlapping if staff_count and len(overlapping) >= staff_count else []


async def resolve_staff(session: AsyncSession, business_id: int, staff_name: Optional[str]) -> Optional[int]:
    """Case-insensitive active-staff name match. None for missing / 'siapa aja' / null."""
    if not staff_name:
        return None
    row = (await session.execute(
        select(Staff).where(
            Staff.business_id == business_id, Staff.active == True,  # noqa: E712
            func.lower(Staff.name) == staff_name.strip().lower(),
        )
    )).scalar_one_or_none()
    return row.id if row else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_booking_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/booking_service.py backend/tests/test_booking_service.py
git commit -m "feat(phase-c): booking_service — create, clash, resolve_staff"
```

---

## Task 5: Booking list + patch endpoints

**Files:**
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_bookings_api.py` (new)

**Interfaces:**
- Produces: `BookingResponse` (incl `clash: bool`, `customer_name`), `BookingUpdate{status?, scheduled_at?, staff_id?}`; `GET /api/bookings` (filters `status`, `date`), `PATCH /api/bookings/{id}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bookings_api.py
"""Bookings list/patch scoped; cross-tenant 404; status edit."""
import asyncio
import datetime

import database, models
import services.booking_service as bk
from sqlalchemy import select
from helpers import register, auth


def _seed_booking(client, token, when=None):
    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            cust = models.Customer(phone_number="628701", business_id=biz.id, name="Budi")
            s.add(cust); await s.flush()
            b = await bk.create_booking(s, biz.id, cust.id,
                                        items=[{"name": "Facial", "price": 80000, "duration_minutes": 60}],
                                        scheduled_at=when or datetime.datetime(2026, 7, 1, 14, 0),
                                        staff_id=None, total=80000, deposit_amount=None, notes="")
            await s.commit()
            return b.id
    return asyncio.get_event_loop().run_until_complete(_run())


def test_list_and_patch_status(client):
    t = register(client)
    h = auth(t["access_token"])
    bid = _seed_booking(client, t["access_token"])
    rows = client.get("/api/bookings", headers=h).json()
    assert any(r["id"] == bid and r["status"] == "requested" for r in rows)

    r = client.patch(f"/api/bookings/{bid}", headers=h, json={"status": "confirmed"})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"


def test_cross_tenant_patch_404(client):
    a = register(client)
    b = register(client, phone="082222222222")
    bid = _seed_booking(client, a["access_token"])
    r = client.patch(f"/api/bookings/{bid}", headers=auth(b["access_token"]), json={"status": "confirmed"})
    assert r.status_code == 404


def test_invalid_status_422(client):
    t = register(client)
    bid = _seed_booking(client, t["access_token"])
    r = client.patch(f"/api/bookings/{bid}", headers=auth(t["access_token"]), json={"status": "ngawur"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_bookings_api.py -v`
Expected: FAIL.

- [ ] **Step 3: Add schemas**

In `backend/schemas.py`:

```python
class BookingResponse(BaseModel):
    id: int
    customer_name: str
    staff_id: Optional[int] = None
    items: list = Field(default_factory=list)
    total: float
    deposit_amount: Optional[float] = None
    scheduled_at: Optional[datetime.datetime] = None
    duration_minutes: Optional[int] = None
    status: str
    notes: Optional[str] = None
    clash: bool = False
    created_at: datetime.datetime


class BookingUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(requested|confirmed|rejected|completed|cancelled)$")
    scheduled_at: Optional[datetime.datetime] = None
    staff_id: Optional[int] = None
```

- [ ] **Step 4: Add the endpoints**

In `backend/main.py` add `Booking` to the models import and the new schemas + `check_booking_clash` (`from services.booking_service import check_booking_clash`). Add a helper + the endpoints:

```python
async def _booking_to_dict(session: AsyncSession, b: Booking, customer_name: str) -> dict:
    clash = bool(await check_booking_clash(session, b.business_id, b.staff_id, b.scheduled_at, b.duration_minutes)) \
        if b.status in ("requested", "confirmed") else False
    return {
        "id": b.id, "customer_name": customer_name, "staff_id": b.staff_id,
        "items": b.items or [], "total": b.total, "deposit_amount": b.deposit_amount,
        "scheduled_at": b.scheduled_at, "duration_minutes": b.duration_minutes,
        "status": b.status, "notes": b.notes, "clash": clash, "created_at": b.created_at,
    }


@app.get("/api/bookings", response_model=list[BookingResponse])
async def list_bookings(
    status: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    stmt = (
        select(Booking, Customer)
        .join(Customer, Booking.customer_id == Customer.id)
        .where(Booking.business_id == business.id)
        .order_by(Booking.scheduled_at.asc().nullslast(), Booking.created_at.desc())
    )
    if status:
        stmt = stmt.where(Booking.status == status)
    if date:  # YYYY-MM-DD
        day = datetime.date.fromisoformat(date)
        start = datetime.datetime.combine(day, datetime.time.min)
        end = datetime.datetime.combine(day, datetime.time.max)
        stmt = stmt.where(Booking.scheduled_at >= start, Booking.scheduled_at <= end)
    rows = (await session.execute(stmt)).all()
    return [await _booking_to_dict(session, b, c.name or c.phone_number) for b, c in rows]


@app.patch("/api/bookings/{booking_id}", response_model=BookingResponse)
async def update_booking(
    booking_id: int,
    body: BookingUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    row = (await session.execute(
        select(Booking, Customer).join(Customer, Booking.customer_id == Customer.id)
        .where(Booking.id == booking_id, Booking.business_id == business.id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Booking not found for this business.")
    booking, customer = row
    if body.scheduled_at is not None:
        booking.scheduled_at = body.scheduled_at
    if body.staff_id is not None:
        booking.staff_id = body.staff_id
    if body.status is not None:
        booking.status = body.status
    await session.flush()
    # Task 6 wires the status→WA notify + payment here.
    await _maybe_notify_booking_status(session, business, booking, customer, body.status)
    return await _booking_to_dict(session, booking, customer.name or customer.phone_number)
```

Add a placeholder so this task is self-contained (Task 6 fills it in):

```python
async def _maybe_notify_booking_status(session, business, booking, customer, new_status) -> None:
    """Placeholder — Task 6 implements booking status→WA notify + payment."""
    return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_bookings_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py backend/main.py backend/tests/test_bookings_api.py
git commit -m "feat(phase-c): booking list + patch endpoints (clash flag, scoped)"
```

---

## Task 6: Booking status → WA notify + payment on confirm

**Files:**
- Modify: `backend/main.py`
- Test: `backend/tests/test_booking_status_sync.py` (new)

**Interfaces:**
- Consumes: `within_service_window`, `send_message`, `send_payment_info` (Phase B).
- Produces: `_maybe_notify_booking_status` real body; `BOOKING_STATUS_WA_MESSAGE` map.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_booking_status_sync.py
"""Confirm → WA notify + payment; within-window only."""
import asyncio
import datetime

import main
import database, models
import services.booking_service as bk
from sqlalchemy import select
from helpers import register, connect_wa, auth


def _seed(client, token, with_inbound=True):
    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            cust = models.Customer(phone_number="628702", business_id=biz.id, name="Budi")
            s.add(cust); await s.flush()
            if with_inbound:
                s.add(models.Message(business_id=biz.id, customer_id=cust.id,
                                     content="hi", direction="inbound"))
            b = await bk.create_booking(s, biz.id, cust.id,
                                        items=[{"name": "Facial", "price": 80000, "duration_minutes": 60}],
                                        scheduled_at=datetime.datetime(2026, 7, 1, 14, 0),
                                        staff_id=None, total=80000, deposit_amount=20000, notes="")
            await s.commit()
            return b.id
    return asyncio.get_event_loop().run_until_complete(_run())


def test_confirm_notifies_and_sends_deposit(client, monkeypatch):
    notes, pay = [], {}

    async def cap_send(to, body, **k):
        notes.append(body); return {"ok": True}

    async def cap_pay(session, business, customer, total):
        pay["total"] = total; return True

    monkeypatch.setattr(main, "send_message", cap_send)
    monkeypatch.setattr(main, "send_payment_info", cap_pay)

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    bid = _seed(client, t["access_token"])
    client.patch(f"/api/bookings/{bid}", headers=auth(t["access_token"]), json={"status": "confirmed"})
    assert any("dikonfirmasi" in n for n in notes)
    assert pay.get("total") == 20000  # deposit, not full total
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_booking_status_sync.py -v`
Expected: FAIL (placeholder sends nothing).

- [ ] **Step 3: Implement the notify + payment**

In `backend/main.py`, near `STATUS_WA_MESSAGE` add:

```python
def _fmt_when(dt) -> str:
    return dt.strftime("%d/%m %H:%M") if dt else "(waktu menyusul)"


BOOKING_STATUS_WA_MESSAGE = {
    "confirmed": "Booking kakak {when} sudah dikonfirmasi ✅",
    "rejected": "Mohon maaf, jadwal yang diminta belum bisa. Boleh pilih waktu lain Kak?",
    "completed": "Terima kasih sudah datang ke {store} ya Kak 😊",
    "cancelled": "Booking kakak dibatalkan.",
}
```

Replace the placeholder `_maybe_notify_booking_status`:

```python
async def _maybe_notify_booking_status(session, business, booking, customer, new_status) -> None:
    """Notify the customer of a booking status change (24h-gated); on confirm, send payment."""
    if not new_status:
        return
    template = BOOKING_STATUS_WA_MESSAGE.get(new_status)
    if template and await within_service_window(session, customer.id):
        msg = template.format(when=_fmt_when(booking.scheduled_at), store=business.business_name)
        try:
            await send_message(customer.phone_number, msg,
                               phone_number_id=business.phone_number_id, access_token=business.access_token)
        except Exception:
            logger.exception("Booking status notify failed for booking %d", booking.id)
    if new_status == "confirmed":
        amount = booking.deposit_amount if booking.deposit_amount else booking.total
        try:
            await send_payment_info(session, business, customer, amount)
        except Exception:
            logger.exception("Booking payment send failed for booking %d", booking.id)
```

(`within_service_window`, `send_message`, `send_payment_info` are already imported from Phase B.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_booking_status_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_booking_status_sync.py
git commit -m "feat(phase-c): booking status→WA notify + deposit/total payment on confirm"
```

---

## Task 7: Booking reminder + send-payment endpoints

**Files:**
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_booking_remind.py` (new)

**Interfaces:**
- Produces: `POST /api/bookings/{id}/remind` and `POST /api/bookings/{id}/send-payment`, both returning `{sent: bool}` (reuse `SendPaymentResponse` for send-payment).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_booking_remind.py
"""Manual reminder + send-payment are window-gated."""
import asyncio
import datetime

import main
import database, models
import services.booking_service as bk
from sqlalchemy import select
from helpers import register, connect_wa, auth


def _seed(client, token, with_inbound):
    async def _run():
        async with database.async_session_factory() as s:
            biz = (await s.execute(select(models.Business))).scalars().first()
            cust = models.Customer(phone_number="628703", business_id=biz.id, name="Budi")
            s.add(cust); await s.flush()
            if with_inbound:
                s.add(models.Message(business_id=biz.id, customer_id=cust.id, content="hi", direction="inbound"))
            b = await bk.create_booking(s, biz.id, cust.id, items=[{"name": "Facial", "price": 80000}],
                                        scheduled_at=datetime.datetime(2026, 7, 1, 14, 0),
                                        staff_id=None, total=80000, deposit_amount=None, notes="")
            await s.commit()
            return b.id
    return asyncio.get_event_loop().run_until_complete(_run())


def test_remind_sends_within_window(client, monkeypatch):
    async def cap_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", cap_send)
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    bid = _seed(client, t["access_token"], with_inbound=True)
    r = client.post(f"/api/bookings/{bid}/remind", headers=auth(t["access_token"]))
    assert r.status_code == 200 and r.json()["sent"] is True


def test_remind_skips_outside_window(client, monkeypatch):
    async def cap_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", cap_send)
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    bid = _seed(client, t["access_token"], with_inbound=False)  # no inbound → window closed
    r = client.post(f"/api/bookings/{bid}/remind", headers=auth(t["access_token"]))
    assert r.status_code == 200 and r.json()["sent"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_booking_remind.py -v`
Expected: FAIL.

- [ ] **Step 3: Add the endpoints**

In `backend/main.py` (after the booking PATCH). `SendPaymentResponse` is already imported from Phase B:

```python
async def _load_booking(session, business, booking_id):
    row = (await session.execute(
        select(Booking, Customer).join(Customer, Booking.customer_id == Customer.id)
        .where(Booking.id == booking_id, Booking.business_id == business.id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Booking not found for this business.")
    return row


@app.post("/api/bookings/{booking_id}/remind", response_model=SendPaymentResponse)
async def remind_booking(
    booking_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    booking, customer = await _load_booking(session, business, booking_id)
    if not await within_service_window(session, customer.id):
        return SendPaymentResponse(sent=False)
    msg = f"Halo Kak, pengingat booking {_fmt_when(booking.scheduled_at)} ya 🙏"
    try:
        await send_message(customer.phone_number, msg,
                           phone_number_id=business.phone_number_id, access_token=business.access_token)
        return SendPaymentResponse(sent=True)
    except Exception:
        logger.exception("Reminder send failed for booking %d", booking.id)
        return SendPaymentResponse(sent=False)


@app.post("/api/bookings/{booking_id}/send-payment", response_model=SendPaymentResponse)
async def send_booking_payment(
    booking_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    booking, customer = await _load_booking(session, business, booking_id)
    amount = booking.deposit_amount if booking.deposit_amount else booking.total
    sent = await send_payment_info(session, business, customer, amount)
    return SendPaymentResponse(sent=sent)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_booking_remind.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_booking_remind.py
git commit -m "feat(phase-c): booking manual reminder + send-payment (window-gated)"
```

---

## Task 8: AI BOOKING intent + business_type routing

**Files:**
- Modify: `ai/nlu.py`
- Modify: `ai/ai_service.py`
- Modify: `ai/conversation.py`
- Test: `ai/tests/test_booking_routing.py` (new)

**Interfaces:**
- Produces: NLU `BOOKING` intent; `ReplyRequest.business_type`; `generate_reply(..., business_type=None)` routing — `warung` keeps the order flow, `salon`/`wedding` enter the booking flow (`_handle_booking_flow`).

- [ ] **Step 1: Write the failing test**

```python
# ai/tests/test_booking_routing.py
import conversation as conv_mod
from nlu import classify_intent


def test_booking_intent_detected():
    assert classify_intent("mau booking facial besok jam 2") == "BOOKING"


def test_warung_does_not_enter_booking_flow(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "halo kak")
    called = {"booking": False}
    monkeypatch.setattr(conv_mod, "_handle_booking_flow",
                        lambda *a, **k: called.__setitem__("booking", True) or None)
    mgr = conv_mod.ConversationManager(); monkeypatch.setattr(conv_mod, "manager", mgr)
    conv_mod.generate_reply("628", "mau booking", catalog=[{"name": "Facial", "price": 80000}], business_type="warung")
    assert called["booking"] is False


def test_salon_enters_booking_flow(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "halo kak")
    called = {"booking": False}
    monkeypatch.setattr(conv_mod, "_handle_booking_flow",
                        lambda *a, **k: called.__setitem__("booking", True) or "ok")
    mgr = conv_mod.ConversationManager(); monkeypatch.setattr(conv_mod, "manager", mgr)
    conv_mod.generate_reply("629", "mau booking", catalog=[{"name": "Facial", "price": 80000}], business_type="salon")
    assert called["booking"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai && python -m pytest tests/test_booking_routing.py -v`
Expected: FAIL.

- [ ] **Step 3: Add the BOOKING intent**

In `ai/nlu.py`, add to `INTENT_PATTERNS` (before `INQUIRY_PRICE` so booking words win for service businesses):

```python
    "BOOKING": [
        r"\bbooking\b", r"\bbuking\b", r"\bbuk in\b",
        r"\bjanji\b", r"\bjanjian\b", r"\breservasi\b", r"\breserve\b",
        r"\bjadwal\b", r"\bjadwalin\b",
        r"\b(?:kapan|jam berapa) (?:bisa|kosong|available)\b",
        r"\bmau (?:booking|janji|reservasi|jadwal)\b",
    ],
```

- [ ] **Step 4: Thread business_type through the API + routing**

In `ai/ai_service.py`, add to `ReplyRequest`:

```python
    business_type: Optional[str] = Field(default="warung", description="warung | salon | wedding")
```

In `ai_reply`, pass it to `generate_reply(...)`: add `business_type=request.business_type` to the call.

In `ai/conversation.py` `generate_reply`, add the param and route:

```python
def generate_reply(session_id: str, incoming_message: str,
                   business_context: Optional[dict] = None,
                   catalog: Optional[list[dict]] = None,
                   customer: Optional[dict] = None,
                   business_type: str = "warung") -> str:
```

Inside, after the guardrail block and before `_handle_order_flow`, branch:

```python
    if business_type in ("salon", "wedding"):
        response = _handle_booking_flow(conv, incoming_message, intent, analysis, business_context, business_type)
    else:
        response = _handle_order_flow(conv, incoming_message, intent, analysis, business_context)
```

Add a minimal `_handle_booking_flow` stub (Task 9 fills the real logic):

```python
def _handle_booking_flow(conv, message, intent, analysis, business_context, business_type):
    """Placeholder — Task 9 implements the booking flow. Falls through to the LLM."""
    return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ai && python -m pytest tests/test_booking_routing.py -v` then `cd ai && python -m pytest tests/`
Expected: PASS; AI suite green.

- [ ] **Step 6: Commit**

```bash
git add ai/nlu.py ai/ai_service.py ai/conversation.py ai/tests/test_booking_routing.py
git commit -m "feat(phase-c): BOOKING intent + business_type routing in AI reply"
```

---

## Task 9: extract_booking_from_chat + ReplyResponse.booking

**Files:**
- Modify: `ai/conversation.py`
- Modify: `ai/ai_service.py`
- Test: `ai/tests/test_booking_extract.py` (new)

**Interfaces:**
- Produces: `extract_booking_from_chat(history, catalog, business_type) -> dict` (`{items, scheduled_at, staff_name, deposit_amount, notes}`); `Conversation.closed_booking`; `ReplyResponse.booking`; `_handle_booking_flow` real body with the ambiguity guardrail.

- [ ] **Step 1: Write the failing test**

```python
# ai/tests/test_booking_extract.py
import conversation as conv_mod


def test_close_with_date_sets_booking(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "ok kak")
    monkeypatch.setattr(conv_mod, "extract_booking_from_chat",
        lambda h, c, bt: {"items": [{"name": "Facial", "price": 80000, "duration_minutes": 60}],
                          "scheduled_at": "2026-07-01T14:00:00", "staff_name": "Sari",
                          "deposit_amount": None, "notes": ""})
    mgr = conv_mod.ConversationManager(); monkeypatch.setattr(conv_mod, "manager", mgr)
    cat = [{"name": "Facial", "price": 80000}]
    conv_mod.generate_reply("628", "booking facial sama sari", catalog=cat, business_type="salon")
    conv_mod.generate_reply("628", "iya itu aja", catalog=cat, business_type="salon")
    conv = mgr.get("628")
    assert conv.closed_booking is not None
    assert conv.closed_booking["status"] == "closed"
    assert conv.closed_booking["scheduled_at"] == "2026-07-01T14:00:00"


def test_ambiguous_date_no_booking(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "untuk tanggal berapa ya kak?")
    monkeypatch.setattr(conv_mod, "extract_booking_from_chat",
        lambda h, c, bt: {"items": [{"name": "Facial", "price": 80000}],
                          "scheduled_at": None, "staff_name": None, "deposit_amount": None, "notes": ""})
    mgr = conv_mod.ConversationManager(); monkeypatch.setattr(conv_mod, "manager", mgr)
    cat = [{"name": "Facial", "price": 80000}]
    conv_mod.generate_reply("630", "mau booking facial", catalog=cat, business_type="salon")
    conv_mod.generate_reply("630", "itu aja", catalog=cat, business_type="salon")
    assert mgr.get("630").closed_booking is None  # no date → no booking
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai && python -m pytest tests/test_booking_extract.py -v`
Expected: FAIL.

- [ ] **Step 3: Add `closed_booking` + reset**

In `ai/conversation.py`, add to `Conversation` (after `closed_order`):

```python
    closed_booking: Optional[dict] = None
```

In `generate_reply`, next to `conv.closed_order = None` add `conv.closed_booking = None`.

- [ ] **Step 4: Implement `extract_booking_from_chat`**

Add to `ai/conversation.py` (near `extract_order_from_chat`):

```python
def extract_booking_from_chat(chat_messages: list[dict], catalog: Optional[list[dict]], business_type: str) -> dict:
    """Extract a structured booking from the conversation. scheduled_at is an ISO
    8601 string, or null when the customer hasn't given a clear date/time."""
    catalog_text = ""
    if catalog:
        catalog_text = "\n".join(
            f"- {i['name']}: Rp{i['price']:,.0f}" + (f" ({i.get('duration_minutes')} menit)" if i.get('duration_minutes') else "")
            for i in catalog[:30]
        )
    system_prompt = (
        "Kamu mengekstrak data booking jasa dari percakapan WhatsApp. "
        "Kembalikan HANYA JSON: {\"items\":[{\"name\":\"...\",\"price\":0,\"duration_minutes\":null}],"
        "\"scheduled_at\":\"YYYY-MM-DDTHH:MM:SS\"|null,\"staff_name\":\"...\"|null,"
        "\"deposit_amount\":null,\"notes\":\"...\"}. "
        "scheduled_at HARUS null jika pelanggan belum menyebut tanggal/jam yang jelas — "
        "JANGAN mengarang tanggal. Hanya pakai layanan dari KATALOG.\n\nKATALOG:\n" + catalog_text
    )
    chat_text = "\n".join(
        f"{'Pelanggan' if m['role'] == 'user' else 'Waku'}: {m['content']}" for m in chat_messages[-30:]
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Ekstrak booking dari percakapan ini:\n{chat_text}"},
    ]
    response = ask_llm(messages, intent="BOOKING", temperature=0.1, max_tokens=512)
    try:
        cleaned = response.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0]
        data = json.loads(cleaned)
        return {
            "items": data.get("items", []),
            "scheduled_at": data.get("scheduled_at"),
            "staff_name": data.get("staff_name"),
            "deposit_amount": data.get("deposit_amount"),
            "notes": data.get("notes", ""),
        }
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Failed to parse booking extraction: {e}")
        return {"items": [], "scheduled_at": None, "staff_name": None, "deposit_amount": None, "notes": ""}
```

- [ ] **Step 5: Implement `_handle_booking_flow`**

Replace the Task 8 placeholder in `ai/conversation.py`:

```python
_BOOKING_CLOSE_SIGNALS = ["itu aja", "itu saja", "cukup", "fix", "oke", "ok", "iya itu", "ya itu", "deal", "gas"]


def _handle_booking_flow(conv, message, intent, analysis, business_context, business_type):
    """Salon/wedding booking flow. Shows services, and on close extracts the booking.
    Returns a reply string, or None to fall through to the LLM."""
    text_lower = analysis["normalized_text"]

    # Menu / service inquiry → show the (already-retrieved) catalog.
    if intent in ("BOOKING", "ORDER", "INQUIRY_PRICE") and conv.catalog and "?" in message:
        lines = ["Layanan yang tersedia Kak 😊:"]
        for item in conv.catalog[:15]:
            dur = f" · {item['duration_minutes']} menit" if item.get("duration_minutes") else ""
            lines.append(f"  • {item['name']} — Rp{item.get('price', 0):,.0f}{dur}")
        lines.append("\nMau booking yang mana, dan untuk tanggal/jam berapa Kak?")
        return "\n".join(lines)

    # Closing signal → extract the booking.
    if any(sig in text_lower for sig in _BOOKING_CLOSE_SIGNALS):
        extracted = _sys.modules[__name__].extract_booking_from_chat(conv.get_context(), conv.catalog, business_type)
        items = extracted.get("items") or []
        if items and extracted.get("scheduled_at"):
            total = sum(float(it.get("price") or 0) for it in items)
            conv.closed_booking = {
                "items": items, "scheduled_at": extracted["scheduled_at"],
                "staff_name": extracted.get("staff_name"),
                "deposit_amount": extracted.get("deposit_amount"),
                "notes": extracted.get("notes", ""), "total": total, "status": "closed",
            }
            return ("Siap Kak! Permintaan booking dicatat ya, menunggu konfirmasi pemilik. "
                    "Nanti Waku kabari 🙏")
        if items and not extracted.get("scheduled_at"):
            # Ambiguity guardrail: have a service, missing a clear date/time.
            return "Boleh Kak 😊 Untuk tanggal dan jam berapa ya?"

    return None  # fall through to the LLM
```

(`_sys` is imported at module scope in Phase B's close handler — reuse `import sys as _sys` at the call site if not already module-level, mirroring `extract_order_from_chat`'s pattern.)

- [ ] **Step 6: Expose `booking` on the API**

In `ai/ai_service.py`, add to `ReplyResponse`:

```python
    booking: Optional[dict] = Field(default=None, description="Finalised booking on close; null otherwise")
```

In `ai_reply`, where it reads `conv.closed_order`, also read the booking and pass it:

```python
        booking = conv.closed_booking if conv else None
        return ReplyResponse(reply=reply, intent=analysis["intent"], session_id=request.session_id,
                             order=closed, booking=booking)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd ai && python -m pytest tests/test_booking_extract.py -v` then `cd ai && python -m pytest tests/`
Expected: PASS; AI suite green.

- [ ] **Step 8: Commit**

```bash
git add ai/conversation.py ai/ai_service.py ai/tests/test_booking_extract.py
git commit -m "feat(phase-c): extract_booking_from_chat + ReplyResponse.booking (ambiguity guard)"
```

---

## Task 10: Backend booking persist in the webhook

**Files:**
- Modify: `backend/main.py`
- Test: `backend/tests/test_booking_persist.py` (new)

**Interfaces:**
- Consumes: `ReplyResponse.booking`; `create_booking`, `resolve_staff`.
- Produces: `_generate_ai_reply` 4-tuple `(reply, ai_order, ai_booking, ai_ok)`; `_process_tenant_messages` persists a booking for salon/wedding.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_booking_persist.py
"""Salon close-booking is persisted requested; warung path unaffected."""
import main
from helpers import register, connect_wa, customer_message, auth


def _ai(reply, *, order=None, booking=None, ok=True):
    return (reply, order, booking, ok)


def test_salon_booking_persisted(client, monkeypatch):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)

    async def fake_reply(session, business, sid, text, customer=None):
        bk = {"items": [{"name": "Facial", "price": 80000, "duration_minutes": 60}],
              "scheduled_at": "2026-07-01T14:00:00", "staff_name": None,
              "deposit_amount": None, "notes": "", "total": 80000, "status": "closed"} if "itu aja" in text else None
        return _ai("ok kak", booking=bk)
    monkeypatch.setattr(main, "_generate_ai_reply", fake_reply)

    t = register(client)
    h = auth(t["access_token"])
    client.patch("/api/business", headers=h, json={"business_name": "Salon", "business_type": "salon"})
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    customer_message(client, "PNID_T", "628123", "booking facial")
    customer_message(client, "PNID_T", "628123", "itu aja")

    rows = client.get("/api/bookings", headers=h).json()
    assert len(rows) == 1 and rows[0]["status"] == "requested"
    assert rows[0]["total"] == 80000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_booking_persist.py -v`
Expected: FAIL (`_generate_ai_reply` returns a 3-tuple; no booking persist).

- [ ] **Step 3: Make `_generate_ai_reply` a 4-tuple with business_type**

In `backend/main.py` `_generate_ai_reply`:
- Add `"business_type": business.business_type` to the `payload` dict.
- Capture the booking and return the 4-tuple. Change the success path:
  ```python
              ai_order = data.get("order")
              ai_booking = data.get("booking")
              if reply:
                  return reply, ai_order, ai_booking, True
  ```
- Change the unreachable fallback return to `return (<text>, None, None, False)`.
- Update the return type annotation to `tuple[str, Optional[dict], Optional[dict], bool]`.

- [ ] **Step 4: Persist the booking in `_process_tenant_messages`**

In `backend/main.py`, add the imports `from services.booking_service import create_booking, resolve_staff` and `import datetime` is already present. Change the unpack and add the booking branch:

```python
            reply, ai_order, ai_booking, ai_ok = await _generate_ai_reply(
                session, business, customer.phone_number, text, customer=customer
            )

            if business.business_type in ("salon", "wedding"):
                if ai_booking and ai_booking.get("status") == "closed":
                    await _persist_ai_booking(session, business, customer, ai_booking)
            elif ai_order and ai_order.get("status") == "closed":
                await _persist_ai_order(session, business, customer, ai_order)
                await _maybe_send_payment(session, business, customer)
            elif (not ai_ok) and _AI_FALLBACK_ORDER_REGEX:
                # ... existing regex fallback block unchanged ...
```

Add the persist helper:

```python
def _parse_iso(value) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


async def _persist_ai_booking(session, business, customer, ai_booking: dict) -> None:
    items = ai_booking.get("items") or []
    if not items:
        return
    staff_id = await resolve_staff(session, business.id, ai_booking.get("staff_name"))
    await create_booking(
        session, business.id, customer.id,
        items=items,
        scheduled_at=_parse_iso(ai_booking.get("scheduled_at")),
        staff_id=staff_id,
        total=float(ai_booking.get("total") or sum(float(i.get("price") or 0) for i in items)),
        deposit_amount=ai_booking.get("deposit_amount"),
        notes=ai_booking.get("notes", ""),
    )
```

(The warung regex fallback and on-demand payment keyword block stay exactly as Phase B left them.)

- [ ] **Step 5: Run tests to verify they pass + full suite**

Run: `cd backend && uv run pytest tests/test_booking_persist.py -v` then `cd backend && uv run pytest -q`
Expected: PASS. If any Phase B test monkeypatched `_generate_ai_reply` with a 3-tuple, update those stubs to the 4-tuple `(reply, order, booking, ok)` and note each in the commit.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/tests/test_booking_persist.py
git commit -m "feat(phase-c): persist AI booking for salon/wedding (4-tuple reply)"
```

---

## Task 11: Dashboard — types/api/queries + Settings + Products

**Files:**
- Modify: `dashboard/src/lib/{types,api,queries}.ts`
- Modify: `dashboard/src/pages/Settings.tsx`
- Modify: `dashboard/src/pages/Products.tsx`

**Interfaces:**
- Consumes: `GET/PATCH /api/business` (business_type), `GET/POST/DELETE /api/staff`, product `duration_minutes`.

- [ ] **Step 1: Add types + api + hooks**

Read `dashboard/src/lib/{api,queries,types}.ts` and match their patterns. Add:

`types.ts`:
```typescript
export type BusinessType = "warung" | "salon" | "wedding";
export interface Staff { id: number; name: string; active: boolean; }
```
Extend `BusinessProfile` with `business_type?: BusinessType`. Extend the product type with `duration_minutes?: number | null`.

`api.ts`:
```typescript
  listStaff: () => req<Staff[]>("/api/staff"),
  createStaff: (name: string) => req<Staff>("/api/staff", { method: "POST", ...body({ name }) }),
  deleteStaff: (id: number) => req<{ ok: boolean }>(`/api/staff/${id}`, { method: "DELETE" }),
```

`queries.ts`: `useStaff()` (query, key `keys.staff = ["staff"]`), `useCreateStaff()`, `useDeleteStaff()` (mutations invalidating `keys.staff`). Import `Staff` from `./types`.

- [ ] **Step 2: Settings — business_type selector + staff manager**

In `dashboard/src/pages/Settings.tsx`, add a Card using `useBusiness()`/`useUpdateBusiness()` (Phase B) for the type, and the staff hooks for the manager. The selector PATCHes `{ business_name, business_type }`. The staff manager (shown when `business_type === "salon"`) lists `useStaff()`, an add input → `useCreateStaff`, and a remove button → `useDeleteStaff`. Match the existing card markup and primitives (`Card`, `Field`, `Button`, `inputCls`).

- [ ] **Step 3: Products — duration field**

In `dashboard/src/pages/Products.tsx`, add a `duration_minutes` number input to the product form, shown only when the business type is salon (read it from `useBusiness()`), and include it in the create/update payload.

- [ ] **Step 4: Typecheck + build**

Run: `cd dashboard && bun run tsc --noEmit && bun run build`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/types.ts dashboard/src/lib/api.ts dashboard/src/lib/queries.ts dashboard/src/pages/Settings.tsx dashboard/src/pages/Products.tsx
git commit -m "feat(dashboard): business_type selector, staff manager, product duration"
```

---

## Task 12: Dashboard — Bookings page + type-aware nav

**Files:**
- Create: `dashboard/src/pages/Bookings.tsx`
- Modify: `dashboard/src/lib/{types,api,queries}.ts`
- Modify: `dashboard/src/components/BottomNav.tsx`
- Modify: the router registration (wherever routes are declared)

**Interfaces:**
- Consumes: `GET /api/bookings`, `PATCH /api/bookings/{id}`, `POST /api/bookings/{id}/remind`, `POST /api/bookings/{id}/send-payment`.

- [ ] **Step 1: Add types + api + hooks**

`types.ts`:
```typescript
export interface Booking {
  id: number; customer_name: string; staff_id: number | null;
  items: { name: string; price: number; duration_minutes?: number | null }[];
  total: number; deposit_amount: number | null;
  scheduled_at: string | null; duration_minutes: number | null;
  status: "requested" | "confirmed" | "rejected" | "completed" | "cancelled";
  notes: string | null; clash: boolean; created_at: string;
}
```

`api.ts`:
```typescript
  listBookings: (q?: { status?: string; date?: string }) =>
    req<Booking[]>(`/api/bookings${q?.status || q?.date ? "?" + new URLSearchParams(q as Record<string, string>) : ""}`),
  updateBooking: (id: number, d: { status?: string; scheduled_at?: string; staff_id?: number }) =>
    req<Booking>(`/api/bookings/${id}`, { method: "PATCH", ...body(d) }),
  remindBooking: (id: number) => req<{ sent: boolean }>(`/api/bookings/${id}/remind`, { method: "POST" }),
  sendBookingPayment: (id: number) => req<{ sent: boolean }>(`/api/bookings/${id}/send-payment`, { method: "POST" }),
```

`queries.ts`: `useBookings()` (key `keys.bookings = ["bookings"]`), `useUpdateBooking()`, `useRemindBooking()`, `useSendBookingPayment()` — mutations invalidate `keys.bookings`.

- [ ] **Step 2: Build the Bookings page**

Create `dashboard/src/pages/Bookings.tsx`: a "Besok" section (bookings whose `scheduled_at` is tomorrow, each with an "Ingatkan" button → `useRemindBooking`), then the full list. Each row shows customer, item names, `scheduled_at`, status, a clash badge when `clash`, and actions by status: `requested` → Konfirmasi (`updateBooking({status:"confirmed"})`) / Tolak (`rejected`); `confirmed` → Selesai (`completed`) / Batal (`cancelled`) / "Kirim bayar" (`useSendBookingPayment`). Use the Phase B design-system primitives.

- [ ] **Step 3: Type-aware nav + route**

In `dashboard/src/components/BottomNav.tsx`, read the business type (via `useBusiness()`); when `salon`/`wedding`, render the "Booking" item (route `/bookings`) in place of "Pesanan"; for `warung` keep "Pesanan". Register the `/bookings` route alongside the existing routes.

- [ ] **Step 4: Typecheck + build**

Run: `cd dashboard && bun run tsc --noEmit && bun run build`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/pages/Bookings.tsx dashboard/src/lib/types.ts dashboard/src/lib/api.ts dashboard/src/lib/queries.ts dashboard/src/components/BottomNav.tsx
git commit -m "feat(dashboard): Bookings page + type-aware nav"
```

---

## Final Verification

- [ ] Backend: `cd backend && uv run pytest -q` — all pass.
- [ ] AI: `cd ai && python -m pytest tests/ -q` — all pass.
- [ ] Dashboard: `cd dashboard && bun run tsc --noEmit && bun run build` — clean.

---

## Self-Review notes (plan author)

**Spec coverage:**
- business_type (drives flow + dashboard, default warung) → Tasks 1, 3, 8, 10, 11, 12. ✅
- Product duration → Tasks 1, 3, 11. ✅
- Staff (multi-staff) → Tasks 1, 2, 11. ✅
- Booking model + service (create/clash/resolve) → Tasks 1, 4. ✅
- Booking endpoints (list/patch/remind/send-payment) → Tasks 5, 7. ✅
- Status→WA + confirm→payment (deposit/total) → Task 6. ✅
- AI BOOKING intent + routing + extract + ambiguity guard → Tasks 8, 9. ✅
- Backend persist (requested) → Task 10. ✅
- Dashboard (Bookings, Settings, Products, nav) → Tasks 11, 12. ✅
- 24h window the only outbound gate → Tasks 6, 7 (reuse `within_service_window`). ✅

**Type consistency:** `_generate_ai_reply` 4-tuple `(reply, ai_order, ai_booking, ai_ok)` defined in Task 10 and consumed there; Phase B 3-tuple stubs flagged for update in Task 10 step 5. Booking item shape `{name, price, duration_minutes}` consistent across service, AI extract, and persist. `closed_booking` mirrors `closed_order`.

**Known follow-ups (flagged):**
- Date parsing accuracy depends on the LLM; the owner-editable `scheduled_at` (PATCH) is the safety net.
- `check_booking_clash` any-staff capacity is a rough heuristic (overlap count ≥ active-staff count); acceptable per the hybrid design (owner confirms).
- Phase C must be merged on top of Phase B (PR #11); if Phase B changes `_generate_ai_reply`'s shape further before merge, reconcile in Task 10.
