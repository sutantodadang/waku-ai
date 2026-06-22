"""Customer recognition: cached stats + recompute."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import models  # noqa: F401  (populates Base.metadata)
from database import Base, _run_migrations
from models import Business, Customer


@pytest.fixture
async def db_engine(tmp_path):
    """Fresh in-memory DB per test."""
    db = tmp_path / "test.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db}")

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_migrations)

    yield test_engine

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_customer_has_new_columns_with_defaults(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with session_factory() as s:
        biz = Business(phone_number="0810000000", business_name="T")
        s.add(biz)
        await s.flush()
        cust = Customer(phone_number="628999", business_id=biz.id, name="628999")
        s.add(cust)
        await s.flush()
        cid = cust.id
        await s.commit()

    async with session_factory() as s:
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
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with session_factory() as s:
        biz = Business(phone_number="0810000001", business_name="T2")
        s.add(biz)
        await s.flush()
        cust = Customer(phone_number="628998", business_id=biz.id, name="628998", notes="tanpa pedas", tags=["alergi udang"])
        s.add(cust)
        await s.flush()
        cid = cust.id
        await s.commit()

    async with session_factory() as s:
        c = (await s.execute(select(Customer).where(Customer.id == cid))).scalar_one()
        assert c.notes == "tanpa pedas"
        assert c.tags == ["alergi udang"]
