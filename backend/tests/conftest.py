"""Pytest fixtures for the Waku backend (PostgreSQL via testcontainers)."""
import asyncio
import atexit
import os

from cryptography.fernet import Fernet
from testcontainers.postgres import PostgresContainer

# ── Start a throwaway Postgres for the whole test session ─────────────────────
_pg = PostgresContainer("postgres:18-alpine")
_pg.start()
atexit.register(_pg.stop)
_host = _pg.get_container_host_ip()
_port = _pg.get_exposed_port(5432)

# ── Configure env BEFORE importing app modules ───────────────────────────────
os.environ["DATABASE_URL"] = (
    f"postgresql+asyncpg://{_pg.username}:{_pg.password}@{_host}:{_port}/{_pg.dbname}"
)
os.environ["DB_DISABLE_POOL"] = "1"  # NullPool — each connection is loop-local
os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long-abcdef")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ["PLATFORM_PHONE_NUMBER_ID"] = "PLATFORM_TEST"
os.environ["APP_SECRET"] = ""  # webhook signature runs in dev skip-mode for tests

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.api.routers import webhook  # noqa: E402
from app.core.database import Base, engine  # noqa: E402


async def _reset_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture()
def client():
    """Fresh schema + app per test."""
    asyncio.run(_reset_schema())
    webhook.PLATFORM_PHONE_NUMBER_ID = "PLATFORM_TEST"
    with TestClient(main.app) as c:
        yield c
