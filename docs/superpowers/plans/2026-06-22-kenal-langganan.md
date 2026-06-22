# Kenal Langganan (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Waku's AI recognise returning customers (name, usual order, loyalty, notes) and give the owner a Pelanggan page to manage them.

**Architecture:** Denormalised customer stats cached on the `customers` row, fully recomputed from orders on every order write by one function (single invalidation point). The backend builds a compact "customer card" from the cache and injects it into the AI reply prompt with an anti-fabrication guardrail. A new dashboard Pelanggan page reads the cache and edits owner notes/tags.

**Tech Stack:** FastAPI + SQLAlchemy (async, SQLite) backend; separate FastAPI AI service; Bun + Vite + React + TS + TanStack Router/Query + Tailwind v4 dashboard.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-22-kenal-langganan-design.md`. Read it before starting.
- Branch: `feat/kenal-langganan` (already created from `main`).
- Tenant isolation: every customer query is scoped by `business_id == business.id`; cross-tenant access returns 404.
- `REGULAR_THRESHOLD = 5` (module constant in `services/order_service.py`).
- Bounds enforced on PATCH: `tags` ≤ 10 entries, each ≤ 60 chars; `notes` ≤ 1000 chars.
- Loyalty is derived, never stored: `is_regular = is_regular_override if not None else order_count >= REGULAR_THRESHOLD`.
- Personalisation guardrail: only include fields that exist; a customer with `order_count == 0` and no real name (name equals phone number) and no notes/tags gets **no** card — the AI must not fabricate.
- Backend tests run with: `cd backend && uv run pytest -q` (expect all pass, currently 32).
- Frontend gate: `cd dashboard && bunx tsc --noEmit` (0 errors) and `bunx vite build` (succeeds). No frontend test runner exists — do not add one.
- Migrations are additive SQLite `ALTER TABLE ... ADD COLUMN` via `database._run_migrations`, idempotent.
- Commit after every task with the message shown in its final step.

---

### Task 1: Customer model columns + migration

**Files:**
- Modify: `backend/models.py` (Customer class, ~lines 69-79)
- Modify: `backend/database.py` (add `_CUSTOMER_NEW_COLUMNS` + extend `_run_migrations`)
- Test: `backend/tests/test_customer_stats.py` (new)

**Interfaces:**
- Produces: `Customer` ORM with new fields `notes, tags, is_regular_override, order_count, total_spent, last_order_at, top_items, avg_cadence_days, stats_updated_at`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_customer_stats.py`:

```python
"""Customer recognition: cached stats + recompute."""
import asyncio
from datetime import datetime

from sqlalchemy import select

from database import async_session_factory
from models import Business, Customer


def _mk_customer(**extra):
    async def run():
        async with async_session_factory() as s:
            biz = Business(phone_number="0810000000", business_name="T")
            s.add(biz)
            await s.flush()
            cust = Customer(phone_number="628999", business_id=biz.id, name="628999", **extra)
            s.add(cust)
            await s.flush()
            cid = cust.id
            await s.commit()
            return cid
    return asyncio.run(run())


def test_customer_has_new_columns_with_defaults():
    cid = _mk_customer()

    async def check():
        async with async_session_factory() as s:
            c = (await s.execute(select(Customer).where(Customer.id == cid))).scalar_one()
            assert c.order_count == 0
            assert c.total_spent == 0.0
            assert c.tags == []
            assert c.top_items == []
            assert c.notes is None
            assert c.is_regular_override is None
            assert c.last_order_at is None
            assert c.avg_cadence_days is None
    asyncio.run(check())


def test_customer_accepts_notes_and_tags():
    cid = _mk_customer(notes="tanpa pedas", tags=["alergi udang"])

    async def check():
        async with async_session_factory() as s:
            c = (await s.execute(select(Customer).where(Customer.id == cid))).scalar_one()
            assert c.notes == "tanpa pedas"
            assert c.tags == ["alergi udang"]
    asyncio.run(check())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_customer_stats.py -q`
Expected: FAIL — `TypeError: 'notes' is an invalid keyword argument` / `AttributeError: order_count`.

- [ ] **Step 3: Add the columns to the Customer model**

In `backend/models.py`, the `Customer` class currently ends after the `orders` relationship. Add the new columns just before the relationships (after the `business_id` column). The Customer class should read:

```python
class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=False)

    # ── Kenal Langganan: owner-entered ──
    notes: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    is_regular_override: Mapped[Optional[bool]] = mapped_column(Boolean)

    # ── Kenal Langganan: cached stats (recomputed from orders) ──
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[float] = mapped_column(Float, default=0.0)
    last_order_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    top_items: Mapped[list] = mapped_column(JSON, default=list)
    avg_cadence_days: Mapped[Optional[float]] = mapped_column(Float)
    stats_updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    business: Mapped["Business"] = relationship(back_populates="customers")
    messages: Mapped[list["Message"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
```

(`Boolean, DateTime, Float, Integer, String, Text` and `JSON` are already imported in models.py.)

- [ ] **Step 4: Add the idempotent migration**

In `backend/database.py`, after the `_BUSINESS_NEW_COLUMNS` dict (~line 56) add:

```python
_CUSTOMER_NEW_COLUMNS: dict[str, str] = {
    "notes": "TEXT",
    "tags": "JSON",
    "is_regular_override": "BOOLEAN",
    "order_count": "INTEGER DEFAULT 0",
    "total_spent": "FLOAT DEFAULT 0",
    "last_order_at": "DATETIME",
    "top_items": "JSON",
    "avg_cadence_days": "FLOAT",
    "stats_updated_at": "DATETIME",
}
```

Then inside `_run_migrations`, after the businesses unique-index block (after line 75), add:

```python
    # customers: Kenal Langganan columns
    if "customers" in insp.get_table_names():
        cust_existing = {c["name"] for c in insp.get_columns("customers")}
        for name, ddl in _CUSTOMER_NEW_COLUMNS.items():
            if name not in cust_existing:
                sync_conn.exec_driver_sql(f"ALTER TABLE customers ADD COLUMN {name} {ddl}")
                logger.info("Migration: added customers.%s", name)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_customer_stats.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `cd backend && uv run pytest -q`
Expected: all pass (34).

- [ ] **Step 7: Commit**

```bash
git add backend/models.py backend/database.py backend/tests/test_customer_stats.py
git commit -m "feat(customers): add Kenal Langganan columns + migration"
```

---

### Task 2: `recompute_customer_stats` + `is_regular`

**Files:**
- Modify: `backend/services/order_service.py` (add constant + two functions)
- Test: `backend/tests/test_customer_stats.py` (append)

**Interfaces:**
- Consumes: `Customer`, `Order` models from Task 1.
- Produces:
  - `REGULAR_THRESHOLD: int = 5`
  - `async def recompute_customer_stats(session: AsyncSession, customer_id: int) -> None`
  - `def is_regular(cust: Customer) -> bool`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_customer_stats.py`:

```python
from models import Order
from services.order_service import recompute_customer_stats, is_regular, REGULAR_THRESHOLD


def _seed_orders(cid, specs):
    """specs: list of (total, status, created_at, items)."""
    async def run():
        async with async_session_factory() as s:
            for total, status, created, items in specs:
                o = Order(business_id=1, customer_id=cid, items=items, total=total, status=status)
                s.add(o)
                await s.flush()
                o.created_at = created  # override server default for deterministic cadence
            await s.commit()
    asyncio.run(run())


def test_recompute_counts_excludes_cancelled():
    cid = _mk_customer()
    _seed_orders(cid, [
        (14000.0, "completed", datetime(2026, 6, 1, 10), [{"name": "Nasi Goreng", "quantity": 2}]),
        (10000.0, "pending", datetime(2026, 6, 6, 10), [{"name": "Nasi Goreng", "quantity": 1}, {"name": "Es Teh", "qty": 1}]),
        (99000.0, "cancelled", datetime(2026, 6, 7, 10), [{"name": "Parfum", "quantity": 1}]),
    ])

    async def run():
        async with async_session_factory() as s:
            await recompute_customer_stats(s, cid)
            await s.commit()
            c = (await s.execute(select(Customer).where(Customer.id == cid))).scalar_one()
            assert c.order_count == 2                      # cancelled excluded
            assert c.total_spent == 24000.0
            assert c.last_order_at == datetime(2026, 6, 6, 10)
            assert c.top_items[0] == {"name": "Nasi Goreng", "count": 3}
            assert round(c.avg_cadence_days) == 5          # 1 Jun -> 6 Jun
    asyncio.run(run())


def test_single_order_has_null_cadence():
    cid = _mk_customer()
    _seed_orders(cid, [(14000.0, "completed", datetime(2026, 6, 1, 10), [{"name": "Nasi Goreng", "quantity": 1}])])

    async def run():
        async with async_session_factory() as s:
            await recompute_customer_stats(s, cid)
            await s.commit()
            c = (await s.execute(select(Customer).where(Customer.id == cid))).scalar_one()
            assert c.order_count == 1
            assert c.avg_cadence_days is None
    asyncio.run(run())


def test_is_regular_threshold_and_override():
    class C:
        order_count = REGULAR_THRESHOLD
        is_regular_override = None
    assert is_regular(C()) is True
    C.order_count = 1
    assert is_regular(C()) is False
    C.is_regular_override = True
    assert is_regular(C()) is True
    C.is_regular_override = False
    assert is_regular(C()) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_customer_stats.py -q`
Expected: FAIL — `ImportError: cannot import name 'recompute_customer_stats'`.

- [ ] **Step 3: Implement the functions**

In `backend/services/order_service.py`, after the imports/logger (near the top, after `logger = logging.getLogger(__name__)`), add the constant:

```python
REGULAR_THRESHOLD = 5
```

Then add these functions in the "Database operations" section (e.g. after `create_order`):

```python
def is_regular(cust: Customer) -> bool:
    """Loyalty is derived, never stored. Owner override wins when set."""
    if cust.is_regular_override is not None:
        return bool(cust.is_regular_override)
    return (cust.order_count or 0) >= REGULAR_THRESHOLD


async def recompute_customer_stats(session: AsyncSession, customer_id: int) -> None:
    """Recompute the cached stats on a customer from their non-cancelled orders.
    Single source of truth — call after any order create / status change."""
    cust = await session.get(Customer, customer_id)
    if cust is None:
        return

    orders = list((await session.execute(
        select(Order)
        .where(Order.customer_id == customer_id, Order.status != "cancelled")
        .order_by(Order.created_at)
    )).scalars().all())

    cust.order_count = len(orders)
    cust.total_spent = float(sum(o.total or 0 for o in orders))
    cust.last_order_at = orders[-1].created_at if orders else None

    counts: dict[str, int] = {}
    for o in orders:
        for it in (o.items or []):
            name = (it.get("name") or "").strip()
            if not name:
                continue
            qty = int(it.get("quantity") or it.get("qty") or 1)
            counts[name] = counts.get(name, 0) + qty
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
    cust.top_items = [{"name": n, "count": c} for n, c in top]

    if len(orders) >= 2:
        dates = [o.created_at for o in orders]
        gaps = [(dates[i] - dates[i - 1]).total_seconds() / 86400 for i in range(1, len(dates))]
        cust.avg_cadence_days = sum(gaps) / len(gaps)
    else:
        cust.avg_cadence_days = None

    cust.stats_updated_at = datetime.utcnow()
    await session.flush()
```

(`Customer` and `Order` are already imported in order_service.py via `from models import Customer, Message, Order, Product`; `datetime` is already imported.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_customer_stats.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/services/order_service.py backend/tests/test_customer_stats.py
git commit -m "feat(customers): recompute_customer_stats + is_regular"
```

---

### Task 3: Recompute on order create + status change

**Files:**
- Modify: `backend/main.py` (`_process_tenant_messages` after `create_order`; `dashboard_update_order_status` after status set)
- Test: `backend/tests/test_webhook.py` (append)

**Interfaces:**
- Consumes: `recompute_customer_stats` from Task 2.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_webhook.py`:

```python
def test_order_updates_customer_stats(client, monkeypatch):
    async def fake_send(*a, **k):
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "AI_SERVICE_URL", "http://127.0.0.1:9")

    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_T", access_token="TKN_T")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})

    customer_message(client, "PNID_T", "628777", "pesan 2 nasi goreng")
    rows = client.get("/api/customers", headers=auth(t["access_token"])).json()
    assert len(rows) == 1
    assert rows[0]["order_count"] == 1
    assert rows[0]["total_spent"] == 28000
```

(This test also exercises the Task 5 `GET /api/customers` endpoint — implement Task 5 before running it green, or run just the recompute assertion via the DB. Order tasks 3→5; this test goes green at the end of Task 5. For Task 3 in isolation, run the full suite and confirm no regressions.)

- [ ] **Step 2: Add the recompute call after order creation**

In `backend/main.py`, in `_process_tenant_messages`, the block that creates an order currently reads:

```python
            if order_items:
                order = await create_order(session, business.id, customer.id, order_items)
                logger.info("Order #%d auto-extracted from message.", order.id)
```

Change it to recompute the customer's stats right after:

```python
            if order_items:
                order = await create_order(session, business.id, customer.id, order_items)
                logger.info("Order #%d auto-extracted from message.", order.id)
                try:
                    await recompute_customer_stats(session, customer.id)
                except Exception:
                    logger.exception("Failed to recompute stats for customer %d", customer.id)
```

- [ ] **Step 3: Add the recompute call after status change**

In `backend/main.py`, in `dashboard_update_order_status`, after `order.status = db_status` and the flush, recompute (a cancel must drop the order from stats):

```python
    order.status = db_status
    await session.flush()
    try:
        await recompute_customer_stats(session, order.customer_id)
    except Exception:
        logger.exception("Failed to recompute stats for customer %d", order.customer_id)
    return _order_to_dashboard_dict(order, customer.name or customer.phone_number)
```

- [ ] **Step 4: Import the function**

In `backend/main.py`, extend the `from services.order_service import (...)` block to include `recompute_customer_stats`:

```python
from services.order_service import (
    create_order,
    extract_order_from_message,
    get_daily_summary,
    get_or_create_customer,
    get_orders_for_business,
    recompute_customer_stats,
    save_message,
)
```

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `cd backend && uv run pytest -q`
Expected: all prior tests pass; `test_order_updates_customer_stats` may ERROR on the missing `/api/customers` route until Task 5 — that is expected. Everything else green.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/tests/test_webhook.py
git commit -m "feat(customers): recompute stats on order create + status change"
```

---

### Task 4: Customer API schemas

**Files:**
- Modify: `backend/schemas.py` (add three models)
- Test: covered by Task 5's endpoint tests.

**Interfaces:**
- Produces: `CustomerResponse`, `CustomerDetailResponse`, `CustomerUpdate`.

- [ ] **Step 1: Add the schemas**

In `backend/schemas.py`, add (near the other dashboard response models):

```python
# ── Customers (Kenal Langganan) ─────────────────────────────────────────────────
class CustomerResponse(BaseModel):
    id: int
    name: Optional[str] = None
    phone_number: str
    is_regular: bool
    order_count: int
    total_spent: float
    last_order_at: Optional[datetime.datetime] = None
    top_items: list = Field(default_factory=list)
    tags: list = Field(default_factory=list)


class CustomerDetailResponse(CustomerResponse):
    notes: Optional[str] = None
    is_regular_override: Optional[bool] = None
    avg_cadence_days: Optional[float] = None
    recent_orders: list = Field(default_factory=list)


class CustomerUpdate(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[list[str]] = None
    is_regular_override: Optional[bool] = None
```

(`BaseModel`, `Field`, `datetime`, `Optional` are already imported in schemas.py.)

- [ ] **Step 2: Sanity import check**

Run: `cd backend && uv run python -c "import schemas; print(schemas.CustomerDetailResponse.__fields__.keys())"`
Expected: prints the field names including `recent_orders`.

- [ ] **Step 3: Commit**

```bash
git add backend/schemas.py
git commit -m "feat(customers): response + update schemas"
```

---

### Task 5: Customer endpoints (list / detail / patch)

**Files:**
- Modify: `backend/main.py` (three endpoints + imports)
- Test: `backend/tests/test_customers_api.py` (new)

**Interfaces:**
- Consumes: `CustomerResponse, CustomerDetailResponse, CustomerUpdate` (Task 4), `is_regular` (Task 2).
- Produces: `GET /api/customers`, `GET /api/customers/{id}`, `PATCH /api/customers/{id}`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_customers_api.py`:

```python
"""Customer endpoints: scoping, update, bounds."""
import main
from helpers import register, connect_wa, customer_message, auth


def _setup(client, monkeypatch, pnid="PNID_C"):
    async def fake_send(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "AI_SERVICE_URL", "http://127.0.0.1:9")
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id=pnid, access_token="TKN")
    client.post("/api/products", headers=auth(t["access_token"]), json={"name": "Nasi Goreng", "price": 14000})
    return t


def test_list_and_detail(client, monkeypatch):
    t = _setup(client, monkeypatch)
    customer_message(client, "PNID_C", "628111", "pesan 2 nasi goreng")

    rows = client.get("/api/customers", headers=auth(t["access_token"])).json()
    assert len(rows) == 1
    cid = rows[0]["id"]
    assert rows[0]["order_count"] == 1 and rows[0]["total_spent"] == 28000

    detail = client.get(f"/api/customers/{cid}", headers=auth(t["access_token"])).json()
    assert detail["phone_number"] == "628111"
    assert len(detail["recent_orders"]) == 1


def test_patch_notes_and_override(client, monkeypatch):
    t = _setup(client, monkeypatch)
    customer_message(client, "PNID_C", "628111", "pesan 2 nasi goreng")
    cid = client.get("/api/customers", headers=auth(t["access_token"])).json()[0]["id"]

    r = client.patch(f"/api/customers/{cid}", headers=auth(t["access_token"]),
                     json={"notes": "tanpa pedas", "tags": ["alergi udang"], "is_regular_override": True})
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == "tanpa pedas" and body["tags"] == ["alergi udang"]
    assert body["is_regular"] is True  # override forces langganan


def test_tags_bound_rejected(client, monkeypatch):
    t = _setup(client, monkeypatch)
    customer_message(client, "PNID_C", "628111", "pesan 2 nasi goreng")
    cid = client.get("/api/customers", headers=auth(t["access_token"])).json()[0]["id"]
    r = client.patch(f"/api/customers/{cid}", headers=auth(t["access_token"]),
                     json={"tags": [f"t{i}" for i in range(11)]})
    assert r.status_code == 422


def test_cross_tenant_denied(client, monkeypatch):
    t1 = _setup(client, monkeypatch, pnid="PNID_A")
    customer_message(client, "PNID_A", "628111", "pesan 2 nasi goreng")
    cid = client.get("/api/customers", headers=auth(t1["access_token"])).json()[0]["id"]

    t2 = register(client, email="b@x.com", phone="082222222222")
    r = client.get(f"/api/customers/{cid}", headers=auth(t2["access_token"]))
    assert r.status_code == 404
    r = client.patch(f"/api/customers/{cid}", headers=auth(t2["access_token"]), json={"notes": "x"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_customers_api.py -q`
Expected: FAIL — 404 on `/api/customers` (route missing).

- [ ] **Step 3: Add imports**

In `backend/main.py`, add `is_regular` to the order_service import block and the three schemas to the schemas import block:

```python
from services.order_service import (
    create_order,
    extract_order_from_message,
    get_daily_summary,
    get_or_create_customer,
    get_orders_for_business,
    is_regular,
    recompute_customer_stats,
    save_message,
)
```

and in `from schemas import (...)` add:

```python
    CustomerResponse,
    CustomerDetailResponse,
    CustomerUpdate,
```

- [ ] **Step 4: Implement the endpoints**

In `backend/main.py`, add a new section after the orders endpoints (after `dashboard_update_order_status`, before the products section). Add a small builder + three routes:

```python
# ═══════════════════════════════════════════════════════════════════════════════
#  CUSTOMERS API (Kenal Langganan)
# ═══════════════════════════════════════════════════════════════════════════════

def _customer_to_dict(c: Customer) -> dict:
    return {
        "id": c.id,
        "name": None if (c.name or "") == c.phone_number else c.name,
        "phone_number": c.phone_number,
        "is_regular": is_regular(c),
        "order_count": c.order_count or 0,
        "total_spent": c.total_spent or 0.0,
        "last_order_at": c.last_order_at,
        "top_items": c.top_items or [],
        "tags": c.tags or [],
    }


@app.get("/api/customers", response_model=list[CustomerResponse])
async def dashboard_list_customers(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/customers — customers for this business, most recent first."""
    stmt = (
        select(Customer)
        .where(Customer.business_id == business.id)
        .order_by(Customer.last_order_at.desc().nullslast(), Customer.id.desc())
    )
    customers = (await session.execute(stmt)).scalars().all()
    return [_customer_to_dict(c) for c in customers]


@app.get("/api/customers/{customer_id}", response_model=CustomerDetailResponse)
async def dashboard_get_customer(
    customer_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/customers/{id} — profile + recent orders."""
    cust = (await session.execute(
        select(Customer).where(Customer.id == customer_id, Customer.business_id == business.id)
    )).scalar_one_or_none()
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found for this business.")

    orders = (await session.execute(
        select(Order).where(Order.customer_id == cust.id).order_by(Order.created_at.desc()).limit(10)
    )).scalars().all()

    data = _customer_to_dict(cust)
    data.update({
        "notes": cust.notes,
        "is_regular_override": cust.is_regular_override,
        "avg_cadence_days": cust.avg_cadence_days,
        "recent_orders": [_order_to_dashboard_dict(o, cust.name or cust.phone_number) for o in orders],
    })
    return data


@app.patch("/api/customers/{customer_id}", response_model=CustomerDetailResponse)
async def dashboard_update_customer(
    customer_id: int,
    body: CustomerUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """PATCH /api/customers/{id} — update owner notes / tags / loyalty override."""
    cust = (await session.execute(
        select(Customer).where(Customer.id == customer_id, Customer.business_id == business.id)
    )).scalar_one_or_none()
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found for this business.")

    if body.tags is not None:
        if len(body.tags) > 10 or any(len(t) > 60 for t in body.tags):
            raise HTTPException(status_code=422, detail="Maks 10 tag, tiap tag ≤ 60 karakter.")
        cust.tags = body.tags
    if body.notes is not None:
        cust.notes = body.notes
    if body.is_regular_override is not None:
        cust.is_regular_override = body.is_regular_override
    await session.flush()

    orders = (await session.execute(
        select(Order).where(Order.customer_id == cust.id).order_by(Order.created_at.desc()).limit(10)
    )).scalars().all()
    data = _customer_to_dict(cust)
    data.update({
        "notes": cust.notes,
        "is_regular_override": cust.is_regular_override,
        "avg_cadence_days": cust.avg_cadence_days,
        "recent_orders": [_order_to_dashboard_dict(o, cust.name or cust.phone_number) for o in orders],
    })
    return data
```

Note: `is_regular_override` of `False` is a real value the PATCH must store; `CustomerUpdate` sends `None` only when the field is omitted, so `if body.is_regular_override is not None` is correct.

- [ ] **Step 5: Run the customer + webhook tests**

Run: `cd backend && uv run pytest tests/test_customers_api.py tests/test_webhook.py -q`
Expected: PASS (all, including `test_order_updates_customer_stats` from Task 3).

- [ ] **Step 6: Run the full suite**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/main.py backend/tests/test_customers_api.py
git commit -m "feat(customers): list / detail / patch endpoints"
```

---

### Task 6: AI customer card injection + guardrail

**Files:**
- Modify: `backend/main.py` (`_build_customer_card`, thread into `_process_tenant_messages` + `_generate_ai_reply`)
- Modify: `ai/ai_service.py` (`ReplyRequest.customer`, pass to `generate_reply`)
- Modify: `ai/conversation.py` (`generate_reply` + `_llm_reply` accept + render `customer`)
- Test: `backend/tests/test_customer_card.py` (new, backend builder) + `ai` self-check

**Interfaces:**
- Consumes: `is_regular` (Task 2), `Customer` cache (Task 1).
- Produces: backend `_build_customer_card(cust) -> Optional[dict]`; AI `ReplyRequest.customer`; `generate_reply(..., customer=None)`.

- [ ] **Step 1: Write the failing test (backend builder)**

Create `backend/tests/test_customer_card.py`:

```python
"""The customer card must never fabricate for unknown customers."""
import datetime as dt
import main
from models import Customer


def _c(**kw):
    base = dict(id=1, phone_number="628111", name="628111", business_id=1,
                notes=None, tags=[], is_regular_override=None, order_count=0,
                total_spent=0.0, last_order_at=None, top_items=[], avg_cadence_days=None)
    base.update(kw)
    c = Customer.__new__(Customer)
    for k, v in base.items():
        setattr(c, k, v)
    return c


def test_new_unknown_customer_gets_no_card():
    assert main._build_customer_card(_c()) is None


def test_known_regular_customer_card():
    c = _c(name="Budi", order_count=8, top_items=[{"name": "Nasi Goreng", "count": 9}],
           last_order_at=dt.datetime(2026, 6, 1), avg_cadence_days=5.0, tags=["tanpa pedas"])
    card = main._build_customer_card(c)
    assert card["name"] == "Budi"
    assert card["is_regular"] is True
    assert card["usual_items"] == ["Nasi Goreng"]
    assert card["tags"] == ["tanpa pedas"]


def test_card_present_for_named_customer_without_orders():
    # A customer the owner named/annotated but who hasn't ordered yet still gets a card.
    c = _c(name="Budi", notes="langganan lama")
    card = main._build_customer_card(c)
    assert card is not None and card["name"] == "Budi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_customer_card.py -q`
Expected: FAIL — `AttributeError: module 'main' has no attribute '_build_customer_card'`.

- [ ] **Step 3: Implement the backend builder**

In `backend/main.py`, add near `_order_to_dashboard_dict`:

```python
def _build_customer_card(cust: Customer) -> Optional[dict]:
    """Compact personalisation context for the AI. Returns None for an unknown
    customer (no real name, no orders, no notes/tags) so the AI never fabricates."""
    name = (cust.name or "").strip()
    known_name = bool(name) and name != cust.phone_number
    if (cust.order_count or 0) == 0 and not known_name and not cust.notes and not (cust.tags or []):
        return None

    card: dict = {"order_count": cust.order_count or 0, "is_regular": is_regular(cust)}
    if known_name:
        card["name"] = name
    if cust.top_items:
        card["usual_items"] = [t["name"] for t in cust.top_items]
    if cust.last_order_at:
        card["last_order_at"] = cust.last_order_at.isoformat()
        if cust.avg_cadence_days:
            due = cust.last_order_at + timedelta(days=cust.avg_cadence_days)
            card["reorder_due"] = datetime.utcnow() > due
            card["avg_cadence_days"] = round(cust.avg_cadence_days, 1)
    if cust.notes:
        card["notes"] = cust.notes
    if cust.tags:
        card["tags"] = cust.tags
    return card
```

(`Optional`, `datetime`, `timedelta` already imported in main.py.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_customer_card.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Thread the card into the AI call**

In `backend/main.py`, change `_generate_ai_reply`'s signature to accept the customer and send the card. The function signature becomes:

```python
async def _generate_ai_reply(
    session: AsyncSession,
    business: Business,
    session_id: str,
    message_text: str,
    extracted_order: Optional[list[dict]] = None,
    customer: Optional[Customer] = None,
) -> str:
```

Inside it, after `payload` is built, add the card:

```python
    if customer is not None:
        card = _build_customer_card(customer)
        if card is not None:
            payload["customer"] = card
```

And in `_process_tenant_messages`, pass the customer in:

```python
            reply = await _generate_ai_reply(session, business, customer.phone_number, text, order_items or None, customer=customer)
```

- [ ] **Step 6: Accept `customer` in the AI service**

In `ai/ai_service.py`, add the field to `ReplyRequest`:

```python
    customer: Optional[dict] = Field(default=None, description="Personalisation card {name, usual_items, ...}")
```

and pass it through in `ai_reply`:

```python
        reply = generate_reply(
            session_id=request.session_id,
            incoming_message=request.incoming_message,
            business_context=request.business_context,
            catalog=request.catalog,
            customer=request.customer,
        )
```

- [ ] **Step 7: Render the card in the prompt**

In `ai/conversation.py`, change `generate_reply` to accept and forward `customer`:

```python
def generate_reply(session_id: str, incoming_message: str,
                   business_context: Optional[dict] = None,
                   catalog: Optional[list[dict]] = None,
                   customer: Optional[dict] = None) -> str:
```

Inside `generate_reply`, where it currently calls `_llm_reply(conv, intent, business_context)`, change to:

```python
    if response is None:
        # Let LLM handle it
        response = _llm_reply(conv, intent, business_context, customer)
```

Change `_llm_reply`'s signature and inject the card block into `extra_context` (right before the `system_prompt` string is assembled):

```python
def _llm_reply(conv: Conversation, intent: str, business_context: Optional[dict],
               customer: Optional[dict] = None) -> str:
```

and, inside it, after the `if conv.order.active:` block that appends the current order, add:

```python
    if customer:
        lines = []
        if customer.get("name"):
            tag = " (langganan)" if customer.get("is_regular") else ""
            lines.append(f"- Nama: {customer['name']}{tag}, {customer.get('order_count', 0)} order")
        if customer.get("usual_items"):
            lines.append("- Biasa pesan: " + ", ".join(customer["usual_items"]))
        if customer.get("reorder_due"):
            lines.append(f"- Sudah waktunya order lagi (biasanya tiap ~{customer.get('avg_cadence_days')} hari)")
        if customer.get("notes"):
            lines.append(f"- Catatan: {customer['notes']}")
        if customer.get("tags"):
            lines.append("- Preferensi: " + "; ".join(customer["tags"]))
        if lines:
            extra_context += (
                "\n\nPELANGGAN (pakai untuk menyapa akrab & menawarkan pesanan biasanya; "
                "JANGAN mengarang data pelanggan di luar ini):\n" + "\n".join(lines)
            )
```

- [ ] **Step 8: AI self-check (offline)**

Run:

```bash
cd ai && PYTHONIOENCODING=utf-8 uv run python -c "
import conversation as c, llm
llm.ask_llm = lambda *a, **k: 'OK'
c.ask_llm = lambda *a, **k: 'OK'
# customer card flows through without error and is ignored safely when None
print(c.generate_reply('s1', 'halo', None, [{'name':'Nasi Goreng','price':14000}], customer={'name':'Budi','is_regular':True,'order_count':8,'usual_items':['Nasi Goreng']}))
print(c.generate_reply('s2', 'halo', None, None, customer=None))
print('AI card wiring OK')
"
```

Expected: prints two replies then `AI card wiring OK` with no exception.

- [ ] **Step 9: Run the full backend suite**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add backend/main.py backend/tests/test_customer_card.py ai/ai_service.py ai/conversation.py
git commit -m "feat(ai): inject customer card into replies with anti-fabrication guardrail"
```

---

### Task 7: Dashboard Pelanggan page + nav

**Files:**
- Modify: `dashboard/src/lib/types.ts` (Customer types)
- Modify: `dashboard/src/lib/api.ts` (customer methods)
- Modify: `dashboard/src/lib/queries.ts` (hooks)
- Create: `dashboard/src/pages/Customers.tsx`
- Modify: `dashboard/src/router.tsx` (route)
- Modify: `dashboard/src/components/BottomNav.tsx` (Koneksi → Settings, add Pelanggan)
- Modify: `dashboard/src/pages/Settings.tsx` (add a "Koneksi WhatsApp" link card)

**Interfaces:**
- Consumes: `GET/PATCH /api/customers` (Task 5).

- [ ] **Step 1: Add types**

In `dashboard/src/lib/types.ts`, add:

```typescript
export interface Customer {
  id: number;
  name: string | null;
  phone_number: string;
  is_regular: boolean;
  order_count: number;
  total_spent: number;
  last_order_at: string | null;
  top_items: { name: string; count: number }[];
  tags: string[];
}

export interface CustomerDetail extends Customer {
  notes: string | null;
  is_regular_override: boolean | null;
  avg_cadence_days: number | null;
  recent_orders: Order[];
}
```

(`Order` is already exported from types.ts.)

- [ ] **Step 2: Add api methods**

In `dashboard/src/lib/api.ts`, import the types and add methods in the `api` object after the WhatsApp section:

```typescript
  // ── Customers ──
  customers: () => req<Customer[]>("/api/customers"),
  customer: (id: number) => req<CustomerDetail>(`/api/customers/${id}`),
  updateCustomer: (id: number, d: { notes?: string; tags?: string[]; is_regular_override?: boolean }) =>
    req<CustomerDetail>(`/api/customers/${id}`, { method: "PATCH", ...body(d) }),
```

Add `Customer, CustomerDetail` to the type import at the top of api.ts.

- [ ] **Step 3: Add query hooks**

In `dashboard/src/lib/queries.ts`, add to `keys`: `customers: ["customers"] as const, customer: (id: number) => ["customer", id] as const,` and add hooks:

```typescript
export const useCustomers = () => useQuery({ queryKey: keys.customers, queryFn: api.customers });
export const useCustomer = (id: number) =>
  useQuery({ queryKey: keys.customer(id), queryFn: () => api.customer(id) });

export function useUpdateCustomer(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: { notes?: string; tags?: string[]; is_regular_override?: boolean }) => api.updateCustomer(id, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.customer(id) });
      qc.invalidateQueries({ queryKey: keys.customers });
    },
  });
}
```

- [ ] **Step 4: Create the Pelanggan page**

Create `dashboard/src/pages/Customers.tsx`:

```tsx
import { useState } from "react";
import { useCustomers, useCustomer, useUpdateCustomer } from "../lib/queries";
import { fmtRp } from "../lib/format";
import { ApiError } from "../lib/api";
import { Button, Card, ErrorBox, PageTitle, Spinner, inputCls } from "../components/ui";
import type { Customer } from "../lib/types";

function rel(iso: string | null): string {
  if (!iso) return "belum pernah order";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return "hari ini";
  if (days === 1) return "kemarin";
  return `${days} hari lalu`;
}

function Detail({ id, onBack }: { id: number; onBack: () => void }) {
  const { data, isLoading } = useCustomer(id);
  const upd = useUpdateCustomer(id);
  const [notes, setNotes] = useState<string | null>(null);
  const [tagInput, setTagInput] = useState("");

  if (isLoading || !data) return <Spinner />;
  const notesVal = notes ?? data.notes ?? "";
  const tags = data.tags ?? [];

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-sm font-semibold text-ink/55">← Kembali</button>

      <section className="rounded-[24px] bg-ink p-5 text-white shadow-[0_8px_24px_rgba(12,31,23,0.18)]">
        <div className="flex items-center justify-between">
          <p className="font-display text-xl font-extrabold">{data.name ?? data.phone_number}</p>
          {data.is_regular && <span className="rounded-full bg-gold/20 px-2.5 py-1 text-xs font-bold text-gold">Langganan</span>}
        </div>
        <p className="mt-1 text-sm text-white/55">{data.order_count} order • {rel(data.last_order_at)}</p>
        <p className="tnum mt-3 font-display text-3xl font-extrabold text-gold">{fmtRp(data.total_spent)}</p>
        <p className="text-xs text-white/55">total belanja</p>
      </section>

      {data.top_items.length > 0 && (
        <Card>
          <h2 className="mb-2 font-display text-base font-bold text-ink">Item favorit</h2>
          <div className="flex flex-wrap gap-2">
            {data.top_items.map((t) => (
              <span key={t.name} className="rounded-full bg-brand-tint px-3 py-1 text-sm font-semibold text-brand-deep">
                {t.name} · {t.count}×
              </span>
            ))}
          </div>
        </Card>
      )}

      <Card className="space-y-3">
        <h2 className="font-display text-base font-bold text-ink">Catatan & preferensi</h2>
        <textarea
          className={`${inputCls} min-h-[4rem] py-2`}
          value={notesVal}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="mis. tanpa pedas, alamat antar, alergi udang"
        />
        <div className="flex flex-wrap gap-2">
          {tags.map((tg) => (
            <span key={tg} className="flex items-center gap-1 rounded-full bg-ink/5 px-3 py-1 text-sm text-ink/70">
              {tg}
              <button onClick={() => upd.mutate({ tags: tags.filter((x) => x !== tg) })} className="text-ink/40">×</button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input className={inputCls} value={tagInput} onChange={(e) => setTagInput(e.target.value)} placeholder="Tambah tag" />
          <Button
            variant="ghost"
            onClick={() => {
              const tg = tagInput.trim();
              if (tg && !tags.includes(tg)) upd.mutate({ tags: [...tags, tg] });
              setTagInput("");
            }}
          >
            Tambah
          </Button>
        </div>
        <label className="flex items-center justify-between">
          <span className="font-semibold text-ink">Tandai langganan</span>
          <input
            type="checkbox"
            className="h-5 w-9 accent-brand"
            checked={data.is_regular_override ?? data.is_regular}
            onChange={(e) => upd.mutate({ is_regular_override: e.target.checked })}
          />
        </label>
        <Button onClick={() => upd.mutate({ notes: notesVal })} disabled={upd.isPending}>
          {upd.isPending ? "..." : "Simpan catatan"}
        </Button>
      </Card>
    </div>
  );
}

export default function Customers() {
  const { data, isLoading, error } = useCustomers();
  const [openId, setOpenId] = useState<number | null>(null);

  if (openId !== null) return <Detail id={openId} onBack={() => setOpenId(null)} />;

  return (
    <div>
      <PageTitle>Pelanggan</PageTitle>
      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}
      {data && data.length === 0 && (
        <Card><p className="text-sm text-ink/55">Belum ada pelanggan. Mereka muncul di sini setelah chat pertama.</p></Card>
      )}
      <div className="space-y-2">
        {data?.map((c: Customer) => (
          <button key={c.id} onClick={() => setOpenId(c.id)} className="w-full text-left">
            <Card className="flex items-center justify-between !p-4">
              <div className="min-w-0">
                <p className="flex items-center gap-2 font-semibold text-ink">
                  <span className="truncate">{c.name ?? c.phone_number}</span>
                  {c.is_regular && <span className="shrink-0 rounded-full bg-gold/15 px-2 py-0.5 text-[0.65rem] font-bold text-[#9a7400]">Langganan</span>}
                </p>
                <p className="mt-0.5 text-xs text-ink/45">{c.order_count} order • {rel(c.last_order_at)}</p>
              </div>
              <span className="tnum shrink-0 pl-2 font-bold text-ink">{fmtRp(c.total_spent)}</span>
            </Card>
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Register the route**

In `dashboard/src/router.tsx`, add the import and route:

```typescript
import Customers from "./pages/Customers";
```
```typescript
const customersRoute = createRoute({ getParentRoute: () => rootRoute, path: "/customers", component: Customers });
```
and include `customersRoute` in `rootRoute.addChildren([...])`.

- [ ] **Step 6: Update the bottom nav (keep 5 items)**

Replace the `items` array in `dashboard/src/components/BottomNav.tsx` — drop "Koneksi", add "Pelanggan":

```typescript
const items = [
  { to: "/", icon: "🏠", label: "Beranda" },
  { to: "/orders", icon: "🧾", label: "Pesanan" },
  { to: "/customers", icon: "👥", label: "Pelanggan" },
  { to: "/catalog", icon: "🏪", label: "Katalog" },
  { to: "/settings", icon: "💬", label: "Auto-Balas" },
] as const;
```

- [ ] **Step 7: Add a Koneksi link in Settings**

In `dashboard/src/pages/Settings.tsx`, add a `Link` import from `@tanstack/react-router` and a card at the top of the returned list (right under `<PageTitle>Auto-Balas</PageTitle>`):

```tsx
      <Card>
        <Link to="/whatsapp" className="flex items-center justify-between">
          <span>
            <span className="block font-semibold text-ink">Koneksi WhatsApp</span>
            <span className="block text-sm text-ink/50">Hubungkan / cek status nomor bisnis.</span>
          </span>
          <span className="text-ink/30" aria-hidden>→</span>
        </Link>
      </Card>
```

- [ ] **Step 8: Typecheck + build**

Run: `cd dashboard && bunx tsc --noEmit`
Expected: 0 errors.

Run: `cd dashboard && bunx vite build`
Expected: build succeeds.

- [ ] **Step 9: Commit**

```bash
git add dashboard/src
git commit -m "feat(dashboard): Pelanggan page + nav (Koneksi moved into Settings)"
```

---

## Self-Review

**Spec coverage:**
- Schema columns → Task 1. ✓
- `recompute_customer_stats` + loyalty derivation → Task 2. ✓
- Recompute on create + status change → Task 3. ✓
- Customer card + anti-fabrication guardrail + reorder-due (reactive) → Task 6. ✓
- Pelanggan page (list + detail + notes/tags/override), nav 5 items (Koneksi → Settings) → Task 7. ✓
- Endpoints GET/GET{id}/PATCH scoped + bounds → Tasks 4–5. ✓
- Edge cases: new customer empty card (T6), name==phone neutral (T5 `_customer_to_dict`, T6 builder), cancelled excluded (T2), tags bound (T5), cross-tenant 404 (T5), recompute failure non-blocking (T3). ✓
- Out of scope items are not implemented. ✓

**Placeholder scan:** none — every code/test/command step is concrete.

**Type consistency:** `recompute_customer_stats(session, customer_id)`, `is_regular(cust)`, `_build_customer_card(cust)`, `_customer_to_dict(c)`, `generate_reply(..., customer=None)`, `_llm_reply(conv, intent, business_context, customer=None)`, `ReplyRequest.customer`, and the TS `Customer`/`CustomerDetail` shapes match across tasks.
