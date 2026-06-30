"""Pytest fixtures for the Waku backend.

Env is set BEFORE importing the app so the module-global engine, crypto key, and
JWT secret are configured. Each `client` test gets a fresh on-disk SQLite DB.
"""
import os

from cryptography.fernet import Fernet

# ── Configure env before importing app modules ───────────────────────────────
DB_FILE = os.path.join(os.path.dirname(__file__), "_pytest.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_FILE}"
os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long-abcdef")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ["PLATFORM_PHONE_NUMBER_ID"] = "PLATFORM_TEST"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402


@pytest.fixture()
def client():
    """Fresh DB + app per test. Lifespan runs init_db (create_all + migrations)."""
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    # webhook routing compares against this module global
    main.PLATFORM_PHONE_NUMBER_ID = "PLATFORM_TEST"
    with TestClient(main.app) as c:
        yield c
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
