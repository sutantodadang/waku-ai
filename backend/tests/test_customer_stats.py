"""Customer recognition: cached stats + recompute."""
import asyncio
from datetime import datetime

import pytest
from sqlalchemy import func, select

from app import models  # noqa: F401  (populates Base.metadata)
from app.core.database import Base, engine, async_session_factory
from app.models import Business, Customer, Order
from app.services.order_service import recompute_customer_stats, is_regular, REGULAR_THRESHOLD


@pytest.fixture
def db_engine():
    """Reset schema per test on the shared Postgres instance."""
    async def _reset():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(_reset())
    yield engine


_test_counter = 0


def _mk_customer():
    """Create a test business and customer, return (business_id, customer_id)."""
    global _test_counter
    _test_counter += 1

    async def run():
        async with async_session_factory() as s:
            biz = Business(phone_number=f"081000000{_test_counter:02d}", business_name=f"TestBiz{_test_counter}")
            s.add(biz)
            await s.flush()
            bid = biz.id
            cust = Customer(phone_number=f"62899{_test_counter:04d}", business_id=bid, name=f"62899{_test_counter:04d}")
            s.add(cust)
            await s.flush()
            cid = cust.id
            await s.commit()
            return bid, cid

    return asyncio.run(run())


def _seed_orders(business_id, cid, specs):
    """specs: list of (total, status, created_at, items)."""
    async def run():
        async with async_session_factory() as s:
            next_seq = (await s.execute(
                select(func.coalesce(func.max(Order.order_seq), 0) + 1).where(Order.business_id == business_id)
            )).scalar_one()
            for total, status, created, items in specs:
                o = Order(business_id=business_id, customer_id=cid, order_seq=next_seq, items=items, total=total, status=status)
                next_seq += 1
                s.add(o)
                await s.flush()
                o.created_at = created  # override server default for deterministic cadence
            await s.commit()

    asyncio.run(run())


@pytest.mark.asyncio
async def test_customer_has_new_columns_with_defaults(db_engine):
    async with async_session_factory() as s:
        biz = Business(phone_number="0810000000", business_name="T")
        s.add(biz)
        await s.flush()
        cust = Customer(phone_number="628999", business_id=biz.id, name="628999")
        s.add(cust)
        await s.flush()
        cid = cust.id
        await s.commit()

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


@pytest.mark.asyncio
async def test_customer_accepts_notes_and_tags(db_engine):
    async with async_session_factory() as s:
        biz = Business(phone_number="0810000001", business_name="T2")
        s.add(biz)
        await s.flush()
        cust = Customer(phone_number="628998", business_id=biz.id, name="628998", notes="tanpa pedas", tags=["alergi udang"])
        s.add(cust)
        await s.flush()
        cid = cust.id
        await s.commit()

    async with async_session_factory() as s:
        c = (await s.execute(select(Customer).where(Customer.id == cid))).scalar_one()
        assert c.notes == "tanpa pedas"
        assert c.tags == ["alergi udang"]


def test_recompute_counts_excludes_cancelled(db_engine):
    bid, cid = _mk_customer()
    _seed_orders(bid, cid, [
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


def test_single_order_has_null_cadence(db_engine):
    bid, cid = _mk_customer()
    _seed_orders(bid, cid, [(14000.0, "completed", datetime(2026, 6, 1, 10), [{"name": "Nasi Goreng", "quantity": 1}])])

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
