"""Idempotent SQLite migration upgrades an old-schema DB in place without data loss."""
import sqlite3

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import models  # noqa: F401  (populates Base.metadata)
from app.core.database import Base, _run_migrations


async def test_migration_upgrades_old_db_in_place(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE businesses ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "phone_number VARCHAR(32) UNIQUE NOT NULL, "
        "business_name VARCHAR(255) NOT NULL, "
        "settings JSON, "
        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    con.execute("INSERT INTO businesses (phone_number, business_name) VALUES ('0810', 'Toko Lama')")
    con.commit()
    con.close()

    eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_run_migrations)
            await conn.run_sync(_run_migrations)  # idempotent — second run must not error
        async with eng.connect() as conn:
            cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(businesses)"))).all()}
            assert {"phone_number_id", "waba_id", "access_token", "is_connected"} <= cols
            name = (await conn.execute(text("SELECT business_name FROM businesses WHERE phone_number='0810'"))).scalar()
            assert name == "Toko Lama"  # existing data preserved
            tables = {r[0] for r in (await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))).all()}
            assert {"users", "otp_verifications"} <= tables
    finally:
        await eng.dispose()
