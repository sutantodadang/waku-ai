"""
Database setup — SQLAlchemy async engine and session factory.
Uses SQLite by default (via aiosqlite for async support).
"""
from __future__ import annotations

import os
import logging

from app.core.ids import uuid7
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

logger = logging.getLogger(__name__)

# ── Connection ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./waku.db",
)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


# ── Base ────────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Helpers ─────────────────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# New columns added to the pre-existing `businesses` table. create_all does NOT
# alter existing tables, so we add them idempotently here. SQLite only.
_BUSINESS_NEW_COLUMNS: dict[str, str] = {
    "phone_number_id": "VARCHAR(64)",
    "waba_id": "VARCHAR(64)",
    "access_token": "VARCHAR(512)",
    "is_connected": "BOOLEAN DEFAULT 0 NOT NULL",
}

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

_PRODUCT_NEW_COLUMNS: dict[str, str] = {
    "embedding": "JSON",
    "embedding_hash": "VARCHAR(64)",
}

_BUSINESS_PAYMENT_COLUMNS: dict[str, str] = {
    "payment_methods": "JSON",
    "qris_image_url": "VARCHAR(512)",
}

_BUSINESS_TYPE_COLUMN: dict[str, str] = {
    "business_type": "VARCHAR(16) DEFAULT 'warung' NOT NULL",
}

_PRODUCT_DURATION_COLUMN: dict[str, str] = {
    "duration_minutes": "INTEGER",
}

_MESSAGE_MEDIA_COLUMN: dict[str, str] = {"media_url": "VARCHAR(512)"}


def _run_migrations(sync_conn) -> None:
    """Idempotent schema top-up for existing databases (SQLite)."""
    if sync_conn.dialect.name != "sqlite":
        return
    insp = inspect(sync_conn)
    if "businesses" not in insp.get_table_names():
        return  # fresh DB — create_all already built it correctly
    existing = {c["name"] for c in insp.get_columns("businesses")}
    for name, ddl in _BUSINESS_NEW_COLUMNS.items():
        if name not in existing:
            sync_conn.exec_driver_sql(f"ALTER TABLE businesses ADD COLUMN {name} {ddl}")
            logger.info("Migration: added businesses.%s", name)
    # Enforce uniqueness on the routing id (NULLs allowed) for migrated tables.
    sync_conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_businesses_phone_number_id "
        "ON businesses(phone_number_id)"
    )
    # customers: Kenal Langganan columns
    if "customers" in insp.get_table_names():
        cust_existing = {c["name"] for c in insp.get_columns("customers")}
        for name, ddl in _CUSTOMER_NEW_COLUMNS.items():
            if name not in cust_existing:
                sync_conn.exec_driver_sql(f"ALTER TABLE customers ADD COLUMN {name} {ddl}")
                logger.info("Migration: added customers.%s", name)
    # products: Phase B retrieval cache
    if "products" in insp.get_table_names():
        prod_existing = {c["name"] for c in insp.get_columns("products")}
        for name, ddl in _PRODUCT_NEW_COLUMNS.items():
            if name not in prod_existing:
                sync_conn.exec_driver_sql(f"ALTER TABLE products ADD COLUMN {name} {ddl}")
                logger.info("Migration: added products.%s", name)
        # products: Phase C booking duration
        for name, ddl in _PRODUCT_DURATION_COLUMN.items():
            if name not in prod_existing:
                sync_conn.exec_driver_sql(f"ALTER TABLE products ADD COLUMN {name} {ddl}")
                logger.info("Migration: added products.%s", name)
    # businesses: Phase B payment columns
    biz_existing = {c["name"] for c in insp.get_columns("businesses")}
    for name, ddl in _BUSINESS_PAYMENT_COLUMNS.items():
        if name not in biz_existing:
            sync_conn.exec_driver_sql(f"ALTER TABLE businesses ADD COLUMN {name} {ddl}")
            logger.info("Migration: added businesses.%s", name)
    # businesses: Phase C business type
    for name, ddl in _BUSINESS_TYPE_COLUMN.items():
        if name not in biz_existing:
            sync_conn.exec_driver_sql(f"ALTER TABLE businesses ADD COLUMN {name} {ddl}")
            logger.info("Migration: added businesses.%s", name)
    # messages: inbound media URL
    if "messages" in insp.get_table_names():
        msg_existing = {c["name"] for c in insp.get_columns("messages")}
        for name, ddl in _MESSAGE_MEDIA_COLUMN.items():
            if name not in msg_existing:
                sync_conn.exec_driver_sql(f"ALTER TABLE messages ADD COLUMN {name} {ddl}")
                logger.info("Migration: added messages.%s", name)
    # orders: migrate legacy integer PK → UUIDv7 string PK + per-business order_seq.
    if "orders" in insp.get_table_names():
        ord_cols = {c["name"]: str(c["type"]).upper() for c in insp.get_columns("orders")}
        id_type = ord_cols.get("id", "")
        if "INT" in id_type:
            legacy = sync_conn.exec_driver_sql(
                "SELECT id, business_id, customer_id, items, total, status, created_at "
                "FROM orders ORDER BY business_id, created_at, id"
            ).fetchall()
            sync_conn.exec_driver_sql("ALTER TABLE orders RENAME TO orders_legacy")
            sync_conn.exec_driver_sql(
                "CREATE TABLE orders ("
                "id VARCHAR(36) PRIMARY KEY, "
                "business_id INTEGER NOT NULL, "
                "customer_id INTEGER NOT NULL, "
                "order_seq INTEGER NOT NULL DEFAULT 0, "
                "items JSON NOT NULL, "
                "total FLOAT, "
                "status VARCHAR(32), "
                "created_at DATETIME NOT NULL)"
            )
            seq_by_biz: dict[int, int] = {}
            for r in legacy:
                biz = r[1]
                seq_by_biz[biz] = seq_by_biz.get(biz, 0) + 1
                sync_conn.exec_driver_sql(
                    "INSERT INTO orders "
                    "(id, business_id, customer_id, order_seq, items, total, status, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (uuid7(), r[1], r[2], seq_by_biz[biz], r[3], r[4], r[5], r[6]),
                )
            sync_conn.exec_driver_sql("DROP TABLE orders_legacy")
            logger.info("Migration: rebuilt orders with UUIDv7 PK + order_seq (%d rows)", len(legacy))
        elif "order_seq" not in ord_cols:
            sync_conn.exec_driver_sql("ALTER TABLE orders ADD COLUMN order_seq INTEGER NOT NULL DEFAULT 0")
            logger.info("Migration: added orders.order_seq")
        sync_conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_business_seq ON orders(business_id, order_seq)"
        )


async def init_db() -> None:
    """Create all tables + run idempotent migrations.  Safe to call on every startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_migrations)
    logger.info("Database tables created + migrations applied (if needed).")


async def close_db() -> None:
    """Dispose of the engine (call on shutdown)."""
    await engine.dispose()
    logger.info("Database engine disposed.")
