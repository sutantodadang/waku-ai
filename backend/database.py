"""
Database setup — SQLAlchemy async engine and session factory.
Uses SQLite by default (via aiosqlite for async support).
"""
from __future__ import annotations

import os
import logging
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
