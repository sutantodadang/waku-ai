"""
Database setup — SQLAlchemy async engine and session factory.
Uses SQLite by default (via aiosqlite for async support).
"""
from __future__ import annotations

import os
import logging
from typing import AsyncGenerator

from dotenv import load_dotenv
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


async def init_db() -> None:
    """Create all tables.  Safe to call on every startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created (if not already present).")


async def close_db() -> None:
    """Dispose of the engine (call on shutdown)."""
    await engine.dispose()
    logger.info("Database engine disposed.")
